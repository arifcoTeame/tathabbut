"""Orchestration: text -> claims -> retrieval -> alignment -> deterministic verdict -> JSON."""
from __future__ import annotations

import time

from . import dorar_live, extractor
from .arabic import key_tokens
from .index import HybridIndex
from .judge import VERDICTS, Judgement, Thresholds, judge

ENGINE_VERSION = "0.10.0"
DISCLAIMER = "تثبّت أداة مدعومة بالذكاء الاصطناعي ولا تُغني عن المختص. النص الشرعي منسوخ من الفهرس، والدرجات منقولة عن المحدّثين كما هي مسجّلة في المصدر."


def _source_url(doc, quran_link: str) -> str:
    if doc.url:
        return doc.url
    if doc.kind == "quran":
        return quran_link.format(surah=doc.ref.get("surah"), ayah=doc.ref.get("ayah"), gid=doc.ref.get("gid", ""))
    return ""


def _ayah_label(ref: dict) -> str:
    a, b = ref.get("ayah"), ref.get("ayah_end")
    return f"سورة {ref.get('surah_name')}، الآية {a}" if not b else f"سورة {ref.get('surah_name')}، الآيات {a}–{b}"


def _source(doc, quran_link: str) -> dict:
    return {
        "id": doc.id,
        "kind": doc.kind,
        "text": doc.text,
        "ref": doc.ref,
        "url": _source_url(doc, quran_link),
        "verified": doc.verified,
    }


def _explanation(j: Judgement) -> dict | None:
    """Template explanation (no LLM in phase 1). Always labelled as generated text,
    kept separate from the source text."""
    c = j.candidate
    if j.code == "VERIFIED" and c and c.doc.kind == "quran":
        text = f"النص مطابق لما في المصحف: {_ayah_label(c.doc.ref)}."
    elif j.code in ("VERIFIED", "NOT_AUTHENTIC", "DISPUTED", "IN_SOURCE") and c and c.doc.grades:
        g = "؛ ".join(f"{x['muhaddith']} ({x['source']} {x['ref']}): {x['grade']}" for x in c.doc.grades)
        text = f"الدرجة كما هي مسجّلة في المصدر: {g}."
    elif j.code == "ALTERED" and c:
        text = f"النص المدخل يختلف عن النص القرآني المعتمد في Quranpedia ({_ayah_label(c.doc.ref)})؛ انظر موضع الاختلاف."
    elif j.code == "REFER":
        text = "هذه مسألة شخصية تختلف باختلاف الوقائع؛ يُرجع فيها إلى مفتٍ أو جهة إفتاء مؤهلة."
    elif j.code == "NO_ORIGIN":
        text = "لم يُعثر على نص مطابق في الفهرس الحالي؛ عدم العثور لا يحكم على صحة الحديث أو وجوده في مصادر أخرى."
    else:
        return None
    return {"kind": "template", "generated": True, "text": text}


QUESTION_NOTE = (
    "هذا سؤال عام وليس آيةً أو حديثاً منقولاً. تثبّت يتحقق من النصوص المنسوبة إلى القرآن الكريم والسنة النبوية، "
    "ولا يجيب عن الأسئلة العامة ولا يصدر فتوى. الصق الآية أو الحديث الذي تريد التحقق منه."
)
_FOUND = ("VERIFIED", "NOT_AUTHENTIC", "DISPUTED", "IN_SOURCE")


def _reference_note(type_hint: str) -> str:
    what, to = ("حديثاً يثبت", "إلى النبي ﷺ") if type_hint == "hadith" else ("آيةً تثبت", "إلى القرآن الكريم")
    return (f"طلبتَ {what} كلاماً دون ذكر نص منسوب. تثبّت لا ينشئ أحاديث ولا آيات ولا يأتي بأدلة من عنده، "
            f"ولا يوجد في الطلب نص يمكن مقارنته بالمصادر، فلا دليل مطابق يُعرض، ولا يُنسب {to} ما لم يثبت. "
            "إن كان لديك نص منسوب فالصقه كاملاً للتحقق منه.")


def _apply_request(claim, j: Judgement) -> Judgement:
    """Requests are answered only from what the sources hold: a general question is not
    graded as a missing hadith, and «أعطني حديثاً يثبت…» never yields a text that is not
    recorded word for word."""
    if claim.request == "question" and j.code == "NO_ORIGIN":
        return Judgement("OUT_OF_SCOPE", notes=[QUESTION_NOTE])
    if claim.request == "evidence":
        what = "حديثاً" if claim.type_hint == "hadith" else "آيةً"
        if j.code in _FOUND:
            where = "في المصحف" if j.candidate and j.candidate.doc.kind == "quran" else "في الدرر السنية"
            j.notes.insert(0, f"طلبتَ {what} بهذا النص: هذا نص مسجّل بلفظه {where} ومعه حكمه كما في مصدره؛ تثبّت لا ينشئ نصوصاً ولا يقترحها من عنده.")
            return j
        base = "الدرر السنية" if claim.type_hint == "hadith" else "المصحف القرآني المعتمد من Quranpedia"
        note = (f"تثبّت لا ينشئ أحاديث ولا آيات ولا يقترح نصوصاً من عنده. بحث عن «{claim.text}» في {base} "
                "فلم يُعثر على تطابق مطابق؛ وهذا لا يعني الحكم على النص. ابحث عنه بلفظ آخر في الدرر السنية.")
        if claim.type_hint != "hadith":
            note = note.replace(" ابحث عنه بلفظ آخر في الدرر السنية.", " راجع النص في Quranpedia.")
        return Judgement("NO_ORIGIN", closest=j.candidate or j.closest, notes=[note])
    return j


MAX_LIVE_LOOKUPS = 4


def _live_eligible(claim, j: Judgement) -> bool:
    """Ask Dorar only for a hadith-like quotation the local base did not find."""
    if j.code != "NO_ORIGIN" or j.short or claim.level == "D" or claim.request in ("question", "evidence_ref"):
        return False
    n = len(key_tokens(claim.text))
    # An unmarked phrase must be longer: a few common words occur inside many hadiths.
    return (claim.type_hint == "hadith" and n >= 3) or (claim.type_hint == "unknown" and n >= 5)


def run(index: HybridIndex, text: str, th: Thresholds, quran_link: str,
        live: bool = False, live_fetch=None, live_timeout: float = 4.0) -> dict:
    t0 = time.perf_counter()
    claims_out = []
    summary = {code: 0 for code in VERDICTS}
    lookups = 0

    for claim in extractor.extract(text):
        live_info = None
        if claim.request == "evidence_ref":
            j = Judgement("NO_ORIGIN", notes=[_reference_note(claim.type_hint)])
        else:
            j = judge(index, claim, th)
            if live and lookups < MAX_LIVE_LOOKUPS and _live_eligible(claim, j):
                lookups += 1
                found = (live_fetch or dorar_live.fetch)(claim.text, timeout=live_timeout)
                live_info = {"searched": True, "ok": found.ok}
                lj = dorar_live.judge_live(claim.text, found, th)
                if lj is not None:
                    j = lj
                elif found.ok:
                    j.notes.append(dorar_live.NOT_FOUND_NOTE)
                else:
                    j.notes.append(dorar_live.UNAVAILABLE_NOTE)
            j = _apply_request(claim, j)
        if claim.omitted_count:
            j.notes.append(
                f"تجاوز النص حد عرض {extractor.MAX_CLAIMS} بطاقة؛ لم تُعرض {claim.omitted_count} بطاقة إضافية. "
                "تُقدّم الحالات الشخصية للإحالة عند بلوغ الحد. قسّم النص إلى أجزاء لمراجعة بقية الادعاءات."
            )
        summary[j.code] += 1
        c = j.candidate
        verse_not_question = claim.level == "D" and j.code == "VERIFIED" and c is not None and c.doc.kind == "quran"
        level = "A" if c is not None and (claim.level == "B" or verse_not_question) else claim.level
        out = {
            "id": claim.id,
            "text": claim.text,
            "type_hint": claim.type_hint,
            "request": claim.request,
            "level": level,
            "verdict": {"code": j.code, "label_ar": j.label},
            "source": None,
            "grades": [],
            "diff": [],
            "evidence": None,
            "closest": None,
            "alternatives": [],
            "notes": j.notes,
            "explanation": _explanation(j),
            "live": live_info,
        }
        if c is not None:
            out["source"] = _source(c.doc, quran_link)
            out["grades"] = c.doc.grades
            out["alternatives"] = [
                {"id": d.id, "ref": d.ref, "url": _source_url(d, quran_link)} for d in c.alternatives
            ]
            out["diff"] = [] if c.al.exact else c.al.diff
            out["evidence"] = {
                "claim_coverage": round(c.al.claim_coverage, 3),
                "content_coverage": round(c.al.content_coverage, 3),
                "span_coverage": round(c.al.span_coverage, 3),
                "similarity": round(c.al.dice, 3),
                "retrieval_fused": round(c.hit.fused, 5),
                "bm25_rank": c.hit.bm25_rank,
                "dense_rank": c.hit.dense_rank,
            }
        if j.closest is not None:
            out["closest"] = {
                **_source(j.closest.doc, quran_link),
                "grades": j.closest.doc.grades,
                "content_coverage": round(j.closest.al.content_coverage, 3),
                "note": "أقرب نص في الفهرس — غير مطابق، ولا يُبنى عليه حكم.",
            }
        claims_out.append(out)

    return {
        "claims": claims_out,
        "summary": summary,
        "index": index.stats(),
        "disclaimer": DISCLAIMER,
        "engine_version": ENGINE_VERSION,
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
    }

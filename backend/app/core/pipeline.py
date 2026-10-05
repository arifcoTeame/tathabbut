"""Orchestration: text -> claims -> retrieval -> alignment -> deterministic verdict -> JSON."""
from __future__ import annotations

import time

from . import extractor
from .index import HybridIndex
from .judge import VERDICTS, Judgement, Thresholds, judge

ENGINE_VERSION = "0.8.0"
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
    elif j.code in ("VERIFIED", "NOT_AUTHENTIC", "DISPUTED") and c and c.doc.grades:
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


def run(index: HybridIndex, text: str, th: Thresholds, quran_link: str) -> dict:
    t0 = time.perf_counter()
    claims_out = []
    summary = {code: 0 for code in VERDICTS}

    for claim in extractor.extract(text):
        j = judge(index, claim, th)
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

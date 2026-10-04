"""Deterministic verdict rules.

The final verdict is produced ONLY by these rules, from three inputs:
retrieval candidates, word alignment metrics, and the grade recorded in the
source. The system never produces a hadith grade of its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .align import Alignment, align, contains
from .arabic import key_tokens, normalize, wording_tokens
from .extractor import Claim, has_categorical_ruling
from .index import Doc, Hit, HybridIndex

VERDICTS = {
    "VERIFIED": "موثّق",
    "NOT_AUTHENTIC": "لا يصح",
    "ALTERED": "مُحرَّف",
    "NO_ORIGIN": "لم يُعثر عليه",
    "DISPUTED": "خلافي",
    "REFER": "إحالة",
    "NEEDS_REVIEW": "يتطلب مزيد تحقق",
}
MAX_EXTRA_VERSES = 3


@dataclass
class Thresholds:
    quran_altered_min: float = 0.6     # claim coverage for "altered verse"
    quran_unknown_min: float = 0.8     # stricter when the claim was not marked as a verse
    hadith_match_min: float = 0.75     # retrieval gate; recorded wording must also match exactly
    hadith_review_min: float = 0.6     # content coverage: close but not enough -> needs review
    closest_min: float = 0.6           # show a "closest text" hint only above this
    min_words_altered: int = 3
    require_verified_sources: bool = False


@dataclass
class Candidate:
    hit: Hit
    al: Alignment
    doc: Doc
    alternatives: list[Doc] = field(default_factory=list)   # other verses that fit equally well
    ties: int = 1


@dataclass
class Judgement:
    code: str
    candidate: Candidate | None = None      # the source the verdict rests on
    closest: Candidate | None = None        # non-matching nearest text, shown as a hint only
    notes: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return VERDICTS[self.code]


def _quran_candidates(index: HybridIndex, text: str) -> list[Candidate]:
    n_words = len(key_tokens(text))
    out = []
    for h in index.search(text, kind="quran"):
        out.append(Candidate(h, align(text, h.doc.text, stemmed=False, preserve_negation=True), h.doc))
        # multi-verse quotes: extend while the claim is longer than the verse
        for extra in range(1, MAX_EXTRA_VERSES + 1):
            run = index.verse_run(h.doc, extra)
            if run is None:
                break
            out.append(Candidate(h, align(text, run.text, stemmed=False, preserve_negation=True), run))
            if len(run.keys) >= n_words:
                break
    return out


def _surface(claim: str, doc: Doc) -> bool:
    """Exact wording (before stemming) appears as whole words in the source:
    separates «فإن مع العسر» (94:5) from «إن مع العسر» (94:6)."""
    if doc.kind == "quran":
        return contains(wording_tokens(doc.text), wording_tokens(claim))
    return f" {normalize(claim)} " in f" {normalize(doc.text)} "


def _bigrams(word: str) -> set[str]:
    return {word[i : i + 2] for i in range(len(word) - 1)} or {word}


def _residue(c: Candidate) -> float:
    """How closely the claim's unmatched words echo words of this verse
    («طاقتها» ~ «طاقة» in 2:286). Used only to break ties between verses."""
    words = [w for run in c.al.added for w in run]
    if not words:
        return 1.0
    keys = c.doc.keys
    score = 0.0
    for w in words:
        bw = _bigrams(w)
        score += max((len(bw & _bigrams(k)) / len(bw | _bigrams(k)) for k in keys), default=0.0)
    return score / len(words)


def _verse_key(doc: Doc) -> tuple[int, int]:
    return doc.ref["surah"], doc.ref["ayah"]


def _best(index: HybridIndex, text: str, kind: str) -> Candidate | None:
    if kind == "quran":
        cands = _quran_candidates(index, text)
        if not cands:
            return None
        head = lambda c: (round(c.al.claim_coverage, 3), round(c.al.span_coverage, 3), _surface(text, c.doc))
        top = max(head(c) for c in cands)
        tied = [c for c in cands if head(c) == top]
        tied.sort(key=lambda c: (_residue(c), round(c.al.dice, 3), -_verse_key(c.doc)[0], -_verse_key(c.doc)[1]), reverse=True)
        best = tied[0]
        seen, alts = {_verse_key(best.doc)}, []
        for c in tied[1:]:
            if _verse_key(c.doc) not in seen:
                seen.add(_verse_key(c.doc))
                alts.append(c.doc)
        best.alternatives, best.ties = sorted(alts, key=_verse_key)[:4], len(seen)
        return best
    cands = [
        Candidate(h, align(text, h.doc.text, stemmed=False, preserve_negation=True), h.doc)
        for h in index.search(text, kind=kind)
    ]
    key = lambda c: (round(c.al.content_coverage, 3), round(c.al.claim_coverage, 3), _surface(text, c.doc), c.al.dice, c.hit.fused)
    return max(cands, key=key) if cands else None


def _grade_verdict(doc: Doc) -> tuple[str, list[str]]:
    if not doc.grades:
        return "NEEDS_REVIEW", ["لا توجد درجة مسجّلة لهذا النص في المصدر؛ لا يُصدر النظام درجة من عنده."]
    classes = {g.get("class") for g in doc.grades}
    if not classes <= {"authentic", "weak", "very_weak", "fabricated", "baseless", "unverified"}:
        return "NEEDS_REVIEW", ["تصنيف إحدى الدرجات المسجّلة مفقود أو غير معروف؛ تُعرض الدرجات دون استنتاج حكم منها."]
    authentic, other = "authentic" in classes, bool(classes - {"authentic"})
    if authentic and other:
        return "DISPUTED", ["اختلف المحدّثون في درجته؛ تُعرض الأحكام كلها منسوبة لأصحابها دون ترجيح."]
    return ("VERIFIED" if authentic else "NOT_AUTHENTIC"), []


def _no_origin(closest: Candidate | None, th: Thresholds) -> Judgement:
    hint = closest if closest and closest.al.content_coverage >= th.closest_min else None
    return Judgement("NO_ORIGIN", None, hint)


def _judge_quran(index: HybridIndex, claim: Claim, c: Candidate | None, th: Thresholds, strict: bool) -> Judgement:
    minimum = th.quran_unknown_min if strict else th.quran_altered_min
    if c is None or c.al.claim_coverage < minimum:
        return _no_origin(c, th)
    if c.al.exact:
        return Judgement("VERIFIED", c)
    if len(key_tokens(claim.text)) < th.min_words_altered:
        return Judgement("NEEDS_REVIEW", c, notes=["النص قصير جداً للحكم بالتحريف."])
    notes, merged_tail = [], False
    for i, run in enumerate(c.al.added):
        if len(run) < 2:
            continue
        for h in index.search(" ".join(run), kind="quran", k=5):
            if h.doc.id != c.doc.id and contains(h.doc.keys, run):
                notes.append(
                    f"العبارة المضافة وردت في موضع آخر ({h.doc.ref['surah_name']}: {h.doc.ref['ayah']}) ولا يصح دمجها."
                )
                merged_tail = merged_tail or i == len(c.al.added) - 1
                break
    # A trailing claim-only run that is NOT a verse merged from elsewhere is a substitution
    # of the words that follow in the verse (e.g. «طاقتها» in place of «وسعها»).
    last = c.al.diff[-1] if c.al.diff else None
    if last and last["op"] == "added" and c.al.tail_source and not merged_tail:
        c.al.diff[-1] = {"op": "changed", "claim": last["claim"], "source": c.al.tail_source}
    return Judgement("ALTERED", c, notes=notes)


def _judge_hadith(c: Candidate | None, th: Thresholds) -> Judgement:
    if c is None or c.al.content_coverage < th.hadith_review_min:
        return _no_origin(c, th)
    if c.al.content_coverage < th.hadith_match_min or not c.al.exact:
        return Judgement("NEEDS_REVIEW", c, notes=[
            "أقرب نص في المصدر يختلف في ألفاظه؛ تُعرض درجة المصدر ولا تُنقل إلى النص المدخل قبل مراجعة الفروق.",
        ])
    code, notes = _grade_verdict(c.doc)
    return Judgement(code, c, notes=notes)


def judge(index: HybridIndex, claim: Claim, th: Thresholds) -> Judgement:
    # Level D: refuse before any retrieval or generation.
    if claim.level == "D":
        notes = ["حالة شخصية تتطلب فتوى من جهة مؤهلة؛ لا يُصدر النظام حكماً فيها."]
        if has_categorical_ruling(claim.context_after):
            notes.append("ورد بعد السؤال جواب بصيغة القطع؛ يُنصح بتعديله إلى الإحالة.")
        return Judgement("REFER", notes=notes)

    n_words = len(key_tokens(claim.text))
    q = _best(index, claim.text, "quran")
    h = _best(index, claim.text, "hadith")
    q_exact = bool(q and q.al.exact and n_words >= 3)

    if claim.type_hint == "quran":
        j = _judge_quran(index, claim, q, th, strict=False)
        if j.code == "NO_ORIGIN" and h and h.al.content_coverage >= th.hadith_match_min:
            j.closest = h
            j.notes.append("النص ليس آية في المصحف، والأقرب إليه حديث في المصادر (انظر أقرب نص).")
    elif claim.type_hint == "hadith":
        if q_exact:
            j = Judgement("VERIFIED", q, notes=["النسبة خاطئة: النص آية قرآنية وليس حديثاً."])
        else:
            j = _judge_hadith(h, th)
    else:  # unknown type: decide by the strongest evidence
        if q_exact:
            j = Judgement("VERIFIED", q)
        elif h and h.al.content_coverage >= th.hadith_match_min:
            j = _judge_hadith(h, th)
        elif q and q.al.claim_coverage >= th.quran_unknown_min:
            j = _judge_quran(index, claim, q, th, strict=True)
        elif claim.level == "C":
            j = Judgement("DISPUTED", notes=["مسألة اجتهادية؛ لا تُعرض بصيغة القطع ويُحال فيها إلى المختص."])
        else:
            best = max((x for x in (q, h) if x), key=lambda x: x.al.content_coverage, default=None)
            j = _no_origin(best, th)

    c = j.candidate
    if c and c.doc.kind == "quran" and c.alternatives:
        where = "، ".join(f"{d.ref['surah_name']} {d.ref['ayah']}" for d in c.alternatives)
        if j.code == "VERIFIED":
            total = (
                sum(_surface(claim.text, doc) for doc in index.docs if doc.kind == "quran")
                if "ayah_end" not in c.doc.ref else c.ties
            )
            j.notes.append(f"النص نفسه يتكرر في {max(total, c.ties)} مواضع من المصحف، منها: {where}.")
        else:
            j.notes.append(f"قريب بالقدر نفسه من مواضع أخرى: {where}؛ رُجّح الأقرب لفظاً.")
    if j.code == "NO_ORIGIN":
        j.notes.append("لم يُعثر على نص مطابق في الفهرس الحالي؛ عدم العثور لا يحكم على صحة الحديث أو وجوده في مصادر أخرى.")
    quran_related = claim.type_hint == "quran" or (j.candidate and j.candidate.doc.kind == "quran")
    if quran_related and j.code in ("ALTERED", "NO_ORIGIN") and not index.stats()["quran_complete"]:
        j.notes.append("تنبيه: الفهرس القرآني الحالي عينة جزئية؛ الحكم مبدئي حتى تحميل النص الكامل.")
    if th.require_verified_sources and j.candidate and not j.candidate.doc.verified:
        j.notes.append("سجل المصدر لم يُراجع بعد؛ حُوّل الحكم إلى المراجعة.")
        j.code = "NEEDS_REVIEW"
    return j

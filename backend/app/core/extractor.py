"""Rule-based claim extraction (no LLM).

Finds quoted spans (﴿﴾ «» “” "") and unquoted sentences that follow an
attribution cue ("قال رسول الله ﷺ", "قال تعالى"...), tags each claim with a
type hint (quran / hadith / personal / unknown) and its content level (A-D).
An optional LLM extractor can later replace ``extract`` behind the same output.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .arabic import normalize

MAX_CLAIMS = 12
CUE_WINDOW = 70

QURAN_CUES = [normalize(c) for c in (
    "قال تعالى", "قال الله", "يقول الله", "قوله تعالى", "قال عز وجل",
    "قال سبحانه", "يقول تعالى", "في كتابه", "قال الله تعالى", "الآية",
)]
HADITH_CUES = [normalize(c) for c in (
    "رسول الله", "النبي", "صلى الله عليه وسلم", "عليه الصلاة والسلام",
    "في الحديث", "حديث", "يروى", "روي عن",
)]
HADITH_CUES_RAW = ("ﷺ",)

PERSONAL_PATTERNS = [re.compile(p) for p in (
    r"هل يجوز لي", r"هل يحق لي", r"هل يلزمني", r"هل علي ", r"في حالتي",
    r"زوجتي", r"زوجي", r"طليقتي", r"حلفت", r"نذرت", r"ماذا افعل",
    r"\bانا\b.*\bهل\b", r"ما حكم .*\b(لي|علي)\b",
)]
DISPUTE_CUES = [normalize(c) for c in (
    "حكم", "يجوز", "حرام", "حلال", "بالإجماع", "إجماع", "مذهب", "بدعة", "مكروه", "واجب",
)]
RULING_WORDS = re.compile(r"\b(لا يجوز|يجوز|حرام|حلال|واجب|لا يحل)\b")

_QUOTES = [
    (re.compile(r"﴿([^﴾]{2,})﴾"), "quran"),
    (re.compile(r"«([^»]{2,})»"), None),
    (re.compile(r"“([^”]{2,})”"), None),
    (re.compile(r"\"([^\"]{2,})\""), None),
]
_SENTENCE_SPLIT = re.compile(r"[.!؟?\n؛]+")
_REQUEST_OPENING = re.compile(r"^(?:[وف]\s*)?(?:هل\b|ماذا\b|ما حكم\b|في حالتي\b|انا\b|سوالي\b)")


@dataclass
class Claim:
    id: int
    text: str
    type_hint: str            # quran | hadith | personal | unknown
    level: str                # A | B | C | D
    start: int
    end: int
    context_after: str = ""
    omitted_count: int = 0
    request: str = ""         # "" | "evidence" (أعطني حديثاً يثبت أن …) | "evidence_ref" (… يثبت هذا الكلام: no text given)
                              # | "question" (general question, not a quotation)


def is_personal(text: str) -> bool:
    n = normalize(text)
    return any(p.search(n) for p in PERSONAL_PATTERNS)


_INTERROGATIVE = re.compile(r"^\s*[وف]?(?:لماذا|لم|كيف|هل|ماذا|متى|أين|اين|من|ما|ماهو|ماهي|كم|أي|اي|ترجم|اشرح|عرف|عرّف|وضح|وضّح|اذكر|بين|بيّن)\b")


def is_question(sentence: str, text: str) -> bool:
    """A question or instruction addressed to us, rather than a quoted text to check."""
    s = sentence.strip()
    return bool(_INTERROGATIVE.match(s)) or text.rstrip().endswith(("؟", "?"))


def classify_level(text: str, type_hint: str) -> str:
    """Content levels from the challenge's scientific package:
    A stable primary texts · B explanation · C disputed/sensitive · D personal fatwa."""
    if type_hint == "personal":
        return "D"
    # First-person words in a narrated quotation belong to its speaker, not
    # automatically to the person asking us to check the quotation.
    if type_hint in ("quran", "hadith"):
        return "A"
    if is_personal(text):
        return "D"
    n = normalize(text)
    if any(c in n for c in DISPUTE_CUES):
        return "C"
    return "B"


def _cue_type(window: str) -> str | None:
    n = normalize(window)
    if any(c in n for c in QURAN_CUES):
        return "quran"
    if any(c in window for c in HADITH_CUES_RAW) or any(c in n for c in HADITH_CUES):
        return "hadith"
    return None


# An attribution opening the sentence without an honorific: «قال رسول الله الدين النصيحة»,
# «قال النبي …», «قال الله …». (With ﷺ / تعالى the honorific itself marks the end of the cue.)
_LEADS = (
    ("hadith", re.compile(r"^\s*[وف]?(?:قال|يقول|عن)\s+(?:رسول\s+الله|الرسول|النبي|النبى)\s*[:：،,\-]?\s*")),
    ("quran", re.compile(r"^\s*[وف]?(?:قال|يقول)\s+(?:الله|ربنا|ربكم)\s*[:：،,\-]?\s*")),
)


_ASK = r"(?:أعطني|اعطني|أعطيني|اعطيني|هات|أريد|اريد|أبغى|ابغى|أبي|ابي|أحتاج|احتاج)"
_PROPHET = r"(?:النبي|النبى|الرسول|رسول\s+الله)\s*(?:ﷺ|صلى\s+الله\s+عليه\s+وسلم|عليه\s+الصلاة\s+والسلام)?"
_SEP = r"\s*[:：،,\-]?\s*"
# How people actually ask about a quotation. Each lead is removed so that only the quoted
# words are matched; ("hadith"/"quran", request kind, pattern).
_REQUEST_LEADS = (
    ("hadith", "evidence", re.compile(rf"^\s*{_ASK}\s+(?:لي\s+)?(?:حديثا|حديثاً|حديث)\s+(?:صحيحا\s+|صحيحاً\s+)?(?:يثبت|يدل\s+على|يؤكد|عن|في)?\s*(?:أن|ان)?\s*")),
    ("quran", "evidence", re.compile(rf"^\s*{_ASK}\s+(?:لي\s+)?(?:آية|اية)\s+(?:تثبت|تدل\s+على|تؤكد|عن|في)?\s*(?:أن|ان)?\s*")),
    ("hadith", "", re.compile(rf"^\s*[وف]?(?:ما|ماهي|ما\s+هي)\s+(?:مدى\s+)?(?:صحة|درجة|حكم)\s+(?:هذا\s+)?(?:الحديث|حديث){_SEP}")),
    ("hadith", "", re.compile(rf"^\s*[وف]?هل\s+(?:هذا\s+)?(?:الحديث|حديث){_SEP}")),
    ("hadith", "", re.compile(rf"^\s*[وف]?هل\s+(?:صح|يصح|ثبت|يثبت|ورد)\s+(?:عن\s+{_PROPHET}\s*)?(?:أنه\s+قال|انه\s+قال|قوله|حديث)?{_SEP}")),
    ("hadith", "", re.compile(rf"^\s*[وف]?(?:سمعت|قرأت|قريت|يقولون|يقال|قيل|يروى|روي|يقول\s+الناس)\s+(?:أن|ان|إن)\s+{_PROPHET}\s*(?:قال|يقول){_SEP}")),
    ("hadith", "", re.compile(rf"^\s*[وف]?(?:ورد|جاء)\s+في\s+(?:الحديث|حديث){_SEP}")),
    ("hadith", "", re.compile(r"^\s*(?:في\s+الحديث|حديث)\s*[:：،\-]\s*")),
    ("quran", "", re.compile(rf"^\s*[وف]?(?:ما|ماهي)\s+(?:مدى\s+)?صحة\s+(?:هذه\s+)?(?:الآية|آية|الاية|اية){_SEP}")),
    ("quran", "", re.compile(rf"^\s*[وف]?هل\s+(?:هذه\s+)?(?:الآية|آية|الاية|اية){_SEP}")),
    ("quran", "", re.compile(r"^\s*[وف]?هل\s+(?=\S.*\s(?:آية|اية)(?:\s+قرآنية|\s+قرانية)?\s*$)")),
)
_REQUEST_TAIL = re.compile(
    r"(?:\s*[،,]\s*|\s+)(?:"
    r"(?:هل\s+(?:هو|هي|هذا|هذه)\s+)?(?:حديث\s+)?(?:صحيح|صحيحة|ثابت|ثابتة|صح|موضوع|ضعيف)"
    r"|هل\s+(?:هذا|هذه)\s+(?:حديث|آية|اية)(?:\s+صحيح)?"
    r"|[وف]?(?:ما|ماهي)\s+(?:صحته|درجته|حكمه)"
    r"|(?:آية|اية)(?:\s+قرآنية|\s+قرانية)?"
    r")\s*$"
)
_AFTER_HONORIFIC = re.compile(r"^(?:أنه\s+|انه\s+)?(?:قال|يقول)\s*[:：،,\-]?\s*")


# «أعطني حديثاً يثبت هذا الكلام»: the request names no text, only points back at something said.
_REFERENCE_ONLY = re.compile(
    r"^(?:(?:هذا|هذه|ذلك|ذاك|تلك|هذي)\s*)?(?:ال)?(?:كلام|قول|معنى|أمر|امر|مقولة|فكرة|شيء|شي|رأي|راي|كلامي|كلامك|ما\s+سبق|ما\s+قلته|ما\s+ذكرته|ما\s+قلت)?$"
)


def _strip_request(sentence: str) -> tuple[str | None, str, str]:
    """(type, quoted words, request kind) for a verification request, else (None, sentence, "")."""
    for kind, request, lead in _REQUEST_LEADS:
        m = lead.match(sentence)
        if not m:
            continue
        body = _REQUEST_TAIL.sub("", sentence[m.end():]).strip(" :،,-")
        if request == "evidence" and _REFERENCE_ONLY.match(body):
            return kind, sentence, "evidence_ref"
        if len(body.split()) >= 2:
            return kind, body, request
    return None, sentence, ""


def _strip_cue(sentence: str) -> tuple[str | None, str]:
    """For an unquoted sentence, return (type, text after the attribution cue)."""
    for raw in ("ﷺ", "صلى الله عليه وسلم", "عليه الصلاة والسلام", "تعالى", "عز وجل", "سبحانه"):
        pos = sentence.find(raw)
        if pos != -1:
            kind = _cue_type(sentence[: pos + len(raw)])
            rest = sentence[pos + len(raw):].lstrip(" :،,-")
            rest = _AFTER_HONORIFIC.sub("", rest)     # «سمعت أن النبي ﷺ قال …»
            if kind and len(rest.split()) >= 2:
                return kind, rest
    for kind, lead in _LEADS:
        m = lead.match(sentence)
        if m and len(sentence[m.end():].split()) >= 2:
            return kind, sentence[m.end():]
    return None, sentence


def _split_personal_tail(body: str) -> tuple[str, str]:
    """Separate an explicit user question following an unquoted citation.

    A first-person word alone is insufficient: a request must open the clause
    after a comma, so narrated wording such as «زوجتي» stays in the quotation.
    """
    for boundary in re.finditer(r"[،,]\s*", body):
        tail = body[boundary.end():].strip()
        if _REQUEST_OPENING.match(normalize(tail)) and is_personal(tail):
            return body[:boundary.start()].rstrip(), tail
    return body, ""


def extract(text: str) -> list[Claim]:
    spans: list[tuple[int, int, str, str | None]] = []
    for pattern, forced in _QUOTES:
        for m in pattern.finditer(text):
            if any(m.start() < e and m.end() > s for s, e, _, _ in spans):
                continue
            spans.append((m.start(), m.end(), m.group(1).strip(), forced))
    spans.sort()

    claims: list[Claim] = []
    prev_end = 0
    for start, end, body, forced in spans:
        window = text[max(prev_end, start - CUE_WINDOW): start]
        window = _SENTENCE_SPLIT.split(window)[-1]
        kind = forced or _cue_type(window)
        if kind is None and is_personal(body):
            kind = "personal"
        after = text[end: end + 120]
        claims.append(Claim(0, body, kind or "unknown", "", start, end, after))
        prev_end = end

    # unquoted attribution sentences / personal questions outside quotes
    masked = list(text)
    for s, e, _, _ in spans:
        masked[s:e] = [" "] * (e - s)
    masked_text = "".join(masked)
    cursor = 0
    questions: list[Claim] = []    # general questions left over; kept only beside «… يثبت هذا الكلام»
    for sentence in _SENTENCE_SPLIT.split(masked_text):
        pos = masked_text.find(sentence, cursor)
        cursor = pos + len(sentence)
        s = sentence.strip()
        if len(s.split()) < 2:
            continue
        had_quote = any(pos <= qs < cursor for qs, _, _, _ in spans)
        kind, body, request = _strip_request(s)
        if kind is None:
            kind, body = _strip_cue(s)
            # «قال رسول الله ﷺ …، صحيح؟»: drop the question tail only when the sentence is a question,
            # so a verse ending in «آية» (23:50) keeps its last word.
            if kind and masked_text[cursor:cursor + 1] in ("؟", "?"):
                body = _REQUEST_TAIL.sub("", body).strip(" :،,-") or body
        if kind and not had_quote:
            prefix = s[:len(s) - len(body)]
            body, personal_tail = _split_personal_tail(body)
            if body:
                body_start = pos + max(sentence.find(body), 0)
                claims.append(Claim(0, body, kind, "", body_start, body_start + len(body), request=request))
            # The user's question can precede the attribution or follow an
            # unquoted citation. Keep its context without grading that context.
            if is_personal(prefix) or personal_tail:
                request = text[pos:cursor].strip()
                claims.append(Claim(0, request, "personal", "", pos, cursor, text[cursor: cursor + 120]))
        elif is_personal(s):
            # Detect personal context only outside the masked quotations, but
            # show the original sentence so the question remains intelligible.
            request = text[pos:cursor].strip()
            claims.append(Claim(0, request, "personal", "", pos, cursor, text[cursor: cursor + 120]))
        elif not had_quote and is_question(s, text[pos:cursor + 1]):
            start = pos + max(sentence.find(s), 0)
            questions.append(Claim(0, s, "unknown", "", start, start + len(s), request="question"))

    # «لماذا يعبد المسلمون الكعبة؟ أعطني حديثاً يثبت هذا الكلام»: the question the request points at
    # is answered as a general question, and the request itself never yields a text.
    if any(c.request == "evidence_ref" for c in claims):
        claims.extend(questions)

    # nothing recognised: treat the input itself as the claim(s)
    if not claims:
        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if len(s.split()) >= 2]
        if len(text) <= 300 or not sentences:
            sentences = [text.strip()]
        for s in sentences:
            pos = text.find(s)
            if is_personal(s):
                claims.append(Claim(0, s, "personal", "", pos, pos + len(s)))
            else:
                claims.append(Claim(0, s, "unknown", "", pos, pos + len(s), request="question" if is_question(s, text) else ""))

    claims.sort(key=lambda c: c.start)
    for c in claims:
        c.level = classify_level(c.text, c.type_hint)
    if len(claims) > MAX_CLAIMS:
        omitted = len(claims) - MAX_CLAIMS
        # Reserve capacity for referrals even if many quotations precede them.
        # At the limit, show referrals first so they cannot be hidden at the end.
        claims.sort(key=lambda c: (c.level != "D", c.start))
        claims = claims[:MAX_CLAIMS]
        claims[0].omitted_count = omitted
    for i, c in enumerate(claims, 1):
        c.id = i
    return claims


def has_categorical_ruling(text: str) -> bool:
    return bool(RULING_WORDS.search(normalize(text)))

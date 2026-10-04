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


def is_personal(text: str) -> bool:
    n = normalize(text)
    return any(p.search(n) for p in PERSONAL_PATTERNS)


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


def _strip_cue(sentence: str) -> tuple[str | None, str]:
    """For an unquoted sentence, return (type, text after the attribution cue)."""
    for raw in ("ﷺ", "صلى الله عليه وسلم", "عليه الصلاة والسلام", "تعالى", "عز وجل", "سبحانه"):
        pos = sentence.find(raw)
        if pos != -1:
            kind = _cue_type(sentence[: pos + len(raw)])
            rest = sentence[pos + len(raw):].lstrip(" :،,-")
            if kind and len(rest.split()) >= 2:
                return kind, rest
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
    for sentence in _SENTENCE_SPLIT.split(masked_text):
        pos = masked_text.find(sentence, cursor)
        cursor = pos + len(sentence)
        s = sentence.strip()
        if len(s.split()) < 2:
            continue
        had_quote = any(pos <= qs < cursor for qs, _, _, _ in spans)
        kind, body = _strip_cue(s)
        if kind and not had_quote:
            prefix = s[:len(s) - len(body)]
            body, personal_tail = _split_personal_tail(body)
            if body:
                body_start = pos + sentence.find(body)
                claims.append(Claim(0, body, kind, "", body_start, body_start + len(body)))
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

    # nothing recognised: treat the input itself as the claim(s)
    if not claims:
        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if len(s.split()) >= 2]
        if len(text) <= 300 or not sentences:
            sentences = [text.strip()]
        for s in sentences:
            pos = text.find(s)
            claims.append(Claim(0, s, "personal" if is_personal(s) else "unknown", "", pos, pos + len(s)))

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

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


@dataclass
class Claim:
    id: int
    text: str
    type_hint: str            # quran | hadith | personal | unknown
    level: str                # A | B | C | D
    start: int
    end: int
    context_after: str = ""


def is_personal(text: str) -> bool:
    n = normalize(text)
    return any(p.search(n) for p in PERSONAL_PATTERNS)


def classify_level(text: str, type_hint: str) -> str:
    """Content levels from the challenge's scientific package:
    A stable primary texts · B explanation · C disputed/sensitive · D personal fatwa."""
    if type_hint == "personal" or is_personal(text):
        return "D"
    if type_hint in ("quran", "hadith"):
        return "A"
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
        kind = forced or _cue_type(window)
        if kind is None and (is_personal(body) or is_personal(window)):
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
            claims.append(Claim(0, body, kind, "", pos, cursor))
        elif is_personal(s) and not had_quote:
            claims.append(Claim(0, s, "personal", "", pos, cursor, text[cursor: cursor + 120]))

    # nothing recognised: treat the input itself as the claim(s)
    if not claims:
        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if len(s.split()) >= 2]
        if len(text) <= 300 or not sentences:
            sentences = [text.strip()]
        for s in sentences:
            pos = text.find(s)
            claims.append(Claim(0, s, "personal" if is_personal(s) else "unknown", "", pos, pos + len(s)))

    claims.sort(key=lambda c: c.start)
    claims = claims[:MAX_CLAIMS]
    for i, c in enumerate(claims, 1):
        c.id = i
        c.level = classify_level(c.text, c.type_hint)
    return claims


def has_categorical_ruling(text: str) -> bool:
    return bool(RULING_WORDS.search(normalize(text)))

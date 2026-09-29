"""Arabic text normalization, tokenization and light stemming.

Two parallel token streams are produced from the same text:
  * display tokens  - diacritics removed, letters untouched (shown to the user)
  * key tokens      - normalized + lightly stemmed (used for BM25 and alignment)
Both streams always have the same length, so an alignment on keys maps 1:1 onto
display words.
"""
from __future__ import annotations

import re

_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_NON_WORD = re.compile(r"[^\w\s]|[\d٠-٩۰-۹_]")
_SPACES = re.compile(r"\s+")
_LETTER_MAP = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي",
})
_ALLAH = {"الله", "لله", "بالله", "والله", "تالله", "فالله", "اللهم"}
_ARTICLE_PREFIXES = ("بال", "كال", "لل", "ال")

# function words ignored when measuring *content* coverage (keys are normalized+stemmed)
STOPWORDS = {
    "من", "في", "علي", "الي", "عن", "ما", "لا", "ان", "انما", "او", "ثم", "قد", "هو", "هي",
    "كل", "لم", "لن", "لو", "ولو", "مع", "حتي", "الا", "اذا", "اذ", "يا", "ذلك", "هذا", "هذه",
    "التي", "الذي", "الذين", "تي", "ذي", "ذين", "له", "لها", "لهم", "به", "بها", "فيه", "فيها", "منه", "كان", "قال",
}


def strip_diacritics(text: str) -> str:
    return _DIACRITICS.sub("", text)


def normalize(text: str) -> str:
    text = strip_diacritics(text).translate(_LETTER_MAP)
    text = _NON_WORD.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def light_stem(word: str) -> str:
    """Strip a leading conjunction (و/ف) and the definite article. Never strips
    words of three letters or fewer, and keeps the name of Allah intact."""
    if word in _ALLAH:
        return "الله"
    if len(word) >= 4 and word[0] in "وف":
        rest = word[1:]
        if rest in _ALLAH:
            return "الله"
        word = rest
    for prefix in _ARTICLE_PREFIXES:
        if word.startswith(prefix) and len(word) - len(prefix) >= 2:
            return word[len(prefix):]
    return word


def display_tokens(text: str) -> list[str]:
    return _SPACES.sub(" ", _NON_WORD.sub(" ", strip_diacritics(text))).split()


def key_tokens(text: str) -> list[str]:
    return [light_stem(w) for w in normalize(text).split()]

"""Arabic text normalization, tokenization and light stemming.

Two parallel token streams are produced from the same text:
  * display tokens  - diacritics removed, letters untouched (shown to the user)
  * key tokens      - normalized + lightly stemmed (used for retrieval)
Both streams always have the same length, so an alignment on keys maps 1:1 onto
display words. Quotation wording uses a third stream that preserves the letters
and attached particles; retrieval normalization must not establish an exact match.
"""
from __future__ import annotations

import re
import unicodedata

_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_NON_WORD = re.compile(r"[^\w\s]|[\d٠-٩۰-۹_]")
_SPACES = re.compile(r"\s+")
_LETTER_MAP = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي",
})
_ALLAH = {"الله", "لله", "بالله", "والله", "تالله", "فالله", "اللهم"}
_ARTICLE_PREFIXES = ("بال", "كال", "لل", "ال")
NEGATION_KEYS = {"لا", "لم", "لن", "ما", "ليس", "ليست", "لست", "لسنا", "ليسوا", "لستم", "لستن", "لسن"}
# Three-letter forms such as «ولا» are deliberately left intact by the stemmer.
NEGATION_KEYS |= {prefix + word for prefix in ("و", "ف") for word in NEGATION_KEYS}

# function words ignored when measuring *content* coverage (keys are normalized+stemmed)
STOPWORDS = {
    "من", "في", "علي", "الي", "عن", "ما", "لا", "ان", "انما", "او", "ثم", "قد", "هو", "هي",
    "كل", "لم", "لن", "لو", "ولو", "مع", "حتي", "الا", "اذا", "اذ", "يا", "ذلك", "هذا", "هذه",
    "التي", "الذي", "الذين", "تي", "ذي", "ذين", "له", "لها", "لهم", "به", "بها", "فيه", "فيها", "منه", "كان", "قال",
}


def strip_diacritics(text: str) -> str:
    # Compose hamza/madda first so removing vowel marks cannot erase a letter's
    # hamza merely because the input used its decomposed Unicode spelling.
    return _DIACRITICS.sub("", unicodedata.normalize("NFC", text))


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


def wording_tokens(text: str) -> list[str]:
    """Words for checking quotations: ignore vowels, punctuation and the
    wasla sign, but preserve hamza, letters, conjunctions and prepositions."""
    return [word.replace("ٱ", "ا") for word in display_tokens(text)]

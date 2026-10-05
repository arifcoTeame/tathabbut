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


# Orthographic variants between the bundled Tanzil text and the King Fahd
# (imla'i) text published by Quranpedia. Found by scripts/compare_quranpedia.py:
# across all 6236 verses these are the only letter-level differences, so the
# table is exhaustive for that reference. Both spellings are the same word.
_WORDING_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه"})
_JOINED = re.compile(r"(?<!\S)([وف]?)بعدما(?!\S)")          # بعدما ≡ بعد ما
ORTHO_VARIANTS = {"الزنا": "الزنى", "حسرتا": "حسرتى", "ويلتا": "ويلتى"}
_ORTHO_KEYS = {k.translate(str.maketrans({"ى": "ي"})): v.translate(str.maketrans({"ى": "ي"}))
               for k, v in ORTHO_VARIANTS.items()}


# Particles people often type joined to the next word: «لاتاخذه» for «لا تأخذه»,
# «ولانوم» for «ولا نوم», «ياايها» for «يا أيها». Split only when the joined form is
# not a word of the indexed sources and the remainder is one (see register_vocabulary).
_JOINED_PARTICLE = re.compile(r"(?<![\u0621-\u064A])([وف]?لا|يا)([\u0621-\u064A]{2,})(?![\u0621-\u064A])")
_VOCABULARY: frozenset[str] = frozenset()


def _wording_key(word: str) -> str:
    return word.translate(_WORDING_MAP)


def _split_particle(match: re.Match) -> str:
    prefix, rest = match.group(1), match.group(2)
    if _wording_key(prefix + rest) in _VOCABULARY or _wording_key(rest) not in _VOCABULARY:
        return match.group(0)
    return prefix + " " + rest


def register_vocabulary(texts) -> None:
    """Record the words of the indexed sources (wording form). Called once the
    index is built or loaded; source words themselves are never split."""
    global _VOCABULARY
    _VOCABULARY = frozenset()
    words = set()
    for text in texts:
        words.update(_wording_key(w) for w in display_tokens(text))
    _VOCABULARY = frozenset(words)


def strip_diacritics(text: str) -> str:
    # Compose hamza/madda first so removing vowel marks cannot erase a letter's
    # hamza merely because the input used its decomposed Unicode spelling.
    text = _DIACRITICS.sub("", unicodedata.normalize("NFC", text))
    text = _JOINED.sub(r"\1بعد ما", text)
    if _VOCABULARY:
        text = _JOINED_PARTICLE.sub(_split_particle, text)
    return text


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
    return [light_stem(_ORTHO_KEYS.get(w, w)) for w in normalize(text).split()]


# Spelling conventions people type interchangeably and that never change a word
# of the Quran into another word: hamza seats on alef, alef maqsura and ta marbuta.


def wording_tokens(text: str) -> list[str]:
    """Words for checking quotations: ignore vowels, tatweel, punctuation, the
    wasla sign, hamza seats on alef («احد» = «أحد»), ى/ي and ة/ه; preserve
    every other letter, conjunctions and prepositions (و/ف, لا, …)."""
    words = (word.translate(_WORDING_MAP) for word in display_tokens(text))
    return [_ORTHO_KEYS.get(word, word) for word in words]

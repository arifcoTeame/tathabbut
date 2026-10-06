"""Deterministic word-level alignment between a claim and a source text.
No language model is involved: the verdict on wording (exact / altered) comes
only from this module."""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from .arabic import NEGATION_KEYS, STOPWORDS, display_tokens, key_tokens, wording_tokens


@dataclass
class Alignment:
    claim_coverage: float   # share of claim words found, in order, in the source
    content_coverage: float # same, counting content words only (ignores من، في، على...)
    span_coverage: float    # share of the matched source span covered by the claim
    dice: float             # overall similarity vs. the whole source text
    span: tuple[int, int]   # [start, end) word indexes of the matched source span
    diff: list[dict]
    added: list[list[str]]  # claim word runs absent from the source span (keys)
    tail_source: str = ""   # source words right after the span, same count as trailing claim-only words

    @property
    def exact(self) -> bool:
        return bool(self.diff) and all(op["op"] == "equal" for op in self.diff)


def align(claim: str, source: str, *, stemmed: bool = True, preserve_negation: bool = False,
          leading_conjunction: bool = False) -> Alignment:
    c_search, s_search = key_tokens(claim), key_tokens(source)
    c_disp, s_disp = display_tokens(claim), display_tokens(source)
    if not c_search or not s_search:
        return Alignment(0.0, 0.0, 0.0, 0.0, (0, 0), [], [])

    # Loose keys locate the source span, including changed attached particles at
    # its edges. Only the second comparison below can establish exact wording.
    anchors = [b for b in SequenceMatcher(None, c_search, s_search, autojunk=False).get_matching_blocks() if b.size]
    if not anchors:
        return Alignment(0.0, 0.0, 0.0, 0.0, (0, 0), [], [c_search])

    start = anchors[0].b
    end = anchors[-1].b + anchors[-1].size
    # When the whole claim occurs contiguously in the source, compare against that
    # occurrence, not against a span stretched to an earlier stray word: «من غشنا فليس
    # منا» inside «من حمل علينا السلاح فليس منا ومن غشنا فليس منا».
    whole = SequenceMatcher(None, c_search, s_search, autojunk=False).find_longest_match()
    if whole.size == len(c_search):
        start, end = whole.b, whole.b + whole.size
    elif leading_conjunction:
        # Hadith excerpts: the conjunction joined to the first quoted word is part of the
        # surrounding narration («ومن غشنا…» quoted as «من غشنا…»). Quran keeps it.
        n = len(c_search)
        for i in range(len(s_search) - n + 1):
            if s_search[i] in ("و" + c_search[0], "ف" + c_search[0]) and s_search[i + 1:i + n] == c_search[1:]:
                start, end = i, i + n
                break
    c_keys, s_keys = (c_search, s_search) if stemmed else (wording_tokens(claim), wording_tokens(source))
    if not stemmed:
        # A source may contain both «فإن مع العسر يسرا» and «إن مع العسر
        # يسرا». Prefer the actual quotation over an earlier stem-equivalent run.
        literal = SequenceMatcher(None, c_keys, s_keys, autojunk=False).find_longest_match()
        if literal.size == len(c_keys):
            start, end = literal.b, literal.b + literal.size
    # An excerpt starting immediately after «لا» must not be certified after
    # dropping the word that negates it. Include it in the comparison and diff.
    if preserve_negation and start > 0 and s_search[start - 1] in NEGATION_KEYS:
        start -= 1
    span_keys, span_disp = s_keys[start:end], s_disp[start:end]
    if leading_conjunction and span_keys and c_keys and span_keys[0] in ("و" + c_keys[0], "ف" + c_keys[0]):
        span_keys = [c_keys[0]] + span_keys[1:]
    matcher = SequenceMatcher(None, c_keys, span_keys, autojunk=False)
    blocks = [b for b in matcher.get_matching_blocks() if b.size]
    matched = sum(b.size for b in blocks)
    matched_pos = {i for b in blocks for i in range(b.a, b.a + b.size)}
    content = [i for i, k in enumerate(c_search) if k not in STOPWORDS] or list(range(len(c_keys)))
    content_cov = sum(i in matched_pos for i in content) / len(content)

    diff: list[dict] = []
    added: list[list[str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            diff.append({"op": "equal", "text": " ".join(c_disp[i1:i2])})
        elif tag == "delete":        # words in the claim, not in the source
            diff.append({"op": "added", "claim": " ".join(c_disp[i1:i2])})
            added.append(c_search[i1:i2])
        elif tag == "insert":        # words in the source, missing from the claim
            diff.append({"op": "missing", "source": " ".join(span_disp[j1:j2])})
        else:
            diff.append({"op": "changed", "claim": " ".join(c_disp[i1:i2]), "source": " ".join(span_disp[j1:j2])})
            added.append(c_search[i1:i2])

    trail = len(c_keys) - (anchors[-1].a + anchors[-1].size)
    tail_source = " ".join(s_disp[end : end + trail]) if trail else ""

    return Alignment(
        tail_source=tail_source,
        claim_coverage=matched / len(c_keys),
        content_coverage=content_cov,
        span_coverage=matched / (end - start),
        dice=2 * matched / (len(c_keys) + len(s_keys)),
        span=(start, end),
        diff=diff,
        added=added,
    )


def contains(haystack_keys: list[str], needle_keys: list[str]) -> bool:
    n = len(needle_keys)
    return n > 0 and any(haystack_keys[i : i + n] == needle_keys for i in range(len(haystack_keys) - n + 1))

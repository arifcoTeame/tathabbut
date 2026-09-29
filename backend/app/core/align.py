"""Deterministic word-level alignment between a claim and a source text.
No language model is involved: the verdict on wording (exact / altered) comes
only from this module."""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from .arabic import STOPWORDS, display_tokens, key_tokens


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
        return self.claim_coverage >= 0.999 and self.span_coverage >= 0.999


def align(claim: str, source: str) -> Alignment:
    c_keys, s_keys = key_tokens(claim), key_tokens(source)
    c_disp, s_disp = display_tokens(claim), display_tokens(source)
    if not c_keys or not s_keys:
        return Alignment(0.0, 0.0, 0.0, 0.0, (0, 0), [], [])

    blocks = [b for b in SequenceMatcher(None, c_keys, s_keys, autojunk=False).get_matching_blocks() if b.size]
    matched = sum(b.size for b in blocks)
    if not matched:
        return Alignment(0.0, 0.0, 0.0, 0.0, (0, 0), [], [c_keys])

    matched_pos = {i for b in blocks for i in range(b.a, b.a + b.size)}
    content = [i for i, k in enumerate(c_keys) if k not in STOPWORDS] or list(range(len(c_keys)))
    content_cov = sum(i in matched_pos for i in content) / len(content)

    start = blocks[0].b
    end = blocks[-1].b + blocks[-1].size
    span_keys, span_disp = s_keys[start:end], s_disp[start:end]

    diff: list[dict] = []
    added: list[list[str]] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, c_keys, span_keys, autojunk=False).get_opcodes():
        if tag == "equal":
            diff.append({"op": "equal", "text": " ".join(c_disp[i1:i2])})
        elif tag == "delete":        # words in the claim, not in the source
            diff.append({"op": "added", "claim": " ".join(c_disp[i1:i2])})
            added.append(c_keys[i1:i2])
        elif tag == "insert":        # words in the source, missing from the claim
            diff.append({"op": "missing", "source": " ".join(span_disp[j1:j2])})
        else:
            diff.append({"op": "changed", "claim": " ".join(c_disp[i1:i2]), "source": " ".join(span_disp[j1:j2])})
            added.append(c_keys[i1:i2])

    trail = len(c_keys) - (blocks[-1].a + blocks[-1].size)
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

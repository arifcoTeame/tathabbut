"""Hybrid index: BM25 (lexical, stemmed keys) + dense vectors (inner product),
fused with Reciprocal Rank Fusion. The index holds both Quran and Hadith records;
each search can be restricted to one collection.

Both retrievers are vectorised for small CPUs (e.g. a 0.1-vCPU free host):
* BM25 is precomputed as a sparse doc x term weight matrix (scores identical to
  rank_bm25.BM25Okapi), so a query is one sparse mat-vec instead of a Python loop per term.
* Dense search is an exact NumPy inner product; FAISS is used only for very large corpora.
Ties are broken by document order (earliest verse first), so results are deterministic."""
from __future__ import annotations

import json
from difflib import SequenceMatcher
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from rank_bm25 import BM25Okapi
from scipy import sparse

try:  # optional accelerator, only worth it for very large corpora
    import faiss
except ImportError:  # pragma: no cover
    faiss = None

from . import embedder as emb
from .arabic import key_tokens, register_vocabulary

RRF_K = 60
QURAN_VERSES = 6236
FAISS_MIN_DOCS = 50_000


@dataclass
class Doc:
    id: str
    kind: str                      # "quran" | "hadith"
    text: str
    ref: dict = field(default_factory=dict)
    grades: list[dict] = field(default_factory=list)
    url: str = ""
    verified: bool = False

    @property
    def keys(self) -> list[str]:
        return key_tokens(self.text)


@dataclass
class Hit:
    doc: Doc
    fused: float
    bm25_rank: int | None
    dense_rank: int | None


def _close(a: str, b: str) -> bool:
    """Two words differing by a small spelling slip (a dropped, added or changed letter)."""
    if min(len(a), len(b)) < 2:
        return False
    return SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.75


class HybridIndex:
    def __init__(self, docs: list[Doc], embedder: emb.Embedder, vectors: np.ndarray):
        self.docs = docs
        register_vocabulary(d.text for d in docs)
        self.embedder = embedder
        self._keys = [d.keys for d in docs]
        # Positions of every key word, to find records that contain a quotation
        # word for word even when ranking misses them (an excerpt of a long verse).
        self._positions: dict[str, list[tuple[int, int]]] = {}
        for doc_i, keys in enumerate(self._keys):
            for pos, key in enumerate(keys):
                self._positions.setdefault(key, []).append((doc_i, pos))
        self.by_verse = {
            (d.ref["surah"], d.ref["ayah"]): d for d in docs if d.kind == "quran"
        }
        self._build_bm25()
        self._vectors = np.ascontiguousarray(vectors, dtype="float32")
        self._kind_mask = {
            kind: np.array([d.kind == kind for d in docs]) for kind in {d.kind for d in docs}
        }
        self._faiss = None
        if faiss is not None and len(docs) >= FAISS_MIN_DOCS:
            self._faiss = faiss.IndexFlatIP(self._vectors.shape[1])
            self._faiss.add(self._vectors)

    def _build_bm25(self) -> None:
        """Precompute BM25Okapi term weights as a sparse (docs x terms) matrix."""
        bm25 = BM25Okapi(self._keys)
        self._vocab = {term: j for j, term in enumerate(bm25.idf)}
        rows, cols, vals = [], [], []
        for i, freqs in enumerate(bm25.doc_freqs):
            norm = bm25.k1 * (1 - bm25.b + bm25.b * bm25.doc_len[i] / bm25.avgdl)
            for term, f in freqs.items():
                rows.append(i)
                cols.append(self._vocab[term])
                vals.append(bm25.idf[term] * (f * (bm25.k1 + 1) / (f + norm)))
        self._bm25_w = sparse.csr_matrix(
            (np.array(vals), (rows, cols)), shape=(len(self._keys), len(self._vocab))
        )

    def bm25_scores(self, tokens: list[str]) -> np.ndarray:
        """Same values as ``BM25Okapi.get_scores`` (repeated query terms count again)."""
        q = np.zeros(len(self._vocab))
        for t in tokens:
            j = self._vocab.get(t)
            if j is not None:
                q[j] += 1.0
        return self._bm25_w @ q

    # ------------------------------------------------------------------ build/io
    @classmethod
    def build(cls, docs: list[Doc], embedder_name: str) -> "HybridIndex":
        embedder = emb.create(embedder_name)
        texts = [d.text for d in docs]
        embedder.fit(texts)
        return cls(docs, embedder, embedder.encode(texts))

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        with open(directory / "docs.jsonl", "w", encoding="utf-8") as fh:
            for d in self.docs:
                fh.write(json.dumps(asdict(d), ensure_ascii=False) + "\n")
        np.save(directory / "vectors.npy", self._vectors)
        self.embedder.save(directory)
        meta = {"embedder": self.embedder.name, **self.stats()}
        (directory / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")

    @classmethod
    def load(cls, directory: Path) -> "HybridIndex":
        meta = json.loads((directory / "meta.json").read_text("utf-8"))
        with open(directory / "docs.jsonl", encoding="utf-8") as fh:
            docs = [Doc(**json.loads(line)) for line in fh if line.strip()]
        embedder = emb.load(meta["embedder"], directory)
        return cls(docs, embedder, np.load(directory / "vectors.npy"))

    # --------------------------------------------------------------------- query
    def stats(self) -> dict:
        kinds = [d.kind for d in self.docs]
        return {
            "embedder": self.embedder.name,
            "docs": len(self.docs),
            "quran": kinds.count("quran"),
            "hadith": kinds.count("hadith"),
            "verified_docs": sum(d.verified for d in self.docs),
            "quran_complete": kinds.count("quran") >= QURAN_VERSES,
        }

    def verse_run(self, doc: Doc, extra: int) -> Doc | None:
        """Concatenate a verse with the next ``extra`` verses (for multi-verse quotes)."""
        surah, ayah = doc.ref["surah"], doc.ref["ayah"]
        parts = [doc]
        for n in range(1, extra + 1):
            nxt = self.by_verse.get((surah, ayah + n))
            if nxt is None:
                return None
            parts.append(nxt)
        return Doc(
            id=f"quran-{surah}:{ayah}-{ayah + extra}",
            kind="quran",
            text=" ".join(p.text for p in parts),
            ref={**doc.ref, "ayah_end": ayah + extra},
            verified=all(p.verified for p in parts),
        )

    def count_containing(self, keys: list[str], kind: str = "quran") -> int:
        """Number of records whose text contains ``keys`` as a contiguous word run."""
        n = len(keys)
        total = 0
        for d, k in zip(self.docs, self._keys):
            if d.kind == kind and any(k[i : i + n] == keys for i in range(len(k) - n + 1)):
                total += 1
        return total

    def phrase_matches(self, keys: list[str], mask: np.ndarray, limit: int) -> list[int]:
        """Records containing ``keys`` (3+ words) as a contiguous run, shortest first."""
        if len(keys) < 3:
            return []
        found = []
        for doc_i, pos in self._positions.get(keys[0], ()):
            if mask[doc_i] and self._keys[doc_i][pos : pos + len(keys)] == keys:
                found.append(doc_i)
        found = sorted(set(found), key=lambda i: (len(self._keys[i]), i))
        return found[:limit]

    def near_phrase_matches(self, keys: list[str], mask: np.ndarray, limit: int) -> list[int]:
        """Records containing ``keys`` contiguously with one word (two for 6+ words) misspelled:
        the misspelled word must still be close in spelling («احي» ~ «احيي»)."""
        n = len(keys)
        if n < 3:
            return []
        allowed = 1 if n < 6 else 2
        found: set[int] = set()
        for anchor in range(min(2, n)):              # a typo may be in the first word
            for doc_i, pos in self._positions.get(keys[anchor], ()):
                start = pos - anchor
                window = self._keys[doc_i][start : start + n] if start >= 0 else []
                if not mask[doc_i] or len(window) != n:
                    continue
                misses = [(a, b) for a, b in zip(keys, window) if a != b]
                if 0 < len(misses) <= allowed and all(_close(a, b) for a, b in misses):
                    found.add(doc_i)
        return sorted(found, key=lambda i: (len(self._keys[i]), i))[:limit]

    def _with_phrase_matches(self, top: list[tuple[int, float]], keys: list[str], mask: np.ndarray, k: int):
        """Keep the fused ranking, but make sure records that contain the quotation
        word for word (or with one misspelled word) are among the candidates passed
        to the word alignment."""
        exact = self.phrase_matches(keys, mask, k)
        exact += [i for i in self.near_phrase_matches(keys, mask, k) if i not in exact]
        exact = exact[:k]
        present = {i for i, _ in top}
        missing = [i for i in exact if i not in present]
        if not missing:
            return top
        # Added after the ranked candidates, never in place of them: the same words typed
        # with or without a slip should be compared with the same verses.
        floor = min((score for _, score in top), default=0.0)
        return top + [(i, floor) for i in missing]

    def search(self, text: str, kind: str | None = None, k: int = 8) -> list[Hit]:
        if kind is None:
            mask = np.ones(len(self.docs), dtype=bool)
        elif kind in self._kind_mask:
            mask = self._kind_mask[kind]
        else:
            return []
        depth = k * 3

        bm25_scores = self.bm25_scores(key_tokens(text))
        cand = np.flatnonzero(mask & (bm25_scores > 0))
        bm25_order = cand[np.argsort(-bm25_scores[cand], kind="stable")][:depth].tolist()

        query_vec = self.embedder.encode([text])
        if self._faiss is not None:
            _, ids = self._faiss.search(query_vec, len(self.docs))
            dense_order = [int(i) for i in ids[0] if mask[i]][:depth]
        else:
            cand = np.flatnonzero(mask)
            sims = self._vectors[cand] @ query_vec[0]
            dense_order = cand[np.argsort(-sims, kind="stable")][:depth].tolist()

        bm25_rank = {doc_i: r for r, doc_i in enumerate(bm25_order)}
        dense_rank = {doc_i: r for r, doc_i in enumerate(dense_order)}
        fused: dict[int, float] = {}
        for rank_map in (bm25_rank, dense_rank):
            for doc_i, r in rank_map.items():
                fused[doc_i] = fused.get(doc_i, 0.0) + 1.0 / (RRF_K + r + 1)

        top = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:k]
        top = self._with_phrase_matches(top, key_tokens(text), mask, k)
        return [
            Hit(self.docs[i], score, bm25_rank.get(i), dense_rank.get(i)) for i, score in top
        ]

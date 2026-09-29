"""Hybrid index: BM25 (lexical, stemmed keys) + dense vectors (inner product),
fused with Reciprocal Rank Fusion. Uses FAISS when installed, otherwise exact
NumPy search (identical results; fast enough for tens of thousands of texts). The index holds both Quran and Hadith records;
each search can be restricted to one collection."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

try:  # optional accelerator
    import faiss
except ImportError:  # pragma: no cover
    faiss = None
from rank_bm25 import BM25Okapi

from . import embedder as emb
from .arabic import key_tokens

RRF_K = 60
QURAN_VERSES = 6236


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


class HybridIndex:
    def __init__(self, docs: list[Doc], embedder: emb.Embedder, vectors: np.ndarray):
        self.docs = docs
        self.embedder = embedder
        self._keys = [d.keys for d in docs]
        self.by_verse = {
            (d.ref["surah"], d.ref["ayah"]): d for d in docs if d.kind == "quran"
        }
        self._bm25 = BM25Okapi(self._keys)
        self._vectors = np.ascontiguousarray(vectors, dtype="float32")
        self._faiss = None
        if faiss is not None:
            self._faiss = faiss.IndexFlatIP(self._vectors.shape[1])
            self._faiss.add(self._vectors)

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

    def search(self, text: str, kind: str | None = None, k: int = 8) -> list[Hit]:
        allowed = [i for i, d in enumerate(self.docs) if kind is None or d.kind == kind]
        if not allowed:
            return []
        allowed_set = set(allowed)

        bm25_scores = self._bm25.get_scores(key_tokens(text))
        bm25_order = [i for i in np.argsort(-bm25_scores) if i in allowed_set and bm25_scores[i] > 0]

        query_vec = self.embedder.encode([text])
        if self._faiss is not None:
            _, ids = self._faiss.search(query_vec, len(self.docs))
            order = ids[0]
        else:
            order = np.argsort(-(self._vectors @ query_vec[0]))
        dense_order = [int(i) for i in order if int(i) in allowed_set]

        bm25_rank = {doc_i: r for r, doc_i in enumerate(bm25_order[: k * 3])}
        dense_rank = {doc_i: r for r, doc_i in enumerate(dense_order[: k * 3])}
        fused: dict[int, float] = {}
        for rank_map in (bm25_rank, dense_rank):
            for doc_i, r in rank_map.items():
                fused[doc_i] = fused.get(doc_i, 0.0) + 1.0 / (RRF_K + r + 1)

        top = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:k]
        return [
            Hit(self.docs[i], score, bm25_rank.get(i), dense_rank.get(i)) for i, score in top
        ]

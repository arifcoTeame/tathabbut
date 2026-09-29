"""Dense embedding backends.

* ``bge-m3``      BAAI/bge-m3 via sentence-transformers (multilingual, ~2.3 GB RAM).
                  Needs requirements-bge.txt. Best quality; host on HF Spaces.
* ``tfidf-char``  Character n-gram TF-IDF (2-4) + SVD to 256 dims. Few MB, CPU-only, robust to
                  Arabic spelling variation. Default fallback (Render free tier,
                  CI, offline machines).

Both return L2-normalized float32 vectors so inner product == cosine.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np

from .arabic import normalize, strip_diacritics


class Embedder:
    name: str = "base"

    def fit(self, texts: list[str]) -> None:  # only needed by corpus-fitted models
        pass

    def encode(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError

    def save(self, directory: Path) -> None:
        pass

    @classmethod
    def load(cls, directory: Path) -> "Embedder":
        return cls()


def _l2(x: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (x / norms).astype("float32")


class TfidfCharEmbedder(Embedder):
    """Character n-gram TF-IDF compressed with truncated SVD (LSA) to <=256 dims,
    so the full Quran index stays a few MB instead of ~1 GB of dense vectors."""

    name = "tfidf-char"
    _file = "tfidf_char.pkl"
    max_dims = 256

    def __init__(self) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True, min_df=1
        )
        self.svd = None

    def fit(self, texts: list[str]) -> None:
        from sklearn.decomposition import TruncatedSVD

        matrix = self.vectorizer.fit_transform([normalize(t) for t in texts])
        dims = min(self.max_dims, matrix.shape[0] - 1, matrix.shape[1] - 1)
        self.svd = TruncatedSVD(n_components=dims, random_state=0).fit(matrix)

    def encode(self, texts: list[str]) -> np.ndarray:
        matrix = self.vectorizer.transform([normalize(t) for t in texts])
        return _l2(self.svd.transform(matrix))

    def save(self, directory: Path) -> None:
        with open(directory / self._file, "wb") as fh:
            pickle.dump({"vectorizer": self.vectorizer, "svd": self.svd}, fh)

    @classmethod
    def load(cls, directory: Path) -> "TfidfCharEmbedder":
        obj = cls()
        with open(directory / cls._file, "rb") as fh:
            state = pickle.load(fh)
        obj.vectorizer, obj.svd = state["vectorizer"], state["svd"]
        return obj


class BgeM3Embedder(Embedder):
    name = "bge-m3"
    model_id = "BAAI/bge-m3"

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer  # optional dependency

        self.model = SentenceTransformer(self.model_id, device="cpu")

    def encode(self, texts: list[str]) -> np.ndarray:
        vectors = self.model.encode(
            [strip_diacritics(t) for t in texts],
            batch_size=16,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype="float32")


BACKENDS: dict[str, type[Embedder]] = {
    TfidfCharEmbedder.name: TfidfCharEmbedder,
    BgeM3Embedder.name: BgeM3Embedder,
}


def create(name: str) -> Embedder:
    if name not in BACKENDS:
        raise ValueError(f"Unknown embedder '{name}'. Choose one of {sorted(BACKENDS)}")
    return BACKENDS[name]()


def load(name: str, directory: Path) -> Embedder:
    return BACKENDS[name].load(directory)

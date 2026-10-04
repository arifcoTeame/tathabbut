"""Build the hybrid index (BM25 + dense) from the approved sources.

Usage (from backend/):
    python scripts/build_index.py                      # tfidf-char, seed data
    python scripts/build_index.py --embedder bge-m3    # BGE-M3 (needs requirements-bge.txt)

Quran source priority: data/raw/quran_full.json (fetch_quran.py) > data/quran/quran_full.json (bundled Tanzil copy)
> data/seed/quran_seed.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import ROOT, settings  # noqa: E402
from app.core.index import Doc, HybridIndex  # noqa: E402
from app.core.quran_meta import surah_name  # noqa: E402

DATA = ROOT / "data"


FULL_QURAN_CANDIDATES = (DATA / "raw" / "quran_full.json", DATA / "quran" / "quran_full.json")


def full_quran_path() -> Path | None:
    return next((p for p in FULL_QURAN_CANDIDATES if p.exists()), None)


BASMALA = "بسم الله الرحمن الرحيم"


def verse_text(record: dict) -> str:
    """The Tanzil file prepends the basmala to verse 1 of every surah except
    al-Fatiha (where it is verse 1) and at-Tawba (which has none). In the
    Madani mushaf numbering it is not part of that verse, so it is separated
    here for indexing and display; the bundled file itself stays verbatim."""
    text = record["text"]
    if record["ayah"] == 1 and record["surah"] != 1 and text.startswith(BASMALA + " "):
        return text[len(BASMALA) + 1:]
    return text


def load_quran(prefer_full: bool = True) -> tuple[list[Doc], str]:
    full = full_quran_path()
    use_full = prefer_full and full is not None
    path, verified = (full, True) if use_full else (DATA / "seed" / "quran_seed.json", False)
    records = json.loads(path.read_text("utf-8"))["records"]
    docs = [
        Doc(
            id=f"quran-{r['surah']}:{r['ayah']}",
            kind="quran",
            text=verse_text(r),
            ref={"surah": r["surah"], "ayah": r["ayah"], "surah_name": surah_name(r["surah"])},
            verified=verified,
        )
        for r in records
    ]
    return docs, path.name


def load_hadith() -> list[Doc]:
    records = json.loads((DATA / "seed" / "hadith_seed.json").read_text("utf-8"))["records"]
    docs = []
    for r in records:
        query = " ".join(r["text"].split()[:6])
        docs.append(
            Doc(
                id=f"hadith-{r['id']}",
                kind="hadith",
                text=r["text"],
                ref={"narrator": r.get("narrator", ""), "context": r.get("dorar_text", "")},
                grades=r["grades"],
                url=r.get("url") or f"https://dorar.net/hadith/search?q={quote(query)}",
                verified=bool(r.get("verified")),
            )
        )
    return docs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--embedder", default="tfidf-char", choices=["tfidf-char", "bge-m3"])
    ap.add_argument("--out", type=Path, default=settings.index_dir)
    args = ap.parse_args()

    t0 = time.time()
    quran, quran_file = load_quran()
    hadith = load_hadith()
    index = HybridIndex.build(quran + hadith, args.embedder)
    index.save(args.out)
    print(f"Quran: {len(quran)} verses from {quran_file} | Hadith: {len(hadith)} records")
    print(f"Embedder: {args.embedder} | Saved to {args.out} | {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()

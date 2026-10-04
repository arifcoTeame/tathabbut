"""Reproducible, offline reference-retrieval comparison; not a verdict benchmark.

Prepare and inspect the fixture before running any retrieval. Running the benchmark
never changes expected references, source records, production thresholds or models.
From backend/:
  .venv/bin/python scripts/benchmark_retrieval.py --prepare-fixture
  .venv/bin/python scripts/benchmark_retrieval.py
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import re
import sys
import time
import unicodedata
from zoneinfo import ZoneInfo

import numpy as np
from threadpoolctl import threadpool_limits

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import ROOT  # noqa: E402
from app.core.arabic import key_tokens, wording_tokens  # noqa: E402
from app.core.index import Doc, HybridIndex, RRF_K  # noqa: E402
from scripts.build_index import load_hadith  # noqa: E402

FIXTURE = ROOT / "data/evaluation/retrieval-cases-v1.json"
OUTPUT = ROOT / "docs/evidence/retrieval-evaluation-2026-10-03.json"
QURAN = ROOT / "data/quran/quran_full.json"
HADITH = ROOT / "data/seed/hadith_seed.json"
SEED = "tathabbut-retrieval-protocol-2026-10-03-v1"
K = 8
ARABIC_LETTERS = re.compile(r"^[ء-غف-ي]+$")
NEGATIONS = {"لا", "ولا", "فلا", "لم", "ولم", "فلم", "لن", "ولن", "ليس", "فليس", "وليس"}


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def stable_json(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def now() -> str:
    return datetime.now(ZoneInfo("Asia/Riyadh")).isoformat()


def corpus() -> list[Doc]:
    records = json.loads(QURAN.read_text("utf-8"))["records"]
    docs = [Doc(id=f"quran-{r['surah']}:{r['ayah']}", kind="quran", text=r["text"],
                ref={"surah": r["surah"], "ayah": r["ayah"]}, verified=True) for r in records]
    docs += load_hadith()
    if len(docs) != 6248 or sum(d.kind == "quran" for d in docs) != 6236:
        raise ValueError("Protocol v1 requires exactly 6236 Quran verses and 12 seed hadiths")
    return docs


def content_digest(docs: list[Doc]) -> str:
    return digest(stable_json([{"id": d.id, "kind": d.kind, "text": d.text} for d in docs]))


def transpose_one_word(text: str) -> str | None:
    words = text.split()
    for i in sorted(range(len(words)), key=lambda n: (-len(words[n]), n)):
        word = words[i]
        if len(word) < 4 or not ARABIC_LETTERS.fullmatch(word):
            continue
        for j in range(1, len(word) - 1):
            if word[j] != word[j + 1]:
                words[i] = word[:j] + word[j + 1] + word[j] + word[j + 2:]
                return " ".join(words)
    return None


def mutations(text: str):
    words = wording_tokens(text)
    plain = " ".join(words)
    yield "verbatim", text, plain
    yield "punctuation_spacing", "« " + " ،  ".join(words) + " »", plain
    # Artificial marks test processing only. This is NOT a proposed vocalization.
    vowels = " ".join(w[:1] + "َ" + w[1:] for w in words)
    yield "synthetic_vowel_noise", vowels, plain
    folded = plain.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا"}))
    if folded != plain:
        yield "hamza_folding", folded, plain
    decomposed = unicodedata.normalize("NFD", plain)
    if decomposed != plain:
        yield "unicode_decomposed", decomposed, plain
    if len(words) >= 8:
        start = (len(words) - 5) // 2
        anchor = " ".join(words[start:start + 5])
        yield "five_word_excerpt", anchor, anchor
        corrupted = transpose_one_word(anchor)
        if corrupted:
            yield "five_word_excerpt_transposition", corrupted, anchor
    else:
        corrupted = transpose_one_word(plain)
        if corrupted:
            yield "single_word_transposition", corrupted, plain
    # Relevance remains the original source to be retrieved for comparison.
    # Successful retrieval must NEVER be read as approving these altered inputs.
    yield "negation_added", "لا " + plain, plain
    for i, word in enumerate(words):
        if word in NEGATIONS and len(words) > 2:
            yield "negation_removed", " ".join(words[:i] + words[i + 1:]), plain
            break


def prepare_fixture(path: Path, docs: list[Doc]) -> None:
    if path.exists():
        raise ValueError("Fixture exists; keep the frozen v1 or explicitly choose a new --fixture path")
    by_id = {d.id: d for d in docs}
    old_records = json.loads((ROOT / "data/seed/quran_seed.json").read_text("utf-8"))["records"]
    old_ids = {f"quran-{r['surah']}:{r['ayah']}" for r in old_records}
    # Conservatively exclude every chapter containing a Quran development example,
    # plus 55 and 65, used by test_full_corpus.py. All hadith records are development.
    excluded_surahs = {r["surah"] for r in old_records} | {55, 65}
    by_surah: dict[int, list[Doc]] = {}
    for doc in docs:
        if doc.kind == "quran" and doc.ref["surah"] not in excluded_surahs and 8 <= len(wording_tokens(doc.text)) <= 40:
            by_surah.setdefault(doc.ref["surah"], []).append(doc)
    chosen = [min(group, key=lambda d: digest((SEED + d.id).encode())) for group in by_surah.values()]
    chosen = sorted(chosen, key=lambda d: digest((SEED + "source" + d.id).encode()))[:72]
    selected = [(by_id[i], "development_reference") for i in sorted(old_ids)]
    selected += [(d, "development_reference") for d in docs if d.kind == "hadith"]
    selected += [(d, "new_reference") for d in sorted(chosen, key=lambda d: (d.ref["surah"], d.ref["ayah"]))]
    token_strings = {d.id: " " + " ".join(wording_tokens(d.text)) + " " for d in docs}
    cases = []
    for doc, split in selected:
        for family, query, anchor in mutations(doc.text):
            # Literal equivalents/containing passages are valid alternatives. For
            # corrupted input this uses the original anchor fixed BEFORE retrieval.
            needle = " " + anchor + " "
            relevant = [d.id for d in docs if d.kind == doc.kind and needle in token_strings[d.id]]
            if doc.id not in relevant:
                raise AssertionError(doc.id)
            cases.append({"id": f"{doc.id}/{family}", "split": split, "kind": doc.kind,
                          "family": family, "source_id": doc.id,
                          "source_text_sha256": digest(doc.text.encode()),
                          "query": query, "original_anchor": anchor, "relevant_ids": relevant})
    fixture = {
        "protocol": "reference-retrieval-v1", "frozen_at": now(), "selection_seed": SEED,
        "scope": "Synthetic reference retrieval only; NOT verdict correctness, a blind study, user benefit, or general accuracy",
        "selection": {"new_quran_sources": len(chosen), "new_quran_surahs": len({d.ref['surah'] for d in chosen}),
                      "development_sources": len(selected) - len(chosen),
                      "excluded_quran_surahs": sorted(excluded_surahs),
                      "method": "One hash-selected verse of 8-40 words per eligible surah; 72 surahs selected by fixed hash; no retrieval outcomes consulted"},
        "corpus_text_sha256": content_digest(docs),
        "files": {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in (QURAN, HADITH)},
        "expected_ids_policy": "All same-kind source records containing the unchanged original anchor as literal words; fixed before querying",
        "mutation_warning": "Vowels and changed letters/negations are artificial test inputs, not approved scripture or alternative readings",
        "ranking": {"k": K, "rrf_constant": 60, "production_candidate_depth": K * 3,
                    "kind_filter": "oracle kind supplied equally to all methods"},
        "counts": dict(Counter(c["split"] for c in cases)), "cases": cases,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"fixture": str(path), "sha256": digest(path.read_bytes()), "cases": len(cases),
                      "sources": len(selected), "split_counts": fixture["counts"]}, ensure_ascii=False))


def metrics(rows: list[dict], method: str) -> dict:
    ranks = [r["methods"][method]["first_relevant_rank"] for r in rows]
    n = len(rows)
    return {"queries": n,
            "hit_at_1": sum(r is not None and r <= 1 for r in ranks) / n,
            "hit_at_3": sum(r is not None and r <= 3 for r in ranks) / n,
            "hit_at_8": sum(r is not None and r <= 8 for r in ranks) / n,
            "mrr_at_8": sum(1 / r for r in ranks if r is not None) / n}


def evaluate(path: Path, output: Path, docs: list[Doc]) -> None:
    fixture_bytes = path.read_bytes()
    fixture = json.loads(fixture_bytes)
    if fixture["corpus_text_sha256"] != content_digest(docs):
        raise ValueError("Corpus text/order changed; the frozen fixture no longer matches")
    if fixture["ranking"]["k"] != K:
        raise ValueError("Fixture k differs from this protocol")
    if fixture["ranking"]["rrf_constant"] != RRF_K:
        raise ValueError("Production RRF constant differs from this frozen protocol")
    by_id = {d.id: d for d in docs}
    for case in fixture["cases"]:
        if case["source_text_sha256"] != digest(by_id[case["source_id"]].text.encode()):
            raise ValueError("Source text changed: " + case["id"])
        if not case["relevant_ids"] or any(i not in by_id for i in case["relevant_ids"]):
            raise ValueError("Invalid expected references: " + case["id"])
    started = time.perf_counter()
    with threadpool_limits(limits=1):
        index = HybridIndex.build(docs, "tfidf-char")
        build_seconds = time.perf_counter() - started
        results = []
        for case in fixture["cases"]:
            query, kind = case["query"], case["kind"]
            allowed = np.flatnonzero(np.array([d.kind == kind for d in docs]))
            bm25_scores = index.bm25_scores(key_tokens(query))
            bm25_candidates = allowed[bm25_scores[allowed] > 0]
            bm25_order = bm25_candidates[np.argsort(-bm25_scores[bm25_candidates], kind="stable")][:K]
            query_vector = index.embedder.encode([query])[0]
            similarities = index._vectors[allowed] @ query_vector
            dense_order = allowed[np.argsort(-similarities, kind="stable")][:K]
            rankings = {"bm25_only": [docs[i].id for i in bm25_order],
                        "tfidf_svd_only": [docs[i].id for i in dense_order],
                        # Use the production method directly, including its k*3 pool.
                        "hybrid_rrf": [h.doc.id for h in index.search(query, kind=kind, k=K)]}
            methods = {}
            for method, ranking in rankings.items():
                rank = next((n for n, doc_id in enumerate(ranking, 1) if doc_id in case["relevant_ids"]), None)
                methods[method] = {"top_ids": ranking, "first_relevant_rank": rank}
            results.append({"case_id": case["id"], "split": case["split"], "kind": kind,
                            "family": case["family"], "source_id": case["source_id"], "methods": methods})
    method_names = ["bm25_only", "tfidf_svd_only", "hybrid_rrf"]
    groups = {"all": results}
    for key in ("split", "kind", "family"):
        for value in sorted({r[key] for r in results}):
            groups[f"{key}/{value}"] = [r for r in results if r[key] == value]
    code_paths = [Path(__file__), ROOT / "backend/app/core/index.py",
                  ROOT / "backend/app/core/embedder.py", ROOT / "backend/app/core/arabic.py"]
    report = {"protocol": fixture["protocol"], "evaluated_at": now(),
              "scope": fixture["scope"], "fixture": str(path.relative_to(ROOT)),
              "fixture_sha256": digest(fixture_bytes), "fixture_frozen_at": fixture["frozen_at"],
              "corpus_text_sha256": content_digest(docs), "index_stats": index.stats(),
              "fresh_index": True, "network_used": False,
              "runtime": {"python": platform.python_version(),
                          "platform": platform.platform(),
                          "packages": {name: version(name) for name in
                                       ("numpy", "scipy", "scikit-learn", "rank-bm25", "threadpoolctl")}},
              "code_sha256": {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in code_paths},
              "ranking": fixture["ranking"], "build_seconds": round(build_seconds, 3),
              "total_seconds": round(time.perf_counter() - started, 3),
              "timing_scope": "Single-thread local offline evaluation, not latency/throughput or live service benchmark",
              "metric_definitions": {"hit_at_k": "Fraction with at least one fixed relevant reference in top k; not set recall",
                                     "mrr_at_8": "Mean reciprocal first relevant rank among top 8; absent = 0"},
              "groups": {name: {m: metrics(rows, m) for m in method_names} for name, rows in groups.items()},
              "regressions": {m: [r["case_id"] for r in results
                                  if r["methods"][m]["first_relevant_rank"] is not None
                                  and r["methods"]["hybrid_rrf"]["first_relevant_rank"] is None]
                              for m in ("bm25_only", "tfidf_svd_only")},
              "cases": results}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"output": str(output), "all": report["groups"]["all"],
                      "new": report["groups"].get("split/new_reference"), "seconds": report["total_seconds"]}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-fixture", action="store_true")
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    docs = corpus()
    if args.prepare_fixture:
        prepare_fixture(args.fixture, docs)
    else:
        evaluate(args.fixture, args.output, docs)


if __name__ == "__main__":
    main()

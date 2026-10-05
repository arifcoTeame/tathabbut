"""What does each retrieval method contribute when the quotation has typing errors?

For a fixed random sample of verses (seed 7) the script builds queries with the
mistakes people actually make when quoting from memory or typing on a phone,
then asks each method to find the source verse among all 6236:

  exact              the verse as written (control)
  letter_dropped     one letter missing in the longest word        («الصبرين»)
  letters_swapped    two neighbouring letters swapped in the longest word
  two_words_typos    the two longest words each lose one letter
  excerpt_with_typo  a 5-word excerpt from the middle with one letter missing

Methods: BM25 alone (word matching), TF-IDF character n-grams + SVD alone
(sub-word similarity), and the production hybrid (Reciprocal Rank Fusion).
A query counts as found at k when a verse in the top k really contains the
intended words (the source verse, an identical verse, or another verse in
which the quoted excerpt occurs word for word). Retrieval only proposes a
source; the verdict still comes from word-by-word alignment (a typo is shown
as a difference, never accepted as the verse).

    python scripts/benchmark_typos.py --output ../docs/evidence/retrieval-typos-<version>.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.arabic import key_tokens, strip_diacritics, wording_tokens  # noqa: E402
from app.core.index import HybridIndex  # noqa: E402
from app.core import pipeline  # noqa: E402
from app.core.judge import Thresholds  # noqa: E402
from app.core.pipeline import ENGINE_VERSION  # noqa: E402

K = 8


def drop_letter(word: str) -> str:
    return word[: len(word) // 2] + word[len(word) // 2 + 1:]


def swap_letters(word: str) -> str:
    i = len(word) // 2
    return word[:i - 1] + word[i] + word[i - 1] + word[i + 1:] if word[i] != word[i - 1] else drop_letter(word)


def queries(words: list[str]):
    """Yield (kind, query, intended words): the intended words are what the person meant to quote."""
    yield "exact", " ".join(words), words
    longest = sorted(range(len(words)), key=lambda i: (-len(words[i]), i))
    if len(words[longest[0]]) >= 4:
        w = list(words); w[longest[0]] = drop_letter(w[longest[0]]); yield "letter_dropped", " ".join(w), words
        w = list(words); w[longest[0]] = swap_letters(w[longest[0]]); yield "letters_swapped", " ".join(w), words
    if len(words) >= 4 and len(words[longest[1]]) >= 4:
        w = list(words)
        for i in longest[:2]:
            w[i] = drop_letter(w[i])
        yield "two_words_typos", " ".join(w), words
    if len(words) >= 9:
        s = (len(words) - 5) // 2
        ex = words[s:s + 5]
        j = max(range(5), key=lambda n: len(ex[n]))
        if len(ex[j]) >= 4:
            bad = list(ex); bad[j] = drop_letter(bad[j]); yield "excerpt_with_typo", " ".join(bad), ex


def contains(hay: list[str], needle: list[str]) -> bool:
    n = len(needle)
    return any(hay[i:i + n] == needle for i in range(len(hay) - n + 1))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=1000)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args(argv)
    index = HybridIndex.load(ROOT.parent / "data" / "index")
    docs = index.docs
    quran = [i for i, d in enumerate(docs) if d.kind == "quran"]
    allowed = np.array(quran)
    wording = {docs[i].id: wording_tokens(docs[i].text) for i in quran}

    def holds(doc_id: str, intended: list[str]) -> bool:
        """The returned verse (or verse run) really contains the intended words."""
        if not doc_id:
            return False
        loc = doc_id[len("quran-"):]
        if "-" in loc:
            s, a = loc.split("-")[0].split(":")
            b = int(loc.split("-")[1])
            hay = [w for n in range(int(a), b + 1) for w in wording.get(f"quran-{s}:{n}", [])]
        else:
            hay = wording.get(doc_id, [])
        return contains(hay, intended)
    rng = random.Random(7)
    sample = sorted(rng.sample(quran, args.sample))
    stats = defaultdict(lambda: defaultdict(lambda: {"n": 0, "hit1": 0, "hit8": 0}))
    for i in sample:
        doc = docs[i]
        words = strip_diacritics(doc.text).split()
        for kind, q, intended_raw in queries(words):
            intended = wording_tokens(" ".join(intended_raw))
            bm = index.bm25_scores(key_tokens(q))
            cand = allowed[bm[allowed] > 0]
            bm_order = [docs[j].id for j in cand[np.argsort(-bm[cand], kind="stable")][:K]]
            vec = index.embedder.encode([q])[0]
            sims = index._vectors[allowed] @ vec
            dense_order = [docs[j].id for j in allowed[np.argsort(-sims, kind="stable")][:K]]
            hybrid_order = [h.doc.id for h in index.search(q, kind="quran", k=K)]
            claim = pipeline.run(index, "﴿" + q + "﴾", Thresholds(), "{surah}")["claims"][0]
            src = (claim.get("source") or {}).get("id") or ""
            expected = "VERIFIED" if kind == "exact" else "ALTERED"
            e2e = stats[kind]["engine_end_to_end"]
            e2e["n"] += 1
            located = holds(src, intended)
            e2e["hit1"] += bool(located and claim["verdict"]["code"] == expected)
            e2e["hit8"] += bool(located)
            for method, order in (("bm25_only", bm_order), ("tfidf_svd_only", dense_order), ("hybrid_rrf", hybrid_order)):
                s = stats[kind][method]
                s["n"] += 1
                s["hit1"] += bool(order[:1] and holds(order[0], intended))
                s["hit8"] += any(holds(x, intended) for x in order)
    table = {kind: {m: ({"queries": v["n"], "correct_verse_and_verdict": round(v["hit1"] / v["n"], 4),
                         "correct_verse_shown": round(v["hit8"] / v["n"], 4)} if m == "engine_end_to_end" else
                        {"queries": v["n"], "hit_at_1": round(v["hit1"] / v["n"], 4), "hit_at_8": round(v["hit8"] / v["n"], 4)})
                    for m, v in methods.items()} for kind, methods in stats.items()}
    report = {"checked_at": datetime.now(ZoneInfo("Asia/Riyadh")).isoformat(), "engine_version": ENGINE_VERSION,
              "corpus": "6236 verses (King Fahd print text, Quranpedia)", "sample_verses": args.sample, "seed": 7,
              "k": K, "results": table,
              "engine_end_to_end": "The full engine on ﴿query﴾: correct_verse_and_verdict = the source verse is shown and the verdict is VERIFIED for the exact text, ALTERED (with the typo as a difference) otherwise.",
              "limits": ["Synthetic typing errors on a random verse sample; not user traffic.",
                         "Retrieval only: the verdict still requires word-by-word alignment, so a typo is reported as a difference."]}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    for kind, methods in table.items():
        print(kind, {m: tuple(list(v.values())[1:]) for m, v in methods.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())

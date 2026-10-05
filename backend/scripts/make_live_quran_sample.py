"""Build data/evaluation/live-quran-sample-v0.7.1.json: one verse from each of the 114
surahs (random, seed 114, 4+ words when the surah has such a verse) in three forms, for
checking the deployed site against the whole Quran rather than a single example.

    python scripts/make_live_quran_sample.py
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.arabic import key_tokens, wording_tokens  # noqa: E402
from scripts.verify_quran_variants import drop_middle, noisy, plain  # noqa: E402

DATA = ROOT.parent / "data"


def main() -> int:
    recs = json.loads((DATA / "quran/quran_kfc.json").read_text("utf-8"))["records"]
    words = {f"{r['surah']}:{r['ayah']}": tuple(wording_tokens(r["text"])) for r in recs}
    same: dict[tuple, list[str]] = {}
    for k, v in words.items():
        same.setdefault(v, []).append(k)
    by_surah: dict[int, list[dict]] = {}
    for r in recs:
        by_surah.setdefault(r["surah"], []).append(r)
    rng, cases = random.Random(114), []
    for s in range(1, 115):
        pool = [r for r in by_surah[s] if len(key_tokens(plain(r["text"]))) >= 4] or by_surah[s]
        r = rng.choice(pool)
        k = f"{s}:{r['ayah']}"
        accept = ["quran-" + x for x in same[words[k]]]
        forms = [("kfc_marked", "﴿" + r["text"] + "﴾", "VERIFIED"), ("noisy_unmarked", noisy(r["text"]), "VERIFIED"),
                 ("marked_word_missing", drop_middle(r["text"]), "ALTERED")]
        cases += [{"verse": k, "form": f, "text": t, "expect": e, "accept": accept} for f, t, e in forms if t]
    out = DATA / "evaluation/live-quran-sample-v0.7.1.json"
    meta = json.loads(out.read_text("utf-8"))["_meta"] if out.exists() else {}
    out.write_text(json.dumps({"_meta": meta, "cases": cases}, ensure_ascii=False, indent=0), "utf-8")
    print(len(cases))
    return 0


if __name__ == "__main__":
    sys.exit(main())

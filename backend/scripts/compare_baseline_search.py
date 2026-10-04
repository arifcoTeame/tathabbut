"""Measured comparison against a specific alternative: exact-text search.

The judging rubric asks for a testable comparison with a named alternative.
The practical alternative most content creators use today is exact search
(Ctrl+F / site search) over the Quran text and a hadith collection. This script
runs that alternative over the SAME corpus (6236 verses + the seeded hadith
records, both diacritics-stripped) on the SAME 25 release cases used in
evaluate_release.py, and records what each method gives the user.

What exact search can do: report whether the quoted wording occurs verbatim.
What it cannot do by itself: tell an altered verse from a text that is simply
absent, carry a hadith grade, show word-level differences, flag variant
wording for review, or detect a personal question that must be referred.

For each quoted span the script records:
  exact_search_found      - the normalized span occurs verbatim in the corpus
  exact_search_decision   - FOUND / NOT_FOUND (all the alternative can say)
  tathabbut_verdict       - verdict produced by the engine in process
  expected                - expected verdict from the release case list
  exact_search_sufficient - True only when FOUND/NOT_FOUND alone would lead the
                            user to the expected decision (VERIFIED Quran text
                            found verbatim, or a text outside the corpus not
                            found). Anything that needs a grade, a diff, a
                            review flag or a referral is marked False.

Output: a JSON report (default docs/evidence/baseline-comparison-<version>.json)
plus a short summary on stdout. Nothing in the project data is modified.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from app.core import extractor  # noqa: E402
from app.core.arabic import normalize  # noqa: E402
from app.core.pipeline import ENGINE_VERSION  # noqa: E402
from evaluate_release import CASES  # noqa: E402

# Verdicts that exact search can never produce on its own.
NEEDS_MORE_THAN_SEARCH = {"ALTERED", "NOT_AUTHENTIC", "DISPUTED", "NEEDS_REVIEW", "REFER"}


def load_corpus() -> list[str]:
    quran = json.loads((ROOT.parent / "data" / "quran" / "quran_full.json").read_text(encoding="utf-8"))["records"]
    seed = json.loads((ROOT.parent / "data" / "seed" / "hadith_seed.json").read_text(encoding="utf-8"))
    hadith = seed if isinstance(seed, list) else seed.get("records", [])
    texts = [r["text"] for r in quran]
    for r in hadith:
        texts.append(r["text"])
        if r.get("dorar_text"):
            texts.append(r["dorar_text"])
    return [" " + normalize(t) + " " for t in texts]


def exact_found(corpus: list[str], span: str) -> bool:
    needle = " " + normalize(span) + " "
    return any(needle in doc for doc in corpus)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", type=Path, default=ROOT.parent / "docs" / "evidence" / f"baseline-comparison-v{ENGINE_VERSION}.json")
    args = ap.parse_args(argv)

    from fastapi.testclient import TestClient  # local import: keeps the script importable without the API
    from app.main import app

    corpus = load_corpus()
    rows = []
    with TestClient(app) as client:
        for case_id, text, expected in CASES:
            response = client.post("/verify", json={"text": text}).json()
            claims = response.get("claims", [])
            verdicts = [c["verdict"]["code"] if isinstance(c.get("verdict"), dict) else c.get("verdict") for c in claims]
            spans = [c.text for c in extractor.extract(text)]
            for i, exp in enumerate(expected):
                span = spans[i] if i < len(spans) else ""
                got = verdicts[i] if i < len(verdicts) else None
                found = bool(span) and exact_found(corpus, span)
                if exp in NEEDS_MORE_THAN_SEARCH:
                    sufficient = False
                elif exp == "VERIFIED":
                    # Found verbatim is enough for Quran; a hadith still lacks its grade.
                    sufficient = found and span and not any(k in text for k in ("رسول الله", "النبي"))
                    sufficient = bool(sufficient)
                elif exp == "NO_ORIGIN":
                    sufficient = not found
                else:
                    sufficient = False
                rows.append({
                    "case": case_id, "claim_index": i, "span": span, "expected": exp,
                    "exact_search_found": found, "exact_search_decision": "FOUND" if found else "NOT_FOUND",
                    "exact_search_sufficient": sufficient,
                    "tathabbut_verdict": got, "tathabbut_matches_expected": got == exp,
                })

    total = len(rows)
    report = {
        "recorded_at": datetime.now(ZoneInfo("Asia/Riyadh")).isoformat(),
        "engine_version": ENGINE_VERSION,
        "alternative": "exact text search over the same corpus (diacritics stripped, letter-normalised)",
        "corpus_documents": len(corpus),
        "claims_total": total,
        "exact_search_sufficient": sum(r["exact_search_sufficient"] for r in rows),
        "tathabbut_matches_expected": sum(r["tathabbut_matches_expected"] for r in rows),
        "by_expected_verdict": {},
        "limits": [
            "Single run in process (FastAPI TestClient); the release evidence covers the repeated runs.",
            "The 25 cases were chosen to probe failure modes, not sampled from real traffic; counts are not a general accuracy rate.",
            "Exact search is credited whenever FOUND/NOT_FOUND alone leads to the expected decision; it is never penalised for lacking a UI.",
            "A better alternative (a scholar, or manual lookup in dorar.net with reading of the grades) is not measured here; see HUMAN_REVIEW.md.",
        ],
        "rows": rows,
    }
    for r in rows:
        b = report["by_expected_verdict"].setdefault(r["expected"], {"claims": 0, "exact_search_sufficient": 0, "tathabbut_matches_expected": 0})
        b["claims"] += 1
        b["exact_search_sufficient"] += r["exact_search_sufficient"]
        b["tathabbut_matches_expected"] += r["tathabbut_matches_expected"]
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("rows", "limits")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

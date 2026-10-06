"""Measured benefit against a named alternative: exact text search.

Track 04 asks whether the tool improves the accuracy of verifying a quotation and
shows the source and the state of the evidence. The alternative most people use
today is to search the quoted words (Ctrl+F, site search, a search engine). This
script gives that alternative every advantage it can have and compares it with
Tathabbut on four reproducible sets:

  1. release      - the targeted release cases (scripts/evaluate_release.py)
  2. hadith_forms - every hadith record, asked in three ways people write:
                    «قال رسول الله ﷺ: «…»», «ما صحة حديث …؟», «سمعت أن النبي قال …، صحيح؟»
  3. quran_sample - one verse per surah in three forms (data/evaluation/live-quran-sample-v0.7.1.json)
  4. quran_typos  - verses with typing errors (docs/evidence/retrieval-typos-*.json, read, not re-run)

A result is ACTIONABLE when it gives the user the right publish decision together
with what is needed to act on it: the verse and its place for a Quran text, the
corrected wording for an altered verse, the recorded grade for a hadith, a
referral for a personal question, an out-of-scope notice for a general question,
and «not found» for a text that is in neither source.

Exact search is credited generously: it is given only the quoted words (the user
is assumed to strip «قال رسول الله ﷺ», «ما صحة حديث» … by hand), letters and
diacritics are normalised, and a verbatim Quran hit counts as actionable because
the hit carries the verse number. It cannot supply a hadith grade, a corrected
verse, a referral or a scope notice, so those cases are not credited to it.

Output: docs/evidence/benefit-comparison-v<version>.json. Nothing is modified.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT.parent / "data"
EVIDENCE = ROOT.parent / "docs" / "evidence"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from app.core import extractor  # noqa: E402
from app.core.arabic import normalize  # noqa: E402
from app.core.pipeline import ENGINE_VERSION  # noqa: E402
from evaluate_release import CASES  # noqa: E402

FOUND_CODES = {"VERIFIED", "NOT_AUTHENTIC", "DISPUTED"}


def corpus() -> tuple[list[str], list[str]]:
    quran = json.loads((DATA / "quran" / "quran_kfc.json").read_text("utf-8"))["records"]
    hadith = json.loads((DATA / "seed" / "hadith_seed.json").read_text("utf-8"))["records"]
    q = [" " + normalize(r["text"]) + " " for r in quran]
    h = []
    for r in hadith:
        h.append(" " + normalize(r["text"]) + " ")
        if r.get("dorar_text"):
            h.append(" " + normalize(r["dorar_text"]) + " ")
    return q, h


def found_in(docs: list[str], span: str) -> bool:
    needle = " " + normalize(span) + " "
    return len(needle.split()) > 0 and any(needle in d for d in docs)


def exact_actionable(expected: str, span: str, q: list[str], h: list[str]) -> bool:
    """What exact search alone lets the user do correctly."""
    if expected == "VERIFIED":
        return found_in(q, span)            # a verbatim verse hit carries its place; a hadith hit has no grade
    if expected == "NO_ORIGIN":
        return not found_in(q, span) and not found_in(h, span)
    return False                            # grade, correction, referral or scope notice: not available


def engine_actionable(expected: str, got: dict | None, expected_source: str | None = None) -> bool:
    if got is None or got["verdict"]["code"] != expected:
        return False
    if expected_source is not None:
        src = (got.get("source") or {}).get("id")
        return src == expected_source
    if expected in FOUND_CODES | {"ALTERED"}:
        return got.get("source") is not None
    return True


def summarise(rows: list[dict]) -> dict:
    n = len(rows)
    e = sum(r["exact_search_actionable"] for r in rows)
    t = sum(r["tathabbut_actionable"] for r in rows)
    return {"items": n, "exact_search_actionable": e, "tathabbut_actionable": t,
            "exact_search_rate": round(e / n, 4) if n else None, "tathabbut_rate": round(t / n, 4) if n else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", type=Path, default=EVIDENCE / f"benefit-comparison-v{ENGINE_VERSION}.json")
    ap.add_argument("--typos", type=Path, default=None, help="retrieval-typos evidence to read")
    args = ap.parse_args(argv)

    from fastapi.testclient import TestClient
    from app.main import app

    q, h = corpus()
    sets: dict[str, list[dict]] = {"release": [], "hadith_forms": [], "quran_sample": []}
    with TestClient(app) as client:
        post = lambda text: client.post("/verify", json={"text": text}).json()["claims"]

        for case_id, text, expected in CASES:
            claims = post(text)
            spans = [c.text for c in extractor.extract(text)]
            for i, exp in enumerate(expected):
                got = claims[i] if i < len(claims) else None
                span = spans[i] if i < len(spans) else ""
                sets["release"].append({
                    "case": case_id, "claim": i, "expected": exp, "tathabbut": got and got["verdict"]["code"],
                    "exact_search_actionable": exact_actionable(exp, span, q, h),
                    "tathabbut_actionable": engine_actionable(exp, got),
                })

        records = json.loads((DATA / "seed" / "hadith_seed.json").read_text("utf-8"))["records"]
        for r in records:
            canonical = post(f"قال رسول الله ﷺ: «{r['text']}»")[0]
            exp, src = canonical["verdict"]["code"], (canonical.get("source") or {}).get("id")
            for form, text in (
                ("quoted", f"قال رسول الله ﷺ: «{r['text']}»"),
                ("what_is_its_grade", f"ما صحة حديث {r['text']}؟"),
                ("heard_that", f"سمعت أن النبي قال {r['text']}، صحيح؟"),
            ):
                got = post(text)[0]
                sets["hadith_forms"].append({
                    "record": r["id"], "form": form, "expected": exp, "tathabbut": got["verdict"]["code"],
                    "exact_search_found_text": found_in(h, r["text"]),
                    "exact_search_actionable": exact_actionable(exp, r["text"], q, h),
                    "tathabbut_actionable": src is not None and engine_actionable(exp, got, src),
                })

        sample = json.loads((DATA / "evaluation" / "live-quran-sample-v0.7.1.json").read_text("utf-8"))["cases"]
        for c in sample:
            got = post(c["text"])[0]
            span = extractor.extract(c["text"])[0].text
            ok = got["verdict"]["code"] == c["expect"] and (got.get("source") or {}).get("id") in c["accept"]
            sets["quran_sample"].append({
                "verse": c["verse"], "form": c["form"], "expected": c["expect"], "tathabbut": got["verdict"]["code"],
                "exact_search_actionable": exact_actionable(c["expect"], span, q, h),
                "tathabbut_actionable": ok,
            })

    report = {
        "recorded_at": datetime.now(ZoneInfo("Asia/Riyadh")).isoformat(),
        "engine_version": ENGINE_VERSION,
        "alternative": "exact text search over the same sources (Quranpedia KFC text and the platform's hadith records), "
                       "letters and diacritics normalised, given only the quoted words",
        "definition": "actionable = right publish decision plus what is needed to act on it (verse and place, corrected wording, "
                      "recorded grade, referral, scope notice, or not-found)",
        "summary": {name: summarise(rows) for name, rows in sets.items()},
        "by_form": {},
        "limits": [
            "Automated measurement, not a user study: it shows what each method can give, not how people use it.",
            "The release cases were chosen to probe failure modes; the hadith forms use every record in the platform's limited base; "
            "the Quran sample has one random verse per surah. Rates are not a general accuracy claim.",
            "Exact search is credited generously (see the script docstring). A scholar or a careful reading of dorar.net is a "
            "stronger alternative and is not measured here.",
            "For hadith forms the expected verdict is the engine's own verdict on the canonical quoted form, which the release cases "
            "and the Dorar entry check (dorar-links-v0.8.0) validate; this set measures robustness to how the question is written.",
        ],
        "rows": sets,
    }
    report["summary"]["hadith_forms"]["exact_search_found_text"] = sum(r["exact_search_found_text"] for r in sets["hadith_forms"])
    for name in ("hadith_forms", "quran_sample"):
        forms = sorted({r["form"] for r in sets[name]})
        report["by_form"][name] = {f: summarise([r for r in sets[name] if r["form"] == f]) for f in forms}

    typos_path = args.typos or max(EVIDENCE.glob("retrieval-typos-v*.json"))
    typos = json.loads(typos_path.read_text("utf-8"))
    t_rows = {}
    for kind, res in typos["results"].items():
        e2e = res["engine_end_to_end"]
        t_rows[kind] = {
            "items": e2e["queries"],
            "tathabbut_rate": e2e["correct_verse_and_verdict"],
            # exact search finds a verse only when the text is typed exactly as in the mushaf
            "exact_search_rate": 1.0 if kind == "exact" else 0.0,
        }
    report["summary"]["quran_typos"] = {"source": typos_path.name, "by_error_type": t_rows}

    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=1))
    print(json.dumps(report["by_form"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

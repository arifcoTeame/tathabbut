"""Enter every verse of the Quran into the engine in three spellings and record the verdicts.

  kfc_marked     the King Fahd print text (Quranpedia, with diacritics) as ﴿…﴾
  tanzil_marked  the Tanzil «simple clean» text (no diacritics, other spelling source) as ﴿…﴾
  plain_unmarked no diacritics, no hamza on alef, ة→ه, ى→ي, and no ﴿﴾ or «قال تعالى»:
                 the way people often paste a verse (e.g. «قل هو الله احد»)

Expected: every verse VERIFIED at its own location or at a location whose wording is
identical. Very short verses (fewer than 3 words, e.g. «الم») are only accepted as Quran
when presented as a verse, so they are reported separately for the unmarked run.

    python scripts/verify_quran_variants.py --output ../docs/evidence/quran-variants-<version>.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import pipeline  # noqa: E402
from app.core.arabic import key_tokens, strip_diacritics, wording_tokens  # noqa: E402
from app.core.index import HybridIndex  # noqa: E402
from app.core.judge import Thresholds  # noqa: E402
from scripts.build_index import verse_text  # noqa: E402

DATA = ROOT.parent / "data"
PLAIN = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي"})


def plain(text: str) -> str:
    return re.sub(r"\s+", " ", strip_diacritics(text).translate(PLAIN)).strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--runs", default="kfc_marked,tanzil_marked,plain_unmarked")
    args = ap.parse_args(argv)
    index = HybridIndex.load(DATA / "index")
    kfc = {(r["surah"], r["ayah"]): r["text"] for r in json.loads((DATA / "quran/quran_kfc.json").read_text("utf-8"))["records"]}
    tanzil = {(r["surah"], r["ayah"]): verse_text(r) for r in json.loads((DATA / "quran/quran_full.json").read_text("utf-8"))["records"]}
    wording = {k: wording_tokens(v) for k, v in kfc.items()}
    keys = sorted(kfc)[: args.limit or None]
    runs = {"kfc_marked": lambda k: "﴿" + kfc[k] + "﴾",
            "tanzil_marked": lambda k: "﴿" + tanzil[k] + "﴾",
            "plain_unmarked": lambda k: plain(kfc[k])}
    report = {"checked_at": datetime.now(ZoneInfo("Asia/Riyadh")).isoformat(), "engine_version": pipeline.ENGINE_VERSION,
              "verses": len(keys), "runs": {}}
    for name, make in runs.items():
        if name not in args.runs.split(","):
            continue
        verdicts, wrong, short_unmarked = Counter(), [], []
        for k in keys:
            text = make(k)
            claims = pipeline.run(index, text, Thresholds(), "{surah}:{ayah}")["claims"]
            c = claims[0] if claims else None
            code = c["verdict"]["code"] if c else "NONE"
            sid = (c.get("source") or {}).get("id") if c else None
            if name == "plain_unmarked" and len(key_tokens(text)) < 3 and code != "VERIFIED":
                short_unmarked.append(f"{k[0]}:{k[1]}")
                continue
            verdicts[code] += 1
            ok_loc = False
            if code == "VERIFIED" and sid and sid.startswith("quran-"):
                loc = sid[len("quran-"):]
                first = tuple(map(int, loc.split("-")[0].split(":")))
                if "-" in loc:            # multi-verse run that starts at or before this verse
                    end = int(loc.split("-")[1])
                    ok_loc = first[0] == k[0] and first[1] <= k[1] <= end
                else:                     # same verse, or a verse with word-for-word identical text
                    ok_loc = first == k or wording.get(first) == wording[k]
            if not (code == "VERIFIED" and ok_loc):
                wrong.append({"verse": f"{k[0]}:{k[1]}", "verdict": code, "source": sid})
        report["runs"][name] = {"verdicts": dict(verdicts), "not_verified_or_wrong_location": wrong,
                                "short_verses_unmarked_not_claimed_as_quran": short_unmarked}
        print(name, dict(verdicts), "wrong:", len(wrong), "short-unmarked:", len(short_unmarked), flush=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

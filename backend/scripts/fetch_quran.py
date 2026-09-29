"""Fetch the full Quran text (Tanzil, simple-clean, Hafs) and convert it to
data/raw/quran_full.json for build_index.py.

Usage (from backend/):
    python scripts/fetch_quran.py                 # download from tanzil.net
    python scripts/fetch_quran.py --file q.txt    # use a manually downloaded file

Tanzil text is used under its terms of use (verbatim text, attribution to
tanzil.net, no modification). Download page: https://tanzil.net/download/
Choose: Quran type "Simple Clean", output "Text (with aya numbers)".
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

URL = "https://tanzil.net/pub/download/index.php?quranType=simple-clean&outType=txt-2&agree=true"
OUT = Path(__file__).resolve().parents[2] / "data" / "raw" / "quran_full.json"
LINE = re.compile(r"^(\d+)\|(\d+)\|(.+)$")


def parse(raw: str) -> list[dict]:
    records = []
    for line in raw.splitlines():
        m = LINE.match(line.strip())
        if m:
            records.append({"surah": int(m[1]), "ayah": int(m[2]), "text": m[3].strip()})
    return records


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=Path)
    args = ap.parse_args()

    raw = args.file.read_text("utf-8") if args.file else urllib.request.urlopen(URL, timeout=60).read().decode("utf-8")
    records = parse(raw)
    if len(records) != 6236:
        sys.exit(f"Expected 6236 verses, got {len(records)}. Check the downloaded file format.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"_meta": {"source": "tanzil.net simple-clean (Hafs)", "count": len(records)}, "records": records},
                   ensure_ascii=False),
        "utf-8",
    )
    print(f"Saved {len(records)} verses to {OUT}")


if __name__ == "__main__":
    main()

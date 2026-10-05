"""Build data/quran/quran_kfc.json from the official Quranpedia Hafs dump.

The challenge's scientific reference names the King Fahd Complex print or
quranpedia.net as the approved Quran text. Quranpedia publishes «مصحف حفص»
(«موافق لطبعة مجمع الملك فهد لطباعة المصحف الشريف») as a versioned dump at
https://quranpedia.net/dumps (mushafs-1.json.gz). This script copies the verse
text verbatim (only invisible BOM / zero-width characters are removed) with
its surah, ayah and Quranpedia verse id, and records the source, version,
SHA-256 and license so the attribution travels with the data.

    python scripts/prepare_quran_kfc.py ~/Downloads/mushafs-1.json
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "quran" / "quran_kfc.json"
INVISIBLE = re.compile("[﻿​-‏⁠]")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dump", type=Path)
    ap.add_argument("--output", type=Path, default=OUT)
    args = ap.parse_args(argv)
    raw = args.dump.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    data = json.loads(gzip.decompress(raw) if args.dump.suffix == ".gz" else raw)
    mushaf, lic = data["data"], data.get("license", {})
    records = []
    for surah in mushaf["surahs"]:
        for a in surah["ayahs"]:
            records.append({"surah": int(a["surah"]), "ayah": int(a["number"]), "gid": int(a["id"]),
                            "text": INVISIBLE.sub("", a["text"]).strip()})
    if len(records) != 6236 or len({(r["surah"], r["ayah"]) for r in records}) != 6236:
        print("Expected 6236 distinct verses", file=sys.stderr)
        return 1
    meta = {
        "source": "Quranpedia.net — " + mushaf.get("name", "") + " (" + mushaf.get("description", "") + ")",
        "source_url": "https://quranpedia.net/dumps",
        "dump_file": args.dump.name, "dump_sha256": digest, "version": lic.get("version"),
        "count": len(records),
        "attribution": "Quran text: Quranpedia.net (https://quranpedia.net), dump version " + str(lic.get("version")),
        "license_en": lic.get("en"), "license_ar": lic.get("ar"),
        "changes": "Verse text copied verbatim; only invisible BOM/zero-width characters removed.",
    }
    args.output.write_text(json.dumps({"_meta": meta, "records": records}, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("source", "version", "count", "dump_sha256")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

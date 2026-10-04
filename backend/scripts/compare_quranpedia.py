"""Compare the bundled Tanzil text with an official Quranpedia Hafs dump.

The scientific reference package names the King Fahd Complex edition or what
Quranpedia (quranpedia.net) carries. Quranpedia publishes versioned dumps at
https://quranpedia.net/dumps (Hafs text: mushafs-1.json.gz, with a SHA-256).
This environment could not download the file (HTTP 403), so the comparison is
left as a reproducible step for anyone who has the dump:

    python scripts/compare_quranpedia.py /path/to/mushafs-1.json.gz \
        --output ../docs/evidence/quranpedia-compare.json

The script is schema-tolerant: it looks for records carrying a surah number,
an ayah number and a text field under common key names. Comparison is done on
letters only (diacritics, tatweel and hamza/alef-variant spelling removed),
and every residual difference is listed verbatim so a human can review it.
Nothing in the project data is modified.
"""
from __future__ import annotations

import argparse
import difflib
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLED = ROOT / "data" / "quran" / "quran_full.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_index import verse_text  # noqa: E402  (basmala separated as in the index)

DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
SURAH_KEYS = ("surah", "sura", "sura_id", "surah_id", "surah_number", "chapter", "SoraNum", "sora")
AYAH_KEYS = ("ayah", "aya", "aya_id", "ayah_id", "ayah_number", "verse", "AyaNum", "number")
TEXT_KEYS = ("text", "aya_text", "ayah_text", "verse_text", "AyaText", "simple", "text_simple", "content")


INVISIBLE = re.compile("[\ufeff\u200b-\u200f\u2060\u00ad]")  # BOM, zero-width and direction marks


def normalize(text: str) -> str:
    text = INVISIBLE.sub("", text)
    text = DIACRITICS.sub("", text)
    text = re.sub("[آأإٱ]", "ا", text)  # alef variants -> alef
    text = text.replace("ة", "ه").replace("ى", "ي")  # ta marbuta / alef maqsura
    text = text.replace("ی", "ي").replace("ک", "ك")  # farsi yeh / kaf
    return " ".join(text.split())


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_any(path: Path):
    raw = gzip.open(path, "rb").read() if path.suffix == ".gz" else path.read_bytes()
    return json.loads(raw.decode("utf-8"))


def first_key(record: dict, keys) -> str | None:
    for k in keys:
        if k in record:
            return k
    return None


def walk(obj):
    """Yield every dict found anywhere inside the loaded JSON."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def extract_verses(dump) -> dict[tuple[int, int], str]:
    verses: dict[tuple[int, int], str] = {}
    for rec in walk(dump):
        sk, ak, tk = first_key(rec, SURAH_KEYS), first_key(rec, AYAH_KEYS), first_key(rec, TEXT_KEYS)
        if not (sk and ak and tk) or not isinstance(rec[tk], str):
            continue
        try:
            key = (int(rec[sk]), int(rec[ak]))
        except (TypeError, ValueError):
            continue
        verses.setdefault(key, rec[tk])
    return verses


def compare(bundled: list[dict], reference: dict[tuple[int, int], str]) -> dict:
    diffs, missing, matched = [], [], 0
    for rec in bundled:
        key = (rec["surah"], rec["ayah"])
        if key not in reference:
            missing.append({"surah": key[0], "ayah": key[1]})
            continue
        a, b = normalize(verse_text(rec)), normalize(reference[key])
        if a == b:
            matched += 1
        else:
            wa, wb = a.split(), b.split()
            ops = difflib.SequenceMatcher(None, wa, wb).get_opcodes()
            words = [{"op": op, "bundled": " ".join(wa[i1:i2]), "reference": " ".join(wb[j1:j2])}
                     for op, i1, i2, j1, j2 in ops if op != "equal"]
            diffs.append({"surah": key[0], "ayah": key[1], "words": words})
    extra = [{"surah": s, "ayah": a} for (s, a) in sorted(set(reference) - {(r["surah"], r["ayah"]) for r in bundled})]
    return {
        "bundled_verses": len(bundled),
        "reference_verses": len(reference),
        "matched_after_normalization": matched,
        "differences": diffs,
        "missing_in_reference": missing,
        "extra_in_reference": extra,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dump", type=Path, help="Quranpedia mushaf dump (.json or .json.gz)")
    ap.add_argument("--expected-sha256", help="hash published on quranpedia.net/dumps")
    ap.add_argument("--output", type=Path, help="write the full report as JSON")
    args = ap.parse_args(argv)

    digest = sha256(args.dump)
    if args.expected_sha256 and digest.lower() != args.expected_sha256.lower():
        print(f"SHA-256 mismatch: file={digest} expected={args.expected_sha256}", file=sys.stderr)
        return 2

    dump = load_any(args.dump)
    reference = extract_verses(dump)
    if not reference:
        print("No verse records recognised in the dump; inspect its schema and extend the key lists.", file=sys.stderr)
        return 3

    bundled = json.loads(BUNDLED.read_text(encoding="utf-8"))["records"]
    lic = dump.get("license", {}) if isinstance(dump, dict) else {}
    report = {"reference": "Quranpedia.net — Hafs mushaf (King Fahd Complex print), https://quranpedia.net/dumps",
              "reference_version": lic.get("version"), "dump_file": args.dump.name, "dump_sha256": digest,
              "note": "Only verse locations and differing words are kept; the reference text itself is not redistributed.",
              **compare(bundled, reference)}
    summary = {k: (len(v) if isinstance(v, list) else v) for k, v in report.items() if k not in ("note", "reference")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if not report["differences"] and not report["missing_in_reference"] else 1


if __name__ == "__main__":
    sys.exit(main())

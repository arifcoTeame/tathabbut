"""Check seed structure, or validate manually selected Dorar API results.

Selection input: {"records": [{id, text, narrator, grades, evidence: [
  {grade_index, snapshot, result_html, reviewed_at, review_note}
]}]}. A result must be selected explicitly; no search result is auto-imported.

Each result_html must occur literally in the captured API response and contain
one hadith with its five labelled bibliographic fields. The parser fails closed
on unfamiliar formats. Live API compatibility remains unverified while access
returns HTTP 403. --export produces a separate review file, never the seed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path

try:
    from .fetch_hadith import ENDPOINT, ROOT, strings, validate_snapshot, write_json
except ImportError:
    from fetch_hadith import ENDPOINT, ROOT, strings, validate_snapshot, write_json

SEED = ROOT / "data" / "seed" / "hadith_seed.json"
CAPTURES = ROOT / "data" / "review" / "hadith_dorar"
LEGACY_IDS = {
    "bukhari-1", "bukhari-6484", "bukhari-13", "bukhari-24", "muslim-55",
    "muslim-101", "muslim-223", "muslim-2553", "ibnmajah-224", "daifa-416", "daifa-36", "daifa-57",
}
GRADE_CLASSES = {
    "صحيح": "authentic", "حسن": "authentic", "حسن صحيح": "authentic",
    "صحيح لغيره": "authentic", "حسن لغيره": "authentic", "ضعيف": "weak",
    "ضعيف جدا": "very_weak", "منكر": "very_weak", "موضوع": "fabricated",
    "باطل": "fabricated", "كذب": "fabricated", "لا أصل له": "baseless",
    # Verbatim wordings met in the October 2026 review (dorar.net). Keys are text_key() forms.
    "إسناده حسن": "authentic", "صحيح مركب من حديثين": "authentic",
    "إسناده فيه ضعف": "weak", "ضعيف وبعضهم جعله في الموضوعات": "weak",
    "منكر لا أصل له": "very_weak",
    "عمرو بن بكر السكسكي واه وأحاديثه شبه موضوعه": "very_weak",
    "كذب ليس له أصل منكر جدا": "fabricated", "أورده في كتاب الموضوعات": "fabricated",
    "في إسناده مسعود بن عمرو قال الذهبي في الميزان لا أعرفه وخبره باطل": "fabricated",
    "هذا القول المشهور لا يصح عن النبي صلى الله عليه وسلم فهو من الأحاديث الموضوعة": "fabricated",
    "قيل لا أصل له أو بأصله موضوع": "fabricated",
    "لا أصل له مرفوعا": "baseless", "لم أجده بهذا اللفظ مرفوعا": "baseless",
    "لا أعلم له أصلا شرعيا ولا أعلم أنه ورد في ذلك حديث يعتمد عليه": "baseless",
    # A general negation without a named grade: shown verbatim, never promoted to a grade.
    "لا يصح": "unverified", "لا يصح من جميع الوجوه": "unverified",
    "رفعه إلى النبي صلى الله عليه وسلم ليس بصحيح": "unverified",
}
LABELS = {
    "الراوي": "narrator", "المحدث": "muhaddith", "المصدر": "source",
    "الصفحة أو الرقم": "ref", "خلاصة حكم المحدث": "grade",
}
LABEL_RE = re.compile(r"(" + "|".join(re.escape(k) for k in LABELS) + r")\s*:")


def plain_spaces(text: str) -> str:
    return " ".join(text.split())


def text_key(text: str) -> str:
    # Deliberately preserve hamza, ta marbuta and word order: no stemming.
    text = "".join(c for c in text if not unicodedata.category(c).startswith("M") and c != "ـ")
    return plain_spaces("".join(" " if unicodedata.category(c).startswith("P") else c for c in text))


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def parse_result(fragment: str) -> dict:
    parser = PlainText()
    parser.feed(fragment)
    text = plain_spaces(" ".join(parser.parts))
    matches = list(LABEL_RE.finditer(text))
    if len(matches) != 5 or {m.group(1) for m in matches} != set(LABELS):
        raise ValueError("Select exactly one result with all five source labels")
    original = re.sub(r"^\s*\d+\s*[-–.]\s*", "", text[:matches[0].start()]).strip(" |")
    if not original:
        raise ValueError("Source result has no hadith text")
    fields = {"original_text": original}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = text[match.end():end].strip(" |")
        if not value:
            raise ValueError("Empty source metadata field")
        fields[LABELS[match.group(1)]] = value
    return fields


def check_record(record: dict) -> None:
    for key in ("id", "text"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError(f"Missing record {key}")
    if not isinstance(record.get("narrator"), str):
        raise ValueError(f"{record['id']}: narrator must be copied as text")
    if not record.get("grades"):
        raise ValueError(f"{record['id']}: no source grades")
    for grade in record["grades"]:
        if any(not isinstance(grade.get(k), str) or not grade[k].strip() for k in ("muhaddith", "source", "ref", "grade", "class")):
            raise ValueError(f"{record['id']}: incomplete source grade")
        mapped = GRADE_CLASSES.get(text_key(grade["grade"]))
        if mapped is None or mapped != grade["class"]:
            raise ValueError(f"{record['id']}: unknown or mismatched grade class; needs separate review")


def validate_selection(data: dict, captures: Path) -> dict:
    output = []
    ids = set()
    for record in data["records"]:
        check_record(record)
        if record["id"] in ids:
            raise ValueError(f"Duplicate record ID: {record['id']}")
        ids.add(record["id"])
        evidence = record.get("evidence", [])
        if len(evidence) != len(record["grades"]) or {e.get("grade_index") for e in evidence} != set(range(len(record["grades"]))):
            raise ValueError(f"{record['id']}: one source selection is required for each grade")
        proofs = []
        for item in evidence:
            path = (captures / item["snapshot"]).resolve()
            if not path.is_relative_to(captures.resolve()) or path.suffix != ".json":
                raise ValueError("Snapshot must be a JSON file inside the capture directory")
            snapshot = json.loads(path.read_text("utf-8"))
            response = validate_snapshot(snapshot)
            fragment = item["result_html"]
            if not fragment or not any(fragment in s for s in strings(response["ahadith"])):
                raise ValueError(f"{record['id']}: selected result is absent from the captured response")
            fields = parse_result(fragment)
            grade = record["grades"][item["grade_index"]]
            for key in ("muhaddith", "source", "ref", "grade"):
                if plain_spaces(grade[key]) != fields[key]:
                    raise ValueError(f"{record['id']}: {key} differs from the selected source result")
            if plain_spaces(record["narrator"]) != fields["narrator"]:
                raise ValueError(f"{record['id']}: narrator differs from the selected source result")
            if f" {text_key(record['text'])} " not in f" {text_key(fields['original_text'])} ":
                raise ValueError(f"{record['id']}: record text is not a continuous source quotation")
            reviewed_on = date.fromisoformat(item["reviewed_at"])
            retrieved_on = datetime.fromisoformat(snapshot["retrieved_at"].replace("Z", "+00:00")).date()
            if reviewed_on < retrieved_on:
                raise ValueError("Selection review date predates the captured response")
            if not isinstance(item.get("review_note"), str) or not item["review_note"].strip():
                raise ValueError("A manual selection note is required")
            proofs.append({
                **item,
                "request_url": snapshot["request_url"],
                "retrieved_at": snapshot["retrieved_at"],
                "response_sha256": snapshot["response_sha256"],
                "source_record": fields,
                "scope": "source_text_and_bibliography_only",
            })
        output.append({**record, "verified": True, "evidence": proofs})
    if not output:
        raise ValueError("No records were selected")
    return {"_meta": {"status": "source_matched_pending_manual_merge", "not_a_comprehensive_grade_review": True}, "records": output}


def validate_seed(data: dict) -> dict:
    ids = set()
    legacy = transcript = 0
    for record in data["records"]:
        check_record(record)
        if record["id"] in ids:
            raise ValueError(f"Duplicate record ID: {record['id']}")
        ids.add(record["id"])
        if record.get("verified") is not True:
            raise ValueError(f"{record['id']}: seed source is not marked reviewed")
        if record["id"] in LEGACY_IDS:
            legacy += 1
        elif record.get("provenance", {}).get("method") == "assisted_api_transcript":
            check_transcript_provenance(record)
            transcript += 1
        elif not record.get("evidence"):
            raise ValueError(f"{record['id']}: new seed record needs source evidence")
    return {"records": len(ids), "legacy_records": legacy, "transcript_records": transcript,
            "validation": "schema_only", "new_source_recheck": False}


def check_transcript_provenance(record: dict) -> None:
    """Records reviewed on 2026-10-03 through the documented Dorar API, transcribed by an
    assisted browser fetch rather than a byte-level capture. The transcript of the cited
    entry is stored in ``dorar_text``; the record text must be a continuous quotation of it."""
    prov = record["provenance"]
    for key in ("method", "endpoint", "query", "retrieved_at", "reviewed_at"):
        if not isinstance(prov.get(key), str) or not prov[key].strip():
            raise ValueError(f"{record['id']}: incomplete transcript provenance ({key})")
    if not prov["endpoint"].startswith(ENDPOINT):
        raise ValueError(f"{record['id']}: provenance endpoint is not the official Dorar API")
    date.fromisoformat(prov["retrieved_at"]); date.fromisoformat(prov["reviewed_at"])
    source_text = record.get("dorar_text", "")
    if not source_text.strip():
        raise ValueError(f"{record['id']}: transcript record needs dorar_text")
    needle, hay = f" {text_key(record['text'])} ", f" {text_key(source_text)} "
    clitic = re.sub(r"^ (\S)", r" \1", needle)  # same string; kept for clarity
    if needle not in hay and not re.search(r" [وف]" + re.escape(needle.strip()) + " ", hay):
        raise ValueError(f"{record['id']}: record text is not a continuous source quotation")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--seed", type=Path, default=None)
    mode.add_argument("--selection", type=Path)
    parser.add_argument("--captures", type=Path, default=CAPTURES)
    parser.add_argument("--export", type=Path, help="Separate reviewed output; does not merge into the seed")
    args = parser.parse_args()
    try:
        if args.selection:
            result = validate_selection(json.loads(args.selection.read_text("utf-8")), args.captures)
            if args.export:
                if args.export.resolve() in (SEED.resolve(), args.selection.resolve()):
                    raise ValueError("Export must not overwrite the seed or the manual selection")
                write_json(args.export, result)
            print(json.dumps({"validated_selected_records": len(result["records"]), "seed_changed": False}, ensure_ascii=False))
        else:
            if args.export:
                raise ValueError("--export requires --selection")
            data = json.loads((args.seed or SEED).read_text("utf-8"))
            result = validate_seed(data)
            new_records = [r for r in data["records"] if r["id"] not in LEGACY_IDS
                           and r.get("provenance", {}).get("method") != "assisted_api_transcript"]
            if new_records:
                validate_selection({"records": new_records}, args.captures)
                result["new_records_with_checked_evidence"] = len(new_records)
            print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

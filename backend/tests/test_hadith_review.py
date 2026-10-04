"""Offline checks for source-review tooling. All source snippets are synthetic.

The fake snippets below are test data, not hadith quotations or source evidence.
No test performs a network request or rewrites the seed.
"""
from __future__ import annotations

import copy
import hashlib
import json
from urllib.error import HTTPError

import pytest

from scripts import fetch_hadith as fetcher
from scripts import validate_hadith as reviewer
from scripts.validate_hadith import LEGACY_IDS, SEED, parse_result, validate_seed, validate_selection

SYNTHETIC_FRAGMENT = (
    '<div class="hadith">1 - نص المصدر للاختبار فقط ولا يمثل حديثا</div>'
    '<div class="hadith-info">'
    '<span>الراوي:</span> راو للاختبار | '
    '<span>المحدث:</span> محدث للاختبار | '
    '<span>المصدر:</span> كتاب للاختبار | '
    '<span>الصفحة أو الرقم:</span> 123 | '
    '<span>خلاصة حكم المحدث:</span> صحيح</div>'
)


def snapshot(query="عبارة اختبار", fragment=SYNTHETIC_FRAGMENT):
    body = json.dumps({"ahadith": {"result": fragment}}, ensure_ascii=False)
    return {
        "schema_version": 1,
        "query": query,
        "request_url": fetcher.api_url(query),
        "retrieved_at": "2026-10-03T00:00:00+00:00",
        "response_text": body,
        "response_sha256": hashlib.sha256(body.encode()).hexdigest(),
    }


@pytest.fixture
def selection(tmp_path):
    fetcher.write_json(tmp_path / "synthetic.json", snapshot())
    return {
        "records": [{
            "id": "synthetic-test-only",
            "text": "نص المصدر للاختبار فقط",
            "narrator": "راو للاختبار",
            "grades": [{"muhaddith": "محدث للاختبار", "source": "كتاب للاختبار", "ref": "123", "grade": "صحيح", "class": "authentic"}],
            "evidence": [{"grade_index": 0, "snapshot": "synthetic.json", "result_html": SYNTHETIC_FRAGMENT, "reviewed_at": "2026-10-03", "review_note": "Synthetic fixture only, not a real hadith."}],
        }]
    }


def test_candidate_list_has_95_queries_without_claimed_grades():
    data = json.loads(fetcher.Path(fetcher.__file__).with_name("hadith_candidates.json").read_text("utf-8"))
    rows = data["candidates"]
    assert len(rows) == len({r["id"] for r in rows}) == len({r["query"] for r in rows}) == 95
    assert {r["existing_record_id"] for r in rows if "existing_record_id" in r} == LEGACY_IDS
    assert all(not ({"text", "grade", "grades", "verified"} & set(r)) for r in rows)


def test_fetch_cli_is_disabled_without_permitted_use_confirmation(monkeypatch):
    monkeypatch.setattr(fetcher.sys, "argv", ["fetch_hadith.py"])
    monkeypatch.setattr(fetcher, "fetch", lambda query: pytest.fail("Network must not be used"))
    with pytest.raises(SystemExit) as exc:
        fetcher.main()
    assert exc.value.code == 2


@pytest.mark.parametrize("status,state", [(403, "access_denied"), (429, "rate_limited")])
def test_denial_stops_batch_without_a_capture_or_retry(monkeypatch, tmp_path, status, state):
    calls = []

    def denied(query):
        calls.append(query)
        raise HTTPError(fetcher.api_url(query), status, "blocked", {}, None)

    monkeypatch.setattr(fetcher, "fetch", denied)
    candidates = [{"id": "first", "query": "العبارة الأولى"}, {"id": "second", "query": "العبارة الثانية"}]
    result = fetcher.run(candidates, tmp_path, limit=2, delay=1)
    assert calls == ["العبارة الأولى"]
    assert result["queries"]["first"]["state"] == state
    assert list(tmp_path.iterdir()) == [tmp_path / "status.json"]


def test_duplicate_candidate_ids_fail_before_network(monkeypatch, tmp_path):
    monkeypatch.setattr(fetcher, "fetch", lambda query: pytest.fail("Network must not be used"))
    with pytest.raises(ValueError, match="unique"):
        fetcher.run([{"id": "same", "query": "a"}, {"id": "same", "query": "b"}], tmp_path, 2, 1)


def test_resume_validates_cache_and_does_not_refetch(monkeypatch, tmp_path):
    fetcher.write_json(tmp_path / "first.json", snapshot())
    monkeypatch.setattr(fetcher, "fetch", lambda query: pytest.fail("Cache must be reused"))
    fetcher.run([{"id": "first", "query": "عبارة اختبار"}], tmp_path, 1, 1)


def test_captured_response_hash_detects_local_change():
    data = snapshot()
    data["response_text"] += " "
    with pytest.raises(ValueError, match="hash"):
        fetcher.validate_snapshot(data)


def test_snapshot_rejects_unofficial_source_url():
    data = snapshot()
    data["request_url"] = "https://example.invalid/data"
    with pytest.raises(ValueError, match="official"):
        fetcher.validate_snapshot(data)


def test_manually_selected_result_exports_provenance(selection, tmp_path):
    original = copy.deepcopy(selection)
    result = validate_selection(selection, tmp_path)
    row = result["records"][0]
    assert row["verified"] is True
    assert row["evidence"][0]["source_record"]["original_text"] == "نص المصدر للاختبار فقط ولا يمثل حديثا"
    assert row["evidence"][0]["retrieved_at"] == "2026-10-03T00:00:00+00:00"
    assert row["evidence"][0]["response_sha256"] == snapshot()["response_sha256"]
    assert selection == original


def test_export_cannot_overwrite_the_seed(selection, tmp_path, monkeypatch):
    selection_path = tmp_path / "selection.json"
    fetcher.write_json(selection_path, selection)
    before = SEED.read_bytes()
    monkeypatch.setattr(reviewer.sys, "argv", ["validate_hadith.py", "--selection", str(selection_path), "--captures", str(tmp_path), "--export", str(SEED)])
    assert reviewer.main() == 1
    assert SEED.read_bytes() == before


def test_selection_without_source_evidence_cannot_be_promoted(selection, tmp_path):
    selection["records"][0].pop("evidence")
    with pytest.raises(ValueError, match="one source selection"):
        validate_selection(selection, tmp_path)


def test_unsaved_source_excerpt_cannot_be_promoted(selection, tmp_path):
    selection["records"][0]["evidence"][0]["result_html"] = SYNTHETIC_FRAGMENT.replace("صحيح", "ضعيف")
    with pytest.raises(ValueError, match="absent"):
        validate_selection(selection, tmp_path)


@pytest.mark.parametrize("field,value", [("source", "كتاب آخر"), ("ref", "456"), ("muhaddith", "شخص آخر"), ("grade", "حسن")])
def test_source_fields_must_match_the_same_result(selection, tmp_path, field, value):
    selection["records"][0]["grades"][0][field] = value
    with pytest.raises(ValueError, match="differs"):
        validate_selection(selection, tmp_path)


def test_different_wording_is_not_accepted_as_a_source_quote(selection, tmp_path):
    selection["records"][0]["text"] = "نص المصدر الصحيح للاختبار"
    with pytest.raises(ValueError, match="continuous"):
        validate_selection(selection, tmp_path)


def test_diacritics_do_not_break_a_continuous_quote(selection, tmp_path):
    selection["records"][0]["text"] = "نَصُّ المَصْدَرِ"
    assert validate_selection(selection, tmp_path)["records"][0]["verified"] is True


def test_grade_class_cannot_invert_the_copied_ruling(selection, tmp_path):
    selection["records"][0]["grades"][0]["class"] = "fabricated"
    with pytest.raises(ValueError, match="grade class"):
        validate_selection(selection, tmp_path)


def test_duplicate_record_ids_are_rejected(selection, tmp_path):
    selection["records"].append(copy.deepcopy(selection["records"][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        validate_selection(selection, tmp_path)


def test_a_fragment_containing_two_results_is_rejected():
    with pytest.raises(ValueError, match="exactly one"):
        parse_result(SYNTHETIC_FRAGMENT + SYNTHETIC_FRAGMENT)


def test_each_grade_requires_its_own_source_selection(selection, tmp_path):
    selection["records"][0]["grades"].append(copy.deepcopy(selection["records"][0]["grades"][0]))
    with pytest.raises(ValueError, match="each grade"):
        validate_selection(selection, tmp_path)


def test_snapshot_cannot_escape_capture_directory(selection, tmp_path):
    selection["records"][0]["evidence"][0]["snapshot"] = "../outside.json"
    with pytest.raises(ValueError, match="inside"):
        validate_selection(selection, tmp_path)


def test_review_cannot_predate_source_capture(selection, tmp_path):
    selection["records"][0]["evidence"][0]["reviewed_at"] = "2026-10-02"
    with pytest.raises(ValueError, match="predates"):
        validate_selection(selection, tmp_path)


def test_legacy_ids_texts_and_distinct_narration_notes_are_preserved():
    data = json.loads(SEED.read_text("utf-8"))
    records = [r for r in data["records"] if r["id"] in LEGACY_IDS]
    assert len(records) == 12
    digest = hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert digest == "ad50bc4115a5a75aef0e146fa1fbb1100b71d18db5d85c4d6f71c99a725d522b"
    assert validate_seed(data)["new_source_recheck"] is False


def test_new_seed_record_without_provenance_is_rejected(selection):
    row = selection["records"][0]
    row["verified"] = True
    row.pop("evidence")
    with pytest.raises(ValueError, match="source evidence"):
        validate_seed(selection)

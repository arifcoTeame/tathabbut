import gzip
import json

from scripts import compare_quranpedia as cq


def test_normalize_ignores_diacritics_and_alef_variants():
    assert cq.normalize("بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ") == cq.normalize("بسم الله الرحمن")
    assert cq.normalize("إياك") == cq.normalize("اياك")
    assert cq.normalize("نعبد وإياك") != cq.normalize("نعبد فإياك")


def test_extract_verses_is_schema_tolerant():
    dump = {"data": {"ayat": [{"sura_id": 1, "aya_id": 1, "aya_text": "x"}, {"SoraNum": "1", "AyaNum": "2", "AyaText": "y"}]}}
    assert cq.extract_verses(dump) == {(1, 1): "x", (1, 2): "y"}


def test_compare_reports_differences_and_gaps():
    bundled = [{"surah": 1, "ayah": 1, "text": "بسم الله الرحمن الرحيم"}, {"surah": 1, "ayah": 2, "text": "الحمد لله رب العالمين"}]
    reference = {(1, 1): "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ", (1, 2): "الحمد لله رب العالمين الكريم", (1, 3): "zzz"}
    rep = cq.compare(bundled, reference)
    assert rep["matched_after_normalization"] == 1
    assert [d["ayah"] for d in rep["differences"]] == [2]
    assert rep["extra_in_reference"] == [{"surah": 1, "ayah": 3}]


def test_main_end_to_end_with_gzip_dump(tmp_path):
    records = json.loads(cq.BUNDLED.read_text(encoding="utf-8"))["records"]
    dump = [{"surah": r["surah"], "ayah": r["ayah"], "text": r["text"]} for r in records]
    path = tmp_path / "mushafs-1.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(dump, fh, ensure_ascii=False)
    out = tmp_path / "report.json"
    assert cq.main([str(path), "--output", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["matched_after_normalization"] == 6236 and report["differences"] == []
    assert cq.main([str(path), "--expected-sha256", "0" * 64]) == 2

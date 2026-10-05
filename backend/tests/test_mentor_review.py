"""Mentor review, 5 October 2026: a hadith that is not in the 72 records must not be
judged «لا يصح»; it is «لم يُعثر عليه ضمن قاعدة البيانات الحالية / يتطلب تحققاً»."""
import pytest

from app.core import pipeline

LINK = "https://quranpedia.net/surah/1/{surah}#verse-{gid}"


@pytest.mark.parametrize("text", [
    "قال رسول الله ﷺ: «تفاءلوا بالخير تجدوه»",
    "قال رسول الله ﷺ: «سافروا تصحوا»",
    "قال رسول الله ﷺ: «الدال على الخير كفاعله»",
    "قال رسول الله ﷺ: «الصبر مفتاح الفرج»",
])
def test_hadith_outside_the_database_is_not_judged(index, th, text):
    c = pipeline.run(index, text, th, LINK)["claims"][0]
    assert c["verdict"]["code"] == "NO_ORIGIN"
    assert c["verdict"]["label_ar"] == "لم يُعثر عليه ضمن قاعدة البيانات الحالية"
    assert c["grades"] == [] and c["source"] is None
    assert any("يتطلب تحققاً" in n for n in c["notes"])


def test_not_authentic_only_with_a_recorded_grade(index, th):
    c = pipeline.run(index, "قال رسول الله ﷺ: «حب الوطن من الإيمان»", th, LINK)["claims"][0]
    assert c["verdict"]["code"] == "NOT_AUTHENTIC"
    assert c["grades"] and all(g["muhaddith"] and g["source"] for g in c["grades"])


def test_wording_close_to_a_weak_record_is_not_judged_by_it(index, th):
    """Extra words beyond a recorded weak hadith: the record's grade is not transferred."""
    c = pipeline.run(index, "قال رسول الله ﷺ: «حب الوطن من الايمان والنظافة»", th, LINK)["claims"][0]
    assert c["verdict"]["code"] in ("NO_ORIGIN", "NEEDS_REVIEW")

"""Mentor review, 5 October 2026: a hadith that is not in the 72 records must not be
judged «لا يصح»; it is «لم يُعثر عليه ضمن قاعدة البيانات الحالية / يتطلب تحققاً»."""
import pytest

from app.core import pipeline

LINK = "https://quranpedia.net/surah/1/{surah}?ayah_id={gid}"


@pytest.mark.parametrize("text", [
    "قال رسول الله ﷺ: «تفاءلوا بالخير تجدوه»",
    "قال رسول الله ﷺ: «سافروا تصحوا»",
    "قال رسول الله ﷺ: «الدال على الخير كفاعله»",
    "قال رسول الله ﷺ: «الصبر مفتاح الفرج»",
])
def test_hadith_outside_the_database_is_not_judged(index, th, text):
    c = pipeline.run(index, text, th, LINK)["claims"][0]
    assert c["verdict"]["code"] == "NO_ORIGIN"
    assert c["verdict"]["label_ar"] == "لم يُعثر على تطابق مطابق"
    assert c["grades"] == [] and c["source"] is None
    assert any("لا تعني أن الحديث غير موجود في الدرر السنية" in n and "ابحث عنه كاملًا في موقع الدرر السنية" in n for n in c["notes"])


def test_not_authentic_only_with_a_recorded_grade(index, th):
    c = pipeline.run(index, "قال رسول الله ﷺ: «حب الوطن من الإيمان»", th, LINK)["claims"][0]
    assert c["verdict"]["code"] == "NOT_AUTHENTIC"
    assert c["grades"] and all(g["muhaddith"] and g["source"] for g in c["grades"])


def test_wording_close_to_a_weak_record_is_not_judged_by_it(index, th):
    """Extra words beyond a recorded weak hadith: the record's grade is not transferred."""
    c = pipeline.run(index, "قال رسول الله ﷺ: «حب الوطن من الايمان والنظافة»", th, LINK)["claims"][0]
    assert c["verdict"]["code"] in ("NO_ORIGIN", "NEEDS_REVIEW")


# Owner check on the phone, 6 October 00:54–01:00: «قال رسول الله حب الوطن من الايمان» (no ﷺ,
# no quotation marks, no hamza) was «لم يُعثر عليه» because «قال رسول الله» stayed in the text.
@pytest.mark.parametrize("text, code, source", [
    ("قال رسول الله حب الوطن من الايمان", "NOT_AUTHENTIC", "hadith-daifa-36"),
    ("قال رسول الله خير الناس انفعهم للناس", "DISPUTED", "hadith-sahihjami-3289"),
    ("قال رسول الله انما بعثت لاتمم مكارم الاخلاق", "NEEDS_REVIEW", "hadith-tamhid-24-333"),
    ("قال النبي: الدين النصيحة", "VERIFIED", "hadith-muslim-55"),
])
def test_unquoted_attribution_without_honorific(index, th, text, code, source):
    c = pipeline.run(index, text, th, LINK)["claims"][0]
    assert c["type_hint"] == "hadith" and c["verdict"]["code"] == code
    assert c["source"]["id"] == source
    assert not c["text"].startswith("قال")


def test_common_saying_is_not_attributed(index, th):
    c = pipeline.run(index, "قال رسول الله الصبر مفتاح الفرج", th, LINK)["claims"][0]
    assert c["text"] == "الصبر مفتاح الفرج" and c["verdict"]["code"] == "NO_ORIGIN" and c["source"] is None


# User review, 6 October 2026: a Dorar button may say «فتح النتيجة» only when it opens
# the cited entry itself (dorar.net/h/…); otherwise it is a search link.
def test_hadith_button_opens_the_cited_dorar_entry(index, th):
    c = pipeline.run(index, "قال رسول الله ﷺ: «حب الوطن من الإيمان»", th, LINK)["claims"][0]
    assert c["source"]["url"] == "https://dorar.net/h/v9O0rvM9"
    assert c["grades"][0]["url"] == c["source"]["url"]
    assert c["grades"][0]["muhaddith"] == "الألباني" and c["grades"][0]["ref"] == "36"


def test_every_hadith_link_is_an_entry_or_a_search():
    import json
    from app.config import ROOT
    links = json.loads((ROOT / "data" / "seed" / "dorar_links.json").read_text("utf-8"))["records"]
    seed = json.loads((ROOT / "data" / "seed" / "hadith_seed.json").read_text("utf-8"))["records"]
    assert set(links) == {r["id"] for r in seed}
    for r in seed:
        urls = links[r["id"]]["grades"]
        assert len(urls) == len(r["grades"])
        assert all(u is None or u.startswith("https://dorar.net/h/") for u in urls)


def test_record_without_checked_entry_keeps_a_search_link(index, th):
    c = pipeline.run(index, "قال رسول الله ﷺ: «لا ضرر ولا ضرار»", th, LINK)["claims"][0]
    assert c["source"]["url"].startswith("https://dorar.net/hadith/search?q=")
    assert all("url" not in g for g in c["grades"])

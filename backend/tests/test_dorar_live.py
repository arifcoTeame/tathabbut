"""Live Dorar lookup: parsing, reading rulings, matching and the conservative labels.

All inputs are real responses from dorar.net/dorar_api.json (2026-10-24), stored as fixtures;
no test reaches the network."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core import dorar_live as dl
from app.core.judge import Thresholds

FIX = Path(__file__).parent / "fixtures"
RECORDS = json.loads((FIX / "dorar_records.json").read_text(encoding="utf-8"))["queries"]
TH = Thresholds()


def lookup(q: str) -> dl.Lookup:
    rows = RECORDS.get(q, [])
    return dl.Lookup(True, [dl.Record(t, n.strip("[] ") if n != "-" else "", m, s, r, g) for t, n, m, s, r, g in rows])


def fake_fetch(text: str, timeout: float = 4.0) -> dl.Lookup:
    for q in RECORDS:
        if dl.normalize(q) in dl.normalize(text):
            return lookup(q)
    return dl.Lookup(True, [])


def test_parse_raw_response():
    recs = dl.parse((FIX / "dorar_api_raw.json").read_text(encoding="utf-8"))
    assert len(recs) == 3
    assert recs[0].text == "اطلُبوا العِلْمَ ولو بالصِّينِ"
    assert (recs[1].muhaddith, recs[1].source, recs[1].ref, recs[1].grade) == ("ابن حبان", "المجروحين", "1/489", "باطل لا أصل له")
    assert recs[1].narrator == "أنس بن مالك"
    assert recs[2].narrator == ""            # «-» in the source


@pytest.mark.parametrize("grade,cls", [
    ("حسن لغيره", "authentic"), ("[صحيح]", "authentic"), ("إسناده صحيح على شرط مسلم", "authentic"),
    ("موضوع", "fabricated"), ("باطل لا أصل له", "fabricated"), ("ليس بحديث", "baseless"),
    ("غير صحيح", "weak"), ("لا يصح لأبي الحمراء عن النبي صلى الله عليه وسلم حديث", "weak"),
    ("ضعيف وبعضهم جعله في الموضوعات", "weak"), ("لم أقف عليه", "unclassified"),
    ("موقوف له حكم الرفع", "unclassified"),
    # A narrator named al-Hasan is not the grade «حسن».
    ("[فيه] الحسن بن عمارة متروك", "weak"),
])
def test_classify(grade, cls):
    assert dl.classify(grade) == cls


def test_chain_rulings_do_not_reject_the_hadith():
    # «خيركم من تعلم القرآن وعلمه» is in al-Bukhari; Dorar's first results are rulings on single chains.
    j = dl.judge_live("خيركم من تعلم القرآن وعلمه", lookup("خيركم من تعلم القرآن وعلمه"), TH)
    assert j.code == "IN_SOURCE"
    assert len(j.candidate.doc.grades) == 6


def test_fabricated_hadith():
    j = dl.judge_live("حب الوطن من الإيمان", lookup("حب الوطن من الإيمان"), TH)
    assert j.code == "NOT_AUTHENTIC"
    muhaddiths = {g["muhaddith"] for g in j.candidate.doc.grades}
    assert "الألباني" in muhaddiths and "محمد بن محمد الغزي" not in muhaddiths   # «حب الوطن قتال» is another text


def test_baseless_hadith():
    j = dl.judge_live("اطلبوا العلم ولو بالصين", lookup("اطلبوا العلم ولو بالصين"), TH)
    assert j.code == "NOT_AUTHENTIC"
    assert j.candidate.doc.ref["live"] is True
    assert j.candidate.doc.url.startswith("https://dorar.net/hadith/search?q=")


def test_mixed_rulings_are_disputed():
    j = dl.judge_live("الصبر مفتاح الفرج", lookup("الصبر مفتاح الفرج"), TH)
    assert j.code == "DISPUTED"
    assert {g["grade"] for g in j.candidate.doc.grades} == {"بلا إسناد عن الحسين بن علي", "حسن لغيره"}


def test_authentic_hadith():
    j = dl.judge_live("لا يدخل الجنة نمام", lookup("لا يدخل الجنة نمام"), TH)
    assert j.code == "VERIFIED"
    assert j.candidate.doc.text == "لا يدخلُ الجنةَ نمَّامٌ"     # shortest record containing the quotation


def test_unrelated_results_are_not_a_match():
    assert dl.judge_live("الكرسي الأزرق يطير فوق الغيم البنفسجي",
                         lookup("الكرسي الأزرق يطير فوق الغيم البنفسجي"), TH) is None


def test_failed_lookup_returns_none():
    assert dl.judge_live("حب الوطن من الإيمان", dl.Lookup(False, error="URLError"), TH) is None


def test_fetch_reports_network_failure():
    def broken(*a, **k):
        raise OSError("down")
    res = dl.fetch("نص لا يخزن في الذاكرة المؤقتة 123", opener=broken)
    assert not res.ok and res.error == "OSError"


# --- through the pipeline ----------------------------------------------------

def run(index, text, live=True, fetch=fake_fetch):
    from app.core import pipeline
    return pipeline.run(index, text, TH, "https://quranpedia.net/surah/1/{surah}?ayah_id={gid}",
                        live=live, live_fetch=fetch)


def test_pipeline_uses_dorar_when_local_base_misses(index):
    out = run(index, "قال رسول الله ﷺ: «لا يدخل الجنة نمام»")
    c = out["claims"][0]
    assert c["live"] == {"searched": True, "ok": True}
    assert c["source"]["ref"]["live"] is True
    assert c["verdict"]["code"] == "VERIFIED"
    assert any("البحث المباشر في الدرر السنية" in n for n in c["notes"])


def test_local_base_is_still_first(index):
    calls = []
    out = run(index, "قال رسول الله ﷺ: «إنما الأعمال بالنيات»", fetch=lambda t, timeout=4: calls.append(t) or dl.Lookup(True))
    assert not calls
    assert out["claims"][0]["live"] is None


def test_no_lookup_for_verses_questions_or_when_off(index):
    calls = []
    f = lambda t, timeout=4: calls.append(t) or dl.Lookup(True)
    run(index, "قال تعالى: ﴿وتوكلوا على الرحمن في الشدائد ولا تيأسوا﴾", fetch=f)
    run(index, "لماذا يعبد المسلمون الكعبة؟", fetch=f)
    run(index, "قال رسول الله ﷺ: «لا يدخل الجنة نمام»", live=False, fetch=f)
    assert calls == []


def test_unavailable_dorar_keeps_not_found(index):
    out = run(index, "قال رسول الله ﷺ: «الصبر مفتاح الفرج»", fetch=lambda t, timeout=4: dl.Lookup(False, error="URLError"))
    c = out["claims"][0]
    assert c["verdict"]["code"] == "NO_ORIGIN"
    assert c["live"] == {"searched": True, "ok": False}
    assert dl.UNAVAILABLE_NOTE in c["notes"]

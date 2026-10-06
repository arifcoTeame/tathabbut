"""0.9.0: verification requests as people write them, and the scientific package's
test questions. A general question is not graded as a missing hadith, and a request for
evidence never yields a text that is not recorded word for word."""
import pytest

from app.core import pipeline
from app.core.extractor import extract

LINK = "https://quranpedia.net/surah/1/{surah}?ayah_id={gid}"


@pytest.mark.parametrize("text,quote,kind", [
    ("سمعت أن النبي قال اطلبوا العلم ولو بالصين، صحيح؟", "اطلبوا العلم ولو بالصين", "hadith"),
    ("ما صحة حديث اختلاف أمتي رحمة؟", "اختلاف أمتي رحمة", "hadith"),
    ("هل حديث حب الوطن من الإيمان صحيح؟", "حب الوطن من الإيمان", "hadith"),
    ("يقولون إن النبي ﷺ قال: النظافة من الإيمان، هل هذا صحيح؟", "النظافة من الإيمان", "hadith"),
    ("سمعت أن النبي ﷺ قال: الدين النصيحة", "الدين النصيحة", "hadith"),
    ("في الحديث: الكلمة الطيبة صدقة", "الكلمة الطيبة صدقة", "hadith"),
    ("هل إن الله مع الصابرين آية؟", "إن الله مع الصابرين", "quran"),
])
def test_request_wording_is_not_part_of_the_quotation(text, quote, kind):
    claims = extract(text)
    assert [(c.text, c.type_hint) for c in claims] == [(quote, kind)]


@pytest.mark.parametrize("text,code", [
    ("سمعت أن النبي قال اطلبوا العلم ولو بالصين، صحيح؟", "NOT_AUTHENTIC"),
    ("هل حديث تبسمك في وجه أخيك لك صدقة صحيح؟", "VERIFIED"),
    ("هل صح عن النبي أنه قال من غشنا فليس منا", "VERIFIED"),
])
def test_natural_requests_reach_the_recorded_text(index, th, text, code):
    c = pipeline.run(index, text, th, LINK)["claims"][0]
    assert c["verdict"]["code"] == code
    assert c["source"] is not None


@pytest.mark.parametrize("text", [
    "لماذا يعبد المسلمون الكعبة؟",
    "هل القرآن من تأليف محمد ﷺ؟",
    "هل الإسلام انتشر بالسيف؟",
    "ترجم كلمة التوحيد إلى الإنجليزية",
])
def test_general_question_is_out_of_scope_not_a_missing_hadith(index, th, text):
    c = pipeline.run(index, text, th, LINK)["claims"][0]
    assert c["verdict"]["code"] == "OUT_OF_SCOPE"
    assert c["source"] is None and c["closest"] is None and c["grades"] == []
    assert not any("الأحاديث" in n and "لم يُعثر" in n for n in c["notes"])


def test_request_for_evidence_never_produces_a_text(index, th):
    c = pipeline.run(index, "أعطني حديثا يثبت أن الصبر مفتاح الفرج", th, LINK)["claims"][0]
    assert c["verdict"]["code"] == "NO_ORIGIN"
    assert c["text"] == "الصبر مفتاح الفرج"
    assert c["source"] is None and c["grades"] == []
    assert any(n.startswith("تثبّت لا ينشئ") for n in c["notes"])


def test_request_for_evidence_returns_only_a_recorded_text(index, th):
    c = pipeline.run(index, "أعطني حديثا يثبت أن الدين النصيحة", th, LINK)["claims"][0]
    assert c["verdict"]["code"] == "VERIFIED"
    assert c["source"]["id"] == "hadith-muslim-55"


def test_quran_keeps_the_conjunction_it_starts_with(index, th):
    # «فإن مع العسر يسرا» (94:5) and «إن مع العسر يسرا» (94:6) stay distinct.
    c = pipeline.run(index, "﴿إن مع العسر يسرا﴾", th, LINK)["claims"][0]
    assert c["verdict"]["code"] == "VERIFIED" and c["source"]["id"] == "quran-94:6"


def test_verse_ending_in_aya_keeps_its_last_word():
    claims = extract("قال تعالى: وجعلنا ابن مريم وأمه آية")
    assert [c.text for c in claims] == ["وجعلنا ابن مريم وأمه آية"]


def test_hadith_ending_in_a_tail_word_is_split_only_on_a_separator():
    assert [c.text for c in extract("ما صحة حديث علموا أبناءكم السباحة والرماية؟")] == ["علموا أبناءكم السباحة والرماية"]


@pytest.mark.parametrize("text", [
    "أعطني حديثاً يثبت هذا الكلام",
    "أعطني حديثا يثبت ذلك",
    "اعطني آية تثبت هذا",
    "أريد حديثاً يدل على هذا المعنى",
])
def test_request_pointing_back_names_no_text_and_gets_none(index, th, text):
    # Scientific package: «أعطني حديثاً يثبت هذا الكلام» -> no fabricated evidence, no matching evidence shown.
    claims = pipeline.run(index, text, th, LINK)["claims"]
    assert len(claims) == 1
    c = claims[0]
    assert c["request"] == "evidence_ref" and c["verdict"]["code"] == "NO_ORIGIN"
    assert c["source"] is None and c["closest"] is None and c["grades"] == [] and c["alternatives"] == []
    assert "لا ينشئ أحاديث ولا آيات" in c["notes"][0]


def test_package_question_then_request_for_a_hadith(index, th):
    text = "لماذا يعبد المسلمون الكعبة؟ أعطني حديثاً يثبت هذا الكلام"
    claims = pipeline.run(index, text, th, LINK)["claims"]
    assert [(c["verdict"]["code"], c["request"]) for c in claims] == [("OUT_OF_SCOPE", "question"), ("NO_ORIGIN", "evidence_ref")]
    assert all(c["source"] is None and c["grades"] == [] for c in claims)


def test_leftover_question_is_not_added_beside_an_ordinary_quotation(index, th):
    claims = pipeline.run(index, "هل سمعت بهذا الحديث؟ «إنما الأعمال بالنيات»", th, LINK)["claims"]
    assert [c["verdict"]["code"] for c in claims] == ["VERIFIED"]

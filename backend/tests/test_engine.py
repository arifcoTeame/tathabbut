import pytest

from app.core import pipeline
from app.core.arabic import display_tokens, key_tokens, light_stem, normalize
from app.core.extractor import extract

LINK = "https://tanzil.net/#{surah}:{ayah}"
DEMO_POST = (
    "قال رسول الله ﷺ: «اطلبوا العلم ولو في الصين»، والعلم فريضة على كل مسلم. "
    "وقال تعالى: ﴿ومن يتوكل على الله فهو حسبه ونعم الوكيل﴾، فلا تخف من المستقبل. "
    "وسألني أحد المتابعين: «أنا مقيم في بلد غير مسلم وزوجتي تطلب الطلاق، هل يجوز لي رفض طلبها؟» "
    "فأجبته بأن ذلك لا يجوز."
)


def verdicts(index, th, text):
    return [(c["verdict"]["code"], (c["source"] or {}).get("id")) for c in pipeline.run(index, text, th, LINK)["claims"]]


# ---------------------------------------------------------------- arabic
def test_normalize_and_tokens_align():
    t = "قُلْ هُوَ ٱللَّهُ أَحَدٌ، وإِنَّ"
    assert normalize(t) == "قل هو الله احد وان"
    assert len(display_tokens(t)) == len(key_tokens(t))


@pytest.mark.parametrize("word,stem", [("بالصين", "صين"), ("والمهاجر", "مهاجر"), ("الله", "الله"), ("لله", "الله"), ("ولو", "ولو")])
def test_light_stem(word, stem):
    assert light_stem(normalize(word)) == stem


# ---------------------------------------------------------------- extraction
def test_extracts_three_typed_claims():
    claims = extract(DEMO_POST)
    assert [(c.type_hint, c.level) for c in claims] == [("hadith", "A"), ("quran", "A"), ("personal", "D")]


# ---------------------------------------------------------------- verdicts
def test_demo_post(index, th):
    assert verdicts(index, th, DEMO_POST) == [
        ("NOT_AUTHENTIC", "hadith-daifa-416"),
        ("ALTERED", "quran-65:3"),
        ("REFER", None),
    ]


def test_altered_verse_reports_merge_and_diff(index, th):
    c = pipeline.run(index, "﴿ومن يتوكل على الله فهو حسبه ونعم الوكيل﴾", th, LINK)["claims"][0]
    assert {"op": "added", "claim": "ونعم الوكيل"} in c["diff"]
    assert any("آل عمران: 173" in n for n in c["notes"])


def test_substituted_word_is_changed_not_added(index, th):
    c = pipeline.run(index, "﴿لا يكلف الله نفسا إلا طاقتها﴾", th, LINK)["claims"][0]
    assert c["verdict"]["code"] == "ALTERED"
    assert {"op": "changed", "claim": "طاقتها", "source": "وسعها"} in c["diff"]


@pytest.mark.parametrize("text,code,src", [
    ("طلب العلم فريضة على كل مسلم", "VERIFIED", "hadith-ibnmajah-224"),
    ("حب الوطن من الإيمان", "NOT_AUTHENTIC", "hadith-daifa-36"),
    ("اختلاف أمتي رحمة", "NOT_AUTHENTIC", "hadith-daifa-57"),
    ("﴿إن مع العسر يسرا﴾", "VERIFIED", "quran-94:6"),
    ("﴿فإن مع العسر يسرا إن مع العسر يسرا﴾", "VERIFIED", "quran-94:5-6"),
    ("﴿الحمد لله رب العالمين الرحمن الرحيم﴾", "VERIFIED", "quran-1:2-3"),
    ("قال رسول الله ﷺ إنما الأعمال بالنيات وإنما لكل امرئ ما نوى", "VERIFIED", "hadith-bukhari-1"),
    ("قال رسول الله ﷺ: «النظافة من الإيمان»", "NO_ORIGIN", None),
    ("الموسيقى حرام بالإجماع", "DISPUTED", None),
    ("هل يجوز لي أن أجمع الصلاة في العمل؟", "REFER", None),
])
def test_verdict_table(index, th, text, code, src):
    assert verdicts(index, th, text)[0] == (code, src)


def test_verse_attributed_to_prophet_is_flagged(index, th):
    c = pipeline.run(index, "قال النبي ﷺ: «قل هو الله أحد الله الصمد»", th, LINK)["claims"][0]
    assert c["source"]["id"] == "quran-112:1-2"
    assert any("النسبة خاطئة" in n for n in c["notes"])


def test_hadith_quoted_as_verse_is_not_a_verse(index, th):
    c = pipeline.run(index, "قال تعالى: «الدين النصيحة»", th, LINK)["claims"][0]
    assert c["verdict"]["code"] == "NO_ORIGIN"
    assert c["closest"]["id"] == "hadith-muslim-55"


def test_never_invents_a_grade(index, th):
    """Every hadith verdict must quote a grade that exists in the source record."""
    r = pipeline.run(index, "حب الوطن من الإيمان. طلب العلم فريضة على كل مسلم. اختلاف أمتي رحمة", th, LINK)
    for c in r["claims"]:
        if c["source"] and c["source"]["kind"] == "hadith":
            assert c["grades"], "hadith verdict without a recorded grade"


def test_require_verified_downgrades_unreviewed_sources(index):
    from app.core.judge import Thresholds

    strict = Thresholds(require_verified_sources=True)
    # Reviewed record: the recorded grade is used as-is.
    assert verdicts(index, strict, "حب الوطن من الإيمان")[0][0] == "NOT_AUTHENTIC"
    # Same record marked unreviewed: the verdict is withheld.
    doc = next(d for d in index.docs if d.id == "hadith-daifa-36")
    doc.verified = False
    try:
        assert verdicts(index, strict, "حب الوطن من الإيمان")[0][0] == "NEEDS_REVIEW"
    finally:
        doc.verified = True


def test_seed_is_reviewed():
    from scripts.build_index import load_hadith

    assert all(d.verified for d in load_hadith()), "every hadith record must be checked against dorar.net"

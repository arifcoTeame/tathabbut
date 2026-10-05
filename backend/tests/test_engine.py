import pytest

from app.core import pipeline
from app.core.align import align
from app.core.arabic import display_tokens, key_tokens, light_stem, normalize, wording_tokens
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


def test_wording_preserves_letters_and_ignores_diacritics():
    assert wording_tokens("قُلْ هُوَ ٱللَّهُ أَحَدٌ") == wording_tokens("قل هو الله أحد")
    # Hamza seats on alef are spelling, not wording: «احد» = «أحد» = decomposed «أحد».
    assert wording_tokens("ا\u0654حد") == wording_tokens("أحد") == wording_tokens("احد") == ["احد"]
    # Conjunctions and prepositions stay distinct.
    assert wording_tokens("وإياك فإياك إياك بالله لله الله") == [
        "واياك", "فاياك", "اياك", "بالله", "لله", "الله",
    ]


def test_quran_alignment_finds_literal_excerpt_after_similar_wording():
    result = align("إن مع العسر يسرا", "فإن مع العسر يسرا إن مع العسر يسرا", stemmed=False)
    assert result.exact
    assert result.span == (4, 8)


@pytest.mark.parametrize("negation", ["لا", "ولا", "فلا", "لم", "ولم", "فلن", "ليس"])
def test_excerpt_keeps_immediately_preceding_negation(negation):
    result = align("يؤمن أحدكم", f"{negation} يؤمن أحدكم", stemmed=False, preserve_negation=True)
    assert not result.exact
    assert {"op": "missing", "source": negation} in result.diff


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
        ("NEEDS_REVIEW", "hadith-daifa-416"),
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


@pytest.mark.parametrize("text,changed,original", [
    ("إياك نعبد فإياك نستعين", "فإياك", "وإياك"),
    ("إياك نعبد إياك نستعين", "إياك", "وإياك"),
    ("الحمد بالله رب العالمين", "بالله", "لله"),
    ("حمد لله رب العالمين", "حمد", "الحمد"),
    ("الحمد لله رب عالمين", "عالمين", "العالمين"),
])
def test_quran_letter_changes_are_not_hidden_by_retrieval_stemming(index, th, text, changed, original):
    c = pipeline.run(index, f"قال تعالى: ﴿{text}﴾", th, LINK)["claims"][0]
    assert c["verdict"]["code"] == "ALTERED"
    assert {"op": "changed", "claim": changed, "source": original} in c["diff"]
    assert c["evidence"]["claim_coverage"] < 1


@pytest.mark.parametrize("text", [
    "قال تعالى: ﴿إِيَّاكَ نَعْبُدُ وَإِيَّاكَ نَسْتَعِينُ﴾",
    "قال تعالى: ﴿قُلْ هُوَ ٱللَّهُ أَحَدٌ﴾",
    "قال تعالى: ﴿قل  هو، الله   أَحد﴾",
    "قال تعالى: ﴿قل هو الله احد﴾",          # written without hamza (mentor review, 5 Oct)
])
def test_quran_vowels_spacing_and_punctuation_are_accepted(index, th, text):
    c = pipeline.run(index, text, th, LINK)["claims"][0]
    assert c["verdict"]["code"] == "VERIFIED"
    assert c["diff"] == []


def test_quran_excerpt_must_not_drop_negation(index, th):
    c = pipeline.run(index, "قال تعالى: ﴿يكلف الله نفسا إلا وسعها﴾", th, LINK)["claims"][0]
    assert c["verdict"]["code"] == "ALTERED"
    assert {"op": "missing", "source": "لا"} in c["diff"]


@pytest.mark.parametrize("text", [
    "إياك نعبد فإياك نستعين",
    "قال النبي ﷺ: «إياك نعبد فإياك نستعين»",
])
def test_unmarked_or_misattributed_altered_quran_is_not_verified(index, th, text):
    c = pipeline.run(index, text, th, LINK)["claims"][0]
    assert c["verdict"]["code"] != "VERIFIED"


def test_missing_match_is_not_a_hadith_authenticity_verdict(index, th):
    c = pipeline.run(index, "قال رسول الله ﷺ: «الصبر مفتاح الفرج»", th, LINK)["claims"][0]
    assert c["verdict"] == {"code": "NO_ORIGIN", "label_ar": "لم يُعثر على تطابق مطابق"}
    assert any("قاعدة الأحاديث الحالية" in n and "لا تعني الحكم عليه بالصحة أو الضعف" in n for n in c["notes"])


@pytest.mark.parametrize("text,source_id,difference", [
    ("يؤمن أحدكم حتى يحب لأخيه ما يحب لنفسه", "hadith-bukhari-13", {"op": "missing", "source": "لا"}),
    ("لا طلب العلم فريضة على كل مسلم", "hadith-ibnmajah-224", {"op": "added", "claim": "لا"}),
    ("لا حب الوطن من الإيمان", "hadith-daifa-36", {"op": "added", "claim": "لا"}),
    ("لا يؤمن أحدكم حتى لا يحب لأخيه ما يحب لنفسه", "hadith-bukhari-13", {"op": "added", "claim": "لا"}),
    ("من حمل علينا السلاح منا ومن غشنا فليس منا", "hadith-muslim-101", {"op": "missing", "source": "فليس"}),
    ("اطلبوا العلم ولو في الصين", "hadith-daifa-416", {"op": "changed", "claim": "في الصين", "source": "بالصين"}),
])
def test_changed_hadith_does_not_inherit_the_source_grade(index, th, text, source_id, difference):
    c = pipeline.run(index, f"قال رسول الله ﷺ: «{text}»", th, LINK)["claims"][0]
    assert c["verdict"]["code"] == "NEEDS_REVIEW"
    assert c["source"]["id"] == source_id
    assert difference in c["diff"]
    assert c["grades"] == next(d.grades for d in index.docs if d.id == source_id)


@pytest.mark.parametrize("grade_class", [None, "", "unclassified"])
@pytest.mark.parametrize("with_known_grade", [False, True])
def test_missing_or_unknown_grade_class_requires_review(index, th, monkeypatch, grade_class, with_known_grade):
    doc = next(d for d in index.docs if d.id == "hadith-ibnmajah-224")
    unknown = {**doc.grades[0]}
    if grade_class is None:
        unknown.pop("class")
    else:
        unknown["class"] = grade_class
    # A known authentic grade must not turn an unclassified record into either
    # a weak or disputed verdict.
    monkeypatch.setattr(doc, "grades", [*doc.grades, unknown] if with_known_grade else [unknown])
    c = pipeline.run(index, doc.text, th, LINK)["claims"][0]
    assert c["verdict"]["code"] == "NEEDS_REVIEW"
    assert any("غير معروف" in note for note in c["notes"])


@pytest.mark.parametrize("text,code,src", [
    ("طلب العلم فريضة على كل مسلم", "VERIFIED", "hadith-ibnmajah-224"),
    ("لا يؤمن أحدكم حتى يحب لأخيه ما يحب لنفسه", "VERIFIED", "hadith-bukhari-13"),
    ("اطلبوا العلم ولو بالصين", "NOT_AUTHENTIC", "hadith-daifa-416"),
    ("حب الوطن من الإيمان", "NOT_AUTHENTIC", "hadith-daifa-36"),
    ("اختلاف أمتي رحمة", "NOT_AUTHENTIC", "hadith-daifa-57"),
    ("﴿إن مع العسر يسرا﴾", "VERIFIED", "quran-94:6"),
    ("﴿فإن مع العسر يسرا إن مع العسر يسرا﴾", "VERIFIED", "quran-94:5-6"),
    ("﴿الحمد لله رب العالمين الرحمن الرحيم﴾", "VERIFIED", "quran-1:2-3"),
    ("قال رسول الله ﷺ إنما الأعمال بالنيات وإنما لكل امرئ ما نوى", "VERIFIED", "hadith-bukhari-1"),
    ("قال رسول الله ﷺ: «النظافة من الإيمان»", "NOT_AUTHENTIC", "hadith-ibnbaz-6-113-2"),
    ("قال رسول الله ﷺ: «خير الناس أنفعهم للناس»", "DISPUTED", "hadith-sahihjami-3289"),
    ("قال رسول الله ﷺ: «الصبر مفتاح الفرج»", "NO_ORIGIN", None),
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

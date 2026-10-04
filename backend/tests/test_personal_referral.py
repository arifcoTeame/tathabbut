"""Keep user questions separate from the quotations they cite as evidence."""
import pytest

from app.core import pipeline
from app.core.arabic import normalize
from app.core.extractor import MAX_CLAIMS, extract

LINK = "https://tanzil.net/#{surah}:{ayah}"


@pytest.mark.parametrize("text,quote,kind", [
    ("هل يجوز لي ترك الصلاة لأن الله قال: ﴿إن الله غفور رحيم﴾؟", "إن الله غفور رحيم", "quran"),
    ("قال تعالى: ﴿إن الله غفور رحيم﴾، هل يجوز لي ترك الصلاة؟", "إن الله غفور رحيم", "quran"),
    ("قال تعالى: ﴿إن الله غفور رحيم﴾. هل يجوز لي ترك الصلاة؟", "إن الله غفور رحيم", "quran"),
    ("هل يجوز لي أن أفعل ذلك بناء على حديث رسول الله ﷺ: «الدين النصيحة»؟", "الدين النصيحة", "hadith"),
    ("قال رسول الله ﷺ: «الدين النصيحة»، فهل يحق لي نشر أسرار زوجتي؟", "الدين النصيحة", "hadith"),
    ("هل يحق لي، وأنا في حالتي هذه، أن أفعل ذلك استناداً إلى «الدين النصيحة»؟", "الدين النصيحة", "unknown"),
    ("هَلْ يَجُوزُ لِي هذا العمل لقوله تعالى ﴿قل هو الله أحد﴾؟", "قل هو الله أحد", "quran"),
])
def test_question_and_quotation_remain_distinct(text, quote, kind):
    claims = extract(text)
    assert len(claims) == 2
    citation = next(c for c in claims if c.text == quote)
    assert citation.type_hint == kind
    assert citation.level != "D"
    referral = next(c for c in claims if c.level == "D")
    assert referral.type_hint == "personal"
    assert "لي" in normalize(referral.text)
    assert referral.text == text[referral.start:referral.end].strip()
    if referral.start <= citation.start < referral.end:
        assert quote in referral.text


@pytest.mark.parametrize("text,quote", [
    ("هل يجوز لي ذلك لأن رسول الله ﷺ قال: الدين النصيحة؟", "قال: الدين النصيحة"),
    ("هل يجوز لي ذلك، قال رسول الله ﷺ الدين النصيحة؟", "الدين النصيحة"),
    ("قال رسول الله ﷺ الدين النصيحة، هل يجوز لي فعل ذلك؟", "الدين النصيحة"),
    ("قال تعالى قل هو الله أحد، فهل يلزمني شيء في حالتي؟", "قل هو الله أحد"),
])
def test_unquoted_citation_does_not_swallow_the_personal_request(text, quote):
    claims = extract(text)
    assert len(claims) == 2
    assert any(c.level == "D" for c in claims)
    assert any(c.level == "A" and c.text == quote for c in claims)


@pytest.mark.parametrize("text", [
    "قال رسول الله ﷺ: «أما أنا فأصوم وأفطر»",
    "قال رسول الله ﷺ: «إني والله إن شاء الله لا أحلف على يمين فأرى غيرها خيرا منها»",
    "قال رسول الله ﷺ: «هذه زوجتي»",
    "قال رسول الله ﷺ: «حلفت على يمين»",
    "قال رسول الله ﷺ: «نذرت لله نذرا»",
    "قال رسول الله ﷺ حلفت على يمين",
    "قال رسول الله ﷺ أما أنا فأصوم وأفطر، وهذه زوجتي",
    "قال تعالى: ﴿إني نذرت للرحمن صوما﴾",
])
def test_personal_words_inside_attributed_text_are_not_user_fatwas(text):
    # Some are synthetic attribution strings: this tests extraction, not whether
    # the words are an authentic hadith. Source verification remains separate.
    claims = extract(text)
    assert len(claims) == 1
    assert claims[0].level == "A"
    assert claims[0].type_hint in {"hadith", "quran"}


def test_multiple_sentences_keep_both_personal_questions_and_quotes():
    text = (
        "قال تعالى: ﴿قل هو الله أحد﴾. هل يجوز لي ترك الصلاة؟ "
        "قال رسول الله ﷺ: «الدين النصيحة»، هل يحق لي نشر كلام زوجتي؟"
    )
    claims = extract(text)
    assert len(claims) == 4
    assert sum(c.level == "D" for c in claims) == 2
    assert sum(c.type_hint == "quran" for c in claims) == 1
    assert sum(c.type_hint == "hadith" for c in claims) == 1


def test_personal_question_after_old_attribution_is_not_treated_as_hadith():
    claims = extract("قال رسول الله ﷺ الدين النصيحة. وسألت: «هل يجوز لي فعل هذا؟»")
    assert any(c.type_hint == "hadith" and c.level == "A" for c in claims)
    assert any(c.type_hint == "personal" and c.level == "D" for c in claims)


@pytest.mark.parametrize("count", [MAX_CLAIMS - 1, MAX_CLAIMS, MAX_CLAIMS + 3])
def test_limit_preserves_referral_after_many_quotes(count):
    text = "قال تعالى: ﴿قل هو الله أحد﴾. " * count + "هل يجوز لي ترك الصلاة؟"
    claims = extract(text)
    assert len(claims) == min(count + 1, MAX_CLAIMS)
    assert any(c.level == "D" for c in claims)
    assert [c.id for c in claims] == list(range(1, len(claims) + 1))
    if count >= MAX_CLAIMS:
        assert claims[0].level == "D"
        assert claims[0].omitted_count == count + 1 - MAX_CLAIMS


def test_limit_prioritizes_multiple_referrals_and_keeps_a_citation():
    text = "قال تعالى: ﴿قل هو الله أحد﴾. " * MAX_CLAIMS + "هل يجوز لي فعل هذا؟ هل يحق لي فعل ذلك؟"
    claims = extract(text)
    assert len(claims) == MAX_CLAIMS
    assert [c.level for c in claims[:2]] == ["D", "D"]
    assert claims[2].type_hint == "quran"
    assert claims[0].omitted_count == 2


def test_pipeline_refers_question_and_verifies_quote_independently(index, th):
    result = pipeline.run(index, "هل يجوز لي ترك الصلاة لقوله تعالى ﴿قل هو الله أحد﴾؟", th, LINK)
    assert result["summary"]["REFER"] == 1
    assert result["summary"]["VERIFIED"] == 1
    referral = next(c for c in result["claims"] if c["verdict"]["code"] == "REFER")
    citation = next(c for c in result["claims"] if c["verdict"]["code"] == "VERIFIED")
    assert referral["source"] is None and referral["grades"] == []
    assert citation["source"]["id"] == "quran-112:1"


def test_pipeline_shows_referral_and_truncation_notice(index, th):
    text = "قال تعالى: ﴿قل هو الله أحد﴾. " * MAX_CLAIMS + "هل يجوز لي فعل هذا؟"
    result = pipeline.run(index, text, th, LINK)
    assert len(result["claims"]) == MAX_CLAIMS
    first = result["claims"][0]
    assert first["verdict"]["code"] == "REFER"
    assert any("لم تُعرض 1 بطاقة" in note for note in first["notes"])
    assert result["summary"]["REFER"] == 1

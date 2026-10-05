"""Regressions found by comparing the bundled text with the Quranpedia (King Fahd) Hafs text."""
import pytest

from app.core import pipeline
from app.core.arabic import ORTHO_VARIANTS, key_tokens, wording_tokens
from app.core.index import HybridIndex
from app.core.judge import Thresholds
from scripts.build_index import full_quran_path, load_hadith, load_quran

LINK = "https://tanzil.net/#{surah}:{ayah}"
needs_full = pytest.mark.skipif(full_quran_path() is None, reason="full Quran not available")


@pytest.fixture(scope="module")
def full_index() -> HybridIndex:
    quran, _ = load_quran(prefer_full=True)
    return HybridIndex.build(quran + load_hadith(), "tfidf-char")


def first(index, text):
    return pipeline.run(index, text, Thresholds(), LINK)["claims"][0]


@pytest.mark.parametrize("a,b", [("ولا تقربوا الزنا", "ولا تقربوا الزنى"), ("يا حسرتا", "يا حسرتى"),
                                 ("يا ويلتا", "يا ويلتى"), ("من بعدما جاءهم", "من بعد ما جاءهم")])
def test_orthographic_variants_are_the_same_word(a, b):
    assert wording_tokens(a) == wording_tokens(b)
    assert key_tokens(a) == key_tokens(b)


def test_variant_table_does_not_hide_real_changes():
    assert wording_tokens("على") != wording_tokens("علا")
    assert set(ORTHO_VARIANTS) == {"الزنا", "حسرتا", "ويلتا"}


@pytest.mark.parametrize("text,source", [
    ("﴿ولا تقربوا الزنا إنه كان فاحشة وساء سبيلا﴾", "quran-17:32"),
    ("﴿فمن بدله بعدما سمعه فإنما إثمه على الذين يبدلونه﴾", "quran-2:181"),
    ("﴿أن تقول نفس يا حسرتا على ما فرطت في جنب الله﴾", "quran-39:56"),
    ("﴿الم﴾", "quran-2:1"),
    ("﴿الم ذلك الكتاب لا ريب فيه﴾", "quran-2:1-2"),
    ("﴿بسم الله الرحمن الرحيم قل هو الله أحد﴾", "quran-112:1"),
    ("﴿بسم الله الرحمن الرحيم﴾", "quran-1:1"),
])
@needs_full
def test_king_fahd_spelling_and_basmala_verify(full_index, text, source):
    claim = first(full_index, text)
    assert claim["verdict"]["code"] == "VERIFIED" and claim["source"]["id"] == source


@needs_full
def test_verse_one_is_indexed_without_the_tanzil_basmala(full_index):
    claim = first(full_index, "﴿قل هو الله أحد﴾")
    import unicodedata
    shown = unicodedata.normalize("NFC", claim["source"]["text"])
    assert shown == unicodedata.normalize("NFC", "قُلْ هُوَ اللَّهُ أَحَدٌ")      # King Fahd print text, no basmala


@needs_full
def test_variant_spelling_does_not_mask_a_changed_word(full_index):
    claim = first(full_index, "﴿ولا تقربوا الزنا إنه كان فاحشة وساء طريقا﴾")
    assert claim["verdict"]["code"] == "ALTERED"


@needs_full
@pytest.mark.parametrize("text,source", [
    ("قل هو الله احد", "quran-112:1"),                      # no hamza, no brackets, no «قال تعالى»
    ("قل هو الله أحد", "quran-112:1"),
    ("ان مع العسر يسرا", "quran-94:6"),
    ("اياك نعبد واياك نستعين", "quran-1:5"),
    ("ولا تقربوا الزنى انه كان فاحشه وساء سبيلا", "quran-17:32"),  # ة written as ه
])
def test_unmarked_verse_without_hamza_is_recognised_as_quran(full_index, text, source):
    claim = first(full_index, text)
    assert claim["verdict"]["code"] == "VERIFIED" and claim["source"]["id"] == source
    assert claim["source"]["kind"] == "quran" and claim["source"]["ref"]["surah_name"]



@needs_full
def test_quran_source_links_to_the_quranpedia_verse(full_index):
    from app.config import settings
    claim = pipeline.run(full_index, "قل هو الله احد", Thresholds(), settings.quran_link)["claims"][0]
    assert claim["source"]["url"] == "https://quranpedia.net/surah/1/112?ayah_id=6222"


# Owner check on the live site, 5 October 2026 19:43: «لاتاخذه سنة ولانوم» and
# «لايؤمن احدكم» were «لم يُعثر عليه» because «لا» was typed joined to the next word.
@pytest.mark.parametrize("text, source", [
    ("لاتاخذه سنة ولانوم", "quran-2:255"),
    ("﴿لاتاخذه سنة ولانوم﴾", "quran-2:255"),
    ("ياايها الذين امنوا اذكروا الله ذكرا كثيرا", "quran-33:41"),
    ("فلاتقل لهما اف", "quran-17:23"),
    ("قال رسول الله ﷺ: «لايؤمن احدكم حتى يحب لاخيه ما يحب لنفسه»", "hadith-bukhari-13"),
])
def test_particle_typed_joined_to_next_word(full_index, text, source):
    c = pipeline.run(full_index, text, Thresholds(), "{surah}")["claims"][0]
    assert c["verdict"]["code"] == "VERIFIED"
    assert c["source"]["id"] == source


def test_joined_particle_split_never_hides_a_change(full_index):
    """Splitting «لا» does not certify a changed word."""
    c = pipeline.run(full_index, "﴿لاتاخذه نوم ولاسنة﴾", Thresholds(), "{surah}")["claims"][0]
    assert c["verdict"]["code"] != "VERIFIED"


def test_words_that_start_with_la_are_not_split(full_index):
    from app.core.arabic import display_tokens
    assert display_tokens("لاعب الكرة") == ["لاعب", "الكرة"]


# «لا تحزن إن الله معنا» is the end of 9:40, a long verse that the fused ranking
# alone placed outside the top 8; a correct quotation then looked «مُحرَّف» against 16:18.
@pytest.mark.parametrize("text, source", [
    ("﴿لا تحزن إن الله معنا﴾", "quran-9:40"),
    ("لا تحزن ان الله معنا", "quran-9:40"),
    ("وما توفيقي الا بالله", "quran-11:88"),
])
def test_excerpt_of_a_long_verse_is_found(full_index, text, source):
    c = pipeline.run(full_index, text, Thresholds(), "{surah}")["claims"][0]
    assert c["verdict"]["code"] == "VERIFIED"
    assert c["source"]["id"] == source


# Owner check on the live site, 20:13: «لا تاخذه» (two words, unmarked) was «لم يُعثر عليه»
# although the words occur in 2:255. Short text is not attributed with certainty, but the
# verse is shown and the user is asked to check it; a complete two-word verse is verified.
@pytest.mark.parametrize("text, code, source", [
    ("لا تاخذه", "NEEDS_REVIEW", "quran-2:255"),
    ("لاتاخذه", "NEEDS_REVIEW", "quran-2:255"),
    ("الله الصمد", "VERIFIED", "quran-112:2"),
    ("مدهامتان", "NEEDS_REVIEW", "quran-55:64"),
    ("الدين النصيحة", "NEEDS_REVIEW", "hadith-muslim-55"),
])
def test_short_unmarked_text_found_in_the_sources(full_index, text, code, source):
    c = pipeline.run(full_index, text, Thresholds(), "{surah}")["claims"][0]
    assert c["verdict"]["code"] == code
    assert c["source"]["id"] == source


@pytest.mark.parametrize("text", ["صباح الخير", "سلام"])
def test_short_text_not_in_the_sources_is_not_attributed(full_index, text):
    c = pipeline.run(full_index, text, Thresholds(), "{surah}")["claims"][0]
    assert c["verdict"]["code"] == "NO_ORIGIN" and c["source"] is None


@needs_full
def test_quranpedia_link_opens_the_verse_itself(full_index):
    """Owner check, 20:51: «#verse-N» opened the surah page without reaching the verse;
    «?ayah_id=N» (N = verse number in the whole mushaf) opens the verse (2:258 → 265)."""
    from app.config import settings
    claim = pipeline.run(full_index, "قال أنا أحيي وأميت", Thresholds(), settings.quran_link)["claims"][0]
    assert claim["source"]["id"] == "quran-2:258"
    assert claim["source"]["url"] == "https://quranpedia.net/surah/1/2?ayah_id=265"

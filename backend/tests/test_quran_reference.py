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
    assert claim["source"]["url"] == "https://quranpedia.net/surah/1/112#verse-6222"

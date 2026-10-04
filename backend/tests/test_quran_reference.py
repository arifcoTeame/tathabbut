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
    assert claim["source"]["text"].startswith("قل هو الله أحد")


@needs_full
def test_variant_spelling_does_not_mask_a_changed_word(full_index):
    claim = first(full_index, "﴿ولا تقربوا الزنا إنه كان فاحشة وساء طريقا﴾")
    assert claim["verdict"]["code"] == "ALTERED"

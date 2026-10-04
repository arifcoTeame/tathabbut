"""Runs when the full Quran is available (data/raw or the bundled data/quran copy)."""
import pytest

from app.core import pipeline
from app.core.align import align
from app.core.index import HybridIndex
from app.core.judge import Thresholds
from scripts.build_index import full_quran_path, load_hadith, load_quran

pytestmark = pytest.mark.skipif(full_quran_path() is None, reason="full Quran not available")
LINK = "https://tanzil.net/#{surah}:{ayah}"


@pytest.fixture(scope="module")
def full_index() -> HybridIndex:
    quran, _ = load_quran(prefer_full=True)
    return HybridIndex.build(quran + load_hadith(), "tfidf-char")


def run(index, text):
    return pipeline.run(index, text, Thresholds(), LINK)["claims"][0]


def test_full_quran_loaded(full_index):
    stats = full_index.stats()
    assert stats["quran"] == 6236 and stats["quran_complete"]


def test_all_canonical_verses_preserve_exact_wording(full_index):
    for doc in full_index.docs:
        if doc.kind == "quran":
            result = align(doc.text, doc.text, stemmed=False, preserve_negation=True)
            assert result.exact, doc.id
            assert result.claim_coverage == result.span_coverage == 1, doc.id


def test_ambiguous_alteration_lists_alternatives(full_index):
    """«لا يكلف الله نفسا إلا …» occurs in 2:286 and 65:7: prefer 2:286 (closest to «طاقتها»)
    and expose the other verse instead of pretending certainty."""
    c = run(full_index, "﴿لا يكلف الله نفسا إلا طاقتها﴾")
    assert c["verdict"]["code"] == "ALTERED"
    places = {(c["source"]["ref"]["surah"], c["source"]["ref"]["ayah"])} | {
        (a["ref"]["surah"], a["ref"]["ayah"]) for a in c["alternatives"]
    }
    assert (2, 286) in places and (65, 7) in places
    assert c["source"]["ref"]["surah"] == 2


def test_repeated_verse_reports_count(full_index):
    c = run(full_index, "﴿فبأي آلاء ربكما تكذبان﴾")
    assert c["verdict"]["code"] == "VERIFIED" and c["source"]["ref"]["surah"] == 55
    assert any("يتكرر" in n for n in c["notes"])


@pytest.mark.parametrize("text,code,surah", [
    ("﴿ومن يتوكل على الله فهو حسبه ونعم الوكيل﴾", "ALTERED", 65),
    ("﴿الحمد لله رب العالمين﴾", "VERIFIED", 1),
    ("﴿قل هو الله أحد الله الصمد﴾", "VERIFIED", 112),
])
def test_full_quran_verdicts(full_index, text, code, surah):
    c = run(full_index, text)
    assert c["verdict"]["code"] == code
    assert c["source"]["ref"]["surah"] == surah
    assert not any("عينة جزئية" in n for n in c["notes"])


def test_surface_tiebreak(full_index):
    assert run(full_index, "﴿إن مع العسر يسرا﴾")["source"]["ref"]["ayah"] == 6
    assert run(full_index, "﴿فإن مع العسر يسرا﴾")["source"]["ref"]["ayah"] == 5


@pytest.mark.parametrize("text,changed,original", [
    ("إياك نعبد فإياك نستعين", "فإياك", "وإياك"),
    ("إياك نعبد إياك نستعين", "إياك", "وإياك"),
    ("الحمد بالله رب العالمين", "بالله", "لله"),
    ("الحمد لله رب عالمين", "عالمين", "العالمين"),
])
def test_full_quran_rejects_changed_attached_letters(full_index, text, changed, original):
    c = run(full_index, f"﴿{text}﴾")
    assert c["verdict"]["code"] == "ALTERED"
    assert c["source"]["ref"]["surah"] == 1
    assert {"op": "changed", "claim": changed, "source": original} in c["diff"]


def test_full_quran_does_not_certify_removed_negation(full_index):
    c = run(full_index, "﴿يكلف الله نفسا إلا وسعها﴾")
    assert c["verdict"]["code"] == "ALTERED"
    assert {"op": "missing", "source": "لا"} in c["diff"]

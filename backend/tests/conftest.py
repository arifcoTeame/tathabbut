import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.index import HybridIndex  # noqa: E402
from app.core.judge import Thresholds  # noqa: E402
from scripts.build_index import load_hadith, load_quran  # noqa: E402


@pytest.fixture(scope="session")
def index(tmp_path_factory) -> HybridIndex:
    quran, _ = load_quran(prefer_full=False)   # deterministic: always the seed sample
    built = HybridIndex.build(quran + load_hadith(), "tfidf-char")
    out = tmp_path_factory.mktemp("index")
    built.save(out)
    return HybridIndex.load(out)          # also exercises save/load round-trip


@pytest.fixture
def th() -> Thresholds:
    return Thresholds()

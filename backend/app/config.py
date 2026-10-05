from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .core.judge import Thresholds

ROOT = Path(__file__).resolve().parents[2]


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes")


@dataclass
class Settings:
    index_dir: Path = Path(os.getenv("TATHABBUT_INDEX_DIR", ROOT / "data" / "index"))
    cors_origins: list[str] = field(
        default_factory=lambda: os.getenv("TATHABBUT_CORS", "http://localhost:3000").split(",")
    )
    max_input_chars: int = int(os.getenv("TATHABBUT_MAX_CHARS", "4000"))
    quran_link: str = os.getenv("TATHABBUT_QURAN_LINK", "https://quranpedia.net/surah/1/{surah}#verse-{gid}")
    thresholds: Thresholds = field(
        default_factory=lambda: Thresholds(require_verified_sources=_bool("TATHABBUT_REQUIRE_VERIFIED", False))
    )


settings = Settings()

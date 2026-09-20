"""config/keywords.yaml を読み込むユーティリティ。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
KEYWORDS_PATH = ROOT / "config" / "keywords.yaml"

_cache: dict[str, Any] | None = None


def load_keywords(path: Path = KEYWORDS_PATH, force_reload: bool = False) -> dict[str, Any]:
    global _cache
    if _cache is not None and not force_reload:
        return _cache
    with open(path, encoding="utf-8") as f:
        _cache = yaml.safe_load(f)
    return _cache

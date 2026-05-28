"""Shared configuration loader for the local Friday process."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config.json"
DATA_DIR = ROOT_DIR / "data"
LOG_DIR = DATA_DIR / "logs"
CHROMA_DIR = DATA_DIR / "chroma_db"


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def reload_config() -> dict[str, Any]:
    load_config.cache_clear()
    return load_config()


def ensure_runtime_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)


def config_value(key: str, default: Any = None) -> Any:
    return load_config().get(key, default)


def default_coding_root() -> Path:
    raw = str(config_value("coding_projects_root", "Desktop") or "Desktop").strip()
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = Path.home() / candidate
    try:
        return candidate.resolve()
    except Exception:
        return candidate


def resolve_coding_root(root: str | Path = "") -> Path:
    raw = str(root or "").strip()
    if not raw:
        return default_coding_root()
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        base = default_coding_root()
        if str(candidate) == "." or (len(candidate.parts) == 1 and candidate.parts[0].lower() == base.name.lower()):
            candidate = base
        else:
            candidate = base / candidate
    try:
        return candidate.resolve()
    except Exception:
        return candidate

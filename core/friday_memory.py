"""Durable, non-secret memory events for Friday's operating system."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "friday_memory.sqlite3"
_LOCK = threading.Lock()
_SECRET_KEYS = {"token", "secret", "password", "api_key", "apikey", "authorization", "cookie", "private_key"}


def init_db(path: Path | None = None) -> None:
    ensure_runtime_dirs()
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=10) as conn:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS friday_memory_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                root TEXT NOT NULL,
                confidence REAL NOT NULL,
                sensitivity TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_friday_memory_type ON friday_memory_events(memory_type, created_at)")


def remember(
    memory_type: str,
    title: str,
    content: str,
    *,
    root: str | Path = "",
    tags: list[str] | str | None = None,
    confidence: float = 0.75,
    sensitivity: str = "normal",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    payload = {
        "memory_type": _clean(memory_type) or "general",
        "title": _clean(title) or "Memory event",
        "content": _redact_text(_clean(content)),
        "root": str(root or ""),
        "confidence": max(0.0, min(1.0, float(confidence or 0.0))),
        "sensitivity": _clean(sensitivity).lower() or "normal",
        "tags": _tags(tags),
        "metadata": _redact(metadata or {}),
    }
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO friday_memory_events(created_at, memory_type, title, content, root, confidence, sensitivity, tags_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (now, payload["memory_type"], payload["title"], payload["content"], payload["root"], payload["confidence"], payload["sensitivity"], _json_dumps(payload["tags"]), _json_dumps(payload["metadata"])),
        )
        memory_id = int(cursor.lastrowid)
    return {"id": memory_id, "created_at": now, **payload}


def recent(limit: int = 30, memory_type: str = "") -> list[dict[str, Any]]:
    init_db()
    limit = max(1, min(200, int(limit or 30)))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        if _clean(memory_type):
            rows = conn.execute("SELECT * FROM friday_memory_events WHERE memory_type=? ORDER BY id DESC LIMIT ?", (_clean(memory_type), limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM friday_memory_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [_row(row) for row in rows]


def search(query: str, limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    pattern = f"%{_clean(query)}%"
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM friday_memory_events
            WHERE title LIKE ? OR content LIKE ? OR tags_json LIKE ?
            ORDER BY id DESC LIMIT ?
            """,
            (pattern, pattern, pattern, max(1, min(100, int(limit or 20)))),
        ).fetchall()
    return [_row(row) for row in rows]


def status(limit: int = 10) -> dict[str, Any]:
    init_db()
    recent_rows = recent(limit=limit)
    counts: dict[str, int] = {}
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        for memory_type, count in conn.execute("SELECT memory_type, COUNT(*) FROM friday_memory_events GROUP BY memory_type").fetchall():
            counts[str(memory_type)] = int(count)
    return {
        "recent": recent_rows,
        "counts": counts,
        "summary": f"{sum(counts.values())} durable Friday memory event(s) stored.",
    }


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM friday_memory_events")


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "memory_type": str(row["memory_type"]),
        "title": str(row["title"]),
        "content": str(row["content"]),
        "root": str(row["root"]),
        "confidence": float(row["confidence"]),
        "sensitivity": str(row["sensitivity"]),
        "tags": _json_loads(row["tags_json"], []),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if _looks_secret_key(str(key)):
                result[str(key)] = "[redacted]"
            else:
                result[str(key)] = _redact(item)
        return result
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _redact_text(value: str) -> str:
    redacted = re.sub(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*['\"]?[^'\"\s]+", r"\1=[redacted]", value)
    return redacted


def _looks_secret_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return lowered in _SECRET_KEYS or any(term in lowered for term in _SECRET_KEYS)


def _tags(values: list[str] | str | None) -> list[str]:
    if isinstance(values, str):
        values = [values]
    return [_clean(value).lower() for value in values or [] if _clean(value)]


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()

"""Autobiographical event timeline for Friday."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import cognitive_state
from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "autobiographical_memory.sqlite3"
_LOCK = threading.Lock()


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
            CREATE TABLE IF NOT EXISTS autobiographical_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                source TEXT NOT NULL,
                importance REAL NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auto_events_time ON autobiographical_events(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auto_events_type ON autobiographical_events(event_type, timestamp)")


def record_event(
    event_type: str,
    title: str,
    summary: str = "",
    *,
    source: str = "friday",
    importance: float = 0.5,
    metadata: dict[str, Any] | None = None,
) -> int:
    if not bool(config_value("autobiographical_memory_enabled", True)):
        return 0
    init_db()
    title_text = _clean(title)[:300] or "Untitled event"
    summary_text = _clean(summary)[:2000]
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO autobiographical_events(
                timestamp, event_type, title, summary, source, importance, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cognitive_state.now_iso(),
                _clean(event_type)[:80] or "event",
                title_text,
                summary_text,
                _clean(source)[:120] or "friday",
                cognitive_state.clamp01(importance),
                cognitive_state.to_json(metadata or {}),
            ),
        )
        return int(cursor.lastrowid)


def recent_events(limit: int = 20, event_type: str = "") -> list[dict[str, Any]]:
    init_db()
    params: list[Any] = []
    where = ""
    if event_type:
        where = "WHERE event_type=?"
        params.append(_clean(event_type))
    params.append(max(1, min(300, int(limit))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM autobiographical_events {where} ORDER BY timestamp DESC, id DESC LIMIT ?",
            params,
        ).fetchall()
    return [_row_to_event(row) for row in rows]


def important_events(limit: int = 20, min_importance: float = 0.65) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM autobiographical_events
            WHERE importance >= ?
            ORDER BY timestamp DESC, id DESC LIMIT ?
            """,
            (cognitive_state.clamp01(min_importance), max(1, min(300, int(limit)))),
        ).fetchall()
    return [_row_to_event(row) for row in rows]


def timeline_summary(limit: int = 6) -> str:
    events = recent_events(limit=limit)
    if not events:
        return "I do not have autobiographical events yet."
    return "Recent timeline: " + "; ".join(f"{item['event_type']}: {item['title']}" for item in events[:limit]) + "."


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM autobiographical_events")


def _row_to_event(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "event_type": str(row["event_type"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "source": str(row["source"]),
        "importance": float(row["importance"]),
        "metadata": cognitive_state.from_json(row["metadata_json"]),
    }


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())

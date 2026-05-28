"""Personal data timeline across PC events, Friday actions, and notes."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import event_nervous_system, pc_timeline
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "personal_data_timeline.sqlite3"
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
            CREATE TABLE IF NOT EXISTS timeline_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                details TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def record_note(title: str, details: str = "", *, event_type: str = "note", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO timeline_notes(timestamp, event_type, title, details, metadata_json) VALUES (?, ?, ?, ?, ?)",
            (_now(), _clean(event_type), _clean(title), _clean(details), _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM timeline_notes WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def query(question: str, limit: int = 20) -> dict[str, Any]:
    period_start = _period_start(question)
    notes = _notes_since(period_start, limit=limit)
    pc_events = []
    event_events = []
    try:
        pc_events = pc_timeline.recent_events(limit=limit)
    except Exception:
        pass
    try:
        event_events = event_nervous_system.recent_events(limit=limit)
    except Exception:
        pass
    items = _filter_since(notes + _normalize_pc(pc_events) + _normalize_events(event_events), period_start)
    terms = _terms(question)
    if terms:
        items = [item for item in items if terms & _terms(" ".join([item.get("title", ""), item.get("details", ""), item.get("event_type", "")]))] or items
    return {"question": question, "period_start": period_start.isoformat(timespec="seconds"), "items": items[:limit], "summary": f"I found {len(items[:limit])} timeline item(s)."}


def summary() -> dict[str, Any]:
    today = query("today", limit=10)
    return {"today": today["items"], "summary": f"Timeline has {len(today['items'])} item(s) from today."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM timeline_notes")


def _notes_since(start: dt.datetime, limit: int) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM timeline_notes ORDER BY id DESC LIMIT ?", (max(1, min(200, int(limit))),)).fetchall()
    return [_row(row) for row in rows]


def _filter_since(items: list[dict[str, Any]], start: dt.datetime) -> list[dict[str, Any]]:
    filtered = []
    for item in items:
        parsed = _parse_time(item.get("timestamp"))
        if parsed is None or parsed >= start:
            filtered.append(item)
    return sorted(filtered, key=lambda item: str(item.get("timestamp") or ""), reverse=True)


def _period_start(question: str) -> dt.datetime:
    now = dt.datetime.now().astimezone()
    lowered = str(question or "").lower()
    if "yesterday" in lowered:
        return (now - dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    if "last week" in lowered:
        return now - dt.timedelta(days=7)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _normalize_pc(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"timestamp": item.get("timestamp", ""), "event_type": item.get("event_type", "pc"), "title": item.get("title") or item.get("active_window") or "PC event", "details": json.dumps(item, default=str)[:1000], "metadata": item} for item in items]


def _normalize_events(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"timestamp": item.get("timestamp", ""), "event_type": item.get("event_type", "event"), "title": item.get("title") or item.get("summary") or "Friday event", "details": item.get("details") or item.get("summary") or "", "metadata": item} for item in items]


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "event_type": str(row["event_type"]),
        "title": str(row["title"]),
        "details": str(row["details"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _parse_time(value: Any) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
    except Exception:
        return None


def _terms(value: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9_]+", str(value or "").lower()) if len(part) > 2}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

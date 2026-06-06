"""Trace spine for Friday runs, gates, tools, and proof artifacts.

This is intentionally OpenTelemetry-shaped without requiring a collector. Every
run can carry a trace_id now; exporting to LangSmith/OpenTelemetry later becomes
a transport decision instead of another data-model rewrite.
"""

from __future__ import annotations

import datetime as dt
import json
import secrets
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "friday_traces.sqlite3"
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
            CREATE TABLE IF NOT EXISTS traces (
                trace_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                root TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trace_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                status TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                FOREIGN KEY(trace_id) REFERENCES traces(trace_id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_events_trace ON trace_events(trace_id, id)")


def new_trace_id(prefix: str = "trace") -> str:
    clean_prefix = _clean(prefix).lower().replace(" ", "_") or "trace"
    return f"{clean_prefix}-{secrets.token_hex(16)}"


def ensure_trace_id(metadata: dict[str, Any] | None = None, *, prefix: str = "trace") -> tuple[str, dict[str, Any]]:
    merged = dict(metadata or {})
    trace_id = _clean(merged.get("trace_id") or "") or new_trace_id(prefix)
    merged["trace_id"] = trace_id
    return trace_id, merged


def start_trace(
    trace_id: str,
    *,
    kind: str,
    title: str,
    root: str | Path = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO traces(trace_id, created_at, updated_at, kind, title, root, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trace_id) DO UPDATE SET
                updated_at=excluded.updated_at,
                kind=excluded.kind,
                title=excluded.title,
                root=excluded.root,
                metadata_json=excluded.metadata_json
            """,
            (trace_id, now, now, _clean(kind), _clean(title), str(root or ""), _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM traces WHERE trace_id=?", (trace_id,)).fetchone()
    return _trace_row(row)


def record_event(
    trace_id: str,
    *,
    event_type: str,
    title: str,
    summary: str = "",
    status: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not _clean(trace_id):
        trace_id = new_trace_id()
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE traces SET updated_at=? WHERE trace_id=?", (_now(), trace_id))
        cursor = conn.execute(
            """
            INSERT INTO trace_events(trace_id, timestamp, event_type, status, title, summary, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (trace_id, _now(), _clean(event_type), _clean(status), _clean(title), _clean(summary), _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM trace_events WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _event_row(row)


def get_trace(trace_id: str) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM traces WHERE trace_id=?", (_clean(trace_id),)).fetchone()
        if not row:
            return None
        events = conn.execute("SELECT * FROM trace_events WHERE trace_id=? ORDER BY id ASC", (_clean(trace_id),)).fetchall()
    trace = _trace_row(row)
    trace["events"] = [_event_row(event) for event in events]
    return trace


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM traces ORDER BY updated_at DESC LIMIT ?", (max(1, min(200, int(limit or 20))),)).fetchall()
    return [_trace_row(row) for row in rows]


def _trace_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "trace_id": str(row["trace_id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "kind": str(row["kind"]),
        "title": str(row["title"]),
        "root": str(row["root"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _event_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "trace_id": str(row["trace_id"]),
        "timestamp": str(row["timestamp"]),
        "event_type": str(row["event_type"]),
        "status": str(row["status"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return fallback


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

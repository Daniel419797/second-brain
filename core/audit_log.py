"""SQLite audit log for actions that affect the real machine or network."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "audit_log.sqlite3"
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
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                actor TEXT NOT NULL,
                category TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT NOT NULL,
                success INTEGER NOT NULL,
                details_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_events(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_category ON audit_events(category, action)")


def record(
    *,
    actor: str = "friday",
    category: str,
    action: str,
    target: str = "",
    success: bool = True,
    details: dict[str, Any] | None = None,
) -> int:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO audit_events (timestamp, actor, category, action, target, success, details_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _now(),
                _clean(actor) or "friday",
                _clean(category) or "general",
                _clean(action) or "action",
                _clean(target),
                1 if success else 0,
                _json_dumps(details or {}),
            ),
        )
        return int(cursor.lastrowid)


def recent(limit: int = 100, *, category: str | None = None) -> list[dict[str, Any]]:
    init_db()
    where = ""
    params: list[Any] = []
    if category:
        where = "WHERE category = ?"
        params.append(category)
    params.append(max(1, int(limit)))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM audit_events {where} ORDER BY timestamp DESC, id DESC LIMIT ?",
            params,
        )
        return [_row_to_event(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM audit_events")


def _row_to_event(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "actor": str(row["actor"]),
        "category": str(row["category"]),
        "action": str(row["action"]),
        "target": str(row["target"]),
        "success": bool(row["success"]),
        "details": _json_loads(row["details_json"]),
    }


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=True)


def _json_loads(value: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return value


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

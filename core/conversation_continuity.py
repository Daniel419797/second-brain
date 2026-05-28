"""Open-thread memory for conversations and unfinished work."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import continuity_brain, personal_knowledge_vault
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "conversation_continuity.sqlite3"
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
            CREATE TABLE IF NOT EXISTS continuity_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                status TEXT NOT NULL,
                last_blocker TEXT NOT NULL,
                source TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_continuity_status ON continuity_threads(status, updated_at)")


def capture(
    title: str,
    *,
    summary: str = "",
    blocker: str = "",
    evidence: list[str] | str | None = None,
    source: str = "conversation",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    clean_title = _clean(title) or "Open thread"
    clean_summary = _clean(summary) or clean_title
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO continuity_threads(created_at, updated_at, title, summary, status, last_blocker, source, evidence_json, metadata_json)
            VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?)
            """,
            (now, now, clean_title[:300], clean_summary[:2000], _clean(blocker)[:1000], _clean(source)[:120] or "conversation", _json_dumps(_list(evidence)), _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM continuity_threads WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    item = _row(row)
    _safe(lambda: personal_knowledge_vault.remember("continuity", item["title"], item["summary"], confidence=0.78, tags=["conversation_continuity"], metadata={"thread_id": item["id"], "blocker": item["last_blocker"]}), None)
    _safe(lambda: continuity_brain.capture_current_state(note=item["summary"]), None)
    return item


def open_threads(limit: int = 10) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM continuity_threads WHERE status='open' ORDER BY updated_at DESC LIMIT ?",
            (max(1, min(100, int(limit or 10))),),
        ).fetchall()
    return [_row(row) for row in rows]


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM continuity_threads ORDER BY updated_at DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def remind(limit: int = 5) -> dict[str, Any]:
    threads = open_threads(limit=limit)
    if not threads:
        return {"threads": [], "summary": "No unfinished conversation threads are currently open."}
    first = threads[0]
    summary = f"We still have {len(threads)} open thread(s). Most recent: {first['title']}. {first['summary']}"
    return {"threads": threads, "summary": summary}


def resolve(thread_id: int, *, note: str = "") -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            "UPDATE continuity_threads SET status='resolved', updated_at=?, summary=summary || ? WHERE id=?",
            (_now(), f" Resolved: {_clean(note)}" if note else " Resolved.", int(thread_id)),
        )
        row = conn.execute("SELECT * FROM continuity_threads WHERE id=?", (int(thread_id),)).fetchone()
    return {"resolved": bool(row), "thread": _row(row) if row else None}


def status() -> dict[str, Any]:
    threads = open_threads(limit=8)
    legacy = _safe(lambda: continuity_brain.status(), {})
    return {"open": threads, "legacy": legacy, "summary": remind(limit=5)["summary"]}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM continuity_threads")


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "status": str(row["status"]),
        "last_blocker": str(row["last_blocker"]),
        "source": str(row["source"]),
        "evidence": _json_loads(row["evidence_json"], []),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _list(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    return [_clean(item) for item in value if _clean(item)]


def _safe(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

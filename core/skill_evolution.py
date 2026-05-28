"""Detect repeated workflows and suggest reusable skills."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import personal_command_memory
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "skill_evolution.sqlite3"
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
            CREATE TABLE IF NOT EXISTS workflow_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                signature TEXT NOT NULL,
                description TEXT NOT NULL,
                count INTEGER NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS skill_suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                signature TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                status TEXT NOT NULL,
                confidence REAL NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_workflow_signature ON workflow_observations(signature)")


def observe_workflow(signature: str, description: str = "", *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    sig = _normalize(signature)
    if not sig:
        return {"ok": False, "summary": "Workflow signature is required."}
    desc = _clean(description) or signature
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        current = conn.execute("SELECT * FROM workflow_observations WHERE signature=? ORDER BY id DESC LIMIT 1", (sig,)).fetchone()
        count = int(current["count"]) + 1 if current else 1
        conn.execute(
            "INSERT INTO workflow_observations(timestamp, signature, description, count, metadata_json) VALUES (?, ?, ?, ?, ?)",
            (now, sig, desc, count, _json_dumps(metadata or {})),
        )
    suggestion = _maybe_suggest(sig, desc, count, metadata or {})
    return {"ok": True, "signature": sig, "count": count, "suggestion": suggestion, "summary": suggestion.get("summary") if suggestion else f"Workflow observed {count} time(s)."}


def suggest_from_patterns() -> dict[str, Any]:
    created = []
    try:
        for item in personal_command_memory.list_commands(limit=50):
            if int(item.get("success_count") or 0) >= 2:
                created.append(_maybe_suggest(_normalize(item["canonical_command"]), item["canonical_command"], int(item["success_count"]), {"source": "personal_command_memory", "command": item}))
    except Exception:
        pass
    return {"created": [item for item in created if item], "suggestions": suggestions(limit=20), "summary": "Skill evolution suggestions refreshed."}


def suggestions(limit: int = 20, *, status: str = "open") -> list[dict[str, Any]]:
    init_db()
    where = "WHERE status=?" if status else ""
    params: list[Any] = [status] if status else []
    params.append(max(1, min(100, int(limit or 20))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM skill_suggestions {where} ORDER BY confidence DESC, updated_at DESC LIMIT ?", params).fetchall()
    return [_row(row) for row in rows]


def resolve_suggestion(suggestion_id: int, status: str = "accepted") -> dict[str, Any]:
    init_db()
    normalized = status if status in {"accepted", "dismissed", "open"} else "accepted"
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE skill_suggestions SET status=?, updated_at=? WHERE id=?", (normalized, _now(), int(suggestion_id)))
        row = conn.execute("SELECT * FROM skill_suggestions WHERE id=?", (int(suggestion_id),)).fetchone()
    return _row(row) if row else {"ok": False, "summary": "Skill suggestion not found."}


def status() -> dict[str, Any]:
    items = suggestions(limit=8)
    return {"open_count": len(suggestions(limit=100)), "suggestions": items, "summary": f"{len(items)} skill evolution suggestion(s)." if items else "No repeated workflow suggestions yet."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM workflow_observations")
        conn.execute("DELETE FROM skill_suggestions")


def _maybe_suggest(signature: str, description: str, count: int, metadata: dict[str, Any]) -> dict[str, Any] | None:
    if count < 3:
        return None
    now = _now()
    title = f"Save workflow: {description[:80]}"
    summary = f"You have done '{description}' {count} time(s). Friday can save it as a reusable skill."
    confidence = min(0.95, 0.55 + count * 0.1)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO skill_suggestions(created_at, updated_at, signature, title, summary, status, confidence, metadata_json)
            VALUES (?, ?, ?, ?, ?, 'open', ?, ?)
            ON CONFLICT(signature) DO UPDATE SET updated_at=excluded.updated_at, summary=excluded.summary, confidence=max(skill_suggestions.confidence, excluded.confidence)
            """,
            (now, now, signature, title, summary, confidence, _json_dumps({"count": count, **metadata})),
        )
        row = conn.execute("SELECT * FROM skill_suggestions WHERE signature=?", (signature,)).fetchone()
    return _row(row)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "signature": str(row["signature"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "status": str(row["status"]),
        "confidence": float(row["confidence"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _normalize(value: str) -> str:
    return " ".join(_clean(value).lower().split())


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

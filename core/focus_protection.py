"""Attention guard for batching low-value interruptions while the user works."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import context_aware_silence, notification_center
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "focus_protection.sqlite3"
_LOCK = threading.Lock()

MODE_MAP = {
    "normal": ("normal", 2),
    "focus": ("coding", 4),
    "deep_work": ("coding", 4),
    "coding": ("coding", 4),
    "debugging": ("debugging", 3),
    "study": ("study", 2),
    "silent": ("silent_operator", 5),
    "silent_operator": ("silent_operator", 5),
    "gaming": ("gaming", 5),
    "movie": ("movie", 5),
}


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
            CREATE TABLE IF NOT EXISTS focus_state (
                id INTEGER PRIMARY KEY CHECK (id=1),
                mode TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                reason TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS focus_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                category TEXT NOT NULL,
                severity INTEGER NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO focus_state(id, mode, updated_at, reason, metadata_json) VALUES (1, 'normal', ?, 'default', '{}')",
            (_now(),),
        )


def set_mode(mode: str, *, reason: str = "manual", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    normalized = _normalize_mode(mode)
    silence_mode, _threshold = MODE_MAP[normalized]
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            "UPDATE focus_state SET mode=?, updated_at=?, reason=?, metadata_json=? WHERE id=1",
            (normalized, now, _clean(reason), _json_dumps(metadata or {})),
        )
    _safe(lambda: context_aware_silence.set_mode(silence_mode, reason=f"focus_protection:{reason}", metadata={"focus_mode": normalized, **(metadata or {})}), None)
    return status()


def protect_now(reason: str = "user requested focus") -> dict[str, Any]:
    return set_mode("focus", reason=reason)


def current() -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM focus_state WHERE id=1").fetchone()
    mode = str(row["mode"]) if row else "normal"
    silence_mode, threshold = MODE_MAP.get(mode, MODE_MAP["normal"])
    return {
        "mode": mode,
        "silence_mode": silence_mode,
        "threshold": threshold,
        "updated_at": str(row["updated_at"]) if row else "",
        "reason": str(row["reason"]) if row else "default",
        "metadata": _json_loads(str(row["metadata_json"]), {}) if row else {},
    }


def should_interrupt(severity: int, *, category: str = "", explicit: bool = False) -> dict[str, Any]:
    state = current()
    allowed = bool(explicit or int(severity or 0) >= int(state["threshold"]))
    return {
        "allowed": allowed,
        "mode": state["mode"],
        "threshold": state["threshold"],
        "category": _clean(category),
        "reason": "explicit user request" if explicit else f"severity {int(severity or 0)} vs threshold {state['threshold']}",
    }


def evaluate_notification(
    *,
    title: str,
    message: str,
    severity: int = 2,
    category: str = "general",
    metadata: dict[str, Any] | None = None,
    explicit: bool = False,
) -> dict[str, Any]:
    decision = should_interrupt(severity, category=category, explicit=explicit)
    if decision["allowed"]:
        note = notification_center.add(
            source="focus_protection",
            category=category or "general",
            severity=severity,
            title=title or "Friday alert",
            message=message or title or "Friday has an update.",
            metadata={"focus_decision": decision, **(metadata or {})},
        )
        return {"decision": "deliver", "notification": note, "focus": decision, "summary": f"Delivered: {note['title']}"}
    item = _queue(category, severity, title, message, metadata or {})
    return {"decision": "batched", "item": item, "focus": decision, "summary": f"Batched low-priority alert: {item['title']}"}


def queue(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM focus_queue WHERE status='batched' ORDER BY severity DESC, id DESC LIMIT ?",
            (max(1, min(100, int(limit or 20))),),
        ).fetchall()
    return [_row(row) for row in rows]


def flush(limit: int = 50) -> dict[str, Any]:
    items = queue(limit=limit)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE focus_queue SET status='released' WHERE status='batched'")
    for item in items:
        _safe(
            lambda item=item: notification_center.add(
                source="focus_protection",
                category=item["category"],
                severity=item["severity"],
                title=item["title"],
                message=item["message"],
                metadata={"released_from_focus_queue": True, "item": item},
            ),
            None,
        )
    return {"released": items, "summary": f"Released {len(items)} batched focus alert(s)."}


def next_action() -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for producer in (
        lambda: _safe(lambda: __import__("core.os_autopilot", fromlist=["recommendation"]).recommendation(), {}),
        lambda: _safe(lambda: __import__("core.goal_manager", fromlist=["next_goal_action"]).next_goal_action(), {}),
    ):
        item = producer()
        if isinstance(item, dict) and item:
            candidates.append(item)
    summary = "Keep one clear next action in front of you."
    if candidates:
        summary = str(candidates[0].get("summary") or candidates[0].get("next_action") or summary)
    return {"candidates": candidates, "summary": summary}


def status() -> dict[str, Any]:
    state = current()
    batched = queue(limit=10)
    return {
        "current": state,
        "batched": batched,
        "next_action": next_action(),
        "summary": f"Focus mode {state['mode']}; {len(batched)} batched alert(s).",
    }


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM focus_queue")
        conn.execute("DELETE FROM focus_state")
        conn.execute("INSERT INTO focus_state(id, mode, updated_at, reason, metadata_json) VALUES (1, 'normal', ?, 'default', '{}')", (_now(),))


def _queue(category: str, severity: int, title: str, message: str, metadata: dict[str, Any]) -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO focus_queue(timestamp, category, severity, title, message, status, metadata_json) VALUES (?, ?, ?, ?, ?, 'batched', ?)",
            (_now(), _clean(category) or "general", max(1, min(5, int(severity or 1))), _clean(title)[:300] or "Friday update", _clean(message)[:2000], _json_dumps(metadata)),
        )
        row = conn.execute("SELECT * FROM focus_queue WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "category": str(row["category"]),
        "severity": int(row["severity"]),
        "title": str(row["title"]),
        "message": str(row["message"]),
        "status": str(row["status"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _normalize_mode(mode: str) -> str:
    normalized = _clean(mode).lower().replace(" ", "_") or "normal"
    if normalized not in MODE_MAP:
        normalized = "focus"
    return normalized


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

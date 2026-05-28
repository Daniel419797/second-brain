"""Context-aware speaking policy for Friday."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "context_aware_silence.sqlite3"
_LOCK = threading.Lock()

MODES = {
    "normal": {"threshold": 2, "style": "balanced", "summary": "Friday may speak for useful updates and questions."},
    "coding": {"threshold": 4, "style": "brief/evidence-heavy", "summary": "Only interrupt for blockers, failures, security, battery, or explicit questions."},
    "debugging": {"threshold": 3, "style": "concise and proof-first", "summary": "Speak for failures, evidence, next checks, and direct answers."},
    "study": {"threshold": 2, "style": "teacher", "summary": "Coach more, ask gentle checks, and use examples."},
    "silent_operator": {"threshold": 5, "style": "quiet", "summary": "Do not speak unless safety-critical or explicitly asked."},
    "gaming": {"threshold": 5, "style": "quiet", "summary": "Stay quiet except urgent alerts."},
    "movie": {"threshold": 5, "style": "quiet", "summary": "Stay quiet except urgent alerts."},
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
            CREATE TABLE IF NOT EXISTS silence_state (
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
            CREATE TABLE IF NOT EXISTS silence_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                mode TEXT NOT NULL,
                event_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO silence_state(id, mode, updated_at, reason, metadata_json) VALUES (1, 'normal', ?, 'default', '{}')",
            (_now(),),
        )


def set_mode(mode: str, *, reason: str = "manual", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    normalized = str(mode or "").strip().lower().replace(" ", "_")
    if normalized not in MODES:
        return {"ok": False, "summary": f"Unknown silence mode. Try: {', '.join(MODES)}."}
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE silence_state SET mode=?, updated_at=?, reason=?, metadata_json=? WHERE id=1", (normalized, now, _clean(reason), _json_dumps(metadata or {})))
        conn.execute(
            "INSERT INTO silence_events(timestamp, mode, event_type, summary, metadata_json) VALUES (?, ?, 'mode', ?, ?)",
            (now, normalized, f"Silence mode set to {normalized}.", _json_dumps(metadata or {})),
        )
    return current()


def current() -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM silence_state WHERE id=1").fetchone()
    mode = str(row["mode"]) if row else "normal"
    rule = MODES.get(mode, MODES["normal"])
    return {
        "mode": mode,
        "updated_at": str(row["updated_at"]) if row else "",
        "reason": str(row["reason"]) if row else "default",
        "threshold": int(rule["threshold"]),
        "style": str(rule["style"]),
        "summary": str(rule["summary"]),
        "metadata": _json_loads(row["metadata_json"], {}) if row else {},
    }


def should_interrupt(severity: int, *, category: str = "", explicit_user_question: bool = False) -> dict[str, Any]:
    state = current()
    allowed = bool(explicit_user_question or int(severity) >= int(state["threshold"]))
    reason = "explicit user question" if explicit_user_question else f"severity {severity} vs threshold {state['threshold']}"
    return {"allowed": allowed, "mode": state["mode"], "style": state["style"], "reason": reason, "category": category}


def summary() -> dict[str, Any]:
    state = current()
    return {"current": state, "modes": MODES, "summary": f"Silence mode: {state['mode']}. {state['summary']}"}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM silence_events")
        conn.execute("DELETE FROM silence_state")
        conn.execute("INSERT INTO silence_state(id, mode, updated_at, reason, metadata_json) VALUES (1, 'normal', ?, 'default', '{}')", (_now(),))


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

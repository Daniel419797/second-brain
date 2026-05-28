"""Goal and operational regulation state for Friday."""

from __future__ import annotations

import datetime as dt
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import cognitive_state
from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "goal_regulation.sqlite3"
VALID_GOAL_STATUSES = {"active", "blocked", "paused", "done", "cancelled"}
VALID_STATES = {"calm", "focused", "uncertain", "blocked", "overloaded", "recovering", "waiting_for_user"}
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
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                priority INTEGER NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deadline_at TEXT NOT NULL,
                progress REAL NOT NULL,
                parent_id INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS goal_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                details_json TEXT NOT NULL,
                FOREIGN KEY(goal_id) REFERENCES goals(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS affective_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                state TEXT NOT NULL,
                arousal REAL NOT NULL,
                confidence REAL NOT NULL,
                frustration REAL NOT NULL,
                focus REAL NOT NULL,
                reason TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_goals_status_priority ON goals(status, priority, updated_at)")


def create_goal(title: str, description: str = "", priority: int = 5, source: str = "user", deadline_at: str = "", parent_id: int | None = None) -> int:
    init_db()
    cleaned = _clean(title)
    if not cleaned:
        raise ValueError("Goal title is empty.")
    now = cognitive_state.now_iso()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO goals(title, description, status, priority, source, created_at, updated_at, deadline_at, progress, parent_id)
            VALUES (?, ?, 'active', ?, ?, ?, ?, ?, 0.0, ?)
            """,
            (_clean(title), _clean(description), int(priority), _clean(source) or "user", now, now, _clean(deadline_at), parent_id),
        )
        goal_id = int(cursor.lastrowid)
    record_goal_event(goal_id, "created", {"title": title, "source": source})
    return goal_id


def update_goal(goal_id: int, *, status: str | None = None, progress: float | None = None, note: str = "") -> dict[str, Any]:
    init_db()
    goal = get_goal(goal_id)
    if not goal:
        raise ValueError(f"Goal {goal_id} not found.")
    updates = ["updated_at=?"]
    params: list[Any] = [cognitive_state.now_iso()]
    if status is not None:
        normalized = _normalize_status(status)
        updates.append("status=?")
        params.append(normalized)
    if progress is not None:
        updates.append("progress=?")
        params.append(cognitive_state.clamp01(progress, default=float(goal.get("progress") or 0.0)))
    params.append(int(goal_id))
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(f"UPDATE goals SET {', '.join(updates)} WHERE id=?", params)
    record_goal_event(goal_id, "updated", {"status": status, "progress": progress, "note": note})
    return get_goal(goal_id) or {}


def active_goals(limit: int = 10) -> list[dict[str, Any]]:
    return list_goals(status="active", limit=limit)


def list_goals(status: str = "", limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    where = ""
    params: list[Any] = []
    if status:
        where = "WHERE status=?"
        params.append(_normalize_status(status))
    params.append(max(1, min(200, int(limit))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM goals {where} ORDER BY priority ASC, updated_at DESC, id DESC LIMIT ?",
            params,
        ).fetchall()
    return [_goal_from_row(row) for row in rows]


def get_goal(goal_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM goals WHERE id=?", (int(goal_id),)).fetchone()
    return _goal_from_row(row) if row else None


def record_goal_event(goal_id: int, event_type: str, details: dict[str, Any] | None = None) -> int:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            "INSERT INTO goal_events(goal_id, timestamp, event_type, details_json) VALUES (?, ?, ?, ?)",
            (int(goal_id), cognitive_state.now_iso(), _clean(event_type), cognitive_state.to_json(details or {})),
        )
        return int(cursor.lastrowid)


def set_affective_state(
    state: str,
    reason: str = "",
    *,
    confidence: float = 0.6,
    arousal: float | None = None,
    frustration: float | None = None,
    focus: float | None = None,
) -> dict[str, Any]:
    init_db()
    normalized = _normalize_state(state)
    defaults = _state_defaults(normalized)
    item = cognitive_state.AffectiveState(
        state=normalized,
        arousal=cognitive_state.clamp01(arousal if arousal is not None else defaults["arousal"]),
        confidence=cognitive_state.clamp01(confidence),
        frustration=cognitive_state.clamp01(frustration if frustration is not None else defaults["frustration"]),
        focus=cognitive_state.clamp01(focus if focus is not None else defaults["focus"]),
        reason=_clean(reason),
    )
    now = cognitive_state.now_iso()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO affective_state(timestamp, state, arousal, confidence, frustration, focus, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (now, item.state, item.arousal, item.confidence, item.frustration, item.focus, item.reason),
        )
        state_id = int(cursor.lastrowid)
    result = cognitive_state.to_dict(item)
    result["id"] = state_id
    result["timestamp"] = now
    return result


def current_regulation() -> dict[str, Any]:
    init_db()
    state = _latest_affective_state()
    if not state:
        state = set_affective_state(str(config_value("goal_regulation_default_state", "calm")), "default state", confidence=0.5)
    return {"state": state, "active_goals": active_goals(limit=5), "blocked_goals": list_goals(status="blocked", limit=5)}


def regulation_prompt_context() -> str:
    regulation = current_regulation()
    state = regulation.get("state") or {}
    goals = regulation.get("active_goals") or []
    goal_text = "; ".join(f"#{goal['id']} {goal['title']} ({goal['progress']:.0%})" for goal in goals[:3])
    return f"Operational state: {state.get('state')} because {state.get('reason') or 'normal operation'}. Active goals: {goal_text or 'none'}."


def infer_state_from_feedback(text: str) -> dict[str, Any] | None:
    lowered = str(text or "").lower()
    if any(term in lowered for term in ["you lied", "still lied", "didn't work", "did not work", "wrong"]):
        return set_affective_state("recovering", "user reported a failed or unverified action", confidence=0.8, frustration=0.4, focus=0.8)
    if any(term in lowered for term in ["confused", "not accurate", "i said"]):
        return set_affective_state("uncertain", "user corrected Friday's understanding", confidence=0.75, frustration=0.2, focus=0.7)
    return None


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM goal_events")
        conn.execute("DELETE FROM goals")
        conn.execute("DELETE FROM affective_state")


def _latest_affective_state() -> dict[str, Any] | None:
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM affective_state ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "state": str(row["state"]),
        "arousal": float(row["arousal"]),
        "confidence": float(row["confidence"]),
        "frustration": float(row["frustration"]),
        "focus": float(row["focus"]),
        "reason": str(row["reason"]),
    }


def _goal_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "title": str(row["title"]),
        "description": str(row["description"]),
        "status": str(row["status"]),
        "priority": int(row["priority"]),
        "source": str(row["source"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "deadline_at": str(row["deadline_at"]),
        "progress": float(row["progress"]),
        "parent_id": row["parent_id"],
    }


def _normalize_status(status: str) -> str:
    value = _clean(status).lower()
    return value if value in VALID_GOAL_STATUSES else "active"


def _normalize_state(state: str) -> str:
    value = _clean(state).lower()
    return value if value in VALID_STATES else "calm"


def _state_defaults(state: str) -> dict[str, float]:
    return {
        "calm": {"arousal": 0.2, "frustration": 0.0, "focus": 0.5},
        "focused": {"arousal": 0.4, "frustration": 0.0, "focus": 0.9},
        "uncertain": {"arousal": 0.45, "frustration": 0.15, "focus": 0.7},
        "blocked": {"arousal": 0.5, "frustration": 0.25, "focus": 0.6},
        "overloaded": {"arousal": 0.85, "frustration": 0.45, "focus": 0.3},
        "recovering": {"arousal": 0.55, "frustration": 0.3, "focus": 0.85},
        "waiting_for_user": {"arousal": 0.25, "frustration": 0.0, "focus": 0.4},
    }.get(state, {"arousal": 0.2, "frustration": 0.0, "focus": 0.5})


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())

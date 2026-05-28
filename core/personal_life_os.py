"""Personal Life OS: routines, follow-ups, planning, and summaries."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import app_integrations, capability_center, goal_regulation
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "personal_life_os.sqlite3"
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
            CREATE TABLE IF NOT EXISTS routines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                cadence TEXT NOT NULL,
                next_due_at TEXT NOT NULL,
                notes TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mood_energy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                mood TEXT NOT NULL,
                energy INTEGER NOT NULL,
                notes TEXT NOT NULL
            )
            """
        )


def daily_plan() -> dict[str, Any]:
    brief = capability_center.personal_brief()
    routines = due_routines(limit=8)
    missed = missed_followups(limit=8)
    mood = latest_mood()
    blocks = [
        {"title": "First focus", "items": [brief["next_action"]["title"]]},
        {"title": "Follow-ups", "items": [item["title"] for item in missed[:3]] or ["No missed follow-ups detected."]},
        {"title": "Routines", "items": [item["title"] for item in routines[:3]] or ["No routines due."]},
    ]
    if mood:
        blocks.append({"title": "Energy fit", "items": [_energy_advice(mood)]})
    return {"generated_at": _now(), "brief": brief, "routines_due": routines, "missed_followups": missed, "mood": mood, "blocks": blocks, "summary": f"Plan ready: {brief['next_action']['title']}."}


def what_should_i_do_next() -> dict[str, Any]:
    plan = daily_plan()
    item = plan["brief"]["next_action"]
    if plan["missed_followups"]:
        item = {"kind": "followup", "title": plan["missed_followups"][0]["title"], "reason": "This follow-up appears missed or overdue."}
    return item | {"summary": f"Next: {item.get('title')}."}


def create_routine(title: str, *, cadence: str = "daily", next_due_at: str = "", notes: str = "") -> dict[str, Any]:
    init_db()
    now = _now()
    due = next_due_at or _next_due(cadence)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO routines(title, cadence, next_due_at, notes, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'active', ?, ?)",
            (_clean(title), _clean(cadence) or "daily", due, _clean(notes), now, now),
        )
        row = conn.execute("SELECT * FROM routines WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def due_routines(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    now = _now()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM routines WHERE status='active' AND (next_due_at='' OR next_due_at<=?) ORDER BY next_due_at, id DESC LIMIT ?",
            (now, max(1, min(100, int(limit)))),
        ).fetchall()
    return [_row(row) for row in rows]


def complete_routine(routine_id: int) -> dict[str, Any] | None:
    routine = get_routine(routine_id)
    if not routine:
        return None
    next_due = _next_due(routine.get("cadence") or "daily")
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE routines SET next_due_at=?, updated_at=? WHERE id=?", (next_due, _now(), int(routine_id)))
    return get_routine(routine_id)


def get_routine(routine_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM routines WHERE id=?", (int(routine_id),)).fetchone()
    return _row(row) if row else None


def set_mood(mood: str, energy: int = 5, notes: str = "") -> dict[str, Any]:
    init_db()
    energy_value = max(1, min(10, int(energy or 5)))
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO mood_energy(timestamp, mood, energy, notes) VALUES (?, ?, ?, ?)",
            (_now(), _clean(mood) or "neutral", energy_value, _clean(notes)),
        )
        row = conn.execute("SELECT * FROM mood_energy WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def latest_mood() -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM mood_energy ORDER BY id DESC LIMIT 1").fetchone()
    return _row(row) if row else None


def missed_followups(limit: int = 20) -> list[dict[str, Any]]:
    reminders = app_integrations.list_reminders(limit=100)
    missed = []
    now = dt.datetime.now().astimezone()
    for reminder in reminders:
        due_at = _parse_time(reminder.get("due_at"))
        if due_at and due_at < now and reminder.get("status") == "active":
            missed.append(reminder | {"missed_by_minutes": int((now - due_at).total_seconds() // 60)})
    return missed[: max(1, min(100, int(limit)))]


def end_of_day_summary() -> dict[str, Any]:
    plan = daily_plan()
    regulation = goal_regulation.current_regulation()
    return {
        "generated_at": _now(),
        "completed_hint": "Review completed tasks in the task board and mark any reminders done.",
        "missed_followups": plan["missed_followups"],
        "goals": regulation.get("active_goals", []),
        "summary": f"End-of-day check: {len(plan['missed_followups'])} missed follow-ups, {len(regulation.get('active_goals', []))} active goals.",
    }


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM routines")
        conn.execute("DELETE FROM mood_energy")


def _next_due(cadence: str) -> str:
    now = dt.datetime.now().astimezone()
    lowered = _clean(cadence).lower()
    if lowered == "weekly":
        delta = dt.timedelta(days=7)
    elif lowered == "monthly":
        delta = dt.timedelta(days=30)
    else:
        delta = dt.timedelta(days=1)
    return (now + delta).replace(hour=9, minute=0, second=0, microsecond=0).isoformat(timespec="minutes")


def _parse_time(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
    except Exception:
        return None


def _energy_advice(mood: dict[str, Any]) -> str:
    energy = int(mood.get("energy") or 5)
    if energy <= 3:
        return "Low energy: choose a small admin task or one short focused block."
    if energy >= 8:
        return "High energy: use this for coding, planning, or hard decisions."
    return "Medium energy: pick one clear task and avoid context switching."


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

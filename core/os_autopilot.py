"""Personal operating system autopilot for work rhythm and next-action guidance."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import context_aware_silence, goal_manager, operating_rhythm, pc_timeline, task_queue
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "os_autopilot.sqlite3"
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
            CREATE TABLE IF NOT EXISTS os_autopilot_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                kind TEXT NOT NULL,
                summary TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS os_autopilot_recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                mode TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                evidence_json TEXT NOT NULL
            )
            """
        )


def recommendation() -> dict[str, Any]:
    init_db()
    rhythm = operating_rhythm.summary()
    goals = goal_manager.progress_summary(limit=5)
    tasks = task_queue.counts()
    timeline = pc_timeline.summary()
    hour = dt.datetime.now().astimezone().hour
    mode = _mode(hour, tasks, rhythm)
    text = _recommendation_text(mode, tasks, goals)
    silence = context_aware_silence.set_mode("debugging" if mode == "debug" else "coding" if mode == "coding" else "normal", reason="os_autopilot")
    evidence = {"rhythm": rhythm, "goals": goals, "task_counts": tasks, "timeline": timeline, "silence": silence}
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO os_autopilot_recommendations(timestamp, mode, recommendation, evidence_json) VALUES (?, ?, ?, ?)",
            (_now(), mode, text, _json_dumps(evidence)),
        )
        row = conn.execute("SELECT * FROM os_autopilot_recommendations WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _recommendation_row(row)


def record_signal(kind: str, summary: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO os_autopilot_signals(timestamp, kind, summary, metadata_json) VALUES (?, ?, ?, ?)",
            (_now(), _clean(kind) or "signal", _clean(summary)[:1000], _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM os_autopilot_signals WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _signal_row(row)


def status() -> dict[str, Any]:
    recommendations = recent_recommendations(limit=6)
    signals = recent_signals(limit=8)
    latest = recommendations[0] if recommendations else None
    return {
        "latest": latest,
        "signals": signals,
        "recommendations": recommendations,
        "summary": latest["recommendation"] if latest else "OS autopilot is ready to recommend what to do next.",
    }


def recent_signals(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM os_autopilot_signals ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_signal_row(row) for row in rows]


def recent_recommendations(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM os_autopilot_recommendations ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_recommendation_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM os_autopilot_signals")
        conn.execute("DELETE FROM os_autopilot_recommendations")


def _mode(hour: int, tasks: dict[str, Any], rhythm: dict[str, Any]) -> str:
    if int(tasks.get("failed") or 0) > 0:
        return "debug"
    if 9 <= hour <= 13 or 16 <= hour <= 20:
        return "coding"
    if int(tasks.get("pending") or 0) > 5:
        return "admin"
    return "planning"


def _recommendation_text(mode: str, tasks: dict[str, Any], goals: dict[str, Any]) -> str:
    if mode == "debug":
        return "This looks like a debugging block: review failed tasks first, keep replies concise, and ask for evidence."
    if mode == "coding":
        return "This is a good coding window: focus on one project task, keep agents quiet unless something important breaks."
    if mode == "admin":
        return "Clear queued admin work: reminders, pending approvals, and small tasks before starting a deep session."
    next_goal = (goals.get("next_action") or {}).get("title") if isinstance(goals, dict) else ""
    return f"Plan the next move{': ' + next_goal if next_goal else ''}. Keep Friday low-noise until you pick a goal."


def _signal_row(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": int(row["id"]), "timestamp": str(row["timestamp"]), "kind": str(row["kind"]), "summary": str(row["summary"]), "metadata": _json_loads(row["metadata_json"], {})}


def _recommendation_row(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": int(row["id"]), "timestamp": str(row["timestamp"]), "mode": str(row["mode"]), "recommendation": str(row["recommendation"]), "evidence": _json_loads(row["evidence_json"], {})}


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


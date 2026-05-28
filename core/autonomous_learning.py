"""Autonomous learning plans based on user goals and active projects."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import agent_memory, goal_manager, long_term_learning, task_queue
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "autonomous_learning.sqlite3"
_LOCK = threading.Lock()

DEFAULT_TOPICS = {
    "saas": ["auth", "billing", "dashboard UX", "deployment", "security headers"],
    "coding": ["testing", "debugging", "performance", "maintainability", "documentation"],
    "design": ["layout", "accessibility", "forms", "responsive dashboards"],
    "security": ["dependency audit", "secret scanning", "secure defaults"],
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
            CREATE TABLE IF NOT EXISTS learning_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                goal TEXT NOT NULL,
                topics_json TEXT NOT NULL,
                task_ids_json TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL
            )
            """
        )


def run_cycle(goal: str = "", *, create_tasks: bool = True) -> dict[str, Any]:
    init_db()
    target_goal = _clean(goal) or _infer_goal()
    topics = _topics_for(target_goal)
    task_ids: list[int] = []
    if create_tasks:
        for topic in topics:
            task_ids.append(
                task_queue.create_task(
                    f"Autonomous learning: {topic}",
                    description=f"Research and store reusable lessons about {topic} for the user's current goals: {target_goal}",
                    agent_id=_agent_for(topic),
                    priority=9,
                    input_data={"source": "autonomous_learning", "goal": target_goal, "topic": topic},
                )
            )
    for topic in topics:
        agent_memory.remember(_agent_for(topic), "lesson", f"Learning focus: {topic}", f"Study {topic} because it supports: {target_goal}", tags=["autonomous_learning"], confidence=0.62, source="autonomous_learning")
        long_term_learning.record_learning("learning_focus", topic, f"Friday should keep improving {topic} for goal: {target_goal}", source="autonomous_learning", confidence=0.55)
    summary = f"Autonomous learning plan created for {len(topics)} topic(s): {', '.join(topics[:5])}."
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO learning_plans(timestamp, goal, topics_json, task_ids_json, status, summary) VALUES (?, ?, ?, ?, 'active', ?)",
            (_now(), target_goal, _json_dumps(topics), _json_dumps(task_ids), summary),
        )
        row = conn.execute("SELECT * FROM learning_plans WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM learning_plans ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def summary() -> dict[str, Any]:
    plans = recent(limit=6)
    return {"plans": plans, "summary": f"{len(plans)} autonomous learning plan(s)." if plans else "No autonomous learning plan yet."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM learning_plans")


def _infer_goal() -> str:
    try:
        next_action = goal_manager.next_goal_action()
        if next_action.get("goal"):
            return str(next_action["goal"].get("title") or next_action.get("summary") or "general improvement")
        return str(next_action.get("summary") or "general improvement")
    except Exception:
        return "general improvement"


def _topics_for(goal: str) -> list[str]:
    lowered = goal.lower()
    topics: list[str] = []
    for key, values in DEFAULT_TOPICS.items():
        if key in lowered or any(word in lowered for word in values):
            topics.extend(values)
    if not topics:
        topics = DEFAULT_TOPICS["coding"] + DEFAULT_TOPICS["security"][:2]
    seen = []
    for topic in topics:
        if topic not in seen:
            seen.append(topic)
    return seen[:8]


def _agent_for(topic: str) -> str:
    lowered = topic.lower()
    if any(term in lowered for term in ("security", "secret", "audit")):
        return "cybersecurity_analyst"
    if any(term in lowered for term in ("ux", "layout", "design", "accessibility")):
        return "ui_ux_designer"
    return "research_analyst"


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "goal": str(row["goal"]),
        "topics": _json_loads(row["topics_json"], []),
        "task_ids": _json_loads(row["task_ids_json"], []),
        "status": str(row["status"]),
        "summary": str(row["summary"]),
    }


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

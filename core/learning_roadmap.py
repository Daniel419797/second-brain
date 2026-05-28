"""Personal learning roadmap: weekly plan, weak areas, quizzes, and progress."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import goal_manager, learning_coach, personal_knowledge_vault
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "learning_roadmap.sqlite3"
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
            CREATE TABLE IF NOT EXISTS learning_roadmaps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                topic TEXT NOT NULL,
                goal TEXT NOT NULL,
                status TEXT NOT NULL,
                weekly_plan_json TEXT NOT NULL,
                weak_areas_json TEXT NOT NULL,
                quiz_plan_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL
            )
            """
        )


def create(topic: str, goal: str = "", *, weeks: int = 4) -> dict[str, Any]:
    init_db()
    topic = _clean(topic) or "general learning"
    progress = _safe(learning_coach.progress, {})
    vault = _safe(personal_knowledge_vault.what_matters_this_week, {})
    goals = _safe(lambda: goal_manager.progress_summary(limit=8), {})
    weak_areas = _weak_areas(topic, progress)
    weekly_plan = [
        {
            "week": index,
            "focus": _focus_for_week(topic, weak_areas, index),
            "practice": ["short lesson", "2 examples", "quiz", "tiny project or explanation"],
        }
        for index in range(1, max(1, min(12, int(weeks or 4))) + 1)
    ]
    quiz_plan = [{"topic": area, "cadence": "every 2 days", "target_score": 0.8} for area in weak_areas[:5]]
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO learning_roadmaps(created_at, topic, goal, status, weekly_plan_json, weak_areas_json, quiz_plan_json, evidence_json) VALUES (?, ?, ?, 'active', ?, ?, ?, ?)",
            (_now(), topic, _clean(goal) or f"Improve at {topic}", _json_dumps(weekly_plan), _json_dumps(weak_areas), _json_dumps(quiz_plan), _json_dumps({"learning_progress": progress, "weekly_priorities": vault, "goals": goals})),
        )
        row = conn.execute("SELECT * FROM learning_roadmaps WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def next_quiz(topic: str = "") -> dict[str, Any]:
    roadmap = latest(topic)
    if not roadmap:
        roadmap = create(topic or "general")
    weak = (roadmap.get("weak_areas") or ["basics"])[0]
    quiz = _safe(lambda: learning_coach.quiz(weak), {})
    return {"topic": weak, "quiz": quiz, "summary": quiz.get("summary") or f"Ready to quiz {weak}."}


def latest(topic: str = "") -> dict[str, Any] | None:
    init_db()
    params: list[Any] = []
    clause = ""
    if topic:
        clause = "WHERE topic LIKE ?"
        params.append(f"%{_clean(topic)}%")
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(f"SELECT * FROM learning_roadmaps {clause} ORDER BY id DESC LIMIT 1", params).fetchone()
    return _row(row) if row else None


def status(limit: int = 6) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM learning_roadmaps ORDER BY id DESC LIMIT ?", (max(1, min(50, int(limit or 6))),)).fetchall()
    roadmaps = [_row(row) for row in rows]
    return {"roadmaps": roadmaps, "summary": f"{len(roadmaps)} learning roadmap(s) active or recent."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM learning_roadmaps")


def _weak_areas(topic: str, progress: dict[str, Any]) -> list[str]:
    weak = []
    for item in progress.get("weak_areas") or []:
        if isinstance(item, dict):
            weak.append(str(item.get("topic") or item.get("name") or ""))
        else:
            weak.append(str(item))
    if not weak:
        weak = [f"{topic} fundamentals", f"{topic} practice", f"{topic} mistakes"]
    return [item for item in weak if item][:8]


def _focus_for_week(topic: str, weak_areas: list[str], index: int) -> str:
    if weak_areas:
        return weak_areas[(index - 1) % len(weak_areas)]
    return f"{topic} week {index}"


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "topic": str(row["topic"]),
        "goal": str(row["goal"]),
        "status": str(row["status"]),
        "weekly_plan": _json_loads(row["weekly_plan_json"], []),
        "weak_areas": _json_loads(row["weak_areas_json"], []),
        "quiz_plan": _json_loads(row["quiz_plan_json"], []),
        "evidence": _json_loads(row["evidence_json"], {}),
        "summary": f"Roadmap for {row['topic']}: {len(_json_loads(row['weekly_plan_json'], []))} week(s), {len(_json_loads(row['weak_areas_json'], []))} weak area(s).",
    }


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

"""Teach Friday workflows and promote them into reusable skills."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import skill_library
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "skill_training_studio.sqlite3"
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
            CREATE TABLE IF NOT EXISTS workflows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                status TEXT NOT NULL,
                skill_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id INTEGER NOT NULL,
                step_order INTEGER NOT NULL,
                instruction TEXT NOT NULL,
                expected_result TEXT NOT NULL
            )
            """
        )


def start_workflow(name: str, *, description: str = "", agent_id: str = "jarvis", tags: list[str] | None = None) -> dict[str, Any]:
    init_db()
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO workflows(name, description, agent_id, tags_json, status, skill_id, created_at, updated_at) VALUES (?, ?, ?, ?, 'draft', '', ?, ?)",
            (_clean(name), _clean(description), _clean(agent_id) or "jarvis", _json_dumps(sorted(set(tags or []))), now, now),
        )
        row = conn.execute("SELECT * FROM workflows WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return get_workflow(int(row["id"])) or {}


def add_step(workflow_id: int, instruction: str, *, expected_result: str = "") -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        order = int(conn.execute("SELECT COALESCE(MAX(step_order), 0) + 1 FROM workflow_steps WHERE workflow_id=?", (int(workflow_id),)).fetchone()[0])
        conn.execute(
            "INSERT INTO workflow_steps(workflow_id, step_order, instruction, expected_result) VALUES (?, ?, ?, ?)",
            (int(workflow_id), order, _clean(instruction), _clean(expected_result)),
        )
        conn.execute("UPDATE workflows SET updated_at=? WHERE id=?", (_now(), int(workflow_id)))
    return get_workflow(workflow_id) or {}


def finish_workflow(workflow_id: int) -> dict[str, Any]:
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise ValueError("workflow not found")
    pattern = "\n".join(f"{step['step_order']}. {step['instruction']} -> {step['expected_result'] or 'verify before continuing'}" for step in workflow["steps"])
    skill_id = skill_library.add_skill(
        workflow["name"],
        workflow["description"] or f"Workflow taught through Skill Training Studio.",
        pattern or workflow["description"],
        agent_id=workflow["agent_id"],
        tags=workflow["tags"] + ["trained_workflow"],
        source="skill_training_studio",
    )
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE workflows SET status='published', skill_id=?, updated_at=? WHERE id=?", (skill_id, _now(), int(workflow_id)))
    return get_workflow(workflow_id) or {}


def get_workflow(workflow_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM workflows WHERE id=?", (int(workflow_id),)).fetchone()
        if row is None:
            return None
        steps = conn.execute("SELECT * FROM workflow_steps WHERE workflow_id=? ORDER BY step_order", (int(workflow_id),)).fetchall()
    return _workflow_row(row) | {"steps": [_step_row(step) for step in steps]}


def list_workflows(limit: int = 30) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM workflows ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit))),)).fetchall()
    return [get_workflow(int(row["id"])) or _workflow_row(row) for row in rows]


def summary() -> dict[str, Any]:
    workflows = list_workflows(limit=5)
    return {"workflows": workflows, "summary": f"{len(workflows)} recent taught workflow(s)."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM workflow_steps")
        conn.execute("DELETE FROM workflows")


def _workflow_row(row: sqlite3.Row) -> dict[str, Any]:
    data = {key: row[key] for key in row.keys() if key != "tags_json"}
    data["tags"] = _json_loads(row["tags_json"], [])
    return data


def _step_row(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


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

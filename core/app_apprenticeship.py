"""Record demonstrated app workflows and turn them into reusable operator skills."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import app_state_memory, skill_evolution, skill_improvement, skill_training_studio, vision_skill_learning
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "app_apprenticeship.sqlite3"
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
            CREATE TABLE IF NOT EXISTS apprenticeships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                app TEXT NOT NULL,
                workflow TEXT NOT NULL,
                goal TEXT NOT NULL,
                status TEXT NOT NULL,
                skill_workflow_id INTEGER,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS apprenticeship_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apprenticeship_id INTEGER NOT NULL,
                step_order INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                narration TEXT NOT NULL,
                action TEXT NOT NULL,
                observation TEXT NOT NULL,
                selector TEXT NOT NULL,
                screenshot TEXT NOT NULL,
                success INTEGER NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def start(app: str, workflow: str, *, goal: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    now = _now()
    clean_app = _clean(app).lower().replace(" ", "_") or "unknown_app"
    clean_workflow = _clean(workflow) or f"{clean_app} workflow"
    training = _safe(
        lambda: skill_training_studio.start_workflow(
            f"{clean_app}: {clean_workflow}",
            description=goal or "Workflow demonstrated through app apprenticeship.",
            agent_id="app_operator",
            tags=[clean_app, "app_apprenticeship"],
        ),
        {},
    )
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO apprenticeships(created_at, updated_at, app, workflow, goal, status, skill_workflow_id, metadata_json) VALUES (?, ?, ?, ?, ?, 'recording', ?, ?)",
            (now, now, clean_app, clean_workflow[:300], _clean(goal)[:1000], int(training.get("id") or 0) or None, _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM apprenticeships WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return get(int(row["id"])) or {}


def record_step(
    apprenticeship_id: int,
    narration: str,
    *,
    action: str = "",
    observation: str = "",
    selector: str = "",
    screenshot: str = "",
    success: bool = True,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    session = get(apprenticeship_id)
    if not session:
        raise ValueError("apprenticeship not found")
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        order = int(conn.execute("SELECT COALESCE(MAX(step_order), 0) + 1 FROM apprenticeship_steps WHERE apprenticeship_id=?", (int(apprenticeship_id),)).fetchone()[0])
        cursor = conn.execute(
            """
            INSERT INTO apprenticeship_steps(apprenticeship_id, step_order, timestamp, narration, action, observation, selector, screenshot, success, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(apprenticeship_id),
                order,
                _now(),
                _clean(narration)[:1000],
                _clean(action)[:1000],
                _clean(observation)[:1000],
                _clean(selector)[:500],
                _clean(screenshot)[:1000],
                1 if success else 0,
                _json_dumps(metadata or {}),
            ),
        )
        conn.execute("UPDATE apprenticeships SET updated_at=? WHERE id=?", (_now(), int(apprenticeship_id)))
        row = conn.execute("SELECT * FROM apprenticeship_steps WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    item = _step_row(row)
    _promote_step(session, item)
    return {"step": item, "apprenticeship": get(apprenticeship_id), "summary": f"Recorded step {item['step_order']} for {session['app']}."}


def finish(apprenticeship_id: int, *, publish: bool = True) -> dict[str, Any]:
    session = get(apprenticeship_id)
    if not session:
        raise ValueError("apprenticeship not found")
    skill_workflow = None
    if publish and session.get("skill_workflow_id"):
        skill_workflow = _safe(lambda: skill_training_studio.finish_workflow(int(session["skill_workflow_id"])), {})
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE apprenticeships SET status='published', updated_at=? WHERE id=?", (_now(), int(apprenticeship_id)))
    _safe(lambda: skill_evolution.observe_workflow(f"{session['app']}:{session['workflow']}", "published apprenticeship", metadata={"steps": len(session.get("steps") or [])}), None)
    updated = get(apprenticeship_id) or {}
    return {"apprenticeship": updated, "skill_workflow": skill_workflow, "summary": f"Published {session['app']} apprenticeship with {len(session.get('steps') or [])} step(s)."}


def improve_from_result(app: str, workflow: str, *, success: bool, notes: str = "", selector: str = "") -> dict[str, Any]:
    if success:
        _safe(lambda: skill_evolution.observe_workflow(f"{app}:{workflow}", notes or "successful operator run", metadata={"selector": selector}), None)
        if selector:
            _safe(lambda: app_state_memory.remember_success(app, selector, notes or workflow), None)
        return {"summary": f"Recorded successful app operator lesson for {app}."}
    return skill_improvement.record_failure(f"{app}_operator", notes or "operator run failed", context={"app": app, "workflow": workflow, "selector": selector})


def get(apprenticeship_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM apprenticeships WHERE id=?", (int(apprenticeship_id),)).fetchone()
        if not row:
            return None
        steps = conn.execute("SELECT * FROM apprenticeship_steps WHERE apprenticeship_id=? ORDER BY step_order", (int(apprenticeship_id),)).fetchall()
    return _session_row(row) | {"steps": [_step_row(step) for step in steps]}


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM apprenticeships ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [get(int(row["id"])) or _session_row(row) for row in rows]


def status() -> dict[str, Any]:
    items = recent(limit=8)
    active = [item for item in items if item.get("status") == "recording"]
    return {"recent": items, "active": active, "summary": f"{len(active)} app apprenticeship recording(s), {len(items)} recent workflow(s)."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM apprenticeship_steps")
        conn.execute("DELETE FROM apprenticeships")


def _promote_step(session: dict[str, Any], step: dict[str, Any]) -> None:
    workflow_id = int(session.get("skill_workflow_id") or 0)
    if workflow_id:
        _safe(lambda: skill_training_studio.add_step(workflow_id, step["narration"] or step["action"], expected_result=step["observation"]), None)
    if step.get("selector"):
        if step.get("success"):
            _safe(lambda: app_state_memory.remember_success(session["app"], step["selector"], step["observation"] or step["narration"]), None)
        else:
            _safe(lambda: app_state_memory.remember_failure(session["app"], step["selector"], step["observation"] or "failed demonstrated step"), None)
    if step.get("observation") or step.get("selector"):
        _safe(
            lambda: vision_skill_learning.learn_pattern(
                app=session["app"],
                label=step["narration"] or step["action"] or session["workflow"],
                pattern_type="demonstrated_step",
                visual_cues=[step["observation"]] if step["observation"] else [],
                dom_cues=[step["selector"]] if step["selector"] else [],
                meaning=session["workflow"],
                action_hint=step["action"] or step["narration"],
                confidence=0.72 if step.get("success") else 0.45,
            ),
            None,
        )


def _session_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "app": str(row["app"]),
        "workflow": str(row["workflow"]),
        "goal": str(row["goal"]),
        "status": str(row["status"]),
        "skill_workflow_id": int(row["skill_workflow_id"]) if row["skill_workflow_id"] is not None else None,
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _step_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "apprenticeship_id": int(row["apprenticeship_id"]),
        "step_order": int(row["step_order"]),
        "timestamp": str(row["timestamp"]),
        "narration": str(row["narration"]),
        "action": str(row["action"]),
        "observation": str(row["observation"]),
        "selector": str(row["selector"]),
        "screenshot": str(row["screenshot"]),
        "success": bool(row["success"]),
        "metadata": _json_loads(row["metadata_json"], {}),
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

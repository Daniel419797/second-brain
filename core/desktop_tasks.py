"""Persistent desktop task sessions for human-like app control."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "desktop_tasks.sqlite3"
_LOCK = threading.Lock()

ACTIVE_STATUSES = {"active", "paused", "waiting_confirmation"}
FINAL_STATUSES = {"completed", "stopped", "cancelled"}


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
            CREATE TABLE IF NOT EXISTS desktop_task_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal TEXT NOT NULL,
                status TEXT NOT NULL,
                current_step INTEGER NOT NULL,
                max_steps INTEGER NOT NULL,
                no_progress_count INTEGER NOT NULL,
                recovery_count INTEGER NOT NULL,
                last_signature TEXT NOT NULL,
                last_progress TEXT NOT NULL,
                pending_action_json TEXT NOT NULL,
                pending_reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS desktop_task_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                step_number INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                status TEXT NOT NULL,
                progress TEXT NOT NULL,
                action_json TEXT NOT NULL,
                result TEXT NOT NULL,
                screenshot TEXT NOT NULL,
                risk TEXT NOT NULL,
                details_json TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES desktop_task_sessions(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS desktop_ui_elements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_key TEXT NOT NULL,
                label TEXT NOT NULL,
                action TEXT NOT NULL,
                x INTEGER,
                y INTEGER,
                uses INTEGER NOT NULL,
                last_seen_at TEXT NOT NULL,
                details_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_desktop_sessions_status ON desktop_task_sessions(status, updated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_desktop_steps_session ON desktop_task_steps(session_id, step_number)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_desktop_elements_key ON desktop_ui_elements(memory_key, last_seen_at)")


def create_session(goal: str, *, max_steps: int) -> int:
    init_db()
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO desktop_task_sessions (
                goal, status, current_step, max_steps, no_progress_count, recovery_count,
                last_signature, last_progress, pending_action_json, pending_reason,
                created_at, updated_at
            )
            VALUES (?, 'active', 0, ?, 0, 0, '', '', '{}', '', ?, ?)
            """,
            (_clean(goal), int(max_steps), now, now),
        )
        session_id = int(cursor.lastrowid)
    _create_world_expectation(session_id, goal)
    return session_id


def get_session(session_id: int, *, include_steps: bool = False) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM desktop_task_sessions WHERE id=?", (int(session_id),)).fetchone()
        if row is None:
            return None
        session = _session_from_row(row)
        if include_steps:
            session["steps"] = get_steps(int(session["id"]), limit=500)
        return session


def latest_session(*, statuses: set[str] | None = None) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            row = conn.execute(
                f"SELECT * FROM desktop_task_sessions WHERE status IN ({placeholders}) ORDER BY updated_at DESC, id DESC LIMIT 1",
                tuple(statuses),
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM desktop_task_sessions ORDER BY updated_at DESC, id DESC LIMIT 1").fetchone()
        return _session_from_row(row) if row else None


def list_sessions(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM desktop_task_sessions ORDER BY updated_at DESC, id DESC LIMIT ?",
            (max(1, min(100, int(limit))),),
        ).fetchall()
        return [_session_from_row(row) for row in rows]


def get_steps(session_id: int, limit: int = 200) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM desktop_task_steps WHERE session_id=? ORDER BY step_number ASC, id ASC LIMIT ?",
            (int(session_id), max(1, min(500, int(limit)))),
        ).fetchall()
        return [_step_from_row(row) for row in rows]


def append_step(
    session_id: int,
    *,
    step_number: int,
    status: str,
    progress: str = "",
    action: dict[str, Any] | None = None,
    result: str = "",
    screenshot: str = "",
    risk: str = "",
    details: dict[str, Any] | None = None,
) -> int:
    init_db()
    now = _now()
    action = action or {}
    with _LOCK, sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO desktop_task_steps (
                session_id, step_number, timestamp, status, progress, action_json,
                result, screenshot, risk, details_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(session_id),
                int(step_number),
                now,
                _clean(status),
                _clean(progress),
                _json_dumps(action),
                _clean(result),
                _clean(screenshot),
                _clean(risk),
                _json_dumps(details or {}),
            ),
        )
        conn.execute(
            "UPDATE desktop_task_sessions SET current_step=MAX(current_step, ?), updated_at=? WHERE id=?",
            (int(step_number), now, int(session_id)),
        )
        step_id = int(cursor.lastrowid)
    _record_world_observation(session_id, step_number, status, progress, result, action, details or {})
    return step_id


def update_session(session_id: int, **fields: Any) -> None:
    if not fields:
        return
    init_db()
    allowed = {
        "status",
        "current_step",
        "max_steps",
        "no_progress_count",
        "recovery_count",
        "last_signature",
        "last_progress",
        "pending_action_json",
        "pending_reason",
        "completed_at",
    }
    updates: list[str] = []
    values: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        updates.append(f"{key}=?")
        if key.endswith("_json"):
            values.append(_json_dumps(value if isinstance(value, dict) else {}))
        else:
            values.append(_clean(value) if isinstance(value, str) else value)
    if not updates:
        return
    updates.append("updated_at=?")
    values.append(_now())
    values.append(int(session_id))
    with _LOCK, sqlite3.connect(DB_PATH) as conn:
        conn.execute(f"UPDATE desktop_task_sessions SET {', '.join(updates)} WHERE id=?", values)


def finish_session(session_id: int, status: str) -> None:
    final = status if status in FINAL_STATUSES else "stopped"
    update_session(session_id, status=final, completed_at=_now(), pending_action_json={}, pending_reason="")
    _record_world_observation(session_id, 0, final, "desktop task finished", final, {}, {})


def pause_session(session_id: int | None = None) -> dict[str, Any] | None:
    session = _target_session(session_id, statuses={"active"})
    if not session:
        return None
    update_session(int(session["id"]), status="paused")
    return get_session(int(session["id"]))


def cancel_session(session_id: int | None = None) -> dict[str, Any] | None:
    session = _target_session(session_id, statuses=ACTIVE_STATUSES)
    if not session:
        return None
    finish_session(int(session["id"]), "cancelled")
    return get_session(int(session["id"]))


def record_pending_confirmation(session_id: int, *, action: dict[str, Any], reason: str) -> None:
    update_session(
        session_id,
        status="waiting_confirmation",
        pending_action_json=action,
        pending_reason=reason,
    )


def clear_pending_confirmation(session_id: int) -> None:
    update_session(session_id, status="active", pending_action_json={}, pending_reason="")


def remember_ui_element(goal: str, plan: dict[str, Any], action: dict[str, Any]) -> None:
    action_name = str(action.get("action") or "")
    if action_name not in {"click", "double_click", "right_click", "move_mouse"}:
        return
    if action.get("x") is None or action.get("y") is None:
        return
    key = _memory_key(goal)
    label = _clean(plan.get("progress") or plan.get("reason") or action_name)[:160]
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT id, uses FROM desktop_ui_elements
            WHERE memory_key=? AND label=? AND action=?
            ORDER BY last_seen_at DESC LIMIT 1
            """,
            (key, label, action_name),
        ).fetchone()
        details = {"goal": goal, "plan": plan, "action": action}
        if row:
            conn.execute(
                """
                UPDATE desktop_ui_elements
                SET x=?, y=?, uses=?, last_seen_at=?, details_json=?
                WHERE id=?
                """,
                (
                    int(float(action["x"])),
                    int(float(action["y"])),
                    int(row[1]) + 1,
                    now,
                    _json_dumps(details),
                    int(row[0]),
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO desktop_ui_elements (memory_key, label, action, x, y, uses, last_seen_at, details_json)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    key,
                    label,
                    action_name,
                    int(float(action["x"])),
                    int(float(action["y"])),
                    now,
                    _json_dumps(details),
                ),
            )


def element_hints(goal: str, limit: int = 8) -> list[dict[str, Any]]:
    init_db()
    key = _memory_key(goal)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM desktop_ui_elements
            WHERE memory_key=?
            ORDER BY uses DESC, last_seen_at DESC LIMIT ?
            """,
            (key, max(1, min(20, int(limit)))),
        ).fetchall()
        return [_element_from_row(row) for row in rows]


def _target_session(session_id: int | None, *, statuses: set[str]) -> dict[str, Any] | None:
    if session_id:
        session = get_session(int(session_id))
        if session and session.get("status") in statuses:
            return session
        return None
    return latest_session(statuses=statuses)


def _create_world_expectation(session_id: int, goal: str) -> None:
    if not bool(config_value("desktop_task_expectations_enabled", True)):
        return
    try:
        from core import world_model

        world_model.create_expectation(
            f"desktop_task:{int(session_id)}",
            f"Desktop task should make visible progress toward: {_clean(goal)[:240]}",
            ttl_seconds=float(config_value("desktop_task_expectation_ttl_seconds", 900)),
            confidence=0.55,
        )
    except Exception:
        return


def _record_world_observation(
    session_id: int,
    step_number: int,
    status: str,
    progress: str,
    result: str,
    action: dict[str, Any],
    details: dict[str, Any],
) -> None:
    if not bool(config_value("desktop_task_world_model_enabled", True)):
        return
    progress_text = _clean(progress)
    result_text = _clean(result)
    action_name = _clean(action.get("action") if isinstance(action, dict) else "")
    observation = _clean(
        f"Desktop task {int(session_id)} step {int(step_number)} {status}. "
        f"{progress_text or result_text or action_name or 'Progress recorded.'}"
    )
    try:
        from core import world_model

        world_model.resolve_expectations(observation)
        if bool(config_value("desktop_task_world_snapshots_enabled", True)):
            world_model.capture_snapshot(
                f"desktop_task:{int(session_id)}",
                summary=observation,
                visible_state={
                    "desktop_task_step": {
                        "session_id": int(session_id),
                        "step_number": int(step_number),
                        "status": _clean(status),
                        "progress": progress_text,
                        "result": result_text,
                        "action": action,
                        "details": details,
                    }
                },
                confidence=0.65,
            )
    except Exception:
        return


def _session_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "goal": row["goal"],
        "status": row["status"],
        "current_step": int(row["current_step"]),
        "max_steps": int(row["max_steps"]),
        "no_progress_count": int(row["no_progress_count"]),
        "recovery_count": int(row["recovery_count"]),
        "last_signature": row["last_signature"],
        "last_progress": row["last_progress"],
        "pending_action": _json_loads(row["pending_action_json"], {}),
        "pending_reason": row["pending_reason"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"] or "",
    }


def _step_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "session_id": int(row["session_id"]),
        "step_number": int(row["step_number"]),
        "timestamp": row["timestamp"],
        "status": row["status"],
        "progress": row["progress"],
        "action": _json_loads(row["action_json"], {}),
        "result": row["result"],
        "screenshot": row["screenshot"],
        "risk": row["risk"],
        "details": _json_loads(row["details_json"], {}),
    }


def _element_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "label": row["label"],
        "action": row["action"],
        "x": row["x"],
        "y": row["y"],
        "uses": int(row["uses"]),
        "last_seen_at": row["last_seen_at"],
        "details": _json_loads(row["details_json"], {}),
    }


def _memory_key(goal: str) -> str:
    words = [word for word in re.sub(r"[^a-z0-9]+", " ", str(goal).lower()).split() if len(word) > 2]
    return " ".join(words[:8]) or "desktop"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

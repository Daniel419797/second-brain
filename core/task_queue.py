"""Persistent SQLite task queue for v2 background agents."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "task_queue.sqlite3"
_LOCK = threading.Lock()

ACTIVE_STATUSES = {"pending", "active", "blocked"}
FINAL_STATUSES = {"done", "failed", "cancelled"}


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
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                status TEXT NOT NULL,
                priority INTEGER NOT NULL,
                input_json TEXT NOT NULL,
                output_json TEXT NOT NULL,
                parent_id INTEGER,
                scheduled_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT
            )
            """
        )
        _ensure_column(conn, "tasks", "scheduled_at", "TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                sender TEXT NOT NULL,
                message TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_heartbeats (
                process_id TEXT PRIMARY KEY,
                updated_at TEXT NOT NULL,
                workers INTEGER NOT NULL,
                desired_workers INTEGER NOT NULL,
                running INTEGER NOT NULL,
                mode TEXT NOT NULL,
                last_activity TEXT NOT NULL,
                runtime_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status_priority ON tasks(status, priority, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_agent ON tasks(agent_id, status)")


def create_task(
    title: str,
    *,
    description: str = "",
    agent_id: str = "research_analyst",
    priority: int = 5,
    input_data: dict[str, Any] | None = None,
    parent_id: int | None = None,
    scheduled_at: Any | None = None,
    status: str = "pending",
) -> int:
    init_db()
    title = _clean(title) or "Untitled task"
    description = _clean(description or title)
    initial_status = _clean(status).lower()
    if initial_status not in ACTIVE_STATUSES:
        initial_status = "pending"
    now = _now()
    started_at = now if initial_status == "active" else None
    with _LOCK, sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO tasks (
                title, description, agent_id, status, priority, input_json,
                output_json, parent_id, scheduled_at, created_at, updated_at, started_at
            )
            VALUES (?, ?, ?, ?, ?, ?, '{}', ?, ?, ?, ?, ?)
            """,
            (
                title,
                description,
                _clean(agent_id) or "research_analyst",
                initial_status,
                int(priority),
                _json_dumps(input_data or {}),
                parent_id,
                _normalize_when(scheduled_at),
                now,
                now,
                started_at,
            ),
        )
        task_id = int(cursor.lastrowid)
    post_message(task_id, "system", f"Task created for {agent_id}.")
    return task_id


def claim_next_task(agent_ids: list[str] | None = None) -> dict[str, Any] | None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        where = "status = 'pending' AND (scheduled_at IS NULL OR scheduled_at = '' OR scheduled_at <= ?)"
        params: list[Any] = [_now()]
        if agent_ids:
            placeholders = ",".join("?" for _ in agent_ids)
            where += f" AND agent_id IN ({placeholders})"
            params.extend(agent_ids)
        row = conn.execute(
            f"SELECT * FROM tasks WHERE {where} ORDER BY priority ASC, created_at ASC LIMIT 1",
            params,
        ).fetchone()
        if row is None:
            return None
        now = _now()
        cursor = conn.execute(
            "UPDATE tasks SET status='active', started_at=COALESCE(started_at, ?), updated_at=? WHERE id=? AND status='pending'",
            (now, now, int(row["id"])),
        )
        if cursor.rowcount <= 0:
            return None
        task = _row_to_task(row)
        task["status"] = "active"
        task["started_at"] = task.get("started_at") or now
        task["updated_at"] = now
        return task


def complete_task(task_id: int, output: Any, status: str = "done") -> None:
    if status not in FINAL_STATUSES:
        status = "done"
    _finish_task(task_id, status=status, output=output)


def fail_task(task_id: int, error: str) -> None:
    _finish_task(task_id, status="failed", output={"error": error})


def cancel_task(task_id: int) -> bool:
    task = get_task(task_id)
    if task is None or task["status"] in FINAL_STATUSES:
        return False
    _finish_task(task_id, status="cancelled", output={"cancelled": True})
    post_message(task_id, "system", "Task cancelled.")
    return True


def reassign_task(task_id: int, agent_id: str, *, status: str | None = None) -> bool:
    task = get_task(task_id)
    if task is None or task["status"] in FINAL_STATUSES:
        return False
    agent = _clean(agent_id) or "research_analyst"
    next_status = _clean(status or task["status"]).lower()
    if next_status not in ACTIVE_STATUSES:
        next_status = str(task["status"])
    now = _now()
    fields = ["agent_id = ?", "status = ?", "updated_at = ?"]
    params: list[Any] = [agent, next_status, now]
    if next_status == "pending":
        fields.extend(["started_at = NULL", "completed_at = NULL"])
    with _LOCK, sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", [*params, int(task_id)])
        changed = cursor.rowcount > 0
    if changed:
        status_note = " and returned to pending" if next_status == "pending" else ""
        post_message(task_id, "system", f"Task reassigned to {agent}{status_note}.")
    return changed


def set_scheduled_at(task_id: int, scheduled_at: Any | None = None) -> bool:
    init_db()
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "UPDATE tasks SET scheduled_at=?, updated_at=? WHERE id=?",
            (_normalize_when(scheduled_at), now, int(task_id)),
        )
        changed = cursor.rowcount > 0
    if changed:
        post_message(task_id, "system", "Task released for scheduling." if not scheduled_at else f"Task scheduled for {scheduled_at}.")
    return changed


def update_status(task_id: int, status: str, output: Any | None = None) -> bool:
    init_db()
    status = _clean(status).lower()
    if status not in ACTIVE_STATUSES | FINAL_STATUSES:
        return False
    now = _now()
    fields = ["status = ?", "updated_at = ?"]
    params: list[Any] = [status, now]
    if output is not None:
        fields.append("output_json = ?")
        params.append(_json_dumps(output))
    if status in FINAL_STATUSES:
        fields.append("completed_at = ?")
        params.append(now)
    params.append(int(task_id))
    with _LOCK, sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", params)
        return cursor.rowcount > 0


def get_task(task_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (int(task_id),)).fetchone()
        return _row_to_task(row) if row else None


def list_tasks(status: str | None = None, agent_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    where: list[str] = []
    params: list[Any] = []
    if status:
        where.append("status = ?")
        params.append(status)
    if agent_id:
        where.append("agent_id = ?")
        params.append(agent_id)
    sql = "SELECT * FROM tasks"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'pending' THEN 1 WHEN 'blocked' THEN 2 ELSE 3 END, priority ASC, updated_at DESC LIMIT ?"
    params.append(max(1, int(limit)))
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return [_row_to_task(row) for row in conn.execute(sql, params)]


def post_message(task_id: int, sender: str, message: str) -> int:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "INSERT INTO task_messages (task_id, timestamp, sender, message) VALUES (?, ?, ?, ?)",
            (int(task_id), _now(), _clean(sender) or "system", _clean(message)),
        )
        return int(cursor.lastrowid)


def get_messages(task_id: int, limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM task_messages WHERE task_id = ? ORDER BY timestamp DESC, id DESC LIMIT ?",
            (int(task_id), max(1, int(limit))),
        )
        return [
            {
                "id": int(row["id"]),
                "task_id": int(row["task_id"]),
                "timestamp": str(row["timestamp"]),
                "sender": str(row["sender"]),
                "message": str(row["message"]),
            }
            for row in rows
        ]


def task_progress(task_id: int, status: str | None = None) -> int:
    normalized = _clean(status or "").lower()
    if normalized == "done":
        return 100
    if normalized in {"failed", "cancelled"}:
        return 0
    if normalized == "blocked":
        return 10
    if normalized == "pending":
        return 15
    messages = get_messages(task_id, limit=30)
    best = 35 if normalized == "active" else 0
    for message in messages:
        match = re.search(r"\bprogress\s+(\d{1,3})\s*%", str(message.get("message") or ""), re.IGNORECASE)
        if match:
            best = max(best, min(99, int(match.group(1))))
    return best


def counts() -> dict[str, int]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status").fetchall()
    result = {status: 0 for status in sorted(ACTIVE_STATUSES | FINAL_STATUSES)}
    result.update({str(status): int(count) for status, count in rows})
    result["total"] = sum(value for key, value in result.items() if key != "total")
    return result


def record_worker_heartbeat(
    process_id: str,
    *,
    workers: int,
    desired_workers: int,
    running: bool,
    mode: str,
    last_activity: str = "",
    runtime: dict[str, Any] | None = None,
) -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO worker_heartbeats (
                process_id, updated_at, workers, desired_workers, running, mode, last_activity, runtime_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(process_id) DO UPDATE SET
                updated_at=excluded.updated_at,
                workers=excluded.workers,
                desired_workers=excluded.desired_workers,
                running=excluded.running,
                mode=excluded.mode,
                last_activity=excluded.last_activity,
                runtime_json=excluded.runtime_json
            """,
            (
                _clean(process_id),
                _now(),
                max(0, int(workers)),
                max(1, int(desired_workers)),
                1 if running else 0,
                _clean(mode),
                _clean(last_activity),
                _json_dumps(runtime or {}),
            ),
        )


def worker_heartbeats(max_age_seconds: float = 20.0) -> list[dict[str, Any]]:
    init_db()
    cutoff = dt.datetime.now(dt.timezone.utc).astimezone() - dt.timedelta(seconds=float(max_age_seconds))
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = list(conn.execute("SELECT * FROM worker_heartbeats ORDER BY updated_at DESC"))
    items: list[dict[str, Any]] = []
    for row in rows:
        try:
            updated = dt.datetime.fromisoformat(str(row["updated_at"]))
        except ValueError:
            continue
        if updated < cutoff:
            continue
        items.append(
            {
                "process_id": str(row["process_id"]),
                "updated_at": str(row["updated_at"]),
                "workers": int(row["workers"]),
                "desired_workers": int(row["desired_workers"]),
                "running": bool(row["running"]),
                "mode": str(row["mode"]),
                "last_activity": str(row["last_activity"] or ""),
                "runtime": _json_loads(row["runtime_json"]),
            }
        )
    return items


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM task_messages")
        conn.execute("DELETE FROM tasks")
        conn.execute("DELETE FROM worker_heartbeats")


def _finish_task(task_id: int, status: str, output: Any) -> None:
    init_db()
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE tasks SET status=?, output_json=?, updated_at=?, completed_at=? WHERE id=?",
            (status, _json_dumps(output), now, now, int(task_id)),
        )
    post_message(task_id, "system", f"Task {status}.")


def _row_to_task(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "title": str(row["title"]),
        "description": str(row["description"]),
        "agent_id": str(row["agent_id"]),
        "status": str(row["status"]),
        "priority": int(row["priority"]),
        "input": _json_loads(row["input_json"]),
        "output": _json_loads(row["output_json"]),
        "parent_id": row["parent_id"],
        "scheduled_at": str(row["scheduled_at"] or ""),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "started_at": str(row["started_at"] or ""),
        "completed_at": str(row["completed_at"] or ""),
    }


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=True)


def _json_loads(value: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return value


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _normalize_when(value: Any | None) -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        stamp = value
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
        return stamp.astimezone().isoformat(timespec="seconds")
    text = _clean(str(value))
    if not text:
        return ""
    try:
        return dt.datetime.fromisoformat(text).astimezone().isoformat(timespec="seconds")
    except ValueError:
        return text


def _clean(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

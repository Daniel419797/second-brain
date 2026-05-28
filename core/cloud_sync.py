"""Optional SQLite to PostgreSQL sync for v2 cloud deployments."""

from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

try:
    import psycopg
except Exception:  # pragma: no cover
    psycopg = None

try:
    from apscheduler.schedulers.background import BackgroundScheduler
except Exception:  # pragma: no cover
    BackgroundScheduler = None

from core import audit_log, task_queue
from core.config import config_value

_SCHEDULER: Any = None


def sync_once(database_url: str | None = None) -> dict[str, Any]:
    """Push local task/audit state into PostgreSQL using idempotent upserts."""
    url = database_url or os.getenv(str(config_value("cloud_sync_database_url_env", "DATABASE_URL")), "")
    if not url or _is_placeholder_url(url):
        return {"enabled": False, "tasks": 0, "messages": 0, "audit_events": 0, "duration_ms": 0.0}
    if psycopg is None:
        return {"enabled": False, "error": "psycopg is not installed", "tasks": 0, "messages": 0, "audit_events": 0, "duration_ms": 0.0}
    start = time.perf_counter()
    task_queue.init_db()
    audit_log.init_db()
    tasks, messages = _read_tasks(task_queue.DB_PATH)
    events = _read_audit(audit_log.DB_PATH)
    with psycopg.connect(url) as conn:
        _ensure_schema(conn)
        with conn.cursor() as cur:
            for task in tasks:
                cur.execute(
                    """
                    INSERT INTO synced_tasks (
                        id, title, description, agent_id, status, priority, input_json,
                        output_json, parent_id, scheduled_at, created_at, updated_at,
                        started_at, completed_at, synced_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        title=EXCLUDED.title,
                        description=EXCLUDED.description,
                        agent_id=EXCLUDED.agent_id,
                        status=EXCLUDED.status,
                        priority=EXCLUDED.priority,
                        input_json=EXCLUDED.input_json,
                        output_json=EXCLUDED.output_json,
                        parent_id=EXCLUDED.parent_id,
                        scheduled_at=EXCLUDED.scheduled_at,
                        updated_at=EXCLUDED.updated_at,
                        started_at=EXCLUDED.started_at,
                        completed_at=EXCLUDED.completed_at,
                        synced_at=EXCLUDED.synced_at
                    """,
                    _task_values(task),
                )
            for message in messages:
                cur.execute(
                    """
                    INSERT INTO synced_task_messages (id, task_id, timestamp, sender, message, synced_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        task_id=EXCLUDED.task_id,
                        timestamp=EXCLUDED.timestamp,
                        sender=EXCLUDED.sender,
                        message=EXCLUDED.message,
                        synced_at=EXCLUDED.synced_at
                    """,
                    _message_values(message),
                )
            for event in events:
                cur.execute(
                    """
                    INSERT INTO synced_audit_events (id, timestamp, actor, category, action, target, success, details_json, synced_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        timestamp=EXCLUDED.timestamp,
                        actor=EXCLUDED.actor,
                        category=EXCLUDED.category,
                        action=EXCLUDED.action,
                        target=EXCLUDED.target,
                        success=EXCLUDED.success,
                        details_json=EXCLUDED.details_json,
                        synced_at=EXCLUDED.synced_at
                    """,
                    _audit_values(event),
                )
        conn.commit()
    return {
        "enabled": True,
        "tasks": len(tasks),
        "messages": len(messages),
        "audit_events": len(events),
        "duration_ms": round((time.perf_counter() - start) * 1000, 3),
    }


def start_scheduler() -> Any:
    global _SCHEDULER
    if not bool(config_value("cloud_sync_enabled", False)):
        return None
    if BackgroundScheduler is None:
        return None
    if _SCHEDULER is not None and getattr(_SCHEDULER, "running", False):
        return _SCHEDULER
    minutes = max(1, int(config_value("cloud_sync_interval_minutes", 5)))
    _SCHEDULER = BackgroundScheduler(daemon=True)
    _SCHEDULER.add_job(sync_once, "interval", minutes=minutes, id="cloud_sync", replace_existing=True)
    _SCHEDULER.start()
    return _SCHEDULER


def stop_scheduler() -> None:
    global _SCHEDULER
    if _SCHEDULER is None:
        return
    try:
        if getattr(_SCHEDULER, "running", False):
            _SCHEDULER.shutdown(wait=False)
    finally:
        _SCHEDULER = None


def _read_tasks(path: Path) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        tasks = list(conn.execute("SELECT * FROM tasks"))
        messages = list(conn.execute("SELECT * FROM task_messages"))
    return tasks, messages


def _read_audit(path: Path) -> list[sqlite3.Row]:
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return list(conn.execute("SELECT * FROM audit_events"))


def _ensure_schema(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS synced_tasks (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                status TEXT NOT NULL,
                priority INTEGER NOT NULL,
                input_json JSONB NOT NULL,
                output_json JSONB NOT NULL,
                parent_id INTEGER,
                scheduled_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                synced_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS synced_task_messages (
                id INTEGER PRIMARY KEY,
                task_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                sender TEXT NOT NULL,
                message TEXT NOT NULL,
                synced_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS synced_audit_events (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                actor TEXT NOT NULL,
                category TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT NOT NULL,
                success BOOLEAN NOT NULL,
                details_json JSONB NOT NULL,
                synced_at TEXT NOT NULL
            )
            """
        )


def _task_values(row: sqlite3.Row) -> tuple[Any, ...]:
    return (
        int(row["id"]),
        str(row["title"]),
        str(row["description"]),
        str(row["agent_id"]),
        str(row["status"]),
        int(row["priority"]),
        _jsonb(row["input_json"]),
        _jsonb(row["output_json"]),
        row["parent_id"],
        str(row["scheduled_at"] or ""),
        str(row["created_at"]),
        str(row["updated_at"]),
        str(row["started_at"] or ""),
        str(row["completed_at"] or ""),
        _now(),
    )


def _message_values(row: sqlite3.Row) -> tuple[Any, ...]:
    return (int(row["id"]), int(row["task_id"]), str(row["timestamp"]), str(row["sender"]), str(row["message"]), _now())


def _audit_values(row: sqlite3.Row) -> tuple[Any, ...]:
    return (
        int(row["id"]),
        str(row["timestamp"]),
        str(row["actor"]),
        str(row["category"]),
        str(row["action"]),
        str(row["target"]),
        bool(row["success"]),
        _jsonb(row["details_json"]),
        _now(),
    )


def _jsonb(value: str) -> str:
    try:
        return json.dumps(json.loads(value), ensure_ascii=True)
    except Exception:
        return json.dumps(value, ensure_ascii=True)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _is_placeholder_url(value: str) -> bool:
    lowered = str(value or "").lower()
    return not lowered or "user:password@host" in lowered or "your_" in lowered or lowered.endswith("/friday_placeholder")

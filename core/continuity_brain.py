"""Continuity memory for unfinished threads across days."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import autonomous_debugger, mission_control, task_queue, trust_proof
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "continuity_brain.sqlite3"
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
            CREATE TABLE IF NOT EXISTS continuity_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                topic TEXT NOT NULL UNIQUE,
                summary TEXT NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                priority INTEGER NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS continuity_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                thread_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def remember_thread(topic: str, summary: str, *, source: str = "manual", status: str = "open", priority: int = 3, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    cleaned_topic = _clean(topic)
    cleaned_summary = _clean(summary)
    if not cleaned_topic or not cleaned_summary:
        return {"ok": False, "summary": "Continuity needs a topic and summary."}
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO continuity_threads(created_at, updated_at, topic, summary, source, status, priority, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(topic) DO UPDATE SET
                updated_at=excluded.updated_at,
                summary=excluded.summary,
                source=excluded.source,
                status=excluded.status,
                priority=max(continuity_threads.priority, excluded.priority),
                metadata_json=excluded.metadata_json
            """,
            (now, now, cleaned_topic, cleaned_summary, _clean(source), _status(status), _priority(priority), _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM continuity_threads WHERE topic=?", (cleaned_topic,)).fetchone()
        event_id = conn.execute(
            "INSERT INTO continuity_events(timestamp, thread_id, event_type, summary, metadata_json) VALUES (?, ?, 'remember', ?, ?)",
            (now, int(row["id"]), cleaned_summary, _json_dumps(metadata or {})),
        ).lastrowid
    item = _row(row)
    item["ok"] = True
    item["event_id"] = int(event_id)
    return item


def close_thread(thread_id: int, *, note: str = "") -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE continuity_threads SET status='closed', updated_at=? WHERE id=?", (_now(), int(thread_id)))
        row = conn.execute("SELECT * FROM continuity_threads WHERE id=?", (int(thread_id),)).fetchone()
        if row:
            conn.execute(
                "INSERT INTO continuity_events(timestamp, thread_id, event_type, summary, metadata_json) VALUES (?, ?, 'close', ?, '{}')",
                (_now(), int(thread_id), _clean(note) or "Closed."),
            )
    return _row(row) if row else {"ok": False, "summary": "Continuity thread not found."}


def capture_current_state() -> dict[str, Any]:
    """Capture unfinished context from tasks, missions, debugger reports, and proof gaps."""
    captured: list[dict[str, Any]] = []
    try:
        for task in task_queue.list_tasks(limit=40):
            if str(task.get("status") or "") in {"active", "pending", "blocked", "failed"}:
                captured.append(
                    remember_thread(
                        f"task:{task.get('id')}",
                        f"{task.get('title') or 'Task'} is {task.get('status')}.",
                        source="task_queue",
                        status="open" if task.get("status") != "failed" else "blocked",
                        priority=int(task.get("priority") or 3),
                        metadata={"task": task},
                    )
                )
    except Exception:
        pass
    try:
        for mission in mission_control.list_missions(limit=10):
            if str(mission.get("status") or "") in {"running", "blocked", "paused"}:
                captured.append(
                    remember_thread(
                        f"mission:{mission.get('id')}",
                        f"Mission '{mission.get('goal')}' is {mission.get('status')} at {mission.get('current_phase')}.",
                        source="mission_control",
                        status=str(mission.get("status") or "open"),
                        priority=int(mission.get("priority") or 3),
                        metadata={"mission": mission},
                    )
                )
    except Exception:
        pass
    try:
        for report in autonomous_debugger.recent(limit=6):
            if str(report.get("status") or "") == "open":
                captured.append(
                    remember_thread(
                        f"debugger:{report.get('id')}",
                        f"Debugger issue: {report.get('summary')}",
                        source="autonomous_debugger",
                        status="blocked",
                        priority=4,
                        metadata={"debugger_report": report},
                    )
                )
    except Exception:
        pass
    try:
        latest_proof = trust_proof.recent(limit=1)
        if latest_proof:
            proof = latest_proof[0]
            if proof.get("risks"):
                captured.append(
                    remember_thread(
                        f"proof-risk:{proof.get('id')}",
                        f"Proof report '{proof.get('title')}' still has remaining risk.",
                        source="trust_proof",
                        status="open",
                        priority=3,
                        metadata={"proof": proof},
                    )
                )
    except Exception:
        pass
    return {"captured": [item for item in captured if item.get("ok")], "summary": f"Captured {len([item for item in captured if item.get('ok')])} continuity thread(s)."}


def open_threads(limit: int = 12) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM continuity_threads WHERE status!='closed' ORDER BY priority DESC, updated_at DESC LIMIT ?",
            (max(1, min(100, int(limit or 12))),),
        ).fetchall()
    return [_row(row) for row in rows]


def recent_events(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM continuity_events ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_event_row(row) for row in rows]


def status() -> dict[str, Any]:
    threads = open_threads(limit=8)
    if threads:
        first = threads[0]
        voice = f"{len(threads)} unfinished thread(s). Top: {first['summary']}"
    else:
        voice = "No unfinished continuity threads."
    return {"open_count": len(open_threads(limit=100)), "threads": threads, "events": recent_events(limit=6), "summary": voice}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM continuity_events")
        conn.execute("DELETE FROM continuity_threads")


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "topic": str(row["topic"]),
        "summary": str(row["summary"]),
        "source": str(row["source"]),
        "status": str(row["status"]),
        "priority": int(row["priority"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _event_row(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": int(row["id"]), "timestamp": str(row["timestamp"]), "thread_id": int(row["thread_id"]), "event_type": str(row["event_type"]), "summary": str(row["summary"]), "metadata": _json_loads(row["metadata_json"], {})}


def _status(value: str) -> str:
    cleaned = _clean(value).lower()
    return cleaned if cleaned in {"open", "blocked", "paused", "running", "pending", "closed"} else "open"


def _priority(value: Any) -> int:
    try:
        return max(1, min(5, int(value)))
    except Exception:
        return 3


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

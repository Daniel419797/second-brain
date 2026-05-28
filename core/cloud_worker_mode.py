"""Cloud worker mode for heavy but safe background jobs.

This is a provider-neutral queue. It does not spend money or ship private data
by itself; if no external worker endpoint is configured, jobs become local
fallback tasks so Friday can keep the laptop fast and stay honest.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import notification_center, task_queue
from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "cloud_worker_mode.sqlite3"
_LOCK = threading.Lock()
SAFE_JOB_TYPES = {"research", "long_tests", "deployment_check", "document_indexing", "scheduled_mission"}


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
            CREATE TABLE IF NOT EXISTS cloud_worker_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                job_type TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                provider TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                local_task_id INTEGER
            )
            """
        )


def submit(job_type: str, title: str, payload: dict[str, Any] | None = None, *, prefer_cloud: bool = True) -> dict[str, Any]:
    init_db()
    normalized = _clean(job_type).lower().replace(" ", "_")
    if normalized not in SAFE_JOB_TYPES:
        return {"ok": False, "summary": "Unsupported or unsafe cloud worker job type.", "allowed": sorted(SAFE_JOB_TYPES)}
    safe_payload = _safe_payload(payload or {})
    provider = _provider() if prefer_cloud else "local_fallback"
    status = "queued_cloud" if provider != "local_fallback" else "queued_local"
    task_id = 0
    if provider == "local_fallback":
        task_id = task_queue.create_task(
            f"Cloud-worker fallback: {title}",
            description=f"Local fallback for {normalized}. Keep heavy work background-safe and report proof.",
            agent_id=_agent_for(normalized),
            priority=7,
            input_data={"source": "cloud_worker_mode", "job_type": normalized, "payload": safe_payload},
        )
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO cloud_worker_jobs(created_at, updated_at, job_type, title, status, provider, payload_json, result_json, local_task_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?)
            """,
            (now, now, normalized, _clean(title)[:300], status, provider, _json_dumps(safe_payload), task_id or None),
        )
        row = conn.execute("SELECT * FROM cloud_worker_jobs WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    notification_center.add(source="cloud_worker_mode", category="background_work", severity=1, title="Cloud worker job queued", message=f"{title} queued via {provider}.", metadata={"job_type": normalized})
    return _row(row)


def complete(job_id: int, result: dict[str, Any] | None = None, *, status: str = "done") -> dict[str, Any]:
    init_db()
    normalized = _clean(status).lower() or "done"
    if normalized not in {"done", "failed", "cancelled"}:
        normalized = "done"
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE cloud_worker_jobs SET status=?, result_json=?, updated_at=? WHERE id=?", (normalized, _json_dumps(_safe_payload(result or {})), _now(), int(job_id)))
        row = conn.execute("SELECT * FROM cloud_worker_jobs WHERE id=?", (int(job_id),)).fetchone()
    return _row(row) if row else {"ok": False, "summary": "Cloud worker job not found."}


def list_jobs(limit: int = 30, status: str = "") -> list[dict[str, Any]]:
    init_db()
    where = ""
    params: list[Any] = []
    if status:
        where = "WHERE status=?"
        params.append(_clean(status).lower())
    params.append(max(1, min(100, int(limit or 30))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM cloud_worker_jobs {where} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    jobs = list_jobs(limit=12)
    provider = _provider()
    queued = [job for job in jobs if str(job.get("status", "")).startswith("queued")]
    return {
        "provider": provider,
        "configured": provider != "local_fallback",
        "safe_job_types": sorted(SAFE_JOB_TYPES),
        "queued": len(queued),
        "recent": jobs,
        "summary": f"Cloud worker mode is {'configured' if provider != 'local_fallback' else 'using local fallback'} with {len(queued)} queued job(s).",
    }


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM cloud_worker_jobs")


def _provider() -> str:
    if os.getenv("FRIDAY_CLOUD_WORKER_URL") or str(config_value("cloud_worker_url", "")).strip():
        return str(config_value("cloud_worker_provider", "custom_worker"))
    return "local_fallback"


def _agent_for(job_type: str) -> str:
    return {
        "research": "research_analyst",
        "long_tests": "qa_engineer",
        "deployment_check": "senior_developer",
        "document_indexing": "research_analyst",
        "scheduled_mission": "project_manager",
    }.get(job_type, "research_analyst")


def _safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in payload.items():
        name = _clean(key)[:80]
        if not name:
            continue
        if any(term in name.lower() for term in ("password", "secret", "token", "api_key", "credential", "authorization")):
            safe[name] = "[redacted]"
        elif isinstance(value, (str, int, float, bool)) or value is None:
            safe[name] = str(value)[:4000] if isinstance(value, str) else value
        else:
            safe[name] = _clean(value)[:1000]
    return safe


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "job_type": str(row["job_type"]),
        "title": str(row["title"]),
        "status": str(row["status"]),
        "provider": str(row["provider"]),
        "payload": _json_loads(row["payload_json"], {}),
        "result": _json_loads(row["result_json"], {}),
        "local_task_id": int(row["local_task_id"] or 0),
        "summary": f"{row['title']} is {row['status']} via {row['provider']}.",
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

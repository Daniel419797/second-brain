"""Real agent scheduler for worker timing, retries, and quota-aware planning."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import background_agents, llm, model_router_brain, notification_center, task_queue
from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "agent_scheduler.sqlite3"
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
            CREATE TABLE IF NOT EXISTS scheduler_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                kind TEXT NOT NULL,
                summary TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )


def plan(mode: str = "auto", *, voice_active: bool = False, apply: bool = False) -> dict[str, Any]:
    """Create a worker plan without changing runtime state unless apply=True."""
    init_db()
    normalized = _clean(mode).lower() or "auto"
    now = dt.datetime.now().astimezone()
    hour = now.hour
    worker_state = background_agents.worker_status()
    counts = task_queue.counts()
    provider_limits = llm.provider_limit_status()
    online = llm.online_provider_available()
    pending = int(counts.get("pending") or 0)
    failed = int(counts.get("failed") or 0)
    active = int(counts.get("active") or 0)
    default_online = int(config_value("v2_api_background_worker_count", 10))
    default_local = int(config_value("v2_local_background_worker_count", 1))
    max_workers = max(1, default_online if online else default_local)
    night_start = int(config_value("agent_scheduler_night_start_hour", 22))
    night_end = int(config_value("agent_scheduler_night_end_hour", 6))
    is_night = hour >= night_start or hour < night_end
    quota_pressure = _quota_pressure(provider_limits)

    reasons: list[str] = []
    if voice_active or normalized in {"voice", "fast_voice", "conversation"}:
        desired = 0
        action = "pause"
        reasons.append("voice mode should keep the laptop responsive")
    elif normalized in {"overnight", "night"} or (normalized == "auto" and is_night and pending):
        desired = min(max_workers, int(config_value("agent_scheduler_overnight_workers", 6 if online else 1)))
        action = "start" if desired else "idle"
        reasons.append("overnight window can run research/build work quietly")
    elif pending or active:
        desired = min(max_workers, max(1, min(pending + active, max_workers)))
        action = "start"
        reasons.append("work is queued or active")
    else:
        desired = 0
        action = "idle"
        reasons.append("no pending work needs workers")

    if quota_pressure and desired > 1:
        desired = max(1, min(desired, int(config_value("agent_scheduler_quota_safe_workers", 2))))
        reasons.append("hosted model provider backoff/rate pressure detected")
    if not online and desired > default_local:
        desired = default_local
        reasons.append("offline/local mode keeps Ollama to one CPU-safe worker")
    if failed:
        reasons.append(f"{failed} failed task(s) can be retried when approved")

    payload = {
        "mode": normalized,
        "timestamp": _now(),
        "online_agent_mode": bool(online),
        "is_night_window": bool(is_night),
        "voice_active": bool(voice_active),
        "action": action,
        "desired_workers": int(desired),
        "current_workers": int(worker_state.get("workers") or 0),
        "worker_state": worker_state,
        "task_counts": counts,
        "provider_limits": provider_limits,
        "quota_pressure": quota_pressure,
        "reasons": reasons,
        "summary": _summary(action, desired, reasons),
    }
    _record("plan", payload["summary"], payload)
    if apply:
        return apply_plan(payload)
    return payload


def apply_plan(plan_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = plan_payload or plan()
    desired = max(0, int(payload.get("desired_workers") or 0))
    if desired <= 0:
        background_agents.stop_workers()
        applied = "stopped"
    else:
        background_agents.start_workers(desired)
        applied = "started"
    result = {**payload, "applied": applied, "worker_state_after": background_agents.worker_status()}
    result["summary"] = f"Agent scheduler {applied} workers; target is {desired}."
    _record("apply", result["summary"], result)
    return result


def retry_failed_tasks(limit: int = 3) -> dict[str, Any]:
    init_db()
    retried: list[dict[str, Any]] = []
    for task in task_queue.list_tasks(status="failed", limit=max(1, min(25, int(limit or 3)))):
        task_id = int(task.get("id") or 0)
        if not task_id:
            continue
        if task_queue.update_status(task_id, "pending", output={"retried_by": "agent_scheduler", "previous_output": task.get("output")}):
            task_queue.post_message(task_id, "agent_scheduler", "Returned failed task to pending for a safe retry.")
            retried.append(task_queue.get_task(task_id) or task)
    summary = f"Queued {len(retried)} failed task(s) for retry."
    payload = {"retried": retried, "summary": summary}
    _record("retry_failed", summary, payload)
    if retried:
        notification_center.add(
            source="agent_scheduler",
            category="agents",
            severity=2,
            title="Failed tasks retried",
            message=summary,
            metadata={"task_ids": [item.get("id") for item in retried]},
        )
    return payload


def schedule_overnight_research(topic: str = "", *, priority: int = 9) -> dict[str, Any]:
    title = _clean(topic) or "Overnight research queue"
    due = _next_overnight_window()
    task_id = task_queue.create_task(
        title=f"Research: {title}",
        description=f"Research background context for {title} and pass findings to the relevant agent notebook.",
        agent_id="research_analyst",
        priority=max(5, min(20, int(priority or 9))),
        input_data={"source": "agent_scheduler", "topic": title, "handoff": True},
        scheduled_at=due,
    )
    task_queue.post_message(task_id, "agent_scheduler", f"Scheduled for overnight research at {due}.")
    payload = {"task_id": task_id, "scheduled_at": due, "topic": title, "summary": f"Scheduled overnight research task #{task_id}."}
    _record("schedule_research", payload["summary"], payload)
    return payload


def status() -> dict[str, Any]:
    latest = recent_events(limit=1)
    current = plan(mode="status") if not latest else None
    return {
        "latest": latest[0] if latest else current,
        "events": recent_events(limit=8),
        "worker_state": background_agents.worker_status(),
        "task_counts": task_queue.counts(),
        "summary": latest[0]["summary"] if latest else "Agent scheduler is ready.",
    }


def recent_events(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM scheduler_events ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM scheduler_events")


def _quota_pressure(provider_limits: dict[str, Any]) -> bool:
    for provider, data in (provider_limits or {}).items():
        if not isinstance(data, dict):
            continue
        if provider == "ollama":
            continue
        if float(data.get("backoff_seconds") or 0.0) > 0 or int(data.get("failure_streak") or 0) >= 2:
            return True
    return False


def _summary(action: str, desired: int, reasons: list[str]) -> str:
    reason = "; ".join(reasons[:3]) if reasons else "no reason recorded"
    return f"Scheduler recommends {action} with {desired} worker(s): {reason}."


def _next_overnight_window() -> str:
    start = int(config_value("agent_scheduler_night_start_hour", 22))
    now = dt.datetime.now().astimezone()
    target = now.replace(hour=start, minute=0, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return target.isoformat(timespec="seconds")


def _record(kind: str, summary: str, payload: dict[str, Any]) -> int:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            "INSERT INTO scheduler_events(timestamp, kind, summary, payload_json) VALUES (?, ?, ?, ?)",
            (_now(), _clean(kind), _clean(summary)[:1000], _json_dumps(payload)),
        )
    return int(cursor.lastrowid)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "kind": str(row["kind"]),
        "summary": str(row["summary"]),
        "payload": _json_loads(row["payload_json"], {}),
    }


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


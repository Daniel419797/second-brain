"""Proactive guardian mode for important PC, project, and assistant signals."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable

from core import app_integrations, background_agents, capability_center, evaluation_lab, notification_center, phone_bridge, task_queue, voice_reliability
from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "proactive_guardian.sqlite3"
_LOCK = threading.Lock()
_STOP = threading.Event()
_THREAD: threading.Thread | None = None
_LAST_STATUS = "stopped"

LogFn = Callable[[str, str], None]


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
            CREATE TABLE IF NOT EXISTS guardian_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                summary TEXT NOT NULL,
                alert_count INTEGER NOT NULL,
                alerts_json TEXT NOT NULL,
                stats_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_guardian_runs_time ON guardian_runs(timestamp)")


def start_service(log_fn: LogFn | None = None) -> bool:
    global _THREAD, _LAST_STATUS
    if not bool(config_value("proactive_guardian_enabled", True)):
        _LAST_STATUS = "disabled"
        return False
    with _LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return True
        _STOP.clear()
        _THREAD = threading.Thread(target=_loop, args=(log_fn,), name="FridayProactiveGuardian", daemon=True)
        _THREAD.start()
        _LAST_STATUS = "running"
        return True


def stop_service(timeout: float = 2.0) -> None:
    global _LAST_STATUS
    _STOP.set()
    thread = _THREAD
    if thread is not None:
        thread.join(timeout=timeout)
    _LAST_STATUS = "stopped"


def status() -> dict[str, Any]:
    thread = _THREAD
    return {
        "enabled": bool(config_value("proactive_guardian_enabled", True)),
        "running": bool(thread and thread.is_alive() and not _STOP.is_set()),
        "status": _LAST_STATUS,
        "last_run": latest_run(),
        "notifications": notification_center.summary(limit=6),
    }


def run_scan(*, light: bool = True, notify: bool = True) -> dict[str, Any]:
    """Collect important signals and create notifications only for meaningful issues."""

    init_db()
    alerts: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}
    stats["maintenance"] = _safe(lambda: capability_center.maintenance_report(light=light), {})
    stats["security"] = _safe(lambda: capability_center.security_overview(light=light), {})
    stats["workers"] = _safe(background_agents.worker_status, {})
    stats["phone"] = _safe(phone_bridge.status, {})
    stats["voice"] = _safe(voice_reliability.summary, {})
    stats["evaluation"] = _safe(evaluation_lab.summary, {})
    stats["task_counts"] = _safe(task_queue.counts, {})

    alerts.extend(_battery_alerts(stats["maintenance"]))
    alerts.extend(_disk_alerts(stats["maintenance"]))
    alerts.extend(_security_alerts(stats["security"]))
    alerts.extend(_task_alerts())
    alerts.extend(_reminder_alerts())
    alerts.extend(_evaluation_alerts(stats["evaluation"]))
    alerts.extend(_voice_alerts(stats["voice"]))
    alerts.extend(_phone_alerts(stats["phone"]))

    if notify:
        for alert in alerts:
            notification_center.add(**alert)
    summary = _summary(alerts)
    run_id = _persist_run(summary, alerts, stats)
    return {
        "id": run_id,
        "timestamp": _now(),
        "summary": summary,
        "alerts": alerts,
        "stats": stats,
        "notifications": notification_center.summary(limit=8),
    }


def latest_run() -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM guardian_runs ORDER BY id DESC LIMIT 1").fetchone()
    return _row(row) if row else None


def recent_runs(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM guardian_runs ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit))),)).fetchall()
    return [_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM guardian_runs")


def _loop(log_fn: LogFn | None) -> None:
    global _LAST_STATUS
    interval = max(30.0, float(config_value("proactive_guardian_interval_seconds", 120.0)))
    startup_delay = max(0.0, float(config_value("proactive_guardian_startup_delay_seconds", 15.0)))
    if startup_delay:
        _STOP.wait(startup_delay)
    while not _STOP.is_set():
        try:
            _LAST_STATUS = "checking"
            result = run_scan(light=True, notify=True)
            if log_fn and result.get("alerts"):
                log_fn("INFO", f"[GUARDIAN] {result['summary']}")
            _LAST_STATUS = "running"
        except Exception as exc:
            _LAST_STATUS = f"error: {exc.__class__.__name__}"
            if log_fn:
                log_fn("WARNING", f"[GUARDIAN] scan failed ({exc})")
        _STOP.wait(interval)


def _battery_alerts(maintenance: dict[str, Any]) -> list[dict[str, Any]]:
    health = maintenance.get("health") or {}
    battery = health.get("battery") or {}
    percent = battery.get("percent")
    if percent is None:
        return []
    threshold = float(config_value("guardian_battery_low_percent", 20))
    if float(percent) >= threshold or battery.get("plugged"):
        return []
    return [_alert("guardian", "battery", 4, "Battery is low", f"Laptop battery is {percent}%.", "battery-low", {"battery": battery})]


def _disk_alerts(maintenance: dict[str, Any]) -> list[dict[str, Any]]:
    alerts = []
    for disk in maintenance.get("disk") or []:
        free = disk.get("free_percent")
        if free is not None and float(free) < float(config_value("guardian_disk_low_percent", 15)):
            alerts.append(_alert("guardian", "disk", 4, "Disk space is low", f"{disk.get('path')} has {free}% free.", f"disk-low:{disk.get('path')}", {"disk": disk}))
    return alerts


def _security_alerts(security: dict[str, Any]) -> list[dict[str, Any]]:
    alerts = []
    processes = security.get("suspicious_processes") or []
    if processes:
        alerts.append(_alert("guardian", "security", 5, "Suspicious process signal", f"{len(processes)} suspicious process signal(s) found.", "security:processes", {"processes": processes[:8]}))
    open_ports = (security.get("open_ports") or {}).get("open_ports") or []
    risky_ports = [item for item in open_ports if int(item.get("port") or 0) not in {80, 443, 8000}]
    if risky_ports:
        alerts.append(_alert("guardian", "security", 3, "Local ports are open", f"{len(risky_ports)} non-web local port(s) are open.", "security:ports", {"ports": risky_ports[:20]}))
    return alerts


def _task_alerts() -> list[dict[str, Any]]:
    alerts = []
    failed = task_queue.list_tasks(status="failed", limit=10)
    if failed:
        alerts.append(_alert("guardian", "agents", 4, "Agent task failed", f"{len(failed)} recent task(s) failed.", "tasks:failed", {"tasks": failed[:5]}))
    blocked = task_queue.list_tasks(status="blocked", limit=10)
    if blocked:
        alerts.append(_alert("guardian", "agents", 4, "Agent task needs a decision", f"{len(blocked)} task(s) are blocked.", "tasks:blocked", {"tasks": blocked[:5]}))
    cutoff = _aware_now() - dt.timedelta(minutes=float(config_value("guardian_stuck_task_minutes", 30)))
    stuck = []
    for task in task_queue.list_tasks(status="active", limit=100):
        timestamp = _parse_time(task.get("updated_at") or task.get("started_at"))
        if timestamp and timestamp < cutoff:
            stuck.append(task)
    if stuck:
        alerts.append(_alert("guardian", "agents", 4, "Agent task looks stuck", f"{len(stuck)} active task(s) have not updated recently.", "tasks:stuck", {"tasks": stuck[:5]}))
    return alerts


def _reminder_alerts() -> list[dict[str, Any]]:
    now = _aware_now()
    missed = []
    for reminder in app_integrations.list_reminders(include_done=False, limit=100):
        due = _parse_time(reminder.get("due_at"))
        if due and due < now:
            missed.append(reminder)
    if not missed:
        return []
    return [_alert("guardian", "reminders", 3, "Reminder is overdue", f"{len(missed)} reminder(s) are overdue.", "reminders:overdue", {"reminders": missed[:8]})]


def _evaluation_alerts(evaluation: dict[str, Any]) -> list[dict[str, Any]]:
    counts = evaluation.get("counts") or {}
    alerts = []
    if int(counts.get("slow_response") or 0) >= int(config_value("guardian_slow_response_count", 3)):
        alerts.append(_alert("guardian", "performance", 3, "Friday has been slow", f"{counts.get('slow_response')} slow responses recorded.", "eval:slow", {"counts": counts}))
    if int(counts.get("failed_tool") or 0) or int(counts.get("agent_failure") or 0):
        alerts.append(_alert("guardian", "tools", 4, "Tool or agent failures detected", "Recent failures need review.", "eval:failures", {"counts": counts}))
    return alerts


def _voice_alerts(voice: dict[str, Any]) -> list[dict[str, Any]]:
    mistakes = sum(int(data.get("mistakes") or 0) for data in (voice.get("backends") or {}).values())
    if mistakes < int(config_value("guardian_voice_mistake_threshold", 3)):
        return []
    aliases = ", ".join((voice.get("learned_aliases") or [])[:5])
    return [_alert("guardian", "voice", 3, "Voice reliability needs attention", f"{mistakes} STT mistake(s) recorded. Learned aliases: {aliases or 'none'}.", "voice:mistakes", {"voice": voice})]


def _phone_alerts(phone: dict[str, Any]) -> list[dict[str, Any]]:
    battery = phone.get("battery") or {}
    level = battery.get("level")
    if level is None or not battery.get("available"):
        return []
    if float(level) >= float(config_value("guardian_phone_battery_low_percent", 15)):
        return []
    return [_alert("guardian", "phone", 3, "Phone battery is low", f"Android battery is {level}%.", "phone:battery-low", {"battery": battery})]


def _alert(source: str, category: str, severity: int, title: str, message: str, dedupe_key: str, metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": source,
        "category": category,
        "severity": severity,
        "title": title,
        "message": message,
        "dedupe_key": dedupe_key,
        "metadata": metadata,
    }


def _summary(alerts: list[dict[str, Any]]) -> str:
    if not alerts:
        return "Guardian scan found no important issues."
    critical = [item for item in alerts if int(item.get("severity") or 0) >= 4]
    return f"Guardian found {len(alerts)} important signal(s), including {len(critical)} high-priority item(s)."


def _persist_run(summary: str, alerts: list[dict[str, Any]], stats: dict[str, Any]) -> int:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            "INSERT INTO guardian_runs(timestamp, summary, alert_count, alerts_json, stats_json) VALUES (?, ?, ?, ?, ?)",
            (_now(), summary, len(alerts), _json_dumps(alerts), _json_dumps(stats)),
        )
        return int(cursor.lastrowid)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "summary": str(row["summary"]),
        "alert_count": int(row["alert_count"]),
        "alerts": _json_loads(row["alerts_json"], []),
        "stats": _json_loads(row["stats_json"], {}),
    }


def _safe(fn: Callable[[], Any], default: Any) -> Any:
    try:
        return fn()
    except Exception as exc:
        return {"error": str(exc)} if isinstance(default, dict) else default


def _parse_time(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_aware_now().tzinfo)
    return parsed.astimezone()


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=True)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _aware_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).astimezone()


def _now() -> str:
    return _aware_now().isoformat(timespec="seconds")

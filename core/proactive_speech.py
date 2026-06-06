"""Controlled proactive speech for Friday voice sessions."""

from __future__ import annotations

import datetime as dt
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable

from core import app_integrations, task_queue
from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "proactive_speech.sqlite3"
_STOP = threading.Event()
_THREAD: threading.Thread | None = None
_LOCK = threading.Lock()
_LAST_STATUS = "stopped"

SpeakFn = Callable[[str], None]
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
            CREATE TABLE IF NOT EXISTS proactive_events (
                event_key TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                message TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                spoken_at TEXT NOT NULL
            )
            """
        )


def start_service(speak_fn: SpeakFn, log_fn: LogFn | None = None) -> bool:
    """Start the background proactive speech loop."""
    global _THREAD, _LAST_STATUS
    if not bool(config_value("proactive_speech_enabled", False)):
        _LAST_STATUS = "disabled"
        return False
    with _LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return True
        _STOP.clear()
        _THREAD = threading.Thread(target=_loop, args=(speak_fn, log_fn), name="FridayProactiveSpeech", daemon=True)
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
        "enabled": bool(config_value("proactive_speech_enabled", False)),
        "running": bool(thread and thread.is_alive() and not _STOP.is_set()),
        "status": _LAST_STATUS,
        "quiet_now": _quiet_hours_active(),
        "sources": _sources(),
        "max_per_hour": int(config_value("proactive_speech_max_per_hour", 3)),
    }


def collect_notifications(now: dt.datetime | None = None) -> list[dict[str, str]]:
    """Return pending proactive messages in priority order."""
    now = _aware(now)
    if not bool(config_value("proactive_speech_enabled", False)):
        return []
    if _quiet_hours_active(now):
        return []
    if not _hourly_quota_available(now):
        return []
    notifications: list[dict[str, str]] = []
    sources = _sources()
    if "reminders" in sources:
        notifications.extend(_due_reminder_notifications(now))
    if "calendar" in sources:
        notifications.extend(_upcoming_calendar_notifications(now))
    if "agent_tasks" in sources:
        notifications.extend(_agent_task_notifications(now))
    if "notifications" in sources:
        notifications.extend(_notification_center_notifications(now))
    return [item for item in notifications if not _already_spoken(item["key"])]


def mark_spoken(event_key: str, source: str, message: str, now: dt.datetime | None = None) -> None:
    init_db()
    stamp = _iso(_aware(now))
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO proactive_events(event_key, source, message, first_seen_at, spoken_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(event_key), str(source), str(message), stamp, stamp),
        )
    if str(source) == "notifications":
        try:
            from core import notification_center

            notice_id = int(str(event_key).split(":", 2)[1])
            notification_center.mark(notice_id, "read")
        except Exception:
            pass


def recent_events(limit: int = 20) -> list[dict[str, str]]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM proactive_events ORDER BY spoken_at DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
    return [{key: str(row[key]) for key in row.keys()} for row in rows]


def _loop(speak_fn: SpeakFn, log_fn: LogFn | None) -> None:
    global _LAST_STATUS
    interval = max(5.0, float(config_value("proactive_speech_poll_seconds", 30.0)))
    startup_delay = max(0.0, float(config_value("proactive_speech_startup_delay_seconds", 8.0)))
    if startup_delay:
        _STOP.wait(startup_delay)
    while not _STOP.is_set():
        try:
            _LAST_STATUS = "checking"
            for item in collect_notifications():
                if _STOP.is_set():
                    break
                message = item["message"]
                if log_fn:
                    log_fn("FRIDAY", message)
                speak_fn(message)
                mark_spoken(item["key"], item["source"], message)
                break
            _LAST_STATUS = "running"
        except Exception as exc:
            _LAST_STATUS = f"error: {exc.__class__.__name__}"
            if log_fn:
                log_fn("WARNING", f"[PROACTIVE] speech check failed ({exc})")
        _STOP.wait(interval)


def _due_reminder_notifications(now: dt.datetime) -> list[dict[str, str]]:
    lookahead = dt.timedelta(minutes=float(config_value("proactive_speech_reminder_lookahead_minutes", 2)))
    items = []
    for reminder in app_integrations.list_reminders(limit=50):
        due_at = _parse_time(reminder.get("due_at"))
        if due_at is None or due_at > now + lookahead:
            continue
        title = str(reminder.get("title") or "your reminder")
        items.append(
            {
                "key": f"reminder:{reminder.get('id')}:due",
                "source": "reminders",
                "message": f"Reminder: {title}.",
            }
        )
    return items


def _upcoming_calendar_notifications(now: dt.datetime) -> list[dict[str, str]]:
    lookahead = dt.timedelta(minutes=float(config_value("proactive_speech_calendar_lookahead_minutes", 10)))
    items = []
    for event in app_integrations.list_calendar_events(limit=50):
        start_at = _parse_time(event.get("start_at"))
        if start_at is None or start_at < now or start_at > now + lookahead:
            continue
        title = str(event.get("title") or "calendar event")
        minutes = max(0, round((start_at - now).total_seconds() / 60))
        when = "now" if minutes <= 0 else f"in {minutes} minutes"
        items.append(
            {
                "key": f"calendar:{event.get('id')}:start",
                "source": "calendar",
                "message": f"Calendar heads-up: {title} starts {when}.",
            }
        )
    return items


def _agent_task_notifications(now: dt.datetime) -> list[dict[str, str]]:
    threshold = int(config_value("proactive_speech_task_priority_threshold", 3))
    items: list[dict[str, str]] = []
    for task in task_queue.list_tasks(status="blocked", limit=20):
        items.append(
            {
                "key": f"task:{task.get('id')}:blocked",
                "source": "agent_tasks",
                "message": f"Task {task.get('id')} needs your approval: {task.get('title')}.",
            }
        )
    for task in task_queue.list_tasks(status="failed", limit=20):
        if int(task.get("priority") or 5) > threshold:
            continue
        completed = _parse_time(task.get("completed_at"))
        if completed and completed < now - dt.timedelta(hours=1):
            continue
        items.append(
            {
                "key": f"task:{task.get('id')}:failed",
                "source": "agent_tasks",
                "message": f"Important task failed: {task.get('title')}.",
            }
        )
    for task in task_queue.list_tasks(status="done", limit=20):
        if int(task.get("priority") or 5) > threshold:
            continue
        completed = _parse_time(task.get("completed_at"))
        if completed is None or completed < now - dt.timedelta(hours=1):
            continue
        items.append(
            {
                "key": f"task:{task.get('id')}:done",
                "source": "agent_tasks",
                "message": _done_task_message(task),
            }
        )
    return items


def _done_task_message(task: dict[str, Any]) -> str:
    if str(task.get("agent_id") or "") == "doctor":
        output = task.get("output") if isinstance(task.get("output"), dict) else {}
        report = output.get("diagnostic_report") if isinstance(output.get("diagnostic_report"), dict) else {}
        status = str(report.get("overall_status") or output.get("diagnostic_status") or "complete")
        summary = str(report.get("summary") or output.get("summary") or task.get("title") or "Diagnostics completed.")
        return f"Doctor diagnostics completed with status {status}: {summary[:420]}"
    return f"Task {task.get('id')} is done: {task.get('title')}."


def _notification_center_notifications(now: dt.datetime) -> list[dict[str, str]]:
    try:
        from core import notification_center

        pending = notification_center.pending_for_speech(limit=5)
    except Exception:
        return []
    items = []
    for notice in pending:
        items.append(
            {
                "key": f"notification:{notice.get('id')}:spoken",
                "source": "notifications",
                "message": f"{notice.get('title')}: {notice.get('message')}",
            }
        )
    return items


def _already_spoken(event_key: str) -> bool:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT 1 FROM proactive_events WHERE event_key=?", (str(event_key),)).fetchone()
    return bool(row)


def _hourly_quota_available(now: dt.datetime) -> bool:
    init_db()
    max_per_hour = int(config_value("proactive_speech_max_per_hour", 3))
    if max_per_hour <= 0:
        return False
    since = _iso(now - dt.timedelta(hours=1))
    with sqlite3.connect(DB_PATH) as conn:
        count = int(conn.execute("SELECT COUNT(*) FROM proactive_events WHERE spoken_at >= ?", (since,)).fetchone()[0])
    return count < max_per_hour


def _sources() -> set[str]:
    raw = str(config_value("proactive_speech_sources", "reminders,calendar,agent_tasks"))
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _quiet_hours_active(now: dt.datetime | None = None) -> bool:
    now = _aware(now)
    start = _parse_clock(str(config_value("proactive_speech_quiet_hours_start", "22:00")))
    end = _parse_clock(str(config_value("proactive_speech_quiet_hours_end", "08:00")))
    if start is None or end is None or start == end:
        return False
    current = now.time().replace(second=0, microsecond=0)
    if start < end:
        return start <= current < end
    return current >= start or current < end


def _parse_clock(value: str) -> dt.time | None:
    try:
        hour, minute = [int(part) for part in value.strip().split(":", 1)]
        return dt.time(hour=hour, minute=minute)
    except Exception:
        return None


def _parse_time(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    return _aware(parsed)


def _aware(value: dt.datetime | None = None) -> dt.datetime:
    current = value or dt.datetime.now().astimezone()
    if current.tzinfo is None:
        return current.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
    return current.astimezone()


def _iso(value: dt.datetime) -> str:
    return _aware(value).isoformat(timespec="seconds")

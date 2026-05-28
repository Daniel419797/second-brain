"""Event-driven nervous system for instant Friday awareness signals."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable

from core import app_integrations, capability_center, notification_center, pc_awareness, phone_bridge, task_queue
from core.config import DATA_DIR, ROOT_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "event_nervous_system.sqlite3"
_LOCK = threading.Lock()
_STOP = threading.Event()
_THREAD: threading.Thread | None = None
_STATE: dict[str, Any] = {}
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
            CREATE TABLE IF NOT EXISTS nervous_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                source TEXT NOT NULL,
                severity INTEGER NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                status TEXT NOT NULL,
                dedupe_key TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nervous_events_time ON nervous_events(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nervous_events_key ON nervous_events(dedupe_key, status)")


def start_service(log_fn: LogFn | None = None) -> bool:
    global _THREAD, _LAST_STATUS
    if not bool(config_value("event_nervous_system_enabled", True)):
        _LAST_STATUS = "disabled"
        return False
    with _LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return True
        _STOP.clear()
        _THREAD = threading.Thread(target=_loop, args=(log_fn,), name="FridayEventNervousSystem", daemon=True)
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
        "enabled": bool(config_value("event_nervous_system_enabled", True)),
        "running": bool(thread and thread.is_alive() and not _STOP.is_set()),
        "status": _LAST_STATUS,
        "state": dict(_STATE),
        "summary": summary(limit=5),
    }


def emit_event(
    event_type: str,
    title: str,
    summary: str = "",
    *,
    source: str = "friday",
    severity: int = 2,
    dedupe_key: str = "",
    metadata: dict[str, Any] | None = None,
    notify: bool = True,
) -> dict[str, Any]:
    init_db()
    key = _clean(dedupe_key) or f"{source}:{event_type}:{title}".lower()
    payload = {
        "source": _clean(source) or "friday",
        "category": _clean(event_type) or "event",
        "severity": _severity(severity),
        "title": _clean(title)[:300],
        "message": _clean(summary)[:2000],
        "dedupe_key": f"nervous:{key}",
        "metadata": metadata or {},
    }
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            "SELECT * FROM nervous_events WHERE dedupe_key=? AND status='open' ORDER BY id DESC LIMIT 1",
            (key,),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE nervous_events SET timestamp=?, severity=max(severity, ?), summary=?, metadata_json=? WHERE id=?",
                (_now(), payload["severity"], payload["message"], _json_dumps(metadata or {}), int(existing["id"])),
            )
            row = conn.execute("SELECT * FROM nervous_events WHERE id=?", (int(existing["id"]),)).fetchone()
            event = _row(row) | {"deduped": True}
        else:
            cursor = conn.execute(
                """
                INSERT INTO nervous_events(timestamp, event_type, source, severity, title, summary, status, dedupe_key, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?)
                """,
                (_now(), payload["category"], payload["source"], payload["severity"], payload["title"], payload["message"], key, _json_dumps(metadata or {})),
            )
            row = conn.execute("SELECT * FROM nervous_events WHERE id=?", (int(cursor.lastrowid),)).fetchone()
            event = _row(row) | {"deduped": False}
    if notify and payload["severity"] >= int(config_value("event_nervous_system_notify_min_severity", 3)):
        notification_center.add(**payload)
    return event


def run_once(*, notify: bool = True) -> dict[str, Any]:
    init_db()
    events: list[dict[str, Any]] = []
    for fn in [_watch_active_window, _watch_open_apps, _watch_downloads, _watch_battery, _watch_reminders, _watch_phone, _watch_agent_stuck]:
        try:
            events.extend(fn(notify=notify))
        except Exception as exc:
            events.append(
                emit_event(
                    "watcher_error",
                    "Nervous system watcher failed",
                    f"{fn.__name__}: {exc}",
                    source="event_nervous_system",
                    severity=3,
                    dedupe_key=f"watcher:{fn.__name__}",
                    metadata={"error": str(exc)},
                    notify=notify,
                )
            )
    return {"events": events, "count": len(events), "summary": f"Nervous system captured {len(events)} event(s)."}


def recent_events(limit: int = 50, event_type: str = "", status: str = "") -> list[dict[str, Any]]:
    init_db()
    where: list[str] = []
    params: list[Any] = []
    if event_type:
        where.append("event_type=?")
        params.append(_clean(event_type))
    if status:
        where.append("status=?")
        params.append(_clean(status))
    params.append(max(1, min(500, int(limit or 50))))
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM nervous_events {clause} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_row(row) for row in rows]


def summary(limit: int = 10) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT event_type, COUNT(*) FROM nervous_events GROUP BY event_type").fetchall()
        open_count = conn.execute("SELECT COUNT(*) FROM nervous_events WHERE status='open'").fetchone()[0]
    counts = {str(kind): int(count) for kind, count in rows}
    recent = recent_events(limit=limit)
    return {
        "counts": counts,
        "open_count": int(open_count),
        "recent": recent,
        "voice_summary": _voice_summary(recent, int(open_count)),
    }


def wipe_all() -> None:
    init_db()
    _STATE.clear()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM nervous_events")


def _loop(log_fn: LogFn | None) -> None:
    global _LAST_STATUS
    interval = max(2.0, float(config_value("event_nervous_system_interval_seconds", 8.0)))
    while not _STOP.is_set():
        try:
            _LAST_STATUS = "checking"
            result = run_once(notify=True)
            if log_fn and result["count"]:
                log_fn("INFO", f"[EVENTS] {result['summary']}")
            _LAST_STATUS = "running"
        except Exception as exc:
            _LAST_STATUS = f"error: {exc.__class__.__name__}"
            if log_fn:
                log_fn("WARNING", f"[EVENTS] nervous system failed ({exc})")
        _STOP.wait(interval)


def _watch_active_window(*, notify: bool) -> list[dict[str, Any]]:
    snapshot = pc_awareness.snapshot()
    active = str(snapshot.get("active_window") or "")
    previous = str(_STATE.get("active_window") or "")
    _STATE["active_window"] = active
    if active and previous and active != previous:
        return [
            emit_event(
                "app_focus_changed",
                "Active app changed",
                active,
                source="pc_awareness",
                severity=1,
                dedupe_key=f"active-window:{active}",
                metadata={"previous": previous, "current": active},
                notify=False,
            )
        ]
    return []


def _watch_open_apps(*, notify: bool) -> list[dict[str, Any]]:
    apps = {str(item.get("name") or "") for item in pc_awareness.running_apps(limit=120) if item.get("name")}
    previous = set(_STATE.get("running_apps") or [])
    _STATE["running_apps"] = sorted(apps)
    if not previous:
        return []
    events = []
    for name in sorted(apps - previous)[:8]:
        events.append(emit_event("app_opened", "App opened", name, source="pc_awareness", severity=1, dedupe_key=f"app-opened:{name}", notify=False))
    return events


def _watch_downloads(*, notify: bool) -> list[dict[str, Any]]:
    root = _downloads_dir()
    if not root.exists():
        return []
    seen = set(_STATE.get("downloads") or [])
    current = {str(path) for path in root.glob("*") if path.is_file()}
    _STATE["downloads"] = sorted(current)[-300:]
    if not seen:
        return []
    events = []
    for path_text in sorted(current - seen)[:8]:
        path = Path(path_text)
        events.append(
            emit_event(
                "file_downloaded",
                "New file downloaded",
                path.name,
                source="filesystem",
                severity=2,
                dedupe_key=f"download:{path.name}:{path.stat().st_size if path.exists() else 0}",
                metadata={"path": str(path)},
                notify=notify,
            )
        )
    return events


def _watch_battery(*, notify: bool) -> list[dict[str, Any]]:
    report = capability_center.maintenance_report(light=True)
    battery = ((report.get("health") or {}).get("battery") or {})
    percent = battery.get("percent")
    if percent is None or battery.get("plugged"):
        return []
    if float(percent) <= float(config_value("event_battery_low_percent", config_value("guardian_battery_low_percent", 20))):
        return [
            emit_event(
                "battery_low",
                "Battery is low",
                f"Laptop battery is {percent}%.",
                source="maintenance",
                severity=4,
                dedupe_key="battery-low",
                metadata={"battery": battery},
                notify=notify,
            )
        ]
    return []


def _watch_reminders(*, notify: bool) -> list[dict[str, Any]]:
    now = _aware_now()
    events = []
    for reminder in app_integrations.list_reminders(include_done=False, limit=100):
        due = _parse_time(reminder.get("due_at"))
        if not due or due > now:
            continue
        events.append(
            emit_event(
                "reminder_due",
                "Reminder due",
                str(reminder.get("title") or "Reminder"),
                source="reminders",
                severity=3,
                dedupe_key=f"reminder:{reminder.get('id')}",
                metadata={"reminder": reminder},
                notify=notify,
            )
        )
    return events[:10]


def _watch_phone(*, notify: bool) -> list[dict[str, Any]]:
    status = phone_bridge.status()
    connected = bool(status.get("adb_connected"))
    previous = _STATE.get("phone_connected")
    _STATE["phone_connected"] = connected
    if previous is not None and connected != bool(previous):
        return [
            emit_event(
                "phone_connected" if connected else "phone_disconnected",
                "Phone connection changed",
                "Android phone connected." if connected else "Android phone disconnected.",
                source="phone_bridge",
                severity=2,
                dedupe_key=f"phone-connected:{connected}",
                metadata={"phone": status},
                notify=notify,
            )
        ]
    return []


def _watch_agent_stuck(*, notify: bool) -> list[dict[str, Any]]:
    cutoff = _aware_now() - dt.timedelta(minutes=float(config_value("event_agent_stuck_minutes", config_value("guardian_stuck_task_minutes", 30))))
    events = []
    for task in task_queue.list_tasks(status="active", limit=100):
        updated = _parse_time(task.get("updated_at") or task.get("started_at"))
        if updated and updated < cutoff:
            events.append(
                emit_event(
                    "agent_stuck",
                    "Agent task may be stuck",
                    str(task.get("title") or "Task"),
                    source="task_queue",
                    severity=4,
                    dedupe_key=f"agent-stuck:{task.get('id')}",
                    metadata={"task": task},
                    notify=notify,
                )
            )
    return events[:10]


def _downloads_dir() -> Path:
    configured = str(config_value("event_nervous_system_downloads_dir", "Downloads") or "Downloads")
    path = Path(configured).expanduser()
    if not path.is_absolute():
        home = Path.home()
        path = home / configured
    if not path.exists():
        path = ROOT_DIR / configured
    return path


def _voice_summary(recent: list[dict[str, Any]], open_count: int) -> str:
    important = [item for item in recent if int(item.get("severity") or 0) >= 3]
    if not important:
        return f"Nervous system is watching. {open_count} open event(s)."
    top = important[0]
    return f"{top['title']}: {top['summary']}"


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "event_type": str(row["event_type"]),
        "source": str(row["source"]),
        "severity": int(row["severity"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "status": str(row["status"]),
        "dedupe_key": str(row["dedupe_key"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


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


def _severity(value: Any) -> int:
    try:
        return max(1, min(5, int(float(value))))
    except Exception:
        return 2


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


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

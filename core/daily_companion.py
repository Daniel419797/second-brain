"""Daily companion briefings and gentle check-ins."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable

from core import app_integrations, capability_center, goal_manager, notification_center, personal_life_os, project_autopilot, task_queue
from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "daily_companion.sqlite3"
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
            CREATE TABLE IF NOT EXISTS companion_briefs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                kind TEXT NOT NULL,
                summary TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_companion_briefs_time ON companion_briefs(timestamp)")


def start_service(log_fn: LogFn | None = None) -> bool:
    global _THREAD, _LAST_STATUS
    if not bool(config_value("daily_companion_enabled", True)):
        _LAST_STATUS = "disabled"
        return False
    with _LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return True
        _STOP.clear()
        _THREAD = threading.Thread(target=_loop, args=(log_fn,), name="FridayDailyCompanion", daemon=True)
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
        "enabled": bool(config_value("daily_companion_enabled", True)),
        "running": bool(thread and thread.is_alive() and not _STOP.is_set()),
        "status": _LAST_STATUS,
        "last_brief": recent_briefs(limit=1)[0] if recent_briefs(limit=1) else None,
        "recent": recent_briefs(limit=5),
    }


def morning_brief(*, notify: bool = True) -> dict[str, Any]:
    payload = _brief_payload()
    summary = _compose_brief(payload)
    brief = _persist("morning", summary, payload)
    if notify:
        notification_center.add(
            source="daily_companion",
            category="briefing",
            severity=3,
            title="Daily briefing ready",
            message=summary,
            dedupe_key=f"daily-brief:{_today_key()}",
            metadata={"brief_id": brief["id"]},
        )
    return brief | {"payload": payload}


def check_in(*, notify: bool = True) -> dict[str, Any]:
    payload = _brief_payload(light=True)
    next_action = (payload.get("next_action") or {}).get("summary") or "No clear next action."
    pending = int((payload.get("task_counts") or {}).get("pending") or 0)
    summary = f"Check-in: {next_action} {pending} pending task(s) are in the queue."
    brief = _persist("check_in", summary, payload)
    if notify:
        notification_center.add(
            source="daily_companion",
            category="check_in",
            severity=2,
            title="Friday check-in",
            message=summary,
            dedupe_key=f"daily-checkin:{_hour_key()}",
            metadata={"brief_id": brief["id"]},
        )
    return brief | {"payload": payload}


def recent_briefs(limit: int = 20, kind: str = "") -> list[dict[str, Any]]:
    init_db()
    where = ""
    params: list[Any] = []
    if kind:
        where = "WHERE kind=?"
        params.append(_clean(kind))
    params.append(max(1, min(100, int(limit or 20))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM companion_briefs {where} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM companion_briefs")


def _loop(log_fn: LogFn | None) -> None:
    global _LAST_STATUS
    interval = max(30.0, float(config_value("daily_companion_poll_seconds", 60.0)))
    last_slots: set[str] = set()
    while not _STOP.is_set():
        try:
            _LAST_STATUS = "checking"
            slot = _due_slot()
            if slot and slot not in last_slots:
                result = morning_brief() if slot == "morning" else check_in()
                last_slots.add(slot)
                if log_fn:
                    log_fn("INFO", f"[COMPANION] {result['summary']}")
            _LAST_STATUS = "running"
        except Exception as exc:
            _LAST_STATUS = f"error: {exc.__class__.__name__}"
            if log_fn:
                log_fn("WARNING", f"[COMPANION] check-in failed ({exc})")
        _STOP.wait(interval)


def _brief_payload(*, light: bool = False) -> dict[str, Any]:
    reminders = _safe(lambda: app_integrations.list_reminders(include_done=False, limit=12), [])
    overdue = [item for item in reminders if _is_due(item.get("due_at"))]
    return {
        "day_plan": _safe(personal_life_os.daily_plan, {}),
        "next_action": _safe(personal_life_os.what_should_i_do_next, {}),
        "goals": _safe(lambda: goal_manager.progress_summary(limit=5), {}),
        "task_counts": _safe(task_queue.counts, {}),
        "reminders": reminders,
        "overdue_reminders": overdue,
        "pc_health": _safe(lambda: capability_center.maintenance_report(light=True), {}),
        "project_reports": _safe(lambda: project_autopilot.recent_reports(limit=3), []),
        "security": {} if light else _safe(lambda: capability_center.security_overview(light=True), {}),
    }


def _compose_brief(payload: dict[str, Any]) -> str:
    next_action = (payload.get("next_action") or {}).get("summary") or "Start with the highest-priority task."
    overdue = payload.get("overdue_reminders") or []
    counts = payload.get("task_counts") or {}
    battery = (((payload.get("pc_health") or {}).get("health") or {}).get("battery") or {}).get("percent")
    pieces = [f"Today: {next_action}"]
    if overdue:
        pieces.append(f"{len(overdue)} overdue reminder(s).")
    if counts:
        pieces.append(f"Tasks: {counts.get('active', 0)} active, {counts.get('pending', 0)} pending.")
    if battery is not None:
        pieces.append(f"Battery {battery}%.")
    return " ".join(pieces)


def _persist(kind: str, summary: str, payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO companion_briefs(timestamp, kind, summary, payload_json) VALUES (?, ?, ?, ?)",
            (_now(), _clean(kind), _clean(summary)[:2000], _json_dumps(payload)),
        )
        row = conn.execute("SELECT * FROM companion_briefs WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def _due_slot() -> str:
    now = _aware_now()
    morning = str(config_value("daily_companion_morning_hour", "08:00"))
    if now.strftime("%H:%M") == morning:
        return "morning"
    checkins = [part.strip() for part in str(config_value("daily_companion_checkin_hours", "12:30,17:30")).split(",") if part.strip()]
    if now.strftime("%H:%M") in checkins:
        return f"check_in:{now.strftime('%H:%M')}"
    return ""


def _is_due(value: Any) -> bool:
    parsed = _parse_time(value)
    return bool(parsed and parsed <= _aware_now())


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


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "kind": str(row["kind"]),
        "summary": str(row["summary"]),
        "payload": _json_loads(row["payload_json"], {}),
    }


def _safe(fn: Callable[[], Any], default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


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


def _today_key() -> str:
    return _aware_now().strftime("%Y-%m-%d")


def _hour_key() -> str:
    return _aware_now().strftime("%Y-%m-%d-%H")


def _now() -> str:
    return _aware_now().isoformat(timespec="seconds")

"""Background automation daemon that evaluates useful trigger/action recipes."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import automation_builder, environment_awareness, notification_center, phone_mesh, project_watchdog, test_build_monitor
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "personal_automation_daemon.sqlite3"
_LOCK = threading.Lock()

DEFAULT_AUTOMATIONS = [
    {
        "name": "VS Code focus startup",
        "trigger": "active_vscode",
        "action": "suggest_start_workspace",
        "summary": "When VS Code opens, suggest starting API/dashboard for the active workspace.",
    },
    {
        "name": "Low battery saver",
        "trigger": "battery_low",
        "action": "suggest_reduce_brightness",
        "summary": "When battery is low, suggest reducing brightness and pausing heavy agents.",
    },
    {
        "name": "Test failure fix report",
        "trigger": "test_failed",
        "action": "create_fix_report",
        "summary": "When tests fail, create a fix-prep report instead of pretending success.",
    },
    {
        "name": "Phone connected sync",
        "trigger": "phone_connected",
        "action": "sync_phone_context",
        "summary": "When phone is connected, sync handoff context and recent companion state.",
    },
]


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
            CREATE TABLE IF NOT EXISTS automation_daemon_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                automation_name TEXT NOT NULL,
                trigger_name TEXT NOT NULL,
                action_name TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )


def install_defaults() -> dict[str, Any]:
    created = []
    for item in DEFAULT_AUTOMATIONS:
        created.append(automation_builder.create_from_text(item["summary"]))
    return {"created": created, "summary": f"Installed/evaluated {len(DEFAULT_AUTOMATIONS)} default daemon automation descriptions."}


def run_once(*, run_actions: bool = True) -> dict[str, Any]:
    init_db()
    env = _safe(lambda: environment_awareness.snapshot(force_refresh=True), {})
    monitor = _safe(test_build_monitor.status, {})
    watchdog = _safe(project_watchdog.status, {})
    phone = _safe(phone_mesh.status, {})
    matched = []
    for item in DEFAULT_AUTOMATIONS:
        if _matches(item["trigger"], env, monitor, watchdog, phone):
            matched.append(_record(item, env=env, monitor=monitor, watchdog=watchdog, phone=phone, run_actions=run_actions))
    recipe_matches = _safe(lambda: automation_builder.evaluate_triggers(run=run_actions), {"matched": []})
    return {
        "matched": matched,
        "recipe_matches": recipe_matches.get("matched") or [],
        "summary": f"{len(matched)} daemon automation(s) matched; {len(recipe_matches.get('matched') or [])} recipe(s) matched.",
    }


def status(limit: int = 12) -> dict[str, Any]:
    events = recent(limit=limit)
    return {"defaults": DEFAULT_AUTOMATIONS, "recent": events, "summary": f"{len(DEFAULT_AUTOMATIONS)} default daemon rule(s), {len(events)} recent event(s)."}


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM automation_daemon_events ORDER BY id DESC LIMIT ?", (max(1, min(200, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM automation_daemon_events")


def _matches(trigger: str, env: dict[str, Any], monitor: dict[str, Any], watchdog: dict[str, Any], phone: dict[str, Any]) -> bool:
    text = json.dumps({"env": env, "monitor": monitor, "watchdog": watchdog, "phone": phone}, ensure_ascii=True, default=str).lower()
    if trigger == "active_vscode":
        return "visual studio code" in text or "vscode" in text or "code.exe" in text
    if trigger == "battery_low":
        return "battery low" in text or '"battery_percent": 2' in text
    if trigger == "test_failed":
        return "failed" in text and ("test" in text or "build" in text)
    if trigger == "phone_connected":
        return "connected" in text or "android" in text
    return False


def _record(item: dict[str, str], **payload: Any) -> dict[str, Any]:
    result = _run_action(item["action"], item, payload) if payload.get("run_actions") else {"status": "matched", "summary": "Matched but not run."}
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO automation_daemon_events(timestamp, automation_name, trigger_name, action_name, status, summary, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), item["name"], item["trigger"], item["action"], result.get("status", "done"), result.get("summary", item["summary"]), _json_dumps(payload)),
        )
        row = conn.execute("SELECT * FROM automation_daemon_events WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def _run_action(action: str, item: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    notification_center.add(
        source="personal_automation_daemon",
        category="automation",
        severity=2 if action.startswith("suggest") else 3,
        title=item["name"],
        message=item["summary"],
        dedupe_key=f"automation-daemon:{item['trigger']}",
        metadata={"action": action},
    )
    if action == "sync_phone_context":
        try:
            phone_mesh.create_handoff("android", "Phone connected sync", {"source": "automation_daemon"})
        except Exception:
            pass
    return {"status": "done", "summary": item["summary"]}


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "automation_name": str(row["automation_name"]),
        "trigger": str(row["trigger_name"]),
        "action": str(row["action_name"]),
        "status": str(row["status"]),
        "summary": str(row["summary"]),
        "payload": _json_loads(row["payload_json"], {}),
    }


def _safe(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

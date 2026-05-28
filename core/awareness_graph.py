"""Realtime awareness graph for Friday's current situation.

The graph is a compact, persisted map of live signals Friday already knows:
PC/app state, project context, phone/app bridge, browser page/console, mission
state, approvals, tone, PC health, and recent errors. It is intentionally a
read-only situational model; action modules still own execution.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import (
    android_companion,
    approval_inbox,
    autonomous_debugger,
    browser_extension_bridge,
    capability_center,
    context_fusion,
    emotion_tone,
    environment_awareness,
    error_radar,
    mission_control,
    notification_center,
    pc_awareness,
    task_queue,
    test_build_monitor,
)
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "awareness_graph.sqlite3"
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
            CREATE TABLE IF NOT EXISTS awareness_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                summary TEXT NOT NULL,
                graph_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS awareness_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                kind TEXT NOT NULL,
                summary TEXT NOT NULL,
                severity INTEGER NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )


def refresh(*, force: bool = False) -> dict[str, Any]:
    init_db()
    graph = _build(force=force)
    summary = graph["summary"]
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO awareness_snapshots(timestamp, summary, graph_json) VALUES (?, ?, ?)",
            (_now(), summary, _json_dumps(graph)),
        )
        for signal in graph["signals"]:
            conn.execute(
                "INSERT INTO awareness_events(timestamp, kind, summary, severity, payload_json) VALUES (?, ?, ?, ?, ?)",
                (_now(), str(signal.get("kind") or "signal"), str(signal.get("summary") or "")[:1200], int(signal.get("severity") or 1), _json_dumps(signal)),
            )
        row = conn.execute("SELECT * FROM awareness_snapshots WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _snapshot_row(row)


def status() -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM awareness_snapshots ORDER BY id DESC LIMIT 1").fetchone()
    if row:
        return _snapshot_row(row)
    return refresh(force=False)


def answer(question: str = "what is happening right now") -> dict[str, Any]:
    graph = status()
    data = graph.get("graph") or {}
    signals = data.get("signals") or []
    top = signals[:5]
    lines = [data.get("summary") or "I have no major live signals right now."]
    for item in top:
        lines.append(f"- {item.get('summary')}")
    return {
        "question": question,
        "answer": "\n".join(lines),
        "snapshot": graph,
        "summary": lines[0],
    }


def recent_events(limit: int = 30) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM awareness_events ORDER BY id DESC LIMIT ?", (max(1, min(200, int(limit or 30))),)).fetchall()
    return [_event_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM awareness_events")
        conn.execute("DELETE FROM awareness_snapshots")


def _build(*, force: bool) -> dict[str, Any]:
    fused = _safe(lambda: context_fusion.snapshot(force_refresh=force), {})
    env = _safe(lambda: environment_awareness.snapshot(force_refresh=True) if force else environment_awareness.status(), {})
    pc = _safe(lambda: pc_awareness.snapshot(force_refresh=force), {})
    browser = _safe(browser_extension_bridge.latest_page_insight, {})
    phone = _safe(android_companion.status, {})
    missions = _safe(mission_control.status, {})
    approvals = _safe(approval_inbox.summary, {})
    tone = _safe(emotion_tone.summary, {})
    health = _safe(lambda: capability_center.maintenance_report(light=True), {})
    errors = {
        "debugger": _safe(autonomous_debugger.status, {}),
        "radar": _safe(error_radar.status, {}),
        "build_monitor": _safe(test_build_monitor.status, {}),
    }
    tasks = _safe(task_queue.counts, {})
    notifications = _safe(notification_center.summary, {})
    signals = _signals(fused, env, pc, browser, phone, missions, approvals, tone, health, errors, tasks, notifications)
    return {
        "timestamp": _now(),
        "active_app": _active_app(env, pc),
        "open_project": _open_project(env),
        "phone": phone,
        "browser": browser,
        "missions": missions,
        "approvals": approvals,
        "tone": tone,
        "pc_health": health,
        "errors": errors,
        "tasks": tasks,
        "notifications": notifications,
        "context_fusion": fused,
        "signals": signals,
        "summary": _summary(signals),
    }


def _signals(*parts: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    fused = parts[0] if isinstance(parts[0], dict) else {}
    out.extend([dict(item) for item in fused.get("observations") or []])
    _add_if(out, "approvals", parts[6].get("count"), f"{parts[6].get('count')} approval/decision item(s) are waiting.", 4)
    browser = parts[3]
    if browser.get("ok") and browser.get("console_errors"):
        _add_if(out, "browser_error", True, f"Browser page has {len(browser.get('console_errors') or [])} console warning/error event(s).", 4)
    errors = parts[9]
    debugger = errors.get("debugger") or {}
    if debugger.get("open_count"):
        _add_if(out, "debugger", True, f"{debugger.get('open_count')} debugger issue(s) are open.", 4)
    monitor = errors.get("build_monitor") or {}
    latest_report = (monitor.get("recent") or [{}])[0] if isinstance(monitor.get("recent"), list) else {}
    if latest_report.get("status") == "failed":
        _add_if(out, "build_failed", True, latest_report.get("summary") or "Latest build/test monitor check failed.", 4)
    health = parts[8]
    if health.get("suggestions"):
        _add_if(out, "pc_health", True, health.get("summary") or "PC health has suggestions.", 2)
    tasks = parts[10]
    if int(tasks.get("active") or 0) or int(tasks.get("blocked") or 0):
        _add_if(out, "task_queue", True, f"{tasks.get('active', 0)} active task(s), {tasks.get('blocked', 0)} blocked task(s).", 3)
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in sorted(out, key=lambda signal: int(signal.get("severity") or 1), reverse=True):
        key = f"{item.get('kind')}:{item.get('summary')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:20]


def _add_if(out: list[dict[str, Any]], kind: str, condition: Any, summary: str, severity: int) -> None:
    if condition:
        out.append({"kind": kind, "severity": severity, "summary": summary, "evidence": kind})


def _active_app(env: dict[str, Any], pc: dict[str, Any]) -> str:
    latest = env.get("latest") if isinstance(env.get("latest"), dict) else env
    return str(latest.get("active_window") or pc.get("active_window") or "")


def _open_project(env: dict[str, Any]) -> str:
    latest = env.get("latest") if isinstance(env.get("latest"), dict) else env
    return str(latest.get("open_project") or "")


def _summary(signals: list[dict[str, Any]]) -> str:
    if not signals:
        return "Awareness graph is quiet; no urgent live signal right now."
    return f"{len(signals)} live signal(s). Top: {signals[0].get('summary')}"


def _snapshot_row(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": int(row["id"]), "timestamp": str(row["timestamp"]), "summary": str(row["summary"]), "graph": _json_loads(row["graph_json"], {})}


def _event_row(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": int(row["id"]), "timestamp": str(row["timestamp"]), "kind": str(row["kind"]), "summary": str(row["summary"]), "severity": int(row["severity"]), "payload": _json_loads(row["payload_json"], {})}


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

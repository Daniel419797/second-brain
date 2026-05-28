"""Fuse live signals into one current-situation model."""

from __future__ import annotations

import datetime as dt
from typing import Any

from core import (
    android_companion,
    browser_extension_bridge,
    calendar_email_assistant,
    continuity_brain,
    emotion_tone,
    environment_awareness,
    mission_control,
    notification_center,
    pc_timeline,
    project_watchdog,
    task_queue,
)


def snapshot(*, force_refresh: bool = False) -> dict[str, Any]:
    env = _safe(lambda: environment_awareness.snapshot(force_refresh=True) if force_refresh else environment_awareness.status(), {})
    browser = _safe(browser_extension_bridge.latest_page_insight, {})
    phone = _safe(android_companion.status, {})
    tasks = _safe(task_queue.counts, {})
    missions = _safe(mission_control.status, {})
    notifications = _safe(notification_center.summary, {})
    tone = _safe(emotion_tone.summary, {})
    watchdog = _safe(project_watchdog.status, {})
    calendar_email = _safe(calendar_email_assistant.status, {})
    continuity = _safe(continuity_brain.status, {})
    timeline = _safe(pc_timeline.summary, {})
    observations = _observations(env, browser, phone, tasks, missions, notifications, tone, watchdog, continuity)
    return {
        "timestamp": _now(),
        "environment": env,
        "browser": browser,
        "phone": phone,
        "tasks": tasks,
        "missions": missions,
        "notifications": notifications,
        "tone": tone,
        "project_watchdog": watchdog,
        "calendar_email": calendar_email,
        "continuity": continuity,
        "pc_timeline": timeline,
        "observations": observations,
        "summary": _summary(observations),
    }


def status() -> dict[str, Any]:
    return snapshot(force_refresh=False)


def _observations(env: dict[str, Any], browser: dict[str, Any], phone: dict[str, Any], tasks: dict[str, Any], missions: dict[str, Any], notifications: dict[str, Any], tone: dict[str, Any], watchdog: dict[str, Any], continuity: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    latest_env = env.get("latest") if isinstance(env.get("latest"), dict) else env
    active = str(latest_env.get("active_window") or "")
    project = str(latest_env.get("open_project") or "")
    if project:
        out.append({"kind": "workspace", "severity": 2, "summary": f"Active project appears to be {project}.", "evidence": active})
    if "visual studio code" in active.lower() or "vscode" in active.lower():
        out.append({"kind": "coding_context", "severity": 2, "summary": "VS Code is active; Friday can load project context, run checks, or start the dashboard/API.", "evidence": active})
    battery = latest_env.get("battery") if isinstance(latest_env.get("battery"), dict) else {}
    percent = battery.get("percent") if battery else latest_env.get("battery_percent")
    plugged = battery.get("plugged") if battery else latest_env.get("plugged")
    if percent is not None and not plugged and float(percent) <= 25:
        out.append({"kind": "battery", "severity": 4, "summary": f"Laptop battery is low at {percent}%.", "evidence": "environment"})
    if browser.get("ok") and browser.get("console_errors"):
        out.append({"kind": "browser_console", "severity": 4, "summary": f"Current browser page has {len(browser.get('console_errors') or [])} warning/error event(s).", "evidence": browser.get("summary", "")})
    for device in phone.get("app_devices") or []:
        status = device.get("status") if isinstance(device, dict) else {}
        battery_value = status.get("battery") or status.get("battery_percent") or status.get("level")
        try:
            if battery_value is not None and float(battery_value) <= 20:
                out.append({"kind": "phone_battery", "severity": 3, "summary": f"{device.get('name') or 'Phone'} battery looks low at {battery_value}%.", "evidence": device.get("device_id")})
        except Exception:
            pass
    active_tasks = int(tasks.get("active") or 0) if isinstance(tasks, dict) else 0
    blocked_tasks = int(tasks.get("blocked") or 0) if isinstance(tasks, dict) else 0
    if active_tasks or blocked_tasks:
        out.append({"kind": "work_queue", "severity": 3 if blocked_tasks else 2, "summary": f"{active_tasks} active task(s), {blocked_tasks} blocked task(s).", "evidence": "task_queue"})
    if missions.get("blocked"):
        out.append({"kind": "mission_blocked", "severity": 4, "summary": "At least one autonomous mission is blocked.", "evidence": missions.get("summary", "")})
    if notifications.get("unread_count"):
        out.append({"kind": "notifications", "severity": 2, "summary": f"{notifications.get('unread_count')} unread Friday notification(s).", "evidence": notifications.get("voice_summary", "")})
    if tone.get("primary") in {"frustrated", "tired", "rushed", "worried"}:
        out.append({"kind": "tone", "severity": 3, "summary": f"User tone looks {tone.get('primary')}; replies should be concise and supportive.", "evidence": tone.get("summary", "")})
    latest_watchdog = watchdog.get("latest") if isinstance(watchdog.get("latest"), dict) else {}
    if latest_watchdog.get("status") == "attention":
        out.append({"kind": "project_health", "severity": 3, "summary": latest_watchdog.get("summary") or "Project watchdog found issues.", "evidence": "project_watchdog"})
    if continuity.get("open_count"):
        out.append({"kind": "continuity", "severity": 2, "summary": continuity.get("summary") or "Unfinished threads exist.", "evidence": "continuity_brain"})
    return sorted(out, key=lambda item: int(item.get("severity") or 0), reverse=True)[:12]


def _summary(observations: list[dict[str, Any]]) -> str:
    if not observations:
        return "Context fusion is quiet; no important combined signal right now."
    top = observations[0]
    return f"{len(observations)} live context signal(s). Top: {top['summary']}"


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

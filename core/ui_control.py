"""Dynamic UI control surface for desktop, browser, and app operators."""

from __future__ import annotations

from typing import Any

from core import app_operator_mastery, app_operators, app_state_memory, browser_extension_bridge, desktop_tasks, pc_awareness, visual_monitor

ACTION_SPECS: list[dict[str, Any]] = [
    {"id": "active_window", "label": "Active Window", "kind": "inspect", "inputs": []},
    {"id": "mouse_position", "label": "Mouse", "kind": "inspect", "inputs": []},
    {"id": "screen_size", "label": "Screen", "kind": "inspect", "inputs": []},
    {"id": "pc_awareness_snapshot", "label": "PC Snapshot", "kind": "inspect", "inputs": []},
    {"id": "find_app", "label": "Find App", "kind": "inspect", "inputs": ["target"]},
    {"id": "open_app", "label": "Open App", "kind": "app", "inputs": ["app"]},
    {"id": "focus_window", "label": "Focus", "kind": "app", "inputs": ["target"]},
    {"id": "screenshot", "label": "Screenshot", "kind": "inspect", "inputs": []},
    {"id": "inspect_screen", "label": "Inspect Screen", "kind": "vision", "inputs": ["instruction"]},
    {"id": "screen_step", "label": "One Step", "kind": "vision", "inputs": ["instruction"]},
    {"id": "inspect_browser", "label": "Browser DOM", "kind": "browser", "inputs": []},
    {"id": "inspect_accessibility", "label": "Accessibility", "kind": "desktop", "inputs": []},
    {"id": "open_browser_debug", "label": "Debug Browser", "kind": "browser", "inputs": ["url"]},
    {"id": "click", "label": "Click", "kind": "pointer", "inputs": ["x", "y"]},
    {"id": "double_click", "label": "Double Click", "kind": "pointer", "inputs": ["x", "y"]},
    {"id": "right_click", "label": "Right Click", "kind": "pointer", "inputs": ["x", "y"]},
    {"id": "move_mouse", "label": "Move", "kind": "pointer", "inputs": ["x", "y"]},
    {"id": "scroll", "label": "Scroll", "kind": "pointer", "inputs": ["amount"]},
    {"id": "type_text", "label": "Type", "kind": "keyboard", "inputs": ["text"]},
    {"id": "press_key", "label": "Key", "kind": "keyboard", "inputs": ["key"]},
    {"id": "hotkey", "label": "Hotkey", "kind": "keyboard", "inputs": ["keys"]},
    {"id": "wait", "label": "Wait", "kind": "timing", "inputs": ["seconds"]},
    {"id": "desktop_task_pause", "label": "Pause", "kind": "session", "inputs": ["session_id"]},
    {"id": "desktop_task_resume", "label": "Resume", "kind": "session", "inputs": ["session_id"]},
    {"id": "desktop_task_confirm", "label": "Confirm", "kind": "session", "inputs": ["session_id"]},
    {"id": "desktop_task_cancel", "label": "Cancel", "kind": "session", "inputs": ["session_id"]},
]

PC_ACTIONS = {item["id"] for item in ACTION_SPECS}


def status(app: str = "", *, limit: int = 12) -> dict[str, Any]:
    state = pc_awareness.snapshot()
    sessions = desktop_tasks.list_sessions(limit=max(1, min(50, int(limit or 12))))
    active_session = desktop_tasks.latest_session(statuses=desktop_tasks.ACTIVE_STATUSES)
    operators = app_operators.list_operators()
    discovered = _discovered_apps(state, limit=limit)
    return {
        "summary": _summary(state, sessions, active_session),
        "app": app,
        "active_window": state.get("active_window") or "",
        "stats": state.get("stats") or {},
        "operators": operators,
        "discovered_apps": discovered,
        "desktop_sessions": sessions,
        "active_session": active_session,
        "actions": ACTION_SPECS,
        "visual": _safe(visual_monitor.status, {}),
    }


def context(app: str = "", instruction: str = "") -> dict[str, Any]:
    selected = str(app or "").strip()
    payload = status(selected)
    if selected:
        payload["operator"] = app_operators.operator_context(selected)
        payload["mastery_plan"] = app_operator_mastery.plan(selected, instruction or "Inspect the current app state.")
        payload["memories"] = _safe(lambda: app_state_memory.search(app=selected, limit=12), [])
    else:
        payload["operator"] = {}
        payload["mastery_plan"] = {}
        payload["memories"] = []
    payload["browser"] = _safe(browser_extension_bridge.latest_page_insight, {})
    payload["summary"] = payload.get("operator", {}).get("summary") or payload["summary"]
    return payload


def execute(action: str, *, app: str = "", instruction: str = "", target: str = "", **inputs: Any) -> dict[str, Any]:
    key = _normalize_action(action)
    if key == "context":
        return context(app or target, instruction)
    if key == "plan":
        return app_operator_mastery.plan(app or target or "chrome", instruction)
    if key == "open_app":
        return app_operators.open_app(app or target)
    if key == "operate_app":
        return app_operators.operate(app or target, instruction or target, max_steps=_int(inputs.get("max_steps"), 12))
    if key not in PC_ACTIONS:
        return {"ok": False, "summary": f"Unknown UI control action: {action}"}
    payload = _pc_payload(key, app=app, instruction=instruction, target=target, **inputs)
    from tools import pc_control

    reply = pc_control.execute(payload)
    return {"ok": _reply_ok(reply), "action": key, "input": payload, "reply": reply, "summary": reply}


def task_instruction(app: str, instruction: str) -> str:
    app_text = str(app or "").strip()
    goal = str(instruction or "").strip()
    if not app_text:
        return goal
    return (
        f"Use the {app_text} UI. Goal: {goal}. "
        "Prefer DOM/accessibility context when available, verify visible progress after each step, "
        "and pause before sending, publishing, deleting, paying, or exposing credentials."
    )


def _pc_payload(action: str, *, app: str = "", instruction: str = "", target: str = "", **inputs: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"action": action}
    target_text = str(target or app or "").strip()
    if action == "find_app":
        payload["query"] = target_text
    elif action == "focus_window":
        payload["target"] = target_text
    elif action in {"inspect_screen", "screen_step"}:
        payload["instruction"] = str(instruction or target or "").strip()
    elif action == "open_browser_debug":
        payload["url"] = str(inputs.get("url") or target or "").strip()
    elif action in {"click", "double_click", "right_click", "move_mouse"}:
        x = _optional_float(inputs.get("x"))
        y = _optional_float(inputs.get("y"))
        if x is not None:
            payload["x"] = x
        if y is not None:
            payload["y"] = y
    elif action == "scroll":
        payload["amount"] = _int(inputs.get("amount") or inputs.get("delta") or target, -5)
    elif action == "type_text":
        payload["text"] = str(inputs.get("text") or target or "").strip()
    elif action == "press_key":
        payload["key"] = str(inputs.get("key") or target or "").strip()
    elif action == "hotkey":
        payload["keys"] = _keys(inputs.get("keys") or target)
    elif action == "wait":
        payload["seconds"] = _optional_float(inputs.get("seconds") or target) or 1
    elif action.startswith("desktop_task_"):
        payload["session_id"] = _int(inputs.get("session_id") or target, 0)
    elif target_text:
        payload["target"] = target_text
    if "limit" in inputs:
        payload["limit"] = _int(inputs.get("limit"), 40)
    return payload


def _discovered_apps(state: dict[str, Any], *, limit: int = 12) -> list[dict[str, Any]]:
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for bucket in ("running_apps", "desktop_apps", "shortcuts", "installed_apps"):
        for item in state.get(bucket) or []:
            name = str(item.get("name") or "").strip()
            key = name.lower()
            if not name or key in seen:
                continue
            seen.add(key)
            rows.append({"name": name, "source": item.get("source") or bucket, "launch_target": item.get("launch_target") or item.get("path") or item.get("exe") or ""})
            if len(rows) >= max(1, min(50, int(limit or 12))):
                return rows
    return rows


def _summary(state: dict[str, Any], sessions: list[dict[str, Any]], active_session: dict[str, Any] | None) -> str:
    active = state.get("active_window") or "no active window"
    if active_session:
        return f"UI control ready. Active window: {active}. Desktop session #{active_session.get('id')} is {active_session.get('status')}."
    return f"UI control ready. Active window: {active}. {len(sessions)} recent desktop session(s)."


def _normalize_action(action: str) -> str:
    text = str(action or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "open": "open_app",
        "operate": "operate_app",
        "task": "operate_app",
        "inspect": "inspect_screen",
        "step": "screen_step",
        "dom": "inspect_browser",
        "accessibility": "inspect_accessibility",
        "pause": "desktop_task_pause",
        "resume": "desktop_task_resume",
        "confirm": "desktop_task_confirm",
        "cancel": "desktop_task_cancel",
    }
    return aliases.get(text, text)


def _reply_ok(reply: str) -> bool:
    lowered = str(reply or "").lower()
    return not any(marker in lowered for marker in ("failed", "unavailable", "could not", "unknown action", "permission blocked"))


def _keys(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value or "").replace("+", ",").split(",") if part.strip()]


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _optional_float(value: Any) -> float | None:
    try:
        text = str(value).strip()
        return float(text) if text else None
    except Exception:
        return None


def _safe(func: Any, default: Any) -> Any:
    try:
        return func()
    except Exception:
        return default

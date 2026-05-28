"""Screenshot analysis and desktop action planning."""

from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Any

try:
    import requests
except Exception:  # pragma: no cover - dependency may be absent in minimal installs
    requests = None

from core import app_accessibility, browser_dom, desktop_tasks, pc_awareness, visual_monitor
from core.config import config_value

SAFE_SCREEN_ACTIONS = {
    "move_mouse",
    "click",
    "double_click",
    "right_click",
    "scroll",
    "type_text",
    "press_key",
    "hotkey",
    "wait",
    "open_app",
    "dom_click",
    "dom_type",
    "dom_select",
    "dom_scroll",
    "dom_navigate",
    "dom_press",
    "uia_invoke",
    "uia_focus",
    "uia_set_text",
}


def run_desktop_task(instruction: str, *, max_steps: int | None = None, session_id: int | None = None) -> str:
    """Run a bounded screenshot-plan-act-check loop for a desktop task."""
    goal = str(instruction or "").strip()
    if not goal:
        return "Tell me what desktop task to perform."
    if not bool(config_value("desktop_vision_allow_actions", True)):
        return "Desktop task actions are disabled in config."

    absolute_limit = max(1, min(200, int(config_value("desktop_task_absolute_max_steps", 80))))
    step_limit = max(1, min(absolute_limit, int(max_steps or config_value("desktop_task_max_steps", 5))))
    no_progress_limit = max(1, min(5, int(config_value("desktop_task_no_progress_limit", 2))))
    recovery_limit = max(0, min(6, int(config_value("desktop_task_recovery_limit", 3))))
    delay = max(0.0, min(5.0, float(config_value("desktop_task_step_delay_seconds", 0.6))))
    session_id = int(session_id or desktop_tasks.create_session(goal, max_steps=step_limit))
    session = desktop_tasks.get_session(session_id)
    if not session:
        return "Desktop task session was not found."
    if session["status"] == "paused":
        return f"Desktop task #{session_id} is paused at step {session['current_step']}."
    if session["status"] == "waiting_confirmation":
        return f"Desktop task #{session_id} is waiting for confirmation: {session['pending_reason']}"
    if session["status"] in desktop_tasks.FINAL_STATUSES:
        return f"Desktop task #{session_id} is already {session['status']}."

    step_limit = max(step_limit, int(session["max_steps"]))
    history = desktop_tasks.get_steps(session_id, limit=500)
    last_signature = str(session.get("last_signature") or "")
    last_progress = str(session.get("last_progress") or "")
    no_progress_count = int(session.get("no_progress_count") or 0)
    recovery_count = int(session.get("recovery_count") or 0)
    started = time.perf_counter()

    for step in range(int(session["current_step"]) + 1, step_limit + 1):
        session = desktop_tasks.get_session(session_id) or {}
        if session.get("status") == "paused":
            return _desktop_task_summary("paused", goal, history, f"Paused at step {step - 1}.", started, session_id=session_id)
        if session.get("status") == "waiting_confirmation":
            return _desktop_task_summary("waiting_confirmation", goal, history, str(session.get("pending_reason") or ""), started, session_id=session_id)
        if session.get("status") in desktop_tasks.FINAL_STATUSES:
            return _desktop_task_summary(str(session.get("status")), goal, history, "Session already ended.", started, session_id=session_id)

        screenshot = _capture_screenshot()
        if not screenshot.get("path"):
            reason = str(screenshot.get("message") or "I could not capture the screen.")
            desktop_tasks.finish_session(session_id, "stopped")
            return _desktop_task_summary("stopped", goal, history, reason, started, session_id=session_id)

        path = Path(str(screenshot["path"]))
        contexts = _collect_control_context(goal)
        handoff = _human_handoff_reason(goal, contexts)
        if handoff:
            history.append({"step": step, "status": "needs_user", "progress": handoff, "screenshot": str(path)})
            desktop_tasks.append_step(session_id, step_number=step, status="needs_user", progress=handoff, screenshot=str(path), details={"contexts": contexts})
            desktop_tasks.update_session(session_id, status="paused", pending_reason=handoff)
            return _desktop_task_summary("paused", goal, history, handoff, started, session_id=session_id)

        plan = _plan_desktop_step(path, goal, history, step, step_limit, contexts=contexts)
        status = str(plan.get("status") or "").strip().lower()
        progress = str(plan.get("progress") or plan.get("reason") or "").strip()
        if not status:
            status = "blocked"
        _log_desktop_step(step, status, progress)

        if status in {"complete", "done", "success"}:
            entry = {"step": step, "status": "complete", "progress": progress, "screenshot": str(path)}
            history.append(entry)
            desktop_tasks.append_step(session_id, step_number=step, status="complete", progress=progress, screenshot=str(path), details={"plan": plan, "contexts": contexts})
            desktop_tasks.finish_session(session_id, "completed")
            return _desktop_task_summary("completed", goal, history, progress or "The task appears complete.", started, session_id=session_id)

        if status in {"blocked", "needs_user", "need_user", "unsafe", "failed"}:
            reason = str(plan.get("reason") or progress or "I could not safely continue.").strip()
            history.append({"step": step, "status": "blocked", "progress": reason, "screenshot": str(path)})
            desktop_tasks.append_step(session_id, step_number=step, status="blocked", progress=reason, screenshot=str(path), details={"plan": plan, "contexts": contexts})
            desktop_tasks.finish_session(session_id, "stopped")
            return _desktop_task_summary("stopped", goal, history, reason, started, session_id=session_id)

        action = plan.get("action") if isinstance(plan.get("action"), dict) else {}
        if status == "wait" and not action:
            action = {"action": "wait", "seconds": plan.get("seconds") or 1}
        action = _normalize_safe_action(action)
        if not action:
            reason = str(plan.get("reason") or "The planner did not provide a safe next action.").strip()
            history.append({"step": step, "status": "blocked", "progress": reason, "screenshot": str(path)})
            desktop_tasks.append_step(session_id, step_number=step, status="blocked", progress=reason, screenshot=str(path), details={"plan": plan, "contexts": contexts})
            desktop_tasks.finish_session(session_id, "stopped")
            return _desktop_task_summary("stopped", goal, history, reason, started, session_id=session_id)

        signature = json.dumps(action, sort_keys=True)
        if signature == last_signature and progress == last_progress:
            no_progress_count += 1
        else:
            no_progress_count = 0
        if no_progress_count >= no_progress_limit:
            recovery = _recovery_action(history, recovery_count)
            if recovery and recovery_count < recovery_limit:
                result = _execute_safe_action(recovery)
                recovery_count += 1
                no_progress_count = 0
                entry = {
                    "step": step,
                    "status": "recovery",
                    "progress": "Trying a recovery action after repeated no-progress.",
                    "action": recovery,
                    "result": result,
                    "screenshot": str(path),
                }
                history.append(entry)
                desktop_tasks.append_step(
                    session_id,
                    step_number=step,
                    status="recovery",
                    progress=entry["progress"],
                    action=recovery,
                    result=result,
                    screenshot=str(path),
                    details={"plan": plan, "contexts": contexts},
                )
                desktop_tasks.update_session(session_id, no_progress_count=0, recovery_count=recovery_count, last_signature="", last_progress="")
                if delay:
                    time.sleep(delay)
                continue
            reason = "I stopped because the same action was repeating without visible progress."
            history.append({"step": step, "status": "no_progress", "progress": reason, "action": action, "screenshot": str(path)})
            desktop_tasks.append_step(session_id, step_number=step, status="no_progress", progress=reason, action=action, screenshot=str(path), details={"plan": plan, "contexts": contexts})
            desktop_tasks.finish_session(session_id, "stopped")
            return _desktop_task_summary("stopped", goal, history, reason, started, session_id=session_id)

        risk = _risky_action_reason(goal, plan, action)
        if risk:
            desktop_tasks.record_pending_confirmation(session_id, action=action, reason=risk)
            history.append({"step": step, "status": "waiting_confirmation", "progress": risk, "action": action, "screenshot": str(path)})
            desktop_tasks.append_step(session_id, step_number=step, status="waiting_confirmation", progress=risk, action=action, screenshot=str(path), risk=risk, details={"plan": plan, "contexts": contexts})
            return _desktop_task_summary("waiting_confirmation", goal, history, risk, started, session_id=session_id)

        result = _execute_safe_action(action)
        entry = {"step": step, "status": "action", "progress": progress, "action": action, "result": result, "screenshot": str(path)}
        history.append(entry)
        desktop_tasks.append_step(session_id, step_number=step, status="action", progress=progress, action=action, result=result, screenshot=str(path), details={"plan": plan, "contexts": contexts})
        desktop_tasks.remember_ui_element(goal, plan, action)
        if _action_failed(result):
            recovery = _recovery_action(history, recovery_count)
            if recovery and recovery_count < recovery_limit:
                recovery_result = _execute_safe_action(recovery)
                recovery_count += 1
                recovery_entry = {
                    "step": step,
                    "status": "recovery",
                    "progress": "Trying a recovery action after a failed desktop action.",
                    "action": recovery,
                    "result": recovery_result,
                    "screenshot": str(path),
                }
                history.append(recovery_entry)
                desktop_tasks.append_step(
                    session_id,
                    step_number=step,
                    status="recovery",
                    progress=recovery_entry["progress"],
                    action=recovery,
                    result=recovery_result,
                    screenshot=str(path),
                    details={"failed_action": action, "failed_result": result, "contexts": contexts},
                )
                desktop_tasks.update_session(session_id, recovery_count=recovery_count)
                if delay:
                    time.sleep(delay)
                continue
            failures = sum(1 for item in history[-2:] if _action_failed(str(item.get("result") or "")))
            if failures >= 2:
                desktop_tasks.finish_session(session_id, "stopped")
                return _desktop_task_summary("stopped", goal, history, "Two desktop actions failed in a row.", started, session_id=session_id)
        last_signature = signature
        last_progress = progress
        desktop_tasks.update_session(
            session_id,
            no_progress_count=no_progress_count,
            recovery_count=recovery_count,
            last_signature=last_signature,
            last_progress=last_progress,
        )
        if delay:
            time.sleep(delay)

    if _should_extend_session(history, no_progress_count) and step_limit < absolute_limit:
        new_limit = min(absolute_limit, step_limit + max(1, int(config_value("desktop_task_extend_by_steps", 5))))
        desktop_tasks.update_session(session_id, max_steps=new_limit)
        desktop_tasks.append_step(
            session_id,
            step_number=step_limit,
            status="extended",
            progress=f"Extending desktop task session from {step_limit} to {new_limit} steps because visible progress is still being made.",
        )
        return run_desktop_task(goal, session_id=session_id, max_steps=new_limit)

    reason = "I reached the desktop task step limit before I could verify completion."
    desktop_tasks.finish_session(session_id, "stopped")
    return _desktop_task_summary("stopped", goal, history, reason, started, session_id=session_id)


def pause_desktop_task(session_id: int | None = None) -> str:
    session = desktop_tasks.pause_session(session_id)
    if not session:
        return "No active desktop task is available to pause."
    return f"Desktop task #{session['id']} paused at step {session['current_step']}."


def resume_desktop_task(session_id: int | None = None) -> str:
    session = desktop_tasks.get_session(session_id) if session_id else desktop_tasks.latest_session(statuses={"paused", "active", "waiting_confirmation"})
    if not session:
        return "No desktop task is available to resume."
    if session["status"] == "waiting_confirmation":
        return f"Desktop task #{session['id']} is waiting for confirmation: {session['pending_reason']}"
    desktop_tasks.update_session(int(session["id"]), status="active", pending_reason="")
    return run_desktop_task(str(session["goal"]), session_id=int(session["id"]), max_steps=int(session["max_steps"]))


def confirm_desktop_task(session_id: int | None = None) -> str:
    session = desktop_tasks.get_session(session_id) if session_id else desktop_tasks.latest_session(statuses={"waiting_confirmation"})
    if not session or session["status"] != "waiting_confirmation":
        return "No desktop task is waiting for confirmation."
    action = session.get("pending_action") or {}
    if not action:
        return "No pending desktop action was found."
    result = _execute_safe_action(action)
    step = int(session["current_step"]) + 1
    desktop_tasks.append_step(
        int(session["id"]),
        step_number=step,
        status="confirmed_action",
        progress=str(session.get("pending_reason") or "Confirmed by user."),
        action=action,
        result=result,
        risk="confirmed",
        details={"confirmed": True},
    )
    if _action_failed(result):
        desktop_tasks.finish_session(int(session["id"]), "stopped")
        return f"Desktop task #{session['id']} stopped after confirmed action failed: {result}"
    desktop_tasks.clear_pending_confirmation(int(session["id"]))
    return run_desktop_task(str(session["goal"]), session_id=int(session["id"]), max_steps=int(session["max_steps"]))


def cancel_desktop_task(session_id: int | None = None) -> str:
    session = desktop_tasks.cancel_session(session_id)
    if not session:
        return "No active desktop task is available to cancel."
    return f"Desktop task #{session['id']} cancelled."


def inspect_screen(instruction: str = "", *, act: bool = False) -> str:
    """Capture the visible screen, analyze it, and optionally run one safe UI action."""
    start = time.perf_counter()
    screenshot = _capture_screenshot()
    if not screenshot.get("path"):
        return str(screenshot.get("message") or "I could not capture the screen.")

    path = Path(str(screenshot["path"]))
    analysis = analyze_screenshot(path, instruction=instruction)
    action_result = ""
    if act:
        action_result = _maybe_execute_action(analysis, instruction)

    duration_ms = round((time.perf_counter() - start) * 1000)
    prefix = f"Screen inspected in {duration_ms}ms. "
    if action_result:
        return prefix + analysis + "\nAction result: " + action_result
    return prefix + analysis


def analyze_screenshot(path: str | Path, *, instruction: str = "") -> str:
    """Use an optional free/cheap vision provider, then fall back to local screen metadata."""
    image_path = Path(path)
    provider = str(config_value("desktop_vision_provider", "gemini")).lower()
    if provider == "gemini":
        gemini = _analyze_with_gemini(image_path, instruction)
        if gemini:
            return gemini
    return _local_screen_summary(image_path, instruction)


def _capture_screenshot() -> dict[str, str]:
    try:
        from tools import pc_control

        result = pc_control.execute({"action": "screenshot"})
    except Exception as exc:
        return {"message": f"Screenshot failed: {exc}"}
    prefix = "Screenshot saved to "
    if not str(result).startswith(prefix):
        return {"message": str(result)}
    path = str(result)[len(prefix) :].rstrip(".")
    return {"path": path, "message": str(result)}


def _analyze_with_gemini(path: Path, instruction: str) -> str:
    return _ask_gemini_vision(path, _vision_prompt(instruction), max_tokens=int(config_value("desktop_vision_max_output_tokens", 400)))


def _ask_gemini_vision(path: Path, prompt: str, *, max_tokens: int) -> str:
    if requests is None or not path.exists():
        return ""
    api_key = os.getenv(str(config_value("gemini_api_key_env", "GEMINI_API_KEY")))
    if _placeholder(api_key):
        return ""
    model = str(config_value("desktop_vision_model", config_value("gemini_model", "gemini-2.0-flash-lite")))
    base_url = str(config_value("gemini_base_url", "https://generativelanguage.googleapis.com/v1beta")).rstrip("/")
    timeout = int(config_value("desktop_vision_timeout", config_value("gemini_timeout", 60)))
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": _mime_type(path),
                            "data": base64.b64encode(path.read_bytes()).decode("ascii"),
                        }
                    },
                ],
            }
        ],
        "generationConfig": {
            "temperature": float(config_value("desktop_vision_temperature", 0.1)),
            "maxOutputTokens": int(max_tokens),
        },
    }
    try:
        response = requests.post(f"{base_url}/models/{model}:generateContent?key={api_key}", json=payload, timeout=timeout)
        response.raise_for_status()
        return _extract_gemini_text(response.json())
    except Exception:
        return ""


def _plan_desktop_step(path: Path, goal: str, history: list[dict[str, Any]], step: int, max_steps: int, *, contexts: dict[str, Any] | None = None) -> dict[str, Any]:
    prompt = _desktop_task_prompt(goal, history, step, max_steps, contexts=contexts or {})
    text = _ask_gemini_vision(path, prompt, max_tokens=int(config_value("desktop_task_max_output_tokens", 700)))
    if not text:
        summary = _local_screen_summary(path, goal)
        return {
            "status": "blocked",
            "reason": (
                "I need a configured vision provider to operate apps autonomously. "
                + summary
            ),
        }
    plan = _extract_plan_json(text)
    if not plan:
        return {"status": "blocked", "reason": "The vision planner did not return a usable action plan."}
    return plan


def _desktop_task_prompt(goal: str, history: list[dict[str, Any]], step: int, max_steps: int, *, contexts: dict[str, Any] | None = None) -> str:
    compact_history = [
        {
            "step": item.get("step"),
            "status": item.get("status"),
            "progress": item.get("progress"),
            "action": item.get("action"),
            "result": item.get("result"),
        }
        for item in history[-4:]
    ]
    element_hints = desktop_tasks.element_hints(goal, limit=6)
    control_contexts = _compact_contexts(contexts or {})
    return (
        "You are Friday's desktop control planner. Use screenshot evidence plus any PC inventory, browser DOM, or Windows accessibility context to decide one safe next step.\n"
        f"Goal: {goal}\n"
        f"Step: {step} of {max_steps}\n"
        f"Recent history JSON: {json.dumps(compact_history, ensure_ascii=True)}\n\n"
        f"UI element memory JSON: {json.dumps(element_hints, ensure_ascii=True)}\n\n"
        f"Control context JSON: {json.dumps(control_contexts, ensure_ascii=True)}\n\n"
        "Rules:\n"
        "- Prefer browser DOM actions for websites when a matching DOM selector is available.\n"
        "- Prefer UI Automation actions for native apps when a reliable automation_id or name is available.\n"
        "- Use PC awareness context to identify which apps are open/installed and which Desktop/Start Menu shortcuts can launch a complex app.\n"
        "- Use screenshot coordinates only when DOM/UIA context is unavailable or insufficient.\n"
        "- Do not assume success; each action will be verified from a new screenshot/context pass.\n"
        "- Use exactly one action at a time, then the program will take another screenshot.\n"
        "- Allowed actions: open_app, move_mouse, click, double_click, right_click, scroll, type_text, press_key, hotkey, wait, dom_click, dom_type, dom_select, dom_scroll, dom_navigate, dom_press, uia_invoke, uia_focus, uia_set_text.\n"
        "- For open_app, include target. For clicks, include x and y coordinates. For typing, include text. For hotkeys, include keys or target.\n"
        "- For dom_* actions, include selector. For uia_* actions, include name, automation_id, or control_type.\n"
        "- If the goal is already complete, set status to complete and no action.\n"
        "- If blocked, unsafe, logged out, CAPTCHA, credential entry, ambiguous, or a destructive final confirmation is needed, set status to blocked.\n"
        "- Do not click final Send, Delete, Purchase, Pay, Submit, or Confirm buttons unless the user's goal explicitly authorizes that exact final action.\n\n"
        "Return only this JSON, with no markdown:\n"
        "{"
        '"status":"action|wait|complete|blocked",'
        '"progress":"short visible progress note",'
        '"reason":"why this is the next safe step",'
        '"action":{"action":"click","x":100,"y":200}'
        "}\n"
        "If status is complete or blocked, use an empty action object."
    )


def _vision_prompt(instruction: str) -> str:
    intent = str(instruction or "").strip()
    action_clause = (
        "If one visible desktop action would satisfy the instruction, add a final line starting with ACTION_JSON: "
        "followed by JSON for one safe action. Allowed actions are move_mouse, click, double_click, right_click, "
        "scroll, type_text, press_key, hotkey, wait. Use x/y coordinates when clicking."
    )
    if not bool(config_value("desktop_vision_allow_actions", True)):
        action_clause = "Do not propose actions; describe the screen only."
    return (
        "You are Friday's desktop vision module. Describe the visible screen concisely, focusing on app/window, "
        "important controls, and anything relevant to the user's instruction. "
        f"Instruction: {intent or 'inspect the screen'}.\n{action_clause}"
    )


def _local_screen_summary(path: Path, instruction: str) -> str:
    active = ""
    browser = browser_dom.context_summary(limit=12)
    accessibility = app_accessibility.context_summary(limit=12)
    try:
        from tools import pc_control

        active = pc_control.execute({"action": "active_window"})
    except Exception:
        active = ""
    details = [f"Screenshot saved to {path}."]
    if active:
        details.append(active)
    if browser.get("available"):
        details.append(f"Browser DOM: {browser.get('title') or browser.get('url')} with {len(browser.get('elements') or [])} controls.")
    if accessibility.get("available"):
        details.append(f"Accessibility tree: {accessibility.get('window_name') or 'active window'} with {len(accessibility.get('elements') or [])} controls.")
    if instruction:
        details.append("No vision API is configured; I can still use browser DOM or Windows accessibility context when available.")
    else:
        details.append("No vision API is configured, so I captured the screen for inspection.")
    return " ".join(details)


def _maybe_execute_action(analysis: str, instruction: str) -> str:
    if not bool(config_value("desktop_vision_allow_actions", True)):
        return "Vision actions are disabled in config."
    action = _extract_action_json(analysis)
    if not action:
        return ""
    action = _normalize_safe_action(action)
    if not action:
        return "Vision action blocked: missing or unsafe action."
    return _execute_safe_action(action)


def _extract_action_json(text: str) -> dict[str, Any]:
    data = _extract_json_object(str(text or ""), marker="ACTION_JSON:")
    return data if isinstance(data, dict) else {}


def _extract_plan_json(text: str) -> dict[str, Any]:
    data = _extract_json_object(str(text or ""), marker="DESKTOP_STEP_JSON:")
    if not data:
        data = _extract_json_object(str(text or ""), marker="")
    return data if isinstance(data, dict) else {}


def _extract_json_object(text: str, *, marker: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    start_at = 0
    if marker:
        found = raw.lower().find(marker.lower())
        if found < 0:
            return {}
        start_at = found + len(marker)
    brace = raw.find("{", start_at)
    if brace < 0:
        return {}
    depth = 0
    in_string = False
    escape = False
    for index in range(brace, len(raw)):
        char = raw[index]
        if escape:
            escape = False
            continue
        if char == "\\" and in_string:
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(raw[brace : index + 1])
                except Exception:
                    return {}
                return parsed if isinstance(parsed, dict) else {}
    return {}


def _normalize_safe_action(action: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(action, dict):
        return {}
    action_name = str(action.get("action") or "").strip().lower()
    if action_name not in SAFE_SCREEN_ACTIONS:
        return {}
    normalized = dict(action)
    normalized["action"] = action_name
    if action_name in {"click", "double_click", "right_click", "move_mouse"}:
        if normalized.get("x") is None or normalized.get("y") is None:
            return {}
    if action_name in {"dom_click", "dom_type", "dom_select"} and not normalized.get("selector"):
        return {}
    if action_name == "dom_navigate":
        url = str(normalized.get("url") or normalized.get("target") or "")
        if not url.startswith(("http://", "https://")):
            return {}
    if action_name == "open_app" and not (normalized.get("target") or normalized.get("name")):
        return {}
    if action_name in {"uia_invoke", "uia_focus", "uia_set_text"}:
        if not (normalized.get("name") or normalized.get("automation_id") or normalized.get("target") or normalized.get("control_type")):
            return {}
    return normalized


def _execute_safe_action(action: dict[str, Any]) -> str:
    action_name = str(action.get("action") or "").lower()
    if action_name.startswith("dom_"):
        return browser_dom.execute_dom_action(action)
    if action_name.startswith("uia_"):
        return app_accessibility.execute_uia_action(action)
    try:
        from tools import pc_control

        return pc_control.execute(action)
    except Exception as exc:
        return f"Vision action failed: {exc}"


def _action_failed(result: str) -> bool:
    lowered = str(result or "").lower()
    return any(token in lowered for token in ("could not", "failed", "blocked", "disabled", "unavailable", "outside the screen", "not connected", "not found"))


def _risky_action_reason(goal: str, plan: dict[str, Any], action: dict[str, Any]) -> str:
    if not bool(config_value("desktop_task_confirm_risky_actions", True)):
        return ""
    action_name = str(action.get("action") or "").lower()
    if action_name not in {"click", "double_click", "press_key", "hotkey", "dom_click", "dom_press", "uia_invoke"}:
        return ""
    combined = " ".join(
        [
            str(goal or ""),
            str(plan.get("progress") or ""),
            str(plan.get("reason") or ""),
            json.dumps(action, ensure_ascii=True),
        ]
    ).lower()
    risky_terms = (
        "send",
        "submit",
        "delete",
        "remove",
        "purchase",
        "buy",
        "pay",
        "confirm",
        "authorize",
        "transfer",
        "install",
        "uninstall",
        "sign out",
        "log out",
        "post",
        "publish",
    )
    if not any(term in combined for term in risky_terms):
        return ""
    return f"Confirm before I run this risky desktop action: {action_name}."


def _recovery_action(history: list[dict[str, Any]], recovery_count: int) -> dict[str, Any]:
    if not bool(config_value("desktop_task_recovery_enabled", True)):
        return {}
    sequence = [
        {"action": "wait", "seconds": 1},
        {"action": "press_key", "target": "escape"},
        {"action": "dom_scroll", "amount": 650},
        {"action": "press_key", "target": "tab"},
        {"action": "hotkey", "target": "alt tab"},
    ]
    if recovery_count < len(sequence):
        return sequence[recovery_count]
    recent = " ".join(str(item.get("result") or item.get("progress") or "") for item in history[-3:]).lower()
    if "menu" in recent or "popup" in recent or "dialog" in recent:
        return {"action": "press_key", "target": "escape"}
    return {}


def _collect_control_context(goal: str) -> dict[str, Any]:
    contexts: dict[str, Any] = {}
    if bool(config_value("browser_dom_enabled", True)):
        contexts["browser_dom"] = browser_dom.context_summary(limit=int(config_value("browser_dom_max_elements", 60)))
    if bool(config_value("app_accessibility_enabled", True)):
        contexts["app_accessibility"] = app_accessibility.context_summary(limit=int(config_value("app_accessibility_max_nodes", 60)))
    if bool(config_value("visual_monitor_planner_context_enabled", True)):
        contexts["visual_monitor"] = visual_monitor.planner_context(limit=int(config_value("visual_monitor_context_events", 6)))
    if bool(config_value("desktop_task_pc_awareness_context_enabled", True)):
        contexts["pc_awareness"] = pc_awareness.planner_context()
    contexts["goal_terms"] = [word for word in re.sub(r"[^a-z0-9]+", " ", goal.lower()).split() if len(word) > 2][:12]
    return contexts


def _compact_contexts(contexts: dict[str, Any]) -> dict[str, Any]:
    browser = dict(contexts.get("browser_dom") or {})
    app = dict(contexts.get("app_accessibility") or {})
    vision = dict(contexts.get("visual_monitor") or {})
    pc_state = dict(contexts.get("pc_awareness") or {})
    if browser.get("elements"):
        browser["elements"] = browser["elements"][:20]
    if browser.get("page_text"):
        browser["page_text"] = str(browser["page_text"])[:500]
    if app.get("elements"):
        app["elements"] = app["elements"][:25]
    if vision.get("recent_events"):
        vision["recent_events"] = vision["recent_events"][:6]
    if pc_state.get("running_apps"):
        pc_state["running_apps"] = pc_state["running_apps"][:20]
    if pc_state.get("desktop_apps"):
        pc_state["desktop_apps"] = pc_state["desktop_apps"][:25]
    if pc_state.get("installed_app_names"):
        pc_state["installed_app_names"] = pc_state["installed_app_names"][:50]
    return {
        "browser_dom": browser,
        "app_accessibility": app,
        "visual_monitor": vision,
        "pc_awareness": pc_state,
        "goal_terms": contexts.get("goal_terms") or [],
    }


def _human_handoff_reason(goal: str, contexts: dict[str, Any]) -> str:
    detections: set[str] = set()
    for key in ("browser_dom", "app_accessibility"):
        value = contexts.get(key) or {}
        detections.update(str(item).lower() for item in value.get("detections") or [])
    if "captcha" in detections:
        return "I found a CAPTCHA or human-verification challenge. I paused so you can solve it manually, then resume the desktop task."
    goal_text = str(goal or "").lower()
    if "login" in detections and not any(token in goal_text for token in ("already logged in", "after i log in", "once i log in")):
        return "I found a login or credential screen. I paused so you can enter credentials manually, then resume the desktop task."
    return ""


def _should_extend_session(history: list[dict[str, Any]], no_progress_count: int) -> bool:
    if not bool(config_value("desktop_task_auto_extend_steps", True)):
        return False
    if no_progress_count:
        return False
    recent = history[-3:]
    if not recent:
        return False
    productive = {"action", "confirmed_action", "recovery"}
    return any(item.get("status") in productive and str(item.get("progress") or "").strip() for item in recent)


def _desktop_task_summary(status: str, goal: str, history: list[dict[str, Any]], reason: str, started: float, *, session_id: int | None = None) -> str:
    elapsed = round((time.perf_counter() - started) * 1000)
    steps = len([item for item in history if item.get("status") in {"action", "confirmed_action"}])
    last_result = next((str(item.get("result") or "") for item in reversed(history) if item.get("result")), "")
    if status == "completed":
        prefix = "Desktop task completed"
    elif status == "paused":
        prefix = "Desktop task paused"
    elif status == "waiting_confirmation":
        prefix = "Desktop task waiting for confirmation"
    else:
        prefix = "Desktop task stopped"
    if session_id:
        prefix += f" #{session_id}"
    details = f"{prefix} after {steps} action{'s' if steps != 1 else ''} in {elapsed}ms. {reason}".strip()
    if last_result:
        details += f" Last action result: {last_result}"
    return details


def _log_desktop_step(step: int, status: str, progress: str) -> None:
    try:
        from output.display import log

        note = " ".join(str(progress or "").split())[:160]
        log("INFO", f"[DESKTOP] step={step} status={status} progress={note}")
    except Exception:
        return


def _extract_gemini_text(data: dict[str, Any]) -> str:
    parts: list[str] = []
    for candidate in data.get("candidates") or []:
        for part in (candidate.get("content") or {}).get("parts") or []:
            if "text" in part:
                parts.append(str(part.get("text") or ""))
    return "\n".join(part for part in parts if part).strip()


def _mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    return "image/png"


def _placeholder(value: str | None) -> bool:
    normalized = str(value or "").strip().lower()
    return not normalized or normalized.startswith("your_") or normalized in {"your_key_here", "xxxx-xxxx-xxxx-xxxx"}

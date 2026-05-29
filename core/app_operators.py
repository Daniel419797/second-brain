"""App-specific operator registry for reliable human-like workflows."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from core import app_integrations, browser_playwright, desktop_tasks, pc_awareness


OPERATORS: dict[str, dict[str, Any]] = {
    "vscode": {"name": "VS Code operator", "open_target": "vscode", "mode": "desktop", "strengths": ["files", "terminal", "debugging", "tests"]},
    "chrome": {"name": "Chrome operator", "open_target": "chrome", "mode": "browser", "strengths": ["tabs", "forms", "DOM", "downloads"]},
    "figma": {"name": "Figma operator", "open_target": "figma", "mode": "browser", "strengths": ["files", "frames", "layers", "comments"]},
    "gmail": {"name": "Gmail operator", "open_target": "gmail", "mode": "browser", "strengths": ["search", "compose draft", "labels"]},
    "whatsapp": {"name": "WhatsApp Web operator", "open_target": "whatsapp", "mode": "browser", "strengths": ["chat search", "drafting", "media handoff"]},
    "discord": {"name": "Discord operator", "open_target": "discord", "mode": "browser", "strengths": ["servers", "channels", "message drafts"]},
    "file_explorer": {"name": "File Explorer operator", "open_target": "explorer", "mode": "desktop", "strengths": ["folders", "files", "copy/move planning"]},
}


def list_operators() -> list[dict[str, Any]]:
    return [{"id": key, **value} for key, value in OPERATORS.items()]


def operator_context(app: str) -> dict[str, Any]:
    key = _key(app)
    spec = _operator_spec(app)
    if not spec:
        return {"available": False, "summary": f"No app name provided."}
    awareness = pc_awareness.snapshot()
    open_windows = [
        item for item in awareness.get("running_apps", [])
        if key in str(item.get("name") or item.get("exe") or "").lower() or spec["open_target"] in str(item).lower()
    ][:8]
    source = "specialist" if key in OPERATORS else "dynamic"
    return {
        "available": True,
        "id": key,
        "operator": spec,
        "source": source,
        "open_windows": open_windows,
        "summary": f"{spec['name']} ready with {len(open_windows)} related running windows.",
    }


def open_app(app: str) -> dict[str, Any]:
    key = _key(app)
    spec = _operator_spec(app)
    if not spec:
        return {"ok": False, "summary": "Tell me which app to open."}
    target = spec["open_target"]
    link = app_integrations.app_link(target)
    if link:
        from tools import pc_control

        reply = pc_control.execute({"action": "open_path", "target": link})
        return {"ok": "could not" not in reply.lower(), "reply": reply, "summary": reply}
    from tools import pc_control

    reply = pc_control.execute({"action": "open_app", "target": target})
    return {"ok": "could not" not in reply.lower() and "not in the allowed" not in reply.lower(), "reply": reply, "summary": reply}


def operate(app: str, instruction: str, *, max_steps: int = 0) -> dict[str, Any]:
    key = _key(app)
    spec = _operator_spec(app)
    if not spec:
        return {"ok": False, "summary": "Tell me which app to operate."}
    context = operator_context(key)
    task_instruction = (
        f"Use the {spec['name']} for {app}. Goal: {instruction}. "
        f"Prefer app-specific browser DOM/accessibility context when available. "
        f"Do not send messages, delete files, or publish changes without confirmation."
    )
    session_id = desktop_tasks.create_session(task_instruction, max_steps=max_steps or 12)
    task = desktop_tasks.get_session(session_id) or {"id": session_id}
    return {
        "ok": True,
        "operator": spec,
        "task": task,
        "context": context,
        "summary": f"Started {spec['name']} session #{task['id']}.",
    }


def browser_inspect(app: str = "chrome") -> dict[str, Any]:
    context = operator_context(app)
    target = context.get("operator", {}).get("open_target", app) if context.get("available") else app
    url = app_integrations.app_link(target) or "about:blank"
    page = browser_playwright.inspect_url(url) if url != "about:blank" else browser_playwright.available()
    return {"context": context, "browser": page, "summary": page.get("summary", context.get("summary", ""))}


def _key(value: str) -> str:
    lowered = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {"vs_code": "vscode", "visual_studio_code": "vscode", "explorer": "file_explorer", "files": "file_explorer"}
    return aliases.get(lowered, lowered)


def _operator_spec(app: str) -> dict[str, Any] | None:
    key = _key(app)
    if not key:
        return None
    if key in OPERATORS:
        return dict(OPERATORS[key])
    found = pc_awareness.find_app(app)
    launch_target = str(found.get("launch_target") or app).strip()
    name = str(found.get("name") or app).strip()
    mode = "desktop"
    if name.lower() in {"gmail", "figma", "discord", "whatsapp", "chrome", "browser"}:
        mode = "browser"
    return {
        "name": f"{name} dynamic operator",
        "open_target": launch_target or app,
        "mode": mode,
        "strengths": ["dynamic app discovery", "screen control", "accessibility", "workflow learning"],
        "dynamic": True,
        "found": bool(found.get("found")),
        "source": found.get("source") or "manual",
    }

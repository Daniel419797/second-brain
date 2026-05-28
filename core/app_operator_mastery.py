"""Specialist app operator mastery and muscle-memory summaries."""

from __future__ import annotations

from typing import Any

from core import app_operators, app_state_memory, browser_extension_bridge, browser_pc_copilot, contextual_workspace


def status() -> dict[str, Any]:
    operators = app_operators.list_operators()
    memories = app_state_memory.summary(limit=12)
    return {
        "operators": operators,
        "memory": memories,
        "summary": f"{len(operators)} specialist operator(s) registered with app-state memory online.",
    }


def operator_brief(app: str) -> dict[str, Any]:
    context = app_operators.operator_context(app)
    memories = app_state_memory.search(app=app, limit=12) if hasattr(app_state_memory, "search") else []
    browser = browser_extension_bridge.latest_page_insight()
    workspace = contextual_workspace.summary()
    return {
        "app": app,
        "context": context,
        "memories": memories,
        "browser": browser,
        "workspace": workspace,
        "summary": context.get("summary") or f"{app} operator context unavailable.",
    }


def plan(app: str, instruction: str) -> dict[str, Any]:
    brief = operator_brief(app)
    selector_hints = []
    for item in brief.get("memories") or []:
        selector = item.get("selector") or item.get("metadata", {}).get("selector")
        if selector:
            selector_hints.append(selector)
    if str(app).lower() in {"chrome", "gmail", "figma", "discord", "whatsapp"}:
        summarize = getattr(browser_pc_copilot, "summarize_current_page", None) or getattr(browser_pc_copilot, "summarize_current_tab", None)
        copilot = summarize() if summarize else {"summary": "Browser/PC copilot summary unavailable."}
    else:
        copilot = {"summary": "Desktop/accessibility operator path preferred."}
    return {
        "app": app,
        "instruction": instruction,
        "brief": brief,
        "selector_hints": selector_hints[:8],
        "copilot": copilot,
        "steps": [
            "Open or focus the target app.",
            "Load app-specific memory and current browser/accessibility context.",
            "Prefer remembered selectors/menus that previously worked.",
            "Use screenshots/DOM/accessibility only as verification, not as unsupported proof.",
            "Stop and ask before sending messages, deleting files, publishing, or using credentials.",
        ],
        "summary": f"Prepared {app} operator mastery plan.",
    }


def start(app: str, instruction: str, *, max_steps: int = 0) -> dict[str, Any]:
    plan_payload = plan(app, instruction)
    session = app_operators.operate(app, instruction, max_steps=max_steps)
    return {"plan": plan_payload, "session": session, "summary": session.get("summary", plan_payload["summary"])}

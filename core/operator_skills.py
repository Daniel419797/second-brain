"""High-reliability specialist operators for common apps."""

from __future__ import annotations

from typing import Any

from core import app_operator_mastery, app_operators, app_state_memory, browser_extension_pro, project_memory


OPERATORS: dict[str, dict[str, Any]] = {
    "figma": {
        "name": "Figma Designer",
        "strengths": ["layers", "toolbar memory", "component inspection", "design handoff"],
        "safe_boundaries": ["will ask before publishing, sharing, deleting, or overwriting files"],
    },
    "vscode": {
        "name": "VS Code Debugger",
        "strengths": ["terminal errors", "file search", "debug panels", "repo context"],
        "safe_boundaries": ["will create proof before claiming fixes"],
    },
    "chrome": {
        "name": "Chrome Tester",
        "strengths": ["DOM context", "forms", "console errors", "Playwright-friendly selectors"],
        "safe_boundaries": ["will not fill passwords or private tokens without approval"],
    },
    "render": {
        "name": "Render Deployer",
        "strengths": ["logs", "deploy status", "environment name checks", "rollback notes"],
        "safe_boundaries": ["deploy actions are approval-gated"],
    },
    "vercel": {
        "name": "Vercel Deployer",
        "strengths": ["build errors", "domain hints", "deployment checklist"],
        "safe_boundaries": ["deploy actions are approval-gated"],
    },
    "gmail": {
        "name": "Gmail Executive Assistant",
        "strengths": ["drafts", "follow-ups", "email triage"],
        "safe_boundaries": ["will ask before sending messages"],
    },
    "calendar": {
        "name": "Calendar Executive Assistant",
        "strengths": ["planning", "conflict checks", "daily agenda"],
        "safe_boundaries": ["will ask before creating account-bound events unless allowed"],
    },
    "file_explorer": {
        "name": "File Explorer Organizer",
        "strengths": ["file search", "folder summaries", "safe organization plans"],
        "safe_boundaries": ["will ask before deleting or moving important files"],
    },
}


def list_operators() -> list[dict[str, Any]]:
    learned = app_state_memory.summary(limit=3).get("by_app", {})
    return [dict(value, id=key, learned_patterns=int(learned.get(key, 0))) for key, value in OPERATORS.items()]


def plan(app: str, instruction: str = "", *, root: str = "") -> dict[str, Any]:
    app_id = _canonical(app)
    spec = OPERATORS.get(app_id, {"name": f"{app_id.title()} Operator", "strengths": ["generic app operation"], "safe_boundaries": ["uses desktop safety checks"]})
    mastery = app_operator_mastery.plan(app_id, instruction)
    patterns = app_state_memory.search_patterns(app_id, instruction, limit=6)
    repo = project_memory.profile(root) if root else None
    steps = [
        "Inspect live app/browser/accessibility context.",
        "Recall app-specific successful selectors, menus, and recovery hints.",
        "Choose the safest DOM/accessibility action before falling back to mouse control.",
        "Verify the UI changed as expected.",
        "Record success/failure back into app muscle memory.",
    ]
    if app_id in {"render", "vercel"}:
        steps.append("Stop at deployment unless explicit deploy approval exists.")
    return {
        "app": app_id,
        "operator": spec,
        "instruction": instruction,
        "steps": steps,
        "mastery": mastery,
        "patterns": patterns,
        "project": repo,
        "summary": f"{spec['name']} plan ready with {len(patterns)} learned pattern(s).",
    }


def start(app: str, instruction: str, *, max_steps: int = 12, root: str = "") -> dict[str, Any]:
    app_id = _canonical(app)
    plan_data = plan(app_id, instruction, root=root)
    if app_id == "chrome" and ("button" in instruction.lower() or "form" in instruction.lower() or "page" in instruction.lower()):
        browser_hint = browser_extension_pro.guidance(instruction)
        plan_data["browser_hint"] = browser_hint
    result = app_operators.operate(app_id, instruction, max_steps=max_steps)
    return {"plan": plan_data, "result": result, "summary": result.get("summary") or plan_data["summary"]}


def status() -> dict[str, Any]:
    operators = list_operators()
    return {"operators": operators, "summary": f"{len(operators)} specialist operator skill(s) available."}


def _canonical(value: str) -> str:
    text = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {"vs_code": "vscode", "code": "vscode", "google_chrome": "chrome", "explorer": "file_explorer", "files": "file_explorer"}
    return aliases.get(text, text or "chrome")

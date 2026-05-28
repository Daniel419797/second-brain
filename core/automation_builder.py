"""Natural-language automation builder on top of capability-center recipes."""

from __future__ import annotations

import re
from typing import Any

from core import capability_center, notification_center, pc_awareness


def create_from_text(text: str) -> dict[str, Any]:
    raw = _clean(text)
    if not raw:
        return {"ok": False, "summary": "No automation description was provided."}
    trigger_type, trigger = _parse_trigger(raw)
    action_type, action = _parse_action(raw)
    recipe = capability_center.create_recipe(
        _recipe_name(raw),
        trigger_type,
        trigger,
        action_type,
        action,
        enabled=True,
    )
    notification_center.add(
        source="automation_builder",
        category="automation",
        severity=2,
        title="Automation recipe created",
        message=f"{recipe['name']} is ready.",
        dedupe_key=f"automation:{recipe['id']}",
        metadata={"recipe": recipe},
    )
    return {"ok": True, "recipe": recipe, "summary": f"Created automation: {recipe['name']}."}


def evaluate_triggers(*, run: bool = True) -> dict[str, Any]:
    recipes = capability_center.list_recipes(limit=200)
    matched = []
    for recipe in recipes:
        if not recipe.get("enabled"):
            continue
        if _trigger_matches(recipe):
            result = capability_center.run_recipe(int(recipe["id"])) if run else {"ok": True, "summary": "Matched but not run."}
            matched.append({"recipe": recipe, "result": result})
    return {"matched": matched, "summary": f"{len(matched)} automation recipe(s) matched."}


def explain_recipe(recipe_id: int) -> dict[str, Any]:
    recipe = next((item for item in capability_center.list_recipes(limit=500) if int(item.get("id") or 0) == int(recipe_id)), None)
    if not recipe:
        return {"ok": False, "summary": "Recipe not found."}
    return {
        "ok": True,
        "recipe": recipe,
        "summary": f"When {recipe['trigger_type']} {recipe['trigger']}, Friday will run {recipe['action_type']} {recipe['action']}.",
    }


def _parse_trigger(text: str) -> tuple[str, dict[str, Any]]:
    lowered = text.lower()
    if "battery" in lowered and any(term in lowered for term in ["low", "below", "under"]):
        match = re.search(r"(?:below|under)\s+(\d+)", lowered)
        return "battery_below", {"percent": int(match.group(1)) if match else 25}
    if "open vs code" in lowered or "open vscode" in lowered or "open visual studio code" in lowered:
        return "active_app", {"app": "vscode"}
    if "open chrome" in lowered:
        return "active_app", {"app": "chrome"}
    if "time" in lowered and "every day" in lowered:
        return "daily_time", {"time": "09:00"}
    return "manual", {}


def _parse_action(text: str) -> tuple[str, dict[str, Any]]:
    lowered = text.lower()
    if "brightness" in lowered:
        match = re.search(r"(\d+)\s*%?", lowered)
        return "set_brightness", {"level": int(match.group(1)) if match else 40}
    if "start api" in lowered or "dashboard" in lowered:
        return "start_dashboard", {}
    if "open chrome" in lowered:
        return "open_app", {"target": "chrome"}
    if "notify" in lowered or "phone" in lowered:
        return "notify_phone", {"message": text}
    return "notify_phone", {"message": f"Automation matched: {text}"}


def _trigger_matches(recipe: dict[str, Any]) -> bool:
    trigger_type = str(recipe.get("trigger_type") or "")
    trigger = recipe.get("trigger") or {}
    if trigger_type == "manual":
        return False
    if trigger_type == "active_app":
        app = str(trigger.get("app") or "").lower()
        active = str(pc_awareness.snapshot().get("active_window") or "").lower()
        aliases = {
            "vscode": ["vscode", "vs code", "visual studio code", "code.exe"],
            "chrome": ["chrome", "google chrome", "chrome.exe"],
        }
        needles = aliases.get(app, [app])
        return bool(app and any(needle in active for needle in needles))
    if trigger_type == "battery_below":
        try:
            import psutil  # type: ignore

            battery = psutil.sensors_battery()
            return bool(battery and battery.percent <= float(trigger.get("percent") or 25) and not battery.power_plugged)
        except Exception:
            return False
    return False


def _recipe_name(text: str) -> str:
    words = re.sub(r"[^a-zA-Z0-9]+", " ", text).split()
    return " ".join(words[:8]) or "Friday automation"


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())

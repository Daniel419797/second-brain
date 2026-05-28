"""Daily Life OS mode for priorities, study, energy, and end-of-day flow."""

from __future__ import annotations

from typing import Any

from core import daily_companion, executive_capabilities, goal_manager, learning_coach, operating_rhythm, os_autopilot, personal_life_os


def status() -> dict[str, Any]:
    return {
        "brief": _safe(daily_companion.status, {}),
        "life_dashboard": _safe(executive_capabilities.life_dashboard, {}),
        "rhythm": _safe(operating_rhythm.summary, {}),
        "os_autopilot": _safe(os_autopilot.status, {}),
        "learning": _safe(learning_coach.progress, {}),
        "goals": _safe(goal_manager.progress_summary, {}),
        "summary": "Life OS mode is ready.",
    }


def daily_brief() -> dict[str, Any]:
    brief = _safe(daily_companion.morning_brief, {})
    plan = _safe(personal_life_os.daily_plan, {})
    rhythm = _safe(os_autopilot.recommendation, {})
    return {"brief": brief, "plan": plan, "rhythm": rhythm, "summary": brief.get("summary") or plan.get("summary") or "Daily brief ready."}


def next_action() -> dict[str, Any]:
    return {
        "personal_os": _safe(personal_life_os.what_should_i_do_next, {}),
        "goal_manager": _safe(goal_manager.next_goal_action, {}),
        "rhythm": _safe(os_autopilot.recommendation, {}),
        "summary": _safe(lambda: os_autopilot.recommendation().get("summary"), "Next action ready."),
    }


def end_of_day() -> dict[str, Any]:
    return {"personal_os": _safe(personal_life_os.end_of_day_summary, {}), "rhythm": _safe(operating_rhythm.summary, {}), "summary": "End-of-day summary ready."}


def _safe(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default

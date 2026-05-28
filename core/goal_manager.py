"""Higher-level goal manager built on Friday's goal regulation store."""

from __future__ import annotations

import datetime as dt
from typing import Any

from core import app_integrations, goal_regulation, personal_knowledge_vault, personal_life_os


def create_goal_plan(title: str, description: str = "", *, deadline_at: str = "", priority: int = 3) -> dict[str, Any]:
    goal_id = goal_regulation.create_goal(title, description=description, priority=priority, source="goal_manager", deadline_at=deadline_at)
    personal_knowledge_vault.remember("goal", title, description, confidence=0.85, tags=["active_goal"], metadata={"goal_id": goal_id, "deadline_at": deadline_at})
    steps = _plan_steps(title, description)
    child_goals = []
    for index, step in enumerate(steps, 1):
        child_id = goal_regulation.create_goal(step, description=f"Step {index} for: {title}", priority=priority + index, source="goal_manager", parent_id=goal_id)
        child_goals.append(goal_regulation.get_goal(child_id))
    reminder = app_integrations.create_reminder(f"Review goal: {title}", due_at="tomorrow", notes="Goal Manager follow-up.")
    return {
        "goal": goal_regulation.get_goal(goal_id),
        "steps": [item for item in child_goals if item],
        "reminder": reminder,
        "summary": f"Created goal plan with {len(child_goals)} step(s): {title}.",
    }


def weekly_plan() -> dict[str, Any]:
    vault = personal_knowledge_vault.what_matters_this_week()
    life = personal_life_os.daily_plan()
    active = goal_regulation.active_goals(limit=10)
    blocks = []
    for goal in active[:5]:
        blocks.append({"goal_id": goal["id"], "title": goal["title"], "progress": goal["progress"], "next": _next_step_for(goal)})
    return {
        "what_matters": vault,
        "daily_plan": life,
        "goals": active,
        "blocks": blocks,
        "summary": vault.get("summary") or "Weekly plan ready.",
    }


def next_goal_action() -> dict[str, Any]:
    goals = goal_regulation.active_goals(limit=20)
    if not goals:
        return {"kind": "setup", "summary": "No active goals are tracked. Add a big goal first."}
    goal = goals[0]
    state = personal_life_os.latest_mood()
    energy = int((state or {}).get("energy") or 5)
    if energy <= 3:
        action = f"Do a 10-minute low-energy review of {goal['title']}."
    elif energy >= 7:
        action = f"Make concrete progress on {goal['title']} for 45 minutes."
    else:
        action = f"Pick one next step for {goal['title']} and finish it."
    return {"goal": goal, "energy": energy, "action": action, "summary": action}


def progress_summary(limit: int = 10) -> dict[str, Any]:
    goals = goal_regulation.list_goals(limit=limit)
    active = [goal for goal in goals if goal["status"] == "active"]
    blocked = [goal for goal in goals if goal["status"] == "blocked"]
    done = [goal for goal in goals if goal["status"] == "done"]
    return {
        "active": active,
        "blocked": blocked,
        "done": done,
        "summary": f"{len(active)} active goal(s), {len(blocked)} blocked, {len(done)} done.",
    }


def _plan_steps(title: str, description: str) -> list[str]:
    base = title.strip() or "the goal"
    lowered = f"{title} {description}".lower()
    steps = [
        f"Clarify success criteria for {base}",
        f"Break {base} into the next small deliverable",
        f"Schedule a focused work block for {base}",
        f"Review progress and adjust {base}",
    ]
    if any(term in lowered for term in ["project", "app", "code", "build"]):
        steps.insert(2, f"Map dependencies and risks for {base}")
    if any(term in lowered for term in ["study", "learn", "exam"]):
        steps.insert(2, f"Create study notes and recall questions for {base}")
    return steps[:6]


def _next_step_for(goal: dict[str, Any]) -> str:
    progress = float(goal.get("progress") or 0.0)
    if progress <= 0:
        return "Define done and start the smallest useful step."
    if progress < 0.5:
        return "Continue the main work block and remove blockers."
    if progress < 0.9:
        return "Verify, polish, and document the result."
    return "Close the goal or capture final lessons."


def today_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().date().isoformat()

"""Prospective self-learning task seeding for v2 agents."""

from __future__ import annotations

import datetime as dt
from typing import Any

from core import task_queue
from core.config import config_value

LEARNING_TASKS: tuple[dict[str, Any], ...] = (
    {
        "key": "ui_ux_youtube_learning",
        "agent_id": "ui_ux_designer",
        "title": "Learn UI/UX patterns from free tutorials",
        "description": "Use YouTube transcripts and free articles to collect reusable dashboard, mobile, accessibility, and design-system lessons.",
    },
    {
        "key": "dev_official_docs_learning",
        "agent_id": "research_analyst",
        "title": "Read official documentation for current project stack",
        "description": "Review official docs for Python, FastAPI, Next.js, Electron, SQLite, and deployment constraints. Store reusable implementation lessons.",
    },
    {
        "key": "security_cve_review",
        "agent_id": "cybersecurity_analyst",
        "title": "Review defensive security updates",
        "description": "Check free security sources for relevant dependency advisories and practical hardening work.",
    },
)


def seed_learning_tasks(now: dt.datetime | None = None) -> list[int]:
    if not bool(config_value("v2_self_learning_enabled", True)):
        return []
    current = now or dt.datetime.now(dt.timezone.utc).astimezone()
    existing = task_queue.list_tasks(limit=500)
    repeat_hours = float(config_value("v2_self_learning_repeat_hours", 12))
    recent_cutoff = current - dt.timedelta(hours=max(0.0, repeat_hours))
    active_titles = {str(task.get("title") or "").lower() for task in existing if task.get("status") in task_queue.ACTIVE_STATUSES}
    recent_titles = {
        str(task.get("title") or "").lower()
        for task in existing
        if _task_is_recent(task, recent_cutoff)
    }
    created: list[int] = []
    scheduled_at = current + dt.timedelta(minutes=float(config_value("v2_self_learning_delay_minutes", 15)))
    for template in LEARNING_TASKS:
        title = template["title"].lower()
        if title in active_titles or title in recent_titles:
            continue
        task_id = task_queue.create_task(
            template["title"],
            description=template["description"],
            agent_id=template["agent_id"],
            priority=int(config_value("v2_self_learning_priority", 10)),
            input_data={"source": "self_learning_scheduler", "key": template["key"]},
            scheduled_at=scheduled_at,
        )
        created.append(task_id)
    return created


def _task_is_recent(task: dict[str, Any], cutoff: dt.datetime) -> bool:
    for key in ("completed_at", "updated_at", "created_at"):
        raw = str(task.get(key) or "")
        if not raw:
            continue
        try:
            stamp = dt.datetime.fromisoformat(raw)
        except ValueError:
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=dt.timezone.utc)
        if stamp.astimezone() >= cutoff:
            return True
    return False

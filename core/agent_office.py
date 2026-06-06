"""Virtual office snapshots for the v2 agent team."""

from __future__ import annotations

import sqlite3
from collections import Counter
from typing import Any

from core import agents, competence, task_queue
from core.config import config_value

ROOM_NAMES = {
    "ceo": "Command Office",
    "product_manager": "Product Room",
    "project_manager": "Delivery Desk",
    "senior_developer": "Architecture Studio",
    "junior_developer": "Build Bench",
    "devops": "Operations Bay",
    "cybersecurity_analyst": "Security Desk",
    "ethical_hacker": "Authorization Lab",
    "ui_ux_designer": "Design Studio",
    "brand_content_designer": "Content Studio",
    "research_analyst": "Research Library",
    "data_scientist": "Data Lab",
    "qa_engineer": "QA Lab",
    "code_reviewer": "Review Desk",
    "doctor": "Diagnostics Bay",
}


def all_offices() -> list[dict[str, Any]]:
    return [office(agent.id) for agent in agents.ROSTER]


def office(agent_id: str) -> dict[str, Any]:
    profile = agents.get_agent(agent_id)
    tasks = _agent_tasks(profile.id)
    current_task = _current_task(tasks)
    recent_messages = _recent_messages(profile.id, limit=5)
    task_counts = Counter(str(task.get("status") or "") for task in tasks)
    progress = _progress(current_task, recent_messages)
    status = _office_status(task_counts, current_task)
    latest = current_task or (tasks[0] if tasks else {})
    topics = competence.get_agent_map(profile.id)
    strengths = sorted(topics.items(), key=lambda item: item[1], reverse=True)[:3]

    return {
        "agent_id": profile.id,
        "agent_name": profile.name,
        "purpose": profile.purpose,
        "room_name": ROOM_NAMES.get(profile.id, f"{profile.name} Office"),
        "status": status,
        "progress_percent": progress,
        "current_focus": _focus_text(current_task, status),
        "current_task": _task_preview(current_task),
        "recent_tasks": [_task_preview(task) for task in tasks[:5]],
        "recent_messages": recent_messages,
        "task_counts": {name: int(task_counts.get(name, 0)) for name in ["active", "pending", "blocked", "done", "failed", "cancelled"]},
        "provider_chain": agents.agent_provider_chain(profile.id),
        "known_peers": _known_peers(profile.id),
        "competence": [{"topic": topic, "score": round(float(score), 2)} for topic, score in strengths],
        "last_activity": str(latest.get("updated_at") or ""),
    }


def office_summary(limit: int = 6) -> str:
    offices = all_offices()
    active = [item for item in offices if item["status"] in {"working", "queued", "blocked"}]
    if not active:
        return "All agent offices are idle. No active or pending work right now."
    lines = []
    for item in active[: max(1, int(limit))]:
        lines.append(
            f"{item['agent_name']}: {item['status']}, {item['progress_percent']}%, {item['current_focus']}"
        )
    return "\n".join(lines)


def _agent_tasks(agent_id: str) -> list[dict[str, Any]]:
    task_queue.init_db()
    limit = max(10, int(config_value("agent_office_task_limit", 120)))
    with sqlite3.connect(task_queue.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM tasks
            WHERE agent_id = ?
            ORDER BY
                CASE status WHEN 'active' THEN 0 WHEN 'pending' THEN 1 WHEN 'blocked' THEN 2 ELSE 3 END,
                updated_at DESC
            LIMIT ?
            """,
            (agent_id, limit),
        ).fetchall()
    return [task_queue._row_to_task(row) for row in rows]


def _recent_messages(agent_id: str, limit: int) -> list[dict[str, Any]]:
    task_queue.init_db()
    with sqlite3.connect(task_queue.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT m.id, m.task_id, m.timestamp, m.sender, m.message, t.title, t.status
            FROM task_messages m
            JOIN tasks t ON t.id = m.task_id
            WHERE t.agent_id = ?
            ORDER BY m.timestamp DESC, m.id DESC
            LIMIT ?
            """,
            (agent_id, max(1, int(limit))),
        ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "task_id": int(row["task_id"]),
            "timestamp": str(row["timestamp"]),
            "sender": str(row["sender"]),
            "message": str(row["message"]),
            "task_title": str(row["title"]),
            "task_status": str(row["status"]),
        }
        for row in rows
    ]


def _current_task(tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    for status in ["active", "blocked", "pending"]:
        for task in tasks:
            if task.get("status") == status:
                return task
    return None


def _task_preview(task: dict[str, Any] | None) -> dict[str, Any] | None:
    if not task:
        return None
    output = task.get("output") if isinstance(task.get("output"), dict) else {}
    return {
        "id": int(task.get("id") or 0),
        "title": str(task.get("title") or ""),
        "status": str(task.get("status") or ""),
        "priority": int(task.get("priority") or 0),
        "summary": str(output.get("summary") or "")[:240],
        "updated_at": str(task.get("updated_at") or ""),
    }


def _office_status(counts: Counter[str], current_task: dict[str, Any] | None) -> str:
    if current_task:
        status = str(current_task.get("status") or "")
        if status == "active":
            return "working"
        if status == "blocked":
            return "blocked"
        if status == "pending":
            return "queued"
    if counts.get("failed", 0):
        return "needs_review"
    if counts.get("done", 0):
        return "resting"
    return "idle"


def _progress(task: dict[str, Any] | None, messages: list[dict[str, Any]]) -> int:
    if not task:
        return 0
    status = str(task.get("status") or "")
    if status == "done":
        return 100
    if status in {"failed", "cancelled"}:
        return 0
    if status == "blocked":
        return 10
    if status == "pending":
        return 15
    if status == "active":
        return task_queue.task_progress(int(task.get("id") or 0), status)
    return 0


def _known_peers(agent_id: str) -> list[dict[str, str]]:
    return [
        {"id": peer.id, "name": peer.name, "purpose": peer.purpose}
        for peer in agents.ROSTER
        if peer.id != agent_id
    ]


def _focus_text(task: dict[str, Any] | None, status: str) -> str:
    if task:
        return str(task.get("title") or "Untitled task")
    if status == "resting":
        return "Recent work completed"
    return "Waiting for assignment"

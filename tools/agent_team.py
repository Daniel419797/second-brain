"""Tool interface for the v2 local background agent team."""

from __future__ import annotations

import re
from typing import Any

from core import agent_blackboard, agent_thought_bus, agents, agent_office, approval_inbox, background_agents, task_queue


def execute(inputs: dict[str, Any]) -> str:
    action = str(inputs.get("action") or "status").lower()
    if action in {"run_diagnostics", "diagnostics", "doctor"}:
        return _run_diagnostics(inputs)
    if action in {"monitor_task", "monitor_diagnostics", "diagnostics_status"}:
        return _monitor_task(inputs)
    if action == "create_task":
        return _create_task(inputs)
    if action == "list_tasks":
        return _list_tasks(inputs)
    if action in {"questions", "list_questions"}:
        return _list_questions(inputs)
    if action in {"blackboard", "blackboard_summary"}:
        return _blackboard_summary()
    if action in {"thoughts", "thought_bus", "silent_thoughts"}:
        return _thought_summary()
    if action in {"approvals", "approval_inbox", "decisions"}:
        return approval_inbox.voice_summary()
    if action == "get_task":
        return _get_task(inputs)
    if action in {"assign_task", "reassign_task"}:
        return _assign_task(inputs)
    if action == "cancel_task":
        return _cancel_task(inputs)
    if action == "approve_task":
        return _approve_task(inputs)
    if action == "status":
        return _status()
    if action in {"offices", "office_floor"}:
        return agent_office.office_summary(limit=_int(inputs.get("limit"), 6))
    if action == "office":
        agent_id = str(inputs.get("agent_id") or inputs.get("target") or "")
        return _format_office(agent_office.office(agent_id))
    if action == "roster":
        return agents.format_roster()
    if action == "start_workers":
        count = background_agents.start_workers()
        return f"Agent workers running: {count}."
    if action == "stop_workers":
        background_agents.stop_workers()
        return "Agent workers stopped."
    if action == "run_one":
        task = background_agents.run_one_task()
        return _format_task(task) if task else "No pending tasks."
    return "Unknown agent team action."


def _run_diagnostics(inputs: dict[str, Any]) -> str:
    profile = _diagnostic_profile(inputs)
    root = str(inputs.get("root") or "").strip()
    title = str(inputs.get("title") or inputs.get("target") or "Run Friday diagnostics").strip()
    description = str(inputs.get("description") or "").strip() or (
        f"Run {profile} diagnostics for Friday and report evidence-backed results. "
        "Write decisions, progress, and final evidence to task messages, the blackboard, and the thought bus."
    )
    task_id = agents.create_task(
        title,
        description=description,
        agent_id="doctor",
        priority=_int(inputs.get("priority"), 2),
        input_data={
            "source": "diagnostics_request",
            "diagnostic_profile": profile,
            "root": root,
            "handoff_required": True,
            "auto_report_required": True,
        },
    )
    task_queue.post_message(task_id, "friday", f"Friday handed this diagnostic request to Doctor agent with profile {profile}.")
    try:
        agent_thought_bus.post_thought(
            "friday",
            "delegation",
            f"Diagnostic request delegated to Doctor as task #{task_id}.",
            {"task_id": task_id, "agent_id": "doctor", "profile": profile, "root": root},
            target_agent_id="doctor",
            task_id=task_id,
            confidence=0.9,
            priority=1,
            visibility="surface",
            metadata={"source": "agent_team.run_diagnostics"},
        )
    except Exception:
        pass
    workers = background_agents.start_workers(count=1)
    worker_note = f" Agent workers running: {workers}." if workers else " Agent workers did not start; the task is still queued."
    return (
        f"Diagnostics handed to Doctor agent as task #{task_id} using the {profile} profile."
        f"{worker_note} Monitor it with: show task {task_id}."
    )


def _create_task(inputs: dict[str, Any]) -> str:
    title = str(inputs.get("title") or inputs.get("target") or "").strip()
    description = str(inputs.get("description") or title).strip()
    agent_id = str(inputs.get("agent_id") or "")
    priority = _int(inputs.get("priority"), 5)
    scheduled_at = inputs.get("scheduled_at") or ""
    if not title:
        return "Tell me what task to give the team."
    task_id = agents.create_task(title, description=description, agent_id=agent_id, priority=priority, scheduled_at=scheduled_at)
    task = task_queue.get_task(task_id)
    if not task:
        return f"Task {task_id} created."
    schedule = f" scheduled for {task['scheduled_at']}" if task.get("scheduled_at") else ""
    return f"Task {task_id} queued for {task['agent_id']}{schedule}: {task['title']}."


def _list_tasks(inputs: dict[str, Any]) -> str:
    status = str(inputs.get("status") or "").strip().lower() or None
    tasks = task_queue.list_tasks(status=status, limit=_int(inputs.get("limit"), 8))
    if not tasks:
        return "No tasks found."
    return "\n".join(_format_task(task) for task in tasks)


def _monitor_task(inputs: dict[str, Any]) -> str:
    task_id = _task_id(inputs)
    task = task_queue.get_task(task_id) if task_id is not None else _latest_doctor_task()
    if not task:
        return "No Doctor diagnostic task found."
    task_id = int(task["id"])
    messages = list(reversed(task_queue.get_messages(task_id, limit=_int(inputs.get("limit"), 12))))
    thoughts = agent_thought_bus.list_thoughts(task_id=task_id, limit=8)
    blackboard = agent_blackboard.list_items(task_id=task_id, limit=8)
    output = task.get("output") if isinstance(task.get("output"), dict) else {}
    report = output.get("diagnostic_report") if isinstance(output.get("diagnostic_report"), dict) else {}
    lines = [_format_task(task)]
    if report:
        lines.append(f"Diagnostic status: {report.get('overall_status')} - {report.get('summary')}")
        checks = report.get("checks") or []
        if checks:
            lines.append("Checks: " + "; ".join(f"{item.get('name')}={item.get('status')}" for item in checks[:8]))
    if messages:
        lines.append("Messages: " + " | ".join(f"{item['sender']}: {item['message']}" for item in messages[-6:]))
    decisions = [item for item in thoughts if item.get("packet_type") == "decision"]
    if decisions:
        lines.append("Decisions: " + " | ".join(str(item.get("summary") or "") for item in decisions[:4]))
    evidence = [item for item in blackboard if item.get("item_type") in {"evidence", "decision", "progress"}]
    if evidence:
        lines.append("Blackboard: " + " | ".join(f"{item.get('item_type')}: {item.get('title')}" for item in evidence[:5]))
    return "\n".join(lines)


def _list_questions(inputs: dict[str, Any]) -> str:
    tasks = [
        task
        for task in task_queue.list_tasks(limit=_int(inputs.get("limit"), 20))
        if isinstance(task.get("input"), dict) and task["input"].get("source") == "agent_question"
    ]
    if not tasks:
        return "No agent-to-agent questions are waiting right now."
    lines = []
    for task in tasks[: _int(inputs.get("limit"), 8)]:
        source = task["input"].get("from_agent", "agent")
        question = str(task["input"].get("question") or task.get("description") or "").strip()
        lines.append(f"#{task['id']} [{task['status']}] {source} asked {task['agent_id']}: {question}")
    return "\n".join(lines)


def _blackboard_summary() -> str:
    summary = agent_blackboard.summary(limit=6)
    open_count = int(summary.get("open_count") or 0)
    if not open_count:
        return "The agent blackboard has no open items."
    questions = summary.get("questions") or []
    blockers = summary.get("blockers") or []
    return f"Blackboard: {open_count} open, {len(questions)} questions, {len(blockers)} blockers."


def _thought_summary() -> str:
    summary = agent_thought_bus.summary(limit=5)
    open_count = int(summary.get("open_count") or 0)
    if not open_count:
        return "The silent thought bus has no active packets."
    targeted = summary.get("targeted") or {}
    recent = summary.get("recent") or []
    target_note = ", ".join(f"{target}: {count}" for target, count in list(targeted.items())[:4])
    latest = "; ".join(f"{item['source_agent_id']} to {item['target_agent_id'] or 'team'}: {item['summary']}" for item in recent[:3])
    return f"Silent thought bus: {open_count} active packets. {target_note}. Latest: {latest}"


def _get_task(inputs: dict[str, Any]) -> str:
    task_id = _task_id(inputs)
    if task_id is None:
        return "Tell me which task ID."
    task = task_queue.get_task(task_id)
    if not task:
        return f"Task {task_id} not found."
    messages = task_queue.get_messages(task_id, limit=3)
    text = _format_task(task)
    if task.get("output"):
        text += f"\nOutput: {task['output']}"
    if messages:
        text += "\nRecent messages: " + " | ".join(message["message"] for message in reversed(messages))
    return text


def _assign_task(inputs: dict[str, Any]) -> str:
    task_id = _task_id(inputs)
    agent_id = agents.normalize_agent_id(str(inputs.get("agent_id") or inputs.get("agent") or inputs.get("target_agent") or ""))
    if task_id is None:
        return "Tell me which task ID to reassign."
    if agent_id not in {agent["id"] for agent in agents.roster()}:
        return f"I do not recognize agent {agent_id}."
    status = str(inputs.get("status") or "pending")
    if not task_queue.reassign_task(task_id, agent_id, status=status):
        return f"I could not reassign task {task_id}."
    task = task_queue.get_task(task_id)
    return f"Task {task_id} reassigned to {agent_id}." if not task else _format_task(task)


def _cancel_task(inputs: dict[str, Any]) -> str:
    task_id = _task_id(inputs)
    if task_id is None:
        return "Tell me which task ID to cancel."
    return f"Task {task_id} cancelled." if task_queue.cancel_task(task_id) else f"I could not cancel task {task_id}."


def _approve_task(inputs: dict[str, Any]) -> str:
    task_id = _task_id(inputs)
    confirmation = str(inputs.get("confirmation") or inputs.get("target") or "")
    if task_id is None:
        return "Tell me which task ID to approve."
    if agents.approve_guarded_task(task_id, confirmation):
        return f"Task {task_id} approved and returned to pending."
    return f"I could not approve task {task_id}. Say or type: I authorize task {task_id}."


def _status() -> str:
    status = background_agents.worker_status()
    counts = status["tasks"]
    running = "running" if status["running"] else "stopped"
    runtime = status.get("runtime") or {}
    mode = str(status.get("mode") or ("API-backed" if runtime.get("api_agent_mode") else "local-safe"))
    active_note = ""
    if not status["running"] and counts.get("active", 0):
        active_note = " Active tasks are only marked active in the queue; no worker is executing them right now."
    return (
        f"Agent workers are {running} in {mode} mode ({status.get('workers', 0)}/{status.get('desired_workers', 1)} workers). "
        f"Tasks: {counts.get('active', 0)} active, {counts.get('pending', 0)} pending, "
        f"{counts.get('done', 0)} done, {counts.get('failed', 0)} failed.{active_note}"
    )


def _format_task(task: dict[str, Any] | None) -> str:
    if not task:
        return "No task."
    schedule = f" @ {task['scheduled_at']}" if task.get("scheduled_at") else ""
    return f"#{task['id']} [{task['status']}] {task['agent_id']}{schedule}: {task['title']}"


def _format_office(office: dict[str, Any]) -> str:
    current = office.get("current_task") or {}
    task = f" Task #{current.get('id')}: {current.get('title')}." if current else ""
    return (
        f"{office['agent_name']} is {office['status']} in {office['room_name']}. "
        f"Progress: {office['progress_percent']}%. Focus: {office['current_focus']}.{task}"
    )


def _task_id(inputs: dict[str, Any]) -> int | None:
    raw = inputs.get("task_id") or inputs.get("target") or ""
    match = re.search(r"\d+", str(raw))
    return int(match.group(0)) if match else None


def _latest_doctor_task() -> dict[str, Any] | None:
    tasks = task_queue.list_tasks(agent_id="doctor", limit=20)
    return tasks[0] if tasks else None


def _diagnostic_profile(inputs: dict[str, Any]) -> str:
    text = " ".join(str(inputs.get(key) or "") for key in ("profile", "title", "description", "target", "scope")).lower()
    if re.search(r"\b(deep|full|all|everything|complete)\b", text):
        return "deep"
    if re.search(r"\b(quick|fast|light)\b", text):
        return "quick"
    return "standard"


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

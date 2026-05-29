"""Dynamic Friday-authored interface copy and action metadata.

The frontend should not have to invent Friday's wording. This module turns the
live dashboard snapshot into screen copy, empty-state language, and action
contracts that can move with the current mission, workspace, and risk state.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from typing import Any


VIEW_KEYS = [
    "dashboard",
    "chat",
    "voice-mode",
    "agents",
    "tasks",
    "mission-control",
    "approvals",
    "safety",
    "memory",
    "operators",
    "integrations",
    "android",
    "vision",
    "projects",
    "agency",
    "control-room",
    "notifications",
    "settings",
    "reliability",
    "governance",
]

ALIASES = {
    "mission": "mission-control",
    "missions": "mission-control",
    "mission_control": "mission-control",
    "control_room": "control-room",
    "control": "control-room",
    "voice": "voice-mode",
    "voice_mode": "voice-mode",
    "operator": "operators",
    "ui-control": "operators",
    "ui_control": "operators",
}


def snapshot(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the full dynamic interface contract for the current snapshot."""

    source = payload if isinstance(payload, dict) else {}
    facts = _facts(source)
    views = {view: view_copy(view, source, _facts=facts) for view in VIEW_KEYS}
    chrome = _chrome(facts)
    return {
        "timestamp": source.get("timestamp") or _now(),
        "source": "friday_dynamic_interface",
        "brand": {
            "name": "Friday",
            "title": chrome["title"],
            "signature": chrome["signature"],
        },
        "chrome": chrome,
        "facts": {
            key: facts[key]
            for key in [
                "active_window",
                "app",
                "workers",
                "workers_running",
                "approval_count",
                "pending_tasks",
                "mission_title",
                "notification_count",
                "connector_count",
                "high_risk_count",
                "project_count",
            ]
        },
        "actions": _global_actions(facts),
        "views": views,
    }


def view_copy(view: str, payload: dict[str, Any] | None = None, *, _facts: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the dynamic interface contract for one view."""

    source = payload if isinstance(payload, dict) else {}
    key = normalize_view(view)
    facts = _facts or globals()["_facts"](source)
    builder = _BUILDERS.get(key, _default_view)
    copy = builder(facts, source, key)
    copy["view"] = key
    copy.setdefault("title", _default_title(facts, key))
    copy.setdefault("subtitle", _default_subtitle(facts))
    copy.setdefault("summary", copy["subtitle"])
    copy.setdefault("modeLabel", _mode_label(facts))
    copy.setdefault("status", _status_line(facts))
    copy.setdefault("labels", {})
    copy.setdefault("empty", {})
    copy.setdefault("actions", [])
    copy.setdefault("rail", {})
    copy["labels"] = {
        "refresh": _pick(facts, key, ["Refresh live read", "Resync Friday", "Pull fresh state"]),
        "dismiss": _pick(facts, key, ["Close this read", "Fold the rail", "Dismiss for now"]),
        "execute": _pick(facts, key, ["Take me there", "Open the surface", "Move to work"]),
        "ask": _pick(facts, key, ["Ask Friday", "Talk it through", "Ask for a run"]),
        **copy["labels"],
    }
    copy["empty"] = {**_empty_states(facts), **copy["empty"]}
    copy["rail"] = {
        "title": "FRIDAY LIVE READ",
        "subtitle": _rail_subtitle(facts),
        "focus": facts["focus"],
        **copy["rail"],
    }
    if copy["actions"]:
        copy["primaryAction"] = copy["actions"][0]
    return copy


def normalize_view(view: str) -> str:
    key = re.sub(r"[^a-z0-9_-]+", "-", str(view or "dashboard").strip().lower()).strip("-_")
    key = ALIASES.get(key, key)
    return key if key in VIEW_KEYS else "dashboard"


def _chrome(facts: dict[str, Any]) -> dict[str, Any]:
    if facts["mission_title"]:
        title = f"Friday is driving {trim(facts['mission_title'], 58)}"
        signature = "mission-aware"
    elif facts["approval_count"]:
        title = f"Friday has {facts['approval_count']} decision {_plural(facts['approval_count'], 'gate')} open"
        signature = "decision-aware"
    elif facts["active_window"]:
        title = f"Friday is reading {trim(facts['active_window'], 58)}"
        signature = "workspace-aware"
    else:
        title = "Friday is holding the local command map"
        signature = "standby-aware"
    return {
        "title": title,
        "signature": signature,
        "modeLabel": _mode_label(facts),
        "voiceLabel": _pick(facts, "voice", ["Speak to Friday", "Voice channel", "Hands-free route"]),
        "intelligenceTitle": _pick(facts, "intel", ["Open Friday's read", "Show live reasoning", "Inspect system intelligence"]),
        "workersTitle": f"{'Restart' if facts['workers_running'] else 'Start'} {facts['workers'] or 'agent'} worker {_plural(facts['workers'] or 1, 'service')}",
        "approvalsLabel": f"{facts['approval_count'] if facts['approval_count'] <= 9 else '9+'} {_plural(facts['approval_count'] or 0, 'Approval')}",
        "notificationTitle": f"{facts['notification_count']} {_plural(facts['notification_count'], 'fresh signal')}",
    }


def _dashboard_view(facts: dict[str, Any], source: dict[str, Any], _key: str) -> dict[str, Any]:
    action = _next_action(facts)
    return {
        "title": action["headline"],
        "subtitle": action["detail"],
        "summary": _status_line(facts),
        "actions": [
            action["action"],
            _action("talk-to-friday", "Ask Friday to shape the next run", href="/chat"),
            _action("wake-workers", "Wake the worker pool", endpoint="/workers/start", method="POST"),
        ],
        "empty": {
            "urgent": "Nothing is shouting right now. Friday will lift the first blocked task, mission turn, or decision gate into this slot.",
            "activity": _idle_activity(facts),
        },
        "rail": {
            "subtitle": f"{facts['pending_tasks']} task {_plural(facts['pending_tasks'], 'thread')} and {facts['approval_count']} decision {_plural(facts['approval_count'], 'gate')}",
            "focus": action["detail"],
        },
    }


def _chat_view(facts: dict[str, Any], _source: dict[str, Any], _key: str) -> dict[str, Any]:
    return {
        "title": f"Friday chat is anchored to {facts['anchor']}",
        "subtitle": f"Use the same orchestrator that sees {facts['pending_tasks']} task {_plural(facts['pending_tasks'], 'thread')}, {facts['approval_count']} approval {_plural(facts['approval_count'], 'gate')}, and {facts['notification_count']} signal {_plural(facts['notification_count'], 'packet')}.",
        "actions": [
            _action("voice-route", "Switch to voice", href="/voice-mode"),
            _action("review-memory", "Open active memory", href="/memory"),
        ],
        "empty": {
            "messages": "This thread is clear. Friday will pull mission, memory, and desktop context into the first answer.",
        },
    }


def _voice_view(facts: dict[str, Any], _source: dict[str, Any], _key: str) -> dict[str, Any]:
    return {
        "title": f"Voice route is tuned for {facts['anchor']}",
        "subtitle": f"Friday can keep the reply short while still carrying {facts['workers']} worker {_plural(facts['workers'], 'signal')} and the active workspace context.",
        "actions": [
            _action("chat-route", "Use typed chat", href="/chat"),
            _action("repair-voice", "Repair a wake phrase", href="/settings"),
        ],
    }


def _agents_view(facts: dict[str, Any], source: dict[str, Any], _key: str) -> dict[str, Any]:
    agents = _list(source.get("agents"))
    offices = _list(source.get("offices"))
    return {
        "title": f"{len(offices) or facts['agent_count']} agent {_plural(len(offices) or facts['agent_count'], 'seat')} on Friday's bench",
        "subtitle": f"Workers are {'running' if facts['workers_running'] else 'paused'} with {facts['pending_tasks']} active task {_plural(facts['pending_tasks'], 'thread')} in range.",
        "actions": [
            _action("run-worker-cycle", "Run one worker cycle", endpoint="/workers/run-one", method="POST"),
            _action("open-tasks", "Open task queue", href="/tasks"),
        ],
        "empty": {
            "agents": f"No roster rows came back from the backend. Worker state still says {facts['workers']} service {_plural(facts['workers'], 'slot')} available.",
        },
        "rail": {"focus": agents[0].get("summary") if agents and isinstance(agents[0], dict) else facts["focus"]},
    }


def _tasks_view(facts: dict[str, Any], _source: dict[str, Any], _key: str) -> dict[str, Any]:
    return {
        "title": f"{facts['pending_tasks']} task {_plural(facts['pending_tasks'], 'thread')} need Friday's order",
        "subtitle": f"The queue is tied to {facts['anchor']} and {facts['workers']} worker {_plural(facts['workers'], 'slot')}.",
        "actions": [
            _action("create-task", "Give Friday a new task", href="/tasks"),
            _action("wake-workers", "Wake workers for the queue", endpoint="/workers/start", method="POST"),
        ],
        "empty": {
            "tasks": "The queue is clear. Drop a goal into Chat or Tasks and Friday will assign the right agent lane.",
        },
    }


def _mission_view(facts: dict[str, Any], _source: dict[str, Any], _key: str) -> dict[str, Any]:
    title = f"Mission lane: {trim(facts['mission_title'], 70)}" if facts["mission_title"] else "Mission lane is empty and ready"
    return {
        "title": title,
        "subtitle": f"Friday is tracking {facts['pending_tasks']} task {_plural(facts['pending_tasks'], 'thread')} and {facts['approval_count']} decision {_plural(facts['approval_count'], 'gate')} around this run.",
        "actions": [
            _action("new-mission", "Start a mission from Chat", href="/chat"),
            _action("review-approvals", "Review mission gates", href="/approvals"),
        ],
        "empty": {
            "missions": f"No mission is moving yet. Tell Friday the outcome and preferred stack; it will build the run plan from {facts['anchor']}.",
        },
    }


def _approvals_view(facts: dict[str, Any], _source: dict[str, Any], _key: str) -> dict[str, Any]:
    return {
        "title": f"{facts['approval_count']} decision {_plural(facts['approval_count'], 'gate')} waiting",
        "subtitle": "Friday keeps risky work gated until the request, evidence, and blast radius are visible.",
        "actions": [
            _action("open-safety", "Check policy context", href="/safety"),
            _action("open-control-room", "Open control room", href="/control-room"),
        ],
        "empty": {
            "approvals": "No decision is waiting. Friday will park anything risky here before it touches files, services, money, or outbound messages.",
        },
    }


def _safety_view(facts: dict[str, Any], source: dict[str, Any], _key: str) -> dict[str, Any]:
    guardian = _dict(source.get("guardian") or source.get("trustProof") or source.get("memoryGovernance"))
    return {
        "title": f"Safety is watching {facts['anchor']}",
        "subtitle": guardian.get("summary") or f"{facts['high_risk_count']} high-risk gateway {_plural(facts['high_risk_count'], 'event')} and {facts['approval_count']} approval {_plural(facts['approval_count'], 'gate')} are visible.",
        "actions": [
            _action("review-approvals", "Review gated actions", href="/approvals"),
            _action("control-room", "Open control room", href="/control-room"),
        ],
        "empty": {
            "highRisk": f"No high-risk gateway event is waiting around {facts['anchor']}. Friday will still ask before money, credentials, external posting, or destructive changes.",
        },
    }


def _memory_view(facts: dict[str, Any], source: dict[str, Any], _key: str) -> dict[str, Any]:
    continuity = _dict(source.get("conversationContinuity"))
    return {
        "title": f"Memory is holding {facts['anchor']}",
        "subtitle": continuity.get("summary") or f"{facts['project_count']} project {_plural(facts['project_count'], 'profile')} and {facts['pending_tasks']} task {_plural(facts['pending_tasks'], 'thread')} are available to Friday.",
        "actions": [
            _action("project-memory", "Open project memory", href="/projects"),
            _action("chat-with-memory", "Ask with memory attached", href="/chat"),
        ],
        "empty": {
            "memory": "No recent memory packet is open. Friday will write one when a preference, project fact, or repeated workflow becomes reusable.",
        },
    }


def _operators_view(facts: dict[str, Any], source: dict[str, Any], _key: str) -> dict[str, Any]:
    control = _dict(source.get("uiControl"))
    app = facts["app"] or "active app"
    return {
        "title": f"Friday can operate {labelize(app)}",
        "subtitle": control.get("summary") or f"UI control is using {facts['active_window'] or 'the desktop'} with {facts['workers']} worker {_plural(facts['workers'], 'slot')} nearby.",
        "actions": [
            _action("inspect-ui", f"Inspect {labelize(app)}", endpoint="/ui-control/context", method="POST", payload={"app": app, "instruction": f"Inspect {app} and summarize what is visible."}),
            _action("run-guided-ui-task", f"Run a guided {labelize(app)} task", endpoint="/ui-control/task", method="POST", payload={"app": app, "instruction": f"Open {app}, inspect the UI, and wait before risky actions.", "max_steps": 12}),
            _action("learn-pattern", f"Teach Friday a {labelize(app)} pattern", href="/vision"),
        ],
        "empty": {
            "sessions": f"No UI session is active for {labelize(app)}. Start with Inspect so Friday can see before it acts.",
            "evidence": f"Evidence will appear after Friday reads {labelize(app)} through screen, browser, or accessibility channels.",
        },
        "labels": {
            "primaryInstruction": f"Inspect {labelize(app)} and tell me what Friday can safely do next.",
        },
    }


def _integrations_view(facts: dict[str, Any], source: dict[str, Any], _key: str) -> dict[str, Any]:
    integrations = _dict(source.get("integrations"))
    thought = integrations.get("thought_summary") or integrations.get("summary")
    return {
        "title": f"{facts['connector_count']} connector {_plural(facts['connector_count'], 'lane')} in Friday's reach",
        "subtitle": thought or f"Friday can route work through Google, browser, local apps, and device bridges when connectors are configured.",
        "actions": [
            _action("refresh-integrations", "Refresh connector dashboard", endpoint="/integrations/dashboard/refresh", method="POST"),
            _action("open-agency", "Use connectors for outreach", href="/agency"),
        ],
        "empty": {
            "connectors": "No connector detail came back. Friday can still queue local work and will show setup prompts for any external lane.",
        },
    }


def _android_view(facts: dict[str, Any], source: dict[str, Any], _key: str) -> dict[str, Any]:
    mesh = _dict(source.get("android"))
    return {
        "title": "Friday's phone mesh is listening",
        "subtitle": mesh.get("summary") or f"Desktop context is {facts['anchor']}; Android handoffs can bridge notifications, camera input, and clipboard movement.",
        "actions": [
            _action("open-android", "Open phone mesh", href="/android"),
            _action("ring-phone", "Ring default phone", endpoint="/phone/ring", method="POST", payload={"message": "Friday is testing the device mesh."}),
        ],
        "empty": {
            "handoffs": "No phone handoff is waiting. The next notification, clipboard, or camera event will land here.",
        },
    }


def _vision_view(facts: dict[str, Any], source: dict[str, Any], _key: str) -> dict[str, Any]:
    observation = _first(_dict(item).get("summary") for item in _list(_dict(source.get("contextFusion")).get("observations")))
    return {
        "title": f"Vision is aimed at {facts['anchor']}",
        "subtitle": observation or "Friday can capture the screen, recognize recurring UI patterns, and turn those patterns into safer operator moves.",
        "actions": [
            _action("capture-screen", "Capture one screen frame", endpoint="/vision/monitor/capture", method="POST", payload={"source": "screen", "analyze": True}),
            _action("open-operators", "Use the learned UI", href="/operators"),
        ],
        "empty": {
            "frames": f"No frame is loaded for {facts['anchor']}. Capture once to give Friday a visual anchor.",
            "patterns": "No learned visual pattern is active. Successful inspections will become reusable UI memory.",
        },
    }


def _projects_view(facts: dict[str, Any], source: dict[str, Any], _key: str) -> dict[str, Any]:
    project = _first(_list(source.get("projects")) + _list(_dict(source.get("projectMemory")).get("projects")))
    project = _dict(project)
    name = project.get("name") or project.get("root") or "the current workspace"
    insight = _project_insight(project, facts)
    return {
        "title": f"Project memory is keyed to {trim(name, 64)}",
        "subtitle": f"Friday sees {facts['project_count']} project {_plural(facts['project_count'], 'profile')} and can bind coding, screenshots, decisions, and references to the right workspace.",
        "insight": insight,
        "actions": [
            _action("profile-project", "Refresh project profile", endpoint="/project-memory/profile", method="POST", payload={}),
            _action("review-project-insight", insight["action_label"], href="/chat"),
            _action("start-project-run", "Start a project run", href="/chat"),
        ],
        "empty": {
            "projects": "No project profile is active. Ask Friday to inspect the workspace and it will build one from files, tasks, and recent choices.",
            "insight": "Friday has not produced a project insight for this snapshot yet.",
        },
    }


def _agency_view(facts: dict[str, Any], source: dict[str, Any], _key: str) -> dict[str, Any]:
    agency = _dict(source.get("agency"))
    lead_count = int(agency.get("lead_count") or 0)
    drafts = len(_list(agency.get("draft_outreach")))
    approved = len(_list(agency.get("approved_outreach")))
    return {
        "title": f"Agency lane has {lead_count} lead {_plural(lead_count, 'record')}",
        "subtitle": agency.get("summary") or f"{drafts} draft outreach item {_plural(drafts, 'item')} and {approved} approved item {_plural(approved, 'item')} are ready for review before sending.",
        "actions": [
            _action("draft-outreach", "Draft outreach", href="/agency"),
            _action("approve-outreach", "Review send queue", href="/agency"),
            _action("campaign-brief", "Ask Friday for an ad campaign", href="/chat"),
        ],
        "empty": {
            "outreach": "No outreach draft is waiting. Friday can draft one from the selected lead, offer, tone, and call to action before any send step.",
        },
    }


def _control_room_view(facts: dict[str, Any], source: dict[str, Any], _key: str) -> dict[str, Any]:
    room = _dict(source.get("controlRoom"))
    return {
        "title": f"Control room sees {facts['high_risk_count']} high-risk {_plural(facts['high_risk_count'], 'event')}",
        "subtitle": room.get("summary") or f"{facts['connector_count']} connector {_plural(facts['connector_count'], 'lane')}, {facts['approval_count']} approval {_plural(facts['approval_count'], 'gate')}, and {facts['workers']} worker {_plural(facts['workers'], 'slot')} are in view.",
        "actions": [
            _action("refresh-control", "Refresh control room", endpoint="/control-room/status"),
            _action("emergency-stop", "Emergency stop", endpoint="/gateway/emergency-stop", method="POST", payload={"reason": "Dynamic interface emergency stop"}),
            _action("review-approvals", "Review gates", href="/approvals"),
        ],
        "empty": {
            "highRisk": f"No high-risk gateway event is waiting around {facts['anchor']}. Friday will escalate the next external, costly, or destructive action before it runs.",
            "errors": "No failed audit event is in the current control window.",
        },
    }


def _notifications_view(facts: dict[str, Any], source: dict[str, Any], _key: str) -> dict[str, Any]:
    notifications = _dict(source.get("notifications"))
    return {
        "title": f"{facts['notification_count']} notification {_plural(facts['notification_count'], 'signal')} in Friday's inbox",
        "subtitle": notifications.get("summary") or f"Friday will rank signals against {facts['anchor']} instead of showing a flat feed.",
        "actions": [
            _action("mark-all-read", "Clear read signals", endpoint="/notifications/mark-all-read", method="POST"),
            _action("open-control-room", "Open control room", href="/control-room"),
        ],
        "empty": {
            "notifications": "No fresh signal is waiting. Friday will surface the next alert with source, severity, and suggested action.",
        },
    }


def _settings_view(facts: dict[str, Any], _source: dict[str, Any], _key: str) -> dict[str, Any]:
    return {
        "title": "Friday settings follow the current work",
        "subtitle": f"Preferences should tune voice, workers, connectors, and permissions around {facts['anchor']}.",
        "actions": [
            _action("open-permissions", "Review permission model", href="/safety"),
            _action("voice-mode", "Tune voice route", href="/voice-mode"),
        ],
    }


def _reliability_view(facts: dict[str, Any], source: dict[str, Any], _key: str) -> dict[str, Any]:
    reliability = _dict(source.get("reliability"))
    score = reliability.get("overall") or _dict(reliability.get("latest_score")).get("overall")
    score_text = str(round(float(score))) if _is_number(score) else "unscored"
    return {
        "title": f"Reliability is {score_text}",
        "subtitle": reliability.get("summary") or f"Friday is comparing provider readiness, unsupported claims, and task health around {facts['anchor']}.",
        "actions": [
            _action("refresh-reliability", "Refresh reliability score", endpoint="/reliability/dashboard/refresh", method="POST"),
            _action("open-evaluation", "Review evidence signals", href="/safety"),
        ],
    }


def _governance_view(facts: dict[str, Any], source: dict[str, Any], _key: str) -> dict[str, Any]:
    governance = _dict(source.get("memoryGovernance"))
    return {
        "title": "Governance is shaping Friday's memory",
        "subtitle": governance.get("summary") or f"Memory, claims, and permissions are checked before Friday carries {facts['anchor']} forward.",
        "actions": [
            _action("open-memory", "Review memory", href="/memory"),
            _action("open-safety", "Review safety gates", href="/safety"),
        ],
    }


def _default_view(facts: dict[str, Any], _source: dict[str, Any], key: str) -> dict[str, Any]:
    return {
        "title": _default_title(facts, key),
        "subtitle": _default_subtitle(facts),
        "actions": [_action("ask-friday", "Ask Friday what belongs here", href="/chat")],
    }


_BUILDERS = {
    "dashboard": _dashboard_view,
    "chat": _chat_view,
    "voice-mode": _voice_view,
    "agents": _agents_view,
    "tasks": _tasks_view,
    "mission-control": _mission_view,
    "approvals": _approvals_view,
    "safety": _safety_view,
    "memory": _memory_view,
    "operators": _operators_view,
    "integrations": _integrations_view,
    "android": _android_view,
    "vision": _vision_view,
    "projects": _projects_view,
    "agency": _agency_view,
    "control-room": _control_room_view,
    "notifications": _notifications_view,
    "settings": _settings_view,
    "reliability": _reliability_view,
    "governance": _governance_view,
}


def _facts(source: dict[str, Any]) -> dict[str, Any]:
    tasks = _list(source.get("tasks"))
    missions = _list(source.get("missions"))
    agents = _list(source.get("agents"))
    offices = _list(source.get("offices"))
    approvals = _list(source.get("approvals"))
    approval_summary = _dict(source.get("approvalSummary"))
    status = _dict(source.get("status"))
    pc = _dict(source.get("pcAwareness"))
    notifications = _dict(source.get("notifications"))
    gateway = _dict(source.get("gateway"))
    control_room = _dict(source.get("controlRoom"))
    integrations = _dict(source.get("integrations"))
    project_memory = _dict(source.get("projectMemory"))
    projects = _list(source.get("projects")) or _list(project_memory.get("projects"))
    mission = _active_mission(missions)
    active_window = _clean(pc.get("active_window") or pc.get("summary"))
    app = _guess_app(active_window)
    pending_tasks = len([task for task in tasks if _clean(_dict(task).get("status")).lower() not in {"done", "completed", "cancelled"}])
    notification_items = _list(notifications.get("items"))
    connector_count = int(_num(gateway.get("enabled_count") or gateway.get("configured_count") or integrations.get("enabled_count") or 0))
    high_risk = int(_num(gateway.get("pending_high_risk") or _dict(control_room.get("gateway")).get("pending_high_risk") or 0))
    mission_title = _mission_title(mission)
    observation = _first(_dict(item).get("summary") for item in _list(_dict(source.get("contextFusion")).get("observations")))
    focus = (
        observation
        or mission_title
        or _first(_dict(task).get("title") for task in tasks)
        or active_window
        or _clean(source.get("timestamp"))
        or "the local workspace"
    )
    facts = {
        "active_window": active_window,
        "app": app,
        "workers": int(_num(status.get("workers") or 0)),
        "workers_running": bool(status.get("running")),
        "status_mode": _clean(status.get("mode")) or ("agent mode" if status.get("running") else "standby"),
        "tasks": tasks,
        "pending_tasks": pending_tasks,
        "approval_count": int(_num(approval_summary.get("count") if approval_summary else len(approvals))),
        "notification_count": int(_num(notifications.get("unread_count") or len(notification_items))),
        "mission": mission,
        "mission_title": mission_title,
        "agent_count": len(agents) or len(offices),
        "office_count": len(offices),
        "connector_count": connector_count,
        "high_risk_count": high_risk,
        "project_count": len(projects),
        "running_apps": int(_num(_dict(pc.get("stats")).get("running_apps") or 0)),
        "focus": trim(focus, 220),
    }
    facts["anchor"] = _anchor(facts)
    return facts


def _active_mission(missions: list[Any]) -> dict[str, Any]:
    for mission in missions:
        row = _dict(mission)
        if _clean(row.get("status")).lower() in {"active", "running", "in_progress", "in progress"}:
            return row
    return _dict(missions[0]) if missions else {}


def _mission_title(mission: dict[str, Any]) -> str:
    return _clean(mission.get("title") or mission.get("goal") or mission.get("summary"))


def _anchor(facts: dict[str, Any]) -> str:
    if facts.get("mission_title"):
        return trim(facts["mission_title"], 72)
    if facts.get("active_window"):
        return trim(facts["active_window"], 72)
    if facts.get("project_count"):
        return f"{facts['project_count']} project {_plural(facts['project_count'], 'profile')}"
    return "the local workspace"


def _next_action(facts: dict[str, Any]) -> dict[str, Any]:
    if facts["approval_count"]:
        count = facts["approval_count"]
        return {
            "headline": f"{count} decision {_plural(count, 'gate')} need you",
            "detail": f"Friday is holding risky or irreversible work until you review the evidence for {facts['anchor']}.",
            "action": _action("review-approvals", f"Review {count} {_plural(count, 'gate')}", href="/approvals"),
        }
    if facts["mission_title"]:
        return {
            "headline": f"Keep pressure on {trim(facts['mission_title'], 62)}",
            "detail": f"Friday has {facts['pending_tasks']} task {_plural(facts['pending_tasks'], 'thread')} and {facts['workers']} worker {_plural(facts['workers'], 'slot')} around this mission.",
            "action": _action("open-mission", "Open mission lane", href="/mission-control"),
        }
    if facts["pending_tasks"]:
        return {
            "headline": f"{facts['pending_tasks']} task {_plural(facts['pending_tasks'], 'thread')} can move next",
            "detail": f"Friday can assign the next worker pass from {facts['anchor']}.",
            "action": _action("open-tasks", "Open task queue", href="/tasks"),
        }
    if facts["notification_count"]:
        return {
            "headline": f"{facts['notification_count']} signal {_plural(facts['notification_count'], 'packet')} came in",
            "detail": f"Friday will sort the inbox against {facts['anchor']} instead of making you scan everything.",
            "action": _action("open-notifications", "Open signal inbox", href="/notifications"),
        }
    return {
        "headline": f"Friday is clear around {facts['anchor']}",
        "detail": "Nothing urgent is blocking the current workspace. This is a good moment to start the next concrete run.",
        "action": _action("start-with-chat", "Start the next run", href="/chat"),
    }


def _global_actions(facts: dict[str, Any]) -> list[dict[str, Any]]:
    actions = [_next_action(facts)["action"]]
    if facts["app"]:
        actions.append(_action("operate-active-app", f"Operate {labelize(facts['app'])}", href="/operators"))
    actions.append(_action("voice", "Talk to Friday", href="/voice-mode"))
    return actions


def _project_insight(project: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    name = project.get("name") or project.get("root") or facts["anchor"]
    architecture = _dict(project.get("architecture"))
    issue = _first(_list(project.get("common_bugs"))) or _first(_list(project.get("todos"))) or ""
    recent_fix = _first(_list(project.get("past_fixes"))) or ""
    commands = _list(project.get("commands"))
    env_count = len(_list(project.get("env_names")))
    stack = _project_stack(project)
    if issue and recent_fix:
        summary = (
            f"Friday sees {trim(name, 54)} carrying a recurring issue, {trim(issue, 78)}, "
            f"with prior repair context from {trim(recent_fix, 64)}. The next useful move is a scoped fix plan plus a proof command, not a broad refactor."
        )
        confidence = "high"
    elif issue:
        summary = (
            f"Friday sees {trim(name, 54)} with {trim(issue, 86)} as the clearest project signal. "
            f"The safest next move is to inspect the nearby files, prepare one patch path, and attach verification before editing."
        )
        confidence = "medium"
    elif architecture.get("summary"):
        summary = (
            f"Friday's current read on {trim(name, 54)} is architectural: {trim(architecture['summary'], 110)} "
            f"The next project action should refresh the profile and choose a concrete task before changing code."
        )
        confidence = "medium"
    else:
        summary = (
            f"Friday has {trim(name, 54)} in project memory, but the signal is still thin. "
            f"Run a project profile refresh so Friday can connect files, commands, risks, and recent work before proposing a fix."
        )
        confidence = "low"
    evidence = []
    if stack:
        evidence.append(f"stack:{stack}")
    if commands:
        evidence.append(f"{len(commands)} command {_plural(len(commands), 'hint')}")
    if env_count:
        evidence.append(f"{env_count} env {_plural(env_count, 'reference')}")
    if issue:
        evidence.append("issue memory")
    if recent_fix:
        evidence.append("past fix memory")
    return {
        "title": "Friday's Project Read",
        "summary": summary,
        "project": trim(name, 90),
        "signal": trim(issue or architecture.get("summary") or facts["focus"], 120),
        "confidence": confidence,
        "evidence": evidence,
        "action_label": "Ask Friday for the fix path" if issue else "Refresh project profile",
    }


def _empty_states(facts: dict[str, Any]) -> dict[str, str]:
    return {
        "urgent": "Friday has no urgent item to lift right now.",
        "missions": f"No mission is active around {facts['anchor']}.",
        "approvals": "No gated decision is waiting.",
        "tasks": "No queued task is waiting.",
        "agents": "No agent row came back in this snapshot.",
        "activity": _idle_activity(facts),
        "sessions": "No live session is attached to this surface.",
        "evidence": "No evidence packet is attached yet.",
        "errors": "No recent failure is in this window.",
        "highRisk": "No high-risk event is waiting.",
        "notifications": "No fresh notification is waiting.",
        "memory": "No recent memory packet is open.",
        "projects": "No project profile is loaded.",
        "frames": "No visual frame is loaded.",
        "patterns": "No learned UI pattern is active.",
        "connectors": "No connector detail came back.",
        "outreach": "No outreach draft is waiting.",
    }


def _idle_activity(facts: dict[str, Any]) -> str:
    return f"No recent event is competing with {facts['anchor']}. Friday will pin the next alert with source and suggested move."


def _mode_label(facts: dict[str, Any]) -> str:
    if facts["mission_title"]:
        return f"Mission: {trim(facts['mission_title'], 34)}"
    if facts["approval_count"]:
        return f"{facts['approval_count']} decision {_plural(facts['approval_count'], 'gate')}"
    if facts["active_window"]:
        return f"Watching {trim(facts['active_window'], 34)}"
    return "Observation mode"


def _status_line(facts: dict[str, Any]) -> str:
    worker = f"{facts['workers']} worker {_plural(facts['workers'], 'slot')}"
    tasks = f"{facts['pending_tasks']} task {_plural(facts['pending_tasks'], 'thread')}"
    gates = f"{facts['approval_count']} decision {_plural(facts['approval_count'], 'gate')}"
    return f"{worker}; {tasks}; {gates}; anchored to {facts['anchor']}."


def _rail_subtitle(facts: dict[str, Any]) -> str:
    return _pick(
        facts,
        "rail",
        [
            f"Friday's read on {facts['anchor']}",
            f"Live reasoning from {facts['status_mode']}",
            f"{facts['workers']} worker {_plural(facts['workers'], 'slot')} near {facts['anchor']}",
        ],
    )


def _default_title(facts: dict[str, Any], key: str) -> str:
    label = labelize(key)
    return _pick(
        facts,
        key,
        [
            f"{label} is reading {facts['anchor']}",
            f"Friday shaped {label} around {facts['anchor']}",
            f"{label} is synced to Friday's live state",
        ],
    )


def _default_subtitle(facts: dict[str, Any]) -> str:
    return f"Friday sees {facts['pending_tasks']} task {_plural(facts['pending_tasks'], 'thread')}, {facts['approval_count']} decision {_plural(facts['approval_count'], 'gate')}, and {facts['notification_count']} signal {_plural(facts['notification_count'], 'packet')}."


def _action(
    action_id: str,
    label: str,
    *,
    href: str = "",
    endpoint: str = "",
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    disabled: bool = False,
    reason: str = "",
) -> dict[str, Any]:
    item = {
        "id": action_id,
        "label": label,
        "kind": "request" if endpoint else "link",
        "method": method.upper(),
        "disabled": bool(disabled),
    }
    if href:
        item["href"] = href
    if endpoint:
        item["endpoint"] = endpoint
    if payload:
        item["payload"] = payload
    if reason:
        item["reason"] = reason
    return item


def _pick(facts: dict[str, Any], salt: str, options: list[str]) -> str:
    if not options:
        return ""
    seed = json.dumps(
        {
            "salt": salt,
            "anchor": facts.get("anchor"),
            "tasks": facts.get("pending_tasks"),
            "approvals": facts.get("approval_count"),
            "notifications": facts.get("notification_count"),
        },
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    return options[int(digest[:8], 16) % len(options)]


def _guess_app(active_window: str) -> str:
    text = active_window.lower()
    hints = [
        ("chrome", ["chrome", "google chrome"]),
        ("vscode", ["visual studio code", "code.exe", "vscode"]),
        ("terminal", ["powershell", "terminal", "cmd.exe", "windows terminal"]),
        ("gmail", ["gmail"]),
        ("calendar", ["calendar"]),
        ("figma", ["figma"]),
        ("slack", ["slack"]),
        ("discord", ["discord"]),
        ("notion", ["notion"]),
        ("github", ["github"]),
        ("postman", ["postman"]),
        ("browser", ["edge", "firefox"]),
    ]
    for app, needles in hints:
        if any(needle in text for needle in needles):
            return app
    return ""


def _project_stack(project: dict[str, Any]) -> str:
    metadata = _dict(project.get("metadata"))
    commands = " ".join(str(command).lower() for command in _list(project.get("commands")))
    env_names = " ".join(str(name).lower() for name in _list(project.get("env_names")))
    root = str(project.get("root") or project.get("name") or "").lower()
    text = f"{commands} {env_names} {root}"
    if metadata.get("has_package_json") or "npm " in text or "next" in text or "react" in text:
        return "web"
    if metadata.get("has_pyproject") or "pytest" in text or "python" in text or ".py" in text:
        return "python"
    if "go test" in text or "/cmd/" in text:
        return "go"
    if "cargo" in text or "rust" in text:
        return "rust"
    if "flutter" in text or "dart" in text:
        return "mobile"
    return ""


def labelize(value: Any) -> str:
    text = _clean(value).replace("_", " ").replace("-", " ")
    if not text:
        return "Friday"
    return " ".join(part[:1].upper() + part[1:] for part in text.split())


def trim(value: Any, limit: int = 120) -> str:
    text = _clean(value)
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)].rstrip()}..."


def _plural(count: int | float, word: str) -> str:
    return word if int(count or 0) == 1 else f"{word}s"


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first(values: Any) -> Any:
    for value in values:
        if value:
            return value
    return None


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _num(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except Exception:
        return False


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

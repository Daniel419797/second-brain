"""Executive capability layer for higher-level Friday behavior.

This module coordinates existing Friday systems into user-facing powers:
memory review, task autopilot, voice personality, life dashboard, skill
recording, documentation upkeep, personal search, trust/privacy checks,
learning profile, relationship follow-up, and deployment inspection.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import socket
import sqlite3
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from core import (
    capability_center,
    contextual_workspace,
    daily_companion,
    goal_manager,
    learning_coach,
    local_file_intelligence,
    memory,
    notification_center,
    offline_survival,
    pc_timeline,
    personal_crm,
    personal_data_timeline,
    personal_finance,
    personal_knowledge_vault,
    personal_life_os,
    privacy_vault,
    project_autopilot,
    skill_training_studio,
    task_contracts,
    task_queue,
    workspace_brain,
)
from core.config import DATA_DIR, config_value, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "executive_capabilities.sqlite3"
_LOCK = threading.Lock()

PERSONALITY_PROFILES: dict[str, dict[str, Any]] = {
    "focused": {"pace": "fast", "warmth": "low", "detail": "minimal", "instruction": "Lead with the answer and next action."},
    "gentle": {"pace": "steady", "warmth": "high", "detail": "moderate", "instruction": "Be soft, patient, and reassuring without being vague."},
    "teacher": {"pace": "slow", "warmth": "medium", "detail": "high", "instruction": "Explain concepts step by step and quiz for understanding."},
    "big_brother": {"pace": "steady", "warmth": "high", "detail": "moderate", "instruction": "Be protective, direct, encouraging, and practical."},
    "silent_operator": {"pace": "fast", "warmth": "low", "detail": "minimal", "instruction": "Speak only for confirmations, blockers, and final results."},
    "debugger": {"pace": "methodical", "warmth": "medium", "detail": "high", "instruction": "State hypothesis, evidence, test, result, and next fix."},
}

PROGRAMMING_PRIORITIES = [
    "security",
    "correctness",
    "speed and performance",
    "maintainability",
    "reliability",
    "readability",
    "scalability",
    "testability",
    "clear documentation",
    "rollback safety",
]

SENSITIVE_PATTERNS = {
    "secret": r"\b(secret|api[_ -]?key|token|password|credential|private key|ssh key|recovery phrase)\b",
    "env": r"(^|[\\/])\.env($|[\\/.])|\b\.env\b",
    "money": r"\b(bank|card|payment|salary|invoice|receipt|finance|budget)\b",
    "identity": r"\b(passport|nin|ssn|bvn|address|phone number|email address)\b",
    "messages": r"\b(send|reply|message|email|sms|whatsapp|discord)\b",
    "destructive": r"\b(delete|remove|wipe|format|reset|overwrite|drop table)\b",
}


def init_db(path: Path | None = None) -> None:
    ensure_runtime_dirs()
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=10) as conn:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                resolved_at TEXT NOT NULL,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                question TEXT NOT NULL,
                status TEXT NOT NULL,
                decision TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_reviews_status ON memory_reviews(status, created_at)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS autopilot_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                goal TEXT NOT NULL,
                sphere TEXT NOT NULL,
                root TEXT NOT NULL,
                status TEXT NOT NULL,
                current_checkpoint INTEGER NOT NULL,
                success_criteria_json TEXT NOT NULL,
                checkpoints_json TEXT NOT NULL,
                task_ids_json TEXT NOT NULL,
                summary TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS personality_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                profile TEXT NOT NULL,
                reason TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS skill_recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                transcript TEXT NOT NULL,
                workflow_id INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS skill_recording_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recording_id INTEGER NOT NULL,
                step_order INTEGER NOT NULL,
                instruction TEXT NOT NULL,
                expected_result TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS capability_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )


def generate_memory_reviews(limit: int = 12) -> dict[str, Any]:
    """Create review prompts for saved user memories and relationship facts."""
    init_db()
    candidates: list[dict[str, Any]] = []
    for item in _safe(lambda: personal_knowledge_vault.list_items(limit=limit), []):
        candidates.append(
            {
                "source": "personal_knowledge_vault",
                "source_id": str(item["id"]),
                "title": item["title"],
                "content": item.get("content", ""),
                "question": f"Is this still true: {item['title']}?",
                "metadata": {"kind": item.get("kind"), "confidence": item.get("confidence")},
            }
        )
    for person in _safe(lambda: personal_crm.search_people(limit=limit), []):
        candidates.append(
            {
                "source": "personal_crm",
                "source_id": str(person["id"]),
                "title": person["name"],
                "content": f"{person.get('relationship', '')} {person.get('notes', '')}".strip(),
                "question": f"Should I still remember {person['name']} this way?",
                "metadata": {"relationship": person.get("relationship"), "birthday": person.get("birthday")},
            }
        )
    created = []
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        for candidate in candidates[: max(1, min(100, int(limit)))]:
            existing = conn.execute(
                "SELECT * FROM memory_reviews WHERE source=? AND source_id=? AND status='pending'",
                (candidate["source"], candidate["source_id"]),
            ).fetchone()
            if existing:
                created.append(_memory_review_row(existing))
                continue
            cursor = conn.execute(
                """
                INSERT INTO memory_reviews(created_at, resolved_at, source, source_id, title, content, question, status, decision, metadata_json)
                VALUES (?, '', ?, ?, ?, ?, ?, 'pending', '', ?)
                """,
                (
                    _now(),
                    candidate["source"],
                    candidate["source_id"],
                    candidate["title"],
                    candidate["content"],
                    candidate["question"],
                    _json_dumps(candidate["metadata"]),
                ),
            )
            row = conn.execute("SELECT * FROM memory_reviews WHERE id=?", (int(cursor.lastrowid),)).fetchone()
            created.append(_memory_review_row(row))
    return {"items": created, "summary": f"{len(created)} memory review question(s) ready."}


def list_memory_reviews(status: str = "pending", limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    where = ""
    params: list[Any] = []
    if status:
        where = "WHERE status=?"
        params.append(_clean(status).lower())
    params.append(max(1, min(200, int(limit))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM memory_reviews {where} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_memory_review_row(row) for row in rows]


def resolve_memory_review(review_id: int, decision: str, note: str = "") -> dict[str, Any]:
    init_db()
    normalized = _clean(decision).lower()
    if normalized not in {"confirm", "keep", "forget", "update", "skip"}:
        normalized = "skip"
    status = "resolved"
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute("SELECT * FROM memory_reviews WHERE id=?", (int(review_id),)).fetchone()
        if existing is None:
            raise ValueError("memory review not found")
        metadata = _json_loads(existing["metadata_json"], {})
        metadata["resolution_note"] = _clean(note)
        conn.execute(
            "UPDATE memory_reviews SET status=?, decision=?, resolved_at=?, metadata_json=? WHERE id=?",
            (status, normalized, _now(), _json_dumps(metadata), int(review_id)),
        )
        row = conn.execute("SELECT * FROM memory_reviews WHERE id=?", (int(review_id),)).fetchone()
    if row is None:
        raise ValueError("memory review not found")
    result = _memory_review_row(row)
    if normalized == "forget":
        notification_center.add(
            source="memory_review",
            category="privacy",
            severity=3,
            title="Memory review requested forgetting",
            message=f"Review #{review_id} was marked forget. Manual deletion remains guarded.",
            dedupe_key=f"memory-review-forget:{review_id}",
            metadata=result,
        )
    return result


def start_task_autopilot(goal: str, *, sphere: str = "", root: str | Path = "", priority: int = 2) -> dict[str, Any]:
    """Create an end-to-end task run with checkpoints and contracts."""
    init_db()
    clean_goal = _clean(goal)
    if not clean_goal:
        raise ValueError("goal is required")
    detected_sphere = _sphere(clean_goal, sphere)
    base = _safe_root(root)
    criteria = _success_criteria(detected_sphere)
    checkpoints = _checkpoints(clean_goal, detected_sphere)
    task_ids = []
    for index, checkpoint in enumerate(checkpoints, start=1):
        task_id = task_queue.create_task(
            f"Autopilot {index}: {checkpoint['title']}",
            description=checkpoint["description"],
            agent_id=checkpoint["agent_id"],
            priority=max(1, int(priority)) + index - 1,
            input_data={
                "source": "task_autopilot",
                "goal": clean_goal,
                "sphere": detected_sphere,
                "root": str(base),
                "checkpoint": checkpoint,
                "quality_priorities": PROGRAMMING_PRIORITIES if detected_sphere == "programming" else _general_priorities(detected_sphere),
                "success_criteria": criteria,
                "ask_only_when_blocked": True,
            },
        )
        task_ids.append(task_id)
        task = task_queue.get_task(task_id)
        if task:
            task_contracts.ensure_contract(task)
            task_queue.post_message(task_id, "friday_autopilot", "Work continuously until this checkpoint is complete; ask the user only for blocked decisions or risky permissions.")
    now = _now()
    summary = f"Autopilot started for {detected_sphere} goal with {len(task_ids)} checkpoint task(s)."
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO autopilot_runs(created_at, updated_at, goal, sphere, root, status, current_checkpoint, success_criteria_json, checkpoints_json, task_ids_json, summary)
            VALUES (?, ?, ?, ?, ?, 'running', 1, ?, ?, ?, ?)
            """,
            (now, now, clean_goal, detected_sphere, str(base), _json_dumps(criteria), _json_dumps(checkpoints), _json_dumps(task_ids), summary),
        )
        row = conn.execute("SELECT * FROM autopilot_runs WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _autopilot_row(row) | {"tasks": [task_queue.get_task(task_id) for task_id in task_ids]}


def refresh_task_autopilot(run_id: int | None = None) -> dict[str, Any]:
    runs = list_task_autopilots(status="running", limit=50)
    if run_id:
        runs = [run for run in runs if int(run["id"]) == int(run_id)]
    refreshed = []
    for run in runs:
        tasks = [task_queue.get_task(task_id) for task_id in run["task_ids"]]
        active_tasks = [task for task in tasks if task and task.get("status") in task_queue.ACTIVE_STATUSES]
        done_tasks = [task for task in tasks if task and task.get("status") == "done"]
        failed_tasks = [task for task in tasks if task and task.get("status") == "failed"]
        status = "blocked" if any(task and task.get("status") == "blocked" for task in tasks) else "running"
        if failed_tasks:
            status = "needs_attention"
        if tasks and len(done_tasks) == len(tasks):
            status = "done"
        current = min(len(done_tasks) + 1, len(run["checkpoints"]) or 1)
        summary = f"Autopilot #{run['id']}: {len(done_tasks)}/{len(tasks)} checkpoints done; status {status}."
        with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
            conn.execute("UPDATE autopilot_runs SET status=?, current_checkpoint=?, summary=?, updated_at=? WHERE id=?", (status, current, summary, _now(), int(run["id"])))
        refreshed.append(get_task_autopilot(int(run["id"])) or run)
        if status in {"needs_attention", "blocked"}:
            notification_center.add(
                source="task_autopilot",
                category="approval",
                severity=4,
                title="Task autopilot needs attention",
                message=summary,
                dedupe_key=f"task-autopilot-attention:{run['id']}",
                metadata={"run_id": run["id"], "active_tasks": [task.get("id") for task in active_tasks if task]},
            )
    return {"runs": refreshed, "summary": f"Refreshed {len(refreshed)} autopilot run(s)."}


def get_task_autopilot(run_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM autopilot_runs WHERE id=?", (int(run_id),)).fetchone()
    return _autopilot_row(row) if row else None


def list_task_autopilots(status: str = "", limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    where = ""
    params: list[Any] = []
    if status:
        where = "WHERE status=?"
        params.append(_clean(status).lower())
    params.append(max(1, min(100, int(limit))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM autopilot_runs {where} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_autopilot_row(row) for row in rows]


def set_personality_profile(profile: str, reason: str = "manual") -> dict[str, Any]:
    init_db()
    key = _profile_key(profile)
    if key not in PERSONALITY_PROFILES:
        raise ValueError(f"unknown personality profile: {profile}")
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("INSERT INTO personality_events(timestamp, profile, reason) VALUES (?, ?, ?)", (_now(), key, _clean(reason)))
    return current_personality_profile()


def current_personality_profile() -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM personality_events ORDER BY id DESC LIMIT 1").fetchone()
    profile = str(row["profile"]) if row else str(config_value("voice_personality_default_profile", "focused"))
    if profile not in PERSONALITY_PROFILES:
        profile = "focused"
    return {
        "profile": profile,
        "available": PERSONALITY_PROFILES,
        "settings": PERSONALITY_PROFILES[profile],
        "reason": str(row["reason"]) if row else "default",
        "summary": f"Voice personality is {profile.replace('_', ' ')}.",
    }


def life_dashboard() -> dict[str, Any]:
    dashboard = {
        "daily": _safe(daily_companion.status, {}),
        "plan": _safe(personal_life_os.daily_plan, {}),
        "next_action": _safe(goal_manager.next_goal_action, {}),
        "goals": _safe(goal_manager.progress_summary, {}),
        "pc_health": _safe(lambda: capability_center.maintenance_report(light=True), {}),
        "projects": _safe(lambda: project_autopilot.recent_reports(limit=5), []),
        "finance": _safe(personal_finance.summary, {}),
        "relationships": _safe(relationship_assistant, {}),
        "learning": _safe(learning_twin, {}),
        "notifications": _safe(notification_center.summary, {}),
        "offline": _safe(offline_survival.status, {}),
    }
    summary = "Life dashboard ready: "
    summary += dashboard.get("plan", {}).get("summary") or dashboard.get("daily", {}).get("summary") or "no plan saved yet."
    return dashboard | {"summary": summary}


def start_skill_recording(name: str) -> dict[str, Any]:
    init_db()
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO skill_recordings(created_at, updated_at, name, status, transcript, workflow_id) VALUES (?, ?, ?, 'recording', '', 0)",
            (now, now, _clean(name) or "Untitled workflow"),
        )
        row = conn.execute("SELECT * FROM skill_recordings WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _recording_row(row)


def add_skill_recording_step(recording_id: int, narration: str, expected_result: str = "") -> dict[str, Any]:
    init_db()
    steps = _parse_steps(narration)
    if not steps:
        steps = [_clean(narration)]
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        order_row = conn.execute("SELECT COALESCE(MAX(step_order), 0) + 1 FROM skill_recording_steps WHERE recording_id=?", (int(recording_id),)).fetchone()
        order = int(order_row[0])
        for instruction in steps:
            conn.execute(
                "INSERT INTO skill_recording_steps(recording_id, step_order, instruction, expected_result) VALUES (?, ?, ?, ?)",
                (int(recording_id), order, instruction, _clean(expected_result)),
            )
            order += 1
        conn.execute("UPDATE skill_recordings SET transcript=TRIM(transcript || char(10) || ?), updated_at=? WHERE id=?", (_clean(narration), _now(), int(recording_id)))
    item = get_skill_recording(recording_id)
    return item or {}


def finish_skill_recording(recording_id: int) -> dict[str, Any]:
    recording = get_skill_recording(recording_id)
    if not recording:
        raise ValueError("recording not found")
    workflow = skill_training_studio.start_workflow(recording["name"], description=recording["transcript"], tags=["recorded_workflow"])
    for step in recording["steps"]:
        workflow = skill_training_studio.add_step(workflow["id"], step["instruction"], expected_result=step["expected_result"])
    published = skill_training_studio.finish_workflow(workflow["id"])
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE skill_recordings SET status='published', workflow_id=?, updated_at=? WHERE id=?", (int(published["id"]), _now(), int(recording_id)))
    return get_skill_recording(recording_id) or {}


def get_skill_recording(recording_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM skill_recordings WHERE id=?", (int(recording_id),)).fetchone()
        if row is None:
            return None
        steps = conn.execute("SELECT * FROM skill_recording_steps WHERE recording_id=? ORDER BY step_order", (int(recording_id),)).fetchall()
    return _recording_row(row) | {"steps": [_step_row(step) for step in steps]}


def list_skill_recordings(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM skill_recordings ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit))),)).fetchall()
    return [get_skill_recording(int(row["id"])) or _recording_row(row) for row in rows]


def update_documentation(root: str | Path = "") -> dict[str, Any]:
    base = _safe_root(root)
    workspace_docs = _safe(lambda: workspace_brain.generate_docs(base), {"summary": "Workspace docs unavailable."})
    auto_docs = _safe(lambda: capability_center.workspace_auto_docs(base), {"summary": "Auto docs unavailable."})
    deploy_notes = _write_deployment_notes(base)
    payload = {"workspace_docs": workspace_docs, "auto_docs": auto_docs, "deployment_notes": deploy_notes}
    _record_event("documentation", "Autonomous documentation run", f"Documentation updated for {base.name}.", payload)
    return payload | {"root": str(base), "summary": f"Documentation brain updated docs for {base.name}."}


def personal_search(query: str, *, limit: int = 8) -> dict[str, Any]:
    query = _clean(query)
    results: list[dict[str, Any]] = []
    file_answer = _safe(lambda: local_file_intelligence.answer(query), {})
    if file_answer:
        results.append({"source": "local_files", "title": "Local file answer", "summary": file_answer.get("answer") or file_answer.get("summary"), "items": file_answer.get("results") or []})
    timeline = _safe(lambda: personal_data_timeline.query(query, limit=limit), {})
    if timeline:
        results.append({"source": "personal_timeline", "title": "Timeline", "summary": timeline.get("summary"), "items": timeline.get("items") or []})
    vault = _safe(lambda: personal_knowledge_vault.search(query, limit=limit), [])
    if vault:
        results.append({"source": "personal_knowledge", "title": "Knowledge vault", "summary": f"{len(vault)} memory match(es).", "items": vault})
    private = _safe(lambda: privacy_vault.search(query, limit=limit), [])
    if private:
        results.append({"source": "privacy_vault", "title": "Privacy vault", "summary": f"{len(private)} sensitive redacted match(es).", "items": private})
    pc_items = _safe(lambda: _filter_pc_timeline(query, limit), [])
    if pc_items:
        results.append({"source": "pc_timeline", "title": "PC timeline", "summary": f"{len(pc_items)} PC event match(es).", "items": pc_items})
    facts = _safe(lambda: memory.recall(query, n=limit), [])
    if facts:
        results.append({"source": "conversation_memory", "title": "Conversation facts", "summary": f"{len(facts)} recalled fact(s).", "items": [{"fact": fact} for fact in facts]})
    summary = f"Personal search found {sum(len(item.get('items') or []) for item in results)} item(s) across {len(results)} source(s)."
    payload = {"query": query, "results": results, "summary": summary}
    _record_event("personal_search", "Personal search", summary, payload)
    return payload


def trust_assessment(instruction: str, *, domain: str = "general") -> dict[str, Any]:
    instruction = _clean(instruction)
    firewall = privacy_firewall_check(instruction, context=domain)
    risk = _risk_level(instruction, domain, firewall)
    evidence = _evidence_for(instruction, domain)
    confidence = _trust_confidence(risk, evidence, firewall)
    requires_approval = risk in {"high", "critical"} or firewall["decision"] == "ask"
    fallback = _fallback_plan(risk, domain)
    payload = {
        "instruction": instruction,
        "domain": domain,
        "risk": risk,
        "confidence": confidence,
        "evidence": evidence,
        "fallback_plan": fallback,
        "privacy": firewall,
        "requires_approval": requires_approval,
        "summary": f"Trust meter: {risk} risk, {confidence:.0%} confidence; approval {'required' if requires_approval else 'not required'}.",
    }
    _record_event("trust_meter", "Trust assessment", payload["summary"], payload)
    return payload


def privacy_firewall_check(instruction: str, *, context: str = "") -> dict[str, Any]:
    text = f"{instruction} {context}".lower()
    triggers = []
    for name, pattern in SENSITIVE_PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            triggers.append(name)
    sensitivity = "secret" if any(item in triggers for item in {"secret", "env"}) else "sensitive" if triggers else "normal"
    decision = "ask" if sensitivity in {"secret", "sensitive"} else "allow"
    if "reveal" in text and sensitivity == "secret":
        decision = "ask"
    payload = {
        "instruction": _clean(instruction),
        "context": _clean(context),
        "sensitivity": sensitivity,
        "triggers": triggers,
        "decision": decision,
        "summary": "Privacy firewall requires approval." if decision == "ask" else "Privacy firewall allows this.",
    }
    _record_event("privacy_firewall", "Privacy firewall check", payload["summary"], payload)
    return payload


def learning_twin() -> dict[str, Any]:
    progress = _safe(learning_coach.progress, {})
    due = progress.get("due") or []
    accuracy = float(progress.get("accuracy") or 0)
    if accuracy < 0.5 and int(progress.get("attempts") or 0) > 0:
        style = "Use smaller steps and more examples."
    elif due:
        style = "Keep reviews short and frequent."
    else:
        style = "Add new cards from current work."
    return {
        "progress": progress,
        "learning_style": style,
        "custom_quiz": _safe(lambda: learning_coach.quiz(limit=5), {"cards": []}),
        "summary": f"Learning twin: {progress.get('cards', 0)} cards, {len(due)} due. {style}",
    }


def relationship_assistant() -> dict[str, Any]:
    people = _safe(lambda: personal_crm.search_people(limit=20), [])
    followups = _safe(lambda: personal_crm.upcoming_followups(limit=10), [])
    birthdays = [person for person in people if _birthday_soon(person.get("birthday", ""))]
    prompts = []
    for item in followups[:3]:
        prompts.append(f"Follow up with {item.get('person_name')}: {item.get('promise') or item.get('summary')}")
    for person in birthdays[:3]:
        prompts.append(f"Birthday soon: {person['name']} ({person.get('birthday')})")
    return {"people": people[:8], "followups": followups, "birthdays": birthdays, "prompts": prompts, "summary": f"{len(followups)} follow-up(s), {len(birthdays)} birthday reminder(s)."}


def deployment_inspect(target: str = "", *, root: str | Path = "") -> dict[str, Any]:
    base = _safe_root(root)
    normalized_target = _normalize_url(target)
    status = _http_status(normalized_target) if normalized_target else {"summary": "No deployment URL provided."}
    dns = _dns_summary(normalized_target) if normalized_target else {"summary": "No DNS target."}
    headers = _safe(lambda: capability_center.web_security_headers(normalized_target), {"summary": "Security header check needs verified scope or target."}) if normalized_target else {"summary": "No target."}
    project = _safe(lambda: project_autopilot.inspect_project(base, run_tests=False, notify=False), {"summary": "Project inspection unavailable."})
    env_refs = _env_references(base)
    rollback = _rollback_notes(base)
    payload = {
        "target": normalized_target,
        "root": str(base),
        "http": status,
        "status": status,
        "dns": dns,
        "security_headers": headers,
        "project": project,
        "env_references": env_refs,
        "rollback": rollback,
        "summary": f"Deployment commander inspected {normalized_target or base.name}. {status.get('summary', '')}",
    }
    _record_event("deployment", "Deployment inspection", payload["summary"], payload)
    return payload


def summary() -> dict[str, Any]:
    reviews = list_memory_reviews(limit=5)
    all_reviews = list_memory_reviews(limit=100)
    autopilots = list_task_autopilots(limit=5)
    return {
        "memory_reviews": {"pending": reviews, "summary": f"{len(all_reviews)} pending memory review(s)."},
        "autopilot": {"runs": autopilots, "summary": f"{len(autopilots)} recent autopilot run(s)."},
        "personality": current_personality_profile(),
        "life_dashboard": life_dashboard(),
        "skill_recordings": list_skill_recordings(limit=5),
        "learning_twin": learning_twin(),
        "relationships": relationship_assistant(),
        "summary": "Executive capabilities are online.",
    }


def recent_events(kind: str = "", limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    where = ""
    params: list[Any] = []
    if kind:
        where = "WHERE kind=?"
        params.append(_clean(kind))
    params.append(max(1, min(100, int(limit))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM capability_events {where} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_event_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM memory_reviews")
        conn.execute("DELETE FROM autopilot_runs")
        conn.execute("DELETE FROM personality_events")
        conn.execute("DELETE FROM skill_recording_steps")
        conn.execute("DELETE FROM skill_recordings")
        conn.execute("DELETE FROM capability_events")


def _success_criteria(sphere: str) -> list[str]:
    if sphere == "programming":
        return [
            "Requirements are understood and broken into checkpoints.",
            "Security risks are identified and mitigated.",
            "Implementation favors speed, performance, maintainability, reliability, readability, scalability, and tests.",
            "Relevant tests/builds are run or explicit limits are recorded.",
            "Docs or handoff notes are updated.",
            "Friday reports evidence, residual risks, and next action.",
        ]
    return [
        "Goal is decomposed into checkpoints.",
        "Relevant research/context is gathered.",
        "Execution plan includes verification and risk controls.",
        "Progress is reported through tasks/checkpoints.",
        "Friday asks only when blocked or permission is required.",
    ]


def _checkpoints(goal: str, sphere: str) -> list[dict[str, str]]:
    if sphere == "programming":
        return [
            {"title": "Understand and scope", "agent_id": "project_manager", "description": f"Clarify the programming goal and success criteria: {goal}"},
            {"title": "Research and architecture", "agent_id": "research_analyst", "description": "Gather relevant docs, repo context, risks, and design options."},
            {"title": "Implementation plan", "agent_id": "senior_developer", "description": "Plan secure, performant, maintainable changes with rollback strategy."},
            {"title": "Security review", "agent_id": "cybersecurity_analyst", "description": "Identify abuse cases, secret exposure, auth risks, and hardening steps."},
            {"title": "Quality verification", "agent_id": "qa_engineer", "description": "Define and run/prepare focused tests, reliability checks, and regression coverage."},
            {"title": "Documentation and final report", "agent_id": "brand_content_designer", "description": "Update docs and summarize evidence, tradeoffs, residual risks, and next step."},
        ]
    return [
        {"title": "Understand and decompose", "agent_id": "project_manager", "description": f"Break down this goal: {goal}"},
        {"title": "Research", "agent_id": "research_analyst", "description": "Gather necessary context and evidence."},
        {"title": "Execution plan", "agent_id": "ceo", "description": "Plan the work, risks, tools, and checkpoints."},
        {"title": "Verification", "agent_id": "qa_engineer", "description": "Verify outputs against success criteria."},
        {"title": "Final report", "agent_id": "project_manager", "description": "Summarize completion evidence and remaining risks."},
    ]


def _sphere(goal: str, explicit: str = "") -> str:
    explicit = _clean(explicit).lower()
    if explicit:
        return explicit
    lowered = goal.lower()
    if re.search(r"\b(code|program|app|bug|test|api|frontend|backend|deploy|repo|python|javascript|nextjs|electron)\b", lowered):
        return "programming"
    if re.search(r"\b(write|essay|content|script|blog)\b", lowered):
        return "writing"
    if re.search(r"\b(study|learn|math|english|quiz)\b", lowered):
        return "learning"
    return "general"


def _general_priorities(sphere: str) -> list[str]:
    return ["safety", "accuracy", "clarity", "speed", "reliability", "maintainability", "user approval when risky", f"{sphere} best practices"]


def _risk_level(instruction: str, domain: str, firewall: dict[str, Any]) -> str:
    text = f"{instruction} {domain}".lower()
    if firewall.get("sensitivity") == "secret" or re.search(SENSITIVE_PATTERNS["destructive"], text):
        return "critical"
    if firewall.get("sensitivity") == "sensitive" or re.search(r"\b(deploy|send|email|payment|scan|shell|install|modify|write)\b", text):
        return "high"
    if re.search(r"\b(open|click|download|web|phone|file)\b", text):
        return "medium"
    return "low"


def _evidence_for(instruction: str, domain: str) -> list[dict[str, Any]]:
    evidence = [{"kind": "instruction", "summary": instruction[:300]}]
    if "code" in domain or "program" in domain or "repo" in instruction.lower():
        evidence.append({"kind": "workspace", "summary": _safe(lambda: contextual_workspace.summary().get("summary"), "No workspace context yet.")})
    if re.search(r"\b(file|pdf|download|folder)\b", instruction.lower()):
        evidence.append({"kind": "local_files", "summary": "Local file intelligence can search indexed files."})
    return evidence


def _trust_confidence(risk: str, evidence: list[dict[str, Any]], firewall: dict[str, Any]) -> float:
    base = {"low": 0.82, "medium": 0.68, "high": 0.54, "critical": 0.42}.get(risk, 0.6)
    base += min(0.1, len(evidence) * 0.025)
    if firewall.get("decision") == "ask":
        base -= 0.08
    return round(max(0.15, min(0.95, base)), 3)


def _fallback_plan(risk: str, domain: str) -> str:
    if risk in {"critical", "high"}:
        return "Pause, ask for approval, create backup or dry-run plan, then proceed only with verified evidence."
    if domain == "programming":
        return "Work in small checkpoints, run focused tests, and report residual risks."
    return "Use read-only inspection first, then take the smallest reversible action."


def _write_deployment_notes(base: Path) -> dict[str, Any]:
    docs = base / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    path = docs / "friday_deployment_commander.md"
    package = base / "package.json"
    requirements = base / "requirements.txt"
    body = [
        "# Friday Deployment Commander Notes",
        "",
        f"Generated: {_now()}",
        f"Root: `{base}`",
        "",
        "## Environment",
        "- Keep `.env` local and out of commits.",
        "- Record required variable names in `.env.example`, not secret values.",
        "",
        "## Build And Test",
    ]
    if package.exists():
        body.append("- Node project detected. Check `npm run build`, `npm test`, and deployment logs.")
    if requirements.exists():
        body.append("- Python project detected. Check virtualenv, `pytest`, and dependency audit.")
    body.extend(["", "## Rollback", "- Keep the last known good deployment/build ID.", "- Roll back before debugging live user-facing failures when impact is high."])
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return {"path": str(path), "summary": f"Deployment notes written to {path}."}


def _http_status(url: str) -> dict[str, Any]:
    if not url:
        return {"ok": False, "summary": "No URL."}
    try:
        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "FridayDeploymentCommander/1.0"})
        with urllib.request.urlopen(request, timeout=8) as response:
            return {"ok": True, "status": int(response.status), "url": url, "summary": f"{url} returned HTTP {response.status}."}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": int(exc.code), "url": url, "summary": f"{url} returned HTTP {exc.code}."}
    except Exception as exc:
        return {"ok": False, "status": 0, "url": url, "summary": f"Could not reach {url}: {exc}"}


def _dns_summary(url: str) -> dict[str, Any]:
    host = re.sub(r"^https?://", "", url).split("/", 1)[0].split(":", 1)[0]
    try:
        info = socket.getaddrinfo(host, None)
        addresses = sorted({item[4][0] for item in info})[:8]
        return {"ok": True, "host": host, "addresses": addresses, "summary": f"{host} resolves to {', '.join(addresses[:3])}."}
    except Exception as exc:
        return {"ok": False, "host": host, "addresses": [], "summary": f"DNS lookup failed for {host}: {exc}"}


def _env_references(base: Path) -> dict[str, Any]:
    env_example = base / ".env.example"
    config_files = [path for path in [env_example, base / "render.yaml", base / "docker-compose.yml", base / "Dockerfile"] if path.exists()]
    refs = []
    for path in config_files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        names = sorted(set(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", text)))[:80]
        refs.append({"path": str(path), "env_names": names})
    return {"files": refs, "summary": f"{sum(len(item['env_names']) for item in refs)} env/config reference(s) found without reading secret values."}


def _rollback_notes(base: Path) -> dict[str, Any]:
    reports = _safe(lambda: project_autopilot.recent_reports(limit=3, root=base), [])
    return {"reports": reports, "summary": "Rollback plan: keep last good build, config snapshot, and revert small change sets first."}


def _birthday_soon(value: str) -> bool:
    text = _clean(value)
    if not text:
        return False
    for fmt in ("%Y-%m-%d", "%m-%d", "%d-%m"):
        try:
            parsed = dt.datetime.strptime(text, fmt)
            now = dt.datetime.now()
            day = parsed.replace(year=now.year)
            if 0 <= (day.date() - now.date()).days <= 14:
                return True
        except ValueError:
            continue
    return False


def _parse_steps(text: str) -> list[str]:
    cleaned = _clean(text)
    if not cleaned:
        return []
    parts = re.split(r"\b(?:first|then|next|after that|finally)\b|[;\n]+|\d+\.\s*", cleaned, flags=re.IGNORECASE)
    return [_clean(part) for part in parts if _clean(part)]


def _filter_pc_timeline(query: str, limit: int) -> list[dict[str, Any]]:
    terms = {part for part in re.split(r"[^a-z0-9_]+", str(query or "").lower()) if len(part) > 2}
    items = pc_timeline.recent_events(limit=max(20, limit * 4))
    if not terms:
        return items[:limit]
    matched = []
    for item in items:
        haystack = " ".join(str(item.get(key, "")) for key in ("event_type", "title", "summary", "source")).lower()
        if terms & {part for part in re.split(r"[^a-z0-9_]+", haystack) if len(part) > 2}:
            matched.append(item)
    return matched[:limit]


def _record_event(kind: str, title: str, summary_text: str, payload: dict[str, Any]) -> int:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            "INSERT INTO capability_events(timestamp, kind, title, summary, payload_json) VALUES (?, ?, ?, ?, ?)",
            (_now(), kind, title, summary_text, _json_dumps(payload)),
        )
        return int(cursor.lastrowid)


def _memory_review_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "resolved_at": str(row["resolved_at"]),
        "source": str(row["source"]),
        "source_id": str(row["source_id"]),
        "title": str(row["title"]),
        "content": str(row["content"]),
        "question": str(row["question"]),
        "status": str(row["status"]),
        "decision": str(row["decision"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _autopilot_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "goal": str(row["goal"]),
        "sphere": str(row["sphere"]),
        "root": str(row["root"]),
        "status": str(row["status"]),
        "current_checkpoint": int(row["current_checkpoint"]),
        "success_criteria": _json_loads(row["success_criteria_json"], []),
        "checkpoints": _json_loads(row["checkpoints_json"], []),
        "task_ids": _json_loads(row["task_ids_json"], []),
        "summary": str(row["summary"]),
    }


def _recording_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "name": str(row["name"]),
        "status": str(row["status"]),
        "transcript": str(row["transcript"]),
        "workflow_id": int(row["workflow_id"]),
    }


def _step_row(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _event_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "kind": str(row["kind"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "payload": _json_loads(row["payload_json"], {}),
    }


def _profile_key(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")


def _normalize_url(value: str) -> str:
    text = _clean(value)
    if not text:
        return ""
    if not re.match(r"^https?://", text, re.IGNORECASE):
        text = "https://" + text
    return text


def _safe_root(root: str | Path = "") -> Path:
    candidate = resolve_coding_root(root)
    try:
        resolved = candidate.resolve()
    except Exception:
        resolved = resolve_coding_root()
    fallback = resolve_coding_root()
    return resolved if resolved.exists() and resolved.is_dir() else fallback


def _safe(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

"""Approval-gated mission kernel for long autonomous Friday work."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import backup_recovery, notification_center, task_contracts, task_queue
from core.config import DATA_DIR, ROOT_DIR, config_value, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "mission_control.sqlite3"
_LOCK = threading.Lock()

PHASES: list[dict[str, str]] = [
    {"name": "intake", "agent": "product_manager", "title": "Clarify mission goal and constraints"},
    {"name": "research", "agent": "research_analyst", "title": "Research context, examples, risks, and sources"},
    {"name": "architecture", "agent": "senior_developer", "title": "Plan architecture and technical approach"},
    {"name": "design", "agent": "ui_ux_designer", "title": "Prepare UX, workflow, and interaction design"},
    {"name": "design_preview_approval", "agent": "project_manager", "title": "Show UI preview and wait for approval"},
    {"name": "implementation", "agent": "junior_developer", "title": "Implement the approved build plan safely"},
    {"name": "autonomous_qa", "agent": "qa_engineer", "title": "Run autonomous QA evidence checks"},
    {"name": "documentation", "agent": "brand_content_designer", "title": "Update docs, notes, and user-facing explanation"},
    {"name": "release_prep", "agent": "devops", "title": "Prepare release, changelog, risks, and rollback notes"},
    {"name": "deployment_approval", "agent": "project_manager", "title": "Wait for explicit deploy approval"},
    {"name": "deployment_runbook", "agent": "devops", "title": "Prepare or execute deployment runbook after approval"},
    {"name": "final_proof", "agent": "ceo", "title": "Collect final proof and completion report"},
]

FINAL_STATUSES = {"completed", "stopped", "cancelled", "failed"}
MISSION_CHANNELS = {"conversation", "background_mission", "pc_control", "agent_question", "urgent_alert"}
DESIGN_PREVIEW_APPROVAL_KIND = "design_preview"
HELD_PHASE_SCHEDULED_AT = "2099-12-31T23:59:59+00:00"
DESIGN_GATED_PHASES = {
    "design_preview_approval",
    "implementation",
    "autonomous_qa",
    "documentation",
    "release_prep",
    "deployment_approval",
    "deployment_runbook",
    "final_proof",
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
            CREATE TABLE IF NOT EXISTS mission_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                goal TEXT NOT NULL,
                mission_type TEXT NOT NULL,
                root TEXT NOT NULL,
                status TEXT NOT NULL,
                current_phase TEXT NOT NULL,
                authority_mode TEXT NOT NULL,
                deploy_policy TEXT NOT NULL,
                summary TEXT NOT NULL,
                task_ids_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mission_runs_status ON mission_runs(status, updated_at)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mission_phases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id INTEGER NOT NULL,
                phase_order INTEGER NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                assigned_agent TEXT NOT NULL,
                task_id INTEGER,
                summary TEXT NOT NULL,
                evidence_count INTEGER NOT NULL,
                blocker_count INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mission_phases_mission ON mission_phases(mission_id, phase_order)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mission_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                channel TEXT NOT NULL,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mission_events_mission ON mission_events(mission_id, id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mission_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id INTEGER NOT NULL,
                phase_name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mission_evidence_mission ON mission_evidence(mission_id, id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mission_blockers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id INTEGER NOT NULL,
                phase_name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                severity INTEGER NOT NULL,
                status TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                resolution TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mission_blockers_mission ON mission_blockers(mission_id, status)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mission_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mission_approvals_mission ON mission_approvals(mission_id, status)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS desktop_locks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id INTEGER NOT NULL,
                owner TEXT NOT NULL,
                status TEXT NOT NULL,
                acquired_at TEXT NOT NULL,
                released_at TEXT NOT NULL,
                reason TEXT NOT NULL
            )
            """
        )


def create_mission(
    goal: str,
    *,
    root: str | Path = "",
    mission_type: str = "",
    authority_mode: str = "",
    deploy_policy: str = "",
    priority: int = 2,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a deterministic, approval-gated long mission with phase tasks."""

    init_db()
    clean_goal = _clean(goal) or "Untitled mission"
    mission_type = _normalize_type(mission_type or _infer_type(clean_goal))
    authority_mode = _clean(authority_mode or str(config_value("mission_default_authority_mode", "approval_gated"))) or "approval_gated"
    deploy_policy = _clean(deploy_policy or str(config_value("mission_default_deploy_policy", "approve_step"))) or "approve_step"
    mission_root = resolve_coding_root(root) if mission_type == "project_builder" else _safe_root(root)
    now = _now()
    meta = dict(metadata or {})
    design_preview_gate = _requires_design_preview_gate(clean_goal, mission_type, meta)
    meta.update(
        {
            "channels": sorted(MISSION_CHANNELS),
            "non_interrupting_work_mode": True,
            "explicit_stop_required": True,
            "deployments_require_approval": True,
            "design_preview_gate": design_preview_gate,
        }
    )
    task_ids: dict[str, int] = {}
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO mission_runs(created_at, updated_at, goal, mission_type, root, status, current_phase, authority_mode, deploy_policy, summary, task_ids_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, 'running', 'intake', ?, ?, ?, '{}', ?)
            """,
            (
                now,
                now,
                clean_goal,
                mission_type,
                str(mission_root),
                authority_mode,
                deploy_policy,
                f"Mission started: {clean_goal}",
                _json_dumps(meta),
            ),
        )
        mission_id = int(cursor.lastrowid)
        for index, phase in enumerate(PHASES, start=1):
            task_id = _create_phase_task(
                mission_id,
                phase,
                clean_goal,
                mission_root,
                mission_type,
                priority + index,
                hold_until_released=phase["name"] == "design_preview_approval" or (design_preview_gate and phase["name"] in DESIGN_GATED_PHASES),
            )
            task_ids[phase["name"]] = task_id
            conn.execute(
                """
                INSERT INTO mission_phases(mission_id, phase_order, name, status, assigned_agent, task_id, summary, evidence_count, blocker_count, started_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?, '')
                """,
                (
                    mission_id,
                    index,
                    phase["name"],
                    "active" if index == 1 else "pending",
                    phase["agent"],
                    task_id,
                    phase["title"],
                    now if index == 1 else "",
                ),
            )
        conn.execute("UPDATE mission_runs SET task_ids_json=? WHERE id=?", (_json_dumps(task_ids), mission_id))
        _insert_event_conn(
            conn,
            mission_id,
            "background_mission",
            "created",
            "Mission created",
            "Friday created phase tasks, contracts, approval gates, and evidence tracking.",
            {"task_ids": task_ids, "mission_type": mission_type},
        )
        _insert_evidence_conn(
            conn,
            mission_id,
            "intake",
            "mission_control",
            "Mission contract",
            "Mission uses fixed phases, approval-gated deployment, and final proof requirements.",
            {"goal": clean_goal, "authority_mode": authority_mode, "deploy_policy": deploy_policy},
        )
        if deploy_policy == "approve_step":
            _insert_approval_conn(
                conn,
                mission_id,
                "deploy",
                "pending",
                "Deploy approval required",
                "Friday may prepare deploy steps, but cannot run deployment until you approve deploy for this mission.",
                {"approval_phrase": f"approve deploy {mission_id}"},
            )
    _safe_snapshot_config(mission_id)
    _notify("Mission started", f"Mission #{mission_id}: {clean_goal}", severity=2, metadata={"mission_id": mission_id})
    return get_mission(mission_id) or {"id": mission_id, "goal": clean_goal, "status": "running"}


def list_missions(status: str = "", limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    clause = ""
    params: list[Any] = []
    if status:
        clause = "WHERE status=?"
        params.append(_clean(status).lower())
    params.append(max(1, min(200, int(limit or 20))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM mission_runs {clause} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_hydrate_run(row, include_children=False) for row in rows]


def get_mission(mission_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM mission_runs WHERE id=?", (int(mission_id),)).fetchone()
    if not row:
        return None
    return _hydrate_run(row, include_children=True)


def pause_mission(mission_id: int, note: str = "") -> dict[str, Any]:
    return _set_status(mission_id, "paused", note or "Mission paused by user.", channel="conversation", event_type="paused")


def resume_mission(mission_id: int, note: str = "") -> dict[str, Any]:
    mission = _set_status(mission_id, "running", note or "Mission resumed by user.", channel="conversation", event_type="resumed")
    refresh_mission(mission_id)
    return get_mission(mission_id) or mission


def stop_mission(mission_id: int, note: str = "") -> dict[str, Any]:
    mission = get_mission(mission_id)
    if mission:
        for task_id in (mission.get("task_ids") or {}).values():
            task_queue.cancel_task(int(task_id))
    release_desktop_lock(mission_id, reason="Mission stopped.")
    return _set_status(mission_id, "stopped", note or "Mission stopped by user.", channel="conversation", event_type="stopped")


def approve_mission(mission_id: int, kind: str = "next_step", note: str = "") -> dict[str, Any]:
    init_db()
    now = _now()
    normalized_kind = _clean(kind or "next_step").lower().replace(" ", "_")
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            """
            UPDATE mission_approvals
            SET status='approved', timestamp=?, summary=summary || ?
            WHERE mission_id=? AND kind=? AND status='pending'
            """,
            (now, f" Approved: {_clean(note)}" if note else " Approved.", int(mission_id), normalized_kind),
        )
        _insert_event_conn(
            conn,
            int(mission_id),
            "conversation",
            "approval",
            "Mission approval recorded",
            f"Approved {normalized_kind}.",
            {"note": note},
        )
    if normalized_kind == DESIGN_PREVIEW_APPROVAL_KIND:
        refresh_mission(mission_id)
    return get_mission(mission_id) or {}


def approve_deploy(mission_id: int, note: str = "") -> dict[str, Any]:
    init_db()
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            """
            UPDATE mission_approvals
            SET status='approved', timestamp=?, summary=summary || ?
            WHERE mission_id=? AND kind='deploy' AND status='pending'
            """,
            (now, f" Approved: {_clean(note)}" if note else " Approved.", int(mission_id)),
        )
        if conn.total_changes == 0:
            _insert_approval_conn(
                conn,
                int(mission_id),
                "deploy",
                "approved",
                "Deploy approval granted",
                _clean(note) or "User approved deployment step.",
                {"note": note},
            )
        _insert_event_conn(
            conn,
            int(mission_id),
            "conversation",
            "deploy_approved",
            "Deploy approval recorded",
            "Friday may run deployment/runbook steps for this mission.",
            {"note": note},
        )
        conn.execute(
            "UPDATE mission_phases SET status='active', started_at=CASE WHEN started_at='' THEN ? ELSE started_at END WHERE mission_id=? AND name='deployment_runbook' AND status='pending'",
            (now, int(mission_id)),
        )
    return get_mission(mission_id) or {}


def refresh_mission(mission_id: int | None = None) -> dict[str, Any]:
    """Sync mission phases from task state and enforce final-proof requirements."""

    init_db()
    missions = [get_mission(int(mission_id))] if mission_id else list_missions(status="running", limit=50) + list_missions(status="blocked", limit=50) + list_missions(status="paused", limit=50)
    refreshed: list[dict[str, Any]] = []
    for mission in [item for item in missions if item]:
        if mission.get("status") in FINAL_STATUSES or mission.get("status") == "paused":
            refreshed.append(mission)
            continue
        _refresh_one(int(mission["id"]))
        latest = get_mission(int(mission["id"]))
        if latest:
            refreshed.append(latest)
    return {"refreshed": len(refreshed), "missions": refreshed, "summary": _voice_summary(refreshed)}


def events(mission_id: int, limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM mission_events WHERE mission_id=? ORDER BY id DESC LIMIT ?",
            (int(mission_id), max(1, min(500, int(limit or 100)))),
        ).fetchall()
    return [_event_row(row) for row in rows]


def evidence(mission_id: int, limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM mission_evidence WHERE mission_id=? ORDER BY id DESC LIMIT ?",
            (int(mission_id), max(1, min(500, int(limit or 100)))),
        ).fetchall()
    return [_evidence_row(row) for row in rows]


def blockers(mission_id: int = 0, status: str = "open", limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    where: list[str] = []
    params: list[Any] = []
    if mission_id:
        where.append("mission_id=?")
        params.append(int(mission_id))
    if status:
        where.append("status=?")
        params.append(_clean(status).lower())
    params.append(max(1, min(200, int(limit or 50))))
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM mission_blockers {clause} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_blocker_row(row) for row in rows]


def approvals(mission_id: int = 0, status: str = "pending", limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    where: list[str] = []
    params: list[Any] = []
    if mission_id:
        where.append("mission_id=?")
        params.append(int(mission_id))
    if status:
        where.append("status=?")
        params.append(_clean(status).lower())
    params.append(max(1, min(200, int(limit or 50))))
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM mission_approvals {clause} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_approval_row(row) for row in rows]


def design_preview_state(mission_id: int) -> dict[str, Any]:
    return _design_preview_state(mission_id)


def add_evidence(
    mission_id: int,
    phase_name: str,
    source: str,
    title: str,
    summary: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        row_id = _insert_evidence_conn(conn, mission_id, phase_name, source, title, summary, payload or {})
    return {"id": row_id, "mission_id": int(mission_id), "phase_name": phase_name, "title": title, "summary": summary}


def add_blocker(
    mission_id: int,
    phase_name: str,
    title: str,
    summary: str,
    *,
    severity: int = 3,
    status: str = "open",
) -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO mission_blockers(mission_id, phase_name, timestamp, severity, status, title, summary, resolution)
            VALUES (?, ?, ?, ?, ?, ?, ?, '')
            """,
            (int(mission_id), _clean(phase_name), _now(), max(1, min(5, int(severity))), _clean(status).lower(), _clean(title), _clean(summary)),
        )
        row_id = int(cursor.lastrowid)
        _insert_event_conn(conn, mission_id, "agent_question", "blocker", title, summary, {"severity": severity})
    _notify(title, summary, severity=severity, metadata={"mission_id": mission_id, "phase": phase_name})
    return {"id": row_id, "mission_id": int(mission_id), "phase_name": phase_name, "title": title, "summary": summary, "status": status}


def acquire_desktop_lock(mission_id: int, owner: str = "mission_control", reason: str = "") -> dict[str, Any]:
    init_db()
    if not bool(config_value("mission_desktop_lock_enabled", True)):
        return {"locked": False, "reason": "desktop lock disabled"}
    active = desktop_lock_status()
    if active.get("locked") and int(active.get("mission_id") or 0) != int(mission_id):
        return {"locked": False, "blocked_by": active, "reason": "desktop already locked"}
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE desktop_locks SET status='released', released_at=? WHERE status='active'", (_now(),))
        cursor = conn.execute(
            "INSERT INTO desktop_locks(mission_id, owner, status, acquired_at, released_at, reason) VALUES (?, ?, 'active', ?, '', ?)",
            (int(mission_id), _clean(owner) or "mission_control", _now(), _clean(reason)),
        )
    return {"locked": True, "id": int(cursor.lastrowid), "mission_id": int(mission_id), "owner": owner, "reason": reason}


def release_desktop_lock(mission_id: int = 0, reason: str = "") -> dict[str, Any]:
    init_db()
    where = "status='active'"
    params: list[Any] = [_now(), _clean(reason)]
    if mission_id:
        where += " AND mission_id=?"
        params.append(int(mission_id))
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(f"UPDATE desktop_locks SET status='released', released_at=?, reason=? WHERE {where}", params)
    return {"released": int(cursor.rowcount or 0)}


def desktop_lock_status() -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM desktop_locks WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return {"locked": False}
    return {
        "locked": True,
        "id": int(row["id"]),
        "mission_id": int(row["mission_id"]),
        "owner": str(row["owner"]),
        "acquired_at": str(row["acquired_at"]),
        "reason": str(row["reason"]),
    }


def status() -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT status, COUNT(*) FROM mission_runs GROUP BY status").fetchall()
    counts = {str(key): int(value) for key, value in rows}
    active = list_missions(status="running", limit=10) + list_missions(status="blocked", limit=10) + list_missions(status="paused", limit=10)
    pending_approvals = approvals(status="pending", limit=20)
    open_blockers = blockers(status="open", limit=20)
    return {
        "counts": counts,
        "active": active,
        "pending_approvals": pending_approvals,
        "open_blockers": open_blockers,
        "desktop_lock": desktop_lock_status(),
        "summary": f"{len(active)} active mission(s), {len(open_blockers)} blocker(s), {len(pending_approvals)} approval(s) waiting.",
    }


def voice_status() -> str:
    state = refresh_mission()
    missions = state.get("missions") or []
    if not missions:
        return "No active missions are running."
    return _voice_summary(missions)


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        for table in (
            "mission_approvals",
            "mission_blockers",
            "mission_evidence",
            "mission_events",
            "mission_phases",
            "mission_runs",
            "desktop_locks",
        ):
            conn.execute(f"DELETE FROM {table}")


def _refresh_one(mission_id: int) -> None:
    mission = get_mission(mission_id)
    if not mission:
        return
    now = _now()
    phases = mission.get("phases") or []
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        for phase in phases:
            task_id = int(phase.get("task_id") or 0)
            task = task_queue.get_task(task_id) if task_id else None
            if not task:
                continue
            status = str(task.get("status") or "")
            next_status = _phase_status_from_task(status, str(phase.get("name") or ""))
            if next_status != phase.get("status"):
                completed_at = now if next_status in {"done", "failed", "cancelled"} else str(phase.get("completed_at") or "")
                started_at = now if next_status == "active" and not phase.get("started_at") else str(phase.get("started_at") or "")
                conn.execute(
                    "UPDATE mission_phases SET status=?, started_at=?, completed_at=? WHERE id=?",
                    (next_status, started_at, completed_at, int(phase["id"])),
                )
                _insert_event_conn(
                    conn,
                    mission_id,
                    "background_mission",
                    "phase_status",
                    f"{phase['name']} {next_status}",
                    f"Task #{task_id} is {status}.",
                    {"task_id": task_id, "phase": phase["name"], "task_status": status},
                )
            if status in {"failed", "blocked"} and not _has_open_blocker(conn, mission_id, str(phase["name"]), task_id):
                conn.execute(
                    """
                    INSERT INTO mission_blockers(mission_id, phase_name, timestamp, severity, status, title, summary, resolution)
                    VALUES (?, ?, ?, 4, 'open', ?, ?, '')
                    """,
                    (
                        mission_id,
                        str(phase["name"]),
                        now,
                        f"{phase['name']} task is {status}",
                        f"Task #{task_id} needs attention before mission completion.",
                    ),
                )
            if status == "done":
                _maybe_add_task_evidence(conn, mission_id, str(phase["name"]), task)
                if str(phase.get("name") or "") == "design" and _design_preview_gate_enabled(mission):
                    _ensure_design_preview_approval(conn, mission_id, task)
        _advance_phases(conn, mission_id)
        _enforce_final_proof(conn, mission_id)


def _advance_phases(conn: sqlite3.Connection, mission_id: int) -> None:
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM mission_phases WHERE mission_id=? ORDER BY phase_order", (mission_id,)).fetchall()
    mission_row = conn.execute("SELECT metadata_json FROM mission_runs WHERE id=?", (mission_id,)).fetchone()
    mission_meta = _json_loads(str(mission_row["metadata_json"] or "{}"), {}) if mission_row else {}
    if not isinstance(mission_meta, dict):
        mission_meta = {}
    design_gate_enabled = bool(mission_meta.get("design_preview_gate"))
    design_preview_status = _approval_status(conn, mission_id, DESIGN_PREVIEW_APPROVAL_KIND)
    current = ""
    blocked = conn.execute("SELECT COUNT(*) FROM mission_blockers WHERE mission_id=? AND status='open'", (mission_id,)).fetchone()[0]
    pending_deploy = conn.execute("SELECT COUNT(*) FROM mission_approvals WHERE mission_id=? AND kind='deploy' AND status='pending'", (mission_id,)).fetchone()[0]
    for index, row in enumerate(rows):
        status = str(row["status"])
        name = str(row["name"])
        previous_done = index == 0 or all(_phase_row_done_for_advance(prev, design_gate_enabled, design_preview_status) for prev in rows[:index])
        if name == "design_preview_approval":
            if not design_gate_enabled:
                _complete_virtual_phase(conn, row, "Design preview gate not required for this mission.")
                continue
            if previous_done and design_preview_status == "approved":
                _complete_virtual_phase(conn, row, "Design preview approved; implementation may begin.")
                continue
            if previous_done:
                conn.execute(
                    "UPDATE mission_phases SET status='active', started_at=CASE WHEN started_at='' THEN ? ELSE started_at END WHERE id=?",
                    (_now(), int(row["id"])),
                )
                current = name
                break
        if design_gate_enabled and name in DESIGN_GATED_PHASES - {"design_preview_approval"} and design_preview_status != "approved":
            if previous_done:
                current = "design_preview_approval"
                break
        if status in {"pending"}:
            if previous_done:
                if name == "deployment_runbook" and pending_deploy:
                    current = "deployment_approval"
                    break
                _release_phase_task(row)
                conn.execute(
                    "UPDATE mission_phases SET status='active', started_at=CASE WHEN started_at='' THEN ? ELSE started_at END WHERE id=?",
                    (_now(), int(row["id"])),
                )
                current = name
                break
        if status in {"active", "blocked"}:
            current = name
            break
    if not current:
        current = "final_proof"
    mission_status = "blocked" if blocked else "running"
    conn.execute(
        "UPDATE mission_runs SET current_phase=?, status=CASE WHEN status NOT IN ('paused','stopped','cancelled','failed','completed') THEN ? ELSE status END, updated_at=? WHERE id=?",
        (current, mission_status, _now(), mission_id),
    )


def _phase_row_done_for_advance(row: sqlite3.Row, design_gate_enabled: bool, design_preview_status: str) -> bool:
    name = str(row["name"])
    status = str(row["status"])
    if status == "done":
        return True
    if name == "design_preview_approval":
        return not design_gate_enabled or design_preview_status == "approved"
    return False


def _release_phase_task(row: sqlite3.Row) -> None:
    task_id = int(row["task_id"] or 0)
    if task_id > 0:
        task_queue.set_scheduled_at(task_id, None)


def _complete_virtual_phase(conn: sqlite3.Connection, row: sqlite3.Row, summary: str) -> None:
    task_id = int(row["task_id"] or 0)
    now = _now()
    conn.execute(
        "UPDATE mission_phases SET status='done', completed_at=CASE WHEN completed_at='' THEN ? ELSE completed_at END WHERE id=?",
        (now, int(row["id"])),
    )
    if task_id > 0:
        task = task_queue.get_task(task_id)
        if task and str(task.get("status")) not in task_queue.FINAL_STATUSES:
            task_queue.complete_task(
                task_id,
                {
                    "summary": f"Summary: {summary} Next step: continue the mission phase sequence. Risks: implementation must follow the approved design preview.",
                    "virtual_phase": str(row["name"]),
                },
            )


def _approval_status(conn: sqlite3.Connection, mission_id: int, kind: str) -> str:
    row = conn.execute(
        "SELECT status FROM mission_approvals WHERE mission_id=? AND kind=? ORDER BY id DESC LIMIT 1",
        (int(mission_id), _clean(kind).lower().replace(" ", "_")),
    ).fetchone()
    return str(row["status"]) if row else ""


def _enforce_final_proof(conn: sqlite3.Connection, mission_id: int) -> None:
    conn.row_factory = sqlite3.Row
    phases = conn.execute("SELECT name, status FROM mission_phases WHERE mission_id=? ORDER BY phase_order", (mission_id,)).fetchall()
    if not phases or not all(str(row["status"]) == "done" for row in phases):
        return
    qa_count = conn.execute(
        "SELECT COUNT(*) FROM mission_evidence WHERE mission_id=? AND source='qa_lab'",
        (mission_id,),
    ).fetchone()[0]
    if not qa_count:
        if not _has_open_blocker(conn, mission_id, "final_proof", 0):
            conn.execute(
                """
                INSERT INTO mission_blockers(mission_id, phase_name, timestamp, severity, status, title, summary, resolution)
                VALUES (?, 'final_proof', ?, 5, 'open', 'QA evidence missing', 'Friday cannot mark the mission complete until QA evidence exists or verification limits are explicitly documented.', '')
                """,
                (mission_id, _now()),
            )
        conn.execute("UPDATE mission_runs SET status='blocked', current_phase='final_proof', updated_at=? WHERE id=?", (_now(), mission_id))
        return
    conn.execute(
        "UPDATE mission_runs SET status='completed', current_phase='final_proof', summary='Mission complete with QA evidence and final proof.', updated_at=? WHERE id=?",
        (_now(), mission_id),
    )
    _insert_event_conn(
        conn,
        mission_id,
        "background_mission",
        "completed",
        "Mission completed",
        "All phases are done and QA/final proof evidence exists.",
        {},
    )


def _create_phase_task(
    mission_id: int,
    phase: dict[str, str],
    goal: str,
    root: Path,
    mission_type: str,
    priority: int,
    *,
    hold_until_released: bool = False,
) -> int:
    criteria = _phase_criteria(phase["name"], mission_type)
    task_id = task_queue.create_task(
        f"Mission #{mission_id} {phase['name']}: {phase['title']}",
        description=(
            f"Mission goal: {goal}\n"
            f"Root: {root}\n"
            f"Success criteria:\n- " + "\n- ".join(criteria) + "\n"
            "Post progress messages as 'Progress NN%: ...' and include evidence/limits in the final output."
        ),
        agent_id=phase["agent"],
        priority=priority,
        input_data={
            "source": "mission_control",
            "mission_id": mission_id,
            "phase": phase["name"],
            "goal": goal,
            "root": str(root),
            "mission_type": mission_type,
            "success_criteria": criteria,
            "held_until_design_preview_approval": hold_until_released,
        },
        scheduled_at=HELD_PHASE_SCHEDULED_AT if hold_until_released else None,
    )
    task = task_queue.get_task(task_id)
    if task:
        task_contracts.ensure_contract(task)
    return task_id


def _phase_criteria(name: str, mission_type: str) -> list[str]:
    base = {
        "intake": ["Goal and constraints are restated.", "Risky boundaries and approvals are identified."],
        "research": ["Relevant local/project/context research is summarized.", "Sources or evidence limits are stated."],
        "architecture": ["Implementation architecture is explained.", "Security, performance, maintainability, and rollback concerns are included."],
        "design": [
            "User workflow and UI/UX expectations are stated.",
            "A visible design preview is produced before implementation begins.",
            "The preview covers screens, layout, components, states, copy, accessibility, and developer handoff notes.",
            "If no image/prototype is available, a concise textual wireframe is included.",
        ],
        "design_preview_approval": ["The UI sample/design preview is shown to the user.", "Implementation remains paused until the preview is approved."],
        "implementation": ["Planned code/work changes are prepared or completed safely.", "Risky edits are gated by approval and backups."],
        "autonomous_qa": ["QA checks are listed and run where possible.", "Failures and unverified areas are documented."],
        "documentation": ["Setup, usage, architecture, and known limitations are documented."],
        "release_prep": ["Changelog, checklist, risks, and rollback plan exist."],
        "deployment_approval": ["Deployment waits for explicit user approval."],
        "deployment_runbook": ["Deployment runbook is prepared or executed only after approval."],
        "final_proof": ["Final report lists evidence, tests, blockers, and limits before saying done."],
    }
    criteria = list(base.get(name, ["Work is summarized with evidence."]))
    if mission_type == "project_builder":
        criteria.append("Programming priorities: security, performance, maintainability, reliability, readability, scalability, and tests.")
    return criteria


def _set_status(mission_id: int, status: str, summary: str, *, channel: str, event_type: str) -> dict[str, Any]:
    init_db()
    normalized = _clean(status).lower()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            "UPDATE mission_runs SET status=?, summary=?, updated_at=? WHERE id=?",
            (normalized, _clean(summary), _now(), int(mission_id)),
        )
        _insert_event_conn(conn, int(mission_id), channel, event_type, summary, summary, {})
    return get_mission(mission_id) or {"id": int(mission_id), "status": normalized, "summary": summary}


def _safe_snapshot_config(mission_id: int) -> None:
    try:
        backup_recovery.snapshot_config(f"mission-{mission_id}-preflight")
    except Exception:
        pass


def _maybe_add_task_evidence(conn: sqlite3.Connection, mission_id: int, phase_name: str, task: dict[str, Any]) -> None:
    task_id = int(task.get("id") or 0)
    exists = conn.execute(
        "SELECT COUNT(*) FROM mission_evidence WHERE mission_id=? AND source='task_queue' AND json_extract(payload_json, '$.task_id')=?",
        (mission_id, task_id),
    ).fetchone()[0]
    if exists:
        return
    output = task.get("output") or {}
    summary = _clean(output.get("summary") if isinstance(output, dict) else output) or f"Task #{task_id} completed."
    _insert_evidence_conn(
        conn,
        mission_id,
        phase_name,
        "task_queue",
        f"Task #{task_id} complete",
        summary[:1000],
        {"task_id": task_id, "output": output},
    )


def _ensure_design_preview_approval(conn: sqlite3.Connection, mission_id: int, design_task: dict[str, Any]) -> None:
    existing = conn.execute(
        "SELECT COUNT(*) FROM mission_approvals WHERE mission_id=? AND kind=?",
        (int(mission_id), DESIGN_PREVIEW_APPROVAL_KIND),
    ).fetchone()[0]
    if existing:
        return
    output = design_task.get("output") or {}
    preview = _clean(output.get("summary") if isinstance(output, dict) else output)
    if not preview:
        preview = "The UI/UX Designer completed the design phase, but the preview summary was empty."
    _insert_approval_conn(
        conn,
        mission_id,
        DESIGN_PREVIEW_APPROVAL_KIND,
        "pending",
        "Review UI design preview",
        "Implementation is paused until you approve the UI sample/design preview.",
        {
            "approval_phrase": f"approve design preview {mission_id}",
            "design_task_id": int(design_task.get("id") or 0),
            "preview": preview[:1800],
        },
    )
    _insert_event_conn(
        conn,
        mission_id,
        "background_mission",
        "design_preview_waiting",
        "UI design preview waiting",
        "Friday paused implementation until the design preview is approved.",
        {"design_task_id": int(design_task.get("id") or 0)},
    )


def _has_open_blocker(conn: sqlite3.Connection, mission_id: int, phase_name: str, task_id: int = 0) -> bool:
    query = "SELECT COUNT(*) FROM mission_blockers WHERE mission_id=? AND phase_name=? AND status='open'"
    return bool(conn.execute(query, (mission_id, phase_name)).fetchone()[0])


def _phase_status_from_task(task_status: str, phase_name: str) -> str:
    if task_status == "done":
        return "done"
    if task_status in {"failed", "cancelled"}:
        return task_status
    if task_status == "blocked":
        return "blocked"
    if phase_name == "deployment_approval":
        return "done"
    return "active" if task_status == "active" else "pending"


def _hydrate_run(row: sqlite3.Row, *, include_children: bool) -> dict[str, Any]:
    item = {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "goal": str(row["goal"]),
        "mission_type": str(row["mission_type"]),
        "root": str(row["root"]),
        "status": str(row["status"]),
        "current_phase": str(row["current_phase"]),
        "authority_mode": str(row["authority_mode"]),
        "deploy_policy": str(row["deploy_policy"]),
        "summary": str(row["summary"]),
        "task_ids": _json_loads(row["task_ids_json"], {}),
        "metadata": _json_loads(row["metadata_json"], {}),
        "design_preview": _design_preview_state(int(row["id"])),
    }
    if include_children:
        item["phases"] = _list_phases(item["id"])
        item["events"] = events(item["id"], limit=40)
        item["evidence"] = evidence(item["id"], limit=40)
        item["blockers"] = blockers(item["id"], status="", limit=40)
        item["approvals"] = approvals(item["id"], status="", limit=40)
        item["desktop_lock"] = desktop_lock_status()
    else:
        item["progress_percent"] = _mission_progress(item["id"])
    return item


def _list_phases(mission_id: int) -> list[dict[str, Any]]:
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM mission_phases WHERE mission_id=? ORDER BY phase_order", (int(mission_id),)).fetchall()
    return [
        {
            "id": int(row["id"]),
            "mission_id": int(row["mission_id"]),
            "phase_order": int(row["phase_order"]),
            "name": str(row["name"]),
            "status": str(row["status"]),
            "assigned_agent": str(row["assigned_agent"]),
            "task_id": int(row["task_id"] or 0),
            "summary": str(row["summary"]),
            "evidence_count": int(row["evidence_count"]),
            "blocker_count": int(row["blocker_count"]),
            "started_at": str(row["started_at"] or ""),
            "completed_at": str(row["completed_at"] or ""),
            "progress_percent": task_queue.task_progress(int(row["task_id"] or 0), str(row["status"])) if row["task_id"] else 0,
        }
        for row in rows
    ]


def _mission_progress(mission_id: int) -> int:
    phases = _list_phases(mission_id)
    if not phases:
        return 0
    done = sum(1 for phase in phases if phase["status"] == "done")
    active_progress = sum(int(phase.get("progress_percent") or 0) for phase in phases if phase["status"] == "active")
    return min(99, int((done / len(phases)) * 100 + active_progress / max(1, len(phases))))


def _event_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "mission_id": int(row["mission_id"]),
        "timestamp": str(row["timestamp"]),
        "channel": str(row["channel"]),
        "event_type": str(row["event_type"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "payload": _json_loads(row["payload_json"], {}),
    }


def _evidence_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "mission_id": int(row["mission_id"]),
        "phase_name": str(row["phase_name"]),
        "timestamp": str(row["timestamp"]),
        "source": str(row["source"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "payload": _json_loads(row["payload_json"], {}),
    }


def _blocker_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "mission_id": int(row["mission_id"]),
        "phase_name": str(row["phase_name"]),
        "timestamp": str(row["timestamp"]),
        "severity": int(row["severity"]),
        "status": str(row["status"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "resolution": str(row["resolution"]),
    }


def _approval_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "mission_id": int(row["mission_id"]),
        "timestamp": str(row["timestamp"]),
        "kind": str(row["kind"]),
        "status": str(row["status"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "payload": _json_loads(row["payload_json"], {}),
    }


def _design_preview_state(mission_id: int) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        approval = conn.execute(
            "SELECT * FROM mission_approvals WHERE mission_id=? AND kind=? ORDER BY id DESC LIMIT 1",
            (int(mission_id), DESIGN_PREVIEW_APPROVAL_KIND),
        ).fetchone()
        evidence = conn.execute(
            "SELECT * FROM mission_evidence WHERE mission_id=? AND phase_name='design' ORDER BY id DESC LIMIT 1",
            (int(mission_id),),
        ).fetchone()
        mission = conn.execute("SELECT metadata_json FROM mission_runs WHERE id=?", (int(mission_id),)).fetchone()
    approval_item = _approval_row(approval) if approval else None
    evidence_item = _evidence_row(evidence) if evidence else None
    metadata = _json_loads(str(mission["metadata_json"] or "{}"), {}) if mission else {}
    preview = ""
    if approval_item:
        payload = approval_item.get("payload") or {}
        if isinstance(payload, dict):
            preview = _clean(payload.get("preview") or "")
    if not preview and evidence_item:
        preview = _clean(evidence_item.get("summary") or "")
    required = bool(metadata.get("design_preview_gate")) if isinstance(metadata, dict) else False
    status = str(approval_item.get("status") if approval_item else "").lower()
    return {
        "required": required,
        "status": status or ("waiting_for_design" if required else "not_required"),
        "pending": status == "pending",
        "approved": status == "approved",
        "approval": approval_item,
        "evidence": evidence_item,
        "preview": preview,
    }


def _insert_event_conn(conn: sqlite3.Connection, mission_id: int, channel: str, event_type: str, title: str, summary: str, payload: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO mission_events(mission_id, timestamp, channel, event_type, title, summary, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(mission_id),
            _now(),
            channel if channel in MISSION_CHANNELS else "background_mission",
            _clean(event_type),
            _clean(title)[:300],
            _clean(summary)[:4000],
            _json_dumps(payload),
        ),
    )
    return int(cursor.lastrowid)


def _insert_evidence_conn(conn: sqlite3.Connection, mission_id: int, phase_name: str, source: str, title: str, summary: str, payload: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO mission_evidence(mission_id, phase_name, timestamp, source, title, summary, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (int(mission_id), _clean(phase_name), _now(), _clean(source), _clean(title)[:300], _clean(summary)[:4000], _json_dumps(payload)),
    )
    conn.execute(
        "UPDATE mission_phases SET evidence_count=evidence_count+1 WHERE mission_id=? AND name=?",
        (int(mission_id), _clean(phase_name)),
    )
    return int(cursor.lastrowid)


def _insert_approval_conn(conn: sqlite3.Connection, mission_id: int, kind: str, status: str, title: str, summary: str, payload: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO mission_approvals(mission_id, timestamp, kind, status, title, summary, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (int(mission_id), _now(), _clean(kind).lower().replace(" ", "_"), _clean(status).lower(), _clean(title)[:300], _clean(summary)[:3000], _json_dumps(payload)),
    )
    return int(cursor.lastrowid)


def _notify(title: str, message: str, *, severity: int, metadata: dict[str, Any]) -> None:
    try:
        notification_center.add(
            source="mission_control",
            category="mission",
            title=title,
            message=message,
            severity=severity,
            dedupe_key=f"mission:{metadata.get('mission_id')}:{title}",
            metadata=metadata,
        )
    except Exception:
        pass


def _voice_summary(missions: list[dict[str, Any]]) -> str:
    if not missions:
        return "No active missions are running."
    mission = missions[0]
    return f"Mission #{mission['id']} is {mission['status']} in {str(mission.get('current_phase') or '').replace('_', ' ')}."


def _safe_root(value: str | Path) -> Path:
    text = _clean(str(value or ""))
    if not text:
        return ROOT_DIR
    try:
        return Path(text).expanduser().resolve()
    except Exception:
        return ROOT_DIR


def _normalize_type(value: str) -> str:
    text = _clean(value).lower().replace(" ", "_")
    return text if text else "general"


def _requires_design_preview_gate(goal: str, mission_type: str, metadata: dict[str, Any]) -> bool:
    if "design_preview_gate" in metadata:
        return bool(metadata.get("design_preview_gate"))
    lowered = f"{goal} {mission_type}".lower()
    return mission_type == "project_builder" or any(
        word in lowered
        for word in ("ui", "ux", "interface", "frontend", "screen", "website", "dashboard", "app", "prototype", "wireframe")
    )


def _design_preview_gate_enabled(mission: dict[str, Any]) -> bool:
    metadata = mission.get("metadata") if isinstance(mission, dict) else {}
    return bool(metadata.get("design_preview_gate")) if isinstance(metadata, dict) else False


def _infer_type(goal: str) -> str:
    lowered = goal.lower()
    if any(word in lowered for word in ("build", "app", "saas", "website", "dashboard", "api", "code", "mvp")):
        return "project_builder"
    if any(word in lowered for word in ("deploy", "release", "production")):
        return "deployment"
    if any(word in lowered for word in ("study", "learn", "quiz", "course")):
        return "learning"
    return "general"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=True)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return default

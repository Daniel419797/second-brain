"""Durable company-style worker runtime for Friday specialist agents."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import audit_log, notification_center
from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "company_runtime.sqlite3"
_LOCK = threading.Lock()

ALLOWED_STATES = {"idle", "planning", "working", "waiting_approval", "blocked", "verifying", "done", "failed"}

DEFAULT_RUNBOOKS: tuple[dict[str, Any], ...] = (
    {
        "agent_id": "ceo",
        "role": "CEO / strategist",
        "mission": "Set strategy, prioritize work, protect cash, and escalate hard tradeoffs.",
        "steps": ["Clarify outcome", "Set success metrics", "Assign owner", "Review evidence before success claim"],
    },
    {
        "agent_id": "sales_agent",
        "role": "Sales agent",
        "mission": "Find qualified prospects and move them through approved outreach.",
        "steps": ["Research prospect", "Score fit", "Draft outreach", "Wait for approval before sending"],
    },
    {
        "agent_id": "lead_researcher",
        "role": "Lead researcher",
        "mission": "Collect verifiable market, prospect, and project evidence.",
        "steps": ["Gather sources", "Cross-check claims", "Attach citations or proof", "Flag unknowns"],
    },
    {
        "agent_id": "proposal_writer",
        "role": "Proposal writer",
        "mission": "Turn client needs into proposals, contracts, and project plans.",
        "steps": ["Summarize need", "Define scope", "Draft deliverables", "Send for approval"],
    },
    {
        "agent_id": "project_manager",
        "role": "Project manager",
        "mission": "Keep client work moving with blockers, handoffs, timelines, and proof.",
        "steps": ["Break down work", "Track blockers", "Coordinate handoffs", "Update status portal"],
    },
    {
        "agent_id": "ui_ux_designer",
        "role": "Designer",
        "mission": "Create usable, accessible, domain-fit product experiences.",
        "steps": ["Inspect audience", "Design workflow", "Check responsive layout", "Capture visual proof"],
    },
    {
        "agent_id": "senior_developer",
        "role": "Senior developer",
        "mission": "Implement maintainable code with tests, security checks, and rollback notes.",
        "steps": ["Read existing patterns", "Make scoped change", "Run tests", "Record proof"],
    },
    {
        "agent_id": "frontend_developer",
        "role": "Frontend developer",
        "mission": "Build polished web UI with responsive behavior and live state.",
        "steps": ["Follow design system", "Use realtime APIs", "Verify mobile and desktop", "Capture screenshot proof"],
    },
    {
        "agent_id": "qa_engineer",
        "role": "QA engineer",
        "mission": "Reproduce bugs, discover tests, and verify fixes without false success.",
        "steps": ["Reproduce issue", "Run focused tests", "Run smoke suite", "Escalate failures"],
    },
    {
        "agent_id": "devops",
        "role": "DevOps agent",
        "mission": "Prepare CI, deploy previews, environment checks, and rollback plans.",
        "steps": ["Check secrets", "Generate CI", "Verify deploy target", "Require approval before production deploy"],
    },
    {
        "agent_id": "finance_admin",
        "role": "Finance/admin agent",
        "mission": "Track invoices, revenue, expenses, API costs, and payment approvals.",
        "steps": ["Update ledger", "Check budget", "Draft invoice", "Require approval for payments"],
    },
    {
        "agent_id": "customer_support",
        "role": "Customer support agent",
        "mission": "Triage client messages, draft responses, and escalate sensitive replies.",
        "steps": ["Classify message", "Draft reply", "Attach context", "Wait for approval before sending"],
    },
)


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
            CREATE TABLE IF NOT EXISTS company_runbooks (
                agent_id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                mission TEXT NOT NULL,
                steps_json TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS company_worker_states (
                agent_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                task_id INTEGER NOT NULL,
                blocker TEXT NOT NULL,
                progress REAL NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS company_handoffs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                from_agent TEXT NOT NULL,
                to_agent TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                task_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                evidence_json TEXT NOT NULL
            )
            """
        )
        _seed_defaults(conn)


def status(limit: int = 12) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        worker_rows = conn.execute("SELECT * FROM company_worker_states ORDER BY updated_at DESC LIMIT ?", (_limit(limit, 50),)).fetchall()
        handoff_rows = conn.execute("SELECT * FROM company_handoffs ORDER BY id DESC LIMIT ?", (_limit(limit, 50),)).fetchall()
        runbook_count = int(conn.execute("SELECT COUNT(*) FROM company_runbooks WHERE enabled=1").fetchone()[0] or 0)
    workers = [_state_row(row) for row in worker_rows]
    blockers = [item for item in workers if item["state"] in {"blocked", "waiting_approval", "failed"}]
    return {
        "enabled": bool(config_value("company_runtime_enabled", True)),
        "runbook_count": runbook_count,
        "workers": workers,
        "handoffs": [_handoff_row(row) for row in handoff_rows],
        "blockers": blockers,
        "allowed_states": sorted(ALLOWED_STATES),
        "summary": f"Company runtime has {runbook_count} runbook(s), {len(workers)} tracked worker(s), and {len(blockers)} blocker(s).",
    }


def runbooks() -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM company_runbooks ORDER BY role").fetchall()
    return [_runbook_row(row) for row in rows]


def set_worker_state(
    agent_id: str,
    state: str,
    *,
    task_id: int = 0,
    blocker: str = "",
    progress: float = 0.0,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    safe_agent = _key(agent_id)
    if not safe_agent:
        raise ValueError("agent_id is required")
    safe_state = _key(state)
    if safe_state not in ALLOWED_STATES:
        raise ValueError(f"state must be one of {', '.join(sorted(ALLOWED_STATES))}")
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO company_worker_states(agent_id, state, task_id, blocker, progress, updated_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET
                state=excluded.state,
                task_id=excluded.task_id,
                blocker=excluded.blocker,
                progress=excluded.progress,
                updated_at=excluded.updated_at,
                metadata_json=excluded.metadata_json
            """,
            (
                safe_agent,
                safe_state,
                max(0, int(task_id or 0)),
                _clean(blocker)[:2000],
                _progress(progress),
                now,
                _json_dumps(metadata or {}),
            ),
        )
        row = conn.execute("SELECT * FROM company_worker_states WHERE agent_id=?", (safe_agent,)).fetchone()
    item = _state_row(row)
    if safe_state in {"blocked", "waiting_approval", "failed"}:
        notification_center.add(
            source="company_runtime",
            category="agent",
            severity=3 if safe_state != "failed" else 4,
            title=f"{safe_agent} is {safe_state.replace('_', ' ')}",
            message=item["summary"],
            dedupe_key=f"company:{safe_agent}:{safe_state}:{task_id or 0}",
            metadata={"worker": item},
        )
    audit_log.record(category="company_runtime", action="set_worker_state", target=safe_agent, success=True, details=item)
    return item


def handoff(
    from_agent: str,
    to_agent: str,
    title: str,
    summary: str,
    *,
    task_id: int = 0,
    evidence: list[str] | str | None = None,
) -> dict[str, Any]:
    init_db()
    source = _key(from_agent)
    target = _key(to_agent)
    if not source or not target:
        raise ValueError("from_agent and to_agent are required")
    now = _now()
    proof = _list(evidence)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO company_handoffs(timestamp, from_agent, to_agent, title, summary, task_id, status, evidence_json)
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?)
            """,
            (now, source, target, _clean(title)[:300] or "Agent handoff", _clean(summary)[:4000], max(0, int(task_id or 0)), _json_dumps(proof)),
        )
        row = conn.execute("SELECT * FROM company_handoffs WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    set_worker_state(target, "planning", task_id=task_id, metadata={"handoff_id": int(row["id"])})
    item = _handoff_row(row)
    notification_center.add(
        source="company_runtime",
        category="agent",
        severity=2,
        title=f"Handoff to {target}",
        message=item["summary"],
        metadata={"handoff": item},
    )
    audit_log.record(category="company_runtime", action="handoff", target=f"{source}->{target}", success=True, details=item)
    return item


def timeline(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM company_handoffs ORDER BY id DESC LIMIT ?", (_limit(limit, 200),)).fetchall()
    return [_handoff_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM company_handoffs")
        conn.execute("DELETE FROM company_worker_states")
        conn.execute("DELETE FROM company_runbooks")
        _seed_defaults(conn)


def _seed_defaults(conn: sqlite3.Connection) -> None:
    now = _now()
    for item in DEFAULT_RUNBOOKS:
        conn.execute(
            """
            INSERT OR IGNORE INTO company_runbooks(agent_id, role, mission, steps_json, enabled, updated_at)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (item["agent_id"], item["role"], item["mission"], _json_dumps(item["steps"]), now),
        )


def _runbook_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "agent_id": str(row["agent_id"]),
        "role": str(row["role"]),
        "mission": str(row["mission"]),
        "steps": _json_loads(row["steps_json"], []),
        "enabled": bool(row["enabled"]),
        "updated_at": str(row["updated_at"]),
    }


def _state_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "agent_id": str(row["agent_id"]),
        "state": str(row["state"]),
        "task_id": int(row["task_id"] or 0),
        "blocker": str(row["blocker"]),
        "progress": float(row["progress"] or 0.0),
        "updated_at": str(row["updated_at"]),
        "metadata": _json_loads(row["metadata_json"], {}),
        "summary": f"{row['agent_id']} is {row['state']} at {round(float(row['progress'] or 0.0) * 100)}%.",
    }


def _handoff_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "from_agent": str(row["from_agent"]),
        "to_agent": str(row["to_agent"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "task_id": int(row["task_id"] or 0),
        "status": str(row["status"]),
        "evidence": _json_loads(row["evidence_json"], []),
    }


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())


def _list(value: list[str] | str | None) -> list[str]:
    raw = value if isinstance(value, list) else [value] if value else []
    return [_clean(item)[:1000] for item in raw if _clean(item)][:20]


def _progress(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0


def _limit(value: int, maximum: int) -> int:
    return max(1, min(maximum, int(value or 50)))


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

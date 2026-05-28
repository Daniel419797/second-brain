"""Autonomous skill improvement proposals from repeated failures."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import app_state_memory, self_debugger, skill_evolution, task_queue, voice_command_repair
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "skill_improvement.sqlite3"
_LOCK = threading.Lock()


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
            CREATE TABLE IF NOT EXISTS skill_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                skill TEXT NOT NULL,
                failure TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                context_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS improvement_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                skill TEXT NOT NULL,
                title TEXT NOT NULL,
                proposal TEXT NOT NULL,
                status TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_failures_skill ON skill_failures(skill, timestamp)")


def record_failure(skill: str, failure: str, *, evidence: list[str] | str | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    clean_skill = _clean(skill).lower().replace(" ", "_") or "unknown_skill"
    clean_failure = _clean(failure) or "Unspecified failure"
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO skill_failures(timestamp, skill, failure, evidence_json, context_json) VALUES (?, ?, ?, ?, ?)",
            (_now(), clean_skill, clean_failure[:2000], _json_dumps(_list(evidence)), _json_dumps(context or {})),
        )
        row = conn.execute("SELECT * FROM skill_failures WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    failure_item = _failure_row(row)
    proposal = _maybe_propose(clean_skill)
    _apply_obvious_learning(clean_skill, clean_failure, evidence, context or {})
    return {"failure": failure_item, "proposal": proposal, "summary": proposal.get("summary") if proposal else f"Recorded failure for {clean_skill}."}


def analyze_recent(limit: int = 50) -> dict[str, Any]:
    failures = recent_failures(limit=limit)
    proposals = []
    for skill in sorted({item["skill"] for item in failures}):
        proposal = _maybe_propose(skill)
        if proposal:
            proposals.append(proposal)
    return {"failures": failures, "proposals": proposals, "summary": f"{len(proposals)} skill improvement proposal(s) ready."}


def proposals(limit: int = 20, *, status: str = "open") -> list[dict[str, Any]]:
    init_db()
    where = "WHERE status=?" if status else ""
    params: list[Any] = [status] if status else []
    params.append(max(1, min(100, int(limit or 20))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM improvement_proposals {where} ORDER BY confidence DESC, updated_at DESC LIMIT ?", params).fetchall()
    return [_proposal_row(row) for row in rows]


def recent_failures(limit: int = 30, *, skill: str = "") -> list[dict[str, Any]]:
    init_db()
    params: list[Any] = []
    clause = ""
    if skill:
        clause = "WHERE skill=?"
        params.append(_clean(skill).lower().replace(" ", "_"))
    params.append(max(1, min(200, int(limit or 30))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM skill_failures {clause} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_failure_row(row) for row in rows]


def status() -> dict[str, Any]:
    open_items = proposals(limit=12)
    failures = recent_failures(limit=12)
    return {"open_proposals": open_items, "recent_failures": failures, "summary": f"{len(open_items)} open skill improvement proposal(s)."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM skill_failures")
        conn.execute("DELETE FROM improvement_proposals")


def _maybe_propose(skill: str) -> dict[str, Any] | None:
    failures = recent_failures(limit=20, skill=skill)
    if len(failures) < 2:
        return None
    summary = _proposal_text(skill, failures)
    title = f"Improve {skill.replace('_', ' ')}"
    confidence = min(0.95, 0.55 + len(failures) * 0.08)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO improvement_proposals(created_at, updated_at, skill, title, proposal, status, confidence, evidence_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?)
            """,
            (_now(), _now(), skill, title, summary, confidence, _json_dumps([item["failure"] for item in failures[:5]]), _json_dumps({"failure_count": len(failures)})),
        )
        row = conn.execute("SELECT * FROM improvement_proposals WHERE id=last_insert_rowid()").fetchone()
    proposal = _proposal_row(row)
    task_id = _safe(lambda: task_queue.create_task(title, agent_id="senior_developer", priority=4, input_data={"source": "skill_improvement", "proposal": proposal}), 0)
    proposal["task_id"] = task_id
    proposal["summary"] = f"{title}: {summary}"
    _safe(lambda: self_debugger.record_failure("skill_improvement", summary), None)
    return proposal


def _apply_obvious_learning(skill: str, failure: str, evidence: list[str] | str | None, context: dict[str, Any]) -> None:
    lower = f"{skill} {failure}".lower()
    if "freddie" in lower or "friady" in lower or "fryday" in lower:
        _safe(lambda: voice_command_repair.record_repair("Friday", failure, source="skill_improvement"), None)
    if "operator" in lower or "selector" in lower or "button" in lower:
        _safe(lambda: app_state_memory.remember_failure(context.get("app", skill), context.get("selector", ""), failure), None)
    _safe(lambda: skill_evolution.observe_workflow(skill, failure, metadata={"source": "skill_improvement", "evidence": _list(evidence)}), None)


def _proposal_text(skill: str, failures: list[dict[str, Any]]) -> str:
    lower = skill.lower()
    if "volume" in lower or "audio" in lower:
        return "Add stronger before/after device verification and refuse success wording unless the actual volume reading changes."
    if "stt" in lower or "voice" in lower:
        return "Add transcript correction examples, wake-name aliases, and confidence checks for repeated mishearing patterns."
    if "render" in lower or "deploy" in lower:
        return "Create or refine a deploy operator skill with selectors, approval gates, log checks, and rollback notes."
    if "operator" in lower or "figma" in lower:
        return "Record the failed UI selector, learn a stronger DOM/accessibility anchor, and add a recovery step."
    return f"Review {len(failures)} repeated failure(s), add evidence checks, and create a focused regression test."


def _failure_row(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": int(row["id"]), "timestamp": str(row["timestamp"]), "skill": str(row["skill"]), "failure": str(row["failure"]), "evidence": _json_loads(row["evidence_json"], []), "context": _json_loads(row["context_json"], {})}


def _proposal_row(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": int(row["id"]), "created_at": str(row["created_at"]), "updated_at": str(row["updated_at"]), "skill": str(row["skill"]), "title": str(row["title"]), "proposal": str(row["proposal"]), "status": str(row["status"]), "confidence": float(row["confidence"]), "evidence": _json_loads(row["evidence_json"], []), "metadata": _json_loads(row["metadata_json"], {}), "summary": str(row["proposal"])}


def _list(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    return [_clean(item) for item in value if _clean(item)]


def _safe(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

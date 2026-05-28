"""Dry-run agent plans and failure cases before a mission touches files/apps."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import agents
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "agent_simulation_sandbox.sqlite3"
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
            CREATE TABLE IF NOT EXISTS agent_simulations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                goal TEXT NOT NULL,
                agent_ids_json TEXT NOT NULL,
                phases_json TEXT NOT NULL,
                failure_cases_json TEXT NOT NULL,
                rollback_plan TEXT NOT NULL,
                confidence REAL NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def simulate(goal: str, *, agent_ids: list[str] | None = None, root: str = "", risk_level: str = "medium") -> dict[str, Any]:
    init_db()
    selected = _select_agents(goal, agent_ids)
    phases = _phases(goal, selected, risk_level)
    failures = _failure_cases(goal, risk_level)
    rollback = "Keep a checkpoint before each phase; stop before destructive, private, paid, or external deployment actions."
    confidence = 0.74 if selected else 0.44
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO agent_simulations(timestamp, goal, agent_ids_json, phases_json, failure_cases_json, rollback_plan, confidence, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (_now(), _clean(goal)[:3000], _json_dumps(selected), _json_dumps(phases), _json_dumps(failures), rollback, confidence, _json_dumps({"root": root, "risk_level": risk_level})),
        )
        row = conn.execute("SELECT * FROM agent_simulations WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    item = _row(row)
    item["summary"] = f"Simulated {len(phases)} phase(s) with {len(failures)} failure case(s)."
    return item


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM agent_simulations ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    items = recent(limit=6)
    return {"recent": items, "summary": f"{len(items)} agent simulation(s) recorded."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM agent_simulations")


def _select_agents(goal: str, explicit: list[str] | None) -> list[str]:
    if explicit:
        return [agents.normalize_agent_id(item) for item in explicit if item][:8]
    base = ["ceo", agents.choose_agent(goal), "qa_engineer"]
    lowered = goal.lower()
    if "design" in lowered or "figma" in lowered:
        base.append("ui_ux_designer")
    if "security" in lowered or "deploy" in lowered:
        base.append("cybersecurity_analyst")
    if "research" in lowered or "learn" in lowered:
        base.append("research_analyst")
    return list(dict.fromkeys(base))


def _phases(goal: str, selected: list[str], risk_level: str) -> list[dict[str, Any]]:
    names = ["intake", "research", "plan", "simulate", "execute", "verify", "report"]
    phases = []
    for index, name in enumerate(names, start=1):
        phases.append({"order": index, "phase": name, "lead_agent": selected[min(index - 1, len(selected) - 1)] if selected else "ceo", "success_check": f"{name} has evidence before moving on", "risk_level": risk_level})
    return phases


def _failure_cases(goal: str, risk_level: str) -> list[str]:
    cases = ["Missing evidence causes Friday to pause instead of claiming done.", "Tool/API failure creates a failure autopsy and retry plan."]
    lowered = goal.lower()
    if any(term in lowered for term in ("code", "build", "app", "project")):
        cases.append("Tests fail or no test runner exists; final report must say what was and was not verified.")
    if any(term in lowered for term in ("deploy", "send", "delete", "message", "email")) or risk_level == "high":
        cases.append("Approval gate blocks risky external action until the user explicitly approves.")
    return cases


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "goal": str(row["goal"]),
        "agent_ids": _json_loads(row["agent_ids_json"], []),
        "phases": _json_loads(row["phases_json"], []),
        "failure_cases": _json_loads(row["failure_cases_json"], []),
        "rollback_plan": str(row["rollback_plan"]),
        "confidence": float(row["confidence"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

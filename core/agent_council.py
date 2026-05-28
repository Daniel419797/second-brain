"""Private multi-agent council for hard decisions."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import agent_thought_bus, agents, certainty_brain
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "agent_council.sqlite3"
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
            CREATE TABLE IF NOT EXISTS council_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                question TEXT NOT NULL,
                agent_ids_json TEXT NOT NULL,
                opinions_json TEXT NOT NULL,
                disagreements_json TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                confidence REAL NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def convene(question: str, *, agent_ids: list[str] | None = None, context: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    clean_question = _clean(question)
    selected = _select_agents(clean_question, agent_ids)
    opinions = [_opinion(agent_id, clean_question, context) for agent_id in selected]
    disagreements = _disagreements(opinions)
    recommendation, confidence = _recommend(opinions, disagreements)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO council_sessions(timestamp, question, agent_ids_json, opinions_json, disagreements_json, recommendation, confidence, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (_now(), clean_question[:2000], _json_dumps(selected), _json_dumps(opinions), _json_dumps(disagreements), recommendation, confidence, _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM council_sessions WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    item = _row(row)
    _safe(lambda: certainty_brain.record("known" if confidence >= 0.72 else "guess", "agent_council", recommendation, confidence=confidence, evidence=[op["summary"] for op in opinions], source="agent_council"), None)
    _safe(lambda: agent_thought_bus.post_thought("ceo", "decision", f"Council recommendation: {recommendation}", item, confidence=confidence, visibility="debug"), None)
    return item


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM council_sessions ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    items = recent(limit=8)
    latest = items[0] if items else None
    return {"recent": items, "latest": latest, "summary": latest["recommendation"] if latest else "Agent council is ready."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM council_sessions")


def _select_agents(question: str, agent_ids: list[str] | None) -> list[str]:
    if agent_ids:
        return [agents.normalize_agent_id(item) for item in agent_ids if item][:6]
    lowered = question.lower()
    selected = ["ceo", "senior_developer", "qa_engineer"]
    if any(word in lowered for word in ("design", "ui", "figma")):
        selected.append("ui_ux_designer")
    if any(word in lowered for word in ("security", "risk", "hack", "vulnerability")):
        selected.append("cybersecurity_analyst")
    if any(word in lowered for word in ("research", "latest", "source")):
        selected.append("research_analyst")
    return list(dict.fromkeys(selected))[:6]


def _opinion(agent_id: str, question: str, context: str) -> dict[str, Any]:
    profile = agents.get_agent(agent_id)
    angle = profile.purpose
    confidence = 0.62
    lowered = f"{question} {context}".lower()
    if any(keyword in lowered for keyword in profile.keywords):
        confidence += 0.18
    summary = f"{profile.name}: from my role, prioritize {angle.lower()} Evidence required before final action."
    return {"agent_id": profile.id, "agent_name": profile.name, "summary": summary, "confidence": round(min(0.92, confidence), 3), "stance": _stance(profile.id, lowered)}


def _stance(agent_id: str, lowered: str) -> str:
    if agent_id in {"qa_engineer", "cybersecurity_analyst", "code_reviewer"}:
        return "cautious"
    if "urgent" in lowered or "fast" in lowered:
        return "move_fast_with_checks"
    return "balanced"


def _disagreements(opinions: list[dict[str, Any]]) -> list[str]:
    stances = {item["stance"] for item in opinions}
    if len(stances) <= 1:
        return []
    return [f"Council has mixed stances: {', '.join(sorted(stances))}."]


def _recommend(opinions: list[dict[str, Any]], disagreements: list[str]) -> tuple[str, float]:
    if not opinions:
        return "No council recommendation could be formed.", 0.0
    confidence = sum(float(item["confidence"]) for item in opinions) / len(opinions)
    if disagreements:
        confidence -= 0.12
    recommendation = "Proceed with the highest-evidence path, keep risky steps approval-gated, and verify before claiming completion."
    return recommendation, round(max(0.1, min(0.95, confidence)), 3)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "question": str(row["question"]),
        "agent_ids": _json_loads(row["agent_ids_json"], []),
        "opinions": _json_loads(row["opinions_json"], []),
        "disagreements": _json_loads(row["disagreements_json"], []),
        "recommendation": str(row["recommendation"]),
        "confidence": float(row["confidence"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


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

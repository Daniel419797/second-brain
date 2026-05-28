"""Evidence-based memory debate: belief, proof, confidence, and review prompts."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import certainty_brain, personal_knowledge_vault, personal_memory_review
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "memory_debate.sqlite3"
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
            CREATE TABLE IF NOT EXISTS memory_debates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                topic TEXT NOT NULL,
                belief TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence_json TEXT NOT NULL,
                stale INTEGER NOT NULL,
                question TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )


def debate(topic: str = "", *, limit: int = 8) -> dict[str, Any]:
    init_db()
    query = _clean(topic)
    vault = personal_knowledge_vault.search(query, limit=limit) if query else personal_knowledge_vault.list_items(limit=limit)
    certainty = certainty_brain.search(query, limit=limit)
    beliefs = [_belief_from_vault(item) for item in vault] + [_belief_from_certainty(item) for item in certainty]
    beliefs = sorted(beliefs, key=lambda item: item["confidence"], reverse=True)[:limit]
    records = [_record(query or item["topic"], item) for item in beliefs]
    return {"topic": query, "beliefs": records, "summary": _summary(records)}


def review(limit: int = 8) -> dict[str, Any]:
    generated = _safe(lambda: personal_memory_review.generate(limit=limit), {})
    debates = debate("", limit=limit)["beliefs"]
    return {"memory_review": generated, "debates": debates, "summary": f"{len(debates)} belief(s) ready for keep/update/forget review."}


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM memory_debates ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    items = recent(limit=8)
    return {"recent": items, "summary": f"{len(items)} recent memory debate item(s)." if items else "Memory debate is ready."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM memory_debates")


def _belief_from_vault(item: dict[str, Any]) -> dict[str, Any]:
    confidence = float(item.get("confidence") or 0.5)
    evidence = [item.get("content") or item.get("title") or ""]
    return {"topic": str(item.get("kind") or "memory"), "belief": str(item.get("title") or ""), "confidence": confidence, "evidence": evidence, "stale": confidence < 0.7}


def _belief_from_certainty(item: dict[str, Any]) -> dict[str, Any]:
    return {"topic": str(item.get("topic") or "certainty"), "belief": str(item.get("statement") or ""), "confidence": float(item.get("confidence") or 0.5), "evidence": item.get("evidence") or [], "stale": item.get("kind") in {"guess", "stale", "needs_confirmation"}}


def _record(topic: str, belief: dict[str, Any]) -> dict[str, Any]:
    question = "Is this still true, should I update it, or should I forget it?" if belief["stale"] else "Should I keep this memory as-is?"
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO memory_debates(timestamp, topic, belief, confidence, evidence_json, stale, question, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'open')",
            (_now(), _clean(topic)[:200], _clean(belief["belief"])[:1000], float(belief["confidence"]), _json_dumps(belief["evidence"]), 1 if belief["stale"] else 0, question),
        )
        row = conn.execute("SELECT * FROM memory_debates WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def _summary(items: list[dict[str, Any]]) -> str:
    if not items:
        return "I do not have a strong belief to debate yet."
    top = items[0]
    return f"I believe '{top['belief']}' with {int(top['confidence'] * 100)}% confidence. {top['question']}"


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": int(row["id"]), "timestamp": str(row["timestamp"]), "topic": str(row["topic"]), "belief": str(row["belief"]), "confidence": float(row["confidence"]), "evidence": _json_loads(row["evidence_json"], []), "stale": bool(row["stale"]), "question": str(row["question"]), "status": str(row["status"])}


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

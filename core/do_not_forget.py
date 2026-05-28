"""Route important new knowledge into the right memory tier."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import decision_memory, personal_knowledge_vault, skill_improvement
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "do_not_forget.sqlite3"
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
            CREATE TABLE IF NOT EXISTS memory_routing_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                content TEXT NOT NULL,
                destination TEXT NOT NULL,
                confidence REAL NOT NULL,
                reason TEXT NOT NULL,
                stored_reference TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def classify(content: str, *, source: str = "friday", context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Decide whether something is temporary, project, preference, identity, or skill memory."""

    init_db()
    text = _clean(content)
    lowered = text.lower()
    destination, reason, confidence = _destination(lowered)
    reference = ""
    metadata = dict(context or {})

    if text:
        try:
            if destination == "user_preference":
                item = personal_knowledge_vault.remember_preference("User preference", text, confidence=confidence, tags=["do_not_forget", source])
                decision_memory.learn_from_text(text, source=f"do_not_forget:{source}")
                reference = f"knowledge_vault:{item.get('id')}"
            elif destination == "project_memory":
                item = personal_knowledge_vault.remember("project_fact", "Project memory candidate", text, confidence=confidence, tags=["project", source])
                reference = f"knowledge_vault:{item.get('id')}"
            elif destination == "identity_rule":
                item = personal_knowledge_vault.remember("identity_rule", "Friday identity rule candidate", text, confidence=confidence, tags=["identity", "needs_review"])
                reference = f"knowledge_vault:{item.get('id')}"
            elif destination == "skill_improvement":
                item = skill_improvement.record_failure("general", text, evidence=[source], context=metadata)
                reference = f"skill_improvement:{item.get('id')}"
            else:
                item = personal_knowledge_vault.remember("temporary_context", "Temporary context", text, confidence=confidence, tags=["temporary", source])
                reference = f"knowledge_vault:{item.get('id')}"
        except Exception as exc:
            reference = f"store_failed:{exc}"

    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO memory_routing_decisions(timestamp, source, content, destination, confidence, reason, stored_reference, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_now(), _clean(source)[:120], text[:4000], destination, confidence, reason, reference, _json_dumps(metadata)),
        )
        row = conn.execute("SELECT * FROM memory_routing_decisions WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    item = _row(row)
    item["summary"] = f"Routed memory to {destination}: {reason}"
    return item


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM memory_routing_decisions ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT destination, COUNT(*) FROM memory_routing_decisions GROUP BY destination").fetchall()
    counts = {str(name): int(count) for name, count in rows}
    return {"counts": counts, "recent": recent(limit=8), "summary": f"{sum(counts.values())} do-not-forget routing decision(s)."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM memory_routing_decisions")


def _destination(lowered: str) -> tuple[str, str, float]:
    if any(term in lowered for term in ("never pretend", "must never", "always ask", "must ask", "do not claim", "don't claim")):
        return "identity_rule", "Looks like a stable rule for who Friday must be.", 0.84
    if any(term in lowered for term in ("prefer", "i like", "i don't like", "i dont like", "do not like", "free api", "free tools", "ask first", "too robotic", "too slow")):
        return "user_preference", "Looks like a user preference or correction.", 0.82
    if any(term in lowered for term in ("failed", "didn't work", "did not work", "keeps hearing", "broke", "wrong", "bug")):
        return "skill_improvement", "Looks like a repeated failure Friday should improve from.", 0.78
    if any(term in lowered for term in ("project", "repo", "codebase", "deploy", "auth", "api", "dashboard", "figma", "render", "vercel")):
        return "project_memory", "Looks connected to a project or workflow.", 0.72
    return "temporary_context", "Useful context, but not clearly permanent yet.", 0.52


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "source": str(row["source"]),
        "content": str(row["content"]),
        "destination": str(row["destination"]),
        "confidence": float(row["confidence"]),
        "reason": str(row["reason"]),
        "stored_reference": str(row["stored_reference"]),
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

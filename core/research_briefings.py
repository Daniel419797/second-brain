"""Autonomous research briefings with task handoff support."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import research, task_queue
from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "research_briefings.sqlite3"
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
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL UNIQUE,
                cadence TEXT NOT NULL,
                target_agent_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS briefings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                findings_json TEXT NOT NULL,
                task_id INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_briefings_topic_time ON briefings(topic, timestamp)")


def subscribe(topic: str, *, cadence: str = "daily", target_agent_id: str = "research_analyst") -> dict[str, Any]:
    init_db()
    cleaned = _clean(topic)
    if not cleaned:
        raise ValueError("topic is required")
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO topics(topic, cadence, target_agent_id, status, created_at, updated_at)
            VALUES (?, ?, ?, 'active', ?, ?)
            ON CONFLICT(topic) DO UPDATE SET cadence=excluded.cadence, target_agent_id=excluded.target_agent_id, status='active', updated_at=excluded.updated_at
            """,
            (cleaned, _clean(cadence) or "daily", _clean(target_agent_id) or "research_analyst", now, now),
        )
        row = conn.execute("SELECT * FROM topics WHERE topic=?", (cleaned,)).fetchone()
    return _row(row) | {"summary": f"Subscribed research briefing for {cleaned}."}


def topics(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM topics ORDER BY updated_at DESC LIMIT ?", (max(1, min(100, int(limit))),)).fetchall()
    return [_row(row) for row in rows]


def generate(topic: str, *, max_sources: int | None = None, create_task: bool = False) -> dict[str, Any]:
    cleaned = _clean(topic)
    if not cleaned:
        raise ValueError("topic is required")
    max_sources = max_sources if max_sources is not None else int(config_value("research_briefing_max_sources", 3))
    findings: list[dict[str, Any]] = []
    summary_text = ""
    try:
        report = research.research_topic(cleaned, max_sources=max_sources)
        notes = str(report.get("notes") or "")
        summary_text = _summarize_notes(notes)
        findings = [{"kind": "note", "text": line.strip("- ").strip()} for line in notes.splitlines() if line.strip().startswith("-")][:10]
    except Exception as exc:
        summary_text = f"Could not complete live research: {exc}"
        findings = [{"kind": "error", "text": str(exc)}]
    task_id = 0
    if create_task:
        task = task_queue.create_task(
            f"Research briefing: {cleaned}",
            description=f"Prepare a clean briefing on {cleaned} and pass reusable findings to relevant agents.",
            agent_id="research_analyst",
            priority=int(config_value("research_briefing_task_priority", 7)),
        )
        task_id = int(task.get("id") or 0)
    briefing = _store_briefing(cleaned, f"Briefing: {cleaned}", summary_text, findings, task_id=task_id, source="research")
    return briefing | {"summary": summary_text}


def recent(limit: int = 20, topic: str = "") -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        if _clean(topic):
            rows = conn.execute("SELECT * FROM briefings WHERE topic LIKE ? ORDER BY id DESC LIMIT ?", (f"%{_clean(topic)}%", max(1, min(100, int(limit))))).fetchall()
        else:
            rows = conn.execute("SELECT * FROM briefings ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit))),)).fetchall()
    return [_briefing_row(row) for row in rows]


def summary() -> dict[str, Any]:
    active = [item for item in topics() if item.get("status") == "active"]
    latest = recent(limit=5)
    return {"topics": active, "recent": latest, "summary": f"{len(active)} research briefing topic(s), {len(latest)} recent briefing(s)."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM briefings")
        conn.execute("DELETE FROM topics")


def _store_briefing(topic: str, title: str, summary_text: str, findings: list[dict[str, Any]], *, task_id: int = 0, source: str = "manual") -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO briefings(topic, timestamp, title, summary, findings_json, task_id, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (topic, _now(), title, summary_text, _json_dumps(findings), int(task_id), source),
        )
        row = conn.execute("SELECT * FROM briefings WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _briefing_row(row)


def _summarize_notes(notes: str) -> str:
    lines = [_clean(line.strip("- ")) for line in notes.splitlines() if _clean(line.strip("- "))]
    if not lines:
        return "No new findings yet."
    return "Briefing ready: " + "; ".join(lines[:3])[:500]


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _briefing_row(row: sqlite3.Row) -> dict[str, Any]:
    data = {key: row[key] for key in row.keys() if key != "findings_json"}
    data["findings"] = _json_loads(row["findings_json"], [])
    return data


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

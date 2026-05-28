"""Meeting and study companion for transcripts, summaries, tasks, and flashcards."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import app_integrations, notification_center
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "meeting_study_companion.sqlite3"
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
            CREATE TABLE IF NOT EXISTS study_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                kind TEXT NOT NULL,
                source TEXT NOT NULL,
                transcript TEXT NOT NULL,
                summary TEXT NOT NULL,
                action_items_json TEXT NOT NULL,
                flashcards_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def create_session(title: str, *, kind: str = "meeting", source: str = "", transcript: str = "") -> dict[str, Any]:
    init_db()
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO study_sessions(title, kind, source, transcript, summary, action_items_json, flashcards_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, '', '[]', '[]', ?, ?)
            """,
            (_clean(title) or "Untitled session", _clean(kind) or "meeting", _clean(source), _clean(transcript), now, now),
        )
        row = conn.execute("SELECT * FROM study_sessions WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    session = _row(row)
    if transcript:
        return summarize_session(session["id"])
    return session


def add_transcript(session_id: int, text: str, *, append: bool = True) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        return {"ok": False, "summary": "Session not found."}
    transcript = f"{session.get('transcript', '')}\n{text}" if append else str(text or "")
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE study_sessions SET transcript=?, updated_at=? WHERE id=?", (_clean(transcript), _now(), int(session_id)))
    return summarize_session(session_id)


def summarize_session(session_id: int) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        return {"ok": False, "summary": "Session not found."}
    transcript = session.get("transcript") or ""
    summary = _summarize(transcript)
    actions = _action_items(transcript)
    flashcards = _flashcards(transcript)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            "UPDATE study_sessions SET summary=?, action_items_json=?, flashcards_json=?, updated_at=? WHERE id=?",
            (summary, _json_dumps(actions), _json_dumps(flashcards), _now(), int(session_id)),
        )
    if actions:
        notification_center.add(
            source="study_companion",
            category="follow_up",
            severity=2,
            title="Study session has follow-ups",
            message=f"{len(actions)} action item(s) extracted from {session['title']}.",
            dedupe_key=f"study-actions:{session_id}",
            metadata={"session_id": session_id, "actions": actions},
        )
    return get_session(session_id) or {"id": session_id}


def create_followup_reminders(session_id: int, *, due_at: str = "tomorrow") -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        return {"ok": False, "summary": "Session not found."}
    created = []
    for action in session.get("action_items") or []:
        created.append(app_integrations.create_reminder(action["title"], due_at=due_at, notes=f"From {session['title']}"))
    return {"ok": True, "created": created, "summary": f"Created {len(created)} follow-up reminder(s)."}


def get_session(session_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM study_sessions WHERE id=?", (int(session_id),)).fetchone()
    return _row(row) if row else None


def list_sessions(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM study_sessions ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM study_sessions")


def _summarize(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", _clean(text))
    picked = [sentence for sentence in sentences if len(sentence.split()) >= 5][:5]
    return " ".join(picked)[:1200] or "No transcript summary yet."


def _action_items(text: str) -> list[dict[str, Any]]:
    actions = []
    for line in re.split(r"[\n.;]+", text or ""):
        cleaned = _clean(line)
        lowered = cleaned.lower()
        if not cleaned:
            continue
        if any(term in lowered for term in ["todo", "to do", "need to", "must", "follow up", "remember to", "action item"]):
            actions.append({"title": cleaned[:220], "source": "transcript"})
    return actions[:20]


def _flashcards(text: str) -> list[dict[str, str]]:
    cards = []
    for sentence in re.split(r"(?<=[.!?])\s+", _clean(text)):
        match = re.match(r"(.{3,80}?)\s+(?:is|are|means|refers to)\s+(.{5,180})", sentence, flags=re.IGNORECASE)
        if match:
            cards.append({"front": f"What is {match.group(1).strip()}?", "back": match.group(2).strip()})
    return cards[:30]


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "title": str(row["title"]),
        "kind": str(row["kind"]),
        "source": str(row["source"]),
        "transcript": str(row["transcript"]),
        "summary": str(row["summary"]),
        "action_items": _json_loads(row["action_items_json"], []),
        "flashcards": _json_loads(row["flashcards_json"], []),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=True)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

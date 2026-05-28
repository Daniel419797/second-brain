"""Turn detected emotion/tone into behavior timing decisions."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import emotion_tone
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "emotional_timing.sqlite3"
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
            CREATE TABLE IF NOT EXISTS timing_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                text TEXT NOT NULL,
                tone TEXT NOT NULL,
                behavior_json TEXT NOT NULL
            )
            """
        )


def advise(text: str = "", *, explicit_tone: str = "") -> dict[str, Any]:
    init_db()
    analysis = emotion_tone.analyze_text(text or explicit_tone, store=True)
    tone = explicit_tone or analysis.get("tone") or "neutral"
    behavior = _behavior(str(tone), analysis)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO timing_events(timestamp, text, tone, behavior_json) VALUES (?, ?, ?, ?)",
            (_now(), str(text or "")[:2000], str(tone), _json_dumps(behavior)),
        )
        row = conn.execute("SELECT * FROM timing_events WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    item = _row(row)
    item["analysis"] = analysis
    item["summary"] = behavior["summary"]
    return item


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM timing_events ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    items = recent(limit=8)
    return {"recent": items, "summary": items[0]["summary"] if items else "Emotional timing is ready."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM timing_events")


def _behavior(tone: str, analysis: dict[str, Any]) -> dict[str, Any]:
    tone = tone or "neutral"
    table = {
        "frustrated": {"max_words": 45, "ask_count": 0, "interrupt_threshold": "only critical", "action_bias": "verify_first", "summary": "Use fewer words, verify actions, and avoid claiming success without proof."},
        "tired": {"max_words": 55, "ask_count": 1, "interrupt_threshold": "low", "action_bias": "one_next_step", "summary": "Keep it light and offer one concrete next step."},
        "rushed": {"max_words": 35, "ask_count": 0, "interrupt_threshold": "high", "action_bias": "direct_answer", "summary": "Lead with the answer and postpone optional detail."},
        "confused": {"max_words": 70, "ask_count": 1, "interrupt_threshold": "medium", "action_bias": "clarify_then_act", "summary": "Clarify assumptions in plain language before acting."},
        "focused": {"max_words": 40, "ask_count": 0, "interrupt_threshold": "critical_only", "action_bias": "silent_operator", "summary": "Stay quiet unless something important breaks."},
    }
    behavior = dict(table.get(tone, {"max_words": 65, "ask_count": 1, "interrupt_threshold": "normal", "action_bias": "balanced", "summary": "Respond normally and stay concise."}))
    behavior["tone"] = tone
    behavior["confidence"] = analysis.get("confidence", 0.5)
    behavior["intensity"] = analysis.get("intensity", 0.0)
    return behavior


def _row(row: sqlite3.Row) -> dict[str, Any]:
    behavior = _json_loads(row["behavior_json"], {})
    return {"id": int(row["id"]), "timestamp": str(row["timestamp"]), "text": str(row["text"]), "tone": str(row["tone"]), "behavior": behavior, "summary": behavior.get("summary", "")}


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

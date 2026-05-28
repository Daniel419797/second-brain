"""Personal operating rhythm and energy planning."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import pc_timeline, task_queue
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "operating_rhythm.sqlite3"
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
            CREATE TABLE IF NOT EXISTS energy_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                mood TEXT NOT NULL,
                energy INTEGER NOT NULL,
                focus INTEGER NOT NULL,
                notes TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rhythm_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                kind TEXT NOT NULL,
                value TEXT NOT NULL,
                score REAL NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def record_energy(mood: str = "neutral", energy: int = 5, focus: int = 5, notes: str = "") -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO energy_notes(timestamp, mood, energy, focus, notes) VALUES (?, ?, ?, ?, ?)",
            (_now(), _clean(mood)[:120] or "neutral", _clamp(energy), _clamp(focus), _clean(notes)[:1000]),
        )
        row = conn.execute("SELECT * FROM energy_notes WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _energy_row(row)


def learn_from_timeline() -> dict[str, Any]:
    init_db()
    summary = _safe(lambda: pc_timeline.summary(), {})
    counts = _safe(lambda: task_queue.counts(), {})
    now_hour = dt.datetime.now().hour
    signals = [
        ("active_hour", str(now_hour), 0.5, {"source": "clock"}),
        ("tasks_pending", str(counts.get("pending", 0)), float(counts.get("pending", 0) or 0), {"source": "task_queue"}),
        ("pc_activity", str(summary.get("summary", "")), 0.5, {"source": "pc_timeline"}),
    ]
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        for kind, value, score, metadata in signals:
            conn.execute(
                "INSERT INTO rhythm_signals(timestamp, kind, value, score, metadata_json) VALUES (?, ?, ?, ?, ?)",
                (_now(), kind, value, float(score), _json_dumps(metadata)),
            )
    return {"signals": len(signals), "summary": "Operating rhythm signals refreshed."}


def summary() -> dict[str, Any]:
    init_db()
    latest_energy = energy_notes(limit=1)
    counts = _safe(lambda: task_queue.counts(), {})
    pending = int(counts.get("pending", 0) or 0)
    failed = int(counts.get("failed", 0) or 0)
    energy = latest_energy[0]["energy"] if latest_energy else 5
    focus = latest_energy[0]["focus"] if latest_energy else 5
    recommendation = _recommendation(energy, focus, pending, failed)
    return {
        "latest_energy": latest_energy[0] if latest_energy else None,
        "task_counts": counts,
        "recommendation": recommendation,
        "productive_window": _productive_window(),
        "summary": recommendation,
    }


def energy_notes(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM energy_notes ORDER BY id DESC LIMIT ?", (max(1, min(200, int(limit or 20))),)).fetchall()
    return [_energy_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM energy_notes")
        conn.execute("DELETE FROM rhythm_signals")


def _recommendation(energy: int, focus: int, pending: int, failed: int) -> str:
    if failed:
        return "Start with repair work: failed tasks need attention before new missions."
    if energy >= 7 and focus >= 7:
        return "This looks like a coding/deep-work window."
    if energy <= 3:
        return "Keep it light: admin, review, or planning is better than heavy coding right now."
    if pending >= 5:
        return "Clear small pending tasks first, then return to deep work."
    return "Balanced day: one meaningful project block, then admin cleanup."


def _productive_window() -> str:
    hour = dt.datetime.now().hour
    if 8 <= hour < 12:
        return "morning focus"
    if 12 <= hour < 16:
        return "afternoon execution"
    if 16 <= hour < 21:
        return "evening review"
    return "low-noise planning"


def _energy_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "mood": str(row["mood"]),
        "energy": int(row["energy"]),
        "focus": int(row["focus"]),
        "notes": str(row["notes"]),
    }


def _safe(fn, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _clamp(value: int) -> int:
    try:
        return max(1, min(10, int(value)))
    except Exception:
        return 5


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=True)

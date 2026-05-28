"""Adaptive attention profile for Friday's wake/name gate."""

from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import cognitive_state
from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "adaptive_attention.sqlite3"
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
            CREATE TABLE IF NOT EXISTS attention_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                transcript TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT NOT NULL,
                audio_seconds REAL NOT NULL,
                accepted INTEGER NOT NULL,
                user_corrected INTEGER NOT NULL,
                context_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS attention_profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                updated_at TEXT NOT NULL,
                name_strictness REAL NOT NULL,
                followup_window_seconds REAL NOT NULL,
                false_positive_rate REAL NOT NULL,
                false_negative_rate REAL NOT NULL,
                background_noise_score REAL NOT NULL,
                profile_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_attention_events_time ON attention_events(timestamp)")
        _seed_profile(conn)


def record_attention_event(
    transcript: str,
    decision: str,
    reason: str = "",
    context: dict[str, Any] | None = None,
    *,
    audio_seconds: float = 0.0,
    accepted: bool | None = None,
    user_corrected: bool = False,
) -> int:
    init_db()
    normalized_decision = _clean(decision).lower() or "unknown"
    accepted_value = int(bool(accepted if accepted is not None else normalized_decision in {"accepted", "handled", "command"}))
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO attention_events(timestamp, transcript, decision, reason, audio_seconds, accepted, user_corrected, context_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cognitive_state.now_iso(),
                _clean(transcript)[:1000],
                normalized_decision,
                _clean(reason)[:500],
                max(0.0, float(audio_seconds or 0.0)),
                accepted_value,
                int(bool(user_corrected)),
                cognitive_state.to_json(context or {}),
            ),
        )
        event_id = int(cursor.lastrowid)
    update_profile()
    return event_id


def record_user_correction(expected_text: str, heard_text: str = "") -> dict[str, Any]:
    record_attention_event(
        heard_text or expected_text,
        "corrected",
        "user corrected what Friday heard",
        {"expected_text": expected_text, "heard_text": heard_text},
        accepted=False,
        user_corrected=True,
    )
    profile = update_profile()
    aliases = set(profile.get("profile", {}).get("learned_aliases", []))
    for word in _possible_friday_aliases(f"{expected_text} {heard_text}"):
        aliases.add(word)
    details = dict(profile.get("profile") or {})
    details["learned_aliases"] = sorted(aliases)
    _write_profile(profile | {"profile": details})
    try:
        from core import evaluation_lab, voice_reliability

        voice_reliability.record_sample(
            heard_text,
            expected_text=expected_text,
            raw_text=heard_text,
            backend="user_correction",
            accepted=False,
            correction_applied=True,
            metadata={"source": "adaptive_attention"},
        )
        evaluation_lab.record_event(
            "stt_mistake",
            f"Expected '{expected_text}' but heard '{heard_text}'.",
            source="adaptive_attention",
            severity=3,
            metadata={"expected_text": expected_text, "heard_text": heard_text},
        )
    except Exception:
        pass
    return current_profile()


def update_profile() -> dict[str, Any]:
    init_db()
    events = recent_events(limit=max(8, int(config_value("adaptive_attention_min_events", 8))))
    if not events:
        return current_profile()
    ignored_noise = [event for event in events if not event["accepted"] and _looks_like_background(event["transcript"])]
    corrections = [event for event in events if event["user_corrected"]]
    accepted = [event for event in events if event["accepted"]]
    false_positive_rate = len(ignored_noise) / max(1, len(events))
    false_negative_rate = len(corrections) / max(1, len(events))
    base = current_profile()
    strictness = float(base["name_strictness"])
    followup = float(base["followup_window_seconds"])
    if false_positive_rate >= 0.35:
        strictness = min(1.0, strictness + 0.08)
        followup = max(3.0, followup - 1.0)
    if false_negative_rate >= 0.2:
        strictness = max(0.2, strictness - 0.06)
        followup = min(20.0, followup + 1.0)
    if len(accepted) >= len(events) * 0.7:
        strictness = max(0.25, strictness - 0.02)
    updated = {
        **base,
        "updated_at": cognitive_state.now_iso(),
        "name_strictness": round(strictness, 3),
        "followup_window_seconds": round(followup, 2),
        "false_positive_rate": round(false_positive_rate, 3),
        "false_negative_rate": round(false_negative_rate, 3),
        "background_noise_score": round(false_positive_rate, 3),
    }
    _write_profile(updated)
    return current_profile()


def current_profile() -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM attention_profile WHERE id=1").fetchone()
    return _profile_from_row(row) if row else _default_profile()


def recommended_attention_config() -> dict[str, Any]:
    profile = current_profile()
    return {
        "name_strictness": profile["name_strictness"],
        "followup_window_seconds": profile["followup_window_seconds"],
        "runtime_hints_only": bool(config_value("adaptive_attention_runtime_hints_only", True)),
        "learned_aliases": profile.get("profile", {}).get("learned_aliases", []),
        "reason": f"false_positive_rate={profile['false_positive_rate']}, false_negative_rate={profile['false_negative_rate']}",
    }


def apply_runtime_attention_hints() -> dict[str, Any]:
    return recommended_attention_config()


def recent_events(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM attention_events ORDER BY id DESC LIMIT ?",
            (max(1, min(500, int(limit))),),
        ).fetchall()
    return [_event_from_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM attention_events")
        conn.execute("DELETE FROM attention_profile")
        _seed_profile(conn)


def _seed_profile(conn: sqlite3.Connection) -> None:
    default = _default_profile()
    conn.execute(
        """
        INSERT OR IGNORE INTO attention_profile(
            id, updated_at, name_strictness, followup_window_seconds,
            false_positive_rate, false_negative_rate, background_noise_score, profile_json
        )
        VALUES (1, ?, ?, ?, 0.0, 0.0, 0.0, ?)
        """,
        (
            default["updated_at"],
            default["name_strictness"],
            default["followup_window_seconds"],
            cognitive_state.to_json(default["profile"]),
        ),
    )


def _write_profile(profile: dict[str, Any]) -> None:
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            """
            UPDATE attention_profile
            SET updated_at=?, name_strictness=?, followup_window_seconds=?,
                false_positive_rate=?, false_negative_rate=?, background_noise_score=?, profile_json=?
            WHERE id=1
            """,
            (
                profile.get("updated_at") or cognitive_state.now_iso(),
                float(profile.get("name_strictness", 0.5)),
                float(profile.get("followup_window_seconds", 8.0)),
                float(profile.get("false_positive_rate", 0.0)),
                float(profile.get("false_negative_rate", 0.0)),
                float(profile.get("background_noise_score", 0.0)),
                cognitive_state.to_json(profile.get("profile") or {}),
            ),
        )


def _default_profile() -> dict[str, Any]:
    return {
        "updated_at": cognitive_state.now_iso(),
        "name_strictness": 0.5,
        "followup_window_seconds": float(config_value("conversation_followup_turns", 2)) * 4.0,
        "false_positive_rate": 0.0,
        "false_negative_rate": 0.0,
        "background_noise_score": 0.0,
        "profile": {"learned_aliases": []},
    }


def _profile_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "updated_at": str(row["updated_at"]),
        "name_strictness": float(row["name_strictness"]),
        "followup_window_seconds": float(row["followup_window_seconds"]),
        "false_positive_rate": float(row["false_positive_rate"]),
        "false_negative_rate": float(row["false_negative_rate"]),
        "background_noise_score": float(row["background_noise_score"]),
        "profile": cognitive_state.from_json(row["profile_json"]),
    }


def _event_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "transcript": str(row["transcript"]),
        "decision": str(row["decision"]),
        "reason": str(row["reason"]),
        "audio_seconds": float(row["audio_seconds"]),
        "accepted": bool(row["accepted"]),
        "user_corrected": bool(row["user_corrected"]),
        "context": cognitive_state.from_json(row["context_json"]),
    }


def _looks_like_background(text: str) -> bool:
    lowered = str(text or "").lower()
    phrases = ["thank you for watching", "subscribe", "credits", "video", "i'm going to show you"]
    return any(phrase in lowered for phrase in phrases)


def _possible_friday_aliases(text: str) -> list[str]:
    aliases = []
    for word in re.findall(r"[a-z]+", str(text or "").lower()):
        if word.startswith("fri") or word in {"freddie", "freddy", "fred"}:
            aliases.append(word)
    return aliases


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())

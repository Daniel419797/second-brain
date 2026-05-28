"""Voice reliability lab for bad transcripts, corrections, and learned aliases."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "voice_reliability.sqlite3"
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
            CREATE TABLE IF NOT EXISTS voice_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                expected_text TEXT NOT NULL,
                heard_text TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                audio_seconds REAL NOT NULL,
                backend TEXT NOT NULL,
                confidence REAL,
                accepted INTEGER NOT NULL,
                correction_applied INTEGER NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_voice_samples_time ON voice_samples(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_voice_samples_backend ON voice_samples(backend, accepted)")


def record_sample(
    heard_text: str,
    *,
    expected_text: str = "",
    raw_text: str = "",
    audio_seconds: float = 0.0,
    backend: str = "",
    confidence: float | None = None,
    accepted: bool = True,
    correction_applied: bool = False,
    metadata: dict[str, Any] | None = None,
) -> int:
    if not bool(config_value("voice_reliability_enabled", True)):
        return 0
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO voice_samples (
                timestamp, expected_text, heard_text, raw_text, audio_seconds, backend,
                confidence, accepted, correction_applied, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _now(),
                _clean(expected_text)[:1000],
                _clean(heard_text)[:1000],
                _clean(raw_text or heard_text)[:1000],
                max(0.0, float(audio_seconds or 0.0)),
                _clean(backend)[:80],
                float(confidence) if confidence is not None else None,
                1 if accepted else 0,
                1 if correction_applied else 0,
                _json_dumps(metadata or {}),
            ),
        )
        return int(cursor.lastrowid)


def record_correction(expected_text: str, heard_text: str = "", *, backend: str = "user", metadata: dict[str, Any] | None = None) -> int:
    sample_id = record_sample(
        heard_text,
        expected_text=expected_text,
        raw_text=heard_text,
        backend=backend,
        accepted=False,
        correction_applied=True,
        metadata=metadata or {},
    )
    _sync_attention_aliases(expected_text, heard_text)
    try:
        from core import evaluation_lab

        evaluation_lab.record_event(
            "stt_mistake",
            f"Expected '{expected_text}' but heard '{heard_text}'.",
            source="voice_reliability",
            severity=3,
            metadata={"sample_id": sample_id, **(metadata or {})},
        )
    except Exception:
        pass
    return sample_id


def recent_samples(limit: int = 80, *, mistakes_only: bool = False) -> list[dict[str, Any]]:
    init_db()
    where = "WHERE correction_applied = 1 OR accepted = 0" if mistakes_only else ""
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM voice_samples {where} ORDER BY id DESC LIMIT ?",
            (max(1, min(500, int(limit))),),
        ).fetchall()
    return [_row_to_sample(row) for row in rows]


def summary(limit: int = 12) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT backend, COUNT(*), SUM(CASE WHEN accepted = 0 OR correction_applied = 1 THEN 1 ELSE 0 END) FROM voice_samples GROUP BY backend").fetchall()
    backends: dict[str, dict[str, int]] = {}
    for backend, count, mistakes in rows:
        backends[str(backend or "unknown")] = {"samples": int(count), "mistakes": int(mistakes or 0)}
    return {
        "backends": backends,
        "learned_aliases": learned_aliases(),
        "recent_mistakes": recent_samples(limit=limit, mistakes_only=True),
    }


def learned_aliases(limit: int = 20) -> list[str]:
    aliases: set[str] = set()
    for sample in recent_samples(limit=200, mistakes_only=True):
        expected = sample.get("expected_text", "")
        heard = sample.get("heard_text", "")
        if "friday" in expected.lower():
            aliases.update(_possible_friday_aliases(heard))
    return sorted(aliases)[:limit]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM voice_samples")


def _sync_attention_aliases(expected_text: str, heard_text: str) -> None:
    try:
        from core import adaptive_attention

        adaptive_attention.record_user_correction(expected_text, heard_text)
    except Exception:
        return


def _possible_friday_aliases(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z'-]{1,24}", str(text or "").lower())
    aliases: list[str] = []
    for word in words:
        if _levenshtein(word, "friday") <= 3 or word in {"freddie", "freddy", "fred", "friady", "friyday", "friiday", "fryday"}:
            aliases.append(word)
    return aliases


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def _row_to_sample(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "expected_text": str(row["expected_text"]),
        "heard_text": str(row["heard_text"]),
        "raw_text": str(row["raw_text"]),
        "audio_seconds": float(row["audio_seconds"]),
        "backend": str(row["backend"]),
        "confidence": row["confidence"],
        "accepted": bool(row["accepted"]),
        "correction_applied": bool(row["correction_applied"]),
        "metadata": _json_loads(row["metadata_json"]),
    }


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=True)


def _json_loads(value: str) -> Any:
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

"""User-specific command aliases and learned command style."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "personal_command_memory.sqlite3"
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
            CREATE TABLE IF NOT EXISTS command_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                heard_phrase TEXT NOT NULL,
                normalized_phrase TEXT NOT NULL UNIQUE,
                canonical_command TEXT NOT NULL,
                confidence REAL NOT NULL,
                success_count INTEGER NOT NULL,
                failure_count INTEGER NOT NULL,
                notes TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_command_memory_norm ON command_memories(normalized_phrase)")


def learn(heard_phrase: str, canonical_command: str, *, notes: str = "", confidence: float = 0.8, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    heard = _clean(heard_phrase)
    canonical = _clean(canonical_command)
    if not heard or not canonical:
        return {"ok": False, "summary": "Both the phrase and command are required."}
    norm = _normalize(heard)
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO command_memories(created_at, updated_at, heard_phrase, normalized_phrase, canonical_command, confidence, success_count, failure_count, notes, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
            ON CONFLICT(normalized_phrase) DO UPDATE SET
                updated_at=excluded.updated_at,
                heard_phrase=excluded.heard_phrase,
                canonical_command=excluded.canonical_command,
                confidence=max(command_memories.confidence, excluded.confidence),
                notes=excluded.notes,
                metadata_json=excluded.metadata_json
            """,
            (now, now, heard, norm, canonical, _clamp(confidence), _clean(notes), _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM command_memories WHERE normalized_phrase=?", (norm,)).fetchone()
    item = _row(row)
    item["ok"] = True
    item["summary"] = f"Learned: when you say '{item['heard_phrase']}', run '{item['canonical_command']}'."
    return item


def resolve(text: str, *, min_confidence: float = 0.55) -> dict[str, Any] | None:
    init_db()
    norm = _normalize(text)
    if not norm:
        return None
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM command_memories WHERE normalized_phrase=? AND confidence>=?",
            (norm, float(min_confidence)),
        ).fetchone()
        if row:
            return _row(row)
        rows = conn.execute("SELECT * FROM command_memories WHERE confidence>=? ORDER BY confidence DESC, success_count DESC LIMIT 200", (float(min_confidence),)).fetchall()
    terms = set(norm.split())
    best: tuple[float, sqlite3.Row] | None = None
    for row in rows:
        candidate = str(row["normalized_phrase"])
        candidate_terms = set(candidate.split())
        if not candidate_terms:
            continue
        overlap = len(terms & candidate_terms) / max(len(candidate_terms), len(terms), 1)
        exactish = norm in candidate or candidate in norm
        score = overlap + (0.35 if exactish else 0.0) + min(0.15, int(row["success_count"]) * 0.03)
        if score >= 0.82 and (best is None or score > best[0]):
            best = (score, row)
    if not best:
        return None
    item = _row(best[1])
    item["match_score"] = round(best[0], 3)
    return item


def record_result(command_id: int, *, success: bool, note: str = "") -> dict[str, Any] | None:
    init_db()
    field = "success_count" if success else "failure_count"
    confidence_delta = 0.04 if success else -0.12
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            f"UPDATE command_memories SET {field}={field}+1, confidence=max(0.1, min(1.0, confidence + ?)), updated_at=?, notes=CASE WHEN ?='' THEN notes ELSE ? END WHERE id=?",
            (confidence_delta, _now(), _clean(note), _clean(note), int(command_id)),
        )
        row = conn.execute("SELECT * FROM command_memories WHERE id=?", (int(command_id),)).fetchone()
    return _row(row) if row else None


def list_commands(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM command_memories ORDER BY updated_at DESC, confidence DESC LIMIT ?",
            (max(1, min(200, int(limit or 50))),),
        ).fetchall()
    return [_row(row) for row in rows]


def summary(limit: int = 8) -> dict[str, Any]:
    items = list_commands(limit=limit)
    return {
        "count": len(list_commands(limit=200)),
        "recent": items,
        "summary": f"{len(items)} learned command shortcut(s) ready." if items else "No personal command shortcuts learned yet.",
    }


def install_default_language() -> dict[str, Any]:
    defaults = [
        ("start work", "open VS Code and start the API and dashboard"),
        ("check Friday", "show pending tasks, health, workers, and recent failures"),
        ("check project", "run deep project autopilot"),
        ("ship it", "run build, QA lab, release preparation, and proof report"),
        ("reduce volume", "set PC volume to 40%"),
    ]
    installed = [learn(heard, command, notes="default personal command language", confidence=0.72) for heard, command in defaults]
    return {"installed": installed, "summary": f"Installed {len(installed)} default personal command shortcut(s)."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM command_memories")


def parse_learning_phrase(text: str) -> tuple[str, str] | None:
    cleaned = _clean(text)
    patterns = (
        r"^when i say ['\"]?(.+?)['\"]?,?\s+(?:do|run|execute|make friday do)\s+(.+)$",
        r"^(?:remember|learn)\s+(?:the\s+)?command\s+['\"]?(.+?)['\"]?\s+(?:means|as|to mean)\s+(.+)$",
        r"^no,?\s+i\s+said\s+(.+?)\s+(?:which means|meaning)\s+(.+)$",
    )
    for pattern in patterns:
        match = re.match(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            return _clean(match.group(1)), _clean(match.group(2))
    return None


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "heard_phrase": str(row["heard_phrase"]),
        "canonical_command": str(row["canonical_command"]),
        "confidence": float(row["confidence"]),
        "success_count": int(row["success_count"]),
        "failure_count": int(row["failure_count"]),
        "notes": str(row["notes"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9%]+", " ", str(value or "").lower())).strip()


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())


def _clamp(value: Any) -> float:
    try:
        return max(0.1, min(1.0, float(value)))
    except Exception:
        return 0.8


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

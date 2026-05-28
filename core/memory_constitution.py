"""Policy layer for what Friday may remember, ask about, expire, or keep private."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "memory_constitution.sqlite3"
_LOCK = threading.Lock()

DEFAULT_POLICIES = [
    {"kind": "user_preference", "mode": "allow", "retention": "long", "private": "no", "description": "Preferences the user explicitly states."},
    {"kind": "project_memory", "mode": "allow", "retention": "project_lifetime", "private": "maybe", "description": "Facts about user-owned projects."},
    {"kind": "identity_rule", "mode": "ask", "retention": "long", "private": "no", "description": "Rules about Friday identity and behavior."},
    {"kind": "personal_file", "mode": "ask", "retention": "short", "private": "yes", "description": "Personal documents and sensitive local files."},
    {"kind": "secret", "mode": "block", "retention": "never", "private": "yes", "description": "Passwords, tokens, .env values, hidden credentials."},
    {"kind": "inferred_personal_fact", "mode": "ask", "retention": "review", "private": "yes", "description": "Personal facts Friday inferred but user did not explicitly state."},
]


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
            CREATE TABLE IF NOT EXISTS memory_policies (
                kind TEXT PRIMARY KEY,
                mode TEXT NOT NULL,
                retention TEXT NOT NULL,
                private TEXT NOT NULL,
                description TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_policy_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                kind TEXT NOT NULL,
                content_excerpt TEXT NOT NULL,
                decision_json TEXT NOT NULL
            )
            """
        )
        for policy in DEFAULT_POLICIES:
            conn.execute(
                """
                INSERT OR IGNORE INTO memory_policies(kind, mode, retention, private, description, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (policy["kind"], policy["mode"], policy["retention"], policy["private"], policy["description"], _now()),
            )


def evaluate(kind: str, content: str = "", *, sensitivity: str = "normal") -> dict[str, Any]:
    init_db()
    inferred = _infer_kind(kind, content, sensitivity)
    policy = get_policy(inferred)
    decision = {
        "kind": inferred,
        "mode": policy.get("mode", "ask"),
        "retention": policy.get("retention", "review"),
        "private": policy.get("private", "maybe") in {"yes", "maybe"} or sensitivity.lower() in {"private", "secret"},
        "ask_required": policy.get("mode") == "ask",
        "blocked": policy.get("mode") == "block",
        "reason": policy.get("description", ""),
        "summary": "",
    }
    if decision["blocked"]:
        decision["summary"] = "Memory constitution blocks storing this content."
    elif decision["ask_required"]:
        decision["summary"] = "Memory constitution requires user approval before storing or using this."
    else:
        decision["summary"] = "Memory constitution allows this memory under its retention rule."
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            "INSERT INTO memory_policy_events(timestamp, kind, content_excerpt, decision_json) VALUES (?, ?, ?, ?)",
            (_now(), inferred, _clean(content)[:500], _json_dumps(decision)),
        )
    return decision


def get_policy(kind: str) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM memory_policies WHERE kind=?", (_clean(kind).lower().replace(" ", "_"),)).fetchone()
    if row:
        return _row(row)
    return {"kind": kind, "mode": "ask", "retention": "review", "private": "maybe", "description": "Unknown memory type; ask first."}


def set_policy(kind: str, *, mode: str = "ask", retention: str = "review", private: str = "maybe", description: str = "") -> dict[str, Any]:
    init_db()
    normalized = _clean(kind).lower().replace(" ", "_")
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO memory_policies(kind, mode, retention, private, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(kind) DO UPDATE SET mode=excluded.mode, retention=excluded.retention, private=excluded.private, description=excluded.description, updated_at=excluded.updated_at
            """,
            (normalized, _mode(mode), _clean(retention) or "review", _private(private), _clean(description), _now()),
        )
        row = conn.execute("SELECT * FROM memory_policies WHERE kind=?", (normalized,)).fetchone()
    return _row(row)


def rules() -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM memory_policies ORDER BY kind").fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    return {"rules": rules(), "summary": f"{len(rules())} memory constitution rule(s) active."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM memory_policies")
        conn.execute("DELETE FROM memory_policy_events")
    init_db()


def _infer_kind(kind: str, content: str, sensitivity: str) -> str:
    explicit = _clean(kind).lower().replace(" ", "_")
    lowered = content.lower()
    if sensitivity.lower() == "secret" or ".env" in lowered or re.search(r"(api[_-]?key|password|token|secret)\s*[:=]", lowered):
        return "secret"
    if explicit:
        return explicit
    if any(term in lowered for term in ("i prefer", "i like", "i don't like", "i dont like")):
        return "user_preference"
    if any(term in lowered for term in ("project", "repo", "deploy", "auth")):
        return "project_memory"
    return "inferred_personal_fact"


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {"kind": str(row["kind"]), "mode": str(row["mode"]), "retention": str(row["retention"]), "private": str(row["private"]), "description": str(row["description"]), "updated_at": str(row["updated_at"])}


def _mode(value: str) -> str:
    text = _clean(value).lower()
    return text if text in {"allow", "ask", "block"} else "ask"


def _private(value: str) -> str:
    text = _clean(value).lower()
    return text if text in {"yes", "no", "maybe"} else "maybe"


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

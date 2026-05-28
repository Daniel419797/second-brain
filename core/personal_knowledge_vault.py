"""Private personal knowledge vault for stable user/project context."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "personal_knowledge_vault.sqlite3"
VALID_KINDS = {"goal", "project", "habit", "person", "preference", "correction", "weekly_priority", "fact", "routine"}
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
            CREATE TABLE IF NOT EXISTS vault_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                confidence REAL NOT NULL,
                tags TEXT NOT NULL,
                status TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vault_kind ON vault_items(kind, status, updated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vault_title ON vault_items(title)")


def remember(
    kind: str,
    title: str,
    content: str = "",
    *,
    confidence: float = 0.7,
    tags: list[str] | str | None = None,
    status: str = "active",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    normalized_kind = _kind(kind)
    clean_title = _clean(title)
    if not clean_title:
        raise ValueError("Vault title is required.")
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO vault_items(timestamp, updated_at, kind, title, content, confidence, tags, status, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                now,
                normalized_kind,
                clean_title[:300],
                _clean(content)[:5000],
                _confidence(confidence),
                _tags(tags),
                _clean(status).lower() or "active",
                _json_dumps(metadata or {}),
            ),
        )
        row = conn.execute("SELECT * FROM vault_items WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def remember_preference(title: str, content: str = "", *, confidence: float = 0.8, tags: list[str] | str | None = None) -> dict[str, Any]:
    return remember("preference", title, content, confidence=confidence, tags=tags)


def remember_correction(expected: str, heard: str = "", *, source: str = "voice") -> dict[str, Any]:
    title = f"Correction: {expected[:120]}"
    content = f"Expected: {expected}. Heard: {heard}."
    return remember("correction", title, content, confidence=0.9, tags=["correction", source], metadata={"expected": expected, "heard": heard, "source": source})


def set_weekly_priority(title: str, content: str = "") -> dict[str, Any]:
    return remember("weekly_priority", title, content, confidence=0.8, tags=["this_week"])


def list_items(kind: str = "", *, status: str = "active", limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    where: list[str] = []
    params: list[Any] = []
    if kind:
        where.append("kind=?")
        params.append(_kind(kind))
    if status:
        where.append("status=?")
        params.append(_clean(status).lower())
    params.append(max(1, min(500, int(limit or 50))))
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM vault_items {clause} ORDER BY confidence DESC, updated_at DESC, id DESC LIMIT ?", params).fetchall()
    return [_row(row) for row in rows]


def search(query: str, *, kind: str = "", limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    terms = [term for term in re.split(r"\s+", _clean(query).lower()) if term][:8]
    if not terms:
        return list_items(kind=kind, limit=limit)
    where: list[str] = []
    params: list[Any] = []
    if kind:
        where.append("kind=?")
        params.append(_kind(kind))
    for term in terms:
        needle = f"%{term}%"
        where.append("(lower(title) LIKE ? OR lower(content) LIKE ? OR lower(tags) LIKE ?)")
        params.extend([needle, needle, needle])
    params.append(max(1, min(200, int(limit or 20))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM vault_items WHERE {' AND '.join(where)} ORDER BY confidence DESC, updated_at DESC LIMIT ?", params).fetchall()
    return [_row(row) for row in rows]


def what_matters_this_week(limit: int = 10) -> dict[str, Any]:
    priorities = list_items("weekly_priority", limit=limit)
    goals = list_items("goal", limit=limit)
    projects = list_items("project", limit=limit)
    return {
        "priorities": priorities,
        "goals": goals,
        "projects": projects,
        "summary": _weekly_summary(priorities, goals, projects),
    }


def summary(limit: int = 8) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT kind, COUNT(*) FROM vault_items WHERE status='active' GROUP BY kind").fetchall()
    counts = {str(kind): int(count) for kind, count in rows}
    return {
        "counts": counts,
        "weekly": what_matters_this_week(limit=limit),
        "recent": list_items(limit=limit),
    }


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM vault_items")


def _weekly_summary(priorities: list[dict[str, Any]], goals: list[dict[str, Any]], projects: list[dict[str, Any]]) -> str:
    if priorities:
        return "This week matters most: " + "; ".join(item["title"] for item in priorities[:3]) + "."
    if goals:
        return "Main active goal: " + goals[0]["title"] + "."
    if projects:
        return "Main known project: " + projects[0]["title"] + "."
    return "No weekly priorities have been saved yet."


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "updated_at": str(row["updated_at"]),
        "kind": str(row["kind"]),
        "title": str(row["title"]),
        "content": str(row["content"]),
        "confidence": float(row["confidence"]),
        "tags": [item for item in str(row["tags"]).split(",") if item],
        "status": str(row["status"]),
        "metadata": _json_loads(row["metadata_json"]),
    }


def _kind(value: str) -> str:
    kind = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    return kind if kind in VALID_KINDS else "fact"


def _tags(value: list[str] | str | None) -> str:
    if value is None:
        return ""
    raw = value.split(",") if isinstance(value, str) else value
    tags = []
    for item in raw:
        tag = re.sub(r"[^a-z0-9_]+", "_", str(item or "").strip().lower()).strip("_")
        if tag and tag not in tags:
            tags.append(tag)
    return ",".join(tags[:20])


def _confidence(value: float) -> float:
    try:
        raw = float(value)
    except Exception:
        raw = 0.7
    return max(0.0, min(1.0, raw))


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

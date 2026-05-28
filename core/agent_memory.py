"""Per-agent notebooks for reusable specialist memory."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "agent_memory.sqlite3"
_LOCK = threading.Lock()

VALID_KINDS = {"source", "fact", "implementation_pattern", "recurring_bug", "design_rule", "security_check", "lesson", "note"}


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
            CREATE TABLE IF NOT EXISTS agent_notebook_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_memory_agent ON agent_notebook_items(agent_id, kind, updated_at)")
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS agent_notebook_fts USING fts5(title, content, tags, content='')")


def remember(
    agent_id: str,
    kind: str,
    title: str,
    content: str,
    *,
    tags: list[str] | tuple[str, ...] | None = None,
    confidence: float = 0.55,
    source: str = "",
) -> dict[str, Any]:
    init_db()
    now = _now()
    normalized_kind = _normalize_kind(kind)
    tag_list = [str(tag).strip().lower() for tag in (tags or []) if str(tag).strip()]
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO agent_notebook_items (
                agent_id, kind, title, content, tags_json, confidence, source, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _clean(agent_id) or "agent",
                normalized_kind,
                _clean(title)[:300] or normalized_kind.title(),
                _clean(content)[:6000],
                _json_dumps(tag_list),
                _clamp01(confidence),
                _clean(source)[:300],
                now,
                now,
            ),
        )
        item_id = int(cursor.lastrowid)
        conn.execute(
            "INSERT INTO agent_notebook_fts(rowid, title, content, tags) VALUES (?, ?, ?, ?)",
            (item_id, _clean(title), _clean(content), " ".join(tag_list)),
        )
        row = conn.execute("SELECT * FROM agent_notebook_items WHERE id=?", (item_id,)).fetchone()
    return _row_to_item(row)


def search(agent_id: str, query: str = "", *, limit: int = 8) -> list[dict[str, Any]]:
    init_db()
    normalized_agent = _clean(agent_id)
    cleaned_query = _fts_query(query)
    params: list[Any]
    sql: str
    if cleaned_query:
        sql = (
            "SELECT m.* FROM agent_notebook_items m "
            "JOIN agent_notebook_fts f ON f.rowid = m.id "
            "WHERE m.agent_id = ? AND agent_notebook_fts MATCH ? "
            "ORDER BY bm25(agent_notebook_fts), m.updated_at DESC LIMIT ?"
        )
        params = [normalized_agent, cleaned_query, max(1, min(100, int(limit)))]
    else:
        sql = "SELECT * FROM agent_notebook_items WHERE agent_id=? ORDER BY updated_at DESC, id DESC LIMIT ?"
        params = [normalized_agent, max(1, min(100, int(limit)))]
    try:
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM agent_notebook_items WHERE agent_id=? ORDER BY updated_at DESC, id DESC LIMIT ?",
                (normalized_agent, max(1, min(100, int(limit)))),
            ).fetchall()
    return [_row_to_item(row) for row in rows]


def notebook(agent_id: str, limit: int = 30) -> dict[str, Any]:
    items = search(agent_id, "", limit=limit)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(item["kind"], []).append(item)
    return {"agent_id": _clean(agent_id), "items": items, "by_kind": grouped}


def context_for_agent(agent_id: str, query: str, limit: int = 5) -> str:
    items = search(agent_id, query, limit=limit)
    if not items:
        return ""
    lines = [f"{agent_id} notebook memory:"]
    for item in items:
        tags = ", ".join(item.get("tags") or [])
        lines.append(f"- {item['kind']} ({item['confidence']:.2f}) {item['title']}: {item['content'][:260]} {f'[{tags}]' if tags else ''}")
    return "\n".join(lines)


def summary(limit: int = 5) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT agent_id, kind, COUNT(*) FROM agent_notebook_items GROUP BY agent_id, kind").fetchall()
    agents: dict[str, dict[str, int]] = {}
    for agent_id, kind, count in rows:
        agents.setdefault(str(agent_id), {})[str(kind)] = int(count)
    return {
        "agents": agents,
        "recent": _recent(limit=limit),
    }


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM agent_notebook_items")
        conn.execute("DROP TABLE IF EXISTS agent_notebook_fts")
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS agent_notebook_fts USING fts5(title, content, tags, content='')")


def _recent(limit: int = 10) -> list[dict[str, Any]]:
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM agent_notebook_items ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit))),)).fetchall()
    return [_row_to_item(row) for row in rows]


def _normalize_kind(value: str) -> str:
    kind = _clean(value).lower().replace(" ", "_").replace("-", "_")
    return kind if kind in VALID_KINDS else "note"


def _row_to_item(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "agent_id": str(row["agent_id"]),
        "kind": str(row["kind"]),
        "title": str(row["title"]),
        "content": str(row["content"]),
        "tags": _json_loads(row["tags_json"], []),
        "confidence": float(row["confidence"]),
        "source": str(row["source"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def _fts_query(value: str) -> str:
    words = [word.strip() for word in "".join(ch if ch.isalnum() or ch == "_" else " " for ch in str(value or "").lower()).split()]
    return " OR ".join(words[:8])


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=True)


def _json_loads(value: str, default: Any = None) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return [] if default is None else default


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _clamp01(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.5


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

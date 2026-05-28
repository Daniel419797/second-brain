"""Shared structured workspace for Friday's agent team."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "agent_blackboard.sqlite3"
_LOCK = threading.Lock()

VALID_TYPES = {"finding", "question", "evidence", "blocker", "decision", "need", "progress"}
OPEN_STATUSES = {"open", "active", "blocked", "needs_answer"}
FINAL_STATUSES = {"resolved", "closed", "cancelled"}


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
            CREATE TABLE IF NOT EXISTS blackboard_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                task_id INTEGER,
                item_type TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                confidence REAL NOT NULL,
                target_agent_id TEXT NOT NULL,
                status TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_blackboard_status ON blackboard_items(status, updated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_blackboard_agent ON blackboard_items(agent_id, item_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_blackboard_task ON blackboard_items(task_id)")


def post_item(
    agent_id: str,
    item_type: str,
    title: str,
    content: str = "",
    *,
    task_id: int | None = None,
    confidence: float = 0.5,
    target_agent_id: str = "",
    status: str = "open",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    now = _now()
    normalized_type = _normalize_type(item_type)
    normalized_status = _normalize_status(status, normalized_type)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO blackboard_items (
                timestamp, updated_at, agent_id, task_id, item_type, title, content,
                confidence, target_agent_id, status, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                now,
                _clean(agent_id) or "agent",
                int(task_id) if task_id else None,
                normalized_type,
                _clean(title)[:300] or normalized_type.title(),
                _clean(content)[:5000],
                _clamp01(confidence),
                _clean(target_agent_id),
                normalized_status,
                _json_dumps(metadata or {}),
            ),
        )
        row = conn.execute("SELECT * FROM blackboard_items WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row_to_item(row)


def list_items(
    *,
    status: str = "",
    item_type: str = "",
    agent_id: str = "",
    task_id: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    init_db()
    where: list[str] = []
    params: list[Any] = []
    if status:
        where.append("status = ?")
        params.append(_normalize_status(status))
    if item_type:
        where.append("item_type = ?")
        params.append(_normalize_type(item_type))
    if agent_id:
        where.append("agent_id = ?")
        params.append(_clean(agent_id))
    if task_id:
        where.append("task_id = ?")
        params.append(int(task_id))
    sql = "SELECT * FROM blackboard_items"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'active' THEN 1 WHEN 'needs_answer' THEN 2 WHEN 'blocked' THEN 3 ELSE 4 END, id DESC LIMIT ?"
    params.append(max(1, min(300, int(limit))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_item(row) for row in rows]


def resolve_item(item_id: int, note: str = "", *, status: str = "resolved") -> dict[str, Any] | None:
    init_db()
    normalized = _normalize_status(status)
    if normalized not in FINAL_STATUSES | {"resolved"}:
        normalized = "resolved"
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM blackboard_items WHERE id=?", (int(item_id),)).fetchone()
        if not row:
            return None
        metadata = _json_loads(row["metadata_json"])
        if note:
            metadata["resolution_note"] = _clean(note)
        conn.execute(
            "UPDATE blackboard_items SET status=?, updated_at=?, metadata_json=? WHERE id=?",
            (normalized, now, _json_dumps(metadata), int(item_id)),
        )
        updated = conn.execute("SELECT * FROM blackboard_items WHERE id=?", (int(item_id),)).fetchone()
    return _row_to_item(updated)


def summary(limit: int = 12) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT item_type, status, COUNT(*) FROM blackboard_items GROUP BY item_type, status").fetchall()
    counts: dict[str, dict[str, int]] = {}
    for item_type, status, count in rows:
        counts.setdefault(str(item_type), {})[str(status)] = int(count)
    open_items = list_items(status="open", limit=limit)
    blockers = list_items(status="blocked", limit=limit)
    questions = [item for item in list_items(item_type="question", limit=limit) if item["status"] in OPEN_STATUSES]
    return {
        "counts": counts,
        "open_count": sum(count for statuses in counts.values() for status, count in statuses.items() if status in OPEN_STATUSES),
        "open_items": open_items[:limit],
        "blockers": blockers[:limit],
        "questions": questions[:limit],
    }


def task_context(task_id: int, limit: int = 8) -> str:
    items = list_items(task_id=task_id, limit=limit)
    if not items:
        return ""
    lines = ["Agent blackboard context:"]
    for item in items[:limit]:
        lines.append(
            f"- {item['item_type']} from {item['agent_id']} ({item['confidence']:.2f}, {item['status']}): "
            f"{item['title']} - {item['content'][:220]}"
        )
    return "\n".join(lines)


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM blackboard_items")


def _normalize_type(value: str) -> str:
    item_type = _clean(value).lower().replace(" ", "_")
    return item_type if item_type in VALID_TYPES else "finding"


def _normalize_status(value: str, item_type: str = "") -> str:
    status = _clean(value).lower().replace(" ", "_")
    if status in OPEN_STATUSES | FINAL_STATUSES:
        return status
    if item_type == "question":
        return "needs_answer"
    if item_type == "blocker":
        return "blocked"
    return "open"


def _row_to_item(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "updated_at": str(row["updated_at"]),
        "agent_id": str(row["agent_id"]),
        "task_id": row["task_id"],
        "item_type": str(row["item_type"]),
        "title": str(row["title"]),
        "content": str(row["content"]),
        "confidence": float(row["confidence"]),
        "target_agent_id": str(row["target_agent_id"] or ""),
        "status": str(row["status"]),
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


def _clamp01(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.5


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

"""Silent internal thought bus for Friday's agent team.

This is not hidden model-state telepathy. It is a practical shared working
memory where agents can pass compact, structured packets to each other without
turning every note into a spoken status update.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "agent_thought_bus.sqlite3"
_LOCK = threading.Lock()

VALID_PACKET_TYPES = {
    "context",
    "finding",
    "question",
    "answer",
    "research_handoff",
    "plan",
    "risk",
    "result_summary",
    "need",
    "decision",
    "delegation",
    "memory",
}
VALID_STATUSES = {"open", "seen", "resolved", "expired", "cancelled"}
VALID_VISIBILITY = {"silent", "surface", "debug"}


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
            CREATE TABLE IF NOT EXISTS thought_packets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source_agent_id TEXT NOT NULL,
                target_agent_id TEXT NOT NULL,
                task_id INTEGER,
                packet_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                content_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                priority INTEGER NOT NULL,
                status TEXT NOT NULL,
                visibility TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                keywords_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_thought_status ON thought_packets(status, updated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_thought_target ON thought_packets(target_agent_id, status, updated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_thought_task ON thought_packets(task_id, status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_thought_type ON thought_packets(packet_type, status)")


def post_thought(
    source_agent_id: str,
    packet_type: str,
    summary: str,
    content: dict[str, Any] | str | None = None,
    *,
    target_agent_id: str = "",
    task_id: int | None = None,
    confidence: float = 0.55,
    priority: int = 5,
    status: str = "open",
    visibility: str = "silent",
    ttl_seconds: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Store a silent packet from one agent to another.

    Empty target means "team-visible internal context". Packets remain readable
    from the dashboard, but the default visibility keeps them out of voice
    responses unless explicitly queried.
    """

    init_db()
    now = _now()
    expires = _expires_at(ttl_seconds)
    normalized_type = _normalize_type(packet_type)
    normalized_status = _normalize_status(status)
    normalized_visibility = _normalize_visibility(visibility)
    payload = _payload(content)
    cleaned_summary = _clean(summary)[:500] or normalized_type.replace("_", " ").title()
    keywords = _keywords(" ".join([cleaned_summary, _json_dumps(payload), _json_dumps(metadata or {})]))
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO thought_packets (
                timestamp, updated_at, source_agent_id, target_agent_id, task_id, packet_type,
                summary, content_json, confidence, priority, status, visibility,
                expires_at, keywords_json, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                now,
                _agent_id(source_agent_id) or "agent",
                _agent_id(target_agent_id),
                int(task_id) if task_id else None,
                normalized_type,
                cleaned_summary,
                _json_dumps(payload),
                _clamp01(confidence),
                _priority(priority),
                normalized_status,
                normalized_visibility,
                expires,
                _json_dumps(keywords),
                _json_dumps(metadata or {}),
            ),
        )
        row = conn.execute("SELECT * FROM thought_packets WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row_to_packet(row)


def list_thoughts(
    *,
    status: str = "",
    packet_type: str = "",
    source_agent_id: str = "",
    target_agent_id: str = "",
    task_id: int | None = None,
    visibility: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    init_db()
    expire_old()
    where: list[str] = []
    params: list[Any] = []
    if status:
        where.append("status = ?")
        params.append(_normalize_status(status))
    if packet_type:
        where.append("packet_type = ?")
        params.append(_normalize_type(packet_type))
    if source_agent_id:
        where.append("source_agent_id = ?")
        params.append(_agent_id(source_agent_id))
    if target_agent_id:
        where.append("target_agent_id = ?")
        params.append(_agent_id(target_agent_id))
    if task_id:
        where.append("task_id = ?")
        params.append(int(task_id))
    if visibility:
        where.append("visibility = ?")
        params.append(_normalize_visibility(visibility))
    sql = "SELECT * FROM thought_packets"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'seen' THEN 1 ELSE 2 END, priority ASC, id DESC LIMIT ?"
    params.append(max(1, min(300, int(limit))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_packet(row) for row in rows]


def recent_thoughts(agent_id: str = "", *, task_id: int | None = None, limit: int = 20) -> list[dict[str, Any]]:
    agent = _agent_id(agent_id)
    thoughts = list_thoughts(task_id=task_id, limit=max(limit * 3, 20))
    if not agent:
        return thoughts[:limit]
    filtered = [
        item
        for item in thoughts
        if item["target_agent_id"] in {"", agent} or item["source_agent_id"] == agent
    ]
    return filtered[:limit]


def relevant_thoughts(agent_id: str, query: str, *, task_id: int | None = None, limit: int = 8) -> list[dict[str, Any]]:
    agent = _agent_id(agent_id)
    query_keywords = set(_keywords(query))
    candidates = recent_thoughts(agent, task_id=task_id, limit=max(limit * 5, 30))
    scored: list[tuple[float, dict[str, Any]]] = []
    for item in candidates:
        if item["status"] not in {"open", "seen"}:
            continue
        if item["target_agent_id"] not in {"", agent} and item["source_agent_id"] != agent:
            continue
        keywords = set(item.get("keywords") or [])
        overlap = len(query_keywords & keywords)
        score = overlap * 2.0
        if task_id and item.get("task_id") == task_id:
            score += 4.0
        if item["target_agent_id"] == agent:
            score += 3.0
        if item["packet_type"] in {"question", "need", "risk"}:
            score += 1.5
        score += float(item.get("confidence") or 0) + max(0, 10 - int(item.get("priority") or 5)) * 0.1
        if score > 0.2:
            scored.append((score, item))
    scored.sort(key=lambda pair: (pair[0], pair[1]["id"]), reverse=True)
    return [item for _, item in scored[:limit]]


def context_for_agent(agent_id: str, query: str, *, task_id: int | None = None, limit: int = 6) -> str:
    items = relevant_thoughts(agent_id, query, task_id=task_id, limit=limit)
    if not items:
        return ""
    lines = ["Silent thought bus context:"]
    for item in items:
        target = f" -> {item['target_agent_id']}" if item["target_agent_id"] else ""
        lines.append(
            f"- {item['packet_type']} {item['source_agent_id']}{target} "
            f"({item['confidence']:.2f}, P{item['priority']}): {item['summary']} "
            f"{_content_excerpt(item.get('content'))}"
        )
    return "\n".join(lines)


def mark_seen(packet_id: int, agent_id: str = "") -> dict[str, Any] | None:
    return update_status(packet_id, "seen", metadata_update={"seen_by": _agent_id(agent_id)} if agent_id else None)


def resolve_thought(packet_id: int, note: str = "", *, status: str = "resolved") -> dict[str, Any] | None:
    return update_status(packet_id, status, metadata_update={"resolution_note": _clean(note)} if note else None)


def update_status(packet_id: int, status: str, metadata_update: dict[str, Any] | None = None) -> dict[str, Any] | None:
    init_db()
    normalized = _normalize_status(status)
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM thought_packets WHERE id=?", (int(packet_id),)).fetchone()
        if not row:
            return None
        metadata = _json_loads(row["metadata_json"], {})
        if metadata_update:
            metadata.update({key: value for key, value in metadata_update.items() if value not in {None, ""}})
        conn.execute(
            "UPDATE thought_packets SET status=?, updated_at=?, metadata_json=? WHERE id=?",
            (normalized, now, _json_dumps(metadata), int(packet_id)),
        )
        updated = conn.execute("SELECT * FROM thought_packets WHERE id=?", (int(packet_id),)).fetchone()
    return _row_to_packet(updated)


def expire_old() -> int:
    init_db()
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            "UPDATE thought_packets SET status='expired', updated_at=? WHERE status IN ('open', 'seen') AND expires_at <= ?",
            (now, now),
        )
        return int(cursor.rowcount or 0)


def summary(limit: int = 8) -> dict[str, Any]:
    init_db()
    expire_old()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT packet_type, status, COUNT(*) FROM thought_packets GROUP BY packet_type, status").fetchall()
        agents = conn.execute("SELECT target_agent_id, COUNT(*) FROM thought_packets WHERE status IN ('open', 'seen') GROUP BY target_agent_id").fetchall()
    counts: dict[str, dict[str, int]] = {}
    for packet_type, status, count in rows:
        counts.setdefault(str(packet_type), {})[str(status)] = int(count)
    targeted = {str(target or "team"): int(count) for target, count in agents}
    recent = list_thoughts(limit=limit)
    open_count = sum(count for statuses in counts.values() for status, count in statuses.items() if status in {"open", "seen"})
    urgent = [item for item in recent if int(item.get("priority") or 5) <= 2 and item["status"] in {"open", "seen"}]
    return {
        "counts": counts,
        "open_count": open_count,
        "targeted": targeted,
        "urgent": urgent[:limit],
        "recent": recent[:limit],
    }


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM thought_packets")


def _row_to_packet(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "updated_at": str(row["updated_at"]),
        "source_agent_id": str(row["source_agent_id"]),
        "target_agent_id": str(row["target_agent_id"] or ""),
        "task_id": row["task_id"],
        "packet_type": str(row["packet_type"]),
        "summary": str(row["summary"]),
        "content": _json_loads(row["content_json"], {}),
        "confidence": float(row["confidence"]),
        "priority": int(row["priority"]),
        "status": str(row["status"]),
        "visibility": str(row["visibility"]),
        "expires_at": str(row["expires_at"]),
        "keywords": _json_loads(row["keywords_json"], []),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _payload(content: dict[str, Any] | str | None) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    if content is None:
        return {}
    return {"text": _clean(content)[:6000]}


def _content_excerpt(content: Any) -> str:
    if isinstance(content, dict):
        text = content.get("text") or content.get("summary") or content.get("question") or content.get("finding") or ""
        if not text:
            text = _json_dumps(content)
    else:
        text = str(content or "")
    cleaned = _clean(text)
    return f"- {cleaned[:220]}" if cleaned else ""


def _normalize_type(value: str) -> str:
    packet_type = _clean(value).lower().replace(" ", "_").replace("-", "_")
    return packet_type if packet_type in VALID_PACKET_TYPES else "context"


def _normalize_status(value: str) -> str:
    status = _clean(value).lower().replace(" ", "_").replace("-", "_")
    return status if status in VALID_STATUSES else "open"


def _normalize_visibility(value: str) -> str:
    visibility = _clean(value).lower().replace(" ", "_").replace("-", "_")
    return visibility if visibility in VALID_VISIBILITY else "silent"


def _priority(value: Any) -> int:
    try:
        return max(1, min(10, int(value)))
    except Exception:
        return 5


def _clamp01(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.5


def _agent_id(value: Any) -> str:
    return _clean(value).lower().replace(" ", "_").replace("-", "_")[:120]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _keywords(value: Any) -> list[str]:
    stop = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "task",
        "agent",
        "summary",
        "next",
        "step",
        "risk",
        "risks",
    }
    words = [
        word
        for word in "".join(ch.lower() if ch.isalnum() or ch == "_" else " " for ch in str(value or "")).split()
        if len(word) >= 3 and word not in stop
    ]
    seen: set[str] = set()
    result: list[str] = []
    for word in words:
        if word in seen:
            continue
        seen.add(word)
        result.append(word)
        if len(result) >= 80:
            break
    return result


def _expires_at(ttl_seconds: int | None) -> str:
    default_hours = float(config_value("agent_thought_bus_default_ttl_hours", 168))
    ttl = int(ttl_seconds if ttl_seconds is not None else default_hours * 60 * 60)
    ttl = max(60, min(90 * 24 * 60 * 60, ttl))
    return (dt.datetime.now(dt.timezone.utc).astimezone() + dt.timedelta(seconds=ttl)).isoformat(timespec="seconds")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=True)


def _json_loads(value: str, default: Any = None) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return {} if default is None else default

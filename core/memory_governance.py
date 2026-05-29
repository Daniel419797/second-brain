"""Governed long-term memory review, confidence, and contradiction handling."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import audit_log, personal_knowledge_vault
from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "memory_governance.sqlite3"
_LOCK = threading.Lock()

ALLOWED_KINDS = {
    "people",
    "lead",
    "client",
    "project",
    "deployment_step",
    "coding_style",
    "past_failure",
    "successful_workflow",
    "reusable_decision",
    "client_preference",
}


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
            CREATE TABLE IF NOT EXISTS governed_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                confidence REAL NOT NULL,
                status TEXT NOT NULL,
                review_after TEXT NOT NULL,
                vault_id INTEGER NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_governed_memory_kind ON governed_memories(kind, status, review_after)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_review_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                memory_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                priority INTEGER NOT NULL,
                status TEXT NOT NULL,
                note TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_reviews_status ON memory_review_queue(status, priority, id)")


def remember(
    kind: str,
    title: str,
    content: str,
    *,
    confidence: float = 0.75,
    review_after_days: int = 30,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    normalized = _kind(kind)
    safe_title = _clean(title)[:300]
    if not safe_title:
        raise ValueError("title is required")
    safe_content = _clean(content)[:6000]
    score = _confidence(confidence)
    contradiction = detect_contradiction(normalized, safe_title, safe_content)
    vault_kind = "person" if normalized == "people" else "project" if normalized == "project" else "preference" if normalized in {"coding_style", "client_preference"} else "fact"
    vault = personal_knowledge_vault.remember(
        vault_kind,
        safe_title,
        safe_content,
        confidence=score,
        tags=["governed_memory", normalized],
        metadata={"governed_kind": normalized, **(metadata or {})},
    )
    now = _now()
    review_after = (dt.datetime.now(dt.timezone.utc).astimezone() + dt.timedelta(days=max(1, int(review_after_days or 30)))).isoformat(timespec="seconds")
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO governed_memories(timestamp, updated_at, kind, title, content, confidence, status, review_after, vault_id, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (now, now, normalized, safe_title, safe_content, score, review_after, int(vault.get("id") or 0), _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM governed_memories WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    item = _memory_row(row)
    if score < float(config_value("memory_governance_low_confidence_threshold", 0.62)):
        queue_review(item["id"], "low_confidence", priority=2)
    if contradiction["has_contradiction"]:
        queue_review(item["id"], "possible_contradiction", priority=1)
    audit_log.record(category="memory_governance", action="remember", target=f"{normalized}:{safe_title}", success=True, details={"memory_id": item["id"], "confidence": score})
    return item | {"contradiction": contradiction, "summary": f"Saved governed {normalized} memory #{item['id']} with confidence {score:.2f}."}


def detect_contradiction(kind: str, title: str, content: str) -> dict[str, Any]:
    init_db()
    normalized = _kind(kind)
    title_key = _title_key(title)
    matches: list[dict[str, Any]] = []
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM governed_memories WHERE kind=? AND status='active' ORDER BY id DESC LIMIT 100",
            (normalized,),
        ).fetchall()
    new_content = _clean(content).lower()
    for row in rows:
        item = _memory_row(row)
        same_title = _title_key(item["title"]) == title_key
        if same_title and item["content"].strip().lower() and item["content"].strip().lower() != new_content:
            matches.append(item)
    return {
        "has_contradiction": bool(matches),
        "matches": matches[:5],
        "summary": "Possible contradiction found." if matches else "No contradiction detected.",
    }


def queue_review(memory_id: int, reason: str, *, priority: int = 3) -> dict[str, Any]:
    init_db()
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO memory_review_queue(timestamp, updated_at, memory_id, reason, priority, status, note)
            VALUES (?, ?, ?, ?, ?, 'pending', '')
            """,
            (now, now, int(memory_id), _clean(reason)[:200] or "review", max(1, min(5, int(priority or 3)))),
        )
        row = conn.execute("SELECT * FROM memory_review_queue WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _review_row(row)


def reviews(status: str = "", limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    where = ""
    params: list[Any] = []
    if status:
        where = "WHERE status=?"
        params.append(_key(status))
    params.append(_limit(limit, 200))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM memory_review_queue {where} ORDER BY priority ASC, id DESC LIMIT ?", params).fetchall()
    return [_attach_memory(_review_row(row)) for row in rows]


def resolve(review_id: int, decision: str, note: str = "") -> dict[str, Any]:
    init_db()
    action = _key(decision)
    if action not in {"approve", "archive", "reject", "keep", "stale"}:
        raise ValueError("decision must be approve, archive, reject, keep, or stale")
    status_value = "resolved"
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM memory_review_queue WHERE id=?", (int(review_id),)).fetchone()
        if not row:
            raise ValueError("review not found")
        memory_id = int(row["memory_id"] or 0)
        conn.execute("UPDATE memory_review_queue SET status=?, updated_at=?, note=? WHERE id=?", (status_value, now, _clean(note)[:1000], int(review_id)))
        if action in {"archive", "reject", "stale"}:
            conn.execute("UPDATE governed_memories SET status=?, updated_at=? WHERE id=?", (action, now, memory_id))
        else:
            conn.execute("UPDATE governed_memories SET updated_at=? WHERE id=?", (now, memory_id))
        updated = conn.execute("SELECT * FROM memory_review_queue WHERE id=?", (int(review_id),)).fetchone()
    item = _attach_memory(_review_row(updated))
    audit_log.record(category="memory_governance", action="resolve_review", target=str(review_id), success=True, details={"decision": action, "memory_id": item["memory_id"]})
    return item | {"summary": f"Memory review #{review_id} resolved as {action}."}


def status(limit: int = 12) -> dict[str, Any]:
    init_db()
    now = _now()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        counts = conn.execute("SELECT status, COUNT(*) FROM governed_memories GROUP BY status").fetchall()
        pending = int(conn.execute("SELECT COUNT(*) FROM memory_review_queue WHERE status='pending'").fetchone()[0] or 0)
        stale = int(conn.execute("SELECT COUNT(*) FROM governed_memories WHERE status='active' AND review_after<=?", (now,)).fetchone()[0] or 0)
    return {
        "enabled": bool(config_value("memory_governance_enabled", True)),
        "counts": {str(key): int(value) for key, value in counts},
        "pending_reviews": pending,
        "stale_memories": stale,
        "reviews": reviews(status="pending", limit=limit),
        "allowed_kinds": sorted(ALLOWED_KINDS),
        "summary": f"Memory governance has {pending} pending review(s) and {stale} stale active memory item(s).",
    }


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM memory_review_queue")
        conn.execute("DELETE FROM governed_memories")


def _attach_memory(review: dict[str, Any]) -> dict[str, Any]:
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM governed_memories WHERE id=?", (int(review["memory_id"]),)).fetchone()
    review["memory"] = _memory_row(row) if row else None
    return review


def _memory_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "updated_at": str(row["updated_at"]),
        "kind": str(row["kind"]),
        "title": str(row["title"]),
        "content": str(row["content"]),
        "confidence": float(row["confidence"]),
        "status": str(row["status"]),
        "review_after": str(row["review_after"]),
        "vault_id": int(row["vault_id"] or 0),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _review_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "updated_at": str(row["updated_at"]),
        "memory_id": int(row["memory_id"]),
        "reason": str(row["reason"]),
        "priority": int(row["priority"] or 3),
        "status": str(row["status"]),
        "note": str(row["note"]),
    }


def _kind(value: Any) -> str:
    key = _key(value)
    return key if key in ALLOWED_KINDS else "reusable_decision"


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")


def _title_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())[:120]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.6


def _limit(value: int, maximum: int) -> int:
    return max(1, min(maximum, int(value or 50)))


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

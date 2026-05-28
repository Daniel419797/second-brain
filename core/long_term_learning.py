"""Durable learning store for repeated Friday lessons."""

from __future__ import annotations

import datetime as dt
import hashlib
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import cognitive_state, memory, skill_library
from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "long_term_learning.sqlite3"
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
            CREATE TABLE IF NOT EXISTS learning_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_key TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL,
                topic TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                evidence_count INTEGER NOT NULL,
                confidence REAL NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_reinforced_at TEXT NOT NULL,
                next_review_at TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS learning_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                reviewed_at TEXT NOT NULL,
                result TEXT NOT NULL,
                confidence_delta REAL NOT NULL,
                FOREIGN KEY(item_id) REFERENCES learning_items(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_learning_status_review ON learning_items(status, next_review_at)")


def record_learning(kind: str, topic: str, content: str, source: str = "reflection", confidence: float = 0.5) -> int:
    init_db()
    cleaned = _clean(content)
    if not cleaned:
        raise ValueError("Learning content is empty.")
    item_key = _item_key(kind, topic, cleaned)
    now = cognitive_state.now_iso()
    next_review = _next_review(1)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        row = conn.execute("SELECT id, evidence_count, confidence FROM learning_items WHERE item_key=?", (item_key,)).fetchone()
        if row:
            item_id = int(row[0])
            evidence = int(row[1]) + 1
            updated_confidence = min(1.0, float(row[2]) + 0.08)
            conn.execute(
                """
                UPDATE learning_items
                SET evidence_count=?, confidence=?, updated_at=?, last_reinforced_at=?, next_review_at=?, status='active'
                WHERE id=?
                """,
                (evidence, updated_confidence, now, now, _next_review(evidence), item_id),
            )
        else:
            cursor = conn.execute(
                """
                INSERT INTO learning_items (
                    item_key, kind, topic, content, source, evidence_count, confidence,
                    created_at, updated_at, last_reinforced_at, next_review_at, status
                )
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, 'active')
                """,
                (
                    item_key,
                    _clean(kind) or "lesson",
                    _clean(topic) or "general",
                    cleaned,
                    _clean(source) or "reflection",
                    cognitive_state.clamp01(confidence),
                    now,
                    now,
                    now,
                    next_review,
                ),
            )
            item_id = int(cursor.lastrowid)
    try:
        maybe_propose_self_update(item_id)
    except Exception:
        pass
    return item_id


def reinforce_learning(item_id: int, evidence: str = "") -> dict[str, Any]:
    init_db()
    item = get_item(item_id)
    if not item:
        raise ValueError(f"Learning item {item_id} not found.")
    now = cognitive_state.now_iso()
    evidence_count = int(item["evidence_count"]) + 1
    confidence = min(1.0, float(item["confidence"]) + 0.08)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            "UPDATE learning_items SET evidence_count=?, confidence=?, updated_at=?, last_reinforced_at=?, next_review_at=? WHERE id=?",
            (evidence_count, confidence, now, now, _next_review(evidence_count), int(item_id)),
        )
    if evidence:
        memory.remember_fact(f"Friday learning reinforced: {item['content']} Evidence: {_clean(evidence)[:160]}", metadata={"source": "long_term_learning"})
    updated = get_item(item_id) or {}
    try:
        maybe_propose_self_update(item_id)
    except Exception:
        pass
    return updated


def due_reviews(limit: int = 10) -> list[dict[str, Any]]:
    init_db()
    now = cognitive_state.now_iso()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM learning_items
            WHERE status='active' AND next_review_at <= ?
            ORDER BY next_review_at ASC, confidence ASC
            LIMIT ?
            """,
            (now, max(1, min(100, int(limit)))),
        ).fetchall()
    return [_item_from_row(row) for row in rows]


def run_reviews(limit: int = 10) -> dict[str, Any]:
    items = due_reviews(limit=limit)
    reviewed = []
    for item in items:
        evidence = int(item["evidence_count"])
        confidence = float(item["confidence"])
        delta = 0.03 if evidence >= int(config_value("long_term_learning_min_evidence", 2)) else -0.03
        new_confidence = cognitive_state.clamp01(confidence + delta)
        status = "active" if new_confidence >= 0.15 else "archived"
        now = cognitive_state.now_iso()
        with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
            conn.execute(
                "UPDATE learning_items SET confidence=?, status=?, updated_at=?, next_review_at=? WHERE id=?",
                (new_confidence, status, now, _next_review(evidence), int(item["id"])),
            )
            conn.execute(
                "INSERT INTO learning_reviews(item_id, reviewed_at, result, confidence_delta) VALUES (?, ?, ?, ?)",
                (int(item["id"]), now, status, delta),
            )
        reviewed.append({"id": item["id"], "result": status, "confidence": new_confidence})
        if status == "active":
            try:
                proposal = maybe_propose_self_update(int(item["id"]))
                if proposal:
                    reviewed[-1]["self_update_id"] = proposal.get("id")
            except Exception:
                pass
    return {"reviewed": len(reviewed), "items": reviewed}


def recent_items(limit: int = 20, status: str = "active") -> list[dict[str, Any]]:
    init_db()
    where = ""
    params: list[Any] = []
    if status:
        where = "WHERE status=?"
        params.append(status)
    params.append(max(1, min(200, int(limit))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM learning_items {where} ORDER BY updated_at DESC, id DESC LIMIT ?",
            params,
        ).fetchall()
    return [_item_from_row(row) for row in rows]


def get_item(item_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM learning_items WHERE id=?", (int(item_id),)).fetchone()
    return _item_from_row(row) if row else None


def learning_context(topic: str = "general", limit: int = 5) -> str:
    terms = set(_words(topic))
    items = recent_items(limit=80)
    selected = []
    for item in items:
        haystack = set(_words(f"{item['topic']} {item['content']}"))
        if not terms or terms & haystack:
            selected.append(item)
        if len(selected) >= limit:
            break
    if not selected:
        return ""
    return "Long-term lessons:\n" + "\n".join(f"- {item['content']} (confidence {item['confidence']:.2f})" for item in selected)


def promote_to_skill(item_id: int) -> dict[str, Any]:
    item = get_item(item_id)
    if not item:
        raise ValueError(f"Learning item {item_id} not found.")
    skill_id = skill_library.add_skill(
        f"Learned lesson: {item['topic']}",
        f"Promoted from long-term learning item {item_id}.",
        item["content"],
        agent_id="jarvis",
        tags=[item["kind"], item["topic"]],
        source="long_term_learning",
    )
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE learning_items SET status='promoted', updated_at=? WHERE id=?", (cognitive_state.now_iso(), int(item_id)))
    return {"skill_id": skill_id, "item": get_item(item_id)}


def maybe_propose_self_update(item_id: int) -> dict[str, Any] | None:
    if not bool(config_value("long_term_learning_self_update_enabled", True)):
        return None
    item = get_item(item_id)
    if not item or item.get("status") != "active":
        return None
    if _self_update_already_proposed(int(item_id)):
        return None
    if int(item.get("evidence_count") or 0) < int(config_value("long_term_learning_self_update_min_evidence", 3)):
        return None
    if float(item.get("confidence") or 0.0) < float(config_value("long_term_learning_self_update_min_confidence", 0.72)):
        return None
    topic = str(item.get("topic") or "").lower()
    content = str(item.get("content") or "").lower()
    if not _looks_self_updatable(topic, content):
        return None
    try:
        from core import self_update

        proposal = self_update.create_proposal(
            "Long-term learning suggests a guarded code improvement. "
            f"Learning item #{item_id} ({item['topic']}): {item['content']}"
        )
    except Exception:
        return None
    _mark_self_update_proposed(int(item_id), int(proposal.get("id") or 0))
    return proposal


def auto_promote_self_updates(limit: int = 10) -> dict[str, Any]:
    proposals = []
    for item in recent_items(limit=max(1, min(100, int(limit))), status="active"):
        proposal = maybe_propose_self_update(int(item["id"]))
        if proposal:
            proposals.append(proposal)
    return {"proposed": len(proposals), "items": proposals}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM learning_reviews")
        conn.execute("DELETE FROM learning_items")


def _item_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "kind": str(row["kind"]),
        "topic": str(row["topic"]),
        "content": str(row["content"]),
        "source": str(row["source"]),
        "evidence_count": int(row["evidence_count"]),
        "confidence": float(row["confidence"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "last_reinforced_at": str(row["last_reinforced_at"]),
        "next_review_at": str(row["next_review_at"]),
        "status": str(row["status"]),
    }


def _item_key(kind: str, topic: str, content: str) -> str:
    digest = hashlib.sha256(f"{_clean(kind).lower()}:{_clean(topic).lower()}:{content.lower()}".encode("utf-8")).hexdigest()[:24]
    return f"learn_{digest}"


def _next_review(evidence_count: int) -> str:
    hours = min(24 * 14, max(1, 2 ** max(0, min(8, int(evidence_count)))))
    return (dt.datetime.now(dt.timezone.utc).astimezone() + dt.timedelta(hours=hours)).isoformat(timespec="seconds")


def _self_update_already_proposed(item_id: int) -> bool:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        row = conn.execute(
            "SELECT id FROM learning_reviews WHERE item_id=? AND result LIKE 'self_update_proposed:%' LIMIT 1",
            (int(item_id),),
        ).fetchone()
    return row is not None


def _mark_self_update_proposed(item_id: int, proposal_id: int) -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            "INSERT INTO learning_reviews(item_id, reviewed_at, result, confidence_delta) VALUES (?, ?, ?, 0.0)",
            (int(item_id), cognitive_state.now_iso(), f"self_update_proposed:{int(proposal_id)}"),
        )


def _looks_self_updatable(topic: str, content: str) -> bool:
    terms = {
        "unverified_claim",
        "tool_failure",
        "misheard_command",
        "attention",
        "volume",
        "desktop",
        "permission",
        "slow_response",
        "self_update",
        "stt",
        "voice",
        "safety",
    }
    haystack = f"{topic} {content}"
    return any(term in haystack for term in terms)


def _words(text: str) -> list[str]:
    import re

    return [part for part in re.split(r"[^a-z0-9]+", str(text).lower()) if len(part) > 2]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())

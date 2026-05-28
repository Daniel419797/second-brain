"""Rank Friday notifications by urgency, noise, and project relevance."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import notification_center, contextual_workspace
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "notification_intelligence.sqlite3"
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
            CREATE TABLE IF NOT EXISTS notification_rankings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                notification_id INTEGER NOT NULL,
                rank TEXT NOT NULL,
                reason TEXT NOT NULL,
                score REAL NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_notification_rankings_notification ON notification_rankings(notification_id, timestamp)")


def rank_pending(limit: int = 50) -> dict[str, Any]:
    init_db()
    items = notification_center.list_notifications("unread", limit=limit)
    workspace = _safe(contextual_workspace.summary, {})
    ranked = [_rank_one(item, workspace) for item in items]
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        for item in ranked:
            conn.execute(
                "INSERT INTO notification_rankings(timestamp, notification_id, rank, reason, score, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
                (_now(), int(item["notification_id"]), item["rank"], item["reason"], float(item["score"]), _json_dumps(item)),
            )
    buckets: dict[str, list[dict[str, Any]]] = {"urgent": [], "needs_action": [], "current_project": [], "can_wait": [], "noise": []}
    for item in ranked:
        buckets.setdefault(item["rank"], []).append(item)
    return {
        "ranked": ranked,
        "buckets": buckets,
        "summary": f"{len(buckets['urgent'])} urgent, {len(buckets['needs_action'])} need action, {len(buckets['noise'])} likely noise.",
    }


def recent(limit: int = 30) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM notification_rankings ORDER BY id DESC LIMIT ?", (max(1, min(200, int(limit or 30))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    ranked = rank_pending(limit=30)
    return {"latest": ranked, "recent": recent(limit=8), "summary": ranked["summary"]}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM notification_rankings")


def _rank_one(item: dict[str, Any], workspace: dict[str, Any]) -> dict[str, Any]:
    text = " ".join([str(item.get("title") or ""), str(item.get("message") or ""), str(item.get("category") or ""), str(item.get("source") or "")]).lower()
    severity = int(item.get("severity") or 1)
    score = severity * 0.2
    reasons: list[str] = [f"severity {severity}"]
    if any(term in text for term in ("approval", "blocked", "failed", "error", "crash", "secret", "security", "urgent")):
        score += 0.35
        reasons.append("action or risk keyword")
    if any(term in text for term in ("spam", "credits", "subscribe", "watching")):
        score -= 0.35
        reasons.append("noise keyword")
    project_terms = _terms(workspace.get("summary") or "") | _terms(workspace.get("root") or "")
    if project_terms and _terms(text) & project_terms:
        score += 0.25
        reasons.append("matches current project context")
    if score >= 0.75:
        rank = "urgent"
    elif "approval" in text or "blocked" in text:
        rank = "needs_action"
    elif "matches current project context" in reasons:
        rank = "current_project"
    elif score <= 0.1:
        rank = "noise"
    else:
        rank = "can_wait"
    return {
        "notification_id": int(item.get("id") or 0),
        "rank": rank,
        "score": round(max(0.0, min(1.0, score)), 3),
        "reason": "; ".join(reasons),
        "notification": item,
    }


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "notification_id": int(row["notification_id"]),
        "rank": str(row["rank"]),
        "reason": str(row["reason"]),
        "score": float(row["score"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _terms(text: str) -> set[str]:
    return {part for part in re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).split() if len(part) > 2}


def _safe(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

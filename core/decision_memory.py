"""Decision preferences: how the user tends to choose under tradeoffs."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import personal_knowledge_vault
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "decision_memory.sqlite3"
_LOCK = threading.Lock()

CATEGORIES = {
    "speed_vs_quality",
    "cost",
    "permission",
    "approval",
    "coding_style",
    "design_taste",
    "good_enough",
    "risk",
    "communication",
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
            CREATE TABLE IF NOT EXISTS decision_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                category TEXT NOT NULL,
                preference TEXT NOT NULL,
                threshold TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL,
                evidence_json TEXT NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        _ensure_column(conn, "decision_preferences", "threshold", "TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_decision_category ON decision_preferences(category, status, confidence)")


def remember(category: str, preference: str, *, threshold: str = "", evidence: list[str] | str | None = None, confidence: float = 0.75, source: str = "user", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    normalized = _category(category)
    clean_preference = _clean(preference)
    if not clean_preference:
        raise ValueError("preference is required")
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO decision_preferences(created_at, updated_at, category, preference, threshold, confidence, evidence_json, source, status, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
            """,
            (now, now, normalized, clean_preference[:1000], _clean(threshold)[:500], _confidence(confidence), _json_dumps(_list(evidence)), _clean(source)[:120] or "user", _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM decision_preferences WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    item = _row(row)
    _safe(lambda: personal_knowledge_vault.remember("preference", f"Decision: {item['category']}", item["preference"], confidence=item["confidence"], tags=["decision_memory", item["category"]], metadata={"source": item["source"], "evidence": item["evidence"]}), None)
    return item


def learn_from_text(text: str, *, source: str = "user") -> dict[str, Any]:
    cleaned = _clean(text)
    learned: list[dict[str, Any]] = []
    lower = cleaned.lower()
    if any(term in lower for term in ("free", "broke", "can't afford", "cannot afford", "cheap")):
        learned.append(remember("cost", "Prefer free or cheapest reliable tools before paid services.", threshold="Pay only after free/local options fail or the user approves cost.", evidence=cleaned, confidence=0.9, source=source))
    if any(term in lower for term in ("ask first", "ask me", "approval", "before deleting", "before sending")):
        learned.append(remember("permission", "Ask before sensitive, destructive, private-data, deploy, or outbound-message actions.", threshold="Ask first whenever action changes external state or uses private data.", evidence=cleaned, confidence=0.88, source=source))
    if any(term in lower for term in ("fast", "quick", "speed", "latency", "speed over perfection")):
        learned.append(remember("speed_vs_quality", "Prefer fast, responsive behavior for live voice and simple commands.", threshold="Use simpler local/direct paths when the request is low-risk.", evidence=cleaned, confidence=0.72, source=source))
    if any(term in lower for term in ("design taste", "ui taste", "clean ui", "dashboard", "stitch", "polished ui")):
        learned.append(remember("design_taste", "Prefer polished, practical interfaces that feel like a real command center instead of a rough demo.", threshold="Use compact, clear, responsive UI and avoid fake/overdecorated panels.", evidence=cleaned, confidence=0.72, source=source))
    if any(term in lower for term in ("security", "maintainability", "readability", "performance", "scalability")):
        learned.append(remember("coding_style", "For programming, prioritize security, performance, maintainability, reliability, readability, and scalability.", threshold="Do not mark programming work done without tests or clear proof gaps.", evidence=cleaned, confidence=0.86, source=source))
    if any(term in lower for term in ("good enough", "ship", "mvp", "don't overdo")):
        learned.append(remember("good_enough", "Prefer a working, verified MVP over endless polishing when scope is large.", threshold="Stop polishing after success criteria and verification are met.", evidence=cleaned, confidence=0.68, source=source))
    if not learned and cleaned:
        learned.append(remember("communication", cleaned, evidence=cleaned, confidence=0.55, source=source))
    return {"learned": learned, "summary": f"Learned {len(learned)} decision preference(s)."}


def choose(question: str = "", *, category: str = "", context: str = "") -> dict[str, Any]:
    candidates = search(question or context, category=category, limit=8)
    if not candidates and category:
        candidates = search("", category=category, limit=8)
    if not candidates:
        return {"preference": None, "confidence": 0.0, "evidence": [], "summary": "No decision preference is known yet. Ask first for anything risky."}
    best = candidates[0]
    return {
        "preference": best,
        "confidence": best["confidence"],
        "evidence": best["evidence"],
        "summary": f"Use preference '{best['preference']}' with {int(best['confidence'] * 100)}% confidence.",
    }


def search(query: str = "", *, category: str = "", limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    where = ["status='active'"]
    params: list[Any] = []
    if category:
        where.append("category=?")
        params.append(_category(category))
    terms = [term for term in re.split(r"\s+", _clean(query).lower()) if term][:8]
    for term in terms:
        needle = f"%{term}%"
        where.append("(lower(preference) LIKE ? OR lower(evidence_json) LIKE ? OR lower(category) LIKE ?)")
        params.extend([needle, needle, needle])
    params.append(max(1, min(100, int(limit or 20))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM decision_preferences WHERE {' AND '.join(where)} ORDER BY confidence DESC, updated_at DESC LIMIT ?", params).fetchall()
    return [_row(row) for row in rows]


def review_candidates(limit: int = 8) -> dict[str, Any]:
    items = [item for item in search("", limit=100) if item["confidence"] < 0.72][:limit]
    return {"items": items, "summary": f"{len(items)} decision preference(s) could use confirmation."}


def status(limit: int = 10) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT category, COUNT(*) FROM decision_preferences WHERE status='active' GROUP BY category").fetchall()
    counts = {str(category): int(count) for category, count in rows}
    recent = search("", limit=limit)
    return {"counts": counts, "recent": recent, "review": review_candidates(limit=5), "summary": f"{sum(counts.values())} active decision preference(s)."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM decision_preferences")


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "category": str(row["category"]),
        "preference": str(row["preference"]),
        "threshold": str(row["threshold"]) if "threshold" in row.keys() else "",
        "confidence": float(row["confidence"]),
        "evidence": _json_loads(row["evidence_json"], []),
        "source": str(row["source"]),
        "status": str(row["status"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _category(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return normalized if normalized in CATEGORIES else "communication"


def _confidence(value: Any) -> float:
    try:
        return max(0.05, min(1.0, float(value)))
    except Exception:
        return 0.75


def _list(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    return [_clean(item) for item in value if _clean(item)]


def _safe(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, spec: str) -> None:
    columns = [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {spec}")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

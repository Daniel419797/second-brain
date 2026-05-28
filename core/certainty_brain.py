"""Friday's ledger of known facts, guesses, stale memories, and gaps."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import notification_center
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "certainty_brain.sqlite3"
_LOCK = threading.Lock()
KINDS = {"known", "guess", "missing", "stale", "needs_confirmation"}


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
            CREATE TABLE IF NOT EXISTS certainty_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                topic TEXT NOT NULL,
                statement TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence_json TEXT NOT NULL,
                source TEXT NOT NULL,
                stale_after TEXT NOT NULL,
                status TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_certainty_kind ON certainty_items(kind, status, updated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_certainty_topic ON certainty_items(topic, status)")


def record(
    kind: str,
    topic: str,
    statement: str,
    *,
    confidence: float = 0.6,
    evidence: list[Any] | str | None = None,
    source: str = "friday",
    stale_after: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    normalized = _kind(kind)
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO certainty_items(created_at, updated_at, kind, topic, statement, confidence, evidence_json, source, stale_after, status, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
            """,
            (
                now,
                now,
                normalized,
                _norm_topic(topic),
                _clean(statement)[:2000] or "Unspecified uncertainty.",
                _confidence(confidence),
                _json_dumps(_list(evidence)),
                _clean(source)[:120] or "friday",
                _clean(stale_after),
                _json_dumps(metadata or {}),
            ),
        )
        row = conn.execute("SELECT * FROM certainty_items WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    item = _row(row)
    if normalized in {"missing", "needs_confirmation", "stale"}:
        _notify(item)
    return item


def record_known(topic: str, statement: str, *, evidence: list[Any] | str | None = None, confidence: float = 0.9, source: str = "tool") -> dict[str, Any]:
    return record("known", topic, statement, confidence=confidence, evidence=evidence, source=source)


def record_guess(topic: str, statement: str, *, evidence: list[Any] | str | None = None, confidence: float = 0.45, source: str = "inference") -> dict[str, Any]:
    return record("guess", topic, statement, confidence=confidence, evidence=evidence, source=source)


def record_missing(topic: str, statement: str, *, source: str = "friday") -> dict[str, Any]:
    return record("missing", topic, statement, confidence=0.15, source=source)


def mark_status(item_id: int, status: str = "resolved") -> dict[str, Any]:
    init_db()
    normalized = _clean(status).lower() or "resolved"
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE certainty_items SET status=?, updated_at=? WHERE id=?", (normalized, _now(), int(item_id)))
        row = conn.execute("SELECT * FROM certainty_items WHERE id=?", (int(item_id),)).fetchone()
    return _row(row) if row else {}


def search(query: str = "", *, kind: str = "", limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    where: list[str] = ["status='open'"]
    params: list[Any] = []
    if kind:
        where.append("kind=?")
        params.append(_kind(kind))
    if query:
        like = f"%{_clean(query)}%"
        where.append("(topic LIKE ? OR statement LIKE ? OR source LIKE ?)")
        params.extend([like, like, like])
    params.append(max(1, min(200, int(limit or 20))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM certainty_items WHERE {' AND '.join(where)} ORDER BY confidence ASC, id DESC LIMIT ?", params).fetchall()
    return [_row(row) for row in rows]


def summary(limit: int = 10) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT kind, COUNT(*) FROM certainty_items WHERE status='open' GROUP BY kind").fetchall()
    counts = {str(kind): int(count) for kind, count in rows}
    gaps = search(kind="missing", limit=limit)
    guesses = search(kind="guess", limit=limit)
    stale = search(kind="stale", limit=limit)
    return {
        "counts": counts,
        "gaps": gaps,
        "guesses": guesses,
        "stale": stale,
        "summary": f"{sum(counts.values())} open certainty item(s): {counts.get('missing', 0)} missing, {counts.get('guess', 0)} guesses, {counts.get('stale', 0)} stale.",
    }


def answer(question: str = "what do you know and not know") -> dict[str, Any]:
    state = summary(limit=5)
    known = search(question, kind="known", limit=5)
    lines = [state["summary"]]
    if known:
        lines.append("Known: " + "; ".join(item["statement"] for item in known[:3]))
    if state["guesses"]:
        lines.append("Guesses: " + "; ".join(item["statement"] for item in state["guesses"][:3]))
    if state["gaps"]:
        lines.append("Missing evidence: " + "; ".join(item["statement"] for item in state["gaps"][:3]))
    return {"question": question, "answer": "\n".join(lines), "state": state}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM certainty_items")


def _notify(item: dict[str, Any]) -> None:
    try:
        notification_center.add(
            source="certainty_brain",
            category="memory_review",
            severity=2 if item["kind"] == "guess" else 3,
            title="Friday needs confirmation",
            message=item["statement"],
            dedupe_key=f"certainty:{item['kind']}:{item['topic']}:{item['statement'][:80]}",
            metadata={"item_id": item["id"]},
        )
    except Exception:
        pass


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "kind": str(row["kind"]),
        "topic": str(row["topic"]),
        "statement": str(row["statement"]),
        "confidence": float(row["confidence"]),
        "evidence": _json_loads(row["evidence_json"], []),
        "source": str(row["source"]),
        "stale_after": str(row["stale_after"]),
        "status": str(row["status"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _kind(value: str) -> str:
    normalized = _clean(value).lower().replace(" ", "_")
    return normalized if normalized in KINDS else "needs_confirmation"


def _norm_topic(value: str) -> str:
    return re.sub(r"[^a-z0-9_.-]+", "_", _clean(value).lower()).strip("_") or "general"


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.5


def _list(value: list[Any] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    return [_clean(value)] if _clean(value) else []


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

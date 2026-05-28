"""App-specific interaction memory for reliable human-like control."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "app_state_memory.sqlite3"
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
            CREATE TABLE IF NOT EXISTS app_state_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                app TEXT NOT NULL,
                context TEXT NOT NULL,
                element_label TEXT NOT NULL,
                selector TEXT NOT NULL,
                action TEXT NOT NULL,
                outcome TEXT NOT NULL,
                confidence REAL NOT NULL,
                notes TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_app_state_app ON app_state_patterns(app, outcome, timestamp)")


def record_pattern(
    app: str,
    element_label: str,
    action: str,
    outcome: str,
    *,
    selector: str = "",
    context: str = "",
    confidence: float = 0.7,
    notes: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO app_state_patterns(timestamp, app, context, element_label, selector, action, outcome, confidence, notes, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _now(),
                _norm(app),
                _clean(context)[:1000],
                _clean(element_label)[:300],
                _clean(selector)[:500],
                _clean(action).lower()[:120],
                _clean(outcome).lower()[:120],
                _confidence(confidence),
                _clean(notes)[:2000],
                _json_dumps(metadata or {}),
            ),
        )
        row = conn.execute("SELECT * FROM app_state_patterns WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def remember_success(app: str, element_label: str, action: str, *, selector: str = "", context: str = "", notes: str = "") -> dict[str, Any]:
    return record_pattern(app, element_label, action, "success", selector=selector, context=context, confidence=0.85, notes=notes)


def remember_failure(app: str, element_label: str, action: str, *, selector: str = "", context: str = "", notes: str = "") -> dict[str, Any]:
    return record_pattern(app, element_label, action, "failure", selector=selector, context=context, confidence=0.55, notes=notes)


def search_patterns(app: str = "", query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    where: list[str] = []
    params: list[Any] = []
    if app:
        where.append("app=?")
        params.append(_norm(app))
    if query:
        like = f"%{_clean(query)}%"
        where.append("(element_label LIKE ? OR selector LIKE ? OR action LIKE ? OR notes LIKE ? OR context LIKE ?)")
        params.extend([like, like, like, like, like])
    params.append(max(1, min(200, int(limit or 20))))
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM app_state_patterns {clause} ORDER BY confidence DESC, id DESC LIMIT ?", params).fetchall()
    return [_row(row) for row in rows]


def summary(limit: int = 8) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT app, COUNT(*) FROM app_state_patterns GROUP BY app ORDER BY COUNT(*) DESC").fetchall()
    by_app = {str(app): int(count) for app, count in rows}
    recent = search_patterns(limit=limit)
    return {"by_app": by_app, "recent": recent, "summary": f"{sum(by_app.values())} app memory pattern(s) stored."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM app_state_patterns")


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "app": str(row["app"]),
        "context": str(row["context"]),
        "element_label": str(row["element_label"]),
        "selector": str(row["selector"]),
        "action": str(row["action"]),
        "outcome": str(row["outcome"]),
        "confidence": float(row["confidence"]),
        "notes": str(row["notes"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", _clean(value).lower()).strip("_") or "unknown_app"


def _confidence(value: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.5


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=True)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return default

"""SQLite-backed episodic memory for timestamped Friday actions."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "episodic_store.sqlite3"
_LOCK = threading.Lock()


def init_db(path: Path | None = None) -> None:
    ensure_runtime_dirs()
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS episodic_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                task_id TEXT,
                action_type TEXT NOT NULL,
                inputs_json TEXT NOT NULL,
                outputs_json TEXT NOT NULL,
                success_score REAL NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_episodic_agent_time ON episodic_events(agent_id, timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_episodic_action ON episodic_events(action_type)")


def insert_event(
    *,
    agent_id: str = "jarvis",
    task_id: str = "",
    action_type: str = "command",
    inputs: Any = None,
    outputs: Any = None,
    success_score: float = 1.0,
    metadata: dict[str, Any] | None = None,
    timestamp: dt.datetime | None = None,
) -> int:
    init_db()
    stamp = (timestamp or _now()).isoformat(timespec="seconds")
    with _LOCK, sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO episodic_events (
                timestamp, agent_id, task_id, action_type, inputs_json,
                outputs_json, success_score, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stamp,
                agent_id,
                task_id,
                action_type,
                _json_dumps(inputs),
                _json_dumps(outputs),
                float(max(0.0, min(1.0, success_score))),
                _json_dumps(metadata or {}),
            ),
        )
        return int(cursor.lastrowid)


def query_events(
    *,
    agent_id: str | None = None,
    action_type: str | None = None,
    date_from: dt.datetime | None = None,
    date_to: dt.datetime | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    init_db()
    where: list[str] = []
    params: list[Any] = []
    if agent_id:
        where.append("agent_id = ?")
        params.append(agent_id)
    if action_type:
        where.append("action_type = ?")
        params.append(action_type)
    if date_from:
        where.append("timestamp >= ?")
        params.append(date_from.isoformat(timespec="seconds"))
    if date_to:
        where.append("timestamp <= ?")
        params.append(date_to.isoformat(timespec="seconds"))
    sql = "SELECT * FROM episodic_events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY timestamp DESC, id DESC LIMIT ?"
    params.append(max(1, int(limit)))
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return [_row_to_event(row) for row in conn.execute(sql, params)]


def today_events(agent_id: str | None = None, limit: int = 1000) -> list[dict[str, Any]]:
    now = _now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + dt.timedelta(days=1)
    return query_events(agent_id=agent_id, date_from=start, date_to=end, limit=limit)


def summarize_recent(agent_id: str = "jarvis", limit: int = 5) -> str:
    events = query_events(agent_id=agent_id, limit=limit)
    lines: list[str] = []
    for event in reversed(events):
        action = event["action_type"]
        inputs = _compact(event.get("inputs"))
        outputs = _compact(event.get("outputs"))
        lines.append(f"{event['timestamp']} | {action} | input={inputs} | output={outputs}")
    return "\n".join(lines)


def count_events() -> int:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM episodic_events").fetchone()[0])


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM episodic_events")


def _row_to_event(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "agent_id": str(row["agent_id"]),
        "task_id": str(row["task_id"] or ""),
        "action_type": str(row["action_type"]),
        "inputs": _json_loads(row["inputs_json"]),
        "outputs": _json_loads(row["outputs_json"]),
        "success_score": float(row["success_score"]),
        "metadata": _json_loads(row["metadata_json"]),
    }


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=True)


def _json_loads(value: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return value


def _compact(value: Any, limit: int = 140) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=True, default=str)
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).astimezone()

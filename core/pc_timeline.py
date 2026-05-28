"""Screen/PC awareness timeline: what changed, what Friday did, what failed."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import audit_log, pc_awareness
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "pc_timeline.sqlite3"
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
            CREATE TABLE IF NOT EXISTS pc_timeline_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                source TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pc_timeline_time ON pc_timeline_events(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pc_timeline_type ON pc_timeline_events(event_type, timestamp)")


def record_event(event_type: str, title: str, summary: str = "", *, source: str = "friday", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO pc_timeline_events(timestamp, event_type, title, summary, source, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
            (_now(), _clean(event_type) or "event", _clean(title)[:300], _clean(summary)[:1000], _clean(source) or "friday", _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM pc_timeline_events WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def capture_snapshot() -> dict[str, Any]:
    current = pc_awareness.refresh()
    latest = latest_event("pc_snapshot")
    previous = (latest or {}).get("metadata", {}).get("snapshot", {}) if latest else {}
    events = []
    active = current.get("active_window") or ""
    previous_active = previous.get("active_window") or ""
    if active and active != previous_active:
        events.append(record_event("active_window_changed", "Active window changed", active, source="pc_awareness", metadata={"previous": previous_active, "current": active}))
    current_apps = {str(item.get("name") or "") for item in current.get("running_apps") or [] if item.get("name")}
    previous_apps = {str(item.get("name") or "") for item in previous.get("running_apps") or [] if item.get("name")}
    new_apps = sorted(current_apps - previous_apps)[:20]
    if new_apps:
        events.append(record_event("apps_opened", "New running app entries", ", ".join(new_apps), source="pc_awareness", metadata={"apps": new_apps}))
    snapshot_event = record_event("pc_snapshot", "PC snapshot captured", current.get("summary", ""), source="pc_awareness", metadata={"snapshot": current})
    return {"snapshot": current, "events": events, "snapshot_event": snapshot_event, "summary": f"Captured PC timeline snapshot with {len(events)} change event(s)."}


def sync_audit_events(limit: int = 50) -> dict[str, Any]:
    synced = 0
    for event in reversed(audit_log.recent(limit=limit)):
        key = f"audit:{event.get('id')}"
        if _exists_key(key):
            continue
        record_event(
            "friday_action" if event.get("success") else "friday_failure",
            str(event.get("action") or "Action"),
            str(event.get("target") or event.get("category") or ""),
            source="audit_log",
            metadata={"audit": event, "dedupe_key": key},
        )
        synced += 1
    return {"synced": synced, "summary": f"Synced {synced} audit event(s) into the PC timeline."}


def recent_events(limit: int = 50, event_type: str = "") -> list[dict[str, Any]]:
    init_db()
    where = ""
    params: list[Any] = []
    if event_type:
        where = "WHERE event_type=?"
        params.append(_clean(event_type))
    params.append(max(1, min(500, int(limit or 50))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM pc_timeline_events {where} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_row(row) for row in rows]


def latest_event(event_type: str = "") -> dict[str, Any] | None:
    events = recent_events(limit=1, event_type=event_type)
    return events[0] if events else None


def summary(limit: int = 12) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT event_type, COUNT(*) FROM pc_timeline_events GROUP BY event_type").fetchall()
    counts = {str(kind): int(count) for kind, count in rows}
    return {"counts": counts, "recent": recent_events(limit=limit), "summary": f"{sum(counts.values())} PC timeline event(s) recorded."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM pc_timeline_events")


def _exists_key(key: str) -> bool:
    init_db()
    needle = f'%"dedupe_key": "{key}"%'
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        row = conn.execute("SELECT 1 FROM pc_timeline_events WHERE metadata_json LIKE ? LIMIT 1", (needle,)).fetchone()
    return bool(row)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "event_type": str(row["event_type"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "source": str(row["source"]),
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


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

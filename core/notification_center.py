"""Unified notification center for Friday's important signals."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "notification_center.sqlite3"
VALID_STATUSES = {"unread", "read", "dismissed", "archived"}
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
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source TEXT NOT NULL,
                category TEXT NOT NULL,
                severity INTEGER NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL,
                dedupe_key TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status, severity, updated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_dedupe ON notifications(dedupe_key, status)")


def add(
    *,
    source: str,
    category: str,
    title: str,
    message: str,
    severity: int = 2,
    dedupe_key: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add an alert, deduping unresolved copies within a configurable cooldown."""

    init_db()
    key = _clean(dedupe_key) or f"{_clean(source)}:{_clean(category)}:{_clean(title).lower()}"
    now = _now()
    cooldown_minutes = float(config_value("notification_dedupe_cooldown_minutes", 60))
    cutoff = _iso(_aware_now() - dt.timedelta(minutes=max(0.0, cooldown_minutes)))
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            """
            SELECT * FROM notifications
            WHERE dedupe_key=? AND status='unread' AND updated_at >= ?
            ORDER BY id DESC LIMIT 1
            """,
            (key, cutoff),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE notifications
                SET updated_at=?, severity=max(severity, ?), message=?, metadata_json=?
                WHERE id=?
                """,
                (now, _severity(severity), _clean(message)[:2000], _json_dumps(metadata or {}), int(existing["id"])),
            )
            row = conn.execute("SELECT * FROM notifications WHERE id=?", (int(existing["id"]),)).fetchone()
            return _row(row) | {"deduped": True}
        cursor = conn.execute(
            """
            INSERT INTO notifications(timestamp, updated_at, source, category, severity, title, message, status, dedupe_key, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'unread', ?, ?)
            """,
            (
                now,
                now,
                _clean(source) or "friday",
                _clean(category) or "general",
                _severity(severity),
                _clean(title)[:300] or "Friday notice",
                _clean(message)[:2000],
                key,
                _json_dumps(metadata or {}),
            ),
        )
        row = conn.execute("SELECT * FROM notifications WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row) | {"deduped": False}


def list_notifications(status: str = "", *, min_severity: int = 0, limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    where: list[str] = []
    params: list[Any] = []
    normalized_status = _normalize_status(status, allow_empty=True)
    if normalized_status:
        where.append("status=?")
        params.append(normalized_status)
    if int(min_severity or 0) > 0:
        where.append("severity>=?")
        params.append(_severity(min_severity))
    params.append(max(1, min(500, int(limit or 50))))
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM notifications {clause} ORDER BY status='unread' DESC, severity DESC, updated_at DESC, id DESC LIMIT ?", params).fetchall()
    return [_row(row) for row in rows]


def mark(notification_id: int, status: str = "read") -> dict[str, Any]:
    init_db()
    normalized = _normalize_status(status)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE notifications SET status=?, updated_at=? WHERE id=?", (normalized, _now(), int(notification_id)))
        row = conn.execute("SELECT * FROM notifications WHERE id=?", (int(notification_id),)).fetchone()
    return _row(row) if row else {}


def mark_all_read() -> dict[str, int]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute("UPDATE notifications SET status='read', updated_at=? WHERE status='unread'", (_now(),))
    return {"updated": int(cursor.rowcount or 0)}


def summary(limit: int = 12) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT status, COUNT(*) FROM notifications GROUP BY status").fetchall()
        severity_rows = conn.execute("SELECT severity, COUNT(*) FROM notifications WHERE status='unread' GROUP BY severity").fetchall()
    by_status = {str(status): int(count) for status, count in rows}
    by_severity = {str(severity): int(count) for severity, count in severity_rows}
    unread = list_notifications("unread", limit=limit)
    return {
        "count": sum(by_status.values()),
        "unread_count": by_status.get("unread", 0),
        "by_status": by_status,
        "unread_by_severity": by_severity,
        "items": unread,
        "voice_summary": voice_summary(unread),
    }


def voice_summary(items: list[dict[str, Any]] | None = None) -> str:
    pending = items if items is not None else list_notifications("unread", limit=20)
    important = [item for item in pending if int(item.get("severity") or 0) >= int(config_value("notification_voice_min_severity", 3))]
    if not important:
        return "No important notifications are waiting."
    top = important[0]
    extra = len(important) - 1
    suffix = f" and {extra} more" if extra else ""
    return f"{top['title']}{suffix}."


def pending_for_speech(limit: int = 3) -> list[dict[str, Any]]:
    min_severity = int(config_value("notification_voice_min_severity", 3))
    return list_notifications("unread", min_severity=min_severity, limit=limit)


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM notifications")


def _row(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "updated_at": str(row["updated_at"]),
        "source": str(row["source"]),
        "category": str(row["category"]),
        "severity": int(row["severity"]),
        "title": str(row["title"]),
        "message": str(row["message"]),
        "status": str(row["status"]),
        "dedupe_key": str(row["dedupe_key"]),
        "metadata": _json_loads(row["metadata_json"]),
    }


def _normalize_status(value: str, *, allow_empty: bool = False) -> str:
    status = _clean(value).lower()
    if allow_empty and not status:
        return ""
    return status if status in VALID_STATUSES else "unread"


def _severity(value: int | float | str) -> int:
    try:
        raw = int(float(value))
    except Exception:
        raw = 2
    return max(1, min(5, raw))


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


def _aware_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).astimezone()


def _iso(value: dt.datetime) -> str:
    return value.astimezone().isoformat(timespec="seconds")


def _now() -> str:
    return _iso(_aware_now())

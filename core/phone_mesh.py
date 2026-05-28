"""Phone-to-PC mesh handoff queue for the Android companion."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import android_companion, notification_center
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "phone_mesh.sqlite3"
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
            CREATE TABLE IF NOT EXISTS phone_handoffs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                device_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                result TEXT NOT NULL
            )
            """
        )


def create_handoff(device_id: str, title: str, payload: dict[str, Any] | None = None, *, direction: str = "phone_to_pc", kind: str = "command") -> dict[str, Any]:
    init_db()
    now = _now()
    safe_payload = _safe_payload(payload or {})
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO phone_handoffs(created_at, updated_at, device_id, direction, kind, title, payload_json, status, result)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', '')
            """,
            (now, now, _clean(device_id) or "android", _direction(direction), _clean(kind) or "command", _clean(title)[:300], _json_dumps(safe_payload)),
        )
        row = conn.execute("SELECT * FROM phone_handoffs WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    notification_center.add(source="phone_mesh", category="phone_handoff", severity=2, title="Phone handoff received", message=_clean(title), metadata={"handoff_id": int(row["id"])})
    return _row(row)


def pending(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM phone_handoffs WHERE status='pending' ORDER BY id ASC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def complete(handoff_id: int, *, status: str = "done", result: str = "") -> dict[str, Any]:
    init_db()
    normalized = status if status in {"done", "failed", "cancelled"} else "done"
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE phone_handoffs SET status=?, result=?, updated_at=? WHERE id=?", (normalized, _clean(result)[:1000], _now(), int(handoff_id)))
        row = conn.execute("SELECT * FROM phone_handoffs WHERE id=?", (int(handoff_id),)).fetchone()
    return _row(row) if row else {"ok": False, "summary": "Phone handoff not found."}


def send_to_phone(title: str, payload: dict[str, Any] | None = None, *, device_id: str = "") -> dict[str, Any]:
    item = create_handoff(device_id or "default", title, payload or {}, direction="pc_to_phone", kind="notification")
    try:
        ring = android_companion.ring(_clean(title))
    except Exception:
        ring = {"summary": "Phone notification bridge unavailable."}
    item["bridge"] = ring
    return item


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM phone_handoffs ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    app = android_companion.status()
    waiting = pending(limit=10)
    return {"devices": app.get("app_devices") or [], "pending": waiting, "recent": recent(limit=8), "summary": f"{len(waiting)} phone handoff(s) waiting."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM phone_handoffs")


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "device_id": str(row["device_id"]),
        "direction": str(row["direction"]),
        "kind": str(row["kind"]),
        "title": str(row["title"]),
        "payload": _json_loads(row["payload_json"], {}),
        "status": str(row["status"]),
        "result": str(row["result"]),
        "summary": f"{row['direction']} {row['kind']}: {row['title']} ({row['status']})",
    }


def _direction(value: str) -> str:
    return "pc_to_phone" if str(value).strip().lower() == "pc_to_phone" else "phone_to_pc"


def _safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in (payload or {}).items():
        name = _clean(key)
        if any(term in name.lower() for term in ("password", "token", "secret", "credential", "authorization")):
            safe[name] = "[redacted]"
        elif isinstance(value, str):
            safe[name] = "[redacted-sensitive]" if any(term in value.lower() for term in ("password", "token", "secret", "authorization")) else value[:3000]
        elif isinstance(value, (int, float, bool)) or value is None:
            safe[name] = value
        else:
            safe[name] = _clean(value)[:1000]
    return safe


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

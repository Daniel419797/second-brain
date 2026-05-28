"""Command handoff mesh across laptop, Android companion, and browser extension."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import android_companion, browser_extension_bridge, phone_mesh
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "device_command_mesh.sqlite3"
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
            CREATE TABLE IF NOT EXISTS mesh_commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source_device TEXT NOT NULL,
                target_device TEXT NOT NULL,
                command_type TEXT NOT NULL,
                title TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT NOT NULL
            )
            """
        )


def create_command(
    command_type: str,
    title: str,
    *,
    source_device: str = "laptop",
    target_device: str = "laptop",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO mesh_commands(timestamp, updated_at, source_device, target_device, command_type, title, payload_json, status, result_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', '{}')
            """,
            (_now(), _now(), _clean(source_device) or "laptop", _clean(target_device) or "laptop", _clean(command_type) or "handoff", _clean(title)[:300] or "Device handoff", _json_dumps(payload or {})),
        )
        row = conn.execute("SELECT * FROM mesh_commands WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    item = _row(row)
    _forward(item)
    return get(item["id"]) or item


def continue_on_laptop(title: str, payload: dict[str, Any] | None = None, *, source_device: str = "android") -> dict[str, Any]:
    return create_command("continue_on_laptop", title, source_device=source_device, target_device="laptop", payload=payload or {})


def send_browser_page_to_friday(note: str = "") -> dict[str, Any]:
    insight = _safe(browser_extension_bridge.latest_page_insight, {})
    return create_command("browser_page", insight.get("title") or insight.get("url") or "Browser page", source_device="browser_extension", target_device="friday", payload={"note": note, "page": insight})


def phone_camera_to_friday(device_id: str = "", note: str = "") -> dict[str, Any]:
    status = _safe(android_companion.status, {})
    files = status.get("recent_files") or []
    latest = next((item for item in files if item.get("kind") == "camera"), files[0] if files else {})
    return create_command("phone_camera", note or "Phone camera snapshot", source_device=device_id or "android", target_device="friday", payload={"latest": latest})


def complete(command_id: int, result: dict[str, Any] | str | None = None) -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE mesh_commands SET status='done', updated_at=?, result_json=? WHERE id=?", (_now(), _json_dumps(result or {}), int(command_id)))
        row = conn.execute("SELECT * FROM mesh_commands WHERE id=?", (int(command_id),)).fetchone()
    return _row(row) if row else {}


def get(command_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM mesh_commands WHERE id=?", (int(command_id),)).fetchone()
    return _row(row) if row else None


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM mesh_commands ORDER BY id DESC LIMIT ?", (max(1, min(200, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    commands = recent(limit=12)
    phone = _safe(phone_mesh.status, {})
    android = _safe(android_companion.status, {})
    browser = _safe(lambda: browser_extension_bridge.status(limit=3), {})
    pending = [item for item in commands if item["status"] == "pending"]
    return {"commands": commands, "pending": pending, "phone_mesh": phone, "android": android, "browser": browser, "summary": f"{len(pending)} pending device mesh command(s)."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM mesh_commands")


def _forward(item: dict[str, Any]) -> None:
    try:
        if item["target_device"] == "android":
            phone_mesh.create_handoff("android", item["title"], item["payload"])
        elif item["target_device"] in {"laptop", "friday"}:
            phone_mesh.create_handoff(item["source_device"], item["title"], item["payload"])
    except Exception:
        pass


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "updated_at": str(row["updated_at"]),
        "source_device": str(row["source_device"]),
        "target_device": str(row["target_device"]),
        "command_type": str(row["command_type"]),
        "title": str(row["title"]),
        "payload": _json_loads(row["payload_json"], {}),
        "status": str(row["status"]),
        "result": _json_loads(row["result_json"], {}),
        "summary": f"{row['source_device']} -> {row['target_device']}: {row['title']}",
    }


def _safe(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


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

"""Android companion layer on top of the free-first phone bridge."""

from __future__ import annotations

import datetime as dt
import json
import base64
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import notification_center, phone_bridge
from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "android_companion.sqlite3"
FILE_DIR = DATA_DIR / "android_companion_files"
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
            CREATE TABLE IF NOT EXISTS android_companion_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                summary TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS android_app_devices (
                device_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                registered_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                capabilities_json TEXT NOT NULL,
                status_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS android_app_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                device_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                name TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def status() -> dict[str, Any]:
    bridge = phone_bridge.status()
    return {
        "enabled": bool(config_value("android_companion_enabled", True)),
        "bridge": bridge,
        "capabilities": [
            "native_android_app",
            "microphone_voice_to_friday",
            "notification_sync",
            "camera_frame_metadata",
            "clipboard_sync",
            "file_transfer_metadata",
            "location_if_allowed",
            "call_or_ring_phone",
            "sms_drafts",
            "photo_import",
            "phone_voice_to_friday_endpoint",
        ],
        "app_devices": list_app_devices(limit=8),
        "recent_events": recent_events(limit=8),
        "recent_files": recent_files(limit=8),
        "summary": bridge.get("setup_hint", "Android companion status unavailable."),
    }


def sync_notifications() -> dict[str, Any]:
    bridge = phone_bridge.status()
    if not bridge.get("adb_connected"):
        payload = {"ok": False, "summary": "Notification sync needs an ADB-connected Android phone.", "bridge": bridge}
        _record("sync_notifications", payload["summary"], payload)
        return payload
    payload = {
        "ok": True,
        "summary": "Android notification sync is ready for a companion app; ADB notification scraping is device/OEM-dependent.",
        "bridge": bridge,
    }
    _record("sync_notifications", payload["summary"], payload)
    return payload


def force_global_sync() -> dict[str, Any]:
    bridge = phone_bridge.status()
    sync = sync_notifications()
    payload = {
        "ok": bool(sync.get("ok") or bridge.get("adb_connected") or bridge.get("ntfy_configured") or list_app_devices(limit=1)),
        "summary": sync.get("summary") or bridge.get("setup_hint") or "Android device mesh sync completed.",
        "bridge": bridge,
        "notification_sync": sync,
        "app_devices": list_app_devices(limit=12),
        "recent_events": recent_events(limit=12),
        "recent_files": recent_files(limit=12),
    }
    _record("global_sync", payload["summary"], payload)
    return payload


def voice_to_friday(text: str) -> dict[str, Any]:
    cleaned = _clean(text)
    if not cleaned:
        return {"ok": False, "summary": "No phone voice text provided."}
    from core import orchestrator

    reply = orchestrator.handle_command(cleaned)
    _record("voice_to_friday", f"Phone voice command handled: {cleaned}", {"text": cleaned, "reply": reply})
    return {"ok": True, "text": cleaned, "reply": reply, "summary": "Phone voice command handled."}


def register_app_device(name: str = "", device_id: str = "", capabilities: list[str] | None = None, status_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    stable_id = _clean(device_id) or f"android-{abs(hash(_clean(name) or 'phone'))}"
    now = _now()
    payload = _safe_payload(status_payload or {})
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO android_app_devices(device_id, name, registered_at, updated_at, capabilities_json, status_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                name=excluded.name,
                updated_at=excluded.updated_at,
                capabilities_json=excluded.capabilities_json,
                status_json=excluded.status_json
            """,
            (stable_id, _clean(name) or "Android companion", now, now, _json_dumps(capabilities or []), _json_dumps(payload)),
        )
        row = conn.execute("SELECT * FROM android_app_devices WHERE device_id=?", (stable_id,)).fetchone()
    _record("app_register", f"Android companion app registered: {row['name']}", {"device_id": stable_id, "capabilities": capabilities or []})
    return _device_row(row)


def ingest_app_status(device_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _update_device_event(device_id, "app_status", payload)


def ingest_notification(device_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = _safe_payload(payload)
    title = _clean(sanitized.get("title") or "Android notification")
    _record("app_notification", title, {"device_id": _clean(device_id), "notification": sanitized})
    notification_center.add(source="android_companion", category="phone_notification", severity=1, title=title[:120], message=_clean(sanitized.get("text") or ""), metadata={"device_id": _clean(device_id)})
    return {"ok": True, "summary": "Phone notification received.", "notification": sanitized}


def ingest_clipboard(device_id: str, text: str) -> dict[str, Any]:
    cleaned = _redact_sensitive(_clean(text))[:4000]
    _record("app_clipboard", "Android clipboard synced.", {"device_id": _clean(device_id), "text": cleaned})
    return {"ok": True, "summary": "Android clipboard synced.", "text": cleaned}


def ingest_location(device_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = _safe_payload(payload)
    _record("app_location", "Android location update received.", {"device_id": _clean(device_id), "location": sanitized})
    return {"ok": True, "summary": "Android location update received.", "location": sanitized}


def ingest_file_event(device_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = _safe_payload(payload)
    stored = _store_optional_blob(_clean(device_id), sanitized, kind="file")
    _record("app_file", f"Android file event: {_clean(sanitized.get('name') or 'file')}", {"device_id": _clean(device_id), "file": sanitized, "stored": stored})
    return {"ok": True, "summary": "Android file received." if stored.get("stored_path") else "Android file metadata received.", "file": sanitized, "stored": stored}


def ingest_camera_frame(device_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = _safe_payload(payload)
    stored = _store_optional_blob(_clean(device_id), sanitized, kind="camera")
    _record("app_camera_frame", "Android camera frame received.", {"device_id": _clean(device_id), "frame": sanitized, "stored": stored})
    return {"ok": True, "summary": "Android camera snapshot received." if stored.get("stored_path") else "Android camera frame metadata received.", "frame": sanitized, "stored": stored}


def list_app_devices(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM android_app_devices ORDER BY updated_at DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_device_row(row) for row in rows]


def ring(message: str = "") -> dict[str, Any]:
    payload = phone_bridge.ring_phone(message)
    _record("ring", payload.get("summary", "Ring requested."), payload)
    return payload


def recent_events(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM android_companion_events ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit))),)).fetchall()
    return [_row(row) for row in rows]


def recent_files(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM android_app_files ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_file_row(row) for row in rows]


def get_file(file_id: int) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM android_app_files WHERE id=?", (int(file_id),)).fetchone()
    return _file_row(row) if row else {}


def companion_summary() -> dict[str, Any]:
    data = status()
    configured = bool(data.get("bridge", {}).get("adb_connected") or data.get("bridge", {}).get("ntfy_configured"))
    return {"configured": configured, "summary": data["summary"], "status": data}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM android_companion_events")
        conn.execute("DELETE FROM android_app_devices")
        conn.execute("DELETE FROM android_app_files")


def _store_optional_blob(device_id: str, payload: dict[str, Any], *, kind: str) -> dict[str, Any]:
    raw = str(payload.get("content_base64") or payload.get("image_base64") or "")
    if not raw:
        return {"stored_path": "", "summary": "No file bytes included."}
    try:
        data = base64.b64decode(raw, validate=False)
    except Exception:
        return {"stored_path": "", "summary": "Invalid base64 payload."}
    max_bytes = int(config_value("android_companion_max_upload_bytes", 2_000_000))
    if len(data) > max_bytes:
        return {"stored_path": "", "summary": f"Upload too large ({len(data)} bytes > {max_bytes})."}
    FILE_DIR.mkdir(parents=True, exist_ok=True)
    name = _clean(payload.get("name") or f"{kind}_{_timestamp_slug()}.bin")
    safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)[:120] or f"{kind}.bin"
    target = FILE_DIR / f"{_timestamp_slug()}_{safe_name}"
    target.write_bytes(data)
    metadata = dict(payload)
    metadata.pop("content_base64", None)
    metadata.pop("image_base64", None)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            "INSERT INTO android_app_files(timestamp, device_id, kind, name, mime_type, stored_path, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), device_id, kind, safe_name, _clean(payload.get("mime_type") or ""), str(target), _json_dumps(metadata)),
        )
    return {"stored_path": str(target), "bytes": len(data), "summary": f"Stored {len(data)} byte(s) from Android."}


def _record(action: str, summary: str, metadata: dict[str, Any]) -> int:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            "INSERT INTO android_companion_events(timestamp, action, summary, metadata_json) VALUES (?, ?, ?, ?)",
            (_now(), _clean(action), _clean(summary)[:1000], _json_dumps(metadata)),
        )
    if "failed" in summary.lower() or "needs" in summary.lower():
        notification_center.add(source="android_companion", category="phone", severity=2, title="Android companion notice", message=summary, dedupe_key=f"android:{action}", metadata=metadata)
    return int(cursor.lastrowid)


def _update_device_event(device_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    stable_id = _clean(device_id) or "android-companion"
    sanitized = _safe_payload(payload)
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM android_app_devices WHERE device_id=?", (stable_id,)).fetchone()
        if row:
            conn.execute("UPDATE android_app_devices SET updated_at=?, status_json=? WHERE device_id=?", (now, _json_dumps(sanitized), stable_id))
        else:
            conn.execute(
                "INSERT INTO android_app_devices(device_id, name, registered_at, updated_at, capabilities_json, status_json) VALUES (?, 'Android companion', ?, ?, '[]', ?)",
                (stable_id, now, now, _json_dumps(sanitized)),
            )
        row = conn.execute("SELECT * FROM android_app_devices WHERE device_id=?", (stable_id,)).fetchone()
    _record(action, f"Android companion {action.replace('_', ' ')} received.", {"device_id": stable_id, "payload": sanitized})
    return {"ok": True, "device": _device_row(row), "summary": f"Android companion {action.replace('_', ' ')} received."}


def _device_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "device_id": str(row["device_id"]),
        "name": str(row["name"]),
        "registered_at": str(row["registered_at"]),
        "updated_at": str(row["updated_at"]),
        "capabilities": _json_loads(row["capabilities_json"], []),
        "status": _json_loads(row["status_json"], {}),
    }


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": int(row["id"]), "timestamp": str(row["timestamp"]), "action": str(row["action"]), "summary": str(row["summary"]), "metadata": _json_loads(row["metadata_json"], {})}


def _file_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "device_id": str(row["device_id"]),
        "kind": str(row["kind"]),
        "name": str(row["name"]),
        "mime_type": str(row["mime_type"]),
        "stored_path": str(row["stored_path"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in (payload or {}).items():
        name = _clean(key)
        if not name:
            continue
        if any(term in name.lower() for term in ("password", "token", "secret", "credential", "authorization")):
            safe[name] = "[redacted]"
        elif isinstance(value, str):
            safe[name] = _redact_sensitive(value)[:4000]
        elif isinstance(value, (int, float, bool)) or value is None:
            safe[name] = value
        else:
            safe[name] = _clean(value)[:1000]
    return safe


def _redact_sensitive(value: str) -> str:
    text = str(value or "")
    for marker in ("password", "token", "secret", "api_key", "authorization", "bearer"):
        if marker in text.lower():
            return "[redacted-sensitive-phone-text]"
    return text


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _timestamp_slug() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")

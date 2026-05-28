"""Free-first Android phone bridge for Friday.

Supported paths:
- ntfy push notifications for free phone alerts/ringing.
- ADB for local Android device status, battery, opening URLs, and dialing.

This module intentionally does not fake carrier calls. Without a paid telephony
provider, "call me" means ring/notify the user's phone or ask the Android phone
itself to open the dialer when ADB is connected.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import quote

from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "phone_bridge.sqlite3"
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
            CREATE TABLE IF NOT EXISTS phone_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                platform TEXT NOT NULL,
                adb_serial TEXT NOT NULL,
                ntfy_topic TEXT NOT NULL,
                phone_number TEXT NOT NULL,
                is_default INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_phone_default ON phone_devices(is_default, updated_at)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS phone_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT NOT NULL,
                success INTEGER NOT NULL,
                summary TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_phone_events_time ON phone_events(timestamp)")
        _seed_default_device(conn)


def register_device(
    name: str,
    *,
    adb_serial: str = "",
    ntfy_topic: str = "",
    phone_number: str = "",
    is_default: bool = True,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    cleaned_name = _clean(name) or "Android Phone"
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        if is_default:
            conn.execute("UPDATE phone_devices SET is_default=0")
        cursor = conn.execute(
            """
            INSERT INTO phone_devices(name, platform, adb_serial, ntfy_topic, phone_number, is_default, metadata_json, created_at, updated_at)
            VALUES (?, 'android', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cleaned_name,
                _clean(adb_serial),
                _clean(ntfy_topic),
                _clean_phone(phone_number),
                1 if is_default else 0,
                _json_dumps(metadata or {}),
                now,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM phone_devices WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    device = _row_to_device(row)
    _record_event("register_device", cleaned_name, True, f"Registered {cleaned_name}.", {"device": device})
    return device


def list_devices() -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM phone_devices ORDER BY is_default DESC, id DESC").fetchall()
    return [_row_to_device(row) for row in rows]


def default_device() -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM phone_devices ORDER BY is_default DESC, id DESC LIMIT 1").fetchone()
    return _row_to_device(row) if row else None


def status() -> dict[str, Any]:
    device = default_device()
    adb = adb_devices()
    battery = battery_status(record=False)
    ntfy_topic = _device_ntfy_topic(device)
    return {
        "enabled": bool(config_value("phone_bridge_enabled", True)),
        "platform": "android",
        "adb_available": _adb_path() != "",
        "adb_path": _adb_path() or str(config_value("phone_bridge_adb_path", "adb")),
        "adb_devices": adb,
        "adb_connected": any(item.get("state") == "device" for item in adb),
        "ntfy_configured": bool(ntfy_topic),
        "ntfy_topic": ntfy_topic,
        "ntfy_base_url": _ntfy_base_url(),
        "default_device": device,
        "battery": battery,
        "recent_events": recent_events(limit=8),
        "setup_hint": setup_hint(),
    }


def setup_hint() -> str:
    pieces = []
    if not _device_ntfy_topic(default_device()):
        pieces.append("Install ntfy on Android, subscribe to a private topic, then set PHONE_NTFY_TOPIC in .env.")
    if not _adb_path():
        pieces.append("Install Android platform-tools and put adb.exe on PATH, or set phone_bridge_adb_path in config.json.")
    if not pieces:
        return "Phone bridge is configured. ADB gives local control; ntfy gives remote alerts."
    return " ".join(pieces)


def adb_devices() -> list[dict[str, Any]]:
    adb = _adb_path()
    if not adb:
        return []
    result = _run_adb(["devices", "-l"], serial="")
    if not result["ok"]:
        return []
    devices: list[dict[str, Any]] = []
    for line in result["stdout"].splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        meta = {}
        for part in parts[2:]:
            if ":" in part:
                key, value = part.split(":", 1)
                meta[key] = value
        devices.append({"serial": serial, "state": state, "metadata": meta})
    return devices


def battery_status(*, record: bool = True) -> dict[str, Any]:
    serial = _target_serial(default_device())
    if not serial and len(adb_devices()) == 1:
        serial = adb_devices()[0]["serial"]
    if not serial:
        payload = {"available": False, "reason": "No ADB device connected.", "level": None, "charging": None}
        if record:
            _record_event("battery", "", False, payload["reason"], payload)
        return payload
    result = _run_adb(["shell", "dumpsys", "battery"], serial=serial)
    if not result["ok"]:
        payload = {"available": False, "serial": serial, "reason": result["stderr"] or result["stdout"], "level": None, "charging": None}
        if record:
            _record_event("battery", serial, False, "Could not read phone battery.", payload)
        return payload
    parsed = _parse_battery(result["stdout"])
    payload = {"available": True, "serial": serial, **parsed}
    if record:
        _record_event("battery", serial, True, f"Phone battery is {parsed.get('level')}%.", payload)
    return payload


def send_notification(
    title: str,
    message: str,
    *,
    priority: str = "high",
    tags: str = "iphone",
    click_url: str = "",
) -> dict[str, Any]:
    device = default_device()
    topic = _device_ntfy_topic(device)
    if not topic:
        payload = {"ok": False, "summary": "No ntfy topic configured. Set PHONE_NTFY_TOPIC in .env or register a device with ntfy_topic."}
        _record_event("notify", "", False, payload["summary"], payload)
        return payload
    base = _ntfy_base_url()
    url = f"{base}/{quote(topic, safe='')}"
    headers = {
        "Title": _clean(title)[:200] or "Friday",
        "Priority": _ntfy_priority(priority),
        "Tags": _clean(tags)[:120] or "iphone",
    }
    token = _env_or_config("PHONE_NTFY_TOKEN", "phone_bridge_ntfy_token", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if click_url:
        headers["Click"] = click_url
    body = str(message or "").encode("utf-8")
    try:
        req = request.Request(url, data=body, headers=headers, method="POST")
        with request.urlopen(req, timeout=float(config_value("phone_bridge_ntfy_timeout_seconds", 8.0))) as response:
            response_text = response.read().decode("utf-8", errors="replace")
        payload = {"ok": True, "summary": "Notification sent to phone.", "response": response_text, "topic": topic}
        _record_event("notify", topic, True, payload["summary"], payload)
        return payload
    except (error.URLError, TimeoutError, OSError) as exc:
        payload = {"ok": False, "summary": f"Phone notification failed: {exc}", "topic": topic}
        _record_event("notify", topic, False, payload["summary"], payload)
        return payload


def ring_phone(message: str = "") -> dict[str, Any]:
    title = str(config_value("jarvis_name", "Friday"))
    body = _clean(message) or "Friday is trying to reach you."
    payload = send_notification(title, body, priority="urgent", tags="rotating_light,phone")
    adb_payload = _adb_attention_signal()
    payload["adb_signal"] = adb_payload
    payload["summary"] = "Phone ring alert sent." if payload.get("ok") else payload.get("summary", "Phone ring failed.")
    _record_event("ring", _device_name(default_device()), bool(payload.get("ok") or adb_payload.get("ok")), payload["summary"], payload)
    return payload


def open_url(url: str) -> dict[str, Any]:
    cleaned_url = _normalize_url(url)
    if not cleaned_url:
        payload = {"ok": False, "summary": "No URL provided."}
        _record_event("open_url", "", False, payload["summary"], payload)
        return payload
    serial = _target_serial(default_device())
    if serial or len(adb_devices()) == 1:
        serial = serial or adb_devices()[0]["serial"]
        result = _run_adb(["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", cleaned_url], serial=serial)
        if result["ok"]:
            payload = {"ok": True, "summary": "Opened URL on Android phone.", "serial": serial, "url": cleaned_url, "adb": result}
            _record_event("open_url", cleaned_url, True, payload["summary"], payload)
            return payload
    notify = send_notification("Open on phone", cleaned_url, priority="high", tags="link", click_url=cleaned_url)
    notify["url"] = cleaned_url
    notify["summary"] = "Sent URL to phone." if notify.get("ok") else notify.get("summary", "Could not send URL to phone.")
    _record_event("open_url", cleaned_url, bool(notify.get("ok")), notify["summary"], notify)
    return notify


def dial_number(number: str, *, direct: bool = False) -> dict[str, Any]:
    cleaned = _clean_phone(number)
    if not cleaned:
        payload = {"ok": False, "summary": "No phone number provided."}
        _record_event("dial", "", False, payload["summary"], payload)
        return payload
    serial = _target_serial(default_device())
    if not serial and len(adb_devices()) == 1:
        serial = adb_devices()[0]["serial"]
    if not serial:
        payload = {
            "ok": False,
            "summary": "No ADB phone connected. I can only place/open calls through your Android phone when ADB is connected.",
        }
        _record_event("dial", cleaned, False, payload["summary"], payload)
        return payload
    action = "android.intent.action.CALL" if direct and bool(config_value("phone_bridge_allow_direct_call", False)) else "android.intent.action.DIAL"
    result = _run_adb(["shell", "am", "start", "-a", action, "-d", f"tel:{cleaned}"], serial=serial)
    ok = bool(result.get("ok"))
    summary = "Opened the Android dialer." if action.endswith("DIAL") and ok else "Asked Android to place the call." if ok else "Could not open Android dialer."
    payload = {"ok": ok, "summary": summary, "serial": serial, "number": _mask_phone(cleaned), "action": action, "adb": result}
    _record_event("dial", _mask_phone(cleaned), ok, summary, payload)
    return payload


def call_contact(query: str, *, direct: bool = False) -> dict[str, Any]:
    from core import app_integrations

    matches = app_integrations.search_contacts(query, limit=5)
    contact = next((item for item in matches if item.get("phone")), None)
    if not contact:
        payload = {"ok": False, "summary": f"I could not find a saved contact phone number for {query}."}
        _record_event("call_contact", query, False, payload["summary"], payload)
        return payload
    payload = dial_number(str(contact.get("phone") or ""), direct=direct)
    payload["contact"] = {"id": contact.get("id"), "name": contact.get("name")}
    return payload


def sms_draft(number: str, message: str = "") -> dict[str, Any]:
    cleaned = _clean_phone(number)
    if not cleaned:
        payload = {"ok": False, "summary": "No phone number provided for SMS draft."}
        _record_event("sms_draft", "", False, payload["summary"], payload)
        return payload
    serial = _auto_serial()
    if not serial:
        payload = {"ok": False, "summary": "No ADB phone connected. I can only open SMS drafts through Android when ADB is connected."}
        _record_event("sms_draft", _mask_phone(cleaned), False, payload["summary"], payload)
        return payload
    args = ["shell", "am", "start", "-a", "android.intent.action.SENDTO", "-d", f"smsto:{cleaned}"]
    if message:
        args.extend(["--es", "sms_body", str(message)[:2000]])
    result = _run_adb(args, serial=serial)
    payload = {
        "ok": bool(result.get("ok")),
        "summary": "Opened SMS draft on Android phone." if result.get("ok") else "Could not open SMS draft on Android phone.",
        "number": _mask_phone(cleaned),
        "adb": result,
    }
    _record_event("sms_draft", _mask_phone(cleaned), bool(payload["ok"]), payload["summary"], payload)
    return payload


def push_file_to_phone(local_path: str, phone_path: str = "/sdcard/Download/") -> dict[str, Any]:
    serial = _auto_serial()
    source = Path(local_path).expanduser()
    if not serial:
        payload = {"ok": False, "summary": "No ADB phone connected for file transfer."}
        _record_event("push_file", str(source), False, payload["summary"], payload)
        return payload
    if not source.exists() or not source.is_file():
        payload = {"ok": False, "summary": "Local file not found."}
        _record_event("push_file", str(source), False, payload["summary"], payload)
        return payload
    destination = _phone_safe_path(phone_path or "/sdcard/Download/")
    result = _run_adb(["push", str(source), destination], serial=serial)
    payload = {
        "ok": bool(result.get("ok")),
        "summary": "File sent to Android phone." if result.get("ok") else "Could not send file to Android phone.",
        "source": str(source),
        "destination": destination,
        "adb": result,
    }
    _record_event("push_file", str(source), bool(payload["ok"]), payload["summary"], payload)
    return payload


def pull_file_from_phone(phone_path: str, local_dir: str = "") -> dict[str, Any]:
    serial = _auto_serial()
    if not serial:
        payload = {"ok": False, "summary": "No ADB phone connected for file import."}
        _record_event("pull_file", phone_path, False, payload["summary"], payload)
        return payload
    source = _phone_safe_path(phone_path)
    if not source:
        payload = {"ok": False, "summary": "No Android file path provided."}
        _record_event("pull_file", phone_path, False, payload["summary"], payload)
        return payload
    destination = Path(local_dir or (DATA_DIR / "phone_imports")).expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    result = _run_adb(["pull", source, str(destination)], serial=serial)
    payload = {
        "ok": bool(result.get("ok")),
        "summary": "File imported from Android phone." if result.get("ok") else "Could not import file from Android phone.",
        "source": source,
        "destination": str(destination),
        "adb": result,
    }
    _record_event("pull_file", source, bool(payload["ok"]), payload["summary"], payload)
    return payload


def set_clipboard(text: str) -> dict[str, Any]:
    serial = _auto_serial()
    value = str(text or "")[:4000]
    if not value:
        payload = {"ok": False, "summary": "No clipboard text provided."}
        _record_event("clipboard_set", "", False, payload["summary"], payload)
        return payload
    if not serial:
        notify = send_notification("Copy this", value, priority="high", tags="clipboard")
        notify["summary"] = "Sent clipboard text to phone as a notification." if notify.get("ok") else notify.get("summary", "Could not send clipboard text.")
        _record_event("clipboard_set", "", bool(notify.get("ok")), notify["summary"], notify)
        return notify
    escaped = value.replace("\\", "\\\\").replace("'", "'\"'\"'")
    result = _run_adb(["shell", "cmd", "clipboard", "set", escaped], serial=serial)
    if not result.get("ok"):
        notify = send_notification("Copy this", value, priority="high", tags="clipboard")
        notify["adb"] = result
        notify["summary"] = "Android clipboard command failed; sent text as a notification." if notify.get("ok") else "Could not set Android clipboard."
        _record_event("clipboard_set", "", bool(notify.get("ok")), notify["summary"], notify)
        return notify
    payload = {"ok": True, "summary": "Android clipboard updated.", "adb": result}
    _record_event("clipboard_set", "", True, payload["summary"], payload)
    return payload


def import_photos(local_dir: str = "", limit: int = 50) -> dict[str, Any]:
    serial = _auto_serial()
    if not serial:
        payload = {"ok": False, "summary": "No ADB phone connected for photo import."}
        _record_event("import_photos", "", False, payload["summary"], payload)
        return payload
    destination = Path(local_dir or (DATA_DIR / "phone_photos")).expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    source_dir = str(config_value("phone_bridge_photo_dir", "/sdcard/DCIM/Camera"))
    result = _run_adb(["pull", source_dir, str(destination)], serial=serial)
    payload = {
        "ok": bool(result.get("ok")),
        "summary": "Photo import started from Android phone." if result.get("ok") else "Could not import photos from Android phone.",
        "source": source_dir,
        "destination": str(destination),
        "limit": int(limit),
        "adb": result,
    }
    _record_event("import_photos", source_dir, bool(payload["ok"]), payload["summary"], payload)
    return payload


def recent_events(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM phone_events ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit))),)).fetchall()
    return [
        {
            "id": int(row["id"]),
            "timestamp": str(row["timestamp"]),
            "action": str(row["action"]),
            "target": str(row["target"]),
            "success": bool(row["success"]),
            "summary": str(row["summary"]),
            "metadata": _json_loads(row["metadata_json"], {}),
        }
        for row in rows
    ]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM phone_events")
        conn.execute("DELETE FROM phone_devices")


def _seed_default_device(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT COUNT(*) FROM phone_devices").fetchone()
    if int(row[0]) > 0:
        return
    topic = _env_or_config("PHONE_NTFY_TOPIC", "phone_bridge_ntfy_topic", "")
    serial = str(config_value("phone_bridge_adb_serial", "") or "").strip()
    number = _env_or_config("PHONE_NUMBER", "phone_bridge_user_phone_number", "")
    if not any([topic, serial, number]):
        return
    now = _now()
    conn.execute(
        """
        INSERT INTO phone_devices(name, platform, adb_serial, ntfy_topic, phone_number, is_default, metadata_json, created_at, updated_at)
        VALUES (?, 'android', ?, ?, ?, 1, '{}', ?, ?)
        """,
        (str(config_value("phone_bridge_default_name", "My Android Phone")), serial, topic, _clean_phone(number), now, now),
    )


def _row_to_device(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "platform": str(row["platform"]),
        "adb_serial": str(row["adb_serial"]),
        "ntfy_topic": str(row["ntfy_topic"]),
        "phone_number": _mask_phone(str(row["phone_number"])),
        "has_phone_number": bool(str(row["phone_number"])),
        "is_default": bool(row["is_default"]),
        "metadata": _json_loads(row["metadata_json"], {}),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def _device_ntfy_topic(device: dict[str, Any] | None) -> str:
    return str((device or {}).get("ntfy_topic") or _env_or_config("PHONE_NTFY_TOPIC", "phone_bridge_ntfy_topic", "") or "").strip()


def _target_serial(device: dict[str, Any] | None) -> str:
    return str((device or {}).get("adb_serial") or config_value("phone_bridge_adb_serial", "") or "").strip()


def _device_name(device: dict[str, Any] | None) -> str:
    return str((device or {}).get("name") or config_value("phone_bridge_default_name", "Android Phone") or "Android Phone")


def _ntfy_base_url() -> str:
    return _env_or_config("PHONE_NTFY_BASE_URL", "phone_bridge_ntfy_base_url", "https://ntfy.sh").rstrip("/")


def _adb_path() -> str:
    configured = str(config_value("phone_bridge_adb_path", "adb") or "adb").strip()
    if Path(configured).exists():
        return configured
    return shutil.which(configured) or ""


def _run_adb(args: list[str], *, serial: str = "") -> dict[str, Any]:
    adb = _adb_path()
    if not adb:
        return {"ok": False, "stdout": "", "stderr": "adb not found"}
    command = [adb]
    if serial:
        command.extend(["-s", serial])
    command.extend(args)
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=float(config_value("phone_bridge_adb_timeout_seconds", 8.0)),
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "returncode": proc.returncode,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "stdout": "", "stderr": str(exc), "returncode": -1}


def _adb_attention_signal() -> dict[str, Any]:
    serial = _auto_serial()
    if not serial:
        return {"ok": False, "summary": "No ADB phone connected."}
    results = []
    for _ in range(3):
        results.append(_run_adb(["shell", "input", "keyevent", "24"], serial=serial))
    vibrate = _run_adb(["shell", "cmd", "vibrator", "vibrate", "800"], serial=serial)
    ok = any(result.get("ok") for result in results) or vibrate.get("ok")
    return {"ok": ok, "serial": serial, "volume_key_sent": any(result.get("ok") for result in results), "vibrate": vibrate}


def _auto_serial() -> str:
    serial = _target_serial(default_device())
    devices = adb_devices()
    if not serial and len(devices) == 1:
        serial = devices[0]["serial"]
    return serial


def _phone_safe_path(path: str) -> str:
    value = str(path or "").strip().replace("\\", "/")
    if not value:
        return ""
    allowed_prefixes = tuple(part.strip() for part in str(config_value("phone_bridge_allowed_paths", "/sdcard/,/storage/emulated/0/")).split(",") if part.strip())
    if not value.startswith(allowed_prefixes):
        value = "/sdcard/Download/" + value.lstrip("/")
    return value[:500]


def _parse_battery(text: str) -> dict[str, Any]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip().lower()] = value.strip()
    level = _int(values.get("level"), None)
    status = _int(values.get("status"), 0)
    plugged = _int(values.get("plugged"), 0)
    charging = status in {2, 5} or plugged > 0
    return {
        "level": level,
        "charging": charging,
        "status_code": status,
        "plugged_code": plugged,
        "temperature_c": round((_int(values.get("temperature"), 0) or 0) / 10.0, 1) if values.get("temperature") else None,
        "raw": values,
    }


def _record_event(action: str, target: str, success: bool, summary: str, metadata: dict[str, Any] | None = None) -> int:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            "INSERT INTO phone_events(timestamp, action, target, success, summary, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
            (_now(), _clean(action), _clean(target)[:300], 1 if success else 0, _clean(summary)[:1000], _json_dumps(metadata or {})),
        )
        return int(cursor.lastrowid)


def _ntfy_priority(value: str) -> str:
    lowered = _clean(value).lower()
    mapping = {"urgent": "urgent", "max": "urgent", "high": "high", "default": "default", "low": "low", "min": "min"}
    return mapping.get(lowered, "high")


def _normalize_url(value: str) -> str:
    text = _clean(value)
    if not text:
        return ""
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", text):
        text = "https://" + text
    return text[:2000]


def _clean_phone(value: str) -> str:
    text = str(value or "").strip()
    keep = []
    for index, char in enumerate(text):
        if char.isdigit() or (char == "+" and index == 0):
            keep.append(char)
    return "".join(keep)[:40]


def _mask_phone(value: str) -> str:
    cleaned = _clean_phone(value)
    if len(cleaned) <= 4:
        return cleaned
    return "*" * max(0, len(cleaned) - 4) + cleaned[-4:]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _env_or_config(env_name: str, config_key: str, default: str = "") -> str:
    return str(os.getenv(env_name) or config_value(config_key, default) or "").strip()


def _int(value: Any, default: Any = 0) -> Any:
    try:
        return int(value)
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=True)


def _json_loads(value: str, default: Any = None) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return {} if default is None else default

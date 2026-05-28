"""Tool wrapper for Friday's Android phone bridge."""

from __future__ import annotations

import json
from typing import Any

from core import phone_bridge


def execute(inputs: dict[str, Any]) -> str:
    action = str(inputs.get("action") or "status").strip().lower()
    permission_reply = _permission_reply(inputs)
    if permission_reply:
        return permission_reply
    try:
        if action == "status":
            return _format_status(phone_bridge.status())
        if action == "list_devices":
            return _format_devices(phone_bridge.list_devices())
        if action == "register_device":
            device = phone_bridge.register_device(
                str(inputs.get("name") or inputs.get("target") or "Android Phone"),
                adb_serial=str(inputs.get("adb_serial") or ""),
                ntfy_topic=str(inputs.get("ntfy_topic") or ""),
                phone_number=str(inputs.get("phone_number") or ""),
                is_default=bool(inputs.get("is_default", True)),
            )
            return f"Phone registered: {device['name']}."
        if action in {"battery", "battery_status"}:
            return _format_battery(phone_bridge.battery_status())
        if action in {"notify", "send_notification", "send_to_phone"}:
            title = str(inputs.get("title") or "Friday")
            message = str(inputs.get("message") or inputs.get("target") or "")
            result = phone_bridge.send_notification(title, message, priority=str(inputs.get("priority") or "high"), tags=str(inputs.get("tags") or "iphone"))
            return result.get("summary", "Notification processed.")
        if action in {"ring", "call_me", "find_phone"}:
            result = phone_bridge.ring_phone(str(inputs.get("message") or inputs.get("target") or "Friday is trying to reach you."))
            return result.get("summary", "Phone ring processed.")
        if action == "open_url":
            result = phone_bridge.open_url(str(inputs.get("url") or inputs.get("target") or ""))
            return result.get("summary", "URL processed.")
        if action in {"dial", "call_number"}:
            result = phone_bridge.dial_number(str(inputs.get("number") or inputs.get("target") or ""), direct=bool(inputs.get("direct")))
            return result.get("summary", "Dial processed.")
        if action == "call_contact":
            result = phone_bridge.call_contact(str(inputs.get("name") or inputs.get("target") or ""), direct=bool(inputs.get("direct")))
            return result.get("summary", "Contact call processed.")
        if action in {"sms_draft", "draft_sms"}:
            result = phone_bridge.sms_draft(str(inputs.get("number") or inputs.get("target") or ""), str(inputs.get("message") or inputs.get("body") or ""))
            return result.get("summary", "SMS draft processed.")
        if action in {"push_file", "send_file"}:
            result = phone_bridge.push_file_to_phone(str(inputs.get("local_path") or inputs.get("path") or inputs.get("target") or ""), str(inputs.get("phone_path") or ""))
            return result.get("summary", "File transfer processed.")
        if action in {"pull_file", "import_file"}:
            result = phone_bridge.pull_file_from_phone(str(inputs.get("phone_path") or inputs.get("target") or ""), str(inputs.get("local_dir") or ""))
            return result.get("summary", "File import processed.")
        if action in {"set_clipboard", "clipboard"}:
            result = phone_bridge.set_clipboard(str(inputs.get("text") or inputs.get("target") or ""))
            return result.get("summary", "Clipboard processed.")
        if action in {"import_photos", "photo_import"}:
            result = phone_bridge.import_photos(str(inputs.get("local_dir") or ""), limit=_int(inputs.get("limit"), 50))
            return result.get("summary", "Photo import processed.")
        if action == "events":
            return _format_events(phone_bridge.recent_events(limit=_int(inputs.get("limit"), 8)))
    except Exception as exc:
        return f"Phone bridge action failed: {exc}"
    return "Unknown phone bridge action."


def _permission_reply(inputs: dict[str, Any]) -> str:
    try:
        from core import permissions

        decision = permissions.evaluate("phone_bridge", inputs)
        if decision["blocked"]:
            return f"Permission blocked: {decision['label']} is set to block."
        if decision["requires_confirmation"] and not inputs.get("_permission_confirmed"):
            return f"Permission required: {decision['label']} is set to ask first."
    except Exception:
        return ""
    return ""


def _format_status(payload: dict[str, Any]) -> str:
    device = payload.get("default_device") or {}
    battery = payload.get("battery") or {}
    parts = []
    if device:
        parts.append(f"default phone: {device.get('name')}")
    parts.append("ADB connected" if payload.get("adb_connected") else "ADB not connected")
    parts.append("ntfy configured" if payload.get("ntfy_configured") else "ntfy not configured")
    if battery.get("available"):
        parts.append(f"battery {battery.get('level')}%" + (" charging" if battery.get("charging") else ""))
    return "Phone bridge: " + "; ".join(parts) + "."


def _format_devices(devices: list[dict[str, Any]]) -> str:
    if not devices:
        return "No phone devices registered yet."
    return "\n".join(f"#{item['id']} {item['name']} ({item['platform']}) default={item['is_default']}" for item in devices[:10])


def _format_battery(payload: dict[str, Any]) -> str:
    if not payload.get("available"):
        return str(payload.get("reason") or "Phone battery is unavailable.")
    charging = " and charging" if payload.get("charging") else ""
    return f"Phone battery is {payload.get('level')}%{charging}."


def _format_events(events: list[dict[str, Any]]) -> str:
    if not events:
        return "No phone bridge events yet."
    return "\n".join(f"{event['action']}: {event['summary']}" for event in events[:10])


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def to_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=True, indent=2)

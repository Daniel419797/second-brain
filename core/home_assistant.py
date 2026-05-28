"""Optional Home Assistant integration for free local smart-home control."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, request

from core.config import config_value


def status() -> dict[str, Any]:
    base = _base_url()
    token = _token()
    configured = bool(base and token)
    if not configured:
        return {
            "configured": False,
            "summary": "Home Assistant is not configured. Set HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN to enable local smart-home control.",
        }
    result = _api("GET", "/api/")
    return {"configured": True, "url": base, "reachable": bool(result.get("ok")), "summary": result.get("message") or result.get("summary", "Home Assistant checked.")}


def list_states() -> dict[str, Any]:
    result = _api("GET", "/api/states")
    states = result.get("data") if isinstance(result.get("data"), list) else []
    devices = [
        {
            "entity_id": item.get("entity_id"),
            "state": item.get("state"),
            "friendly_name": (item.get("attributes") or {}).get("friendly_name", ""),
            "domain": str(item.get("entity_id") or "").split(".", 1)[0],
            "attributes": _safe_attributes(item.get("attributes") or {}),
            "last_changed": item.get("last_changed", ""),
            "last_updated": item.get("last_updated", ""),
        }
        for item in states[:200]
    ]
    return {"ok": bool(result.get("ok")), "devices": devices, "summary": f"Loaded {len(devices)} Home Assistant entities." if result.get("ok") else result.get("summary", "Home Assistant unavailable.")}


def call_service(domain: str, service: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    domain = _clean(domain)
    service = _clean(service)
    if not domain or not service:
        return {"ok": False, "summary": "Home Assistant domain and service are required."}
    result = _api("POST", f"/api/services/{domain}/{service}", data or {})
    return {"ok": bool(result.get("ok")), "domain": domain, "service": service, "summary": "Home Assistant service called." if result.get("ok") else result.get("summary", "Service call failed."), "result": result}


def focus_mode(on: bool = True) -> dict[str, Any]:
    entity_id = str(config_value("home_assistant_focus_entity_id", "") or "").strip()
    if not entity_id:
        return {"ok": False, "summary": "Set home_assistant_focus_entity_id to use focus mode."}
    domain = entity_id.split(".", 1)[0]
    service = "turn_on" if on else "turn_off"
    return call_service(domain, service, {"entity_id": entity_id})


def _api(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    base = _base_url()
    token = _token()
    if not base or not token:
        return {"ok": False, "summary": "Home Assistant is not configured."}
    data = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        req = request.Request(base.rstrip("/") + path, data=data, headers=headers, method=method.upper())
        with request.urlopen(req, timeout=float(config_value("home_assistant_timeout_seconds", 8.0))) as response:
            text = response.read().decode("utf-8", errors="replace")
        parsed = json.loads(text) if text and text[:1] in "[{" else text
        return {"ok": 200 <= int(response.status) < 300, "status": int(response.status), "data": parsed, "message": text[:300]}
    except (OSError, TimeoutError, error.URLError) as exc:
        return {"ok": False, "summary": str(exc)}


def _base_url() -> str:
    return (os.getenv("HOME_ASSISTANT_URL") or str(config_value("home_assistant_url", "") or "")).strip().rstrip("/")


def _token() -> str:
    return (os.getenv("HOME_ASSISTANT_TOKEN") or str(config_value("home_assistant_token", "") or "")).strip()


def _clean(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum() or ch in {"_", "-"})


def _safe_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "battery_level",
        "brightness",
        "current_power_w",
        "device_class",
        "friendly_name",
        "icon",
        "mode",
        "temperature",
        "unit_of_measurement",
        "volume_level",
    }
    safe: dict[str, Any] = {}
    for key in allowed:
        if key in attributes:
            value = attributes.get(key)
            if isinstance(value, (str, int, float, bool)) or value is None:
                safe[key] = value
    return safe

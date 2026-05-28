"""Defensive security guardian pro mode."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import browser_extension_bridge, capability_center, personal_safety_guardian, project_watchdog
from core.config import resolve_coding_root


def scan(root: str | Path = "", *, light: bool = True) -> dict[str, Any]:
    base = resolve_coding_root(root)
    overview = _safe(lambda: capability_center.security_overview(light=light), {})
    secrets = _safe(lambda: capability_center.project_secret_scan(base), {})
    dependencies = _safe(lambda: capability_center.dependency_security_scan(base), {})
    personal = _safe(lambda: personal_safety_guardian.scan(base, max_files=300 if light else 1000), {})
    browser = _browser_extension_risk()
    watchdog = _safe(lambda: project_watchdog.run_once(base, notify=False), {})
    findings = []
    findings.extend(_findings_from_overview(overview))
    findings.extend(secrets.get("findings") or [])
    findings.extend(personal.get("findings") or [])
    if browser.get("risk_count"):
        findings.append({"kind": "browser_extension", "severity": 3, "summary": browser["summary"]})
    return {
        "root": str(base),
        "overview": overview,
        "secrets": secrets,
        "dependencies": dependencies,
        "personal_safety": personal,
        "browser_extension_audit": browser,
        "watchdog": watchdog,
        "findings": findings[:50],
        "summary": f"Security Guardian Pro found {len(findings)} defensive finding(s).",
    }


def status() -> dict[str, Any]:
    return {"latest": _safe(lambda: personal_safety_guardian.status(), {}), "overview": _safe(lambda: capability_center.security_overview(light=True), {}), "summary": "Security Guardian Pro is defensive-only and ready."}


def _browser_extension_risk() -> dict[str, Any]:
    status_payload = browser_extension_bridge.status(limit=8)
    console_errors = [item for item in status_payload.get("console") or [] if str(item.get("level")).lower() in {"error", "warn", "warning"}]
    return {"risk_count": len(console_errors), "console_errors": console_errors, "summary": f"{len(console_errors)} browser console warning/error event(s)."}


def _findings_from_overview(overview: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    for proc in overview.get("suspicious_processes") or []:
        findings.append({"kind": "process", "severity": 3, "summary": proc.get("summary") or proc.get("name")})
    for port in (overview.get("open_ports") or {}).get("open_ports") or []:
        findings.append({"kind": "open_port", "severity": 2, "summary": f"Local port {port.get('port')} open ({port.get('service')})."})
    for ext in overview.get("browser_extensions") or []:
        if ext.get("risk_permissions"):
            findings.append({"kind": "browser_extension", "severity": 2, "summary": f"{ext.get('name') or ext.get('id')} has risk permissions."})
    return findings


def _safe(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default

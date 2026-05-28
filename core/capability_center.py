"""Friday capability center for devices, ops, workspace, maintenance, and defensive security.

The security functions in this module are intentionally defensive and scoped.
They do not run exploit payloads, credential attacks, stealth, evasion, or
unsolicited internet scans. External targets must be local/private or have a
recorded ownership scope before Friday will run even low-impact checks.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import threading
from pathlib import Path
from typing import Any
from urllib import request
from urllib.parse import urlparse

try:
    import psutil
except Exception:  # pragma: no cover - optional in some test envs
    psutil = None

from core import command_runner
from core.config import DATA_DIR, ROOT_DIR, config_value, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "capability_center.sqlite3"
REPORT_DIR = DATA_DIR / "reports"
_LOCK = threading.Lock()

DEFAULT_SECURITY_PORTS = [21, 22, 25, 53, 80, 110, 143, 443, 445, 587, 993, 995, 3000, 5000, 5432, 6379, 8000, 8080, 8443]


def init_db(path: Path | None = None) -> None:
    ensure_runtime_dirs()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=10) as conn:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS capability_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                area TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT NOT NULL,
                success INTEGER NOT NULL,
                summary TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS automation_recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                trigger_type TEXT NOT NULL,
                trigger_json TEXT NOT NULL,
                action_type TEXT NOT NULL,
                action_json TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                last_run_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS security_scopes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target TEXT NOT NULL,
                kind TEXT NOT NULL,
                proof TEXT NOT NULL,
                token TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                verified_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS security_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                category TEXT NOT NULL,
                severity INTEGER NOT NULL,
                target TEXT NOT NULL,
                summary TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )


def overview(root: str | Path = "") -> dict[str, Any]:
    return {
        "home": home_status(),
        "personal": personal_brief(),
        "workspace": workspace_project_map(root, max_files=300),
        "maintenance": maintenance_report(light=True),
        "security": security_overview(light=True),
        "automation": {"recipes": list_recipes(limit=10)},
    }


def home_status() -> dict[str, Any]:
    router = router_status()
    printers = list_printers()
    bluetooth = list_bluetooth_devices()
    smart = configured_smart_devices()
    network = local_network_devices(limit=20)
    payload = {
        "router": router,
        "printers": printers,
        "bluetooth": bluetooth,
        "smart_devices": smart,
        "local_network_devices": network,
        "connection_quality": connection_quality(),
    }
    _record_event("home", "status", "", True, "Home/device status collected.", payload)
    return payload


def router_status() -> dict[str, Any]:
    gateway = _default_gateway()
    if not gateway:
        return {"available": False, "summary": "No default gateway found.", "gateway": ""}
    ping = _ping(gateway, count=2)
    return {
        "available": True,
        "gateway": gateway,
        "url": f"http://{gateway}/",
        "reachable": ping.get("ok", False),
        "latency_ms": ping.get("avg_ms"),
        "summary": f"Router gateway is {gateway}.",
    }


def list_printers() -> list[dict[str, Any]]:
    result = _powershell_json("Get-Printer | Select-Object Name,DriverName,PortName,PrinterStatus,Shared,Default")
    if isinstance(result, dict):
        items = [result]
    elif isinstance(result, list):
        items = result
    else:
        return []
    return [_json_safe_dict(item) for item in items[:50]]


def list_bluetooth_devices() -> list[dict[str, Any]]:
    result = _powershell_json("Get-PnpDevice -Class Bluetooth | Select-Object FriendlyName,Status,InstanceId")
    if isinstance(result, dict):
        items = [result]
    elif isinstance(result, list):
        items = result
    else:
        return []
    return [_json_safe_dict(item) for item in items[:80]]


def configured_smart_devices() -> list[dict[str, Any]]:
    raw = config_value("home_smart_devices", [])
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip().startswith("[") else []
        except Exception:
            raw = []
    devices = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        host = str(item.get("host") or "").strip()
        reachable = _ping(host, count=1).get("ok", False) if host else False
        devices.append({**_json_safe_dict(item), "reachable": reachable})
    return devices


def control_smart_device(name: str, action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run a configured local smart-device action.

    Devices are defined in config.json as entries like:
    {"name": "Desk lamp", "host": "192.168.1.50", "actions": {"on": {"url": "http://192.168.1.50/on", "method": "POST"}}}
    Only local/private device URLs are accepted.
    """

    query = _clean(name).lower()
    action_name = _clean(action).lower()
    if not query or not action_name:
        return {"ok": False, "summary": "Smart-device name and action are required."}
    devices = configured_smart_devices()
    device = next(
        (
            item
            for item in devices
            if any(query in str(item.get(field) or "").lower() for field in ("name", "id", "host"))
        ),
        None,
    )
    if not device:
        return {"ok": False, "summary": f"No configured smart device matched {name}."}
    actions = device.get("actions") if isinstance(device.get("actions"), dict) else {}
    spec = actions.get(action_name)
    if not isinstance(spec, dict):
        return {"ok": False, "summary": f"{device.get('name') or name} has no configured '{action_name}' action."}
    url = str(spec.get("url") or "").strip()
    host = _host_from_target(url or str(device.get("host") or ""))
    if not host or not _is_local_or_private(host):
        return {"ok": False, "summary": "Smart-device actions are limited to local/private devices."}
    result = _http_action(url, method=str(spec.get("method") or "POST"), body=spec.get("body"), headers=spec.get("headers"), params=params or {})
    payload = {
        "ok": bool(result.get("ok")),
        "device": device.get("name") or name,
        "action": action_name,
        "summary": f"{device.get('name') or name} {action_name} action sent." if result.get("ok") else f"Could not run {action_name} on {device.get('name') or name}.",
        "result": result,
    }
    _record_event("home", "control_smart_device", str(payload["device"]), bool(payload["ok"]), payload["summary"], payload)
    return payload


def local_network_devices(limit: int = 80) -> list[dict[str, Any]]:
    output = _run(["arp", "-a"], timeout=5).get("stdout", "")
    devices = []
    for match in re.finditer(r"(?P<ip>\d+\.\d+\.\d+\.\d+)\s+(?P<mac>[0-9a-fA-F:-]{11,17})\s+(?P<kind>\w+)", output):
        devices.append({"ip": match.group("ip"), "mac": match.group("mac"), "type": match.group("kind")})
    return devices[: max(1, min(200, int(limit)))]


def connection_quality(host: str = "1.1.1.1") -> dict[str, Any]:
    return _ping(host, count=3)


def personal_brief() -> dict[str, Any]:
    from core import app_integrations, goal_regulation, task_queue

    reminders = app_integrations.list_reminders(include_done=False, limit=8)
    events = app_integrations.list_calendar_events(limit=8)
    tasks = task_queue.counts()
    goals = goal_regulation.current_regulation().get("active_goals", [])
    next_action = personal_next_action(reminders=reminders, events=events, tasks=tasks, goals=goals)
    return {
        "generated_at": _now(),
        "reminders": reminders,
        "events": events,
        "task_counts": tasks,
        "goals": goals,
        "next_action": next_action,
        "summary": _brief_sentence(reminders, events, tasks, next_action),
    }


def personal_next_action(
    *,
    reminders: list[dict[str, Any]] | None = None,
    events: list[dict[str, Any]] | None = None,
    tasks: dict[str, Any] | None = None,
    goals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from core import app_integrations, goal_regulation, task_queue

    reminders = reminders if reminders is not None else app_integrations.list_reminders(include_done=False, limit=10)
    events = events if events is not None else app_integrations.list_calendar_events(limit=10)
    tasks = tasks if tasks is not None else task_queue.counts()
    goals = goals if goals is not None else goal_regulation.current_regulation().get("active_goals", [])
    due = [item for item in reminders if _looks_due(item.get("due_at", ""))]
    if due:
        return {"kind": "reminder", "title": due[0].get("title"), "reason": "This reminder is due or overdue."}
    if int(tasks.get("active") or 0):
        return {"kind": "task", "title": "Review active background work", "reason": f"{tasks.get('active')} task is active."}
    if int(tasks.get("pending") or 0):
        return {"kind": "task", "title": "Start or review pending agent work", "reason": f"{tasks.get('pending')} tasks are pending."}
    if goals:
        return {"kind": "goal", "title": goals[0].get("title"), "reason": "This is your highest tracked goal."}
    if events:
        return {"kind": "calendar", "title": events[0].get("title"), "reason": "Upcoming calendar item."}
    return {"kind": "focus", "title": "Choose one concrete next task", "reason": "No urgent reminder, event, or agent task is waiting."}


def plan_day() -> dict[str, Any]:
    brief = personal_brief()
    blocks = []
    if brief["reminders"]:
        blocks.append({"block": "Reminders", "items": [item.get("title") for item in brief["reminders"][:3]]})
    if brief["events"]:
        blocks.append({"block": "Calendar", "items": [item.get("title") for item in brief["events"][:3]]})
    blocks.append({"block": "Next", "items": [brief["next_action"]["title"]]})
    return {"summary": brief["summary"], "blocks": blocks, "generated_at": brief["generated_at"]}


def workspace_project_map(root: str | Path = "", max_files: int | None = None) -> dict[str, Any]:
    base = _safe_root(root)
    max_count = int(max_files or config_value("workspace_project_map_max_files", 1000))
    skip = _csv_set(config_value("workspace_index_skip_dirs", ".git,.venv,node_modules,__pycache__,.next,dist,build"))
    extensions: dict[str, int] = {}
    key_files: list[dict[str, Any]] = []
    total = 0
    for path in _iter_files(base, skip=skip, max_files=max_count):
        total += 1
        ext = path.suffix.lower() or "(none)"
        extensions[ext] = extensions.get(ext, 0) + 1
        rel = _rel(path, base)
        if path.name.lower() in {"package.json", "requirements.txt", "pyproject.toml", "dockerfile", "render.yaml", "next.config.js", "vite.config.js"} or path.parent == base:
            key_files.append({"path": rel, "size": path.stat().st_size})
    return {
        "root": str(base),
        "total_files_scanned": total,
        "extensions": dict(sorted(extensions.items(), key=lambda item: item[1], reverse=True)[:20]),
        "key_files": key_files[:80],
        "summary": f"Mapped {total} files under {base.name}.",
    }


def workspace_dependency_health(root: str | Path = "") -> dict[str, Any]:
    base = _safe_root(root)
    manifests = _dependency_manifests(base)
    audits = []
    if (base / "package.json").exists():
        audits.append(_npm_audit(base))
    if (base / "requirements.txt").exists() or (base / "pyproject.toml").exists():
        audits.append(_pip_audit(base))
    payload = {"root": str(base), "manifests": manifests, "audits": audits, "summary": _dependency_summary(manifests, audits)}
    _record_event("workspace", "dependency_health", str(base), True, payload["summary"], payload)
    return payload


def workspace_auto_docs(root: str | Path = "") -> dict[str, Any]:
    base = _safe_root(root)
    project_map = workspace_project_map(base)
    dependency = workspace_dependency_health(base)
    docs_dir = base / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    out = docs_dir / "friday_project_map.md"
    body = [
        "# Friday Project Map",
        "",
        f"Generated: {_now()}",
        f"Root: `{base}`",
        "",
        "## Summary",
        project_map["summary"],
        dependency["summary"],
        "",
        "## Key Files",
    ]
    body.extend(f"- `{item['path']}` ({item['size']} bytes)" for item in project_map["key_files"][:80])
    body.extend(["", "## File Types"])
    body.extend(f"- `{ext}`: {count}" for ext, count in project_map["extensions"].items())
    out.write_text("\n".join(body) + "\n", encoding="utf-8")
    return {"path": str(out), "summary": f"Project map written to {out}."}


def test_failure_watcher(command: str = "") -> dict[str, Any]:
    cmd = command or str(config_value("workspace_test_watch_command", config_value("self_update_test_command", "python -m pytest -q")))
    result = _run_shell(cmd, cwd=ROOT_DIR, timeout=int(config_value("workspace_test_watch_timeout_seconds", 120)))
    ok = bool(result.get("ok"))
    payload = {
        "ok": ok,
        "command": cmd,
        "stdout_tail": _tail(result.get("stdout", ""), 4000),
        "stderr_tail": _tail(result.get("stderr", ""), 4000),
        "summary": "Tests passed." if ok else "Tests failed or timed out.",
    }
    _record_event("workspace", "test_watch", cmd, ok, payload["summary"], payload)
    return payload


def maintenance_report(light: bool = False) -> dict[str, Any]:
    disks = disk_cleanup_suggestions()
    startup = startup_app_audit(limit=30 if light else 100)
    health = battery_cpu_health()
    drivers = driver_update_status(light=light)
    suggestions = []
    suggestions.extend(item["suggestion"] for item in disks if item.get("suggestion"))
    if len(startup) > 12:
        suggestions.append("Review startup apps; many entries can slow boot.")
    if health.get("battery", {}).get("percent") is not None and health["battery"].get("percent", 100) < 20:
        suggestions.append("Battery is low; consider charging or enabling power saving.")
    return {
        "generated_at": _now(),
        "disk": disks,
        "startup_apps": startup,
        "health": health,
        "drivers": drivers,
        "suggestions": suggestions[:12],
        "summary": f"{len(suggestions[:12])} maintenance suggestions found.",
    }


def disk_cleanup_suggestions() -> list[dict[str, Any]]:
    items = []
    for drive in _candidate_drives():
        try:
            usage = shutil.disk_usage(drive)
        except Exception:
            continue
        free_percent = round((usage.free / usage.total) * 100.0, 1) if usage.total else 0.0
        suggestion = "Free space is healthy."
        if free_percent < 15:
            suggestion = "Low disk space; clean downloads, temp files, or old builds."
        items.append({"path": drive, "total_gb": round(usage.total / (1024**3), 1), "free_gb": round(usage.free / (1024**3), 1), "free_percent": free_percent, "suggestion": suggestion})
    return items


def startup_app_audit(limit: int = 100) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    startup_dirs = [
        Path(os.getenv("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup",
        Path(os.getenv("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup",
    ]
    for folder in startup_dirs:
        if folder.exists():
            for path in folder.iterdir():
                items.append({"source": "startup_folder", "name": path.name, "path": str(path)})
    reg = _powershell_json(
        "Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run','HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run' -ErrorAction SilentlyContinue | Select-Object PSPath,*"
    )
    for row in reg if isinstance(reg, list) else ([reg] if isinstance(reg, dict) else []):
        source = str(row.get("PSPath") or "registry")
        for key, value in row.items():
            if key.startswith("PS") or key in {"RunspaceId"} or not value:
                continue
            items.append({"source": source, "name": key, "path": str(value)})
    return items[: max(1, min(300, int(limit)))]


def battery_cpu_health() -> dict[str, Any]:
    battery = {}
    cpu = {}
    memory = {}
    if psutil is not None:
        try:
            batt = psutil.sensors_battery()
            if batt:
                battery = {"percent": round(float(batt.percent), 1), "plugged": bool(batt.power_plugged)}
        except Exception:
            pass
        try:
            cpu = {"percent": psutil.cpu_percent(interval=0.1), "logical_count": psutil.cpu_count(), "physical_count": psutil.cpu_count(logical=False)}
            vm = psutil.virtual_memory()
            memory = {"percent": vm.percent, "available_gb": round(vm.available / (1024**3), 2), "total_gb": round(vm.total / (1024**3), 2)}
        except Exception:
            pass
    return {"battery": battery, "cpu": cpu, "memory": memory}


def driver_update_status(light: bool = False) -> dict[str, Any]:
    if light:
        return {"checked": False, "summary": "Driver detail skipped in light mode."}
    result = _powershell_json("Get-CimInstance Win32_PnPSignedDriver | Select-Object -First 40 DeviceName,Manufacturer,DriverVersion,DriverDate")
    rows = result if isinstance(result, list) else ([result] if isinstance(result, dict) else [])
    return {"checked": True, "drivers_sample": [_json_safe_dict(item) for item in rows], "summary": f"Sampled {len(rows)} signed drivers."}


def security_overview(light: bool = False) -> dict[str, Any]:
    processes = suspicious_processes(limit=12 if light else 40)
    startup = startup_persistence_checks(limit=12 if light else 80)
    ports = scan_open_ports("127.0.0.1", ports=DEFAULT_SECURITY_PORTS[:10] if light else DEFAULT_SECURITY_PORTS, require_scope=False)
    extensions = browser_extension_audit(limit=12 if light else 120)
    return {
        "generated_at": _now(),
        "suspicious_processes": processes,
        "startup_persistence": startup,
        "open_ports": ports,
        "browser_extensions": extensions,
        "scope_policy": "External targets require local/private address or verified ownership proof before scanning.",
        "summary": f"{len(processes)} process alerts, {len(startup)} startup entries, {len(ports.get('open_ports', []))} local open ports.",
    }


def suspicious_processes(limit: int = 40) -> list[dict[str, Any]]:
    alerts = []
    if psutil is None:
        return alerts
    temp_dirs = [str(Path(os.getenv("TEMP", "")).resolve()).lower(), str(Path(os.getenv("TMP", "")).resolve()).lower()]
    suspicious_names = {"nc.exe", "netcat.exe", "mimikatz.exe", "miner.exe", "xmrig.exe", "powershell.exe", "wscript.exe", "cscript.exe"}
    for proc in psutil.process_iter(["pid", "name", "exe", "cmdline", "cpu_percent"]):
        try:
            info = proc.info
            name = str(info.get("name") or "").lower()
            exe = str(info.get("exe") or "")
            exe_l = exe.lower()
            reasons = []
            if name in suspicious_names:
                reasons.append("high-risk process name")
            if exe_l and any(exe_l.startswith(temp) for temp in temp_dirs if temp):
                reasons.append("running from temp path")
            cmd = " ".join(str(part) for part in (info.get("cmdline") or []))
            if "-enc" in cmd.lower() and "powershell" in name:
                reasons.append("encoded PowerShell command")
            if reasons:
                alerts.append({"pid": info.get("pid"), "name": info.get("name"), "path": exe, "reasons": reasons})
        except Exception:
            continue
    return alerts[: max(1, min(200, int(limit)))]


def startup_persistence_checks(limit: int = 80) -> list[dict[str, Any]]:
    return startup_app_audit(limit=limit)


def scan_open_ports(target: str, ports: list[int] | None = None, *, require_scope: bool = True, timeout: float = 0.35) -> dict[str, Any]:
    host = _host_from_target(target)
    if not host:
        return {"ok": False, "summary": "No scan target provided.", "target": target, "open_ports": []}
    if require_scope and not target_allowed(host):
        return {
            "ok": False,
            "requires_scope": True,
            "target": host,
            "summary": "Target is outside local/private scope. Add and verify an ownership scope before scanning.",
            "open_ports": [],
        }
    checked_ports = [int(port) for port in (ports or DEFAULT_SECURITY_PORTS) if 0 < int(port) < 65536][:100]
    open_ports = []
    for port in checked_ports:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                open_ports.append({"port": port, "service": _service_name(port)})
        except Exception:
            continue
    payload = {"ok": True, "target": host, "checked_ports": checked_ports, "open_ports": open_ports, "summary": f"{len(open_ports)} open ports found on {host}."}
    _record_finding("open_ports", 2 if open_ports else 0, host, payload["summary"], payload, "Close unused services or restrict them with firewall rules.")
    return payload


def browser_extension_audit(limit: int = 120) -> list[dict[str, Any]]:
    roots = [
        Path(os.getenv("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Default" / "Extensions",
        Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "User Data" / "Default" / "Extensions",
    ]
    extensions = []
    for root in roots:
        browser = "edge" if "Edge" in str(root) else "chrome"
        if not root.exists():
            continue
        for ext_dir in root.iterdir():
            if not ext_dir.is_dir():
                continue
            versions = [item for item in ext_dir.iterdir() if item.is_dir()]
            manifest = next((version / "manifest.json" for version in sorted(versions, reverse=True) if (version / "manifest.json").exists()), None)
            name = ext_dir.name
            permissions: list[str] = []
            if manifest:
                try:
                    data = json.loads(manifest.read_text(encoding="utf-8", errors="ignore"))
                    name = str(data.get("name") or name)
                    permissions = [str(item) for item in data.get("permissions", []) if isinstance(item, str)]
                except Exception:
                    pass
            risk = [perm for perm in permissions if perm in {"tabs", "webRequest", "webRequestBlocking", "cookies", "history", "downloads", "nativeMessaging"}]
            extensions.append({"browser": browser, "id": ext_dir.name, "name": name, "permissions": permissions[:20], "risk_permissions": risk})
    return extensions[: max(1, min(300, int(limit)))]


def web_security_headers(target: str) -> dict[str, Any]:
    host = _host_from_target(target)
    if not host:
        return {"ok": False, "summary": "No web target provided.", "target": target}
    if not target_allowed(host):
        return {"ok": False, "requires_scope": True, "target": host, "summary": "Verify ownership scope before checking deployed web security headers."}
    url = _normalize_web_url(target)
    try:
        req = request.Request(url, method="GET", headers={"User-Agent": "Friday-Security-Lab/1.0"})
        with request.urlopen(req, timeout=8) as response:
            headers = {key.lower(): value for key, value in response.headers.items()}
            status_code = int(response.status)
    except Exception as exc:
        return {"ok": False, "target": host, "url": url, "summary": f"Could not fetch headers: {exc}"}
    required = {
        "content-security-policy": "Add a Content-Security-Policy to reduce XSS blast radius.",
        "x-content-type-options": "Add X-Content-Type-Options: nosniff.",
        "referrer-policy": "Add a Referrer-Policy header.",
        "strict-transport-security": "Add HSTS after HTTPS is stable.",
    }
    missing = [{"header": key, "recommendation": recommendation} for key, recommendation in required.items() if key not in headers]
    payload = {
        "ok": True,
        "target": host,
        "url": url,
        "status_code": status_code,
        "present_headers": sorted(key for key in required if key in headers),
        "missing_headers": missing,
        "server": headers.get("server", ""),
        "summary": f"{len(missing)} recommended security headers missing on {host}.",
    }
    _record_finding("web_headers", 2 if missing else 0, host, payload["summary"], payload, "Add the missing security headers at your reverse proxy or app framework.")
    return payload


def project_secret_scan(root: str | Path = "") -> dict[str, Any]:
    base = _safe_root(root)
    skip = _csv_set(config_value("workspace_index_skip_dirs", ".git,.venv,node_modules,__pycache__,.next,dist,build"))
    risky_files = []
    risky_patterns = []
    file_names = {".env", ".env.local", ".env.production", "id_rsa", "id_dsa", "credentials.json", "service-account.json"}
    pattern_re = re.compile(r"(api[_-]?key|secret|password|token|private[_-]?key)\s*[:=]", re.IGNORECASE)
    for path in _iter_files(base, skip=skip, max_files=700):
        rel = _rel(path, base)
        lower_name = path.name.lower()
        if lower_name in file_names or lower_name.endswith(".pem"):
            risky_files.append({"path": rel, "reason": "sensitive filename"})
        if path.suffix.lower() not in {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".env", ".txt", ".md", ".toml", ".yaml", ".yml"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:120000]
        except Exception:
            continue
        if pattern_re.search(text):
            risky_patterns.append({"path": rel, "reason": "possible secret assignment"})
    payload = {
        "ok": True,
        "root": str(base),
        "risky_files": risky_files[:80],
        "risky_patterns": risky_patterns[:80],
        "summary": f"Found {len(risky_files)} risky filenames and {len(risky_patterns)} possible secret patterns.",
    }
    severity = 3 if risky_files or risky_patterns else 0
    _record_finding("secret_scan", severity, str(base), payload["summary"], payload, "Keep secrets out of source control, rotate exposed credentials, and use environment variables or a secrets manager.")
    return payload


def create_security_scope(target: str, *, kind: str = "web", proof: str = "") -> dict[str, Any]:
    init_db()
    cleaned = _host_from_target(target) or str(target or "").strip()
    token = "friday-" + _hash_token(cleaned)
    status = "verified" if _is_local_or_private(cleaned) else "pending"
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO security_scopes(target, kind, proof, token, status, created_at, verified_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (cleaned, str(kind or "web"), str(proof or ""), token, status, now, now if status == "verified" else "", _json_dumps({})),
        )
        row = conn.execute("SELECT * FROM security_scopes WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _scope_from_row(row)


def list_security_scopes(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM security_scopes ORDER BY id DESC LIMIT ?", (max(1, min(200, int(limit))),)).fetchall()
    return [_scope_from_row(row) for row in rows]


def verify_security_scope(scope_id: int, proof_url: str = "") -> dict[str, Any]:
    init_db()
    scope = _get_scope(scope_id)
    if not scope:
        return {"ok": False, "summary": "Scope not found."}
    target = scope["target"]
    if _is_local_or_private(target):
        _set_scope_verified(scope_id, {"method": "local_private"})
        return _get_scope(scope_id) | {"ok": True, "summary": "Local/private scope verified."}
    url = proof_url or f"https://{target}/.well-known/friday-ownership.txt"
    try:
        with request.urlopen(url, timeout=8) as response:
            body = response.read().decode("utf-8", errors="replace")
        if scope["token"] not in body:
            return {"ok": False, "summary": "Ownership token was not found at proof URL.", "proof_url": url}
        _set_scope_verified(scope_id, {"method": "http_file", "proof_url": url})
        return _get_scope(scope_id) | {"ok": True, "summary": "Ownership scope verified."}
    except Exception as exc:
        return {"ok": False, "summary": f"Ownership verification failed: {exc}", "proof_url": url}


def target_allowed(target: str) -> bool:
    host = _host_from_target(target)
    if not host:
        return False
    if _is_local_or_private(host):
        return True
    return any(scope["target"] == host and scope["status"] == "verified" for scope in list_security_scopes(limit=200))


def dependency_security_scan(root: str | Path = "") -> dict[str, Any]:
    result = workspace_dependency_health(root)
    severity = 1 if result.get("audits") else 0
    _record_finding("dependency_audit", severity, result["root"], result["summary"], result, "Update vulnerable packages and pin known-good versions.")
    return result


def generate_security_report(target: str = "", root: str | Path = "") -> dict[str, Any]:
    base = _safe_root(root)
    overview_payload = security_overview(light=False)
    dependency = dependency_security_scan(base)
    target_host = _host_from_target(target) if target else "127.0.0.1"
    ports = scan_open_ports(target_host, require_scope=True) if target_host else {"summary": "No target."}
    headers = web_security_headers(target_host) if target_host else {"summary": "No target."}
    secrets = project_secret_scan(base)
    report = {
        "generated_at": _now(),
        "target": target_host,
        "root": str(base),
        "overview": overview_payload,
        "dependency": dependency,
        "ports": ports,
        "headers": headers,
        "secrets": secrets,
        "hardening": hardening_plan(target_host, root=base),
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"security_report_{_timestamp_slug()}.md"
    path.write_text(_security_report_markdown(report), encoding="utf-8")
    report["path"] = str(path)
    _record_event("security", "report", target_host, True, f"Security report written to {path}.", {"path": str(path)})
    return report


def hardening_plan(target: str = "", root: str | Path = "") -> dict[str, Any]:
    dependency = workspace_dependency_health(root)
    host = _host_from_target(target) or ""
    headers = web_security_headers(host) if host and target_allowed(host) else {"missing_headers": []}
    secrets = project_secret_scan(root)
    steps = [
        "Keep dependencies updated and remove unused packages.",
        "Set secure HTTP headers on web apps: Content-Security-Policy, X-Content-Type-Options, Referrer-Policy, and HSTS when HTTPS is stable.",
        "Disable debug endpoints and development servers on public deployments.",
        "Restrict databases, admin panels, and dev ports to private networks or VPN.",
        "Use environment variables for secrets and rotate any credential that may have leaked.",
        "Add CI checks for npm audit/pip-audit/bandit/semgrep where available.",
    ]
    if dependency.get("audits"):
        steps.insert(0, "Review dependency audit output and patch vulnerable packages first.")
    if headers.get("missing_headers"):
        steps.insert(0, "Add the missing deployed-site security headers reported by Friday's header check.")
    if secrets.get("risky_files") or secrets.get("risky_patterns"):
        steps.insert(0, "Review possible secrets in the project, remove them from code, and rotate anything that may have leaked.")
    return {"target": host, "root": str(_safe_root(root)), "steps": steps, "summary": f"{len(steps)} hardening steps prepared."}


def create_recipe(name: str, trigger_type: str, trigger: dict[str, Any] | None, action_type: str, action: dict[str, Any] | None, enabled: bool = True) -> dict[str, Any]:
    init_db()
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO automation_recipes(name, trigger_type, trigger_json, action_type, action_json, enabled, last_run_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, '', ?, ?)
            """,
            (_clean(name) or "Automation recipe", _clean(trigger_type), _json_dumps(trigger or {}), _clean(action_type), _json_dumps(action or {}), 1 if enabled else 0, now, now),
        )
        row = conn.execute("SELECT * FROM automation_recipes WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    recipe = _recipe_from_row(row)
    _record_event("automation", "create_recipe", recipe["name"], True, f"Recipe created: {recipe['name']}.", recipe)
    return recipe


def list_recipes(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM automation_recipes ORDER BY id DESC LIMIT ?", (max(1, min(200, int(limit))),)).fetchall()
    return [_recipe_from_row(row) for row in rows]


def run_recipe(recipe_id: int) -> dict[str, Any]:
    recipe = _get_recipe(recipe_id)
    if not recipe:
        return {"ok": False, "summary": "Recipe not found."}
    result = _execute_recipe_action(recipe)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE automation_recipes SET last_run_at=?, updated_at=? WHERE id=?", (_now(), _now(), int(recipe_id)))
    _record_event("automation", "run_recipe", recipe["name"], bool(result.get("ok")), result.get("summary", "Recipe run."), {"recipe": recipe, "result": result})
    return {"ok": bool(result.get("ok")), "recipe": recipe, "result": result, "summary": result.get("summary", "Recipe run.")}


def recent_events(limit: int = 30, area: str = "") -> list[dict[str, Any]]:
    init_db()
    params: list[Any] = []
    where = ""
    if area:
        where = "WHERE area=?"
        params.append(area)
    params.append(max(1, min(200, int(limit))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM capability_events {where} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_event_from_row(row) for row in rows]


def recent_findings(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM security_findings ORDER BY id DESC LIMIT ?", (max(1, min(200, int(limit))),)).fetchall()
    return [_finding_from_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM capability_events")
        conn.execute("DELETE FROM automation_recipes")
        conn.execute("DELETE FROM security_scopes")
        conn.execute("DELETE FROM security_findings")


def _execute_recipe_action(recipe: dict[str, Any]) -> dict[str, Any]:
    action_type = recipe.get("action_type", "")
    action = recipe.get("action", {})
    if action_type == "notify_phone":
        from core import phone_bridge

        return phone_bridge.send_notification("Friday automation", str(action.get("message") or recipe.get("name") or "Automation ran."))
    if action_type == "open_app":
        from tools import pc_control

        reply = pc_control.execute({"action": "open_app", "target": str(action.get("target") or "")})
        return {"ok": "could not" not in reply.lower() and "failed" not in reply.lower(), "summary": reply}
    if action_type == "set_brightness":
        from tools import pc_control

        reply = pc_control.execute({"action": "set_brightness", "target": str(action.get("level") or action.get("target") or "50")})
        return {"ok": "set" in reply.lower(), "summary": reply}
    if action_type == "start_dashboard":
        return {"ok": True, "summary": "Use package scripts to start API/dashboard; background launch is intentionally manual from this recipe runner."}
    return {"ok": False, "summary": f"Unsupported recipe action: {action_type}."}


def _brief_sentence(reminders: list[dict[str, Any]], events: list[dict[str, Any]], tasks: dict[str, Any], next_action: dict[str, Any]) -> str:
    return (
        f"You have {len(reminders)} open reminders, {len(events)} upcoming local events, "
        f"{tasks.get('active', 0)} active tasks, and {tasks.get('pending', 0)} pending tasks. "
        f"Next: {next_action.get('title')}."
    )


def _looks_due(value: str) -> bool:
    if not value:
        return False
    text = str(value).lower()
    if any(word in text for word in {"today", "now", "overdue"}):
        return True
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
        return parsed <= dt.datetime.now().astimezone()
    except Exception:
        return False


def _dependency_manifests(base: Path) -> list[dict[str, Any]]:
    manifests = []
    for name in ["package.json", "package-lock.json", "requirements.txt", "pyproject.toml", "poetry.lock", "pnpm-lock.yaml", "yarn.lock"]:
        path = base / name
        if path.exists():
            manifests.append({"path": name, "size": path.stat().st_size})
    return manifests


def _npm_audit(base: Path) -> dict[str, Any]:
    has_lockfile = any((base / name).exists() for name in ["package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock"])
    if not shutil.which("npm") or not (base / "package.json").exists() or not has_lockfile:
        return {"tool": "npm audit", "available": False, "summary": "npm, package.json, or lockfile unavailable."}
    result = _run(["npm", "audit", "--json", "--audit-level=low"], cwd=base, timeout=int(config_value("security_npm_audit_timeout_seconds", 45)))
    data = _json_loads(result.get("stdout", ""), {})
    counts = data.get("metadata", {}).get("vulnerabilities", {}) if isinstance(data, dict) else {}
    return {"tool": "npm audit", "available": True, "ok": result.get("ok"), "counts": counts, "stderr_tail": _tail(result.get("stderr", ""), 1000)}


def _pip_audit(base: Path) -> dict[str, Any]:
    exe = shutil.which("pip-audit")
    if not exe:
        return {"tool": "pip-audit", "available": False, "summary": "pip-audit is not installed."}
    result = _run([exe, "-f", "json"], cwd=base, timeout=int(config_value("security_pip_audit_timeout_seconds", 45)))
    data = _json_loads(result.get("stdout", ""), {})
    return {"tool": "pip-audit", "available": True, "ok": result.get("ok"), "result_count": len(data.get("dependencies", [])) if isinstance(data, dict) else 0, "stderr_tail": _tail(result.get("stderr", ""), 1000)}


def _dependency_summary(manifests: list[dict[str, Any]], audits: list[dict[str, Any]]) -> str:
    if not manifests:
        return "No dependency manifests found."
    unavailable = [item["tool"] for item in audits if not item.get("available", True)]
    if unavailable:
        return f"Found {len(manifests)} dependency manifests. Optional tools unavailable: {', '.join(unavailable)}."
    return f"Found {len(manifests)} dependency manifests and ran {len(audits)} audit checks."


def _default_gateway() -> str:
    result = _powershell_json("Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | Select-Object -First 1 NextHop")
    if isinstance(result, dict) and result.get("NextHop"):
        return str(result["NextHop"])
    output = _run(["ipconfig"], timeout=5).get("stdout", "")
    match = re.search(r"Default Gateway[ .]*:\s*([0-9.]+)", output)
    return match.group(1) if match else ""


def _ping(host: str, count: int = 2) -> dict[str, Any]:
    if not host:
        return {"ok": False, "host": host}
    result = _run(["ping", "-n", str(max(1, min(5, count))), host], timeout=8)
    output = result.get("stdout", "")
    match = re.search(r"Average = (\d+)ms", output)
    return {"ok": bool(result.get("ok")), "host": host, "avg_ms": int(match.group(1)) if match else None}


def _powershell_json(script: str) -> Any:
    command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f"{script} | ConvertTo-Json -Depth 4"]
    result = _run(command, timeout=12)
    if not result.get("ok") or not result.get("stdout"):
        return None
    return _json_loads(result["stdout"], None)


def _run(args: list[str], cwd: Path | None = None, timeout: int | float = 20) -> dict[str, Any]:
    try:
        proc = subprocess.run(args, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout, check=False)
        return {"ok": proc.returncode == 0, "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "returncode": -1, "stdout": "", "stderr": str(exc)}


def _run_shell(command: str, cwd: Path | None = None, timeout: int | float = 20) -> dict[str, Any]:
    try:
        proc = command_runner.run(command, cwd=cwd, timeout=timeout)
        return {"ok": proc.returncode == 0, "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
    except (OSError, subprocess.TimeoutExpired, command_runner.CommandRejected) as exc:
        return {"ok": False, "returncode": -1, "stdout": "", "stderr": str(exc)}


def _http_action(url: str, *, method: str = "POST", body: Any = None, headers: Any = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if not url:
        return {"ok": False, "summary": "No action URL configured."}
    payload = body
    if isinstance(payload, str):
        for key, value in (params or {}).items():
            payload = payload.replace("{{" + str(key) + "}}", str(value))
        data = payload.encode("utf-8")
    elif payload is None:
        data = None
    else:
        data = _json_dumps(payload).encode("utf-8")
    request_headers = {str(k): str(v) for k, v in (headers if isinstance(headers, dict) else {}).items()}
    if data is not None and "Content-Type" not in request_headers:
        request_headers["Content-Type"] = "application/json"
    try:
        req = request.Request(url, data=data, headers=request_headers, method=str(method or "POST").upper())
        with request.urlopen(req, timeout=float(config_value("home_device_control_timeout_seconds", 6.0))) as response:
            response_body = response.read(1200).decode("utf-8", errors="replace")
        return {"ok": 200 <= int(response.status) < 300, "status_code": int(response.status), "body_preview": response_body}
    except Exception as exc:
        return {"ok": False, "summary": str(exc)}


def _candidate_drives() -> list[str]:
    system = os.getenv("SystemDrive", "C:") + "\\"
    drives = [system]
    if psutil is not None:
        try:
            drives.extend(part.mountpoint for part in psutil.disk_partitions() if "fixed" in part.opts.lower() or os.name != "nt")
        except Exception:
            pass
    return list(dict.fromkeys(drives))


def _iter_files(base: Path, *, skip: set[str], max_files: int):
    count = 0
    for path in base.rglob("*"):
        if count >= max_files:
            break
        if any(part in skip for part in path.parts):
            continue
        if path.is_file():
            count += 1
            yield path


def _safe_root(root: str | Path = "") -> Path:
    candidate = resolve_coding_root(root)
    try:
        resolved = candidate.resolve()
    except Exception:
        resolved = resolve_coding_root()
    fallback = resolve_coding_root()
    return resolved if resolved.exists() and resolved.is_dir() else fallback


def _host_from_target(target: str) -> str:
    text = str(target or "").strip()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"//{text}")
    host = parsed.hostname or text.split("/")[0].split(":")[0]
    return host.strip().lower()


def _normalize_web_url(target: str) -> str:
    text = str(target or "").strip()
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return f"https://{text}"


def _is_local_or_private(host: str) -> bool:
    host = _host_from_target(host)
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(socket.gethostbyname(host))
        return ip.is_loopback or ip.is_private or ip.is_link_local
    except Exception:
        return False


def _service_name(port: int) -> str:
    try:
        return socket.getservbyport(int(port), "tcp")
    except Exception:
        return "unknown"


def _record_event(area: str, action: str, target: str, success: bool, summary: str, metadata: dict[str, Any] | None = None) -> int:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            "INSERT INTO capability_events(timestamp, area, action, target, success, summary, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), _clean(area), _clean(action), _clean(target)[:400], 1 if success else 0, _clean(summary)[:1000], _json_dumps(metadata or {})),
        )
        return int(cursor.lastrowid)


def _record_finding(category: str, severity: int, target: str, summary: str, evidence: dict[str, Any], recommendation: str) -> int:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            "INSERT INTO security_findings(timestamp, category, severity, target, summary, evidence_json, recommendation, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'open')",
            (_now(), _clean(category), int(severity), _clean(target)[:400], _clean(summary)[:1000], _json_dumps(evidence), _clean(recommendation)[:1000]),
        )
        return int(cursor.lastrowid)


def _scope_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "target": str(row["target"]),
        "kind": str(row["kind"]),
        "proof": str(row["proof"]),
        "token": str(row["token"]),
        "status": str(row["status"]),
        "created_at": str(row["created_at"]),
        "verified_at": str(row["verified_at"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _get_scope(scope_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM security_scopes WHERE id=?", (int(scope_id),)).fetchone()
    return _scope_from_row(row) if row else None


def _set_scope_verified(scope_id: int, metadata: dict[str, Any]) -> None:
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE security_scopes SET status='verified', verified_at=?, metadata_json=? WHERE id=?", (_now(), _json_dumps(metadata), int(scope_id)))


def _recipe_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "trigger_type": str(row["trigger_type"]),
        "trigger": _json_loads(row["trigger_json"], {}),
        "action_type": str(row["action_type"]),
        "action": _json_loads(row["action_json"], {}),
        "enabled": bool(row["enabled"]),
        "last_run_at": str(row["last_run_at"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def _get_recipe(recipe_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM automation_recipes WHERE id=?", (int(recipe_id),)).fetchone()
    return _recipe_from_row(row) if row else None


def _event_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "area": str(row["area"]),
        "action": str(row["action"]),
        "target": str(row["target"]),
        "success": bool(row["success"]),
        "summary": str(row["summary"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _finding_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "category": str(row["category"]),
        "severity": int(row["severity"]),
        "target": str(row["target"]),
        "summary": str(row["summary"]),
        "evidence": _json_loads(row["evidence_json"], {}),
        "recommendation": str(row["recommendation"]),
        "status": str(row["status"]),
    }


def _security_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Friday Security Report",
        "",
        f"Generated: {report['generated_at']}",
        f"Target: `{report.get('target')}`",
        f"Project root: `{report.get('root')}`",
        "",
        "## Summary",
        f"- {report['overview'].get('summary')}",
        f"- {report['dependency'].get('summary')}",
        f"- {report['ports'].get('summary')}",
        "",
        "## Hardening Plan",
    ]
    lines.extend(f"- {step}" for step in report["hardening"].get("steps", []))
    return "\n".join(lines) + "\n"


def _rel(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except Exception:
        return str(path)


def _csv_set(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    return {part.strip() for part in str(value or "").split(",") if part.strip()}


def _json_safe_dict(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    return {str(k): _json_safe_value(v) for k, v in item.items()}


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dt.datetime):
        return value.isoformat()
    return str(value)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any = None) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _hash_token(value: str) -> str:
    import hashlib

    return hashlib.sha256(f"{value}:{_now()}".encode("utf-8")).hexdigest()[:18]


def _timestamp_slug() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _tail(value: str, chars: int) -> str:
    text = str(value or "")
    return text[-chars:]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

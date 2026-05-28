"""Voice/tool wrapper for Friday's capability center."""

from __future__ import annotations

from typing import Any

from core import capability_center


def execute(inputs: dict[str, Any]) -> str:
    action = str(inputs.get("action") or "overview").strip().lower()
    permission_reply = _permission_reply(inputs)
    if permission_reply:
        return permission_reply
    try:
        if action == "overview":
            return _format_overview(capability_center.overview(str(inputs.get("root") or "")))
        if action in {"home_status", "home_devices"}:
            return _format_home(capability_center.home_status())
        if action == "control_smart_device":
            result = capability_center.control_smart_device(
                str(inputs.get("name") or inputs.get("target") or ""),
                str(inputs.get("device_action") or inputs.get("command") or ""),
                _dict(inputs.get("params")),
            )
            return result.get("summary", "Smart-device action processed.")
        if action == "router_status":
            router = capability_center.router_status()
            return router.get("summary", "Router status unavailable.")
        if action == "local_network":
            devices = capability_center.local_network_devices(limit=_int(inputs.get("limit"), 30))
            return _format_items("network devices", devices, "ip")
        if action == "connection_quality":
            quality = capability_center.connection_quality(str(inputs.get("target") or inputs.get("host") or "1.1.1.1"))
            return f"Connection to {quality.get('host')} is {'ok' if quality.get('ok') else 'not confirmed'}; average latency {quality.get('avg_ms')} ms."
        if action == "daily_brief":
            return capability_center.personal_brief().get("summary", "No daily brief available.")
        if action == "next_action":
            item = capability_center.personal_next_action()
            return f"Next: {item.get('title')}. Reason: {item.get('reason')}"
        if action == "plan_day":
            plan = capability_center.plan_day()
            return plan.get("summary", "No plan generated.")
        if action == "workspace_map":
            mapped = capability_center.workspace_project_map(str(inputs.get("root") or ""))
            return mapped.get("summary", "Workspace map unavailable.")
        if action == "dependency_health":
            health = capability_center.workspace_dependency_health(str(inputs.get("root") or ""))
            return health.get("summary", "Dependency health unavailable.")
        if action == "auto_docs":
            result = capability_center.workspace_auto_docs(str(inputs.get("root") or ""))
            return result.get("summary", "Auto docs unavailable.")
        if action == "test_watch":
            result = capability_center.test_failure_watcher(str(inputs.get("command") or ""))
            return result.get("summary", "Test watcher unavailable.")
        if action == "maintenance_report":
            report = capability_center.maintenance_report()
            return report.get("summary", "Maintenance report unavailable.")
        if action == "security_overview":
            report = capability_center.security_overview()
            return report.get("summary", "Security overview unavailable.")
        if action == "create_security_scope":
            scope = capability_center.create_security_scope(str(inputs.get("target") or ""), kind=str(inputs.get("kind") or "web"), proof=str(inputs.get("proof") or ""))
            return f"Security scope #{scope['id']} created for {scope['target']}. Status: {scope['status']}. Token: {scope['token']}."
        if action == "verify_security_scope":
            result = capability_center.verify_security_scope(_int(inputs.get("scope_id") or inputs.get("target")), proof_url=str(inputs.get("proof_url") or ""))
            return result.get("summary", "Verification complete.")
        if action == "list_security_scopes":
            scopes = capability_center.list_security_scopes(limit=_int(inputs.get("limit"), 10))
            return _format_scopes(scopes)
        if action == "open_port_scan":
            target = str(inputs.get("target") or "127.0.0.1")
            ports = _ports(inputs.get("ports"))
            result = capability_center.scan_open_ports(target, ports=ports or None)
            return result.get("summary", "Port scan unavailable.")
        if action == "dependency_security_scan":
            result = capability_center.dependency_security_scan(str(inputs.get("root") or ""))
            return result.get("summary", "Dependency scan unavailable.")
        if action == "web_security_check":
            result = capability_center.web_security_headers(str(inputs.get("target") or ""))
            return result.get("summary", "Web security check unavailable.")
        if action == "secret_scan":
            result = capability_center.project_secret_scan(str(inputs.get("root") or ""))
            return result.get("summary", "Secret scan unavailable.")
        if action == "security_report":
            result = capability_center.generate_security_report(str(inputs.get("target") or ""), root=str(inputs.get("root") or ""))
            return f"Security report generated: {result.get('path')}"
        if action == "hardening_plan":
            result = capability_center.hardening_plan(str(inputs.get("target") or ""), root=str(inputs.get("root") or ""))
            return "Hardening plan: " + "; ".join(result.get("steps", [])[:4])
        if action == "list_recipes":
            return _format_recipes(capability_center.list_recipes(limit=_int(inputs.get("limit"), 10)))
        if action == "create_recipe":
            recipe = capability_center.create_recipe(
                str(inputs.get("name") or inputs.get("target") or "Automation recipe"),
                str(inputs.get("trigger_type") or "manual"),
                _dict(inputs.get("trigger")),
                str(inputs.get("action_type") or "notify_phone"),
                _dict(inputs.get("action_data")),
                enabled=bool(inputs.get("enabled", True)),
            )
            return f"Automation recipe #{recipe['id']} created."
        if action == "run_recipe":
            result = capability_center.run_recipe(_int(inputs.get("recipe_id") or inputs.get("target")))
            return result.get("summary", "Recipe run complete.")
    except Exception as exc:
        return f"Capability center action failed: {exc}"
    return "Unknown capability center action."


def _permission_reply(inputs: dict[str, Any]) -> str:
    try:
        from core import permissions

        decision = permissions.evaluate("capability_center", inputs)
        if decision["blocked"]:
            return f"Permission blocked: {decision['label']} is set to block."
        if decision["requires_confirmation"] and not inputs.get("_permission_confirmed"):
            return f"Permission required: {decision['label']} is set to ask first."
    except Exception:
        return ""
    return ""


def _format_overview(payload: dict[str, Any]) -> str:
    return (
        f"Capability center ready. {payload.get('personal', {}).get('summary', '')} "
        f"{payload.get('maintenance', {}).get('summary', '')} {payload.get('security', {}).get('summary', '')}"
    ).strip()


def _format_home(payload: dict[str, Any]) -> str:
    router = payload.get("router", {})
    return (
        f"Router: {router.get('gateway') or 'unknown'}. "
        f"Printers: {len(payload.get('printers') or [])}. Bluetooth devices: {len(payload.get('bluetooth') or [])}. "
        f"Network devices seen: {len(payload.get('local_network_devices') or [])}."
    )


def _format_items(label: str, items: list[dict[str, Any]], title_key: str = "name") -> str:
    if not items:
        return f"No {label} found."
    return "\n".join(str(item.get(title_key) or item.get("name") or item.get("summary") or item) for item in items[:10])


def _format_scopes(scopes: list[dict[str, Any]]) -> str:
    if not scopes:
        return "No security scopes have been added."
    return "\n".join(f"#{item['id']} {item['target']} - {item['status']}" for item in scopes[:10])


def _format_recipes(recipes: list[dict[str, Any]]) -> str:
    if not recipes:
        return "No automation recipes yet."
    return "\n".join(f"#{item['id']} {item['name']} -> {item['action_type']}" for item in recipes[:10])


def _ports(value: Any) -> list[int]:
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value or "").replace(",", " ").split()
    ports = []
    for item in raw:
        try:
            port = int(item)
            if 0 < port < 65536:
                ports.append(port)
        except Exception:
            continue
    return ports[:100]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default

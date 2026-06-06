"""Scoped Security Lab for authorized defensive testing and CTF/lab work."""

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
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core import approval_inbox, autonomy_control, capability_center, command_runner, permissions
from core.config import DATA_DIR, config_value, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "security_lab.sqlite3"
ARTIFACT_ROOT = DATA_DIR / "security_lab"
_LOCK = threading.Lock()


@dataclass(frozen=True)
class SecurityTool:
    id: str
    label: str
    executable: str
    category: str
    surface: str
    risk: str = "low"
    requires_target: bool = False
    requires_scope: bool = False
    internal: bool = False
    description: str = ""


TOOLS: dict[str, SecurityTool] = {
    "secret_scan": SecurityTool("secret_scan", "Secret Scan", "", "code", "filesystem", internal=True, description="Find likely secrets and risky credential files."),
    "dependency_summary": SecurityTool("dependency_summary", "Dependency Security Scan", "", "code", "filesystem", internal=True, description="Run Friday's dependency security summary."),
    "threat_model": SecurityTool("threat_model", "Threat Model", "", "planning", "project", internal=True, description="Generate a project threat model and hardening map."),
    "hardening_plan": SecurityTool("hardening_plan", "Hardening Plan", "", "planning", "project", internal=True, description="Generate practical hardening steps for the app/server."),
    "auth_session_review": SecurityTool("auth_session_review", "Auth/Session/Rate-Limit Review", "", "code", "filesystem", internal=True, description="Inspect source signals for auth, session cookies, CSRF, and rate limiting."),
    "web_headers": SecurityTool("web_headers", "Security Headers", "", "web", "http", internal=True, requires_target=True, requires_scope=True, description="Inspect deployed web security headers."),
    "semgrep": SecurityTool("semgrep", "Semgrep", "semgrep", "sast", "filesystem", description="Static application security analysis."),
    "bandit": SecurityTool("bandit", "Bandit", "bandit", "sast", "filesystem", description="Python security static analysis."),
    "npm_audit": SecurityTool("npm_audit", "npm audit", "npm", "dependencies", "filesystem", description="Node dependency vulnerability audit."),
    "pip_audit": SecurityTool("pip_audit", "pip-audit", "pip-audit", "dependencies", "filesystem", description="Python dependency vulnerability audit."),
    "safety": SecurityTool("safety", "Safety", "safety", "dependencies", "filesystem", description="Python dependency vulnerability scan."),
    "gitleaks": SecurityTool("gitleaks", "Gitleaks", "gitleaks", "secrets", "filesystem", description="Git and filesystem secret scanning."),
    "trivy_fs": SecurityTool("trivy_fs", "Trivy FS", "trivy", "supply_chain", "filesystem", description="Filesystem, dependency, and IaC vulnerability scan."),
    "nmap_discovery": SecurityTool("nmap_discovery", "Nmap Service Discovery", "nmap", "network", "network", "medium", True, True, description="Scoped host service discovery."),
    "nmap_web": SecurityTool("nmap_web", "Nmap Web Scripts", "nmap", "network", "network", "medium", True, True, description="Scoped HTTP/TLS script scan."),
    "nuclei": SecurityTool("nuclei", "Nuclei", "nuclei", "web", "http", "medium", True, True, description="Template-based scoped web checks."),
    "zap_baseline": SecurityTool("zap_baseline", "OWASP ZAP Baseline", "zap-baseline.py", "web", "http", "medium", True, True, description="OWASP ZAP passive baseline scan."),
    "nikto": SecurityTool("nikto", "Nikto", "nikto", "web", "http", "medium", True, True, description="Scoped web server misconfiguration scan."),
}

PROFILE_TOOLS: dict[str, list[str]] = {
    "code_audit": ["secret_scan", "dependency_summary", "auth_session_review", "semgrep", "bandit", "gitleaks", "trivy_fs", "npm_audit", "pip_audit"],
    "auth_review": ["auth_session_review", "secret_scan", "semgrep"],
    "dependency_scan": ["dependency_summary", "npm_audit", "pip_audit", "safety", "trivy_fs"],
    "secret_scan": ["secret_scan", "gitleaks"],
    "web_owasp": ["web_headers", "nmap_web", "nuclei", "zap_baseline", "nikto"],
    "network_discovery": ["nmap_discovery"],
    "ctf_lab": ["nmap_discovery", "nmap_web", "nuclei", "web_headers"],
    "full_authorized": ["secret_scan", "dependency_summary", "auth_session_review", "semgrep", "bandit", "gitleaks", "trivy_fs", "npm_audit", "pip_audit", "web_headers", "nmap_discovery", "nmap_web", "nuclei", "zap_baseline"],
}


def init_db() -> None:
    ensure_runtime_dirs()
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS security_lab_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                root TEXT NOT NULL,
                target TEXT NOT NULL,
                profile TEXT NOT NULL,
                tools_json TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                artifact_dir TEXT NOT NULL,
                report_path TEXT NOT NULL,
                results_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def status() -> dict[str, Any]:
    init_db()
    tools = list_tools()
    ready = [tool for tool in tools if tool.get("available")]
    return {
        "enabled": True,
        "policy": {
            "scope_required": "Public/external targets require a verified scope. Local/private and CTF lab targets are allowed.",
            "execution": "Tools run with scrubbed environment, fixed argument builders, timeouts, logs, and artifacts.",
            "approval": "Approval-gated authority mode creates an approval item before tool execution.",
        },
        "tool_count": len(tools),
        "available_count": len(ready),
        "tools": tools,
        "profiles": [{"id": key, "tools": value} for key, value in PROFILE_TOOLS.items()],
        "recent_runs": recent_runs(limit=8),
        "scopes": capability_center.list_security_scopes(limit=12),
        "summary": f"{len(ready)} of {len(tools)} Security Lab tools are available.",
    }


def list_tools() -> list[dict[str, Any]]:
    return [_tool_payload(spec) for spec in TOOLS.values()]


def recent_runs(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM security_lab_runs ORDER BY id DESC LIMIT ?",
            (max(1, min(100, int(limit))),),
        ).fetchall()
    return [_run_from_row(row, include_results=False) for row in rows]


def get_run(run_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM security_lab_runs WHERE id = ?", (int(run_id),)).fetchone()
    return _run_from_row(row, include_results=True) if row else None


def run_scan(
    *,
    root: str | Path = "",
    target: str = "",
    profile: str = "auto",
    tools: list[str] | None = None,
    intensity: str = "safe",
    execution_mode: str = "host",
    timeout: int = 180,
    ctf_lab: bool = False,
    authorization_note: str = "",
    scope_id: int = 0,
    apply_fixes: bool = False,
) -> dict[str, Any]:
    init_db()
    selected = _select_tools(profile, tools, target=target)
    base = _safe_root(root)
    target_host = _host_from_target(target)
    normalized_execution = str(execution_mode or "host").strip().lower().replace("-", "_")
    if normalized_execution not in {"host", "local"} and not bool(config_value("security_lab_sandbox_enabled", False)):
        return {
            "ok": False,
            "status": "blocked_sandbox_unavailable",
            "execution_mode": normalized_execution,
            "summary": "A true Security Lab sandbox is not configured yet. Use host mode for scoped authorized scans.",
        }
    gate = _permission_gate(root=str(base), target=target_host or target, tools=selected)
    if gate:
        return gate
    auth = _target_authorization(target_host or target, scope_id=scope_id, ctf_lab=ctf_lab, authorization_note=authorization_note)
    blocked = [tool for tool in selected if TOOLS.get(tool, TOOLS["threat_model"]).requires_scope and not auth.get("authorized")]
    if blocked:
        return {
            "ok": False,
            "status": "blocked_for_scope",
            "target": target_host or target,
            "blocked_tools": blocked,
            "authorization": auth,
            "summary": "Add and verify a security scope before running network/web tools against this target.",
        }
    run_id = _create_run(base, target_host or target, profile, selected, metadata={"intensity": intensity, "execution_mode": normalized_execution, "ctf_lab": ctf_lab, "authorization": auth})
    artifact_dir = ARTIFACT_ROOT / f"run-{run_id:05d}"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for tool_id in selected:
        results.append(_run_tool(tool_id, root=base, target=target_host or target, artifact_dir=artifact_dir, timeout=timeout))
    remediation = remediation_plan(results, root=base, target=target_host or target, apply=apply_fixes)
    summary = _summary(results)
    report_path = artifact_dir / "security-lab-report.md"
    report_path.write_text(_report_markdown(run_id, base, target_host or target, selected, results, remediation, auth), encoding="utf-8")
    result_path = artifact_dir / "results.json"
    result_path.write_text(_json({"run_id": run_id, "results": results, "remediation": remediation, "authorization": auth}), encoding="utf-8")
    status_value = "done" if any(item.get("status") == "passed" or item.get("ok") for item in results) else "partial"
    _update_run(run_id, status=status_value, summary=summary, results=results, report_path=report_path, artifact_dir=artifact_dir, metadata={"remediation": remediation, "authorization": auth})
    run = get_run(run_id) or {}
    run["remediation"] = remediation
    return run


def generate_report(*, root: str | Path = "", target: str = "", run_id: int = 0) -> dict[str, Any]:
    if run_id:
        run = get_run(run_id)
        if run:
            return run
    return run_scan(root=root, target=target, profile="code_audit" if not target else "full_authorized", tools=[], timeout=120)


def hardening_plan(*, root: str | Path = "", target: str = "") -> dict[str, Any]:
    base = _safe_root(root)
    plan = capability_center.hardening_plan(target, root=base)
    threat = _threat_model(base, target)
    artifact_dir = ARTIFACT_ROOT / "hardening"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / f"hardening-plan-{_slug_time()}.md"
    path.write_text(_hardening_markdown(base, target, plan, threat), encoding="utf-8")
    return {"ok": True, "status": "done", "root": str(base), "target": _host_from_target(target), "path": str(path), "plan": plan, "threat_model": threat, "summary": plan.get("summary") or "Hardening plan generated."}


def remediate(*, run_id: int = 0, root: str | Path = "", target: str = "", apply: bool = False) -> dict[str, Any]:
    run = get_run(run_id) if run_id else None
    results = run.get("results", []) if run else []
    base = _safe_root(root or (run or {}).get("root", ""))
    resolved_target = target or (run or {}).get("target", "")
    plan = remediation_plan(results, root=base, target=resolved_target, apply=apply)
    artifact_dir = Path((run or {}).get("artifact_dir") or (ARTIFACT_ROOT / "remediation"))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / "security-remediation-plan.md"
    path.write_text(_remediation_markdown(base, resolved_target, plan), encoding="utf-8")
    return {"ok": True, "status": "done", "run_id": int(run_id or 0), "path": str(path), "remediation": plan, "summary": plan["summary"]}


def remediation_plan(results: list[dict[str, Any]], *, root: str | Path = "", target: str = "", apply: bool = False) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    for result in results:
        tool = result.get("tool") or result.get("tool_id")
        if result.get("status") in {"blocked_for_scope", "unavailable"}:
            actions.append({"tool": tool, "priority": "setup", "action": result.get("summary", "Resolve tool/setup gap.")})
        if tool in {"secret_scan", "gitleaks"} and _has_signal(result):
            actions.append({"tool": tool, "priority": "critical", "action": "Review possible leaked secrets, remove them from source, and rotate affected credentials."})
        if tool in {"npm_audit", "pip_audit", "safety", "trivy_fs", "dependency_summary"} and _has_signal(result):
            actions.append({"tool": tool, "priority": "high", "action": "Patch vulnerable dependencies, pin safe versions, and rerun dependency scans."})
        if tool in {"web_headers"} and _has_signal(result):
            actions.append({"tool": tool, "priority": "medium", "action": "Add missing CSP, HSTS, X-Content-Type-Options, and Referrer-Policy headers where applicable."})
        if tool in {"nmap_discovery", "nmap_web"} and result.get("ok"):
            actions.append({"tool": tool, "priority": "medium", "action": "Review exposed services and restrict admin/dev ports behind VPN, firewall, or private network controls."})
    if not actions:
        actions.append({"tool": "security_lab", "priority": "info", "action": "No urgent remediation action was inferred from this run."})
    return {
        "apply": bool(apply),
        "applied": False,
        "actions": actions,
        "summary": f"{len(actions)} remediation action(s) prepared. Automatic patching stays conservative and plan-first.",
    }


def _run_tool(tool_id: str, *, root: Path, target: str, artifact_dir: Path, timeout: int) -> dict[str, Any]:
    spec = TOOLS.get(tool_id)
    if spec is None:
        return {"tool_id": tool_id, "status": "unknown", "ok": False, "summary": "Unknown security tool."}
    if spec.internal:
        return _run_internal_tool(spec, root=root, target=target, artifact_dir=artifact_dir)
    exe = shutil.which(spec.executable)
    if not exe:
        return {"tool": spec.id, "label": spec.label, "status": "unavailable", "ok": False, "summary": f"{spec.executable} is not installed or not on PATH."}
    args, output_path = _tool_args(spec, exe, root=root, target=target, artifact_dir=artifact_dir)
    if spec.requires_target and not target:
        return {"tool": spec.id, "label": spec.label, "status": "missing_target", "ok": False, "summary": "This tool requires a target."}
    return _execute(args, cwd=root, timeout=timeout, artifact_dir=artifact_dir, output_path=output_path, tool=spec)


def _run_internal_tool(spec: SecurityTool, *, root: Path, target: str, artifact_dir: Path) -> dict[str, Any]:
    if spec.id == "secret_scan":
        payload = capability_center.project_secret_scan(root)
    elif spec.id == "dependency_summary":
        payload = capability_center.dependency_security_scan(root)
    elif spec.id == "web_headers":
        payload = capability_center.web_security_headers(target)
    elif spec.id == "hardening_plan":
        payload = capability_center.hardening_plan(target, root=root)
    elif spec.id == "auth_session_review":
        payload = _auth_session_review(root)
    elif spec.id == "threat_model":
        payload = _threat_model(root, target)
    else:
        payload = {"ok": False, "summary": "Internal tool is not implemented."}
    path = artifact_dir / f"{spec.id}.json"
    path.write_text(_json(payload), encoding="utf-8")
    return {"tool": spec.id, "label": spec.label, "status": "passed" if payload.get("ok", True) else "failed", "ok": bool(payload.get("ok", True)), "artifact": str(path), "summary": payload.get("summary", f"{spec.label} complete."), "payload": _compact_payload(payload)}


def _tool_args(spec: SecurityTool, exe: str, *, root: Path, target: str, artifact_dir: Path) -> tuple[list[str], Path]:
    safe_target = target
    if spec.id == "semgrep":
        output = artifact_dir / "semgrep.json"
        return [exe, "scan", "--config", "auto", "--json", "--output", str(output), "."], output
    if spec.id == "bandit":
        output = artifact_dir / "bandit.json"
        return [exe, "-r", ".", "-f", "json", "-o", str(output)], output
    if spec.id == "npm_audit":
        output = artifact_dir / "npm-audit.json"
        return [exe, "audit", "--json", "--audit-level=low"], output
    if spec.id == "pip_audit":
        output = artifact_dir / "pip-audit.json"
        req = root / "requirements.txt"
        args = [exe, "-f", "json", "-o", str(output)]
        if req.exists():
            args.extend(["-r", str(req)])
        return args, output
    if spec.id == "safety":
        output = artifact_dir / "safety.json"
        return [exe, "check", "--json"], output
    if spec.id == "gitleaks":
        output = artifact_dir / "gitleaks.json"
        return [exe, "detect", "--source", str(root), "--report-format", "json", "--report-path", str(output), "--no-banner"], output
    if spec.id == "trivy_fs":
        output = artifact_dir / "trivy-fs.json"
        return [exe, "fs", "--format", "json", "--output", str(output), str(root)], output
    if spec.id == "nmap_discovery":
        output = artifact_dir / "nmap-discovery.xml"
        return [exe, "-sV", "--version-light", "-T3", "--reason", "-oX", str(output), safe_target], output
    if spec.id == "nmap_web":
        output = artifact_dir / "nmap-web.xml"
        return [exe, "-sV", "--version-light", "--script", "http-title,http-headers,ssl-cert", "-p", "80,443,8080,8443", "-oX", str(output), safe_target], output
    if spec.id == "nuclei":
        output = artifact_dir / "nuclei.jsonl"
        return [exe, "-u", _web_url(safe_target), "-jsonl", "-o", str(output), "-severity", "low,medium,high,critical", "-silent"], output
    if spec.id == "zap_baseline":
        output = artifact_dir / "zap-baseline.json"
        return [exe, "-t", _web_url(safe_target), "-J", str(output)], output
    if spec.id == "nikto":
        output = artifact_dir / "nikto.json"
        return [exe, "-h", _web_url(safe_target), "-Format", "json", "-output", str(output)], output
    output = artifact_dir / f"{spec.id}.txt"
    return [exe], output


def _execute(args: list[str], *, cwd: Path, timeout: int, artifact_dir: Path, output_path: Path, tool: SecurityTool) -> dict[str, Any]:
    stdout_path = artifact_dir / f"{tool.id}.stdout.log"
    stderr_path = artifact_dir / f"{tool.id}.stderr.log"
    started = dt.datetime.now(dt.timezone.utc)
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=max(5, min(1800, int(timeout))),
            check=False,
            shell=False,
            env=command_runner.safe_environment(),
        )
        stdout_path.write_text(proc.stdout or "", encoding="utf-8", errors="replace")
        stderr_path.write_text(proc.stderr or "", encoding="utf-8", errors="replace")
        if tool.id in {"npm_audit", "safety"} and proc.stdout and not output_path.exists():
            output_path.write_text(proc.stdout, encoding="utf-8", errors="replace")
        duration_ms = int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000)
        ok = proc.returncode == 0
        return {
            "tool": tool.id,
            "label": tool.label,
            "status": "passed" if ok else "findings_or_error",
            "ok": ok,
            "returncode": proc.returncode,
            "duration_ms": duration_ms,
            "command": _redacted_command(args),
            "artifact": str(output_path) if output_path.exists() else "",
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "summary": _tool_summary(tool, proc.returncode, output_path, proc.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(str(exc.output or ""), encoding="utf-8", errors="replace")
        stderr_path.write_text(str(exc.stderr or "Timed out."), encoding="utf-8", errors="replace")
        return {"tool": tool.id, "label": tool.label, "status": "timeout", "ok": False, "command": _redacted_command(args), "stdout": str(stdout_path), "stderr": str(stderr_path), "summary": f"{tool.label} timed out after {timeout}s."}
    except Exception as exc:
        stderr_path.write_text(str(exc), encoding="utf-8", errors="replace")
        return {"tool": tool.id, "label": tool.label, "status": "failed", "ok": False, "command": _redacted_command(args), "stderr": str(stderr_path), "summary": f"{tool.label} failed: {exc}"}


def _permission_gate(*, root: str, target: str, tools: list[str]) -> dict[str, Any] | None:
    decision = permissions.evaluate("power_center", {"action": "security_lab_run", "root": root, "target": target, "tools": tools})
    if decision.get("blocked"):
        return {"ok": False, "status": "blocked", "permission": decision, "summary": "Security Lab is blocked by the current permission policy."}
    if decision.get("requires_confirmation"):
        approval = approval_inbox.create(
            kind="security_lab",
            title="Approve Security Lab run",
            summary=f"Run Security Lab tools: {', '.join(tools[:8])}.",
            source="security_lab",
            payload={"root": root, "target": target, "tools": tools},
        )
        return {"ok": False, "status": "blocked_for_approval", "permission": decision, "approval": approval, "summary": "Security Lab run requires approval or full-access authority mode."}
    return None


def _target_authorization(target: str, *, scope_id: int = 0, ctf_lab: bool = False, authorization_note: str = "") -> dict[str, Any]:
    if not target:
        return {"authorized": True, "reason": "No network target."}
    host = _host_from_target(target)
    if _is_local_or_private(host):
        return {"authorized": True, "reason": "Local/private target.", "host": host}
    if scope_id:
        scope = next((item for item in capability_center.list_security_scopes(limit=200) if int(item.get("id") or 0) == int(scope_id)), None)
        if scope and scope.get("status") == "verified" and scope.get("target") == host:
            return {"authorized": True, "reason": "Verified scope.", "host": host, "scope_id": scope_id}
    if capability_center.target_allowed(host):
        return {"authorized": True, "reason": "Previously verified scope.", "host": host}
    return {"authorized": False, "reason": "Target is not local/private and has no verified scope.", "host": host, "ctf_lab": bool(ctf_lab), "authorization_note": authorization_note[:400]}


def _select_tools(profile: str, tools: list[str] | None, *, target: str) -> list[str]:
    requested = [str(tool).strip() for tool in (tools or []) if str(tool).strip()]
    if requested:
        return [tool for tool in requested if tool in TOOLS]
    normalized = str(profile or "auto").strip().lower().replace("-", "_")
    if normalized == "auto":
        normalized = "full_authorized" if target else "code_audit"
    return [tool for tool in PROFILE_TOOLS.get(normalized, PROFILE_TOOLS["code_audit"]) if tool in TOOLS]


def _tool_payload(spec: SecurityTool) -> dict[str, Any]:
    available = spec.internal or bool(shutil.which(spec.executable))
    return {
        "id": spec.id,
        "label": spec.label,
        "category": spec.category,
        "surface": spec.surface,
        "risk": spec.risk,
        "requires_target": spec.requires_target,
        "requires_scope": spec.requires_scope,
        "internal": spec.internal,
        "executable": spec.executable,
        "available": available,
        "path": "" if spec.internal else (shutil.which(spec.executable) or ""),
        "description": spec.description,
    }


def _create_run(root: Path, target: str, profile: str, tools: list[str], metadata: dict[str, Any]) -> int:
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO security_lab_runs(created_at, updated_at, root, target, profile, tools_json, status, summary, artifact_dir, report_path, results_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, 'running', 'Security Lab run started.', '', '', '[]', ?)
            """,
            (now, now, str(root), target, profile, _json(tools), _json(metadata)),
        )
        return int(cursor.lastrowid)


def _update_run(run_id: int, *, status: str, summary: str, results: list[dict[str, Any]], report_path: Path, artifact_dir: Path, metadata: dict[str, Any]) -> None:
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            """
            UPDATE security_lab_runs
            SET updated_at=?, status=?, summary=?, artifact_dir=?, report_path=?, results_json=?, metadata_json=?
            WHERE id=?
            """,
            (_now(), status, summary, str(artifact_dir), str(report_path), _json(results), _json(metadata), int(run_id)),
        )


def _run_from_row(row: sqlite3.Row, *, include_results: bool) -> dict[str, Any]:
    results = _json_loads(row["results_json"], [])
    payload = {
        "id": int(row["id"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "root": row["root"],
        "target": row["target"],
        "profile": row["profile"],
        "tools": _json_loads(row["tools_json"], []),
        "status": row["status"],
        "summary": row["summary"],
        "artifact_dir": row["artifact_dir"],
        "report_path": row["report_path"],
        "metadata": _json_loads(row["metadata_json"], {}),
        "result_count": len(results),
    }
    if include_results:
        payload["results"] = results
    return payload


def _safe_root(root: str | Path = "") -> Path:
    candidate = resolve_coding_root(root)
    return candidate if candidate.exists() and candidate.is_dir() else resolve_coding_root()


def _host_from_target(target: str) -> str:
    text = str(target or "").strip()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"//{text}")
    host = parsed.hostname or text.split("/")[0].split(":")[0]
    return host.strip().lower()


def _web_url(target: str) -> str:
    text = str(target or "").strip()
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return f"https://{_host_from_target(text)}"


def _is_local_or_private(host: str) -> bool:
    host = _host_from_target(host)
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(socket.gethostbyname(host))
        return ip.is_loopback or ip.is_private or ip.is_link_local
    except Exception:
        return False


def _threat_model(root: Path, target: str = "") -> dict[str, Any]:
    files = {path.name.lower() for path in root.iterdir()} if root.exists() else set()
    stack = []
    if "package.json" in files:
        stack.append("node/javascript")
    if "requirements.txt" in files or "pyproject.toml" in files:
        stack.append("python")
    if "dockerfile" in files or "docker-compose.yml" in files:
        stack.append("containerized")
    assets = ["source code", "environment variables", "user/session data", "deployment credentials"]
    threats = [
        {"area": "auth/session", "risk": "Broken auth, weak session cookies, missing rate limits.", "control": "Review auth flows, cookie flags, CSRF protections, MFA/admin separation, and rate limits."},
        {"area": "input handling", "risk": "Injection, XSS, SSRF, path traversal, unsafe deserialization.", "control": "Validate inputs, use parameterized queries, sanitize rendered content, and restrict outbound fetches."},
        {"area": "secrets", "risk": "Credentials committed to source or exposed in logs.", "control": "Run Gitleaks/secret scans, rotate exposed keys, and keep secrets in a manager."},
        {"area": "dependencies", "risk": "Known vulnerable packages or abandoned libraries.", "control": "Run package audits, patch critical CVEs, and remove unused dependencies."},
        {"area": "deployment", "risk": "Public debug ports, weak headers, overbroad cloud permissions.", "control": "Use secure headers, private admin surfaces, least privilege, and monitored deploy logs."},
    ]
    return {"ok": True, "root": str(root), "target": _host_from_target(target), "stack": stack or ["unknown"], "assets": assets, "threats": threats, "summary": f"Threat model prepared with {len(threats)} risk area(s)."}


def _auth_session_review(root: Path) -> dict[str, Any]:
    skip_dirs = {".git", ".venv", "node_modules", ".next", "dist", "build", "__pycache__"}
    signals = {"auth": 0, "session": 0, "cookie": 0, "csrf": 0, "rate_limit": 0, "jwt": 0, "password_hash": 0}
    examples: dict[str, list[str]] = {key: [] for key in signals}
    patterns = {
        "auth": re.compile(r"\b(auth|login|signin|middleware)\b", re.I),
        "session": re.compile(r"\b(session|refresh[_-]?token)\b", re.I),
        "cookie": re.compile(r"\b(cookie|httponly|samesite|secure)\b", re.I),
        "csrf": re.compile(r"\b(csrf|xsrf)\b", re.I),
        "rate_limit": re.compile(r"\b(rate[_-]?limit|limiter|throttle|slowdown)\b", re.I),
        "jwt": re.compile(r"\b(jwt|jsonwebtoken|jose|bearer)\b", re.I),
        "password_hash": re.compile(r"\b(bcrypt|argon2|scrypt|pbkdf2)\b", re.I),
    }
    for path in _iter_source_files(root, skip_dirs=skip_dirs, limit=500):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:160000]
        except Exception:
            continue
        rel = str(path.relative_to(root))
        for key, pattern in patterns.items():
            if pattern.search(text):
                signals[key] += 1
                if len(examples[key]) < 6:
                    examples[key].append(rel)
    findings = []
    if signals["auth"] and not signals["rate_limit"]:
        findings.append("Auth/login surfaces were found, but no clear rate-limit/throttle signal was detected.")
    if signals["cookie"] and "samesite" not in json.dumps(examples).lower():
        findings.append("Cookie usage exists; manually verify HttpOnly, Secure, and SameSite flags.")
    if signals["jwt"] and not signals["session"]:
        findings.append("JWT usage exists; verify refresh-token rotation, revocation, expiry, and audience/issuer checks.")
    if not signals["auth"]:
        findings.append("No obvious auth surface detected; verify whether the app intentionally has no login/session boundary.")
    return {
        "ok": True,
        "signals": signals,
        "examples": examples,
        "findings": findings,
        "summary": f"Auth/session review found {len(findings)} follow-up item(s).",
    }


def _report_markdown(run_id: int, root: Path, target: str, tools: list[str], results: list[dict[str, Any]], remediation: dict[str, Any], auth: dict[str, Any]) -> str:
    lines = [
        "# Friday Security Lab Report",
        "",
        f"- Run ID: {run_id}",
        f"- Root: {root}",
        f"- Target: {target or 'none'}",
        f"- Authorization: {auth.get('reason', 'not recorded')}",
        f"- Tools: {', '.join(tools)}",
        "",
        "## Results",
        "",
    ]
    for result in results:
        lines.extend([
            f"### {result.get('label') or result.get('tool')}",
            f"- Status: {result.get('status')}",
            f"- Summary: {result.get('summary')}",
            f"- Artifact: {result.get('artifact') or result.get('stdout') or ''}",
            "",
        ])
    lines.extend(["## Remediation", ""])
    for action in remediation.get("actions") or []:
        lines.append(f"- [{action.get('priority')}] {action.get('action')}")
    lines.extend(["", "## Gaps", "", "- Findings from external tools require human review before business-impact claims."])
    return "\n".join(lines)


def _hardening_markdown(root: Path, target: str, plan: dict[str, Any], threat: dict[str, Any]) -> str:
    lines = ["# Security Hardening Plan", "", f"- Root: {root}", f"- Target: {_host_from_target(target) or 'none'}", "", "## Steps", ""]
    lines.extend(f"- {step}" for step in plan.get("steps") or [])
    lines.extend(["", "## Threat Model", ""])
    lines.extend(f"- {item.get('area')}: {item.get('control')}" for item in threat.get("threats") or [])
    return "\n".join(lines)


def _remediation_markdown(root: Path, target: str, plan: dict[str, Any]) -> str:
    lines = ["# Security Remediation Plan", "", f"- Root: {root}", f"- Target: {_host_from_target(target) or 'none'}", f"- Apply requested: {plan.get('apply')}", "", "## Actions", ""]
    for action in plan.get("actions") or []:
        lines.append(f"- [{action.get('priority')}] {action.get('tool')}: {action.get('action')}")
    lines.extend(["", "## Note", "", "Automatic source patches remain conservative; review this plan before changing production systems."])
    return "\n".join(lines)


def _iter_source_files(root: Path, *, skip_dirs: set[str], limit: int):
    suffixes = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".cs", ".php", ".rb", ".yaml", ".yml", ".json"}
    count = 0
    for path in root.rglob("*"):
        if count >= limit:
            break
        if any(part in skip_dirs for part in path.parts):
            continue
        if path.is_file() and path.suffix.lower() in suffixes:
            count += 1
            yield path


def _summary(results: list[dict[str, Any]]) -> str:
    unavailable = sum(1 for item in results if item.get("status") == "unavailable")
    passed = sum(1 for item in results if item.get("ok"))
    return f"Security Lab completed {len(results)} tool step(s): {passed} passed/clean, {unavailable} unavailable, {len(results) - passed - unavailable} with findings/errors."


def _tool_summary(tool: SecurityTool, returncode: int, output_path: Path, stderr: str) -> str:
    if output_path.exists():
        return f"{tool.label} finished with exit code {returncode}; artifact captured."
    if stderr:
        return f"{tool.label} finished with exit code {returncode}: {_tail(stderr, 240)}"
    return f"{tool.label} finished with exit code {returncode}."


def _has_signal(result: dict[str, Any]) -> bool:
    text = json.dumps(result, ensure_ascii=True, default=str).lower()
    return any(term in text for term in ("critical", "high", "secret", "vulnerab", "missing", "open_ports", "leak"))


def _compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(payload, ensure_ascii=True, default=str)
    if len(text) <= 6000:
        return payload
    return {"summary": payload.get("summary"), "truncated": True, "keys": sorted(payload.keys())}


def _redacted_command(args: list[str]) -> list[str]:
    return ["[redacted]" if re.search(r"(token|secret|password|key)", str(part), re.I) else str(part) for part in args]


def _tail(text: str, limit: int = 1000) -> str:
    return str(text or "")[-max(1, int(limit)):]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _slug_time() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")

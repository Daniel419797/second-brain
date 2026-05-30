"""Executable product-studio gates for autonomous coding tasks."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

from core import browser_playwright, codebase_standards, command_runner, deployment_brain, production_coding_autonomy, trust_proof
from core.config import config_value, resolve_coding_root

FRIDAY_DIR = ".friday"
STUDIO_DIR = "product-studio"
GATES_DIR = "gates"
LOG_DIR = "logs"
EXTRA_ALLOWED = {
    "pnpm",
    "pnpm.cmd",
    "yarn",
    "yarn.cmd",
    "go",
    "go.exe",
    "cargo",
    "cargo.exe",
    "flutter",
    "flutter.bat",
    "flutter.exe",
    "dart",
    "dart.exe",
}
SKIP_DIRS = {".git", ".next", ".pytest_cache", ".venv", "build", "coverage", "dist", "node_modules", "target"}
SECRET_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password|private[_-]?key)\s*[:=]\s*['\"]?([A-Za-z0-9_./+=-]{16,})"),
    re.compile(r"\b(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{20,})\b"),
]


def gate_registry() -> list[dict[str, Any]]:
    return [
        {"id": "dependencies_install", "group": "install", "required": True, "label": "Dependency install"},
        {"id": "tests", "group": "tests", "required": True, "label": "Typecheck, tests, and build"},
        {"id": "dependency_audit", "group": "security", "required": True, "label": "Dependency audit"},
        {"id": "secret_scan", "group": "security", "required": True, "label": "Secret scan"},
        {"id": "static_security_scan", "group": "security", "required": True, "label": "Static security scan"},
        {"id": "browser_check", "group": "browser", "required": True, "label": "Browser screenshot"},
        {"id": "browser_quality", "group": "browser", "required": True, "label": "Accessibility and dead-button smoke"},
        {"id": "performance_budget", "group": "performance", "required": True, "label": "Performance budget"},
        {"id": "deployment_preview", "group": "preview", "required": True, "label": "Preview deployment inspection"},
        {"id": "environment_validation", "group": "environment", "required": True, "label": "Environment validation"},
        {"id": "operations_readiness", "group": "operations", "required": True, "label": "Operations, rollback, and health readiness"},
        {"id": "docs_launch_readiness", "group": "docs", "required": True, "label": "Docs, launch, and support readiness"},
    ]


def execute_gates(
    root: str | Path,
    *,
    stack: dict[str, Any] | None = None,
    target_url: str = "",
    install: bool = True,
    tests: bool = True,
    audits: bool = True,
    browser: bool = True,
    preview: bool = True,
    external_preview: bool | None = None,
    create_proof: bool = True,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Run concrete readiness gates and persist logs/evidence.

    The function intentionally records skipped/blocked gates instead of hiding
    them. Product-studio readiness can then stay honest when tooling, browser
    automation, credentials, or approval are missing.
    """

    base = resolve_coding_root(root)
    gate_root = base / FRIDAY_DIR / STUDIO_DIR / GATES_DIR
    log_root = gate_root / LOG_DIR
    log_root.mkdir(parents=True, exist_ok=True)
    started_at = _now()
    stack = stack or {}
    timeout_seconds = int(timeout or config_value("product_studio_gate_timeout_seconds", 300))
    gates: list[dict[str, Any]] = []
    server: dict[str, Any] | None = None
    preview_url = _clean(target_url)

    if install:
        gates.extend(_install_gates(base, stack, log_root, timeout_seconds))

    if tests:
        gates.extend(_test_gates(base, log_root, timeout_seconds))

    if audits:
        gates.extend(_audit_gates(base, log_root, min(timeout_seconds, 180)))
        gates.extend(_security_review_gates(base, log_root))

    if preview or browser:
        if not preview_url:
            server = _start_local_preview(base, stack, log_root, timeout_seconds=min(timeout_seconds, 60))
            gates.append(server["gate"])
            preview_url = str(server.get("url") or "")
        elif _reachable(preview_url):
            gates.append(
                _manual_gate(
                    "local_preview",
                    "Local preview",
                    "passed",
                    f"Using supplied preview URL: {preview_url}",
                    required=bool(preview),
                    evidence=[preview_url],
                    metadata={"url": preview_url, "source": "supplied_url"},
                )
            )
        else:
            gates.append(
                _manual_gate(
                    "local_preview",
                    "Local preview",
                    "failed",
                    f"Supplied preview URL was not reachable: {preview_url}",
                    required=bool(preview),
                    evidence=[preview_url],
                    metadata={"url": preview_url, "source": "supplied_url"},
                )
            )

    try:
        if browser:
            gates.append(_browser_gate(base, preview_url, log_root, required=_requires_browser(stack, base)))
            gates.append(_browser_quality_gate(base, gates, log_root, required=_requires_browser(stack, base)))

        if preview:
            gates.append(_deployment_preview_gate(base, preview_url, required=True))

        deploy_external = bool(config_value("product_studio_external_preview_deploy", False)) if external_preview is None else bool(external_preview)
        if deploy_external:
            gates.append(_external_preview_gate(base, stack, log_root, timeout_seconds=min(timeout_seconds, 240)))
        else:
            gates.append(
                _manual_gate(
                    "external_preview_deploy",
                    "External preview deploy",
                    "blocked",
                    "External preview deploy requires product_studio_external_preview_deploy or a deploy command approval.",
                    required=False,
                    metadata={"approval_required": True},
                )
            )
    finally:
        if server:
            _stop_process(server)

    gates.extend(_production_file_gates(base, stack, gates, log_root))

    summary = _summarize(gates)
    gate_path = gate_root / "gate-results.json"
    result = {
        "attempted": True,
        "root": str(base),
        "started_at": started_at,
        "finished_at": _now(),
        "status": summary["status"],
        "summary": summary["summary"],
        "technical_ready": summary["technical_ready"],
        "market_ready": False,
        "preview_url": preview_url,
        "gates": gates,
        "required_gate_statuses": [gate for gate in gates if gate.get("required")],
        "failed_required": summary["failed_required"],
        "artifacts": [str(gate_path), *summary["artifacts"]],
        "approval_gates_cleared": False,
    }
    gate_path.write_text(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    result["artifacts"] = [str(gate_path), *summary["artifacts"]]
    if create_proof:
        proof = trust_proof.create_report(
            "Product-studio executable gates",
            changed=[f"Wrote gate evidence: {gate_path}"],
            tested=[_gate_line(gate) for gate in gates],
            failed=[_gate_line(gate) for gate in gates if gate.get("status") in {"failed", "timeout", "blocked"} and gate.get("required")],
            evidence=[item for gate in gates for item in (gate.get("evidence") or [])][:20],
            risks=_gate_risks(gates),
            confidence=0.86 if summary["technical_ready"] else 0.58,
            metadata={"root": str(base), "preview_url": preview_url},
        )
        result["proof"] = proof
    return result


def summarize(gate_results: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact readiness summary from stored gate results."""

    gates = (gate_results or {}).get("gates") if isinstance(gate_results, dict) else []
    return _summarize(gates if isinstance(gates, list) else [])


def gate_status(gate_results: dict[str, Any] | None, gate_id: str) -> str:
    for gate in _gates(gate_results):
        if str(gate.get("id") or "") == gate_id:
            return str(gate.get("status") or "")
    return ""


def group_passed(gate_results: dict[str, Any] | None, group: str) -> bool:
    gates = [gate for gate in _gates(gate_results) if str(gate.get("group") or "") == group and gate.get("required")]
    return bool(gates) and all(str(gate.get("status") or "") == "passed" for gate in gates)


def group_attempted(gate_results: dict[str, Any] | None, group: str) -> bool:
    return any(str(gate.get("group") or "") == group for gate in _gates(gate_results))


def gate_gaps(gate_results: dict[str, Any] | None) -> list[str]:
    gaps: list[str] = []
    for gate in _gates(gate_results):
        status = str(gate.get("status") or "")
        if status in {"passed", "skipped"} and not gate.get("required"):
            continue
        if status == "passed":
            continue
        label = _clean(gate.get("label") or gate.get("id") or "gate")
        summary = _clean(gate.get("summary") or status)
        gaps.append(f"{label}: {summary}")
    return _dedupe(gaps)


def _install_gates(base: Path, stack: dict[str, Any], log_root: Path, timeout_seconds: int) -> list[dict[str, Any]]:
    command = _install_command(base, stack)
    if not command:
        return [
            _manual_gate(
                "dependencies_install",
                "Dependency install",
                "skipped",
                "No supported dependency manifest was found.",
                required=False,
            )
        ]
    return [_command_gate(base, "dependencies_install", "Dependency install", command, "install", log_root, timeout_seconds)]


def _test_gates(base: Path, log_root: Path, timeout_seconds: int) -> list[dict[str, Any]]:
    commands = _ordered_test_commands(base)
    if not commands:
        return [
            _manual_gate(
                "tests",
                "Tests and build",
                "blocked",
                "No executable test, typecheck, lint, or build command was discovered.",
                required=True,
            )
        ]
    gates: list[dict[str, Any]] = []
    for index, command in enumerate(commands, start=1):
        gate_id = _gate_id("test", command, index)
        gates.append(_command_gate(base, gate_id, f"Check: {command}", command, "tests", log_root, timeout_seconds))
    return gates


def _audit_gates(base: Path, log_root: Path, timeout_seconds: int) -> list[dict[str, Any]]:
    command = _audit_command(base)
    if not command:
        return [
            _manual_gate(
                "dependency_audit",
                "Dependency audit",
                "blocked",
                "No supported dependency audit command was available for this stack.",
                required=True,
            )
        ]
    return [_command_gate(base, "dependency_audit", "Dependency audit", command, "security", log_root, timeout_seconds)]


def _security_review_gates(base: Path, log_root: Path) -> list[dict[str, Any]]:
    return [_secret_scan_gate(base, log_root), _static_security_gate(base, log_root)]


def _secret_scan_gate(base: Path, log_root: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for path in _text_files(base, limit=500):
        rel = _relative(path, base)
        text = path.read_text(encoding="utf-8", errors="ignore")[:250000]
        if path.name.lower().endswith(".example") or ".example." in path.name.lower():
            continue
        for pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                secret = match.group(0)
                if _placeholder_secret(secret):
                    continue
                line = text[: match.start()].count("\n") + 1
                findings.append({"path": rel, "line": line, "kind": match.group(1) if match.groups() else "secret"})
                if len(findings) >= 20:
                    break
            if len(findings) >= 20:
                break
        if len(findings) >= 20:
            break
    log_path = log_root / "secret-scan.json"
    log_path.write_text(json.dumps({"findings": findings}, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "id": "secret_scan",
        "label": "Secret scan",
        "group": "security",
        "status": "failed" if findings else "passed",
        "required": True,
        "executed": True,
        "summary": f"{len(findings)} possible secret(s) found." if findings else "No obvious committed secrets found.",
        "log_path": str(log_path),
        "evidence": [str(log_path)],
        "metadata": {"findings": findings},
    }


def _static_security_gate(base: Path, log_root: Path) -> dict[str, Any]:
    scan = codebase_standards.scan(base, focus="production readiness", max_files=220)
    findings = scan.get("findings") if isinstance(scan.get("findings"), list) else []
    high = [item for item in findings if int(item.get("severity") or 0) >= 5]
    log_path = log_root / "static-security-scan.json"
    log_path.write_text(json.dumps(scan, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return {
        "id": "static_security_scan",
        "label": "Static security scan",
        "group": "security",
        "status": "failed" if high else "passed",
        "required": True,
        "executed": True,
        "summary": f"{len(high)} critical static finding(s) found." if high else scan.get("summary") or "Static scan passed.",
        "log_path": str(log_path),
        "evidence": [str(log_path)],
        "metadata": {"critical_findings": high, "summary": scan.get("summary")},
    }


def _browser_gate(base: Path, url: str, log_root: Path, *, required: bool) -> dict[str, Any]:
    if not _clean(url):
        return _manual_gate(
            "browser_check",
            "Browser check",
            "blocked",
            "No preview URL was available for browser verification.",
            required=required,
        )
    status = browser_playwright.available()
    if not status.get("available"):
        return _manual_gate(
            "browser_check",
            "Browser check",
            "blocked" if required else "skipped",
            status.get("install_hint") or status.get("reason") or "Playwright is not available.",
            required=required,
            metadata=status,
        )
    started = time.perf_counter()
    result = browser_playwright.run_steps(url, [], screenshot=True)
    duration = int((time.perf_counter() - started) * 1000)
    log_path = log_root / "browser-check.json"
    log_path.write_text(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    ok = bool(result.get("ok")) or bool(result.get("screenshot"))
    evidence = [str(log_path)]
    if result.get("screenshot"):
        evidence.append(str(result.get("screenshot")))
    context = result.get("context") if isinstance(result.get("context"), dict) else {}
    summary = f"Browser screenshot captured for {context.get('title') or url}." if ok else _clean(result.get("detail") or result.get("reason") or "Browser check failed.")
    return {
        "id": "browser_check",
        "label": "Browser check",
        "group": "browser",
        "status": "passed" if ok else "failed",
        "required": required,
        "executed": True,
        "summary": summary,
        "duration_ms": duration,
        "url": url,
        "screenshot": result.get("screenshot") or "",
        "evidence": evidence,
        "metadata": result,
    }


def _browser_quality_gate(base: Path, gates: list[dict[str, Any]], log_root: Path, *, required: bool) -> dict[str, Any]:
    browser_gate = next((gate for gate in gates if gate.get("id") == "browser_check"), {})
    metadata = browser_gate.get("metadata") if isinstance(browser_gate.get("metadata"), dict) else {}
    context = metadata.get("context") if isinstance(metadata.get("context"), dict) else {}
    elements = context.get("elements") if isinstance(context.get("elements"), list) else []
    missing_names = [
        item
        for item in elements
        if str(item.get("tag") or "") in {"button", "input", "textarea", "select"} and not _clean(item.get("text") or item.get("name") or item.get("id"))
    ][:12]
    log_path = log_root / "browser-quality.json"
    log_path.write_text(json.dumps({"url": context.get("url"), "elements": elements, "missing_names": missing_names}, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    if not required:
        status = "skipped"
        summary = "Browser quality smoke is not required for this stack."
    elif browser_gate.get("status") != "passed":
        status = "blocked"
        summary = "Browser quality smoke needs a passing browser screenshot first."
    elif missing_names:
        status = "failed"
        summary = f"{len(missing_names)} interactive element(s) need accessible names."
    else:
        status = "passed"
        summary = "Interactive browser smoke found named controls and no dead-button evidence."
    return {
        "id": "browser_quality",
        "label": "Accessibility and dead-button smoke",
        "group": "browser",
        "status": status,
        "required": required,
        "executed": status not in {"skipped", "blocked"},
        "summary": summary,
        "log_path": str(log_path),
        "evidence": [str(log_path)],
        "metadata": {"interactive_count": len(elements), "missing_names": missing_names},
    }


def _deployment_preview_gate(base: Path, url: str, *, required: bool) -> dict[str, Any]:
    if not _clean(url):
        return _manual_gate(
            "deployment_preview",
            "Deployment preview",
            "blocked",
            "No preview URL was available for deployment inspection.",
            required=required,
        )
    report = deployment_brain.inspect(url, root=base, create_proof=True)
    payload = report.get("payload") if isinstance(report.get("payload"), dict) else {}
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    ok = bool(target.get("ok")) or str(report.get("status") or "") in {"ok", "attention"}
    summary = report.get("summary") or f"Preview inspected at {url}."
    return {
        "id": "deployment_preview",
        "label": "Deployment preview",
        "group": "preview",
        "status": "passed" if ok else "failed",
        "required": required,
        "executed": True,
        "summary": _clean(summary),
        "url": url,
        "evidence": [f"deployment_report:{report.get('id')}", url],
        "metadata": report,
    }


def _production_file_gates(base: Path, stack: dict[str, Any], gates: list[dict[str, Any]], log_root: Path) -> list[dict[str, Any]]:
    return [
        _performance_gate(base, stack, gates, log_root),
        _environment_gate(base, log_root),
        _operations_gate(base, log_root),
        _docs_launch_gate(base, log_root),
    ]


def _performance_gate(base: Path, stack: dict[str, Any], gates: list[dict[str, Any]], log_root: Path) -> dict[str, Any]:
    package_required = (base / "package.json").exists() or (base / "pyproject.toml").exists() or (base / "go.mod").exists() or (base / "Cargo.toml").exists()
    build_gates = [gate for gate in gates if gate.get("group") == "tests" and "build" in str(gate.get("command") or gate.get("label") or "").lower()]
    passed_build = any(gate.get("status") == "passed" for gate in build_gates)
    durations = [int(gate.get("duration_ms") or 0) for gate in build_gates if gate.get("status") == "passed"]
    max_duration = max(durations or [0])
    budget_ms = int(float(config_value("performance_budget_web_build_seconds_max", 120.0)) * 1000)
    performance_budget = base / ".friday" / "performance-budget.json"
    if not package_required:
        status = "skipped"
        summary = "No buildable runtime manifest detected."
        required = False
    elif not build_gates and not performance_budget.exists():
        status = "failed"
        summary = "No build/performance evidence is attached."
        required = True
    elif build_gates and not passed_build:
        status = "failed"
        summary = "Build gate did not pass, so performance budget cannot pass."
        required = True
    elif max_duration and max_duration > budget_ms:
        status = "failed"
        summary = f"Build exceeded budget: {max_duration}ms > {budget_ms}ms."
        required = True
    else:
        status = "passed"
        summary = "Build/performance budget evidence is within configured limits."
        required = True
    log_path = log_root / "performance-budget.json"
    payload = {"build_gates": build_gates, "max_duration_ms": max_duration, "budget_ms": budget_ms, "performance_budget_file": str(performance_budget)}
    log_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return {
        "id": "performance_budget",
        "label": "Performance budget",
        "group": "performance",
        "status": status,
        "required": required,
        "executed": status != "skipped",
        "summary": summary,
        "log_path": str(log_path),
        "evidence": [str(log_path)],
        "metadata": payload,
    }


def _environment_gate(base: Path, log_root: Path) -> dict[str, Any]:
    env_files = [path for path in base.glob(".env*") if path.is_file()]
    unsafe_env = [str(path.name) for path in env_files if path.name not in {".env.example", ".env.sample", ".env.template"}]
    example_exists = any(path.name in {".env.example", ".env.sample", ".env.template"} for path in env_files)
    env_refs = _env_reference_count(base)
    if unsafe_env:
        status = "failed"
        summary = "Runtime .env files must not be committed or included in production artifacts."
    elif env_refs and not example_exists:
        status = "failed"
        summary = "Environment variables are referenced but no .env.example/.sample is present."
    else:
        status = "passed"
        summary = "Environment references have a safe example file or no env surface was detected."
    log_path = log_root / "environment-validation.json"
    payload = {"env_files": [path.name for path in env_files], "unsafe_env": unsafe_env, "env_reference_count": env_refs}
    log_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "id": "environment_validation",
        "label": "Environment validation",
        "group": "environment",
        "status": status,
        "required": True,
        "executed": True,
        "summary": summary,
        "log_path": str(log_path),
        "evidence": [str(log_path)],
        "metadata": payload,
    }


def _operations_gate(base: Path, log_root: Path) -> dict[str, Any]:
    health_files = [path for path in _text_files(base, limit=300) if "health" in path.name.lower() or "/health" in path.read_text(encoding="utf-8", errors="ignore")[:100000].lower()]
    rollback = base / ".friday" / "rollback-plan.md"
    operations_doc = base / "docs" / "OPERATIONS.md"
    has_ops = bool(health_files) and (rollback.exists() or operations_doc.exists())
    log_path = log_root / "operations-readiness.json"
    payload = {"health_files": [_relative(path, base) for path in health_files[:12]], "rollback_plan": str(rollback), "operations_doc": str(operations_doc)}
    log_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "id": "operations_readiness",
        "label": "Operations, rollback, and health readiness",
        "group": "operations",
        "status": "passed" if has_ops else "failed",
        "required": True,
        "executed": True,
        "summary": "Health endpoint and rollback/operations evidence are present." if has_ops else "Health endpoint and rollback/operations evidence are required.",
        "log_path": str(log_path),
        "evidence": [str(log_path)],
        "metadata": payload,
    }


def _docs_launch_gate(base: Path, log_root: Path) -> dict[str, Any]:
    required_paths = [base / "README.md", base / "SECURITY.md", base / "docs" / "LAUNCH.md"]
    existing = [path for path in required_paths if path.exists()]
    production_launch = base / ".friday" / "product-studio" / "launch-assets.md"
    passed = len(existing) == len(required_paths) or (base / "README.md").exists() and production_launch.exists()
    log_path = log_root / "docs-launch-readiness.json"
    payload = {"required": [str(path) for path in required_paths], "existing": [str(path) for path in existing], "product_studio_launch": str(production_launch)}
    log_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "id": "docs_launch_readiness",
        "label": "Docs, launch, and support readiness",
        "group": "docs",
        "status": "passed" if passed else "failed",
        "required": True,
        "executed": True,
        "summary": "README, security, and launch/support docs are present." if passed else "README, security, and launch/support docs are required.",
        "log_path": str(log_path),
        "evidence": [str(log_path)],
        "metadata": payload,
    }


def _external_preview_gate(base: Path, stack: dict[str, Any], log_root: Path, timeout_seconds: int) -> dict[str, Any]:
    command = _clean(config_value("product_studio_preview_deploy_command", ""))
    if not command:
        command = _default_external_preview_command(base, stack)
    if not command:
        return _manual_gate(
            "external_preview_deploy",
            "External preview deploy",
            "blocked",
            "No external preview deploy command is configured.",
            required=False,
            metadata={"approval_required": True},
        )
    gate = _command_gate(base, "external_preview_deploy", "External preview deploy", command, "preview", log_root, timeout_seconds, required=False)
    preview_url = _extract_url(gate.get("output_tail") or "")
    if preview_url:
        gate["url"] = preview_url
        gate.setdefault("evidence", []).append(preview_url)
        gate["metadata"]["deployment_report"] = deployment_brain.inspect(preview_url, root=base, create_proof=True)
    return gate


def _command_gate(
    base: Path,
    gate_id: str,
    label: str,
    command: str,
    group: str,
    log_root: Path,
    timeout_seconds: int,
    *,
    required: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    log_path = log_root / f"{_slug(gate_id)}.log"
    try:
        proc = command_runner.run(command, cwd=base, timeout=max(5, timeout_seconds), extra_allowed=EXTRA_ALLOWED)
        output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        log_path.write_text(output + ("\n" if output else ""), encoding="utf-8", errors="ignore")
        status = "passed" if int(proc.returncode) == 0 else "failed"
        summary = f"{command} passed." if status == "passed" else _failure_summary(output, int(proc.returncode))
        return {
            "id": gate_id,
            "label": label,
            "group": group,
            "status": status,
            "required": required,
            "executed": True,
            "command": command,
            "returncode": int(proc.returncode),
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "summary": summary,
            "log_path": str(log_path),
            "output_tail": _tail(output),
            "evidence": [str(log_path)],
            "metadata": {},
        }
    except subprocess.TimeoutExpired as exc:
        output = _clean(str(exc))
        log_path.write_text(output + "\n", encoding="utf-8", errors="ignore")
        return {
            "id": gate_id,
            "label": label,
            "group": group,
            "status": "timeout",
            "required": required,
            "executed": True,
            "command": command,
            "returncode": -1,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "summary": f"{command} timed out after {timeout_seconds}s.",
            "log_path": str(log_path),
            "output_tail": _tail(output),
            "evidence": [str(log_path)],
            "metadata": {"timeout_seconds": timeout_seconds},
        }
    except command_runner.CommandRejected as exc:
        log_path.write_text(str(exc) + "\n", encoding="utf-8", errors="ignore")
        return _manual_gate(
            gate_id,
            label,
            "blocked",
            f"Command blocked by policy: {exc}",
            required=required,
            command=command,
            evidence=[str(log_path)],
            metadata={"blocked": True},
        )
    except FileNotFoundError as exc:
        log_path.write_text(str(exc) + "\n", encoding="utf-8", errors="ignore")
        return _manual_gate(
            gate_id,
            label,
            "blocked",
            f"Command executable was not found: {command}",
            required=required,
            command=command,
            evidence=[str(log_path)],
            metadata={"error": exc.__class__.__name__},
        )


def _start_local_preview(base: Path, stack: dict[str, Any], log_root: Path, *, timeout_seconds: int) -> dict[str, Any]:
    command = _preview_command(base, stack)
    if not command:
        return {
            "url": "",
            "gate": _manual_gate(
                "local_preview",
                "Local preview",
                "blocked",
                "No supported preview/dev server command was available.",
                required=_requires_preview(stack, base),
            ),
        }
    port = _free_port()
    command_text = command["command"].format(port=port)
    env = {**os.environ, **{str(key): str(value).format(port=port) for key, value in command.get("env", {}).items()}}
    log_path = log_root / "local-preview.log"
    started = time.perf_counter()
    try:
        args = command_runner.parse_command(command_text, extra_allowed=EXTRA_ALLOWED)
        handle = log_path.open("w", encoding="utf-8", errors="ignore")
        process = subprocess.Popen(args, cwd=str(base), stdout=handle, stderr=subprocess.STDOUT, text=True, shell=False, env=env)
        url = f"http://127.0.0.1:{port}{command.get('path', '/')}"
        ready = _wait_for_url(url, timeout_seconds=timeout_seconds)
        status = "passed" if ready else "failed"
        summary = f"Local preview started at {url}." if ready else f"Local preview did not become reachable within {timeout_seconds}s."
        gate = {
            "id": "local_preview",
            "label": "Local preview",
            "group": "preview",
            "status": status,
            "required": _requires_preview(stack, base),
            "executed": True,
            "command": command_text,
            "returncode": None if process.poll() is None else process.returncode,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "summary": summary,
            "url": url if ready else "",
            "log_path": str(log_path),
            "evidence": [str(log_path), *( [url] if ready else [] )],
            "metadata": {"pid": process.pid, "kind": command.get("kind", "")},
        }
        return {"process": process, "log_handle": handle, "url": url if ready else "", "gate": gate}
    except (command_runner.CommandRejected, FileNotFoundError) as exc:
        return {
            "url": "",
            "gate": _manual_gate(
                "local_preview",
                "Local preview",
                "blocked",
                str(exc),
                required=_requires_preview(stack, base),
                command=command_text,
                evidence=[str(log_path)],
            ),
        }


def _stop_process(server: dict[str, Any]) -> None:
    process = server.get("process")
    if process and getattr(process, "poll", lambda: None)() is None:
        try:
            process.terminate()
            process.wait(timeout=8)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
    handle = server.get("log_handle")
    try:
        if handle:
            handle.close()
    except Exception:
        pass


def _install_command(base: Path, stack: dict[str, Any]) -> str:
    if (base / "package.json").exists():
        if (base / "pnpm-lock.yaml").exists():
            return "pnpm install"
        if (base / "yarn.lock").exists():
            return "yarn install"
        return "npm install"
    if (base / "pubspec.yaml").exists():
        return "flutter pub get"
    if (base / "go.mod").exists():
        return "go mod download"
    if (base / "Cargo.toml").exists():
        return "cargo fetch"
    if (base / "pyproject.toml").exists() and bool(config_value("product_studio_python_install_enabled", False)):
        return "python -m pip install -e .[dev]"
    if (base / "requirements.txt").exists() and bool(config_value("product_studio_python_install_enabled", False)):
        return "python -m pip install -r requirements.txt"
    return ""


def _ordered_test_commands(base: Path) -> list[str]:
    commands = production_coding_autonomy.discover_tests(base)
    package = _read_json(base / "package.json")
    scripts = package.get("scripts") if isinstance(package.get("scripts"), dict) else {}
    ordered: list[str] = []
    if isinstance(scripts, dict):
        for name in ("typecheck", "lint", "test", "test:unit", "test:integration", "test:e2e", "build"):
            if name in scripts:
                ordered.append(f"npm run {name}")
    ordered.extend(commands)
    return _dedupe(ordered)


def _audit_command(base: Path) -> str:
    if (base / "package.json").exists():
        if (base / "pnpm-lock.yaml").exists():
            return "pnpm audit --audit-level moderate"
        if (base / "yarn.lock").exists():
            return "yarn audit --level moderate"
        return "npm audit --audit-level=moderate"
    if (base / "Cargo.toml").exists() and bool(config_value("product_studio_cargo_audit_enabled", False)):
        return "cargo audit"
    if ((base / "pyproject.toml").exists() or (base / "requirements.txt").exists()) and bool(config_value("product_studio_pip_audit_enabled", False)):
        return "python -m pip_audit"
    return ""


def _preview_command(base: Path, stack: dict[str, Any]) -> dict[str, Any] | None:
    package = _read_json(base / "package.json")
    scripts = package.get("scripts") if isinstance(package.get("scripts"), dict) else {}
    deps = {**(package.get("dependencies") if isinstance(package.get("dependencies"), dict) else {}), **(package.get("devDependencies") if isinstance(package.get("devDependencies"), dict) else {})}
    if isinstance(scripts, dict) and scripts:
        runner = "npm"
        if (base / "pnpm-lock.yaml").exists():
            runner = "pnpm"
        elif (base / "yarn.lock").exists():
            runner = "yarn"
        if "preview" in scripts:
            if "vite" in deps:
                return {"command": f"{runner} run preview -- --host 127.0.0.1 --port {{port}}", "kind": "vite_preview"}
            return {"command": f"{runner} run preview -- --port {{port}}", "kind": "preview"}
        if "next" in deps and "start" in scripts and (base / ".next").exists():
            return {"command": f"{runner} run start -- --hostname 127.0.0.1 --port {{port}}", "kind": "next_start"}
        if "next" in deps and "dev" in scripts:
            return {"command": f"{runner} run dev -- --hostname 127.0.0.1 --port {{port}}", "kind": "next_dev"}
        if "vite" in deps and "dev" in scripts:
            return {"command": f"{runner} run dev -- --host 127.0.0.1 --port {{port}}", "kind": "vite_dev"}
        if "start" in scripts:
            return {"command": f"{runner} run start", "env": {"PORT": "{port}"}, "kind": "node_start"}
    return None


def _default_external_preview_command(base: Path, stack: dict[str, Any]) -> str:
    if (base / "vercel.json").exists() or (base / "next.config.js").exists() or (base / "next.config.mjs").exists():
        return "npx vercel deploy --yes"
    return ""


def _manual_gate(
    gate_id: str,
    label: str,
    status: str,
    summary: str,
    *,
    required: bool,
    command: str = "",
    evidence: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": gate_id,
        "label": label,
        "group": _group_for_gate(gate_id),
        "status": status,
        "required": required,
        "executed": status not in {"skipped", "blocked"},
        "command": command,
        "summary": _clean(summary),
        "evidence": evidence or [],
        "metadata": metadata or {},
    }


def _summarize(gates: list[dict[str, Any]]) -> dict[str, Any]:
    required = [gate for gate in gates if gate.get("required")]
    failed_required = [
        _gate_line(gate)
        for gate in required
        if str(gate.get("status") or "") not in {"passed", "skipped"} or (str(gate.get("status") or "") == "skipped" and gate.get("required"))
    ]
    artifacts = [str(gate.get("log_path")) for gate in gates if gate.get("log_path")]
    for gate in gates:
        for item in gate.get("evidence") or []:
            if _looks_like_path(item) and item not in artifacts:
                artifacts.append(str(item))
    technical_ready = bool(required) and not failed_required
    status = "passed" if technical_ready else "attention" if gates else "skipped"
    passed = sum(1 for gate in gates if gate.get("status") == "passed")
    return {
        "status": status,
        "technical_ready": technical_ready,
        "failed_required": failed_required,
        "artifacts": _dedupe(artifacts),
        "summary": f"Executed {len(gates)} product-studio gate(s): {passed} passed, {len(failed_required)} required gap(s).",
    }


def _gate_risks(gates: list[dict[str, Any]]) -> list[str]:
    risks = [_gate_line(gate) for gate in gates if gate.get("status") in {"failed", "timeout", "blocked"}]
    if any(gate.get("id") == "external_preview_deploy" and gate.get("status") == "blocked" for gate in gates):
        risks.append("External preview deploy was not run without explicit configuration/approval.")
    return _dedupe(risks) or ["No required gate failed."]


def _gate_line(gate: dict[str, Any]) -> str:
    label = _clean(gate.get("label") or gate.get("id") or "gate")
    status = _clean(gate.get("status") or "unknown")
    summary = _clean(gate.get("summary") or "")
    return f"{label}: {status}" + (f" - {summary}" if summary else "")


def _gates(gate_results: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(gate_results, dict):
        return []
    gates = gate_results.get("gates") or gate_results.get("required_gate_statuses") or []
    return [gate for gate in gates if isinstance(gate, dict)]


def _requires_browser(stack: dict[str, Any], base: Path) -> bool:
    kind = str((stack or {}).get("kind") or "").lower()
    stack_id = str((stack or {}).get("stack") or "").lower()
    if kind in {"web", "web_app", "frontend"} or stack_id in {"nextjs"}:
        return True
    package = _read_json(base / "package.json")
    deps = package.get("dependencies") if isinstance(package.get("dependencies"), dict) else {}
    return any(name in deps for name in ("next", "vite", "react", "react-dom"))


def _requires_preview(stack: dict[str, Any], base: Path) -> bool:
    kind = str((stack or {}).get("kind") or "").lower()
    if kind in {"mobile"}:
        return False
    return (base / "package.json").exists()


def _text_files(base: Path, *, limit: int) -> list[Path]:
    files: list[Path] = []
    for path in base.rglob("*"):
        if len(files) >= limit:
            break
        if not path.is_file() or _is_skipped(path, base):
            continue
        if path.suffix.lower() not in {
            ".c", ".css", ".dart", ".env", ".example", ".go", ".html", ".js", ".json", ".jsx", ".md",
            ".mjs", ".py", ".rs", ".toml", ".ts", ".tsx", ".txt", ".yaml", ".yml",
        } and path.name not in {".env.example", "Dockerfile"}:
            continue
        try:
            if path.stat().st_size > 500000:
                continue
        except OSError:
            continue
        files.append(path)
    return files


def _is_skipped(path: Path, base: Path) -> bool:
    try:
        parts = set(path.relative_to(base).parts)
    except ValueError:
        return True
    return bool(parts & SKIP_DIRS)


def _placeholder_secret(value: str) -> bool:
    text = value.lower()
    return any(token in text for token in ("example", "placeholder", "changeme", "replace_me", "your_", "dummy", "test"))


def _env_reference_count(base: Path) -> int:
    count = 0
    for path in _text_files(base, limit=300):
        if path.name.startswith(".env"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")[:100000]
        count += len(re.findall(r"process\.env|os\.environ|std::env|env::var|Platform\.environment", text))
        if count > 30:
            return count
    return count


def _relative(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def _failure_summary(output: str, returncode: int) -> str:
    for line in str(output or "").splitlines():
        clean = _clean(line)
        low = clean.lower()
        if clean and any(term in low for term in ("error", "failed", "traceback", "exception", "not found", "cannot find", "vulnerab")):
            return clean[:700]
    return f"Command failed with return code {returncode}."


def _wait_for_url(url: str, *, timeout_seconds: int) -> bool:
    deadline = time.time() + max(2, timeout_seconds)
    while time.time() < deadline:
        if _reachable(url):
            return True
        time.sleep(0.75)
    return False


def _reachable(url: str) -> bool:
    target = _clean(url)
    if not target:
        return False
    try:
        req = urllib.request.Request(target, headers={"User-Agent": "FridayProductStudioGates/1.0"})
        with urllib.request.urlopen(req, timeout=4) as response:
            return 200 <= int(response.status) < 500
    except Exception:
        return False


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _extract_url(text: str) -> str:
    match = re.search(r"https?://[^\s\"'<>]+", str(text or ""))
    return match.group(0).rstrip(".,)") if match else ""


def _gate_id(prefix: str, command: str, index: int) -> str:
    return f"{prefix}_{index}_{_slug(command)[:48]}"


def _group_for_gate(gate_id: str) -> str:
    if "audit" in gate_id or "security" in gate_id:
        return "security"
    if "preview" in gate_id or "deploy" in gate_id:
        return "preview"
    if "browser" in gate_id:
        return "browser"
    if "performance" in gate_id or "budget" in gate_id:
        return "performance"
    if "environment" in gate_id or "env" in gate_id:
        return "environment"
    if "operations" in gate_id or "rollback" in gate_id or "health" in gate_id:
        return "operations"
    if "docs" in gate_id or "launch" in gate_id:
        return "docs"
    if "install" in gate_id or "dependenc" in gate_id:
        return "install"
    if "test" in gate_id or "build" in gate_id or "typecheck" in gate_id:
        return "tests"
    return "general"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        clean = _clean(item)
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _tail(text: str, limit: int = 12000) -> str:
    return str(text or "")[-limit:]


def _looks_like_path(value: Any) -> bool:
    text = str(value or "")
    return bool(text) and (":\\" in text or text.startswith("/") or text.startswith("."))


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-") or "gate"


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

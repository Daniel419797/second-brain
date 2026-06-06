"""Executable product-studio gates for autonomous coding tasks."""

from __future__ import annotations

import datetime as dt
import json
import re
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from core import browser_playwright, codebase_standards, command_runner, deployment_brain, design_providers, production_coding_autonomy, project_scaffolds, trust_proof, web_project_contract
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
SKIP_DIRS = {".friday", ".git", ".next", ".pytest_cache", ".venv", "build", "coverage", "dist", "node_modules", "target"}
SECRET_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password|private[_-]?key)\s*[:=]\s*['\"]?([A-Za-z0-9_./+=-]{16,})"),
    re.compile(r"\b(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{20,})\b"),
]


def gate_registry() -> list[dict[str, Any]]:
    return [
        _gate_definition("dependencies_install", "install", "Dependency install", dependencies=[]),
        _gate_definition("tests", "tests", "Typecheck, tests, and build", dependencies=["dependencies_install"]),
        _gate_definition("dependency_audit", "security", "Dependency audit", dependencies=["dependencies_install"]),
        _gate_definition("secret_scan", "security", "Secret scan", dependencies=[]),
        _gate_definition("static_security_scan", "security", "Static security scan", dependencies=[]),
        _gate_definition("browser_check", "browser", "Browser screenshot", dependencies=["dependencies_install", "local_preview"]),
        _gate_definition("browser_quality", "browser", "Accessibility and dead-button smoke", dependencies=["browser_check"]),
        _gate_definition("browser_visual_review", "browser", "Rendered UI visual review", dependencies=["browser_check"]),
        _gate_definition("performance_budget", "performance", "Performance budget", dependencies=["browser_check", "tests"]),
        _gate_definition("deployment_preview", "preview", "Preview deployment inspection", dependencies=["tests", "browser_check"]),
        _gate_definition("product_domain_fit", "product", "Product/domain fit", dependencies=[]),
        _gate_definition("ux_copy_quality", "product", "UX and copy quality", dependencies=[]),
        _gate_definition("environment_validation", "environment", "Environment validation", dependencies=[]),
        _gate_definition("operations_readiness", "operations", "Operations, rollback, and health readiness", dependencies=[]),
        _gate_definition("docs_launch_readiness", "docs", "Docs, launch, and support readiness", dependencies=[]),
    ]


def _gate_definition(gate_id: str, group: str, label: str, *, dependencies: list[str]) -> dict[str, Any]:
    return {
        "id": gate_id,
        "group": group,
        "required": True,
        "required_for": ["production", "technical_ready"],
        "label": label,
        "dependencies": dependencies,
        "blocks_readiness": True,
        "evidence_schema": {
            "status": "passed|failed|blocked|timeout|skipped",
            "summary": "human-readable result",
            "log_path": "optional proof log path",
            "evidence": "list of artifact paths or preview URLs",
        },
    }


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
    request: str = "",
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
    timeout_seconds = int(timeout or config_value("product_studio_gate_timeout_seconds", 600))
    gates: list[dict[str, Any]] = []
    server: dict[str, Any] | None = None
    preview_url = _clean(target_url)

    if install:
        gates.extend(_install_gates(base, stack, log_root, timeout_seconds))
    dependency_ready = _dependency_install_ready(gates)

    if tests:
        if dependency_ready:
            gates.extend(_test_gates(base, log_root, timeout_seconds))
        else:
            gates.append(
                _manual_gate(
                    "tests",
                    "Tests and build",
                    "blocked",
                    "Dependency install did not pass, so test/build commands were not run.",
                    required=True,
                    metadata={"blocked_by": "dependencies_install"},
                )
            )

    if audits:
        if dependency_ready:
            gates.extend(_audit_gates(base, log_root, min(timeout_seconds, 180)))
        else:
            gates.append(
                _manual_gate(
                    "dependency_audit",
                    "Dependency audit",
                    "blocked",
                    "Dependency install did not pass, so dependency audit was not run.",
                    required=True,
                    metadata={"blocked_by": "dependencies_install"},
                )
            )
        gates.extend(_security_review_gates(base, log_root))

    if preview or browser:
        if not dependency_ready:
            gates.append(
                _manual_gate(
                    "local_preview",
                    "Local preview",
                    "blocked",
                    "Dependency install did not pass, so local preview was not launched.",
                    required=bool(preview),
                    metadata={"blocked_by": "dependencies_install"},
                )
            )
        elif not preview_url:
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
            browser_required = _requires_browser(stack, base)
            browser_gate = _browser_gate(base, preview_url, log_root, required=browser_required)
            gates.append(browser_gate)
            visual_gate = _browser_visual_review_gate(base, preview_url, log_root, required=browser_required, request=request)
            recovered_browser_gate = _recover_browser_gate_from_visual_review(browser_gate, visual_gate, log_root)
            if recovered_browser_gate:
                gates[-1] = recovered_browser_gate
                browser_gate = recovered_browser_gate
            gates.append(_browser_quality_gate(base, gates, log_root, required=browser_required, request=request))
            gates.append(visual_gate)

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

    gates.extend(_production_file_gates(base, stack, gates, log_root, request=request))

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


def _dependency_install_ready(gates: list[dict[str, Any]]) -> bool:
    install_gates = [gate for gate in gates if gate.get("id") == "dependencies_install" and gate.get("required")]
    return not install_gates or all(str(gate.get("status") or "") == "passed" for gate in install_gates)


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
    status = browser_playwright.ensure_available(log_root)
    if not status.get("available"):
        return _manual_gate(
            "browser_check",
            "Browser check",
            "blocked" if required else "skipped",
            status.get("install_hint") or status.get("reason") or "Playwright is not available.",
            required=required,
            evidence=status.get("install_logs") or [],
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


def _browser_quality_gate(base: Path, gates: list[dict[str, Any]], log_root: Path, *, required: bool, request: str = "") -> dict[str, Any]:
    browser_gate = next((gate for gate in gates if gate.get("id") == "browser_check"), {})
    metadata = browser_gate.get("metadata") if isinstance(browser_gate.get("metadata"), dict) else {}
    context = metadata.get("context") if isinstance(metadata.get("context"), dict) else {}
    elements = context.get("elements") if isinstance(context.get("elements"), list) else []
    route_smoke = (
        _browser_route_smoke(str(context.get("url") or browser_gate.get("url") or ""), elements, log_root, request=request)
        if browser_gate.get("status") == "passed"
        else {"status": "blocked", "steps": []}
    )
    missing_names = [
        item
        for item in elements
        if str(item.get("tag") or "") in {"button", "input", "textarea", "select"} and not _clean(item.get("text") or item.get("name") or item.get("id"))
    ][:12]
    log_path = log_root / "browser-quality.json"
    log_path.write_text(
        json.dumps(
            {"url": context.get("url"), "elements": elements, "missing_names": missing_names, "route_smoke": route_smoke},
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    if not required:
        status = "skipped"
        summary = "Browser quality smoke is not required for this stack."
    elif browser_gate.get("status") != "passed":
        status = "blocked"
        summary = "Browser quality smoke needs a passing browser screenshot first."
    elif missing_names:
        status = "failed"
        summary = f"{len(missing_names)} interactive element(s) need accessible names."
    elif route_smoke.get("status") == "failed":
        status = "failed"
        summary = _clean(route_smoke.get("summary") or "Browser interaction smoke failed.")
    else:
        status = "passed"
        summary = "Interactive browser smoke found named controls and no dead-button evidence."
    evidence = [str(log_path)]
    if route_smoke.get("screenshot"):
        evidence.append(str(route_smoke.get("screenshot")))
    return {
        "id": "browser_quality",
        "label": "Accessibility and dead-button smoke",
        "group": "browser",
        "status": status,
        "required": required,
        "executed": status not in {"skipped", "blocked"},
        "summary": summary,
        "log_path": str(log_path),
        "evidence": evidence,
        "metadata": {"interactive_count": len(elements), "missing_names": missing_names, "route_smoke": route_smoke},
    }


def _browser_visual_review_gate(base: Path, url: str, log_root: Path, *, required: bool, request: str = "") -> dict[str, Any]:
    if not required:
        return _manual_gate(
            "browser_visual_review",
            "Rendered UI visual review",
            "skipped",
            "Rendered UI visual review is not required for this stack.",
            required=False,
        )
    if not _clean(url):
        return _manual_gate(
            "browser_visual_review",
            "Rendered UI visual review",
            "blocked",
            "No preview URL was available for rendered UI review.",
            required=True,
        )
    started = time.perf_counter()
    screenshot_dir = log_root / "visual-screenshots"
    result = browser_playwright.visual_audit(url, screenshot_dir=screenshot_dir)
    request_findings = _request_visual_findings(result, request)
    if request_findings:
        result = {**result, "ok": False, "findings": _dedupe([*(result.get("findings") or []), *request_findings])}
    duration = int((time.perf_counter() - started) * 1000)
    log_path = log_root / "browser-visual-review.json"
    md_path = log_root / "browser-visual-review.md"
    log_path.write_text(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    findings = [str(item) for item in (result.get("findings") or []) if _clean(item)]
    screenshots = [str(item) for item in (result.get("screenshots") or []) if _clean(item)]
    md_lines = [
        "# Browser Visual Review",
        "",
        f"URL: {url}",
        f"Status: {'passed' if result.get('ok') else 'failed'}",
        "",
        "## Findings",
        *([f"- {item}" for item in findings] if findings else ["- No visual blocking issues detected by Friday's browser heuristics."]),
        "",
        "## Screenshots",
        *([f"- {item}" for item in screenshots] if screenshots else ["- No screenshots captured."]),
    ]
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    if not screenshots and not result.get("ok"):
        status = "blocked"
        summary = _clean(result.get("detail") or result.get("reason") or "Rendered UI review could not capture screenshots.")
    elif findings:
        status = "failed"
        summary = f"Rendered UI review found {len(findings)} visual issue(s): {findings[0]}"
    else:
        status = "passed"
        summary = f"Rendered UI review captured {len(screenshots)} screenshot(s) and found no blocking visual issues."
    return {
        "id": "browser_visual_review",
        "label": "Rendered UI visual review",
        "group": "browser",
        "status": status,
        "required": True,
        "executed": status != "blocked",
        "summary": summary,
        "duration_ms": duration,
        "url": url,
        "evidence": [str(log_path), str(md_path), *screenshots],
        "screenshot": screenshots[0] if screenshots else "",
        "metadata": result,
    }


def _request_visual_findings(result: dict[str, Any], request: str) -> list[str]:
    text = str(request or "").lower()
    if not text:
        return []
    findings: list[str] = []
    developer_tools = _developer_tools_request(text)
    energy_climate = _energy_climate_request(text)
    requested_3d = any(term in text for term in ("3d", "three.js", "webgl", "react-three", "react three", "interactive scene", "immersive scene"))
    requested_parallax = any(term in text for term in ("parallax", "scroll animation", "scroll-driven", "scroll driven", "pinned scroll", "cinematic scroll"))
    requested_motion = requested_3d or requested_parallax or any(term in text for term in ("animation", "animated", "motion", "microinteraction", "micro-interaction"))
    marketing_landing = any(term in text for term in ("landing page", "marketing website", "product page", "company website", "website"))
    explicit_multi_page = len(web_project_contract.expected_routes(request, stack={"stack": "nextjs"})) >= 2 or any(
        marker in text
        for marker in ("four-page", "4-page", "four pages", "4 pages", "multi-page", "multipage", "pages must", "pages should")
    )
    expected_section_depth = not explicit_multi_page and any(
        term in text
        for term in (
            "capabilities",
            "how it works",
            "how-it-works",
            "feature sections",
            "features section",
            "product proof",
            "proof band",
            "proof section",
            "conversion sections",
            "cta section",
            "marketplace story",
            "security section",
            "case study section",
            "case studies section",
        )
    )
    expected_nav_terms = _expected_visible_nav_terms(request)
    for item in result.get("contexts") or []:
        if not isinstance(item, dict):
            continue
        viewport = item.get("viewport") if isinstance(item.get("viewport"), dict) else {}
        label = str(viewport.get("label") or f"{viewport.get('width', '?')}x{viewport.get('height', '?')}")
        visual = item.get("visual") if isinstance(item.get("visual"), dict) else {}
        context = item.get("context") if isinstance(item.get("context"), dict) else {}
        page_text = _clean(context.get("page_text") or "")
        page_lower = page_text.lower()
        for heading in visual.get("headings") or []:
            heading_text = _clean(heading.get("text") if isinstance(heading, dict) else "")
            if _incoherent_visible_copy(heading_text):
                findings.append(f"{label}: incoherent visible headline copy found: {heading_text[:100]}.")
                break
        expected_brand = _explicit_brand_from_request(request)
        if expected_brand:
            brand_lower = expected_brand.lower()
            distinctive_tokens = _distinctive_brand_tokens(expected_brand)
            brand_visible = brand_lower in page_lower or bool(distinctive_tokens and all(token in page_lower for token in distinctive_tokens[:2]))
            if not brand_visible:
                findings.append(f"{label}: visible UI does not show the requested product/brand name: {expected_brand}.")
        if energy_climate:
            energy_terms = _energy_domain_terms()
            energy_matches = [term for term in energy_terms if re.search(rf"\b{re.escape(term)}s?\b", page_lower)]
            if page_text and len(energy_matches) < 3:
                findings.append(
                    f"{label}: climate/energy request lacks enough energy-domain copy or proof objects; found {len(energy_matches)} signal(s)."
                )
            wrong_terms = [term for term in _energy_wrong_domain_terms() if term not in text and term in page_lower]
            if wrong_terms:
                findings.append(
                    f"{label}: climate/energy request drifted into wrong-domain copy: {', '.join(wrong_terms[:4])}."
                )
        if expected_nav_terms and page_text:
            missing_nav = [term for term in expected_nav_terms if term not in page_lower]
            if len(missing_nav) >= 2:
                findings.append(f"{label}: rendered navigation/content is missing requested page labels: {', '.join(missing_nav[:4])}.")
        if marketing_landing and expected_section_depth and str(label).lower() == "desktop":
            viewport_height = float((visual.get("viewport") or {}).get("height") or viewport.get("height") or 0)
            body_height = float(visual.get("bodyHeight") or 0)
            visible_headings = [
                heading
                for heading in (visual.get("headings") or [])
                if isinstance(heading, dict) and heading.get("visible")
            ]
            shallow_height = bool(viewport_height and body_height and body_height <= viewport_height * 1.35)
            shallow_content = len(visible_headings) < 3 or len(page_text) < 850
            if shallow_height and shallow_content:
                findings.append(
                    f"{label}: insufficient landing-page depth for the requested section set."
                )
        if developer_tools:
            for image in visual.get("images") or []:
                if not isinstance(image, dict):
                    continue
                rect = image.get("rect") if isinstance(image.get("rect"), dict) else {}
                if not rect.get("visible"):
                    continue
                alt = _clean(image.get("alt") or "").lower()
                width = float(rect.get("width") or 0)
                height = float(rect.get("height") or 0)
                large_hero = width >= 260 and height >= 220 and float(rect.get("top") or 9999) < 760
                personish = any(term in alt for term in ("contributor", "portrait", "avatar", "person", "people", "woman", "man", "face", "founder", "team"))
                if large_hero and personish:
                    findings.append(f"{label}: developer-tools hero uses stock/person portrait imagery instead of product, code, docs, or architecture proof.")
                    break
        motion = visual.get("motion") if isinstance(visual.get("motion"), dict) else {}
        canvases = visual.get("canvases") if isinstance(visual.get("canvases"), list) else []
        visible_canvases = [
            canvas
            for canvas in canvases
            if isinstance(canvas, dict)
            and isinstance(canvas.get("rect"), dict)
            and canvas["rect"].get("visible")
            and float(canvas["rect"].get("width") or 0) >= 160
            and float(canvas["rect"].get("height") or 0) >= 120
        ]
        if requested_3d:
            if not visible_canvases and not motion.get("hasVideo"):
                findings.append(f"{label}: requested 3D/immersive experience has no visible canvas, WebGL, or scene media proof.")
            else:
                blank = [
                    canvas
                    for canvas in visible_canvases
                    if isinstance(canvas.get("signal"), dict)
                    and not canvas["signal"].get("nonBlankSample")
                    and int(canvas["signal"].get("dataUrlLength") or 0) < 1200
                ]
                if blank:
                    findings.append(f"{label}: requested 3D/immersive experience has a blank or unrendered canvas.")
        if requested_parallax and not motion.get("hasParallaxHints"):
            findings.append(f"{label}: requested parallax/cinematic scroll experience has no detectable parallax or scroll-motion implementation.")
        if requested_motion and not motion.get("hasReducedMotionCss"):
            findings.append(f"{label}: requested motion/3D/parallax experience has no detectable prefers-reduced-motion fallback.")
    return _dedupe(findings)


def _incoherent_visible_copy(text: str) -> bool:
    lowered = _clean(text).lower()
    if not lowered:
        return False
    patterns = (
        r"\bfor\s+the\s+of\b",
        r"\b(?:the|a|an)\s+of\b",
        r"\bof\s+(?:the\s+)?of\b",
        r"\bfor\s+for\b",
        r"\bthe\s+the\b",
    )
    return any(re.search(pattern, lowered) for pattern in patterns)


def _explicit_brand_from_request(request: str) -> str:
    text = _clean(request)
    if not text:
        return ""
    patterns = (
        r"\bfor\s+(?:an?\s+)?([A-Z][A-Za-z0-9&' -]{2,80}?)(?=,\s+(?:an?|the)\b)",
        r"\bfor\s+(?:an?\s+)?([A-Z][A-Za-z0-9&' -]{2,80}?)(?=\s+(?:is|helps|offers|builds|provides)\b)",
        r"\bcalled\s+(?:an?\s+)?([A-Z][A-Za-z0-9&' -]{2,80}?)(?=\s*(?:[,.;]|$|\s+(?:is|helps|offers|builds|provides)\b))",
        r"\bnamed\s+(?:an?\s+)?([A-Z][A-Za-z0-9&' -]{2,80}?)(?=\s*(?:[,.;]|$|\s+(?:is|helps|offers|builds|provides)\b))",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            candidate = _clean(match.group(1)).strip(" .,:;")
            if _distinctive_brand_tokens(candidate):
                return candidate
    inferred = project_scaffolds.product_name(text)
    if inferred and inferred not in {"FlowPilot"} and not inferred.endswith(" Workspace") and _distinctive_brand_tokens(inferred):
        return inferred
    return ""


def _distinctive_brand_tokens(product_name: str) -> list[str]:
    generic = {
        "app",
        "apps",
        "web",
        "site",
        "page",
        "tool",
        "tools",
        "risk",
        "studio",
        "dashboard",
        "command",
        "center",
        "workspace",
        "platform",
        "management",
        "system",
        "systems",
        "service",
        "services",
    }
    tokens = [token.lower() for token in re.findall(r"[A-Za-z0-9]+", _clean(product_name)) if len(token) >= 4]
    return [token for token in tokens if token not in generic]


def _developer_tools_request(request_lower: str) -> bool:
    return any(
        term in request_lower
        for term in (
            "developer tool",
            "developer tools",
            "backend-as-a-service",
            "backend as a service",
            "baas",
            "api platform",
            "sdk",
            "cli",
            "websocket",
            "websockets",
            "web3",
            "x402",
            "open-source",
            "open source",
            "self-hosted",
            "self hosted",
            "plugin marketplace",
            "docs",
            "documentation",
            "schema builder",
        )
    )


def _energy_climate_request(request_lower: str) -> bool:
    return any(
        term in request_lower
        for term in (
            "climate-tech",
            "climatetech",
            "climate-risk",
            "climate risk",
            "property risk",
            "portfolio risk",
            "wildfire",
            "flood",
            "heat risk",
            "insurance risk",
            "tenant-impact",
            "tenant impact",
            "clean energy",
            "energy management",
            "energy grid",
            "microgrid",
            "microgrids",
            "solar",
            "battery",
            "batteries",
            "demand spike",
            "demand spikes",
            "outage risk",
            "building energy",
            "commercial building",
            "commercial buildings",
            "grid monitoring",
            "renewable",
            "decarbonization",
        )
    )


def _energy_domain_terms() -> tuple[str, ...]:
    return (
        "climate",
        "risk",
        "property",
        "portfolio",
        "wildfire",
        "flood",
        "heat",
        "insurance",
        "tenant",
        "maintenance",
        "microgrid",
        "energy",
        "solar",
        "battery",
        "grid",
        "demand",
        "outage",
        "building",
        "load",
        "resilience",
        "telemetry",
        "facility",
        "sustainability",
    )


def _energy_wrong_domain_terms() -> tuple[str, ...]:
    return (
        "construction services",
        "contractor",
        "jobsite",
        "handover",
        "crane",
        "concrete",
        "bid package",
        "atelier",
        "collections",
        "private inquiry",
        "private clients",
        "private client",
        "private appointment",
        "high-intent clients",
        "concierge",
        "concierge access",
        "permanent legacy",
        "craftsmanship",
        "provenance",
        "notice the difference",
        "crafted for private",
        "quiet confidence",
        "every detail",
        "material integrity",
        "intelligence collection",
        "appointment",
        "self-hosted backend",
        "web3 modules",
        "web3 module",
        "cli install",
        "api routes",
        "schema builder",
    )


def _expected_visible_nav_terms(request: str) -> list[str]:
    labels = [
        str(route.get("label") or route.get("id") or "")
        for route in web_project_contract.expected_routes(request, stack={"stack": "nextjs"})
        if isinstance(route, dict)
    ]
    terms: list[str] = []
    for label in labels:
        clean = _clean(label).lower()
        if clean in {"home", "contact"}:
            continue
        for token in re.split(r"[^a-z0-9]+", clean):
            if len(token) >= 4 and token not in terms:
                terms.append(token)
    return terms[:8]


def _recover_browser_gate_from_visual_review(browser_gate: dict[str, Any], visual_gate: dict[str, Any], log_root: Path) -> dict[str, Any] | None:
    if browser_gate.get("status") == "passed" or visual_gate.get("status") != "passed":
        return None
    metadata = visual_gate.get("metadata") if isinstance(visual_gate.get("metadata"), dict) else {}
    contexts = metadata.get("contexts") if isinstance(metadata.get("contexts"), list) else []
    first_context = next((item.get("context") for item in contexts if isinstance(item, dict) and isinstance(item.get("context"), dict)), {})
    if not first_context:
        first_context = {"url": visual_gate.get("url") or browser_gate.get("url") or "", "elements": []}
    screenshot = _clean(visual_gate.get("screenshot") or "")
    evidence = _dedupe([*(browser_gate.get("evidence") or []), *(visual_gate.get("evidence") or []), screenshot])
    recovered = {
        **browser_gate,
        "status": "passed",
        "executed": True,
        "summary": "Browser screenshot proof recovered from rendered UI visual review.",
        "screenshot": screenshot,
        "evidence": evidence,
        "metadata": {
            "ok": True,
            "source": "browser_visual_review_recovery",
            "original_browser_check": browser_gate.get("metadata") if isinstance(browser_gate.get("metadata"), dict) else {},
            "context": first_context,
            "screenshot": screenshot,
            "screenshots": metadata.get("screenshots") or [],
        },
    }
    log_path = log_root / "browser-check-recovered.json"
    log_path.write_text(json.dumps(recovered, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    recovered["log_path"] = str(log_path)
    recovered["evidence"] = _dedupe([*evidence, str(log_path)])
    return recovered


def _browser_route_smoke(url: str, elements: list[dict[str, Any]], log_root: Path, *, request: str = "") -> dict[str, Any]:
    if not _clean(url):
        return {"status": "skipped", "summary": "No browser URL available for route smoke.", "steps": []}
    texts = {_clean(item.get("text")).lower() for item in elements}
    if "open workspace" not in texts:
        routes = _contract_routes_from_log_root(log_root) or _design_import_routes_from_log_root(log_root) or _browser_routes_to_check(url, elements, request=request)
        anchors = _browser_hash_anchors_to_check(url, elements)
        non_root_routes = [route for route in routes if route != "/"]
        if non_root_routes:
            return _browser_site_route_smoke(url, routes, log_root)
        if anchors:
            return _browser_anchor_smoke(url, anchors, log_root)
        if routes:
            return _browser_site_route_smoke(url, routes, log_root)
        return {"status": "skipped", "summary": "No recognized workspace route control or website routes to exercise.", "steps": []}
    steps = [
        {"action": "click", "selector": "text=Open workspace"},
        {"action": "wait", "ms": 500},
        {"action": "click", "selector": "text=Draft brief"},
        {"action": "wait", "ms": 500},
        {"action": "click", "selector": "text=Mark reviewed"},
        {"action": "wait", "ms": 300},
    ]
    result = browser_playwright.run_steps(url, steps, screenshot=True)
    status = "passed" if result.get("ok") else "failed"
    log_path = log_root / "browser-route-smoke.json"
    log_path.write_text(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    failed_steps = [step for step in result.get("steps") or [] if not step.get("ok")]
    return {
        "status": status,
        "summary": "Workspace route and primary controls responded." if status == "passed" else f"{len(failed_steps)} browser interaction step(s) failed.",
        "steps": result.get("steps") or [],
        "screenshot": result.get("screenshot") or "",
        "log_path": str(log_path),
        "context": result.get("context") if isinstance(result.get("context"), dict) else {},
    }


def _browser_routes_to_check(url: str, elements: list[dict[str, Any]], *, request: str = "") -> list[str]:
    parsed_base = urllib.parse.urlparse(_clean(url))
    if not parsed_base.scheme or not parsed_base.netloc:
        return []
    routes: list[str] = []

    def add(route: str) -> None:
        normalized = _normalize_smoke_route(route)
        if normalized and normalized not in routes:
            routes.append(normalized)

    try:
        for route in web_project_contract.expected_routes(request, stack={"stack": "nextjs"}):
            add(str(route.get("route") or ""))
    except Exception:
        pass

    if _looks_like_website_request(request):
        try:
            for page in design_providers._website_page_specs(request):
                add(str(page.get("route") or ""))
        except Exception:
            pass

    for item in elements:
        if not isinstance(item, dict):
            continue
        if item.get("visible") is False:
            continue
        rect = item.get("rect") if isinstance(item.get("rect"), dict) else {}
        if rect and rect.get("visible") is False:
            continue
        href = _clean(item.get("href"))
        if not href or href.startswith("#") or href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue
        parsed = urllib.parse.urlparse(href)
        if parsed.scheme and parsed.scheme not in {"http", "https"}:
            continue
        if parsed.netloc and parsed.netloc != parsed_base.netloc:
            continue
        add(parsed.path or href)
    return routes[:12]


def _browser_hash_anchors_to_check(url: str, elements: list[dict[str, Any]]) -> list[dict[str, str]]:
    parsed_base = urllib.parse.urlparse(_clean(url))
    if not parsed_base.scheme or not parsed_base.netloc:
        return []
    anchors: list[dict[str, str]] = []
    for item in elements:
        if not isinstance(item, dict):
            continue
        if item.get("visible") is False:
            continue
        rect = item.get("rect") if isinstance(item.get("rect"), dict) else {}
        if rect and rect.get("visible") is False:
            continue
        href = _clean(item.get("href"))
        if not href or href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue
        parsed = urllib.parse.urlparse(href)
        fragment = parsed.fragment or (href[1:] if href.startswith("#") else "")
        if not fragment:
            continue
        if parsed.scheme and parsed.scheme not in {"http", "https"}:
            continue
        if parsed.netloc and parsed.netloc != parsed_base.netloc:
            continue
        if parsed.path and parsed.path not in {"", parsed_base.path or "/"}:
            continue
        anchor = f"#{fragment.strip('#')}"
        if anchor == "#":
            continue
        entry = {"anchor": anchor, "text": _clean(item.get("text") or anchor)}
        if entry not in anchors:
            anchors.append(entry)
    return anchors[:8]


def _design_import_routes_from_log_root(log_root: Path) -> list[str]:
    try:
        project_root = log_root.parents[3]
    except IndexError:
        return []
    manifest_path = project_root / ".friday" / "design-import" / "source-manifest.json"
    if not manifest_path.is_file():
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8", errors="ignore") or "{}")
    except json.JSONDecodeError:
        return []
    routes: list[str] = []
    for page in manifest.get("pages") or []:
        if not isinstance(page, dict):
            continue
        route = _normalize_smoke_route(str(page.get("route") or ""))
        if route and route not in routes:
            routes.append(route)
    return routes[:12]


def _contract_routes_from_log_root(log_root: Path) -> list[str]:
    try:
        project_root = log_root.parents[3]
    except IndexError:
        return []
    contract_path = project_root / "src" / "lib" / "webProjectContract.ts"
    if not contract_path.is_file():
        return []
    routes: list[str] = []
    for match in re.finditer(r"""(?:["']route["']|\broute\b)\s*:\s*["']([^"']+)["']""", contract_path.read_text(encoding="utf-8", errors="ignore")):
        route = _normalize_smoke_route(match.group(1))
        if route and route not in routes:
            routes.append(route)
    return routes[:12]


def _browser_anchor_smoke(url: str, anchors: list[dict[str, str]], log_root: Path) -> dict[str, Any]:
    base_url = urllib.parse.urldefrag(_clean(url))[0] or _clean(url)
    screenshot_dir = log_root / "anchor-screenshots"
    steps: list[dict[str, Any]] = []
    for item in anchors[:8]:
        anchor = _clean(item.get("anchor"))
        if not anchor.startswith("#") or len(anchor) <= 1:
            continue
        target = f"{base_url}{anchor}"
        result = browser_playwright.visual_audit(
            target,
            screenshot_dir=screenshot_dir,
            viewports=[{"label": f"anchor-{anchor.lstrip('#')}", "width": 1440, "height": 900}],
        )
        context = next((ctx for ctx in result.get("contexts") or [] if isinstance(ctx, dict)), {})
        visual = context.get("visual") if isinstance(context.get("visual"), dict) else {}
        visible_headings = [
            heading
            for heading in (visual.get("headings") or [])
            if isinstance(heading, dict) and heading.get("visible") and _clean(heading.get("text"))
        ]
        text_length = int(visual.get("firstViewportTextLength") or 0)
        screenshots = [str(path) for path in (result.get("screenshots") or []) if _clean(path)]
        ok = bool(result.get("ok")) and (text_length >= 90 or bool(visible_headings))
        steps.append(
            {
                "anchor": anchor,
                "label": item.get("text") or anchor,
                "url": target,
                "ok": ok,
                "first_viewport_text_length": text_length,
                "visible_headings": [_clean(heading.get("text")) for heading in visible_headings[:4]],
                "screenshot": screenshots[0] if screenshots else "",
                "detail": "Anchor lands on meaningful content." if ok else "Anchor lands on a blank or weak first viewport.",
            }
        )
    failed = [step for step in steps if not step.get("ok")]
    status = "failed" if failed else "passed"
    result = {
        "status": status,
        "summary": f"{len(failed)} hash anchor(s) landed on blank or weak content." if failed else f"{len(steps)} hash anchor(s) landed on meaningful content.",
        "steps": steps,
        "screenshot": next((step.get("screenshot") for step in steps if step.get("screenshot")), ""),
    }
    log_path = log_root / "browser-anchor-smoke.json"
    log_path.write_text(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    result["log_path"] = str(log_path)
    return result


def _browser_site_route_smoke(url: str, routes: list[str], log_root: Path) -> dict[str, Any]:
    base_url = _clean(url)
    steps: list[dict[str, Any]] = []
    for route in routes:
        target = urllib.parse.urljoin(base_url.rstrip("/") + "/", route.lstrip("/"))
        if route == "/":
            target = urllib.parse.urljoin(base_url.rstrip("/") + "/", "")
        status_code, detail = _fetch_url_status(target)
        steps.append(
            {
                "route": route,
                "url": target,
                "status_code": status_code,
                "ok": 200 <= status_code < 400,
                "detail": detail,
            }
        )
    failed = [step for step in steps if not step.get("ok")]
    status = "failed" if failed else "passed"
    result = {
        "status": status,
        "summary": f"{len(failed)} internal route(s) failed smoke checks." if failed else f"{len(steps)} internal route(s) returned successful status codes.",
        "steps": steps,
    }
    log_path = log_root / "browser-site-route-smoke.json"
    log_path.write_text(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    result["log_path"] = str(log_path)
    return result


def _normalize_smoke_route(route: str) -> str:
    cleaned = _clean(route)
    if not cleaned:
        return ""
    parsed = urllib.parse.urlparse(cleaned)
    path = parsed.path or cleaned
    if not path or path.startswith("#"):
        return ""
    if not path.startswith("/"):
        path = f"/{path}"
    path = "/" + path.strip("/")
    return "/" if path == "/" else path.rstrip("/")


def _looks_like_website_request(request: str) -> bool:
    text = str(request or "").lower()
    return bool(
        "website" in text
        or "landing page" in text
        or re.search(r"\b(?:four|4|multi)[-\s]?page\b", text)
        or re.search(r"\bpages?\s+(?:must|should|include|including|be)\b", text)
    )


def _fetch_url_status(url: str) -> tuple[int, str]:
    target = _clean(url)
    if not target:
        return 0, "empty url"
    try:
        req = urllib.request.Request(target, headers={"User-Agent": "FridayProductStudioRouteSmoke/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            return int(response.status), "ok"
    except urllib.error.HTTPError as exc:
        return int(exc.code), str(exc)
    except Exception as exc:
        return 0, str(exc)


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


def _production_file_gates(base: Path, stack: dict[str, Any], gates: list[dict[str, Any]], log_root: Path, *, request: str = "") -> list[dict[str, Any]]:
    return [
        _web_route_contract_gate(base, request, stack, log_root),
        _product_fit_gate(base, request, log_root),
        _ux_copy_quality_gate(base, log_root, request=request),
        _performance_gate(base, stack, gates, log_root),
        _environment_gate(base, log_root),
        _operations_gate(base, log_root),
        _docs_launch_gate(base, log_root),
    ]


def _web_route_contract_gate(base: Path, request: str, stack: dict[str, Any], log_root: Path) -> dict[str, Any]:
    log_path = log_root / "web-route-contract.json"
    routes = web_project_contract.expected_routes(request, stack=stack)
    if len(routes) <= 1:
        payload = {"request": _clean(request), "routes": routes, "missing": [], "checked": []}
        log_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {
            "id": "web_route_contract",
            "label": "Web route contract",
            "group": "product",
            "status": "skipped",
            "required": False,
            "executed": False,
            "summary": "No multi-route web contract was inferred from the request.",
            "log_path": str(log_path),
            "evidence": [str(log_path)],
            "metadata": payload,
        }
    route_paths = web_project_contract.expected_route_paths(base, request, stack=stack)
    missing = [route_id for route_id, path in route_paths.items() if not path.exists()]
    fat_routes = []
    for route_id, path in route_paths.items():
        if not path.exists():
            continue
        lines = [line for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
        if len(lines) > 30:
            fat_routes.append(route_id)
    payload = {
        "request": _clean(request),
        "routes": routes,
        "checked": {route_id: str(path) for route_id, path in route_paths.items()},
        "missing": missing,
        "fat_routes": fat_routes,
    }
    log_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    passed = not missing and not fat_routes
    summary = (
        f"All {len(routes)} requested web route(s) exist as thin Next.js routes."
        if passed
        else f"Web route contract failed; missing: {', '.join(missing) or 'none'}; oversized route files: {', '.join(fat_routes) or 'none'}."
    )
    return {
        "id": "web_route_contract",
        "label": "Web route contract",
        "group": "product",
        "status": "passed" if passed else "failed",
        "required": True,
        "executed": True,
        "summary": summary,
        "log_path": str(log_path),
        "evidence": [str(log_path), *[str(path) for path in route_paths.values() if path.exists()]],
        "metadata": payload,
    }


def _product_fit_gate(base: Path, request: str, log_root: Path) -> dict[str, Any]:
    keywords = _domain_keywords(request)
    log_path = log_root / "product-domain-fit.json"
    if not keywords:
        payload = {"request": _clean(request), "request_keywords": [], "matched_keywords": [], "missing_keywords": []}
        log_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {
            "id": "product_domain_fit",
            "label": "Product/domain fit",
            "group": "product",
            "status": "skipped",
            "required": False,
            "executed": False,
            "summary": "No specific product-domain keywords were available to check.",
            "log_path": str(log_path),
            "evidence": [str(log_path)],
            "metadata": payload,
        }
    files = _visible_product_surface_files(base) or _product_surface_files(base)
    text_parts: list[str] = []
    for path in files:
        body = path.read_text(encoding="utf-8", errors="ignore")[:150000]
        body = _remove_raw_request_copy(body)
        text_parts.append(body)
    surface_text = "\n".join(text_parts).lower()
    matched = [keyword for keyword in keywords if keyword in surface_text]
    missing = [keyword for keyword in keywords if keyword not in matched]
    request_lower = str(request or "").lower()
    stale_terms = ["invoice", "designer", "service businesses", "smb operators", "customer asked"]
    if _energy_climate_request(request_lower):
        stale_terms.extend(_energy_wrong_domain_terms())
    stale_copy = [term for term in stale_terms if term not in request_lower and term in surface_text]
    required_specific = _required_domain_terms(request)
    missing_specific = [term for term in required_specific if term not in surface_text]
    minimum = max(2, min(len(keywords), (len(keywords) + 1) // 2))
    passed = len(matched) >= minimum and not stale_copy and not missing_specific
    payload = {
        "request": _clean(request),
        "request_keywords": keywords,
        "matched_keywords": matched,
        "missing_keywords": missing,
        "minimum_required_matches": minimum,
        "stale_generic_copy": stale_copy,
        "required_specific_terms": required_specific,
        "missing_specific_terms": missing_specific,
        "files_checked": [_relative(path, base) for path in files],
    }
    log_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = (
        f"Product surfaces match {len(matched)}/{len(keywords)} domain keyword(s)."
        if passed
        else f"Product surfaces only match {len(matched)}/{len(keywords)} domain keyword(s); stale generic copy: {', '.join(stale_copy) or 'none'}; missing specific terms: {', '.join(missing_specific) or 'none'}."
    )
    return {
        "id": "product_domain_fit",
        "label": "Product/domain fit",
        "group": "product",
        "status": "passed" if passed else "failed",
        "required": True,
        "executed": True,
        "summary": summary,
        "log_path": str(log_path),
        "evidence": [str(log_path)],
        "metadata": payload,
    }


def _ux_copy_quality_gate(base: Path, log_root: Path, *, request: str = "") -> dict[str, Any]:
    log_path = log_root / "ux-copy-quality.json"
    surface_paths = [
        base / "src" / "lib" / "productPlan.ts",
        base / "src" / "lib" / "siteContent.ts",
        base / "src" / "lib" / "stitchNativeContent.ts",
        base / "src" / "lib" / "webProjectContract.ts",
        base / "src" / "components" / "Landing" / "HomePage.tsx",
        base / "src" / "components" / "Workspace" / "WorkspaceConsole.tsx",
        base / "src" / "components" / "Marketing" / "AboutPage.tsx",
        base / "src" / "components" / "Marketing" / "ServicesPage.tsx",
        base / "src" / "components" / "Marketing" / "ContactPage.tsx",
        base / "src" / "components" / "WebContract" / "ContractShell.tsx",
        base / "src" / "components" / "WebContract" / "WebContractPage.tsx",
        base / "src" / "components" / "WebContract" / "DashboardPreviewPage.tsx",
        base / "src" / "components" / "Stitch" / "StitchNativePage.tsx",
        base / "src" / "components" / "Stitch" / "StitchNativePage.module.css",
        base / "src" / "app" / "globals.css",
    ]
    files = [path for path in surface_paths if path.exists()]
    if not files:
        payload = {"files_checked": [], "issues": []}
        log_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {
            "id": "ux_copy_quality",
            "label": "UX and copy quality",
            "group": "product",
            "status": "skipped",
            "required": False,
            "executed": False,
            "summary": "No frontend product surfaces were available to review.",
            "log_path": str(log_path),
            "evidence": [str(log_path)],
            "metadata": payload,
        }

    bodies = {path: path.read_text(encoding="utf-8", errors="ignore")[:150000] for path in files}
    combined = "\n".join(bodies.values())
    issues: list[str] = []
    plan = bodies.get(base / "src" / "lib" / "productPlan.ts", "")
    site_content = bodies.get(base / "src" / "lib" / "siteContent.ts", "")
    native_content = bodies.get(base / "src" / "lib" / "stitchNativeContent.ts", "")
    web_contract = bodies.get(base / "src" / "lib" / "webProjectContract.ts", "")
    home = bodies.get(base / "src" / "components" / "Landing" / "HomePage.tsx", "")
    workspace = bodies.get(base / "src" / "components" / "Workspace" / "WorkspaceConsole.tsx", "")
    css = bodies.get(base / "src" / "app" / "globals.css", "")
    marketing_site = bool(site_content and "siteContent" in site_content and "components/Marketing" in combined)
    native_surface = bool(native_content and "stitchNativeContent" in native_content)
    contract_surface = bool(web_contract and "webProject" in web_contract and "WebContractPage" in combined)

    name_match = re.search(r"\bname:\s*['\"]([^'\"]+)['\"]", plan)
    site_brand_match = re.search(r"\bbrand:\s*['\"]([^'\"]+)['\"]", site_content)
    native_name_match = re.search(r'"productName":\s*"([^"]+)"', native_content)
    contract_name_match = re.search(r"""(?:["']product_name["']|\bproduct_name\b)\s*:\s*["']([^"']+)["']""", web_contract)
    product_name = (
        name_match.group(1).strip()
        if name_match
        else site_brand_match.group(1).strip()
        if site_brand_match
        else native_name_match.group(1).strip()
        if native_name_match
        else contract_name_match.group(1).strip()
        if contract_name_match
        else ""
    )
    if _looks_like_machined_product_name(product_name):
        issues.append(f"Product name is not human-readable: {product_name}.")
    if not marketing_site and not native_surface and not contract_surface and "summary:" not in plan:
        issues.append("Product plan is missing a human-written summary field for visible copy.")
    if "productPlan.request" in home or "plan.request" in workspace:
        issues.append("Visible UI renders the raw user request instead of product copy.")
    if not marketing_site and not native_surface and not contract_surface and home and "productPlan.summary" not in home:
        issues.append("Landing page does not render productPlan.summary.")
    if not marketing_site and not native_surface and not contract_surface and workspace and "plan.summary" not in workspace:
        issues.append("Workspace page does not render plan.summary.")
    if native_surface and not re.search(r'"summary":\s*"[^"]{20,}"', native_content):
        issues.append("Native design content is missing a human-written page summary.")
    generic_phrases = [
        "AI everyday tool",
        "Launch signal",
        "Generate a brief to see the AI workflow.",
        "Customer asked for status",
        "designer is blocked",
        "service businesses",
        "SMB operators",
    ]
    request_lower = str(request or "").lower()
    stale_phrases = [phrase for phrase in generic_phrases if phrase.lower() in combined.lower() and phrase.lower() not in request_lower]
    if stale_phrases:
        issues.append(f"Visible surfaces contain generic scaffold copy: {', '.join(stale_phrases)}.")
    if _energy_climate_request(request_lower):
        wrong_terms = [term for term in _energy_wrong_domain_terms() if term not in request_lower and term in combined.lower()]
        if wrong_terms:
            issues.append(f"Climate/energy UI copy drifted into wrong-domain language: {', '.join(wrong_terms[:6])}.")
    field_service_surface = _looks_like_field_service_surface(plan)
    if field_service_surface:
        required_terms = ["dispatch", "technician", "emergency", "parts", "sla", "invoice"]
        missing_terms = [term for term in required_terms if term not in combined.lower()]
        if missing_terms:
            issues.append(f"Field service UI copy is too generic; missing dispatch terms: {', '.join(missing_terms)}.")
    restaurant_surface = _looks_like_restaurant_surface(plan)
    if restaurant_surface:
        required_terms = ["waitlist", "kitchen", "staff", "inventory", "delivery", "refund", "food safety", "cash close"]
        missing_terms = [term for term in required_terms if term not in combined.lower()]
        if missing_terms:
            issues.append(f"Restaurant UI copy is too generic; missing shift terms: {', '.join(missing_terms)}.")
    if css and "overflow-wrap" not in css:
        issues.append("Global heading styles do not protect long product names from clipping.")

    payload = {
        "files_checked": [_relative(path, base) for path in files],
        "issues": issues,
        "product_name": product_name,
    }
    log_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    passed = not issues
    return {
        "id": "ux_copy_quality",
        "label": "UX and copy quality",
        "group": "product",
        "status": "passed" if passed else "failed",
        "required": True,
        "executed": True,
        "summary": "Visible UI copy and layout safeguards passed." if passed else "Visible UI copy/layout needs revision.",
        "log_path": str(log_path),
        "evidence": [str(log_path)],
        "metadata": payload,
    }


def _looks_like_machined_product_name(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    if " " in text:
        return False
    return bool(len(text) > 15 and re.search(r"[a-z][A-Z]", text))


def _visible_product_surface_files(base: Path) -> list[Path]:
    if (base / "src/lib/stitchNativeContent.ts").is_file():
        preferred = [
            "src/lib/stitchNativeContent.ts",
            "src/components/Stitch/StitchNativePage.tsx",
            "src/components/Stitch/StitchNativePage.module.css",
            "src/app/page.tsx",
        ]
        return [base / path for path in preferred if (base / path).is_file()]
    if (base / "src/lib/webProjectContract.ts").is_file():
        preferred = [
            "src/lib/webProjectContract.ts",
            "src/components/Landing/HomePage.tsx",
            "src/components/WebContract/WebContractPage.tsx",
            "src/components/WebContract/DashboardPreviewPage.tsx",
            "src/app/page.tsx",
            "src/app/product/page.tsx",
            "src/app/features/page.tsx",
            "src/app/pricing/page.tsx",
            "src/app/about/page.tsx",
            "src/app/services/page.tsx",
            "src/app/contact/page.tsx",
            "src/app/dashboard-preview/page.tsx",
        ]
        return [base / path for path in preferred if (base / path).is_file()]
    if (base / "src/lib/siteContent.ts").is_file():
        preferred = [
            "src/lib/siteContent.ts",
            "src/components/Landing/HomePage.tsx",
            "src/components/Marketing/AboutPage.tsx",
            "src/components/Marketing/ServicesPage.tsx",
            "src/components/Marketing/ContactPage.tsx",
        ]
        return [base / path for path in preferred if (base / path).is_file()]
    preferred = [
        "src/lib/productPlan.ts",
        "src/components/Landing/HomePage.tsx",
        "src/components/Workspace/WorkspaceConsole.tsx",
    ]
    return [base / path for path in preferred if (base / path).is_file()]


def _remove_raw_request_copy(body: str) -> str:
    lines = []
    skip = False
    for line in str(body or "").splitlines():
        stripped = line.strip()
        if re.match(r"request:\s*['\"]", stripped):
            skip = not stripped.endswith(",")
            continue
        if skip:
            if stripped.endswith(",") or stripped.endswith("`,"):
                skip = False
            continue
        if stripped.lower().startswith(("request:", "user request:", "build a web-app", "build a web app")):
            continue
        lines.append(line)
    return "\n".join(lines)


def _required_domain_terms(request: str) -> list[str]:
    text = str(request or "").lower()
    if _energy_climate_request(text):
        candidates = ["energy", "microgrid", "solar", "battery", "grid", "demand", "outage", "building", "load", "resilience"]
        selected = [term for term in candidates if term in text]
        return selected[:6] or ["energy", "grid", "building", "demand"]
    if any(term in text for term in ("permit", "civic", "city planning", "municipal", "public transparency")):
        return ["permit", "intake", "review", "queue", "inspection", "applicant", "transparency", "audit"]
    if "field service" in text or any(term in text for term in ("hvac", "plumbing", "electrical", "technician", "dispatch")):
        return ["dispatch", "technician", "emergency", "parts", "sla", "invoice"]
    if "restaurant" in text or any(term in text for term in ("waitlist", "kitchen", "staff coverage", "food safety", "cash close")):
        return ["restaurant", "waitlist", "kitchen", "staff", "inventory", "delivery", "refund", "food safety", "cash close"]
    if any(term in text for term in ("university", "registrar", "lecturer", "student", "bursary")):
        return ["registrar", "student", "course", "fee", "lecturer"]
    return []


def _looks_like_field_service_surface(plan: str) -> bool:
    lowered = str(plan or "").lower()
    return "field service" in lowered or "dispatch" in lowered or "technician" in lowered


def _looks_like_restaurant_surface(plan: str) -> bool:
    lowered = str(plan or "").lower()
    return "restaurant" in lowered or "waitlist" in lowered or "kitchen" in lowered or "cash close" in lowered


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
    health_files = [
        path
        for path in _text_files(base, limit=300)
        if "health" in _relative(path, base).replace("\\", "/").lower()
        or "/health" in path.read_text(encoding="utf-8", errors="ignore")[:100000].lower()
    ]
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
            "metadata": {"sandbox": _sandbox_metadata(base)},
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
            "metadata": {"timeout_seconds": timeout_seconds, "sandbox": _sandbox_metadata(base)},
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
    env = command_runner.safe_environment({str(key): str(value).format(port=port) for key, value in command.get("env", {}).items()})
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
            "metadata": {"pid": process.pid, "kind": command.get("kind", ""), "sandbox": _sandbox_metadata(base)},
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
            command_runner.terminate_process_tree(int(process.pid))
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
            return "pnpm install --ignore-scripts"
        if (base / "yarn.lock").exists():
            return "yarn install --ignore-scripts"
        return "npm install --ignore-scripts --no-audit --no-fund --prefer-online"
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
            path = "/health" if any(name in deps for name in ("fastify", "@fastify/cors")) else "/"
            return {"command": f"{runner} run start", "env": {"PORT": "{port}"}, "kind": "node_start", "path": path}
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


def _sandbox_metadata(base: Path) -> dict[str, Any]:
    return {
        "cwd": str(base),
        "shell": False,
        "env_scrubbed": True,
        "secret_env_removed": True,
        "host_isolation": "process_only",
        "note": "Commands run with allowlisted executables, no shell metacharacters, scrubbed environment, timeouts, and process cleanup. Container or microVM isolation is still recommended for untrusted code.",
    }


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


def _product_surface_files(base: Path) -> list[Path]:
    preferred = [
        "src/lib/productPlan.ts",
        "src/components/Landing/HomePage.tsx",
        "src/components/Workspace/WorkspaceConsole.tsx",
        "README.md",
        "src/app/api/brief/route.ts",
        "src/app/api/health/route.ts",
        "src/app.js",
        "src/routes/brief.js",
        "src/routes/workItems.js",
        "src/services/briefService.js",
    ]
    files = [base / path for path in preferred if (base / path).is_file()]
    if files:
        return files
    return _text_files(base, limit=40)


def _domain_keywords(request: str) -> list[str]:
    stop = {
        "about", "after", "also", "and", "any", "app", "apps", "application", "backend", "build", "can",
        "create", "dashboard", "everyday", "for", "from", "frontend", "generate", "into", "make", "mobile",
        "next", "nextjs", "project", "prototype", "server", "should", "small", "system", "that", "the",
        "this", "tool", "using", "want", "web", "webapp", "website", "with", "production", "quality",
        "specific", "copy", "follow", "structure", "requirements", "implementation", "features", "docs",
        "google", "stitch", "handoff", "claim", "technical", "ready", "market", "proof", "real", "gates",
    }
    words = [word for word in re.split(r"[^a-z0-9]+", str(request or "").lower()) if len(word) > 2 and word not in stop]
    result: list[str] = []
    for word in words:
        if word.endswith("s") and len(word) > 4:
            singular = word[:-1]
        else:
            singular = word
        if word not in result:
            result.append(word)
        if singular != word and singular not in result:
            result.append(singular)
        if len(result) >= 12:
            break
    return result


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
    except urllib.error.HTTPError as exc:
        return 200 <= int(exc.code) < 500
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

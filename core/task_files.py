"""Readable task packets Friday writes before/after serious work."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from core import document_exports
from core.config import resolve_coding_root

TASK_FILE_DIR = ".friday/task-files"
DEFAULT_FORMATS = ("md", "docx", "pdf")


def write_task_files(
    root: str | Path,
    request: str,
    *,
    run_id: int | str = "",
    intent: dict[str, Any] | None = None,
    preflight: dict[str, Any] | None = None,
    architecture: dict[str, Any] | None = None,
    research_context: dict[str, Any] | None = None,
    execution_plan: dict[str, Any] | None = None,
    formats: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    base = resolve_coding_root(root)
    packet_id = _packet_id(run_id, request)
    packet_root = base / TASK_FILE_DIR / packet_id
    packet_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "request": _clean(request),
        "intent": intent or {},
        "preflight": preflight or {},
        "architecture": architecture or {},
        "research_context": research_context or {},
        "execution_plan": execution_plan or {},
        "created_at": _now(),
        "packet_id": packet_id,
    }
    docs = {
        "requirements": _requirements_doc(payload),
        "system-design": _system_design_doc(payload),
        "implementation-plan": _implementation_plan_doc(payload),
        "features": _features_doc(payload),
    }
    selected_formats = _formats(formats)
    written = []
    exports: dict[str, Any] = {}
    for name, content in docs.items():
        exported = document_exports.export_markdown(content, packet_root / name, formats=selected_formats)
        exports[name] = exported.get("paths") or {}
        written.extend(str(path) for path in (exported.get("paths") or {}).values())
    manifest = {
        **payload,
        "formats": selected_formats,
        "documents": {
            "requirements": "Requirements, acceptance criteria, constraints, and quality bar.",
            "system-design": "Architecture, components, data, API/UI contracts, security, observability, and deployment shape.",
            "implementation-plan": "Sequenced execution plan, files to touch, gates, risks, and proof requirements.",
            "features": "Feature inventory, priorities, user flows, expected states, and validation notes.",
        },
        "exports": exports,
    }
    manifest_path = packet_root / "manifest.json"
    manifest_path.write_text(_json_dumps(manifest), encoding="utf-8")
    written.append(str(manifest_path))
    return {
        "packet_id": packet_id,
        "root": str(packet_root),
        "files": written,
        "exports": exports,
        "summary": f"Task packet written with requirements, system design, implementation plan, and features documents in {', '.join(selected_formats).upper()}.",
    }


def _task_brief_section(payload: dict[str, Any]) -> str:
    intent = payload.get("intent") if isinstance(payload.get("intent"), dict) else {}
    return (
        f"Created: {payload['created_at']}\n\n"
        f"Request: {payload['request']}\n\n"
        f"Intent: {intent.get('user_intent') or intent.get('intent') or 'not classified'}\n\n"
        f"Recommended action: {intent.get('recommended_action') or 'not recorded'}\n\n"
        "Rule: Friday must inspect, verify, and attach proof before claiming completion.\n"
    )


def _context_research_section(payload: dict[str, Any]) -> str:
    research = payload.get("research_context") if isinstance(payload.get("research_context"), dict) else {}
    preflight = payload.get("preflight") if isinstance(payload.get("preflight"), dict) else {}
    intelligence = preflight.get("intelligence") if isinstance(preflight.get("intelligence"), dict) else {}
    sources = research.get("sources") if isinstance(research.get("sources"), list) else []
    lines = [
        f"Project root: {intelligence.get('root') or 'not recorded'}",
        f"Stack: {(intelligence.get('stack') or {}).get('label') if isinstance(intelligence.get('stack'), dict) else 'not recorded'}",
        f"Style profile: {(intelligence.get('style_profile') or {}).get('id') if isinstance(intelligence.get('style_profile'), dict) else 'none'}",
        "",
        "## Research Sources",
    ]
    if not sources:
        lines.append("- No live research context was attached for this task.")
    for source in sources:
        lines.append(f"- {source.get('title') or 'Untitled'} - {source.get('url') or 'no url'}")
    return "\n".join(lines) + "\n"


def _requirements_doc(payload: dict[str, Any]) -> str:
    preflight = payload.get("preflight") if isinstance(payload.get("preflight"), dict) else {}
    acceptance = preflight.get("acceptance_criteria") if isinstance(preflight.get("acceptance_criteria"), list) else []
    lines = ["# Requirements", "", _task_brief_section(payload), "## Context", "", _context_research_section(payload), "## Acceptance Criteria", ""]
    if not acceptance:
        acceptance = [
            "Project inspection is recorded.",
            "Architecture and stack decision are explicit.",
            "Implementation produces real artifacts.",
            "Verification gates or explicit limits are attached.",
            "Final proof names remaining gaps honestly.",
        ]
    for item in acceptance:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Non-Functional Requirements",
            "- Security, privacy, and secret handling are explicit.",
            "- Performance and reliability checks are part of readiness.",
            "- Maintainability, readability, and scoped responsibility boundaries are preserved.",
            "- Reusability is introduced only where it reduces real duplication or complexity.",
            "",
            "## Open Questions",
            "- Confirm user-facing workflows, data model, integrations, and launch constraints before market readiness.",
        ]
    )
    return "\n".join(lines) + "\n"


def _system_design_doc(payload: dict[str, Any]) -> str:
    architecture = payload.get("architecture") if isinstance(payload.get("architecture"), dict) else {}
    preflight = payload.get("preflight") if isinstance(payload.get("preflight"), dict) else {}
    intelligence = preflight.get("intelligence") if isinstance(preflight.get("intelligence"), dict) else {}
    boundaries = intelligence.get("component_structure") if isinstance(intelligence.get("component_structure"), list) else []
    routes = intelligence.get("route_conventions") if isinstance(intelligence.get("route_conventions"), list) else []
    api = intelligence.get("api_conventions") if isinstance(intelligence.get("api_conventions"), list) else []
    lines = [
        "# System Design",
        "",
        f"Request: {payload['request']}",
        "",
        "## Architecture Decision",
        f"- Framework: {architecture.get('framework') or 'not recorded'}",
        f"- Stack: {(architecture.get('stack') or {}).get('label') if isinstance(architecture.get('stack'), dict) else (architecture.get('stack') or 'not recorded')}",
        f"- Package manager: {architecture.get('package_manager') or 'not recorded'}",
        f"- Style profile: {architecture.get('style_profile_id') or 'none'}",
        f"- Routing: {', '.join(routes) or architecture.get('routing') or 'not recorded'}",
        f"- API layer: {', '.join(api) or architecture.get('api_layer') or 'not recorded'}",
        "",
        "## Responsibility Boundaries",
    ]
    for item in boundaries or ["Routes stay thin.", "UI, state, services, validation, persistence, tests, and docs stay separated."]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Data And Integrations",
            f"- Database layer: {intelligence.get('database_layer') or 'not detected'}",
            f"- Auth layer: {intelligence.get('auth_layer') or 'not detected'}",
            f"- Deployment target: {intelligence.get('deployment_target') or 'not detected'}",
            "",
            "## Security And Reliability",
            "- Validate external input at boundaries.",
            "- Keep secrets in environment/secret stores, never in memory or generated docs.",
            "- Attach health checks, rollback notes, observability, and backup expectations before production readiness.",
        ]
    )
    return "\n".join(lines) + "\n"


def _implementation_plan_doc(payload: dict[str, Any]) -> str:
    architecture = payload.get("architecture") if isinstance(payload.get("architecture"), dict) else {}
    plan = payload.get("execution_plan") if isinstance(payload.get("execution_plan"), dict) else {}
    flow = plan.get("flow") if isinstance(plan.get("flow"), list) else ["inspect", "plan", "implement", "verify", "prove"]
    lines = [
        "# Implementation Plan",
        "",
        f"Request: {payload['request']}",
        "",
        f"Framework: {architecture.get('framework') or 'not recorded'}",
        f"Package manager: {architecture.get('package_manager') or 'not recorded'}",
        f"Style profile: {architecture.get('style_profile_id') or 'none'}",
        "",
        "## Flow",
    ]
    for step in flow:
        lines.append(f"- {step}")
    lines.extend(
        [
            "",
            "## Required Verification",
            "- Install dependencies or record why install was not possible.",
            "- Run typecheck/lint/build/tests that match the stack.",
            "- Run security/dependency checks where tools are available.",
            "- For frontend work, run browser/e2e or screenshot checks.",
            "- Write final proof with gaps before claiming completion.",
            "",
            "## Completion Rule",
            "- Friday cannot mark the task done from prose alone; docs, artifacts, gates, and proof must exist.",
        ]
    )
    return "\n".join(lines) + "\n"


def _features_doc(payload: dict[str, Any]) -> str:
    request = payload.get("request") or ""
    features = _feature_rows(request)
    lines = [
        "# Features",
        "",
        f"Request: {request}",
        "",
        "## Feature Inventory",
    ]
    for feature in features:
        lines.append(f"- {feature['priority']} - {feature['name']}: {feature['description']}")
    lines.extend(
        [
            "",
            "## Expected States",
            "- Empty/loading/error/success states are visible where users wait on data or actions.",
            "- Buttons and controls must call real backend endpoints or clearly show blocked/approval state.",
            "- Generated text should come from backend evidence, memory, or run reports, not hardcoded Friday claims.",
            "",
            "## Validation",
            "- Each feature needs at least one acceptance check and one verification artifact before readiness is upgraded.",
        ]
    )
    return "\n".join(lines) + "\n"


def _packet_id(run_id: int | str, request: str) -> str:
    prefix = f"run-{run_id}" if str(run_id or "").strip() else dt.datetime.now(dt.timezone.utc).strftime("task-%Y%m%d-%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", _clean(request).lower()).strip("-")[:42] or "task"
    return f"{prefix}-{slug}"


def _feature_rows(request: str) -> list[dict[str, str]]:
    lowered = request.lower()
    rows = [
        {"priority": "P0", "name": "Core workflow", "description": "The primary user flow requested by the task works end to end."},
        {"priority": "P0", "name": "Proof and status", "description": "Friday records progress, artifacts, verification, and gaps."},
        {"priority": "P1", "name": "Readable project docs", "description": "Requirements, system design, implementation plan, and features docs guide the build."},
    ]
    if any(term in lowered for term in ("web-app", "web app", "frontend", "ui", "dashboard")):
        rows.extend(
            [
                {"priority": "P0", "name": "Routed UI", "description": "Screens, buttons, forms, and modals are wired to backend APIs."},
                {"priority": "P1", "name": "Browser verification", "description": "Frontend states are checked through build and browser evidence."},
            ]
        )
    if any(term in lowered for term in ("mobile", "flutter")):
        rows.append({"priority": "P0", "name": "Mobile app flow", "description": "Flutter screens, state layer, API client, and tests match the requested workflow."})
    if "backend" in lowered or "api" in lowered:
        rows.append({"priority": "P0", "name": "Backend API", "description": "Routes, validation, auth/rate limits, logging, health checks, and tests are implemented."})
    if any(term in lowered for term in ("ads", "launch", "pricing", "market")):
        rows.append({"priority": "P1", "name": "Launch readiness", "description": "Pricing, launch assets, ads drafts, privacy notes, and approvals are prepared."})
    return rows


def _formats(formats: list[str] | tuple[str, ...] | None) -> list[str]:
    raw = formats or DEFAULT_FORMATS
    selected = [str(item or "").strip().lower().lstrip(".") for item in raw if str(item or "").strip()]
    allowed = {"md", "docx", "pdf"}
    return [item for item in selected if item in allowed] or list(DEFAULT_FORMATS)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n"


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

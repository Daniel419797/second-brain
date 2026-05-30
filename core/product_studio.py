"""Full product-studio operating model for Friday's autonomous build tasks."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from core import product_studio_gates
from core.config import resolve_coding_root

FRIDAY_DIR = ".friday"
STUDIO_DIR = "product-studio"


def studio_phases() -> list[dict[str, str]]:
    return [
        {"id": "requirements_acceptance", "label": "Requirements and acceptance criteria", "owner": "product_manager"},
        {"id": "architecture_stack", "label": "Architecture and stack decision", "owner": "senior_developer"},
        {"id": "feature_implementation", "label": "Feature implementation", "owner": "senior_developer"},
        {"id": "unit_integration_e2e_tests", "label": "Unit, integration, and e2e tests", "owner": "qa_engineer"},
        {"id": "security_dependency_scan", "label": "Security and dependency scan", "owner": "cybersecurity_analyst"},
        {"id": "performance_reliability", "label": "Performance and reliability checks", "owner": "devops"},
        {"id": "ux_browser_verification", "label": "UX, accessibility, and browser verification", "owner": "ui_ux_designer"},
        {"id": "data_privacy_compliance", "label": "Data, privacy, and compliance review", "owner": "cybersecurity_analyst"},
        {"id": "observability_analytics", "label": "Observability, analytics, and feedback loops", "owner": "devops"},
        {"id": "deployment_preview_release", "label": "Deployment preview and release plan", "owner": "devops"},
        {"id": "launch_market", "label": "Launch assets, pricing, ads, and positioning", "owner": "brand_content_designer"},
        {"id": "docs_support_operations", "label": "Docs, onboarding, support, backups, and handover", "owner": "customer_support"},
        {"id": "final_proof_gaps", "label": "Final proof report with gaps", "owner": "code_reviewer"},
    ]


def prepare_product_studio(
    root: str | Path,
    request: str,
    *,
    product_name: str = "",
    stack: dict[str, Any] | None = None,
    inspection: dict[str, Any] | None = None,
    execution_plan: dict[str, Any] | None = None,
    artifact_verification: dict[str, Any] | None = None,
    production_prep: dict[str, Any] | None = None,
    gate_results: dict[str, Any] | None = None,
    standards: dict[str, Any] | None = None,
    changed_files: list[str] | None = None,
    test_commands: list[str] | None = None,
    create_files: bool = True,
) -> dict[str, Any]:
    project_root = resolve_coding_root(root)
    name = _clean(product_name) or _product_name_from_root(project_root)
    context = {
        "root": str(project_root),
        "request": _clean(request),
        "product_name": name,
        "stack": stack or {},
        "inspection": inspection or {},
        "execution_plan": execution_plan or {},
        "artifact_verification": artifact_verification or {},
        "production_prep": production_prep or {},
        "gate_results": gate_results or {},
        "standards": standards or {},
        "changed_files": changed_files or [],
        "test_commands": test_commands or [],
    }
    launch_assets = _launch_assets(name, request)
    phases = _phase_statuses(context, launch_assets)
    final_report = _final_report(project_root, name, phases, context, launch_assets)
    artifacts = _write_artifacts(project_root, context, phases, final_report, launch_assets) if create_files else []
    summary = _summary(name, phases, final_report)
    return {
        "product_name": name,
        "root": str(project_root),
        "market_ready": bool(final_report.get("market_ready")),
        "summary": summary,
        "phases": phases,
        "launch_assets": launch_assets,
        "final_proof_report": final_report,
        "gate_results": gate_results or {},
        "artifacts": artifacts,
        "gaps": final_report.get("gaps", []),
    }


def _phase_statuses(context: dict[str, Any], launch_assets: dict[str, Any]) -> list[dict[str, Any]]:
    verification = context["artifact_verification"]
    production = context["production_prep"]
    inspection = context["inspection"]
    stack = context["stack"]
    tests = context["test_commands"] or production.get("test_commands") or []
    artifacts = production.get("artifacts") or []
    standards = context["standards"]
    findings = standards.get("findings") if isinstance(standards, dict) else []
    high_findings = [item for item in findings or [] if int(item.get("severity") or 0) >= 4]
    security = production.get("security_preflight") if isinstance(production.get("security_preflight"), dict) else {}
    performance = production.get("performance_budget") if isinstance(production.get("performance_budget"), dict) else {}
    deploy = production.get("deploy_preview") if isinstance(production.get("deploy_preview"), dict) else {}
    gate_results = context.get("gate_results") if isinstance(context.get("gate_results"), dict) else {}
    gates_attempted = bool(gate_results.get("attempted"))
    gates_summary = gate_results.get("summary") if gates_attempted else ""
    gate_gaps = product_studio_gates.gate_gaps(gate_results)
    test_gates_passed = product_studio_gates.group_passed(gate_results, "tests")
    test_gates_attempted = product_studio_gates.group_attempted(gate_results, "tests")
    security_gates_passed = product_studio_gates.group_passed(gate_results, "security")
    security_gates_attempted = product_studio_gates.group_attempted(gate_results, "security")
    browser_gate = product_studio_gates.gate_status(gate_results, "browser_check")
    preview_gate = product_studio_gates.gate_status(gate_results, "deployment_preview")
    local_preview_gate = product_studio_gates.gate_status(gate_results, "local_preview")
    browser_screenshot = _browser_screenshot(gate_results)

    phase_map = {
        "requirements_acceptance": _phase(
            "requirements_acceptance",
            "documented",
            ["Request captured", "Acceptance criteria artifact generated"],
            ["Acceptance criteria still need user/customer validation"],
        ),
        "architecture_stack": _phase(
            "architecture_stack",
            "documented" if stack else "blocked",
            [f"Stack selected: {stack.get('label') or stack.get('stack') or 'unknown'}", inspection.get("summary", "")],
            [] if stack else ["No stack decision was recorded"],
        ),
        "feature_implementation": _phase(
            "feature_implementation",
            "verified" if verification.get("status") == "passed" else "blocked",
            [verification.get("summary", ""), f"Changed files: {len(context['changed_files'])}"],
            [] if verification.get("status") == "passed" else ["Generated/changed files did not pass artifact verification"],
        ),
        "unit_integration_e2e_tests": _phase(
            "unit_integration_e2e_tests",
            "verified" if test_gates_passed else "blocked" if test_gates_attempted else "partial" if tests else "planned",
            [*tests, gates_summary],
            [] if test_gates_passed else ["Executable test/build gates have not all passed"],
        ),
        "security_dependency_scan": _phase(
            "security_dependency_scan",
            "verified" if security_gates_passed and not high_findings else "blocked" if security_gates_attempted and gate_gaps else "partial" if security or standards else "planned",
            [security.get("path", ""), standards.get("summary", "") if isinstance(standards, dict) else "", gates_summary],
            [] if security_gates_passed and not high_findings else _security_gaps(high_findings, gates_attempted=gates_attempted),
        ),
        "performance_reliability": _phase(
            "performance_reliability",
            "partial" if performance or gates_attempted else "planned",
            [performance.get("path", ""), "Rollback plan prepared" if artifacts else "", gates_summary],
            ["Performance budget/build evidence is attached, but no full load, latency, or bundle benchmark has run yet"],
        ),
        "ux_browser_verification": _phase(
            "ux_browser_verification",
            "verified" if browser_gate == "passed" else "blocked" if browser_gate in {"failed", "blocked", "timeout"} else "planned",
            ["UX/browser checklist artifact generated", browser_screenshot],
            [] if browser_gate == "passed" else ["No passing browser screenshot, accessibility sweep, or e2e browser proof is attached yet"],
        ),
        "data_privacy_compliance": _phase(
            "data_privacy_compliance",
            "planned",
            ["Privacy/data review artifact generated"],
            ["Auth, data retention, PII handling, compliance needs, and consent copy require product-specific review"],
        ),
        "observability_analytics": _phase(
            "observability_analytics",
            "planned",
            ["Observability and analytics checklist generated"],
            ["No production telemetry, alerting, analytics events, or error budget is wired yet"],
        ),
        "deployment_preview_release": _phase(
            "deployment_preview_release",
            "verified" if preview_gate == "passed" else "partial" if local_preview_gate == "passed" or deploy else "planned",
            [deploy.get("path", ""), _clean(gate_results.get("preview_url") or "")],
            [] if preview_gate == "passed" else ["No passing preview deployment inspection is attached yet"],
        ),
        "launch_market": _phase(
            "launch_market",
            "documented",
            ["Pricing, positioning, launch copy, and ads generated"],
            ["Ads are drafts only; posting/spend requires explicit approval and account setup"],
        ),
        "docs_support_operations": _phase(
            "docs_support_operations",
            "documented",
            ["Docs, onboarding, support, backup, and handover plan generated"],
            ["Support inbox, SLA, backups, runbooks, and customer docs need live configuration"],
        ),
    }
    phases = []
    for phase in studio_phases()[:-1]:
        item = phase_map.get(phase["id"], _phase(phase["id"], "planned", [], ["Phase has no evidence yet"]))
        phases.append({**phase, **item})
    phases.append(
        {
            **studio_phases()[-1],
            **_phase(
                "final_proof_gaps",
                "verified",
                ["Final proof report generated"],
                [],
            ),
        }
    )
    return phases


def _write_artifacts(
    root: Path,
    context: dict[str, Any],
    phases: list[dict[str, Any]],
    final_report: dict[str, Any],
    launch_assets: dict[str, Any],
) -> list[str]:
    studio_root = root / FRIDAY_DIR / STUDIO_DIR
    studio_root.mkdir(parents=True, exist_ok=True)
    files = {
        "requirements.md": _requirements_md(context, phases),
        "architecture.md": _architecture_md(context),
        "test-plan.md": _test_plan_md(context),
        "security-privacy.md": _security_privacy_md(context),
        "performance-reliability.md": _performance_reliability_md(context),
        "ux-browser-verification.md": _ux_browser_md(context),
        "deployment-release.md": _deployment_md(context),
        "launch-assets.md": _launch_md(launch_assets),
        "operations-support.md": _operations_md(context),
        "proof-report.md": _proof_report_md(final_report),
        "studio-plan.json": json.dumps({"phases": phases, "final_proof_report": final_report, "launch_assets": launch_assets}, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n",
        "gate-results-summary.json": json.dumps(context.get("gate_results") or {}, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n",
    }
    written: list[str] = []
    for name, content in files.items():
        path = studio_root / name
        path.write_text(content, encoding="utf-8")
        written.append(str(path))
    return written


def _final_report(
    root: Path,
    product_name: str,
    phases: list[dict[str, Any]],
    context: dict[str, Any],
    launch_assets: dict[str, Any],
) -> dict[str, Any]:
    gaps: list[str] = []
    for phase in phases:
        gaps.extend(str(item) for item in phase.get("gaps") or [] if str(item).strip())
    gate_results = context.get("gate_results") if isinstance(context.get("gate_results"), dict) else {}
    gates_attempted = bool(gate_results.get("attempted"))
    technical_ready = bool(gate_results.get("technical_ready"))
    approval_gates_cleared = bool(gate_results.get("approval_gates_cleared"))
    gaps.extend(product_studio_gates.gate_gaps(gate_results))
    if not gates_attempted:
        gaps.append("Executable product-studio gates have not run yet")
    critical_gaps = [
        gap
        for gap in gaps
        if any(word in gap.lower() for word in ("blocked", "failed", "timeout", "not run", "no live", "requires", "not wired", "not attached", "approval", "compliance", "auth"))
    ]
    market_ready = (
        technical_ready
        and approval_gates_cleared
        and not critical_gaps
        and all(phase.get("status") == "verified" for phase in phases if phase["id"] != "final_proof_gaps")
    )
    return {
        "generated_at": _now(),
        "product_name": product_name,
        "root": str(root),
        "market_ready": market_ready,
        "technical_ready": technical_ready,
        "approval_gates_cleared": approval_gates_cleared,
        "gate_status": gate_results.get("status") or ("not_run" if not gates_attempted else "unknown"),
        "phase_counts": _phase_counts(phases),
        "verified_phases": [phase["id"] for phase in phases if phase.get("status") == "verified"],
        "gaps": _dedupe(gaps),
        "critical_gaps": _dedupe(critical_gaps),
        "next_step": _next_step(technical_ready, approval_gates_cleared, critical_gaps),
        "approval_gates": [
            "explicit approval before launch actions",
            "spend money",
            "post ads",
            "send emails or messages",
            "deploy production",
            "handle customer data",
            "enable billing",
            "publish app store or marketplace listing",
        ],
        "launch_assets_ready": bool(launch_assets),
        "evidence": {
            "changed_files": context.get("changed_files") or [],
            "test_commands": context.get("test_commands") or [],
            "artifact_verification": context.get("artifact_verification") or {},
            "product_studio_gates": gate_results,
        },
    }


def _launch_assets(product_name: str, request: str) -> dict[str, Any]:
    audience = "individuals, small teams, agencies, and SMB operators"
    offer = f"{product_name} turns recurring operational work into clear actions, updates, and proof."
    return {
        "positioning": offer,
        "target_audience": audience,
        "pricing": [
            {"plan": "Free", "price": "$0", "promise": "personal workspace and manual workflows"},
            {"plan": "Pro", "price": "$12/month", "promise": "AI briefs, saved templates, and integrations"},
            {"plan": "Team", "price": "$39/month", "promise": "shared queues, approvals, analytics, and admin controls"},
        ],
        "landing_copy": {
            "headline": product_name,
            "subheadline": _clean(request) or offer,
            "primary_cta": "Start with one recurring workflow",
            "proof_points": ["save coordination time", "reduce missed handoffs", "ship customer-ready updates"],
        },
        "ads": [
            {
                "channel": "LinkedIn",
                "hook": "Your team repeats the same status work every day.",
                "body": f"{product_name} turns notes, blockers, and customer requests into action briefs your team can use.",
                "cta": "Try the workflow",
            },
            {
                "channel": "X / indie maker community",
                "hook": "Stop losing half the day to tiny ops tasks.",
                "body": f"I built {product_name} to convert recurring work into owners, risks, and sendable updates.",
                "cta": "Join the first-user list",
            },
            {
                "channel": "Google Search",
                "hook": "AI workflow assistant for small teams",
                "body": "Capture work, draft updates, and keep handoffs moving with approval-gated automation.",
                "cta": "See product",
            },
        ],
        "docs": ["README", "quickstart", "admin setup", "security notes", "support handoff"],
    }


def _phase(phase_id: str, status: str, evidence: list[str], gaps: list[str]) -> dict[str, Any]:
    return {
        "id": phase_id,
        "status": status,
        "evidence": [item for item in evidence if _clean(item)],
        "gaps": [item for item in gaps if _clean(item)],
    }


def _security_gaps(high_findings: list[dict[str, Any]], *, gates_attempted: bool = False) -> list[str]:
    gaps = ["Dependency audit, secret scan, and threat model have not all passed against installed dependencies yet"]
    if not gates_attempted:
        gaps.append("Security/dependency gates have not executed yet")
    if high_findings:
        gaps.append(f"{len(high_findings)} high-severity codebase standard finding(s) need review")
    return gaps


def _requirements_md(context: dict[str, Any], phases: list[dict[str, Any]]) -> str:
    return _md(
        "Requirements and Acceptance Criteria",
        [
            f"Product: {context['product_name']}",
            f"Request: {context['request']}",
            "",
            "Acceptance Criteria:",
            "- Core user can complete the primary workflow without developer intervention.",
            "- All customer-visible actions are approval-gated until configured otherwise.",
            "- Security, tests, performance, deployment, docs, and launch proof are attached before market-ready claims.",
            "- Final report clearly states remaining gaps.",
            "",
            "Studio Phases:",
            *[f"- {phase['label']}: {phase['status']}" for phase in phases],
        ],
    )


def _architecture_md(context: dict[str, Any]) -> str:
    stack = context["stack"]
    return _md(
        "Architecture and Stack Decision",
        [
            f"Selected stack: {stack.get('label') or stack.get('stack') or 'not selected'}",
            f"Language: {stack.get('language') or 'unknown'}",
            f"Kind: {stack.get('kind') or 'unknown'}",
            "",
            "Rationale:",
            "- Match the user's requested surface first: web-app -> Next.js, mobile -> Flutter, backend -> requested language or Fastify default.",
            "- Keep route/UI, state, domain logic, validation, persistence, tests, and proof separated.",
            "- Prefer boring file names and explicit boundaries.",
        ],
    )


def _test_plan_md(context: dict[str, Any]) -> str:
    tests = context.get("test_commands") or context.get("production_prep", {}).get("test_commands") or []
    return _md(
        "Test Plan",
        [
            "Required layers:",
            "- Unit tests for domain logic.",
            "- Integration tests for API routes and persistence.",
            "- E2E/browser tests for the primary user flow.",
            "- Smoke tests for deployment preview.",
            "",
            "Discovered commands:",
            *([f"- `{command}`" for command in tests] if tests else ["- No executable test command discovered yet."]),
        ],
    )


def _security_privacy_md(context: dict[str, Any]) -> str:
    return _md(
        "Security, Privacy, and Compliance",
        [
            "Required checks:",
            "- Secret scan and environment variable review.",
            "- Dependency audit after install.",
            "- Auth, authorization, CORS, CSRF/XSS, injection, rate limiting, and abuse review.",
            "- PII inventory, retention policy, export/delete path, and consent copy where needed.",
            "- Approval gate for outbound messages, ad posting, billing, production deploy, and customer data access.",
        ],
    )


def _performance_reliability_md(context: dict[str, Any]) -> str:
    return _md(
        "Performance and Reliability",
        [
            "Required checks:",
            "- Build time, bundle size, API latency, and cold-start budget.",
            "- Timeout and retry behavior for network calls.",
            "- Error handling, logging, rollback, and degraded states.",
            "- Load test or realistic workflow timing before market-ready claim.",
        ],
    )


def _ux_browser_md(context: dict[str, Any]) -> str:
    return _md(
        "UX, Accessibility, and Browser Verification",
        [
            "Required checks:",
            "- Desktop and mobile screenshot review.",
            "- Primary workflow click-through.",
            "- Keyboard and screen-reader basics.",
            "- No overlapping UI, unreadable text, dead buttons, or broken empty states.",
            "- Attach browser proof before claiming market-ready.",
        ],
    )


def _deployment_md(context: dict[str, Any]) -> str:
    return _md(
        "Deployment Preview and Release",
        [
            "Required checks:",
            "- Environment variables configured in the target host.",
            "- Preview deployment URL attached.",
            "- Smoke test proof against preview.",
            "- Rollback target and owner recorded.",
            "- Production deployment requires explicit approval.",
        ],
    )


def _launch_md(assets: dict[str, Any]) -> str:
    ads = assets.get("ads") or []
    pricing = assets.get("pricing") or []
    lines = [
        "Positioning:",
        str(assets.get("positioning") or ""),
        "",
        "Pricing:",
        *[f"- {item.get('plan')}: {item.get('price')} - {item.get('promise')}" for item in pricing],
        "",
        "Ad Drafts:",
    ]
    for ad in ads:
        lines.extend([f"- Channel: {ad.get('channel')}", f"  Hook: {ad.get('hook')}", f"  Body: {ad.get('body')}", f"  CTA: {ad.get('cta')}"])
    lines.extend(["", "Posting ads or spending money requires explicit approval."])
    return _md("Launch Assets, Pricing, Ads, and Positioning", lines)


def _operations_md(context: dict[str, Any]) -> str:
    return _md(
        "Docs, Support, and Operations",
        [
            "Required before market-ready:",
            "- Quickstart and admin setup docs.",
            "- Support inbox or support form.",
            "- Customer data backup and restore path.",
            "- Incident runbook and escalation owner.",
            "- Analytics events for activation, retention, conversion, and failure points.",
            "- Cost controls for AI/provider usage.",
        ],
    )


def _proof_report_md(report: dict[str, Any]) -> str:
    return _md(
        "Final Proof Report",
        [
            f"Market ready: {report.get('market_ready')}",
            f"Technical ready: {report.get('technical_ready')}",
            f"Gate status: {report.get('gate_status')}",
            f"Next step: {report.get('next_step')}",
            "",
            "Critical Gaps:",
            *[f"- {gap}" for gap in (report.get("critical_gaps") or ["None recorded."])],
            "",
            "All Gaps:",
            *[f"- {gap}" for gap in (report.get("gaps") or ["None recorded."])],
        ],
    )


def _summary(product_name: str, phases: list[dict[str, Any]], final_report: dict[str, Any]) -> str:
    counts = _phase_counts(phases)
    if final_report.get("market_ready"):
        status = "market-ready"
    elif final_report.get("technical_ready"):
        status = "technically gated but waiting on launch/approval gaps"
    else:
        status = "not market-ready yet"
    return f"{product_name} product-studio proof is {status}: {counts.get('verified', 0)} verified, {counts.get('partial', 0)} partial, {counts.get('planned', 0)} planned phase(s)."


def _next_step(technical_ready: bool, approval_gates_cleared: bool, critical_gaps: list[str]) -> str:
    if not technical_ready:
        return "Fix failed or blocked executable gates, then rerun install, tests, audit, browser, and preview checks."
    if not approval_gates_cleared:
        return "Review proof, clear explicit launch approvals, then rerun final readiness."
    if critical_gaps:
        return "Close the remaining product, security, privacy, launch, or operations gaps."
    return "Review final proof and approve launch."


def _browser_screenshot(gate_results: dict[str, Any]) -> str:
    for gate in gate_results.get("gates") or []:
        if isinstance(gate, dict) and gate.get("id") == "browser_check" and gate.get("screenshot"):
            return f"Browser screenshot: {gate.get('screenshot')}"
    return ""


def _phase_counts(phases: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for phase in phases:
        status = str(phase.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _md(title: str, lines: list[str]) -> str:
    body = "\n".join(str(line) for line in lines)
    return f"# {title}\n\n{body.strip()}\n"


def _product_name_from_root(root: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]+", " ", root.name).strip().title().replace(" ", "") or "FridayProduct"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        clean = _clean(item)
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

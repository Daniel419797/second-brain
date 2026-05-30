"""Friday's explicit engineering habits and preflight discipline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import coding_workflow, project_intelligence, style_profiles


QUALITY_PRIORITIES = [
    "security",
    "speed_and_performance",
    "maintainability",
    "reliability",
    "practical_reusability",
    "readability",
    "good_coding_practices",
]


def operating_habits() -> list[dict[str, str]]:
    return [
        {"id": "understand", "label": "Understand", "rule": "Inspect the repo, stack, tests, style profile, and user intent before editing."},
        {"id": "plan", "label": "Plan", "rule": "Create a short implementation plan with acceptance criteria and ownership boundaries."},
        {"id": "implement", "label": "Implement", "rule": "Keep edits scoped and split responsibilities by routes, UI, state, services, validation, persistence, and tests."},
        {"id": "verify", "label": "Verify", "rule": "Run executable gates and collect logs, screenshots, artifacts, and preview evidence."},
        {"id": "fix", "label": "Fix", "rule": "When a required gate fails, fix the smallest meaningful cause and rerun failed gates."},
        {"id": "prove", "label": "Prove", "rule": "Write a final proof report and never mark readiness from prose alone."},
        {"id": "remember", "label": "Remember", "rule": "Store reusable project conventions, failures, and successful patterns without secrets."},
        {"id": "improve", "label": "Improve", "rule": "Use memory to avoid repeating failures and to match the user's house style."},
    ]


def preflight(root: str | Path, request: str, *, stack: dict[str, Any] | None = None, execution_kind: str = "") -> dict[str, Any]:
    intelligence = project_intelligence.inspect_project(root, request, stack=stack)
    workflow_inspection = intelligence.get("workflow_inspection") if isinstance(intelligence.get("workflow_inspection"), dict) else {}
    plan = coding_workflow.build_execution_plan(
        request,
        root,
        stack=intelligence.get("stack") if isinstance(intelligence.get("stack"), dict) else stack,
        inspection=workflow_inspection,
        standards={},
        execution_kind=execution_kind or "friday_os_run",
    )
    architecture = project_intelligence.architecture_decision(intelligence, request)
    acceptance = acceptance_criteria(intelligence)
    return {
        "habits": operating_habits(),
        "quality_priorities": QUALITY_PRIORITIES,
        "intelligence": intelligence,
        "architecture": architecture,
        "execution_plan": plan,
        "acceptance_criteria": acceptance,
        "style_profile": intelligence.get("style_profile") or {},
        "style_evaluation": intelligence.get("style_evaluation") or {},
        "summary": f"Preflight complete: {intelligence.get('summary')}",
    }


def acceptance_criteria(intelligence: dict[str, Any] | None = None) -> list[str]:
    criteria = [
        "A project inspection is recorded before implementation.",
        "Architecture and stack decision are explicit.",
        "Responsibilities are separated by project convention.",
        "Real files or approved artifacts are produced.",
        "Install, tests/build, security, browser/preview, performance, env, ops, docs, and launch gates are recorded where applicable.",
        "Technical readiness requires required technical gates to pass.",
        "Market readiness requires technical readiness plus launch assets, privacy/security notes, support path, analytics/observability plan, preview proof, and approvals.",
        "Final proof names remaining gaps honestly.",
    ]
    style = intelligence.get("style_profile") if isinstance(intelligence, dict) and isinstance(intelligence.get("style_profile"), dict) else {}
    if style.get("id") == "nexus_forge_nextjs":
        criteria.append("Next.js frontend follows the NexusForge profile: thin app routes, feature components, ui primitives, services, stores, hooks, lib, types, and Vitest setup.")
    return criteria


def readiness_policy() -> dict[str, Any]:
    return {
        "technical_ready": "Only true when required executable technical gates pass and proof artifacts exist.",
        "market_ready": "Only true when technical_ready is true and market approvals, launch assets, privacy/security notes, support, analytics, preview proof, and gaps are complete.",
        "approval_gated": ["deploy_preview", "deploy_production", "post_ads", "enable_billing", "send_outreach", "customer_data_access", "paid_api_spend"],
        "never_claim_done_without": ["inspection", "artifacts", "gate_results", "final_proof_report"],
    }


def evaluate_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    gaps = []
    if not isinstance(evidence.get("inspection"), dict) or not evidence["inspection"]:
        gaps.append("Missing project inspection.")
    if not isinstance(evidence.get("architecture"), dict) or not evidence["architecture"]:
        gaps.append("Missing architecture decision.")
    if not evidence.get("artifacts"):
        gaps.append("Missing real artifacts.")
    gate_results = evidence.get("gate_results") if isinstance(evidence.get("gate_results"), dict) else {}
    if not gate_results.get("attempted"):
        gaps.append("Missing executable gate results.")
    if not evidence.get("final_proof_report"):
        gaps.append("Missing final proof report.")
    return {
        "ok": not gaps,
        "gaps": gaps,
        "policy": readiness_policy(),
        "summary": "Engineering evidence is complete." if not gaps else f"Engineering evidence has {len(gaps)} gap(s).",
    }


def apply_default_style_memory(root: str | Path) -> dict[str, Any]:
    profile = style_profiles.infer_profile(root, "nextjs")
    if not profile:
        return {"ok": False, "summary": "No default style profile applies."}
    return style_profiles.apply_profile(root, profile["id"])

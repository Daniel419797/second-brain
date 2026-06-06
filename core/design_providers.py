"""Design-generation provider policy for Friday's UI and frontend agents."""

from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from core.config import ROOT_DIR, config_value, resolve_coding_root
from core import command_runner, design_asset_manager, design_continuity, design_director, design_prompt_compiler, design_visual_reviewer, friday_learning_loop, project_scaffolds, style_profiles


def status(*, probe: bool = False, root: str | Path = "") -> dict[str, Any]:
    """Return safe design-provider readiness without exposing credentials."""

    base = resolve_coding_root(root or "") if str(root or "").strip() else ROOT_DIR
    providers = {
        "stitch": _stitch_status(probe=probe),
        "v0": _v0_status(),
        "local_style_memory": _local_style_memory_status(base),
    }
    order = provider_order()
    selected = {
        "ui_design_agent": _select_ui_design_provider(providers, order),
        "frontend_agent": _select_frontend_provider(providers, order),
        "style_memory": "local_style_memory" if providers["local_style_memory"]["ready"] else "",
    }
    missing = _missing_steps(providers)
    return {
        "ok": bool(selected["ui_design_agent"] or selected["style_memory"]),
        "probe": probe,
        "root": str(base),
        "provider_order": order,
        "providers": providers,
        "selected": selected,
        "missing": missing,
        "summary": _summary(providers, selected, missing),
    }


def stitch_debug(*, root: str | Path = "", limit: int = 12) -> dict[str, Any]:
    """Return safe Stitch attempt/debug artifacts for Friday Studio."""

    base = resolve_coding_root(root or "") if str(root or "").strip() else ROOT_DIR
    design_root = base / ".friday" / "design"
    provider_status = status(probe=False, root=base)
    reports = _collect_stitch_json_artifacts(design_root, "stitch-reliability-report*.json", limit=limit)
    attempts = _collect_stitch_json_artifacts(design_root, "stitch-attempt-*.json", limit=limit)
    raw_manifests = _collect_stitch_json_artifacts(design_root, "stitch*raw-response-manifest.json", limit=limit)
    latest = reports[0]["data"] if reports else {}
    return {
        "ok": bool(provider_status.get("providers", {}).get("stitch", {}).get("ready")),
        "root": str(base),
        "design_root": str(design_root),
        "fallback_policy": _stitch_fallback_policy({"root": str(base), "provider_status": provider_status, "stack": {"stack": "nextjs"}}),
        "provider_status": provider_status.get("providers", {}).get("stitch", {}),
        "selected": provider_status.get("selected", {}),
        "latest": latest,
        "reports": reports,
        "attempts": attempts,
        "raw_manifests": raw_manifests,
        "summary": _stitch_debug_summary(provider_status, latest, reports, attempts),
    }


def _collect_stitch_json_artifacts(design_root: Path, pattern: str, *, limit: int = 12) -> list[dict[str, Any]]:
    if not design_root.exists():
        return []
    paths = sorted(design_root.rglob(pattern), key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
    items: list[dict[str, Any]] = []
    for path in paths[: max(1, min(50, int(limit or 12)))]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            data = {"status": "unreadable", "summary": str(exc)}
        items.append(
            {
                "path": str(path),
                "updated_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
                "data": _sanitize_stitch_payload(data),
            }
        )
    return items


def _stitch_debug_summary(provider_status: dict[str, Any], latest: dict[str, Any], reports: list[dict[str, Any]], attempts: list[dict[str, Any]]) -> str:
    stitch = provider_status.get("providers", {}).get("stitch", {}) if isinstance(provider_status.get("providers"), dict) else {}
    if not stitch.get("ready"):
        return stitch.get("reason") or "Stitch is not configured."
    if latest:
        status_text = latest.get("status") or "recorded"
        attempts_text = latest.get("attempt_count") or len(attempts)
        source = "succeeded" if latest.get("ok") else "did not produce an accepted screen"
        return f"Latest Stitch run {source}: {status_text}, {attempts_text} attempt(s)."
    if reports:
        return "Stitch reports are present but no latest payload was readable."
    return "Stitch is configured, but no reliability report has been recorded yet."


def provider_order() -> list[str]:
    raw = str(config_value("design_provider_chain", "stitch>local_style_memory>v0") or "")
    providers = [_clean(item).lower() for item in raw.replace(",", ">").split(">") if _clean(item)]
    return providers or ["stitch", "local_style_memory", "v0"]


def agent_context(agent_id: str, request: str = "", *, root: str | Path = "") -> str:
    """Small prompt note injected into design/frontend agents."""

    normalized = str(agent_id or "").strip().lower()
    if normalized not in {"ui_ux_designer", "frontend_developer"}:
        return ""
    payload = status(probe=False, root=root)
    providers = payload["providers"]
    selected = payload["selected"]
    lines = [
        "Design provider policy:",
        "- UI design agent should use Google Stitch SDK first when STITCH_API_KEY and the SDK are configured.",
        "- Frontend agent may use v0 only when Friday has verified it is free for this workspace; otherwise treat it as unavailable.",
        "- Design-system memory uses local style profiles by default and is free; do not call paid Figma/design APIs unless explicitly approved.",
        "- Design critique loop should generate 2-3 variants, score each against product fit and style memory, reject weak variants, and hand off only the selected design.",
        f"- Selected UI design provider: {selected.get('ui_design_agent') or 'none'}",
        f"- Selected frontend provider: {selected.get('frontend_agent') or 'none'}",
        f"- Local style profile count: {len(providers['local_style_memory'].get('profiles') or [])}",
    ]
    if normalized == "ui_ux_designer" and not providers["stitch"].get("ready"):
        lines.append(f"- Stitch blocked: {providers['stitch'].get('reason')}")
    if normalized == "frontend_developer" and providers["v0"].get("blocked"):
        lines.append(f"- v0 blocked: {providers['v0'].get('reason')}")
    if normalized == "frontend_developer":
        lines.append("- If .friday/design/frontend-handoff.md exists, convert only its selected design; rejected variants are not valid source material.")
    if _clean(request):
        lines.append(f"- Current design request: {_clean(request)[:300]}")
    return "\n".join(lines)


def design_brief(
    request: str,
    *,
    root: str | Path = "",
    product_name: str = "",
    stack: dict[str, Any] | None = None,
    create_files: bool = True,
    artifact_scope: str = "",
    research_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a provider-aware design brief for product-studio work."""

    project_root = resolve_coding_root(root or "")
    original_request = _clean(request)
    initial_product_name = _clean(product_name) or _product_name_from_request(original_request)
    brief_autopilot = _brief_autopilot(original_request, initial_product_name, stack or {}, project_root)
    effective_request = _clean(brief_autopilot.get("expanded_request")) or original_request
    planning_request = effective_request if (brief_autopilot.get("vague") or brief_autopilot.get("product_missing")) else original_request
    resolved_product_name = _clean(brief_autopilot.get("product_name")) or initial_product_name
    provider_status = status(probe=False, root=project_root)
    profile = style_profiles.infer_profile(project_root, (stack or {}).get("stack", "")) or style_profiles.get_profile("nexus_forge_nextjs") or {}
    design_root = _design_root(project_root, artifact_scope)
    contract = _design_contract(planning_request, resolved_product_name, stack or {}, artifact_scope=artifact_scope)
    strategy = design_director.design_strategy(
        planning_request,
        resolved_product_name,
        page_label=contract.get("page_label") or "",
        stack=stack or {},
    )
    design_context = _design_context_package(
        project_root,
        planning_request,
        resolved_product_name,
        stack or {},
        profile,
        contract,
        strategy,
        artifact_scope=artifact_scope,
        original_request=original_request,
        expanded_request=effective_request,
        brief_autopilot=brief_autopilot,
        research_context=research_context,
    )
    raw_stitch_prompt = _stitch_prompt(
        planning_request,
        resolved_product_name,
        profile,
        stack or {},
        contract=contract,
        strategy=strategy,
        design_context=design_context,
    )
    compiled_prompt = _compile_stitch_prompt(
        design_context,
        profile,
        stack or {},
        contract,
        strategy,
        raw_prompt=raw_stitch_prompt,
    )
    brief = {
        "request": original_request,
        "expanded_request": effective_request,
        "product_name": resolved_product_name,
        "root": str(project_root),
        "design_root": str(design_root),
        "artifact_scope": _clean_artifact_scope(artifact_scope),
        "stack": stack or {},
        "provider_status": provider_status,
        "style_profile": profile,
        "brief_autopilot": brief_autopilot,
        "design_contract": contract,
        "design_strategy": strategy,
        "design_context": design_context,
        "stitch_prompt_full": raw_stitch_prompt,
        "stitch_prompt_compilation": compiled_prompt["metadata"],
        "instructions": [
            "Use Stitch SDK for UI exploration when configured; capture screenshots or exported HTML as evidence.",
            "Generate 2-3 design variants before accepting a direction when live design generation is approved.",
            "Score each variant against product/domain fit, user style memory, accessibility, copy quality, operational density, and frontend feasibility.",
            "Reject weak variants and convert only the highest-scoring accepted design into frontend implementation guidance.",
            "Use v0 only as a frontend-code fallback when a free allowance is verified.",
            "Use local style profiles and user style memory by default because they are free.",
            "Treat style profile names as internal implementation guidance; never render them as product branding unless the user requested that brand.",
            "Never accept generated design blindly; run browser, product-fit, UX/copy, accessibility, and dead-button gates.",
        ],
        "stitch_prompt": compiled_prompt["prompt"],
    }
    artifacts: list[str] = []
    if create_files:
        design_root.mkdir(parents=True, exist_ok=True)
        json_path = design_root / "design-provider-plan.json"
        md_path = design_root / "design-brief.md"
        context_path = design_root / "design-context.json"
        design_md_path = design_root / "DESIGN.md"
        stitch_prompt_path = design_root / "stitch-prompt.md"
        prompt_call_plan_path = design_root / "stitch-prompt-call-plan.json"
        base_design_root = project_root / ".friday" / "design"
        site_system_path = base_design_root / "site-design-system.json"
        json_path.write_text(json.dumps(brief, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        md_path.write_text(markdown(brief), encoding="utf-8")
        context_path.write_text(json.dumps(design_context, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        design_md_path.write_text(_design_context_markdown(brief), encoding="utf-8")
        stitch_prompt_path.write_text(brief["stitch_prompt"] + "\n", encoding="utf-8")
        prompt_call_plan_path.write_text(json.dumps(compiled_prompt["metadata"].get("call_plan") or [], ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        site_system = (design_context.get("site_continuity") or {}).get("site_design_system") if isinstance(design_context.get("site_continuity"), dict) else {}
        if isinstance(site_system, dict) and site_system:
            base_design_root.mkdir(parents=True, exist_ok=True)
            site_system_path.write_text(json.dumps(site_system, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
            artifacts.append(str(site_system_path))
        artifacts.extend([str(json_path), str(md_path), str(context_path), str(design_md_path), str(stitch_prompt_path), str(prompt_call_plan_path)])
    return brief | {"artifacts": artifacts}


def markdown(brief: dict[str, Any]) -> str:
    status_payload = brief.get("provider_status") if isinstance(brief.get("provider_status"), dict) else {}
    providers = status_payload.get("providers") if isinstance(status_payload.get("providers"), dict) else {}
    profile = brief.get("style_profile") if isinstance(brief.get("style_profile"), dict) else {}
    design_context = brief.get("design_context") if isinstance(brief.get("design_context"), dict) else {}
    inspiration = design_context.get("inspiration_references") if isinstance(design_context.get("inspiration_references"), list) else []
    learned = design_context.get("learned_rules") if isinstance(design_context.get("learned_rules"), dict) else {}
    autopilot = brief.get("brief_autopilot") if isinstance(brief.get("brief_autopilot"), dict) else {}
    return "\n".join(
        [
            "# Design Provider Plan",
            "",
            f"Product: {_clean(brief.get('product_name')) or 'Unnamed product'}",
            f"Request: {_clean(brief.get('request'))}",
            "",
            "## Provider Policy",
            f"- Stitch: {_provider_line(providers.get('stitch'))}",
            f"- v0: {_provider_line(providers.get('v0'))}",
            f"- Local style memory: {_provider_line(providers.get('local_style_memory'))}",
            "",
            "## Style Memory",
            f"- Profile: {profile.get('name') or profile.get('id') or 'none'}",
            "",
            "## Design Contract",
            f"- Page: {(brief.get('design_contract') or {}).get('page_label') or 'primary screen'}",
            f"- Objective: {(brief.get('design_contract') or {}).get('objective') or 'not recorded'}",
            f"- Required sections: {', '.join((brief.get('design_contract') or {}).get('required_sections') or [])}",
            f"- Scale rule: {(brief.get('design_contract') or {}).get('scale_rule') or 'not recorded'}",
            "",
            "## Brief Autopilot",
            f"- Active: {autopilot.get('active')}",
            f"- Expanded request: {_prompt_clip(_clean(brief.get('expanded_request')), 900)}",
            f"- Assumption: {autopilot.get('assumption_summary') or 'none'}",
            f"- Smart default: {(autopilot.get('smart_defaults') or {}).get('selected_default') or 'not recorded'}",
            f"- Selected direction: {((autopilot.get('design_direction_generator') or {}).get('selected')) or 'not recorded'}",
            f"- Research status: {(autopilot.get('research_before_design') or {}).get('status') or 'not recorded'}",
            "",
            "## Art Direction",
            f"- Direction: {(brief.get('design_strategy') or {}).get('direction') or 'not recorded'}",
            f"- Visual language: {(brief.get('design_strategy') or {}).get('visual_language') or 'not recorded'}",
            f"- Layout signature: {(brief.get('design_strategy') or {}).get('layout_signature') or 'not recorded'}",
            f"- Palette: {(brief.get('design_strategy') or {}).get('palette') or 'not recorded'}",
            *[f"- Variant direction: {item}" for item in ((brief.get('design_strategy') or {}).get('variant_directions') or [])[:3]],
            *[f"- {rule}" for rule in (profile.get("rules") or [])[:12]],
            "",
            "## Rich Design Context",
            f"- Product goal: {design_context.get('product_goal') or 'not recorded'}",
            f"- Target audience: {', '.join(design_context.get('target_audience') or []) or 'not recorded'}",
            f"- Emotional intent: {design_context.get('emotional_intent') or 'not recorded'}",
            f"- Core message: {design_context.get('message') or 'not recorded'}",
            *[f"- Inspiration direction: {(item or {}).get('name')}: {(item or {}).get('why')}" for item in inspiration[:4] if isinstance(item, dict)],
            f"- Learned rules: {learned.get('summary') or 'none'}",
            "- Context artifacts: design-context.json, DESIGN.md, stitch-prompt.md, and site-design-system.json",
            f"- Stitch prompt compilation: {(brief.get('stitch_prompt_compilation') or {}).get('compiled_length') or 0}/{(brief.get('stitch_prompt_compilation') or {}).get('budget') or 'unknown'} chars",
            "",
            "## Stitch Prompt",
            "",
            str(brief.get("stitch_prompt") or ""),
            "",
            "## Guardrails",
            *[f"- {item}" for item in brief.get("instructions") or []],
            "",
        ]
    )


def design_critique_plan(brief: dict[str, Any], *, variant_count: int | None = None) -> dict[str, Any]:
    """Return the non-network plan for Friday's design critique loop."""

    if not bool(config_value("design_critique_enabled", True)):
        return _critique_report(
            brief,
            [],
            selected=None,
            status="disabled",
            summary="Design critique loop is disabled by design_critique_enabled=false.",
            frontend_handoff_allowed=False,
        )
    return _critique_plan(brief, _variant_count(variant_count))


def generate_with_stitch(request: str, *, root: str | Path = "", product_name: str = "", dry_run: bool = True) -> dict[str, Any]:
    """Prepare or execute a Stitch SDK design request.

    Friday does not make external design calls from this helper unless dry_run is
    explicitly false, the SDK is installed, and credentials are configured.
    """

    brief = design_brief(request, root=root, product_name=product_name, create_files=True)
    stitch = brief["provider_status"]["providers"]["stitch"]
    if dry_run:
        return {
            "ok": False,
            "status": "planned",
            "provider": "stitch",
            "summary": "Stitch design request prepared; dry_run=True so no external API call was made.",
            "brief": brief,
            "artifacts": brief.get("artifacts") or [],
        }
    if not stitch.get("ready"):
        return {
            "ok": False,
            "status": "blocked",
            "provider": "stitch",
            "summary": stitch.get("reason") or "Stitch SDK is not ready.",
            "brief": brief,
            "artifacts": brief.get("artifacts") or [],
        }
    return _run_stitch_reliable(brief, variant_count=1, purpose="base")


def run_design_critique_loop(
    request: str,
    *,
    root: str | Path = "",
    product_name: str = "",
    stack: dict[str, Any] | None = None,
    variant_count: int | None = None,
    dry_run: bool = True,
    artifact_scope: str = "",
    research_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate variants, score them, and create a selected frontend handoff.

    The live Stitch call stays behind dry_run=False because it can consume an
    external provider quota. Dry runs still write the critique plan so the UI and
    product-studio proof can show exactly what would happen.
    """

    brief = design_brief(
        request,
        root=root,
        product_name=product_name,
        stack=stack or {},
        create_files=True,
        artifact_scope=artifact_scope,
        research_context=research_context,
    )
    design_root = Path(str(brief.get("design_root") or Path(str(brief.get("root") or ROOT_DIR)) / ".friday" / "design"))
    count = _variant_count(variant_count)
    fallback_policy = _stitch_fallback_policy(brief)
    if not bool(config_value("design_critique_enabled", True)):
        report = _critique_report(
            brief,
            [],
            selected=None,
            status="disabled",
            summary="Design critique loop is disabled by design_critique_enabled=false.",
            frontend_handoff_allowed=False,
        )
        artifacts = _write_design_critique_artifacts(design_root, report)
        return {
            "ok": False,
            "status": "disabled",
            "provider": "design_critique_loop",
            "summary": report["summary"],
            "brief": brief,
            "variant_count": count,
            "frontend_handoff_allowed": False,
            "artifacts": [*(brief.get("artifacts") or []), *artifacts],
            **report,
        }
    if dry_run:
        plan = _critique_plan(brief, count)
        artifacts = _write_design_critique_artifacts(design_root, plan)
        return {
            "ok": False,
            "status": "planned",
            "provider": "design_critique_loop",
            "summary": f"Design critique loop planned for {count} variant(s); dry_run=True so no external design call was made.",
            "brief": brief,
            "variant_count": count,
            "frontend_handoff_allowed": False,
            "artifacts": [*(brief.get("artifacts") or []), *artifacts],
            **plan,
        }
    stitch = brief["provider_status"]["providers"]["stitch"]
    if not stitch.get("ready"):
        generation = {
            "ok": False,
            "status": "blocked",
            "provider": "stitch",
            "summary": stitch.get("reason") or "Stitch SDK is not ready.",
            "brief": brief,
            "artifacts": brief.get("artifacts") or [],
        }
        fallback = _fallback_critique_after_stitch_problem(
            brief,
            count,
            generation,
            design_root,
            fallback_policy=fallback_policy,
            reason=str(generation["summary"]),
        )
        if fallback:
            return fallback
        report = _critique_report(
            brief,
            [],
            selected=None,
            status="blocked",
            summary=str(generation["summary"]),
            frontend_handoff_allowed=False,
            generation=generation,
        )
        artifacts = _write_design_critique_artifacts(design_root, report)
        return {
            "ok": False,
            "status": "blocked",
            "provider": "design_critique_loop",
            "summary": report["summary"],
            "brief": brief,
            "variant_count": count,
            "frontend_handoff_allowed": False,
            "artifacts": [*(brief.get("artifacts") or []), *artifacts],
            **report,
        }
    generation = _run_stitch_reliable(brief, variant_count=count, purpose="base")
    if not generation.get("ok"):
        fallback = _fallback_critique_after_stitch_problem(
            brief,
            count,
            generation,
            design_root,
            fallback_policy=fallback_policy,
            reason=str(generation.get("summary") or "Stitch generation failed."),
        )
        if fallback:
            return fallback
        report = _critique_report(
            brief,
            [],
            selected=None,
            status=str(generation.get("status") or "failed"),
            summary=str(generation.get("summary") or "Design generation failed."),
            frontend_handoff_allowed=False,
            generation=generation,
        )
        artifacts = _write_design_critique_artifacts(design_root, report)
        return {
            "ok": False,
            "status": report["status"],
            "provider": "design_critique_loop",
            "summary": report["summary"],
            "brief": brief,
            "generation": generation,
            "variant_count": count,
            "frontend_handoff_allowed": False,
            "artifacts": [*(generation.get("artifacts") or []), *artifacts],
            **report,
        }
    variants = _normalize_variants(generation.get("result") or {})
    variants = _attach_variant_assets(variants, design_root)
    critique_brief = {
        **brief,
        "expected_variant_count": count,
        "provider_generation_status": generation.get("status"),
        "single_variant_allowed": bool(config_value("design_single_variant_handoff_allowed", False)),
    }
    critique = critique_design_variants(
        variants,
        critique_brief,
        visual_review=bool(config_value("design_variant_visual_review_enabled", True)),
    )
    revision_attempts: list[dict[str, Any]] = [
        {
            "attempt": 0,
            "status": critique.get("status"),
            "summary": critique.get("summary"),
            "frontend_handoff_allowed": bool(critique.get("frontend_handoff_allowed")),
        }
    ]
    max_revisions = max(0, min(2, int(config_value("design_critique_revision_attempts", 1) or 0)))
    for attempt in range(1, max_revisions + 1):
        if critique.get("frontend_handoff_allowed"):
            break
        revision_brief = _revision_brief_from_critique(brief, critique, attempt=attempt)
        revised_generation = _run_stitch_reliable(revision_brief, variant_count=count, purpose=f"revision-{attempt}")
        revision_attempt: dict[str, Any] = {
            "attempt": attempt,
            "generation_ok": bool(revised_generation.get("ok")),
            "generation_status": revised_generation.get("status"),
            "feedback": revision_brief.get("design_revision_feedback"),
        }
        if not revised_generation.get("ok"):
            revision_attempt["summary"] = revised_generation.get("summary") or revised_generation.get("error") or "Revision generation failed."
            revision_attempts.append(revision_attempt)
            break
        revised_variants = _normalize_variants(revised_generation.get("result") or {})
        revised_variants = _attach_variant_assets(revised_variants, design_root)
        revision_critique_brief = {
            **revision_brief,
            "expected_variant_count": count,
            "provider_generation_status": revised_generation.get("status"),
            "single_variant_allowed": bool(config_value("design_single_variant_handoff_allowed", False)),
        }
        revised_critique = critique_design_variants(
            revised_variants,
            revision_critique_brief,
            visual_review=bool(config_value("design_variant_visual_review_enabled", True)),
        )
        revision_attempt.update(
            {
                "status": revised_critique.get("status"),
                "summary": revised_critique.get("summary"),
                "frontend_handoff_allowed": bool(revised_critique.get("frontend_handoff_allowed")),
            }
        )
        revision_attempts.append(revision_attempt)
        generation = revised_generation
        brief = revision_brief
        critique = revised_critique
    if not critique.get("frontend_handoff_allowed"):
        fallback = _fallback_critique_after_stitch_problem(
            brief,
            count,
            generation,
            design_root,
            fallback_policy=_stitch_fallback_policy(brief),
            reason=f"Stitch design failed critique: {critique.get('summary') or 'no selected design'}.",
            source_critique=critique,
        )
        if fallback:
            return {
                **fallback,
                "revision_attempts": revision_attempts,
                "stitch_critique": critique,
            }
    if len(revision_attempts) > 1:
        critique = {
            **critique,
            "revision_attempts": revision_attempts,
            "summary": _clean(
                f"{critique.get('summary') or ''} "
                f"Design revision attempts: {len(revision_attempts) - 1}."
            ),
        }
    critique = {
        **critique,
        "source_provider": "stitch",
        "provider_source": "google_stitch_sdk",
        "fallback_label": "This design came from Google Stitch.",
        "stitch_generation": generation,
        "stitch_fallback_policy": _stitch_fallback_policy(brief),
        "stitch_required": _stitch_fallback_policy(brief) == "stitch_required",
    }
    artifacts = _write_design_critique_artifacts(design_root, critique)
    return {
        "ok": bool(critique.get("frontend_handoff_allowed")),
        "status": critique.get("status"),
        "provider": "design_critique_loop",
        "summary": critique.get("summary"),
        "brief": brief,
        "generation": generation,
        "variant_count": count,
        "frontend_handoff_allowed": bool(critique.get("frontend_handoff_allowed")),
        "artifacts": _dedupe([*(generation.get("artifacts") or []), *(critique.get("artifacts") or []), *artifacts]),
        **critique,
    }


def run_multipage_website_design_critique(
    request: str,
    *,
    root: str | Path = "",
    product_name: str = "",
    stack: dict[str, Any] | None = None,
    variant_count: int | None = None,
    dry_run: bool = True,
    research_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run page-scoped Stitch critique for a four-page marketing website."""

    project_root = resolve_coding_root(root)
    site_brief = design_brief(
        request,
        root=project_root,
        product_name=product_name,
        stack=stack or {},
        create_files=True,
        research_context=research_context,
    )
    pages = _website_page_specs(request)
    artifacts: list[str] = [str(item) for item in (site_brief.get("artifacts") or []) if str(item).strip()]
    results: list[dict[str, Any]] = []
    provider_blocker = ""
    for index, page in enumerate(pages):
        if provider_blocker:
            skipped = {
                "id": page["id"],
                "label": page["label"],
                "route": page["route"],
                "status": "skipped",
                "ok": False,
                "frontend_handoff_allowed": False,
                "summary": f"Skipped because the configured design provider failed earlier: {provider_blocker}",
                "score": None,
                "design_root": str(_design_root(project_root, f"pages/{page['id']}")),
                "artifacts": [],
            }
            results.append(skipped)
            continue
        page_request = _website_page_request(request, product_name, page)
        result = run_design_critique_loop(
            page_request,
            root=project_root,
            product_name=_page_product_name(product_name, page),
            stack=stack or {},
            variant_count=variant_count,
            dry_run=dry_run,
            artifact_scope=f"pages/{page['id']}",
            research_context=research_context,
        )
        artifacts.extend(str(item) for item in (result.get("artifacts") or []) if str(item).strip())
        results.append(
            {
                "id": page["id"],
                "label": page["label"],
                "route": page["route"],
                "status": result.get("status"),
                "ok": bool(result.get("ok")),
                "frontend_handoff_allowed": bool(result.get("frontend_handoff_allowed")),
                "summary": result.get("summary"),
                "score": (result.get("selected_variant") or {}).get("score") if isinstance(result.get("selected_variant"), dict) else None,
                "selected_variant": result.get("selected_variant") if isinstance(result.get("selected_variant"), dict) else {},
                "source_provider": result.get("source_provider") or result.get("provider_source") or "",
                "design_root": str(_design_root(project_root, f"pages/{page['id']}")),
                "artifacts": result.get("artifacts") or [],
            }
        )
        if index == 0 and _is_design_provider_transport_failure(result):
            provider_blocker = _clean(result.get("summary") or result.get("status") or "design provider failed")
    selected_count = sum(1 for item in results if item.get("frontend_handoff_allowed"))
    planned = bool(dry_run)
    continuity = _cross_page_continuity_review(request, product_name, results, site_brief)
    ok = selected_count == len(pages) and not planned and bool(continuity.get("ok"))
    status_value = "planned" if planned else "selected" if ok else "partial"
    report = {
        "ok": ok,
        "status": status_value,
        "provider": "multipage_design_critique",
        "summary": (
            f"Generated selected Stitch handoffs for all {len(pages)} website pages."
            if ok
            else f"Prepared {len(pages)} website page design run(s); {selected_count}/{len(pages)} selected handoff(s)."
        ),
        "request": _clean(request),
        "product_name": _clean(product_name),
        "page_count": len(pages),
        "selected_page_count": selected_count,
        "frontend_handoff_allowed": ok,
        "site_design_system": ((site_brief.get("design_context") or {}).get("site_continuity") or {}).get("site_design_system") if isinstance(site_brief.get("design_context"), dict) else {},
        "cross_page_continuity": continuity,
        "pages": results,
        "artifacts": _dedupe([*artifacts, *(continuity.get("artifacts") or [])]),
    }
    manifest_artifacts = _write_multipage_design_report(project_root, report)
    return {**report, "artifacts": _dedupe([*(report.get("artifacts") or []), *manifest_artifacts])}


def rerun_cached_design_critique(
    root: str | Path,
    *,
    product_name: str = "",
    request: str = "",
    stack: dict[str, Any] | None = None,
    artifact_scope: str = "",
) -> dict[str, Any]:
    """Re-score an existing Stitch result with the current Friday quality logic."""

    project_root = resolve_coding_root(root)
    design_root = _design_root(project_root, artifact_scope)
    result_path = design_root / "stitch-result.json"
    if not result_path.exists():
        return {
            "ok": False,
            "status": "missing_cached_stitch_result",
            "summary": f"No cached Stitch result exists at {result_path}.",
            "frontend_handoff_allowed": False,
            "artifacts": [],
        }
    brief_path = design_root / "design-provider-plan.json"
    if brief_path.exists():
        try:
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
        except Exception:
            brief = {}
    else:
        brief = {}
    if not isinstance(brief, dict) or not brief:
        brief = design_brief(
            request,
            root=project_root,
            product_name=product_name,
            stack=stack or {},
            create_files=True,
            artifact_scope=artifact_scope,
        )
    else:
        if request:
            brief["request"] = _clean(request)
        if product_name:
            brief["product_name"] = _clean(product_name)
        if stack:
            brief["stack"] = stack
        brief["root"] = str(project_root)
        brief["design_root"] = str(design_root)
        brief["artifact_scope"] = _clean_artifact_scope(artifact_scope)
        brief["design_contract"] = _design_contract(
            str(brief.get("request") or request),
            str(brief.get("product_name") or product_name),
            brief.get("stack") if isinstance(brief.get("stack"), dict) else stack or {},
            artifact_scope=artifact_scope,
        )
    try:
        generation = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "ok": False,
            "status": "invalid_cached_stitch_result",
            "summary": f"Cached Stitch result could not be read: {exc}",
            "frontend_handoff_allowed": False,
            "artifacts": [str(result_path)],
        }
    variants = _normalize_variants(generation)
    variants = _attach_variant_assets(variants, design_root)
    critique = critique_design_variants(variants, brief)
    artifacts = _write_design_critique_artifacts(design_root, critique)
    return {
        "ok": bool(critique.get("frontend_handoff_allowed")),
        "status": critique.get("status"),
        "provider": "cached_design_critique",
        "summary": critique.get("summary"),
        "brief": brief,
        "generation": generation,
        "frontend_handoff_allowed": bool(critique.get("frontend_handoff_allowed")),
        "artifacts": [str(result_path), *artifacts],
        **critique,
    }


def rerun_cached_multipage_website_design_critique(
    root: str | Path,
    *,
    product_name: str = "",
    request: str = "",
    stack: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Re-score every cached page-scoped Stitch result for a website."""

    project_root = resolve_coding_root(root)
    pages = _website_page_specs(request)
    artifacts: list[str] = []
    results: list[dict[str, Any]] = []
    for page in pages:
        result = rerun_cached_design_critique(
            project_root,
            product_name=product_name,
            request=_website_page_request(request, product_name, page),
            stack=stack or {},
            artifact_scope=f"pages/{page['id']}",
        )
        artifacts.extend(str(item) for item in (result.get("artifacts") or []) if str(item).strip())
        results.append(
            {
                "id": page["id"],
                "label": page["label"],
                "route": page["route"],
                "status": result.get("status"),
                "ok": bool(result.get("ok")),
                "frontend_handoff_allowed": bool(result.get("frontend_handoff_allowed")),
                "summary": result.get("summary"),
                "score": (result.get("selected_variant") or {}).get("score") if isinstance(result.get("selected_variant"), dict) else None,
                "design_root": str(_design_root(project_root, f"pages/{page['id']}")),
                "artifacts": result.get("artifacts") or [],
            }
        )
    selected_count = sum(1 for item in results if item.get("frontend_handoff_allowed"))
    ok = selected_count == len(pages)
    report = {
        "ok": ok,
        "status": "selected" if ok else "partial",
        "provider": "cached_multipage_design_critique",
        "summary": (
            f"Re-scored cached Stitch handoffs for all {len(pages)} website pages."
            if ok
            else f"Re-scored cached website page design run(s); {selected_count}/{len(pages)} selected handoff(s)."
        ),
        "request": _clean(request),
        "product_name": _clean(product_name),
        "page_count": len(pages),
        "selected_page_count": selected_count,
        "frontend_handoff_allowed": ok,
        "pages": results,
        "artifacts": artifacts,
    }
    manifest_artifacts = _write_multipage_design_report(project_root, report)
    return {**report, "artifacts": [*artifacts, *manifest_artifacts]}


def _is_design_provider_transport_failure(result: dict[str, Any]) -> bool:
    if bool(result.get("ok")):
        return False
    status = _clean(result.get("status")).lower()
    summary = _clean(result.get("summary")).lower()
    transport_terms = (
        "transport error",
        "fetch failed",
        "econnreset",
        "timed out",
        "timeout",
        "sdk runner failed",
        "stitch sdk failed",
    )
    return status in {"failed", "timeout"} or any(term in summary for term in transport_terms)


def _cross_page_continuity_review(request: str, product_name: str, pages: list[dict[str, Any]], site_brief: dict[str, Any]) -> dict[str, Any]:
    root = _design_root(resolve_coding_root(site_brief.get("root") or ""), "multipage")
    return design_continuity.review_multipage_site(
        request=request,
        product_name=product_name,
        pages=pages,
        site_brief=site_brief,
        design_root=root,
    )


def apply_selected_design_to_nextjs(
    root: str | Path,
    *,
    request: str = "",
    product_name: str = "",
) -> dict[str, Any]:
    """Apply the selected Stitch handoff as the visible Next.js app surface."""

    project_root = resolve_coding_root(root)
    design_root = project_root / ".friday" / "design"
    if _is_multipage_website_request(request) and (design_root / "pages").exists():
        return apply_website_designs_to_nextjs(project_root, request=request, product_name=product_name)

    handoff_path = design_root / "frontend-handoff.json"
    selected_path = design_root / "selected-design.html"
    if not handoff_path.exists():
        return {
            "ok": False,
            "status": "missing_handoff",
            "summary": "No frontend handoff exists to apply.",
            "artifacts": [],
        }
    try:
        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "ok": False,
            "status": "invalid_handoff",
            "summary": f"Frontend handoff could not be read: {exc}",
            "artifacts": [str(handoff_path)],
        }
    html_candidate = _clean(handoff.get("html_path"))
    if html_candidate:
        candidate_path = Path(html_candidate)
        if not candidate_path.is_absolute():
            candidate_path = project_root / candidate_path
        if candidate_path.exists():
            selected_path = candidate_path
    if not selected_path.exists():
        return {
            "ok": False,
            "status": "missing_selected_html",
            "summary": "Frontend handoff exists, but selected-design.html is missing.",
            "artifacts": [str(handoff_path)],
        }
    raw_html = selected_path.read_text(encoding="utf-8", errors="replace")
    page = _selected_design_page_payload("home", "/", "Home", raw_html, handoff=handoff, product_name=product_name or _product_name_from_request(request) or project_root.name)
    if not _clean(page.get("body_html")):
        return {
            "ok": False,
            "status": "empty_selected_html",
            "summary": "Selected design HTML was empty after sanitization.",
            "artifacts": [str(handoff_path), str(selected_path)],
        }

    name = _clean(product_name) or _clean(handoff.get("selected_variant_label")) or _product_name_from_request(request) or project_root.name
    applied = _apply_design_pages_to_nextjs(project_root, [page], request=request, product_name=name)
    written = list(applied.get("files") or [])

    workspace_page = project_root / "src" / "app" / "(dashboard)" / "workspace" / "page.tsx"
    if workspace_page.exists():
        workspace_page.write_text(_stitch_page_module("home"), encoding="utf-8")
        written.append(str(workspace_page))

    manifest = {
        "ok": True,
        "status": "applied",
        "mode": "stitch_native_nextjs_surface",
        "summary": f"Applied selected Stitch design to {len(written)} Next.js source file(s).",
        "source_html": str(selected_path),
        "handoff": str(handoff_path),
        "product_name": name,
        "request": _clean(request),
        "files": written,
        "selected_variant_id": handoff.get("selected_variant_id"),
        "selected_variant_label": handoff.get("selected_variant_label"),
        "score": handoff.get("score"),
    }
    manifest_path = design_root / "applied-design.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return {**manifest, "artifacts": [*written, str(manifest_path)]}


def apply_website_designs_to_nextjs(
    root: str | Path,
    *,
    request: str = "",
    product_name: str = "",
) -> dict[str, Any]:
    """Apply page-scoped Stitch website handoffs to matching Next.js routes."""

    project_root = resolve_coding_root(root)
    pages: list[dict[str, Any]] = []
    missing: list[str] = []
    for spec in _website_page_specs(request):
        page_root = _design_root(project_root, f"pages/{spec['id']}")
        handoff_path = page_root / "frontend-handoff.json"
        selected_path = page_root / "selected-design.html"
        if not handoff_path.exists() or not selected_path.exists():
            missing.append(spec["id"])
            continue
        try:
            handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
        except Exception:
            missing.append(spec["id"])
            continue
        pages.append(
            _selected_design_page_payload(
                spec["id"],
                spec["route"],
                spec["label"],
                selected_path.read_text(encoding="utf-8", errors="replace"),
                handoff=handoff,
                product_name=product_name,
            )
        )
    if missing or not pages:
        return {
            "ok": False,
            "status": "missing_page_handoffs",
            "summary": f"Missing selected Stitch handoff(s) for website page(s): {', '.join(missing or ['all'])}.",
            "missing_pages": missing or [item["id"] for item in _website_page_specs(request)],
            "artifacts": [],
        }
    name = _clean(product_name) or _product_name_from_request(request) or project_root.name
    applied = _apply_design_pages_to_nextjs(project_root, pages, request=request, product_name=name)
    manifest_path = project_root / ".friday" / "design" / "applied-design.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "ok": True,
        "status": "applied",
        "mode": "stitch_multipage_native_nextjs",
        "summary": f"Applied selected Stitch designs to {len(pages)} website route(s).",
        "product_name": name,
        "request": _clean(request),
        "pages": [{"id": page["id"], "route": page["route"], "title": page["title"], "score": page.get("score")} for page in pages],
        "files": applied.get("files") or [],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return {**manifest, "artifacts": [*(applied.get("files") or []), str(manifest_path)]}


def critique_design_variants(variants: list[dict[str, Any]], brief: dict[str, Any], *, visual_review: bool = False) -> dict[str, Any]:
    """Score generated design variants and select exactly one frontend source."""

    threshold = int(config_value("design_critique_min_score", 72) or 72)
    expected_variant_count = max(0, int(brief.get("expected_variant_count") or 0))
    provider_generation_status = _clean(brief.get("provider_generation_status")).lower()
    single_variant_allowed = bool(brief.get("single_variant_allowed") or config_value("design_single_variant_handoff_allowed", False))
    variants = _dedupe_design_variants(variants)
    visual_report: dict[str, Any] = {}
    if visual_review and variants:
        visual_report = design_visual_reviewer.review_variants(
            variants,
            design_root=Path(str(brief.get("design_root") or Path(str(brief.get("root") or ROOT_DIR)) / ".friday" / "design")),
            request=str(brief.get("request") or ""),
            required=bool(config_value("design_variant_visual_review_required", True)),
        )
        variants = [dict(item) for item in (visual_report.get("variants") or variants)]
    scored: list[dict[str, Any]] = []
    for index, variant in enumerate(variants, start=1):
        scored_variant = score_design_variant(variant, brief, index=index)
        scored.append(scored_variant)
    variant_count_blocker = ""
    if provider_generation_status == "partial_provider_result" and expected_variant_count and len(scored) < expected_variant_count and not single_variant_allowed:
        variant_count_blocker = f"Stitch returned {len(scored)}/{expected_variant_count} requested variant(s); partial provider output cannot be handed off."
        scored = [
            {**variant, "rejection_reasons": _dedupe([*(variant.get("rejection_reasons") or []), variant_count_blocker])}
            for variant in scored
        ]
    scored, diversity = _apply_variant_diversity_review(scored)
    selected = _select_design_variant(scored, threshold)
    selected_id = selected.get("id") if selected else ""
    final_variants: list[dict[str, Any]] = []
    for variant in scored:
        rejection_reasons = list(variant.get("rejection_reasons") or [])
        if selected_id and variant.get("id") != selected_id:
            rejection_reasons.append("Lower score than the selected variant.")
        accepted = bool(selected_id and variant.get("id") == selected_id and not rejection_reasons and int(variant.get("score") or 0) >= threshold)
        final_variants.append({**variant, "accepted": accepted, "rejection_reasons": _dedupe(rejection_reasons)})
    selected = next((variant for variant in final_variants if variant.get("id") == selected_id and variant.get("accepted")), None)
    frontend_handoff_allowed = bool(selected)
    status = "selected" if frontend_handoff_allowed else "needs_revision"
    summary = (
        f"Selected {selected.get('label') or selected.get('id')} with score {selected.get('score')}/100 for frontend handoff."
        if selected
        else variant_count_blocker or f"No generated variant reached the design quality threshold of {threshold}/100."
    )
    report = _critique_report(
        brief,
        final_variants,
        selected=selected,
        status=status,
        summary=summary,
        frontend_handoff_allowed=frontend_handoff_allowed,
        diversity=diversity,
    )
    if visual_report:
        return {
            **report,
            "browser_variant_review": visual_report,
            "artifacts": _dedupe([*(report.get("artifacts") or []), *(visual_report.get("artifacts") or [])]),
        }
    return report


def _revision_brief_from_critique(brief: dict[str, Any], critique: dict[str, Any], *, attempt: int) -> dict[str, Any]:
    feedback = _critique_revision_feedback(critique)
    existing_prompt = str(brief.get("stitch_prompt") or brief.get("request") or "")
    revision_prompt = "\n\n".join(
        part
        for part in (
            existing_prompt,
            "FRIDAY DESIGN REVISION REQUIRED",
            f"Revision attempt: {attempt}",
            feedback,
            "Do not return a hero-only or shallow page. Include at least three meaningful sections before the footer: hero, product/proof section, pricing or trust/security section, and final conversion path where appropriate.",
            "Use clear, crisp product/domain visuals or UI proof. Do not wash out images with low opacity. Do not use blurry placeholder media.",
            "Keep the product category, copy voice, and emotional feel from the original brief.",
        )
        if _clean(part)
    )
    return {
        **brief,
        "request": _clean(f"{brief.get('request') or ''}\n\nDesign revision feedback: {feedback}"),
        "stitch_prompt": revision_prompt,
        "stitch_prompt_full": revision_prompt,
        "design_revision_feedback": feedback,
        "design_revision_attempt": attempt,
    }


def _critique_revision_feedback(critique: dict[str, Any]) -> str:
    reasons: list[str] = []
    for variant in critique.get("variants") or []:
        if not isinstance(variant, dict):
            continue
        label = _clean(variant.get("label") or variant.get("id") or "Variant")
        for reason in variant.get("rejection_reasons") or []:
            text = _clean(reason)
            if text:
                reasons.append(f"{label}: {text}")
        for gap in variant.get("gaps") or []:
            text = _clean(gap)
            if text:
                reasons.append(f"{label}: {text}")
    if not reasons:
        summary = _clean(critique.get("summary") or "Previous design did not pass Friday's frontend handoff gate.")
        reasons.append(summary)
    return " / ".join(_dedupe(reasons)[:8])


def score_design_variant(variant: dict[str, Any], brief: dict[str, Any], *, index: int = 1) -> dict[str, Any]:
    """Deterministic design-quality scoring against product fit and user taste."""

    html = _variant_html(variant)
    visible_text = _visible_text(html) or _clean(variant.get("text") or variant.get("summary") or "")
    request = _clean(brief.get("request"))
    product_name = _clean(brief.get("product_name"))
    profile = brief.get("style_profile") if isinstance(brief.get("style_profile"), dict) else {}
    strategy = brief.get("design_strategy") if isinstance(brief.get("design_strategy"), dict) else {}
    profile_name = _clean(profile.get("name"))
    profile_id = _clean(profile.get("id"))
    criteria = [
        _criterion("product_branding", "Uses the requested product brand and avoids internal profile names.", 18, _brand_score(visible_text, product_name, profile_name, profile_id)),
        _criterion("domain_fit", "Covers the real domain and recurring workflows in the request.", 22, _domain_fit_score(visible_text, request)),
        _criterion("art_direction_fit", "Matches the selected creative direction instead of a generic scaffold or samey SaaS layout.", 10, design_director.art_direction_score(html, visible_text, request, strategy)),
        _criterion(
            "website_content_depth" if _is_marketing_website_request(request) else "operational_density",
            "Shows a clear multi-page website, trust path, page-specific content, and conversion flow." if _is_marketing_website_request(request) else "Shows dense operational objects, queues, statuses, metrics, and actions.",
            16,
            _website_content_depth_score(html, visible_text, request) if _is_marketing_website_request(request) else _operational_density_score(html, visible_text),
        ),
        _criterion("accessibility_semantics", "Includes semantic structure and accessible control hints.", 12, _accessibility_score(html)),
        _criterion("copy_quality", "Avoids placeholders and uses specific, readable product copy.", 14, _copy_quality_score(visible_text)),
        _criterion("frontend_feasibility", "Can be converted into structured frontend components without a one-file blob.", 18, _frontend_feasibility_score(html, visible_text)),
    ]
    score = max(0, min(100, sum(int(item["score"]) for item in criteria)))
    gaps: list[str] = []
    rejection_reasons: list[str] = []
    for item in criteria:
        if not item["passed"]:
            gaps.append(f"{item['label']} scored {item['score']}/{item['weight']}.")
    leak_terms = [term for term in {profile_name, profile_id, "NexusForge"} if term and re.search(re.escape(term), visible_text, re.IGNORECASE)]
    if leak_terms:
        rejection_reasons.append("Visible UI leaks an internal style/profile name.")
    if _placeholder_copy_found(visible_text):
        rejection_reasons.append("Visible UI still contains placeholder or generic scaffold copy.")
    off_domain = _off_domain_findings(visible_text, request)
    if off_domain:
        rejection_reasons.append(f"Visible UI contains off-domain or misleading copy: {', '.join(off_domain[:4])}.")
    copy_findings = _copy_specificity_findings(visible_text, request)
    if copy_findings:
        rejection_reasons.append(f"Visible UI copy is too generic or thin: {', '.join(copy_findings[:4])}.")
    interactive_findings = _interactive_accessibility_findings(html)
    if interactive_findings:
        rejection_reasons.append(f"Interactive controls are not handoff-ready: {', '.join(interactive_findings[:4])}.")
    image_findings = _image_quality_findings(html, request)
    if image_findings:
        rejection_reasons.append(f"Hero/media quality is not usable enough for frontend handoff: {', '.join(image_findings[:4])}.")
    style_findings = design_director.style_findings(html, visible_text, request, strategy)
    severe_style_findings = [item for item in style_findings if int(item.get("severity") or 0) >= 4]
    if severe_style_findings:
        rejection_reasons.append(
            "Design direction is too generic or mismatched: "
            + "; ".join(str(item.get("message") or item.get("id")) for item in severe_style_findings[:3])
        )
    handoff_findings = _bad_website_handoff_findings(html, visible_text, request, product_name)
    if handoff_findings:
        rejection_reasons.append(f"Website handoff has layout or page-scope issues: {', '.join(handoff_findings[:4])}.")
    visual_review = _visual_composition_review(html, visible_text, brief)
    if not visual_review.get("passed"):
        rejection_reasons.append(
            "Visual composition review failed: "
            + "; ".join(str(item) for item in (visual_review.get("findings") or [])[:3])
        )
    browser_review = variant.get("browser_visual_review") if isinstance(variant.get("browser_visual_review"), dict) else {}
    if browser_review and not browser_review.get("passed"):
        rejection_reasons.append(
            "Browser screenshot review failed: "
            + "; ".join(str(item) for item in (browser_review.get("findings") or [])[:3])
        )
    minimum_domain_score = 8 if _is_marketing_website_request(request) else 11
    if int(criteria[1]["score"]) < minimum_domain_score:
        rejection_reasons.append("Domain fit is too weak for the user's project request.")
    variant_id = _clean(variant.get("id") or variant.get("screenId") or f"variant_{index}")
    return {
        **variant,
        "id": variant_id,
        "label": _clean(variant.get("label") or f"Variant {index}"),
        "score": score,
        "threshold": int(config_value("design_critique_min_score", 72) or 72),
        "criteria": criteria,
        "gaps": [
            *gaps,
            *[f"Off-domain copy found: {item}." for item in off_domain],
            *[f"Copy specificity issue: {item}." for item in copy_findings],
            *[f"Interactive accessibility issue: {item}." for item in interactive_findings],
            *[f"Image/media issue: {item}." for item in image_findings],
            *[str(item.get("message") or item.get("id")) for item in style_findings],
            *[f"Browser screenshot issue: {item}." for item in (browser_review.get("findings") or [])],
        ],
        "visual_review": visual_review,
        "browser_visual_review": browser_review,
        "rejection_reasons": _dedupe(rejection_reasons),
    }


def _apply_variant_diversity_review(variants: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len(variants) < 2:
        return variants, {"required": False, "unique_count": len(variants), "samey": False}
    if all(str(variant.get("id") or "").startswith("local-") for variant in variants):
        return variants, {"required": False, "unique_count": len(variants), "samey": False, "reason": "local fallback variants are allowed when Stitch is not required"}
    signatures = [_variant_signature(variant) for variant in variants]
    groups: list[list[int]] = []
    for index, signature in enumerate(signatures):
        placed = False
        for group in groups:
            if _signature_similarity(signature, signatures[group[0]]) >= 0.82:
                group.append(index)
                placed = True
                break
        if not placed:
            groups.append([index])
    unique_count = len(groups)
    samey = unique_count < 2
    configured_threshold = int(config_value("design_critique_min_score", 72) or 72)
    best_index = max(range(len(variants)), key=lambda item: int(variants[item].get("score") or 0))
    best_score = int(variants[best_index].get("score") or 0)
    allow_excellent_samey_handoff = (
        samey
        and configured_threshold >= 70
        and best_score >= max(88, configured_threshold + 15)
        and not variants[best_index].get("rejection_reasons")
    )
    group_representatives = {
        tuple(group): max(group, key=lambda item: int(variants[item].get("score") or 0))
        for group in groups
        if group
    }
    reviewed: list[dict[str, Any]] = []
    for index, variant in enumerate(variants):
        rejection_reasons = list(variant.get("rejection_reasons") or [])
        duplicate_group = next((group for group in groups if index in group and len(group) > 1), None)
        if duplicate_group:
            representative = group_representatives.get(tuple(duplicate_group), duplicate_group[0])
            if index != representative:
                rejection_reasons.append("Design variant is not meaningfully distinct from the strongest representative in its group.")
        if samey and not (allow_excellent_samey_handoff and index == best_index):
            rejection_reasons.append("Design exploration returned samey variants; Friday needs genuinely different directions before frontend handoff.")
        reviewed.append({**variant, "rejection_reasons": _dedupe(rejection_reasons)})
    return reviewed, {
        "required": True,
        "unique_count": unique_count,
        "samey": samey,
        "groups": groups,
        "excellent_samey_handoff_allowed": allow_excellent_samey_handoff,
        "warning": "Design exploration was samey; Friday selected the strongest excellent variant and should keep the diversity gap visible."
        if allow_excellent_samey_handoff
        else "",
    }


def _dedupe_design_variants(variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate provider projections of the same generated screen."""

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, variant in enumerate(variants):
        if not isinstance(variant, dict):
            continue
        provider_parts = [
            _clean(variant.get("screenId") or variant.get("id")),
            _clean(variant.get("htmlUrl")),
            _clean(variant.get("imageUrl")),
        ]
        marker = "|".join(item for item in provider_parts if item)
        if not marker:
            marker = _clean(variant.get("html_path"))
        if not marker:
            marker = f"index:{index}"
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(variant)
    return deduped


def _variant_signature(variant: dict[str, Any]) -> set[str]:
    html = _variant_html(variant)
    visible = _visible_text(html) or _clean(variant.get("text") or variant.get("summary") or "")
    tokens = {token.lower() for token in _keywords(visible)[:32] if len(token) > 3}
    lowered = html.lower()
    for tag in ("header", "nav", "main", "aside", "section", "article", "form", "table", "button", "img", "figure"):
        count = lowered.count(f"<{tag}")
        if count:
            tokens.add(f"{tag}:{min(count, 6)}")
    for class_term in ("grid", "flex", "card", "hero", "sidebar", "panel", "table", "form", "dark", "gradient"):
        if class_term in lowered:
            tokens.add(f"class:{class_term}")
    return tokens


def _signature_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, len(left | right))


def _run_stitch_reliable(brief: dict[str, Any], *, variant_count: int = 1, purpose: str = "base") -> dict[str, Any]:
    """Run Stitch through a retry/backoff reliability envelope."""

    project_root = Path(str(brief.get("root") or ROOT_DIR))
    design_root = Path(str(brief.get("design_root") or project_root / ".friday" / "design"))
    design_root.mkdir(parents=True, exist_ok=True)
    max_attempts = max(1, min(5, int(config_value("design_stitch_max_attempts", config_value("design_stitch_generate_attempts", 1)) or 1)))
    backoff_seconds = max(0.0, float(config_value("design_stitch_retry_backoff_seconds", 4.0) or 0.0))
    attempts: list[dict[str, Any]] = []
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    result: dict[str, Any] = {
        "ok": False,
        "status": "failed",
        "provider": "stitch",
        "summary": "Stitch did not run.",
        "brief": brief,
        "artifacts": brief.get("artifacts") or [],
    }
    for attempt in range(1, max_attempts + 1):
        attempt_brief = {
            **brief,
            "stitch_attempt": {
                "purpose": _clean(purpose) or "base",
                "attempt": attempt,
                "max_attempts": max_attempts,
                "fallback_policy": _stitch_fallback_policy(brief),
            },
        }
        result = _run_stitch_sdk(attempt_brief, variant_count=variant_count)
        attempts.append(_stitch_attempt_summary(result, attempt=attempt, purpose=purpose))
        if result.get("ok"):
            break
        if attempt < max_attempts and _stitch_retryable(result):
            if backoff_seconds:
                time.sleep(min(backoff_seconds * attempt, 30.0))
            continue
        break
    report = _stitch_reliability_report_payload(
        brief,
        result,
        attempts,
        purpose=purpose,
        started_at=started_at,
        total_duration_ms=int((time.perf_counter() - started) * 1000),
        variant_count=variant_count,
    )
    report_artifacts = _write_stitch_reliability_report(design_root, report, purpose=purpose)
    return {
        **result,
        "stitch_reliability": report,
        "provider_attempts": attempts,
        "artifacts": _dedupe([*(result.get("artifacts") or []), *report_artifacts]),
    }


def _stitch_retryable(result: dict[str, Any]) -> bool:
    status = _clean(result.get("status")).lower()
    summary = _clean(result.get("summary")).lower()
    if status in {"timeout", "failed", "no_screen", "blocked"}:
        return True
    return any(term in summary for term in ("timed out", "timeout", "no screen", "mcp error", "network", "fetch failed"))


def _stitch_attempt_summary(result: dict[str, Any], *, attempt: int, purpose: str) -> dict[str, Any]:
    payload = result.get("result") if isinstance(result.get("result"), dict) else {}
    attempt_meta = result.get("stitch_attempt") if isinstance(result.get("stitch_attempt"), dict) else {}
    return {
        "attempt": attempt,
        "purpose": _clean(purpose) or "base",
        "ok": bool(result.get("ok")),
        "status": result.get("status") or "",
        "summary": _clean(result.get("summary") or ""),
        "duration_ms": attempt_meta.get("duration_ms"),
        "model_id": attempt_meta.get("model_id") or payload.get("modelId"),
        "project_id": attempt_meta.get("project_id") or payload.get("projectId"),
        "screen_id": attempt_meta.get("screen_id") or payload.get("screenId"),
        "failure_reason": attempt_meta.get("failure_reason") or ("" if result.get("ok") else _clean(result.get("summary") or "")),
        "artifacts": [str(item) for item in (result.get("artifacts") or []) if str(item).strip()],
    }


def _stitch_reliability_report_payload(
    brief: dict[str, Any],
    result: dict[str, Any],
    attempts: list[dict[str, Any]],
    *,
    purpose: str,
    started_at: str,
    total_duration_ms: int,
    variant_count: int,
) -> dict[str, Any]:
    payload = result.get("result") if isinstance(result.get("result"), dict) else {}
    latest = attempts[-1] if attempts else {}
    return {
        "provider": "stitch",
        "purpose": _clean(purpose) or "base",
        "status": result.get("status") or "failed",
        "ok": bool(result.get("ok")),
        "summary": _clean(result.get("summary") or ""),
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "total_duration_ms": total_duration_ms,
        "attempt_count": len(attempts),
        "max_attempts": max(1, min(5, int(config_value("design_stitch_max_attempts", config_value("design_stitch_generate_attempts", 1)) or 1))),
        "backoff_seconds": max(0.0, float(config_value("design_stitch_retry_backoff_seconds", 4.0) or 0.0)),
        "fallback_policy": _stitch_fallback_policy(brief),
        "fallback_allowed": _stitch_policy_allows_fallback(_stitch_fallback_policy(brief)),
        "request_timeout_ms": max(10000, int(config_value("design_stitch_request_timeout_ms", 240000) or 240000)),
        "variant_timeout_ms": max(5000, int(config_value("design_stitch_variant_timeout_ms", 60000) or 60000)),
        "process_timeout_seconds": int(config_value("design_stitch_timeout_seconds", 300) or 300),
        "model_id": latest.get("model_id") or payload.get("modelId") or str(config_value("design_stitch_model_id", "GEMINI_3_1_PRO") or ""),
        "project_id": latest.get("project_id") or payload.get("projectId") or "",
        "screen_id": latest.get("screen_id") or payload.get("screenId") or "",
        "failure_reason": "" if result.get("ok") else _clean(latest.get("failure_reason") or result.get("summary") or ""),
        "variant_count": variant_count,
        "attempts": attempts,
        "artifacts": [str(item) for item in (result.get("artifacts") or []) if str(item).strip()],
    }


def _write_stitch_reliability_report(design_root: Path, report: dict[str, Any], *, purpose: str = "base") -> list[str]:
    safe_purpose = re.sub(r"[^a-z0-9_-]+", "-", (_clean(purpose) or "base").lower()).strip("-") or "base"
    json_path = design_root / f"stitch-reliability-report-{safe_purpose}.json"
    md_path = design_root / f"stitch-reliability-report-{safe_purpose}.md"
    latest_json = design_root / "stitch-reliability-report.json"
    latest_md = design_root / "stitch-reliability-report.md"
    json_text = json.dumps(_sanitize_stitch_payload(report), ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n"
    lines = [
        "# Stitch Reliability Report",
        "",
        f"- Status: {report.get('status')}",
        f"- OK: {bool(report.get('ok'))}",
        f"- Policy: {report.get('fallback_policy')}",
        f"- Attempts: {report.get('attempt_count')} / {report.get('max_attempts')}",
        f"- Total duration: {report.get('total_duration_ms')}ms",
        f"- Model: {report.get('model_id') or 'unknown'}",
        f"- Project ID: {report.get('project_id') or 'not returned'}",
        f"- Screen ID: {report.get('screen_id') or 'not returned'}",
        f"- Failure reason: {report.get('failure_reason') or 'none'}",
        "",
        "## Attempts",
    ]
    for item in report.get("attempts") or []:
        lines.extend(
            [
                "",
                f"### Attempt {item.get('attempt')} ({item.get('purpose')})",
                f"- Status: {item.get('status')}",
                f"- OK: {bool(item.get('ok'))}",
                f"- Duration: {item.get('duration_ms') or 'unknown'}ms",
                f"- Summary: {item.get('summary') or 'No summary'}",
            ]
        )
    md_text = "\n".join(lines).rstrip() + "\n"
    json_path.write_text(json_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    return _dedupe([str(json_path), str(md_path), str(latest_json), str(latest_md)])


def _stitch_attempt_label(brief: dict[str, Any]) -> str:
    meta = brief.get("stitch_attempt") if isinstance(brief.get("stitch_attempt"), dict) else {}
    if not meta:
        return ""
    purpose = re.sub(r"[^a-z0-9_-]+", "-", _clean(meta.get("purpose") or "base").lower()).strip("-") or "base"
    attempt = max(1, int(meta.get("attempt") or 1))
    return f"{purpose}-attempt-{attempt}"


def _stitch_attempt_metadata(
    brief: dict[str, Any],
    result: dict[str, Any],
    payload: dict[str, Any],
    *,
    started_at: str,
    duration_ms: int,
    timeout_seconds: int,
    prompt_path: Path,
    log_path: Path,
    output_path: Path | None,
    combined: str,
) -> dict[str, Any]:
    meta = brief.get("stitch_attempt") if isinstance(brief.get("stitch_attempt"), dict) else {}
    summary = _clean(result.get("summary") or "")
    return {
        "provider": "stitch",
        "purpose": meta.get("purpose") or "base",
        "attempt": int(meta.get("attempt") or 1),
        "max_attempts": int(meta.get("max_attempts") or 1),
        "status": result.get("status") or ("generated" if result.get("ok") else "failed"),
        "ok": bool(result.get("ok")),
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": duration_ms,
        "timeout_seconds": timeout_seconds,
        "request_timeout_ms": max(10000, int(config_value("design_stitch_request_timeout_ms", 240000) or 240000)),
        "variant_timeout_ms": max(5000, int(config_value("design_stitch_variant_timeout_ms", 60000) or 60000)),
        "model_id": payload.get("modelId") or str(config_value("design_stitch_model_id", "GEMINI_3_1_PRO") or ""),
        "project_id": payload.get("projectId") or "",
        "screen_id": payload.get("screenId") or "",
        "failure_reason": "" if result.get("ok") else summary,
        "summary": summary,
        "prompt_chars": len(str(brief.get("stitch_prompt") or brief.get("request") or "")),
        "prompt_path": str(prompt_path),
        "log_path": str(log_path),
        "output_path": str(output_path or ""),
        "projection_paths_tried": payload.get("projectionPathsTried") or [],
        "warnings": payload.get("warnings") or [],
        "combined_log_tail": _tail_text(combined, 2000),
        "fallback_policy": meta.get("fallback_policy") or _stitch_fallback_policy(brief),
    }


def _run_stitch_sdk(brief: dict[str, Any], *, variant_count: int = 1) -> dict[str, Any]:
    project_root = Path(str(brief.get("root") or ROOT_DIR))
    design_root = Path(str(brief.get("design_root") or project_root / ".friday" / "design"))
    design_root.mkdir(parents=True, exist_ok=True)
    runner_path = design_root / "stitch-runner.mjs"
    attempt_label = _stitch_attempt_label(brief)
    output_path = design_root / (f"stitch-result-{attempt_label}.json" if attempt_label else "stitch-result.json")
    log_path = design_root / (f"stitch-run-{attempt_label}.log" if attempt_label else "stitch-run.log")
    prompt_path = design_root / (f"stitch-prompt-{attempt_label}.md" if attempt_label else "stitch-live-prompt.md")
    attempt_path = design_root / (f"stitch-attempt-{attempt_label}.json" if attempt_label else "stitch-attempt-latest.json")
    runner_path.write_text(_stitch_runner_script(), encoding="utf-8")
    env = os.environ.copy()
    prompt_budget = max(6000, int(config_value("design_stitch_prompt_budget_chars", 12000) or 12000))
    source_prompt = str(brief.get("stitch_prompt") or brief.get("request") or "")
    full_prompt = str(brief.get("stitch_prompt_full") or source_prompt)
    prompt_bundle = design_prompt_compiler.compile_stitch_prompt_bundle(brief, budget=prompt_budget, fallback_prompt=source_prompt)
    bundle_path = design_root / (f"stitch-prompt-bundle-{attempt_label}.json" if attempt_label else "stitch-prompt-bundle.json")
    compiled_prompt = str(prompt_bundle.get("base_prompt") or source_prompt)
    prompt_path.write_text(compiled_prompt + "\n", encoding="utf-8")
    bundle_path.write_text(json.dumps(prompt_bundle, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    env["FRIDAY_STITCH_PROMPT"] = compiled_prompt
    env["FRIDAY_STITCH_COMPILED_PROMPT"] = source_prompt
    env["FRIDAY_STITCH_PROMPT_BUNDLE_JSON"] = json.dumps(prompt_bundle, ensure_ascii=True, sort_keys=True, default=str)
    env["FRIDAY_STITCH_PROMPT_BUDGET_CHARS"] = str(prompt_budget)
    env["FRIDAY_STITCH_PROMPT_FULL_LENGTH"] = str(len(full_prompt))
    env["FRIDAY_STITCH_TITLE"] = str(brief.get("product_name") or "Friday Design")
    env["FRIDAY_STITCH_PROJECT_ID"] = str(config_value("design_stitch_project_id", "") or "")
    env["FRIDAY_STITCH_VARIANT_COUNT"] = str(max(1, int(variant_count or 1)))
    strategy = brief.get("design_strategy") if isinstance(brief.get("design_strategy"), dict) else {}
    env["FRIDAY_STITCH_VARIANT_DIRECTIONS"] = json.dumps(strategy.get("variant_directions") or [], ensure_ascii=True)
    if isinstance(brief.get("design_context"), dict):
        env["FRIDAY_STITCH_CONTEXT_JSON"] = json.dumps(brief.get("design_context") or {}, ensure_ascii=True, sort_keys=True, default=str)
    env["FRIDAY_STITCH_GENERATE_ATTEMPTS"] = str(max(1, min(3, int(config_value("design_stitch_generate_attempts", 1) or 1))))
    env["FRIDAY_STITCH_MODEL_ID"] = str(config_value("design_stitch_model_id", "GEMINI_3_1_PRO") or "GEMINI_3_1_PRO")
    env["FRIDAY_STITCH_REQUEST_TIMEOUT_MS"] = str(max(10000, int(config_value("design_stitch_request_timeout_ms", 240000) or 240000)))
    env["FRIDAY_STITCH_VARIANT_TIMEOUT_MS"] = str(max(5000, int(config_value("design_stitch_variant_timeout_ms", 60000) or 60000)))
    env["FRIDAY_STITCH_FALLBACK_VARIANTS"] = "1" if bool(config_value("design_stitch_fallback_variants", True)) else "0"
    env["FRIDAY_STITCH_RUN_PURPOSE"] = str((brief.get("stitch_attempt") or {}).get("purpose") or "base") if isinstance(brief.get("stitch_attempt"), dict) else "base"
    stitch_key_env = str(config_value("design_stitch_api_key_env", "STITCH_API_KEY") or "STITCH_API_KEY")
    stitch_key = _env_value(stitch_key_env)
    if stitch_key:
        env[stitch_key_env] = stitch_key
        env["STITCH_API_KEY"] = stitch_key
    timeout = int(config_value("design_stitch_timeout_seconds", 300))
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()

    def finish(result: dict[str, Any], *, payload: dict[str, Any] | None = None, combined: str = "") -> dict[str, Any]:
        duration_ms = int((time.perf_counter() - started) * 1000)
        result_artifacts = [str(prompt_path), str(bundle_path), *(result.get("artifacts") or [])]
        latest_log = design_root / "stitch-run.log"
        latest_result = design_root / "stitch-result.json"
        if attempt_label and log_path.exists():
            latest_log.write_text(log_path.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8", errors="ignore")
            if str(latest_log) not in result_artifacts:
                result_artifacts.append(str(latest_log))
        if attempt_label and output_path.exists():
            latest_result.write_text(output_path.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8", errors="ignore")
            if str(latest_result) not in result_artifacts:
                result_artifacts.append(str(latest_result))
        attempt = _stitch_attempt_metadata(
            brief,
            result,
            payload or {},
            started_at=started_at,
            duration_ms=duration_ms,
            timeout_seconds=timeout,
            prompt_path=prompt_path,
            log_path=log_path,
            output_path=output_path if output_path.exists() else None,
            combined=combined,
        )
        attempt_path.write_text(json.dumps(_sanitize_stitch_payload(attempt), ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        result_artifacts.append(str(attempt_path))
        return {
            **result,
            "provider_source": "google_stitch_sdk",
            "source_provider": "stitch",
            "stitch_attempt": attempt,
            "artifacts": _dedupe([item for item in result_artifacts if item]),
        }

    try:
        process = subprocess.Popen(
            ["node", str(runner_path)],
            cwd=ROOT_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = process.communicate(timeout=timeout)
        completed = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
    except subprocess.TimeoutExpired as exc:
        command_runner.terminate_process_tree(process.pid)
        stdout, stderr = process.communicate()
        payload = _stitch_payload_from_stdout(stdout)
        combined = _stitch_log_text(stdout, stderr, payload) or str(exc) + "\n"
        log_path.write_text(combined, encoding="utf-8", errors="ignore")
        raw_artifacts = _write_stitch_raw_artifacts(design_root, payload, prefix=attempt_label)
        if payload.get("ok") and str(payload.get("status") or "") == "base_generated" and int(variant_count or 1) > len(payload.get("variants") or []):
            output_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
            return finish({
                "ok": False,
                "status": "partial_provider_result",
                "provider": "stitch",
                "summary": "Stitch produced a base screen before timing out; Friday kept it as partial evidence and will not treat it as a completed handoff without visual critique.",
                "result": payload,
                "brief": brief,
                "artifacts": [*(brief.get("artifacts") or []), str(runner_path), str(log_path), str(output_path), *raw_artifacts],
            }, payload=payload, combined=combined)
        if payload.get("ok"):
            output_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
            return finish({
                "ok": True,
                "status": "generated",
                "provider": "stitch",
                "summary": "Stitch SDK generated a UI screen, but the runner had to close a lingering process after output capture.",
                "result": payload,
                "brief": brief,
                "artifacts": [*(brief.get("artifacts") or []), str(runner_path), str(log_path), str(output_path), *raw_artifacts],
            }, payload=payload, combined=combined)
        return finish({
            "ok": False,
            "status": "timeout",
            "provider": "stitch",
            "summary": _stitch_failure_summary(combined, fallback=f"Stitch SDK timed out after {timeout} seconds."),
            "result": payload,
            "brief": brief,
            "timeout_seconds": timeout,
            "artifacts": [*(brief.get("artifacts") or []), str(runner_path), str(log_path), *raw_artifacts],
        }, payload=payload, combined=combined)
    except Exception as exc:
        combined = str(exc) + "\n"
        log_path.write_text(combined, encoding="utf-8")
        return finish({
            "ok": False,
            "status": "failed",
            "provider": "stitch",
            "summary": f"Stitch SDK runner failed before completion: {exc}",
            "brief": brief,
            "artifacts": [*(brief.get("artifacts") or []), str(runner_path), str(log_path)],
        }, payload={}, combined=combined)
    payload = _stitch_payload_from_stdout(completed.stdout)
    combined = _stitch_log_text(completed.stdout, completed.stderr, payload)
    log_path.write_text(combined, encoding="utf-8", errors="ignore")
    raw_artifacts = _write_stitch_raw_artifacts(design_root, payload, prefix=attempt_label)
    if completed.returncode == 0 and payload.get("ok"):
        partial = str(payload.get("status") or "") == "partial_provider_result" or bool(payload.get("partialProviderResult"))
        output_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        return finish({
            "ok": True,
            "status": "partial_provider_result" if partial else "generated",
            "provider": "stitch",
            "summary": "Stitch SDK returned a partial design result; Friday will require critique/browser evidence before handoff." if partial else "Stitch SDK generated a UI screen and returned HTML/image URLs.",
            "result": payload,
            "brief": brief,
            "artifacts": [*(brief.get("artifacts") or []), str(runner_path), str(log_path), str(output_path), *raw_artifacts],
        }, payload=payload, combined=combined)
    return finish({
        "ok": False,
        "status": _clean(payload.get("status")) or "failed",
        "provider": "stitch",
        "summary": _clean(payload.get("error") or payload.get("summary")) or _stitch_failure_summary(combined, fallback=f"Stitch SDK exited with code {completed.returncode}."),
        "result": payload,
        "brief": brief,
        "artifacts": [*(brief.get("artifacts") or []), str(runner_path), str(log_path), *raw_artifacts],
    }, payload=payload, combined=combined)


def _stitch_runner_script() -> str:
    return """import { StitchToolClient } from "@google/stitch-sdk";

const dispatcherTimeoutMs = Math.max(10000, Number(process.env.FRIDAY_STITCH_REQUEST_TIMEOUT_MS || "480000"));
try {
  const undici = await import("undici");
  if (undici?.Agent && undici?.setGlobalDispatcher) {
    undici.setGlobalDispatcher(new undici.Agent({
      headersTimeout: dispatcherTimeoutMs,
      bodyTimeout: dispatcherTimeoutMs,
      connectTimeout: Math.min(dispatcherTimeoutMs, 60000)
    }));
  }
} catch {
  // The SDK may use the runtime fetch dispatcher directly. If undici is not
  // importable, continue with the SDK-level timeout below.
}

function pickProjectId(result) {
  const candidates = [
    result?.projectId,
    result?.id,
    result?.project?.projectId,
    result?.project?.id,
    result?.name,
  ].filter(Boolean);
  const first = String(candidates[0] || "");
  return first.includes("/") ? first.split("/").pop() : first;
}

function screenIdFrom(screen) {
  const raw = screen?.screenId || screen?.id || screen?.name || "";
  const value = String(raw || "");
  if (value.includes("/screens/")) {
    return value.split("/screens/").pop();
  }
  return value;
}

function fileUrl(value) {
  if (!value) return "";
  if (typeof value === "string") return value;
  return value.downloadUrl || value.url || value.uri || value.href || "";
}

function looksLikeScreen(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  return Boolean(
    value.htmlCode ||
    value.screenshot ||
    value.htmlUrl ||
    value.imageUrl ||
    value.screenshotUrl ||
    (typeof value.name === "string" && value.name.includes("/screens/")) ||
    (screenIdFrom(value) && (value.width || value.height || value.title))
  );
}

function sanitize(value, depth = 0) {
  if (depth > 12) return "[redacted:depth-limit]";
  if (Array.isArray(value)) {
    return value.slice(0, 200).map((item) => sanitize(item, depth + 1));
  }
  if (value && typeof value === "object") {
    const output = {};
    for (const [key, child] of Object.entries(value)) {
      if (/api.?key|token|secret|authorization|cookie|credential|password/i.test(key)) {
        output[key] = "[redacted]";
      } else {
        output[key] = sanitize(child, depth + 1);
      }
    }
    return output;
  }
  if (typeof value === "string") {
    let text = value;
    if (/^https?:\\/\\//i.test(text)) {
      text = text.replace(/[?#].*$/, "?[redacted]");
    }
    if (text.length > 12000) {
      text = `${text.slice(0, 12000)}...[truncated ${text.length - 12000} chars]`;
    }
    return text;
  }
  return value;
}

function collectScreens(value, path = "$", seen = new Set(), paths = [], screens = []) {
  if (!value || typeof value !== "object" || seen.has(value)) {
    return { screens, paths };
  }
  seen.add(value);
  if (looksLikeScreen(value)) {
    paths.push(path);
    screens.push({ screen: value, path });
  }
  if (Array.isArray(value)) {
    for (let index = 0; index < value.length; index += 1) {
      collectScreens(value[index], `${path}[${index}]`, seen, paths, screens);
    }
    return { screens, paths };
  }
  for (const [key, child] of Object.entries(value)) {
    collectScreens(child, `${path}.${key}`, seen, paths, screens);
  }
  return { screens, paths };
}

function explicitProjectionScreens(raw) {
  const attempts = [];
  const screens = [];
  function pushFrom(candidate, path) {
    attempts.push(path);
    if (Array.isArray(candidate)) {
      candidate.forEach((screen, index) => {
        if (looksLikeScreen(screen)) screens.push({ screen, path: `${path}[${index}]` });
      });
    } else if (looksLikeScreen(candidate)) {
      screens.push({ screen: candidate, path });
    }
  }
  const outputComponents = raw?.outputComponents || raw?.output_components || [];
  if (Array.isArray(outputComponents)) {
    outputComponents.forEach((component, index) => {
      pushFrom(component?.design?.screens, `outputComponents[${index}].design.screens`);
      pushFrom(component?.design?.screen, `outputComponents[${index}].design.screen`);
      pushFrom(component?.screens, `outputComponents[${index}].screens`);
      pushFrom(component?.screen, `outputComponents[${index}].screen`);
      pushFrom(component?.payload?.design?.screens, `outputComponents[${index}].payload.design.screens`);
      pushFrom(component?.data?.design?.screens, `outputComponents[${index}].data.design.screens`);
    });
  } else {
    attempts.push("outputComponents");
  }
  pushFrom(raw?.design?.screens, "design.screens");
  pushFrom(raw?.screens, "screens");
  pushFrom(raw?.screen, "screen");
  pushFrom(raw?.generatedScreen, "generatedScreen");
  pushFrom(raw?.generated_screen, "generated_screen");
  return { screens, attempts };
}

function extractScreens(raw) {
  const explicit = explicitProjectionScreens(raw);
  const deep = collectScreens(raw);
  const seen = new Set();
  const screens = [];
  for (const item of [...explicit.screens, ...deep.screens]) {
    const id = screenIdFrom(item.screen);
    const marker = `${id || ""}|${item.path}`;
    if (seen.has(marker)) continue;
    seen.add(marker);
    screens.push(item);
  }
  return {
    screens,
    paths: [...new Set([...explicit.attempts, ...deep.paths])]
  };
}

function outputTextFrom(raw) {
  const components = raw?.outputComponents || raw?.output_components || [];
  const texts = [];
  if (Array.isArray(components)) {
    for (const component of components) {
      for (const key of ["text", "message", "content", "suggestion", "suggestions"]) {
        const value = component?.[key];
        if (typeof value === "string") texts.push(value);
        if (Array.isArray(value)) texts.push(...value.filter((item) => typeof item === "string"));
      }
    }
  }
  return texts.join("\\n").slice(0, 2000);
}

function screenQuality(screen) {
  const mime = String(screen?.htmlCode?.mimeType || screen?.html?.mimeType || "").toLowerCase();
  const titleText = `${screen?.title || ""} ${screen?.prompt || ""}`.toLowerCase();
  const width = Number(screen?.width || 0);
  const height = Number(screen?.height || 0);
  let score = 0;
  if (mime.includes("text/html")) score += 50;
  if (mime.includes("image/svg")) score -= 45;
  if (width >= 1000) score += 10;
  if (height >= 900) score += 15;
  if (height >= 1800) score += 10;
  if (/\\b(home|atelier|collections?|concierge|contact|about|services?|page|website|landing)\\b/.test(titleText)) score += 10;
  if (/\\b(logo|icon|mark|symbol|brand asset)\\b/.test(titleText)) score -= 35;
  if (screen?.screenshot || screen?.screenshotUrl || screen?.imageUrl) score += 5;
  return score;
}

function rankedScreens(items) {
  return [...items]
    .map((item, index) => ({ ...item, originalIndex: index, quality: screenQuality(item.screen) }))
    .sort((left, right) => (right.quality - left.quality) || (left.originalIndex - right.originalIndex));
}

function toPayload(screen, label, sourcePath) {
  const screenId = screenIdFrom(screen);
  return {
    id: screenId || screen?.id || label,
    label,
    projectId,
    screenId,
    title: screen?.title || "",
    htmlUrl: screen?.htmlUrl || screen?.htmlCodeUrl || fileUrl(screen?.htmlCode) || fileUrl(screen?.html),
    imageUrl: screen?.imageUrl || screen?.screenshotUrl || fileUrl(screen?.screenshot) || fileUrl(screen?.image),
    sourcePath
  };
}

function parseJsonEnv(value, fallback) {
  try {
    const parsed = JSON.parse(value || "");
    return parsed && typeof parsed === "object" ? parsed : fallback;
  } catch {
    return fallback;
  }
}

function compactJson(value, maxLength = 1200) {
  let text = "";
  try {
    text = JSON.stringify(value || {});
  } catch {
    text = String(value || "");
  }
  return text.length > maxLength ? `${text.slice(0, maxLength - 3)}...` : text;
}

function asList(value, limit = 8) {
  return Array.isArray(value) ? value.filter(Boolean).slice(0, limit) : [];
}

function joinList(value, limit = 8) {
  return asList(value, limit).map((item) => String(item)).join(", ");
}

function contextLine(label, value) {
  const text = Array.isArray(value) ? joinList(value, 10) : String(value || "").trim();
  return text ? `- ${label}: ${text}` : "";
}

function compilePromptFromContext(ctx, fallbackPrompt = "") {
  const userIntent = ctx?.user_intent || {};
  const creative = ctx?.creative_brief || {};
  const composition = ctx?.composition_spec || {};
  const experience = ctx?.experience_mode || {};
  const content = ctx?.content_model || {};
  const copy = ctx?.copy_bank || {};
  const output = ctx?.output_contract || {};
  const brand = ctx?.brand_system || {};
  const site = ctx?.site_continuity || {};
  const taxonomy = ctx?.taxonomy_prompt_profile || {};
  const visualMemory = ctx?.visual_reference_memory || {};
  const lines = [
    "Design context package:",
    contextLine("User intent", userIntent.raw_request),
    contextLine("Product goal", ctx?.product_goal),
    contextLine("Target audience", ctx?.target_audience),
    contextLine("Emotional intent", ctx?.emotional_intent),
    contextLine("Core message", ctx?.message),
    "",
    "First viewport composition:",
    contextLine("Composition archetype", composition.archetype_name || composition.archetype),
    contextLine("Archetype rationale", composition.archetype_rationale),
    ...asList(composition.allowed_archetypes, 4).map((item) => {
      if (!item || typeof item !== "object") return `- Alternative archetype: ${String(item)}`;
      return `- Alternative archetype: ${item.name || item.id}: ${item.first_viewport || item.why || ""}`;
    }),
    ...asList(composition.composition_rules, 5).map((item) => `- Composition rule: ${item}`),
    ...asList(composition.first_viewport, 5).map((item) => `- ${item}`),
    contextLine("Visual hierarchy", composition.visual_hierarchy),
    contextLine("Variant policy", composition.variant_policy),
    "",
    "Experience mode and motion/3D contract:",
    contextLine("Experience mode", experience.mode_name || experience.mode),
    contextLine("Intent", experience.intent),
    contextLine("Recommended libraries", experience.recommended_libraries),
    ...asList(experience.allowed_modes, 4).map((item) => {
      if (!item || typeof item !== "object") return `- Alternative mode: ${String(item)}`;
      return `- Alternative mode: ${item.name || item.id}: ${item.intent || item.when_to_use || ""}`;
    }),
    ...asList(experience.implementation_notes, 6).map((item) => `- Implementation note: ${item}`),
    ...asList(experience.motion_rules, 6).map((item) => `- Motion rule: ${item}`),
    ...asList(experience.verification_requirements, 6).map((item) => `- Verify: ${item}`),
    contextLine("Fallback requirement", experience.fallback_requirement),
    contextLine("Performance budget", compactJson(experience.performance_budget || {}, 900)),
    "",
    "Required sections:",
    ...asList(ctx?.section_blueprint, 8).map((item) => {
      if (!item || typeof item !== "object") return `- ${String(item)}`;
      return `- ${item.section || "Section"}: ${item.purpose || ""} Must show: ${joinList(item.must_show, 8)}. Visual objects: ${joinList(item.visual_objects, 6)}.`;
    }),
    "",
    "Component inventory:",
    contextLine("Components", ctx?.component_inventory),
    "",
    "Copy bank:",
    contextLine("Headline directions", copy.headline_directions),
    contextLine("Subhead direction", copy.subhead_direction),
    contextLine("Microcopy examples", copy.microcopy_examples),
    contextLine("Words to avoid", copy.words_to_avoid),
    "",
    "Visual grammar:",
    contextLine("Direction", ctx?.visual_context?.direction),
    contextLine("Palette", ctx?.visual_context?.palette),
    contextLine("Typography", ctx?.visual_context?.typography),
    contextLine("Imagery", ctx?.visual_context?.imagery),
    contextLine("Brand tokens", compactJson(brand.tokens || {}, 900)),
    contextLine("Logo direction", brand.logo_direction),
    contextLine("Site continuity", compactJson(site.site_design_system || {}, 1200)),
    contextLine("Approved visual references", compactJson(visualMemory.assets || [], 900)),
    "",
    "Taxonomy-specific guidance:",
    contextLine("Message", taxonomy.message),
    contextLine("Emotional feel", taxonomy.emotional_feel),
    contextLine("Rejection rules", taxonomy.rejection_rules),
    "",
    "Rejection rules:",
    ...asList(output.rejection_if, 8).map((item) => `- ${item}`),
    "- Do not generate placeholder numbered labels like Home 1, Home 2, Service 1, or Service 2.",
    "- Do not render internal style profile names unless the requested product brand is that exact name.",
    "- Normalize exaggerated scale so the first viewport is usable and copy is not clipped.",
    "",
    "Variant instructions:",
    ...asList(ctx?.variant_briefs, 3).map((item) => `- ${item.variant || "Variant"}: ${item.direction || ""} ${item.must_change || ""}`),
    "",
    "Output contract:",
    ...asList(output.must_return, 6).map((item) => `- Must return: ${item}`),
    contextLine("Minimum depth", output.minimum_depth),
    "",
    "Code/product signals:",
    compactJson(ctx?.code_context || {}, 1000),
    "Design-system context:",
    compactJson(ctx?.design_system_context || {}, 1000),
  ].filter((line) => line !== "");
  const compiled = lines.join("\\n");
  return compiled.length >= 1200 ? compiled : fallbackPrompt;
}

function fitPromptBudget(text, ctx, budget) {
  const maxLength = Math.max(6000, Number(budget || 12000));
  const candidate = String(text || "").trim() || compilePromptFromContext(ctx, "");
  if (candidate.length <= maxLength) return candidate;
  const fromContext = compilePromptFromContext(ctx, candidate);
  if (fromContext && fromContext.length <= maxLength) return fromContext;
  const outputContract = [
    "\\n\\nOutput contract:",
    "- Return a complete desktop screen/page, not a logo or isolated component.",
    "- Include specific visible copy, semantic sections, usable controls, and responsive structure.",
    "- Reject placeholder numbered labels, generic scaffold copy, oversized clipped hero type, and off-domain visuals."
  ].join("\\n");
  const room = Math.max(1000, maxLength - outputContract.length - 80);
  return `${fromContext.slice(0, room)}\\n\\n[Prompt compacted by Friday StitchPromptCompiler to preserve critical context.]${outputContract}`;
}

const prompt = process.env.FRIDAY_STITCH_PROMPT || "";
const contextJson = parseJsonEnv(process.env.FRIDAY_STITCH_CONTEXT_JSON || "{}", {});
const promptBundle = parseJsonEnv(process.env.FRIDAY_STITCH_PROMPT_BUNDLE_JSON || "{}", {});
const compiledEnvPrompt = process.env.FRIDAY_STITCH_COMPILED_PROMPT || "";
const promptBudgetChars = Math.max(6000, Number(process.env.FRIDAY_STITCH_PROMPT_BUDGET_CHARS || "12000"));
const title = process.env.FRIDAY_STITCH_TITLE || "Friday Design";
const variantCount = Math.max(1, Math.min(3, Number(process.env.FRIDAY_STITCH_VARIANT_COUNT || "1")));
let variantDirections = [];
try {
  const parsedDirections = JSON.parse(process.env.FRIDAY_STITCH_VARIANT_DIRECTIONS || "[]");
  variantDirections = Array.isArray(parsedDirections) ? parsedDirections.filter((item) => typeof item === "string" && item.trim()) : [];
} catch {
  variantDirections = [];
}
const modelId = process.env.FRIDAY_STITCH_MODEL_ID || "GEMINI_3_1_PRO";
const requestTimeoutMs = Math.max(10000, Number(process.env.FRIDAY_STITCH_REQUEST_TIMEOUT_MS || "240000"));
const variantTimeoutMs = Math.max(5000, Number(process.env.FRIDAY_STITCH_VARIANT_TIMEOUT_MS || "60000"));
const fallbackVariantsEnabled = process.env.FRIDAY_STITCH_FALLBACK_VARIANTS === "1";
let projectId = process.env.FRIDAY_STITCH_PROJECT_ID || "";
const startedAt = Date.now();
function log(stage, extra = "") {
  console.error(`[friday-stitch] ${stage}${extra ? ` ${extra}` : ""} ${Date.now() - startedAt}ms`);
}
const toolClient = new StitchToolClient({ apiKey: process.env.STITCH_API_KEY, timeout: requestTimeoutMs });
const warnings = [];
const rawGetScreens = [];
const rawFallbackGenerations = [];
let rawGenerate = null;
let rawVariants = null;
const compactPrompt = fitPromptBudget(promptBundle.base_prompt || compiledEnvPrompt || prompt || compilePromptFromContext(contextJson, prompt), contextJson, promptBudgetChars);
const variantPrompt = fitPromptBudget(promptBundle.variant_prompt || `Create genuinely distinct alternatives for the same product. Preserve domain-specific copy, improve hierarchy, accessibility, and operational workflow clarity. Use these art directions: ${variantDirections.join(" / ") || "change layout, visual language, and interaction model"}. Do not use internal style profile names as visible branding.`, contextJson, promptBudgetChars);
function directionFor(index) {
  return variantDirections[(Math.max(1, index) - 1) % Math.max(1, variantDirections.length)] || "change the composition, hierarchy, content emphasis, visual rhythm, and interaction model while keeping the same product and domain.";
}
const attempts = Math.max(1, Math.min(3, Number(process.env.FRIDAY_STITCH_GENERATE_ATTEMPTS || "2")));
function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
function withTimeout(promise, ms, message) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(message)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}
async function generateWithRetry(generatePrompt, label) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      log(`generate_screen_from_text:${label}:start`, `attempt=${attempt} model=${modelId}`);
      const raw = await toolClient.callTool("generate_screen_from_text", {
        projectId,
        prompt: generatePrompt,
        deviceType: "DESKTOP",
        modelId
      });
      log(`generate_screen_from_text:${label}:done`, `session=${raw?.sessionId || raw?.session_id || ""}`);
      return raw;
    } catch (error) {
      lastError = error;
      warnings.push(`${label} attempt ${attempt} failed: ${error?.message || String(error)}`);
      log(`generate_screen_from_text:${label}:error`, error?.message || String(error));
      if (attempt < attempts) {
        await wait(1500 * attempt);
      }
    }
  }
  throw lastError;
}
async function enrichPayload(payload, label) {
  if (!payload.screenId || (payload.htmlUrl && payload.imageUrl)) {
    return payload;
  }
  try {
    log(`get_screen:${label}:start`, payload.screenId);
    const raw = await toolClient.callTool("get_screen", {
      projectId,
      screenId: payload.screenId,
      name: `projects/${projectId}/screens/${payload.screenId}`
    });
    rawGetScreens.push({ screenId: payload.screenId, response: sanitize(raw) });
    const detail = toPayload({ ...raw, projectId }, label, "get_screen");
    log(`get_screen:${label}:done`);
    return {
      ...payload,
      htmlUrl: payload.htmlUrl || detail.htmlUrl,
      imageUrl: payload.imageUrl || detail.imageUrl,
      title: payload.title || detail.title
    };
  } catch (error) {
    warnings.push(`get_screen failed for ${payload.screenId}: ${error?.message || String(error)}`);
    log(`get_screen:${label}:error`, error?.message || String(error));
    return payload;
  }
}
async function main() {
  if (!projectId) {
    log("create_project:start");
    const project = await toolClient.callTool("create_project", { title });
    projectId = pickProjectId(project);
    log("create_project:done", projectId);
  } else {
    log("project:reuse", projectId);
  }
  if (!projectId) {
    throw new Error("Stitch did not return a project id.");
  }
  rawGenerate = await generateWithRetry(compactPrompt, "base");
  const baseExtraction = extractScreens(rawGenerate);
  const rankedBaseScreens = rankedScreens(baseExtraction.screens);
  if (!rankedBaseScreens.length) {
    const error = "Stitch generate_screen_from_text returned no screen in known projection paths.";
    console.log(JSON.stringify({
      ok: false,
      status: "no_screen",
      provider: "stitch",
      projectId,
      modelId,
      error,
      outputText: outputTextFrom(rawGenerate),
      projectionPathsTried: baseExtraction.paths,
      rawGenerate: sanitize(rawGenerate),
      warnings
    }));
    process.exitCode = 2;
    return;
  }
  const variants = [];
  const seenVariantKeys = new Set();
  const baseLimit = variantCount <= 1 ? Math.min(rankedBaseScreens.length, 1) : Math.min(rankedBaseScreens.length, Math.max(variantCount, 6));
  for (let index = 0; index < baseLimit; index += 1) {
    const item = rankedBaseScreens[index];
    const label = index === 0 ? "Base direction" : `Base screen ${index + 1}`;
    const payload = await enrichPayload(toPayload(item.screen, label, item.path), `base ${index + 1}`);
    const marker = `${payload.screenId || payload.id || ""}|${payload.htmlUrl || ""}|${payload.imageUrl || ""}`;
    if (!seenVariantKeys.has(marker)) {
      seenVariantKeys.add(marker);
      variants.push(payload);
    }
  }
  console.log(JSON.stringify({
    ok: true,
    status: "base_generated",
    provider: "stitch",
    projectId,
    modelId,
    screenId: variants[0]?.screenId || "",
    htmlUrl: variants[0]?.htmlUrl || "",
    imageUrl: variants[0]?.imageUrl || "",
    variants,
    projectionPathsTried: baseExtraction.paths,
    rawGenerate: sanitize(rawGenerate),
    rawVariants: null,
    rawGetScreens,
    rawFallbackGenerations,
    warnings: [...warnings, "Base Stitch generation checkpoint captured before optional variant exploration."]
  }));
  if (variantCount > 1 && variants[0]?.screenId && variants.length < variantCount) {
    try {
      log("generate_variants:start", `count=${variantCount - 1} model=${modelId}`);
      rawVariants = await withTimeout(
        toolClient.callTool("generate_variants", {
          projectId,
          selectedScreenIds: [variants[0].screenId],
          prompt: variantPrompt,
          variantOptions: {
            variantCount: variantCount - 1,
            creativeRange: "EXPLORE",
            aspects: ["LAYOUT", "COLOR_SCHEME", "TEXT_CONTENT"]
          },
          deviceType: "DESKTOP",
          modelId
        }),
        variantTimeoutMs,
        `generate_variants timed out after ${variantTimeoutMs}ms`
      );
      const extractedVariants = extractScreens(rawVariants);
      log("generate_variants:done", String(extractedVariants.screens.length));
      for (let index = 0; index < extractedVariants.screens.length; index += 1) {
        const item = extractedVariants.screens[index];
        variants.push(await enrichPayload(toPayload(item.screen, `Exploration ${index + 1}`, item.path), `variant ${index + 1}`));
      }
      if (!extractedVariants.screens.length) {
        warnings.push("variant API returned no screens in known projection paths.");
      }
    } catch (error) {
      warnings.push(`variant API failed: ${error?.message || String(error)}. Continuing with the base Stitch screen.`);
      log("generate_variants:error", error?.message || String(error));
      if (fallbackVariantsEnabled) {
        warnings.push("fallback variant generation is enabled; attempting separate generated screens.");
        for (let index = 1; index < variantCount; index += 1) {
          const rawFallback = await generateWithRetry(`${variantPrompt}\\n\\nAlternative design ${index}: ${directionFor(index)} Do not repeat the base composition.`, `fallback ${index}`);
          rawFallbackGenerations.push(sanitize(rawFallback));
          const extractedFallback = extractScreens(rawFallback);
          if (extractedFallback.screens[0]) {
            const payload = await enrichPayload(toPayload(extractedFallback.screens[0].screen, `Generated alternative ${index}`, extractedFallback.screens[0].path), `fallback ${index}`);
            const marker = `${payload.screenId || payload.id || ""}|${payload.htmlUrl || ""}|${payload.imageUrl || ""}`;
            if (!seenVariantKeys.has(marker)) {
              seenVariantKeys.add(marker);
              variants.push(payload);
            }
          } else {
            warnings.push(`fallback ${index} returned no screen in known projection paths.`);
          }
        }
      } else {
        warnings.push("fallback variant generation is disabled; base Stitch screen remains eligible for critique.");
      }
    }
  }
  const htmlUrl = variants[0]?.htmlUrl || "";
  const imageUrl = variants[0]?.imageUrl || "";
  const partialProviderResult = variantCount > 1 && variants.length < variantCount;
  console.log(JSON.stringify({
    ok: true,
    status: partialProviderResult ? "partial_provider_result" : "generated",
    provider: "stitch",
    projectId,
    modelId,
    screenId: variants[0]?.screenId || "",
    htmlUrl,
    imageUrl,
    variants,
    partialProviderResult,
    projectionPathsTried: baseExtraction.paths,
    rawGenerate: sanitize(rawGenerate),
    rawVariants: rawVariants ? sanitize(rawVariants) : null,
    rawGetScreens,
    rawFallbackGenerations,
    warnings
  }));
}
try {
  await main();
} catch (error) {
  console.log(JSON.stringify({
    ok: false,
    status: "failed",
    provider: "stitch",
    projectId,
    modelId,
    error: error?.message || String(error),
    rawGenerate: rawGenerate ? sanitize(rawGenerate) : null,
    rawVariants: rawVariants ? sanitize(rawVariants) : null,
    rawGetScreens,
    rawFallbackGenerations,
    warnings
  }));
  process.exitCode = process.exitCode || 1;
} finally {
  log("close:start");
  await toolClient.close?.();
  log("close:done");
}
"""


def _stitch_payload_from_stdout(stdout: str | None) -> dict[str, Any]:
    for line in reversed((stdout or "").strip().splitlines()):
        payload = _json_loads(line, {})
        if isinstance(payload, dict) and payload:
            return payload
    return {}


def _stitch_log_text(stdout: str | None, stderr: str | None, payload: dict[str, Any]) -> str:
    lines = []
    if stderr:
        lines.append(str(stderr).strip())
    if payload:
        summary = {
            "stdout_payload": "captured",
            "ok": payload.get("ok"),
            "status": payload.get("status"),
            "provider": payload.get("provider"),
            "modelId": payload.get("modelId"),
            "projectId": payload.get("projectId"),
            "screenId": payload.get("screenId"),
            "variantCount": len(payload.get("variants") or []) if isinstance(payload.get("variants"), list) else 0,
            "projectionPathsTried": payload.get("projectionPathsTried") or [],
            "warnings": payload.get("warnings") or [],
            "rawArtifacts": [
                "stitch-raw-generate-response.json" if payload.get("rawGenerate") is not None else "",
                "stitch-raw-variants-response.json" if payload.get("rawVariants") is not None else "",
                "stitch-raw-get-screen-responses.json" if payload.get("rawGetScreens") is not None else "",
                "stitch-raw-fallback-generate-responses.json" if payload.get("rawFallbackGenerations") is not None else "",
            ],
        }
        summary["rawArtifacts"] = [item for item in summary["rawArtifacts"] if item]
        lines.append(json.dumps(_sanitize_stitch_payload(summary), ensure_ascii=True, sort_keys=True, default=str))
    elif stdout:
        lines.append(str(stdout).strip()[:4000])
    return "\n".join(line for line in lines if line) + "\n"


def _write_stitch_raw_artifacts(design_root: Path, payload: dict[str, Any], *, prefix: str = "") -> list[str]:
    if not isinstance(payload, dict) or not payload:
        return []
    safe_prefix = re.sub(r"[^a-z0-9_-]+", "-", _clean(prefix).lower()).strip("-")
    artifact_keys = {
        "rawGenerate": "stitch-raw-generate-response.json",
        "rawVariants": "stitch-raw-variants-response.json",
        "rawGetScreens": "stitch-raw-get-screen-responses.json",
        "rawFallbackGenerations": "stitch-raw-fallback-generate-responses.json",
    }
    written: list[str] = []
    for key, filename in artifact_keys.items():
        if key not in payload or payload.get(key) is None:
            continue
        path = design_root / (f"stitch-{safe_prefix}-{filename.removeprefix('stitch-')}" if safe_prefix else filename)
        sanitized = _sanitize_stitch_payload(payload.get(key))
        path.write_text(json.dumps(sanitized, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        written.append(str(path))
    if written:
        manifest_path = design_root / (f"stitch-{safe_prefix}-raw-response-manifest.json" if safe_prefix else "stitch-raw-response-manifest.json")
        manifest = {
            "provider": "stitch",
            "attempt": safe_prefix,
            "model_id": payload.get("modelId"),
            "project_id": payload.get("projectId"),
            "screen_id": payload.get("screenId"),
            "status": payload.get("status") or ("generated" if payload.get("ok") else "failed"),
            "projection_paths_tried": payload.get("projectionPathsTried") or [],
            "raw_artifacts": written,
            "warnings": payload.get("warnings") or [],
        }
        manifest_path.write_text(json.dumps(_sanitize_stitch_payload(manifest), ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        written.append(str(manifest_path))
    return written


def _sanitize_stitch_payload(value: Any, *, _depth: int = 0) -> Any:
    if _depth > 12:
        return "[redacted:depth-limit]"
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, child in value.items():
            if re.search(r"api.?key|token|secret|authorization|cookie|credential|password", str(key), re.IGNORECASE):
                sanitized[str(key)] = "[redacted]"
            else:
                sanitized[str(key)] = _sanitize_stitch_payload(child, _depth=_depth + 1)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_stitch_payload(item, _depth=_depth + 1) for item in value[:200]]
    if isinstance(value, str):
        text = re.sub(r"^((?:https?://)[^?#]+)[?#].*$", r"\1?[redacted]", value)
        if len(text) > 12000:
            return f"{text[:12000]}...[truncated {len(text) - 12000} chars]"
        return text
    return value


def _stitch_failure_summary(log_text: str | None, *, fallback: str) -> str:
    lines = [line.strip() for line in (log_text or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if "StitchError:" in line:
            return f"Stitch SDK failed: {line.split('StitchError:', 1)[1].strip()}"
        if "MCP error" in line:
            return f"Stitch SDK failed: {line.split('error', 1)[-1].strip() if '[friday-stitch]' in line else line}"
    for line in reversed(lines):
        if line.startswith("[friday-stitch]"):
            return f"{fallback} Last stage: {line}"
    return fallback


def _stitch_status(*, probe: bool) -> dict[str, Any]:
    enabled = bool(config_value("design_stitch_enabled", True))
    env_key = str(config_value("design_stitch_api_key_env", "STITCH_API_KEY") or "STITCH_API_KEY")
    package = str(config_value("design_stitch_sdk_package", "@google/stitch-sdk") or "@google/stitch-sdk")
    credential = _configured_env(env_key)
    sdk_installed = _node_package_available(package, probe=probe)
    ready = enabled and credential and sdk_installed
    reason = ""
    if not enabled:
        reason = "Stitch provider is disabled by design_stitch_enabled=false."
    elif not credential:
        reason = f"Set {env_key} to enable Google Stitch SDK UI design generation."
    elif not sdk_installed:
        reason = f"Install the Stitch SDK package ({package}) in the Friday runtime."
    return {
        "ready": ready,
        "enabled": enabled,
        "provider": "google_stitch_sdk",
        "role": "ui_design_agent",
        "api_key_env": env_key,
        "credential_configured": credential,
        "sdk_package": package,
        "sdk_installed": sdk_installed,
        "free_required": False,
        "approval_required": bool(config_value("design_external_calls_require_approval", True)),
        "reason": reason or "Stitch SDK is configured for UI design generation.",
        "setup_hint": f"Set {env_key} and install {package}.",
    }


def _v0_status() -> dict[str, Any]:
    enabled = bool(config_value("design_v0_enabled", True))
    free_only = bool(config_value("design_v0_free_only", True))
    free_verified = bool(config_value("design_v0_free_verified", False))
    env_key = str(config_value("design_v0_api_key_env", "V0_API_KEY") or "V0_API_KEY")
    credential = _configured_env(env_key)
    allowed = enabled and credential and (not free_only or free_verified)
    blocked = enabled and (not credential or (free_only and not free_verified))
    if not enabled:
        reason = "v0 fallback is disabled."
    elif not credential:
        reason = f"Set {env_key} only if you want Friday to use v0."
    elif free_only and not free_verified:
        reason = "v0 is configured as free-only; current API docs require Premium/Team usage billing, so Friday will not use it until design_v0_free_verified=true."
    else:
        reason = "v0 frontend fallback is allowed."
    return {
        "ready": allowed,
        "enabled": enabled,
        "provider": "v0",
        "role": "frontend_agent_fallback",
        "api_key_env": env_key,
        "credential_configured": credential,
        "free_only": free_only,
        "free_verified": free_verified,
        "blocked": blocked,
        "reason": reason,
        "setup_hint": "Keep design_v0_free_only=true. Set design_v0_free_verified=true only after confirming the workspace has free v0 API usage.",
    }


def _local_style_memory_status(root: Path) -> dict[str, Any]:
    profiles = style_profiles.list_profiles()
    inferred = style_profiles.infer_profile(root)
    return {
        "ready": True,
        "enabled": bool(config_value("design_style_memory_enabled", True)),
        "provider": "local_style_memory",
        "role": "design_system_memory",
        "free": True,
        "paid_sources_allowed": bool(config_value("design_style_memory_allow_paid_sources", False)),
        "profiles": profiles,
        "inferred_profile": inferred,
        "reason": "Local style profiles are file/database memory and do not require paid API calls.",
    }


def _select_ui_design_provider(providers: dict[str, dict[str, Any]], order: list[str]) -> str:
    for provider in order:
        if provider == "stitch" and providers["stitch"].get("ready"):
            return "stitch"
        if provider == "local_style_memory" and providers["local_style_memory"].get("ready"):
            return "local_style_memory"
    return "local_style_memory" if providers["local_style_memory"].get("ready") else ""


def _select_frontend_provider(providers: dict[str, dict[str, Any]], order: list[str]) -> str:
    for provider in order:
        if provider == "v0" and providers["v0"].get("ready"):
            return "v0"
        if provider == "local_style_memory" and providers["local_style_memory"].get("ready"):
            return "local_style_memory"
    return "local_style_memory" if providers["local_style_memory"].get("ready") else ""


def _missing_steps(providers: dict[str, dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    if not providers["stitch"].get("ready"):
        missing.append(providers["stitch"].get("reason") or "Stitch SDK is not ready.")
    if providers["v0"].get("blocked"):
        missing.append(providers["v0"].get("reason") or "v0 is blocked by free-only policy.")
    if not providers["local_style_memory"].get("ready"):
        missing.append("Local style memory is unavailable.")
    return [item for item in missing if item]


def _summary(providers: dict[str, dict[str, Any]], selected: dict[str, str], missing: list[str]) -> str:
    if providers["stitch"].get("ready"):
        return "Stitch SDK is ready for the UI design agent; frontend fallback follows the free-only v0 policy."
    if selected.get("style_memory"):
        return "Local style memory is ready; Stitch/v0 remain gated until configured and allowed."
    return f"Design providers need setup: {'; '.join(missing[:2])}"


def _brief_autopilot(request: str, product_name: str, stack: dict[str, Any], project_root: Path) -> dict[str, Any]:
    """Expand vague design prompts into a complete, evidence-labeled brief."""

    if not bool(config_value("design_brief_autopilot_enabled", True)):
        return {"version": "brief_autopilot_v1", "active": False, "status": "disabled"}
    original_request = _clean(request)
    meaningful_name = _meaningful_product_name(product_name, original_request)
    vague = _is_vague_design_prompt(original_request)
    style_missing = _style_direction_missing(original_request)
    product_missing = not bool(meaningful_name)
    surface = _autopilot_surface(original_request, stack)
    industry = _autopilot_industry(original_request, stack)
    if vague and product_missing and industry == "general_business" and surface != "operational_dashboard":
        industry = "luxury"
    smart_default = _smart_design_default(industry, surface)
    selected_name = meaningful_name or _autopilot_default_product_name(industry, surface)
    research = _autopilot_research_plan(original_request, selected_name, industry, surface)
    directions = _autopilot_design_directions(industry, surface, smart_default, original_request)
    selected_direction = _select_autopilot_direction(directions, smart_default, original_request)
    intent = _autopilot_intent_expansion(
        original_request,
        selected_name,
        industry,
        surface,
        smart_default,
        selected_direction,
    )
    critique = _autopilot_critique_checks(industry, surface, selected_direction)
    expanded_request = _expanded_autopilot_request(
        original_request,
        selected_name,
        intent,
        smart_default,
        selected_direction,
        research,
        critique,
        product_missing=product_missing,
    )
    active = bool(vague or style_missing or product_missing)
    return {
        "version": "brief_autopilot_v1",
        "active": active,
        "status": "expanded" if active else "specific_request_preserved",
        "vague": vague,
        "style_missing": style_missing,
        "product_missing": product_missing,
        "original_request": original_request,
        "expanded_request": expanded_request if active else original_request,
        "product_name": selected_name,
        "surface": surface,
        "industry": industry,
        "assumption_summary": _autopilot_assumption_summary(product_missing, selected_name, industry, surface, selected_direction),
        "ask_only_when_needed": {
            "needs_user_question": bool(product_missing and vague),
            "question": "What product/company should this website be for?",
            "policy": (
                "If interactive clarification is available, ask this one question. "
                "If Friday must continue autonomously, use the stated tasteful assumption and label it clearly in the proof."
            ),
        },
        "intent_expansion": intent,
        "smart_defaults": smart_default,
        "research_before_design": research,
        "design_direction_generator": {
            "directions": directions,
            "selected": selected_direction.get("id") or "",
            "selection_reason": selected_direction.get("why") or "",
        },
        "stitch_prompt_requirements": {
            "emotional_feel": intent.get("emotional_feel") or "",
            "visual_grammar": smart_default.get("visual_grammar") or "",
            "hero_composition": selected_direction.get("hero_composition") or intent.get("composition_archetype") or "",
            "page_sections": intent.get("content_sections") or [],
            "copy_voice": smart_default.get("copy_voice") or "",
            "assets_image_direction": smart_default.get("assets_image_direction") or "",
            "what_to_avoid": intent.get("rejection_rules") or [],
            "output_contract": [
                "Return a complete page/screen with enough content depth to implement, not a hero-only mockup.",
                "Use product/domain-specific visible copy and clear imagery direction.",
                "Expose all critical links/actions as real controls Friday can wire.",
            ],
        },
        "critique_before_code": critique,
    }


def _meaningful_product_name(product_name: str, request: str) -> str:
    name = _clean(product_name).strip(" .,:;")
    if not name:
        return ""
    lowered = name.lower()
    command_names = {
        "build a website",
        "make a website",
        "create a website",
        "design a website",
        "build website",
        "website",
        "landing page",
        "build a landing page",
        "make a landing page",
        "build a web app",
        "build an app",
    }
    if lowered in command_names:
        return ""
    if lowered.startswith(("build ", "make ", "create ", "design ")) and len(name.split()) <= 5:
        return ""
    if lowered in {"site", "web site", "webapp", "dashboard", "app"}:
        return ""
    return name


def _is_vague_design_prompt(request: str) -> bool:
    text = _clean(request).lower()
    if not text:
        return True
    words = re.findall(r"[a-z0-9]+", text)
    if len(words) <= 5 and any(term in text for term in ("website", "site", "landing page", "app", "dashboard")):
        return True
    generic_commands = (
        "build a website",
        "make a website",
        "create a website",
        "design a website",
        "build me a website",
        "build a landing page",
        "make a landing page",
        "create a landing page",
        "build an app",
        "build a dashboard",
    )
    if any(text == command or text.startswith(command + " ") for command in generic_commands):
        return len(words) <= 9 and not any(marker in text for marker in ("for ", "called ", "about ", "brand ", "company "))
    return False


def _style_direction_missing(request: str) -> bool:
    text = _clean(request).lower()
    style_markers = (
        "luxury",
        "editorial",
        "cinematic",
        "minimal",
        "playful",
        "3d",
        "immersive",
        "parallax",
        "animated",
        "dark",
        "light",
        "brutalist",
        "neumorphic",
        "glass",
        "terminal",
        "premium",
        "tactile",
        "image-led",
        "product-led",
    )
    if any(marker in text for marker in style_markers):
        return False
    return any(marker in text for marker in ("website", "site", "landing page", "web app", "dashboard", "app"))


def _autopilot_surface(request: str, stack: dict[str, Any]) -> str:
    text = _clean(request).lower()
    stack_id = _clean((stack or {}).get("stack") or (stack or {}).get("kind")).lower()
    marketing_intent = any(term in text for term in ("website", "site", "landing page", "landing website", "company website", "business website", "marketing website"))
    if marketing_intent:
        return "marketing_website"
    if any(term in text for term in ("dashboard", "command center", "portal", "admin", "management dashboard")):
        return "operational_dashboard"
    if "management" in text and not any(term in text for term in ("website", "site", "landing page", "landing website", "company website", "business website")):
        return "operational_dashboard"
    if stack_id in {"web-app", "web", "nextjs", "frontend"}:
        return "marketing_website"
    return "product_app"


def _autopilot_industry(request: str, stack: dict[str, Any]) -> str:
    text = _clean(request).lower()
    if _autopilot_surface(request, stack) == "operational_dashboard" and not any(term in text for term in ("marketing", "landing", "website")):
        if any(term in text for term in ("clinic", "hospital", "healthcare", "patient", "dental")):
            return "healthcare"
        if any(term in text for term in ("fleet", "warehouse", "delivery", "dispatch", "logistics")):
            return "logistics"
    try:
        return _clean(design_director.infer_industry(request, stack=stack)) or "general_business"
    except Exception:
        pass
    try:
        strategy = design_director.design_strategy(request, _product_name_from_request(request), stack=stack)
        return _clean(strategy.get("industry")) or "general_business"
    except Exception:
        return "general_business"


def _smart_design_default(industry: str, surface: str) -> dict[str, Any]:
    industry_id = _clean(industry).lower() or "general_business"
    taxonomy = getattr(design_director, "_DESIGN_TAXONOMY", {}) if hasattr(design_director, "_DESIGN_TAXONOMY") else {}
    taxonomy_entry = taxonomy.get(industry_id) if isinstance(taxonomy, dict) else {}
    defaults: dict[str, dict[str, Any]] = {
        "luxury": {
            "selected_default": "luxury_editorial_tactile",
            "reason": "Luxury should signal scarcity, craft, and restraint before conversion pressure.",
            "composition_archetype": "immersive full-bleed or editorial asymmetric hero, never generic SaaS split hero",
            "emotional_feel": "desire, restraint, intimacy, confidence, exclusivity",
            "visual_grammar": "negative space, material close-ups, refined typography, quiet motion, high-touch inquiry path",
            "copy_voice": "spare, sensorial, confident",
            "assets_image_direction": "macro product detail, atelier/craft, private-client atmosphere, crisp non-blurry hero imagery",
        },
        "developer_tools": {
            "selected_default": "terminal_product_proof",
            "reason": "Developers trust concrete product proof, commands, docs, architecture, and technical clarity.",
            "composition_archetype": "terminal/product-proof hero with code, docs, architecture, or live product artifact",
            "emotional_feel": "competence, speed, clarity, control",
            "visual_grammar": "monospace details, code panels, command outputs, architecture diagrams, docs navigation",
            "copy_voice": "direct, technical, specific",
            "assets_image_direction": "product UI, CLI, schema, API, docs, integration proof; no stock lifestyle hero",
        },
        "fintech": {
            "selected_default": "trust_clarity_precision",
            "reason": "Financial products must earn confidence through clarity, safety, and transparent controls.",
            "composition_archetype": "trust-led product-flow hero with balances, transfers, fees, security, and proof",
            "emotional_feel": "trust, precision, control, modern confidence",
            "visual_grammar": "clean data surfaces, secure cues, tabular numbers, transparent fees, compliance notes",
            "copy_voice": "precise, reassuring, transparent",
            "assets_image_direction": "account states, card/payment flows, verification steps, security proof",
        },
        "ai_saas": {
            "selected_default": "workflow_product_demo",
            "reason": "AI SaaS needs to prove the workflow, not hide behind vague intelligence language.",
            "composition_archetype": "workflow-stage hero or product-demo motion with before/after states",
            "emotional_feel": "momentum, clarity, leverage, calm automation",
            "visual_grammar": "workflow lanes, model/action traces, generated outputs, human approval points",
            "copy_voice": "use-case specific, practical, proof-led",
            "assets_image_direction": "product workflow states, automations, approvals, output previews, trace/proof artifacts",
        },
        "construction": {
            "selected_default": "project_photography_credibility",
            "reason": "Construction websites win on built proof, safety, scale, delivery, and trust.",
            "composition_archetype": "project-photography hero with credibility stats, featured builds, and bid/contact path",
            "emotional_feel": "solid, capable, safe, proven, substantial",
            "visual_grammar": "real site/project imagery, material textures, timelines, capability bands, safety proof",
            "copy_voice": "direct, grounded, confident",
            "assets_image_direction": "sharp jobsite/project photography, cranes, interiors, teams, materials, before/after proof",
        },
        "fashion": {
            "selected_default": "image_led_editorial",
            "reason": "Fashion needs taste, image rhythm, product styling, and editorial restraint.",
            "composition_archetype": "image-led editorial hero, lookbook rhythm, collection/product moments",
            "emotional_feel": "desire, identity, freshness, cultural confidence",
            "visual_grammar": "large photography, asymmetry, lookbook cards, tactile product close-ups, campaign pacing",
            "copy_voice": "short, evocative, brand-forward",
            "assets_image_direction": "model/product photography, editorial crops, fabric texture, collection storytelling",
        },
        "dashboard": {
            "selected_default": "dense_operational_ui",
            "reason": "Dashboards should optimize repeated work, scanning, triage, and action.",
            "composition_archetype": "dense operational shell with nav, metrics, queues, detail panels, filters, and actions",
            "emotional_feel": "calm control, speed, confidence, low cognitive load",
            "visual_grammar": "compact data hierarchy, status chips, tables, cards, charts, modals, empty/loading/error states",
            "copy_voice": "specific operational language",
            "assets_image_direction": "real data objects, charts, maps, operational status, no marketing hero stock",
        },
    }
    aliases = {
        "government": "government",
        "ngo": "ngo",
        "education": "education",
        "gaming": "gaming",
        "marketplace": "marketplace",
        "logistics": "logistics",
        "portfolio": "portfolio",
        "healthcare": "healthcare",
        "energy_climate": "energy_climate",
    }
    if surface == "operational_dashboard":
        base = defaults["dashboard"].copy()
        base["selected_default"] = f"{industry_id}_dense_operational_ui" if industry_id != "general_business" else base["selected_default"]
    else:
        base = defaults.get(industry_id) or {}
    if not base and industry_id in aliases:
        base = {
            "selected_default": f"{industry_id}_category_direction",
            "reason": f"Use Friday's {industry_id.replace('_', ' ')} taxonomy instead of generic SaaS defaults.",
            "composition_archetype": (taxonomy_entry or {}).get("layout_signature") or "category-specific hero with proof, depth, and clear action",
            "emotional_feel": (taxonomy_entry or {}).get("emotional_feel") or "credible, useful, specific",
            "visual_grammar": (taxonomy_entry or {}).get("visual_language") or "domain-specific visual objects and production web hierarchy",
            "copy_voice": (taxonomy_entry or {}).get("copy_voice") or "specific and clear",
            "assets_image_direction": (taxonomy_entry or {}).get("imagery") or "realistic domain imagery and product proof",
        }
    if not base:
        base = {
            "selected_default": "cinematic_product_led",
            "reason": "No explicit style was provided, so Friday chooses a strong product-led art direction instead of generic SaaS.",
            "composition_archetype": "cinematic product-led hero with strong first-viewport product signal and content depth",
            "emotional_feel": "polished, confident, original, useful",
            "visual_grammar": "clear hierarchy, memorable hero, specific proof, tactile details, restrained motion",
            "copy_voice": "specific, original, human",
            "assets_image_direction": "sharp product/domain imagery with visible details, not blurry stock or abstract filler",
        }
    category_defaults = dict(taxonomy_entry or {})
    return {**base, "industry": industry_id, "surface": surface, "category_defaults": category_defaults}


def _autopilot_default_product_name(industry: str, surface: str) -> str:
    industry_id = _clean(industry).lower()
    if surface == "operational_dashboard":
        return {
            "healthcare": "CareFlow Command",
            "logistics": "RoutePulse Ops",
            "education": "CampusOps Center",
            "energy_climate": "KineticGrid Energy",
        }.get(industry_id, "SignalWorks Command")
    return {
        "luxury": "Nocturne Audio",
        "fashion": "Vela Atelier",
        "developer_tools": "Nexus Forge",
        "fintech": "Ledgerly",
        "ai_saas": "TaskPilot AI",
        "construction": "Northline Builders",
        "energy_climate": "KineticGrid Energy",
        "marketplace": "CraftMarket",
        "ngo": "Harbor Hope",
        "education": "BrightPath Academy",
        "healthcare": "Westside Clinic",
    }.get(industry_id, "Aster Vale Studio")


def _autopilot_research_plan(request: str, product_name: str, industry: str, surface: str) -> dict[str, Any]:
    industry_label = _clean(industry).replace("_", " ") or "product"
    surface_label = "dashboard" if surface == "operational_dashboard" else "website"
    queries = _dedupe(
        [
            f"{industry_label} {surface_label} design examples",
            f"{industry_label} customer needs {surface_label}",
            f"{industry_label} landing page copy patterns",
            f"{industry_label} competitor website pricing positioning",
            f"{product_name} alternatives competitors" if _clean(product_name) else "",
        ]
    )[:5]
    live_research = bool(config_value("design_autopilot_live_research", False) or config_value("design_research_live_default", False))
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    if live_research:
        try:
            from core import search_broker

            for query in queries[:3]:
                payload = search_broker.search(query, limit=3, use_cache=True)
                results.extend(payload.get("results") or [])
                if payload.get("errors"):
                    errors.extend(str(item.get("error") or item) for item in payload.get("errors") or [])
        except Exception as exc:  # pragma: no cover - live research providers are optional
            errors.append(_clean(str(exc))[:220])
    return {
        "status": "live_research_complete" if live_research and results else "live_research_unavailable" if live_research else "planned_with_local_evidence",
        "live_research": live_research,
        "queries": queries,
        "evidence_basis": _dedupe(
            [
                "Friday design taxonomy",
                "local style/taste memory",
                "product-studio design rules",
                "live web search" if results else "",
            ]
        ),
        "results": results[:8],
        "errors": errors[:4],
        "requires_live_research": not live_research,
        "non_guessing_rule": "Use these evidence sources to form the brief; if evidence is thin, label assumptions instead of pretending certainty.",
    }


def _autopilot_design_directions(industry: str, surface: str, smart_default: dict[str, Any], request: str) -> list[dict[str, str]]:
    if surface == "operational_dashboard":
        return [
            {
                "id": "dense_operational_cockpit",
                "name": "Dense Operational Cockpit",
                "why": "Best for repeated daily work where the user needs scan, triage, and action density.",
                "hero_composition": "app shell first viewport with metrics, queue, detail panel, and visible actions",
                "avoid": "marketing hero, decorative cards, empty whitespace",
            },
            {
                "id": "map_or_flow_first",
                "name": "Map/Flow First",
                "why": "Use when location, movement, routing, stages, or capacity matters.",
                "hero_composition": "map/timeline/workflow canvas with side queue and status rail",
                "avoid": "static infographic with no controls",
            },
            {
                "id": "exception_command_center",
                "name": "Exception Command Center",
                "why": "Use when risks, alerts, approvals, and owner handoffs define the workflow.",
                "hero_composition": "exception queue, risk cards, owners, and action drawer in first viewport",
                "avoid": "generic KPI-only dashboard",
            },
        ]
    industry_id = _clean(industry).lower()
    if industry_id in {"luxury", "fashion"}:
        return [
            {
                "id": "cinematic_product_led",
                "name": "Cinematic Product-Led",
                "why": "Strongest match for premium first impression and memorable product signal.",
                "hero_composition": "full-bleed product/media hero or immersive scene with crisp product detail",
                "avoid": "generic split hero, dashboard cards, blurry imagery",
            },
            {
                "id": "editorial_minimal",
                "name": "Editorial Minimal",
                "why": "Good when the brand needs restraint, confidence, and space.",
                "hero_composition": "single-column statement with magazine-like art direction and large tactile image moments",
                "avoid": "marketing badges, noisy gradients, loud CTAs",
            },
            {
                "id": "material_closeup_story",
                "name": "Material Close-Up Story",
                "why": "Good when craft, provenance, or object quality must carry trust.",
                "hero_composition": "macro material/product close-up with story panels and concierge action",
                "avoid": "flat service cards",
            },
        ]
    if industry_id == "developer_tools":
        return [
            {
                "id": "terminal_product_proof",
                "name": "Terminal Product Proof",
                "why": "Developers need to see the actual workflow, command, API, and result.",
                "hero_composition": "code/terminal/product proof hero with docs and install path visible",
                "avoid": "stock people, vague AI copy, lifestyle hero",
            },
            {
                "id": "architecture_diagram_first",
                "name": "Architecture Diagram First",
                "why": "Best when control, self-hosting, or system trust is the main promise.",
                "hero_composition": "architecture/schema/API diagram as first-viewport proof object",
                "avoid": "abstract cloud icons without code",
            },
            {
                "id": "interactive_demo_motion",
                "name": "Interactive Demo Motion",
                "why": "Useful when the product value is state transformation or generation speed.",
                "hero_composition": "step-by-step product demo with command, generated file, deploy result",
                "avoid": "decorative animation that does not explain the product",
            },
        ]
    if industry_id == "ai_saas":
        return [
            {
                "id": "workflow_product_demo",
                "name": "Workflow Product Demo",
                "why": "AI products need concrete before/after workflow proof.",
                "hero_composition": "workflow stages with human approval, generated output, and proof trail",
                "avoid": "glowing AI orb or vague automation claims",
            },
            {
                "id": "cinematic_scroll",
                "name": "Cinematic Scroll",
                "why": "Good for a product story that unfolds through stages and outcomes.",
                "hero_composition": "centered story hero with scroll-linked product states",
                "avoid": "motion without useful product explanation",
            },
            {
                "id": "interactive_3d_demo",
                "name": "Interactive 3D Demo",
                "why": "Use only when the product has an object/process that benefits from spatial explanation.",
                "hero_composition": "3D/process scene with product state overlays and fallback",
                "avoid": "heavy WebGL for decoration only",
            },
        ]
    return [
        {
            "id": _clean(smart_default.get("selected_default")) or "cinematic_product_led",
            "name": _clean(smart_default.get("selected_default")).replace("_", " ").title() or "Cinematic Product-Led",
            "why": smart_default.get("reason") or "Strong default beats generic SaaS.",
            "hero_composition": smart_default.get("composition_archetype") or "memorable product/domain hero with proof",
            "avoid": "generic SaaS split hero, placeholder copy, blurry imagery",
        },
        {
            "id": "editorial_minimal",
            "name": "Editorial Minimal",
            "why": "A restrained fallback when the product needs credibility and a clean first impression.",
            "hero_composition": "focused statement hero with strong visual object and proof band",
            "avoid": "oversized type and empty brochure sections",
        },
        {
            "id": "interactive_product_demo",
            "name": "Interactive Product Demo",
            "why": "Use when the visitor needs to understand the product through states, steps, or motion.",
            "hero_composition": "product/demo canvas with clear controls and state transitions",
            "avoid": "animation that hides content or hurts performance",
        },
    ]


def _select_autopilot_direction(directions: list[dict[str, str]], smart_default: dict[str, Any], request: str) -> dict[str, str]:
    text = _clean(request).lower()
    if any(term in text for term in ("3d", "immersive", "webgl", "three", "parallax", "animation")):
        for direction in directions:
            if any(term in direction.get("id", "") for term in ("3d", "interactive", "cinematic")):
                return direction
    selected_default = _clean(smart_default.get("selected_default"))
    for direction in directions:
        if selected_default and selected_default in direction.get("id", ""):
            return direction
    return directions[0] if directions else {}


def _autopilot_intent_expansion(
    request: str,
    product_name: str,
    industry: str,
    surface: str,
    smart_default: dict[str, Any],
    selected_direction: dict[str, str],
) -> dict[str, Any]:
    taxonomy = smart_default.get("category_defaults") if isinstance(smart_default.get("category_defaults"), dict) else {}
    sections = _autopilot_sections(industry, surface)
    rejection_rules = _dedupe(
        [
            "Do not generate generic SaaS split-hero scaffolds unless the selected direction explicitly requires a split.",
            "Do not return a hero-only page; include enough below-fold content for the page goal.",
            "Do not use blurry, low-detail, darkened hero imagery as the main proof object.",
            "Do not use placeholder labels such as Home 1, Service 2, feature one, lorem ipsum, or vague startup filler.",
            "Do not implement the first generated design blindly; critique it before code.",
            *(taxonomy.get("anti_patterns") or []),
        ]
    )
    business_model = _autopilot_business_model(industry, surface)
    return {
        "product_company_type": _product_company_type(industry, surface),
        "product_name": product_name,
        "target_users": _autopilot_target_users(industry, surface),
        "emotional_feel": smart_default.get("emotional_feel") or taxonomy.get("emotional_feel") or "",
        "page_goal": _autopilot_page_goal(surface),
        "business_model": business_model,
        "content_sections": sections,
        "design_category": _clean(industry).replace("_", " ") or "general product",
        "composition_archetype": selected_direction.get("hero_composition") or smart_default.get("composition_archetype") or "",
        "copy_voice": smart_default.get("copy_voice") or taxonomy.get("copy_voice") or "",
        "rejection_rules": rejection_rules,
    }


def _autopilot_sections(industry: str, surface: str) -> list[str]:
    if surface == "operational_dashboard":
        return ["navigation shell", "live status metrics", "work/exception queue", "detail panel", "action drawer", "settings/support states"]
    industry_id = _clean(industry).lower()
    by_industry = {
        "luxury": ["immersive product hero", "craft/provenance", "collection or offer", "materials/details", "private inquiry"],
        "fashion": ["editorial hero", "collection lookbook", "fit/material details", "campaign proof", "shop/inquiry path"],
        "developer_tools": ["product/code hero", "quickstart", "architecture proof", "use cases", "pricing/docs/community"],
        "fintech": ["trust-led hero", "product flow", "security/compliance", "fees/pricing", "signup path"],
        "ai_saas": ["workflow hero", "before/after process", "AI proof outputs", "approval/safety", "pricing/demo CTA"],
        "construction": ["project-photo hero", "featured projects", "capabilities", "safety/delivery proof", "bid/contact path"],
        "ngo": ["mission hero", "problem/solution", "impact metrics", "stories", "donate/volunteer action"],
        "education": ["program/value hero", "learning path", "outcomes", "faculty/proof", "admission/contact action"],
        "marketplace": ["search/discovery hero", "category proof", "buyer/seller trust", "how it works", "join/list CTA"],
        "energy_climate": ["energy-risk hero", "asset/telemetry proof", "case outcomes", "resilience metrics", "demo/contact"],
    }
    return by_industry.get(industry_id, ["memorable hero", "problem/solution", "proof", "features/services", "how it works", "conversion action"])


def _autopilot_target_users(industry: str, surface: str) -> list[str]:
    if surface == "operational_dashboard":
        return ["daily operators", "team leads", "managers responsible for exceptions", "support or operations staff"]
    strategy = {"industry": industry, "surface": surface}
    return _target_audience("", strategy)


def _autopilot_business_model(industry: str, surface: str) -> str:
    if surface == "operational_dashboard":
        return "B2B SaaS or internal operations platform; conversion goal is demo, rollout approval, or workspace adoption."
    industry_id = _clean(industry).lower()
    return {
        "luxury": "premium direct-to-consumer or private inquiry sales",
        "fashion": "direct-to-consumer commerce, lookbook inquiry, or boutique retail",
        "developer_tools": "open-source/core free plan with paid managed cloud or pro tiers",
        "fintech": "subscription, transaction fee, interchange, or managed financial services",
        "ai_saas": "subscription or usage-based SaaS with demo/trial conversion",
        "construction": "project bids, consultations, retainers, or service contracts",
        "ngo": "donations, grants, volunteer signups, and partner support",
    }.get(industry_id, "service, product, subscription, or inquiry-led business model depending on final product choice")


def _product_company_type(industry: str, surface: str) -> str:
    if surface == "operational_dashboard":
        return f"{_clean(industry).replace('_', ' ') or 'operations'} dashboard/product workspace"
    return f"{_clean(industry).replace('_', ' ') or 'product'} company website"


def _autopilot_page_goal(surface: str) -> str:
    if surface == "operational_dashboard":
        return "Help operators understand status, triage issues, and take the next action quickly."
    return "Help visitors understand the product/company, trust it, inspect proof, and take a clear next step."


def _autopilot_critique_checks(industry: str, surface: str, selected_direction: dict[str, str]) -> list[str]:
    checks = [
        "Is the UI genuinely beautiful or at least professionally polished for the chosen category?",
        "Is the first viewport strong, specific, and not a generic SaaS split hero?",
        "Is imagery crisp and meaningful enough to inspect, not blurry/washed-out decoration?",
        "Is there enough content depth beyond the hero for the page/screen goal?",
        "Is the copy original, product-specific, and free of scaffold filler?",
        "Does the design match the product category and selected creative direction?",
        "Can Friday implement the design into real routes/components without dead controls?",
    ]
    if surface == "operational_dashboard":
        checks.append("Does the dashboard support repeated operational work with dense but readable data and actions?")
    if "3d" in (selected_direction.get("id") or "") or "interactive" in (selected_direction.get("id") or ""):
        checks.append("If motion/3D is requested, does it add product understanding and include performance/reduced-motion fallbacks?")
    return checks


def _autopilot_assumption_summary(product_missing: bool, product_name: str, industry: str, surface: str, selected_direction: dict[str, str]) -> str:
    if not product_missing:
        return "The request includes a usable product/company signal; Friday expanded missing design details only."
    return (
        f"No usable product/company was supplied, so Friday will ask one short question when possible. "
        f"If running autonomously, it assumes {product_name}, a {_clean(industry).replace('_', ' ') or 'product'} {surface.replace('_', ' ')}, "
        f"and uses the {selected_direction.get('name') or selected_direction.get('id') or 'selected'} direction."
    )


def _expanded_autopilot_request(
    request: str,
    product_name: str,
    intent: dict[str, Any],
    smart_default: dict[str, Any],
    selected_direction: dict[str, str],
    research: dict[str, Any],
    critique: list[str],
    *,
    product_missing: bool,
) -> str:
    assumption = (
        f"Autonomous assumption: because the original prompt did not name a product/company, use {product_name} as a tasteful placeholder concept and label this assumption in proof."
        if product_missing
        else "Use the named product/company from the original prompt."
    )
    return _clean(
        f"{request}\n\n"
        f"FRIDAY INTENT EXPANSION: {assumption} "
        f"Product/company type: {intent.get('product_company_type')}. "
        f"Target users: {', '.join(intent.get('target_users') or [])}. "
        f"Emotional feel: {intent.get('emotional_feel')}. "
        f"Page goal: {intent.get('page_goal')}. "
        f"Business model: {intent.get('business_model')}. "
        f"Design category: {intent.get('design_category')}. "
        f"Composition archetype: {intent.get('composition_archetype')}. "
        f"Content sections: {', '.join(intent.get('content_sections') or [])}. "
        f"Smart default: {smart_default.get('selected_default')} because {smart_default.get('reason')}. "
        f"Creative direction selected: {selected_direction.get('name') or selected_direction.get('id')} - {selected_direction.get('why')}. "
        f"Research before design: use evidence basis ({', '.join(research.get('evidence_basis') or [])}); research queries: {', '.join(research.get('queries') or [])}. "
        f"Critique before code: {'; '.join(critique[:5])}. "
        f"Rejection rules: {'; '.join(intent.get('rejection_rules') or [])}."
    )


def _design_context_package(
    project_root: Path,
    request: str,
    product_name: str,
    stack: dict[str, Any],
    profile: dict[str, Any],
    contract: dict[str, Any],
    strategy: dict[str, Any],
    *,
    artifact_scope: str = "",
    original_request: str = "",
    expanded_request: str = "",
    brief_autopilot: dict[str, Any] | None = None,
    research_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the richer context package Stitch and Friday both consume."""

    request_text = _clean(request)
    surface = _clean(strategy.get("surface") or contract.get("surface") or "product_app")
    industry = _clean(strategy.get("industry") or "general_business")
    keywords = _domain_keywords(request_text)
    page_map = _website_page_specs(request_text) if surface == "marketing_website" else []
    brand_system = _brand_system(product_name, strategy)
    site_continuity = _site_continuity(project_root, request_text, product_name, profile, contract, strategy, brand_system, artifact_scope, page_map)
    visual_memory = _visual_reference_memory(project_root, profile, strategy)
    learned_rules = friday_learning_loop.learning_context_for_request(request_text, root=project_root, domain="design", limit=10)
    return {
        "version": "rich_stitch_context_v1",
        "source": "Friday design provider brief",
        "user_intent": {
            "raw_request": _clean(original_request) or request_text,
            "expanded_request": _clean(expanded_request) or request_text,
            "product_name": _clean(product_name),
            "surface": surface,
            "industry": industry,
            "page_scope": contract.get("page_label") or "primary",
            "requested_stack": stack.get("label") or stack.get("stack") or "",
        },
        "product_goal": _product_goal(request_text, product_name, contract, strategy),
        "target_audience": _target_audience(request_text, strategy),
        "emotional_intent": strategy.get("emotional_feel") or "",
        "message": strategy.get("message") or "",
        "inspiration_references": _inspiration_references(strategy, contract, request_text),
        "visual_reference_memory": visual_memory,
        "learned_rules": learned_rules,
        "research_context": research_context or {},
        "brief_autopilot": brief_autopilot or {},
        "brand_system": brand_system,
        "site_continuity": site_continuity,
        "visual_context": {
            "direction": strategy.get("direction") or "",
            "visual_language": strategy.get("visual_language") or "",
            "layout_signature": strategy.get("layout_signature") or "",
            "palette": strategy.get("palette") or "",
            "typography": strategy.get("typography") or "",
            "imagery": strategy.get("imagery") or "",
            "interaction_model": strategy.get("interaction_model") or "",
            "copy_voice": strategy.get("copy_voice") or "",
            "tokens": _design_tokens(strategy),
        },
        "content_model": _content_model(request_text, product_name, contract, strategy, keywords, page_map),
        "creative_brief": _creative_brief(request_text, product_name, contract, strategy),
        "composition_spec": _composition_spec(request_text, product_name, contract, strategy),
        "experience_mode": _experience_mode_spec(request_text, product_name, contract, strategy),
        "section_blueprint": _section_blueprint(request_text, product_name, contract, strategy, keywords, page_map),
        "copy_bank": _copy_bank(request_text, product_name, contract, strategy, keywords),
        "component_inventory": _component_inventory(request_text, contract, strategy),
        "variant_briefs": _variant_briefs(strategy, contract),
        "output_contract": _stitch_output_contract(contract, strategy),
        "taxonomy_prompt_profile": _industry_prompt_profile(industry, strategy),
        "code_context": _code_context(project_root, stack),
        "design_rules": _design_rules(contract, strategy),
        "design_system_context": _design_system_context(profile, strategy, contract),
        "handoff_requirements": _handoff_requirements(profile, contract, strategy),
    }


def _product_goal(request: str, product_name: str, contract: dict[str, Any], strategy: dict[str, Any]) -> str:
    name = _clean(product_name) or "the product"
    surface = _clean(strategy.get("surface") or contract.get("surface")).lower()
    industry = _clean(strategy.get("industry")).lower()
    if industry == "developer_tools":
        return (
            f"Show technical builders why {name} is useful, credible, and controllable: "
            "make the product model, quickstart path, architecture proof, and conversion action obvious in one scan."
        )
    if surface == "operational_dashboard":
        return (
            f"Design {name} as a working operator surface that helps teams see status, triage work, "
            "choose the next action, and keep proof attached."
        )
    if surface == "marketing_website":
        return (
            f"Help visitors understand {name}, trust the offer, compare the value, and take the next step "
            "without generic filler or oversized brochure sections."
        )
    return f"Turn the request into a concrete product surface for {name} with clear hierarchy, useful actions, and proof."


def _target_audience(request: str, strategy: dict[str, Any]) -> list[str]:
    industry = _clean(strategy.get("industry")).lower()
    surface = _clean(strategy.get("surface")).lower()
    audiences = {
        "developer_tools": ["technical founders", "full-stack developers", "AI builders", "open-source maintainers"],
        "ai_saas": ["operations leaders", "automation teams", "AI product teams", "technical buyers"],
        "fintech": ["finance teams", "risk-conscious customers", "operators handling money movement"],
        "gaming": ["players", "creators", "community moderators", "competitive teams"],
        "logistics": ["dispatchers", "fleet managers", "warehouse operators", "customer support leads"],
        "education": ["administrators", "registrars", "faculty operations teams", "students needing support"],
        "ngo": ["donors", "program managers", "community partners", "volunteers"],
        "fashion": ["style-conscious shoppers", "buyers", "creative directors", "brand followers"],
        "luxury": ["high-intent private clients", "collectors", "concierge buyers", "brand loyalists"],
        "portfolio": ["hiring managers", "clients", "collaborators", "creative directors"],
        "government": ["residents", "public servants", "case workers", "civic administrators"],
        "marketplace": ["buyers", "sellers", "operators", "trust and safety teams"],
        "energy_climate": ["facility managers", "energy managers", "sustainability teams", "commercial building operators", "resilience planners"],
        "construction": ["project owners", "developers", "procurement teams", "site leadership"],
        "healthcare": ["patients", "care coordinators", "clinic operators", "providers"],
        "field_service": ["dispatchers", "technicians", "service managers", "customers waiting on ETAs"],
    }
    selected = list(audiences.get(industry) or ["decision makers", "daily operators", "end users"])
    if surface == "operational_dashboard":
        selected.insert(0, "operators who use this repeatedly during the workday")
    if surface == "marketing_website":
        selected.insert(0, "first-time visitors deciding whether to trust the product")
    if "founder" in request.lower() and "founders" not in " ".join(selected).lower():
        selected.append("founders")
    return _dedupe(selected)[:6]


_INDUSTRY_PROMPT_EXTRAS: dict[str, dict[str, Any]] = {
    "luxury": {
        "decision_moment": "A high-intent private client is deciding whether the brand feels rare, crafted, and worthy of a personal inquiry.",
        "primary_objection": "The experience can feel mass-market, loud, or insufficiently premium.",
        "design_answer": "Use restraint, material detail, provenance, appointment paths, and quiet confidence instead of badges or discounts.",
        "trust_signals": ["craft proof", "provenance", "atelier detail", "private appointment", "concierge access"],
        "sections": [
            ("Hero", "Create desire with brand, material detail, and a discreet action.", ["brand statement", "hero image", "concierge CTA"], ["editorial hero", "material close-up"]),
            ("Provenance", "Show why the object/service is rare and credible.", ["craft", "materials", "heritage"], ["story panel", "detail modules"]),
            ("Collection or offer", "Let the visitor inspect options without ecommerce clutter.", ["collection", "fit", "scarcity"], ["lookbook grid", "product cards"]),
            ("Concierge path", "Make the next step private and high-touch.", ["appointment", "inquiry", "response promise"], ["concierge form", "contact strip"]),
        ],
        "components": ["editorial hero", "material image field", "provenance cards", "lookbook modules", "concierge inquiry form"],
        "headline_directions": ["Crafted for private clients who notice the difference.", "A quieter standard of luxury, made visible.", "Objects and experiences with provenance."],
        "microcopy": ["Request concierge access", "View the collection", "Private appointment"],
        "avoid_words": ["discount", "deal", "limited-time offer", "all-in-one solution"],
    },
    "fintech": {
        "decision_moment": "A user is deciding whether this product can handle money safely, clearly, and without hidden risk.",
        "primary_objection": "Financial products can feel risky, opaque, or overhyped.",
        "design_answer": "Show security, fees, account states, controls, compliance notes, and transparent flows.",
        "trust_signals": ["security posture", "transparent fees", "account controls", "compliance cue", "audit trail"],
        "sections": [
            ("Hero", "Explain the financial action and trust model quickly.", ["secure value prop", "primary action", "fee/security cue"], ["account/payment preview"]),
            ("Trust and security", "Prove safety before asking for conversion.", ["verification", "encryption", "compliance"], ["security cards", "risk controls"]),
            ("Product flow", "Show money movement or account control.", ["send", "receive", "approve", "track"], ["transaction timeline", "account cards"]),
            ("Pricing or fees", "Make costs and limits easy to understand.", ["transparent fee", "plan", "limit"], ["fee table", "calculator"]),
        ],
        "components": ["account snapshot", "transaction timeline", "security proof cards", "fee table", "calculator/input"],
        "headline_directions": ["Move money with clarity and control.", "Financial operations without hidden risk.", "Know every fee, status, and next action."],
        "microcopy": ["View fees", "Verify account", "Transfer securely"],
        "avoid_words": ["guaranteed returns", "risk-free profit", "casino", "moonshot"],
    },
    "gaming": {
        "decision_moment": "A player is deciding if the world, challenge, and community are exciting enough to join now.",
        "primary_objection": "The page can feel like corporate software instead of a living game.",
        "design_answer": "Lead with gameplay, progression, modes, community signals, and immediate play/download actions.",
        "trust_signals": ["gameplay media", "mode cards", "progression loop", "community event", "platform badges"],
        "sections": [
            ("Hero", "Show gameplay energy and immediate play action.", ["title", "trailer/play CTA", "platform"], ["cinematic/gameplay scene"]),
            ("Modes", "Explain what players actually do.", ["mode", "quest", "match", "reward"], ["mode cards"]),
            ("Progression", "Show mastery and reasons to return.", ["level", "loadout", "rank"], ["progression track"]),
            ("Community", "Show events or multiplayer credibility.", ["events", "leaderboard", "guild"], ["leaderboard", "event strip"]),
        ],
        "components": ["gameplay hero", "mode cards", "progression track", "leaderboard", "download/platform CTA"],
        "headline_directions": ["Enter the match before the world resets.", "Build, compete, and claim your rank.", "A world that rewards mastery."],
        "microcopy": ["Play now", "Watch trailer", "Join event"],
        "avoid_words": ["business solution", "workflow automation", "corporate dashboard"],
    },
    "logistics": {
        "decision_moment": "An operator is deciding whether movement, capacity, and exceptions will become easier to control.",
        "primary_objection": "Logistics tools often hide the actual route, timing, and exception pressure.",
        "design_answer": "Show maps, ETAs, capacity, exceptions, shipment statuses, and clear escalation paths.",
        "trust_signals": ["route visibility", "ETA proof", "capacity state", "exception queue", "customer tracking"],
        "sections": [
            ("Hero", "Make movement and timing visible immediately.", ["route", "ETA", "shipment"], ["map or route panel"]),
            ("Operations proof", "Show capacity and exceptions.", ["fleet", "warehouse", "exception"], ["capacity cards", "exception queue"]),
            ("Workflow", "Explain dispatch to delivery.", ["dispatch", "track", "notify"], ["timeline"]),
            ("Customer trust", "Show tracking and support outcomes.", ["tracking", "proof", "contact"], ["tracking preview"]),
        ],
        "components": ["route map", "shipment cards", "capacity strip", "exception queue", "ETA timeline"],
        "headline_directions": ["See every route, delay, and exception before it spreads.", "Fleet movement under control.", "From warehouse pressure to delivery proof."],
        "microcopy": ["Track shipment", "Resolve delay", "Open route"],
        "avoid_words": ["generic CRM", "smarter operations", "launch path"],
    },
    "education": {
        "decision_moment": "A student, staff member, or administrator is deciding whether the system makes academic work clearer and fairer.",
        "primary_objection": "Education systems can feel bureaucratic, confusing, or disconnected from student support.",
        "design_answer": "Separate role paths, show support/status, make policies and actions plain, and use institutional trust cues.",
        "trust_signals": ["role paths", "student support", "registrar clarity", "academic workflow", "policy transparency"],
        "sections": [
            ("Hero", "Explain the academic outcome and who it serves.", ["student", "staff", "admin"], ["role cards"]),
            ("Role paths", "Make journeys clear.", ["students", "faculty", "administrators"], ["tabs/cards"]),
            ("Services or workflows", "Show real academic operations.", ["courses", "approvals", "support"], ["workflow cards"]),
            ("Support and trust", "Show contact, policy, and reporting clarity.", ["help", "policy", "reports"], ["support panel"]),
        ],
        "components": ["role cards", "calendar/status cards", "approval flow", "support panel", "reporting proof"],
        "headline_directions": ["Academic operations students and staff can actually understand.", "Clear paths for campus work.", "Less friction from request to resolution."],
        "microcopy": ["Choose your role", "Check status", "Request support"],
        "avoid_words": ["edtech cartoon", "generic SaaS", "campus magic"],
    },
    "ngo": {
        "decision_moment": "A donor or volunteer is deciding if the mission is credible and the action will create visible impact.",
        "primary_objection": "Impact claims can feel vague, manipulative, or unaccountable.",
        "design_answer": "Lead with human mission, transparent impact metrics, program proof, and direct donation/volunteer paths.",
        "trust_signals": ["impact metric", "program result", "funding transparency", "community story", "partner proof"],
        "sections": [
            ("Mission hero", "Connect problem, people, and action.", ["mission", "community", "CTA"], ["human/field image"]),
            ("Impact proof", "Make outcomes measurable.", ["metric", "program", "result"], ["impact cards"]),
            ("Stories", "Show respectful field context.", ["story", "partner", "community"], ["story modules"]),
            ("Action path", "Make donate/volunteer clear.", ["donate", "volunteer", "newsletter"], ["action cards"]),
        ],
        "components": ["mission hero", "impact metric cards", "story modules", "donation path", "volunteer CTA"],
        "headline_directions": ["Turn concern into measurable community impact.", "A mission with proof, not vague promises.", "Help where the next action is clear."],
        "microcopy": ["Donate", "Volunteer", "See impact"],
        "avoid_words": ["guilt-heavy", "vague impact", "poverty theater"],
    },
    "fashion": {
        "decision_moment": "A visitor is deciding if the brand has taste, identity, and pieces worth wearing or following.",
        "primary_objection": "Fashion pages can become generic ecommerce grids with no point of view.",
        "design_answer": "Use editorial rhythm, campaign imagery, material detail, collection structure, and concise brand voice.",
        "trust_signals": ["collection story", "material detail", "campaign visual", "fit/product detail", "brand point of view"],
        "sections": [
            ("Campaign hero", "Create identity and desire.", ["collection name", "shop/lookbook CTA"], ["full-bleed campaign image"]),
            ("Collection", "Show pieces with rhythm.", ["lookbook", "category", "product"], ["editorial grid"]),
            ("Material/detail", "Make quality tangible.", ["fabric", "silhouette", "finish"], ["detail close-ups"]),
            ("Shop or inquiry", "Give a direct buying path.", ["shop", "size", "contact"], ["product cards"]),
        ],
        "components": ["campaign hero", "lookbook grid", "product detail cards", "material close-ups", "shop CTA"],
        "headline_directions": ["A collection with a point of view.", "Silhouettes made for the season ahead.", "Wear the story, not the trend."],
        "microcopy": ["Shop collection", "View lookbook", "Explore pieces"],
        "avoid_words": ["workflow", "automation", "service package"],
    },
    "portfolio": {
        "decision_moment": "A client or hiring manager is deciding whether the work and judgment are strong enough to start a conversation.",
        "primary_objection": "Portfolios often make claims without showing real work or outcomes.",
        "design_answer": "Lead with selected work, case-study evidence, role/context, process, and direct contact.",
        "trust_signals": ["selected work", "case outcome", "client context", "process proof", "contact path"],
        "sections": [
            ("Intro", "State point of view and role clearly.", ["name", "discipline", "contact"], ["work preview"]),
            ("Selected work", "Show credible project range.", ["case study", "client", "outcome"], ["case grid"]),
            ("Process", "Explain how the work happens.", ["research", "design", "ship"], ["process strip"]),
            ("Contact", "Make collaboration easy.", ["availability", "email", "brief"], ["contact form"]),
        ],
        "components": ["case-study grid", "project metadata", "process strip", "testimonial/proof", "contact CTA"],
        "headline_directions": ["Selected work with the proof still attached.", "A portfolio built around shipped outcomes.", "Taste, systems, and results in one body of work."],
        "microcopy": ["View case study", "Start a project", "Download resume"],
        "avoid_words": ["generic agency", "sample project", "coming soon"],
    },
    "government": {
        "decision_moment": "A resident or public servant is trying to complete a task without confusion.",
        "primary_objection": "Public-service pages are often hard to navigate, inaccessible, or unclear.",
        "design_answer": "Use plain language, high contrast, service search, popular tasks, official notices, and accessible forms.",
        "trust_signals": ["official status", "service search", "accessibility", "documents", "help route"],
        "sections": [
            ("Service finder", "Let people find the task first.", ["search", "popular services", "status"], ["search module"]),
            ("Popular tasks", "Expose frequent actions.", ["permit", "application", "payment"], ["task cards"]),
            ("Announcements", "Show current public information.", ["notice", "deadline", "office"], ["status banner"]),
            ("Help and documents", "Make support and forms accessible.", ["help", "document", "contact"], ["document list"]),
        ],
        "components": ["service search", "task cards", "announcement banner", "document list", "accessibility controls"],
        "headline_directions": ["Find the public service you need.", "Clear steps for civic tasks.", "Public services without the maze."],
        "microcopy": ["Search services", "Start application", "Download form"],
        "avoid_words": ["flashy startup", "growth hack", "low contrast"],
    },
    "ai_saas": {
        "decision_moment": "A buyer is deciding whether the AI is useful, controllable, and safe enough for real work.",
        "primary_objection": "AI products often look magical but fail to show workflow control or proof.",
        "design_answer": "Show workflow before/after, agent traces, approvals, integrations, security, and measurable outcomes.",
        "trust_signals": ["agent trace", "approval control", "integration state", "audit log", "security note"],
        "sections": [
            ("Hero", "Explain the workflow transformation without magic language.", ["problem", "AI workflow", "CTA"], ["workflow preview"]),
            ("Agent proof", "Show how the AI works.", ["prompt", "result", "approval"], ["agent trace panel"]),
            ("Integrations", "Show systems it connects to.", ["Slack", "email", "CRM", "database"], ["integration grid"]),
            ("Security and control", "Address buyer risk.", ["audit", "permissions", "review"], ["security cards"]),
        ],
        "components": ["workflow before/after", "agent trace", "approval panel", "integration grid", "security proof"],
        "headline_directions": ["AI workflows your team can inspect and control.", "Automate the routine without losing oversight.", "From prompt to approved action."],
        "microcopy": ["Run demo", "Review output", "Approve action"],
        "avoid_words": ["AI magic", "orb", "robot portrait", "autonomous everything"],
    },
    "marketplace": {
        "decision_moment": "A buyer or seller is deciding whether there is enough supply, trust, and transaction clarity to participate.",
        "primary_objection": "Marketplaces can hide one side of the transaction or feel empty.",
        "design_answer": "Show buyer/seller paths, listings, filters, trust badges, reviews, and the transaction flow.",
        "trust_signals": ["verified sellers", "reviews", "listing volume", "trust/safety", "clear fees"],
        "sections": [
            ("Discovery hero", "Show what can be found and how.", ["search", "category", "location"], ["search/listing preview"]),
            ("Listings", "Make supply feel real.", ["listing", "price", "rating"], ["listing cards"]),
            ("How it works", "Clarify buyer and seller flow.", ["buyer", "seller", "transaction"], ["two-sided flow"]),
            ("Trust", "Reduce transaction anxiety.", ["verified", "review", "support"], ["trust cards"]),
        ],
        "components": ["search hero", "filter bar", "listing cards", "buyer/seller path cards", "review/trust badges"],
        "headline_directions": ["Find the right match with trust built in.", "A marketplace where both sides know the next step.", "Search, compare, and transact with confidence."],
        "microcopy": ["Search listings", "Become a seller", "Compare options"],
        "avoid_words": ["single-sided", "empty marketplace", "unclear fees"],
    },
    "energy_climate": {
        "decision_moment": "A facility or sustainability leader is deciding whether this product can reduce outage risk, demand spikes, and clean-energy uncertainty across commercial buildings.",
        "primary_objection": "Energy software can look like generic analytics, construction services, or climate marketing without proving live grid intelligence.",
        "design_answer": "Show microgrid telemetry, building load, solar and battery state, demand forecasts, outage-risk alerts, and case-study outcomes.",
        "trust_signals": ["microgrid telemetry", "battery and solar status", "demand spike forecast", "outage-risk score", "commercial building case proof"],
        "sections": [
            ("Hero", "Make grid intelligence visible immediately.", ["microgrid", "solar", "battery", "outage risk"], ["energy-grid scene", "building telemetry panel"]),
            ("Platform modules", "Explain what operators monitor and control.", ["load", "demand", "battery", "solar", "alerts"], ["module cards", "status panels"]),
            ("Case studies", "Prove value in real building contexts.", ["building portfolio", "peak demand", "resilience"], ["case-study cards", "impact metrics"]),
            ("Contact/demo", "Capture facility context and next step.", ["portfolio size", "energy assets", "risk window"], ["demo form", "qualification fields"]),
        ],
        "components": ["energy-grid hero", "microgrid status panel", "load curve chart", "battery/solar cards", "outage-risk alert", "case-study grid", "demo form"],
        "headline_directions": ["See energy risk before it becomes an outage.", "Microgrid intelligence for commercial buildings.", "Solar, batteries, demand, and outage risk in one operating view."],
        "microcopy": ["View platform", "Explore case studies", "Model outage risk", "Request energy review"],
        "avoid_words": ["construction services", "contractor", "handover", "jobsite", "CLI install", "Web3 modules", "self-hosted backend"],
    },
}


def _industry_prompt_profile(industry: str, strategy: dict[str, Any]) -> dict[str, Any]:
    extra = _INDUSTRY_PROMPT_EXTRAS.get(_clean(industry).lower()) or {}
    return {
        "industry": _clean(industry).lower() or "general_business",
        "message": strategy.get("message") or "",
        "emotional_feel": strategy.get("emotional_feel") or "",
        "visual_language": strategy.get("visual_language") or "",
        "layout_signature": strategy.get("layout_signature") or "",
        "copy_voice": strategy.get("copy_voice") or "",
        "decision_moment": extra.get("decision_moment") or "A visitor is deciding whether this product or service is credible enough to continue.",
        "primary_objection": extra.get("primary_objection") or "The page may feel generic, vague, or untrustworthy.",
        "design_answer": extra.get("design_answer") or "Show concrete proof, clear hierarchy, useful actions, and domain-specific visual language.",
        "trust_signals": extra.get("trust_signals") or ["specific proof", "clear process", "visible outcome", "direct next action"],
        "sections": extra.get("sections") or [],
        "components": extra.get("components") or [],
        "headline_directions": extra.get("headline_directions") or [],
        "microcopy": extra.get("microcopy") or [],
        "avoid_words": extra.get("avoid_words") or [],
    }


def _brand_system(product_name: str, strategy: dict[str, Any]) -> dict[str, Any]:
    industry = _clean(strategy.get("industry")).lower()
    tokens = _brand_tokens(industry)
    name = _clean(product_name) or "the product"
    return {
        "brand_name": name,
        "logo_direction": _logo_direction(industry, name),
        "tokens": tokens,
        "color_tokens": tokens,
        "typography": _typography_pairing(industry),
        "spacing_scale": {"xs": "4px", "sm": "8px", "md": "16px", "lg": "24px", "xl": "40px", "section": "72px desktop / 44px mobile"},
        "radius_system": _radius_system(industry),
        "radius": _radius_system(industry),
        "icon_style": _icon_style(industry),
        "imagery_direction": strategy.get("imagery") or "",
        "motion_style": _motion_style(industry),
        "accessibility": ["AA contrast for body text", "visible focus states", "tap targets at least 44px on mobile"],
        "do_not_render": ["internal style profile names", "raw prompt labels", "provider/debug labels"],
    }


def _brand_tokens(industry: str) -> dict[str, str]:
    palettes = {
        "developer_tools": {"bg": "#09090b", "surface": "#121216", "surface_2": "#1d1d22", "text": "#f8fafc", "muted": "#a1a1aa", "accent": "#ff8a00", "accent_2": "#22d3ee", "success": "#22c55e", "warning": "#f59e0b", "danger": "#ef4444", "border": "#2f2f37"},
        "luxury": {"bg": "#f7f1e8", "surface": "#fffaf3", "surface_2": "#14110f", "text": "#17120d", "muted": "#71675e", "accent": "#9f6b3e", "accent_2": "#2f2924", "success": "#3f6f53", "warning": "#b7791f", "danger": "#9f1239", "border": "#ded2c3"},
        "fintech": {"bg": "#f7fafc", "surface": "#ffffff", "surface_2": "#0f172a", "text": "#111827", "muted": "#64748b", "accent": "#0f766e", "accent_2": "#2563eb", "success": "#16a34a", "warning": "#d97706", "danger": "#dc2626", "border": "#dbe3ea"},
        "gaming": {"bg": "#0b0b12", "surface": "#151522", "surface_2": "#211a35", "text": "#f9fafb", "muted": "#b6b6c8", "accent": "#f43f5e", "accent_2": "#8b5cf6", "success": "#2dd4bf", "warning": "#fbbf24", "danger": "#fb7185", "border": "#34344a"},
        "energy_climate": {"bg": "#071111", "surface": "#0d1f20", "surface_2": "#102a2d", "text": "#ecfeff", "muted": "#9bb8b8", "accent": "#22d3ee", "accent_2": "#f59e0b", "success": "#22c55e", "warning": "#f97316", "danger": "#ef4444", "border": "#1f3f43"},
        "construction": {"bg": "#f4f1ea", "surface": "#ffffff", "surface_2": "#111827", "text": "#151515", "muted": "#5f6670", "accent": "#d97706", "accent_2": "#1f3a5f", "success": "#2f855a", "warning": "#f59e0b", "danger": "#b91c1c", "border": "#d8d2c6"},
        "ngo": {"bg": "#fbf8f1", "surface": "#ffffff", "surface_2": "#14342b", "text": "#1f2933", "muted": "#667085", "accent": "#0f766e", "accent_2": "#f97316", "success": "#16a34a", "warning": "#d97706", "danger": "#dc2626", "border": "#e6dfd0"},
        "fashion": {"bg": "#fbfaf7", "surface": "#ffffff", "surface_2": "#111111", "text": "#111111", "muted": "#6f6a64", "accent": "#b91c1c", "accent_2": "#111111", "success": "#47745b", "warning": "#a16207", "danger": "#be123c", "border": "#e5e0d8"},
        "government": {"bg": "#f8fafc", "surface": "#ffffff", "surface_2": "#0b2d4d", "text": "#0f172a", "muted": "#475569", "accent": "#1d4ed8", "accent_2": "#0f766e", "success": "#15803d", "warning": "#b45309", "danger": "#b91c1c", "border": "#cbd5e1"},
    }
    return palettes.get(industry) or {"bg": "#f8fafc", "surface": "#ffffff", "surface_2": "#111827", "text": "#111827", "muted": "#64748b", "accent": "#2563eb", "accent_2": "#0f766e", "success": "#16a34a", "warning": "#d97706", "danger": "#dc2626", "border": "#dbe3ea"}


def _typography_pairing(industry: str) -> dict[str, str]:
    if industry == "developer_tools":
        return {"display": "Inter or Geist Sans, heavy for product headline", "body": "Inter/Geist Sans", "mono": "JetBrains Mono or Geist Mono for commands and API proof"}
    if industry in {"luxury", "fashion"}:
        return {"display": "editorial serif or high-contrast display", "body": "clean readable sans", "mono": "not primary"}
    if industry == "government":
        return {"display": "plain high-readability sans", "body": "plain high-readability sans", "mono": "only for reference IDs"}
    return {"display": "modern readable sans", "body": "modern readable sans", "mono": "tabular/technical labels where useful"}


def _logo_direction(industry: str, product_name: str) -> str:
    if industry == "developer_tools":
        return f"wordmark for {product_name} with optional small geometric forge/module mark; never a mascot or glossy 3D logo"
    if industry == "luxury":
        return f"quiet wordmark for {product_name}; refined spacing, no loud badge"
    if industry == "government":
        return f"official, plain wordmark for {product_name}; prioritize legibility and trust"
    return f"simple readable wordmark for {product_name}; do not make logo the whole screen"


def _radius_system(industry: str) -> str:
    if industry in {"developer_tools", "government", "operational_dashboard"}:
        return "4px to 8px; cards and controls should feel precise"
    if industry == "luxury":
        return "0px to 6px; editorial, not pill-heavy"
    return "6px to 10px; no oversized decorative blobs"


def _icon_style(industry: str) -> str:
    if industry == "developer_tools":
        return "thin technical line icons, status glyphs, code/module symbols"
    if industry == "luxury":
        return "minimal marks; use icons sparingly"
    if industry == "gaming":
        return "bold game-UI glyphs tied to actions and modes"
    return "clear line icons tied to actual actions"


def _motion_style(industry: str) -> str:
    if industry == "gaming":
        return "energetic but controlled transitions for cards, media, and CTA states"
    if industry == "luxury":
        return "slow, restrained reveals; no bouncy UI"
    return "subtle feedback for hover, focus, loading, and state changes"


def _visual_reference_memory(project_root: Path, profile: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
    roots = [
        project_root / ".friday" / "design" / "references",
        project_root / ".friday" / "style-references",
        ROOT_DIR / ".friday" / "design" / "references",
    ]
    extensions = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".html", ".md", ".json"}
    assets: list[dict[str, str]] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*"))[:80]:
            if path.is_file() and path.suffix.lower() in extensions:
                try:
                    relative = str(path.relative_to(project_root))
                except ValueError:
                    relative = str(path)
                assets.append({"path": relative, "type": path.suffix.lower().lstrip("."), "role": "approved visual/style reference"})
    return {
        "available": bool(assets),
        "assets": assets[:24],
        "profile_evidence": (profile.get("evidence") or [])[:12],
        "usage_rule": "Use available references for composition, density, tone, and polish only; do not copy protected assets or render local file paths as UI copy.",
        "missing_reference_rule": "If no approved local visual references exist, rely on brand_system, taxonomy, and output_contract rather than generic SaaS defaults.",
        "industry": strategy.get("industry") or "",
    }


def _site_continuity(
    project_root: Path,
    request: str,
    product_name: str,
    profile: dict[str, Any],
    contract: dict[str, Any],
    strategy: dict[str, Any],
    brand_system: dict[str, Any],
    artifact_scope: str,
    page_map: list[dict[str, str]],
) -> dict[str, Any]:
    site_path = project_root / ".friday" / "design" / "site-design-system.json"
    existing: dict[str, Any] = {}
    if site_path.exists():
        try:
            loaded = json.loads(site_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except Exception:
            existing = {}
    page_label = contract.get("page_label") or _page_label_from_scope(artifact_scope) or "home"
    generated = {
        "version": "site_design_system_v1",
        "product_name": _clean(product_name),
        "surface": strategy.get("surface") or contract.get("surface") or "",
        "industry": strategy.get("industry") or "",
        "brand_system": brand_system,
        "navigation": _navigation_labels(request, strategy, page_map),
        "global_visual_language": {
            "direction": strategy.get("direction") or "",
            "layout_signature": strategy.get("layout_signature") or "",
            "palette": strategy.get("palette") or "",
            "typography": strategy.get("typography") or "",
            "imagery": strategy.get("imagery") or "",
        },
        "shared_components": _component_inventory(request, contract, strategy),
        "style_profile_id": profile.get("id") or "",
        "pages": page_map,
    }
    site_system = existing if existing.get("product_name") == _clean(product_name) and existing.get("brand_system") else generated
    return {
        "page_label": page_label,
        "artifact_scope": _clean_artifact_scope(artifact_scope),
        "site_design_system_path": str(site_path),
        "site_design_system": site_system,
        "rules": [
            "Use this shared site design system for every page in the same website.",
            "Do not let per-page Stitch generations drift in typography, palette, navigation, button style, or brand voice.",
            "Each page may change layout emphasis, but must preserve the global brand system and navigation model.",
        ],
    }


def _inspiration_references(strategy: dict[str, Any], contract: dict[str, Any], request: str) -> list[dict[str, Any]]:
    industry = _clean(strategy.get("industry")).lower()
    surface = _clean(strategy.get("surface") or contract.get("surface")).lower()
    common = [
        {
            "name": "Evidence-first product page",
            "why": "Visitors should see proof, workflow, and CTA before decorative storytelling.",
            "must_include": ["specific hero", "proof objects", "clear CTA"],
            "avoid": ["stock-like hero", "empty gradient panels", "generic feature cards"],
        },
        {
            "name": "Production interface handoff",
            "why": "The design must convert into real components, not a static poster.",
            "must_include": ["semantic sections", "responsive grid", "usable controls"],
            "avoid": ["oversized type", "absolute-positioned collage", "unreadable microcopy"],
        },
    ]
    by_industry: dict[str, list[dict[str, Any]]] = {
        "developer_tools": [
            {
                "name": "Docs-first developer landing page",
                "why": "Developer trust comes from quick comprehension, commands, API examples, and architecture proof.",
                "must_include": ["quickstart command", "schema/API proof", "GitHub/docs CTA", "deployment/status signal"],
                "avoid": ["stock people", "generic AI gradients", "marketing-only claims without code proof"],
            },
            {
                "name": "Open-source infrastructure product page",
                "why": "Self-hosting, control, extensibility, and community credibility need to be visible.",
                "must_include": ["self-hosting path", "module/plugin model", "security/control note"],
                "avoid": ["closed black-box SaaS feel", "pricing before product comprehension"],
            },
            {
                "name": "Product-console proof scene",
                "why": "A realistic builder surface makes abstract backend claims tangible.",
                "must_include": ["schema/table object", "API route generated", "agent/workflow status"],
                "avoid": ["fake analytics-only dashboard", "decorative terminal text"],
            },
        ],
        "luxury": [
            {
                "name": "Quiet editorial luxury",
                "why": "Premium brands need restraint, materiality, white space, and concierge confidence.",
                "must_include": ["material detail", "craft proof", "concierge CTA"],
                "avoid": ["coupon energy", "crowded badges", "loud gradients"],
            }
        ],
        "fintech": [
            {
                "name": "Trust-led financial product",
                "why": "Money products need clarity, risk control, status, and compliance cues.",
                "must_include": ["security proof", "transaction/status objects", "plain-language CTA"],
                "avoid": ["casino visuals", "unclear returns language", "neon clutter"],
            }
        ],
        "gaming": [
            {
                "name": "Immersive game world interface",
                "why": "Gaming products need energy, identity, progression, and community hooks.",
                "must_include": ["progression signal", "event/community CTA", "visual world cue"],
                "avoid": ["corporate SaaS layout", "flat spreadsheet feel"],
            }
        ],
        "energy_climate": [
            {
                "name": "Climate infrastructure command page",
                "why": "Energy products need live telemetry, asset state, demand risk, and resilience proof before claims feel real.",
                "must_include": ["microgrid status", "solar/battery state", "demand or outage risk", "building portfolio proof"],
                "avoid": ["construction-service copy", "developer-tool terminal proof", "generic analytics cards"],
            },
            {
                "name": "Energy-grid visual story",
                "why": "A grid/software product should make electricity movement, building demand, and control decisions visible.",
                "must_include": ["grid lines or topology", "load curve", "alerts", "facility/building context"],
                "avoid": ["beige consulting page", "stock contractor imagery", "Web3/API language"],
            },
        ],
        "construction": [
            {
                "name": "Built-environment credibility",
                "why": "Construction companies need scale, safety, project proof, and material confidence.",
                "must_include": ["project photography direction", "safety/quality proof", "bid/contact path"],
                "avoid": ["generic consulting SaaS hero", "abstract startup dashboard"],
            }
        ],
        "education": [
            {
                "name": "Campus operations clarity",
                "why": "Education products need accessible hierarchy, policy clarity, and stakeholder trust.",
                "must_include": ["student/admin pathways", "status or support proof", "plain navigation"],
                "avoid": ["edtech cartoon cliches", "unclear admin actions"],
            }
        ],
        "ngo": [
            {
                "name": "Impact and trust storytelling",
                "why": "NGO pages must connect mission, proof, and donation/action paths honestly.",
                "must_include": ["impact metric", "community story", "donate/volunteer CTA"],
                "avoid": ["poverty theater", "vague impact claims"],
            }
        ],
        "marketplace": [
            {
                "name": "Two-sided trust marketplace",
                "why": "Marketplaces must show supply, demand, trust, discovery, and conversion.",
                "must_include": ["buyer/seller paths", "listing preview", "trust/safety signal"],
                "avoid": ["single-sided brochure", "unclear transaction model"],
            }
        ],
    }
    surface_refs: list[dict[str, Any]] = []
    if surface == "operational_dashboard":
        surface_refs.append(
            {
                "name": "Dense operator cockpit",
                "why": "Repeated daily use needs scanability, tables, filters, status colors, and fast action paths.",
                "must_include": ["navigation", "metrics", "queue/table", "detail/action panel"],
                "avoid": ["landing-page hero", "decorative cards with no workflow"],
            }
        )
    return _dedupe([*(by_industry.get(industry) or []), *surface_refs, *common])[:5]


def _content_model(
    request: str,
    product_name: str,
    contract: dict[str, Any],
    strategy: dict[str, Any],
    keywords: list[str],
    page_map: list[dict[str, str]],
) -> dict[str, Any]:
    industry = _clean(strategy.get("industry")).lower()
    surface = _clean(strategy.get("surface") or contract.get("surface")).lower()
    return {
        "brand": _clean(product_name),
        "page_label": contract.get("page_label") or "home",
        "required_sections": contract.get("required_sections") or [],
        "navigation": _navigation_labels(request, strategy, page_map),
        "primary_ctas": _cta_labels(industry, surface),
        "proof_objects": _proof_objects(industry, surface),
        "domain_terms": keywords[:18],
        "page_map": page_map,
        "copy_guidance": _copy_guidance(industry, surface),
    }


def _creative_brief(request: str, product_name: str, contract: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
    name = _clean(product_name) or "the product"
    industry = _clean(strategy.get("industry")).lower()
    surface = _clean(strategy.get("surface") or contract.get("surface")).lower()
    profile = _industry_prompt_profile(industry, strategy)
    if industry == "developer_tools":
        return {
            "one_sentence": f"{name} should feel like infrastructure that a serious builder can inspect, run, and own.",
            "decision_moment": "A technical founder is deciding whether this can replace weeks of backend setup without locking them into a black box.",
            "primary_objection": "No-code tools feel limiting, opaque, or toy-like.",
            "design_answer": "Show code-level proof, self-hosting control, generated APIs, module status, and quickstart speed in the first scroll.",
            "trust_signals": ["GitHub/open-source cue", "self-hosting cue", "security/control note", "docs/CLI path", "working API/schema proof"],
        }
    if surface == "operational_dashboard":
        return {
            "one_sentence": f"{name} should feel like a real command surface that operators can use all day.",
            "decision_moment": "An operator needs to know what is urgent, who owns it, and what action is safe to take next.",
            "primary_objection": "Dashboards often look impressive but fail to support repeated real work.",
            "design_answer": "Prioritize tables, filters, ownership, status, risk, and action affordances over decorative hero copy.",
            "trust_signals": ["live queue", "status aging", "owner assignment", "audit/proof trail", "clear next actions"],
        }
    if industry == "construction":
        return {
            "one_sentence": f"{name} should feel proven, physical, safe, and capable of handling large real-world work.",
            "decision_moment": "A project owner or procurement lead is checking if this company can deliver safely and reliably.",
            "primary_objection": "Construction sites often look generic online and do not prove delivery credibility.",
            "design_answer": "Use project scale, materials, safety proof, delivery process, and regional capability as visible evidence.",
            "trust_signals": ["project portfolio", "safety commitments", "delivery method", "sector expertise", "contact path"],
        }
    if profile.get("sections"):
        return {
            "one_sentence": f"{name} should feel like {strategy.get('direction') or 'a distinctive, credible product experience'}.",
            "decision_moment": profile["decision_moment"],
            "primary_objection": profile["primary_objection"],
            "design_answer": profile["design_answer"],
            "trust_signals": profile["trust_signals"],
        }
    return {
        "one_sentence": f"{name} should communicate what it does, why it is credible, and what the visitor should do next.",
        "decision_moment": "A visitor is deciding whether this is relevant and trustworthy enough to continue.",
        "primary_objection": "The page may feel generic, vague, or visually interchangeable.",
        "design_answer": "Use specific domain proof, clear hierarchy, concrete nouns, and one obvious next action.",
        "trust_signals": ["specific offer", "process proof", "outcome metric", "customer or use-case proof", "contact path"],
    }


def _composition_spec(request: str, product_name: str, contract: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
    industry = _clean(strategy.get("industry")).lower()
    surface = _clean(strategy.get("surface") or contract.get("surface")).lower()
    name = _clean(product_name) or "the product"
    composition = strategy.get("composition") if isinstance(strategy.get("composition"), dict) else {}
    primary = composition.get("primary") if isinstance(composition.get("primary"), dict) else {}
    allowed = [item for item in (composition.get("allowed_archetypes") or []) if isinstance(item, dict)]
    primary_id = _clean(primary.get("id") or "centered_statement")
    primary_name = _clean(primary.get("name") or primary_id.replace("_", " ").title())
    first_viewport = [
        f"Use the {primary_name} composition archetype: {primary.get('first_viewport') or 'make the first viewport match the domain and user decision.'}",
        f"Brand and navigation must identify {name} clearly without visible internal profile labels.",
        "The first viewport must expose the next meaningful section; do not end at a blank hero.",
        "Every visible proof object must be domain-specific, not a decorative placeholder.",
    ]
    if primary_id == "docs_terminal":
        first_viewport.extend(
            [
                "For developer tools, show a quickstart command, docs/GitHub path, API/schema/SDK proof, and deployment/module state above the fold.",
                "Do not make the only proof a generic product card; the technical artifact must be inspectable.",
            ]
        )
    elif primary_id == "architecture_diagram":
        first_viewport.append("Use a meaningful architecture diagram with labeled modules, flows, trust boundaries, and deployment path.")
    elif primary_id == "full_bleed_media":
        first_viewport.append("Use real-feeling media, image, material, site, or scene as the hero background with text anchored over it, not trapped in a card.")
    elif primary_id == "immersive_scene":
        first_viewport.append("Use an immersive visual or interactive/gameplay scene as the first signal, with concise copy and action buttons over or beside it.")
    elif primary_id == "dashboard_shell":
        first_viewport.extend(
            [
                "Application shell must include navigation, metrics/status, a primary queue/table/board, detail context, and real action controls.",
                "Do not render a landing-page hero for an operational dashboard.",
            ]
        )
    elif primary_id == "search_first":
        first_viewport.append("Lead with search/finder, category or filter controls, listing previews, and buyer/seller or trust paths.")
    elif primary_id == "map_or_route":
        first_viewport.append("Lead with location, route, ETA, territory, or dispatch state; the map/route object is the decision surface.")
    elif primary_id == "service_pathways":
        first_viewport.append("Lead with role/service paths, task cards, help/search affordance, and a trustworthy next action.")
    elif primary_id == "editorial_asymmetric":
        first_viewport.append("Use asymmetric image/copy/proof placement like an editorial spread; avoid equal card grids in the first viewport.")
    elif primary_id == "workflow_stage":
        first_viewport.append("Show the workflow states as evidence: input/problem, action/automation, human approval, and result/proof.")

    layout_depth = [
        "Generate multiple sections with different rhythm; do not repeat the same card grid after the hero.",
        "Variant explorations must change composition archetype or first-viewport structure, not just palette or copy.",
        "Normalize exaggerated Stitch scale during implementation so headings, sections, and buttons fit real desktop and mobile viewports.",
    ]
    if surface == "operational_dashboard":
        layout_depth = [
            "Use compact application density; the screen should support scanning and action.",
            "Include loading, empty, risk, approval, and audit states as visible examples where possible.",
            "Preserve workflow continuity from nav to queue to detail to action.",
        ]
    elif surface == "marketing_website":
        layout_depth.extend(
            [
                "Use 5 to 7 meaningful sections in a single landing page or page-specific depth for multi-page sites.",
                "Every section should have a job: explain, prove, compare, qualify, transact, or convert.",
            ]
        )

    return {
        "archetype": primary_id,
        "archetype_name": primary_name,
        "archetype_rationale": primary.get("why") or "",
        "allowed_archetypes": [
            {
                "id": item.get("id") or "",
                "name": item.get("name") or "",
                "why": item.get("why") or "",
                "first_viewport": item.get("first_viewport") or "",
                "avoid": item.get("avoid") or "",
            }
            for item in allowed[:5]
        ],
        "composition_rules": composition.get("rules") or [],
        "first_viewport": [
            *first_viewport,
        ],
        "layout_depth": layout_depth,
        "visual_hierarchy": "Composition comes before styling. H1 should be strong but not viewport-breaking; proof must be visible, inspectable, and domain-specific.",
        "responsive_notes": "On mobile, maintain readable type, no overlapping text, and clear CTA order.",
        "variant_policy": "Ask Stitch for compositionally different variants; reject same split-hero/card rhythm unless it is explicitly selected and well justified.",
    }


def _experience_mode_spec(request: str, product_name: str, contract: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
    experience = strategy.get("experience") if isinstance(strategy.get("experience"), dict) else {}
    primary = experience.get("primary") if isinstance(experience.get("primary"), dict) else {}
    allowed = [item for item in (experience.get("allowed_modes") or []) if isinstance(item, dict)]
    mode_id = _clean(primary.get("id") or "static_polished")
    mode_name = _clean(primary.get("name") or mode_id.replace("_", " ").title())
    libraries = [str(item) for item in (primary.get("libraries") or []) if _clean(item)]
    rules = [str(item) for item in (experience.get("rules") or []) if _clean(item)]
    mode_rules = [str(item) for item in (primary.get("rules") or []) if _clean(item)]
    verification = [str(item) for item in (primary.get("verification") or []) if _clean(item)]
    implementation = [str(item) for item in (primary.get("implementation") or []) if _clean(item)]
    rejection_rules = [str(item) for item in (primary.get("rejection_rules") or []) if _clean(item)]
    if mode_id in {"interactive_3d", "immersive_scene", "game_like"}:
        implementation.extend(
            [
                "Use a visible canvas/WebGL or scene layer only when the selected mode requires it.",
                "Provide a static fallback poster or semantic content path for no-WebGL and reduced-motion users.",
                "Keep the primary scene full-bleed or unframed; do not bury it inside a decorative card.",
            ]
        )
    if mode_id in {"cinematic_scroll", "parallax_story"}:
        implementation.extend(
            [
                "Use scroll progress to reveal narrative, proof, or product state rather than decorative movement.",
                "Provide prefers-reduced-motion behavior that keeps all content readable without animation.",
            ]
        )
    if mode_id in {"product_demo_motion", "data_viz_motion"}:
        implementation.append("Tie every animated state to a real product, workflow, chart, map, command, or action.")
    return {
        "mode": mode_id,
        "mode_name": mode_name,
        "intent": primary.get("intent") or "",
        "when_to_use": primary.get("when_to_use") or "",
        "allowed_modes": [
            {
                "id": item.get("id") or "",
                "name": item.get("name") or "",
                "intent": item.get("intent") or "",
                "when_to_use": item.get("when_to_use") or "",
                "libraries": item.get("libraries") or [],
            }
            for item in allowed[:5]
        ],
        "recommended_libraries": libraries,
        "implementation_notes": _dedupe([*implementation])[:12],
        "motion_rules": _dedupe([*mode_rules, *rules])[:12],
        "verification_requirements": _dedupe(verification)[:10],
        "rejection_rules": _dedupe(rejection_rules)[:10],
        "requires_canvas_check": mode_id in {"interactive_3d", "immersive_scene", "game_like"},
        "requires_reduced_motion": bool(libraries) or mode_id in {"cinematic_scroll", "parallax_story", "interactive_3d", "immersive_scene", "game_like", "product_demo_motion"},
        "performance_budget": _experience_performance_budget(mode_id),
        "fallback_requirement": _experience_fallback_requirement(mode_id),
    }


def _experience_performance_budget(mode_id: str) -> dict[str, Any]:
    if mode_id in {"interactive_3d", "immersive_scene", "game_like"}:
        return {
            "initial_js": "keep immersive dependencies justified; lazy-load non-critical scene assets when possible",
            "frame_rate": "target smooth interaction on desktop and acceptable mobile fallback",
            "asset_rule": "compress textures/media and avoid unbounded model sizes",
        }
    if mode_id in {"cinematic_scroll", "parallax_story"}:
        return {
            "animation_rule": "prefer transforms/opacity and avoid layout thrash",
            "scroll_rule": "do not block normal scroll or keyboard navigation",
            "asset_rule": "optimize all large media",
        }
    return {"rule": "prioritize Core Web Vitals, readable layout, and fast interaction feedback"}


def _experience_fallback_requirement(mode_id: str) -> str:
    if mode_id in {"interactive_3d", "immersive_scene", "game_like"}:
        return "Must include no-WebGL/static fallback and prefers-reduced-motion fallback."
    if mode_id in {"cinematic_scroll", "parallax_story", "product_demo_motion"}:
        return "Must include prefers-reduced-motion fallback that preserves all content and actions."
    return "Fallback is normal responsive semantic content."


def _section_blueprint(
    request: str,
    product_name: str,
    contract: dict[str, Any],
    strategy: dict[str, Any],
    keywords: list[str],
    page_map: list[dict[str, str]],
) -> list[dict[str, Any]]:
    industry = _clean(strategy.get("industry")).lower()
    surface = _clean(strategy.get("surface") or contract.get("surface")).lower()
    name = _clean(product_name) or "the product"
    if industry == "developer_tools":
        return [
            {
                "section": "Header and hero",
                "purpose": "Explain the product in one scan and show builder-grade proof immediately.",
                "must_show": ["technical H1", "short product explanation", "Start building CTA", "View GitHub CTA", "CLI command"],
                "visual_objects": ["schema/API proof panel", "deployment status", "module status chip"],
            },
            {
                "section": "Builder proof strip",
                "purpose": "Make the promises concrete before longer storytelling.",
                "must_show": ["Self-hosted", "Open source", "Realtime APIs", "AI workflows", "Web3 modules"],
                "visual_objects": ["status badges", "mini cards", "check indicators"],
            },
            {
                "section": "Backend capabilities",
                "purpose": "Explain what builders can create without burying them in vague platform language.",
                "must_show": ["auth", "database schema", "API routes", "agent workflows", "plugin marketplace"],
                "visual_objects": ["capability grid with code or config fragments"],
            },
            {
                "section": "How it works",
                "purpose": "Show a credible path from project creation to deployed API.",
                "must_show": ["define schema", "generate route", "attach agent/module", "deploy/self-host"],
                "visual_objects": ["numbered flow", "CLI/code block", "architecture diagram"],
            },
            {
                "section": "Pricing or deployment path",
                "purpose": "Clarify open-source/self-hosting and any managed or enterprise path without overclaiming.",
                "must_show": ["Open Source", "Pro or managed", "Enterprise/contact"],
                "visual_objects": ["pricing cards or deployment option cards"],
            },
            {
                "section": "Final CTA",
                "purpose": "Give builders a direct next action.",
                "must_show": ["Start building", "Read docs", "View GitHub"],
                "visual_objects": ["command snippet", "docs/GitHub links"],
            },
        ]
    if surface == "operational_dashboard":
        domain = _fallback_domain(request)
        return [
            {
                "section": "Shell and metrics",
                "purpose": "Orient the operator and show the current state.",
                "must_show": domain.get("nav", [])[:6] + [label for label, _value in domain.get("metrics", [])],
                "visual_objects": ["sidebar or tab nav", "metric cards", "status chips"],
            },
            {
                "section": "Work queue",
                "purpose": "Show real work items and actions.",
                "must_show": ["priority", "owner", "status", "next action", "risk"],
                "visual_objects": ["table", "filters", "row actions"],
            },
            {
                "section": "Inspector panel",
                "purpose": "Let the operator understand and act on a selected item.",
                "must_show": ["context", "blockers", "audit proof", "approval controls"],
                "visual_objects": ["detail panel", "timeline", "buttons"],
            },
        ]
    profile = _industry_prompt_profile(industry, strategy)
    if profile.get("sections"):
        return [
            {"section": section, "purpose": purpose, "must_show": list(must_show), "visual_objects": list(visual_objects)}
            for section, purpose, must_show, visual_objects in profile["sections"]
        ]
    labels = [page["label"] for page in page_map] if page_map else []
    return [
        {
            "section": "Hero",
            "purpose": "Make the brand, offer, and next action unmistakable.",
            "must_show": [name, "specific H1", "supporting copy", "primary CTA", "domain visual"],
            "visual_objects": ["brand-led hero", "proof image or object", "CTA group"],
        },
        {
            "section": "Proof or trust",
            "purpose": "Show why the visitor should believe the claim.",
            "must_show": ["result metric", "client/use case", "process proof"],
            "visual_objects": ["proof cards", "logos or case snippets", "metric strip"],
        },
        {
            "section": "Offer or features",
            "purpose": "Explain the concrete service/product modules.",
            "must_show": keywords[:6] or labels or ["capabilities", "process", "outcomes"],
            "visual_objects": ["feature grid", "service cards", "comparison rows"],
        },
        {
            "section": "Process and CTA",
            "purpose": "Show what happens after the user acts.",
            "must_show": ["step 1", "step 2", "step 3", "contact or signup action"],
            "visual_objects": ["process timeline", "form or CTA band"],
        },
    ]


def _copy_bank(
    request: str,
    product_name: str,
    contract: dict[str, Any],
    strategy: dict[str, Any],
    keywords: list[str],
) -> dict[str, Any]:
    name = _clean(product_name) or "the product"
    industry = _clean(strategy.get("industry")).lower()
    surface = _clean(strategy.get("surface") or contract.get("surface")).lower()
    profile = _industry_prompt_profile(industry, strategy)
    if industry == "developer_tools":
        return {
            "headline_directions": [
                f"Build the backend your AI app needs without giving up control.",
                f"Forge auth, APIs, agents, and Web3 modules in one self-hosted backend.",
                f"No-code backend speed. Code-level ownership.",
            ],
            "subhead_direction": f"{name} should explain self-hosted backend creation with auth, databases, APIs, AI workflows, plugin modules, and Web3 support in plain technical language.",
            "microcopy_examples": ["GET /v1/agents/process", "Schema builder", "Deployment active", "Base chain module active", "CLI install"],
            "words_to_use": ["self-hosted", "open-source", "auth", "database", "API routes", "AI workflows", "Web3 modules", "plugins", "docs"],
            "words_to_avoid": ["seamless", "revolutionary", "unlock potential", "all-in-one solution", "smarter operations"],
        }
    if surface == "operational_dashboard":
        domain = _fallback_domain(request)
        return {
            "headline_directions": [f"{name}", domain.get("eyebrow") or "Operations command center"],
            "subhead_direction": domain.get("summary") or "",
            "microcopy_examples": ["Review queue", "Assign owner", "Resolve blocker", "Open evidence", "Approve action"],
            "words_to_use": ["queue", "owner", "status", "risk", "approval", "audit", "next action"],
            "words_to_avoid": ["launch path", "coming soon", "placeholder", "sample dashboard"],
        }
    if profile.get("headline_directions"):
        return {
            "headline_directions": profile.get("headline_directions") or [],
            "subhead_direction": f"{name} should communicate {strategy.get('message') or 'the product value'} in a {strategy.get('copy_voice') or 'specific'} voice.",
            "microcopy_examples": profile.get("microcopy") or _cta_labels(industry, surface),
            "words_to_use": _dedupe([*(strategy.get("positive_terms") or []), *keywords[:12], *(profile.get("trust_signals") or [])])[:16],
            "words_to_avoid": _dedupe([*(profile.get("avoid_words") or []), "Home 1", "Service 1", "lorem ipsum", "smarter operations"])[:16],
        }
    return {
        "headline_directions": [
            f"{name} should lead with a specific value proposition, not the page label.",
            "Use a headline a real founder or business owner would actually publish.",
        ],
        "subhead_direction": "Use one concise paragraph that says who it serves, what it does, and why it is credible.",
        "microcopy_examples": _cta_labels(industry, surface),
        "words_to_use": keywords[:12],
        "words_to_avoid": ["Home 1", "Service 1", "clear four-page website", "independent service studio", "lorem ipsum"],
    }


def _component_inventory(request: str, contract: dict[str, Any], strategy: dict[str, Any]) -> list[str]:
    industry = _clean(strategy.get("industry")).lower()
    surface = _clean(strategy.get("surface") or contract.get("surface")).lower()
    experience = strategy.get("experience") if isinstance(strategy.get("experience"), dict) else {}
    primary = experience.get("primary") if isinstance(experience.get("primary"), dict) else {}
    mode_id = _clean(primary.get("id")).lower()
    mode_components: list[str] = []
    if mode_id in {"interactive_3d", "immersive_scene", "game_like"}:
        mode_components.extend(["full-bleed scene/canvas surface", "scene fallback poster/content", "reduced-motion controls"])
    elif mode_id in {"cinematic_scroll", "parallax_story"}:
        mode_components.extend(["scroll story sections", "parallax/media layers", "reduced-motion static section flow"])
    elif mode_id == "product_demo_motion":
        mode_components.extend(["animated product state panel", "before/action/result sequence", "pause/reduced-motion path"])
    elif mode_id == "data_viz_motion":
        mode_components.extend(["chart/map/timeline surface", "legend and labels", "data filter controls"])
    if industry == "developer_tools":
        return _dedupe([
            *mode_components,
            "global nav with GitHub/docs/build actions",
            "hero CTA group",
            "CLI command block with copy affordance",
            "schema table or object editor",
            "API route generated card",
            "module/plugin status cards",
            "architecture or workflow diagram",
            "pricing/deployment cards",
            "footer with docs, status, privacy, terms",
        ])
    if surface == "operational_dashboard":
        return _dedupe([
            *mode_components,
            "application shell",
            "sidebar or tab navigation",
            "metric strip",
            "filter/search controls",
            "work queue table",
            "detail inspector",
            "status chips",
            "action buttons",
            "approval/audit timeline",
        ])
    profile = _industry_prompt_profile(industry, strategy)
    if profile.get("components"):
        return _dedupe([*mode_components, *list(profile["components"])])
    return _dedupe([
        *mode_components,
        "global navigation",
        "brand hero",
        "proof band",
        "feature/service cards",
        "process timeline",
        "testimonial or case proof",
        "contact/signup CTA",
        "footer",
    ])


def _variant_briefs(strategy: dict[str, Any], contract: dict[str, Any]) -> list[dict[str, str]]:
    surface = _clean(strategy.get("surface") or contract.get("surface")).lower()
    variants = list(strategy.get("variant_directions") or [])[:3]
    composition = strategy.get("composition") if isinstance(strategy.get("composition"), dict) else {}
    archetypes = [item for item in (composition.get("allowed_archetypes") or []) if isinstance(item, dict)]
    experience = strategy.get("experience") if isinstance(strategy.get("experience"), dict) else {}
    modes = [item for item in (experience.get("allowed_modes") or []) if isinstance(item, dict)]
    if not archetypes:
        archetypes = [{"name": "Domain-specific composition", "id": "domain_specific"}]
    if not modes:
        modes = [{"name": "Static Polished", "id": "static_polished"}]
    return [
        {
            "variant": f"Variant {index}",
            "direction": direction,
            "must_change": (
                f"Use or reinterpret the {archetypes[(index - 1) % len(archetypes)].get('name') or archetypes[(index - 1) % len(archetypes)].get('id')} "
                f"composition archetype with the {modes[(index - 1) % len(modes)].get('name') or modes[(index - 1) % len(modes)].get('id')} experience mode. "
                "Change first-viewport structure, motion/interaction strategy, proof object placement, and section emphasis. Do not only change colors."
            ),
            "evaluation_focus": "Will this be credible, usable, distinctive, and implementable in production?",
            "density": "compact product density" if surface in {"marketing_website", "operational_dashboard"} else "balanced useful density",
        }
        for index, direction in enumerate(variants, start=1)
    ]


def _stitch_output_contract(contract: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
    surface = _clean(strategy.get("surface") or contract.get("surface")).lower()
    experience = strategy.get("experience") if isinstance(strategy.get("experience"), dict) else {}
    primary = experience.get("primary") if isinstance(experience.get("primary"), dict) else {}
    mode_id = _clean(primary.get("id") or "static_polished")
    rejection_if = [
        "the first viewport is mostly blank space",
        "hero text is clipped or too large for the viewport",
        "copy contains numbered artifacts like Home 1 or Service 2",
        "layout looks like a generic SaaS scaffold unrelated to the industry",
        "all variants reuse the same left-text/right-card hero structure without a composition-specific reason",
        "design cannot be implemented without a giant one-file blob",
    ]
    if mode_id in {"interactive_3d", "immersive_scene", "game_like"}:
        rejection_if.extend(
            [
                "the requested 3D/canvas/immersive scene is missing, blank, tiny, hidden, or only decorative",
                "there is no static fallback for no-WebGL or reduced-motion users",
            ]
        )
    if mode_id in {"cinematic_scroll", "parallax_story", "product_demo_motion"}:
        rejection_if.append("motion is decorative only, blocks reading, or lacks a prefers-reduced-motion fallback")
    return {
        "must_return": [
            "a complete desktop screen/page, not a logo or isolated component",
            "semantic sections with readable visible copy",
            "responsive structure that can be converted to Next.js components",
            "all visible buttons and links named as real actions",
            "experience-mode evidence: canvas/scene, scroll behavior, product state transition, or a clear static-polished reason",
        ],
        "minimum_depth": "5 meaningful sections for a landing/website page" if surface == "marketing_website" else "navigation, metrics, work area, details, actions",
        "rejection_if": _dedupe(rejection_if),
    }


def _navigation_labels(request: str, strategy: dict[str, Any], page_map: list[dict[str, str]]) -> list[str]:
    if page_map and len(page_map) > 1:
        return [page["label"] for page in page_map if page.get("label")]
    industry = _clean(strategy.get("industry")).lower()
    surface = _clean(strategy.get("surface")).lower()
    if industry == "developer_tools":
        return ["Product", "AI + Web3", "Marketplace", "Self-hosting", "Docs"]
    if surface == "operational_dashboard":
        return (_fallback_domain(request).get("nav") or ["Overview", "Queue", "Approvals", "Proof"])[:6]
    if industry == "luxury":
        return ["Atelier", "Collections", "Process", "Concierge"]
    if industry == "energy_climate":
        return ["Home", "Platform", "Case Studies", "Contact"]
    if industry == "construction":
        return ["Projects", "Capabilities", "Safety", "Contact"]
    return ["Home", "About", "Services", "Contact"]


def _cta_labels(industry: str, surface: str) -> list[str]:
    if industry == "developer_tools":
        return ["Start building", "View GitHub", "Read docs"]
    if surface == "operational_dashboard":
        return ["Open workspace", "Review queue", "Create action"]
    if industry == "luxury":
        return ["Request concierge access", "Explore collection"]
    if industry == "energy_climate":
        return ["View platform", "Explore case studies", "Request energy review"]
    if industry == "construction":
        return ["Discuss a project", "View capabilities"]
    if industry == "ngo":
        return ["Donate", "Volunteer", "See impact"]
    return ["Start inquiry", "See services"]


def _proof_objects(industry: str, surface: str) -> list[str]:
    if industry == "developer_tools":
        return ["schema builder", "generated API route", "agent workflow status", "Web3 module", "deployment region", "CLI install command"]
    if surface == "operational_dashboard":
        return ["live queue", "SLA risk", "owner status", "audit trail", "approval action"]
    if industry == "energy_climate":
        return ["microgrid telemetry", "battery state", "solar production", "demand spike forecast", "outage-risk score", "building portfolio proof"]
    if industry == "construction":
        return ["completed project", "safety record", "schedule certainty", "delivery method", "regional capability"]
    if industry == "fintech":
        return ["security posture", "transaction status", "audit trail", "risk control"]
    if industry == "ngo":
        return ["impact metric", "program result", "donation use", "community partner"]
    return ["client proof", "process step", "result metric", "response promise"]


def _copy_guidance(industry: str, surface: str) -> list[str]:
    guidance = [
        "Use concrete nouns from the project domain, not vague words like smarter, seamless, or solutions by themselves.",
        "Make every claim attach to a feature, workflow, proof object, or CTA.",
        "Avoid provider artifacts, route labels, and numbered labels as visible marketing copy.",
    ]
    if industry == "developer_tools":
        guidance.extend(
            [
                "Write for builders: mention control, self-hosting, auth, database, APIs, agents, modules, and docs only when relevant.",
                "Prefer crisp technical proof over lifestyle language.",
            ]
        )
    if industry == "energy_climate":
        guidance.extend(
            [
                "Write for facility, energy, and sustainability operators: use microgrid, solar, battery, load, demand, outage, resilience, building portfolio, telemetry, and risk terms.",
                "Never use construction-company phrases like construction services, contractor, project handover, jobsite, crane, or concrete unless the user explicitly asked for construction.",
                "Never use developer-tool copy like CLI install, API routes, Web3 modules, or self-hosted backend unless the user explicitly asked for a developer product.",
            ]
        )
    if surface == "operational_dashboard":
        guidance.append("Use operator language: queue, owner, risk, status, approval, audit, next action.")
    return guidance


def _code_context(project_root: Path, stack: dict[str, Any]) -> dict[str, Any]:
    scripts: dict[str, str] = {}
    dependencies: list[str] = []
    dev_dependencies: list[str] = []
    package_path = project_root / "package.json"
    package_name = ""
    if package_path.exists():
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
            if isinstance(package, dict):
                package_name = _clean(package.get("name"))
                scripts = {str(key): str(value) for key, value in (package.get("scripts") or {}).items() if isinstance(key, str)}
                dependencies = sorted(str(key) for key in (package.get("dependencies") or {}).keys())[:24]
                dev_dependencies = sorted(str(key) for key in (package.get("devDependencies") or {}).keys())[:24]
        except Exception:
            scripts = {}
    return {
        "project_root": str(project_root),
        "package_name": package_name,
        "stack": stack or {},
        "package_manager": _package_manager(project_root),
        "scripts": {key: scripts[key] for key in sorted(scripts)[:12]},
        "dependencies": dependencies,
        "dev_dependencies": dev_dependencies,
        "existing_paths": _existing_relative_paths(
            project_root,
            [
                "src/app",
                "src/app/page.tsx",
                "src/app/layout.tsx",
                "src/components",
                "src/components/ui",
                "src/components/layout",
                "src/services",
                "src/store",
                "src/hooks",
                "src/lib",
                "src/types",
                "components.json",
                "tailwind.config.ts",
                "vitest.config.ts",
                "next.config.mjs",
            ],
        ),
        "implementation_warning": "Use this as context for feasibility; do not render file paths or package metadata as visible UI copy.",
    }


def _package_manager(project_root: Path) -> str:
    if (project_root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (project_root / "yarn.lock").exists():
        return "yarn"
    if (project_root / "package-lock.json").exists():
        return "npm"
    if (project_root / "bun.lockb").exists() or (project_root / "bun.lock").exists():
        return "bun"
    return ""


def _existing_relative_paths(project_root: Path, candidates: list[str]) -> list[str]:
    existing: list[str] = []
    for relative in candidates:
        if (project_root / relative).exists():
            existing.append(relative)
    return existing


def _design_rules(contract: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
    composition = strategy.get("composition") if isinstance(strategy.get("composition"), dict) else {}
    experience = strategy.get("experience") if isinstance(strategy.get("experience"), dict) else {}
    return {
        "scale_rule": contract.get("scale_rule") or "",
        "screen_rule": contract.get("screen_rule") or "",
        "implementation_rule": contract.get("implementation_rule") or "",
        "page_label_rule": contract.get("page_label_rule") or "",
        "forbidden_visible_text": contract.get("forbidden_visible_text") or [],
        "anti_patterns": strategy.get("anti_patterns") or [],
        "composition": composition,
        "experience": experience,
        "quality_bar": strategy.get("quality_bar") or [],
        "normalization_rule": "Stitch may exaggerate scale; Friday must normalize typography, spacing, and viewport height during Next.js implementation.",
        "motion_rule": "Use animation, parallax, 3D, and immersive scenes only when the selected experience mode calls for them; always include reduced-motion or static fallback.",
    }


def _design_system_context(profile: dict[str, Any], strategy: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "style_profile": {
            "id": profile.get("id") or "",
            "name": profile.get("name") or "",
            "framework": profile.get("framework") or "",
            "description": profile.get("description") or "",
            "required_paths": (profile.get("required_paths") or [])[:20],
            "forbidden_paths": (profile.get("forbidden_paths") or [])[:12],
            "rules": (profile.get("rules") or [])[:16],
            "visible_branding_rule": "Profile names are internal memory. Never render NexusForge or profile labels unless they are the user's actual product brand.",
        },
        "surface": strategy.get("surface") or contract.get("surface") or "",
        "industry": strategy.get("industry") or "",
        "experience": strategy.get("experience") or {},
        "tokens": _design_tokens(strategy),
    }


def _design_tokens(strategy: dict[str, Any]) -> dict[str, str]:
    industry = _clean(strategy.get("industry")).lower()
    surface = _clean(strategy.get("surface")).lower()
    experience = strategy.get("experience") if isinstance(strategy.get("experience"), dict) else {}
    primary = experience.get("primary") if isinstance(experience.get("primary"), dict) else {}
    mode_id = _clean(primary.get("id")).lower()
    if mode_id == "interactive_3d":
        return {
            "density": "immersive but still readable",
            "color_mode": "scene-led with enough contrast for overlay text",
            "accent": "use accents to guide interaction, not as decoration",
            "components": "full-bleed canvas, fallback poster, overlay controls, section anchors",
            "motion": "real-time or scroll-reactive 3D with reduced-motion/static fallback",
        }
    if mode_id in {"cinematic_scroll", "parallax_story", "immersive_scene"}:
        return {
            "density": "cinematic sections with visible next content",
            "color_mode": "media-led or art-directed contrast",
            "accent": "used for progression, CTAs, and state cues",
            "components": "layered media, scroll sections, pinned/progressive proof, fallback content",
            "motion": "scroll/reveal motion with reduced-motion fallback",
        }
    if mode_id == "game_like":
        return {
            "density": "energetic but readable",
            "color_mode": "genre-specific high contrast",
            "accent": "player/action accent tied to modes and progression",
            "components": "gameplay scene, mode cards, stats, platform badges, join/play controls",
            "motion": "vivid but purposeful gameplay/progression motion",
        }
    if mode_id == "dashboard_operational":
        return {
            "density": "dense but calm",
            "color_mode": "neutral application shell",
            "accent": "status colors tied to risk, priority, and completion",
            "components": "tables, sidebars, filters, cards, drawers, toasts, modals",
            "motion": "practical feedback for loading, selection, and completion",
        }
    if industry == "developer_tools":
        return {
            "density": "compact, docs/product-console friendly",
            "color_mode": "dark or high-contrast neutral with restrained syntax accents",
            "accent": "orange, cyan, green, or electric blue used sparingly for state and CTA",
            "components": "code blocks, schema tables, terminal snippets, status badges, pricing cards",
            "motion": "subtle command/status transitions only",
        }
    if surface == "operational_dashboard":
        return {
            "density": "dense but calm",
            "color_mode": "neutral application shell",
            "accent": "status colors tied to risk, priority, and completion",
            "components": "tables, sidebars, filters, cards, drawers, toasts, modals",
            "motion": "practical feedback for loading, selection, and completion",
        }
    if industry == "luxury":
        return {
            "density": "spacious but not empty",
            "color_mode": "warm neutral or deep editorial contrast",
            "accent": "metallic or material accent used minimally",
            "components": "editorial image fields, concierge form, collection modules",
            "motion": "slow, restrained reveal",
        }
    return {
        "density": "balanced production web density",
        "color_mode": "domain-appropriate neutral foundation",
        "accent": "one or two purposeful accents, not a one-note palette",
        "components": "semantic sections, proof cards, forms, navigation, CTA blocks",
        "motion": "subtle and purposeful",
    }


def _handoff_requirements(profile: dict[str, Any], contract: dict[str, Any], strategy: dict[str, Any] | None = None) -> list[str]:
    strategy = strategy or {}
    experience = strategy.get("experience") if isinstance(strategy.get("experience"), dict) else {}
    primary = experience.get("primary") if isinstance(experience.get("primary"), dict) else {}
    mode_id = _clean(primary.get("id") or "static_polished")
    mode_requirements: list[str] = []
    if mode_id in {"interactive_3d", "immersive_scene", "game_like"}:
        mode_requirements.extend(
            [
                "Implement visible nonblank canvas/WebGL or scene proof only when the selected design calls for it.",
                "Verify canvas/scene pixels and framing with Playwright before claiming the 3D/immersive experience works.",
                "Include no-WebGL/static fallback and prefers-reduced-motion fallback.",
            ]
        )
    elif mode_id in {"cinematic_scroll", "parallax_story"}:
        mode_requirements.extend(
            [
                "Implement scroll/parallax motion with transforms or proven libraries; do not block normal scroll.",
                "Verify desktop/mobile scroll screenshots and reduced-motion behavior.",
            ]
        )
    elif mode_id == "product_demo_motion":
        mode_requirements.append("Implement motion as product state changes, not decorative floating elements.")
    return [
        "Generate design variants first; frontend implementation may use only the selected accepted handoff.",
        "Preserve the design intent, but normalize exaggerated Stitch scale for usable web/mobile viewports.",
        contract.get("implementation_rule") or "Implement with production component structure.",
        *mode_requirements,
        "Run Playwright/browser screenshot review after implementation.",
        "Reject output with dead buttons, broken navigation, placeholder copy, route-label headings, or internal profile-name leaks.",
        *[f"Style rule: {rule}" for rule in (profile.get("rules") or [])[:8]],
    ]


def _compile_stitch_prompt(
    context: dict[str, Any],
    profile: dict[str, Any],
    stack: dict[str, Any],
    contract: dict[str, Any],
    strategy: dict[str, Any],
    *,
    raw_prompt: str = "",
) -> dict[str, Any]:
    """Compile rich design context into a bounded prompt without dumb truncation."""

    budget = max(6000, int(config_value("design_stitch_prompt_budget_chars", 12000) or 12000))
    sections: list[dict[str, Any]] = []
    creative = context.get("creative_brief") if isinstance(context.get("creative_brief"), dict) else {}
    composition = context.get("composition_spec") if isinstance(context.get("composition_spec"), dict) else {}
    experience = context.get("experience_mode") if isinstance(context.get("experience_mode"), dict) else {}
    content = context.get("content_model") if isinstance(context.get("content_model"), dict) else {}
    copy_bank = context.get("copy_bank") if isinstance(context.get("copy_bank"), dict) else {}
    output_contract = context.get("output_contract") if isinstance(context.get("output_contract"), dict) else {}
    visual = context.get("visual_context") if isinstance(context.get("visual_context"), dict) else {}
    rules = context.get("design_rules") if isinstance(context.get("design_rules"), dict) else {}
    brand = context.get("brand_system") if isinstance(context.get("brand_system"), dict) else {}
    site = context.get("site_continuity") if isinstance(context.get("site_continuity"), dict) else {}
    taxonomy = context.get("taxonomy_prompt_profile") if isinstance(context.get("taxonomy_prompt_profile"), dict) else {}
    research_context = context.get("research_context") if isinstance(context.get("research_context"), dict) else {}
    autopilot = context.get("brief_autopilot") if isinstance(context.get("brief_autopilot"), dict) else {}
    memory = context.get("visual_reference_memory") if isinstance(context.get("visual_reference_memory"), dict) else {}
    learned = context.get("learned_rules") if isinstance(context.get("learned_rules"), dict) else {}
    code = context.get("code_context") if isinstance(context.get("code_context"), dict) else {}
    system = context.get("design_system_context") if isinstance(context.get("design_system_context"), dict) else {}

    def add(title: str, lines: list[str], *, priority: int = 50, required: bool = False) -> None:
        body = "\n".join([title, *[line for line in lines if _clean(line)]])
        sections.append({"title": title.rstrip(":"), "text": body.strip(), "priority": priority, "required": required})

    add(
        "Design context package:",
        [
            f"- Critical rejection rule: {_critical_rejection_rule(strategy)}",
            f"- Domain copy guardrail: {_domain_copy_guardrail(strategy)}",
            "- canvas/WebGL or scene layer required for immersive/3D modes; include static and reduced-motion fallback.",
            "- Do not default to a left-text/right-card split hero.",
            f"- Product goal: {_prompt_clip(str(context.get('product_goal') or ''), 180)}",
            f"- Emotional intent: {_prompt_clip(str(context.get('emotional_intent') or ''), 140)}",
            f"- Design default hero composition: {_prompt_clip(((autopilot.get('stitch_prompt_requirements') or {}).get('hero_composition') if isinstance(autopilot.get('stitch_prompt_requirements'), dict) else '') or (composition.get('archetype_name') or composition.get('archetype') or ''), 180)}",
            "- Critique before code: judge beauty, hero strength, image clarity, content depth, copy, category fit, and implementation feasibility.",
            f"- User intent: {_prompt_clip(_clean((context.get('user_intent') or {}).get('raw_request')), 280)}",
            f"- Expanded working brief: {_prompt_clip(_clean((context.get('user_intent') or {}).get('expanded_request')), 360)}",
            f"- Core message: {context.get('message') or ''}",
            f"- Target audience: {', '.join(context.get('target_audience') or [])}",
            f"- Target stack: {stack.get('label') or stack.get('stack') or 'web/mobile depending on request'}",
            f"- Page/screen objective: {contract.get('objective') or ''}",
        ],
        priority=100,
        required=True,
    )
    if autopilot:
        intent = autopilot.get("intent_expansion") if isinstance(autopilot.get("intent_expansion"), dict) else {}
        smart = autopilot.get("smart_defaults") if isinstance(autopilot.get("smart_defaults"), dict) else {}
        research = autopilot.get("research_before_design") if isinstance(autopilot.get("research_before_design"), dict) else {}
        generator = autopilot.get("design_direction_generator") if isinstance(autopilot.get("design_direction_generator"), dict) else {}
        requirements = autopilot.get("stitch_prompt_requirements") if isinstance(autopilot.get("stitch_prompt_requirements"), dict) else {}
        add(
            "Brief Autopilot:",
            [
                "- Treat vague prompts as incomplete briefs, not permission for generic output.",
                f"- Autopilot active: {autopilot.get('active')} (vague={autopilot.get('vague')}, style_missing={autopilot.get('style_missing')}, product_missing={autopilot.get('product_missing')})",
                f"- Assumption/clarification policy: {autopilot.get('assumption_summary') or ''}",
                f"- Hero composition to request: {requirements.get('hero_composition') or intent.get('composition_archetype') or ''}",
                "- Critique before code: reject weak Stitch results before frontend implementation.",
                f"- Product/company type: {intent.get('product_company_type') or ''}",
                f"- Target users: {', '.join(intent.get('target_users') or [])}",
                f"- Page goal: {intent.get('page_goal') or ''}",
                f"- Business model: {intent.get('business_model') or ''}",
                f"- Smart default: {smart.get('selected_default') or ''}. Reason: {smart.get('reason') or ''}",
                f"- Selected creative direction: {generator.get('selected') or ''}. {generator.get('selection_reason') or ''}",
                f"- Page sections: {', '.join(requirements.get('page_sections') or intent.get('content_sections') or [])}",
                f"- Copy voice: {requirements.get('copy_voice') or intent.get('copy_voice') or ''}",
                f"- Assets/image direction: {requirements.get('assets_image_direction') or ''}",
                f"- Research status: {research.get('status') or ''}; queries: {', '.join(research.get('queries') or [])}",
                *[f"- Reject if: {item}" for item in (intent.get("rejection_rules") or [])[:8]],
                *[f"- Critique before code: {item}" for item in (autopilot.get("critique_before_code") or [])[:7]],
            ],
            priority=99,
            required=True,
        )
    if research_context:
        result_summaries: list[str] = []
        for result in (research_context.get("results") or [])[:4]:
            if not isinstance(result, dict):
                continue
            query = _clean(result.get("query") or "")
            hits = result.get("results") if isinstance(result.get("results"), list) else []
            first = hits[0] if hits and isinstance(hits[0], dict) else {}
            result_summaries.append(
                f"{query}: {first.get('title') or ''} {first.get('snippet') or first.get('description') or ''}".strip()
            )
        dribbble = research_context.get("dribbble_references") if isinstance(research_context.get("dribbble_references"), dict) else {}
        dribbble_lines = [
            f"{item.get('title') or 'Reference'}: {item.get('snippet') or ''}"
            for item in (dribbble.get("references") or [])[:4]
            if isinstance(item, dict)
        ]
        add(
            "Research evidence before design:",
            [
                f"- Research status: {research_context.get('status') or ''}; live={research_context.get('live')}",
                *[f"- Search evidence: {_prompt_clip(item, 260)}" for item in result_summaries],
                *[f"- Dribbble visual reference: {_prompt_clip(item, 240)}" for item in dribbble_lines],
                f"- Competitor/user-need inference: {_prompt_clip(str(research_context.get('summary') or ''), 260)}",
                "- Use research as evidence, not as certainty. If evidence is thin, keep assumptions visible.",
            ],
            priority=98,
            required=True,
        )
    add(
        "Creative brief:",
        [
            f"- One-sentence feel: {creative.get('one_sentence') or ''}",
            f"- Decision moment: {creative.get('decision_moment') or ''}",
            f"- Primary objection to overcome: {creative.get('primary_objection') or ''}",
            f"- Design answer: {creative.get('design_answer') or ''}",
            f"- Trust signals to make visible: {', '.join(creative.get('trust_signals') or [])}",
        ],
        priority=96,
        required=True,
    )
    add(
        "Concrete page composition:",
        [
            f"- Composition archetype: {composition.get('archetype_name') or composition.get('archetype') or ''}",
            f"- Archetype rationale: {composition.get('archetype_rationale') or ''}",
            *[
                f"- Allowed alternative archetype: {item.get('name') or item.get('id')}: {item.get('first_viewport') or item.get('why') or ''}"
                for item in (composition.get("allowed_archetypes") or [])[:4]
                if isinstance(item, dict)
            ],
            *[f"- Composition rule: {item}" for item in (composition.get("composition_rules") or [])[:5]],
            *[f"- First viewport: {item}" for item in (composition.get("first_viewport") or [])[:5]],
            *[f"- Layout depth: {item}" for item in (composition.get("layout_depth") or [])[:4]],
            f"- Visual hierarchy: {composition.get('visual_hierarchy') or ''}",
            f"- Responsive notes: {composition.get('responsive_notes') or ''}",
            f"- Variant policy: {composition.get('variant_policy') or ''}",
        ],
        priority=94,
        required=True,
    )
    add(
        "Experience mode and motion/3D contract:",
        [
            f"- Experience mode: {experience.get('mode_name') or experience.get('mode') or ''}",
            f"- Intent: {experience.get('intent') or ''}",
            f"- Recommended libraries: {', '.join(experience.get('recommended_libraries') or [])}",
            *[
                f"- Allowed alternate mode: {item.get('name') or item.get('id')}: {item.get('intent') or item.get('when_to_use') or ''}"
                for item in (experience.get("allowed_modes") or [])[:4]
                if isinstance(item, dict)
            ],
            *[f"- Implementation note: {item}" for item in (experience.get("implementation_notes") or [])[:8]],
            *[f"- Motion rule: {item}" for item in (experience.get("motion_rules") or [])[:8]],
            *[f"- Verify: {item}" for item in (experience.get("verification_requirements") or [])[:8]],
            *[f"- Reject if: {item}" for item in (experience.get("rejection_rules") or [])[:5]],
            f"- Fallback requirement: {experience.get('fallback_requirement') or ''}",
            f"- Performance budget: {_compact_json_text(experience.get('performance_budget') or {}, limit=700)}",
        ],
        priority=93,
        required=True,
    )
    add(
        "Section-by-section blueprint:",
        [
            f"- {item.get('section')}: {item.get('purpose')} Must show: {', '.join(item.get('must_show') or [])}. Visual objects: {', '.join(item.get('visual_objects') or [])}."
            for item in (context.get("section_blueprint") or [])[:8]
            if isinstance(item, dict)
        ],
        priority=92,
        required=True,
    )
    add(
        "Component inventory to design:",
        [f"- {item}" for item in (context.get("component_inventory") or [])[:18]],
        priority=88,
        required=True,
    )
    add(
        "Copy and content requirements:",
        [
            f"- Navigation: {', '.join(content.get('navigation') or [])}",
            f"- Primary CTAs: {', '.join(content.get('primary_ctas') or [])}",
            f"- Proof objects: {', '.join(content.get('proof_objects') or [])}",
            f"- Headline directions: {' / '.join(copy_bank.get('headline_directions') or [])}",
            f"- Subhead direction: {copy_bank.get('subhead_direction') or ''}",
            f"- Microcopy examples: {', '.join(copy_bank.get('microcopy_examples') or [])}",
            f"- Words to use: {', '.join(copy_bank.get('words_to_use') or [])}",
            f"- Words to avoid: {', '.join(copy_bank.get('words_to_avoid') or [])}",
            *[f"- Copy guidance: {item}" for item in (content.get("copy_guidance") or [])[:8]],
            f"- Industry avoid words: {', '.join(taxonomy.get('avoid_words') or [])}",
        ],
        priority=86,
        required=True,
    )
    add(
        "Brand system:",
        [
            f"- Logo direction: {brand.get('logo_direction') or ''}",
            f"- Typography pair: {_compact_json_text(brand.get('typography') or {}, limit=700)}",
            f"- Color tokens: {_compact_json_text(brand.get('tokens') or {}, limit=900)}",
            f"- Spacing scale: {brand.get('spacing_scale') or ''}",
            f"- Radius system: {brand.get('radius_system') or ''}",
            f"- Icon style: {brand.get('icon_style') or ''}",
            f"- Motion style: {brand.get('motion_style') or ''}",
        ],
        priority=82,
        required=True,
    )
    add(
        "Visual grammar:",
        [
            f"- Art direction: {strategy.get('direction') or visual.get('direction') or ''}",
            f"- Message: {taxonomy.get('message') or strategy.get('message') or ''}",
            f"- Emotional feel: {taxonomy.get('emotional_feel') or strategy.get('emotion') or ''}",
            f"- Visual language: {visual.get('visual_language') or taxonomy.get('visual_grammar') or ''}",
            f"- Layout signature: {visual.get('layout_signature') or ''}",
            f"- Palette: {visual.get('palette') or ''}",
            f"- Typography: {visual.get('typography') or ''}",
            f"- Imagery: {visual.get('imagery') or ''}",
            f"- Copy voice: {visual.get('copy_voice') or taxonomy.get('copy_voice') or ''}",
            f"- Rejection rules: {'; '.join((strategy.get('anti_patterns') or [])[:6])}",
            f"- Industry-specific reject words: {', '.join(taxonomy.get('avoid_words') or [])}",
        ],
        priority=80,
        required=True,
    )
    add(
        "Inspiration references:",
        [
            f"- {(item or {}).get('name')}: {(item or {}).get('why')} Must include: {', '.join((item or {}).get('must_include') or [])}. Avoid: {', '.join((item or {}).get('avoid') or [])}."
            for item in (context.get("inspiration_references") or [])[:4]
            if isinstance(item, dict)
        ],
        priority=85,
        required=True,
    )
    if learned.get("prompt_lines"):
        add(
            "Learned Friday memory rules:",
            [f"- {item}" for item in (learned.get("prompt_lines") or [])[:10]],
            priority=97,
            required=True,
        )
    add(
        "Visual reference memory:",
        [
            f"- Available approved assets: {_compact_json_text(memory.get('assets') or [], limit=1200)}",
            f"- Usage rule: {memory.get('usage_rule') or ''}",
            f"- Missing-reference rule: {memory.get('missing_reference_rule') or ''}",
        ],
        priority=74,
    )
    add(
        "Site continuity:",
        [
            f"- Page label: {site.get('page_label') or ''}",
            f"- Shared site design system: {_compact_json_text(site.get('site_design_system') or {}, limit=1600)}",
            *[f"- Continuity rule: {item}" for item in (site.get("rules") or [])[:4]],
        ],
        priority=72,
    )
    add(
        "Variant instructions:",
        [
            f"- {item.get('variant')}: {item.get('direction')} {item.get('must_change')}"
            for item in (context.get("variant_briefs") or [])[:3]
            if isinstance(item, dict)
        ],
        priority=68,
    )
    add(
        "Output contract:",
        [
            *[f"- Must return: {item}" for item in (output_contract.get("must_return") or [])],
            f"- Minimum depth: {output_contract.get('minimum_depth') or ''}",
            f"- Visible UI branding must use \"{_clean((context.get('content_model') or {}).get('brand')) or brand.get('brand_name') or 'the requested product'}\" or a natural short form from the user request.",
            "- The style profile name is internal implementation guidance; do not render NexusForge or other profile identifiers as visible UI copy unless the user explicitly asks for that brand.",
            "- Reject if the design contains Home 1, Home 2, Service 1, Service 2, placeholder page-number artifacts, or generic scaffold copy.",
            "- Normalize exaggerated Stitch scale: useful web layout beats poster-sized type.",
            *[f"- Reject if: {item}" for item in (output_contract.get("rejection_if") or [])],
            *[f"- Reject if: {item}" for item in (strategy.get("anti_patterns") or [])[:8]],
            *[f"- Reject if: {item}" for item in (taxonomy.get("rejection_rules") or [])[:8]],
        ],
        priority=98,
        required=True,
    )
    add("Design-system context:", [f"- {_compact_json_text(system, limit=900)}"], priority=84, required=True)
    add("Code/product signals:", [f"- {_compact_json_text(code, limit=900)}"], priority=83, required=True)
    add("Design rules:", [f"- {_compact_json_text(rules, limit=1600)}"], priority=56)
    add("Handoff artifact rule:", ["- DESIGN.md, design-context.json, stitch-prompt.md, and site-design-system.json are source-of-truth handoff artifacts for Friday's implementation and critique loop."], priority=54, required=True)

    compiled, metadata = _fit_prompt_sections(sections, budget)
    metadata["raw_length"] = len(str(raw_prompt or ""))
    metadata["compiled_length"] = len(compiled)
    metadata["budget"] = budget
    metadata["call_plan"] = _stitch_prompt_call_plan(context, contract)
    return {"prompt": compiled, "metadata": metadata}


def _stitch_prompt_call_plan(context: dict[str, Any], contract: dict[str, Any]) -> list[dict[str, Any]]:
    user_intent = context.get("user_intent") if isinstance(context.get("user_intent"), dict) else {}
    site = context.get("site_continuity") if isinstance(context.get("site_continuity"), dict) else {}
    pages = ((site.get("site_design_system") or {}).get("pages") if isinstance(site.get("site_design_system"), dict) else []) or []
    plan = [
        {"id": "brief", "purpose": "product identity, user intent, research evidence, target audience"},
        {"id": "art_direction", "purpose": "composition archetype, emotional feel, visual grammar, tokens"},
        {"id": "output_contract", "purpose": "required sections, component inventory, copy bank, rejection rules"},
    ]
    if pages:
        plan.extend({"id": f"page:{page.get('id')}", "purpose": f"page-scoped Stitch prompt for {page.get('label')} route"} for page in pages if isinstance(page, dict))
    else:
        plan.append({"id": f"page:{contract.get('page_label') or user_intent.get('page_scope') or 'primary'}", "purpose": "single page/screen prompt"})
    plan.append({"id": "revision", "purpose": "browser/screenshot critique feedback prompt when the first handoff fails"})
    return plan


def _fit_prompt_sections(sections: list[dict[str, Any]], budget: int) -> tuple[str, dict[str, Any]]:
    selected = [section for section in sections if section.get("required")]
    optional = sorted([section for section in sections if not section.get("required")], key=lambda item: int(item.get("priority") or 0), reverse=True)
    included = [str(section.get("title") or "") for section in selected]
    dropped: list[str] = []
    prompt = "\n\n".join(str(section.get("text") or "") for section in selected if _clean(section.get("text")))
    shrunk_required = False
    if len(prompt) > budget:
        prompt = _shrink_required_prompt(selected, budget)
        shrunk_required = True
    for section in optional:
        candidate = "\n\n".join([prompt, str(section.get("text") or "")]).strip()
        if len(candidate) <= budget:
            prompt = candidate
            included.append(str(section.get("title") or ""))
        else:
            dropped.append(str(section.get("title") or ""))
    if len(prompt) > budget:
        prompt = prompt[: budget - 180].rstrip() + "\n\n[Prompt compacted by Friday StitchPromptCompiler to preserve critical context.]"
    return prompt, {
        "included_sections": [item for item in included if item],
        "dropped_sections": [item for item in dropped if item],
        "truncated": shrunk_required or len(prompt) >= budget,
        "strategy": "priority_section_compiler",
    }


def _shrink_required_prompt(required_sections: list[dict[str, Any]], budget: int) -> str:
    budgets = [_required_prompt_section_budget(str(section.get("title") or ""), budget) for section in required_sections]

    def render(current_budgets: list[int]) -> str:
        texts: list[str] = []
        for section, section_budget in zip(required_sections, current_budgets):
            text = str(section.get("text") or "").strip()
            if len(text) > section_budget:
                text = text[: max(100, section_budget - 80)].rstrip() + "\n- [Section compacted by Friday StitchPromptCompiler.]"
            texts.append(text)
        return "\n\n".join(texts)

    prompt = render(budgets)
    attempts = 0
    while len(prompt) > budget and attempts < 6:
        budgets = [max(360, int(value * 0.82)) for value in budgets]
        prompt = render(budgets)
        attempts += 1
    if len(prompt) > budget:
        footer = "\n\n[Prompt compacted by Friday StitchPromptCompiler to preserve critical context.]"
        room_per_section = max(180, int((budget - len(footer) - (len(required_sections) * 3)) / max(1, len(required_sections))))
        prompt = render([room_per_section for _ in required_sections])
        if len(prompt) > budget:
            prompt = prompt[: budget - len(footer)].rstrip() + footer
    return prompt


def _required_prompt_section_budget(title: str, total_budget: int) -> int:
    base = max(520, int(total_budget / 14))
    title_lower = title.lower()
    if "brief autopilot" in title_lower:
        return max(1500, base + 700)
    if "design context package" in title_lower:
        return max(1200, base + 500)
    if "output contract" in title_lower:
        return max(1500, base + 700)
    if "composition" in title_lower:
        return max(1500, base + 600)
    if "experience mode" in title_lower:
        return max(1500, base + 600)
    if "section-by-section" in title_lower:
        return max(1200, base + 400)
    if "copy and content" in title_lower:
        return max(1100, base + 300)
    if "design-system" in title_lower or "code/product" in title_lower:
        return max(780, base)
    return max(760, base)


def _critical_rejection_rule(strategy: dict[str, Any]) -> str:
    anti_patterns = [str(item) for item in (strategy.get("anti_patterns") or []) if _clean(item)]
    industry = _clean(strategy.get("industry")).replace("_", " ").lower()
    for item in anti_patterns:
        if industry and industry in item.lower():
            return item
    for item in anti_patterns:
        lowered = item.lower()
        if "generic" in lowered or "placeholder" in lowered or "scaffold" in lowered:
            return item
    return anti_patterns[0] if anti_patterns else "Do not use generic placeholder design or copy."


def _domain_copy_guardrail(strategy: dict[str, Any]) -> str:
    industry = _clean(strategy.get("industry")).lower()
    if industry == "energy_climate":
        return "Never use construction-company phrases, contractor/jobsite imagery, CLI/API/Web3 backend language, or generic consulting copy for a climate-energy product."
    if industry == "developer_tools":
        return "Never use lifestyle stock-copy or generic service-business language; show code, docs, architecture, and product proof."
    if industry == "construction":
        return "Never make construction-company pages read like generic SaaS automation; show project, safety, material, delivery, and site credibility."
    return "Never let internal prompt labels, route labels, or scaffold phrases become visible product copy."


def _prompt_clip(value: str, limit: int) -> str:
    text = _clean(value)
    return text if len(text) <= limit else text[: max(0, limit - 3)].rstrip() + "..."


def _design_context_prompt(context: dict[str, Any]) -> str:
    inspiration = context.get("inspiration_references") if isinstance(context.get("inspiration_references"), list) else []
    content = context.get("content_model") if isinstance(context.get("content_model"), dict) else {}
    code = context.get("code_context") if isinstance(context.get("code_context"), dict) else {}
    system = context.get("design_system_context") if isinstance(context.get("design_system_context"), dict) else {}
    visual = context.get("visual_context") if isinstance(context.get("visual_context"), dict) else {}
    rules = context.get("design_rules") if isinstance(context.get("design_rules"), dict) else {}
    creative = context.get("creative_brief") if isinstance(context.get("creative_brief"), dict) else {}
    composition = context.get("composition_spec") if isinstance(context.get("composition_spec"), dict) else {}
    experience = context.get("experience_mode") if isinstance(context.get("experience_mode"), dict) else {}
    section_blueprint = context.get("section_blueprint") if isinstance(context.get("section_blueprint"), list) else []
    copy_bank = context.get("copy_bank") if isinstance(context.get("copy_bank"), dict) else {}
    output_contract = context.get("output_contract") if isinstance(context.get("output_contract"), dict) else {}
    variant_briefs = context.get("variant_briefs") if isinstance(context.get("variant_briefs"), list) else []
    components = context.get("component_inventory") if isinstance(context.get("component_inventory"), list) else []
    brand = context.get("brand_system") if isinstance(context.get("brand_system"), dict) else {}
    site = context.get("site_continuity") if isinstance(context.get("site_continuity"), dict) else {}
    visual_memory = context.get("visual_reference_memory") if isinstance(context.get("visual_reference_memory"), dict) else {}
    learned = context.get("learned_rules") if isinstance(context.get("learned_rules"), dict) else {}
    taxonomy = context.get("taxonomy_prompt_profile") if isinstance(context.get("taxonomy_prompt_profile"), dict) else {}
    research_context = context.get("research_context") if isinstance(context.get("research_context"), dict) else {}
    autopilot = context.get("brief_autopilot") if isinstance(context.get("brief_autopilot"), dict) else {}
    autopilot_intent = autopilot.get("intent_expansion") if isinstance(autopilot.get("intent_expansion"), dict) else {}
    autopilot_research = autopilot.get("research_before_design") if isinstance(autopilot.get("research_before_design"), dict) else {}
    autopilot_generator = autopilot.get("design_direction_generator") if isinstance(autopilot.get("design_direction_generator"), dict) else {}
    return "\n".join(
        [
            "Design context package:",
            f"- User intent: {_clean((context.get('user_intent') or {}).get('raw_request'))}",
            f"- Expanded working brief: {_clean((context.get('user_intent') or {}).get('expanded_request'))}",
            f"- Product goal: {context.get('product_goal') or ''}",
            f"- Target audience: {', '.join(context.get('target_audience') or [])}",
            f"- Emotional intent: {context.get('emotional_intent') or ''}",
            f"- Core message: {context.get('message') or ''}",
            "",
            "Brief Autopilot:",
            "- Vague prompts are incomplete briefs; enrich them before design instead of generating generic UI.",
            f"- Active: {autopilot.get('active')} / assumption: {autopilot.get('assumption_summary') or ''}",
            f"- Product/company type: {autopilot_intent.get('product_company_type') or ''}",
            f"- Business model: {autopilot_intent.get('business_model') or ''}",
            f"- Design category: {autopilot_intent.get('design_category') or ''}",
            f"- Composition archetype: {autopilot_intent.get('composition_archetype') or ''}",
            f"- Selected direction: {autopilot_generator.get('selected') or ''} ({autopilot_generator.get('selection_reason') or ''})",
            f"- Research before design: {autopilot_research.get('status') or ''}; queries: {', '.join(autopilot_research.get('queries') or [])}",
            f"- Live research evidence: {research_context.get('status') or 'not supplied'}; queries: {', '.join(research_context.get('queries') or []) if isinstance(research_context.get('queries'), list) else ''}",
            *[f"- Reject if: {item}" for item in (autopilot_intent.get("rejection_rules") or [])[:8]],
            *[f"- Critique before code: {item}" for item in (autopilot.get("critique_before_code") or [])[:7]],
            "",
            "Creative brief:",
            f"- One-sentence feel: {creative.get('one_sentence') or ''}",
            f"- Decision moment: {creative.get('decision_moment') or ''}",
            f"- Primary objection to overcome: {creative.get('primary_objection') or ''}",
            f"- Design answer: {creative.get('design_answer') or ''}",
            f"- Trust signals to make visible: {', '.join(creative.get('trust_signals') or [])}",
            "",
            "Concrete page composition:",
            f"- Composition archetype: {composition.get('archetype_name') or composition.get('archetype') or ''}",
            f"- Archetype rationale: {composition.get('archetype_rationale') or ''}",
            *[
                f"- Allowed alternative archetype: {item.get('name') or item.get('id')}: {item.get('first_viewport') or item.get('why') or ''}"
                for item in (composition.get("allowed_archetypes") or [])[:4]
                if isinstance(item, dict)
            ],
            *[f"- Composition rule: {item}" for item in (composition.get("composition_rules") or [])[:5]],
            *[f"- First viewport: {item}" for item in (composition.get("first_viewport") or [])],
            *[f"- Layout depth: {item}" for item in (composition.get("layout_depth") or [])],
            f"- Visual hierarchy: {composition.get('visual_hierarchy') or ''}",
            f"- Responsive notes: {composition.get('responsive_notes') or ''}",
            f"- Variant policy: {composition.get('variant_policy') or ''}",
            "",
            "Experience mode and motion/3D contract:",
            f"- Experience mode: {experience.get('mode_name') or experience.get('mode') or ''}",
            f"- Intent: {experience.get('intent') or ''}",
            f"- Recommended libraries: {', '.join(experience.get('recommended_libraries') or [])}",
            *[
                f"- Allowed alternate mode: {item.get('name') or item.get('id')}: {item.get('intent') or item.get('when_to_use') or ''}"
                for item in (experience.get("allowed_modes") or [])[:4]
                if isinstance(item, dict)
            ],
            *[f"- Implementation note: {item}" for item in (experience.get("implementation_notes") or [])[:8]],
            *[f"- Motion rule: {item}" for item in (experience.get("motion_rules") or [])[:8]],
            *[f"- Verify: {item}" for item in (experience.get("verification_requirements") or [])[:8]],
            *[f"- Reject if: {item}" for item in (experience.get("rejection_rules") or [])[:5]],
            f"- Fallback requirement: {experience.get('fallback_requirement') or ''}",
            f"- Performance budget: {_compact_json_text(experience.get('performance_budget') or {}, limit=900)}",
            "",
            "Brand system:",
            f"- Logo direction: {brand.get('logo_direction') or ''}",
            f"- Typography pair: {_compact_json_text(brand.get('typography') or {}, limit=900)}",
            f"- Color tokens: {_compact_json_text(brand.get('tokens') or {}, limit=1000)}",
            f"- Spacing scale: {brand.get('spacing_scale') or ''}",
            f"- Radius system: {brand.get('radius_system') or ''}",
            f"- Icon style: {brand.get('icon_style') or ''}",
            f"- Motion style: {brand.get('motion_style') or ''}",
            "",
            f"Visual grammar: {_compact_json_text(visual, limit=2400)}",
            f"Taxonomy-specific guidance: {_compact_json_text(taxonomy, limit=1800)}",
            "- Inspiration references to use as direction, not as copies:",
            *[
                f"  - {(item or {}).get('name')}: {(item or {}).get('why')} Must include: {', '.join((item or {}).get('must_include') or [])}. Avoid: {', '.join((item or {}).get('avoid') or [])}."
                for item in inspiration[:5]
                if isinstance(item, dict)
            ],
            "",
            "Visual reference memory:",
            f"- Approved assets and evidence: {_compact_json_text(visual_memory, limit=1800)}",
            "",
            "Learned Friday memory rules:",
            *[f"- {item}" for item in (learned.get("prompt_lines") or [])[:10]],
            "",
            "Site continuity:",
            f"- Shared site design system: {_compact_json_text(site.get('site_design_system') or {}, limit=2000)}",
            *[f"- Continuity rule: {item}" for item in (site.get("rules") or [])[:4]],
            "",
            "Section-by-section blueprint:",
            *[
                f"- {item.get('section')}: {item.get('purpose')} Must show: {', '.join(item.get('must_show') or [])}. Visual objects: {', '.join(item.get('visual_objects') or [])}."
                for item in section_blueprint[:8]
                if isinstance(item, dict)
            ],
            "",
            "Copy and content requirements:",
            f"- Navigation: {', '.join(content.get('navigation') or [])}",
            f"- Primary CTAs: {', '.join(content.get('primary_ctas') or [])}",
            f"- Proof objects: {', '.join(content.get('proof_objects') or [])}",
            f"- Headline directions: {' / '.join(copy_bank.get('headline_directions') or [])}",
            f"- Subhead direction: {copy_bank.get('subhead_direction') or ''}",
            f"- Microcopy examples: {', '.join(copy_bank.get('microcopy_examples') or [])}",
            f"- Words to use: {', '.join(copy_bank.get('words_to_use') or [])}",
            f"- Words to avoid: {', '.join(copy_bank.get('words_to_avoid') or [])}",
            "",
            f"Component inventory to design: {', '.join(components)}",
            "",
            "Variant instructions:",
            *[
                f"- {item.get('variant')}: {item.get('direction')} {item.get('must_change')}"
                for item in variant_briefs[:3]
                if isinstance(item, dict)
            ],
            "",
            "Output contract:",
            *[f"- Must return: {item}" for item in (output_contract.get("must_return") or [])],
            f"- Minimum depth: {output_contract.get('minimum_depth') or ''}",
            *[f"- Reject if: {item}" for item in (output_contract.get("rejection_if") or [])],
            "",
            f"Code/product signals: {_compact_json_text(code, limit=2200)}",
            f"Design-system context: {_compact_json_text(system, limit=2400)}",
            f"Design rules: {_compact_json_text(rules, limit=2400)}",
            "- DESIGN.md and design-context.json are source-of-truth handoff artifacts for Friday's implementation and critique loop.",
        ]
    )


def _compact_json_text(value: Any, *, limit: int = 1200) -> str:
    text = json.dumps(value or {}, ensure_ascii=True, sort_keys=True, default=str)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _design_context_markdown(brief: dict[str, Any]) -> str:
    context = brief.get("design_context") if isinstance(brief.get("design_context"), dict) else {}
    visual = context.get("visual_context") if isinstance(context.get("visual_context"), dict) else {}
    content = context.get("content_model") if isinstance(context.get("content_model"), dict) else {}
    rules = context.get("design_rules") if isinstance(context.get("design_rules"), dict) else {}
    system = context.get("design_system_context") if isinstance(context.get("design_system_context"), dict) else {}
    profile = system.get("style_profile") if isinstance(system.get("style_profile"), dict) else {}
    creative = context.get("creative_brief") if isinstance(context.get("creative_brief"), dict) else {}
    composition = context.get("composition_spec") if isinstance(context.get("composition_spec"), dict) else {}
    experience = context.get("experience_mode") if isinstance(context.get("experience_mode"), dict) else {}
    copy_bank = context.get("copy_bank") if isinstance(context.get("copy_bank"), dict) else {}
    output_contract = context.get("output_contract") if isinstance(context.get("output_contract"), dict) else {}
    brand = context.get("brand_system") if isinstance(context.get("brand_system"), dict) else {}
    visual_memory = context.get("visual_reference_memory") if isinstance(context.get("visual_reference_memory"), dict) else {}
    learned = context.get("learned_rules") if isinstance(context.get("learned_rules"), dict) else {}
    site = context.get("site_continuity") if isinstance(context.get("site_continuity"), dict) else {}
    taxonomy = context.get("taxonomy_prompt_profile") if isinstance(context.get("taxonomy_prompt_profile"), dict) else {}
    autopilot = context.get("brief_autopilot") if isinstance(context.get("brief_autopilot"), dict) else {}
    autopilot_intent = autopilot.get("intent_expansion") if isinstance(autopilot.get("intent_expansion"), dict) else {}
    autopilot_smart = autopilot.get("smart_defaults") if isinstance(autopilot.get("smart_defaults"), dict) else {}
    autopilot_research = autopilot.get("research_before_design") if isinstance(autopilot.get("research_before_design"), dict) else {}
    autopilot_generator = autopilot.get("design_direction_generator") if isinstance(autopilot.get("design_direction_generator"), dict) else {}
    lines = [
        "# DESIGN.md",
        "",
        f"Product: {_clean(brief.get('product_name')) or 'Unnamed product'}",
        f"Surface: {(context.get('user_intent') or {}).get('surface') or ''}",
        f"Industry: {(context.get('user_intent') or {}).get('industry') or ''}",
        f"Original request: {_clean(brief.get('request'))}",
        f"Expanded request: {_prompt_clip(_clean(brief.get('expanded_request')), 1000)}",
        "",
        "## Brief Autopilot",
        f"- Active: {autopilot.get('active')}",
        f"- Vague prompt: {autopilot.get('vague')}",
        f"- Style missing: {autopilot.get('style_missing')}",
        f"- Product missing: {autopilot.get('product_missing')}",
        f"- Assumption: {autopilot.get('assumption_summary') or ''}",
        f"- Clarifying question: {(autopilot.get('ask_only_when_needed') or {}).get('question') or ''}",
        f"- Product/company type: {autopilot_intent.get('product_company_type') or ''}",
        f"- Target users: {', '.join(autopilot_intent.get('target_users') or [])}",
        f"- Page goal: {autopilot_intent.get('page_goal') or ''}",
        f"- Business model: {autopilot_intent.get('business_model') or ''}",
        f"- Smart default: {autopilot_smart.get('selected_default') or ''}",
        f"- Smart default reason: {autopilot_smart.get('reason') or ''}",
        f"- Selected direction: {autopilot_generator.get('selected') or ''}",
        f"- Research status: {autopilot_research.get('status') or ''}",
        *[f"- Research query: {item}" for item in (autopilot_research.get("queries") or [])],
        *[f"- Reject: {item}" for item in (autopilot_intent.get("rejection_rules") or [])],
        *[f"- Critique check: {item}" for item in (autopilot.get("critique_before_code") or [])],
        "",
        "## Intent",
        f"- Goal: {context.get('product_goal') or ''}",
        f"- Audience: {', '.join(context.get('target_audience') or [])}",
        f"- Emotional feel: {context.get('emotional_intent') or ''}",
        f"- Message: {context.get('message') or ''}",
        "",
        "## Creative Brief",
        f"- One-sentence feel: {creative.get('one_sentence') or ''}",
        f"- Decision moment: {creative.get('decision_moment') or ''}",
        f"- Primary objection: {creative.get('primary_objection') or ''}",
        f"- Design answer: {creative.get('design_answer') or ''}",
        f"- Trust signals: {', '.join(creative.get('trust_signals') or [])}",
        "",
        "## Composition",
        f"- Archetype: {composition.get('archetype_name') or composition.get('archetype') or ''}",
        f"- Rationale: {composition.get('archetype_rationale') or ''}",
        *[
            f"- Alternative archetype: {item.get('name') or item.get('id')}: {item.get('first_viewport') or item.get('why') or ''}"
            for item in (composition.get("allowed_archetypes") or [])[:5]
            if isinstance(item, dict)
        ],
        *[f"- Composition rule: {item}" for item in composition.get("composition_rules") or []],
        *[f"- First viewport: {item}" for item in composition.get("first_viewport") or []],
        *[f"- Layout depth: {item}" for item in composition.get("layout_depth") or []],
        f"- Visual hierarchy: {composition.get('visual_hierarchy') or ''}",
        f"- Responsive notes: {composition.get('responsive_notes') or ''}",
        f"- Variant policy: {composition.get('variant_policy') or ''}",
        "",
        "## Experience Mode",
        f"- Mode: {experience.get('mode_name') or experience.get('mode') or ''}",
        f"- Intent: {experience.get('intent') or ''}",
        f"- Recommended libraries: {', '.join(experience.get('recommended_libraries') or [])}",
        *[
            f"- Alternative mode: {item.get('name') or item.get('id')}: {item.get('intent') or item.get('when_to_use') or ''}"
            for item in (experience.get("allowed_modes") or [])[:5]
            if isinstance(item, dict)
        ],
        *[f"- Implementation: {item}" for item in experience.get("implementation_notes") or []],
        *[f"- Motion rule: {item}" for item in experience.get("motion_rules") or []],
        *[f"- Verification: {item}" for item in experience.get("verification_requirements") or []],
        *[f"- Reject if: {item}" for item in experience.get("rejection_rules") or []],
        f"- Fallback: {experience.get('fallback_requirement') or ''}",
        f"- Performance: {_compact_json_text(experience.get('performance_budget') or {}, limit=900)}",
        "",
        "## Brand System",
        f"- Logo direction: {brand.get('logo_direction') or ''}",
        f"- Typography: {_compact_json_text(brand.get('typography') or {}, limit=1000)}",
        f"- Color tokens: {_compact_json_text(brand.get('tokens') or {}, limit=1200)}",
        f"- Spacing scale: {brand.get('spacing_scale') or ''}",
        f"- Radius system: {brand.get('radius_system') or ''}",
        f"- Icon style: {brand.get('icon_style') or ''}",
        f"- Motion style: {brand.get('motion_style') or ''}",
        "",
        "## Taxonomy Guidance",
        f"- Message: {taxonomy.get('message') or ''}",
        f"- Emotional feel: {taxonomy.get('emotional_feel') or ''}",
        f"- Visual grammar: {taxonomy.get('visual_grammar') or ''}",
        f"- Copy voice: {taxonomy.get('copy_voice') or ''}",
        *[f"- Reject: {item}" for item in taxonomy.get("rejection_rules") or []],
        "",
        "## Visual Grammar",
        f"- Direction: {visual.get('direction') or ''}",
        f"- Language: {visual.get('visual_language') or ''}",
        f"- Layout: {visual.get('layout_signature') or ''}",
        f"- Palette: {visual.get('palette') or ''}",
        f"- Typography: {visual.get('typography') or ''}",
        f"- Imagery: {visual.get('imagery') or ''}",
        f"- Interaction: {visual.get('interaction_model') or ''}",
        f"- Copy voice: {visual.get('copy_voice') or ''}",
        "",
        "## Content Model",
        f"- Navigation: {', '.join(content.get('navigation') or [])}",
        f"- Primary CTAs: {', '.join(content.get('primary_ctas') or [])}",
        f"- Required sections: {', '.join(content.get('required_sections') or [])}",
        f"- Proof objects: {', '.join(content.get('proof_objects') or [])}",
        f"- Domain terms: {', '.join(content.get('domain_terms') or [])}",
        "",
        "## Section Blueprint",
    ]
    for item in context.get("section_blueprint") or []:
        if isinstance(item, dict):
            lines.append(f"- {item.get('section')}: {item.get('purpose')} Must show: {', '.join(item.get('must_show') or [])}.")
    lines.extend(
        [
            "",
            "## Copy Bank",
            *[f"- Headline direction: {item}" for item in copy_bank.get("headline_directions") or []],
            f"- Subhead direction: {copy_bank.get('subhead_direction') or ''}",
            f"- Microcopy: {', '.join(copy_bank.get('microcopy_examples') or [])}",
            f"- Words to use: {', '.join(copy_bank.get('words_to_use') or [])}",
            f"- Words to avoid: {', '.join(copy_bank.get('words_to_avoid') or [])}",
            "",
            "## Component Inventory",
            *[f"- {item}" for item in context.get("component_inventory") or []],
            "",
            "## Output Contract",
            *[f"- Must return: {item}" for item in output_contract.get("must_return") or []],
            f"- Minimum depth: {output_contract.get('minimum_depth') or ''}",
            *[f"- Reject if: {item}" for item in output_contract.get("rejection_if") or []],
            "",
            "## Variant Briefs",
        ]
    )
    for item in context.get("variant_briefs") or []:
        if isinstance(item, dict):
            lines.append(f"- {item.get('variant')}: {item.get('direction')} {item.get('must_change')}")
    lines.extend(
        [
            "",
            "## Inspiration Directions",
        ]
    )
    for item in context.get("inspiration_references") or []:
        if isinstance(item, dict):
            lines.append(f"- {item.get('name')}: {item.get('why')}")
    lines.extend(
        [
            "",
            "## Visual Reference Memory",
            f"- Available: {visual_memory.get('available')}",
            f"- Usage rule: {visual_memory.get('usage_rule') or ''}",
            *[f"- Reference: {(item or {}).get('path')} ({(item or {}).get('type')})" for item in (visual_memory.get("assets") or [])[:16] if isinstance(item, dict)],
            "",
            "## Learned Friday Memory Rules",
            f"- Available: {learned.get('available')}",
            f"- Summary: {learned.get('summary') or ''}",
            *[f"- {item}" for item in (learned.get("prompt_lines") or [])[:12]],
            "",
            "## Site Continuity",
            f"- Page label: {site.get('page_label') or ''}",
            f"- Site design system path: {site.get('site_design_system_path') or ''}",
            *[f"- {item}" for item in site.get("rules") or []],
            "",
            "## Design Rules",
            f"- Scale: {rules.get('scale_rule') or ''}",
            f"- Screen: {rules.get('screen_rule') or ''}",
            f"- Implementation: {rules.get('implementation_rule') or ''}",
            f"- Page labels: {rules.get('page_label_rule') or ''}",
            f"- Normalization: {rules.get('normalization_rule') or ''}",
            *[f"- Avoid: {item}" for item in (rules.get("anti_patterns") or [])[:12]],
            "",
            "## Design-System Memory",
            f"- Profile: {profile.get('name') or profile.get('id') or 'none'}",
            *[f"- {rule}" for rule in (profile.get("rules") or [])[:14]],
            "",
            "## Handoff Requirements",
            *[f"- {item}" for item in context.get("handoff_requirements") or []],
            "",
        ]
    )
    return "\n".join(lines)


def _stitch_prompt(
    request: str,
    product_name: str,
    profile: dict[str, Any],
    stack: dict[str, Any],
    *,
    contract: dict[str, Any] | None = None,
    strategy: dict[str, Any] | None = None,
    design_context: dict[str, Any] | None = None,
) -> str:
    rules = "\n".join(f"- {rule}" for rule in (profile.get("rules") or [])[:10])
    visible_name = _clean(product_name) or "the requested product"
    contract = contract or _design_contract(request, product_name, stack)
    strategy = strategy or design_director.design_strategy(request, product_name, page_label=contract.get("page_label") or "", stack=stack)
    if design_context is None:
        design_context = _design_context_package(ROOT_DIR, request, visible_name, stack, profile, contract, strategy)
    sections = ", ".join(contract.get("required_sections") or [])
    forbidden = "\n".join(f"- {item}" for item in (contract.get("forbidden_visible_text") or [])[:10])
    screen_rule = contract.get("screen_rule") or "Produce a complete UI screen, not an isolated logo or brand asset."
    return (
        f"Design a production-quality interface for: {visible_name}.\n"
        f"Request: {_clean(request)}\n"
        f"Target stack: {stack.get('label') or stack.get('stack') or 'web/mobile depending on request'}.\n"
        f"Page/screen objective: {contract.get('objective')}.\n"
        f"Required sections/components: {sections}.\n"
        f"{_design_context_prompt(design_context)}\n"
        f"{strategy.get('prompt_block') or ''}\n"
        f"Scale rule: {contract.get('scale_rule')}.\n"
        f"Screen rule: {screen_rule}.\n"
        f"Page-label rule: {contract.get('page_label_rule')}.\n"
        "Produce screens with clear hierarchy, specific domain copy, responsive layouts, accessible controls, and no generic placeholder text.\n"
        f"Visible UI branding must use \"{visible_name}\" or a natural short form from the user request.\n"
        "Do not append page labels to the brand name; page labels belong in navigation, metadata, or section context only.\n"
        "Never render labels like Home 1, Home 2, Service 1, Service 2, or any numbered page artifacts.\n"
        f"Forbidden visible text:\n{forbidden or '- Generic scaffold labels, raw prompts, and provider/debug labels.'}\n"
        "The style profile name is internal implementation guidance; do not render NexusForge or other profile identifiers as visible UI copy unless the user explicitly asks for that brand.\n"
        "Follow this local style memory when converting to code:\n"
        f"{rules or '- Use existing project conventions.'}"
    )


def _design_contract(request: str, product_name: str, stack: dict[str, Any], *, artifact_scope: str = "") -> dict[str, Any]:
    text = _clean(request)
    lower = text.lower()
    is_website = any(term in lower for term in ("website", "site", "landing page", "landing website", "four-page", "4 page", "4-page", "four pages"))
    is_dashboard = any(term in lower for term in ("dashboard", "command center", "portal", "management"))
    is_landing = "landing page" in lower or "landing website" in lower
    page_label = _page_label_from_request(text) or _page_label_from_scope(artifact_scope)
    if is_website:
        page_key = _clean_page_id(page_label or "home").replace("_", "-")
        labels = _explicit_website_page_labels(text)
        nav_text = ", ".join(labels) if labels else ("landing-page sections" if is_landing else "Home, About, Services, and Contact")
        required_by_page = {
            "home": (
                ["global navigation", "brand-specific hero", "proof/status strip", "problem-to-solution", "core capabilities", "how it works", "primary CTA/footer"]
                if is_landing
                else ["global navigation", "brand-specific hero", "trust/proof teaser", "service teaser", "primary contact CTA"]
            ),
            "about": ["global navigation", "company story", "credibility proof", "method or values", "contact CTA"],
            "services": ["global navigation", "service offerings", "delivery process", "fit/qualification details", "contact CTA"],
            "pricing": ["global navigation", "pricing tiers", "plan fit guidance", "objection handling", "contact CTA"],
            "contact": ["global navigation", "inquiry form", "response promise", "contact options", "privacy/trust note"],
            "atelier": ["global navigation", "craftsmanship story", "materials or process proof", "atelier/workshop detail", "concierge CTA"],
            "collections": ["global navigation", "collection/gallery modules", "product provenance", "scarcity or fit details", "concierge CTA"],
            "concierge-contact": ["global navigation", "concierge inquiry form", "appointment options", "privacy/trust note", "response promise"],
        }
        required = required_by_page.get(page_key, required_by_page["home"])
        if "contact" in page_key or "concierge" in page_key:
            required = required_by_page["concierge-contact"] if "concierge" in page_key else required_by_page["contact"]
        if is_landing and not labels:
            objective = (
                "Design a complete product landing page with anchor-style navigation, product proof, conversion actions, and section depth. "
                "This is one cohesive page, not a dashboard screen and not a multi-page website index."
            )
        else:
            objective = (
                f"Design the {page_label or 'page'} route for a real multi-page website, with navigation to {nav_text}. "
                "The page label is route metadata, not a visible hero headline by itself."
            )
    elif is_dashboard:
        required = ["sidebar or command navigation", "metric strip", "work queue/table", "detail panel", "primary action states"]
        objective = "Design an operational dashboard screen that supports repeated work, scanning, triage, and action."
    else:
        required = ["hero/workspace entry", "primary workflow", "proof/status area", "next action"]
        objective = "Design the primary product surface with concrete domain copy and useful controls."
    return {
        "page_label": page_label or "home",
        "objective": objective,
        "required_sections": required,
        "surface": "marketing_website" if is_website else "operational_dashboard" if is_dashboard else "product_app",
        "scale_rule": "Use restrained production UI scale: no oversized headings that exceed one viewport, no decorative empty whitespace, and no section taller than its useful content.",
        "screen_rule": "Produce a complete desktop web page with header/navigation, main content, page-specific sections, conversion action, and footer; do not return only a logo, icon, brand mark, or design-system asset.",
        "implementation_rule": "Friday may adapt spacing, typography, and layout for Next.js implementation; do not copy exaggerated Stitch scale literally.",
        "page_label_rule": "Do not render page labels as giant hero eyebrows, standalone H1 text, or numbered section names.",
        "forbidden_visible_text": [
            "Home 1",
            "Home 2",
            "Service 1",
            "Service 2",
            "About 1",
            "Contact 1",
            "Lorem ipsum",
            "Independent service studio",
            "A clear four-page website",
        ],
    }


def _critique_plan(brief: dict[str, Any], variant_count: int) -> dict[str, Any]:
    threshold = int(config_value("design_critique_min_score", 72) or 72)
    return {
        "status": "planned",
        "summary": f"Generate {variant_count} design variant(s), score them, reject weak directions, and hand off only the best accepted design.",
        "variant_count": variant_count,
        "score_threshold": threshold,
        "frontend_handoff_allowed": False,
        "frontend_handoff_required": bool(config_value("design_frontend_handoff_required", True)),
        "selected_variant": None,
        "variants": [],
        "rejected_variants": [],
        "criteria": [
            "product_branding",
            "domain_fit",
            "art_direction_fit",
            "operational_density",
            "accessibility_semantics",
            "copy_quality",
            "frontend_feasibility",
        ],
        "guardrails": brief.get("instructions") or [],
        "design_strategy": brief.get("design_strategy") or {},
        "design_context": brief.get("design_context") or {},
    }


def _critique_report(
    brief: dict[str, Any],
    variants: list[dict[str, Any]],
    *,
    selected: dict[str, Any] | None,
    status: str,
    summary: str,
    frontend_handoff_allowed: bool,
    generation: dict[str, Any] | None = None,
    diversity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fallback_policy = _stitch_fallback_policy(brief)
    source_provider = ""
    if isinstance(generation, dict):
        source_provider = _clean(generation.get("source_provider") or generation.get("provider_source") or generation.get("provider"))
    return {
        "status": status,
        "summary": _clean(summary),
        "score_threshold": int(config_value("design_critique_min_score", 72) or 72),
        "frontend_handoff_allowed": frontend_handoff_allowed,
        "frontend_handoff_required": bool(config_value("design_frontend_handoff_required", True)),
        "selected_variant": selected,
        "variants": variants,
        "rejected_variants": [variant for variant in variants if not variant.get("accepted")],
        "generation_status": generation.get("status") if isinstance(generation, dict) else "",
        "source_provider": source_provider,
        "provider_source": source_provider,
        "stitch_fallback_policy": fallback_policy,
        "stitch_required": fallback_policy == "stitch_required",
        "request": brief.get("request") or "",
        "product_name": brief.get("product_name") or "",
        "style_profile": (brief.get("style_profile") or {}).get("id") if isinstance(brief.get("style_profile"), dict) else "",
        "design_strategy": brief.get("design_strategy") or {},
        "design_context": brief.get("design_context") or {},
        "diversity": diversity or {},
    }


def _fallback_critique_after_stitch_problem(
    brief: dict[str, Any],
    count: int,
    generation: dict[str, Any],
    design_root: Path,
    *,
    fallback_policy: str,
    reason: str,
    source_critique: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not bool(config_value("design_local_fallback_on_stitch_failure", True)):
        return None
    variants = _local_fallback_design_variants(brief, count, reason=reason)
    critique = critique_design_variants(variants, brief)
    if fallback_policy == "stitch_required":
        report = _critique_report(
            brief,
            [
                {
                    **variant,
                    "accepted": False,
                    "rejection_reasons": _dedupe(
                        [
                            *(variant.get("rejection_reasons") or []),
                            "Google Stitch is required for frontend handoff; local fallback is supporting evidence only.",
                        ]
                    ),
                }
                for variant in critique.get("variants") or []
            ],
            selected=None,
            status=str(generation.get("status") or "blocked"),
            summary=(
                f"{generation.get('summary') or reason or 'Stitch generation failed.'} "
                "Local style-memory fallback was drafted as supporting evidence only; Google Stitch must succeed before Friday can hand off or implement the UI."
            ),
            frontend_handoff_allowed=False,
            generation=generation,
        )
        report = {
            **report,
            "provider_fallback": "local_style_memory_supporting_only",
            "source_provider": "local_style_memory_supporting_only",
            "provider_source": "local_style_memory_supporting_only",
            "stitch_required": True,
            "stitch_fallback_policy": fallback_policy,
            "stitch_generation": generation,
            "stitch_critique": source_critique or {},
        }
        artifacts = _write_design_critique_artifacts(design_root, report)
        return {
            "ok": False,
            "status": report.get("status"),
            "provider": "design_critique_loop",
            "summary": report.get("summary"),
            "brief": brief,
            "generation": generation,
            "variant_count": count,
            "frontend_handoff_allowed": False,
            "artifacts": [*(generation.get("artifacts") or []), *artifacts],
            **report,
        }
    if not _stitch_policy_allows_fallback(fallback_policy):
        return None
    fallback_summary = (
        f"{generation.get('summary') or reason or 'Stitch generation failed.'} "
        f"Used local style-memory fallback under {fallback_policy}; {critique.get('summary') or 'no variant selected'}"
    )
    critique = {
        **critique,
        "summary": _clean(fallback_summary),
        "generation_status": generation.get("status") or "failed",
        "provider_fallback": "local_style_memory",
        "source_provider": "local_style_memory",
        "provider_source": "local_style_memory",
        "fallback_label": "This design came from local style-memory fallback, not Google Stitch.",
        "stitch_generation": generation,
        "stitch_critique": source_critique or {},
        "stitch_required": False,
        "stitch_fallback_policy": fallback_policy,
    }
    artifacts = _write_design_critique_artifacts(design_root, critique)
    return {
        "ok": bool(critique.get("frontend_handoff_allowed")),
        "status": critique.get("status"),
        "provider": "design_critique_loop",
        "summary": critique.get("summary"),
        "brief": brief,
        "generation": generation,
        "variant_count": count,
        "frontend_handoff_allowed": bool(critique.get("frontend_handoff_allowed")),
        "artifacts": [*(generation.get("artifacts") or []), *artifacts],
        **critique,
    }


def _stitch_fallback_policy(brief: dict[str, Any] | None = None) -> str:
    raw = _clean(config_value("design_stitch_fallback_policy", "")).lower().replace("-", "_")
    aliases = {
        "required": "stitch_required",
        "stitch_required": "stitch_required",
        "stitch_only": "stitch_required",
        "preferred": "stitch_preferred",
        "stitch_preferred": "stitch_preferred",
        "fallback": "fallback_allowed",
        "fallback_allowed": "fallback_allowed",
        "allow_fallback": "fallback_allowed",
    }
    if raw in aliases:
        return aliases[raw]
    if _stitch_required_for_frontend(brief or {}):
        return "stitch_required"
    if bool(config_value("design_local_fallback_on_stitch_failure", True)):
        return "stitch_preferred"
    return "stitch_required"


def _stitch_policy_allows_fallback(policy: str) -> bool:
    return _clean(policy).lower() in {"stitch_preferred", "fallback_allowed"}


def _stitch_required_for_frontend(brief: dict[str, Any]) -> bool:
    if not bool(config_value("design_stitch_required_for_web", True)):
        return False
    stack = brief.get("stack") if isinstance(brief.get("stack"), dict) else {}
    stack_id = _clean(stack.get("stack") or stack.get("kind") or "").lower()
    if stack_id not in {"nextjs", "web", "web-app", "frontend"}:
        return False
    return True


def _local_fallback_design_variants(brief: dict[str, Any], count: int, *, reason: str = "") -> list[dict[str, Any]]:
    request = _clean(brief.get("request"))
    product_name = _clean(brief.get("product_name")) or "Friday Product"
    domain = _fallback_domain(request)
    renderer = _local_developer_fallback_html if domain.get("mode") == "developer_tool" else _local_fallback_html
    variants = [
        {
            "id": "local-command-center",
            "label": "Local command center",
            "html": renderer(product_name, domain, "Command center", domain["primary_focus"], reason),
        },
        {
            "id": "local-workflow-board",
            "label": "Local workflow board",
            "html": renderer(product_name, domain, "Workflow board", domain["secondary_focus"], reason),
        },
        {
            "id": "local-risk-briefing",
            "label": "Local risk briefing",
            "html": renderer(product_name, domain, "Risk briefing", domain["tertiary_focus"], reason),
        },
    ]
    return variants[: _variant_count(count)]


def _fallback_domain(request: str) -> dict[str, Any]:
    raw_text = str(request or "").lower()
    text = _domain_decision_text(raw_text)
    if _developer_fallback_request(raw_text):
        return {
            "mode": "developer_tool",
            "eyebrow": "Self-hosted backend forge",
            "summary": "Ship auth, schema, API routes, realtime workflows, AI agents, plugin modules, Base/Web3 actions, x402 monetization, CLI install, and docs without surrendering code-level control.",
            "primary_focus": "schema, auth, and API route generation",
            "secondary_focus": "AI agents, Web3 modules, and marketplace plugins",
            "tertiary_focus": "self-hosting, managed cloud, docs, and pricing",
            "nav": ["Product", "AI + Web3", "Marketplace", "Self-hosting", "Pricing", "Docs"],
            "metrics": [("CLI install", "npx init"), ("API route", "GET /v1/agents/process"), ("module", "Base wallet")],
            "rows": [
                ("Auth + database", "Ready", "Inspect schema", "Self-hosted"),
                ("AI agent route", "Generated", "Open endpoint", "API proof"),
                ("Web3 module", "Active", "Review wallet action", "Base chain"),
                ("Plugin registry", "Reviewing", "Publish module", "Marketplace"),
            ],
            "terminal": [
                "npx nexus-forge init",
                "schema User { id uuid @primary }",
                "GET /v1/agents/process",
                "web3 module active: Base wallet transaction",
            ],
        }
    if _robotics_logistics_request(text):
        return {
            "mode": "robotics_logistics",
            "eyebrow": "Warehouse robotics operations center",
            "summary": "Coordinate robot fleet health, route optimization, exception queues, pick waves, dock congestion, inventory handoffs, throughput risk, and human override decisions in one operational view.",
            "primary_focus": "robot fleet routing and exception triage",
            "secondary_focus": "throughput, pick waves, dock flow, and inventory handoff",
            "tertiary_focus": "robot health, uptime risk, human overrides, and facility proof",
            "nav": ["Platform", "Robotics Network", "Exceptions", "Throughput", "Contact"],
            "metrics": [("active robots", "128"), ("exception rate", "2.4%"), ("orders/hour", "3.8k")],
            "rows": [
                ("Robot fleet routing", "Live", "Rebalance zone", "Route density"),
                ("Pick-wave backlog", "Elevated", "Open wave plan", "Fulfillment risk"),
                ("Dock congestion", "Watch", "Shift robot flow", "Inbound delay"),
                ("Human override queue", "Ready", "Review exception", "Safety proof"),
            ],
        }
    if any(term in text for term in ("field service", "hvac", "plumbing", "electrical", "technician", "dispatch")):
        return {
            "eyebrow": "Field service dispatch command center",
            "summary": "Dispatch incoming jobs, technician availability, emergency calls, parts readiness, SLA risk, customer updates, and invoice handoff from one operational board.",
            "primary_focus": "same-day emergency dispatch",
            "secondary_focus": "technician capacity and route changes",
            "tertiary_focus": "SLA risk, parts blockers, customer ETA, and invoice closeout",
            "nav": ["Dispatch", "Technicians", "Parts", "SLA", "Invoices", "Customers"],
            "metrics": [("urgent jobs", "14"), ("technicians available", "8"), ("parts blockers", "3")],
            "rows": [
                ("Emergency dispatch queue", "High", "Assign technician", "SLA risk"),
                ("Technician capacity board", "Live", "Rebalance route", "Availability"),
                ("Parts readiness check", "Blocked", "Confirm inventory", "Invoice risk"),
                ("Customer ETA updates", "Ready", "Send update", "Customer comms"),
            ],
        }
    if any(term in text for term in ("university", "registrar", "student", "course", "lecturer", "fee")):
        return {
            "eyebrow": "University operations command center",
            "summary": "Coordinate registrar queues, student issue triage, course allocation, lecturer workload, fee exceptions, approvals, SLA risk, and audit trail.",
            "primary_focus": "registrar and student triage",
            "secondary_focus": "course allocation and lecturer workload",
            "tertiary_focus": "fee exceptions, approvals, SLA risk, and audit evidence",
            "nav": ["Registrar", "Students", "Courses", "Fees", "Lecturers", "Audit"],
            "metrics": [("student cases", "42"), ("course conflicts", "7"), ("fee exceptions", "5")],
            "rows": [
                ("Registrar queue", "High", "Review case", "Student SLA"),
                ("Course allocation", "Live", "Resolve conflict", "Department"),
                ("Fee exception", "Blocked", "Approve waiver", "Finance"),
                ("Lecturer workload", "Ready", "Balance load", "Academic office"),
            ],
        }
    keywords = _keywords(request)[:8] or ["operations", "workflow", "approval", "risk", "customer", "team"]
    return {
        "eyebrow": "Operations command center",
        "summary": f"Coordinate {', '.join(keywords[:5])}, owners, statuses, risks, approvals, customer updates, and proof without hiding gaps.",
        "primary_focus": "live operational triage",
        "secondary_focus": "owner handoffs and approvals",
        "tertiary_focus": "risk, status updates, and proof",
        "nav": ["Overview", "Queue", "Owners", "Approvals", "Risks", "Proof"],
        "metrics": [("open items", "18"), ("blocked handoffs", "4"), ("ready updates", "9")],
        "rows": [
            ("Operational queue", "High", "Assign owner", "Risk"),
            ("Approval lane", "Live", "Review request", "Governance"),
            ("Customer update", "Ready", "Draft message", "Communication"),
            ("Proof report", "Tracked", "Open evidence", "Verification"),
        ],
    }


def _local_fallback_html(product_name: str, domain: dict[str, Any], variant_label: str, focus: str, reason: str) -> str:
    nav = "".join(f"<a href='#{_slug(item)}'>{item}</a>" for item in domain["nav"])
    metrics = "".join(f"<article><strong>{value}</strong><span>{label}</span></article>" for label, value in domain["metrics"])
    rows = "".join(
        f"<tr><td>{name}</td><td>{status}</td><td><button type='button'>{action}</button></td><td>{signal}</td></tr>"
        for name, status, action, signal in domain["rows"]
    )
    return f"""
    <main aria-label="{product_name}">
      <aside aria-label="Product navigation"><h2>{product_name}</h2><nav>{nav}</nav></aside>
      <section aria-labelledby="hero-title">
        <p>{domain['eyebrow']}</p>
        <h1 id="hero-title">{product_name}</h1>
        <p>{domain['summary']}</p>
        <button type="button">Open {focus}</button>
      </section>
      <section aria-label="Operational metrics">{metrics}</section>
      <section aria-labelledby="board-title">
        <h2 id="board-title">{variant_label}: {focus}</h2>
        <table>
          <thead><tr><th>Lane</th><th>Status</th><th>Action</th><th>Signal</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </section>
      <section aria-label="Design proof">
        <h2>Design proof and constraints</h2>
        <p>Implementation evidence, quality gates, and unresolved provider notes stay attached in Friday's proof report.</p>
        <button type="button">Review evidence</button>
        <button type="button">Rerun design critique</button>
      </section>
    </main>
    """


def _local_developer_fallback_html(product_name: str, domain: dict[str, Any], variant_label: str, focus: str, reason: str) -> str:
    nav = "".join(f"<a href='#{_slug(item)}'>{item}</a>" for item in domain["nav"])
    terminal = "\n".join(domain.get("terminal") or [])
    module_cards = "".join(f"<article><strong>{value}</strong><span>{label}</span></article>" for label, value in domain["metrics"])
    rows = "".join(
        f"<tr><td>{name}</td><td>{status}</td><td><button type='button'>{action}</button></td><td>{signal}</td></tr>"
        for name, status, action, signal in domain["rows"]
    )
    return f"""
    <main aria-label="{product_name}">
      <header>
        <h2>{product_name}</h2>
        <nav>{nav}</nav>
        <a href="#docs">Docs</a>
        <a href="#pricing">Start building</a>
      </header>
      <section id="product" aria-labelledby="hero-title">
        <p>{domain['eyebrow']}</p>
        <h1 id="hero-title">Build the backend your AI app needs without giving up control.</h1>
        <p>{domain['summary']}</p>
        <a href="#docs">Start building</a>
        <a href="#marketplace">View modules</a>
        <pre aria-label="CLI quickstart"><code>{terminal}</code></pre>
      </section>
      <section id="ai-web3" aria-label="Backend proof cards">{module_cards}</section>
      <section id="marketplace" aria-labelledby="module-title">
        <h2 id="module-title">{variant_label}: {focus}</h2>
        <table>
          <thead><tr><th>Primitive</th><th>Status</th><th>Action</th><th>Proof</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </section>
      <section id="self-hosting" aria-labelledby="hosting-title">
        <h2 id="hosting-title">Self-host first, cloud when it earns trust.</h2>
        <p>Run locally, inspect the generated schema and API routes, then move to managed infrastructure only when monitoring, compliance, and pricing are clear.</p>
      </section>
      <section id="pricing" aria-label="Pricing">
        <article><h2>Open Source</h2><strong>$0</strong><p>Self-hosted backend, local database, basic auth, and community plugins.</p></article>
        <article><h2>Pro</h2><strong>$29/mo</strong><p>Managed hosting, realtime WebSockets, Web3 modules, monitoring, and priority plugin review.</p></article>
        <article><h2>Enterprise</h2><strong>Custom</strong><p>Dedicated clusters, private plugin registry, compliance support, and SLA guarantees.</p></article>
      </section>
      <section id="docs" aria-label="Docs and proof">
        <h2>Docs that start with the CLI.</h2>
        <p>Installation, route examples, schema contracts, deployment states, and module proof stay visible before the first integration call.</p>
        <a href="#product">Copy install command</a>
      </section>
    </main>
    """


def _write_design_critique_artifacts(design_root: Path, report: dict[str, Any]) -> list[str]:
    design_root.mkdir(parents=True, exist_ok=True)
    report_to_write = dict(report)
    selected = dict(report_to_write.get("selected_variant") or {}) if isinstance(report_to_write.get("selected_variant"), dict) else {}
    selected_html = design_root / "selected-design.html"
    if selected and report_to_write.get("frontend_handoff_allowed"):
        html = _variant_html(selected)
        if html:
            selected_html.write_text(html, encoding="utf-8")
            selected["html_path"] = str(selected_html)
            report_to_write["selected_variant"] = selected
            variants = []
            for variant in report_to_write.get("variants") or []:
                if isinstance(variant, dict) and variant.get("id") == selected.get("id"):
                    variants.append({**variant, "html_path": str(selected_html)})
                else:
                    variants.append(variant)
            report_to_write["variants"] = variants
    report_json = design_root / "design-critique-report.json"
    report_md = design_root / "design-critique-report.md"
    report_json.write_text(json.dumps(report_to_write, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    report_md.write_text(_critique_markdown(report_to_write), encoding="utf-8")
    written = [str(report_json), str(report_md)]
    if selected and report_to_write.get("frontend_handoff_allowed"):
        handoff_json = design_root / "frontend-handoff.json"
        handoff_md = design_root / "frontend-handoff.md"
        handoff_json.write_text(json.dumps(_frontend_handoff_payload(report_to_write), ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        handoff_md.write_text(_frontend_handoff_markdown(report_to_write), encoding="utf-8")
        written.extend([str(handoff_json), str(handoff_md)])
        if selected_html.exists():
            written.append(str(selected_html))
    else:
        for stale in ("frontend-handoff.json", "frontend-handoff.md", "selected-design.html", "applied-design.json"):
            try:
                (design_root / stale).unlink(missing_ok=True)
            except Exception:
                pass
    return written


def _critique_markdown(report: dict[str, Any]) -> str:
    selected = report.get("selected_variant") if isinstance(report.get("selected_variant"), dict) else {}
    lines = [
        "# Design Critique Report",
        "",
        f"Status: {report.get('status') or 'unknown'}",
        f"Summary: {report.get('summary') or ''}",
        f"Score threshold: {report.get('score_threshold')}",
        f"Frontend handoff allowed: {bool(report.get('frontend_handoff_allowed'))}",
        f"Frontend handoff required: {bool(report.get('frontend_handoff_required'))}",
        "",
        "## Selected Variant",
    ]
    if selected:
        lines.extend(
            [
                f"- ID: {selected.get('id')}",
                f"- Label: {selected.get('label')}",
                f"- Score: {selected.get('score')}/100",
                f"- HTML: {selected.get('html_path') or selected.get('htmlUrl') or 'not attached'}",
                f"- Image: {selected.get('image_path') or selected.get('imageUrl') or 'not attached'}",
            ]
        )
    else:
        lines.append("- None.")
    lines.extend(["", "## Variants"])
    for variant in report.get("variants") or []:
        reasons = "; ".join(variant.get("rejection_reasons") or []) or "accepted"
        lines.append(f"- {variant.get('label') or variant.get('id')}: {variant.get('score')}/100 - {reasons}")
    return "\n".join(lines) + "\n"


def _frontend_handoff_payload(report: dict[str, Any]) -> dict[str, Any]:
    selected = report.get("selected_variant") if isinstance(report.get("selected_variant"), dict) else {}
    return {
        "selected_variant_id": selected.get("id"),
        "selected_variant_label": selected.get("label"),
        "score": selected.get("score"),
        "html_path": selected.get("html_path"),
        "image_path": selected.get("image_path"),
        "html_url": selected.get("htmlUrl"),
        "image_url": selected.get("imageUrl"),
        "design_context": report.get("design_context") or {},
        "design_strategy": report.get("design_strategy") or {},
        "instructions": [
            "Convert only this selected design into frontend code.",
            "Do not use rejected variants as implementation source material.",
            "Keep routes thin and split feature UI, services, state, hooks, lib, and types according to the active style profile.",
            "Preserve product-specific copy unless a later user or UX gate changes it.",
            "Run browser, accessibility, dead-button, and product-fit gates after conversion.",
        ],
        "rejected_variant_ids": [variant.get("id") for variant in report.get("rejected_variants") or []],
    }


def _frontend_handoff_markdown(report: dict[str, Any]) -> str:
    payload = _frontend_handoff_payload(report)
    selected = report.get("selected_variant") if isinstance(report.get("selected_variant"), dict) else {}
    criteria = selected.get("criteria") if isinstance(selected.get("criteria"), list) else []
    context = payload.get("design_context") if isinstance(payload.get("design_context"), dict) else {}
    content = context.get("content_model") if isinstance(context.get("content_model"), dict) else {}
    return "\n".join(
        [
            "# Frontend Design Handoff",
            "",
            f"Selected variant: {payload.get('selected_variant_label') or payload.get('selected_variant_id')}",
            f"Score: {payload.get('score')}/100",
            f"HTML artifact: {payload.get('html_path') or payload.get('html_url') or 'not attached'}",
            f"Screenshot artifact: {payload.get('image_path') or payload.get('image_url') or 'not attached'}",
            "",
            "## Conversion Rules",
            *[f"- {item}" for item in payload["instructions"]],
            "",
            "## Design Context",
            f"- Product goal: {context.get('product_goal') or 'not recorded'}",
            f"- Audience: {', '.join(context.get('target_audience') or []) or 'not recorded'}",
            f"- Emotional feel: {context.get('emotional_intent') or 'not recorded'}",
            f"- Navigation: {', '.join(content.get('navigation') or []) or 'not recorded'}",
            f"- Proof objects: {', '.join(content.get('proof_objects') or []) or 'not recorded'}",
            "",
            "## Scorecard",
            *[f"- {item.get('id')}: {item.get('score')}/{item.get('weight')} - {item.get('label')}" for item in criteria],
            "",
        ]
    )


def _sanitize_selected_design_document(html: str) -> str:
    text = str(html or "")
    text = re.sub(r"\s+on[a-zA-Z]+\s*=\s*(['\"]).*?\1", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"javascript\s*:", "", text, flags=re.IGNORECASE)

    def keep_safe_script(match: re.Match[str]) -> str:
        attrs = match.group(1) or ""
        tag = match.group(0)
        lowered = attrs.lower()
        if "cdn.tailwindcss.com" in lowered or "tailwind-config" in lowered:
            return tag
        return ""

    text = re.sub(r"<script\b([^>]*)>.*?</script>", keep_safe_script, text, flags=re.IGNORECASE | re.DOTALL)
    if "<html" not in text.lower():
        text = f"<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"/><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/></head><body>{text}</body></html>"
    return text.strip()


def _selected_design_page_payload(
    page_id: str,
    route: str,
    label: str,
    html: str,
    *,
    handoff: dict[str, Any],
    product_name: str,
) -> dict[str, Any]:
    parts = _selected_design_parts(html)
    return {
        "id": _clean_page_id(page_id),
        "route": route,
        "label": label,
        "title": _clean(product_name) or _clean(handoff.get("selected_variant_label")) or label,
        "document_html": parts["document_html"],
        "body_html": parts["body_html"],
        "style_html": parts["style_html"],
        "tailwind_config": parts["tailwind_config"],
        "uses_tailwind_cdn": parts["uses_tailwind_cdn"],
        "imports_css": parts["imports_css"],
        "selected_variant_id": handoff.get("selected_variant_id"),
        "selected_variant_label": handoff.get("selected_variant_label"),
        "score": handoff.get("score"),
    }


def _selected_design_parts(html: str) -> dict[str, Any]:
    document = _sanitize_selected_design_document(html)
    body_match = re.search(r"<body\b[^>]*>(.*?)</body>", document, flags=re.IGNORECASE | re.DOTALL)
    body_html = body_match.group(1) if body_match else document
    style_html = "\n".join(match.group(1) for match in re.finditer(r"<style\b[^>]*>(.*?)</style>", document, flags=re.IGNORECASE | re.DOTALL))
    stylesheet_imports: list[str] = []
    for match in re.finditer(r"<link\b([^>]+)>", document, flags=re.IGNORECASE | re.DOTALL):
        attrs = match.group(1)
        if not re.search(r"rel\s*=\s*(['\"])stylesheet\1", attrs, flags=re.IGNORECASE):
            continue
        href_match = re.search(r"href\s*=\s*(['\"])(.*?)\1", attrs, flags=re.IGNORECASE | re.DOTALL)
        if href_match:
            stylesheet_imports.append(f"@import url({json.dumps(href_match.group(2), ensure_ascii=True)});")
    tailwind_config = ""
    uses_tailwind_cdn = bool(re.search(r"cdn\.tailwindcss\.com", document, flags=re.IGNORECASE))
    config_match = re.search(r"<script\b[^>]*id\s*=\s*(['\"])tailwind-config\1[^>]*>(.*?)</script>", document, flags=re.IGNORECASE | re.DOTALL)
    if config_match:
        tailwind_config = _safe_tailwind_config_script(config_match.group(2))
    body_html = re.sub(r"<script\b[^>]*>.*?</script>", "", body_html, flags=re.IGNORECASE | re.DOTALL)
    body_html = re.sub(r"<style\b[^>]*>.*?</style>", "", body_html, flags=re.IGNORECASE | re.DOTALL)
    body_html = re.sub(r"<link\b[^>]*>", "", body_html, flags=re.IGNORECASE | re.DOTALL)
    return {
        "document_html": document,
        "body_html": _normalize_stitch_html_scale(body_html).strip(),
        "style_html": "\n".join([*stylesheet_imports, style_html, _stitch_scale_normalizer_css()]).strip(),
        "tailwind_config": tailwind_config,
        "uses_tailwind_cdn": uses_tailwind_cdn,
        "imports_css": stylesheet_imports,
    }


def _safe_tailwind_config_script(script: str) -> str:
    cleaned = re.sub(r"</script", "", str(script or ""), flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(fetch|XMLHttpRequest|localStorage|sessionStorage|document\.cookie)\b.*", "", cleaned)
    if "tailwind.config" in cleaned and "window.tailwind" not in cleaned:
        cleaned = "window.tailwind = window.tailwind || {};\n" + cleaned
    return cleaned.strip()


def _normalize_stitch_html_scale(html: str) -> str:
    text = str(html or "")
    replacements = {
        "tracking-[-0.02em]": "tracking-normal",
        "tracking-[-0.01em]": "tracking-normal",
        "text-display-lg-mobile": "text-4xl",
        "md:text-display-lg": "md:text-6xl",
        "text-display-lg": "text-5xl",
        "text-9xl": "text-6xl",
        "text-8xl": "text-6xl",
        "md:text-9xl": "md:text-6xl",
        "md:text-8xl": "md:text-6xl",
        "py-40": "py-24",
        "py-36": "py-24",
        "py-32": "py-24",
        "md:py-40": "md:py-28",
        "md:py-36": "md:py-28",
        "md:py-32": "md:py-28",
        "py-section-padding-desktop": "py-24",
        "md:py-section-padding-desktop": "md:py-28",
        "py-section-padding-mobile": "py-16",
        "px-gutter": "px-6",
        "gap-gutter": "gap-8",
    }
    for before, after in replacements.items():
        text = text.replace(before, after)
    text = re.sub(r"text-\[(7[2-9]|8[0-9]|9[0-9]|1[0-9]{2,})px\]", "text-6xl", text)
    text = re.sub(r"py-\[(1[6-9][0-9]|[2-9][0-9]{2,})px\]", "py-24", text)
    text = re.sub(r"gap-\[(8[0-9]|[1-9][0-9]{2,})px\]", "gap-10", text)
    text = re.sub(r"(font-size\s*:\s*)(?:7[2-9]|8[0-9]|9[0-9]|1[0-9]{2,})px", r"\g<1>64px", text, flags=re.IGNORECASE)
    return text


def _apply_design_pages_to_nextjs(
    project_root: Path,
    pages: list[dict[str, Any]],
    *,
    request: str,
    product_name: str,
) -> dict[str, Any]:
    support_written = _ensure_nextjs_project_shell(project_root, product_name, request)
    content = _native_content_from_design_pages(pages, request=request, product_name=product_name)
    content = _localize_native_visuals(content, project_root)
    stitch_document_routes = _write_stitch_document_public_files(project_root, content)
    native_content_path = project_root / "src" / "lib" / "stitchNativeContent.ts"
    compatibility_path = project_root / "src" / "lib" / "stitchDesignPages.ts"
    native_component_path = project_root / "src" / "components" / "Stitch" / "StitchNativePage.tsx"
    css_path = project_root / "src" / "components" / "Stitch" / "StitchNativePage.module.css"
    component_path = project_root / "src" / "components" / "Stitch" / "StitchPageSurface.tsx"
    legacy_component_path = project_root / "src" / "components" / "Stitch" / "StitchDesignSurface.tsx"
    for path in (native_content_path, compatibility_path, native_component_path, css_path, component_path, legacy_component_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    native_content_path.write_text(_stitch_native_content_module(content), encoding="utf-8")
    compatibility_path.write_text(_stitch_design_pages_compat_module(), encoding="utf-8")
    native_component_path.write_text(_stitch_native_page_component(), encoding="utf-8")
    css_path.write_text(_stitch_native_page_css(), encoding="utf-8")
    component_path.write_text(_stitch_page_surface_component(), encoding="utf-8")
    legacy_component_path.write_text(_stitch_legacy_component(), encoding="utf-8")
    written = [*support_written, *stitch_document_routes.values(), str(native_content_path), str(compatibility_path), str(native_component_path), str(css_path), str(component_path), str(legacy_component_path)]
    for page in pages:
        route_path = _next_route_path(project_root, page["route"])
        route_path.parent.mkdir(parents=True, exist_ok=True)
        route_path.write_text(_stitch_page_module(page["id"]), encoding="utf-8")
        written.append(str(route_path))
    return {"ok": True, "files": written}


def _write_stitch_document_public_files(project_root: Path, content: dict[str, Any]) -> dict[str, str]:
    pages = content.get("pages") if isinstance(content.get("pages"), dict) else {}
    public_routes: dict[str, str] = {}
    public_root = project_root / "public" / "friday-stitch"
    for page_id, page in pages.items():
        if not isinstance(page, dict):
            continue
        if not _clean(page.get("documentHtml")):
            continue
        safe_id = _clean_page_id(str(page_id))
        public_root.mkdir(parents=True, exist_ok=True)
        html_path = public_root / f"{safe_id}.html"
        html_path.write_text(str(page.get("documentHtml") or ""), encoding="utf-8")
        public_routes[safe_id] = f"/friday-stitch/{safe_id}.html"
    return public_routes


def _ensure_nextjs_project_shell(project_root: Path, product_name: str, request: str) -> list[str]:
    """Make a Stitch handoff runnable as a standalone Next.js project."""

    stack = {"stack": "nextjs", "label": "Next.js web app"}
    files = project_scaffolds.files_for_stack(stack, _clean(product_name) or project_root.name, request)
    written: list[str] = []
    for relative, content in files.items():
        path = project_root / relative
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(str(path))
    return written


class _HtmlNode:
    def __init__(self, tag: str, attrs: list[tuple[str, str | None]] | None = None) -> None:
        self.tag = tag.lower()
        self.attrs = {str(key).lower(): str(value or "") for key, value in (attrs or [])}
        self.children: list["_HtmlNode"] = []
        self.text: list[str] = []


class _DesignHtmlParser(HTMLParser):
    _VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _HtmlNode("document")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _HtmlNode(tag, attrs)
        self.stack[-1].children.append(node)
        if tag.lower() not in self._VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.stack[-1].children.append(_HtmlNode(tag, attrs))

    def handle_endtag(self, tag: str) -> None:
        target = tag.lower()
        while len(self.stack) > 1:
            node = self.stack.pop()
            if node.tag == target:
                break

    def handle_data(self, data: str) -> None:
        text = _clean(unescape(data))
        if text:
            self.stack[-1].text.append(text)


def _native_content_from_design_pages(pages: list[dict[str, Any]], *, request: str, product_name: str) -> dict[str, Any]:
    native_pages: dict[str, Any] = {}
    nav: list[dict[str, str]] = []
    site_routes = _site_route_context_for_design_pages(pages, request)
    for page in pages:
        root = _parse_html_fragment(str(page.get("body_html") or ""))
        if not nav:
            nav = _extract_nav(root, product_name=product_name, site_routes=site_routes)
        native_pages[str(page["id"])] = _native_page_from_tree(page, root, product_name=product_name, request=request, site_routes=site_routes)
    if not nav:
        nav = [{"label": item["label"], "href": item["route"]} for item in _website_page_specs(request)]
    primary_action = _primary_native_action(native_pages, request)
    return {
        "meta": {
            "productName": _clean(product_name) or _product_name_from_request(request) or "Friday Website",
            "request": _clean(request),
            "source": "google_stitch_selected_design",
            "implementation": "native_react_components",
            "scalePolicy": "Use Stitch visual direction, but normalize exaggerated type, spacing, and layout scale for production UI.",
            "nav": nav[:6],
            "primaryAction": primary_action,
        },
        "pages": native_pages,
    }


def _parse_html_fragment(fragment: str) -> _HtmlNode:
    parser = _DesignHtmlParser()
    try:
        parser.feed(fragment or "")
        parser.close()
    except Exception:
        pass
    return parser.root


def _native_page_from_tree(
    page: dict[str, Any],
    root: _HtmlNode,
    *,
    product_name: str,
    request: str = "",
    site_routes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    page_id = _clean_page_id(page.get("id") or "home")
    page_label = _clean(page.get("label")) or page_id.title()
    body_html = _normalize_fidelity_body_html(str(page.get("body_html") or ""), request=request, site_routes=site_routes)
    document_html = _sanitize_selected_design_document(str(page.get("document_html") or ""))
    style_html = str(page.get("style_html") or "")
    tailwind_config = str(page.get("tailwind_config") or "")
    uses_tailwind_cdn = bool(page.get("uses_tailwind_cdn"))
    raw_html_support = _stitch_raw_html_support(body_html, style_html, tailwind_config, uses_tailwind_cdn=uses_tailwind_cdn)
    if _clean(body_html) and raw_html_support["supported"]:
        render_mode = "stitch_html"
    else:
        render_mode = "native"
    heading = _native_heading_from_tree(root, page_id=page_id, page_label=page_label, product_name=product_name)
    heading = heading or _clean(page.get("title")) or _fallback_page_heading(page_id, page_label, product_name)
    paragraphs = _texts_by_tag(root, ("p",), limit=12)
    summary = _first_meaningful(paragraphs) or _trim(_node_text(root), 220) or f"{_clean(product_name)} {page.get('label')} page."
    sections = _native_sections(root, fallback_title=heading, page_label=page_label, summary=summary)
    actions = _native_actions(root, product_name=product_name, site_routes=site_routes, request=request)
    visuals = _native_visuals(root)
    return {
        "id": page_id,
        "kind": "contact" if page_id == "contact" else "website",
        "label": page_label,
        "kicker": _native_page_kicker(page_id, page_label),
        "route": _clean(page.get("route")) or "/",
        "score": int(page.get("score") or 0),
        "title": _trim(heading, 96),
        "summary": _trim(summary, 260),
        "actions": actions[:3] or _fallback_native_actions(request, page_id),
        "visuals": visuals[:2],
        "proof": _native_proof_panel(request, product_name, sections, summary),
        "sections": sections[:6],
        "renderMode": render_mode,
        "documentHtml": document_html,
        "bodyHtml": body_html,
        "styleHtml": style_html,
        "tailwindConfig": tailwind_config,
        "usesTailwindCdn": uses_tailwind_cdn,
        "rawHtmlSupport": raw_html_support,
    }


def _native_heading_from_tree(root: _HtmlNode, *, page_id: str, page_label: str, product_name: str) -> str:
    brand = _clean(product_name)
    for heading in _texts_by_tag(root, ("h1", "h2"), limit=8):
        candidate = _clean(heading)
        if not candidate:
            continue
        if _is_route_label_heading(candidate, page_label, brand):
            continue
        return candidate
    return _fallback_page_heading(page_id, page_label, brand)


def _is_route_label_heading(heading: str, page_label: str, product_name: str) -> bool:
    text = _clean(heading).lower()
    label = _clean(page_label).lower()
    brand = _clean(product_name).lower()
    if not text or not label:
        return False
    if text == label:
        return True
    if brand and text == f"{brand} {label}":
        return True
    if re.fullmatch(rf"{re.escape(label)}\s+\d+", text):
        return True
    return False


def _fallback_page_heading(page_id: str, page_label: str, product_name: str) -> str:
    brand = _clean(product_name) or "Website"
    normalized = _clean_page_id(page_id)
    if normalized == "home":
        return brand
    if normalized == "about":
        return f"About {brand}"
    if normalized == "services":
        return f"Services for {brand}"
    if normalized == "pricing":
        return f"Pricing for {brand}"
    if normalized == "contact":
        return f"Contact {brand}"
    if normalized == "atelier":
        return f"Inside the {brand} Atelier"
    if normalized == "collections":
        return f"{brand} Collections"
    return f"{_clean(page_label) or normalized.title()} for {brand}"


def _native_page_kicker(page_id: str, page_label: str) -> str:
    normalized = _clean_page_id(page_id)
    if normalized == "home":
        return ""
    labels = {
        "about": "Company",
        "services": "Capabilities",
        "pricing": "Plans",
        "contact": "Inquiry",
        "atelier": "Atelier",
        "collections": "Collections",
    }
    return labels.get(normalized, _clean(page_label))


def _native_sections(root: _HtmlNode, *, fallback_title: str, page_label: str, summary: str) -> list[dict[str, Any]]:
    section_nodes = [node for node in _descendants(root) if node.tag == "section"]
    sections: list[dict[str, Any]] = []
    skipped_redundant = False
    for index, node in enumerate(section_nodes[:8], start=1):
        text = _node_text(node)
        if len(text) < 40:
            continue
        section_index = len(sections) + 1
        title = _clean_section_title(_first_text(node, ("h2", "h3", "h1")), page_label, section_index)
        body = _first_meaningful(_texts_by_tag(node, ("p",), limit=5), exclude={summary, title}) or _trim(text, 220)
        cards = _native_cards(node)
        points = _native_points(node)
        if _redundant_hero_section(title, body, fallback_title, summary):
            skipped_redundant = True
            continue
        sections.append(
            {
                "label": _section_label(title, page_label, len(sections) + 1),
                "title": _trim(title, 90),
                "body": _trim(body, 280),
                "cards": cards[:6],
                "points": points[:8],
            }
        )
    if not sections and not skipped_redundant:
        sections.append(
            {
                "label": _section_label(fallback_title, page_label, 1),
                "title": _trim(fallback_title, 90),
                "body": _trim(summary, 280),
                "cards": [],
                "points": _native_points(root)[:6],
            }
        )
    return sections


def _redundant_hero_section(title: str, body: str, fallback_title: str, summary: str) -> bool:
    if _similar(title, fallback_title):
        return True
    return bool(_similar(body, summary) and len(_clean(body)) > 60)


def _clean_section_title(title: str, page_label: str, index: int) -> str:
    title = _clean(title)
    label = _clean(page_label)
    lowered = title.lower()
    label_lower = label.lower()
    route_label_only = (
        not title
        or (label_lower and lowered == label_lower)
        or (label_lower and lowered == f"{label_lower} focus")
        or (label_lower and re.fullmatch(rf"{re.escape(label_lower)}\s+\d+", lowered))
        or re.fullmatch(r"(page|section)\s+\d+", lowered or "")
    )
    if not route_label_only:
        return title
    normalized = _clean_page_id(page_label)
    defaults = {
        "home": ("Proof of scale", "How it works", "Ready for the next project"),
        "about": ("Company foundation", "Leadership and values", "How the team works"),
        "services": ("Core capabilities", "Delivery approach", "Service proof"),
        "pricing": ("Plan structure", "What is included", "Buying path"),
        "contact": ("Project inquiry path", "Response expectations", "Regional support"),
    }
    options = defaults.get(normalized, ("Overview", "Details", "Next steps"))
    return options[min(index - 1, len(options) - 1)]


def _section_label(title: str, page_label: str, index: int) -> str:
    text = _clean(title).lower()
    mapping = [
        (("hero", "headline", "brand", "offer"), "Overview"),
        (("method", "process", "framework", "approach", "workflow"), "Method"),
        (("engineering", "system", "operational foundation"), "Method"),
        (("service", "package", "offer", "solution", "capability"), "Services"),
        (("proof", "result", "case", "client", "testimonial", "impact", "metric"), "Proof"),
        (("story", "about", "value", "mission", "credibility", "trust"), "About"),
        (("contact", "inquiry", "consult", "proposal", "book", "ready to", "get started"), "Inquiry"),
        (("pricing", "plan", "tier"), "Pricing"),
        (("question", "faq"), "FAQ"),
    ]
    for terms, label in mapping:
        if any(term in text for term in terms):
            return label
    cleaned_page = _clean(page_label) or "Section"
    if _clean_page_id(cleaned_page) == "home":
        return "Overview" if index == 1 else "Proof"
    return "Overview" if index == 1 else cleaned_page


def _native_cards(root: _HtmlNode) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    seen_titles: set[str] = set()
    for node in _descendants(root):
        if node.tag not in {"article", "li", "div"}:
            continue
        if node.tag == "div" and (_descendant_tag_count(node, {"h3", "h4", "strong"}) > 1 or _first_text(node, ("h2",))):
            continue
        title = _first_text(node, ("h3", "h4", "strong"))
        if not title:
            continue
        body = _first_meaningful(_texts_by_tag(node, ("p",), limit=3), exclude={title})
        if not body:
            continue
        title_key = _clean(title).lower()
        if title_key in seen_titles:
            continue
        card = {"title": _trim(title, 72), "body": _trim(body, 190)}
        if card not in cards:
            cards.append(card)
            seen_titles.add(title_key)
        if len(cards) >= 8:
            break
    return cards


def _native_points(root: _HtmlNode) -> list[str]:
    points: list[str] = []
    for text in _texts_by_tag(root, ("li",), limit=14):
        trimmed = _trim(text, 120)
        if len(trimmed) >= 8 and trimmed not in points:
            points.append(trimmed)
    return points


def _native_actions(root: _HtmlNode, *, product_name: str = "", site_routes: dict[str, Any] | None = None, request: str = "") -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    excluded_nodes = {
        child
        for container in _descendants(root)
        if container.tag in {"nav"}
        for child in _descendants(container)
    }
    nav_terms = {
        "home", "about", "services", "service", "contact", "privacy", "terms", "linkedin", "instagram",
        "email", "menu", "logo", "search", "share", "mail", "arrow_forward", "arrow_outward", "expand_more",
        "health_and_safety", "eco", "verified",
    }
    brand_label = _clean(product_name).lower()
    brand_tokens = {token.lower() for token in _keywords(product_name) if len(token) >= 4}
    for node in _descendants(root):
        if node.tag not in {"a", "button"}:
            continue
        if node in excluded_nodes:
            continue
        label = _trim(_node_text(node), 56)
        lowered = label.lower()
        if len(label) < 3 or lowered in nav_terms or (brand_label and lowered == brand_label) or lowered in brand_tokens:
            continue
        href = _normalize_design_href(node.attrs.get("href", ""), label, site_routes=site_routes)
        if lowered in seen_labels:
            continue
        action = {"label": label, "href": href, "primary": not actions}
        if action not in actions:
            actions.append(action)
            seen_labels.add(lowered)
        if len(actions) >= 4:
            break
    return actions


def _fallback_native_actions(request: str, page_id: str = "home") -> list[dict[str, Any]]:
    lowered = _clean(request).lower()
    if page_id == "contact" or any(term in lowered for term in ("contact", "inquiry", "book", "proposal", "quote")):
        return [{"label": "Start inquiry", "href": "/contact", "primary": True}]
    if _developer_tools_request(lowered):
        return [
            {"label": "Start building", "href": "#quickstart", "primary": True},
            {"label": "Read docs", "href": "#docs", "primary": False},
        ]
    if any(term in lowered for term in ("dashboard", "command center", "operations", "queue")):
        return [
            {"label": "Open workspace", "href": "/workspace", "primary": True},
            {"label": "Review queue", "href": "#work-queue", "primary": False},
        ]
    return [{"label": "Get started", "href": "#next-step", "primary": True}]


def _primary_native_action(pages: dict[str, Any], request: str) -> dict[str, Any]:
    for page in pages.values():
        if not isinstance(page, dict):
            continue
        for action in page.get("actions") or []:
            if isinstance(action, dict) and action.get("primary"):
                return {"label": _clean(action.get("label")) or "Get started", "href": _clean(action.get("href")) or "#next-step", "primary": True}
    fallback = _fallback_native_actions(request, "home")[0]
    return {"label": fallback["label"], "href": fallback["href"], "primary": True}


def _native_proof_panel(request: str, product_name: str, sections: list[dict[str, Any]], summary: str) -> dict[str, Any]:
    lowered = _clean(request).lower()
    if _developer_tools_request(lowered):
        return {
            "kicker": "Builder proof",
            "title": "Schema, API, and module proof",
            "body": "Show the backend as something builders can inspect, run, and own.",
            "items": ["Auth + database schema", "GET /v1/agents/process", "Web3 module active", "Self-hosted deploy path"],
        }
    if any(term in lowered for term in ("dashboard", "command center", "clinic", "patient", "queue", "operations")):
        return {
            "kicker": "Live operations",
            "title": "Queue, owner, risk, next action",
            "body": "The screen should expose operational pressure before work slips.",
            "items": _dedupe([*_keywords(request)[:4], "SLA risk", "Audit trail"])[:6],
        }
    items: list[str] = []
    for section in sections[:3]:
        if isinstance(section, dict):
            if section.get("title"):
                items.append(_clean(section.get("title")))
            for card in section.get("cards") or []:
                if isinstance(card, dict) and card.get("title"):
                    items.append(_clean(card.get("title")))
    return {
        "kicker": "Proof before claims",
        "title": _clean(product_name) or "Project proof",
        "body": _trim(summary, 160),
        "items": _dedupe([item for item in items if item])[:6],
    }


def _native_visuals(root: _HtmlNode) -> list[dict[str, str]]:
    visuals: list[dict[str, str]] = []
    for node in _descendants(root):
        if node.tag != "img":
            continue
        src = _clean(node.attrs.get("src"))
        if not src:
            continue
        visual = {"src": src, "alt": _trim(_clean(node.attrs.get("alt") or node.attrs.get("data-alt") or "Design visual"), 140)}
        if visual not in visuals:
            visuals.append(visual)
    return visuals


def _localize_native_visuals(content: dict[str, Any], project_root: Path) -> dict[str, Any]:
    pages = content.get("pages") if isinstance(content.get("pages"), dict) else {}
    for page in pages.values():
        if not isinstance(page, dict):
            continue
        if page.get("documentHtml"):
            page["documentHtml"] = _localize_fidelity_body_visuals(str(page.get("documentHtml") or ""), project_root)
        if page.get("bodyHtml"):
            page["bodyHtml"] = _localize_fidelity_body_visuals(str(page.get("bodyHtml") or ""), project_root)
        localized: list[dict[str, str]] = []
        for visual in page.get("visuals") or []:
            if not isinstance(visual, dict):
                continue
            src = _clean(visual.get("src"))
            if not src:
                continue
            if re.match(r"^https?://", src, re.IGNORECASE):
                local_src = _localize_remote_visual(project_root, src)
                if not local_src:
                    continue
                visual = {**visual, "src": local_src}
            localized.append({"src": _clean(visual.get("src")), "alt": _clean(visual.get("alt")) or "Design visual"})
        page["visuals"] = localized[:2]
    return content


def _normalize_fidelity_body_html(html: str, *, request: str, site_routes: dict[str, Any] | None = None) -> str:
    """Keep Stitch layout fidelity while removing raw generator artifacts from inline HTML."""

    text = str(html or "")
    if not text:
        return ""

    text = re.sub(
        r"(<span\b[^>]*class\s*=\s*(['\"])[^'\"]*material-symbols-outlined[^'\"]*\2[^>]*>)(.*?)(</span>)",
        lambda match: f"{match.group(1)}{match.group(4)}",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    def rewrite_anchor(match: re.Match[str]) -> str:
        before = match.group(1) or ""
        quote = match.group(2) or '"'
        href = match.group(3) or ""
        after = match.group(4) or ""
        inner = match.group(5) or ""
        label = _trim(_clean(re.sub(r"<[^>]+>", " ", inner)), 80)
        normalized = _normalize_design_href(href, label, site_routes=site_routes)
        safe_href = escape(normalized, quote=True)
        return f"<a{before} href={quote}{safe_href}{quote}{after}>{inner}</a>"

    text = re.sub(
        r"<a\b([^>]*?)\s+href\s*=\s*(['\"])(.*?)\2([^>]*)>(.*?)</a>",
        rewrite_anchor,
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = _add_missing_button_labels_to_fidelity_html(text)
    return text


def _add_missing_button_labels_to_fidelity_html(html: str) -> str:
    def repl(match: re.Match[str]) -> str:
        open_tag, inner, close_tag = match.group(1), match.group(2), match.group(3)
        if re.search(r"\b(?:aria-label|aria-labelledby|title)\s*=", open_tag, flags=re.IGNORECASE):
            return match.group(0)
        visible_text = _clean(re.sub(r"<[^>]+>", " ", inner))
        if visible_text:
            return match.group(0)
        label = "Open menu" if re.search(r"menu|material-symbols|material-icons|icon", f"{open_tag} {inner}", flags=re.IGNORECASE) else "Button"
        return re.sub(r">$", f' aria-label="{escape(label, quote=True)}">', open_tag) + inner + close_tag

    return re.sub(r"(<button\b[^>]*>)(.*?)(</button>)", repl, str(html or ""), flags=re.IGNORECASE | re.DOTALL)


def _stitch_raw_html_support(body_html: str, style_html: str, tailwind_config: str, *, uses_tailwind_cdn: bool) -> dict[str, Any]:
    """Decide whether raw Stitch HTML can render reliably inside a Next.js app.

    Raw Stitch fidelity is useful when it is self-contained, but it is risky when it
    depends on provider-specific Tailwind design-token classes that the generated
    project has not compiled. In that case Friday should use the normalized native
    React rendering extracted from the same Stitch design instead.
    """

    body = str(body_html or "")
    if not _clean(body):
        return {"supported": False, "reason": "empty_body_html", "custom_utility_tokens": []}
    custom_tokens = _custom_stitch_utility_tokens(body)
    if not custom_tokens:
        return {"supported": True, "reason": "standard_or_self_describing_html", "custom_utility_tokens": []}
    css = f"{style_html}\n{tailwind_config}"
    explicitly_styled = [token for token in custom_tokens if re.search(rf"\.{re.escape(token)}\b", style_html)]
    unresolved = [token for token in custom_tokens if token not in explicitly_styled]
    if not unresolved:
        return {"supported": True, "reason": "custom_classes_have_css_rules", "custom_utility_tokens": custom_tokens}
    if (
        uses_tailwind_cdn
        and _clean(tailwind_config)
        and bool(config_value("design_stitch_allow_runtime_tailwind_fidelity", True))
    ):
        return {
            "supported": True,
            "reason": "runtime_tailwind_config_allowed_for_stitch_fidelity",
            "custom_utility_tokens": custom_tokens[:40],
            "unresolved_tokens": unresolved[:40],
            "uses_tailwind_cdn": True,
            "has_tailwind_config": True,
            "has_style_html": bool(_clean(style_html)),
        }
    return {
        "supported": False,
        "reason": "custom_tailwind_tokens_require_unreliable_runtime_cdn" if uses_tailwind_cdn else "custom_utility_tokens_not_compiled",
        "custom_utility_tokens": custom_tokens[:40],
        "unresolved_tokens": unresolved[:40],
        "uses_tailwind_cdn": uses_tailwind_cdn,
        "has_tailwind_config": bool(_clean(tailwind_config)),
        "has_style_html": bool(_clean(style_html)),
        "css_context_mentions": [token for token in unresolved[:20] if token in css],
    }


def _custom_stitch_utility_tokens(html: str) -> list[str]:
    tokens: list[str] = []
    for class_value in re.findall(r"\bclass\s*=\s*(['\"])(.*?)\1", str(html or ""), flags=re.IGNORECASE | re.DOTALL):
        for raw_token in re.split(r"\s+", class_value[1]):
            token = _clean(raw_token)
            if not token:
                continue
            base = token.split(":")[-1]
            if _is_custom_stitch_utility_token(base) and base not in tokens:
                tokens.append(base)
    return tokens


def _is_custom_stitch_utility_token(token: str) -> bool:
    if not token or "[" in token or "]" in token:
        return False
    standard_colors = {
        "black",
        "white",
        "transparent",
        "current",
        "inherit",
        "slate",
        "gray",
        "zinc",
        "neutral",
        "stone",
        "red",
        "orange",
        "amber",
        "yellow",
        "lime",
        "green",
        "emerald",
        "teal",
        "cyan",
        "sky",
        "blue",
        "indigo",
        "violet",
        "purple",
        "fuchsia",
        "pink",
        "rose",
    }
    standard_scales = {
        "0",
        "px",
        "0.5",
        "1",
        "1.5",
        "2",
        "2.5",
        "3",
        "3.5",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        "10",
        "11",
        "12",
        "14",
        "16",
        "20",
        "24",
        "28",
        "32",
        "36",
        "40",
        "44",
        "48",
        "52",
        "56",
        "60",
        "64",
        "72",
        "80",
        "96",
    }
    standard_sizes = {
        "xs",
        "sm",
        "base",
        "lg",
        "xl",
        "2xl",
        "3xl",
        "4xl",
        "5xl",
        "6xl",
        "7xl",
        "8xl",
        "9xl",
        "full",
        "none",
        "md",
    }

    def after(prefix: str) -> str:
        return token[len(prefix) :]

    color_prefixes = ("bg-", "text-", "border-", "from-", "to-", "via-", "accent-", "ring-", "outline-")
    for prefix in color_prefixes:
        if token.startswith(prefix):
            value = after(prefix)
            if prefix == "border-" and re.fullmatch(r"[trblxy]|[trblxy]-0|[trblxy]-2|[trblxy]-4|[trblxy]-8", value):
                return False
            root = value.split("-")[0]
            if root in standard_colors or re.fullmatch(r"\d+|none|current|inherit|transparent", value):
                return False
            if re.fullmatch(r"(xs|sm|base|lg|xl|[2-9]xl)", value) and prefix == "text-":
                return False
            return True
    spacing_prefixes = ("p-", "px-", "py-", "pt-", "pr-", "pb-", "pl-", "m-", "mx-", "my-", "mt-", "mr-", "mb-", "ml-", "gap-", "space-x-", "space-y-")
    for prefix in spacing_prefixes:
        if token.startswith(prefix):
            value = after(prefix)
            return value not in standard_scales and value not in {"auto"}
    if token.startswith("rounded-"):
        value = after("rounded-")
        return value not in standard_scales and value not in standard_sizes
    if token.startswith("font-"):
        value = after("font-")
        return value not in {"thin", "extralight", "light", "normal", "medium", "semibold", "bold", "extrabold", "black", "sans", "serif", "mono"}
    if token.startswith("shadow-"):
        value = after("shadow-")
        return value not in {"sm", "md", "lg", "xl", "2xl", "inner", "none"}
    return False


def _localize_fidelity_body_visuals(html: str, project_root: Path) -> str:
    text = str(html or "")
    if not text:
        return ""

    def replace_img(match: re.Match[str]) -> str:
        tag = match.group(0)
        src_match = re.search(r"\bsrc\s*=\s*(['\"])(.*?)\1", tag, flags=re.IGNORECASE | re.DOTALL)
        if not src_match:
            return tag
        quote = src_match.group(1)
        src = _clean(src_match.group(2))
        if not re.match(r"^https?://", src, re.IGNORECASE):
            return tag
        local_src = _localize_remote_visual(project_root, src)
        if not local_src:
            return ""
        return tag[: src_match.start(2)] + escape(local_src, quote=True) + tag[src_match.end(2) :]

    return re.sub(r"<img\b[^>]*>", replace_img, text, flags=re.IGNORECASE | re.DOTALL)


def _localize_remote_visual(project_root: Path, src: str) -> str:
    assets_root = project_root / "public" / "friday-assets"
    assets_root.mkdir(parents=True, exist_ok=True)
    suffix = _image_suffix(src)
    name = hashlib.sha256(src.encode("utf-8", errors="ignore")).hexdigest()[:16] + suffix
    target = assets_root / name
    if target.exists() and target.stat().st_size > 0:
        return f"/friday-assets/{name}"
    if _download_binary(src, target):
        return f"/friday-assets/{name}"
    try:
        target.unlink(missing_ok=True)
    except Exception:
        pass
    return ""


def _image_suffix(src: str) -> str:
    match = re.search(r"\.(png|jpe?g|webp|gif)(?:\?|$)", src, flags=re.IGNORECASE)
    if not match:
        return ".png"
    value = match.group(1).lower()
    return ".jpg" if value == "jpeg" else f".{value}"


def _extract_nav(root: _HtmlNode, *, product_name: str = "", site_routes: dict[str, Any] | None = None) -> list[dict[str, str]]:
    brand_label = _clean(product_name).lower()
    for nav_node in [node for node in _descendants(root) if node.tag == "nav"]:
        items: list[dict[str, str]] = []
        for link in [node for node in _descendants(nav_node) if node.tag == "a"]:
            label = _trim(_node_text(link), 32)
            if not label:
                continue
            if brand_label and label.lower() == brand_label:
                continue
            href = _normalize_design_href(link.attrs.get("href", ""), label, site_routes=site_routes)
            item = {"label": label, "href": href}
            if item not in items:
                items.append(item)
        if len(items) >= 2:
            return items[:6]
    return []


def _normalize_design_href(href: str, label: str, *, site_routes: dict[str, Any] | None = None) -> str:
    cleaned = _clean(href)
    lowered_label = label.lower()
    route_context = site_routes if isinstance(site_routes, dict) else {}
    allowed_routes = set(route_context.get("allowed_routes") or [])
    single_page = bool(route_context.get("single_page"))
    href_hint = re.sub(r"[/#?&=_-]+", " ", cleaned)
    intended_route = _route_for_action_label(f"{lowered_label} {href_hint}", site_routes=route_context)
    if cleaned.startswith("mailto:") or re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", lowered_label):
        return cleaned if cleaned.startswith("mailto:") else f"mailto:{lowered_label}"
    if cleaned.startswith("tel:"):
        return cleaned
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        return cleaned
    if cleaned.startswith("/") and not cleaned.startswith("//"):
        route = _normalize_internal_route(cleaned)
        if single_page and route == "/" and not intended_route and "home" not in lowered_label:
            return f"#{_anchor_id_for_label(label)}"
        if allowed_routes and route in allowed_routes:
            if route == "/" and intended_route and intended_route != "/":
                return intended_route
            return route
        if intended_route and (not allowed_routes or intended_route in allowed_routes):
            return intended_route
        if not allowed_routes:
            if route == "/" and intended_route and intended_route != "/":
                return intended_route
            return route
        anchor_fallback = _anchor_fallback_for_missing_route(route, lowered_label)
        if anchor_fallback:
            return anchor_fallback
        return _nearest_allowed_route(route, lowered_label, route_context) or "/"
    if intended_route and (not allowed_routes or intended_route in allowed_routes):
        return intended_route
    if cleaned.startswith("#") or not cleaned:
        if single_page and not any(term in lowered_label for term in ("home", "logo")):
            return f"#{_anchor_id_for_label(label)}"
        if allowed_routes:
            return _nearest_allowed_route("", lowered_label, route_context) or "/"
        return "/contact" if any(term in lowered_label for term in ("book", "start", "contact", "inquiry", "proposal", "consult")) else "/"
    return "#"


def _anchor_fallback_for_missing_route(route: str, lowered_label: str) -> str:
    text = f"{_route_alias_key(route.strip('/'))} {lowered_label}".strip()
    if any(term in text for term in ("process", "service", "services", "capability", "capabilities", "atelier", "method")):
        return "#process"
    if any(term in text for term in ("contact", "inquiry", "inquire", "concierge", "appointment", "book", "booking", "quote", "proposal")):
        return "#inquiry"
    if "journal" in text or "press" in text or "news" in text:
        return "#journal"
    if "privacy" in text or "governance" in text:
        return "#privacy"
    if "terms" in text:
        return "#terms"
    return ""


def _anchor_id_for_label(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _clean(label).lower()).strip("-")
    return slug or "section"


def _route_for_action_label(lowered_label: str, *, site_routes: dict[str, Any] | None = None) -> str:
    route_context = site_routes if isinstance(site_routes, dict) else {}
    allowed_routes = set(route_context.get("allowed_routes") or [])
    aliases = route_context.get("aliases") if isinstance(route_context.get("aliases"), dict) else {}
    label_key = _route_alias_key(lowered_label)
    for alias, route in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
        if alias and alias in label_key:
            return str(route)
    route_map = {
        "home": "/",
        "about": "/about",
        "company": "/about",
        "history": "/about",
        "story": "/about",
        "services": "/services",
        "service": "/services",
        "expertise": "/services",
        "capability": "/services",
        "capabilities": "/services",
        "projects": "/services",
        "portfolio": "/services",
        "work": "/services",
        "package": "/services",
        "packages": "/services",
        "pricing": "/pricing",
        "contact": "/contact",
        "concierge": "/contact",
        "inquiry": "/contact",
        "inquire": "/contact",
        "appointment": "/contact",
        "booking": "/contact",
        "quote": "/contact",
        "estimate": "/contact",
        "proposal": "/contact",
        "consult": "/contact",
        "touch": "/contact",
    }
    for key, route in route_map.items():
        if key in lowered_label:
            if allowed_routes and route not in allowed_routes:
                continue
            return route
    return ""


def _site_route_context_for_design_pages(pages: list[dict[str, Any]], request: str) -> dict[str, Any]:
    """Use actual handoff routes as the route contract for imported/generated pages."""

    actual_routes: list[str] = []
    labels: dict[str, str] = {}
    aliases: dict[str, str] = {}

    def add_alias(alias: str, route: str) -> None:
        key = _route_alias_key(alias)
        normalized = _normalize_internal_route(route)
        if key and normalized:
            aliases[key] = normalized

    for page in pages:
        if not isinstance(page, dict):
            continue
        route = _normalize_internal_route(str(page.get("route") or "/"))
        if not route:
            continue
        page_id = _clean_page_id(page.get("id") or "")
        label = _clean(page.get("label")) or page_id.replace("-", " ").title()
        if route not in actual_routes:
            actual_routes.append(route)
        labels[route] = label or route
        add_alias(label, route)
        add_alias(page_id, route)
        if route == "/":
            for alias in ("home", "start", "overview", "homepage", "logo"):
                add_alias(alias, route)
        if any(term in f"{label} {page_id}".lower() for term in ("collection", "gallery", "catalog", "archive")):
            for alias in ("collection", "collections", "gallery", "catalog", "archive", "archives", "view collection", "all collections"):
                add_alias(alias, route)

    if actual_routes:
        return {"allowed_routes": actual_routes, "labels": labels, "aliases": aliases, "single_page": len(actual_routes) == 1}
    return _site_route_context(request)


def _site_route_context(request: str) -> dict[str, Any]:
    pages = _website_page_specs(request)
    allowed: list[str] = []
    labels: dict[str, str] = {}
    aliases: dict[str, str] = {}

    def add_alias(alias: str, route: str) -> None:
        key = _route_alias_key(alias)
        normalized = _normalize_internal_route(route)
        if key and normalized:
            aliases[key] = normalized

    for page in pages:
        route = _normalize_internal_route(page.get("route") or "/")
        label = _clean(page.get("label"))
        page_id = _clean(page.get("id"))
        focus = _clean(page.get("focus"))
        if route not in allowed:
            allowed.append(route)
        labels[route] = label or route
        add_alias(label, route)
        add_alias(page_id, route)
        for token in _keywords(f"{label} {page_id} {focus}"):
            if len(token) >= 3:
                add_alias(token, route)
        text = f"{label} {page_id} {focus}".lower()
        if route == "/":
            for alias in ("home", "start", "overview", "homepage"):
                add_alias(alias, route)
        if any(term in text for term in ("contact", "concierge", "inquiry", "appointment")):
            for alias in (
                "contact",
                "concierge",
                "concierge contact",
                "inquire",
                "inquiry",
                "start inquiry",
                "request inquiry",
                "book",
                "booking",
                "appointment",
                "consult",
                "consultation",
                "quote",
                "estimate",
                "proposal",
                "get in touch",
                "start a project",
            ):
                add_alias(alias, route)
        if any(term in text for term in ("collection", "gallery", "catalog", "portfolio")):
            for alias in ("collection", "collections", "gallery", "catalog", "portfolio", "pieces", "objects", "view collection", "explore collection"):
                add_alias(alias, route)
        if any(term in text for term in ("atelier", "workshop", "craft", "studio", "process")):
            for alias in ("atelier", "workshop", "craft", "craftsmanship", "process", "making", "studio"):
                add_alias(alias, route)
        if any(term in text for term in ("about", "story", "history", "team", "company")):
            for alias in ("about", "story", "history", "team", "company", "who we are"):
                add_alias(alias, route)
        if any(term in text for term in ("service", "capability", "expertise", "project")):
            for alias in ("service", "services", "capability", "capabilities", "expertise", "projects", "work", "packages"):
                add_alias(alias, route)
        if any(term in text for term in ("pricing", "plan", "package")):
            for alias in ("pricing", "price", "plans", "packages"):
                add_alias(alias, route)

    return {"allowed_routes": allowed, "labels": labels, "aliases": aliases, "single_page": len(pages) == 1}


def _normalize_internal_route(route: str) -> str:
    cleaned = _clean(route)
    if not cleaned or cleaned.startswith("#"):
        return ""
    path = cleaned.split("?", 1)[0].split("#", 1)[0].strip()
    if not path:
        return ""
    if not path.startswith("/"):
        path = f"/{path}"
    path = "/" + path.strip("/")
    return "/" if path == "/" else path.rstrip("/")


def _route_alias_key(value: str) -> str:
    return _clean(re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())).strip()


def _nearest_allowed_route(route: str, label: str, site_routes: dict[str, Any]) -> str:
    allowed_routes = list(site_routes.get("allowed_routes") or [])
    if not allowed_routes:
        return ""
    intended = _route_for_action_label(label, site_routes=site_routes)
    if intended in allowed_routes:
        return intended
    route_text = _route_alias_key(route.strip("/"))
    if route_text:
        intended = _route_for_action_label(route_text, site_routes=site_routes)
        if intended in allowed_routes:
            return intended
    if len(allowed_routes) == 1:
        return allowed_routes[0]
    return ""


def _descendants(node: _HtmlNode) -> list[_HtmlNode]:
    items: list[_HtmlNode] = []
    for child in node.children:
        items.append(child)
        items.extend(_descendants(child))
    return items


def _descendant_tag_count(node: _HtmlNode, tags: set[str]) -> int:
    tag_set = {item.lower() for item in tags}
    return sum(1 for item in _descendants(node) if item.tag in tag_set)


def _node_text(node: _HtmlNode) -> str:
    if _is_icon_node(node):
        return ""
    parts = [part for part in node.text if not _is_icon_token(part)]
    for child in node.children:
        child_text = _node_text(child)
        if child_text and not _is_icon_token(child_text):
            parts.append(child_text)
    return _clean(" ".join(part for part in parts if part))


def _is_icon_node(node: _HtmlNode) -> bool:
    class_name = _clean(node.attrs.get("class", "")).lower()
    role = _clean(node.attrs.get("role", "")).lower()
    aria_hidden = _clean(node.attrs.get("aria-hidden", "")).lower()
    return (
        "material-symbol" in class_name
        or "material-icons" in class_name
        or class_name in {"icon", "icons"}
        or role == "img" and len(_clean(" ".join(node.text))) <= 24
        or aria_hidden == "true" and len(_clean(" ".join(node.text))) <= 32
    )


def _is_icon_token(text: str) -> bool:
    lowered = _clean(text).lower()
    if not lowered:
        return True
    tokens = {
        "add", "arrow_forward", "arrow_outward", "check", "check_circle", "close", "eco", "email",
        "expand_more", "health_and_safety", "keyboard_arrow_down", "mail", "menu", "search",
        "share", "verified",
    }
    if lowered in tokens:
        return True
    return bool("_" in lowered and re.fullmatch(r"[a-z0-9_]+", lowered))


def _texts_by_tag(root: _HtmlNode, tags: tuple[str, ...], *, limit: int = 20) -> list[str]:
    texts: list[str] = []
    tag_set = set(tags)
    for node in _descendants(root):
        if node.tag not in tag_set:
            continue
        text = _node_text(node)
        if text and text not in texts:
            texts.append(text)
        if len(texts) >= limit:
            break
    return texts


def _first_text(root: _HtmlNode, tags: tuple[str, ...]) -> str:
    texts = _texts_by_tag(root, tags, limit=1)
    return texts[0] if texts else ""


def _first_meaningful(values: list[str], exclude: set[str] | None = None) -> str:
    excluded = {_clean(item).lower() for item in (exclude or set()) if _clean(item)}
    for value in values:
        text = _clean(value)
        if len(text) < 24:
            continue
        if text.lower() in excluded:
            continue
        return text
    return ""


def _similar(left: str, right: str) -> bool:
    a = _clean(left).lower()
    b = _clean(right).lower()
    return bool(a and b and (a == b or a in b or b in a))


def _trim(value: str, limit: int) -> str:
    text = _clean(value)
    if len(text) <= limit:
        return text
    clipped = text[: max(0, limit - 1)].rsplit(" ", 1)[0].strip()
    return f"{clipped}..."


def _stitch_native_content_module(content: dict[str, Any]) -> str:
    return (
        "export const stitchNativeContent = "
        + json.dumps(content, ensure_ascii=True, indent=2, sort_keys=True, default=str)
        + " as const;\n\nexport type StitchPageId = keyof typeof stitchNativeContent.pages;\n"
    )


def _stitch_design_pages_compat_module() -> str:
    return """import { stitchNativeContent } from './stitchNativeContent';

export const stitchDesignPages = stitchNativeContent.pages;
export const stitchDesignMeta = stitchNativeContent.meta;
export type StitchPageId = keyof typeof stitchNativeContent.pages;
"""


def _stitch_page_surface_component() -> str:
    return """import { StitchNativePage } from './StitchNativePage';
import type { StitchPageId } from '@/lib/stitchNativeContent';

export function StitchPageSurface({ page }: { page: StitchPageId }) {
  return <StitchNativePage page={page} />;
}
"""


def _stitch_native_page_component() -> str:
    return """'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';

import { stitchNativeContent, type StitchPageId } from '@/lib/stitchNativeContent';

import styles from './StitchNativePage.module.css';

type NativeAction = { label: string; href: string; primary: boolean };
type NativeVisual = { src: string; alt: string };
type NativeCard = { title: string; body: string };
type NativeSection = { label: string; title: string; body: string; cards: readonly NativeCard[]; points: readonly string[] };
type NativeProof = { kicker: string; title: string; body: string; items: readonly string[] };
type NativePage = {
  actions: readonly NativeAction[];
  bodyHtml?: string;
  documentHtml?: string;
  kind: string;
  kicker: string;
  label: string;
  renderMode?: string;
  route: string;
  score: number;
  sections: readonly NativeSection[];
  summary: string;
  styleHtml?: string;
  tailwindConfig?: string;
  title: string;
  usesTailwindCdn?: boolean;
  visuals: readonly NativeVisual[];
  proof: NativeProof;
};

export function StitchNativePage({ page }: { page: StitchPageId }) {
  const pages = stitchNativeContent.pages as Record<StitchPageId, NativePage>;
  const data = pages[page];
  const meta = stitchNativeContent.meta;
  const nav = meta.nav.length ? meta.nav : Object.values(pages).map((item) => ({ label: item.label, href: item.route }));
  const heroVisual = data.visuals[0];
  const headerAction = meta.primaryAction || data.actions.find((action) => action.primary) || data.actions[0] || { label: 'Get started', href: data.route || '/', primary: true };
  const proof = data.proof || { kicker: 'Proof', title: meta.productName, body: data.summary, items: [] };
  const renderStitchDocument = data.renderMode === 'stitch_document' && Boolean(data.documentHtml);
  const renderStitchHtml = data.renderMode === 'stitch_html' && Boolean(data.bodyHtml);

  if (renderStitchDocument) {
    return (
      <main className={`${styles.shell} ${styles.documentShell}`} aria-label={`${data.title} page`}>
        <StitchDocumentRuntime pageId={String(page)} data={data} />
      </main>
    );
  }

  if (renderStitchHtml) {
    return (
      <main className={`${styles.shell} ${styles.fidelityShell}`} aria-label={`${data.title} page`}>
        <StitchHtmlRuntime pageId={String(page)} data={data} />
      </main>
    );
  }

  return (
    <main className={styles.shell} aria-label={`${data.title} page`}>
      <header className={styles.header}>
        <Link href="/" className={styles.brand}>{meta.productName}</Link>
        <nav className={styles.nav} aria-label="Primary navigation">
          {nav.map((item) => (
            <Link key={`${item.href}-${item.label}`} href={item.href} className={item.href === data.route ? styles.activeNav : styles.navLink}>
              {item.label}
            </Link>
          ))}
        </nav>
        <Link href={headerAction.href} className={styles.headerAction}>{headerAction.label}</Link>
      </header>

      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          {data.kicker ? <p className={styles.eyebrow}>{data.kicker}</p> : null}
          <h1>{data.title}</h1>
          <p className={styles.summary}>{data.summary}</p>
          <div className={styles.actions}>
            {data.actions.length ? data.actions.slice(0, 2).map((action) => (
              <Link key={`${action.href}-${action.label}`} href={action.href} className={action.primary ? styles.primaryAction : styles.secondaryAction}>
                {action.label}
              </Link>
            )) : <Link href={headerAction.href} className={styles.primaryAction}>{headerAction.label}</Link>}
          </div>
        </div>
        {heroVisual ? (
          <div className={styles.visualPanel}>
            <img src={heroVisual.src} alt={heroVisual.alt || data.title} />
          </div>
        ) : (
          <div className={styles.signalPanel}>
            <p className={styles.eyebrow}>{proof.kicker}</p>
            <h2>{proof.title}</h2>
            <p>{proof.body}</p>
            {proof.items.length ? (
              <ul className={styles.signalList}>
                {proof.items.slice(0, 4).map((item) => <li key={item}>{item}</li>)}
              </ul>
            ) : null}
          </div>
        )}
      </section>

      {data.sections.map((section, index) => (
        <section key={`${section.title}-${index}`} className={styles.section}>
          <div className={styles.sectionHeader}>
            <p className={styles.eyebrow}>{section.label || `Section ${index + 1}`}</p>
            <h2>{section.title}</h2>
            {section.body ? <p>{section.body}</p> : null}
          </div>
          {section.cards.length ? (
            <div className={styles.cardGrid}>
              {section.cards.map((card) => (
                <article key={`${card.title}-${card.body}`} className={styles.card}>
                  <h3>{card.title}</h3>
                  <p>{card.body}</p>
                </article>
              ))}
            </div>
          ) : null}
          {section.points.length ? (
            <ul className={styles.pointList}>
              {section.points.map((point) => <li key={point}>{point}</li>)}
            </ul>
          ) : null}
        </section>
      ))}

      {data.kind === 'contact' ? <ContactBlock productName={meta.productName} /> : null}
    </main>
  );
}

function StitchDocumentRuntime({ pageId, data }: { pageId: string; data: NativePage }) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState('100vh');

  useEffect(() => {
    let cancelled = false;
    let attempts = 0;
    const updateHeight = () => {
      if (cancelled) {
        return;
      }
      attempts += 1;
      const doc = iframeRef.current?.contentDocument;
      const nextHeight = Math.max(
        doc?.documentElement?.scrollHeight || 0,
        doc?.body?.scrollHeight || 0,
        window.innerHeight || 0,
      );
      if (nextHeight > 0) {
        setHeight(`${nextHeight}px`);
      }
      if (attempts < 8) {
        window.setTimeout(updateHeight, 600);
      }
    };
    updateHeight();
    window.addEventListener('resize', updateHeight);
    return () => {
      cancelled = true;
      window.removeEventListener('resize', updateHeight);
    };
  }, [pageId, data.documentHtml]);

  return (
    <iframe
      ref={iframeRef}
      title={`${data.title} Stitch design`}
      className={styles.stitchDocumentFrame}
      srcDoc={data.documentHtml || ''}
      sandbox="allow-scripts allow-forms allow-popups allow-same-origin"
      style={{ height }}
    />
  );
}

function StitchHtmlRuntime({ pageId, data }: { pageId: string; data: NativePage }) {
  useEffect(() => {
    if (!data.usesTailwindCdn || typeof document === 'undefined') {
      return;
    }
    const runtimeId = `stitch-runtime-${pageId}`;
    const existing = document.querySelector(`script[data-friday-stitch-tailwind="${runtimeId}"]`);
    if (existing) {
      return;
    }
    const configScript = document.createElement('script');
    configScript.dataset.fridayStitchTailwind = `${runtimeId}-config`;
    configScript.text = data.tailwindConfig || 'window.tailwind = window.tailwind || {};';
    document.head.appendChild(configScript);

    const cdnScript = document.createElement('script');
    cdnScript.dataset.fridayStitchTailwind = runtimeId;
    cdnScript.src = 'https://cdn.tailwindcss.com?plugins=forms,container-queries';
    cdnScript.async = false;
    document.head.appendChild(cdnScript);

    return () => {
      configScript.remove();
      cdnScript.remove();
    };
  }, [data.tailwindConfig, data.usesTailwindCdn, pageId]);

  return (
    <>
      {data.styleHtml ? <style dangerouslySetInnerHTML={{ __html: data.styleHtml }} /> : null}
      <div className={styles.stitchHtmlSurface} dangerouslySetInnerHTML={{ __html: data.bodyHtml || '' }} />
    </>
  );
}

function ContactBlock({ productName }: { productName: string }) {
  const [submitted, setSubmitted] = useState(false);

  return (
    <section className={styles.contactBlock}>
      <div>
        <p className={styles.eyebrow}>Project inquiry</p>
        <h2>Start a conversation with {productName}</h2>
        <p>Share the project type, location, timing, and the team that should respond. This form is ready to connect to the approved CRM or email workflow.</p>
      </div>
      <form className={styles.form} onSubmit={(event) => { event.preventDefault(); setSubmitted(true); }}>
        <label>Name<input name="name" type="text" placeholder="Jane Doe" /></label>
        <label>Email<input name="email" type="email" placeholder="jane@company.com" /></label>
        <label>Project<textarea name="project" placeholder="Project type, location, timing, and contact path" /></label>
        <button type="submit">Submit inquiry</button>
        {submitted ? <p className={styles.formStatus} role="status">Inquiry draft captured for this preview. Connect the approved inbox or CRM before launch.</p> : null}
      </form>
    </section>
  );
}
"""


def _stitch_native_page_css() -> str:
    return """.shell {
  min-height: 100vh;
  color: #141614;
  background: #f8f8f4;
}

.fidelityShell {
  color: inherit;
  background: #f8f8f4;
}

.documentShell {
  color: inherit;
  background: #f8f8f4;
}

.stitchDocumentFrame {
  display: block;
  width: 100%;
  min-height: 100vh;
  border: 0;
  background: #f8f8f4;
}

.stitchHtmlSurface {
  min-height: 100vh;
  color: inherit;
}

.stitchHtmlSurface :global(a) {
  text-decoration: none;
}

.stitchHtmlSurface :global(nav) {
  padding-left: clamp(20px, 5vw, 72px);
  padding-right: clamp(20px, 5vw, 72px);
}

.stitchHtmlSurface :global(nav > div),
.stitchHtmlSurface :global(nav > div > div) {
  gap: 24px;
}

.stitchHtmlSurface :global(nav a:first-child) {
  margin-right: 24px;
}

.header {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  min-height: 72px;
  padding: 0 clamp(20px, 5vw, 72px);
  border-bottom: 1px solid #dedbd2;
  background: rgba(248, 248, 244, 0.94);
  backdrop-filter: blur(14px);
}

.brand {
  color: #151713;
  font-size: 1rem;
  font-weight: 800;
}

.nav {
  display: flex;
  align-items: center;
  gap: clamp(12px, 2vw, 28px);
}

.navLink,
.activeNav {
  color: #4f564f;
  font-size: 0.94rem;
  font-weight: 650;
}

.activeNav {
  color: #1f4f46;
}

.headerAction,
.primaryAction,
.secondaryAction {
  display: inline-flex;
  min-height: 42px;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  padding: 0 16px;
  font-weight: 750;
}

.headerAction,
.primaryAction {
  color: #fff;
  background: #1f4f46;
}

.secondaryAction {
  color: #151713;
  border: 1px solid #bdb7aa;
  background: transparent;
}

.hero {
  display: grid;
  grid-template-columns: minmax(0, 0.96fr) minmax(280px, 0.88fr);
  gap: clamp(28px, 5vw, 64px);
  align-items: center;
  min-height: auto;
  padding: clamp(40px, 5vw, 68px) clamp(20px, 5vw, 72px);
}

.heroCopy {
  max-width: 720px;
}

.eyebrow {
  margin: 0 0 14px;
  color: #8c3f2d;
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.hero h1 {
  max-width: min(100%, 19ch);
  margin: 0;
  color: #151713;
  font-size: clamp(2.55rem, 4vw, 3.6rem);
  line-height: 1.04;
  letter-spacing: 0;
}

.summary,
.sectionHeader p,
.card p,
.contactBlock p {
  color: #555b52;
  font-size: 1.06rem;
  line-height: 1.62;
}

.summary {
  max-width: 700px;
  margin: 20px 0 0;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 28px;
}

.visualPanel,
.signalPanel {
  min-height: 340px;
  border: 1px solid #d6d1c6;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
  box-shadow: 0 18px 60px rgba(20, 22, 20, 0.08);
}

.visualPanel img {
  width: 100%;
  height: 100%;
  min-height: 340px;
  object-fit: cover;
}

.signalPanel {
  display: grid;
  align-content: end;
  gap: 18px;
  padding: 28px;
}

.signalPanel h2 {
  max-width: 12ch;
  margin: 0;
  color: #1f4f46;
  font-size: clamp(2.1rem, 4vw, 3.25rem);
  font-weight: 850;
  line-height: 1.02;
  letter-spacing: 0;
}

.signalPanel p {
  max-width: 520px;
  margin: 0;
  color: #475149;
  font-size: 1rem;
  line-height: 1.6;
}

.signalList {
  display: grid;
  gap: 10px;
  margin: 4px 0 0;
  padding: 0;
  list-style: none;
}

.signalList li {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #24352f;
  font-size: 0.95rem;
  font-weight: 700;
}

.signalList li::before {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #1f4f46;
  content: '';
}

.section {
  padding: clamp(40px, 5vw, 64px) clamp(20px, 5vw, 72px);
  border-top: 1px solid #e5e1d8;
}

.sectionHeader {
  max-width: 780px;
  margin-bottom: 32px;
}

.sectionHeader h2,
.contactBlock h2 {
  margin: 0;
  color: #151713;
  font-size: clamp(1.8rem, 3vw, 2.25rem);
  line-height: 1.08;
  letter-spacing: 0;
}

.cardGrid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
}

.card {
  min-height: 180px;
  border: 1px solid #ded9cf;
  border-radius: 8px;
  padding: 22px;
  background: #fff;
}

.card h3 {
  margin: 0 0 12px;
  color: #171916;
  font-size: 1.08rem;
  line-height: 1.3;
}

.pointList {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.pointList li {
  border-left: 3px solid #1f4f46;
  padding: 10px 14px;
  background: #fff;
  color: #3f473f;
}

.contactBlock {
  display: grid;
  grid-template-columns: minmax(0, 0.85fr) minmax(320px, 1.15fr);
  gap: clamp(24px, 5vw, 64px);
  padding: clamp(56px, 8vw, 104px) clamp(20px, 5vw, 72px);
  border-top: 1px solid #e5e1d8;
  background: #eef4ef;
}

.form {
  display: grid;
  gap: 14px;
  padding: 22px;
  border: 1px solid #d3dbd4;
  border-radius: 8px;
  background: #fff;
}

.form label {
  display: grid;
  gap: 8px;
  color: #2d342d;
  font-weight: 700;
}

.form input,
.form textarea {
  width: 100%;
  border: 1px solid #c8cec8;
  border-radius: 8px;
  padding: 12px;
  font: inherit;
}

.form textarea {
  min-height: 128px;
  resize: vertical;
}

.form button {
  min-height: 44px;
  border: 0;
  border-radius: 8px;
  color: #fff;
  background: #1f4f46;
  font: inherit;
  font-weight: 800;
}

.formStatus {
  margin: 0;
  color: #1f5b4f;
  font-size: 0.95rem;
  font-weight: 700;
}

@media (max-width: 1120px) {
  .hero h1 {
    font-size: 3rem;
  }

  .sectionHeader h2,
  .contactBlock h2 {
    font-size: 2rem;
  }
}

@media (max-width: 880px) {
  .header {
    align-items: flex-start;
    flex-direction: column;
    padding-top: 16px;
    padding-bottom: 16px;
  }

  .nav {
    flex-wrap: wrap;
  }

  .headerAction {
    display: none;
  }

  .hero,
  .contactBlock {
    grid-template-columns: 1fr;
  }

  .hero h1 {
    max-width: 100%;
    font-size: 2.45rem;
  }

  .cardGrid,
  .pointList {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 560px) {
  .hero h1 {
    font-size: 2rem;
  }

  .sectionHeader h2,
  .contactBlock h2 {
    font-size: 1.75rem;
  }
}
"""

def _stitch_legacy_component() -> str:
    return """import { stitchNativeContent, type StitchPageId } from '@/lib/stitchNativeContent';

import { StitchPageSurface } from './StitchPageSurface';

function defaultPage(): StitchPageId {
  const pages = stitchNativeContent.pages as Record<string, unknown>;
  if ('home' in pages) {
    return 'home' as StitchPageId;
  }
  if ('website_home' in pages) {
    return 'website_home' as StitchPageId;
  }
  return (Object.keys(pages)[0] || 'home') as StitchPageId;
}

export function StitchDesignSurface() {
  return <StitchPageSurface page={defaultPage()} />;
}
"""


def _stitch_page_module(page_id: str = "home") -> str:
    safe_id = _clean_page_id(page_id)
    return f"""import {{ StitchPageSurface }} from '@/components/Stitch/StitchPageSurface';

export default function Page() {{
  return <StitchPageSurface page={json.dumps(safe_id)} />;
}}
"""


def _stitch_document_redirect_page_module(public_route: str) -> str:
    route = _clean(public_route) or "/"
    return f"""import {{ redirect }} from 'next/navigation';

export default function Page() {{
  redirect({json.dumps(route)});
}}
"""


def _stitch_scale_normalizer_css() -> str:
    return """
.friday-stitch-page {
  min-height: 100vh;
  overflow-x: hidden;
  background: #fff;
  color: #111;
}
.friday-stitch-page .friday-stitch-html {
  min-height: 100vh;
  overflow-x: hidden;
}
.friday-stitch-page h1 {
  font-size: clamp(2.4rem, 5vw, 4.8rem) !important;
  line-height: 1.05 !important;
  letter-spacing: 0 !important;
}
.friday-stitch-page h2 {
  font-size: clamp(1.5rem, 3vw, 2.75rem) !important;
  line-height: 1.15 !important;
  letter-spacing: 0 !important;
}
.friday-stitch-page p {
  max-width: 76ch;
}
.friday-stitch-page img {
  max-width: 100%;
  height: auto;
}
.friday-stitch-page button,
.friday-stitch-page a {
  min-height: 40px;
}
@media (min-width: 768px) {
  .friday-stitch-page section {
    scroll-margin-top: 88px;
  }
}
"""


def _next_route_path(project_root: Path, route: str) -> Path:
    normalized = "/" + _clean(str(route or "/")).strip("/")
    if normalized == "/":
        return project_root / "src" / "app" / "page.tsx"
    return project_root / "src" / "app" / normalized.strip("/") / "page.tsx"


def _product_name_from_request(request: str) -> str:
    cleaned = _clean(request)
    inferred = project_scaffolds.product_name(cleaned)
    if inferred and inferred != "FlowPilot" and not inferred.endswith(" Workspace"):
        return inferred
    called = re.search(r"\bcalled\s+([A-Za-z0-9][A-Za-z0-9 &'_-]{1,64})", cleaned, flags=re.IGNORECASE)
    if called:
        return _clean(called.group(1)).strip(" .,:;")
    words = re.findall(r"[A-Za-z0-9]+", cleaned)
    return " ".join(words[:4]).title() if words else ""


def _website_page_specs(request: str) -> list[dict[str, str]]:
    text = str(request or "").lower()
    labels = _explicit_website_page_labels(request)
    if labels:
        pages = [_page_spec_from_label(label, index) for index, label in enumerate(labels)]
    elif _is_landing_page_request(request):
        pages = [
            {
                "id": "home",
                "label": "Home",
                "route": "/",
                "focus": (
                    "complete product landing page with hero, proof/status strip, capabilities, "
                    "how it works, architecture/security proof, plugin or ecosystem story, and conversion call to action"
                ),
            }
        ]
    else:
        pages = [
            {"id": "home", "label": "Home", "route": "/", "focus": "brand, offer, proof, primary call to action"},
            {"id": "about", "label": "About", "route": "/about", "focus": "story, credibility, method, values, trust signals"},
            {"id": "services", "label": "Services", "route": "/services", "focus": "service packages, outcomes, process, fit"},
            {"id": "contact", "label": "Contact", "route": "/contact", "focus": "inquiry form, response promise, qualification, contact options"},
        ]
    if not labels and "pricing" in text and "services" not in text and len(pages) >= 3:
        pages[2] = {"id": "pricing", "label": "Pricing", "route": "/pricing", "focus": "pricing tiers, plan fit, objections, conversion"}
    navigation = "; ".join(f"{page['label']} ({page['route']})" for page in pages)
    for page in pages:
        page["navigation"] = navigation
    return pages


def _website_page_request(request: str, product_name: str, page: dict[str, str]) -> str:
    brand = _clean(product_name) or _product_name_from_request(request) or "the product"
    navigation = _clean(page.get("navigation")) or "Home (/); About (/about); Services (/services); Contact (/contact)"
    site_kind = (
        "This is the complete one-page landing page for the product."
        if _is_landing_page_request(request) and len(_website_page_specs(request)) == 1
        else "This is one page in a cohesive multi-page website."
    )
    return _clean(
        f"{request}\n\n"
        f"Brand name: {brand}. Page label: {page['label']}. Route: {page['route']}. "
        f"Design the {page['label']} page for {brand}. {site_kind} "
        f"Page focus: {page['focus']}. "
        f"Site map: {navigation}. "
        f"Visible logo and brand copy must say {brand}, not {brand} {page['label']}. "
        f"Do not render {page['label']} as a giant eyebrow, standalone H1, numbered tab, or section title just because it is the route label. "
        "Do not label sections as Page 1, Home 1, Services 2, or similar numbered filler. "
        "Design only this route's page content; other pages should appear only as navigation links or short teasers where appropriate, never as repeated full sections. "
        f"Use real route links from this site map ({navigation}) rather than # placeholders or default routes that are not in the site map. "
        "Do not return only a logo, icon, brand mark, style guide, or isolated asset; return a complete page screen with navigation, main content, and footer. "
        "Keep the same design system across pages. Generate a complete page, not only a hero. "
        "Use production web proportions: desktop H1 around 40-58px, readable sections, no oversized whitespace, no sticky header overlap, no giant display type, and no decorative excess. "
        "Use structured sections that Friday can convert into Next.js routes without duplicating the hero."
    )


def _page_product_name(product_name: str, page: dict[str, str]) -> str:
    return _clean(product_name) or "Website"


def _explicit_website_page_labels(request: str) -> list[str]:
    text = _clean(request)
    patterns = [
        r"\bpages?\s+must\s+be\s+([^.\n]+)",
        r"\bpages?\s+should\s+be\s+([^.\n]+)",
        r"\bpages?\s+(?:include|including)\s+([^.\n]+)",
        r"\bwith\s+(?:the\s+)?(?:following\s+)?(?:four|4)[-\s ]?pages?\s*:?\s+([^.\n]+)",
        r"\b(?:four|4)[-\s ]?pages?\s*:?\s+([^.\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        labels = _split_page_labels(match.group(1))
        if len(labels) >= 2:
            return labels[:6]
    return []


def _split_page_labels(raw: str) -> list[str]:
    text = re.sub(r"\([^)]*\)", " ", str(raw or ""))
    text = re.sub(r"\b(?:pages?|routes?)\b", " ", text, flags=re.IGNORECASE)
    parts = re.split(r",|/|\s+\band\b\s+", text)
    labels: list[str] = []
    for part in parts:
        label = _clean(part).strip(" .:;-\"'")
        label = re.sub(r"^(?:and|plus|including)\s+", "", label, flags=re.IGNORECASE).strip()
        if not label or len(label) > 40:
            continue
        if label.lower() in {"a", "an", "the", "with", "for"}:
            continue
        labels.append(label.title() if label.islower() else label)
    return _dedupe(labels)


def _page_spec_from_label(label: str, index: int) -> dict[str, str]:
    clean_label = _clean(label) or f"Page {index + 1}"
    lowered = clean_label.lower()
    if lowered == "home":
        page_id = "home"
        route = "/"
    elif "contact" in lowered:
        page_id = "contact"
        route = "/contact"
    else:
        page_id = _slug(clean_label)
        route = f"/{page_id}"
    return {
        "id": page_id,
        "label": clean_label,
        "route": route,
        "focus": _page_focus_for_label(clean_label, page_id),
    }


def _page_focus_for_label(label: str, page_id: str) -> str:
    text = f"{label} {page_id}".lower()
    if "home" in text:
        return "brand, offer, proof, primary call to action"
    if "about" in text or "story" in text:
        return "story, credibility, method, values, trust signals"
    if "service" in text or "capabil" in text:
        return "service packages, outcomes, process, fit"
    if "pricing" in text or "plans" in text:
        return "pricing tiers, plan fit, objections, conversion"
    if "atelier" in text or "studio" in text or "workshop" in text:
        return "craftsmanship, provenance, materials, process, trust, concierge action"
    if "collection" in text or "gallery" in text or "work" in text:
        return "collection story, item/category modules, provenance, scarcity, inquiry path"
    if "contact" in text or "concierge" in text or "inquiry" in text:
        return "concierge inquiry form, appointment options, response promise, privacy and trust notes"
    return "page-specific story, proof, useful details, and a clear next action"


def _write_multipage_design_report(project_root: Path, report: dict[str, Any]) -> list[str]:
    design_root = project_root / ".friday" / "design"
    design_root.mkdir(parents=True, exist_ok=True)
    json_path = design_root / "multipage-design-report.json"
    md_path = design_root / "multipage-design-report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    lines = [
        "# Multipage Design Report",
        "",
        f"Status: {report.get('status')}",
        f"Summary: {report.get('summary')}",
        f"Pages selected: {report.get('selected_page_count')}/{report.get('page_count')}",
        "",
        "## Pages",
    ]
    for page in report.get("pages") or []:
        lines.append(f"- {page.get('label')} ({page.get('route')}): {page.get('status')} - score {page.get('score') or 'n/a'}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [str(json_path), str(md_path)]


def _design_root(project_root: Path, artifact_scope: str = "") -> Path:
    base = project_root / ".friday" / "design"
    scope = _clean_artifact_scope(artifact_scope)
    return base / scope if scope else base


def _clean_artifact_scope(value: str) -> str:
    raw = str(value or "").replace("\\", "/")
    parts = [re.sub(r"[^A-Za-z0-9_-]+", "-", part).strip("-").lower() for part in raw.split("/") if part.strip()]
    return "/".join(part for part in parts if part)


def _clean_page_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", _clean(value).lower()).strip("_") or "home"


def _normalize_variants(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_variants = payload.get("variants") if isinstance(payload.get("variants"), list) else []
    if not raw_variants and payload:
        raw_variants = [
            {
                "id": payload.get("screenId") or payload.get("id") or "base",
                "label": "Base direction",
                "projectId": payload.get("projectId"),
                "screenId": payload.get("screenId"),
                "htmlUrl": payload.get("htmlUrl"),
                "imageUrl": payload.get("imageUrl"),
                "html": payload.get("html") or payload.get("htmlContent"),
            }
        ]
    variants: list[dict[str, Any]] = []
    for index, item in enumerate(raw_variants or [], start=1):
        if not isinstance(item, dict):
            continue
        variant = dict(item)
        variant["id"] = _clean(variant.get("id") or variant.get("screenId") or f"variant_{index}")
        variant["label"] = _clean(variant.get("label") or f"Variant {index}")
        variants.append(variant)
    return variants


def _attach_variant_assets(variants: list[dict[str, Any]], design_root: Path) -> list[dict[str, Any]]:
    if not bool(config_value("design_download_remote_assets", True)):
        return variants
    variants_root = design_root / "variants"
    variants_root.mkdir(parents=True, exist_ok=True)
    attached: list[dict[str, Any]] = []
    for index, variant in enumerate(variants, start=1):
        item = dict(variant)
        prefix = f"variant-{index:02d}"
        if item.get("html") and not item.get("html_path"):
            html_path = variants_root / f"{prefix}.html"
            html_path.write_text(str(item["html"]), encoding="utf-8")
            item["html_path"] = str(html_path)
        elif item.get("htmlUrl") and not item.get("html_path"):
            html_path = variants_root / f"{prefix}.html"
            html = _download_text(str(item["htmlUrl"]))
            if html:
                html_path.write_text(html, encoding="utf-8")
                item["html_path"] = str(html_path)
                item["html"] = html
        if item.get("imageUrl") and not item.get("image_path"):
            image_path = variants_root / f"{prefix}.png"
            if _download_binary(str(item["imageUrl"]), image_path):
                item["image_path"] = str(image_path)
        attached.append(item)
    return attached


def _download_text(url: str) -> str:
    result = design_asset_manager.download_text(url)
    return str(result.get("text") or "") if result.get("ok") else ""


def _download_binary(url: str, path: Path) -> bool:
    result = design_asset_manager.download_binary(url, path)
    return bool(result.get("ok"))


def _variant_count(value: int | None) -> int:
    raw = value if value is not None else config_value("design_variant_count", 3)
    try:
        count = int(raw)
    except Exception:
        count = 3
    return max(1, min(3, count))


def _select_design_variant(variants: list[dict[str, Any]], threshold: int) -> dict[str, Any] | None:
    candidates = [variant for variant in variants if int(variant.get("score") or 0) >= threshold and not variant.get("rejection_reasons")]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: int(item.get("score") or 0), reverse=True)[0]


def _variant_html(variant: dict[str, Any]) -> str:
    if _clean(variant.get("html") or variant.get("htmlContent")):
        return str(variant.get("html") or variant.get("htmlContent"))
    path = Path(str(variant.get("html_path") or ""))
    if path.exists() and path.is_file():
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""
    return ""


def _visible_text(html: str) -> str:
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html or "", flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-zA-Z0-9#]+;", " ", text)
    return _clean(text)


def _criterion(criterion_id: str, label: str, weight: int, raw_score: int) -> dict[str, Any]:
    score = max(0, min(weight, int(raw_score)))
    return {"id": criterion_id, "label": label, "weight": weight, "score": score, "passed": score >= max(1, int(weight * 0.6))}


def _brand_score(visible_text: str, product_name: str, profile_name: str, profile_id: str) -> int:
    if any(term and re.search(re.escape(term), visible_text, re.IGNORECASE) for term in {profile_name, profile_id, "NexusForge"}):
        return 0
    if product_name and re.search(re.escape(product_name), visible_text, re.IGNORECASE):
        return 18
    product_tokens = [token for token in _keywords(product_name) if len(token) > 4]
    matched = sum(1 for token in product_tokens if re.search(rf"\b{re.escape(token)}\b", visible_text, re.IGNORECASE))
    if product_tokens:
        return int(18 * matched / len(product_tokens))
    return 9


def _domain_fit_score(visible_text: str, request: str) -> int:
    keywords = _domain_keywords(request)
    if not keywords:
        return 11
    matched = sum(1 for token in keywords if re.search(rf"\b{re.escape(token)}\b", visible_text, re.IGNORECASE))
    coverage = matched / max(1, min(len(keywords), 18))
    score = max(0, min(22, int(22 * coverage)))
    text = visible_text.lower()
    request_lower = str(request or "").lower()
    decision_lower = _domain_decision_text(request_lower)
    if "page label: contact" in request_lower or re.search(r"\bcontact\b", request_lower):
        contact_terms = ("contact", "inquiry", "message", "email", "phone", "headquarters", "quote", "project opportunities", "response")
        contact_matches = sum(1 for term in contact_terms if term in text)
        if contact_matches >= 3:
            score = max(score, 13)
    if any(term in request_lower for term in ("construction", "civil infrastructure", "commercial development", "skanska")):
        domain_terms = ("construction", "civil", "infrastructure", "commercial", "development", "project", "safety", "engineering", "site", "build", "building")
        domain_matches = sum(1 for term in domain_terms if re.search(rf"\b{re.escape(term)}\b", text))
        if domain_matches >= 3:
            score = max(score, 14)
    if _energy_climate_request(decision_lower):
        domain_terms = (
            "climate", "risk", "property", "portfolio", "wildfire", "flood", "heat",
            "insurance", "tenant", "maintenance", "energy", "microgrid", "microgrids",
            "solar", "battery", "batteries", "grid", "demand", "outage", "building",
            "buildings", "load", "resilience", "telemetry", "facility", "facilities",
            "sustainability", "renewable", "decarbonization",
        )
        domain_matches = sum(1 for term in domain_terms if re.search(rf"\b{re.escape(term)}\b", text))
        if domain_matches >= 8:
            score = max(score, 18)
        elif domain_matches >= 5:
            score = max(score, 15)
        elif domain_matches >= 3:
            score = max(score, 12)
        if any(term in text for term in _energy_wrong_domain_terms()):
            score = min(score, 9)
    if _robotics_logistics_request(decision_lower):
        domain_terms = (
            "warehouse", "robotic", "robotics", "robot", "robots", "fleet", "route", "routes",
            "optimization", "exception", "exceptions", "throughput", "3pl", "fulfillment",
            "pick", "picking", "wave", "dock", "congestion", "inventory", "handoff", "wms",
            "orchestration", "operator", "operators", "facility", "facilities", "uptime",
            "latency", "autonomous", "mobile", "safety", "override", "telemetry",
        )
        domain_matches = sum(1 for term in domain_terms if re.search(rf"\b{re.escape(term)}s?\b", text))
        if domain_matches >= 9:
            score = max(score, 18)
        elif domain_matches >= 6:
            score = max(score, 15)
        elif domain_matches >= 4:
            score = max(score, 12)
        if any(term in text for term in ("self-hosted backend", "web3 modules", "web3 module", "cli install", "schema builder", "nexus forge", "base wallet", "x402")):
            score = min(score, 8)
    if _developer_tools_request(decision_lower):
        domain_terms = (
            "developer", "developers", "backend", "baas", "api", "auth", "database", "schema",
            "postgres", "websocket", "websockets", "realtime", "real-time", "ai", "agent",
            "agents", "web3", "base", "wallet", "transaction", "transactions", "x402", "payment",
            "payments", "monetization", "plugin", "marketplace", "github", "sdk", "cli", "docs",
            "documentation", "quickstart", "self-hosted", "open-source", "deployment", "deploy",
            "api keys", "no-code", "nocode",
        )
        domain_matches = sum(1 for term in domain_terms if re.search(rf"\b{re.escape(term)}\b", text))
        if domain_matches >= 8:
            score = max(score, 18)
        elif domain_matches >= 5:
            score = max(score, 15)
        elif domain_matches >= 3:
            score = max(score, 12)
    return score


def _domain_keywords(request: str) -> list[str]:
    instruction_terms = {
        "add", "all", "any", "artifacts", "available", "before", "blocker", "brand", "browser", "build",
        "called", "claim", "company", "configured", "context", "design", "done", "evidence", "exactly", "fails",
        "fallback", "final", "four-page", "friday", "gate", "gates", "generated", "giant", "google",
        "call", "cohesive", "focus", "handoff", "handoffs", "implementation", "implement", "known",
        "label", "labels", "layout", "local", "logo", "must", "name", "next", "nextjs", "non-negotiable",
        "normal", "normalize", "only", "page", "pages", "primary", "proof", "public", "raw", "real",
        "render", "required", "requirements", "route", "routes", "run",
        "sanitized", "scaffold", "screen", "screenshots", "spacing", "sticky", "stitch", "text", "type",
        "united", "use", "visible", "website",
    }
    keywords = [token for token in _keywords(request) if token.lower() not in instruction_terms]
    return _dedupe(keywords)


def _operational_density_score(html: str, visible_text: str) -> int:
    terms = [
        "queue", "status", "approval", "audit", "risk", "sla", "payment", "enrollment", "course",
        "student", "metric", "health", "triage", "action", "pending", "critical", "resolved",
    ]
    matched = sum(1 for term in terms if re.search(rf"\b{re.escape(term)}s?\b", visible_text, re.IGNORECASE))
    structure = sum(1 for token in ("<table", "<button", "<nav", "<aside", "<section", "<main", "role=", "aria-") if token in html.lower())
    return max(0, min(16, matched + structure))


def _website_content_depth_score(html: str, visible_text: str, request: str = "") -> int:
    terms = [
        "home", "about", "services", "contact", "inquiry", "consultation", "business", "client",
        "trust", "process", "offer", "automation", "operations", "service", "studio", "project",
    ]
    terms.extend(_domain_keywords(request)[:14])
    for label in _explicit_website_page_labels(request):
        terms.extend(_keywords(label))
    matched = sum(1 for term in terms if re.search(rf"\b{re.escape(term)}s?\b", visible_text, re.IGNORECASE))
    structure = sum(1 for token in ("<header", "<nav", "<main", "<section", "<article", "<form", "<a ") if token in html.lower())
    score = max(0, min(16, matched + structure))
    section_count = str(html or "").lower().count("<section")
    if _requires_full_home_content(request) and section_count < 4:
        return min(score, 7)
    if _is_landing_page_request(request) and section_count < 3:
        return min(score, 7)
    return score


def _accessibility_score(html: str) -> int:
    lowered = html.lower()
    score = 0
    if "<main" in lowered:
        score += 3
    if "<nav" in lowered or "<aside" in lowered:
        score += 2
    if "aria-" in lowered or "role=" in lowered:
        score += 3
    if "<button" in lowered or "<a " in lowered:
        score += 2
    if "<label" in lowered or "alt=" in lowered:
        score += 2
    return min(12, score)


def _copy_quality_score(visible_text: str) -> int:
    if _placeholder_copy_found(visible_text):
        return 2
    words = re.findall(r"[A-Za-z][A-Za-z'-]{2,}", visible_text)
    unique = len({word.lower() for word in words})
    if unique >= 80:
        return 14
    if unique >= 45:
        return 11
    if unique >= 25:
        return 8
    return 4


def _frontend_feasibility_score(html: str, visible_text: str) -> int:
    compact_html = _compact_html_for_scoring(html)
    lowered = compact_html.lower()
    component_signals = sum(1 for token in ("<header", "<nav", "<aside", "<main", "<section", "<table", "<button", "<form", "<article") if token in lowered)
    action_signals = sum(1 for term in ("view", "review", "approve", "assign", "resolve", "open", "new", "filter", "inquire", "inquiry", "contact", "book", "request", "explore", "visit", "start", "install", "copy", "docs", "documentation", "quickstart", "login", "register") if re.search(rf"\b{term}\b", visible_text, re.IGNORECASE))
    scale_penalty = _exaggerated_scale_penalty(compact_html)
    if len(compact_html) > 120000:
        return max(0, min(8, component_signals + action_signals - scale_penalty))
    return max(0, min(18, component_signals * 2 + action_signals - scale_penalty))


def _compact_html_for_scoring(html: str) -> str:
    text = str(html or "")
    text = re.sub(r"data:image/[^\"')\s]+", "data:image/omitted", text, flags=re.IGNORECASE)
    text = re.sub(r"<script\b[^>]*>.*?</script>", "<script></script>", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b[^>]*>.*?</style>", "<style></style>", text, flags=re.IGNORECASE | re.DOTALL)
    return text


def _exaggerated_scale_penalty(html: str) -> int:
    text = str(html or "")
    penalty = 0
    penalty += len(re.findall(r"text-\[(?:7[2-9]|8[0-9]|9[0-9]|1[0-9]{2,})px\]", text))
    penalty += len(re.findall(r"\b(?:md:)?text-(?:8xl|9xl)\b", text))
    penalty += len(re.findall(r"py-\[(?:1[6-9][0-9]|[2-9][0-9]{2,})px\]", text))
    penalty += len(re.findall(r"\b(?:md:)?py-(?:32|36|40)\b", text))
    penalty += len(re.findall(r"gap-\[(?:8[0-9]|[1-9][0-9]{2,})px\]", text))
    penalty += len(re.findall(r"font-size\s*:\s*(?:7[2-9]|8[0-9]|9[0-9]|1[0-9]{2,})px", text, flags=re.IGNORECASE))
    if "tracking-[-0.02em]" in text or "tracking-[-0.01em]" in text:
        penalty += 1
    if "section-padding-desktop" in text and len(text) > 8000:
        penalty += 1
    return min(6, penalty)


def _placeholder_copy_found(visible_text: str) -> bool:
    lowered = visible_text.lower()
    placeholders = [
        "lorem ipsum", "sample text", "placeholder", "untitled", "your app", "dashboard title",
        "project name", "task one", "task 1", "metric title", "coming soon",
    ]
    return any(item in lowered for item in placeholders)


def _requires_full_home_content(request: str) -> bool:
    text = str(request or "").lower()
    label = _page_label_from_request(request).lower()
    if label and label != "home":
        return False
    if label == "home" and ("site pages:" in text or len(_explicit_website_page_labels(request)) >= 2):
        return True
    return bool(not label and _is_multipage_website_request(request))


def _is_marketing_website_request(request: str) -> bool:
    text = str(request or "").lower()
    app_text = text
    for phrase in ("no dashboard", "not a dashboard", "no login", "no login portal", "not a login portal", "not a portal", "no portal", "no app workspace", "no workspace", "not an app workspace"):
        app_text = app_text.replace(phrase, " ")
    strong_site_intent = any(phrase in text for phrase in ("landing page", "landing website", "marketing website", "normal website", "company website", "business website", "four-page", "4-page", "four pages", "4 pages"))
    wants_site = strong_site_intent or any(phrase in text for phrase in ("multi-page website", "multipage website", "website with", "website for"))
    wants_site = wants_site or ("website" in text and any(term in text for term in ("home", "about", "services", "contact", "collections", "atelier", "pages")))
    app_intent = any(phrase in app_text for phrase in ("dashboard", "portal", "command center", "workspace", "management app", "admin app"))
    return wants_site and (strong_site_intent or not app_intent)


def _is_landing_page_request(request: str) -> bool:
    text = str(request or "").lower()
    return "landing page" in text or "landing website" in text


def _is_multipage_website_request(request: str) -> bool:
    text = str(request or "").lower()
    if not _is_marketing_website_request(request):
        return False
    if len(_explicit_website_page_labels(request)) >= 2:
        return True
    if _is_landing_page_request(request):
        return False
    multipage_markers = (
        "four-page", "4-page", "four pages", "4 pages", "multi-page", "multipage",
        "normal website", "company website", "business website", "website with 4", "website with four",
    )
    if any(marker in text for marker in multipage_markers):
        return True
    if _is_landing_page_request(request):
        return False
    return False


def _developer_tools_request(request_lower: str) -> bool:
    return any(
        term in request_lower
        for term in (
            "developer tool", "developer tools", "backend-as-a-service", "backend as a service", "baas",
            "self-hosted", "self hosted", "open-source", "open source", "no-code backend",
            "api monetization", "api key", "api keys", "websocket", "websockets", "web3", "x402",
            "plugin marketplace", "sdk", "cli", "docs", "documentation", "ai agent", "ai agents",
        )
    )


def _domain_decision_text(request_lower: str) -> str:
    text = str(request_lower or "").lower()
    text = re.sub(r"\bnexus\s*forge\b\s+(?:next\.?js\s+)?style profile\b", " ", text)
    text = re.sub(r"\bnexusforge\b\s+(?:next\.?js\s+)?style profile\b", " ", text)
    text = re.sub(r"\bstyle profile:\s*nexus\s*forge\b", " ", text)
    text = re.sub(r"\bfrontend should follow[^.]{0,120}\bnexus\s*forge[^.]*", " ", text)
    text = re.sub(
        r"\b(?:avoid|do not|don't|no|not)\s+[^.]{0,160}\b(?:developer|web3|backend|nexus\s*forge|api|cli|sdk|self-hosted)[^.]*",
        " ",
        text,
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _developer_fallback_request(request_lower: str) -> bool:
    text = _domain_decision_text(request_lower)
    if _robotics_logistics_request(text) or _energy_climate_request(text):
        return False
    if any(term in text for term in ("field service", "hvac", "plumbing", "electrical", "technician", "dispatch", "university", "registrar", "student")):
        return False
    return _developer_tools_request(text) or any(
        term in text
        for term in (
            "developer platform",
            "developer landing",
            "backend platform",
            "api platform",
            "nexus forge is",
        )
    )


def _robotics_logistics_request(request_lower: str) -> bool:
    return any(
        term in request_lower
        for term in (
            "warehouse robotics",
            "robotics company",
            "robotics network",
            "robot fleet",
            "autonomous mobile robot",
            "autonomous mobile robots",
            "amr",
            "agv",
            "fulfillment robot",
            "fulfillment robots",
            "warehouse automation",
            "3pl",
            "third-party logistics",
            "fulfillment",
            "pick wave",
            "pick waves",
            "dock congestion",
            "route optimization",
            "inventory handoff",
            "robot orchestration",
            "robotics platform",
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


def _bad_website_handoff_findings(html: str, visible_text: str, request: str, product_name: str) -> list[str]:
    if not _is_marketing_website_request(request):
        return []
    findings: list[str] = []
    lower_html = str(html or "").lower()
    label = _page_label_from_request(request)
    brand = _clean(product_name)
    configured_threshold = int(config_value("design_critique_min_score", 72) or 72)
    if _exaggerated_scale_penalty(html) >= 3:
        findings.append("uses exaggerated type or spacing scale")
    section_count = lower_html.count("<section")
    if configured_threshold > 30 and _requires_full_home_content(request) and section_count < 4:
        findings.append("home page is too shallow; expected at least four meaningful sections before footer")
    elif configured_threshold > 30 and _is_landing_page_request(request) and section_count < 3:
        findings.append("landing page is too shallow; expected hero plus supporting proof/conversion sections")
    if configured_threshold > 30 and section_count <= 1 and "<footer" in lower_html:
        findings.append("footer appears before enough page content")
    root = _parse_html_fragment(html)
    if label:
        for heading in _texts_by_tag(root, ("h1", "h2"), limit=12):
            if _is_route_label_heading(heading, label, brand):
                findings.append(f"uses route label as visible headline ({_clean(heading)})")
                break
        explicit_labels = {_clean(item).lower() for item in _explicit_website_page_labels(request)}
        default_labels = set() if _is_landing_page_request(request) else {"home", "about", "services", "service", "contact", "pricing"}
        other_page_labels = (explicit_labels or default_labels) - {_clean(label).lower()}
        for node in [item for item in _descendants(root) if item.tag == "section"]:
            heading = _clean(_first_text(node, ("h1", "h2", "h3"))).lower()
            if heading in other_page_labels:
                findings.append(f"uses another route label as a section heading ({heading})")
                break
    if _repeated_heading_findings(root):
        findings.append("repeats major headings inside one page")
    return _dedupe(findings)


def _visual_composition_review(html: str, visible_text: str, brief: dict[str, Any]) -> dict[str, Any]:
    """Lightweight visual-polish gate until screenshot scoring is available."""

    request = _clean(brief.get("request"))
    lower_html = _compact_html_for_scoring(html).lower()
    word_count = len(re.findall(r"[A-Za-z][A-Za-z'-]{2,}", visible_text or ""))
    is_marketing = _is_marketing_website_request(request)
    is_dashboard = (brief.get("design_strategy") or {}).get("surface") == "operational_dashboard"
    findings: list[str] = []
    score = 0

    if "<header" in lower_html and ("<nav" in lower_html or "aria-label=\"primary" in lower_html):
        score += 14
    elif "<nav" in lower_html:
        score += 10
    elif is_marketing:
        findings.append("missing credible header/navigation structure")

    section_count = lower_html.count("<section")
    required_sections = 2 if is_marketing else (2 if is_dashboard else 1)
    if is_marketing and _is_landing_page_request(request):
        required_sections = 3
    if is_marketing and _requires_full_home_content(request):
        required_sections = 4
    if section_count >= required_sections:
        score += 18
    else:
        findings.append(f"only {section_count} meaningful section(s); expected at least {required_sections}")

    if any(token in lower_html for token in ("<img", "<picture", "<figure", "<svg", "<canvas", "<video", "<table", "<pre", "<code", "<article", "<form")):
        score += 18
    else:
        findings.append("missing a domain-specific visual or proof object")

    if any(token in lower_html for token in ("<button", "<a ", "<form", "role=\"button")):
        score += 14
    else:
        findings.append("missing visible user actions")

    if word_count >= (80 if is_marketing else 45):
        score += 14
    elif word_count >= 35:
        score += 8
    else:
        findings.append("visible copy is too thin to judge product fit")

    scale_penalty = _exaggerated_scale_penalty(html)
    if scale_penalty >= 3:
        findings.append("uses exaggerated type or spacing likely to clip first viewport content")
        score -= 18
    else:
        score += 10

    if re.search(r"\b(Home|About|Services?|Contact)\s+[12]\b", visible_text or "", flags=re.IGNORECASE):
        findings.append("visible copy contains numbered page artifacts")
        score -= 20

    if _repeated_heading_findings(_parse_html_fragment(html)):
        findings.append("major headings repeat, suggesting page merge or scaffold copy")
        score -= 10

    configured_threshold = int(config_value("design_critique_min_score", 72) or 72)
    score = max(0, min(100, score))
    severe: list[str] = []
    for item in findings:
        if (
            "numbered page artifacts" in item
            or "exaggerated type" in item
            or "missing visible user actions" in item
            or "missing credible header/navigation" in item
        ):
            severe.append(item)
            continue
        if "meaningful section" in item and is_marketing and _is_landing_page_request(request) and configured_threshold > 30:
            severe.append(item)
        if "meaningful section" in item and is_marketing and _requires_full_home_content(request) and configured_threshold > 30:
            severe.append(item)
    visual_threshold = 32 if configured_threshold <= 30 else (40 if configured_threshold <= 50 else (45 if is_marketing else 42))
    return {
        "score": score,
        "passed": score >= visual_threshold and not severe,
        "findings": _dedupe(findings),
        "needs_screenshot_review": True,
        "method": "html_semantic_visual_proxy",
    }


def _page_label_from_request(request: str) -> str:
    match = re.search(r"\bPage label:\s*([A-Za-z][A-Za-z0-9 _-]{1,32})\.", str(request or ""), flags=re.IGNORECASE)
    return _clean(match.group(1)) if match else ""


def _page_label_from_scope(artifact_scope: str) -> str:
    scope = _clean_artifact_scope(artifact_scope)
    if not scope.startswith("pages/"):
        return ""
    page_id = scope.split("/", 1)[1].split("/", 1)[0]
    labels = {
        "home": "Home",
        "about": "About",
        "services": "Services",
        "pricing": "Pricing",
        "contact": "Contact",
    }
    return labels.get(page_id, page_id.replace("-", " ").title())


def _repeated_heading_findings(root: _HtmlNode) -> bool:
    seen: set[str] = set()
    for text in _texts_by_tag(root, ("h1", "h2", "h3"), limit=80):
        key = _clean(text).lower()
        if len(key) < 8:
            continue
        if key in seen:
            return True
        seen.add(key)
    return False


def _off_domain_findings(visible_text: str, request: str) -> list[str]:
    text = visible_text.lower()
    requested = request.lower()
    guarded_terms = {
        "central intelligence agency": ("central intelligence agency", "cia"),
        "deploy emergency services": ("emergency services", "emergency response"),
        "emergency services": ("emergency services", "emergency response"),
        "network attack": ("cybersecurity", "security", "network attack"),
        "aggressive probe": ("cybersecurity", "security", "network attack"),
        "patient": ("hospital", "clinic", "healthcare", "patient"),
        "invoice": ("invoice", "billing", "accounts receivable"),
        "sales pipeline": ("sales", "crm", "pipeline"),
        "ecommerce": ("ecommerce", "commerce", "storefront"),
    }
    findings: list[str] = []
    if _energy_climate_request(requested):
        for term in _energy_wrong_domain_terms():
            if term in text and term not in requested:
                findings.append(term)
    if _robotics_logistics_request(_domain_decision_text(requested)):
        for term in (
            "self-hosted backend",
            "web3 modules",
            "web3 module",
            "cli install",
            "api routes",
            "schema builder",
            "nexus forge",
            "x402",
            "base wallet",
            "plugin marketplace",
            "no-code backend",
            "backend-as-a-service",
            "baas",
        ):
            if term in text and term not in requested:
                findings.append(term)
    for term, allowed_context in guarded_terms.items():
        if term not in text:
            continue
        if any(allowed in requested for allowed in allowed_context):
            continue
        findings.append(term)
    return findings


def _copy_specificity_findings(visible_text: str, request: str) -> list[str]:
    text = _clean(visible_text).lower()
    requested = str(request or "").lower()
    findings: list[str] = []
    generic_phrases = (
        "ai workflows your team can inspect and control",
        "automate the routine without losing oversight",
        "from prompt to approved action",
        "smarter operations",
        "business deserves",
        "project signal",
        "make daily workflows easier",
    )
    generic_hits = [phrase for phrase in generic_phrases if phrase in text and phrase not in requested]
    if generic_hits:
        findings.append(f"generic scaffold phrase ({generic_hits[0]})")
    if _robotics_logistics_request(_domain_decision_text(requested)):
        domain_terms = (
            "warehouse", "robot", "robots", "robotics", "fleet", "route", "routing", "exception",
            "exceptions", "throughput", "fulfillment", "pick", "picking", "dock", "inventory",
            "wms", "3pl", "orchestration", "operator", "facility", "uptime", "override",
        )
        domain_matches = sum(1 for term in domain_terms if re.search(rf"\b{re.escape(term)}s?\b", text))
        if domain_matches < 5:
            findings.append("copy lacks warehouse robotics specifics")
    return _dedupe(findings)


def _interactive_accessibility_findings(html: str) -> list[str]:
    compact = _compact_html_for_scoring(html)
    findings: list[str] = []
    empty_button_pattern = re.compile(r"<button\b(?P<attrs>[^>]*)>(?P<body>(?:\s|<[^>]+>)*)</button>", re.IGNORECASE)
    for match in empty_button_pattern.finditer(compact):
        attrs = match.group("attrs") or ""
        body = _clean(re.sub(r"<[^>]+>", " ", match.group("body") or ""))
        if body:
            continue
        if re.search(r"\b(?:aria-label|aria-labelledby|title)\s*=", attrs, re.IGNORECASE):
            continue
        findings.append("button has no visible text or accessible name")
        break
    empty_link_pattern = re.compile(r"<a\b(?P<attrs>[^>]*)>(?P<body>(?:\s|<[^>]+>)*)</a>", re.IGNORECASE)
    for match in empty_link_pattern.finditer(compact):
        attrs = match.group("attrs") or ""
        body = _clean(re.sub(r"<[^>]+>", " ", match.group("body") or ""))
        if body:
            continue
        if re.search(r"\b(?:aria-label|aria-labelledby|title)\s*=", attrs, re.IGNORECASE):
            continue
        findings.append("link has no visible text or accessible name")
        break
    return _dedupe(findings)


def _image_quality_findings(html: str, request: str) -> list[str]:
    if not _is_marketing_website_request(request):
        return []
    compact = _compact_html_for_scoring(html)
    lower = compact.lower()
    findings: list[str] = []
    low_opacity_bg = re.search(
        r"background(?:-image)?\s*:[^;\"']{0,80}url\([^)]*\)[\s\S]{0,220}opacity\s*:\s*0\.(?:0|1|2|3)\d*",
        compact,
        flags=re.IGNORECASE,
    ) or re.search(
        r"opacity\s*:\s*0\.(?:0|1|2|3)\d*[\s\S]{0,220}background(?:-image)?\s*:[^;\"']{0,80}url\([^)]*\)",
        compact,
        flags=re.IGNORECASE,
    )
    low_opacity_class = re.search(r"\bopacity-(?:0|5|10|15|20|25|30|35)\b", lower) and any(token in lower for token in ("bg-cover", "background-image", "<img", "<picture"))
    explicit_blur = any(token in lower for token in ("filter: blur", "filter:blur", "blur(", "backdrop-filter: blur"))
    if low_opacity_bg or low_opacity_class:
        findings.append("hero imagery is washed out by very low opacity")
    if explicit_blur and any(token in lower for token in ("hero", "background-image", "<img", "<picture", "bg-cover")):
        findings.append("hero/media layer appears blurred")
    return _dedupe(findings)


def _keywords(text: str) -> list[str]:
    stopwords = {
        "about", "after", "again", "against", "also", "before", "being", "build", "center", "clean",
        "code", "copy", "create", "design", "direction", "each", "frontend", "include", "into",
        "make", "nextjs", "only", "polished", "prioritize", "product", "quality", "real", "same",
        "screen", "show", "specific", "style", "their", "there", "these", "thing", "this", "use",
        "using", "visible", "web", "with", "workflow", "workflows",
    }
    tokens = [token.lower() for token in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", text or "")]
    result: list[str] = []
    for token in tokens:
        if token in stopwords or token in result:
            continue
        result.append(token)
    return result[:24]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-") or "item"


def _provider_line(provider: Any) -> str:
    if not isinstance(provider, dict):
        return "unavailable"
    state = "ready" if provider.get("ready") else "blocked"
    return f"{state} - {provider.get('reason') or provider.get('setup_hint') or provider.get('provider')}"


def _node_package_available(package: str, *, probe: bool) -> bool:
    clean = str(package or "").strip()
    if not clean:
        return False
    package_path = ROOT_DIR / "node_modules" / Path(*clean.split("/"))
    if package_path.exists():
        return True
    if not probe or not shutil.which("node"):
        return False
    script = f"import('{clean}').then(()=>process.exit(0)).catch(()=>process.exit(1));"
    try:
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
        return completed.returncode == 0
    except Exception:
        return False


def _configured_env(env_key: str) -> bool:
    value = _env_value(env_key)
    lowered = value.strip().lower()
    return bool(value.strip() and lowered not in {"placeholder", "changeme", "your_api_key_here"} and not lowered.startswith("your_"))


def _env_value(env_key: str) -> str:
    """Read one configured environment value without exposing or storing it."""

    name = str(env_key or "").strip()
    if not name:
        return ""
    if name in os.environ:
        return str(os.environ.get(name) or "")
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return ""
    try:
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() != name:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            return value
    except Exception:
        return ""
    return ""


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return default


def _tail_text(value: str, limit: int = 4000) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[-limit:]


def _dedupe(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values or []:
        marker = json.dumps(value, sort_keys=True, default=str) if isinstance(value, (dict, list)) else str(value)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return result


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())

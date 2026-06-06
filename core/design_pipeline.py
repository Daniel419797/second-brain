"""End-to-end design pipeline for Friday's product-studio UI work."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from core import design_director, design_providers, dribbble_scraper, product_studio_gates, quality_taste_layer, search_broker
from core.config import config_value, resolve_coding_root

FRIDAY_DIR = ".friday"
PIPELINE_DIR = "design-pipeline"


PIPELINE_STAGES = [
    ("research", "Research -> market, competitors, references, design category"),
    ("brief", "Brief -> product/design spec"),
    ("direction", "Design direction -> emotional feel, composition archetype, visual grammar"),
    ("tokens", "Tokens -> color, type, spacing, radius, shadows, motion"),
    ("page_contracts", "Page contracts -> sections, components, copy, assets, responsive behavior"),
    ("variants", "Generate 2-3 variants -> Stitch / image model / local design memory"),
    ("critique", "Critique variants -> vision + Playwright + taste rules"),
    ("implement", "Implement best variant -> Next.js/shadcn/Tailwind/Framer/Three as needed"),
    ("browser_verification", "Browser verification -> screenshots, dead buttons, layout, mobile, accessibility"),
    ("fix_loop", "Fix loop -> patch, rerun, re-screenshot"),
    ("deliver", "Deliver -> proof report, files, preview, gaps"),
]


def pipeline_contract() -> dict[str, Any]:
    """Return the public contract for the design pipeline."""

    return {
        "version": "design_pipeline_v1",
        "stages": [{"id": stage_id, "label": label} for stage_id, label in PIPELINE_STAGES],
        "readiness_rule": "A design handoff is usable only when a variant is selected, rejected variants are excluded, source is applied when requested, and browser/taste proof passes when those gates are enabled.",
        "approval_rules": [
            "External design/provider calls obey provider readiness and approval config.",
            "Ad posting, paid API spend, production deploy, and customer outreach stay approval-gated.",
            "Generated mockups and external inspiration are evidence, not source code, unless converted through the selected handoff.",
        ],
    }


def run(
    request: str,
    *,
    root: str | Path = "",
    product_name: str = "",
    stack: dict[str, Any] | None = None,
    variant_count: int | None = None,
    dry_run: bool = True,
    apply_to_source: bool = False,
    run_browser: bool | None = None,
    research_live: bool | None = None,
    max_fix_attempts: int | None = None,
) -> dict[str, Any]:
    """Run Friday's full design sequence and write proof artifacts.

    Dry runs still create the spec, research plan, tokens, page contracts, and
    critique plan. Live runs may call configured providers, apply the selected
    handoff, and optionally run browser/taste gates.
    """

    project_root = resolve_coding_root(root or "")
    stack = stack or {}
    name = _clean(product_name) or _product_name_from_request(request) or project_root.name
    pipeline_root = project_root / FRIDAY_DIR / PIPELINE_DIR
    pipeline_root.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    stages: list[dict[str, Any]] = []
    gaps: list[str] = []

    initial_strategy, initial_contract = _initial_design_context(request, name, stack)
    research = _research_context(request, name, initial_strategy, initial_contract, root=project_root, dry_run=dry_run, research_live=research_live)
    research_artifacts = _write_stage(pipeline_root, "01-market-research", research, _research_md(research))
    artifacts.extend([*(research.get("artifacts") or []), *research_artifacts])
    _stage(stages, "research", research.get("status") or "planned", research.get("summary") or "", research_artifacts)

    brief = design_providers.design_brief(
        request,
        root=project_root,
        product_name=name,
        stack=stack,
        create_files=True,
        research_context=research,
    )
    artifacts.extend(brief.get("artifacts") or [])
    design_context = brief.get("design_context") if isinstance(brief.get("design_context"), dict) else {}
    strategy = brief.get("design_strategy") if isinstance(brief.get("design_strategy"), dict) else {}
    contract = brief.get("design_contract") if isinstance(brief.get("design_contract"), dict) else {}

    spec = _product_design_spec(brief, design_context, strategy, contract)
    spec_artifacts = _write_stage(pipeline_root, "02-product-design-spec", spec, _spec_md(spec))
    artifacts.extend(spec_artifacts)
    _stage(stages, "brief", "completed", "Product/design spec written from research-enriched context.", spec_artifacts)
    if research.get("status") == "failed":
        gaps.append(str(research.get("summary") or "Research failed."))

    direction = _design_direction(brief, design_context, strategy)
    artifacts.extend(_write_stage(pipeline_root, "03-design-direction", direction, _direction_md(direction)))
    _stage(stages, "direction", "completed", "Design direction, emotion, composition, and visual grammar captured.", artifacts[-2:])

    tokens = _token_contract(design_context, strategy)
    token_artifacts = _write_stage(pipeline_root, "04-design-tokens", tokens, _tokens_md(tokens))
    token_css = pipeline_root / "04-design-tokens.css"
    token_css.write_text(_tokens_css(tokens), encoding="utf-8")
    artifacts.extend([*token_artifacts, str(token_css)])
    _stage(stages, "tokens", "completed", "Design tokens and motion rules captured.", [*token_artifacts, str(token_css)])

    page_contracts = _page_contracts(request, name, brief, design_context, strategy, contract)
    artifacts.extend(_write_stage(pipeline_root, "05-page-contracts", page_contracts, _page_contracts_md(page_contracts)))
    _stage(stages, "page_contracts", "completed", "Page/component/content contracts written.", artifacts[-2:])

    generation = _generate_variants(
        request,
        project_root=project_root,
        product_name=name,
        stack=stack,
        variant_count=variant_count,
        dry_run=dry_run,
        research_context=research,
    )
    artifacts.extend(str(item) for item in (generation.get("artifacts") or []) if _clean(item))
    artifacts.extend(_write_stage(pipeline_root, "06-variants", generation, _variants_md(generation)))
    variants_status = str(generation.get("status") or ("planned" if dry_run else "blocked"))
    _stage(stages, "variants", variants_status, generation.get("summary") or "", artifacts[-2:])

    critique = _critique_summary(generation)
    artifacts.extend(_write_stage(pipeline_root, "07-critique", critique, _critique_md(critique)))
    _stage(stages, "critique", critique.get("status") or variants_status, critique.get("summary") or "", artifacts[-2:])
    if not generation.get("frontend_handoff_allowed"):
        gaps.append(generation.get("summary") or "No selected design variant is available for handoff.")

    applied = _apply_selected(
        project_root,
        request=request,
        product_name=name,
        generation=generation,
        dry_run=dry_run,
        apply_to_source=apply_to_source,
    )
    artifacts.extend(str(item) for item in (applied.get("artifacts") or []) if _clean(item))
    artifacts.extend(_write_stage(pipeline_root, "08-implementation", applied, _implementation_md(applied, design_context)))
    _stage(stages, "implement", applied.get("status") or "skipped", applied.get("summary") or "", artifacts[-2:])
    if apply_to_source and not dry_run and generation.get("frontend_handoff_allowed") and not applied.get("ok"):
        gaps.append(applied.get("summary") or "Selected design could not be applied to frontend source.")

    browser_required = _should_run_browser(dry_run=dry_run, apply_to_source=apply_to_source, run_browser=run_browser)
    browser = _browser_verification(
        project_root,
        request=request,
        stack=stack,
        generation=generation,
        enabled=browser_required,
    )
    artifacts.extend(str(item) for item in (browser.get("artifacts") or []) if _clean(item))
    artifacts.extend(_write_stage(pipeline_root, "09-browser-verification", browser, _browser_md(browser)))
    _stage(stages, "browser_verification", browser.get("status") or "skipped", browser.get("summary") or "", artifacts[-2:])
    if browser_required and not browser.get("ok"):
        gaps.extend(str(item) for item in browser.get("gaps") or [])

    fix_loop = _fix_loop(
        project_root,
        request=request,
        stack=stack,
        generation=generation,
        browser=browser,
        enabled=browser_required,
        max_attempts=max_fix_attempts,
        product_name=name,
        apply_to_source=apply_to_source,
    )
    artifacts.extend(str(item) for item in (fix_loop.get("artifacts") or []) if _clean(item))
    artifacts.extend(_write_stage(pipeline_root, "10-fix-loop", fix_loop, _fix_loop_md(fix_loop)))
    _stage(stages, "fix_loop", fix_loop.get("status") or "skipped", fix_loop.get("summary") or "", artifacts[-2:])
    if fix_loop.get("gaps"):
        gaps.extend(str(item) for item in fix_loop.get("gaps") or [])

    status = _final_status(dry_run=dry_run, generation=generation, applied=applied, browser=browser, fix_loop=fix_loop, apply_to_source=apply_to_source, run_browser=browser_required)
    ok = status in {"selected", "applied", "verified"}
    proof = {
        "generated_at": _now(),
        "version": "design_pipeline_v1",
        "root": str(project_root),
        "request": _clean(request),
        "product_name": name,
        "status": status,
        "ok": ok,
        "dry_run": bool(dry_run),
        "frontend_handoff_allowed": bool(generation.get("frontend_handoff_allowed")),
        "applied_to_source": bool(applied.get("ok")),
        "browser_verified": bool(browser.get("ok")),
        "design_visual_status": browser.get("design_visual_status") or ("not_applicable" if not browser_required else "failed"),
        "design_visual_ready": str(browser.get("design_visual_status") or "").lower() == "passed",
        "browser_gate_ready": bool(browser.get("browser_gate_ready")),
        "frontend_build_ready": bool(applied.get("ok")) if apply_to_source else bool(generation.get("frontend_handoff_allowed")),
        "technical_ready": bool(browser.get("technical_ready")),
        "stages": stages,
        "gaps": _dedupe(gaps),
        "artifacts": _dedupe(artifacts),
        "selected_variant": generation.get("selected_variant") if isinstance(generation.get("selected_variant"), dict) else None,
        "provider": generation.get("provider") or "design_pipeline",
        "summary": _summary(status, generation, applied, browser, gaps),
    }
    deliver_artifacts = _write_stage(pipeline_root, "11-final-design-proof", proof, _proof_md(proof))
    artifacts.extend(deliver_artifacts)
    _stage(stages, "deliver", "completed", "Final design pipeline proof written.", deliver_artifacts)
    proof["stages"] = stages
    proof["artifacts"] = _dedupe(artifacts)
    manifest = pipeline_root / "design-pipeline.json"
    manifest.write_text(_json_dumps(proof), encoding="utf-8")
    artifacts.append(str(manifest))

    return {
        **proof,
        "brief": brief,
        "design_plan": brief,
        "design_critique": generation,
        "applied_design": applied,
        "gate_results": browser.get("gate_results") if isinstance(browser.get("gate_results"), dict) else {},
        "quality_reviews": _quality_reviews(browser, fix_loop),
        "research": research,
        "direction": direction,
        "tokens": tokens,
        "page_contracts": page_contracts,
        "pipeline_root": str(pipeline_root),
        "artifacts": _dedupe(artifacts),
    }


def _product_design_spec(brief: dict[str, Any], context: dict[str, Any], strategy: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    user_intent = context.get("user_intent") if isinstance(context.get("user_intent"), dict) else {}
    return {
        "product_name": brief.get("product_name") or user_intent.get("product_name"),
        "request": brief.get("request"),
        "surface": user_intent.get("surface") or strategy.get("surface"),
        "industry": user_intent.get("industry") or strategy.get("industry"),
        "page_scope": user_intent.get("page_scope") or contract.get("page_label") or "primary",
        "product_goal": context.get("product_goal") or "",
        "target_audience": context.get("target_audience") or [],
        "acceptance_criteria": [
            "Design must match the product/domain instead of generic SaaS scaffolding.",
            "The first viewport must follow the selected composition archetype and avoid accidental split-hero repetition.",
            "Copy must be specific, coherent, and appropriate to the category voice.",
            "Rejected variants cannot be used as implementation source.",
            "Browser/taste evidence is required before UI-ready claims when verification is enabled.",
        ],
        "provider_policy": (brief.get("provider_status") or {}).get("selected") if isinstance(brief.get("provider_status"), dict) else {},
    }


def _initial_design_context(request: str, product_name: str, stack: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Classify product/surface before research so search does not start generic."""

    contract_fn = getattr(design_providers, "_design_contract", None)
    contract: dict[str, Any] = {}
    if callable(contract_fn):
        try:
            contract = contract_fn(request, product_name, stack)
        except Exception:
            contract = {}
    try:
        strategy = design_director.design_strategy(
            request,
            product_name,
            page_label=str(contract.get("page_label") or ""),
            stack=stack,
        )
    except Exception:
        strategy = {}
    return strategy if isinstance(strategy, dict) else {}, contract if isinstance(contract, dict) else {}


def _research_context(
    request: str,
    product_name: str,
    strategy: dict[str, Any],
    contract: dict[str, Any],
    *,
    root: str | Path = "",
    dry_run: bool,
    research_live: bool | None,
) -> dict[str, Any]:
    industry = _clean(strategy.get("industry") or "general_business")
    surface = _clean(strategy.get("surface") or contract.get("surface") or "product_app")
    queries = _research_queries(request, product_name, industry, surface)
    live = bool(research_live) if research_live is not None else (not dry_run and bool(config_value("design_research_live_default", True)))
    inspiration: list[dict[str, Any]] = []
    if not live:
        return {
            "status": "planned",
            "summary": "Research plan prepared; live search was not run.",
            "live": False,
            "queries": queries,
            "inspiration_references": inspiration,
            "category": {"industry": industry, "surface": surface},
        }
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for query in queries:
        try:
            payload = search_broker.search(query, limit=4, use_cache=True)
        except Exception as exc:
            errors.append(f"{query}: {exc}")
            continue
        results.append({"query": query, **payload})
    dribbble: dict[str, Any] = {}
    if bool(config_value("design_research_dribbble_enabled", True)):
        try:
            dribbble = dribbble_scraper.collect(
                f"{product_name or request} {industry} {surface.replace('_', ' ')}",
                root=root,
                limit=int(config_value("design_research_dribbble_limit", 4) or 4),
                create_artifact=True,
            )
        except Exception as exc:
            errors.append(f"dribbble: {exc}")
    ok = any(item.get("ok") for item in results)
    return {
        "status": "completed" if ok or dribbble.get("ok") else "limited",
        "summary": "Live design research completed before prompt compilation." if ok or dribbble.get("ok") else "Live design research produced no usable search results; using taxonomy and local inspiration.",
        "live": True,
        "queries": queries,
        "results": results,
        "errors": errors,
        "inspiration_references": inspiration,
        "dribbble_references": dribbble,
        "artifacts": dribbble.get("artifacts") or [],
        "category": {"industry": industry, "surface": surface},
    }


def _should_run_browser(*, dry_run: bool, apply_to_source: bool, run_browser: bool | None) -> bool:
    if run_browser is not None:
        return bool(run_browser)
    if dry_run:
        return False
    if apply_to_source:
        return bool(config_value("design_pipeline_browser_required", True))
    return False


def _design_direction(brief: dict[str, Any], context: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
    visual = context.get("visual_context") if isinstance(context.get("visual_context"), dict) else {}
    return {
        "message": strategy.get("message") or context.get("message") or "",
        "emotional_feel": strategy.get("emotional_feel") or context.get("emotional_intent") or "",
        "creative_direction": strategy.get("direction") or visual.get("direction") or "",
        "composition": strategy.get("composition") or {},
        "experience_mode": context.get("experience_mode") or {},
        "visual_grammar": {
            "visual_language": strategy.get("visual_language") or visual.get("visual_language") or "",
            "layout_signature": strategy.get("layout_signature") or visual.get("layout_signature") or "",
            "imagery": strategy.get("imagery") or visual.get("imagery") or "",
            "copy_voice": strategy.get("copy_voice") or visual.get("copy_voice") or "",
        },
        "variant_directions": strategy.get("variant_directions") or [],
        "anti_patterns": strategy.get("anti_patterns") or [],
        "quality_bar": strategy.get("quality_bar") or [],
        "prompt_block": strategy.get("prompt_block") or "",
        "stitch_prompt": brief.get("stitch_prompt") or "",
    }


def _token_contract(context: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
    visual = context.get("visual_context") if isinstance(context.get("visual_context"), dict) else {}
    brand = context.get("brand_system") if isinstance(context.get("brand_system"), dict) else {}
    tokens = visual.get("tokens") if isinstance(visual.get("tokens"), dict) else {}
    return {
        "brand_system": brand,
        "tokens": tokens,
        "palette": strategy.get("palette") or visual.get("palette") or "",
        "typography": strategy.get("typography") or visual.get("typography") or "",
        "spacing": tokens.get("spacing") or "8px grid with page-specific rhythm",
        "radius": tokens.get("radius") or brand.get("radius") or "domain-appropriate radius",
        "shadow": tokens.get("shadow") or brand.get("shadow") or "purposeful elevation only",
        "motion": brand.get("motion_style") or visual.get("interaction_model") or "",
        "experience_mode": context.get("experience_mode") or {},
    }


def _page_contracts(request: str, product_name: str, brief: dict[str, Any], context: dict[str, Any], strategy: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    surface = _clean(strategy.get("surface") or contract.get("surface") or "")
    pages = _page_specs(request) if surface == "marketing_website" else [{"id": "home", "label": contract.get("page_label") or "Primary", "route": "/"}]
    return {
        "product_name": product_name,
        "surface": surface,
        "pages": pages,
        "section_blueprint": context.get("section_blueprint") or [],
        "component_inventory": context.get("component_inventory") or [],
        "copy_bank": context.get("copy_bank") or {},
        "asset_direction": (context.get("brand_system") or {}).get("asset_direction") if isinstance(context.get("brand_system"), dict) else "",
        "responsive_behavior": {
            "desktop": "Use the selected composition archetype with stable spacing and no oversized accidental hero type.",
            "tablet": "Preserve hierarchy while reducing columns before text wraps awkwardly.",
            "mobile": "Single-column, accessible controls, no clipped text, no horizontal overflow.",
        },
        "implementation_requirements": (context.get("handoff_requirements") or {}).get("frontend") if isinstance(context.get("handoff_requirements"), dict) else [],
    }


def _generate_variants(
    request: str,
    *,
    project_root: Path,
    product_name: str,
    stack: dict[str, Any],
    variant_count: int | None,
    dry_run: bool,
    research_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if _is_multipage_website_request(request):
        return design_providers.run_multipage_website_design_critique(
            request,
            root=project_root,
            product_name=product_name,
            stack=stack,
            variant_count=variant_count,
            dry_run=dry_run,
            research_context=research_context,
        )
    return design_providers.run_design_critique_loop(
        request,
        root=project_root,
        product_name=product_name,
        stack=stack,
        variant_count=variant_count,
        dry_run=dry_run,
        research_context=research_context,
    )


def _critique_summary(generation: dict[str, Any]) -> dict[str, Any]:
    variants = generation.get("variants") if isinstance(generation.get("variants"), list) else []
    pages = generation.get("pages") if isinstance(generation.get("pages"), list) else []
    selected = generation.get("selected_variant") if isinstance(generation.get("selected_variant"), dict) else None
    return {
        "status": generation.get("status") or "unknown",
        "summary": generation.get("summary") or "",
        "frontend_handoff_allowed": bool(generation.get("frontend_handoff_allowed")),
        "selected_variant": selected,
        "variant_count": generation.get("variant_count") or len(variants),
        "accepted_variants": [item for item in variants if isinstance(item, dict) and item.get("accepted")],
        "rejected_variants": generation.get("rejected_variants") or [item for item in variants if isinstance(item, dict) and not item.get("accepted")],
        "pages": pages,
        "vision_critique": {
            "source": "Stitch/local design scoring plus Friday taste rules; browser visual review runs in the browser_verification stage when enabled.",
            "score_threshold": generation.get("score_threshold"),
            "diversity": generation.get("diversity") or {},
        },
    }


def _apply_selected(project_root: Path, *, request: str, product_name: str, generation: dict[str, Any], dry_run: bool, apply_to_source: bool) -> dict[str, Any]:
    if dry_run:
        return {"ok": False, "status": "planned", "summary": "Source application skipped because dry_run=True.", "artifacts": []}
    if not apply_to_source:
        return {"ok": False, "status": "skipped", "summary": "Selected design was not applied because apply_to_source=False.", "artifacts": []}
    if not generation.get("frontend_handoff_allowed"):
        return {"ok": False, "status": "blocked", "summary": "No accepted design handoff is available to apply.", "artifacts": []}
    if _is_multipage_website_request(request):
        return design_providers.apply_website_designs_to_nextjs(project_root, request=request, product_name=product_name)
    return design_providers.apply_selected_design_to_nextjs(project_root, request=request, product_name=product_name)


def _browser_verification(project_root: Path, *, request: str, stack: dict[str, Any], generation: dict[str, Any], enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {
            "ok": False,
            "status": "skipped",
            "summary": "Browser verification skipped for this design pipeline run.",
            "design_visual_status": "not_applicable",
            "design_visual_ready": False,
            "browser_gate_ready": False,
            "frontend_build_ready": False,
            "technical_ready": False,
            "artifacts": [],
            "gaps": [],
        }
    gate_results = product_studio_gates.execute_gates(
        project_root,
        stack=stack,
        install=False,
        tests=False,
        audits=False,
        browser=True,
        preview=True,
        request=request,
    )
    review = quality_taste_layer.review_project(project_root, request, stack=stack, gate_results=gate_results, design_handoff=generation)
    gaps = [*(gate_results.get("failed_required") or []), *[item.get("summary") or item.get("id") for item in (review.get("issues") or []) if isinstance(item, dict) and int(item.get("severity") or 0) >= 4]]
    visual_status = product_studio_gates.gate_status(gate_results, "browser_visual_review")
    browser_status = product_studio_gates.gate_status(gate_results, "browser_check")
    quality_status = product_studio_gates.gate_status(gate_results, "browser_quality")
    design_visual_ready = visual_status == "passed" and browser_status == "passed" and quality_status == "passed" and bool(review.get("ok"))
    frontend_build_ready = product_studio_gates.gate_status(gate_results, "local_preview") == "passed"
    required_groups = {"install", "tests", "security", "browser", "preview"}
    attempted_groups = {
        str(gate.get("group") or "")
        for gate in (gate_results.get("gates") or [])
        if isinstance(gate, dict) and str(gate.get("status") or "") not in {"", "skipped", "not_applicable"}
    }
    full_technical_scope = required_groups.issubset(attempted_groups)
    technical_ready = bool(gate_results.get("technical_ready")) and full_technical_scope
    ok = bool(design_visual_ready)
    return {
        "ok": ok,
        "status": "passed" if ok else "needs_revision",
        "summary": "Browser and taste verification passed." if ok else "Browser or taste verification found gaps.",
        "design_visual_status": "passed" if design_visual_ready else "failed",
        "design_visual_ready": design_visual_ready,
        "browser_gate_ready": design_visual_ready,
        "frontend_build_ready": frontend_build_ready,
        "technical_ready": technical_ready,
        "technical_scope_complete": full_technical_scope,
        "gate_results": gate_results,
        "quality_review": review,
        "gaps": _dedupe(gaps),
        "artifacts": [*(gate_results.get("artifacts") or []), *(review.get("artifacts") or [])],
    }


def _fix_loop(
    project_root: Path,
    *,
    request: str,
    product_name: str,
    stack: dict[str, Any],
    generation: dict[str, Any],
    browser: dict[str, Any],
    enabled: bool,
    max_attempts: int | None,
    apply_to_source: bool,
) -> dict[str, Any]:
    if not enabled:
        return {"ok": False, "status": "skipped", "summary": "Fix loop skipped because browser verification did not run.", "artifacts": [], "attempts": [], "gaps": []}
    if browser.get("ok"):
        return {"ok": True, "status": "passed", "summary": "No fix loop needed; browser/taste proof passed.", "artifacts": [], "attempts": [], "gaps": []}
    attempts: list[dict[str, Any]] = []
    artifacts: list[str] = []
    gaps: list[str] = []
    current_review = browser.get("quality_review") if isinstance(browser.get("quality_review"), dict) else {}
    for attempt in range(1, max(0, min(3, int(max_attempts if max_attempts is not None else config_value("design_pipeline_max_fix_attempts", 1) or 1))) + 1):
        if apply_to_source and bool(config_value("design_pipeline_stitch_revision_on_browser_failure", True)):
            revision_request = _revision_request_from_browser(request, browser, attempt=attempt)
            revised = _generate_variants(
                revision_request,
                project_root=project_root,
                product_name=product_name,
                stack=stack,
                variant_count=None,
                dry_run=False,
            )
            apply_revision: dict[str, Any] = {}
            rerun_revision: dict[str, Any] = {}
            if revised.get("frontend_handoff_allowed"):
                apply_revision = _apply_selected(
                    project_root,
                    request=revision_request,
                    product_name=product_name,
                    generation=revised,
                    dry_run=False,
                    apply_to_source=True,
                )
                if apply_revision.get("ok"):
                    rerun_revision = _browser_verification(project_root, request=request, stack=stack, generation=revised, enabled=True)
            attempts.append({"attempt": attempt, "mode": "stitch_revision", "revision_request": revision_request, "generation": revised, "applied": apply_revision, "rerun": rerun_revision})
            artifacts.extend(revised.get("artifacts") or [])
            artifacts.extend(apply_revision.get("artifacts") or [])
            artifacts.extend(rerun_revision.get("artifacts") or [])
            if rerun_revision.get("ok"):
                return {"ok": True, "status": "passed", "summary": "Regenerated the design from browser findings and browser/taste proof passed on rerun.", "artifacts": _dedupe(artifacts), "attempts": attempts, "gaps": []}
            gaps.extend(revised.get("gaps") or [])
            gaps.extend(rerun_revision.get("gaps") or [])
        fix = quality_taste_layer.apply_safe_fixes(project_root, current_review)
        attempts.append({"attempt": attempt, "mode": "safe_css_fix", "fix": fix})
        artifacts.extend(fix.get("changed") or [])
        artifacts.extend(fix.get("artifacts") or [])
        if not fix.get("ok"):
            gaps.append(fix.get("summary") or "No safe deterministic fix available.")
            break
        rerun = _browser_verification(project_root, request=request, stack=stack, generation=generation, enabled=True)
        attempts[-1]["rerun"] = rerun
        artifacts.extend(rerun.get("artifacts") or [])
        if rerun.get("ok"):
            return {"ok": True, "status": "passed", "summary": "Applied safe fixes and browser/taste proof passed on rerun.", "artifacts": _dedupe(artifacts), "attempts": attempts, "gaps": []}
        current_review = rerun.get("quality_review") if isinstance(rerun.get("quality_review"), dict) else current_review
        gaps.extend(rerun.get("gaps") or [])
    return {"ok": False, "status": "needs_revision", "summary": "Fix loop could not clear all browser/taste gaps.", "artifacts": _dedupe(artifacts), "attempts": attempts, "gaps": _dedupe(gaps)}


def _revision_request_from_browser(request: str, browser: dict[str, Any], *, attempt: int) -> str:
    gaps = [str(item) for item in (browser.get("gaps") or []) if _clean(item)]
    gate_results = browser.get("gate_results") if isinstance(browser.get("gate_results"), dict) else {}
    failed = [str(item) for item in (gate_results.get("failed_required") or []) if _clean(item)]
    feedback = " / ".join(_dedupe([*gaps, *failed])[:8]) or "Browser visual review failed."
    return _clean(
        f"{request}\n\nFRIDAY BROWSER-BASED DESIGN REVISION REQUIRED. "
        f"Attempt {attempt}. Fix these rendered UI issues before returning a new handoff: {feedback}. "
        "Do not return the same composition. Increase content depth, remove giant empty regions, keep media crisp, "
        "avoid blurry imagery, ensure mobile layout works, and keep all primary actions real."
    )


def _final_status(*, dry_run: bool, generation: dict[str, Any], applied: dict[str, Any], browser: dict[str, Any], fix_loop: dict[str, Any], apply_to_source: bool, run_browser: bool) -> str:
    if dry_run:
        return "planned"
    if not generation.get("frontend_handoff_allowed"):
        return "blocked"
    if apply_to_source and not applied.get("ok"):
        return "blocked"
    if run_browser and not (browser.get("ok") or fix_loop.get("ok")):
        return "needs_revision"
    if run_browser:
        return "verified"
    if apply_to_source:
        return "applied"
    return "selected"


def _research_queries(request: str, product_name: str, industry: str, surface: str) -> list[str]:
    base = _clean(product_name) or _clean(request)[:80] or "product"
    return _dedupe(
        [
            f"{base} competitors UI design {industry}",
            f"best {industry} {surface.replace('_', ' ')} examples",
            f"{industry} user needs workflow pain points",
        ]
    )


def _page_specs(request: str) -> list[dict[str, Any]]:
    getter = getattr(design_providers, "_website_page_specs", None)
    if callable(getter):
        try:
            return [dict(item) for item in getter(request)]
        except Exception:
            pass
    return [{"id": "home", "label": "Home", "route": "/"}]


def _is_multipage_website_request(request: str) -> bool:
    checker = getattr(design_providers, "_is_multipage_website_request", None)
    if callable(checker):
        try:
            return bool(checker(request))
        except Exception:
            return False
    lowered = _clean(request).lower()
    return "4 page" in lowered or "four-page" in lowered or "about" in lowered and "services" in lowered and "contact" in lowered


def _quality_reviews(browser: dict[str, Any], fix_loop: dict[str, Any]) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    if isinstance(browser.get("quality_review"), dict):
        reviews.append(browser["quality_review"])
    for attempt in fix_loop.get("attempts") or []:
        rerun = attempt.get("rerun") if isinstance(attempt, dict) else {}
        if isinstance(rerun, dict) and isinstance(rerun.get("quality_review"), dict):
            reviews.append(rerun["quality_review"])
    return reviews


def _write_stage(root: Path, stem: str, payload: dict[str, Any], markdown: str) -> list[str]:
    json_path = root / f"{stem}.json"
    md_path = root / f"{stem}.md"
    json_path.write_text(_json_dumps(payload), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    return [str(json_path), str(md_path)]


def _stage(stages: list[dict[str, Any]], stage_id: str, status: str, summary: str, artifacts: list[str] | None = None) -> None:
    stages.append({"id": stage_id, "status": _clean(status) or "unknown", "summary": _clean(summary), "artifacts": [str(item) for item in (artifacts or []) if _clean(item)]})


def _spec_md(spec: dict[str, Any]) -> str:
    return _md("Product Design Spec", [f"Product: {spec.get('product_name')}", f"Surface: {spec.get('surface')}", f"Industry: {spec.get('industry')}", f"Goal: {spec.get('product_goal')}", "", "Acceptance criteria:", *[f"- {item}" for item in spec.get("acceptance_criteria") or []]])


def _research_md(research: dict[str, Any]) -> str:
    lines = [f"Status: {research.get('status')}", research.get("summary") or "", "", "Queries:", *[f"- {item}" for item in research.get("queries") or []]]
    for result in research.get("results") or []:
        lines.append("")
        lines.append(f"Results for: {result.get('query')}")
        for item in result.get("results") or []:
            lines.append(f"- {item.get('title')}: {item.get('url')}")
    dribbble = research.get("dribbble_references") if isinstance(research.get("dribbble_references"), dict) else {}
    if dribbble:
        lines.extend(["", "Dribbble references:"])
        for item in dribbble.get("references") or []:
            if isinstance(item, dict):
                lines.append(f"- {item.get('title')}: {item.get('url')}")
    return _md("Market And Reference Research", lines)


def _direction_md(direction: dict[str, Any]) -> str:
    visual = direction.get("visual_grammar") if isinstance(direction.get("visual_grammar"), dict) else {}
    return _md("Design Direction", [f"Message: {direction.get('message')}", f"Feel: {direction.get('emotional_feel')}", f"Direction: {direction.get('creative_direction')}", f"Visual language: {visual.get('visual_language')}", f"Layout: {visual.get('layout_signature')}", "", "Variants:", *[f"- {item}" for item in direction.get("variant_directions") or []], "", "Reject:", *[f"- {item}" for item in direction.get("anti_patterns") or []]])


def _tokens_md(tokens: dict[str, Any]) -> str:
    return _md("Design Tokens", [f"Palette: {tokens.get('palette')}", f"Typography: {tokens.get('typography')}", f"Spacing: {tokens.get('spacing')}", f"Radius: {tokens.get('radius')}", f"Shadow: {tokens.get('shadow')}", f"Motion: {tokens.get('motion')}"])


def _tokens_css(tokens: dict[str, Any]) -> str:
    brand = tokens.get("brand_system") if isinstance(tokens.get("brand_system"), dict) else {}
    token_values = tokens.get("tokens") if isinstance(tokens.get("tokens"), dict) else {}
    colors = token_values.get("colors") if isinstance(token_values.get("colors"), dict) else {}
    return "\n".join(
        [
            "/* Friday design pipeline tokens. Use as implementation guidance, not an automatic override. */",
            ":root {",
            f"  --friday-brand-primary: {colors.get('primary') or brand.get('primary_color') or '#111827'};",
            f"  --friday-brand-accent: {colors.get('accent') or brand.get('accent_color') or '#f97316'};",
            f"  --friday-radius: {tokens.get('radius') or '8px'};",
            "}",
            "",
        ]
    )


def _page_contracts_md(page_contracts: dict[str, Any]) -> str:
    lines = [f"Surface: {page_contracts.get('surface')}", "", "Pages:"]
    for page in page_contracts.get("pages") or []:
        if isinstance(page, dict):
            lines.append(f"- {page.get('label') or page.get('id')}: {page.get('route')}")
    lines.extend(["", "Responsive behavior:"])
    responsive = page_contracts.get("responsive_behavior") if isinstance(page_contracts.get("responsive_behavior"), dict) else {}
    lines.extend(f"- {key}: {value}" for key, value in responsive.items())
    return _md("Page Contracts", lines)


def _variants_md(generation: dict[str, Any]) -> str:
    lines = [f"Status: {generation.get('status')}", f"Summary: {generation.get('summary')}", f"Provider: {generation.get('provider')}", f"Frontend handoff allowed: {bool(generation.get('frontend_handoff_allowed'))}"]
    selected = generation.get("selected_variant") if isinstance(generation.get("selected_variant"), dict) else {}
    if selected:
        lines.extend(["", f"Selected: {selected.get('label') or selected.get('id')} ({selected.get('score')}/100)"])
    pages = generation.get("pages") if isinstance(generation.get("pages"), list) else []
    if pages:
        lines.extend(["", "Pages:", *[f"- {item.get('label')}: {item.get('status')} score={item.get('score')}" for item in pages if isinstance(item, dict)]])
    return _md("Variant Generation", lines)


def _critique_md(critique: dict[str, Any]) -> str:
    lines = [f"Status: {critique.get('status')}", f"Summary: {critique.get('summary')}", f"Frontend handoff: {bool(critique.get('frontend_handoff_allowed'))}", f"Variant count: {critique.get('variant_count')}"]
    rejected = critique.get("rejected_variants") if isinstance(critique.get("rejected_variants"), list) else []
    if rejected:
        lines.extend(["", "Rejected variants:", *[f"- {item.get('label') or item.get('id')}: {'; '.join(item.get('rejection_reasons') or [])}" for item in rejected if isinstance(item, dict)]])
    return _md("Variant Critique", lines)


def _implementation_md(applied: dict[str, Any], context: dict[str, Any]) -> str:
    experience = context.get("experience_mode") if isinstance(context.get("experience_mode"), dict) else {}
    lines = [f"Status: {applied.get('status')}", f"Summary: {applied.get('summary')}", "", "Experience implementation guidance:", f"- Mode: {experience.get('mode_name') or experience.get('mode')}", f"- Libraries: {', '.join(experience.get('recommended_libraries') or [])}", f"- Fallback: {experience.get('fallback_requirement') or ''}"]
    files = applied.get("files") or applied.get("artifacts") or []
    if files:
        lines.extend(["", "Files/artifacts:", *[f"- {item}" for item in files]])
    return _md("Frontend Implementation", lines)


def _browser_md(browser: dict[str, Any]) -> str:
    lines = [f"Status: {browser.get('status')}", f"Summary: {browser.get('summary')}", f"OK: {bool(browser.get('ok'))}"]
    for gap in browser.get("gaps") or []:
        lines.append(f"- Gap: {gap}")
    return _md("Browser Verification", lines)


def _fix_loop_md(fix_loop: dict[str, Any]) -> str:
    lines = [f"Status: {fix_loop.get('status')}", f"Summary: {fix_loop.get('summary')}", f"OK: {bool(fix_loop.get('ok'))}"]
    for attempt in fix_loop.get("attempts") or []:
        if isinstance(attempt, dict):
            fix = attempt.get("fix") if isinstance(attempt.get("fix"), dict) else {}
            lines.append(f"- Attempt {attempt.get('attempt')}: {fix.get('summary') or fix.get('status')}")
    return _md("Fix Loop", lines)


def _proof_md(proof: dict[str, Any]) -> str:
    lines = [
        f"Product: {proof.get('product_name')}",
        f"Status: {proof.get('status')}",
        f"OK: {bool(proof.get('ok'))}",
        f"Frontend handoff: {bool(proof.get('frontend_handoff_allowed'))}",
        f"Applied to source: {bool(proof.get('applied_to_source'))}",
        f"Browser verified: {bool(proof.get('browser_verified'))}",
        f"Design visual status: {proof.get('design_visual_status') or 'unknown'}",
        f"Browser gate ready: {bool(proof.get('browser_gate_ready'))}",
        f"Technical ready: {bool(proof.get('technical_ready'))}",
        "",
        "Stages:",
    ]
    for stage in proof.get("stages") or []:
        if isinstance(stage, dict):
            lines.append(f"- {stage.get('id')}: {stage.get('status')} - {stage.get('summary')}")
    gaps = proof.get("gaps") if isinstance(proof.get("gaps"), list) else []
    if gaps:
        lines.extend(["", "Gaps:", *[f"- {gap}" for gap in gaps]])
    return _md("Final Design Proof", lines)


def _summary(status: str, generation: dict[str, Any], applied: dict[str, Any], browser: dict[str, Any], gaps: list[str]) -> str:
    if status == "planned":
        return "Design pipeline planned; no live provider or browser execution was run."
    if status == "verified":
        return "Selected design was applied and verified with browser/taste proof."
    if status == "applied":
        return "Selected design was applied to frontend source; browser verification was not requested."
    if status == "selected":
        return "A design handoff was selected; source application was not requested."
    if status == "needs_revision":
        return f"Design pipeline needs revision: {len(gaps)} gap(s) remain."
    return generation.get("summary") or applied.get("summary") or browser.get("summary") or "Design pipeline is blocked."


def _md(title: str, lines: list[Any]) -> str:
    return "# " + title + "\n\n" + "\n".join(str(item) for item in lines if str(item).strip()) + "\n"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n"


def _dedupe(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        text = _clean(value)
        if text and text not in seen:
            result.append(value)
            seen.add(text)
    return result


def _product_name_from_request(request: str) -> str:
    getter = getattr(design_providers, "_product_name_from_request", None)
    if callable(getter):
        try:
            return _clean(getter(request))
        except Exception:
            return ""
    return ""


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()

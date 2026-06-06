"""Stitch prompt bundle compiler for Friday design runs."""

from __future__ import annotations

import json
from typing import Any


def compile_stitch_prompt_bundle(brief: dict[str, Any], *, budget: int, fallback_prompt: str = "") -> dict[str, Any]:
    """Create phase-specific Stitch prompts without blind whole-prompt slicing."""

    context = brief.get("design_context") if isinstance(brief.get("design_context"), dict) else {}
    strategy = brief.get("design_strategy") if isinstance(brief.get("design_strategy"), dict) else {}
    contract = brief.get("design_contract") if isinstance(brief.get("design_contract"), dict) else {}
    product = _clean(brief.get("product_name") or "the product")
    request = _clean(brief.get("request") or fallback_prompt)
    prompt_budget = max(6000, int(budget or 12000))
    art_direction = _section(
        "ART DIRECTION",
        [
            f"Product: {product}",
            f"Request: {request}",
            f"Message: {_clean(strategy.get('message') or context.get('message'))}",
            f"Emotion: {_clean(strategy.get('emotional_feel') or context.get('emotional_intent'))}",
            f"Visual grammar: {_clean(strategy.get('visual_language') or _nested(context, 'visual_context', 'visual_language'))}",
            f"Composition archetype: {_clean(_nested(strategy, 'composition', 'archetype_name') or _nested(strategy, 'composition', 'archetype') or _nested(context, 'composition_spec', 'archetype_name'))}",
            f"Experience mode: {_compact(context.get('experience_mode') or {}, 700)}",
            f"Rejection rules: {_compact((strategy.get('anti_patterns') or [])[:10], 900)}",
        ],
    )
    page_contract = _section(
        "PAGE CONTRACT",
        [
            f"Objective: {_clean(contract.get('objective'))}",
            f"Required sections: {_compact(contract.get('required_sections') or _nested(context, 'content_model', 'required_sections') or [], 1100)}",
            f"Section blueprint: {_compact(context.get('section_blueprint') or [], 1800)}",
            f"Component inventory: {_compact(context.get('component_inventory') or [], 1200)}",
            f"Responsive behavior: desktop first viewport must be useful; mobile must not clip text or overflow.",
        ],
    )
    copy_assets = _section(
        "COPY AND ASSETS",
        [
            f"Copy voice: {_clean(strategy.get('copy_voice') or _nested(context, 'visual_context', 'copy_voice'))}",
            f"Copy bank: {_compact(context.get('copy_bank') or {}, 1600)}",
            f"Proof objects: {_compact(_nested(context, 'content_model', 'proof_objects') or [], 800)}",
            f"Asset direction: {_clean(_nested(context, 'brand_system', 'asset_direction') or _nested(context, 'visual_context', 'imagery'))}",
            "Images must be crisp, legible, and product/category relevant. Do not use blurry, washed-out, decorative-only media.",
        ],
    )
    output_contract = _section(
        "OUTPUT CONTRACT",
        [
            "Return a complete desktop screen/page, not a logo or isolated component.",
            "The first viewport must communicate product value without needing scroll.",
            "Include visible, category-specific copy and real controls.",
            "Do not use placeholder numbered labels, generic SaaS scaffold wording, or giant clipped hero type.",
            f"Minimum depth: {_clean(_nested(context, 'output_contract', 'minimum_depth') or 'hero plus at least two meaningful supporting sections before footer')}",
        ],
    )
    variant_prompt = _section(
        "VARIANT GENERATION",
        [
            "Create genuinely distinct alternatives for the same product.",
            "Change composition, hierarchy, content emphasis, visual rhythm, and interaction model.",
            f"Variant directions: {_compact(context.get('variant_briefs') or strategy.get('variant_directions') or [], 1600)}",
            "Preserve domain-specific copy and improve clarity, accessibility, and product proof.",
            "Do not repeat the base composition.",
        ],
    )
    revision_prompt = _section(
        "REVISION RULES",
        [
            "When critique fails, revise the design instead of defending it.",
            "Fix shallow content, blurry imagery, weak hierarchy, generic copy, empty sections, and mobile clipping.",
            "Return a stronger complete page that satisfies the page contract and output contract.",
        ],
    )
    base_prompt = _join_under_budget([art_direction, page_contract, copy_assets, output_contract], prompt_budget)
    return {
        "version": "stitch_prompt_bundle_v1",
        "budget": prompt_budget,
        "base_prompt": base_prompt or _clip(fallback_prompt, prompt_budget),
        "art_direction_prompt": _clip(art_direction, prompt_budget),
        "page_contract_prompt": _clip(page_contract, prompt_budget),
        "copy_assets_prompt": _clip(copy_assets, prompt_budget),
        "variant_prompt": _clip("\n\n".join([variant_prompt, output_contract]), prompt_budget),
        "revision_prompt": _clip("\n\n".join([revision_prompt, page_contract, output_contract]), prompt_budget),
        "output_contract_prompt": _clip(output_contract, prompt_budget),
        "full_prompt_length": len(str(fallback_prompt or "")),
        "sections": ["art_direction", "page_contract", "copy_assets", "variant", "revision", "output_contract"],
    }


def _section(title: str, lines: list[str]) -> str:
    return "\n".join([title, *[f"- {line}" for line in lines if _clean(line)]])


def _join_under_budget(sections: list[str], budget: int) -> str:
    output: list[str] = []
    for section in sections:
        candidate = "\n\n".join([*output, section])
        if len(candidate) <= budget:
            output.append(section)
            continue
        remaining = max(800, budget - len("\n\n".join(output)) - 80)
        if remaining > 200:
            output.append(_clip(section, remaining))
        break
    return "\n\n".join(output)


def _compact(value: Any, limit: int) -> str:
    try:
        text = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    except Exception:
        text = str(value)
    return _clip(text, limit)


def _nested(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _clip(value: str, limit: int) -> str:
    text = _clean(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 72)].rstrip() + "\n[Compacted by Friday prompt bundle compiler.]"


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").split())

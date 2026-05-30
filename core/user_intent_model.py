"""User-intent model facade for Friday judgment."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import context_interpreter


def infer(text: str, *, root: str | Path = "", context: dict[str, Any] | None = None) -> dict[str, Any]:
    interpreted = context_interpreter.interpret(text, root=root, context=context)
    intent = interpreted["intent"]
    action = {
        "answer_question": "respond_directly",
        "inspect_and_explain": "inspect_then_explain",
        "implement": "edit_or_build_with_verification",
        "test_friday_do_not_bypass": "route_through_friday_and_review_agent_output",
        "push_to_github": "git_publish_with_scope_confirmation",
        "production_system": "run_friday_os_product_studio",
        "fix_ui_wiring": "map_backend_frontend_parity_then_patch",
        "improve_friday_itself": "self_improvement_with_contracts",
    }.get(intent, "respond_directly")
    blocked = []
    if intent == "test_friday_do_not_bypass":
        blocked.append("Do not complete the requested build outside Friday.")
    if interpreted["risk_level"] == "high":
        blocked.extend(["deploy_production", "post_ads", "enable_billing", "send_outreach"])
    return {
        **interpreted,
        "recommended_action": action,
        "blocked_actions": blocked,
        "confidence": _confidence(interpreted),
        "summary": f"{interpreted['summary']} Recommended action: {action}.",
    }


def _confidence(interpreted: dict[str, Any]) -> float:
    if interpreted.get("intent") == "answer_question":
        return 0.62
    confidence = 0.78
    if interpreted.get("referenced_style"):
        confidence += 0.06
    if interpreted.get("do_not_bypass_friday"):
        confidence += 0.1
    return min(0.94, confidence)

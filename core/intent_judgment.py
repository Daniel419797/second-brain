"""Judgment wrapper for messy user intent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import user_intent_model


def judge(text: str, *, root: str | Path = "", context: dict[str, Any] | None = None) -> dict[str, Any]:
    inferred = user_intent_model.infer(text, root=root, context=context)
    return {
        "user_intent": inferred["intent"],
        "inferred_goal": inferred["recommended_action"],
        "risk_level": inferred["risk_level"],
        "project_style": inferred.get("referenced_style") or "",
        "recommended_action": inferred["recommended_action"],
        "evidence_needed": inferred["evidence_needed"],
        "blocked_claims": _blocked_claims(inferred),
        "blocked_actions": inferred.get("blocked_actions") or [],
        "do_not_bypass_friday": bool(inferred.get("do_not_bypass_friday")),
        "confidence": inferred["confidence"],
        "summary": inferred["summary"],
        "raw": inferred,
    }


def _blocked_claims(inferred: dict[str, Any]) -> list[str]:
    claims = ["market_ready", "production_ready", "deployed", "tested", "verified"]
    if inferred.get("risk_level") != "high":
        claims = [claim for claim in claims if claim not in {"deployed", "market_ready"}]
    if inferred.get("intent") == "answer_question":
        claims.append("implemented")
    return claims

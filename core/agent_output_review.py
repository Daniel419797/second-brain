"""Review autonomous agent outputs before accepting them as complete."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import evidence_judgment, readiness_claim_guard


def review(result: Any, *, root: str | Path = "", expected_claims: list[str] | None = None) -> dict[str, Any]:
    evidence = evidence_judgment.judge(result, root=root)
    claims = expected_claims or _claims_from_result(result)
    claim_review = readiness_claim_guard.guard_claims(claims, _evidence_context(result, evidence), root=root)
    accepted = evidence["ok"] and claim_review["ok"]
    return {
        "accepted": accepted,
        "evidence": evidence,
        "claim_review": claim_review,
        "gaps": [*(evidence.get("shallow_output", {}).get("reasons") or []), *(claim_review.get("blocked") or [])],
        "summary": "Agent output accepted." if accepted else "Agent output rejected until proof gaps are fixed.",
    }


def _claims_from_result(result: Any) -> list[str]:
    text = str(result if not isinstance(result, dict) else " ".join(str(result.get(key) or "") for key in ("summary", "voice_summary", "next_step")))
    claims = []
    lowered = text.lower()
    for claim in ("done", "tested", "verified", "production-ready", "market-ready", "deployed"):
        if claim in lowered:
            claims.append(claim)
    return claims


def _evidence_context(result: Any, evidence: dict[str, Any]) -> dict[str, Any]:
    payload = result if isinstance(result, dict) else {}
    gate_results = evidence.get("gate_results") if isinstance(evidence.get("gate_results"), dict) else {}
    return {
        "tested": evidence.get("evidence", {}).get("has_tests"),
        "browser_verified": evidence.get("evidence", {}).get("has_browser_proof"),
        "preview_url": gate_results.get("preview_url") or payload.get("preview_url") or "",
        "technical_ready": gate_results.get("technical_ready") or payload.get("technical_ready") or False,
        "market_ready": payload.get("market_ready") or False,
        "approvals": payload.get("approvals") if isinstance(payload.get("approvals"), dict) else {},
        "failed_required": gate_results.get("failed_required") or [],
        "final_proof": evidence.get("evidence", {}).get("has_final_proof"),
    }

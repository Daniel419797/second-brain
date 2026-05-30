"""Review final Friday answers for evidence-backed claims."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import honesty_gate, self_review_gate


def review(
    text: str,
    *,
    result: Any = None,
    root: str | Path = "",
    request: str = "",
    claims: list[str] | None = None,
) -> dict[str, Any]:
    self_review = self_review_gate.review(text=text, result=result, root=root, request=request, claims=claims)
    honesty = honesty_gate.review_text(text, _evidence_from_self_review(self_review, result), root=root)
    gaps = [*(self_review.get("gaps") or []), *(honesty.get("blocked") or [])]
    return {
        "ok": not gaps,
        "self_review": self_review,
        "honesty": honesty,
        "gaps": _dedupe(gaps),
        "safe_result": {
            "summary": _summary(text, gaps),
            "evidence": _evidence_lines(self_review),
            "verification": _verification_lines(self_review),
            "gaps": _dedupe(gaps),
            "confidence": self_review.get("confidence", 0.5) if not gaps else min(0.55, float(self_review.get("confidence", 0.5))),
        },
        "summary": "Final answer can be sent." if not gaps else f"Final answer needs correction: {len(_dedupe(gaps))} gap(s).",
    }


def _evidence_from_self_review(self_review: dict[str, Any], result: Any) -> dict[str, Any]:
    output = self_review.get("output_review") if isinstance(self_review.get("output_review"), dict) else {}
    evidence = output.get("evidence") if isinstance(output.get("evidence"), dict) else {}
    gate_results = evidence.get("gate_results") if isinstance(evidence.get("gate_results"), dict) else {}
    payload = result if isinstance(result, dict) else {}
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


def _summary(text: str, gaps: list[str]) -> str:
    if not gaps:
        return text
    return "Result cannot be marked complete until the listed evidence gaps are fixed."


def _evidence_lines(self_review: dict[str, Any]) -> list[str]:
    checks = self_review.get("checks") if isinstance(self_review.get("checks"), list) else []
    return [check.get("label") for check in checks if check.get("status") == "passed"]


def _verification_lines(self_review: dict[str, Any]) -> list[str]:
    output = self_review.get("output_review") if isinstance(self_review.get("output_review"), dict) else {}
    evidence = output.get("evidence") if isinstance(output.get("evidence"), dict) else {}
    gate_results = evidence.get("gate_results") if isinstance(evidence.get("gate_results"), dict) else {}
    gates = gate_results.get("gates") if isinstance(gate_results.get("gates"), list) else []
    return [str(gate.get("label") or gate.get("id")) for gate in gates if gate.get("status") == "passed"]


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result

"""Self-review gate before Friday marks work complete."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import agent_output_review, honesty_gate, intent_judgment


REVIEW_QUESTIONS = [
    "Did I inspect first?",
    "Did I modify the right files?",
    "Did I respect user intent?",
    "Did I run the right checks?",
    "Did I attach proof?",
    "Am I overclaiming?",
    "What gaps remain?",
]


def review(
    *,
    text: str = "",
    result: Any = None,
    root: str | Path = "",
    request: str = "",
    claims: list[str] | None = None,
) -> dict[str, Any]:
    intent = intent_judgment.judge(request or text, root=root)
    output = agent_output_review.review(result or {"summary": text}, root=root, expected_claims=claims)
    honesty = honesty_gate.review_text(text or str((result or {}).get("summary") if isinstance(result, dict) else result), _evidence_context(output, result), root=root)
    checks = [
        _check("inspect_first", "Did I inspect first?", bool(_inspection_present(result)), "No inspection evidence is attached."),
        _check("right_files", "Did I modify the right files?", bool(_files_present(result)), "No changed file/artifact evidence is attached."),
        _check("respect_intent", "Did I respect user intent?", not intent.get("do_not_bypass_friday") or _friday_run_present(result), "User appears to be testing Friday, but no Friday run evidence is attached."),
        _check("checks_run", "Did I run the right checks?", bool(_checks_present(result) or output.get("evidence", {}).get("ok")), "No gate/test/build evidence is attached."),
        _check("proof_attached", "Did I attach proof?", not output.get("evidence", {}).get("shallow_output", {}).get("shallow"), "Proof is incomplete or shallow."),
        _check("overclaiming", "Am I overclaiming?", honesty.get("ok"), "; ".join(honesty.get("blocked") or []) or "Unsupported claim."),
    ]
    gaps = [check["summary"] for check in checks if check["status"] == "failed"]
    return {
        "passed": not gaps,
        "questions": REVIEW_QUESTIONS,
        "intent": intent,
        "output_review": output,
        "honesty": honesty,
        "checks": checks,
        "gaps": gaps,
        "summary": "Self-review passed." if not gaps else f"Self-review blocked completion with {len(gaps)} gap(s).",
        "confidence": 0.84 if not gaps else 0.48,
    }


def _evidence_context(output: dict[str, Any], result: Any) -> dict[str, Any]:
    claim_review = output.get("claim_review") if isinstance(output.get("claim_review"), dict) else {}
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
        "claim_review": claim_review,
    }


def _check(check_id: str, label: str, passed: bool, failure: str) -> dict[str, str]:
    return {"id": check_id, "label": label, "status": "passed" if passed else "failed", "summary": label if passed else failure}


def _inspection_present(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    return bool(result.get("inspection") or result.get("intelligence") or metadata.get("intelligence") or metadata.get("preflight"))


def _files_present(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    return bool(result.get("changed") or result.get("changed_files") or result.get("artifacts"))


def _checks_present(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    return bool(result.get("gate_results") or result.get("tested") or metadata.get("product_studio_gates"))


def _friday_run_present(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    return bool(result.get("friday_run_id") or result.get("friday_os_run_id") or result.get("id") and "friday" in str(result).lower())

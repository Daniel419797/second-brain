"""Central judgment kernel for Friday's engineering operating system."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import (
    agent_output_review,
    evidence_judgment,
    failure_autopsy_engine,
    final_answer_reviewer,
    friday_memory,
    honesty_gate,
    intent_judgment,
    project_convention_engine,
    quality_judgment,
    self_review_gate,
    taste_memory,
)


JUDGMENT_LOOP = [
    "read_context",
    "infer_real_intent",
    "inspect_workspace",
    "identify_constraints",
    "choose_action_path",
    "execute",
    "verify",
    "self_review",
    "report_truthfully",
    "remember_lesson",
]


def infer_intent(text: str, *, root: str | Path = "", context: dict[str, Any] | None = None) -> dict[str, Any]:
    return intent_judgment.judge(text, root=root, context=context)


def review(
    *,
    text: str = "",
    result: Any = None,
    root: str | Path = "",
    claims: list[str] | None = None,
    remember: bool = False,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    intent = infer_intent(text or _result_text(result), root=root, context=context)
    evidence = evidence_judgment.judge(result or {"summary": text}, root=root)
    quality = quality_judgment.judge_output(result or {"summary": text}, root=root)
    output = agent_output_review.review(result or {"summary": text}, root=root, expected_claims=claims)
    honesty = honesty_gate.review_text(text or _result_text(result), _evidence_context(result, evidence), root=root, remember=remember)
    self_review = self_review_gate.review(text=text, result=result or {"summary": text}, root=root, request=text, claims=claims)
    gaps = _dedupe([
        *(evidence.get("shallow_output", {}).get("reasons") or []),
        *(quality.get("gaps") or []),
        *(output.get("gaps") or []),
        *(honesty.get("blocked") or []),
        *(self_review.get("gaps") or []),
    ])
    if remember and gaps:
        friday_memory.remember(
            "judgment_gap",
            "Judgment blocked unsupported completion",
            "; ".join(gaps[:8]),
            root=root,
            tags=["judgment", "gap"],
            confidence=0.76,
            metadata={"intent": intent, "claims": claims or []},
        )
    return {
        "ok": not gaps,
        "judgment": {
            "user_intent": intent.get("user_intent"),
            "inferred_goal": intent.get("inferred_goal"),
            "risk_level": intent.get("risk_level"),
            "project_style": intent.get("project_style"),
            "recommended_action": intent.get("recommended_action"),
            "evidence_needed": intent.get("evidence_needed"),
            "blocked_claims": intent.get("blocked_claims"),
            "confidence": intent.get("confidence"),
        },
        "intent": intent,
        "evidence": evidence,
        "quality": quality,
        "output_review": output,
        "honesty": honesty,
        "self_review": self_review,
        "gaps": gaps,
        "summary": "Judgment accepted the result." if not gaps else f"Judgment blocked completion with {len(gaps)} gap(s).",
    }


def review_evidence(result: Any, *, root: str | Path = "") -> dict[str, Any]:
    return evidence_judgment.judge(result, root=root)


def challenge_claims(
    *,
    text: str = "",
    result: Any = None,
    root: str | Path = "",
    claims: list[str] | None = None,
    remember: bool = False,
) -> dict[str, Any]:
    evidence = evidence_judgment.judge(result or {"summary": text}, root=root)
    extracted = claims or honesty_gate.extract_claims(text or _result_text(result))
    return honesty_gate.review_text(" ".join(extracted) if extracted else text, _evidence_context(result, evidence), root=root, remember=remember)


def debug_failure(failure: str | dict[str, Any], *, root: str | Path = "", remember: bool = True) -> dict[str, Any]:
    return failure_autopsy_engine.autopsy(failure, root=root, remember=remember)


def self_review(
    *,
    text: str = "",
    result: Any = None,
    root: str | Path = "",
    request: str = "",
    claims: list[str] | None = None,
) -> dict[str, Any]:
    return self_review_gate.review(text=text, result=result, root=root, request=request, claims=claims)


def final_answer(
    text: str,
    *,
    result: Any = None,
    root: str | Path = "",
    request: str = "",
    claims: list[str] | None = None,
) -> dict[str, Any]:
    return final_answer_reviewer.review(text, result=result, root=root, request=request, claims=claims)


def save_lesson(correction: str, *, domain: str = "coding", root: str | Path = "", evidence: list[str] | None = None) -> dict[str, Any]:
    return taste_memory.learn(correction, domain=domain, root=root, evidence=evidence)


def conventions(root: str | Path, request: str = "") -> dict[str, Any]:
    return project_convention_engine.inspect(root, request=request)


def status() -> dict[str, Any]:
    return {
        "loop": JUDGMENT_LOOP,
        "quality_priorities": quality_judgment.QUALITY_PRIORITIES,
        "taste": taste_memory.status(),
        "recent_memory": friday_memory.status(limit=6),
        "sample_judgment": {
            "user_intent": "",
            "inferred_goal": "",
            "risk_level": "medium",
            "project_style": "",
            "recommended_action": "",
            "evidence_needed": [],
            "blocked_claims": [],
            "confidence": 0.0,
        },
        "summary": "Judgment kernel ready: intent, evidence, quality, honesty, debug, self-review, and memory gates are active.",
    }


def _evidence_context(result: Any, evidence: dict[str, Any]) -> dict[str, Any]:
    payload = result if isinstance(result, dict) else {}
    gate_results = evidence.get("gate_results") if isinstance(evidence.get("gate_results"), dict) else {}
    evidence_flags = evidence.get("evidence") if isinstance(evidence.get("evidence"), dict) else {}
    return {
        "tested": evidence_flags.get("has_tests"),
        "browser_verified": evidence_flags.get("has_browser_proof"),
        "preview_url": gate_results.get("preview_url") or payload.get("preview_url") or "",
        "technical_ready": gate_results.get("technical_ready") or payload.get("technical_ready") or False,
        "market_ready": payload.get("market_ready") or False,
        "approvals": payload.get("approvals") if isinstance(payload.get("approvals"), dict) else {},
        "failed_required": gate_results.get("failed_required") or [],
        "final_proof": evidence_flags.get("has_final_proof"),
    }


def _result_text(result: Any) -> str:
    if isinstance(result, dict):
        return " ".join(str(result.get(key) or "") for key in ("summary", "voice_summary", "actual_output", "output", "next_step"))
    return str(result or "")


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result

"""Structured output contracts for Friday agent/tool results."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


class EvidenceItem(BaseModel):
    kind: str = Field(default="artifact", max_length=80)
    path: str = Field(default="", max_length=2000)
    url: str = Field(default="", max_length=2000)
    summary: str = Field(default="", max_length=2000)


class AgentResult(BaseModel):
    summary: str = Field(min_length=1, max_length=4000)
    next_step: str = Field(default="", max_length=2000)
    risks: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    status: Literal["planned", "done", "blocked", "failed", "technical_ready", "market_ready_blocked", "market_ready"] = "planned"


class DesignBriefOutput(BaseModel):
    product_name: str = Field(min_length=1, max_length=200)
    audience: str = Field(default="", max_length=2000)
    goal: str = Field(min_length=1, max_length=3000)
    emotional_feel: str = Field(default="", max_length=1000)
    visual_grammar: list[str] = Field(default_factory=list)
    sections: list[str] = Field(default_factory=list)
    rejection_rules: list[str] = Field(default_factory=list)
    output_contract: list[str] = Field(default_factory=list)


class GateReportOutput(BaseModel):
    gate_id: str = Field(min_length=1, max_length=120)
    status: Literal["passed", "failed", "blocked", "skipped", "warning"]
    required: bool = True
    summary: str = Field(default="", max_length=4000)
    artifacts: list[str] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class FixPlanOutput(BaseModel):
    failure: str = Field(min_length=1, max_length=4000)
    likely_causes: list[str] = Field(default_factory=list)
    next_probe: str = Field(default="", max_length=2000)
    files_to_touch: list[str] = Field(default_factory=list)
    verification: list[str] = Field(default_factory=list)
    risk: Literal["low", "medium", "high"] = "medium"


CONTRACTS = {
    "agent_result": AgentResult,
    "design_brief": DesignBriefOutput,
    "gate_report": GateReportOutput,
    "fix_plan": FixPlanOutput,
}


def validate(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    model = CONTRACTS.get(str(kind or "").strip().lower())
    if model is None:
        return {"ok": False, "kind": kind, "errors": [f"Unknown structured output contract: {kind}"], "payload": payload}
    try:
        item = model.model_validate(payload)
        return {"ok": True, "kind": kind, "output": item.model_dump()}
    except ValidationError as exc:
        return {"ok": False, "kind": kind, "errors": exc.errors(), "payload": payload}


def coerce_agent_result(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {"summary": str(payload or ""), "status": "done"}
    if not str(payload.get("summary") or "").strip():
        payload["summary"] = str(payload.get("error") or payload.get("status") or "Agent result recorded.")
    payload.setdefault("next_step", "")
    payload.setdefault("risks", [])
    payload.setdefault("evidence", _evidence_from_payload(payload))
    payload.setdefault("gaps", payload.get("failed_required") or [])
    payload.setdefault("confidence", 0.0)
    payload.setdefault("status", payload.get("task_status") or payload.get("status") or "done")
    result = validate("agent_result", payload)
    if result.get("ok"):
        return result["output"]
    return {
        "summary": str(payload.get("summary") or "Agent result recorded."),
        "next_step": str(payload.get("next_step") or ""),
        "risks": [str(item) for item in (payload.get("risks") or [])],
        "evidence": _evidence_from_payload(payload),
        "gaps": [str(item) for item in (payload.get("gaps") or payload.get("failed_required") or [])],
        "confidence": 0.0,
        "status": "failed" if payload.get("error") else "planned",
    }


def _evidence_from_payload(payload: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for key in ("artifacts", "changed"):
        for value in payload.get(key) or []:
            text = str(value or "").strip()
            if text:
                items.append({"kind": "artifact", "path": text, "url": "", "summary": ""})
    preview_url = str(payload.get("preview_url") or "").strip()
    if preview_url:
        items.append({"kind": "preview", "path": "", "url": preview_url, "summary": "Preview URL"})
    return items

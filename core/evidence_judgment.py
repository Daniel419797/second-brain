"""Evidence judgment for Friday task results."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import shallow_output_detector


def judge(result: Any, *, root: str | Path = "") -> dict[str, Any]:
    shallow = shallow_output_detector.detect(result, root=root)
    payload = result if isinstance(result, dict) else {"summary": str(result or "")}
    gate_results = _gate_results(payload)
    evidence = {
        "has_project_root": bool(shallow.get("root")),
        "has_tests": _has_test_evidence(payload),
        "has_gates": bool(gate_results.get("attempted") or gate_results.get("gates")),
        "has_final_proof": not any("final proof" in reason.lower() for reason in shallow.get("reasons") or []),
        "has_browser_proof": not any("browser" in reason.lower() for reason in shallow.get("reasons") or []),
    }
    score = sum(1 for ok in evidence.values() if ok) / max(1, len(evidence))
    return {
        "ok": not shallow["shallow"],
        "score": round(score, 2),
        "evidence": evidence,
        "shallow_output": shallow,
        "gate_results": gate_results,
        "summary": "Evidence is sufficient." if not shallow["shallow"] else f"Evidence is insufficient: {len(shallow['reasons'])} gap(s).",
    }


def _gate_results(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    if isinstance(metadata.get("product_studio_gates"), dict):
        return metadata["product_studio_gates"]
    if isinstance(payload.get("gate_results"), dict):
        return payload["gate_results"]
    execution = payload.get("execution") if isinstance(payload.get("execution"), dict) else {}
    execution_metadata = execution.get("metadata") if isinstance(execution.get("metadata"), dict) else {}
    if isinstance(execution_metadata.get("product_studio_gates"), dict):
        return execution_metadata["product_studio_gates"]
    return {}


def _has_test_evidence(payload: dict[str, Any]) -> bool:
    tested = payload.get("tested")
    if isinstance(payload.get("execution"), dict):
        tested = payload["execution"].get("tested") or tested
    return isinstance(tested, list) and bool(tested)

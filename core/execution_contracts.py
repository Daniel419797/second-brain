"""Evidence contracts for Friday OS runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import engineering_discipline

REQUIRED_PROOF_FILES = [
    "requirements.json",
    "architecture.json",
    "implementation-plan.json",
    "changed-files.json",
    "gate-results.json",
    "artifact-manifest.json",
    "security-report.md",
    "performance-report.md",
    "browser-report.md",
    "launch-pack.md",
    "final-proof-report.md",
]


def validate_run_evidence(run: dict[str, Any]) -> dict[str, Any]:
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    intelligence = run.get("intelligence") if isinstance(run.get("intelligence"), dict) else metadata.get("intelligence")
    architecture = run.get("architecture") if isinstance(run.get("architecture"), dict) else metadata.get("architecture")
    production_run = run.get("production_run") if isinstance(run.get("production_run"), dict) else metadata.get("production_run")
    gate_results = run.get("gate_results") if isinstance(run.get("gate_results"), dict) else (production_run or {}).get("gate_results")
    artifacts = run.get("artifacts") if isinstance(run.get("artifacts"), list) else (production_run or {}).get("artifacts") or []
    final_proof = run.get("final_proof_report") or _find_proof_artifact(artifacts)
    evidence = engineering_discipline.evaluate_evidence(
        {
            "inspection": intelligence,
            "architecture": architecture,
            "artifacts": artifacts,
            "gate_results": gate_results,
            "final_proof_report": final_proof,
        }
    )
    proof_root = _proof_root(run, production_run)
    missing_files = [name for name in REQUIRED_PROOF_FILES if proof_root and not (proof_root / name).exists()]
    gaps = [*evidence["gaps"], *[f"Missing proof artifact: {name}" for name in missing_files]]
    technical_ready = bool((production_run or {}).get("technical_ready"))
    market_ready = bool((production_run or {}).get("market_ready"))
    if technical_ready and gaps:
        gaps.append("Technical readiness cannot be trusted until Friday OS proof artifacts are complete.")
        technical_ready = False
    if market_ready and not technical_ready:
        gaps.append("Market readiness cannot be true when technical readiness is false.")
        market_ready = False
    return {
        "ok": not gaps,
        "technical_ready": technical_ready,
        "market_ready": market_ready,
        "gaps": _dedupe(gaps),
        "required_proof_files": REQUIRED_PROOF_FILES,
        "proof_root": str(proof_root) if proof_root else "",
        "summary": "Friday OS evidence contract satisfied." if not gaps else f"Friday OS evidence contract has {len(_dedupe(gaps))} gap(s).",
    }


def _proof_root(run: dict[str, Any], production_run: dict[str, Any] | None = None) -> Path | None:
    root = run.get("proof_root") or ((run.get("metadata") if isinstance(run.get("metadata"), dict) else {}) or {}).get("proof_root")
    if root:
        return Path(root)
    production_root = (production_run or {}).get("root") or run.get("root")
    if production_root:
        return Path(production_root) / ".friday" / "os"
    return None


def _find_proof_artifact(artifacts: list[Any]) -> str:
    for item in artifacts:
        if str(item).endswith("final-proof-report.md"):
            return str(item)
    return ""


def _dedupe(items: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result

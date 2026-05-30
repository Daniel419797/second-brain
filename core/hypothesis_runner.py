"""Failure hypothesis planning for Friday's fix loop."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import debugging_judgment


def propose(failure: str | dict[str, Any], *, root: str | Path = "") -> dict[str, Any]:
    judgment = debugging_judgment.judge_failure(failure, root=root)
    return {
        **judgment,
        "fix_plan": _fix_plan(judgment),
        "rerun_gate": _rerun_gate(judgment),
    }


def next_probe(failure: str | dict[str, Any], *, root: str | Path = "") -> dict[str, Any]:
    proposed = propose(failure, root=root)
    return {
        "next_probe": proposed.get("next_probe"),
        "fix_scope": proposed.get("fix_scope") or [],
        "rerun_gate": proposed.get("rerun_gate"),
        "summary": proposed.get("summary"),
    }


def _fix_plan(judgment: dict[str, Any]) -> list[str]:
    causes = " ".join(judgment.get("likely_causes") or []).lower()
    if "missing dependency" in causes:
        return ["Inspect the first missing import.", "Add or correct the dependency/import.", "Rerun install/typecheck."]
    if "client hook" in causes:
        return ["Inspect the component boundary.", "Move hook usage into a client component.", "Rerun typecheck/build."]
    if "type mismatch" in causes:
        return ["Open the first TypeScript diagnostic.", "Fix the narrowest contract/type mismatch.", "Rerun typecheck."]
    if "dependency advisory" in causes:
        return ["Inspect audit details.", "Upgrade the narrow vulnerable package.", "Rerun audit and tests."]
    return ["Capture the full failure log.", "Reproduce with the smallest command.", "Patch the narrowest cause and rerun the failed gate."]


def _rerun_gate(judgment: dict[str, Any]) -> str:
    probes = " ".join(judgment.get("probes") or []).lower()
    if "tsc" in probes or "typecheck" in probes:
        return "typecheck"
    if "eslint" in probes:
        return "lint"
    if "audit" in probes:
        return "dependency_audit"
    if "health" in probes or "server" in probes:
        return "smoke_test"
    return "failed_gate"

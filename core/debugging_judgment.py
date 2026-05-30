"""Failure-to-hypothesis judgment for Friday debugging."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def judge_failure(failure: str | dict[str, Any], *, root: str | Path = "") -> dict[str, Any]:
    text = _failure_text(failure)
    lowered = text.lower()
    causes: list[str] = []
    probes: list[str] = []
    scope: list[str] = []

    if "module not found" in lowered or "cannot find module" in lowered or "can't resolve" in lowered:
        causes.extend(["missing dependency", "bad import alias", "file moved without updating imports"])
        probes.extend(["run typecheck", "inspect first missing import stack trace"])
        scope.extend(_paths(text))
    if "use client" in lowered or "hook" in lowered and "server" in lowered:
        causes.extend(["client hook inside server component", "missing use client directive"])
        probes.extend(["inspect component boundary", "move hook into client component"])
    if "typescript" in lowered or "tsc" in lowered or "type error" in lowered:
        causes.extend(["type mismatch", "incorrect DTO contract", "stale generated type"])
        probes.extend(["run tsc --noEmit", "open first TypeScript diagnostic"])
    if "eslint" in lowered or "lint" in lowered:
        causes.extend(["lint rule violation", "unused import", "accessibility issue"])
        probes.extend(["run eslint on changed files"])
    if "timeout" in lowered or "connection refused" in lowered or "econnrefused" in lowered:
        causes.extend(["dev server not ready", "wrong port", "service dependency unavailable"])
        probes.extend(["check server logs", "probe health endpoint"])
    if "npm audit" in lowered or "vulnerab" in lowered:
        causes.extend(["dependency advisory", "transitive package risk"])
        probes.extend(["inspect npm audit json", "upgrade narrow vulnerable package"])

    if not causes:
        causes = ["unknown failure mode", "insufficient logs"]
        probes = ["capture full command output", "reproduce with the smallest command"]
    scope = scope or _default_scope(root)
    return {
        "failure": text[:4000],
        "likely_causes": _dedupe(causes),
        "next_probe": probes[0],
        "probes": _dedupe(probes),
        "fix_scope": _dedupe(scope),
        "summary": f"{len(_dedupe(causes))} likely cause(s); next probe: {probes[0]}.",
    }


def _failure_text(value: str | dict[str, Any]) -> str:
    if isinstance(value, dict):
        fields = [value.get("summary"), value.get("stderr"), value.get("stdout"), value.get("error"), value.get("failure")]
        return "\n".join(str(field or "") for field in fields)
    return str(value or "")


def _paths(text: str) -> list[str]:
    return re.findall(r"[\w./\\()-]+\.(?:ts|tsx|js|jsx|py|go|rs|dart)", text)


def _default_scope(root: str | Path) -> list[str]:
    base = Path(root) if root else Path(".")
    candidates = ["src", "tests", "package.json", "pyproject.toml"]
    return [str(base / item) for item in candidates if (base / item).exists()] or [str(base)]


def _dedupe(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result

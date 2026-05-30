"""Project convention inspection and style-profile matching."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import project_intelligence, style_profiles


def inspect(root: str | Path, request: str = "") -> dict[str, Any]:
    intelligence = project_intelligence.inspect_project(root, request)
    profile = intelligence.get("style_profile") if isinstance(intelligence.get("style_profile"), dict) else {}
    evaluation = intelligence.get("style_evaluation") if isinstance(intelligence.get("style_evaluation"), dict) else {}
    return {
        "root": str(Path(root).expanduser().resolve()),
        "intelligence": intelligence,
        "profile": profile,
        "evaluation": evaluation,
        "ok": bool(evaluation.get("ok")) if evaluation else True,
        "gaps": evaluation.get("gaps") or [],
        "summary": evaluation.get("summary") or intelligence.get("summary") or "Project conventions inspected.",
    }


def apply(root: str | Path, profile_id: str = "nexus_forge_nextjs") -> dict[str, Any]:
    return style_profiles.apply_profile(root, profile_id)


def match(root: str | Path, profile_id: str = "nexus_forge_nextjs") -> dict[str, Any]:
    return style_profiles.evaluate_project(root, profile_id)


def status(root: str | Path = "") -> dict[str, Any]:
    payload = style_profiles.status(root=root)
    payload["summary"] = payload.get("summary") or "Project convention engine ready."
    return payload

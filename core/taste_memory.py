"""Taste and style memory bridge for Friday's judgment loop."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import friday_memory, personal_taste_engine, style_profiles


def learn(correction: str, *, domain: str = "coding", root: str | Path = "", evidence: list[str] | None = None) -> dict[str, Any]:
    taste = personal_taste_engine.learn_from_correction(correction, domain=domain, evidence=evidence or ["judgment_center"])
    memory = friday_memory.remember(
        "user_preference",
        f"{taste.get('domain', domain)} taste",
        taste.get("rule") or correction,
        root=root,
        tags=["taste", taste.get("domain", domain), "judgment"],
        confidence=float(taste.get("confidence") or 0.75),
        metadata={"taste_rule_id": taste.get("id"), "evidence": evidence or []},
    )
    return {"taste": taste, "memory": memory, "summary": taste.get("summary") or "Taste memory saved."}


def learn_style_profile(profile: dict[str, Any], *, root: str | Path = "") -> dict[str, Any]:
    saved = style_profiles.save_profile(profile)
    memory = friday_memory.remember(
        "style_profile",
        saved.get("name") or saved.get("id") or "Style profile",
        saved.get("description") or "Style profile saved from judgment loop.",
        root=root,
        tags=["style", "project_convention"],
        confidence=0.88,
        metadata={"profile_id": saved.get("id"), "framework": saved.get("framework")},
    )
    return {"profile": saved, "memory": memory, "summary": f"Style profile saved: {saved.get('id')}."}


def guidance(domain: str = "coding", *, context: str = "") -> dict[str, Any]:
    return personal_taste_engine.guidance(domain=domain, context=context)


def status() -> dict[str, Any]:
    taste = personal_taste_engine.status()
    profiles = style_profiles.status()
    return {
        "taste": taste,
        "style_profiles": profiles.get("profiles") or [],
        "summary": f"{sum((taste.get('counts') or {}).values())} taste rule(s), {len(profiles.get('profiles') or [])} style profile(s).",
    }

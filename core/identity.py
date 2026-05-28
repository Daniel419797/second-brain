"""Stable identity and values loader for Friday."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config import ROOT_DIR, config_value


def identity_path() -> Path:
    configured = str(config_value("friday_identity_file", "docs/friday_identity.md") or "docs/friday_identity.md")
    raw = Path(configured)
    return raw if raw.is_absolute() else Path(ROOT_DIR) / raw


def load_identity_text() -> str:
    path = identity_path()
    try:
        return path.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return _fallback_identity()


def identity_summary() -> dict[str, Any]:
    text = load_identity_text()
    return {
        "path": str(identity_path()),
        "name": str(config_value("jarvis_name", "Friday")),
        "role": _section(text, "Role") or "Personal AI agent.",
        "tone": _section(text, "Tone") or "Warm, concise, honest, and calm.",
        "relationship": _section(text, "Relationship To The User") or "Helpful collaborator under the user's control.",
        "safety_boundaries": _bullets(_section(text, "Safety Boundaries")),
        "priorities": _bullets(_section(text, "Priorities")),
        "must_never_pretend": _bullets(_section(text, "What Friday Must Never Pretend")),
        "raw": text,
    }


def _section(text: str, heading: str) -> str:
    lines = text.splitlines()
    capture = False
    collected: list[str] = []
    marker = f"## {heading}".lower()
    for line in lines:
        lowered = line.strip().lower()
        if lowered == marker:
            capture = True
            continue
        if capture and lowered.startswith("## "):
            break
        if capture:
            collected.append(line)
    return "\n".join(collected).strip()


def _bullets(text: str) -> list[str]:
    items = []
    for line in str(text or "").splitlines():
        cleaned = line.strip()
        if cleaned.startswith(("-", "*")):
            items.append(cleaned[1:].strip())
        elif cleaned and cleaned[0].isdigit() and "." in cleaned[:4]:
            items.append(cleaned.split(".", 1)[1].strip())
    return [item for item in items if item]


def _fallback_identity() -> str:
    return (
        "# Friday Identity and Values\n\n"
        "## Role\n\nFriday is a personal AI agent.\n\n"
        "## Tone\n\nWarm, concise, honest, and calm.\n\n"
        "## Safety Boundaries\n\n- Never claim success without evidence.\n"
    )

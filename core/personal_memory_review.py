"""Personal memory review coordinator."""

from __future__ import annotations

from typing import Any

from core import executive_capabilities, personal_command_memory, personal_knowledge_vault


def generate(limit: int = 12) -> dict[str, Any]:
    reviews = executive_capabilities.generate_memory_reviews(limit=limit)
    commands = personal_command_memory.summary(limit=8)
    vault = personal_knowledge_vault.summary()
    return {
        "reviews": reviews,
        "command_memory": commands,
        "vault": vault,
        "summary": reviews.get("summary", "Memory review ready."),
    }


def status() -> dict[str, Any]:
    pending = executive_capabilities.list_memory_reviews(status="pending", limit=20)
    return {"pending": pending, "count": len(pending), "summary": f"{len(pending)} memory belief(s) waiting for review."}


def resolve(review_id: int, decision: str, note: str = "") -> dict[str, Any]:
    return executive_capabilities.resolve_memory_review(review_id, decision, note)

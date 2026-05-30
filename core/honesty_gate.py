"""Honesty gate that prevents unsupported Friday success language."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core import friday_memory, readiness_claim_guard


CLAIM_PATTERNS = {
    "done": r"\b(done|complete|completed|finished)\b",
    "tested": r"\b(tested|tests passed|test passed)\b",
    "verified": r"\b(verified|frontend verified|browser verified)\b",
    "production-ready": r"\b(production[- ]ready|technical ready)\b",
    "market-ready": r"\b(market[- ]ready)\b",
    "deployed": r"\b(deployed|preview deployed|live)\b",
}


def review_text(text: str, evidence: dict[str, Any], *, root: str | Path = "", remember: bool = False) -> dict[str, Any]:
    claims = extract_claims(text)
    result = readiness_claim_guard.guard_claims(claims, evidence, root=root)
    if remember and result.get("blocked"):
        friday_memory.remember(
            "blocked_claim",
            "Unsupported claim blocked",
            "; ".join(result["blocked"]),
            root=root,
            tags=["honesty", "claim_guard"],
            metadata={"claims": claims},
        )
    return {**result, "claims": claims}


def extract_claims(text: str) -> list[str]:
    lowered = str(text or "").lower()
    claims = []
    for claim, pattern in CLAIM_PATTERNS.items():
        if re.search(pattern, lowered):
            claims.append(claim)
    return claims

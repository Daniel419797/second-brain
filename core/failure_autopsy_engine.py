"""Failure autopsy engine that turns errors into reusable lessons."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import failure_autopsy, friday_memory, hypothesis_runner


def autopsy(
    failure: str | dict[str, Any],
    *,
    root: str | Path = "",
    source: str = "judgment_kernel",
    remember: bool = True,
) -> dict[str, Any]:
    hypothesis = hypothesis_runner.propose(failure, root=root)
    title = "Friday judgment failure"
    item = failure_autopsy.create(
        title,
        hypothesis.get("failure") or str(failure or ""),
        root_cause=", ".join(hypothesis.get("likely_causes") or []) or "Unknown root cause; needs inspection.",
        next_time=hypothesis.get("next_probe") or "Capture more evidence before retrying.",
        evidence=hypothesis.get("probes") or [],
        code_change_needed=True,
        source=source,
        metadata={"hypothesis": hypothesis, "root": str(root or "")},
    )
    memory = None
    if remember:
        memory = friday_memory.remember(
            "failure_pattern",
            item.get("root_cause") or title,
            item.get("next_time") or hypothesis.get("next_probe") or "",
            root=root,
            tags=["failure", "debugging", source],
            confidence=0.72,
            metadata={"autopsy_id": item.get("id"), "hypothesis": hypothesis},
        )
    return {
        "hypothesis": hypothesis,
        "autopsy": item,
        "memory": memory,
        "summary": item.get("summary") or "Failure autopsy recorded.",
    }

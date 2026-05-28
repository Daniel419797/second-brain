"""Evidence checks that stop Friday from claiming success without support."""

from __future__ import annotations

import re
from typing import Any

from core.config import config_value

ACTION_TERMS = (
    "open",
    "close",
    "launch",
    "start",
    "set",
    "change",
    "increase",
    "reduce",
    "decrease",
    "mute",
    "unmute",
    "send",
    "delete",
    "remove",
    "run",
    "click",
    "type",
    "apply",
    "fix",
    "update",
    "create",
)

SUCCESS_TERMS = (
    "done",
    "completed",
    "success",
    "successful",
    "opened",
    "closed",
    "set",
    "changed",
    "sent",
    "deleted",
    "removed",
    "applied",
    "fixed",
    "muted",
    "unmuted",
)

UNVERIFIED_TERMS = (
    "could not verify",
    "couldn't verify",
    "sent volume",
    "sent the mute key",
    "sent volume key",
    "not verified",
    "unverified",
)

FAILURE_TERMS = (
    "could not",
    "couldn't",
    "cannot",
    "can't",
    "failed",
    "blocked",
    "cancelled",
    "canceled",
    "not found",
    "unknown action",
    "permission required",
    "permission blocked",
    "unavailable",
    "access denied",
)


def action_needs_evidence(user_text: str) -> bool:
    lowered = _clean(user_text).lower()
    return any(re.search(rf"\b{re.escape(term)}\b", lowered) for term in ACTION_TERMS)


def claims_success(reply_text: str) -> bool:
    lowered = _clean(reply_text).lower()
    if not lowered:
        return True
    return any(re.search(rf"\b{re.escape(term)}\b", lowered) for term in SUCCESS_TERMS)


def evidence_supports_success(evidence: Any) -> bool:
    text = _clean(evidence).lower()
    if not text:
        return False
    if any(term in text for term in FAILURE_TERMS):
        return False
    if any(term in text for term in UNVERIFIED_TERMS):
        return False
    return claims_success(text) or "ok" in text or "verified=" in text


def guard_reply(user_text: str, reply_text: str, *, evidence: Any = None) -> str:
    if not bool(config_value("evidence_gate_enabled", True)):
        return str(reply_text or "")
    reply = str(reply_text or "").strip()
    if is_unverified_result(reply):
        return reply
    if not action_needs_evidence(user_text):
        return reply
    if not claims_success(reply):
        return reply
    if evidence_supports_success(evidence):
        return reply
    try:
        from core import evaluation_lab

        evaluation_lab.record_event(
            "unsupported_claim",
            f"Blocked unsupported success claim: {reply[:220]}",
            source="evidence_gate",
            severity=4,
            metadata={"user_text": user_text, "reply": reply, "evidence": str(evidence)[:500]},
        )
    except Exception:
        pass
    return "I do not have verified evidence that action succeeded, so I will not claim it is done."


def tool_result_success(result: Any) -> bool:
    text = _clean(result)
    if not text:
        return False
    return not any(term in text.lower() for term in FAILURE_TERMS)


def is_unverified_result(result: Any) -> bool:
    text = _clean(result).lower()
    return any(term in text for term in UNVERIFIED_TERMS)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())

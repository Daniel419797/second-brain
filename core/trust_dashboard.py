"""Single trust view for evidence, guesses, failures, approvals, and current work."""

from __future__ import annotations

from typing import Any

from core import approval_inbox, autonomy_engine, certainty_brain, evaluation_lab, notification_center, permissions, self_testing_personality, trust_proof


def status() -> dict[str, Any]:
    proof = _safe(trust_proof.summary, {})
    certainty = _safe(certainty_brain.summary, {})
    evaluation = _safe(lambda: evaluation_lab.summary(limit=8), {})
    approvals = _safe(lambda: approval_inbox.summary(limit=8), {})
    notifications = _safe(lambda: notification_center.summary(limit=8), {})
    autonomy = _safe(autonomy_engine.status, {})
    self_test = _safe(self_testing_personality.status, {})
    permission_events = _safe(lambda: permissions.recent_events(limit=8), [])
    failures = _failures(evaluation, self_test, notifications)
    verified = _verified(proof, certainty)
    unknowns = _unknowns(certainty, approvals)
    doing_now = _doing_now(autonomy, approvals)
    return {
        "verified": verified,
        "guessed_or_unknown": unknowns,
        "failed_recently": failures,
        "needs_approval": approvals,
        "doing_now": doing_now,
        "proof": proof,
        "certainty": certainty,
        "evaluation": evaluation,
        "notifications": notifications,
        "self_test": self_test,
        "permission_events": permission_events,
        "summary": _summary(verified, unknowns, failures, approvals, doing_now),
    }


def summary_text() -> str:
    return status()["summary"]


def _verified(proof: dict[str, Any], certainty: dict[str, Any]) -> list[str]:
    items: list[str] = []
    recent = proof.get("recent") or proof.get("reports") or []
    for report in recent[:5]:
        items.append(str(report.get("summary") or report.get("title") or report))
    for item in certainty.get("known") or []:
        items.append(str(item.get("statement") or item))
    return [item for item in items if item][:8]


def _unknowns(certainty: dict[str, Any], approvals: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for key in ("guesses", "missing", "stale", "needs_confirmation"):
        for item in certainty.get(key) or []:
            items.append(str(item.get("statement") or item))
    for item in approvals.get("items") or []:
        items.append(f"Approval needed: {item.get('title') or item.get('summary')}")
    return [item for item in items if item][:10]


def _failures(evaluation: dict[str, Any], self_test: dict[str, Any], notifications: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for item in evaluation.get("recent") or evaluation.get("events") or []:
        text = str(item.get("summary") or item.get("message") or item)
        if any(term in text.lower() for term in ("fail", "error", "slow", "unsupported", "lie", "claim")):
            items.append(text)
    for item in self_test.get("recent") or []:
        items.append(str(item.get("summary") or item))
    for item in notifications.get("items") or []:
        if int(item.get("severity") or 0) >= 4:
            items.append(str(item.get("message") or item.get("title") or item))
    return [item for item in items if item][:10]


def _doing_now(autonomy: dict[str, Any], approvals: dict[str, Any]) -> dict[str, Any]:
    return {
        "autonomy": autonomy,
        "approval_count": approvals.get("count", 0),
        "summary": autonomy.get("summary") or "No autonomous run is reporting active work.",
    }


def _summary(verified: list[str], unknowns: list[str], failures: list[str], approvals: dict[str, Any], doing_now: dict[str, Any]) -> str:
    approval_count = int(approvals.get("count") or 0)
    return (
        f"Trust dashboard: {len(verified)} verified item(s), {len(unknowns)} uncertain item(s), "
        f"{len(failures)} recent failure signal(s), {approval_count} approval(s). {doing_now.get('summary')}"
    )


def _safe(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default

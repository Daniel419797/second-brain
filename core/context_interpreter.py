"""Context interpretation for Friday's judgment loop."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core import project_scaffolds


def interpret(text: str, *, root: str | Path = "", context: dict[str, Any] | None = None) -> dict[str, Any]:
    cleaned = _clean(text)
    lowered = cleaned.lower()
    stack = project_scaffolds.detect_stack(cleaned)
    intent = _intent(lowered)
    referenced_style = _referenced_style(lowered)
    evidence_needed = _evidence_needed(intent, stack, lowered)
    constraints = _constraints(lowered, referenced_style)
    return {
        "raw_text": cleaned,
        "root": str(root or ""),
        "intent": intent,
        "stack": stack,
        "referenced_style": referenced_style,
        "constraints": constraints,
        "evidence_needed": evidence_needed,
        "risk_level": _risk(lowered, intent),
        "do_not_bypass_friday": intent == "test_friday_do_not_bypass",
        "summary": _summary(intent, stack, referenced_style),
        "context": context or {},
    }


def _intent(text: str) -> str:
    if _has_any(text, ("test friday", "testing friday", "using it to test friday", "i gave friday", "gave friday", "why did you do the job i gave friday")):
        return "test_friday_do_not_bypass"
    if _has_any(text, ("push to github", "commit and push", "open a pr", "create pr")):
        return "push_to_github"
    if _has_any(text, ("production ready", "market ready", "full product studio", "production system")):
        return "production_system"
    if _has_any(text, ("buttons don't", "buttons dont", "not wired", "frontend", "ui wiring", "endpoint")):
        return "fix_ui_wiring"
    if _has_any(text, ("friday itself", "make friday", "improve friday", "friday should", "friday must")):
        return "improve_friday_itself"
    if _has_any(text, ("inspect", "look at", "check", "explain", "why")) and not _has_any(text, ("implement", "fix", "build", "create")):
        return "inspect_and_explain"
    if _has_any(text, ("implement", "proceed", "fix", "build", "create", "add", "wire")):
        return "implement"
    return "answer_question"


def _referenced_style(text: str) -> str:
    if _has_any(text, ("nexus-forge", "nexus forge", "my_project", "my project", "typical next")):
        return "nexus_forge_nextjs"
    return ""


def _constraints(text: str, referenced_style: str) -> list[str]:
    constraints = []
    if "do not" in text or "don't" in text or "dont" in text:
        constraints.append("Honor explicit negative instructions before acting.")
    if referenced_style:
        constraints.append(f"Inspect and apply style profile: {referenced_style}.")
    if _has_any(text, ("without approval", "approval", "ads", "billing", "deploy production", "customer data")):
        constraints.append("Approval-gate deploys, ads, billing, outreach, and customer data access.")
    return constraints


def _evidence_needed(intent: str, stack: dict[str, Any], text: str) -> list[str]:
    evidence = ["project inspection", "changed files or proof artifacts", "final proof with gaps"]
    if intent in {"implement", "production_system", "fix_ui_wiring", "improve_friday_itself"}:
        evidence.extend(["tests or explicit test limitation", "gate results"])
    if stack.get("stack") == "nextjs" or _has_any(text, ("frontend", "web-app", "web app", "browser", "ui")):
        evidence.extend(["typecheck/build", "browser screenshot or browser check", "dead-button check"])
    if intent == "production_system":
        evidence.extend(["security scan", "performance check", "preview proof", "approval status"])
    if intent == "push_to_github":
        evidence.extend(["git status", "commit hash", "push result"])
    if intent == "test_friday_do_not_bypass":
        evidence.extend(["Friday task/run id", "agent output review", "do-not-bypass confirmation"])
    return _dedupe(evidence)


def _risk(text: str, intent: str) -> str:
    if intent in {"push_to_github", "production_system"} or _has_any(text, ("production deploy", "post ads", "billing", "customer data", "delete", "paid")):
        return "high"
    if intent in {"implement", "fix_ui_wiring", "improve_friday_itself"}:
        return "medium"
    return "low"


def _summary(intent: str, stack: dict[str, Any], referenced_style: str) -> str:
    style = f" with {referenced_style} style" if referenced_style else ""
    return f"Intent: {intent}; stack: {stack.get('label') or stack.get('stack') or 'unknown'}{style}."


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _dedupe(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()

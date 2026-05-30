"""Guard readiness and completion claims against missing evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any


MARKET_APPROVALS = {"deploy_preview", "deploy_production", "post_ads", "enable_billing", "send_outreach"}


def guard_claims(claims: list[str] | str, evidence: dict[str, Any], *, root: str | Path = "") -> dict[str, Any]:
    claim_list = _claims(claims)
    blocked: list[str] = []
    allowed: list[str] = []
    for claim in claim_list:
        reason = _blocked_reason(claim, evidence, root)
        if reason:
            blocked.append(reason)
        else:
            allowed.append(claim)
    return {
        "ok": not blocked,
        "allowed": allowed,
        "blocked": blocked,
        "summary": "Claims are supported by evidence." if not blocked else f"{len(blocked)} claim(s) blocked by evidence guard.",
    }


def _blocked_reason(claim: str, evidence: dict[str, Any], root: str | Path) -> str:
    normalized = claim.lower().replace("_", "-").strip()
    if normalized in {"tested", "test-passed"} and not evidence.get("tested"):
        return "Claim blocked: tested requires test/build command evidence."
    if normalized in {"verified", "frontend-verified"} and not evidence.get("browser_verified") and _looks_frontend(root):
        return "Claim blocked: frontend verification requires browser screenshot or browser gate evidence."
    if normalized in {"preview-deployed", "deployed"} and not evidence.get("preview_url"):
        return "Claim blocked: deployed/preview claim requires a preview URL or deploy proof."
    if normalized in {"technical-ready", "production-ready"}:
        if evidence.get("failed_required"):
            return "Claim blocked: technical readiness requires all required gates to pass."
        if not evidence.get("technical_ready"):
            return "Claim blocked: technical readiness requires technical_ready=true from gate results."
    if normalized == "market-ready":
        approvals = evidence.get("approvals") if isinstance(evidence.get("approvals"), dict) else {}
        missing = [action for action in sorted(MARKET_APPROVALS) if not approvals.get(action, {}).get("approved")]
        if missing:
            return f"Claim blocked: market readiness requires approvals: {', '.join(missing)}."
        if not evidence.get("market_ready"):
            return "Claim blocked: market_ready=true is not present in readiness evidence."
    if normalized in {"done", "complete"} and not evidence.get("final_proof"):
        return "Claim blocked: done/complete requires final proof."
    return ""


def _claims(values: list[str] | str) -> list[str]:
    if isinstance(values, str):
        values = [values]
    return [str(value or "").strip() for value in values or [] if str(value or "").strip()]


def _looks_frontend(root: str | Path) -> bool:
    if not root:
        return False
    base = Path(root)
    return (base / "next.config.mjs").exists() or (base / "src/app").exists() or (base / "package.json").exists()

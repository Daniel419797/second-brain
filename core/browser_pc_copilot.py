"""Local browser + PC copilot built from extension and environment context."""

from __future__ import annotations

from typing import Any

from core import browser_extension_bridge, environment_awareness


def current_page_help() -> dict[str, Any]:
    env = environment_awareness.status()
    insight = browser_extension_bridge.latest_page_insight()
    if not insight.get("ok"):
        return {"ok": False, "environment": env, "browser": insight, "summary": "No browser page context yet. Load the Friday browser extension in Chrome or Edge."}
    page = insight.get("page") or {}
    forms = page.get("forms") or []
    buttons = page.get("buttons") or []
    inputs = page.get("inputs") or []
    errors = insight.get("console_errors") or []
    capabilities = [
        "summarize current tab",
        "detect headings/buttons/forms/inputs",
        "queue safe DOM actions",
        "debug console errors",
        "explain page structure",
        "refuse password/hidden/secret-like form values",
    ]
    return {
        "ok": True,
        "environment": env,
        "browser": insight,
        "capabilities": capabilities,
        "summary": f"Browser/PC copilot sees {page.get('title') or page.get('url')}: {len(buttons)} button(s), {len(inputs)} input(s), {len(forms)} form(s), {len(errors)} console issue(s).",
    }


def summarize_current_tab() -> dict[str, Any]:
    insight = browser_extension_bridge.latest_page_insight()
    if not insight.get("ok"):
        return insight
    page = insight.get("page") or {}
    headings = page.get("headings") or []
    buttons = page.get("buttons") or []
    links = page.get("links") or []
    summary = [
        f"Title: {page.get('title') or 'unknown'}",
        f"URL: {page.get('url') or 'unknown'}",
        "Headings: " + ", ".join((item.get("text") or "") for item in headings[:8] if item.get("text")),
        "Main buttons: " + ", ".join((item.get("text") or item.get("aria") or "") for item in buttons[:8] if item.get("text") or item.get("aria")),
        f"Links detected: {len(links)}",
    ]
    if insight.get("console_errors"):
        summary.append(f"Console warnings/errors: {len(insight['console_errors'])}")
    return {"ok": True, "summary": " | ".join(part for part in summary if part.strip()), "page": page}


def debug_current_page() -> dict[str, Any]:
    insight = browser_extension_bridge.latest_page_insight()
    if not insight.get("ok"):
        return insight
    errors = insight.get("console_errors") or []
    if not errors:
        return {"ok": True, "summary": "No browser console warnings/errors detected for the current extension context.", "errors": []}
    first = errors[0]
    message = first.get("message") or first.get("summary") or ""
    return {
        "ok": True,
        "summary": f"Browser console issue: {message[:240]}",
        "errors": errors,
        "next_steps": [
            "Reproduce the issue in the same tab.",
            "Open the related source file or component.",
            "Run the narrowest web build/test check.",
            "Create a proof report after the fix.",
        ],
    }


def safe_form_plan(selector: str = "", value: str = "") -> dict[str, Any]:
    if _looks_sensitive(selector + " " + value):
        return {"ok": False, "summary": "Refused: this looks like a password, token, credential, or hidden/private form value."}
    return {"ok": True, "summary": "Form action looks non-sensitive. Queue it through /browser-extension/action so the extension can execute it in-page."}


def status() -> dict[str, Any]:
    return current_page_help()


def _looks_sensitive(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(term in lowered for term in ("password", "token", "secret", "api_key", "authorization", "credential", "hidden"))

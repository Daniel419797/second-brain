"""Optional Playwright browser automation layer for reliable website control."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, config_value


def available() -> dict[str, Any]:
    try:
        import playwright.sync_api  # noqa: F401

        return {"available": True, "reason": "playwright_installed"}
    except Exception as exc:
        return {
            "available": False,
            "reason": "playwright_not_installed",
            "detail": str(exc),
            "install_hint": ".\\.venv\\Scripts\\pip.exe install playwright && .\\.venv\\Scripts\\python.exe -m playwright install chromium",
        }


def inspect_url(url: str, *, limit: int = 40) -> dict[str, Any]:
    if not bool(config_value("browser_playwright_enabled", True)):
        return {"available": False, "reason": "browser_playwright_disabled"}
    status = available()
    if not status["available"]:
        return status
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = _launch_browser(p)
            page = browser.new_page()
            page.goto(_safe_url(url), wait_until="domcontentloaded", timeout=_timeout_ms())
            payload = _page_context(page, limit=limit)
            browser.close()
            return payload | {"available": True}
    except Exception as exc:
        return {"available": False, "reason": "playwright_error", "detail": str(exc)}


def run_steps(url: str, steps: list[dict[str, Any]], *, screenshot: bool = True) -> dict[str, Any]:
    if not bool(config_value("browser_playwright_enabled", True)):
        return {"ok": False, "reason": "browser_playwright_disabled", "steps": []}
    status = available()
    if not status["available"]:
        return {"ok": False, **status, "steps": []}
    executed: list[dict[str, Any]] = []
    screenshot_path = ""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = _launch_browser(p)
            page = browser.new_page()
            page.goto(_safe_url(url), wait_until="domcontentloaded", timeout=_timeout_ms())
            for index, step in enumerate(steps[: int(config_value("browser_playwright_max_steps", 12))], start=1):
                executed.append(_run_step(page, step, index))
            if screenshot:
                screenshot_path = _screenshot_path()
                page.screenshot(path=screenshot_path, full_page=False)
            context = _page_context(page, limit=20)
            browser.close()
            return {"ok": all(item.get("ok") for item in executed), "steps": executed, "screenshot": screenshot_path, "context": context}
    except Exception as exc:
        executed.append({"ok": False, "action": "error", "result": str(exc)})
        return {"ok": False, "reason": "playwright_error", "detail": str(exc), "steps": executed, "screenshot": screenshot_path}


def open_url(url: str) -> dict[str, Any]:
    return run_steps(url, [], screenshot=False)


def _launch_browser(playwright: Any) -> Any:
    headless = bool(config_value("browser_playwright_headless", False))
    channel = str(config_value("browser_playwright_channel", "chrome") or "").strip() or None
    try:
        return playwright.chromium.launch(channel=channel, headless=headless)
    except Exception:
        return playwright.chromium.launch(headless=headless)


def _run_step(page: Any, step: dict[str, Any], index: int) -> dict[str, Any]:
    action = str(step.get("action") or "").strip().lower()
    selector = str(step.get("selector") or step.get("target") or "").strip()
    text = str(step.get("text") or step.get("value") or "").strip()
    try:
        if action in {"click", "press"}:
            if action == "press" and text:
                page.keyboard.press(text)
            else:
                page.locator(selector).first.click(timeout=_timeout_ms())
        elif action in {"fill", "type"}:
            page.locator(selector).first.fill(text, timeout=_timeout_ms())
        elif action == "select":
            page.locator(selector).first.select_option(text, timeout=_timeout_ms())
        elif action == "goto":
            page.goto(_safe_url(text or selector), wait_until="domcontentloaded", timeout=_timeout_ms())
        elif action == "wait":
            page.wait_for_timeout(max(100, min(10000, int(float(text or step.get("ms") or 500)))))
        else:
            return {"index": index, "ok": False, "action": action or "unknown", "selector": selector, "result": "Unsupported Playwright action."}
        return {"index": index, "ok": True, "action": action, "selector": selector, "result": "ok"}
    except Exception as exc:
        return {"index": index, "ok": False, "action": action, "selector": selector, "result": str(exc)}


def _page_context(page: Any, *, limit: int) -> dict[str, Any]:
    elements = page.evaluate(
        """
        (limit) => Array.from(document.querySelectorAll('a,button,input,textarea,select,[role="button"],[contenteditable="true"]'))
          .slice(0, limit)
          .map((el, index) => ({
            index,
            tag: el.tagName.toLowerCase(),
            text: (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim().slice(0, 120),
            role: el.getAttribute('role') || '',
            name: el.getAttribute('name') || '',
            id: el.id || '',
            selector: el.id ? '#' + CSS.escape(el.id) : el.getAttribute('name') ? el.tagName.toLowerCase() + '[name="' + el.getAttribute('name') + '"]' : ''
          }))
        """,
        max(1, min(200, int(limit))),
    )
    text = page.locator("body").inner_text(timeout=_timeout_ms())[:1200]
    return {
        "url": page.url,
        "title": page.title(),
        "elements": elements,
        "page_text": re.sub(r"\s+", " ", text).strip(),
    }


def _safe_url(url: str) -> str:
    target = str(url or "").strip()
    if not target:
        return "about:blank"
    if not re.match(r"^https?://", target, re.IGNORECASE):
        target = "https://" + target
    return target


def _timeout_ms() -> int:
    return max(500, int(float(config_value("browser_playwright_timeout_seconds", 8.0)) * 1000))


def _screenshot_path() -> str:
    root = DATA_DIR / "screenshots"
    root.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(prefix="playwright_", suffix=".png", dir=root, delete=False)
    path = handle.name
    handle.close()
    return str(Path(path))

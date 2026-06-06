"""Optional Playwright browser automation layer for reliable website control."""

from __future__ import annotations

import re
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from core import command_runner
from core.config import DATA_DIR, config_value


def available() -> dict[str, Any]:
    python_status = _python_available()
    if python_status.get("available"):
        return python_status
    cli_status = _cli_available()
    if cli_status.get("available"):
        return {**cli_status, "python_detail": python_status.get("detail")}
    return python_status


def _python_available() -> dict[str, Any]:
    try:
        import playwright.sync_api  # noqa: F401

        return {"available": True, "reason": "playwright_python_installed", "mode": "python"}
    except Exception as exc:
        return {
            "available": False,
            "reason": "playwright_not_installed",
            "detail": str(exc),
            "install_hint": "Install Playwright with either Python or the global CLI: pip install playwright && python -m playwright install chromium, or npm install -g playwright && playwright install chromium.",
        }


def _cli_available() -> dict[str, Any]:
    executable = shutil.which("playwright.cmd") or shutil.which("playwright") or shutil.which("playwright.ps1")
    if not executable:
        return {"available": False, "reason": "playwright_cli_not_found"}
    try:
        completed = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception as exc:
        return {"available": False, "reason": "playwright_cli_error", "detail": str(exc), "executable": executable}
    if completed.returncode != 0:
        return {
            "available": False,
            "reason": "playwright_cli_error",
            "detail": (completed.stderr or completed.stdout or "").strip(),
            "executable": executable,
        }
    return {
        "available": True,
        "reason": "playwright_cli_installed",
        "mode": "cli",
        "executable": executable,
        "version": (completed.stdout or "").strip(),
    }


def ensure_available(log_dir: str | Path | None = None) -> dict[str, Any]:
    """Install Playwright tooling when allowed, then return availability."""

    status = available()
    if status.get("available"):
        return {**status, "install_attempted": False, "install_logs": []}
    if not bool(config_value("browser_playwright_auto_install", True)):
        return {**status, "install_attempted": False, "install_logs": []}

    root = Path(log_dir) if log_dir else DATA_DIR / "logs" / "browser-playwright"
    root.mkdir(parents=True, exist_ok=True)
    timeout = int(config_value("browser_playwright_install_timeout_seconds", 600))
    logs: list[str] = []
    commands = [
        ("playwright-pip-install.log", f"{sys.executable} -m pip install playwright"),
    ]
    for name, command in commands:
        log_path = root / name
        logs.append(str(log_path))
        try:
            completed = command_runner.run(command, timeout=timeout, extra_allowed={sys.executable})
            log_path.write_text((completed.stdout or "") + (completed.stderr or ""), encoding="utf-8", errors="ignore")
            if completed.returncode != 0:
                return {
                    "available": False,
                    "reason": "playwright_install_failed",
                    "detail": f"{command} exited with {completed.returncode}",
                    "install_attempted": True,
                    "install_logs": logs,
                }
        except (command_runner.CommandRejected, FileNotFoundError, subprocess.TimeoutExpired) as exc:
            log_path.write_text(str(exc) + "\n", encoding="utf-8", errors="ignore")
            return {
                "available": False,
                "reason": "playwright_install_failed",
                "detail": str(exc),
                "install_attempted": True,
                "install_logs": logs,
                }

    after_pip = available()
    channel = str(config_value("browser_playwright_channel", "chrome") or "").strip()
    if after_pip.get("available") and channel:
        return {**after_pip, "install_attempted": True, "install_logs": logs, "browser_channel": channel}

    browser_log = root / "playwright-browser-install.log"
    logs.append(str(browser_log))
    browser_command = f"{sys.executable} -m playwright install chromium"
    try:
        completed = command_runner.run(browser_command, timeout=timeout, extra_allowed={sys.executable})
        browser_log.write_text((completed.stdout or "") + (completed.stderr or ""), encoding="utf-8", errors="ignore")
        if completed.returncode != 0:
            return {
                "available": False,
                "reason": "playwright_install_failed",
                "detail": f"{browser_command} exited with {completed.returncode}",
                "install_attempted": True,
                "install_logs": logs,
            }
    except (command_runner.CommandRejected, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        browser_log.write_text(str(exc) + "\n", encoding="utf-8", errors="ignore")
        return {
            "available": False,
            "reason": "playwright_install_failed",
            "detail": str(exc),
            "install_attempted": True,
            "install_logs": logs,
        }

    return {**available(), "install_attempted": True, "install_logs": logs}


def inspect_url(url: str, *, limit: int = 40) -> dict[str, Any]:
    if not bool(config_value("browser_playwright_enabled", True)):
        return {"available": False, "reason": "browser_playwright_disabled"}
    status = available()
    if not status["available"]:
        return status
    if status.get("mode") == "cli":
        return _inspect_url_cli(url, limit=limit)
    try:
        _prepare_python_playwright_runtime()
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = _launch_browser(p)
            page = browser.new_page()
            page.goto(_safe_url(url), wait_until="domcontentloaded", timeout=_timeout_ms())
            payload = _page_context(page, limit=limit)
            browser.close()
            return payload | {"available": True}
    except Exception as exc:
        if _is_python_playwright_subprocess_failure(exc):
            cli_status = _cli_available()
            if cli_status.get("available"):
                return _inspect_url_cli(url, limit=limit)
        return {"available": False, "reason": "playwright_error", "detail": str(exc)}


def run_steps(url: str, steps: list[dict[str, Any]], *, screenshot: bool = True) -> dict[str, Any]:
    if not bool(config_value("browser_playwright_enabled", True)):
        return {"ok": False, "reason": "browser_playwright_disabled", "steps": []}
    status = available()
    if not status["available"]:
        return {"ok": False, **status, "steps": []}
    if status.get("mode") == "cli":
        return _run_steps_cli(url, steps, screenshot=screenshot)
    executed: list[dict[str, Any]] = []
    screenshot_path = ""
    try:
        _prepare_python_playwright_runtime()
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
            visual = _visual_context(page)
            browser.close()
            return {
                "ok": all(item.get("ok") for item in executed),
                "steps": executed,
                "screenshot": screenshot_path,
                "context": context,
                "visual": visual,
                "mode": "python",
            }
    except Exception as exc:
        if _is_python_playwright_subprocess_failure(exc):
            cli_status = _cli_available()
            if cli_status.get("available"):
                return _run_steps_cli(url, steps, screenshot=screenshot)
        executed.append({"ok": False, "action": "error", "result": str(exc)})
        return {"ok": False, "reason": "playwright_error", "detail": str(exc), "steps": executed, "screenshot": screenshot_path}


def open_url(url: str) -> dict[str, Any]:
    return run_steps(url, [], screenshot=False)


def visual_audit(url: str, *, screenshot_dir: str | Path | None = None, viewports: list[dict[str, int]] | None = None) -> dict[str, Any]:
    """Capture rendered screenshots and layout findings for Friday's UI self-review."""

    if not bool(config_value("browser_playwright_enabled", True)):
        return {"ok": False, "reason": "browser_playwright_disabled", "screenshots": [], "findings": []}
    status = ensure_available(screenshot_dir)
    if not status.get("available"):
        return {"ok": False, **status, "screenshots": [], "findings": []}
    targets = viewports or [
        {"width": 1440, "height": 900, "label": "desktop"},
        {"width": 390, "height": 844, "label": "mobile"},
    ]
    if status.get("mode") == "cli":
        return _visual_audit_cli(url, screenshot_dir=screenshot_dir, viewports=targets, status=status)
    return _visual_audit_python(url, screenshot_dir=screenshot_dir, viewports=targets, status=status)


def _inspect_url_cli(url: str, *, limit: int) -> dict[str, Any]:
    result = _run_steps_cli(url, [], screenshot=False, limit=limit)
    if not result.get("ok"):
        return {"available": False, "reason": result.get("reason") or "playwright_cli_error", "detail": result.get("detail")}
    return {"available": True, **(result.get("context") or {}), "visual": result.get("visual") or {}, "mode": "cli"}


def _run_steps_cli(url: str, steps: list[dict[str, Any]], *, screenshot: bool = True, limit: int = 20, viewport: dict[str, int] | None = None) -> dict[str, Any]:
    screenshot_path = _screenshot_path() if screenshot else ""
    payload = _run_node_playwright(
        _safe_url(url),
        steps[: int(config_value("browser_playwright_max_steps", 12))],
        screenshot_path=screenshot_path,
        limit=limit,
        viewport=viewport or {"width": 1440, "height": 900},
    )
    if not payload.get("ok"):
        if screenshot:
            fallback = _cli_screenshot(_safe_url(url), screenshot_path, viewport=viewport or {"width": 1440, "height": 900})
            if fallback.get("ok"):
                return {
                    "ok": not steps,
                    "steps": [],
                    "screenshot": screenshot_path,
                    "context": {},
                    "visual": {},
                    "mode": "cli",
                    "fallback": fallback,
                }
        return {"ok": False, "reason": payload.get("reason") or "playwright_cli_error", "detail": payload.get("detail"), "steps": [], "screenshot": screenshot_path, "mode": "cli"}
    return {**payload, "screenshot": screenshot_path, "mode": "cli"}


def _visual_audit_python(url: str, *, screenshot_dir: str | Path | None, viewports: list[dict[str, int]], status: dict[str, Any]) -> dict[str, Any]:
    screenshots: list[str] = []
    contexts: list[dict[str, Any]] = []
    try:
        _prepare_python_playwright_runtime()
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = _launch_browser(p, headless=True)
            for viewport in viewports:
                width = int(viewport.get("width") or 1440)
                height = int(viewport.get("height") or 900)
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(_safe_url(url), wait_until="domcontentloaded", timeout=_timeout_ms())
                page.wait_for_timeout(500)
                screenshot_path = _screenshot_path(screenshot_dir, prefix=f"visual_{_clean_label(viewport.get('label') or f'{width}x{height}')}_")
                page.screenshot(path=screenshot_path, full_page=False)
                screenshots.append(screenshot_path)
                contexts.append({"viewport": {"width": width, "height": height, "label": viewport.get("label")}, "context": _page_context(page, limit=50), "visual": _visual_context(page)})
                page.close()
            browser.close()
    except Exception as exc:
        if _is_python_playwright_subprocess_failure(exc):
            cli_status = _cli_available()
            if cli_status.get("available"):
                return _visual_audit_cli(url, screenshot_dir=screenshot_dir, viewports=viewports, status=cli_status)
        return {"ok": False, "reason": "playwright_error", "detail": str(exc), "screenshots": screenshots, "findings": []}
    findings = _visual_findings(contexts)
    return {
        "ok": not findings,
        "reason": "visual_findings" if findings else "visual_audit_passed",
        "screenshots": screenshots,
        "findings": findings,
        "contexts": contexts,
        "provider": status,
    }


def _visual_audit_cli(url: str, *, screenshot_dir: str | Path | None, viewports: list[dict[str, int]], status: dict[str, Any]) -> dict[str, Any]:
    screenshots: list[str] = []
    contexts: list[dict[str, Any]] = []
    errors: list[str] = []
    for viewport in viewports:
        width = int(viewport.get("width") or 1440)
        height = int(viewport.get("height") or 900)
        screenshot_path = _screenshot_path(screenshot_dir, prefix=f"visual_{_clean_label(viewport.get('label') or f'{width}x{height}')}_")
        result = _run_node_playwright(
            _safe_url(url),
            [],
            screenshot_path=screenshot_path,
            limit=50,
            viewport={"width": width, "height": height},
        )
        if result.get("ok"):
            screenshots.append(screenshot_path)
            contexts.append({"viewport": {"width": width, "height": height, "label": viewport.get("label")}, "context": result.get("context") or {}, "visual": result.get("visual") or {}})
            continue
        fallback = _cli_screenshot(_safe_url(url), screenshot_path, viewport={"width": width, "height": height})
        if fallback.get("ok"):
            screenshots.append(screenshot_path)
            contexts.append({"viewport": {"width": width, "height": height, "label": viewport.get("label")}, "context": {}, "visual": {}})
        else:
            errors.append(str(result.get("detail") or fallback.get("detail") or "Playwright CLI screenshot failed."))
    findings = _visual_findings(contexts)
    return {
        "ok": bool(screenshots) and not findings and not errors,
        "reason": "visual_findings" if findings else ("playwright_cli_error" if errors else "visual_audit_passed"),
        "screenshots": screenshots,
        "findings": [*findings, *errors],
        "contexts": contexts,
        "provider": status,
    }


def _launch_browser(playwright: Any, *, headless: bool | None = None) -> Any:
    if headless is None:
        headless = bool(config_value("browser_playwright_headless", False))
    channel = str(config_value("browser_playwright_channel", "chrome") or "").strip() or None
    try:
        return playwright.chromium.launch(channel=channel, headless=headless)
    except Exception:
        return playwright.chromium.launch(headless=headless)


def _prepare_python_playwright_runtime() -> None:
    """Keep Python Playwright usable on Windows even after libraries change the loop policy."""

    if not sys.platform.startswith("win"):
        return
    try:
        policy = asyncio.get_event_loop_policy()
        policy_name = policy.__class__.__name__.lower()
        if "selector" in policy_name and hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        return


def _is_python_playwright_subprocess_failure(exc: Exception) -> bool:
    text = f"{exc.__class__.__name__}: {exc}".lower()
    return "notimplementederror" in text or "subprocess" in text or "_make_subprocess_transport" in text


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


def _run_node_playwright(url: str, steps: list[dict[str, Any]], *, screenshot_path: str, limit: int, viewport: dict[str, int]) -> dict[str, Any]:
    node = shutil.which("node")
    if not node:
        return {"ok": False, "reason": "node_not_found", "detail": "Node.js is required for the global Playwright CLI fallback."}
    script_path = _node_script_path()
    timeout = max(5, int(config_value("browser_playwright_timeout_seconds", 8.0) or 8) + 5)
    args = [
        node,
        str(script_path),
        url,
        json.dumps(steps, ensure_ascii=True),
        screenshot_path,
        str(max(500, int(float(config_value("browser_playwright_timeout_seconds", 8.0)) * 1000))),
        str(max(1, min(200, int(limit)))),
        str(int(viewport.get("width") or 1440)),
        str(int(viewport.get("height") or 900)),
    ]
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=_node_env(),
        )
    except Exception as exc:
        return {"ok": False, "reason": "playwright_node_error", "detail": str(exc)}
    if completed.returncode != 0:
        return {
            "ok": False,
            "reason": "playwright_node_error",
            "detail": (completed.stderr or completed.stdout or "").strip(),
        }
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        return {"ok": False, "reason": "playwright_node_parse_error", "detail": str(exc), "stdout": completed.stdout}
    return payload if isinstance(payload, dict) else {"ok": False, "reason": "playwright_node_parse_error"}


def _cli_screenshot(url: str, screenshot_path: str, *, viewport: dict[str, int]) -> dict[str, Any]:
    executable = shutil.which("playwright.cmd") or shutil.which("playwright") or shutil.which("playwright.ps1")
    if not executable:
        return {"ok": False, "reason": "playwright_cli_not_found"}
    width = int(viewport.get("width") or 1440)
    height = int(viewport.get("height") or 900)
    try:
        completed = subprocess.run(
            [executable, "screenshot", f"--viewport-size={width},{height}", url, screenshot_path],
            capture_output=True,
            text=True,
            timeout=max(15, int(config_value("browser_playwright_timeout_seconds", 8.0) or 8) + 10),
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "reason": "playwright_cli_error", "detail": str(exc)}
    return {
        "ok": completed.returncode == 0,
        "reason": "playwright_cli_screenshot" if completed.returncode == 0 else "playwright_cli_error",
        "detail": (completed.stderr or completed.stdout or "").strip(),
    }


def _node_script_path() -> Path:
    root = DATA_DIR / "browser-playwright"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "friday-playwright-runner.cjs"
    path.write_text(_node_script_source(), encoding="utf-8")
    return path


def _node_env() -> dict[str, str]:
    env = os.environ.copy()
    global_root = _npm_root_global()
    if global_root:
        existing = env.get("NODE_PATH", "")
        env["NODE_PATH"] = os.pathsep.join([item for item in (global_root, existing) if item])
    return env


def _npm_root_global() -> str:
    try:
        completed = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, timeout=10, check=False)
    except Exception:
        return ""
    return (completed.stdout or "").strip() if completed.returncode == 0 else ""


def _node_script_source() -> str:
    return r"""
const { chromium } = require('playwright');

const [url, stepsJson, screenshotPath, timeoutRaw, limitRaw, widthRaw, heightRaw] = process.argv.slice(2);
const timeout = Number(timeoutRaw || 8000);
const limit = Math.max(1, Math.min(200, Number(limitRaw || 20)));
const width = Number(widthRaw || 1440);
const height = Number(heightRaw || 900);

function cssEscape(value) {
  return String(value || '').replace(/"/g, '\\"');
}

async function runStep(page, step, index) {
  const action = String(step.action || '').toLowerCase();
  const selector = String(step.selector || step.target || '');
  const text = String(step.text || step.value || '');
  try {
    if (action === 'click') {
      if (selector.startsWith('text=')) {
        await page.getByText(selector.slice(5), { exact: false }).first().click({ timeout });
      } else {
        await page.locator(selector).first().click({ timeout });
      }
    } else if (action === 'press') {
      await page.keyboard.press(text || selector);
    } else if (action === 'fill' || action === 'type') {
      await page.locator(selector).first().fill(text, { timeout });
    } else if (action === 'select') {
      await page.locator(selector).first().selectOption(text, { timeout });
    } else if (action === 'goto') {
      await page.goto(text || selector, { waitUntil: 'domcontentloaded', timeout });
    } else if (action === 'wait') {
      await page.waitForTimeout(Math.max(100, Math.min(10000, Number(text || step.ms || 500))));
    } else {
      return { index, ok: false, action: action || 'unknown', selector, result: 'Unsupported Playwright action.' };
    }
    return { index, ok: true, action, selector, result: 'ok' };
  } catch (error) {
    return { index, ok: false, action, selector, result: String(error && error.message || error) };
  }
}

async function pageContext(page) {
  const elements = await page.evaluate((limit) => Array.from(document.querySelectorAll('a,button,input,textarea,select,[role="button"],[contenteditable="true"]'))
    .slice(0, limit)
    .map((el, index) => {
      const text = (el.innerText || '').trim() || (el.value || '').trim() || (el.getAttribute('aria-label') || '').trim() || (el.getAttribute('title') || '').trim();
      return {
        index,
        tag: el.tagName.toLowerCase(),
        text: text.slice(0, 120),
        role: el.getAttribute('role') || '',
        name: el.getAttribute('name') || '',
        id: el.id || '',
        href: el.getAttribute('href') || '',
        selector: el.id ? '#' + cssEscape(el.id) : el.getAttribute('name') ? el.tagName.toLowerCase() + '[name="' + cssEscape(el.getAttribute('name')) + '"]' : ''
      };
    }), limit);
  const pageText = await page.locator('body').innerText({ timeout }).catch(() => '');
  return {
    url: page.url(),
    title: await page.title(),
    elements,
    page_text: pageText.replace(/\s+/g, ' ').trim().slice(0, 1200)
  };
}

async function visualContext(page) {
  return await page.evaluate(() => {
    const viewport = { width: window.innerWidth, height: window.innerHeight };
    const rectPayload = (el) => {
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      return {
        tag: el.tagName.toLowerCase(),
        text: (el.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 160),
        fontSize: parseFloat(style.fontSize || '0'),
        lineHeight: style.lineHeight,
        top: rect.top,
        bottom: rect.bottom,
        left: rect.left,
        right: rect.right,
        width: rect.width,
        height: rect.height,
        visible: rect.width > 1 && rect.height > 1 && rect.bottom > 0 && rect.top < viewport.height
      };
    };
    const headings = Array.from(document.querySelectorAll('h1,h2,h3')).slice(0, 40).map(rectPayload);
    const images = Array.from(document.querySelectorAll('img')).slice(0, 40).map((el) => ({
      src: el.currentSrc || el.src || '',
      alt: el.getAttribute('alt') || '',
      complete: Boolean(el.complete),
      naturalWidth: el.naturalWidth || 0,
      naturalHeight: el.naturalHeight || 0,
      rect: rectPayload(el)
    }));
    const interactives = Array.from(document.querySelectorAll('a,button,[role="button"]')).slice(0, 80).map((el) => ({
      tag: el.tagName.toLowerCase(),
      text: (el.innerText || el.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim().slice(0, 120),
      href: el.getAttribute('href') || '',
      disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true'),
      rect: rectPayload(el)
    }));
    const firstViewportText = Array.from(document.body.querySelectorAll('h1,h2,h3,p,a,button,label,li'))
      .filter((el) => {
        const rect = el.getBoundingClientRect();
        return rect.bottom > 0 && rect.top < viewport.height && rect.width > 1 && rect.height > 1;
      })
      .map((el) => el.innerText || el.getAttribute('aria-label') || '')
      .join(' ')
      .replace(/\s+/g, ' ')
      .trim();
    const clipped = Array.from(document.body.querySelectorAll('h1,h2,h3,p,a,button,article,section'))
      .filter((el) => {
        const rect = el.getBoundingClientRect();
        return rect.right > viewport.width + 8 || rect.left < -8;
      })
      .slice(0, 20)
      .map(rectPayload);
    const canvasSignal = (el) => {
      const payload = { dataUrlLength: 0, nonBlankSample: false, readable: false, error: '' };
      try {
        payload.dataUrlLength = String(el.toDataURL('image/png') || '').length;
      } catch (error) {
        payload.error = String(error && error.message || error);
      }
      try {
        const ctx = el.getContext('2d', { willReadFrequently: true });
        if (ctx) {
          const width = Math.max(1, Math.min(24, el.width || 1));
          const height = Math.max(1, Math.min(24, el.height || 1));
          const data = ctx.getImageData(0, 0, width, height).data;
          for (let index = 0; index < data.length; index += 4) {
            if (data[index + 3] > 0 && (data[index] !== 0 || data[index + 1] !== 0 || data[index + 2] !== 0)) {
              payload.nonBlankSample = true;
              break;
            }
          }
          payload.readable = true;
        }
      } catch (error) {
        payload.error = payload.error || String(error && error.message || error);
      }
      return payload;
    };
    let cssText = '';
    for (const sheet of Array.from(document.styleSheets || [])) {
      try {
        cssText += Array.from(sheet.cssRules || []).map((rule) => rule.cssText || '').join('\\n').slice(0, 5000);
      } catch {
        // Cross-origin stylesheets are not inspectable.
      }
    }
    const canvases = Array.from(document.querySelectorAll('canvas')).slice(0, 12).map((el) => ({
      width: el.width || 0,
      height: el.height || 0,
      rect: rectPayload(el),
      signal: canvasSignal(el)
    }));
    const videos = Array.from(document.querySelectorAll('video')).slice(0, 12).map((el) => ({
      src: el.currentSrc || el.src || '',
      poster: el.getAttribute('poster') || '',
      paused: Boolean(el.paused),
      readyState: el.readyState || 0,
      rect: rectPayload(el)
    }));
    const motion = {
      hasCanvas: canvases.length > 0,
      hasVideo: videos.length > 0,
      hasReducedMotionCss: /prefers-reduced-motion/i.test(cssText),
      hasParallaxHints: /parallax|scroll-timeline|animation-timeline|position:\\s*sticky|transform:\\s*translate3d|will-change:\\s*transform/i.test(cssText + ' ' + document.body.innerHTML.slice(0, 30000)),
      hasMotionLibraryHints: /framer-motion|gsap|three|react-three|data-framer|motion\\./i.test(document.body.innerHTML.slice(0, 30000))
    };
    const px = (value) => Number.parseFloat(String(value || '0')) || 0;
    const hasUtilitySignal = (token) => /^(p[trblxy]?-|rounded|bg-|shadow|grid$|grid-|flex$|gap-|space-|items-|justify-)/.test(token);
    const isTransparent = (value) => !value || value === 'transparent' || value === 'rgba(0, 0, 0, 0)';
    const isLightColor = (value) => {
      const match = String(value || '').match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/i);
      if (!match) return false;
      return Number(match[1]) >= 210 && Number(match[2]) >= 210 && Number(match[3]) >= 210;
    };
    const visibleElements = Array.from(document.body.querySelectorAll('*')).filter((el) => {
      const rect = el.getBoundingClientRect();
      return rect.width > 3 && rect.height > 3 && rect.bottom > 0 && rect.top < viewport.height * 1.6;
    }).slice(0, 500);
    let classedVisible = 0;
    let utilityStyledChecks = 0;
    let utilityStyledMisses = 0;
    let largeWhiteBorderBoxes = 0;
    let unstyledUtilityElements = 0;
    for (const el of visibleElements) {
      const tokens = Array.from(el.classList || []).map(String).filter(Boolean);
      if (tokens.length) classedVisible += 1;
      const utilityTokens = tokens.filter(hasUtilitySignal);
      if (!utilityTokens.length) continue;
      const style = window.getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      const padding = px(style.paddingTop) + px(style.paddingRight) + px(style.paddingBottom) + px(style.paddingLeft);
      const radius = Math.max(px(style.borderTopLeftRadius), px(style.borderTopRightRadius), px(style.borderBottomLeftRadius), px(style.borderBottomRightRadius));
      const borderWidth = px(style.borderTopWidth) + px(style.borderRightWidth) + px(style.borderBottomWidth) + px(style.borderLeftWidth);
      const hasBg = !isTransparent(style.backgroundColor);
      const hasShadow = Boolean(style.boxShadow && style.boxShadow !== 'none');
      if (tokens.some((token) => /^p[trblxy]?-/.test(token))) {
        utilityStyledChecks += 1;
        if (padding < 4) utilityStyledMisses += 1;
      }
      if (tokens.some((token) => /^rounded/.test(token))) {
        utilityStyledChecks += 1;
        if (radius < 2) utilityStyledMisses += 1;
      }
      if (tokens.some((token) => /^bg-/.test(token))) {
        utilityStyledChecks += 1;
        if (!hasBg) utilityStyledMisses += 1;
      }
      if (tokens.some((token) => /^shadow/.test(token))) {
        utilityStyledChecks += 1;
        if (!hasShadow) utilityStyledMisses += 1;
      }
      if (tokens.some((token) => /^(grid$|grid-|flex$)/.test(token))) {
        utilityStyledChecks += 1;
        if (!['grid', 'flex', 'inline-flex'].includes(style.display)) utilityStyledMisses += 1;
      }
      if (rect.width * rect.height >= 18000 && borderWidth > 0 && radius < 2 && isLightColor(style.borderTopColor)) {
        largeWhiteBorderBoxes += 1;
      }
      if (utilityTokens.length >= 3 && padding < 4 && radius < 2 && !hasBg && !hasShadow) {
        unstyledUtilityElements += 1;
      }
    }
    const styleHealth = {
      classedVisible,
      utilityStyledChecks,
      utilityStyledMisses,
      utilityMissRatio: utilityStyledChecks ? utilityStyledMisses / utilityStyledChecks : 0,
      largeWhiteBorderBoxes,
      unstyledUtilityElements,
      stylesheetCount: Array.from(document.styleSheets || []).length
    };
    return {
      viewport,
      bodyHeight: document.documentElement.scrollHeight,
      scrollWidth: document.documentElement.scrollWidth,
      horizontalOverflow: document.documentElement.scrollWidth > viewport.width + 4,
      firstViewportTextLength: firstViewportText.length,
      headings,
      images,
      interactives,
      clipped,
      canvases,
      videos,
      motion,
      styleHealth
    };
  });
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width, height } });
  const executed = [];
  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout });
    await page.waitForTimeout(500);
    const steps = JSON.parse(stepsJson || '[]');
    for (let index = 0; index < steps.length; index += 1) {
      executed.push(await runStep(page, steps[index], index + 1));
    }
    if (screenshotPath) {
      await page.screenshot({ path: screenshotPath, fullPage: false });
    }
    const context = await pageContext(page);
    const visual = await visualContext(page);
    await browser.close();
    console.log(JSON.stringify({ ok: executed.every((item) => item.ok), steps: executed, context, visual }));
  } catch (error) {
    await browser.close().catch(() => {});
    console.error(String(error && error.stack || error));
    process.exit(1);
  }
})();
"""


def _page_context(page: Any, *, limit: int) -> dict[str, Any]:
    elements = page.evaluate(
        """
        (limit) => Array.from(document.querySelectorAll('a,button,input,textarea,select,[role="button"],[contenteditable="true"]'))
          .slice(0, limit)
          .map((el, index) => {
            const text = (el.innerText || '').trim() || (el.value || '').trim() || (el.getAttribute('aria-label') || '').trim() || (el.getAttribute('title') || '').trim();
            return {
              index,
              tag: el.tagName.toLowerCase(),
              text: text.slice(0, 120),
              role: el.getAttribute('role') || '',
              name: el.getAttribute('name') || '',
              id: el.id || '',
              selector: el.id ? '#' + CSS.escape(el.id) : el.getAttribute('name') ? el.tagName.toLowerCase() + '[name="' + el.getAttribute('name') + '"]' : ''
            };
          })
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


def _visual_context(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """
        () => {
          const viewport = { width: window.innerWidth, height: window.innerHeight };
          const rectPayload = (el) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return {
              tag: el.tagName.toLowerCase(),
              text: (el.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 160),
              fontSize: parseFloat(style.fontSize || '0'),
              lineHeight: style.lineHeight,
              top: rect.top,
              bottom: rect.bottom,
              left: rect.left,
              right: rect.right,
              width: rect.width,
              height: rect.height,
              visible: rect.width > 1 && rect.height > 1 && rect.bottom > 0 && rect.top < viewport.height
            };
          };
          const headings = Array.from(document.querySelectorAll('h1,h2,h3')).slice(0, 40).map(rectPayload);
          const images = Array.from(document.querySelectorAll('img')).slice(0, 40).map((el) => ({
            src: el.currentSrc || el.src || '',
            alt: el.getAttribute('alt') || '',
            complete: Boolean(el.complete),
            naturalWidth: el.naturalWidth || 0,
            naturalHeight: el.naturalHeight || 0,
            rect: rectPayload(el)
          }));
          const interactives = Array.from(document.querySelectorAll('a,button,[role="button"]')).slice(0, 80).map((el) => ({
            tag: el.tagName.toLowerCase(),
            text: (el.innerText || el.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim().slice(0, 120),
            href: el.getAttribute('href') || '',
            disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true'),
            rect: rectPayload(el)
          }));
          const firstViewportText = Array.from(document.body.querySelectorAll('h1,h2,h3,p,a,button,label,li'))
            .filter((el) => {
              const rect = el.getBoundingClientRect();
              return rect.bottom > 0 && rect.top < viewport.height && rect.width > 1 && rect.height > 1;
            })
            .map((el) => el.innerText || el.getAttribute('aria-label') || '')
            .join(' ')
            .replace(/\\s+/g, ' ')
            .trim();
          const clipped = Array.from(document.body.querySelectorAll('h1,h2,h3,p,a,button,article,section'))
            .filter((el) => {
              const rect = el.getBoundingClientRect();
              return rect.right > viewport.width + 8 || rect.left < -8;
            })
            .slice(0, 20)
            .map(rectPayload);
          const canvasSignal = (el) => {
            const payload = { dataUrlLength: 0, nonBlankSample: false, readable: false, error: '' };
            try {
              payload.dataUrlLength = String(el.toDataURL('image/png') || '').length;
            } catch (error) {
              payload.error = String(error && error.message || error);
            }
            try {
              const ctx = el.getContext('2d', { willReadFrequently: true });
              if (ctx) {
                const width = Math.max(1, Math.min(24, el.width || 1));
                const height = Math.max(1, Math.min(24, el.height || 1));
                const data = ctx.getImageData(0, 0, width, height).data;
                for (let index = 0; index < data.length; index += 4) {
                  if (data[index + 3] > 0 && (data[index] !== 0 || data[index + 1] !== 0 || data[index + 2] !== 0)) {
                    payload.nonBlankSample = true;
                    break;
                  }
                }
                payload.readable = true;
              }
            } catch (error) {
              payload.error = payload.error || String(error && error.message || error);
            }
            return payload;
          };
          let cssText = '';
          for (const sheet of Array.from(document.styleSheets || [])) {
            try {
              cssText += Array.from(sheet.cssRules || []).map((rule) => rule.cssText || '').join('\\n').slice(0, 5000);
            } catch {
              // Cross-origin stylesheets are not inspectable.
            }
          }
          const canvases = Array.from(document.querySelectorAll('canvas')).slice(0, 12).map((el) => ({
            width: el.width || 0,
            height: el.height || 0,
            rect: rectPayload(el),
            signal: canvasSignal(el)
          }));
          const videos = Array.from(document.querySelectorAll('video')).slice(0, 12).map((el) => ({
            src: el.currentSrc || el.src || '',
            poster: el.getAttribute('poster') || '',
            paused: Boolean(el.paused),
            readyState: el.readyState || 0,
            rect: rectPayload(el)
          }));
          const motion = {
            hasCanvas: canvases.length > 0,
            hasVideo: videos.length > 0,
            hasReducedMotionCss: /prefers-reduced-motion/i.test(cssText),
            hasParallaxHints: /parallax|scroll-timeline|animation-timeline|position:\\s*sticky|transform:\\s*translate3d|will-change:\\s*transform/i.test(cssText + ' ' + document.body.innerHTML.slice(0, 30000)),
            hasMotionLibraryHints: /framer-motion|gsap|three|react-three|data-framer|motion\\./i.test(document.body.innerHTML.slice(0, 30000))
          };
          const px = (value) => Number.parseFloat(String(value || '0')) || 0;
          const hasUtilitySignal = (token) => /^(p[trblxy]?-|rounded|bg-|shadow|grid$|grid-|flex$|gap-|space-|items-|justify-)/.test(token);
          const isTransparent = (value) => !value || value === 'transparent' || value === 'rgba(0, 0, 0, 0)';
          const isLightColor = (value) => {
            const match = String(value || '').match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/i);
            if (!match) return false;
            return Number(match[1]) >= 210 && Number(match[2]) >= 210 && Number(match[3]) >= 210;
          };
          const visibleElements = Array.from(document.body.querySelectorAll('*')).filter((el) => {
            const rect = el.getBoundingClientRect();
            return rect.width > 3 && rect.height > 3 && rect.bottom > 0 && rect.top < viewport.height * 1.6;
          }).slice(0, 500);
          let classedVisible = 0;
          let utilityStyledChecks = 0;
          let utilityStyledMisses = 0;
          let largeWhiteBorderBoxes = 0;
          let unstyledUtilityElements = 0;
          for (const el of visibleElements) {
            const tokens = Array.from(el.classList || []).map(String).filter(Boolean);
            if (tokens.length) classedVisible += 1;
            const utilityTokens = tokens.filter(hasUtilitySignal);
            if (!utilityTokens.length) continue;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            const padding = px(style.paddingTop) + px(style.paddingRight) + px(style.paddingBottom) + px(style.paddingLeft);
            const radius = Math.max(px(style.borderTopLeftRadius), px(style.borderTopRightRadius), px(style.borderBottomLeftRadius), px(style.borderBottomRightRadius));
            const borderWidth = px(style.borderTopWidth) + px(style.borderRightWidth) + px(style.borderBottomWidth) + px(style.borderLeftWidth);
            const hasBg = !isTransparent(style.backgroundColor);
            const hasShadow = Boolean(style.boxShadow && style.boxShadow !== 'none');
            if (tokens.some((token) => /^p[trblxy]?-/.test(token))) {
              utilityStyledChecks += 1;
              if (padding < 4) utilityStyledMisses += 1;
            }
            if (tokens.some((token) => /^rounded/.test(token))) {
              utilityStyledChecks += 1;
              if (radius < 2) utilityStyledMisses += 1;
            }
            if (tokens.some((token) => /^bg-/.test(token))) {
              utilityStyledChecks += 1;
              if (!hasBg) utilityStyledMisses += 1;
            }
            if (tokens.some((token) => /^shadow/.test(token))) {
              utilityStyledChecks += 1;
              if (!hasShadow) utilityStyledMisses += 1;
            }
            if (tokens.some((token) => /^(grid$|grid-|flex$)/.test(token))) {
              utilityStyledChecks += 1;
              if (!['grid', 'flex', 'inline-flex'].includes(style.display)) utilityStyledMisses += 1;
            }
            if (rect.width * rect.height >= 18000 && borderWidth > 0 && radius < 2 && isLightColor(style.borderTopColor)) {
              largeWhiteBorderBoxes += 1;
            }
            if (utilityTokens.length >= 3 && padding < 4 && radius < 2 && !hasBg && !hasShadow) {
              unstyledUtilityElements += 1;
            }
          }
          const styleHealth = {
            classedVisible,
            utilityStyledChecks,
            utilityStyledMisses,
            utilityMissRatio: utilityStyledChecks ? utilityStyledMisses / utilityStyledChecks : 0,
            largeWhiteBorderBoxes,
            unstyledUtilityElements,
            stylesheetCount: Array.from(document.styleSheets || []).length
          };
          return {
            viewport,
            bodyHeight: document.documentElement.scrollHeight,
            scrollWidth: document.documentElement.scrollWidth,
            horizontalOverflow: document.documentElement.scrollWidth > viewport.width + 4,
            firstViewportTextLength: firstViewportText.length,
            headings,
            images,
            interactives,
            clipped,
            canvases,
            videos,
            motion,
            styleHealth
          };
        }
        """
    )


def _visual_findings(contexts: list[dict[str, Any]]) -> list[str]:
    findings: list[str] = []
    for item in contexts:
        viewport = item.get("viewport") if isinstance(item.get("viewport"), dict) else {}
        visual = item.get("visual") if isinstance(item.get("visual"), dict) else {}
        label = str(viewport.get("label") or f"{viewport.get('width', '?')}x{viewport.get('height', '?')}")
        width = int(viewport.get("width") or (visual.get("viewport") or {}).get("width") or 0)
        height = int(viewport.get("height") or (visual.get("viewport") or {}).get("height") or 0)
        headings = visual.get("headings") if isinstance(visual.get("headings"), list) else []
        h1s = [heading for heading in headings if str(heading.get("tag") or "").lower() == "h1"]
        h1 = h1s[0] if h1s else {}
        h1_size = float(h1.get("fontSize") or 0)
        h1_height = float(h1.get("height") or 0)
        h1_bottom = float(h1.get("bottom") or 0)
        if width >= 900 and h1_size > 112:
            findings.append(f"{label}: H1 font is too large ({h1_size:.0f}px).")
        if width >= 900 and h1_size > 76 and height and h1_height > height * 0.45:
            findings.append(f"{label}: H1 occupies too much of the viewport.")
        if width < 600 and h1_size > 64:
            findings.append(f"{label}: mobile H1 font is too large ({h1_size:.0f}px).")
        if height and h1_height > height * 0.55:
            findings.append(f"{label}: H1 occupies too much of the viewport.")
        if height and h1_bottom > height * 0.95:
            findings.append(f"{label}: hero headline extends beyond the first viewport.")
        if bool(visual.get("horizontalOverflow")):
            findings.append(f"{label}: page has horizontal overflow.")
        if int(visual.get("firstViewportTextLength") or 0) < 25:
            findings.append(f"{label}: first viewport appears visually empty or uninformative.")
        style_health = visual.get("styleHealth") if isinstance(visual.get("styleHealth"), dict) else {}
        visible_images = [
            image
            for image in (visual.get("images") or [])
            if isinstance(image, dict)
            and isinstance(image.get("rect"), dict)
            and image["rect"].get("visible")
            and int(image.get("naturalWidth") or 0) > 1
            and int(image.get("naturalHeight") or 0) > 1
        ]
        hero_is_rendered = (
            bool(h1.get("visible"))
            and int(visual.get("firstViewportTextLength") or 0) >= 80
            and (visible_images or h1_size >= 28)
        )
        classed_visible = int(style_health.get("classedVisible") or 0)
        utility_checks = int(style_health.get("utilityStyledChecks") or 0)
        miss_ratio = float(style_health.get("utilityMissRatio") or 0)
        raw_boxes = int(style_health.get("largeWhiteBorderBoxes") or 0)
        unstyled_elements = int(style_health.get("unstyledUtilityElements") or 0)
        if classed_visible >= 12 and utility_checks >= 12 and miss_ratio >= (0.7 if hero_is_rendered else 0.45):
            findings.append(
                f"{label}: utility-class styling appears uncompiled or missing ({miss_ratio:.0%} of sampled style checks failed)."
            )
        if raw_boxes >= (12 if hero_is_rendered else 6) and miss_ratio >= (0.4 if hero_is_rendered else 0.2):
            findings.append(f"{label}: rendered UI collapsed into raw bordered boxes instead of polished layout.")
        if unstyled_elements >= (16 if hero_is_rendered else 10) and miss_ratio >= (0.5 if hero_is_rendered else 0.25):
            findings.append(f"{label}: many visible utility-class elements have no effective spacing, radius, background, or shadow.")
        clipped = visual.get("clipped") if isinstance(visual.get("clipped"), list) else []
        if clipped:
            findings.append(f"{label}: {len(clipped)} visible element(s) overflow the viewport.")
        for link in visual.get("interactives") or []:
            href = str(link.get("href") or "").strip().lower()
            text = str(link.get("text") or "").strip()
            if href in {"#", "javascript:void(0)", "javascript:;"}:
                findings.append(f"{label}: dead link/button found: {text or href}.")
                break
        broken_images = []
        for image in visual.get("images") or []:
            rect = image.get("rect") if isinstance(image.get("rect"), dict) else {}
            if not rect.get("visible"):
                continue
            if not image.get("complete") or int(image.get("naturalWidth") or 0) <= 1 or int(image.get("naturalHeight") or 0) <= 1:
                broken_images.append(str(image.get("alt") or image.get("src") or "image"))
        if broken_images:
            findings.append(f"{label}: {len(broken_images)} visible image(s) failed to render: {broken_images[0][:80]}.")
        for canvas in visual.get("canvases") or []:
            if not isinstance(canvas, dict):
                continue
            rect = canvas.get("rect") if isinstance(canvas.get("rect"), dict) else {}
            if not rect.get("visible"):
                continue
            width_px = float(rect.get("width") or 0)
            height_px = float(rect.get("height") or 0)
            signal = canvas.get("signal") if isinstance(canvas.get("signal"), dict) else {}
            if width_px >= 160 and height_px >= 120 and not signal.get("nonBlankSample") and int(signal.get("dataUrlLength") or 0) < 1200:
                findings.append(f"{label}: visible canvas/3D scene appears blank or unrendered.")
                break
        primary_actions: dict[str, dict[str, Any]] = {}
        nav_like_labels = {
            "home",
            "about",
            "service",
            "services",
            "contact",
            "pricing",
            "collections",
            "collection",
            "atelier",
            "concierge",
            "concierge contact",
            "privacy",
            "terms",
        }
        for link in visual.get("interactives") or []:
            rect = link.get("rect") if isinstance(link.get("rect"), dict) else {}
            text = str(link.get("text") or "").strip().lower()
            href = str(link.get("href") or "").strip().lower()
            if not text or text in nav_like_labels or not rect.get("visible"):
                continue
            entry = primary_actions.setdefault(text, {"count": 0, "hrefs": set()})
            entry["count"] += 1
            if href:
                entry["hrefs"].add(href)
        repeated_actions = [
            text
            for text, payload in primary_actions.items()
            if int(payload.get("count") or 0) > 2 and len(payload.get("hrefs") or set()) > 1
        ]
        if repeated_actions:
            findings.append(f"{label}: duplicate visible CTA text found: {repeated_actions[0][:80]}.")
        seen: set[str] = set()
        for heading in headings:
            if not heading.get("visible"):
                continue
            text = str(heading.get("text") or "").strip().lower()
            if len(text) < 8:
                continue
            if text in seen:
                findings.append(f"{label}: repeated heading found: {text[:80]}.")
                break
            seen.add(text)
    return _dedupe(findings)


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _safe_url(url: str) -> str:
    target = str(url or "").strip()
    if not target:
        return "about:blank"
    if not re.match(r"^https?://", target, re.IGNORECASE):
        target = "https://" + target
    return target


def _timeout_ms() -> int:
    return max(500, int(float(config_value("browser_playwright_timeout_seconds", 8.0)) * 1000))


def _screenshot_path(root: str | Path | None = None, *, prefix: str = "playwright_") -> str:
    root = Path(root) if root else DATA_DIR / "screenshots"
    root.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(prefix=prefix, suffix=".png", dir=root, delete=False)
    path = handle.name
    handle.close()
    return str(Path(path))


def _clean_label(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "viewport")).strip("-") or "viewport"

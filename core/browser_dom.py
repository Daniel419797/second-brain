"""Chrome DevTools DOM bridge for reliable web UI control."""

from __future__ import annotations

import itertools
import json
import subprocess
from pathlib import Path
from typing import Any

try:
    import requests
except Exception:  # pragma: no cover - optional in minimal installs
    requests = None

try:
    import websocket
except Exception:  # pragma: no cover - optional until requirements are installed
    websocket = None

from core.config import DATA_DIR, config_value

_IDS = itertools.count(1)


def launch_debug_chrome(url: str = "") -> str:
    """Launch Chrome with a DevTools port so Friday can inspect DOM state."""
    chrome = _chrome_path()
    if not chrome:
        return "Chrome executable was not found."
    port = int(config_value("browser_debug_port", 9222))
    user_data_dir = Path(str(config_value("browser_debug_user_data_dir", DATA_DIR / "chrome-debug-profile"))).expanduser()
    user_data_dir.mkdir(parents=True, exist_ok=True)
    args = [
        chrome,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if url:
        args.append(url)
    try:
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        return f"Could not launch Chrome debug mode: {exc}"
    suffix = f" at {url}" if url else ""
    return f"Chrome debug mode opened{suffix}."


def context_summary(limit: int | None = None) -> dict[str, Any]:
    """Return visible-ish DOM controls from the active Chrome page."""
    if not bool(config_value("browser_dom_enabled", True)):
        return {"available": False, "reason": "browser_dom_disabled"}
    if requests is None or websocket is None:
        return {"available": False, "reason": "missing_requests_or_websocket_client"}
    page = _active_page()
    if not page:
        return {"available": False, "reason": "chrome_debug_not_connected"}
    ws_url = str(page.get("webSocketDebuggerUrl") or "")
    if not ws_url:
        return {"available": False, "reason": "chrome_debug_websocket_missing"}
    expression = _collect_dom_script(limit or int(config_value("browser_dom_max_elements", 60)))
    result = _runtime_evaluate(ws_url, expression)
    if not result:
        return {"available": False, "reason": "dom_evaluation_failed", "url": page.get("url", ""), "title": page.get("title", "")}
    result["available"] = True
    result.setdefault("url", page.get("url", ""))
    result.setdefault("title", page.get("title", ""))
    return result


def execute_dom_action(action: dict[str, Any]) -> str:
    page = _active_page()
    if not page:
        return "Browser DOM control unavailable: Chrome debug port is not connected."
    ws_url = str(page.get("webSocketDebuggerUrl") or "")
    name = str(action.get("action") or "").strip().lower()
    selector = str(action.get("selector") or "").strip()
    text = str(action.get("text") or action.get("target") or "")
    if name == "dom_click":
        if not selector:
            return "Browser DOM click failed: selector is missing."
        ok = _runtime_evaluate(ws_url, _dom_click_script(selector))
        return "Browser DOM clicked." if ok and ok.get("ok") else f"Browser DOM click failed: {(ok or {}).get('error', 'element not found')}"
    if name == "dom_type":
        if not selector:
            return "Browser DOM typing failed: selector is missing."
        ok = _runtime_evaluate(ws_url, _dom_type_script(selector, text))
        return "Browser DOM typed the text." if ok and ok.get("ok") else f"Browser DOM typing failed: {(ok or {}).get('error', 'element not found')}"
    if name == "dom_select":
        if not selector:
            return "Browser DOM select failed: selector is missing."
        ok = _runtime_evaluate(ws_url, _dom_select_script(selector, text))
        return "Browser DOM selected the value." if ok and ok.get("ok") else f"Browser DOM select failed: {(ok or {}).get('error', 'element not found')}"
    if name == "dom_scroll":
        amount = _int(action.get("amount") or action.get("y") or action.get("target"), 600)
        ok = _runtime_evaluate(ws_url, f"(() => {{ window.scrollBy(0, {amount}); return {{ok:true}}; }})()")
        return "Browser DOM scrolled." if ok and ok.get("ok") else "Browser DOM scroll failed."
    if name == "dom_navigate":
        url = str(action.get("url") or action.get("target") or "").strip()
        if not url.startswith(("http://", "https://")):
            return "Browser DOM navigation failed: URL must start with http:// or https://."
        response = _cdp_command(ws_url, "Page.navigate", {"url": url})
        return "Browser DOM navigated." if response and "error" not in response else "Browser DOM navigation failed."
    if name == "dom_press":
        key = _safe_key(str(action.get("key") or action.get("target") or ""))
        if not key:
            return "Browser DOM key press failed: unsafe key."
        response = _cdp_command(ws_url, "Input.dispatchKeyEvent", {"type": "keyDown", "key": key})
        _cdp_command(ws_url, "Input.dispatchKeyEvent", {"type": "keyUp", "key": key})
        return "Browser DOM pressed the key." if response and "error" not in response else "Browser DOM key press failed."
    return "Browser DOM action is unsupported."


def _active_page() -> dict[str, Any] | None:
    if requests is None:
        return None
    host = str(config_value("browser_debug_host", "127.0.0.1"))
    port = int(config_value("browser_debug_port", 9222))
    timeout = float(config_value("browser_debug_timeout_seconds", 1.5))
    try:
        response = requests.get(f"http://{host}:{port}/json/list", timeout=timeout)
        response.raise_for_status()
        pages = response.json()
    except Exception:
        return None
    candidates = [
        page
        for page in pages
        if page.get("type") == "page"
        and not str(page.get("url") or "").startswith(("devtools://", "chrome://"))
    ]
    return candidates[0] if candidates else None


def _runtime_evaluate(ws_url: str, expression: str) -> dict[str, Any] | None:
    payload = _cdp_command(
        ws_url,
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
    )
    try:
        value = payload["result"]["result"].get("value")
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _cdp_command(ws_url: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if websocket is None:
        return None
    message_id = next(_IDS)
    timeout = float(config_value("browser_debug_timeout_seconds", 1.5))
    try:
        ws = websocket.create_connection(ws_url, timeout=timeout)
        ws.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        while True:
            payload = json.loads(ws.recv())
            if payload.get("id") == message_id:
                ws.close()
                return payload
    except Exception:
        return None


def _collect_dom_script(limit: int) -> str:
    return f"""
(() => {{
  const limit = {max(1, min(150, int(limit)))};
  const visible = (el) => {{
    const r = el.getBoundingClientRect();
    const s = window.getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  }};
  const cssPath = (el) => {{
    if (el.id) return '#' + CSS.escape(el.id);
    const name = el.getAttribute('name');
    if (name) return el.tagName.toLowerCase() + '[name="' + CSS.escape(name) + '"]';
    const aria = el.getAttribute('aria-label');
    if (aria) return el.tagName.toLowerCase() + '[aria-label="' + CSS.escape(aria) + '"]';
    let path = el.tagName.toLowerCase();
    let parent = el.parentElement;
    if (!parent) return path;
    const siblings = Array.from(parent.children).filter(x => x.tagName === el.tagName);
    if (siblings.length > 1) path += ':nth-of-type(' + (siblings.indexOf(el) + 1) + ')';
    return path;
  }};
  const controls = Array.from(document.querySelectorAll('a,button,input,textarea,select,summary,[role],[aria-label],[placeholder],[contenteditable="true"]'))
    .filter(visible)
    .slice(0, limit)
    .map((el, i) => {{
      const r = el.getBoundingClientRect();
      const text = (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('title') || '').replace(/\\s+/g, ' ').trim();
      return {{
        index: i,
        tag: el.tagName.toLowerCase(),
        role: el.getAttribute('role') || '',
        type: el.getAttribute('type') || '',
        text: text.slice(0, 100),
        name: el.getAttribute('name') || '',
        id: el.id || '',
        selector: cssPath(el),
        disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
        rect: {{x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}}
      }};
    }});
  const bodyText = (document.body ? document.body.innerText : '').replace(/\\s+/g, ' ').trim();
  const iframeText = Array.from(document.querySelectorAll('iframe')).map(f => [f.src, f.title, f.name].join(' ')).join(' ');
  const combined = (bodyText + ' ' + iframeText).toLowerCase();
  const detections = [];
  const hasPassword = !!document.querySelector('input[type="password"]');
  const loginLanguage = /\\b(password|username|one-time code|verification code)\\b/.test(combined) && /\\b(sign in|log in|login|account)\\b/.test(combined);
  if (hasPassword || loginLanguage) detections.push('login');
  if (/\\b(captcha|recaptcha|hcaptcha|cloudflare|verify you are human|not a robot)\\b/.test(combined)) detections.push('captcha');
  if (/\\b(payment|card number|checkout|billing)\\b/.test(combined)) detections.push('payment');
  return {{
    title: document.title || '',
    url: location.href,
    detections,
    page_text: bodyText.slice(0, 1200),
    elements: controls
  }};
}})()
"""


def _dom_click_script(selector: str) -> str:
    return f"""
(() => {{
  const el = document.querySelector({json.dumps(selector)});
  if (!el) return {{ok:false, error:'selector not found'}};
  el.scrollIntoView({{block:'center', inline:'center'}});
  el.click();
  return {{ok:true}};
}})()
"""


def _dom_type_script(selector: str, text: str) -> str:
    return f"""
(() => {{
  const el = document.querySelector({json.dumps(selector)});
  if (!el) return {{ok:false, error:'selector not found'}};
  el.scrollIntoView({{block:'center', inline:'center'}});
  el.focus();
  const text = {json.dumps(text)};
  if ('value' in el) {{
    const setter = Object.getOwnPropertyDescriptor(el.__proto__, 'value')?.set;
    if (setter) setter.call(el, text); else el.value = text;
    el.dispatchEvent(new Event('input', {{bubbles:true}}));
    el.dispatchEvent(new Event('change', {{bubbles:true}}));
  }} else {{
    el.textContent = text;
    el.dispatchEvent(new InputEvent('input', {{bubbles:true, inputType:'insertText', data:text}}));
  }}
  return {{ok:true}};
}})()
"""


def _dom_select_script(selector: str, value: str) -> str:
    return f"""
(() => {{
  const el = document.querySelector({json.dumps(selector)});
  if (!el) return {{ok:false, error:'selector not found'}};
  el.value = {json.dumps(value)};
  el.dispatchEvent(new Event('input', {{bubbles:true}}));
  el.dispatchEvent(new Event('change', {{bubbles:true}}));
  return {{ok:true}};
}})()
"""


def _chrome_path() -> str:
    configured = str(config_value("browser_chrome_path", "") or "").strip()
    candidates = [
        configured,
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for item in candidates:
        if item and Path(item).exists():
            return item
    return ""


def _safe_key(key: str) -> str:
    aliases = {"enter": "Enter", "tab": "Tab", "escape": "Escape", "esc": "Escape", "backspace": "Backspace"}
    return aliases.get(key.strip().lower(), "")


def _int(value: Any, default: int) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return default

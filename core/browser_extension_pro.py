"""Pro browser-control layer built on the local Chrome/Edge extension."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import browser_extension_bridge, notification_center
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "browser_extension_pro.sqlite3"
_LOCK = threading.Lock()


def init_db(path: Path | None = None) -> None:
    ensure_runtime_dirs()
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=10) as conn:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS browser_network_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                browser TEXT NOT NULL,
                url TEXT NOT NULL,
                event_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS browser_page_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                url TEXT NOT NULL,
                summary TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def ingest_network_event(payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    safe = _safe_payload(payload)
    summary = f"{safe.get('event_type') or 'network'} on {safe.get('url') or 'page'}: {safe.get('error') or safe.get('status') or 'event'}"
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO browser_network_events(timestamp, browser, url, event_type, summary, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
            (_now(), str(safe.get("browser") or "extension")[:80], str(safe.get("url") or "")[:2000], str(safe.get("event_type") or "network")[:80], summary[:1000], _json_dumps(safe)),
        )
        row = conn.execute("SELECT * FROM browser_network_events WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    if "error" in str(safe.get("event_type") or "").lower() or safe.get("error"):
        notification_center.add(source="browser_extension_pro", category="browser", severity=3, title="Browser network issue", message=summary, metadata=safe)
    return _network_row(row)


def ingest_page_change(payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    safe = _safe_payload(payload)
    summary = str(safe.get("summary") or "Browser page changed.")
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO browser_page_changes(timestamp, url, summary, metadata_json) VALUES (?, ?, ?, ?)",
            (_now(), str(safe.get("url") or "")[:2000], summary[:1000], _json_dumps(safe)),
        )
        row = conn.execute("SELECT * FROM browser_page_changes WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _change_row(row)


def guidance(question: str = "what should I click") -> dict[str, Any]:
    insight = browser_extension_bridge.latest_page_insight()
    if not insight.get("ok"):
        return {"ok": False, "summary": insight.get("summary", "No browser context."), "suggestions": []}
    page = insight.get("page") or {}
    buttons = page.get("buttons") or []
    forms = page.get("forms") or []
    errors = insight.get("console_errors") or []
    lowered = str(question or "").lower()
    suggestions: list[dict[str, Any]] = []
    if "error" in lowered or "debug" in lowered:
        for error in errors[:5]:
            suggestions.append({"kind": "console_error", "label": error.get("level", "error"), "selector": "", "reason": error.get("message", "")})
    if "form" in lowered or "fill" in lowered:
        for form in forms[:5]:
            suggestions.append({"kind": "form", "label": form.get("name") or "form", "selector": "", "reason": f"{len(form.get('fields') or [])} field(s), sensitive fields skipped."})
    for button in buttons[:8]:
        label = button.get("text") or button.get("aria") or "button"
        suggestions.append({"kind": "button", "label": label, "selector": button.get("selector", ""), "reason": f"Visible page control: {label}"})
    return {
        "ok": True,
        "question": question,
        "page": {"title": page.get("title"), "url": page.get("url")},
        "suggestions": suggestions[:12],
        "summary": f"{len(suggestions[:12])} browser guidance suggestion(s) ready.",
    }


def safe_fill(selector: str, value: str, *, reason: str = "") -> dict[str, Any]:
    action = browser_extension_bridge.queue_action("fill", selector=selector, value=value, reason=reason or "safe browser fill requested")
    if not action.get("ok", True):
        return action
    return action | {"summary": "Safe browser fill queued; extension will refuse password/secret fields."}


def watch_page() -> dict[str, Any]:
    action = browser_extension_bridge.queue_action("watch", reason="watch this page for changes")
    return action | {"summary": action.get("summary") or "Page watch queued for the browser extension."}


def status(limit: int = 8) -> dict[str, Any]:
    bridge = browser_extension_bridge.status(limit=limit)
    return {
        "bridge": bridge,
        "network": recent_network(limit=limit),
        "page_changes": recent_page_changes(limit=limit),
        "guidance": guidance(),
        "summary": "Browser Pro is ready when the Chrome/Edge extension is enabled.",
    }


def recent_network(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM browser_network_events ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_network_row(row) for row in rows]


def recent_page_changes(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM browser_page_changes ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_change_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM browser_network_events")
        conn.execute("DELETE FROM browser_page_changes")


def _safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in (payload or {}).items():
        name = str(key or "").strip()[:80]
        if not name:
            continue
        if any(term in name.lower() for term in ("password", "token", "secret", "cookie", "authorization")):
            safe[name] = "[redacted]"
        elif isinstance(value, (str, int, float, bool)) or value is None:
            safe[name] = browser_extension_bridge.redact_text(str(value))[:4000] if isinstance(value, str) else value
        else:
            safe[name] = browser_extension_bridge.redact_text(json.dumps(value, default=str))[:2000]
    return safe


def _network_row(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": int(row["id"]), "timestamp": str(row["timestamp"]), "browser": str(row["browser"]), "url": str(row["url"]), "event_type": str(row["event_type"]), "summary": str(row["summary"]), "metadata": _json_loads(row["metadata_json"], {})}


def _change_row(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": int(row["id"]), "timestamp": str(row["timestamp"]), "url": str(row["url"]), "summary": str(row["summary"]), "metadata": _json_loads(row["metadata_json"], {})}


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

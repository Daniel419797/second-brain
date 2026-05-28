"""Local bridge for the Friday Chrome/Edge extension."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import app_state_memory
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "browser_extension.sqlite3"
_LOCK = threading.Lock()

SECRET_RE = re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|authorization|bearer|cookie|session|credential)")
TOKEN_VALUE_RE = re.compile(r"(?i)\b([a-z0-9_-]{24,}\.[a-z0-9_-]{12,}\.[a-z0-9_-]{12,}|sk-[a-z0-9_-]{16,}|ghp_[a-z0-9_]{20,})\b")


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
            CREATE TABLE IF NOT EXISTS browser_contexts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                browser TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                selected_text TEXT NOT NULL,
                headings_json TEXT NOT NULL,
                buttons_json TEXT NOT NULL,
                forms_json TEXT NOT NULL,
                redactions INTEGER NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS browser_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                url TEXT NOT NULL,
                action TEXT NOT NULL,
                selector TEXT NOT NULL,
                value TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT NOT NULL,
                result TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_browser_contexts_time ON browser_contexts(timestamp)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS browser_console_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                browser TEXT NOT NULL,
                url TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                source TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def ingest_context(payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    sanitized = _sanitize_context(payload)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO browser_contexts(timestamp, browser, url, title, selected_text, headings_json, buttons_json, forms_json, redactions, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _now(),
                sanitized["browser"],
                sanitized["url"],
                sanitized["title"],
                sanitized["selected_text"],
                _json_dumps(sanitized["headings"]),
                _json_dumps(sanitized["buttons"]),
                _json_dumps(sanitized["forms"]),
                int(sanitized["redactions"]),
                _json_dumps(sanitized["metadata"]),
            ),
        )
        row = conn.execute("SELECT * FROM browser_contexts WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    if sanitized["buttons"]:
        try:
            app_state_memory.record_pattern(
                "browser",
                sanitized["buttons"][0].get("text") or "button",
                "observe",
                "context_seen",
                selector=sanitized["buttons"][0].get("selector", ""),
                context=sanitized["title"],
                metadata={"url": sanitized["url"], "source": "browser_extension"},
            )
        except Exception:
            pass
    return _context_row(row)


def ingest_console(payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    browser = _clean(payload.get("browser") or "extension")[:80]
    url = _redact_url(str(payload.get("url") or ""))[:2000]
    level = _clean(payload.get("level") or "log").lower()[:40]
    message, redactions = _redact_text(str(payload.get("message") or ""))
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO browser_console_events(timestamp, browser, url, level, message, source, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (_now(), browser, url, level, message[:3000], _clean(payload.get("source") or "console")[:200], _json_dumps({"redactions": redactions})),
        )
        row = conn.execute("SELECT * FROM browser_console_events WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _console_row(row)


def queue_action(action: str, *, url: str = "", selector: str = "", value: str = "", reason: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    normalized = _clean(action).lower()
    if normalized not in {"click", "fill", "select", "focus", "scroll", "summarize", "watch", "highlight", "explain", "find"}:
        return {"ok": False, "summary": "Unsupported browser action."}
    if normalized in {"fill", "select"} and _looks_sensitive(selector + " " + value):
        return {"ok": False, "summary": "Refused to queue sensitive browser form action."}
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO browser_actions(timestamp, updated_at, url, action, selector, value, status, reason, result, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, '', ?)
            """,
            (now, now, _redact_url(url)[:2000], normalized, _clean(selector)[:500], _redact_text(value)[0][:2000], _clean(reason)[:1000], _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM browser_actions WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _action_row(row)


def pending_actions(url: str = "", limit: int = 5) -> list[dict[str, Any]]:
    init_db()
    sanitized_url = _redact_url(str(url or ""))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        if sanitized_url:
            rows = conn.execute(
                "SELECT * FROM browser_actions WHERE status='queued' AND (url='' OR url=? OR ? LIKE url || '%') ORDER BY id ASC LIMIT ?",
                (sanitized_url, sanitized_url, max(1, min(20, int(limit or 5)))),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM browser_actions WHERE status='queued' ORDER BY id ASC LIMIT ?", (max(1, min(20, int(limit or 5))),)).fetchall()
    return [_action_row(row) for row in rows]


def complete_action(action_id: int, *, status: str = "done", result: str = "") -> dict[str, Any]:
    init_db()
    normalized = _clean(status).lower() or "done"
    if normalized not in {"done", "failed", "skipped", "blocked"}:
        normalized = "done"
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            "UPDATE browser_actions SET status=?, result=?, updated_at=? WHERE id=?",
            (normalized, _clean(result)[:2000], _now(), int(action_id)),
        )
        row = conn.execute("SELECT * FROM browser_actions WHERE id=?", (int(action_id),)).fetchone()
    return _action_row(row) if row else {"ok": False, "summary": "Browser action not found."}


def latest_page_insight() -> dict[str, Any]:
    contexts = recent_contexts(limit=1)
    console = recent_console(limit=10)
    if not contexts:
        return {"ok": False, "summary": "No browser extension page context has been received yet."}
    context = contexts[0]
    errors = [item for item in console if item.get("url") == context.get("url") and str(item.get("level")).lower() in {"error", "warn", "warning"}]
    forms = context.get("forms") or []
    buttons = context.get("buttons") or []
    headings = context.get("headings") or []
    links = context.get("links") or []
    inputs = context.get("inputs") or []
    return {
        "ok": True,
        "page": context,
        "console_errors": errors,
        "summary": f"{context.get('title') or context.get('url')}: {len(headings)} heading(s), {len(buttons)} button(s), {len(links)} link(s), {len(inputs)} input(s), {len(forms)} form(s), {len(errors)} console warning/error(s).",
    }


def status(limit: int = 6) -> dict[str, Any]:
    contexts = recent_contexts(limit=limit)
    console = recent_console(limit=limit)
    actions = recent_actions(limit=limit)
    return {
        "enabled": True,
        "contexts": contexts,
        "console": console,
        "actions": actions,
        "summary": f"{len(contexts)} recent browser context(s), {len(console)} console event(s), {len([item for item in actions if item['status'] == 'queued'])} queued action(s).",
        "extension_path": "apps/browser-extension",
    }


def recent_contexts(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM browser_contexts ORDER BY id DESC LIMIT ?", (max(1, min(200, int(limit or 20))),)).fetchall()
    return [_context_row(row) for row in rows]


def recent_console(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM browser_console_events ORDER BY id DESC LIMIT ?", (max(1, min(200, int(limit or 20))),)).fetchall()
    return [_console_row(row) for row in rows]


def recent_actions(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM browser_actions ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_action_row(row) for row in rows]


def redact_text(text: str) -> str:
    return _redact_text(text)[0]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM browser_contexts")
        conn.execute("DELETE FROM browser_console_events")
        conn.execute("DELETE FROM browser_actions")


def _sanitize_context(payload: dict[str, Any]) -> dict[str, Any]:
    redactions = 0
    selected_text, count = _redact_text(str(payload.get("selected_text") or payload.get("selectedText") or ""))
    redactions += count
    headings = [_redacted_item(item, ["text"]) for item in _list(payload.get("headings"))[:60]]
    buttons = [_redacted_item(item, ["text", "aria", "selector"]) for item in _list(payload.get("buttons"))[:120]]
    links = [_redacted_item(item, ["text", "href", "selector"]) for item in _list(payload.get("links"))[:120]]
    inputs = [_redacted_item(item, ["name", "type", "label", "selector"]) for item in _list(payload.get("inputs"))[:120]]
    landmarks = [_redacted_item(item, ["role", "label", "selector"]) for item in _list(payload.get("landmarks"))[:80]]
    forms = []
    for form in _list(payload.get("forms"))[:40]:
        fields = []
        for field in _list(form.get("fields") if isinstance(form, dict) else None):
            name = _clean(field.get("name") if isinstance(field, dict) else "")
            field_type = _clean(field.get("type") if isinstance(field, dict) else "text").lower()
            sensitive = field_type in {"password", "hidden"} or bool(SECRET_RE.search(name))
            fields.append({"name": "[redacted]" if sensitive else name[:120], "type": field_type, "sensitive": sensitive})
            if sensitive:
                redactions += 1
        forms.append({"name": _clean(form.get("name") if isinstance(form, dict) else "")[:120], "fields": fields})
    title, count = _redact_text(str(payload.get("title") or ""))
    redactions += count
    return {
        "browser": _clean(payload.get("browser") or "extension")[:80],
        "url": _redact_url(str(payload.get("url") or ""))[:2000],
        "title": title[:300],
        "selected_text": selected_text[:2000],
        "headings": headings,
        "buttons": buttons,
        "links": links,
        "inputs": inputs,
        "landmarks": landmarks,
        "forms": forms,
        "redactions": redactions,
        "metadata": {
            "source": "browser_extension",
            "raw_keys": sorted(str(key) for key in payload.keys()),
            "links": links,
            "inputs": inputs,
            "landmarks": landmarks,
            "performance": _safe_mapping(payload.get("performance")),
        },
    }


def _redacted_item(item: Any, keys: list[str]) -> dict[str, Any]:
    data = item if isinstance(item, dict) else {"text": str(item)}
    out: dict[str, Any] = {}
    for key in keys:
        value, _ = _redact_text(str(data.get(key) or ""))
        out[key] = value[:300]
    return out


def _redact_text(text: str) -> tuple[str, int]:
    redactions = 0
    output = str(text or "")
    output, count = TOKEN_VALUE_RE.subn("[redacted-token]", output)
    redactions += count
    if SECRET_RE.search(output):
        output = SECRET_RE.sub("[redacted-key]", output)
        redactions += 1
    return output, redactions


def _redact_url(url: str) -> str:
    text = str(url or "")
    if "?" not in text:
        return _redact_text(text)[0]
    base, _query = text.split("?", 1)
    return _redact_text(base)[0] + "?[redacted-query]"


def _context_row(row: sqlite3.Row) -> dict[str, Any]:
    metadata = _json_loads(row["metadata_json"], {})
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "browser": str(row["browser"]),
        "url": str(row["url"]),
        "title": str(row["title"]),
        "selected_text": str(row["selected_text"]),
        "headings": _json_loads(row["headings_json"], []),
        "buttons": _json_loads(row["buttons_json"], []),
        "forms": _json_loads(row["forms_json"], []),
        "links": metadata.get("links") or [],
        "inputs": metadata.get("inputs") or [],
        "landmarks": metadata.get("landmarks") or [],
        "redactions": int(row["redactions"]),
        "metadata": metadata,
    }


def _console_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "browser": str(row["browser"]),
        "url": str(row["url"]),
        "level": str(row["level"]),
        "message": str(row["message"]),
        "source": str(row["source"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _action_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "updated_at": str(row["updated_at"]),
        "url": str(row["url"]),
        "action": str(row["action"]),
        "selector": str(row["selector"]),
        "value": str(row["value"]),
        "status": str(row["status"]),
        "reason": str(row["reason"]),
        "result": str(row["result"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, Any] = {}
    for key, item in value.items():
        cleaned_key = _clean(key)[:80]
        if not cleaned_key:
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            output[cleaned_key] = _redact_text(str(item))[0][:300] if isinstance(item, str) else item
    return output


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _looks_sensitive(value: str) -> bool:
    return bool(SECRET_RE.search(str(value or "")))


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=True)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return default

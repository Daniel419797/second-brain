"""Quiet coding coach that watches workspace signals and suggests useful next steps."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import browser_extension_bridge, contextual_workspace, notification_center, project_watchdog, test_build_monitor
from core.config import DATA_DIR, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "live_workspace_coach.sqlite3"
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
            CREATE TABLE IF NOT EXISTS coach_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                root TEXT NOT NULL,
                severity INTEGER NOT NULL,
                signal TEXT NOT NULL,
                suggestion TEXT NOT NULL,
                likely_file TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                status TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def observe(root: str | Path = "", *, log_text: str = "", current_file: str = "", run_tests: bool = False, notify: bool = True) -> dict[str, Any]:
    init_db()
    project_root = _root(root)
    context = _safe(lambda: contextual_workspace.prepare_context(str(project_root)), {})
    watchdog = _safe(lambda: project_watchdog.run_once(str(project_root), notify=False), {})
    browser = _safe(browser_extension_bridge.latest_page_insight, {})
    monitor = _safe(lambda: test_build_monitor.run_check(str(project_root), "", create_proof=False) if run_tests else test_build_monitor.status(), {})
    signal, severity, likely_file, evidence = _diagnose(log_text, current_file, context, watchdog, browser, monitor)
    suggestion = _suggest(signal, likely_file, evidence)
    event = _record(project_root, severity, signal, suggestion, likely_file, evidence, {"context": context, "watchdog": watchdog, "browser": browser, "monitor": monitor})
    if notify and severity >= 4:
        notification_center.add(source="live_workspace_coach", category="workspace", severity=severity, title="Workspace coach suggestion", message=suggestion, metadata={"event": event})
    return {"event": event, "context": context, "watchdog": watchdog, "browser": browser, "monitor": monitor, "summary": suggestion}


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM coach_events ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    events = recent(limit=8)
    latest = events[0] if events else None
    return {"latest": latest, "recent": events, "summary": latest["suggestion"] if latest else "Live workspace coach is ready."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM coach_events")


def _diagnose(log_text: str, current_file: str, context: dict[str, Any], watchdog: dict[str, Any], browser: dict[str, Any], monitor: dict[str, Any]) -> tuple[str, int, str, list[str]]:
    evidence: list[str] = []
    text = _clean(log_text)
    if text:
        evidence.append(text[:500])
    errors = browser.get("console_errors") or []
    if errors:
        evidence.append(str(errors[0].get("message") or "browser console error"))
        return "browser_console_error", 4, _likely_file(text, current_file), evidence
    if re.search(r"(traceback|error|failed|exception|cannot find module|syntaxerror)", text, re.IGNORECASE):
        return "terminal_error", 4, _likely_file(text, current_file), evidence
    if "todo" in json.dumps(watchdog, default=str).lower():
        return "todo_growth", 2, _likely_file(text, current_file), evidence or ["Project watchdog found TODOs."]
    if monitor and any(term in json.dumps(monitor, default=str).lower() for term in ("failed", "crash", "error")):
        return "test_or_build_failure", 4, _likely_file(text, current_file), evidence or ["Test/build monitor reported a failure."]
    return "workspace_ok", 1, _clean(current_file), evidence or ["No urgent workspace issue detected."]


def _suggest(signal: str, likely_file: str, evidence: list[str]) -> str:
    if signal in {"terminal_error", "test_or_build_failure"}:
        suffix = f" in {likely_file}" if likely_file else ""
        return f"The current failure is probably{suffix}. Want me to prepare a fix report?"
    if signal == "browser_console_error":
        suffix = f" and check {likely_file}" if likely_file else ""
        return f"The browser console has an error. I can inspect the page context{suffix}."
    if signal == "todo_growth":
        return "I noticed TODO-style project debt. I can turn it into a small task list."
    return "Workspace looks calm. I will stay quiet unless something important changes."


def _record(root: Path, severity: int, signal: str, suggestion: str, likely_file: str, evidence: list[str], metadata: dict[str, Any]) -> dict[str, Any]:
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO coach_events(timestamp, root, severity, signal, suggestion, likely_file, evidence_json, status, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)",
            (_now(), str(root), int(severity), signal, suggestion, likely_file, _json_dumps(evidence), _json_dumps(metadata)),
        )
        row = conn.execute("SELECT * FROM coach_events WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def _likely_file(text: str, current_file: str) -> str:
    if current_file:
        return _clean(current_file)
    match = re.search(r"([A-Za-z]:)?[\\/\w.-]+\.(?:py|js|jsx|ts|tsx|json|css|html)", text)
    return match.group(0) if match else ""


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": int(row["id"]), "timestamp": str(row["timestamp"]), "root": str(row["root"]), "severity": int(row["severity"]), "signal": str(row["signal"]), "suggestion": str(row["suggestion"]), "likely_file": str(row["likely_file"]), "evidence": _json_loads(row["evidence_json"], []), "status": str(row["status"]), "metadata": _json_loads(row["metadata_json"], {})}


def _root(value: str | Path) -> Path:
    try:
        return resolve_coding_root(value)
    except Exception:
        return resolve_coding_root()


def _safe(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

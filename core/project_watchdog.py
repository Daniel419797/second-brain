"""Continuous project watchdog for tests, docs, TODOs, dependencies, and secrets."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable

from core import capability_center, codebase_standards, notification_center, project_autopilot
from core.config import DATA_DIR, config_value, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "project_watchdog.sqlite3"
_LOCK = threading.Lock()
_STOP = threading.Event()
_THREAD: threading.Thread | None = None
_LAST_STATUS = "stopped"

LogFn = Callable[[str, str], None]


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
            CREATE TABLE IF NOT EXISTS project_watchdog_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                root TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )


def start_service(log_fn: LogFn | None = None) -> bool:
    global _THREAD, _LAST_STATUS
    if not bool(config_value("project_watchdog_enabled", True)):
        _LAST_STATUS = "disabled"
        return False
    with _LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return True
        _STOP.clear()
        _THREAD = threading.Thread(target=_loop, args=(log_fn,), name="FridayProjectWatchdog", daemon=True)
        _THREAD.start()
        _LAST_STATUS = "running"
        return True


def stop_service(timeout: float = 2.0) -> None:
    global _LAST_STATUS
    _STOP.set()
    thread = _THREAD
    if thread is not None:
        thread.join(timeout=timeout)
    _LAST_STATUS = "stopped"


def status() -> dict[str, Any]:
    thread = _THREAD
    return {
        "enabled": bool(config_value("project_watchdog_enabled", True)),
        "running": bool(thread and thread.is_alive() and not _STOP.is_set()),
        "status": _LAST_STATUS,
        "latest": recent_reports(limit=1)[0] if recent_reports(limit=1) else None,
    }


def run_once(root: str = "", *, notify: bool = True) -> dict[str, Any]:
    base = resolve_coding_root(root)
    autopilot = project_autopilot.inspect_project(base, run_tests=bool(config_value("project_watchdog_run_tests", False)), notify=notify)
    secrets = capability_center.project_secret_scan(str(base))
    standards = codebase_standards.scan(str(base), max_files=int(config_value("codebase_standards_watchdog_max_files", 120)))
    issues = list(autopilot.get("issues") or [])
    secret_findings = secrets.get("findings") or secrets.get("matches") or []
    if secret_findings:
        issues.append({"kind": "secrets", "severity": 5, "title": "Potential secrets found", "evidence": secret_findings[:10]})
    standards_findings = [item for item in standards.get("findings") or [] if int(item.get("severity") or 0) >= 3]
    if standards_findings:
        issues.append(
            {
                "kind": "codebase_standards",
                "severity": max(int(item.get("severity") or 0) for item in standards_findings),
                "title": "Codebase standards guard found issues",
                "evidence": standards_findings[:10],
                "recommendation": "Fix findings in priority order: security, performance, maintainability, reliability, portability.",
            }
        )
    status_value = "attention" if issues else "ok"
    summary = f"Project watchdog found {len(issues)} issue(s) under {base.name}."
    report = _persist(base, status_value, summary, {"autopilot": autopilot, "secrets": secrets, "standards": standards, "issues": issues})
    if notify and issues:
        notification_center.add(
            source="project_watchdog",
            category="workspace",
            severity=5 if any(int(item.get("severity") or 0) >= 5 for item in issues) else 3,
            title="Project watchdog found work",
            message=summary,
            dedupe_key=f"project-watchdog:{base}",
            metadata={"report_id": report["id"], "issues": issues[:10]},
        )
    return report | {"issues": issues, "autopilot": autopilot, "secrets": secrets, "standards": standards}


def recent_reports(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM project_watchdog_reports ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit))),)).fetchall()
    return [_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM project_watchdog_reports")


def _loop(log_fn: LogFn | None) -> None:
    global _LAST_STATUS
    interval = max(60.0, float(config_value("project_watchdog_interval_seconds", 300.0)))
    while not _STOP.is_set():
        try:
            _LAST_STATUS = "checking"
            result = run_once(notify=True)
            if log_fn and result.get("issues"):
                log_fn("INFO", f"[PROJECT] {result['summary']}")
            _LAST_STATUS = "running"
        except Exception as exc:
            _LAST_STATUS = f"error: {exc.__class__.__name__}"
            if log_fn:
                log_fn("WARNING", f"[PROJECT] watchdog failed ({exc})")
        _STOP.wait(interval)


def _persist(base: Path, status_value: str, summary: str, payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO project_watchdog_reports(timestamp, root, status, summary, payload_json) VALUES (?, ?, ?, ?, ?)",
            (_now(), str(base), status_value, summary, _json_dumps(payload)),
        )
        row = conn.execute("SELECT * FROM project_watchdog_reports WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    payload = _json_loads(row["payload_json"], {})
    return {"id": int(row["id"]), "timestamp": str(row["timestamp"]), "root": str(row["root"]), "status": str(row["status"]), "summary": str(row["summary"]), "payload": payload, "issues": payload.get("issues", [])}


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

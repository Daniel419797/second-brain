"""Error radar for logs, browser console events, watchdogs, and stuck work."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import browser_extension_bridge, project_watchdog, self_debugger, task_queue
from core.config import DATA_DIR, LOG_DIR, ROOT_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "error_radar.sqlite3"
_LOCK = threading.Lock()
ERROR_RE = re.compile(r"(?i)\b(error|exception|traceback|failed|fatal|crash|unhandled|timeout)\b")


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
            CREATE TABLE IF NOT EXISTS error_radar_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                root TEXT NOT NULL,
                severity INTEGER NOT NULL,
                status TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_error_radar_status ON error_radar_events(status, severity, timestamp)")


def watch(root: str | Path = "", sources: list[str] | None = None) -> dict[str, Any]:
    init_db()
    project_root = _safe_root(root)
    selected = {str(source).strip().lower() for source in (sources or []) if str(source).strip()} or {"logs", "browser", "tasks", "watchdog"}
    created: list[dict[str, Any]] = []
    if "logs" in selected:
        created.extend(_scan_logs(project_root))
    if "browser" in selected:
        created.extend(_scan_browser(project_root))
    if "tasks" in selected:
        created.extend(_scan_tasks(project_root))
    if "watchdog" in selected:
        created.extend(_scan_watchdog(project_root))
    for event in created:
        if int(event.get("severity") or 0) >= 4:
            try:
                self_debugger.record_failure("error_radar", event["summary"], metadata={"event_id": event["id"], "source": event["source"]})
            except Exception:
                pass
    return {"created": len(created), "events": created, "summary": f"Error radar recorded {len(created)} event(s)."}


def recent_events(limit: int = 50, status: str = "") -> list[dict[str, Any]]:
    init_db()
    where = ""
    params: list[Any] = []
    if status:
        where = "WHERE status=?"
        params.append(_clean(status).lower())
    params.append(max(1, min(300, int(limit or 50))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM error_radar_events {where} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT status, COUNT(*) FROM error_radar_events GROUP BY status").fetchall()
        source_rows = conn.execute("SELECT source, COUNT(*) FROM error_radar_events GROUP BY source").fetchall()
    counts = {str(status): int(count) for status, count in rows}
    by_source = {str(source): int(count) for source, count in source_rows}
    recent = recent_events(limit=8)
    return {"counts": counts, "by_source": by_source, "recent": recent, "summary": f"{sum(counts.values())} radar event(s) recorded."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM error_radar_events")


def _scan_logs(root: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in sorted(LOG_DIR.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True)[:3]:
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-120:]
        except Exception:
            continue
        matches = [line for line in lines if ERROR_RE.search(line)]
        if matches:
            events.append(_store("logs", root, 3, "Log errors detected", matches[-1][:500], {"path": str(path), "matches": matches[-10:]}))
    return events


def _scan_browser(root: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        console = browser_extension_bridge.recent_console(limit=30)
    except Exception:
        return events
    for item in console:
        level = str(item.get("level") or "").lower()
        message = str(item.get("message") or "")
        if level in {"error", "warn"} or ERROR_RE.search(message):
            events.append(_store("browser_console", root, 4 if level == "error" else 3, f"Browser {level or 'console'} event", message[:600], item))
    return events


def _scan_tasks(root: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for task in task_queue.list_tasks(limit=80):
        if task.get("status") == "failed":
            events.append(_store("tasks", root, 4, "Task failed", f"Task #{task['id']}: {task['title']}", {"task": task}))
        elif task.get("status") == "blocked":
            events.append(_store("tasks", root, 3, "Task blocked", f"Task #{task['id']}: {task['title']}", {"task": task}))
    return events[:20]


def _scan_watchdog(root: Path) -> list[dict[str, Any]]:
    try:
        reports = project_watchdog.recent_reports(limit=5, root=root)
    except Exception:
        return []
    events: list[dict[str, Any]] = []
    for report in reports:
        if str(report.get("status") or "").lower() in {"failed", "needs_review"} or report.get("findings"):
            events.append(_store("project_watchdog", root, 3, "Project watchdog finding", report.get("summary", "Project watchdog issue."), report))
    return events


def _store(source: str, root: Path, severity: int, title: str, summary: str, payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO error_radar_events(timestamp, source, root, severity, status, title, summary, payload_json)
            VALUES (?, ?, ?, ?, 'open', ?, ?, ?)
            """,
            (_now(), source, str(root), max(1, min(5, int(severity))), _clean(title)[:300], _clean(summary)[:2000], _json_dumps(payload)),
        )
        row = conn.execute("SELECT * FROM error_radar_events WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "source": str(row["source"]),
        "root": str(row["root"]),
        "severity": int(row["severity"]),
        "status": str(row["status"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "payload": _json_loads(row["payload_json"], {}),
    }


def _safe_root(value: str | Path) -> Path:
    text = _clean(str(value or ""))
    if not text:
        return ROOT_DIR
    try:
        return Path(text).expanduser().resolve()
    except Exception:
        return ROOT_DIR


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


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

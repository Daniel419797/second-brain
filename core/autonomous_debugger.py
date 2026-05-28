"""Autonomous debugger sessions for logs, tests, stack traces, and console errors."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import subprocess
import threading
from pathlib import Path
from typing import Any

from core import browser_extension_bridge, error_radar, self_debugger
from core import command_runner
from core.config import DATA_DIR, ROOT_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "autonomous_debugger.sqlite3"
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
            CREATE TABLE IF NOT EXISTS debugger_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                probable_cause TEXT NOT NULL,
                proposed_fix TEXT NOT NULL,
                test_plan TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def analyze_text(text: str, *, source: str = "manual", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    evidence = _extract_evidence(text)
    analysis = _analyze(text, evidence)
    report = self_debugger.record_failure(source, analysis["summary"], metadata={"evidence": evidence, **(metadata or {})})
    return _store(source, "open", analysis, evidence, {"self_debug_report_id": report.get("id"), **(metadata or {})})


def analyze_file(path: str | Path) -> dict[str, Any]:
    file_path = _safe_path(path)
    if not file_path.exists() or not file_path.is_file():
        return {"ok": False, "summary": "Log file not found."}
    text = file_path.read_text(encoding="utf-8", errors="ignore")[-20000:]
    return analyze_text(text, source=str(file_path), metadata={"path": str(file_path)})


def run_check(command: str = "", *, cwd: str | Path = "", timeout: int | None = None) -> dict[str, Any]:
    root = _safe_path(cwd or ROOT_DIR)
    cmd = command or str(config_value("workspace_test_watch_command", "python -m pytest -q"))
    limit = int(timeout or config_value("workspace_test_watch_timeout_seconds", 60))
    try:
        proc = command_runner.run(cmd, cwd=root, timeout=max(5, limit))
        text = (proc.stdout or "") + "\n" + (proc.stderr or "")
        session = analyze_text(text, source="test_command", metadata={"command": cmd, "cwd": str(root), "returncode": proc.returncode})
        session["returncode"] = proc.returncode
        if proc.returncode == 0:
            session["status"] = "passed"
            session["summary"] = "Debugger check passed; no failure output detected."
        return session
    except subprocess.TimeoutExpired as exc:
        return analyze_text(str(exc), source="test_command_timeout", metadata={"command": cmd, "cwd": str(root), "timeout": limit})
    except command_runner.CommandRejected as exc:
        return analyze_text(str(exc), source="test_command_rejected", metadata={"command": cmd, "cwd": str(root), "timeout": limit})


def watch(root: str | Path = "") -> dict[str, Any]:
    radar = error_radar.watch(str(root or ""))
    console = browser_extension_bridge.recent_console(limit=8)
    evidence = [item.get("summary") or item.get("message") or "" for item in radar.get("events", [])]
    evidence.extend(item.get("message", "") for item in console if str(item.get("level")).lower() in {"error", "warn", "warning"})
    if not evidence:
        return _store("watch", "clean", {"summary": "No debugger issues detected.", "probable_cause": "none", "proposed_fix": "No fix needed.", "test_plan": "Keep watching logs and console events."}, [], {"root": str(root or "")})
    return analyze_text("\n".join(evidence), source="watch", metadata={"root": str(root or ""), "radar": radar})


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM debugger_sessions ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    items = recent(limit=8)
    open_items = [item for item in items if item["status"] == "open"]
    return {"open_count": len(open_items), "recent": items, "summary": f"{len(open_items)} debugger issue(s) open."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM debugger_sessions")


def _store(source: str, status: str, analysis: dict[str, str], evidence: list[str], metadata: dict[str, Any]) -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO debugger_sessions(timestamp, source, status, summary, probable_cause, proposed_fix, test_plan, evidence_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _now(),
                _clean(source)[:300],
                _clean(status) or "open",
                _clean(analysis.get("summary"))[:2000],
                _clean(analysis.get("probable_cause")),
                _clean(analysis.get("proposed_fix")),
                _clean(analysis.get("test_plan")),
                _json_dumps(evidence[:30]),
                _json_dumps(metadata),
            ),
        )
        row = conn.execute("SELECT * FROM debugger_sessions WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    item = _row(row)
    item["ok"] = True
    return item


def _extract_evidence(text: str) -> list[str]:
    lines = []
    for line in str(text or "").splitlines():
        cleaned = _clean(line)
        if not cleaned:
            continue
        low = cleaned.lower()
        if any(term in low for term in ("error", "failed", "traceback", "exception", "timeout", "warning", "cannot find", "not found")):
            lines.append(cleaned[:500])
        if len(lines) >= 20:
            break
    return lines


def _analyze(text: str, evidence: list[str]) -> dict[str, str]:
    low = str(text or "").lower()
    if "traceback" in low or "exception" in low:
        cause = "runtime_exception"
        fix = "Read the top stack frame, add a focused regression test, then patch the failing function."
    elif "module not found" in low or "cannot find module" in low or "importerror" in low:
        cause = "missing_dependency_or_import"
        fix = "Verify dependency/install path and update imports or requirements."
    elif "timeout" in low:
        cause = "timeout_or_hanging_process"
        fix = "Add shorter timeouts, reduce blocking work, or move slow work into the background."
    elif "assert" in low or "failed" in low:
        cause = "test_failure"
        fix = "Inspect the failing assertion, reproduce with the narrowest test, then patch behavior and rerun."
    elif "console" in low or "hydration" in low or "react" in low:
        cause = "browser_console_error"
        fix = "Use browser-extension DOM/console context, fix the component or route, then rerun the web build."
    else:
        cause = "unknown"
        fix = "Collect more logs, reproduce the issue, and create a focused test before editing."
    summary = evidence[0] if evidence else "Debugger found no explicit failure line."
    return {
        "summary": summary,
        "probable_cause": cause,
        "proposed_fix": fix,
        "test_plan": "Run the smallest focused check first, then the affected build/test suite, then create a proof report.",
    }


def _safe_path(path: str | Path) -> Path:
    raw = Path(path or ROOT_DIR)
    if not raw.is_absolute():
        raw = ROOT_DIR / raw
    return raw.resolve()


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "source": str(row["source"]),
        "status": str(row["status"]),
        "summary": str(row["summary"]),
        "probable_cause": str(row["probable_cause"]),
        "proposed_fix": str(row["proposed_fix"]),
        "test_plan": str(row["test_plan"]),
        "evidence": _json_loads(row["evidence_json"], []),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

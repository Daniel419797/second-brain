"""Deep project autopilot coordinator: logs, tests, console, fixes, proof."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import autonomous_debugger, browser_extension_bridge, project_autopilot, trust_proof
from core.config import DATA_DIR, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "deep_project_autopilot.sqlite3"
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
            CREATE TABLE IF NOT EXISTS deep_autopilot_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                root TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                proof_report_id INTEGER,
                metadata_json TEXT NOT NULL
            )
            """
        )


def run(root: str | Path = "", *, run_tests: bool = False, log_text: str = "", prepare_fix: bool = False) -> dict[str, Any]:
    init_db()
    base = _safe_root(root)
    project = project_autopilot.inspect_project(base, run_tests=run_tests, notify=False)
    debug = autonomous_debugger.analyze_text(log_text, source="deep_project_autopilot") if log_text else autonomous_debugger.watch(base)
    browser = browser_extension_bridge.latest_page_insight()
    fix = project_autopilot.prepare_fixes(base) if prepare_fix and project.get("issues") else {"skipped": True, "summary": "No fix task requested or no project issues found."}
    evidence = [
        project.get("summary", ""),
        debug.get("summary", ""),
        browser.get("summary", ""),
        fix.get("summary", ""),
    ]
    failures = []
    if project.get("status") == "attention":
        failures.append("Project autopilot found issues.")
    if debug.get("status") == "open":
        failures.append(debug.get("summary", "Debugger issue is open."))
    if browser.get("console_errors"):
        failures.append("Browser console has warnings/errors.")
    proof = trust_proof.create_report(
        "Deep project autopilot proof",
        changed=["Prepared analysis and optional fix task; no risky code edits are applied by this coordinator."],
        tested=["Project inspection", "Debugger/watch analysis", "Browser console context check"],
        failed=failures,
        evidence=[item for item in evidence if item],
        risks=["Fix application still needs focused code changes and verification." if failures else "No major risk detected in this pass."],
        confidence=0.72 if failures else 0.86,
        metadata={"root": str(base)},
    )
    status = "attention" if failures else "ok"
    summary = f"Deep project autopilot complete for {base.name}: {len(failures)} issue signal(s), proof #{proof.get('id')}."
    report = _persist(base, status, summary, proof.get("id"), {"project": project, "debugger": debug, "browser": browser, "fix": fix, "proof": proof})
    report["project"] = project
    report["debugger"] = debug
    report["browser"] = browser
    report["fix"] = fix
    report["proof"] = proof
    return report


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM deep_autopilot_reports ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    reports = recent(limit=6)
    return {"reports": reports, "summary": f"{len(reports)} deep autopilot report(s)." if reports else "Deep project autopilot is ready."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM deep_autopilot_reports")


def _persist(base: Path, status: str, summary: str, proof_report_id: Any, metadata: dict[str, Any]) -> dict[str, Any]:
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO deep_autopilot_reports(timestamp, root, status, summary, proof_report_id, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
            (_now(), str(base), status, summary, int(proof_report_id or 0) or None, _json_dumps(metadata)),
        )
        row = conn.execute("SELECT * FROM deep_autopilot_reports WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "root": str(row["root"]),
        "status": str(row["status"]),
        "summary": str(row["summary"]),
        "proof_report_id": row["proof_report_id"],
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _safe_root(root: str | Path) -> Path:
    return resolve_coding_root(root)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

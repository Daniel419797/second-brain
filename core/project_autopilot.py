"""Project autopilot: watch codebases and prepare safe improvement work."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import autonomous_coding, capability_center, notification_center, workspace_brain
from core.config import DATA_DIR, config_value, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "project_autopilot.sqlite3"
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
            CREATE TABLE IF NOT EXISTS autopilot_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                root TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                issues_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_autopilot_root ON autopilot_reports(root, timestamp)")


def inspect_project(root: str | Path = "", *, run_tests: bool = False, notify: bool = True) -> dict[str, Any]:
    init_db()
    base = _safe_root(root)
    analysis = workspace_brain.analyze_project(base)
    dependency = capability_center.workspace_dependency_health(base)
    test_result = capability_center.test_failure_watcher() if run_tests else {"skipped": True, "summary": "Tests not run in light autopilot mode."}
    docs = _docs_state(base)
    issues = _issues(analysis, dependency, test_result, docs)
    status = "attention" if issues else "ok"
    summary = f"Project autopilot found {len(issues)} issue(s) under {base.name}."
    report_id = _persist_report(base, status, summary, issues, {"analysis": analysis, "dependency": dependency, "tests": test_result, "docs": docs})
    if notify and issues:
        high = [item for item in issues if int(item.get("severity") or 0) >= 4]
        notification_center.add(
            source="project_autopilot",
            category="workspace",
            severity=4 if high else 3,
            title="Project autopilot found work",
            message=summary,
            dedupe_key=f"project-autopilot:{base}",
            metadata={"report_id": report_id, "issues": issues[:10]},
        )
    return {
        "id": report_id,
        "root": str(base),
        "status": status,
        "summary": summary,
        "issues": issues,
        "analysis": analysis,
        "dependency": dependency,
        "tests": test_result,
        "docs": docs,
    }


def prepare_fixes(root: str | Path = "", *, issue_query: str = "") -> dict[str, Any]:
    report = inspect_project(root, run_tests=False, notify=False)
    issues = report.get("issues") or []
    if issue_query:
        issues = [item for item in issues if issue_query.lower() in json.dumps(item, ensure_ascii=True).lower()]
    if not issues:
        return {"ok": False, "summary": "No autopilot issues found to prepare fixes for.", "report": report}
    request = (
        "Prepare safe fixes for the project autopilot findings. "
        "Do not apply changes until tests and user approval. Findings: "
        + "; ".join(f"{item['kind']}: {item['title']}" for item in issues[:8])
    )
    task = autonomous_coding.start(request, root=str(report["root"]), risk_level="medium")
    return {"ok": True, "summary": task["summary"], "task": task, "report": report}


def recent_reports(limit: int = 20, root: str | Path = "") -> list[dict[str, Any]]:
    init_db()
    where = ""
    params: list[Any] = []
    if root:
        where = "WHERE root=?"
        params.append(str(_safe_root(root)))
    params.append(max(1, min(100, int(limit or 20))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM autopilot_reports {where} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM autopilot_reports")


def _issues(analysis: dict[str, Any], dependency: dict[str, Any], tests: dict[str, Any], docs: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    todos = analysis.get("todos") or []
    if todos:
        issues.append({"kind": "todos", "severity": 2, "title": f"{len(todos)} TODO/bug marker(s)", "evidence": todos[:10], "recommendation": "Review or convert TODOs into tracked tasks."})
    for audit in dependency.get("audits") or []:
        if audit.get("available") and audit.get("ok") is False:
            issues.append({"kind": "dependency", "severity": 4, "title": f"{audit.get('tool')} found dependency issues", "evidence": audit, "recommendation": "Review vulnerable dependencies and update where safe."})
    if tests.get("skipped") is not True and not tests.get("ok"):
        issues.append({"kind": "tests", "severity": 5, "title": "Tests are failing", "evidence": tests, "recommendation": "Fix failing tests before shipping changes."})
    if docs.get("stale"):
        issues.append({"kind": "docs", "severity": 2, "title": "Project docs look stale or missing", "evidence": docs, "recommendation": "Regenerate Friday project docs and update README/docs."})
    if not analysis.get("tests"):
        issues.append({"kind": "tests", "severity": 2, "title": "No test files discovered", "evidence": {}, "recommendation": "Add focused tests for important behavior."})
    return issues


def _docs_state(base: Path) -> dict[str, Any]:
    docs = [base / "README.md", base / "docs" / "friday_workspace_brain.md", base / "docs" / "friday_project_map.md"]
    existing = [path for path in docs if path.exists()]
    if not existing:
        return {"stale": True, "existing": [], "summary": "No project docs found."}
    newest_source = _newest_mtime(base, ignore_dirs={".git", ".venv", "node_modules", ".next", "data"})
    newest_doc = max(path.stat().st_mtime for path in existing)
    stale = newest_source > newest_doc + float(config_value("project_autopilot_docs_stale_seconds", 86400))
    return {"stale": stale, "existing": [str(path) for path in existing], "summary": "Docs are stale." if stale else "Docs look current."}


def _newest_mtime(base: Path, *, ignore_dirs: set[str]) -> float:
    latest = 0.0
    count = 0
    max_files = int(config_value("project_autopilot_doc_scan_max_files", 1200))
    for path in base.rglob("*"):
        if count >= max_files:
            break
        if not path.is_file():
            continue
        rel_parts = set(path.relative_to(base).parts[:-1])
        if rel_parts & ignore_dirs:
            continue
        count += 1
        try:
            latest = max(latest, path.stat().st_mtime)
        except OSError:
            continue
    return latest


def _persist_report(base: Path, status: str, summary: str, issues: list[dict[str, Any]], metadata: dict[str, Any]) -> int:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            "INSERT INTO autopilot_reports(timestamp, root, status, summary, issues_json, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
            (_now(), str(base), status, summary, _json_dumps(issues), _json_dumps(metadata)),
        )
        return int(cursor.lastrowid)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "root": str(row["root"]),
        "status": str(row["status"]),
        "summary": str(row["summary"]),
        "issues": _json_loads(row["issues_json"], []),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _safe_root(root: str | Path) -> Path:
    return resolve_coding_root(root)


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=True)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

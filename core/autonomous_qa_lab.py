"""Autonomous QA evidence collector for mission and project work."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import subprocess
import threading
from pathlib import Path
from typing import Any

from core import capability_center, command_runner, project_autopilot
from core.config import DATA_DIR, config_value, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "autonomous_qa_lab.sqlite3"
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
            CREATE TABLE IF NOT EXISTS qa_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                root TEXT NOT NULL,
                mission_id INTEGER,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                checks_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qa_reports_time ON qa_reports(timestamp)")


def run_qa(root: str | Path = "", *, mission_id: int | None = None, run_tests: bool | None = None) -> dict[str, Any]:
    init_db()
    project_root = _safe_root(root)
    should_run_tests = bool(config_value("qa_lab_run_tests_default", False) if run_tests is None else run_tests)
    checks: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    files = _inventory(project_root)
    checks.append(_check("project_files", "pass" if files["count"] else "warn", f"{files['count']} inspectable file(s) found.", files))
    checks.append(_check("test_files", "pass" if files["tests"] else "warn", f"{len(files['tests'])} test file(s) found.", {"tests": files["tests"][:20]}))
    checks.append(_check("docs", "pass" if files["docs"] else "warn", f"{len(files['docs'])} documentation file(s) found.", {"docs": files["docs"][:20]}))

    runner = _detect_test_runner(project_root)
    checks.append(_check("test_runner", "pass" if runner else "warn", runner or "No obvious test runner detected.", {"runner": runner}))
    if should_run_tests and runner:
        test_result = _run_command(project_root, runner)
        checks.append(_check("tests_executed", "pass" if test_result["returncode"] == 0 else "fail", test_result["summary"], test_result))
        evidence.append({"kind": "test_run", "runner": runner, "result": test_result})
    elif runner:
        checks.append(_check("tests_planned", "warn", f"Tests were detected but not run automatically: {runner}", {"runner": runner}))

    try:
        project_report = project_autopilot.inspect_project(project_root, run_tests=False, notify=False)
        checks.append(_check("project_autopilot", "pass", project_report.get("summary", "Project inspection completed."), project_report))
        evidence.append({"kind": "project_autopilot", "report": project_report})
    except Exception as exc:
        checks.append(_check("project_autopilot", "warn", f"Project inspection unavailable: {exc}", {}))

    try:
        deps = capability_center.workspace_dependency_health(project_root)
        checks.append(_check("dependency_health", "pass" if not deps.get("findings") else "warn", deps.get("summary", "Dependency health checked."), deps))
        evidence.append({"kind": "dependencies", "report": deps})
    except Exception as exc:
        checks.append(_check("dependency_health", "warn", f"Dependency health unavailable: {exc}", {}))

    try:
        secrets = capability_center.project_secret_scan(project_root)
        status = "fail" if secrets.get("findings") else "pass"
        checks.append(_check("secret_scan", status, secrets.get("summary", "Secret scan completed."), secrets))
        evidence.append({"kind": "secret_scan", "report": secrets})
    except Exception as exc:
        checks.append(_check("secret_scan", "warn", f"Secret scan unavailable: {exc}", {}))

    checks.extend(_browser_and_accessibility_checks(project_root))
    status = _overall_status(checks)
    summary = _summary(checks)
    report = _store_report(project_root, mission_id, status, summary, checks, evidence)
    if mission_id:
        try:
            from core import mission_control

            mission_control.add_evidence(
                int(mission_id),
                "autonomous_qa",
                "qa_lab",
                "QA Lab report",
                summary,
                {"report_id": report["id"], "status": status, "checks": checks},
            )
        except Exception:
            pass
    return report


def recent_reports(limit: int = 20, root: str | Path = "") -> list[dict[str, Any]]:
    init_db()
    where = ""
    params: list[Any] = []
    if root:
        where = "WHERE root=?"
        params.append(str(_safe_root(root)))
    params.append(max(1, min(200, int(limit or 20))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM qa_reports {where} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT status, COUNT(*) FROM qa_reports GROUP BY status").fetchall()
    counts = {str(status): int(count) for status, count in rows}
    reports = recent_reports(limit=6)
    return {"counts": counts, "recent": reports, "summary": f"{sum(counts.values())} QA report(s) recorded."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM qa_reports")


def _store_report(root: Path, mission_id: int | None, status: str, summary: str, checks: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO qa_reports(timestamp, root, mission_id, status, summary, checks_json, evidence_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (_now(), str(root), int(mission_id) if mission_id else None, status, summary, _json_dumps(checks), _json_dumps(evidence)),
        )
        row = conn.execute("SELECT * FROM qa_reports WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def _inventory(root: Path) -> dict[str, Any]:
    skip = {".git", ".venv", "node_modules", "__pycache__", ".next", "dist", "build"}
    count = 0
    tests: list[str] = []
    docs: list[str] = []
    for path in root.rglob("*"):
        if any(part in skip for part in path.parts):
            continue
        if not path.is_file():
            continue
        count += 1
        rel = str(path.relative_to(root))
        low = rel.lower()
        if low.startswith("test") or "/test" in low.replace("\\", "/") or low.endswith((".spec.js", ".test.js", "_test.py")):
            tests.append(rel)
        if low.endswith((".md", ".rst")) or "readme" in low:
            docs.append(rel)
        if count >= 5000:
            break
    return {"root": str(root), "count": count, "tests": tests, "docs": docs}


def _detect_test_runner(root: Path) -> str:
    package = root / "package.json"
    if package.exists():
        try:
            data = json.loads(package.read_text(encoding="utf-8"))
            scripts = data.get("scripts") or {}
            if "test" in scripts:
                return "npm test -- --watch=false"
            if "build" in scripts:
                return "npm run build"
        except Exception:
            return "npm test"
    if (root / "pytest.ini").exists() or (root / "pyproject.toml").exists() or (root / "tests").exists():
        return ".\\.venv\\Scripts\\python.exe -m pytest -q"
    return ""


def _run_command(root: Path, command: str) -> dict[str, Any]:
    timeout = float(config_value("qa_lab_test_timeout_seconds", 120.0))
    try:
        completed = command_runner.run(command, cwd=root, timeout=timeout)
        output = (completed.stdout + "\n" + completed.stderr).strip()
        return {
            "command": command,
            "returncode": int(completed.returncode),
            "output_tail": output[-4000:],
            "summary": "Tests passed." if completed.returncode == 0 else f"Tests failed with exit code {completed.returncode}.",
        }
    except subprocess.TimeoutExpired as exc:
        return {"command": command, "returncode": 124, "output_tail": str(exc)[-4000:], "summary": "Tests timed out."}
    except command_runner.CommandRejected as exc:
        return {"command": command, "returncode": 126, "output_tail": str(exc), "summary": f"Tests were blocked by command policy: {exc}"}
    except Exception as exc:
        return {"command": command, "returncode": 1, "output_tail": str(exc), "summary": f"Could not run tests: {exc}"}


def _browser_and_accessibility_checks(root: Path) -> list[dict[str, Any]]:
    has_web = any((root / name).exists() for name in ("package.json", "app", "pages", "src"))
    if not has_web:
        return [_check("browser_tests", "warn", "No browser app structure detected; Playwright checklist not run.", {})]
    return [
        _check("browser_tests", "warn", "Add or run Playwright smoke tests for main pages, forms, and auth gates.", {"recommended": True}),
        _check("performance_smoke", "warn", "Run a production build or lighthouse-style smoke check before release.", {"recommended": True}),
        _check("accessibility", "warn", "Check keyboard navigation, labels, contrast, and responsive layouts before release.", {"recommended": True}),
    ]


def _check(name: str, status: str, summary: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "status": status, "summary": _clean(summary), "details": details}


def _overall_status(checks: list[dict[str, Any]]) -> str:
    statuses = {str(check.get("status")) for check in checks}
    if "fail" in statuses:
        return "failed"
    if "warn" in statuses:
        return "needs_review"
    return "passed"


def _summary(checks: list[dict[str, Any]]) -> str:
    failed = sum(1 for check in checks if check.get("status") == "fail")
    warned = sum(1 for check in checks if check.get("status") == "warn")
    passed = sum(1 for check in checks if check.get("status") == "pass")
    return f"QA Lab complete: {passed} passed, {warned} need review, {failed} failed."


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "root": str(row["root"]),
        "mission_id": int(row["mission_id"]) if row["mission_id"] is not None else None,
        "status": str(row["status"]),
        "summary": str(row["summary"]),
        "checks": _json_loads(row["checks_json"], []),
        "evidence": _json_loads(row["evidence_json"], []),
    }


def _safe_root(value: str | Path) -> Path:
    try:
        return resolve_coding_root(value)
    except Exception:
        return resolve_coding_root()


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

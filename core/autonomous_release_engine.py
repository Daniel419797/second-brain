"""Autonomous release engineer: build/test/checklist/proof without deploying silently."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import autonomous_qa_lab, project_watchdog, release_manager, test_build_monitor, trust_proof
from core.config import DATA_DIR, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "autonomous_release_engine.sqlite3"
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
            CREATE TABLE IF NOT EXISTS release_engine_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                root TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                release_id INTEGER,
                qa_report_json TEXT NOT NULL,
                watchdog_json TEXT NOT NULL,
                build_json TEXT NOT NULL,
                dependency_audit_json TEXT NOT NULL,
                security_headers_json TEXT NOT NULL,
                rollback_json TEXT NOT NULL,
                proof_id INTEGER
            )
            """
        )


def prepare(root: str | Path = "", *, build_command: str = "", target_url: str = "", run_tests: bool = False) -> dict[str, Any]:
    init_db()
    project_root = _safe_root(root)
    release = release_manager.prepare_release(project_root)
    qa = autonomous_qa_lab.run_qa(project_root, run_tests=run_tests)
    watchdog = project_watchdog.run_once(project_root, notify=False)
    build = _build_check(project_root, build_command)
    dependency = _dependency_audit(project_root)
    headers = _headers_check(target_url)
    rollback = {"strategy": "Use git revert or redeploy previous build; deploy remains blocked until approval.", "root": str(project_root)}
    failed = []
    for label, payload in [("qa", qa), ("watchdog", watchdog), ("build", build), ("dependency", dependency), ("security_headers", headers)]:
        if str(payload.get("status") or "").lower() in {"failed", "error"}:
            failed.append(f"{label}: {payload.get('summary')}")
    status = "ready_for_approval" if not failed else "needs_fixes"
    summary = f"Release engineer prepared {project_root.name}: {status}. Deploy is still approval-gated."
    proof = trust_proof.create_report(
        "Autonomous release engineer proof",
        changed=[release.get("summary", "release checklist prepared")],
        tested=[qa.get("summary", "QA check"), build.get("summary", "Build check"), dependency.get("summary", "Dependency audit"), headers.get("summary", "Header check")],
        failed=failed,
        evidence=[watchdog.get("summary", ""), release.get("summary", "")],
        risks=["Deploy command is not run until explicit approval.", "Security header check needs a live target URL." if not target_url else ""],
        confidence=0.82 if not failed else 0.55,
        metadata={"source": "autonomous_release_engine", "release_id": release.get("id")},
    )
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO release_engine_runs(timestamp, root, status, summary, release_id, qa_report_json, watchdog_json, build_json, dependency_audit_json, security_headers_json, rollback_json, proof_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_now(), str(project_root), status, summary, int(release.get("id") or 0), _json_dumps(qa), _json_dumps(watchdog), _json_dumps(build), _json_dumps(dependency), _json_dumps(headers), _json_dumps(rollback), int(proof.get("id") or 0)),
        )
        row = conn.execute("SELECT * FROM release_engine_runs WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM release_engine_runs ORDER BY id DESC LIMIT ?", (max(1, min(200, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    runs = recent(limit=8)
    pending = [run for run in runs if run["status"] == "ready_for_approval"]
    return {"recent": runs, "pending_approval": pending, "summary": f"{len(pending)} release engineer run(s) ready for deploy approval."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM release_engine_runs")


def _build_check(root: Path, command: str) -> dict[str, Any]:
    if not command:
        package = root / "package.json"
        if package.exists():
            command = "npm run build"
    if not command:
        return {"status": "skipped", "summary": "No build command detected."}
    return test_build_monitor.run_check(root, command, kind="release_build", create_proof=False)


def _dependency_audit(root: Path) -> dict[str, Any]:
    package = root / "package.json"
    requirements = root / "requirements.txt"
    if package.exists():
        return {"status": "planned", "summary": "Run npm audit before deploy when network/tooling is available.", "command_hint": "npm audit --audit-level=moderate"}
    if requirements.exists():
        return {"status": "planned", "summary": "Run pip-audit before deploy when installed.", "command_hint": "pip-audit -r requirements.txt"}
    return {"status": "skipped", "summary": "No dependency manifest detected."}


def _headers_check(target_url: str) -> dict[str, Any]:
    if not str(target_url or "").strip():
        return {"status": "skipped", "summary": "No target URL provided for security header check."}
    try:
        from core import deployment_brain

        return deployment_brain.inspect(str(target_url), create_proof=False)
    except Exception as exc:
        return {"status": "error", "summary": f"Security header check failed: {exc}"}


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "root": str(row["root"]),
        "status": str(row["status"]),
        "summary": str(row["summary"]),
        "release_id": int(row["release_id"]) if row["release_id"] is not None else None,
        "qa_report": _json_loads(row["qa_report_json"], {}),
        "watchdog": _json_loads(row["watchdog_json"], {}),
        "build": _json_loads(row["build_json"], {}),
        "dependency_audit": _json_loads(row["dependency_audit_json"], {}),
        "security_headers": _json_loads(row["security_headers_json"], {}),
        "rollback": _json_loads(row["rollback_json"], {}),
        "proof_id": int(row["proof_id"]) if row["proof_id"] is not None else None,
    }


def _safe_root(value: str | Path) -> Path:
    try:
        return resolve_coding_root(value)
    except Exception:
        return resolve_coding_root()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

"""Autonomous test/build monitor with debugger analysis and proof reports."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from core import autonomous_debugger, command_runner, error_radar, trust_proof
from core.config import DATA_DIR, config_value, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "test_build_monitor.sqlite3"
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
            CREATE TABLE IF NOT EXISTS test_build_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                root TEXT NOT NULL,
                command TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                returncode INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL,
                summary TEXT NOT NULL,
                output_tail TEXT NOT NULL,
                debugger_json TEXT NOT NULL,
                proof_report_id INTEGER,
                metadata_json TEXT NOT NULL
            )
            """
        )


def run_check(root: str | Path = "", command: str = "", *, kind: str = "auto", create_proof: bool = True, timeout: int | None = None) -> dict[str, Any]:
    init_db()
    base = _safe_root(root)
    cmd = _clean(command) or _choose_command(base)
    if not cmd:
        return _store(base, "", kind, "skipped", 0, 0, "No test or build command was detected.", "", {}, None, {"reason": "no_command"})
    limit = int(timeout or config_value("test_build_monitor_timeout_seconds", 120))
    started = dt.datetime.now(dt.timezone.utc)
    try:
        proc = command_runner.run(cmd, cwd=base, timeout=max(5, limit))
        output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        duration = int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000)
        status = "passed" if proc.returncode == 0 else "failed"
        debugger = autonomous_debugger.analyze_text(output, source="test_build_monitor", metadata={"root": str(base), "command": cmd, "returncode": proc.returncode}) if output or proc.returncode else {}
        summary = "Build/test check passed." if status == "passed" else _failure_summary(output, proc.returncode)
        proof_id = _proof(base, cmd, status, summary, output, debugger, create_proof)
        report = _store(base, cmd, kind, status, int(proc.returncode), duration, summary, _tail(output), debugger, proof_id, {})
        if status == "failed":
            try:
                error_radar.ingest_event("test_build_monitor", "failed_check", summary, root=str(base), metadata={"report_id": report["id"], "command": cmd})
            except Exception:
                pass
        return report
    except subprocess.TimeoutExpired as exc:
        output = ((exc.stdout or "") if isinstance(exc.stdout, str) else "") + "\n" + ((exc.stderr or "") if isinstance(exc.stderr, str) else "")
        summary = f"Build/test command timed out after {limit}s."
        debugger = autonomous_debugger.analyze_text(str(exc) + "\n" + output, source="test_build_timeout", metadata={"root": str(base), "command": cmd, "timeout": limit})
        proof_id = _proof(base, cmd, "timeout", summary, output, debugger, create_proof)
        return _store(base, cmd, kind, "timeout", -1, int(limit * 1000), summary, _tail(output or str(exc)), debugger, proof_id, {"timeout": limit})
    except command_runner.CommandRejected as exc:
        summary = f"Build/test command was blocked by command policy: {exc}"
        debugger = autonomous_debugger.analyze_text(summary, source="test_build_rejected", metadata={"root": str(base), "command": cmd})
        proof_id = _proof(base, cmd, "blocked", summary, str(exc), debugger, create_proof)
        return _store(base, cmd, kind, "blocked", 126, 0, summary, str(exc), debugger, proof_id, {"blocked": True})


def watch(root: str | Path = "", command: str = "") -> dict[str, Any]:
    report = run_check(root, command, kind="watch", create_proof=True)
    return {"ok": report.get("status") == "passed", "report": report, "summary": report.get("summary", "Monitor check completed.")}


def recent_reports(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM test_build_reports ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    reports = recent_reports(limit=8)
    failing = [item for item in reports if item["status"] in {"failed", "timeout"}]
    return {
        "recent": reports,
        "failing_count": len(failing),
        "summary": f"{len(failing)} failing build/test monitor report(s)." if failing else "Test/build monitor is clean or waiting for a run.",
    }


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM test_build_reports")


def _choose_command(base: Path) -> str:
    package = base / "package.json"
    if package.exists():
        try:
            data = json.loads(package.read_text(encoding="utf-8"))
            scripts = data.get("scripts") if isinstance(data, dict) else {}
            if isinstance(scripts, dict):
                if "test" in scripts:
                    return "npm test -- --watch=false"
                if "build" in scripts:
                    return "npm run build"
        except Exception:
            return "npm run build"
    if (base / "pytest.ini").exists() or (base / "tests").exists():
        return f'"{sys.executable}" -m pytest -q'
    return ""


def _proof(base: Path, command: str, status: str, summary: str, output: str, debugger: dict[str, Any], create: bool) -> int | None:
    if not create:
        return None
    report = trust_proof.create_report(
        "Autonomous test/build monitor",
        changed=["No files changed by the monitor."],
        tested=[f"{command} -> {status}"],
        failed=[summary] if status != "passed" else [],
        evidence=[_tail(output, 1200) or summary],
        risks=[] if status == "passed" else ["Friday prepared evidence only; code changes still need a guarded fix task."],
        confidence=0.9 if status == "passed" else 0.65,
        metadata={"root": str(base), "command": command, "debugger_id": debugger.get("id")},
    )
    return int(report.get("id") or 0) or None


def _store(
    base: Path,
    command: str,
    kind: str,
    status: str,
    returncode: int,
    duration_ms: int,
    summary: str,
    output_tail: str,
    debugger: dict[str, Any],
    proof_report_id: int | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO test_build_reports(timestamp, root, command, kind, status, returncode, duration_ms, summary, output_tail, debugger_json, proof_report_id, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_now(), str(base), command, _clean(kind) or "auto", status, int(returncode), int(duration_ms), _clean(summary)[:1000], output_tail[:12000], _json_dumps(debugger), proof_report_id, _json_dumps(metadata)),
        )
        row = conn.execute("SELECT * FROM test_build_reports WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def _failure_summary(output: str, returncode: int) -> str:
    for line in str(output or "").splitlines():
        low = line.lower()
        if any(term in low for term in ("error", "failed", "traceback", "exception", "cannot find", "not found")):
            return _clean(line)[:500]
    return f"Build/test command failed with return code {returncode}."


def _tail(text: str, limit: int = 12000) -> str:
    cleaned = str(text or "")
    return cleaned[-limit:]


def _safe_root(root: str | Path) -> Path:
    return resolve_coding_root(root)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "root": str(row["root"]),
        "command": str(row["command"]),
        "kind": str(row["kind"]),
        "status": str(row["status"]),
        "returncode": int(row["returncode"]),
        "duration_ms": int(row["duration_ms"]),
        "summary": str(row["summary"]),
        "output_tail": str(row["output_tail"]),
        "debugger": _json_loads(row["debugger_json"], {}),
        "proof_report_id": row["proof_report_id"],
        "metadata": _json_loads(row["metadata_json"], {}),
    }


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

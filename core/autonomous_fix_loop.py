"""Approval-gated autonomous fix loop.

This module turns failures into a repeatable loop: detect, diagnose, propose a
safe patch plan, run verification when possible, create proof, and wait for
approval before any risky file change is applied.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import autonomous_coding, autonomous_debugger, error_radar, notification_center, self_update, test_build_monitor, trust_proof
from core.config import DATA_DIR, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "autonomous_fix_loop.sqlite3"
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
            CREATE TABLE IF NOT EXISTS fix_loop_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                root TEXT NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                diagnosis_json TEXT NOT NULL,
                patch_plan_json TEXT NOT NULL,
                verification_json TEXT NOT NULL,
                proof_id INTEGER,
                approval_phrase TEXT NOT NULL,
                task_id INTEGER,
                self_update_id INTEGER
            )
            """
        )


def run(
    *,
    root: str | Path = "",
    command: str = "",
    log_text: str = "",
    source: str = "manual",
    run_tests: bool = True,
    create_patch: bool = True,
) -> dict[str, Any]:
    init_db()
    base = _safe_root(root)
    diagnosis = _diagnose(base, command=command, log_text=log_text, source=source, run_tests=run_tests)
    failed = _has_failure(diagnosis)
    patch_plan = _patch_plan(base, diagnosis) if create_patch and failed else {"needed": failed, "summary": "No patch plan needed."}
    verification = _verification(base, command=command, enabled=run_tests and bool(command))
    proof = trust_proof.create_report(
        "Autonomous fix loop report",
        changed=["No files changed. Patch waits for approval."],
        tested=[verification.get("summary", "Verification not run.")],
        evidence=[diagnosis.get("summary", ""), patch_plan.get("summary", "")],
        risks=["Patch is only a proposal until approved.", "Friday must not claim a fix is applied before a successful tool result."],
        confidence=0.72 if failed else 0.9,
    )
    status = "needs_approval" if failed and patch_plan.get("needed") else "clean"
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO fix_loop_runs(created_at, updated_at, root, source, status, summary, diagnosis_json, patch_plan_json, verification_json, proof_id, approval_phrase, task_id, self_update_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', NULL, NULL)
            """,
            (
                now,
                now,
                str(base),
                _clean(source),
                status,
                _summary(status, diagnosis),
                _json_dumps(diagnosis),
                _json_dumps(patch_plan),
                _json_dumps(verification),
                int(proof.get("id") or 0),
            ),
        )
        run_id = int(cursor.lastrowid)
        phrase = f"I approve fix loop {run_id}"
        conn.execute("UPDATE fix_loop_runs SET approval_phrase=? WHERE id=?", (phrase, run_id))
        row = conn.execute("SELECT * FROM fix_loop_runs WHERE id=?", (run_id,)).fetchone()
    if status == "needs_approval":
        notification_center.add(
            source="autonomous_fix_loop",
            category="approval",
            severity=4,
            title="Fix loop needs approval",
            message=f"Fix loop #{run_id} prepared a patch plan. Say: {phrase}",
            dedupe_key=f"fix-loop:{run_id}",
            metadata={"run_id": run_id, "proof_id": proof.get("id")},
        )
    return _row(row)


def approve(run_id: int, confirmation: str = "") -> dict[str, Any]:
    init_db()
    run_item = get(run_id)
    if not run_item:
        raise ValueError("fix loop run not found")
    phrase = str(run_item.get("approval_phrase") or "").lower()
    if phrase and phrase not in str(confirmation or "").lower():
        raise PermissionError(f"Say or type: {run_item['approval_phrase']}.")
    patch_plan = run_item.get("patch_plan") or {}
    task = autonomous_coding.start(patch_plan.get("request") or run_item.get("summary") or "Prepare safe fix", root=run_item.get("root", ""), risk_level="medium")
    update = self_update.create_proposal(patch_plan.get("request") or run_item.get("summary") or "Prepare exact staged replacements for the approved fix loop.")
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            "UPDATE fix_loop_runs SET status='approved_for_fix_prep', updated_at=?, task_id=?, self_update_id=? WHERE id=?",
            (_now(), int(task.get("task", {}).get("id") or 0), int(update.get("id") or 0), int(run_id)),
        )
        row = conn.execute("SELECT * FROM fix_loop_runs WHERE id=?", (int(run_id),)).fetchone()
    return _row(row)


def get(run_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM fix_loop_runs WHERE id=?", (int(run_id),)).fetchone()
    return _row(row) if row else None


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM fix_loop_runs ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    items = recent(limit=8)
    pending = [item for item in items if item["status"] == "needs_approval"]
    return {"pending": len(pending), "recent": items, "summary": f"{len(pending)} fix loop run(s) waiting for approval."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM fix_loop_runs")


def _diagnose(base: Path, *, command: str, log_text: str, source: str, run_tests: bool) -> dict[str, Any]:
    if log_text.strip():
        return autonomous_debugger.analyze_text(log_text, source=source or "fix_loop", metadata={"root": str(base)})
    if command.strip() and run_tests:
        monitor = test_build_monitor.run_check(base, command, kind="fix_loop", create_proof=True)
        if monitor.get("status") == "passed":
            return {"status": "passed", "summary": monitor.get("summary", "Command passed."), "probable_cause": "none", "evidence": [monitor.get("summary", "")]}
        return autonomous_debugger.analyze_text(monitor.get("raw_output") or monitor.get("summary") or "Command failed.", source="fix_loop_command", metadata={"monitor": monitor})
    watch = error_radar.watch(str(base))
    if watch.get("events"):
        return autonomous_debugger.analyze_text("\n".join(str(item.get("summary") or "") for item in watch.get("events") or []), source="fix_loop_watch", metadata={"watch": watch})
    return {"status": "clean", "summary": "No obvious error detected.", "probable_cause": "none", "evidence": []}


def _patch_plan(base: Path, diagnosis: dict[str, Any]) -> dict[str, Any]:
    likely_files = _likely_files(diagnosis)
    request = (
        "Prepare a minimal, approval-gated patch for this failure. "
        f"Probable cause: {diagnosis.get('probable_cause')}. "
        f"Summary: {diagnosis.get('summary')}. "
        "Inspect likely files, stage exact replacements only after approval, run focused tests, and produce proof."
    )
    return {
        "needed": True,
        "root": str(base),
        "likely_files": likely_files,
        "request": request,
        "steps": [
            "Reproduce or verify the failure evidence.",
            "Inspect the narrowest likely file/function.",
            "Create a tiny change set with rollback notes.",
            "Run the focused failing test/build command.",
            "Create proof and wait for user approval before applying risky changes.",
        ],
        "summary": f"Patch plan prepared for {diagnosis.get('probable_cause', 'unknown issue')}.",
    }


def _verification(base: Path, *, command: str, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"status": "skipped", "summary": "Verification command not run."}
    return test_build_monitor.run_check(base, command, kind="fix_loop_verification", create_proof=False)


def _has_failure(diagnosis: dict[str, Any]) -> bool:
    status = str(diagnosis.get("status") or "").lower()
    cause = str(diagnosis.get("probable_cause") or "").lower()
    summary = str(diagnosis.get("summary") or "").lower()
    return status not in {"clean", "passed"} and cause not in {"none", ""} or any(term in summary for term in ("error", "failed", "traceback", "exception"))


def _likely_files(diagnosis: dict[str, Any]) -> list[str]:
    text = json.dumps(diagnosis, ensure_ascii=True, default=str)
    matches = re.findall(r"([A-Za-z]:\\[^:\n]+?\.(?:py|js|jsx|ts|tsx|json|md)|[\w./\\-]+\.(?:py|js|jsx|ts|tsx|json|md))", text)
    return sorted(set(matches))[:8]


def _summary(status: str, diagnosis: dict[str, Any]) -> str:
    if status == "clean":
        return "Fix loop found no actionable failure."
    return f"Fix loop detected {diagnosis.get('probable_cause', 'an issue')} and prepared an approval-gated patch plan."


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "root": str(row["root"]),
        "source": str(row["source"]),
        "status": str(row["status"]),
        "summary": str(row["summary"]),
        "diagnosis": _json_loads(row["diagnosis_json"], {}),
        "patch_plan": _json_loads(row["patch_plan_json"], {}),
        "verification": _json_loads(row["verification_json"], {}),
        "proof_id": int(row["proof_id"] or 0),
        "approval_phrase": str(row["approval_phrase"]),
        "task_id": int(row["task_id"] or 0),
        "self_update_id": int(row["self_update_id"] or 0),
    }


def _safe_root(root: str | Path) -> Path:
    try:
        return resolve_coding_root(root)
    except Exception:
        return resolve_coding_root()


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

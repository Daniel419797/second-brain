"""Task contracts that define done, evidence, and verification before work starts."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "task_contracts.sqlite3"
_LOCK = threading.Lock()

VALID_STATUSES = {"draft", "active", "verified", "unsatisfied", "cancelled"}


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
            CREATE TABLE IF NOT EXISTS task_contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL UNIQUE,
                goal TEXT NOT NULL,
                success_criteria_json TEXT NOT NULL,
                tools_needed_json TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                expected_output TEXT NOT NULL,
                verification_method TEXT NOT NULL,
                status TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_task_contracts_status ON task_contracts(status, updated_at)")


def ensure_contract(task: dict[str, Any]) -> dict[str, Any]:
    init_db()
    task_id = int(task.get("id") or 0)
    if task_id <= 0:
        raise ValueError("Task id is required for a contract.")
    existing = get_contract(task_id)
    if existing:
        if existing["status"] == "draft":
            return update_status(task_id, "active") or existing
        return existing
    contract = draft_from_task(task)
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO task_contracts (
                task_id, goal, success_criteria_json, tools_needed_json, risk_level,
                expected_output, verification_method, status, evidence_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', '{}', ?, ?)
            """,
            (
                task_id,
                contract["goal"],
                _json_dumps(contract["success_criteria"]),
                _json_dumps(contract["tools_needed"]),
                contract["risk_level"],
                contract["expected_output"],
                contract["verification_method"],
                now,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM task_contracts WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row_to_contract(row)


def draft_from_task(task: dict[str, Any]) -> dict[str, Any]:
    title = _clean(task.get("title") or "Untitled task")
    description = _clean(task.get("description") or title)
    text = f"{title} {description}".lower()
    tools = ["agent_reasoning"]
    if any(word in text for word in ("research", "source", "docs", "web", "youtube")):
        tools.append("research")
    if any(word in text for word in ("code", "implement", "test", "debug", "file")):
        tools.extend(["workspace_files", "tests"])
    if any(word in text for word in ("screen", "desktop", "browser", "app", "click")):
        tools.append("desktop_or_browser_control")
    risk = "low"
    if any(word in text for word in ("delete", "send", "email", "message", "payment", "password", "credential", "shell", "command")):
        risk = "high"
    elif any(word in text for word in ("modify", "write file", "apply", "deploy", "install")):
        risk = "medium"
    success_criteria = [
        "A concise Summary is produced.",
        "A Next step is stated or the task is explicitly complete.",
        "Risks or verification limits are stated.",
    ]
    expected_output = "Concise agent result with Summary, Next step, and Risks."
    verification_method = "Check structured output fields and supporting task messages/evidence."
    if _is_autonomous_coding_task(task):
        success_criteria.extend(
            [
                "Project shape is inspected before files are written or staged.",
                "Responsibility boundaries and scoped execution plan are recorded.",
                "Product-studio phases are recorded: requirements, architecture, implementation, tests, security, performance, UX, deployment, launch, docs, and proof gaps.",
                "Executable product-studio gates are attempted and recorded: dependency install, tests/build, audit, browser check, and preview/deploy proof.",
                "Generated or changed files exist at the reported project root.",
                "File-level verification, discovered checks, or explicit verification limits are recorded.",
                "Final proof report states technical readiness, market-readiness, and names remaining gaps.",
            ]
        )
        expected_output = "Concise coding result with Summary, Next step, Risks, project root, changed files, inspection, execution plan, responsibility boundaries, executable gate results, product-studio phases, final proof gaps, and verification evidence."
        verification_method = "Check structured fields, supporting task messages, reported paths, changed files, inspection/plan metadata, executable product-studio gates, product-studio proof, and verification evidence."
    return {
        "task_id": int(task.get("id") or 0),
        "goal": title,
        "success_criteria": success_criteria,
        "tools_needed": _dedupe(tools),
        "risk_level": risk,
        "expected_output": expected_output,
        "verification_method": verification_method,
        "status": "draft",
        "evidence": {},
    }


def get_contract(task_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM task_contracts WHERE task_id=?", (int(task_id),)).fetchone()
    return _row_to_contract(row) if row else None


def list_contracts(status: str = "", limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    where = ""
    params: list[Any] = []
    if status:
        where = "WHERE status = ?"
        params.append(_normalize_status(status))
    params.append(max(1, min(300, int(limit))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM task_contracts {where} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_row_to_contract(row) for row in rows]


def verify_contract(task: dict[str, Any], result: Any) -> dict[str, Any]:
    contract = ensure_contract(task)
    task_id = int(task.get("id") or contract["task_id"])
    evidence = _evidence_from_result(result)
    satisfied = _satisfies_autonomous_coding_contract(result, evidence) if _is_autonomous_coding_task(task) else _satisfies_default_contract(result, evidence)
    status = "verified" if satisfied else "unsatisfied"
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            "UPDATE task_contracts SET status=?, evidence_json=?, updated_at=? WHERE task_id=?",
            (status, _json_dumps(evidence), now, task_id),
        )
    updated = get_contract(task_id) or contract
    updated["satisfied"] = satisfied
    return updated


def update_status(task_id: int, status: str, evidence: dict[str, Any] | None = None) -> dict[str, Any] | None:
    normalized = _normalize_status(status)
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            "UPDATE task_contracts SET status=?, evidence_json=CASE WHEN ? != '' THEN ? ELSE evidence_json END, updated_at=? WHERE task_id=?",
            (normalized, _json_dumps(evidence or {}) if evidence else "", _json_dumps(evidence or {}), now, int(task_id)),
        )
        if cursor.rowcount <= 0:
            return None
    return get_contract(task_id)


def summary(limit: int = 10) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT status, COUNT(*) FROM task_contracts GROUP BY status").fetchall()
    counts = {status: 0 for status in sorted(VALID_STATUSES)}
    counts.update({str(status): int(count) for status, count in rows})
    return {
        "counts": counts,
        "unsatisfied": list_contracts(status="unsatisfied", limit=limit),
        "recent": list_contracts(limit=limit),
    }


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM task_contracts")


def _satisfies_default_contract(result: Any, evidence: dict[str, Any]) -> bool:
    summary = _clean(evidence.get("summary") or evidence.get("text") or "")
    if not summary:
        return False
    if isinstance(result, dict) and result.get("agent_id") and result.get("summary"):
        return True
    lowered = summary.lower()
    has_summary = "summary:" in lowered or bool(summary)
    has_next = "next step" in lowered or "next:" in lowered or "complete" in lowered or evidence.get("has_next_step")
    has_risk = "risk" in lowered or evidence.get("has_risks")
    return bool(has_summary and has_next and has_risk)


def _satisfies_autonomous_coding_contract(result: Any, evidence: dict[str, Any]) -> bool:
    if not _satisfies_default_contract(result, evidence):
        return False
    if not isinstance(result, dict):
        return False
    if str(result.get("task_status") or "").lower() != "done":
        return False
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    workflow = metadata.get("workflow") if isinstance(metadata.get("workflow"), dict) else {}
    project_root = _clean(metadata.get("project_root") or metadata.get("root") or "")
    changed = [str(item) for item in result.get("changed") or [] if str(item).strip()]
    tested = [str(item) for item in result.get("tested") or [] if str(item).strip()]
    inspection = metadata.get("project_inspection") if isinstance(metadata.get("project_inspection"), dict) else workflow.get("inspection")
    execution_plan = metadata.get("execution_plan") if isinstance(metadata.get("execution_plan"), dict) else workflow.get("execution_plan")
    boundaries = metadata.get("responsibility_boundaries") if isinstance(metadata.get("responsibility_boundaries"), list) else workflow.get("responsibility_boundaries")
    verification = (
        metadata.get("scaffold_verification")
        if isinstance(metadata.get("scaffold_verification"), dict)
        else metadata.get("artifact_verification")
        if isinstance(metadata.get("artifact_verification"), dict)
        else workflow.get("verification")
        if isinstance(workflow.get("verification"), dict)
        else {}
    )
    if not isinstance(inspection, dict) or not inspection.get("summary"):
        return False
    if not isinstance(execution_plan, dict) or not execution_plan.get("flow"):
        return False
    if not isinstance(boundaries, list) or not boundaries:
        return False
    product_studio = metadata.get("product_studio") if isinstance(metadata.get("product_studio"), dict) else workflow.get("product_studio")
    if not isinstance(product_studio, dict):
        return False
    phases = product_studio.get("phases")
    report = product_studio.get("final_proof_report")
    if not isinstance(phases, list) or len(phases) < 10:
        return False
    if not isinstance(report, dict) or "market_ready" not in report or not isinstance(report.get("gaps"), list):
        return False
    if report.get("market_ready") and report.get("critical_gaps"):
        return False
    gate_results = metadata.get("product_studio_gates") if isinstance(metadata.get("product_studio_gates"), dict) else workflow.get("product_studio_gates")
    if not isinstance(gate_results, dict):
        gate_results = product_studio.get("gate_results") if isinstance(product_studio.get("gate_results"), dict) else {}
    if not _valid_product_studio_gates(gate_results):
        return False
    if (report.get("market_ready") or report.get("technical_ready")) and not gate_results.get("technical_ready"):
        return False
    if verification and verification.get("status") != "passed":
        return False
    if project_root and not Path(project_root).exists():
        return False
    existing_changed = [path for path in changed if Path(path).exists()]
    has_file_evidence = bool(project_root and Path(project_root).exists()) or bool(existing_changed)
    has_verification = bool(tested) or bool(verification.get("checks"))
    return bool(has_file_evidence and has_verification)


def _valid_product_studio_gates(gate_results: dict[str, Any]) -> bool:
    if not gate_results.get("attempted"):
        return False
    gates = gate_results.get("gates") if isinstance(gate_results.get("gates"), list) else gate_results.get("required_gate_statuses")
    if not isinstance(gates, list) or not gates:
        return False
    required = [gate for gate in gates if isinstance(gate, dict) and gate.get("required")]
    if not required:
        return False
    required_groups = {str(gate.get("group") or "").strip() for gate in required}
    if not (required_groups & {"install", "tests", "security", "browser", "preview", "general"}):
        return False
    if gate_results.get("technical_ready") and any(str(gate.get("status") or "") != "passed" for gate in required):
        return False
    return True


def _evidence_from_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        summary = _clean(result.get("summary") or result.get("output") or result)
        text = _clean(" ".join(str(value) for value in result.values() if isinstance(value, (str, int, float, bool))))
        return {
            "summary": summary,
            "text": text,
            "keys": sorted(str(key) for key in result.keys()),
            "has_next_step": bool(re.search(r"\bnext\s+step\b|\bnext:", f"{summary} {text}", re.IGNORECASE)),
            "has_risks": bool(re.search(r"\brisks?\b", f"{summary} {text}", re.IGNORECASE)),
        }
    text = _clean(result)
    return {
        "summary": text,
        "text": text,
        "keys": [],
        "has_next_step": bool(re.search(r"\bnext\s+step\b|\bnext:", text, re.IGNORECASE)),
        "has_risks": bool(re.search(r"\brisks?\b", text, re.IGNORECASE)),
    }


def _is_autonomous_coding_task(task: dict[str, Any]) -> bool:
    input_data = task.get("input") if isinstance(task.get("input"), dict) else {}
    if str(input_data.get("source") or "") == "autonomous_coding":
        return True
    return "autonomous coding" in _clean(task.get("title") or "").lower()


def _row_to_contract(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "task_id": int(row["task_id"]),
        "goal": str(row["goal"]),
        "success_criteria": _json_loads(row["success_criteria_json"], []),
        "tools_needed": _json_loads(row["tools_needed_json"], []),
        "risk_level": str(row["risk_level"]),
        "expected_output": str(row["expected_output"]),
        "verification_method": str(row["verification_method"]),
        "status": str(row["status"]),
        "evidence": _json_loads(row["evidence_json"], {}),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def _normalize_status(value: str) -> str:
    status = _clean(value).lower().replace(" ", "_")
    return status if status in VALID_STATUSES else "active"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=True)


def _json_loads(value: str, default: Any = None) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return [] if default is None else default


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

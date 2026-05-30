"""Durable Friday operating system for engineering/product-studio work."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import (
    engineering_discipline,
    execution_contracts,
    friday_memory,
    integration_registry,
    production_readiness,
    project_intelligence,
    project_scaffolds,
    style_profiles,
    task_files,
)
from core.config import DATA_DIR, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "friday_operating_system.sqlite3"
FRIDAY_OS_DIR = ".friday/os"
STATUSES = {"created", "inspecting", "planning", "building", "verifying", "fixing", "blocked", "technical_ready", "market_ready_blocked", "market_ready", "failed"}
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
            CREATE TABLE IF NOT EXISTS friday_os_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                request TEXT NOT NULL,
                root TEXT NOT NULL,
                target TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                production_run_id INTEGER,
                technical_ready INTEGER NOT NULL,
                market_ready INTEGER NOT NULL,
                steps_json TEXT NOT NULL,
                intelligence_json TEXT NOT NULL,
                architecture_json TEXT NOT NULL,
                approvals_json TEXT NOT NULL,
                gate_results_json TEXT NOT NULL,
                artifacts_json TEXT NOT NULL,
                gaps_json TEXT NOT NULL,
                preview_url TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_friday_os_status ON friday_os_runs(status, updated_at)")


def start(
    request: str,
    *,
    root: str | Path = "",
    target: str = "",
    production_profile: str = "auto",
    risk_level: str = "medium",
    max_fix_attempts: int = 0,
) -> dict[str, Any]:
    init_db()
    cleaned_request = _clean(request) or "Friday OS engineering run"
    base = resolve_coding_root(root)
    preflight_root = resolve_coding_root(target) if _clean(target) else base
    stack = project_scaffolds.detect_stack(f"{cleaned_request} {production_profile}")
    run_id = _insert_run(cleaned_request, base, target)
    steps = _default_steps()

    _set_step(steps, "understand", "running", "Inspecting project, stack, tests, and style profile.")
    _update_run(run_id, status="inspecting", steps=steps, summary=f"Friday OS run #{run_id} is inspecting the project.")
    preflight = engineering_discipline.preflight(preflight_root, cleaned_request, stack=stack)
    intelligence = preflight["intelligence"]
    _set_step(steps, "understand", "passed", intelligence.get("summary", "Inspection complete."))

    _set_step(steps, "plan", "running", "Preparing architecture and acceptance criteria.")
    _update_run(run_id, status="planning", steps=steps, intelligence=intelligence, architecture=preflight["architecture"], summary=f"Friday OS run #{run_id} is planning implementation.")
    architecture = preflight["architecture"]
    _set_step(steps, "plan", "passed", "Architecture, acceptance criteria, and responsibility boundaries recorded.")

    _set_step(steps, "implement", "running", "Delegating build/harden/test/preview flow to production readiness.")
    _update_run(run_id, status="building", steps=steps, architecture=architecture, summary=f"Friday OS run #{run_id} is building and hardening.")
    production_run = production_readiness.start(
        cleaned_request,
        root=base,
        target=target,
        production_profile=production_profile,
        risk_level=risk_level,
        max_fix_attempts=max_fix_attempts,
    )
    project_root = Path(production_run.get("root") or preflight_root).resolve()
    post_intelligence = project_intelligence.inspect_project(project_root, cleaned_request, stack=stack)
    style_evaluation = post_intelligence.get("style_evaluation") if isinstance(post_intelligence.get("style_evaluation"), dict) else {}
    task_packet = task_files.write_task_files(
        project_root,
        cleaned_request,
        run_id=run_id,
        intent={"recommended_action": "run_friday_os_product_studio", "risk_level": risk_level},
        preflight=preflight,
        architecture=architecture,
        research_context={},
        execution_plan={"flow": ["understand", "plan", "build", "verify", "prove", "remember"]},
    )
    _set_step(steps, "implement", "passed" if production_run.get("artifacts") else "blocked", production_run.get("summary", "Production readiness flow completed."))

    _set_step(steps, "verify", "running", "Checking gates, style, and proof artifacts.")
    os_artifacts = _write_os_proof(
        project_root,
        run_id=run_id,
        request=cleaned_request,
        preflight=preflight,
        intelligence=post_intelligence,
        production_run=production_run,
        style_evaluation=style_evaluation,
    )
    os_artifacts = [*task_packet.get("files", []), *os_artifacts]
    enriched = {
        "id": run_id,
        "root": str(project_root),
        "metadata": {"intelligence": post_intelligence, "architecture": architecture, "production_run": production_run, "proof_root": str(project_root / FRIDAY_OS_DIR)},
        "production_run": production_run,
        "artifacts": [*(production_run.get("artifacts") or []), *os_artifacts],
    }
    contract = execution_contracts.validate_run_evidence(enriched)
    gate_gaps = production_run.get("gaps") if isinstance(production_run.get("gaps"), list) else []
    style_gaps = style_evaluation.get("gaps") if isinstance(style_evaluation.get("gaps"), list) else []
    gaps = _dedupe([*gate_gaps, *style_gaps, *contract.get("gaps", [])])
    _set_step(steps, "verify", "passed" if not gaps and contract.get("ok") else "blocked", contract.get("summary", "Verification complete."))

    _set_step(steps, "prove", "passed" if contract.get("ok") else "blocked", "Friday OS proof artifacts written under .friday/os.")
    _set_step(steps, "remember", "running", "Writing durable non-secret run memory.")
    memory = friday_memory.remember(
        "friday_os_run",
        f"Friday OS run #{run_id}",
        production_run.get("summary") or contract.get("summary") or "Friday OS run completed.",
        root=project_root,
        tags=["engineering", "production", str(stack.get("stack") or "unknown")],
        confidence=0.86 if contract.get("ok") else 0.58,
        metadata={"run_id": run_id, "production_run_id": production_run.get("id"), "status": production_run.get("status"), "style_profile": (post_intelligence.get("style_profile") or {}).get("id")},
    )
    if (post_intelligence.get("style_profile") or {}).get("id"):
        friday_memory.remember(
            "style_profile",
            (post_intelligence["style_profile"]).get("id"),
            "Use this style profile when building similar projects.",
            root=project_root,
            tags=["style", "project_convention"],
            confidence=0.9,
            metadata={"profile": post_intelligence.get("style_profile")},
        )
    _set_step(steps, "remember", "passed", f"Memory event #{memory.get('id')} recorded.")

    status = _readiness_status(production_run, contract, gaps)
    summary = _summary(project_root.name, status, gaps, production_run)
    _update_run(
        run_id,
        root=project_root,
        status=status,
        summary=summary,
        production_run_id=int(production_run.get("id") or 0) or None,
        technical_ready=status in {"technical_ready", "market_ready_blocked", "market_ready"},
        market_ready=status == "market_ready",
        steps=steps,
        intelligence=post_intelligence,
        architecture=architecture,
        approvals=production_run.get("approvals") if isinstance(production_run.get("approvals"), dict) else {},
        gate_results=production_run.get("gate_results") if isinstance(production_run.get("gate_results"), dict) else {},
        artifacts=[*(production_run.get("artifacts") or []), *os_artifacts],
        gaps=gaps,
        preview_url=production_run.get("preview_url") or "",
        metadata={"preflight": preflight, "contract": contract, "production_run": production_run, "memory_id": memory.get("id"), "proof_root": str(project_root / FRIDAY_OS_DIR), "task_packet": task_packet},
    )
    return get_run(run_id) or {}


def get_run(run_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM friday_os_runs WHERE id=?", (int(run_id),)).fetchone()
    if not row:
        return None
    run = _row(row)
    production_id = int(run.get("production_run_id") or 0)
    if production_id:
        production_run = production_readiness.get_run(production_id)
        if production_run:
            run["production_run"] = production_run
            run["approvals"] = production_run.get("approvals") or run.get("approvals")
            run["gate_results"] = production_run.get("gate_results") or run.get("gate_results")
            run["preview_url"] = production_run.get("preview_url") or run.get("preview_url")
    return run


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM friday_os_runs ORDER BY id DESC LIMIT ?", (max(1, min(200, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status(limit: int = 8) -> dict[str, Any]:
    runs = recent(limit=limit)
    counts: dict[str, int] = {}
    for run in runs:
        counts[run["status"]] = counts.get(run["status"], 0) + 1
    return {
        "runs": runs,
        "counts": counts,
        "latest": runs[0] if runs else None,
        "habits": engineering_discipline.operating_habits(),
        "readiness_policy": engineering_discipline.readiness_policy(),
        "style_profiles": style_profiles.list_profiles(),
        "memory": friday_memory.status(limit=6),
        "integrations": integration_registry.status(),
        "summary": runs[0]["summary"] if runs else "No Friday OS runs yet.",
    }


def pause(run_id: int, note: str = "") -> dict[str, Any]:
    run = get_run(run_id)
    if not run:
        return {"ok": False, "summary": "Friday OS run not found."}
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    metadata["paused"] = True
    metadata["pause_note"] = _clean(note)
    _update_run(run_id, status="blocked", summary=f"Friday OS run #{run_id} paused.", metadata=metadata)
    return get_run(run_id) or {}


def resume(run_id: int) -> dict[str, Any]:
    run = get_run(run_id)
    if not run:
        return {"ok": False, "summary": "Friday OS run not found."}
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    metadata["paused"] = False
    production = run.get("production_run") if isinstance(run.get("production_run"), dict) else metadata.get("production_run") if isinstance(metadata.get("production_run"), dict) else {}
    status_value = _readiness_status(production, metadata.get("contract") if isinstance(metadata.get("contract"), dict) else {}, run.get("gaps") or [])
    _update_run(run_id, status=status_value, summary=f"Friday OS run #{run_id} resumed.", metadata=metadata)
    return get_run(run_id) or {}


def rerun_gates(run_id: int, *, failed_only: bool = True) -> dict[str, Any]:
    run = get_run(run_id)
    if not run:
        return {"ok": False, "summary": "Friday OS run not found."}
    production_id = int(run.get("production_run_id") or 0)
    if not production_id:
        return {"ok": False, "summary": "Run has no linked production readiness run."}
    _update_run(run_id, status="fixing", summary=f"Friday OS run #{run_id} is rerunning gates.")
    production_run = production_readiness.rerun_gates(production_id, failed_only=failed_only)
    root = Path(production_run.get("root") or run.get("root")).resolve()
    intelligence = project_intelligence.inspect_project(root, production_run.get("request") or run.get("request", ""), stack=production_run.get("stack") if isinstance(production_run.get("stack"), dict) else {})
    os_artifacts = _write_os_proof(
        root,
        run_id=run_id,
        request=run.get("request", ""),
        preflight=(run.get("metadata") or {}).get("preflight") if isinstance(run.get("metadata"), dict) else {},
        intelligence=intelligence,
        production_run=production_run,
        style_evaluation=intelligence.get("style_evaluation") if isinstance(intelligence.get("style_evaluation"), dict) else {},
    )
    enriched = {"id": run_id, "root": str(root), "metadata": {"intelligence": intelligence, "architecture": run.get("architecture"), "production_run": production_run, "proof_root": str(root / FRIDAY_OS_DIR)}, "production_run": production_run, "artifacts": [*(production_run.get("artifacts") or []), *os_artifacts]}
    contract = execution_contracts.validate_run_evidence(enriched)
    gaps = _dedupe([*(production_run.get("gaps") or []), *contract.get("gaps", [])])
    status_value = _readiness_status(production_run, contract, gaps)
    _update_run(
        run_id,
        root=root,
        status=status_value,
        summary=_summary(root.name, status_value, gaps, production_run),
        intelligence=intelligence,
        gate_results=production_run.get("gate_results") if isinstance(production_run.get("gate_results"), dict) else {},
        approvals=production_run.get("approvals") if isinstance(production_run.get("approvals"), dict) else {},
        artifacts=[*(production_run.get("artifacts") or []), *os_artifacts],
        gaps=gaps,
        preview_url=production_run.get("preview_url") or "",
        technical_ready=status_value in {"technical_ready", "market_ready_blocked", "market_ready"},
        market_ready=status_value == "market_ready",
        metadata={**(run.get("metadata") if isinstance(run.get("metadata"), dict) else {}), "production_run": production_run, "contract": contract, "last_rerun_failed_only": bool(failed_only)},
    )
    friday_memory.remember("verification_history", f"Friday OS rerun #{run_id}", production_run.get("summary") or "Gates rerun.", root=root, tags=["gates", "rerun"], metadata={"run_id": run_id, "failed_only": failed_only})
    return get_run(run_id) or {}


def approve(run_id: int, action: str, *, note: str = "") -> dict[str, Any]:
    run = get_run(run_id)
    if not run:
        return {"ok": False, "summary": "Friday OS run not found."}
    production_id = int(run.get("production_run_id") or 0)
    if not production_id:
        return {"ok": False, "summary": "Run has no linked production readiness run."}
    production_run = production_readiness.approve(production_id, action, note=note)
    gaps = production_run.get("gaps") if isinstance(production_run.get("gaps"), list) else []
    contract = (run.get("metadata") or {}).get("contract") if isinstance(run.get("metadata"), dict) else {}
    status_value = _readiness_status(production_run, contract if isinstance(contract, dict) else {}, gaps)
    _update_run(
        run_id,
        status=status_value,
        summary=_summary(Path(production_run.get("root") or run["root"]).name, status_value, gaps, production_run),
        approvals=production_run.get("approvals") if isinstance(production_run.get("approvals"), dict) else {},
        gaps=gaps,
        technical_ready=status_value in {"technical_ready", "market_ready_blocked", "market_ready"},
        market_ready=status_value == "market_ready",
        metadata={**(run.get("metadata") if isinstance(run.get("metadata"), dict) else {}), "production_run": production_run},
    )
    friday_memory.remember("approval", f"Approval: {action}", f"Approval recorded for Friday OS run #{run_id}.", root=production_run.get("root") or run.get("root"), tags=["approval", action], metadata={"run_id": run_id, "action": action})
    return get_run(run_id) or {}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM friday_os_runs")


def _insert_run(request: str, root: Path, target: str) -> int:
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO friday_os_runs(created_at, updated_at, request, root, target, status, summary, production_run_id, technical_ready, market_ready, steps_json, intelligence_json, architecture_json, approvals_json, gate_results_json, artifacts_json, gaps_json, preview_url, metadata_json)
            VALUES (?, ?, ?, ?, ?, 'created', ?, NULL, 0, 0, ?, '{}', '{}', '{}', '{}', '[]', '[]', '', '{}')
            """,
            (now, now, request, str(root), _clean(target), "Friday OS run created.", _json_dumps(_default_steps())),
        )
        return int(cursor.lastrowid)


def _update_run(
    run_id: int,
    *,
    root: str | Path | None = None,
    status: str | None = None,
    summary: str | None = None,
    production_run_id: int | None = None,
    technical_ready: bool | None = None,
    market_ready: bool | None = None,
    steps: list[dict[str, Any]] | None = None,
    intelligence: dict[str, Any] | None = None,
    architecture: dict[str, Any] | None = None,
    approvals: dict[str, Any] | None = None,
    gate_results: dict[str, Any] | None = None,
    artifacts: list[str] | None = None,
    gaps: list[str] | None = None,
    preview_url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    current = get_run(run_id)
    if not current:
        return
    values = {
        "root": str(root if root is not None else current.get("root") or ""),
        "status": _status(status if status is not None else current.get("status") or "failed"),
        "summary": _clean(summary if summary is not None else current.get("summary") or ""),
        "production_run_id": production_run_id if production_run_id is not None else current.get("production_run_id"),
        "technical_ready": 1 if (technical_ready if technical_ready is not None else current.get("technical_ready")) else 0,
        "market_ready": 1 if (market_ready if market_ready is not None else current.get("market_ready")) else 0,
        "steps_json": _json_dumps(steps if steps is not None else current.get("steps") or []),
        "intelligence_json": _json_dumps(intelligence if intelligence is not None else current.get("intelligence") or {}),
        "architecture_json": _json_dumps(architecture if architecture is not None else current.get("architecture") or {}),
        "approvals_json": _json_dumps(approvals if approvals is not None else current.get("approvals") or {}),
        "gate_results_json": _json_dumps(gate_results if gate_results is not None else current.get("gate_results") or {}),
        "artifacts_json": _json_dumps(_dedupe(artifacts if artifacts is not None else current.get("artifacts") or [])),
        "gaps_json": _json_dumps(_dedupe(gaps if gaps is not None else current.get("gaps") or [])),
        "preview_url": _clean(preview_url if preview_url is not None else current.get("preview_url") or ""),
        "metadata_json": _json_dumps(metadata if metadata is not None else current.get("metadata") or {}),
    }
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            """
            UPDATE friday_os_runs
            SET updated_at=?, root=?, status=?, summary=?, production_run_id=?, technical_ready=?, market_ready=?, steps_json=?, intelligence_json=?, architecture_json=?, approvals_json=?, gate_results_json=?, artifacts_json=?, gaps_json=?, preview_url=?, metadata_json=?
            WHERE id=?
            """,
            (
                _now(),
                values["root"],
                values["status"],
                values["summary"],
                values["production_run_id"],
                values["technical_ready"],
                values["market_ready"],
                values["steps_json"],
                values["intelligence_json"],
                values["architecture_json"],
                values["approvals_json"],
                values["gate_results_json"],
                values["artifacts_json"],
                values["gaps_json"],
                values["preview_url"],
                values["metadata_json"],
                int(run_id),
            ),
        )


def _write_os_proof(
    project_root: Path,
    *,
    run_id: int,
    request: str,
    preflight: dict[str, Any],
    intelligence: dict[str, Any],
    production_run: dict[str, Any],
    style_evaluation: dict[str, Any],
) -> list[str]:
    proof_root = project_root / FRIDAY_OS_DIR
    proof_root.mkdir(parents=True, exist_ok=True)
    gate_results = production_run.get("gate_results") if isinstance(production_run.get("gate_results"), dict) else {}
    artifacts = production_run.get("artifacts") if isinstance(production_run.get("artifacts"), list) else []
    files: dict[str, Any] = {
        "requirements.json": {"run_id": run_id, "request": request, "acceptance_criteria": preflight.get("acceptance_criteria") or engineering_discipline.acceptance_criteria(intelligence)},
        "architecture.json": preflight.get("architecture") or project_intelligence.architecture_decision(intelligence, request),
        "implementation-plan.json": preflight.get("execution_plan") or {},
        "changed-files.json": {"artifacts": artifacts, "style_profile": (intelligence.get("style_profile") or {}).get("id")},
        "gate-results.json": gate_results,
        "artifact-manifest.json": {"production_artifacts": artifacts, "os_proof_root": str(proof_root), "screenshots": _screenshots(gate_results), "logs": _logs(gate_results)},
        "security-report.md": _security_report(gate_results, style_evaluation),
        "performance-report.md": _performance_report(gate_results),
        "browser-report.md": _browser_report(gate_results),
        "launch-pack.md": _launch_pack(production_run),
        "final-proof-report.md": _final_proof(production_run, style_evaluation),
    }
    written = []
    for name, value in files.items():
        path = proof_root / name
        if name.endswith(".json"):
            path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        else:
            path.write_text(str(value).strip() + "\n", encoding="utf-8")
        written.append(str(path))
    return written


def _default_steps() -> list[dict[str, Any]]:
    return [
        {"id": "understand", "label": "Understand", "status": "pending", "summary": ""},
        {"id": "plan", "label": "Plan", "status": "pending", "summary": ""},
        {"id": "implement", "label": "Implement", "status": "pending", "summary": ""},
        {"id": "verify", "label": "Verify", "status": "pending", "summary": ""},
        {"id": "fix", "label": "Fix", "status": "pending", "summary": "Only runs when required gates fail and retry attempts are available."},
        {"id": "prove", "label": "Prove", "status": "pending", "summary": ""},
        {"id": "remember", "label": "Remember", "status": "pending", "summary": ""},
        {"id": "improve", "label": "Improve", "status": "pending", "summary": "Use stored failures and style profiles on future runs."},
    ]


def _set_step(steps: list[dict[str, Any]], step_id: str, status: str, summary: str) -> None:
    for step in steps:
        if step.get("id") == step_id:
            step["status"] = status
            step["summary"] = summary
            step["updated_at"] = _now()
            return


def _readiness_status(production_run: dict[str, Any], contract: dict[str, Any], gaps: list[Any]) -> str:
    if gaps and not production_run.get("technical_ready"):
        return "failed"
    if production_run.get("market_ready") and contract.get("ok", True):
        return "market_ready"
    if production_run.get("technical_ready") and not production_run.get("market_ready"):
        return "market_ready_blocked"
    if production_run.get("technical_ready"):
        return "technical_ready"
    if production_run.get("status") in {"building", "planned"}:
        return "building"
    return "failed"


def _summary(name: str, status: str, gaps: list[str], production_run: dict[str, Any]) -> str:
    if status == "market_ready":
        return f"{name} is market-ready with Friday OS proof, gates, memory, and approvals attached."
    if status in {"technical_ready", "market_ready_blocked"}:
        return f"{name} is technically ready; {len(gaps)} market/proof gap(s) remain."
    return production_run.get("summary") or f"{name} is not ready; {len(gaps)} gap(s) remain."


def _security_report(gate_results: dict[str, Any], style_evaluation: dict[str, Any]) -> str:
    lines = ["# Security Report", ""]
    for gate in gate_results.get("gates") or []:
        if gate.get("group") == "security":
            lines.append(f"- {gate.get('label')}: {gate.get('status')} - {gate.get('summary')}")
    if style_evaluation.get("gaps"):
        lines.extend(["", "Style/security maintainability gaps:", *[f"- {gap}" for gap in style_evaluation.get("gaps") or []]])
    return "\n".join(lines)


def _performance_report(gate_results: dict[str, Any]) -> str:
    lines = ["# Performance Report", ""]
    for gate in gate_results.get("gates") or []:
        if gate.get("group") == "performance" or "build" in str(gate.get("command") or "").lower():
            lines.append(f"- {gate.get('label')}: {gate.get('status')} - {gate.get('summary')}")
    return "\n".join(lines)


def _browser_report(gate_results: dict[str, Any]) -> str:
    lines = ["# Browser Report", ""]
    for gate in gate_results.get("gates") or []:
        if gate.get("group") in {"browser", "preview"}:
            lines.append(f"- {gate.get('label')}: {gate.get('status')} - {gate.get('summary')}")
            if gate.get("screenshot"):
                lines.append(f"  Screenshot: {gate.get('screenshot')}")
    return "\n".join(lines)


def _launch_pack(production_run: dict[str, Any]) -> str:
    product_studio = production_run.get("product_studio") if isinstance(production_run.get("product_studio"), dict) else {}
    assets = product_studio.get("launch_assets") if isinstance(product_studio.get("launch_assets"), dict) else {}
    approvals = production_run.get("approvals") if isinstance(production_run.get("approvals"), dict) else {}
    lines = ["# Launch Pack", "", f"Positioning: {assets.get('positioning', '')}", "", "Approvals:"]
    lines.extend(f"- {key}: {'approved' if value.get('approved') else 'blocked'}" for key, value in approvals.items())
    return "\n".join(lines)


def _final_proof(production_run: dict[str, Any], style_evaluation: dict[str, Any]) -> str:
    gap_lines = [f"- {gap}" for gap in _dedupe([*(production_run.get("gaps") or []), *(style_evaluation.get("gaps") or [])])]
    if not gap_lines:
        gap_lines = ["- None"]
    lines = [
        "# Friday OS Final Proof",
        "",
        f"Status: {production_run.get('status')}",
        f"Technical ready: {production_run.get('technical_ready')}",
        f"Market ready: {production_run.get('market_ready')}",
        f"Preview URL: {production_run.get('preview_url') or ''}",
        f"Gate summary: {(production_run.get('gate_results') or {}).get('summary', '') if isinstance(production_run.get('gate_results'), dict) else ''}",
        f"Style summary: {style_evaluation.get('summary', '')}",
        "",
        "Gaps:",
        *gap_lines,
    ]
    return "\n".join(lines)


def _screenshots(gate_results: dict[str, Any]) -> list[str]:
    return [str(gate.get("screenshot")) for gate in gate_results.get("gates") or [] if gate.get("screenshot")]


def _logs(gate_results: dict[str, Any]) -> list[str]:
    return [str(gate.get("log_path")) for gate in gate_results.get("gates") or [] if gate.get("log_path")]


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "request": str(row["request"]),
        "root": str(row["root"]),
        "target": str(row["target"]),
        "status": str(row["status"]),
        "summary": str(row["summary"]),
        "production_run_id": int(row["production_run_id"]) if row["production_run_id"] is not None else None,
        "technical_ready": bool(row["technical_ready"]),
        "market_ready": bool(row["market_ready"]),
        "steps": _json_loads(row["steps_json"], []),
        "intelligence": _json_loads(row["intelligence_json"], {}),
        "architecture": _json_loads(row["architecture_json"], {}),
        "approvals": _json_loads(row["approvals_json"], {}),
        "gate_results": _json_loads(row["gate_results_json"], {}),
        "artifacts": _json_loads(row["artifacts_json"], []),
        "gaps": _json_loads(row["gaps_json"], []),
        "preview_url": str(row["preview_url"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _status(value: str) -> str:
    clean = _clean(value).lower()
    return clean if clean in STATUSES else "failed"


def _dedupe(items: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        clean = _clean(item)
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()

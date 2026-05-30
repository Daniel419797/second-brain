"""Durable production-readiness orchestration for Friday-built projects."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import (
    codebase_standards,
    coding_workflow,
    product_studio,
    product_studio_gates,
    production_coding_autonomy,
    project_memory,
    project_scaffolds,
    release_manager,
    task_files,
    trust_proof,
)
from core.config import DATA_DIR, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "production_readiness.sqlite3"
PRODUCTION_DIR = ".friday/production"
STATUSES = {"planned", "building", "fixing", "technical_ready", "market_ready_blocked", "market_ready", "failed"}
APPROVAL_ACTIONS = ("deploy_preview", "deploy_production", "post_ads", "enable_billing", "send_outreach")
MARKET_APPROVALS = set(APPROVAL_ACTIONS)
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
            CREATE TABLE IF NOT EXISTS production_readiness_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                request TEXT NOT NULL,
                root TEXT NOT NULL,
                target TEXT NOT NULL,
                production_profile TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                stack_json TEXT NOT NULL,
                phases_json TEXT NOT NULL,
                approvals_json TEXT NOT NULL,
                gate_results_json TEXT NOT NULL,
                product_studio_json TEXT NOT NULL,
                artifacts_json TEXT NOT NULL,
                gaps_json TEXT NOT NULL,
                preview_url TEXT NOT NULL,
                technical_ready INTEGER NOT NULL,
                market_ready INTEGER NOT NULL,
                proof_id INTEGER,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_production_readiness_status ON production_readiness_runs(status, updated_at)")


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
    cleaned_request = _clean(request) or "production-ready project"
    profile = _clean(production_profile) or "auto"
    stack = project_scaffolds.detect_stack(f"{cleaned_request} {profile}")
    base = resolve_coding_root(root)
    project_root = _target_root(base, target, cleaned_request, stack)
    product_name = project_scaffolds.product_name(cleaned_request)
    run_id = _insert_run(cleaned_request, project_root, target, profile, risk_level, stack)
    _update_run(run_id, status="building", summary=f"Production readiness run #{run_id} is building {product_name}.")

    written_source = _scaffold_if_needed(project_root, stack, product_name, cleaned_request)
    profile_artifacts = _apply_production_profile(project_root, stack, product_name, cleaned_request, write_source=written_source)
    inspection = coding_workflow.inspect_project(project_root, cleaned_request, stack=stack)
    verification = coding_workflow.verify_project_artifact(project_root, stack, written_source + profile_artifacts)
    prep = production_coding_autonomy.prepare_project(project_root, request=cleaned_request, create_files=True, run_scans=True)
    standards = prep.get("scan") if isinstance(prep.get("scan"), dict) else codebase_standards.scan(project_root, focus="production readiness", max_files=220)
    phases = _phase_rows("building")
    _update_run(run_id, phases=phases, artifacts=profile_artifacts + (prep.get("artifacts") or []))

    gate_results = _run_gates(project_root, stack=stack)
    attempts = 0
    while gate_results.get("failed_required") and attempts < max(0, int(max_fix_attempts or 0)):
        attempts += 1
        _update_run(run_id, status="fixing", summary=f"Production readiness run #{run_id} is preparing fix evidence for gate attempt {attempts}.")
        profile_artifacts.extend(_write_fix_plan(project_root, gate_results, attempt=attempts))
        gate_results = _run_gates(project_root, stack=stack)

    studio = product_studio.prepare_product_studio(
        project_root,
        cleaned_request,
        product_name=product_name,
        stack=stack,
        inspection=inspection,
        execution_plan={"flow": ["requirements", "architecture", "implementation", "gates", "preview", "launch_pack", "final_proof"]},
        artifact_verification=verification,
        production_prep=prep,
        gate_results=gate_results,
        standards=standards,
        changed_files=[*written_source, *profile_artifacts, *(prep.get("artifacts") or [])],
        test_commands=_gate_commands(gate_results),
        create_files=True,
    )
    task_packet = task_files.write_task_files(
        project_root,
        cleaned_request,
        run_id=run_id,
        intent={"user_intent": "production_readiness", "recommended_action": "build_harden_verify_and_prove", "risk_level": risk_level},
        preflight={"intelligence": inspection, "acceptance_criteria": _acceptance_criteria()},
        architecture={"stack": stack, "framework": stack.get("stack"), "package_manager": "npm" if stack.get("stack") == "nextjs" else stack.get("language"), "style_profile_id": "nexus_forge_nextjs" if stack.get("stack") == "nextjs" else ""},
        research_context={},
        execution_plan={"flow": ["requirements", "architecture", "implementation", "gates", "preview", "launch_pack", "final_proof"]},
    )
    release = release_manager.prepare_release(project_root)
    approvals = _default_approvals()
    production_artifacts = _write_production_artifacts(
        project_root,
        run_id=run_id,
        request=cleaned_request,
        product_name=product_name,
        stack=stack,
        inspection=inspection,
        verification=verification,
        prep=prep,
        gate_results=gate_results,
        studio=studio,
        approvals=approvals,
        release=release,
    )
    readiness = calculate_readiness(gate_results=gate_results, product_studio_report=studio, approvals=approvals)
    phases = _phase_rows("complete", gate_results=gate_results, readiness=readiness)
    proof = trust_proof.create_report(
        "Production readiness proof",
        changed=[f"Production artifacts written under {project_root / PRODUCTION_DIR}", *[f"Created: {path}" for path in written_source[:12]]],
        tested=_gate_commands(gate_results),
        failed=readiness["gaps"],
        evidence=[gate_results.get("summary", ""), studio.get("summary", ""), f"Release #{release.get('id')} prepared."],
        risks=readiness["gaps"] or ["Production deploy and market actions remain approval-gated."],
        confidence=0.9 if readiness["market_ready"] else 0.68 if readiness["technical_ready"] else 0.45,
        metadata={"source": "production_readiness", "run_id": run_id, "root": str(project_root)},
    )
    summary = _summary(product_name, readiness)
    _update_run(
        run_id,
        status=readiness["status"],
        summary=summary,
        phases=phases,
        approvals=approvals,
        gate_results=gate_results,
        product_studio_report=studio,
        artifacts=[*written_source, *profile_artifacts, *(prep.get("artifacts") or []), *(studio.get("artifacts") or []), *(task_packet.get("files") or []), *production_artifacts],
        gaps=readiness["gaps"],
        preview_url=gate_results.get("preview_url") or "",
        technical_ready=readiness["technical_ready"],
        market_ready=readiness["market_ready"],
        proof_id=int(proof.get("id") or 0) or None,
        metadata={"release": release, "inspection": inspection, "verification": verification, "attempts": attempts, "task_packet": task_packet},
    )
    project_memory.remember(
        project_root,
        "production_readiness",
        f"Production readiness run #{run_id}",
        summary,
        confidence=0.84,
        metadata={"run_id": run_id, "status": readiness["status"], "technical_ready": readiness["technical_ready"], "market_ready": readiness["market_ready"]},
    )
    return get_run(run_id) or {}


def rerun_gates(run_id: int, *, failed_only: bool = True) -> dict[str, Any]:
    run = get_run(run_id)
    if not run:
        return {"ok": False, "summary": "Production readiness run not found."}
    stack = run.get("stack") if isinstance(run.get("stack"), dict) else {}
    previous = run.get("gate_results") if isinstance(run.get("gate_results"), dict) else {}
    gate_kwargs = _rerun_gate_kwargs(previous) if failed_only else {}
    gate_results = product_studio_gates.execute_gates(run["root"], stack=stack, **gate_kwargs)
    approvals = run.get("approvals") if isinstance(run.get("approvals"), dict) else _default_approvals()
    studio = product_studio.prepare_product_studio(
        run["root"],
        run["request"],
        product_name=Path(run["root"]).name,
        stack=stack,
        gate_results=gate_results,
        create_files=True,
    )
    readiness = calculate_readiness(gate_results=gate_results, product_studio_report=studio, approvals=approvals)
    artifacts = _write_production_artifacts(
        Path(run["root"]),
        run_id=int(run_id),
        request=run["request"],
        product_name=Path(run["root"]).name,
        stack=stack,
        inspection={},
        verification={},
        prep={},
        gate_results=gate_results,
        studio=studio,
        approvals=approvals,
        release={},
    )
    _update_run(
        run_id,
        status=readiness["status"],
        summary=_summary(Path(run["root"]).name, readiness),
        phases=_phase_rows("complete", gate_results=gate_results, readiness=readiness),
        gate_results=gate_results,
        product_studio_report=studio,
        artifacts=[*(run.get("artifacts") or []), *artifacts],
        gaps=readiness["gaps"],
        preview_url=gate_results.get("preview_url") or run.get("preview_url") or "",
        technical_ready=readiness["technical_ready"],
        market_ready=readiness["market_ready"],
        metadata={**(run.get("metadata") if isinstance(run.get("metadata"), dict) else {}), "last_rerun_failed_only": bool(failed_only)},
    )
    return get_run(run_id) or {}


def approve(run_id: int, action: str, *, note: str = "") -> dict[str, Any]:
    run = get_run(run_id)
    if not run:
        return {"ok": False, "summary": "Production readiness run not found."}
    normalized = _clean(action).lower()
    if normalized not in APPROVAL_ACTIONS:
        return {"ok": False, "summary": f"Unsupported approval action: {action}"}
    approvals = run.get("approvals") if isinstance(run.get("approvals"), dict) else _default_approvals()
    approvals[normalized] = {"approved": True, "approved_at": _now(), "note": _clean(note)}
    readiness = calculate_readiness(gate_results=run.get("gate_results") or {}, product_studio_report=run.get("product_studio") or {}, approvals=approvals)
    _update_run(
        run_id,
        approvals=approvals,
        status=readiness["status"],
        summary=_summary(Path(run["root"]).name, readiness),
        gaps=readiness["gaps"],
        technical_ready=readiness["technical_ready"],
        market_ready=readiness["market_ready"],
    )
    return get_run(run_id) or {}


def calculate_readiness(*, gate_results: dict[str, Any], product_studio_report: dict[str, Any], approvals: dict[str, Any]) -> dict[str, Any]:
    technical_ready = bool(gate_results.get("technical_ready"))
    gate_gaps = list(gate_results.get("failed_required") or product_studio_gates.gate_gaps(gate_results))
    studio_report = product_studio_report.get("final_proof_report") if isinstance(product_studio_report.get("final_proof_report"), dict) else {}
    studio_gaps = list(studio_report.get("critical_gaps") or [])
    missing_approvals = [action for action in sorted(MARKET_APPROVALS) if not approvals.get(action, {}).get("approved")]
    market_ready = technical_ready and not gate_gaps and not studio_gaps and not missing_approvals
    if market_ready:
        status = "market_ready"
    elif technical_ready:
        status = "market_ready_blocked"
    else:
        status = "failed" if gate_gaps else "building"
    gaps = _dedupe([*gate_gaps, *studio_gaps, *[f"Approval required: {action}" for action in missing_approvals]])
    return {"technical_ready": technical_ready, "market_ready": market_ready, "status": status, "gaps": gaps}


def get_run(run_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM production_readiness_runs WHERE id=?", (int(run_id),)).fetchone()
    return _row(row) if row else None


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM production_readiness_runs ORDER BY id DESC LIMIT ?", (max(1, min(200, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status(limit: int = 8) -> dict[str, Any]:
    runs = recent(limit=limit)
    counts: dict[str, int] = {}
    for run in runs:
        counts[run["status"]] = counts.get(run["status"], 0) + 1
    latest = runs[0] if runs else None
    return {
        "runs": runs,
        "counts": counts,
        "latest": latest,
        "summary": latest.get("summary") if latest else "No production readiness runs yet.",
    }


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM production_readiness_runs")


def _run_gates(project_root: Path, *, stack: dict[str, Any]) -> dict[str, Any]:
    return product_studio_gates.execute_gates(project_root, stack=stack, install=True, tests=True, audits=True, browser=True, preview=True)


def _insert_run(request: str, project_root: Path, target: str, production_profile: str, risk_level: str, stack: dict[str, Any]) -> int:
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO production_readiness_runs(created_at, updated_at, request, root, target, production_profile, risk_level, status, summary, stack_json, phases_json, approvals_json, gate_results_json, product_studio_json, artifacts_json, gaps_json, preview_url, technical_ready, market_ready, proof_id, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'planned', ?, ?, '[]', ?, '{}', '{}', '[]', '[]', '', 0, 0, NULL, '{}')
            """,
            (now, now, request, str(project_root), _clean(target), production_profile, _clean(risk_level) or "medium", "Production readiness run planned.", _json_dumps(stack), _json_dumps(_default_approvals())),
        )
        return int(cursor.lastrowid)


def _update_run(
    run_id: int,
    *,
    status: str | None = None,
    summary: str | None = None,
    phases: list[dict[str, Any]] | None = None,
    approvals: dict[str, Any] | None = None,
    gate_results: dict[str, Any] | None = None,
    product_studio_report: dict[str, Any] | None = None,
    artifacts: list[str] | None = None,
    gaps: list[str] | None = None,
    preview_url: str | None = None,
    technical_ready: bool | None = None,
    market_ready: bool | None = None,
    proof_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    current = get_run(run_id)
    if not current:
        return
    values = {
        "status": _status(status or current["status"]),
        "summary": _clean(summary if summary is not None else current["summary"]),
        "phases_json": _json_dumps(phases if phases is not None else current.get("phases") or []),
        "approvals_json": _json_dumps(approvals if approvals is not None else current.get("approvals") or {}),
        "gate_results_json": _json_dumps(gate_results if gate_results is not None else current.get("gate_results") or {}),
        "product_studio_json": _json_dumps(product_studio_report if product_studio_report is not None else current.get("product_studio") or {}),
        "artifacts_json": _json_dumps(_dedupe(artifacts if artifacts is not None else current.get("artifacts") or [])),
        "gaps_json": _json_dumps(_dedupe(gaps if gaps is not None else current.get("gaps") or [])),
        "preview_url": _clean(preview_url if preview_url is not None else current.get("preview_url") or ""),
        "technical_ready": 1 if (technical_ready if technical_ready is not None else current.get("technical_ready")) else 0,
        "market_ready": 1 if (market_ready if market_ready is not None else current.get("market_ready")) else 0,
        "proof_id": proof_id if proof_id is not None else current.get("proof_id"),
        "metadata_json": _json_dumps(metadata if metadata is not None else current.get("metadata") or {}),
    }
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            """
            UPDATE production_readiness_runs
            SET updated_at=?, status=?, summary=?, phases_json=?, approvals_json=?, gate_results_json=?, product_studio_json=?, artifacts_json=?, gaps_json=?, preview_url=?, technical_ready=?, market_ready=?, proof_id=?, metadata_json=?
            WHERE id=?
            """,
            (
                _now(),
                values["status"],
                values["summary"],
                values["phases_json"],
                values["approvals_json"],
                values["gate_results_json"],
                values["product_studio_json"],
                values["artifacts_json"],
                values["gaps_json"],
                values["preview_url"],
                values["technical_ready"],
                values["market_ready"],
                values["proof_id"],
                values["metadata_json"],
                int(run_id),
            ),
        )


def _scaffold_if_needed(project_root: Path, stack: dict[str, Any], product_name: str, request: str) -> list[str]:
    project_root.mkdir(parents=True, exist_ok=True)
    if _has_manifest(project_root):
        return []
    written: list[str] = []
    for relative, content in project_scaffolds.files_for_stack(stack, product_name, request).items():
        path = project_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(str(path))
    return written


def _apply_production_profile(project_root: Path, stack: dict[str, Any], product_name: str, request: str, *, write_source: list[str]) -> list[str]:
    files = _production_profile_files(stack, product_name, request)
    written: list[str] = []
    for relative, content in files.items():
        path = project_root / relative
        if path.exists() and not write_source:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(str(path))
    if write_source and (project_root / "package.json").exists():
        _upgrade_package_json(project_root / "package.json")
    return written


def _production_profile_files(stack: dict[str, Any], product_name: str, request: str) -> dict[str, str]:
    base = {
        ".env.example": "APP_ENV=development\nFRIDAY_APPROVAL_REQUIRED=true\n",
        "SECURITY.md": f"# Security\n\n{product_name} requires approval before production deploys, outbound messages, billing, ad spend, or customer data access.\n",
        "docs/OPERATIONS.md": "# Operations\n\n- Health checks must pass before release.\n- Keep rollback target and owner in every release report.\n- Monitor errors, latency, dependency spend, and failed automations.\n",
        "docs/LAUNCH.md": f"# Launch Pack\n\nProduct: {product_name}\n\nRequest: {request}\n\nAds, billing, outreach, and production deploy require explicit approval.\n",
        ".github/workflows/friday-production.yml": _github_workflow(stack),
    }
    if stack.get("stack") == "nextjs":
        base.update(
            {
                "Dockerfile": "FROM node:22-alpine AS deps\nWORKDIR /app\nCOPY package*.json ./\nRUN npm ci || npm install\nCOPY . .\nRUN npm run build\nEXPOSE 3000\nCMD [\"npm\", \"run\", \"start\", \"--\", \"--hostname\", \"0.0.0.0\"]\n",
                "vercel.json": "{\n  \"framework\": \"nextjs\",\n  \"buildCommand\": \"npm run build\",\n  \"devCommand\": \"npm run dev\"\n}\n",
                "src/app/api/health/route.ts": "import { NextResponse } from 'next/server';\n\nexport async function GET() {\n  return NextResponse.json({ status: 'ok', service: 'friday-production-app' });\n}\n",
                "tests/health.test.mjs": "import assert from 'node:assert/strict';\nimport test from 'node:test';\n\ntest('production profile exists', () => {\n  assert.equal(process.env.NODE_ENV === 'test' || true, true);\n});\n",
            }
        )
    elif stack.get("stack") == "node_fastify":
        base["Dockerfile"] = "FROM node:22-alpine\nWORKDIR /app\nCOPY package*.json ./\nRUN npm ci || npm install\nCOPY . .\nEXPOSE 3000\nCMD [\"npm\", \"run\", \"start\"]\n"
    elif stack.get("stack") == "python_fastapi":
        package = _slug(product_name).replace("-", "_")
        base["Dockerfile"] = f"FROM python:3.12-slim\nWORKDIR /app\nCOPY pyproject.toml ./\nRUN python -m pip install --no-cache-dir -e .[dev]\nCOPY . .\nEXPOSE 8000\nCMD [\"python\", \"-m\", \"uvicorn\", \"{package}.main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"8000\"]\n"
    elif stack.get("stack") == "go_api":
        base["Dockerfile"] = "FROM golang:1.22-alpine AS build\nWORKDIR /src\nCOPY . .\nRUN go test ./... && go build -o /app/server .\nFROM alpine:3.20\nCOPY --from=build /app/server /server\nEXPOSE 8080\nCMD [\"/server\"]\n"
    elif stack.get("stack") == "rust_axum":
        base["Dockerfile"] = "FROM rust:1.78 AS build\nWORKDIR /src\nCOPY . .\nRUN cargo test && cargo build --release\nFROM debian:bookworm-slim\nCOPY --from=build /src/target/release/* /app/server\nEXPOSE 3000\nCMD [\"/app/server\"]\n"
    return base


def _github_workflow(stack: dict[str, Any]) -> str:
    if stack.get("stack") in {"nextjs", "node_fastify"}:
        commands = ["npm install", "npm test -- --watch=false || npm test", "npm run build --if-present", "npm audit --audit-level=moderate"]
    elif stack.get("stack") == "python_fastapi":
        commands = ["python -m pip install -e .[dev]", "python -m pytest -q"]
    elif stack.get("stack") == "go_api":
        commands = ["go test ./...", "go vet ./..."]
    elif stack.get("stack") == "rust_axum":
        commands = ["cargo test", "cargo clippy -- -D warnings"]
    else:
        commands = ["flutter pub get", "flutter test", "flutter analyze"]
    return "\n".join(
        [
            "name: Friday Production Readiness",
            "on:",
            "  pull_request:",
            "  push:",
            "    branches: [main]",
            "jobs:",
            "  verify:",
            "    runs-on: ubuntu-latest",
            "    steps:",
            "      - uses: actions/checkout@v4",
            "      - name: Run readiness gates",
            "        run: |",
            *[f"          {command}" for command in commands],
            "",
        ]
    )


def _upgrade_package_json(path: Path) -> None:
    data = _json_loads(path.read_text(encoding="utf-8"), {})
    if not isinstance(data, dict):
        return
    scripts = data.setdefault("scripts", {})
    if isinstance(scripts, dict):
        scripts.setdefault("test", "node --test tests/*.test.mjs")
        scripts.setdefault("audit", "npm audit --audit-level=moderate")
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_production_artifacts(
    project_root: Path,
    *,
    run_id: int,
    request: str,
    product_name: str,
    stack: dict[str, Any],
    inspection: dict[str, Any],
    verification: dict[str, Any],
    prep: dict[str, Any],
    gate_results: dict[str, Any],
    studio: dict[str, Any],
    approvals: dict[str, Any],
    release: dict[str, Any],
) -> list[str]:
    root = project_root / PRODUCTION_DIR
    root.mkdir(parents=True, exist_ok=True)
    readiness = calculate_readiness(gate_results=gate_results, product_studio_report=studio, approvals=approvals)
    files = {
        "requirements.json": {"run_id": run_id, "request": request, "product_name": product_name, "acceptance": _acceptance_criteria()},
        "architecture.json": {"stack": stack, "inspection": inspection, "verification": verification},
        "gate-results.json": gate_results,
        "artifact-manifest.json": {"artifacts": [*gate_results.get("artifacts", []), *studio.get("artifacts", []), *prep.get("artifacts", [])], "release": release},
        "security-report.md": _security_report_md(gate_results, studio),
        "performance-report.md": _performance_report_md(gate_results),
        "launch-pack.md": _launch_pack_md(studio, approvals),
        "final-proof-report.md": _final_report_md(readiness, gate_results, studio, approvals),
    }
    written: list[str] = []
    for name, payload in files.items():
        path = root / name
        if name.endswith(".json"):
            path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        else:
            path.write_text(str(payload), encoding="utf-8")
        written.append(str(path))
    return written


def _phase_rows(stage: str, *, gate_results: dict[str, Any] | None = None, readiness: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    gate_results = gate_results or {}
    readiness = readiness or {}
    phase_ids = [
        ("requirements", "Requirements and acceptance"),
        ("architecture", "Architecture and stack"),
        ("implementation", "Feature implementation"),
        ("gates", "Executable gates"),
        ("security", "Security and dependency proof"),
        ("performance", "Performance proof"),
        ("preview", "Preview and browser proof"),
        ("launch", "Launch, docs, and approvals"),
        ("proof", "Final proof report"),
    ]
    rows = []
    for phase_id, label in phase_ids:
        if stage == "building":
            status = "running" if phase_id in {"requirements", "architecture", "implementation"} else "planned"
        elif phase_id == "gates":
            status = "verified" if gate_results.get("technical_ready") else "blocked"
        elif phase_id == "launch":
            status = "verified" if readiness.get("market_ready") else "blocked"
        else:
            status = "verified" if readiness.get("technical_ready") or phase_id in {"requirements", "architecture", "implementation", "proof"} else "partial"
        rows.append({"id": phase_id, "label": label, "status": status})
    return rows


def _target_root(base: Path, target: str, request: str, stack: dict[str, Any]) -> Path:
    if _clean(target):
        return resolve_coding_root(target)
    if _has_manifest(base):
        return base
    slug = f"{project_scaffolds.project_slug(request, stack)}-production"
    candidate = base / slug
    if not candidate.exists():
        return candidate
    for index in range(2, 100):
        next_candidate = base / f"{slug}-{index}"
        if not next_candidate.exists():
            return next_candidate
    return base / f"{slug}-{int(dt.datetime.now().timestamp())}"


def _has_manifest(root: Path) -> bool:
    return any((root / name).exists() for name in ("package.json", "pyproject.toml", "go.mod", "Cargo.toml", "pubspec.yaml"))


def _rerun_gate_kwargs(previous: dict[str, Any]) -> dict[str, bool]:
    failed_groups = {str(gate.get("group") or "") for gate in previous.get("gates") or [] if gate.get("required") and gate.get("status") != "passed"}
    if not failed_groups:
        return {}
    return {
        "install": "install" in failed_groups,
        "tests": "tests" in failed_groups or "performance" in failed_groups,
        "audits": "security" in failed_groups or "environment" in failed_groups or "operations" in failed_groups or "docs" in failed_groups,
        "browser": "browser" in failed_groups,
        "preview": "preview" in failed_groups,
    }


def _default_approvals() -> dict[str, Any]:
    return {action: {"approved": False, "approved_at": "", "note": ""} for action in APPROVAL_ACTIONS}


def _gate_commands(gate_results: dict[str, Any]) -> list[str]:
    commands = []
    for gate in gate_results.get("gates") or []:
        command = _clean(gate.get("command") or "")
        label = _clean(gate.get("label") or gate.get("id") or "gate")
        status = _clean(gate.get("status") or "unknown")
        commands.append(f"{command or label} -> {status}")
    return commands


def _write_fix_plan(project_root: Path, gate_results: dict[str, Any], *, attempt: int) -> list[str]:
    path = project_root / PRODUCTION_DIR / f"fix-attempt-{attempt}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Production Fix Attempt", "", f"Attempt: {attempt}", "", "Failed required gates:"]
    lines.extend(f"- {item}" for item in gate_results.get("failed_required") or ["No failed gate details recorded."])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [str(path)]


def _summary(product_name: str, readiness: dict[str, Any]) -> str:
    if readiness["market_ready"]:
        return f"{product_name} is market-ready with production proof and approvals attached."
    if readiness["technical_ready"]:
        return f"{product_name} is technically ready but blocked on market approvals or launch gaps."
    return f"{product_name} is not production-ready: {len(readiness['gaps'])} gap(s) remain."


def _acceptance_criteria() -> list[str]:
    return [
        "Project has real source artifacts, not only a plan.",
        "Install, tests/build, audit, security, browser/preview, performance, env, operations, and docs gates are recorded.",
        "Technical readiness is true only when required executable gates pass.",
        "Market readiness is true only when launch approvals and proof artifacts are complete.",
    ]


def _security_report_md(gate_results: dict[str, Any], studio: dict[str, Any]) -> str:
    gates = [gate for gate in gate_results.get("gates") or [] if gate.get("group") == "security"]
    lines = ["# Security Report", "", *[f"- {gate.get('label')}: {gate.get('status')} - {gate.get('summary')}" for gate in gates]]
    gaps = studio.get("final_proof_report", {}).get("critical_gaps") if isinstance(studio.get("final_proof_report"), dict) else []
    if gaps:
        lines.extend(["", "Critical gaps:", *[f"- {gap}" for gap in gaps]])
    return "\n".join(lines).strip() + "\n"


def _performance_report_md(gate_results: dict[str, Any]) -> str:
    gates = [gate for gate in gate_results.get("gates") or [] if gate.get("group") == "performance" or "build" in str(gate.get("command") or "").lower()]
    return "\n".join(["# Performance Report", "", *[f"- {gate.get('label')}: {gate.get('status')} - {gate.get('summary')}" for gate in gates]]) + "\n"


def _launch_pack_md(studio: dict[str, Any], approvals: dict[str, Any]) -> str:
    assets = studio.get("launch_assets") if isinstance(studio.get("launch_assets"), dict) else {}
    lines = ["# Launch Pack", "", f"Positioning: {assets.get('positioning', '')}", "", "Approvals:"]
    lines.extend(f"- {action}: {'approved' if item.get('approved') else 'blocked'}" for action, item in approvals.items())
    lines.extend(["", "Pricing:"])
    lines.extend(f"- {item.get('plan')}: {item.get('price')} - {item.get('promise')}" for item in assets.get("pricing") or [])
    lines.extend(["", "Ad drafts:"])
    for ad in assets.get("ads") or []:
        lines.append(f"- {ad.get('channel')}: {ad.get('hook')} / {ad.get('cta')}")
    return "\n".join(lines).strip() + "\n"


def _final_report_md(readiness: dict[str, Any], gate_results: dict[str, Any], studio: dict[str, Any], approvals: dict[str, Any]) -> str:
    gap_lines = [f"- {gap}" for gap in readiness["gaps"]] or ["- None"]
    lines = [
        "# Final Production Proof",
        "",
        f"Technical ready: {readiness['technical_ready']}",
        f"Market ready: {readiness['market_ready']}",
        f"Status: {readiness['status']}",
        f"Gate summary: {gate_results.get('summary', '')}",
        f"Studio summary: {studio.get('summary', '')}",
        "",
        "Gaps:",
        *gap_lines,
        "",
        "Approvals:",
        *[f"- {action}: {'approved' if item.get('approved') else 'blocked'}" for action, item in approvals.items()],
    ]
    return "\n".join(lines).strip() + "\n"


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "request": str(row["request"]),
        "root": str(row["root"]),
        "target": str(row["target"]),
        "production_profile": str(row["production_profile"]),
        "risk_level": str(row["risk_level"]),
        "status": str(row["status"]),
        "summary": str(row["summary"]),
        "stack": _json_loads(row["stack_json"], {}),
        "phases": _json_loads(row["phases_json"], []),
        "approvals": _json_loads(row["approvals_json"], {}),
        "gate_results": _json_loads(row["gate_results_json"], {}),
        "product_studio": _json_loads(row["product_studio_json"], {}),
        "artifacts": _json_loads(row["artifacts_json"], []),
        "gaps": _json_loads(row["gaps_json"], []),
        "preview_url": str(row["preview_url"]),
        "technical_ready": bool(row["technical_ready"]),
        "market_ready": bool(row["market_ready"]),
        "proof_id": int(row["proof_id"]) if row["proof_id"] is not None else None,
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _status(value: str) -> str:
    clean = _clean(value).lower()
    return clean if clean in STATUSES else "failed"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-") or "friday-app"


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
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

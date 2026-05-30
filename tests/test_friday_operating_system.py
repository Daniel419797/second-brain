from pathlib import Path

from core import (
    execution_contracts,
    friday_memory,
    friday_operating_system,
    integration_registry,
    project_scaffolds,
    style_profiles,
)


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(friday_operating_system, "DB_PATH", tmp_path / "friday_os.sqlite3")
    monkeypatch.setattr(friday_memory, "DB_PATH", tmp_path / "friday_memory.sqlite3")
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(integration_registry, "DB_PATH", tmp_path / "integrations.sqlite3")


def _write_next_project(root: Path, request: str = "Build a web-app for operators") -> None:
    stack = project_scaffolds.detect_stack(request)
    files = project_scaffolds.files_for_stack(stack, "OpsPilot", request)
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _fake_production_run(root: Path, *, run_id: int = 42, technical_ready: bool = True) -> dict:
    gate_path = root / ".friday" / "product-studio" / "gates" / "gate-results.json"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text("{}", encoding="utf-8")
    return {
        "id": run_id,
        "request": "Build a web-app for operators",
        "root": str(root),
        "status": "market_ready_blocked" if technical_ready else "failed",
        "summary": "Fake production run completed.",
        "technical_ready": technical_ready,
        "market_ready": False,
        "preview_url": "http://127.0.0.1:3999",
        "approvals": {"deploy_preview": {"approved": False}},
        "gaps": ["Approval required: deploy_preview"] if technical_ready else ["tests failed"],
        "stack": {"stack": "nextjs", "label": "Next.js web app", "language": "typescript"},
        "gate_results": {
            "attempted": True,
            "technical_ready": technical_ready,
            "failed_required": [] if technical_ready else ["tests failed"],
            "summary": "Gate proof attached.",
            "gates": [
                {"id": "dependencies_install", "label": "Dependency install", "group": "install", "status": "passed", "required": True},
                {"id": "browser_check", "label": "Browser check", "group": "browser", "status": "passed", "required": True, "screenshot": str(root / ".friday" / "shot.png")},
            ],
            "artifacts": [str(gate_path)],
        },
        "product_studio": {"launch_assets": {"positioning": "Operators get proof-first automation."}},
        "artifacts": [str(gate_path)],
    }


def test_style_profile_rejects_messy_nextjs_blob(tmp_path):
    root = tmp_path / "messy"
    (root / "src/app").mkdir(parents=True)
    (root / "src/components").mkdir(parents=True)
    (root / "next.config.mjs").write_text("export default {};\n", encoding="utf-8")
    (root / "src/app/page.tsx").write_text("'use client';\nimport { useState } from 'react';\nexport default function Page(){ const [x]=useState(1); return <div>{x}</div>; }\n", encoding="utf-8")
    (root / "src/components/WorkspaceConsole.tsx").write_text("export function WorkspaceConsole(){ return null; }\n", encoding="utf-8")

    result = style_profiles.evaluate_project(root, "nexus_forge_nextjs")

    assert result["ok"] is False
    assert any("Missing required style path" in gap for gap in result["gaps"])
    assert any("forbidden" in gap.lower() or "flat blob" in gap.lower() for gap in result["gaps"])


def test_execution_contract_requires_inspection_and_proof():
    result = execution_contracts.validate_run_evidence(
        {
            "artifacts": [],
            "gate_results": {"attempted": True, "technical_ready": True},
            "production_run": {"technical_ready": True, "market_ready": False},
        }
    )

    assert result["ok"] is False
    assert result["technical_ready"] is False
    assert any("inspection" in gap.lower() for gap in result["gaps"])


def test_friday_os_start_writes_memory_and_os_proof(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    project_root = tmp_path / "ops"

    def fake_start(request, **kwargs):
        _write_next_project(project_root, request)
        return _fake_production_run(project_root)

    monkeypatch.setattr(friday_operating_system.production_readiness, "start", fake_start)
    monkeypatch.setattr(friday_operating_system.production_readiness, "get_run", lambda run_id: _fake_production_run(project_root, run_id=run_id))

    run = friday_operating_system.start("Build a web-app for operators", root=tmp_path, target=str(project_root))

    assert run["status"] == "market_ready_blocked"
    assert run["technical_ready"] is True
    assert (project_root / ".friday" / "os" / "requirements.json").exists()
    assert (project_root / ".friday" / "os" / "final-proof-report.md").exists()
    assert friday_memory.status()["counts"]["friday_os_run"] >= 1


def test_friday_os_rerun_passes_failed_only(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    project_root = tmp_path / "ops"

    monkeypatch.setattr(friday_operating_system.production_readiness, "start", lambda request, **kwargs: (_write_next_project(project_root, request) or _fake_production_run(project_root)))
    monkeypatch.setattr(friday_operating_system.production_readiness, "get_run", lambda run_id: _fake_production_run(project_root, run_id=run_id))
    run = friday_operating_system.start("Build a web-app for operators", root=tmp_path, target=str(project_root))
    captured = []

    def fake_rerun(run_id, *, failed_only=True):
        captured.append(failed_only)
        return _fake_production_run(project_root, run_id=run_id)

    monkeypatch.setattr(friday_operating_system.production_readiness, "rerun_gates", fake_rerun)

    friday_operating_system.rerun_gates(run["id"], failed_only=True)

    assert captured == [True]

from pathlib import Path

from core import codebase_standards, production_readiness, project_memory, release_manager, task_contracts, trust_proof


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(production_readiness, "DB_PATH", tmp_path / "production_readiness.sqlite3")
    monkeypatch.setattr(project_memory, "DB_PATH", tmp_path / "project_memory.sqlite3")
    monkeypatch.setattr(codebase_standards, "DB_PATH", tmp_path / "codebase_standards.sqlite3")
    monkeypatch.setattr(release_manager, "DB_PATH", tmp_path / "release_manager.sqlite3")
    monkeypatch.setattr(trust_proof, "DB_PATH", tmp_path / "trust_proof.sqlite3")
    monkeypatch.setattr(task_contracts, "DB_PATH", tmp_path / "task_contracts.sqlite3")
    monkeypatch.setattr(production_readiness, "_should_run_live_design_critique", lambda stack: False)


def _passing_gates(root, *, stack, **_kwargs):
    return {
        "attempted": True,
        "root": str(root),
        "status": "passed",
        "summary": "Executed 9 production gate(s): all required gates passed.",
        "technical_ready": True,
        "market_ready": False,
        "preview_url": "http://127.0.0.1:3456",
        "failed_required": [],
        "approval_gates_cleared": False,
        "artifacts": [],
        "gates": [
            {"id": "dependencies_install", "label": "Dependency install", "group": "install", "status": "passed", "required": True},
            {"id": "test_1", "label": "Check: npm run build", "group": "tests", "status": "passed", "required": True},
            {"id": "dependency_audit", "label": "Dependency audit", "group": "security", "status": "passed", "required": True},
            {"id": "secret_scan", "label": "Secret scan", "group": "security", "status": "passed", "required": True},
            {"id": "browser_check", "label": "Browser check", "group": "browser", "status": "passed", "required": True, "screenshot": str(Path(root) / "shot.png")},
            {"id": "browser_quality", "label": "Browser quality", "group": "browser", "status": "passed", "required": True},
            {"id": "deployment_preview", "label": "Deployment preview", "group": "preview", "status": "passed", "required": True},
            {"id": "performance_budget", "label": "Performance budget", "group": "performance", "status": "passed", "required": True},
            {"id": "environment_validation", "label": "Environment validation", "group": "environment", "status": "passed", "required": True},
        ],
    }


def test_readiness_requires_gates_and_approvals():
    approvals = production_readiness._default_approvals()

    blocked = production_readiness.calculate_readiness(
        gate_results={"technical_ready": False, "failed_required": ["tests failed"]},
        product_studio_report={"final_proof_report": {"critical_gaps": []}},
        approvals=approvals,
    )
    assert blocked["technical_ready"] is False
    assert blocked["market_ready"] is False
    assert blocked["status"] == "failed"

    approved = {key: {"approved": True} for key in approvals}
    ready = production_readiness.calculate_readiness(
        gate_results={"technical_ready": True, "failed_required": []},
        product_studio_report={"final_proof_report": {"critical_gaps": []}},
        approvals=approved,
    )
    assert ready["technical_ready"] is True
    assert ready["market_ready"] is True
    assert ready["status"] == "market_ready"


def test_readiness_blocks_technical_ready_when_studio_design_handoff_fails():
    approvals = {action: {"approved": True} for action in production_readiness.APPROVAL_ACTIONS}

    readiness = production_readiness.calculate_readiness(
        gate_results={"technical_ready": True, "failed_required": []},
        product_studio_report={
            "final_proof_report": {
                "technical_ready": False,
                "critical_gaps": ["Configured design handoff requires a successful provider-selected design before technical-ready claims"],
            }
        },
        approvals=approvals,
    )

    assert readiness["technical_ready"] is False
    assert readiness["market_ready"] is False
    assert readiness["status"] == "building"


def test_start_creates_durable_run_and_production_artifacts(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(production_readiness, "_run_gates", _passing_gates)

    run = production_readiness.start("Build a web-app for customer followups", root=tmp_path)

    project_root = Path(run["root"])
    assert run["id"] > 0
    assert run["technical_ready"] is True
    assert run["market_ready"] is False
    assert run["status"] == "market_ready_blocked"
    assert run["metadata"]["workflow_phases"] == [
        "requirements_architecture",
        "scaffold_profile",
        "inspect_prepare_design",
        "gates_fix",
        "studio_docs",
        "proof_finalize",
    ]
    assert run["metadata"]["workflow_backend"] in {"langgraph", "native"}
    assert (project_root / ".friday" / "production" / "requirements.json").exists()
    assert (project_root / ".friday" / "production" / "final-proof-report.md").exists()
    assert (project_root / "SECURITY.md").exists()
    assert production_readiness.get_run(run["id"])["summary"] == run["summary"]

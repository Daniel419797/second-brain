import json
from pathlib import Path

from core import audit_log, autonomous_coding, codebase_standards, product_studio, project_memory, self_update, task_contracts, task_queue, trust_proof


def _isolate_common(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(task_contracts, "DB_PATH", tmp_path / "contracts.sqlite3")
    monkeypatch.setattr(project_memory, "DB_PATH", tmp_path / "project_memory.sqlite3")
    monkeypatch.setattr(codebase_standards, "DB_PATH", tmp_path / "standards.sqlite3")
    monkeypatch.setattr(trust_proof, "DB_PATH", tmp_path / "proof.sqlite3")
    monkeypatch.setattr(audit_log, "DB_PATH", tmp_path / "audit.sqlite3")
    monkeypatch.setattr(autonomous_coding, "_execute_product_studio_gates", _fake_product_studio_gates)


def _fake_product_studio_gates(project_root, *, stack, install):
    gate_root = Path(project_root) / ".friday" / "product-studio" / "gates"
    gate_root.mkdir(parents=True, exist_ok=True)
    gate_path = gate_root / "gate-results.json"
    result = {
        "attempted": True,
        "root": str(project_root),
        "status": "attention",
        "summary": "Executed 5 product-studio gate(s): 3 passed, 2 required gap(s).",
        "technical_ready": False,
        "market_ready": False,
        "preview_url": "",
        "approval_gates_cleared": False,
        "failed_required": [
            "Browser check: blocked - Playwright is not installed in the test isolate.",
            "Deployment preview: blocked - No preview URL was available in the test isolate.",
        ],
        "gates": [
            {"id": "dependencies_install", "label": "Dependency install", "group": "install", "status": "passed", "required": True, "command": "npm install" if install else ""},
            {"id": "test_1", "label": "Check: npm run build", "group": "tests", "status": "passed", "required": True, "command": "npm run build"},
            {"id": "dependency_audit", "label": "Dependency audit", "group": "security", "status": "passed", "required": True, "command": "npm audit --audit-level=moderate"},
            {"id": "browser_check", "label": "Browser check", "group": "browser", "status": "blocked", "required": True, "summary": "Playwright is not installed in the test isolate."},
            {"id": "deployment_preview", "label": "Deployment preview", "group": "preview", "status": "blocked", "required": True, "summary": "No preview URL was available in the test isolate."},
        ],
        "artifacts": [str(gate_path)],
    }
    result["required_gate_statuses"] = result["gates"]
    gate_path.write_text(json.dumps(result), encoding="utf-8")
    return result


def test_autonomous_coding_scaffolds_new_app(monkeypatch, tmp_path):
    _isolate_common(monkeypatch, tmp_path)

    result = autonomous_coding.start("Build a web-app HackOnVibe AI-assisted everyday tool", root=str(tmp_path))

    project_root = Path(result["execution"]["metadata"]["project_root"])
    assert result["task"]["status"] == "done"
    assert (project_root / "package.json").exists()
    assert (project_root / "src" / "app" / "page.tsx").exists()
    assert (project_root / "src" / "components" / "Workspace" / "WorkspaceConsole.tsx").exists()
    assert (project_root / "src" / "services" / "BriefService.ts").exists()
    assert (project_root / "src" / "store" / "workspaceStore.ts").exists()
    assert (project_root / "FRONTEND_STRUCTURE.md").exists()
    assert (project_root / "src" / "lib" / "productPlan.ts").exists()
    assert (project_root / "src" / "app" / "api" / "brief" / "route.ts").exists()
    assert (project_root / ".friday" / "ci-plan.yml").exists()
    assert (project_root / ".friday" / "product-studio" / "requirements.md").exists()
    assert (project_root / ".friday" / "product-studio" / "proof-report.md").exists()
    assert result["contract"]["status"] == "verified"
    assert result["execution"]["metadata"]["stack"]["stack"] == "nextjs"
    assert result["execution"]["metadata"]["scaffold_verification"]["status"] == "passed"
    assert result["execution"]["metadata"]["product_studio_gates"]["attempted"] is True
    assert (project_root / ".friday" / "product-studio" / "gates" / "gate-results.json").exists()
    assert result["execution"]["metadata"]["product_studio"]["phases"]
    assert result["execution"]["metadata"]["product_studio"]["final_proof_report"]["market_ready"] is False
    assert any("browser" in gap.lower() for gap in result["execution"]["metadata"]["product_studio"]["gaps"])
    assert result["execution"]["metadata"]["project_inspection"]["summary"]
    assert result["execution"]["metadata"]["execution_plan"]["flow"]
    assert result["execution"]["metadata"]["responsibility_boundaries"]
    assert any("verified file exists" in item for item in result["execution"]["tested"])
    assert "executed product-studio gates" in result["summary"]


def test_autonomous_coding_scaffolds_flutter_mobile_app(monkeypatch, tmp_path):
    _isolate_common(monkeypatch, tmp_path)

    result = autonomous_coding.start("Build a mobile app for shop invoices", root=str(tmp_path))

    project_root = Path(result["execution"]["metadata"]["project_root"])
    assert result["task"]["status"] == "done"
    assert (project_root / "pubspec.yaml").exists()
    assert (project_root / "lib" / "main.dart").exists()
    assert (project_root / "lib" / "home_screen.dart").exists()
    assert (project_root / "lib" / "workflow_store.dart").exists()
    assert result["contract"]["status"] == "verified"
    assert result["execution"]["metadata"]["stack"]["stack"] == "flutter"


def test_autonomous_coding_contract_rejects_missing_project_root(monkeypatch, tmp_path):
    _isolate_common(monkeypatch, tmp_path)
    task_id = task_queue.create_task(
        "Autonomous coding: build app",
        agent_id="senior_developer",
        input_data={"source": "autonomous_coding"},
    )
    task = task_queue.get_task(task_id)

    verified = task_contracts.verify_contract(
        task,
        {
            "agent_id": "senior_developer",
            "task_status": "done",
            "summary": "Summary: done. Next step: review. Risks: not installed.",
            "next_step": "review",
            "risks": ["not installed"],
            "changed": [],
            "tested": ["reported only"],
            "metadata": {"project_root": str(tmp_path / "missing-project")},
        },
    )

    assert verified["status"] == "unsatisfied"


def test_autonomous_coding_contract_requires_product_studio_proof(monkeypatch, tmp_path):
    _isolate_common(monkeypatch, tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()
    task_id = task_queue.create_task(
        "Autonomous coding: build app",
        agent_id="senior_developer",
        input_data={"source": "autonomous_coding"},
    )
    task = task_queue.get_task(task_id)

    verified = task_contracts.verify_contract(
        task,
        {
            "agent_id": "senior_developer",
            "task_status": "done",
            "summary": "Summary: done. Next step: review. Risks: not installed.",
            "next_step": "review",
            "risks": ["not installed"],
            "changed": [str(project_root)],
            "tested": ["verified file exists: README.md"],
            "metadata": {
                "project_root": str(project_root),
                "project_inspection": {"summary": "inspected"},
                "execution_plan": {"flow": ["inspect_project_shape"]},
                "responsibility_boundaries": [{"owner": "README.md", "rule": "docs"}],
                "scaffold_verification": {"status": "passed", "checks": ["verified project root exists"]},
                "product_studio": {
                    "phases": [{"id": f"phase-{index}", "status": "verified"} for index in range(10)],
                    "final_proof_report": {"market_ready": False, "technical_ready": False, "gaps": ["missing gates"]},
                },
            },
        },
    )

    assert verified["status"] == "unsatisfied"


def test_product_studio_writes_market_readiness_artifacts(tmp_path):
    project_root = tmp_path / "studio"
    project_root.mkdir()

    studio = product_studio.prepare_product_studio(
        project_root,
        "Build a web-app for operators",
        product_name="OpsPilot",
        stack={"stack": "nextjs", "label": "Next.js web app", "language": "typescript"},
        artifact_verification={"status": "passed", "summary": "Artifact verification passed."},
        changed_files=[str(project_root / "README.md")],
        test_commands=["npm run build"],
    )

    assert studio["market_ready"] is False
    assert len(studio["phases"]) >= 12
    assert (project_root / ".friday" / "product-studio" / "launch-assets.md").exists()
    assert (project_root / ".friday" / "product-studio" / "studio-plan.json").exists()
    assert any("approval" in gate for gate in studio["final_proof_report"]["approval_gates"])


def test_product_studio_uses_executed_gates_for_technical_readiness(tmp_path):
    project_root = tmp_path / "studio-gated"
    project_root.mkdir()
    gate_results = {
        "attempted": True,
        "status": "passed",
        "technical_ready": True,
        "approval_gates_cleared": False,
        "preview_url": "http://127.0.0.1:3456",
        "failed_required": [],
        "gates": [
            {"id": "dependencies_install", "label": "Dependency install", "group": "install", "status": "passed", "required": True},
            {"id": "test_1", "label": "Check: npm run build", "group": "tests", "status": "passed", "required": True},
            {"id": "dependency_audit", "label": "Dependency audit", "group": "security", "status": "passed", "required": True},
            {"id": "browser_check", "label": "Browser check", "group": "browser", "status": "passed", "required": True, "screenshot": str(project_root / "shot.png")},
            {"id": "deployment_preview", "label": "Deployment preview", "group": "preview", "status": "passed", "required": True},
        ],
    }

    studio = product_studio.prepare_product_studio(
        project_root,
        "Build a web-app for operators",
        product_name="OpsPilot",
        stack={"stack": "nextjs", "label": "Next.js web app", "language": "typescript"},
        artifact_verification={"status": "passed", "summary": "Artifact verification passed."},
        gate_results=gate_results,
        changed_files=[str(project_root / "README.md")],
        test_commands=["npm run build"],
    )

    statuses = {phase["id"]: phase["status"] for phase in studio["phases"]}
    assert studio["final_proof_report"]["technical_ready"] is True
    assert studio["final_proof_report"]["market_ready"] is False
    assert statuses["unit_integration_e2e_tests"] == "verified"
    assert statuses["security_dependency_scan"] == "verified"
    assert statuses["ux_browser_verification"] == "verified"
    assert statuses["deployment_preview_release"] == "verified"


def test_autonomous_coding_remaps_stale_root_desktop_task(monkeypatch, tmp_path):
    _isolate_common(monkeypatch, tmp_path)
    repo = tmp_path / "workspace" / "second-brain"
    repo.mkdir(parents=True)
    monkeypatch.setattr(autonomous_coding, "ROOT_DIR", repo)

    task_id = task_queue.create_task(
        "Autonomous coding: build web-app",
        agent_id="senior_developer",
        input_data={
            "source": "autonomous_coding",
            "request": "Build a web-app HackOnVibe AI-assisted everyday tool",
            "root": "/root/Desktop",
            "risk_level": "low",
        },
    )
    task = task_queue.get_task(task_id)

    result = autonomous_coding.run_task(task)
    project_root = Path(result["metadata"]["project_root"])

    assert result["task_status"] == "done"
    assert project_root.is_relative_to(repo.parent / "friday-projects")
    assert (project_root / "package.json").exists()


def test_approved_self_update_task_stages_llm_change(monkeypatch, tmp_path):
    _isolate_common(monkeypatch, tmp_path)
    root = tmp_path / "repo"
    target = root / "core" / "sample.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 'old'\n", encoding="utf-8")
    monkeypatch.setattr(self_update, "ROOT_DIR", root)
    monkeypatch.setattr(self_update, "DB_PATH", tmp_path / "self_updates.sqlite3")
    monkeypatch.setattr(self_update, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(
        self_update,
        "config_value",
        lambda key, default=None: {
            "self_update_task_priority": 2,
            "self_update_run_tests": False,
            "self_update_max_file_bytes": 240000,
            "self_update_max_change_bytes": 120000,
            "self_update_max_repo_summary_files": 100,
            "self_update_max_file_candidates": 100,
        }.get(key, default),
    )
    monkeypatch.setattr(
        autonomous_coding.llm,
        "ask_simple_with_provider_chain",
        lambda prompt, providers, retries=1: json.dumps(
            {
                "changes": [
                    {
                        "path": "core/sample.py",
                        "find_text": "VALUE = 'old'\n",
                        "replace_text": "VALUE = 'new'\n",
                        "summary": "Update sample value.",
                    }
                ]
            }
        ),
    )

    proposal = self_update.create_proposal("change sample value")
    approved = self_update.approve_update(proposal["id"], proposal["approval_phrase"])
    task = task_queue.get_task(int(approved["task_id"]))

    result = autonomous_coding.run_task(task)

    update = self_update.get_update(proposal["id"])
    assert "Prepared 1 staged change" in result["summary"]
    assert update["changes"][0]["path"].replace("\\", "/") == "core/sample.py"
    assert target.read_text(encoding="utf-8") == "VALUE = 'old'\n"

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
    monkeypatch.setattr(autonomous_coding, "_should_run_live_design_critique", lambda stack: False)


def _fake_product_studio_gates(project_root, *, stack, install, request=""):
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
    assert result["task"]["status"] == "blocked"
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
    assert result["contract"]["status"] == "active"
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
    assert not any("verified file exists" in item for item in result["execution"]["tested"])
    assert result["execution"]["metadata"]["artifact_checks"]
    assert "did not mark it done" in result["summary"]


def test_autonomous_coding_scaffolds_bare_dashboard_request(monkeypatch, tmp_path):
    _isolate_common(monkeypatch, tmp_path)

    result = autonomous_coding.start("a university management dashboard", root=str(tmp_path))

    project_root = Path(result["execution"]["metadata"]["project_root"])
    assert result["task"]["status"] == "blocked"
    assert project_root.name == "university-management-web"
    assert (project_root / "package.json").exists()
    assert result["execution"]["metadata"]["stack"]["stack"] == "nextjs"
    assert result["execution"]["metadata"]["scaffold_verification"]["status"] == "passed"


def test_autonomous_coding_blocks_before_gates_when_required_design_handoff_fails(monkeypatch, tmp_path):
    _isolate_common(monkeypatch, tmp_path)
    monkeypatch.setattr(autonomous_coding, "_should_run_live_design_critique", lambda stack: True)

    def fail_if_gates_run(*args, **kwargs):
        raise AssertionError("install/build gates should not run after required design handoff failure")

    monkeypatch.setattr(autonomous_coding, "_execute_product_studio_gates", fail_if_gates_run)
    monkeypatch.setattr(
        product_studio,
        "prepare_design_handoff",
        lambda *args, **kwargs: {
            "ok": False,
            "status": "partial",
            "summary": "Prepared 4 website page design run(s); 0/4 selected handoff(s).",
            "frontend_handoff_allowed": False,
            "design_plan": {},
            "design_critique": {
                "summary": "Prepared 4 website page design run(s); 0/4 selected handoff(s).",
                "pages": [
                    {"label": "Home", "status": "failed", "frontend_handoff_allowed": False, "summary": "Stitch SDK failed: fetch failed"},
                    {"label": "About", "status": "skipped", "frontend_handoff_allowed": False, "summary": "Skipped because the configured design provider failed earlier."},
                ],
            },
            "applied_design": {},
            "artifacts": [str(tmp_path / "stitch-run.log")],
        },
    )

    result = autonomous_coding.start(
        "Build a normal website for a real construction company: Turner Construction Company. Run desktop and mobile screenshots.",
        root=str(tmp_path),
    )

    project_root = Path(result["execution"]["metadata"]["project_root"])
    assert result["task"]["status"] == "blocked"
    assert result["execution"]["metadata"]["stack"]["stack"] == "nextjs"
    assert result["execution"]["metadata"]["project_name"] == "Turner Construction Company"
    assert result["execution"]["metadata"]["product_studio_gates"]["gates"][0]["id"] == "design_provider_handoff"
    assert (project_root / ".friday" / "product-studio" / "gates" / "gate-results.json").exists()
    assert any("Design provider handoff blocked" in item for item in result["execution"]["failed"])
    assert "npm run build" in result["execution"]["metadata"]["discovered_checks"]
    assert "npm run build" not in result["execution"]["tested"]
    assert "executable gates were skipped" in result["execution"]["summary"].lower()


def test_autonomous_coding_scaffolds_flutter_mobile_app(monkeypatch, tmp_path):
    _isolate_common(monkeypatch, tmp_path)

    result = autonomous_coding.start("Build a mobile app for shop invoices", root=str(tmp_path))

    project_root = Path(result["execution"]["metadata"]["project_root"])
    assert result["task"]["status"] == "blocked"
    assert (project_root / "pubspec.yaml").exists()
    assert (project_root / "lib" / "main.dart").exists()
    assert (project_root / "lib" / "home_screen.dart").exists()
    assert (project_root / "lib" / "workflow_store.dart").exists()
    assert result["contract"]["status"] == "active"
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


def test_product_studio_live_design_critique_is_approval_gated(monkeypatch, tmp_path):
    project_root = tmp_path / "studio-design"
    project_root.mkdir()
    artifact = project_root / ".friday" / "design" / "frontend-handoff.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("# Handoff\n", encoding="utf-8")
    captured = {}

    def fake_config(key, default=None):
        values = {
            "design_external_calls_require_approval": True,
            "autonomy_preapprove_design_preview": True,
        }
        return values.get(key, default)

    def fake_run(request, *, root="", product_name="", stack=None, variant_count=None, dry_run=True):
        captured["dry_run"] = dry_run
        captured["product_name"] = product_name
        return {
            "ok": True,
            "status": "selected",
            "summary": "Selected dispatch command center with score 91/100.",
            "frontend_handoff_allowed": True,
            "selected_variant": {"id": "dispatch", "label": "Dispatch command center", "score": 91},
            "artifacts": [str(artifact)],
        }

    monkeypatch.setattr(product_studio, "config_value", fake_config)
    monkeypatch.setattr(product_studio.design_providers, "run_design_critique_loop", fake_run)

    studio = product_studio.prepare_product_studio(
        project_root,
        "Build a web-app for field service dispatch.",
        product_name="Field Service Dispatch OS",
        stack={"stack": "nextjs", "label": "Next.js web app", "language": "typescript"},
        artifact_verification={"status": "passed", "summary": "Artifact verification passed."},
        changed_files=[str(project_root / "README.md")],
        test_commands=["npm run build"],
        run_live_design_critique=True,
        applied_design={"ok": True, "artifacts": [str(project_root / "src" / "components" / "Stitch" / "StitchDesignSurface.tsx")]},
    )

    critique = studio["final_proof_report"]["evidence"]["design_critique"]
    assert captured["dry_run"] is False
    assert captured["product_name"] == "Field Service Dispatch OS"
    assert critique["auto_run"] is True
    assert critique["frontend_handoff_allowed"] is True
    assert str(artifact) in studio["artifacts"]


def test_product_studio_blocks_technical_ready_when_required_design_handoff_fails(monkeypatch, tmp_path):
    project_root = tmp_path / "studio-design-blocked"
    project_root.mkdir()
    gate_results = {
        "attempted": True,
        "status": "passed",
        "technical_ready": True,
        "approval_gates_cleared": False,
        "failed_required": [],
        "gates": [
            {"id": "browser_check", "label": "Browser check", "group": "browser", "status": "passed", "required": True},
            {"id": "deployment_preview", "label": "Deployment preview", "group": "preview", "status": "passed", "required": True},
            {"id": "test_1", "label": "Check: npm run build", "group": "tests", "status": "passed", "required": True},
            {"id": "dependency_audit", "label": "Dependency audit", "group": "security", "status": "passed", "required": True},
        ],
    }

    monkeypatch.setattr(
        product_studio.design_providers,
        "run_design_critique_loop",
        lambda *args, **kwargs: {
            "ok": False,
            "status": "timeout",
            "summary": "Stitch SDK timed out after 300 seconds.",
            "frontend_handoff_allowed": False,
            "stitch_required": True,
            "artifacts": [],
        },
    )

    studio = product_studio.prepare_product_studio(
        project_root,
        "Build a web-app for field service dispatch.",
        product_name="Field Service Dispatch OS",
        stack={"stack": "nextjs", "label": "Next.js web app", "language": "typescript"},
        artifact_verification={"status": "passed", "summary": "Artifact verification passed."},
        gate_results=gate_results,
        run_live_design_critique=True,
    )

    statuses = {phase["id"]: phase["status"] for phase in studio["phases"]}
    assert studio["final_proof_report"]["technical_ready"] is False
    assert statuses["ux_browser_verification"] == "blocked"
    assert any("design handoff" in gap.lower() for gap in studio["final_proof_report"]["gaps"])
    assert "design-provider handoff" in studio["final_proof_report"]["next_step"]


def test_product_studio_accepts_rendered_visual_proof_when_stitch_is_not_required(monkeypatch, tmp_path):
    project_root = tmp_path / "studio-rendered-proof"
    project_root.mkdir()
    gate_results = {
        "attempted": True,
        "status": "passed",
        "technical_ready": True,
        "approval_gates_cleared": False,
        "failed_required": [],
        "gates": [
            {"id": "browser_check", "label": "Browser check", "group": "browser", "status": "passed", "required": True},
            {"id": "browser_quality", "label": "Browser quality", "group": "browser", "status": "passed", "required": True},
            {"id": "browser_visual_review", "label": "Browser visual review", "group": "browser", "status": "passed", "required": True},
            {"id": "ux_copy_quality", "label": "UX copy quality", "group": "ux", "status": "passed", "required": True},
            {"id": "deployment_preview", "label": "Deployment preview", "group": "preview", "status": "passed", "required": True},
            {"id": "test_1", "label": "Check: npm run build", "group": "tests", "status": "passed", "required": True},
            {"id": "dependency_audit", "label": "Dependency audit", "group": "security", "status": "passed", "required": True},
        ],
    }

    def fake_config(key, default=None):
        values = {
            "design_frontend_handoff_required": True,
            "design_stitch_required_for_web": False,
        }
        return values.get(key, default)

    monkeypatch.setattr(product_studio, "config_value", fake_config)

    studio = product_studio.prepare_product_studio(
        project_root,
        "Build a web-app dashboard for permit operations.",
        product_name="Permitflow Command Workspace",
        stack={"stack": "nextjs", "label": "Next.js web app", "language": "typescript"},
        artifact_verification={"status": "passed", "summary": "Artifact verification passed."},
        gate_results=gate_results,
        run_live_design_critique=True,
        design_critique={
            "auto_run": True,
            "status": "timeout",
            "summary": "Stitch SDK timed out after 90 seconds.",
            "frontend_handoff_allowed": False,
            "stitch_required": False,
            "artifacts": [],
        },
    )

    statuses = {phase["id"]: phase["status"] for phase in studio["phases"]}
    assert studio["final_proof_report"]["technical_ready"] is True
    assert studio["final_proof_report"]["market_ready"] is False
    assert statuses["ux_browser_verification"] == "verified"
    assert not any("design handoff" in gap.lower() for gap in studio["final_proof_report"]["gaps"])


def test_product_studio_blocks_selected_design_that_was_not_applied(monkeypatch, tmp_path):
    project_root = tmp_path / "studio-design-unapplied"
    project_root.mkdir()
    gate_results = {
        "attempted": True,
        "status": "passed",
        "technical_ready": True,
        "approval_gates_cleared": False,
        "failed_required": [],
        "gates": [
            {"id": "browser_check", "label": "Browser check", "group": "browser", "status": "passed", "required": True},
            {"id": "deployment_preview", "label": "Deployment preview", "group": "preview", "status": "passed", "required": True},
            {"id": "test_1", "label": "Check: npm run build", "group": "tests", "status": "passed", "required": True},
            {"id": "dependency_audit", "label": "Dependency audit", "group": "security", "status": "passed", "required": True},
        ],
    }

    studio = product_studio.prepare_product_studio(
        project_root,
        "Build a web-app for field service dispatch.",
        product_name="Field Service Dispatch OS",
        stack={"stack": "nextjs", "label": "Next.js web app", "language": "typescript"},
        artifact_verification={"status": "passed", "summary": "Artifact verification passed."},
        gate_results=gate_results,
        run_live_design_critique=True,
        design_critique={
            "auto_run": True,
            "status": "selected",
            "summary": "Selected a Stitch direction.",
            "frontend_handoff_allowed": True,
            "artifacts": [],
        },
    )

    assert studio["final_proof_report"]["technical_ready"] is False
    assert any("not applied" in gap.lower() for gap in studio["final_proof_report"]["gaps"])


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

    assert result["task_status"] == "blocked"
    assert project_root.is_relative_to(repo.parent / "friday-projects")
    assert (project_root / "package.json").exists()


def test_landing_page_product_request_scaffolds_child_project_in_populated_projects_root(monkeypatch, tmp_path):
    _isolate_common(monkeypatch, tmp_path)
    projects_root = tmp_path / "friday-projects"
    existing_project = projects_root / "old-generated-app"
    existing_project.mkdir(parents=True)
    (existing_project / "package.json").write_text("{}", encoding="utf-8")

    result = autonomous_coding.start(
        "Build a Next.js landing page for a fintech product called TaxNest. TaxNest helps consultants separate income, taxes, invoices, and emergency cash.",
        root=str(projects_root),
    )
    project_root = Path(result["execution"]["metadata"]["project_root"])

    assert result["execution"]["metadata"]["project_name"] == "TaxNest"
    assert project_root == projects_root / "taxnest-web"
    assert (project_root / "package.json").exists()
    assert (project_root / "src" / "components" / "Landing" / "SingleLandingPage.tsx").exists()
    assert not (projects_root / ".friday" / "implementation-plan.md").exists()


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

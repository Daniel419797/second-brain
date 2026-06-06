import json
from pathlib import Path

from core import (
    audit_log,
    autonomous_coding,
    codebase_standards,
    document_intelligence,
    intent_engine,
    memory,
    orchestrator,
    project_memory,
    task_contracts,
    task_queue,
    trust_proof,
)


def _allow_permissions(monkeypatch):
    monkeypatch.setattr(
        orchestrator.permissions,
        "evaluate",
        lambda tool_name, tool_input: {
            "blocked": False,
            "requires_confirmation": False,
            "mode": "allow",
            "key": f"{tool_name}.acceptance",
            "label": tool_name,
        },
    )
    monkeypatch.setattr(orchestrator.permissions, "record_decision", lambda *args, **kwargs: None)


def _fake_product_studio_gates(project_root, *, stack, install, request=""):
    gate_root = Path(project_root) / ".friday" / "product-studio" / "gates"
    gate_root.mkdir(parents=True, exist_ok=True)
    gate_path = gate_root / "gate-results.json"
    result = {
        "attempted": True,
        "root": str(project_root),
        "status": "attention",
        "summary": "Executed acceptance gates: install, tests, audit, browser, and preview evidence recorded.",
        "technical_ready": False,
        "market_ready": False,
        "failed_required": [
            "Browser check: blocked - acceptance test does not launch a browser.",
            "Deployment preview: blocked - acceptance test does not deploy.",
        ],
        "gates": [
            {"id": "dependencies_install", "label": "Dependency install", "group": "install", "status": "passed", "required": True, "command": "npm install" if install else ""},
            {"id": "test_build", "label": "Build/test", "group": "tests", "status": "passed", "required": True, "command": "npm run build"},
            {"id": "dependency_audit", "label": "Dependency audit", "group": "security", "status": "passed", "required": True, "command": "npm audit --audit-level=moderate"},
            {"id": "browser_check", "label": "Browser check", "group": "browser", "status": "blocked", "required": True},
            {"id": "deployment_preview", "label": "Deployment preview", "group": "preview", "status": "blocked", "required": True},
        ],
        "artifacts": [str(gate_path)],
    }
    result["required_gate_statuses"] = result["gates"]
    gate_path.write_text(json.dumps(result), encoding="utf-8")
    return result


def _isolate_coding(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(task_contracts, "DB_PATH", tmp_path / "contracts.sqlite3")
    monkeypatch.setattr(project_memory, "DB_PATH", tmp_path / "project_memory.sqlite3")
    monkeypatch.setattr(codebase_standards, "DB_PATH", tmp_path / "standards.sqlite3")
    monkeypatch.setattr(trust_proof, "DB_PATH", tmp_path / "proof.sqlite3")
    monkeypatch.setattr(audit_log, "DB_PATH", tmp_path / "audit.sqlite3")
    monkeypatch.setattr(autonomous_coding, "_execute_product_studio_gates", _fake_product_studio_gates)


def test_friday_acceptance_routes_user_commands_to_real_capabilities(monkeypatch, tmp_path):
    memory.wipe_all()
    _allow_permissions(monkeypatch)
    calls = []
    monkeypatch.setattr(intent_engine, "resolve_coding_root", lambda root="": tmp_path)
    monkeypatch.setattr(orchestrator, "resolve_coding_root", lambda root="": tmp_path)
    monkeypatch.setattr(orchestrator.llm, "ask", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("generic LLM should not run")))
    monkeypatch.setattr(orchestrator.agent_team, "execute", lambda inputs: (_ for _ in ()).throw(AssertionError("agent queue should not handle these commands")))

    def fake_power(inputs):
        calls.append(inputs)
        if inputs["action"] == "project_ideas_research":
            return "Research-backed idea: Client Onboarding Command Center."
        if inputs["action"] == "autonomous_coding":
            return "Created a scoped Next.js web app with proof artifacts."
        if inputs["action"] == "ad_campaign_draft":
            return "Ad campaign draft ready."
        raise AssertionError(inputs)

    monkeypatch.setattr(orchestrator.power_center, "execute", fake_power)

    assert orchestrator.handle_command("give me an idea on what to build next").startswith("Research-backed idea:")
    assert orchestrator.handle_command("build a university management dashboard").startswith("Created a scoped Next.js")
    assert orchestrator.handle_command("draft an ad for the university dashboard") == "Ad campaign draft ready."

    assert calls[0]["action"] == "project_ideas_research"
    assert calls[1] == {
        "action": "autonomous_coding",
        "request": "Build a web-app for university management dashboard",
        "root": str(tmp_path),
        "risk_level": "medium",
    }
    assert calls[2]["action"] == "ad_campaign_draft"


def test_friday_acceptance_scaffolds_project_docs_and_proof(monkeypatch, tmp_path):
    _isolate_coding(monkeypatch, tmp_path)

    result = autonomous_coding.start("Build a university management dashboard", root=str(tmp_path))

    project_root = Path(result["execution"]["metadata"]["project_root"])
    task_packet_files = [Path(path).name for path in result["execution"]["metadata"]["task_packet"]["files"]]
    assert result["contract"]["status"] == "verified"
    assert project_root.name == "university-management-web"
    assert (project_root / "package.json").exists()
    assert (project_root / "src" / "components" / "Workspace" / "WorkspacePage.tsx").exists()
    assert (project_root / ".friday" / "product-studio" / "proof-report.md").exists()
    assert {"requirements.md", "system-design.md", "implementation-plan.md", "features.md"}.issubset(set(task_packet_files))
    assert result["execution"]["metadata"]["product_studio"]["final_proof_report"]["market_ready"] is False


def test_friday_acceptance_generates_readable_documents(tmp_path):
    result = document_intelligence.generate_document(
        "University Dashboard Requirements",
        "- Student records\n- Fees workflow\n- Approval-gated notifications",
        root=tmp_path,
        filename="university-dashboard-requirements",
        formats=["md", "docx", "pdf"],
    )

    assert result["ok"] is True
    assert set(result["paths"]) == {"md", "docx", "pdf"}
    for path in result["paths"].values():
        read = document_intelligence.read_document(path)
        assert read["ok"] is True
        assert "University Dashboard Requirements" in read["text"]

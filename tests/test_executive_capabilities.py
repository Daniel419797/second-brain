from core import (
    capability_center,
    executive_capabilities,
    local_file_intelligence,
    notification_center,
    pc_timeline,
    personal_crm,
    personal_data_timeline,
    personal_finance,
    personal_knowledge_vault,
    privacy_vault,
    project_autopilot,
    skill_library,
    skill_training_studio,
    task_contracts,
    task_queue,
    workspace_brain,
)


def _isolate(monkeypatch, tmp_path):
    for module in [
        executive_capabilities,
        personal_knowledge_vault,
        personal_crm,
        task_queue,
        task_contracts,
        notification_center,
        local_file_intelligence,
        personal_data_timeline,
        privacy_vault,
        pc_timeline,
        personal_finance,
        project_autopilot,
        skill_training_studio,
        capability_center,
    ]:
        monkeypatch.setattr(module, "DB_PATH", tmp_path / f"{module.__name__.split('.')[-1]}.sqlite3")
    monkeypatch.setattr(skill_library, "SKILLS_PATH", tmp_path / "skills.json")
    monkeypatch.setattr(skill_library, "EXAMPLES_PATH", tmp_path / "skill_examples.json")
    monkeypatch.setattr(workspace_brain.app_integrations, "DB_PATH", tmp_path / "workspace_index.sqlite3")


def test_memory_review_and_personality_profile(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    personal_knowledge_vault.remember_preference("Reply style", "Be direct and practical.")
    personal_crm.remember_person("Ada", relationship="designer")

    generated = executive_capabilities.generate_memory_reviews(limit=4)
    pending = executive_capabilities.list_memory_reviews()
    profile = executive_capabilities.set_personality_profile("debugger", reason="test")
    resolved = executive_capabilities.resolve_memory_review(pending[0]["id"], "keep", note="still true")

    assert len(generated["items"]) >= 2
    assert pending[0]["status"] == "pending"
    assert profile["profile"] == "debugger"
    assert resolved["decision"] == "keep"


def test_task_autopilot_creates_checkpoint_contracts(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    run = executive_capabilities.start_task_autopilot("Improve the API for speed, security, and reliability", sphere="programming", root=tmp_path)
    first_task = task_queue.get_task(run["task_ids"][0])
    contract = task_contracts.get_contract(run["task_ids"][0])

    assert run["sphere"] == "programming"
    assert len(run["task_ids"]) >= 5
    assert "security" in " ".join(run["success_criteria"]).lower()
    assert first_task["status"] == "pending"
    assert contract["verification_method"]


def test_skill_recorder_and_personal_search(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    personal_knowledge_vault.remember("project", "Render deploy", "Check logs before redeploying.")

    recording = executive_capabilities.start_skill_recording("Check Render logs")
    updated = executive_capabilities.add_skill_recording_step(recording["id"], "First open Render. Then check logs. Finally redeploy if healthy.")
    finished = executive_capabilities.finish_skill_recording(recording["id"])
    search = executive_capabilities.personal_search("Render deploy")

    assert len(updated["steps"]) == 3
    assert finished["status"] == "published"
    assert skill_library.search("render logs")
    assert search["results"]


def test_trust_privacy_documentation_and_deployment(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text("# App\n", encoding="utf-8")
    monkeypatch.setattr(executive_capabilities, "_http_status", lambda url: {"url": url, "status": 200, "ok": True})
    monkeypatch.setattr(executive_capabilities, "_dns_summary", lambda host: {"host": host, "addresses": ["127.0.0.1"]})
    monkeypatch.setattr(executive_capabilities.capability_center, "web_security_headers", lambda target: {"summary": "Headers checked."})
    monkeypatch.setattr(executive_capabilities.project_autopilot, "inspect_project", lambda root, run_tests=False: {"issues": []})
    monkeypatch.setattr(executive_capabilities.workspace_brain, "generate_docs", lambda root: {"summary": "Workspace docs updated."})
    monkeypatch.setattr(executive_capabilities.capability_center, "workspace_auto_docs", lambda root: {"summary": "Auto docs updated."})

    trust = executive_capabilities.trust_assessment("delete files in Downloads", domain="desktop")
    privacy = executive_capabilities.privacy_firewall_check("read the .env token")
    docs = executive_capabilities.update_documentation(project)
    deploy = executive_capabilities.deployment_inspect("https://example.com", root=project)

    assert trust["requires_approval"] is True
    assert privacy["decision"] == "ask"
    assert docs["deployment_notes"]["path"].endswith("friday_deployment_commander.md")
    assert deploy["http"]["ok"] is True

from fastapi.testclient import TestClient

from api import server
from core import (
    agent_council,
    agent_lifecycle,
    agent_quality_manager,
    agent_simulation_sandbox,
    agents,
    api_auth,
    code_change_simulator,
    command_graph,
    dev_server_copilot,
    do_not_forget,
    emotional_timing,
    failure_autopsy,
    memory_constitution,
    personal_knowledge_vault,
    personal_taste_engine,
    reality_check,
    refactor_planner,
    skill_improvement,
    task_queue,
    vision_skill_learning,
    visual_skill_memory_v2,
)


def _patch_dbs(monkeypatch, tmp_path):
    modules = [
        agent_quality_manager,
        agent_lifecycle,
        agent_council,
        do_not_forget,
        dev_server_copilot,
        code_change_simulator,
        refactor_planner,
        personal_taste_engine,
        memory_constitution,
        reality_check,
        agent_simulation_sandbox,
        command_graph,
        emotional_timing,
        vision_skill_learning,
        failure_autopsy,
        personal_knowledge_vault,
        skill_improvement,
        task_queue,
    ]
    for module in modules:
        monkeypatch.setattr(module, "DB_PATH", tmp_path / f"{module.__name__.split('.')[-1]}.sqlite3")
    monkeypatch.setattr(api_auth, "SECRET_PATH", tmp_path / "api_secret.txt")
    monkeypatch.setenv("JARVIS_API_PASSWORD", "test-pass")
    monkeypatch.delenv("JARVIS_API_SECRET", raising=False)


def _client(monkeypatch, tmp_path):
    _patch_dbs(monkeypatch, tmp_path)
    client = TestClient(server.create_app())
    token = client.post("/auth/login", json={"username": "friday", "password": "test-pass"}).json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def test_agent_lifecycle_quality_and_council(monkeypatch, tmp_path):
    _patch_dbs(monkeypatch, tmp_path)

    hired = agent_lifecycle.hire_specialist("Figma Export Specialist", "Handle Figma export workflows.", keywords=["figma", "export"])
    assert hired["id"] == "figma_export_specialist"
    assert agents.get_agent("figma export specialist").id == "figma_export_specialist"
    assert "figma_export_specialist" in {item["id"] for item in agents.roster()}

    quality = agent_quality_manager.record_evaluation("figma_export_specialist", task_type="design", accuracy=0.9, usefulness=0.9, speed=0.8, evidence=0.85)
    assert quality["score"] > 0.7
    assert agent_quality_manager.leaderboard("design")[0]["agent_id"] == "figma_export_specialist"

    council = agent_council.convene("Should we automate a Figma export flow?", agent_ids=["figma_export_specialist", "qa_engineer"])
    assert council["confidence"] > 0
    assert council["opinions"]


def test_memory_reality_simulation_and_autopsy(monkeypatch, tmp_path):
    _patch_dbs(monkeypatch, tmp_path)

    routed = do_not_forget.classify("I do not like robotic voices; use free tools first.", source="test")
    assert routed["destination"] == "user_preference"

    policy = memory_constitution.evaluate("secret", "OPENAI_API_KEY=abc", sensitivity="secret")
    assert policy["blocked"]

    check = reality_check.check("Volume set to 40%", evidence="")
    assert check["verdict"] == "unsupported"

    autopsy = failure_autopsy.create("Volume failure", "Friday claimed success without verified evidence.", code_change_needed=True)
    assert "evidence" in autopsy["root_cause"].lower()

    taste = personal_taste_engine.learn_from_correction("The UI is too cluttered, make it cleaner.", domain="ui")
    assert "cleaner" in taste["rule"].lower()


def test_dev_code_refactor_command_emotion_and_visual(monkeypatch, tmp_path):
    _patch_dbs(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("TODO = True\nprint('hello')\n", encoding="utf-8")

    dev = dev_server_copilot.observe(str(repo), log_text='Traceback\nFile "app.py", line 1\nValueError: bad', current_file="app.py")
    assert dev["likely_file"].endswith("app.py")

    simulation = code_change_simulator.simulate("Add API endpoint in api/server.py", root=str(repo))
    assert simulation["tests"]

    refactor = refactor_planner.plan(str(repo))
    assert any(item["kind"] == "todo_debt" for item in refactor["findings"])

    defaults = command_graph.install_defaults()
    assert defaults["created"]
    assert command_graph.resolve("ship it")["found"]

    timing = emotional_timing.advise("This still did not work and I am frustrated")
    assert timing["behavior"]["action_bias"] == "verify_first"

    visual = visual_skill_memory_v2.learn_screen("render", "logs screen", cues=["Logs", "Deploy"], action_hint="open logs")
    assert visual["label"] == "logs screen"

    agent_sim = agent_simulation_sandbox.simulate("Build a dashboard feature")
    assert agent_sim["phases"]


def test_agent_governance_api(monkeypatch, tmp_path):
    client, headers = _client(monkeypatch, tmp_path)

    assert client.post("/agent-lifecycle/hire", headers=headers, json={"name": "Docs Specialist", "purpose": "Update docs."}).status_code == 200
    assert client.get("/agent-lifecycle/status", headers=headers).json()["active"]
    assert client.post("/agent-council/convene", headers=headers, json={"question": "Should we refactor now?"}).status_code == 200
    assert client.post("/code-change-simulator/simulate", headers=headers, json={"instruction": "Change api/server.py"}).status_code == 200
    assert client.post("/reality-check/check", headers=headers, json={"claim": "Done", "evidence": ""}).json()["verdict"] == "unsupported"
    assert client.post("/command-graph/defaults", headers=headers).status_code == 200
    assert "agent_quality_manager" in client.get("/v2/status", headers=headers).json()["implemented"]

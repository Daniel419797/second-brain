from fastapi.testclient import TestClient

from api import server
from core import (
    api_auth,
    app_apprenticeship,
    app_state_memory,
    approval_inbox,
    autonomy_engine,
    certainty_brain,
    context_aware_silence,
    conversation_continuity,
    decision_memory,
    evaluation_lab,
    focus_protection,
    live_workspace_coach,
    local_voice_brain,
    memory_debate,
    notification_center,
    personal_command_memory,
    personal_knowledge_vault,
    personal_memory_review,
    project_cto,
    project_memory,
    project_watchdog,
    self_testing_personality,
    skill_evolution,
    skill_improvement,
    skill_library,
    skill_training_studio,
    task_queue,
    trust_proof,
    vision_skill_learning,
    voice_reliability,
)


def _patch(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_API_PASSWORD", "pw")
    monkeypatch.delenv("JARVIS_API_SECRET", raising=False)
    monkeypatch.setattr(api_auth, "SECRET_PATH", tmp_path / "api_secret.txt")
    for module, name in [
        (app_apprenticeship, "app_apprenticeship.sqlite3"),
        (app_state_memory, "app_state.sqlite3"),
        (approval_inbox, "approval.sqlite3"),
        (autonomy_engine, "autonomy.sqlite3"),
        (certainty_brain, "certainty.sqlite3"),
        (context_aware_silence, "silence.sqlite3"),
        (conversation_continuity, "conversation.sqlite3"),
        (decision_memory, "decision.sqlite3"),
        (evaluation_lab, "evaluation.sqlite3"),
        (focus_protection, "focus.sqlite3"),
        (live_workspace_coach, "coach.sqlite3"),
        (memory_debate, "debate.sqlite3"),
        (notification_center, "notifications.sqlite3"),
        (personal_command_memory, "commands.sqlite3"),
        (personal_knowledge_vault, "vault.sqlite3"),
        (personal_memory_review, "memory_review.sqlite3"),
        (project_cto, "project_cto.sqlite3"),
        (project_memory, "project_memory.sqlite3"),
        (project_watchdog, "watchdog.sqlite3"),
        (self_testing_personality, "self_testing.sqlite3"),
        (skill_evolution, "skill_evolution.sqlite3"),
        (skill_improvement, "skill_improvement.sqlite3"),
        (skill_training_studio, "skill_training.sqlite3"),
        (task_queue, "tasks.sqlite3"),
        (trust_proof, "proof.sqlite3"),
        (vision_skill_learning, "vision.sqlite3"),
        (voice_reliability, "voice.sqlite3"),
    ]:
        monkeypatch.setattr(module, "DB_PATH", tmp_path / name, raising=False)
    monkeypatch.setattr(skill_library, "SKILLS_PATH", tmp_path / "skills.json")
    monkeypatch.setattr(skill_library, "EXAMPLES_PATH", tmp_path / "skill_examples.json")
    monkeypatch.setattr(project_memory.workspace_brain, "analyze_project", lambda root: {"summary": "Project map ready.", "architecture": "simple"})
    monkeypatch.setattr(project_watchdog, "run_once", lambda root="", notify=True: {"summary": "Project watchdog found 0 issue(s).", "status": "ok", "issues": []})
    monkeypatch.setattr(project_cto, "security_guardian_pro", type("Security", (), {"scan": staticmethod(lambda root, light=True: {"findings": [], "summary": "secure"})}))
    monkeypatch.setattr(project_cto, "deployment_brain", type("Deploy", (), {"inspect": staticmethod(lambda **kwargs: {"status": "skipped", "summary": "No deployment target."})}))


def _client(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    client = TestClient(server.create_app())
    token = client.post("/auth/login", json={"username": "friday", "password": "pw"}).json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def test_decision_memory_debate_focus_and_voice_brain(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)

    learned = decision_memory.learn_from_text("I am broke, use free tools and ask first before sending things.")
    chosen = decision_memory.choose("Which API should I use?", category="cost")
    personal_knowledge_vault.remember("preference", "Free APIs", "The user prefers free APIs.", confidence=0.9)
    debate = memory_debate.debate("free APIs")
    focus = focus_protection.set_mode("focus", reason="coding")
    batched = focus_protection.evaluate_notification(title="Tiny reminder", message="Can wait", severity=1)
    voice = local_voice_brain.install_defaults()

    assert learned["learned"]
    assert "free" in chosen["summary"].lower()
    assert debate["beliefs"]
    assert focus["current"]["mode"] == "focus"
    assert batched["decision"] == "batched"
    assert voice["wake_alias_repairs"]


def test_skill_improvement_workspace_coach_apprenticeship_and_cto(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo", encoding="utf-8")

    first = skill_improvement.record_failure("volume_control", "Volume claimed success without verified change.")
    second = skill_improvement.record_failure("volume_control", "Volume still did not change.", evidence=["user correction"])
    coach = live_workspace_coach.observe(repo, log_text="Traceback: ValueError in app.py", current_file="app.py", notify=False)
    session = app_apprenticeship.start("figma", "export frame", goal="Export the selected frame.")
    step = app_apprenticeship.record_step(session["id"], "Click export", action="click", observation="Export panel opens", selector='button[aria-label="Export"]')
    published = app_apprenticeship.finish(session["id"])
    cto = project_cto.report(repo)

    assert first["failure"]["skill"] == "volume_control"
    assert second["proposal"]
    assert coach["event"]["signal"] == "terminal_error"
    assert step["step"]["success"] is True
    assert published["apprenticeship"]["status"] == "published"
    assert cto["project_name"] == "repo"
    assert cto["next_best_task"]


def test_conversation_continuity_trust_dashboard_and_api(monkeypatch, tmp_path):
    client, headers = _client(monkeypatch, tmp_path)

    thread = conversation_continuity.capture("Android companion setup", summary="We were wiring the phone app.")
    proof = trust_proof.create_report("Verified setup", changed=["module added"], tested=["compile"], evidence=["pytest ok"])
    trust = client.get("/trust-dashboard/status", headers=headers)

    responses = [
        client.post("/decision-memory/remember", headers=headers, json={"category": "cost", "preference": "Prefer free APIs", "threshold": "Ask before paid tools."}),
        client.post("/skill-improvement/failure", headers=headers, json={"skill": "stt", "failure": "Heard Freddie"}),
        client.post("/workspace-coach/observe", headers=headers, json={"log_text": "Error: failed"}),
        client.post("/memory-debate", headers=headers, json={"topic": "free", "limit": 5}),
        client.post("/focus-protection/mode", headers=headers, json={"mode": "focus"}),
        client.post("/app-apprenticeship/start", headers=headers, json={"app": "chrome", "workflow": "debug console"}),
        client.post("/project-cto/report", headers=headers, json={"root": str(tmp_path)}),
        client.post("/conversation-continuity/capture", headers=headers, json={"title": "Open OAuth setup"}),
        client.post("/local-voice-brain/defaults", headers=headers),
    ]
    stream = server._task_stream_payload()

    assert thread["status"] == "open"
    assert proof["id"]
    assert trust.status_code == 200
    assert all(response.status_code == 200 for response in responses)
    assert "trust_dashboard" in stream
    assert "decision_memory" in stream

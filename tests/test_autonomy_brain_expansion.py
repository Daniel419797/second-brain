from fastapi.testclient import TestClient

from api import server
from core import (
    android_companion,
    api_auth,
    approval_inbox,
    app_state_memory,
    app_apprenticeship,
    autonomous_qa_lab,
    autonomous_release_engine,
    autonomy_engine,
    browser_extension_bridge,
    certainty_brain,
    device_command_mesh,
    decision_memory,
    evaluation_lab,
    learning_coach,
    learning_roadmap,
    live_workspace_coach,
    memory_debate,
    notification_center,
    notification_intelligence,
    focus_protection,
    operator_skills,
    permissions,
    personal_automation_daemon,
    personal_knowledge_vault,
    phone_mesh,
    privacy_firewall_pro,
    project_cto,
    project_memory,
    project_watchdog,
    release_manager,
    reliability_score,
    self_reflection,
    self_testing_personality,
    skill_improvement,
    task_queue,
    trust_proof,
    vision_skill_learning,
)


def _patch_common(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_API_PASSWORD", "pw")
    monkeypatch.delenv("JARVIS_API_SECRET", raising=False)
    monkeypatch.setattr(api_auth, "SECRET_PATH", tmp_path / "api_secret.txt")
    for module, name in [
        (android_companion, "android.sqlite3"),
        (app_apprenticeship, "app_apprenticeship.sqlite3"),
        (approval_inbox, "approvals.sqlite3"),
        (app_state_memory, "app_state.sqlite3"),
        (autonomous_qa_lab, "qa.sqlite3"),
        (autonomous_release_engine, "release_engine.sqlite3"),
        (autonomy_engine, "autonomy.sqlite3"),
        (browser_extension_bridge, "browser.sqlite3"),
        (certainty_brain, "certainty.sqlite3"),
        (decision_memory, "decision.sqlite3"),
        (device_command_mesh, "device_mesh.sqlite3"),
        (evaluation_lab, "evaluation.sqlite3"),
        (learning_coach, "learning.sqlite3"),
        (learning_roadmap, "roadmap.sqlite3"),
        (live_workspace_coach, "live_workspace_coach.sqlite3"),
        (memory_debate, "memory_debate.sqlite3"),
        (notification_center, "notifications.sqlite3"),
        (notification_intelligence, "notification_intelligence.sqlite3"),
        (focus_protection, "focus_protection.sqlite3"),
        (permissions, "permissions.sqlite3"),
        (personal_automation_daemon, "automation_daemon.sqlite3"),
        (personal_knowledge_vault, "vault.sqlite3"),
        (phone_mesh, "phone_mesh.sqlite3"),
        (privacy_firewall_pro, "privacy_firewall_pro.sqlite3"),
        (project_cto, "project_cto.sqlite3"),
        (project_memory, "project_memory.sqlite3"),
        (project_watchdog, "watchdog.sqlite3"),
        (release_manager, "release.sqlite3"),
        (reliability_score, "reliability.sqlite3"),
        (self_reflection, "reflection.sqlite3"),
        (self_testing_personality, "self_tests.sqlite3"),
        (skill_improvement, "skill_improvement.sqlite3"),
        (task_queue, "tasks.sqlite3"),
        (trust_proof, "proof.sqlite3"),
        (vision_skill_learning, "vision_skills.sqlite3"),
    ]:
        monkeypatch.setattr(module, "DB_PATH", tmp_path / name, raising=False)
    monkeypatch.setattr(android_companion, "FILE_DIR", tmp_path / "android_files")
    monkeypatch.setattr(project_memory.workspace_brain, "analyze_project", lambda root: {"summary": "Repo has a Python app.", "architecture": "simple"})
    monkeypatch.setattr(project_watchdog, "run_once", lambda root="", notify=True: {"summary": "Project watchdog checked repo.", "status": "ok"})


def _headers(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    client = TestClient(server.create_app())
    token = client.post("/auth/login", json={"username": "friday", "password": "pw"}).json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def test_autonomy_certainty_vision_privacy_and_release_modules(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text('{"version":"0.1.0","scripts":{"build":"next build"}}', encoding="utf-8")
    (repo / ".env.example").write_text("NVIDIA_API_KEY=\n", encoding="utf-8")

    known = certainty_brain.record_known("volume", "Verified volume changes require tool proof.", evidence=["pc_control verified=90"])
    missing = certainty_brain.record_missing("deploy", "Need deploy approval before running deploy commands.")
    pattern = vision_skill_learning.learn_pattern(app="figma", label="Toolbar", visual_cues=["left vertical toolbar"], meaning="Figma tools are visible")
    profile = project_memory.profile(repo, refresh=True)
    note = project_memory.remember(repo, "bug", "Volume false success", "Always verify device state.")
    privacy = privacy_firewall_pro.check("Read .env for deployment", paths=[str(repo / ".env")], purpose="deployment setup")
    release = autonomous_release_engine.prepare(repo, run_tests=False)
    run = autonomy_engine.run_until_blocked("verify project proof", root=repo, max_steps=1)

    assert known["kind"] == "known"
    assert missing["kind"] == "missing"
    assert pattern["app"] == "figma"
    assert "NVIDIA_API_KEY" in profile["env_names"]
    assert note["kind"] == "bug"
    assert privacy["status"] == "approval_required"
    assert release["status"] in {"ready_for_approval", "needs_fixes"}
    assert run["status"] in {"running", "completed", "blocked"}
    assert certainty_brain.answer("what do you know")["answer"]


def test_automation_notification_selftest_learning_operator_and_device_mesh(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    notification_center.add(source="test", category="security", severity=5, title="Suspicious process", message="Needs action now")

    personal_automation_daemon.install_defaults()
    automation = personal_automation_daemon.run_once(run_actions=False)
    ranked = notification_intelligence.rank_pending()
    self_test = self_testing_personality.run()
    roadmap = learning_roadmap.create("Python", "Improve debugging", weeks=2)
    operator = operator_skills.plan("chrome", "debug current page")
    mesh = device_command_mesh.continue_on_laptop("Continue Friday setup", {"task": "dashboard"})

    assert "summary" in automation
    assert ranked["ranked"]
    assert self_test["checks"]
    assert len(roadmap["weekly_plan"]) == 2
    assert operator["app"] == "chrome"
    assert mesh["command_type"] == "continue_on_laptop"


def test_autonomy_brain_api_endpoints(monkeypatch, tmp_path):
    client, headers = _headers(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Friday Repo", encoding="utf-8")

    assert client.post("/certainty/known", headers=headers, json={"topic": "Friday", "statement": "Uses proof gates."}).status_code == 200
    assert client.post("/vision-skills/learn", headers=headers, json={"app": "render", "label": "Deploy button", "action_hint": "confirm deployment"}).status_code == 200
    assert client.post("/project-memory/profile", headers=headers, json={"root": str(repo), "refresh": True}).status_code == 200
    assert client.post("/operator-skills/plan", headers=headers, json={"app": "chrome", "instruction": "summarize page"}).status_code == 200
    assert client.post("/learning-roadmap", headers=headers, json={"topic": "math", "weeks": 1}).status_code == 200
    assert client.post("/privacy-firewall-pro/check", headers=headers, json={"instruction": "use .env", "paths": [str(repo / ".env")]}).status_code == 200
    assert client.post("/device-mesh/command", headers=headers, json={"command_type": "handoff", "title": "Continue on laptop"}).status_code == 200
    assert client.post("/release-engine/prepare", headers=headers, json={"root": str(repo)}).status_code == 200
    assert client.post("/automation-daemon/run", headers=headers).status_code == 200
    assert client.post("/notification-intelligence/rank", headers=headers, json={"limit": 10}).status_code == 200
    assert client.post("/self-tests/run", headers=headers).status_code == 200
    assert client.post("/autonomy-engine/start", headers=headers, json={"goal": "verify project proof", "root": str(repo), "max_steps": 1}).status_code == 200

    stream = server._task_stream_payload()
    assert "autonomy_engine" in stream
    assert "certainty_brain" in stream
    assert "release_engine" in stream

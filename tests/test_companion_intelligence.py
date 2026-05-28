from pathlib import Path

from fastapi.testclient import TestClient

from api import server
from core import (
    android_companion,
    api_auth,
    autonomous_debugger,
    autonomous_learning,
    browser_extension_bridge,
    calendar_email_assistant,
    context_aware_silence,
    context_fusion,
    continuity_brain,
    deep_project_autopilot,
    environment_awareness,
    knowledge_graph,
    long_term_learning,
    personal_safety_guardian,
    personal_command_memory,
    phone_mesh,
    project_autopilot,
    skill_evolution,
    task_queue,
    trust_proof,
)


def _patch_common(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_API_PASSWORD", "pw")
    monkeypatch.delenv("JARVIS_API_SECRET", raising=False)
    monkeypatch.setattr(api_auth, "SECRET_PATH", tmp_path / "api_secret.txt")
    monkeypatch.setattr(android_companion, "DB_PATH", tmp_path / "android.sqlite3")
    monkeypatch.setattr(browser_extension_bridge, "DB_PATH", tmp_path / "browser.sqlite3")
    monkeypatch.setattr(autonomous_debugger, "DB_PATH", tmp_path / "debugger.sqlite3")
    monkeypatch.setattr(personal_command_memory, "DB_PATH", tmp_path / "commands.sqlite3")
    monkeypatch.setattr(autonomous_learning, "DB_PATH", tmp_path / "learning.sqlite3")
    monkeypatch.setattr(trust_proof, "DB_PATH", tmp_path / "proof.sqlite3")
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(long_term_learning, "DB_PATH", tmp_path / "long_learning.sqlite3")
    monkeypatch.setattr(environment_awareness, "DB_PATH", tmp_path / "environment.sqlite3")
    monkeypatch.setattr(knowledge_graph, "GRAPH_PATH", tmp_path / "graph.json")
    monkeypatch.setattr(knowledge_graph, "_GRAPH", None)
    monkeypatch.setattr(continuity_brain, "DB_PATH", tmp_path / "continuity.sqlite3")
    monkeypatch.setattr(context_aware_silence, "DB_PATH", tmp_path / "silence.sqlite3")
    monkeypatch.setattr(deep_project_autopilot, "DB_PATH", tmp_path / "deep_autopilot.sqlite3")
    monkeypatch.setattr(project_autopilot, "DB_PATH", tmp_path / "project_autopilot.sqlite3")
    monkeypatch.setattr(skill_evolution, "DB_PATH", tmp_path / "skill_evolution.sqlite3")
    monkeypatch.setattr(personal_safety_guardian, "DB_PATH", tmp_path / "safety.sqlite3")
    monkeypatch.setattr(phone_mesh, "DB_PATH", tmp_path / "phone_mesh.sqlite3")


def test_android_app_browser_actions_commands_learning_and_proof(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    device = android_companion.register_app_device("Pixel", "abc", capabilities=["microphone", "clipboard"])
    clip = android_companion.ingest_clipboard("abc", "hello phone")
    context = browser_extension_bridge.ingest_context(
        {
            "url": "https://example.test/?token=secret",
            "title": "Example",
            "headings": [{"text": "Dashboard"}],
            "buttons": [{"text": "Save", "selector": "#save"}],
            "links": [{"text": "Docs", "href": "https://example.test/docs"}],
            "inputs": [{"name": "email", "selector": "#email"}],
        }
    )
    action = browser_extension_bridge.queue_action("click", url=context["url"], selector="#save", reason="test")
    completed = browser_extension_bridge.complete_action(action["id"], status="done", result="clicked")
    command = personal_command_memory.learn("start work", "open VS Code")
    resolved = personal_command_memory.resolve("start work")
    proof = trust_proof.create_report("Smoke proof", changed=["added layer"], tested=["unit"], evidence=["green"], risks=["none"])
    plan = autonomous_learning.run_cycle("build SaaS auth dashboard", create_tasks=True)

    assert device["device_id"] == "abc"
    assert clip["ok"] is True
    assert context["url"].endswith("?[redacted-query]")
    assert completed["status"] == "done"
    assert command["ok"] is True and resolved["canonical_command"] == "open VS Code"
    assert proof["summary"].startswith("Smoke proof")
    assert plan["task_ids"]


def test_debugger_environment_graph_and_api(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(environment_awareness.pc_awareness, "snapshot", lambda force_refresh=False: {"active_window": "main.py - second-brain - Visual Studio Code", "running_apps": [{"name": "Code"}]})
    monkeypatch.setattr(calendar_email_assistant.google_workspace, "status", lambda: {"connected": False})
    monkeypatch.setattr(calendar_email_assistant.google_workspace, "recent_gmail_messages", lambda limit=8: [])
    monkeypatch.setattr(calendar_email_assistant.google_workspace, "list_calendar_events", lambda limit=8: [])

    debug = autonomous_debugger.analyze_text("Traceback: ValueError failed test", source="pytest")
    env = environment_awareness.snapshot(force_refresh=True)
    edge = knowledge_graph.connect("Friday", "USES", "Gemini")

    assert debug["probable_cause"] == "runtime_exception"
    assert "second-brain" in env["open_project"]
    assert edge["summary"] == "Knowledge graph relationship saved."

    client = TestClient(server.create_app())
    token = client.post("/auth/login", json={"username": "friday", "password": "pw"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/command-memory/learn", headers=headers, json={"heard_phrase": "check project", "canonical_command": "run qa lab"}).status_code == 200
    assert client.post("/browser-extension/action", headers=headers, json={"action": "summarize"}).status_code == 200
    assert client.post("/autonomous-debugger/analyze", headers=headers, json={"text": "Error: failed"}).status_code == 200
    assert client.get("/calendar-email/brief", headers=headers).status_code == 200
    assert client.get("/knowledge-graph/query?q=Gemini", headers=headers).status_code == 200
    assert client.get("/environment/status", headers=headers).status_code == 200
    assert client.post("/proof-reports", headers=headers, json={"title": "API proof", "evidence": ["ok"]}).status_code == 200


def test_android_companion_project_files_exist():
    root = Path(__file__).resolve().parent.parent / "apps" / "android-companion"
    assert (root / "settings.gradle").exists()
    assert (root / "app" / "src" / "main" / "AndroidManifest.xml").exists()
    assert (root / "app" / "src" / "main" / "java" / "com" / "friday" / "companion" / "MainActivity.java").exists()


def test_continuity_context_silence_skill_safety_phone_and_api(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(environment_awareness.pc_awareness, "snapshot", lambda force_refresh=False: {"active_window": "main.py - second-brain - Visual Studio Code", "running_apps": [{"name": "Code"}]})
    browser_extension_bridge.ingest_context({"url": "https://example.test", "title": "App", "buttons": [{"text": "Save", "selector": "#save"}]})
    browser_extension_bridge.ingest_console({"url": "https://example.test", "level": "error", "message": "React failed"})
    thread = continuity_brain.remember_thread("voice latency", "Full pytest timed out while improving voice latency.", source="test")
    fused = context_fusion.snapshot(force_refresh=True)
    silence = context_aware_silence.set_mode("coding")
    for _ in range(3):
        suggestion = skill_evolution.observe_workflow("deploy next app", "Deploy Next.js app")
    safety = personal_safety_guardian.preflight_action("delete .env", path=str(tmp_path / ".env"))
    handoff = phone_mesh.create_handoff("abc", "continue this task on PC", {"command": "open dashboard"})
    defaults = personal_command_memory.install_default_language()

    assert thread["ok"] is True
    assert fused["observations"]
    assert silence["mode"] == "coding"
    assert suggestion["suggestion"]
    assert safety["allowed_without_approval"] is False
    assert handoff["status"] == "pending"
    assert defaults["installed"]

    client = TestClient(server.create_app())
    token = client.post("/auth/login", json={"username": "friday", "password": "pw"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/continuity/capture", headers=headers).status_code == 200
    assert client.get("/context-fusion/status", headers=headers).status_code == 200
    assert client.post("/silence/mode", headers=headers, json={"mode": "debugging"}).status_code == 200
    assert client.get("/browser-pc-copilot/status", headers=headers).status_code == 200
    assert client.post("/skill-evolution/refresh", headers=headers).status_code == 200
    assert client.post("/safety-guardian/preflight", headers=headers, json={"instruction": "delete .env"}).status_code == 200
    assert client.post("/phone-mesh/handoff", headers=headers, json={"title": "continue on PC"}).status_code == 200

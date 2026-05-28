import base64

from fastapi.testclient import TestClient

from api import server
from core import (
    android_companion,
    api_auth,
    app_operator_mastery,
    app_state_memory,
    approval_inbox,
    autonomous_debugger,
    autonomous_fix_loop,
    awareness_graph,
    browser_extension_bridge,
    browser_extension_pro,
    capability_center,
    cloud_worker_mode,
    emotion_tone,
    error_radar,
    executive_capabilities,
    life_os_mode,
    local_ai_search,
    mission_control,
    notification_center,
    os_autopilot,
    personal_command_memory,
    personal_data_timeline,
    personal_knowledge_vault,
    personal_memory_review,
    personal_safety_guardian,
    semantic_search,
    task_queue,
    test_build_monitor,
    trust_proof,
)


def _patch_common(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_API_PASSWORD", "pw")
    monkeypatch.delenv("JARVIS_API_SECRET", raising=False)
    monkeypatch.setattr(api_auth, "SECRET_PATH", tmp_path / "api_secret.txt")
    for module, name in [
        (android_companion, "android.sqlite3"),
        (app_state_memory, "app_state.sqlite3"),
        (autonomous_debugger, "debugger.sqlite3"),
        (autonomous_fix_loop, "fix_loop.sqlite3"),
        (awareness_graph, "awareness.sqlite3"),
        (browser_extension_bridge, "browser.sqlite3"),
        (browser_extension_pro, "browser_pro.sqlite3"),
        (capability_center, "capability.sqlite3"),
        (cloud_worker_mode, "cloud.sqlite3"),
        (emotion_tone, "tone.sqlite3"),
        (error_radar, "radar.sqlite3"),
        (executive_capabilities, "executive.sqlite3"),
        (mission_control, "missions.sqlite3"),
        (notification_center, "notifications.sqlite3"),
        (os_autopilot, "os.sqlite3"),
        (personal_command_memory, "commands.sqlite3"),
        (personal_data_timeline, "timeline.sqlite3"),
        (personal_knowledge_vault, "vault.sqlite3"),
        (personal_safety_guardian, "safety.sqlite3"),
        (semantic_search, "semantic.sqlite3"),
        (task_queue, "tasks.sqlite3"),
        (test_build_monitor, "monitor.sqlite3"),
        (trust_proof, "proof.sqlite3"),
    ]:
        monkeypatch.setattr(module, "DB_PATH", tmp_path / name, raising=False)
    monkeypatch.setattr(android_companion, "FILE_DIR", tmp_path / "android_files")
    monkeypatch.setattr(capability_center, "REPORT_DIR", tmp_path / "reports")


def test_awareness_fix_browser_android_search_life_security_cloud(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(capability_center, "maintenance_report", lambda light=True: {"summary": "PC health ok.", "suggestions": []})
    monkeypatch.setattr(capability_center, "security_overview", lambda light=True: {"summary": "Security overview ok.", "suspicious_processes": [], "open_ports": {"open_ports": []}, "browser_extensions": []})

    browser_extension_bridge.ingest_context({"url": "https://example.test", "title": "Dashboard", "buttons": [{"text": "Save", "selector": "#save"}], "forms": [{"name": "login", "fields": [{"name": "email", "type": "email"}]}]})
    browser_extension_bridge.ingest_console({"url": "https://example.test", "level": "error", "message": "React failed"})
    network = browser_extension_pro.ingest_network_event({"url": "https://example.test/api", "event_type": "network_error", "error": "net::ERR_FAILED"})
    guidance = browser_extension_pro.guidance("what button should I click")
    fill = browser_extension_pro.safe_fill("#email", "user@example.com")

    android_companion.register_app_device("Pixel", "pixel-1", capabilities=["microphone", "files"])
    uploaded = android_companion.ingest_file_event("pixel-1", {"name": "note.txt", "mime_type": "text/plain", "content_base64": base64.b64encode(b"hello").decode("ascii")})

    personal_knowledge_vault.remember("preference", "free APIs", "The user prefers free APIs.", confidence=0.9)
    reviews = personal_memory_review.generate(limit=5)

    sample = tmp_path / "project.md"
    sample.write_text("Friday auth logic and deployment notes", encoding="utf-8")
    indexed = local_ai_search.index([str(tmp_path)], limit=20)
    search = local_ai_search.search("auth deployment", limit=5)

    awareness = awareness_graph.refresh(force=False)
    fix = autonomous_fix_loop.run(root=tmp_path, log_text="Traceback: ValueError failed test", run_tests=False)
    life = life_os_mode.status()
    security = personal_safety_guardian.scan(tmp_path, max_files=20)
    cloud = cloud_worker_mode.submit("research", "Research auth patterns", {"note": "safe"})
    mastery = app_operator_mastery.plan("chrome", "debug the current page")

    assert network["event_type"] == "network_error"
    assert guidance["suggestions"]
    assert fill["status"] == "queued"
    assert uploaded["stored"]["stored_path"]
    assert reviews["reviews"]["items"]
    assert indexed["status"]["chunks"] >= 1
    assert search["results"]
    assert awareness["summary"]
    assert fix["status"] == "needs_approval"
    assert life["summary"]
    assert "summary" in security
    assert cloud["local_task_id"]
    assert mastery["summary"]


def test_advanced_power_api(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(capability_center, "maintenance_report", lambda light=True: {"summary": "PC health ok.", "suggestions": []})
    monkeypatch.setattr(capability_center, "security_overview", lambda light=True: {"summary": "Security overview ok.", "suspicious_processes": [], "open_ports": {"open_ports": []}, "browser_extensions": []})

    client = TestClient(server.create_app())
    token = client.post("/auth/login", json={"username": "friday", "password": "pw"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.post("/browser-extension/context", headers=headers, json={"url": "https://example.test", "title": "App", "buttons": [{"text": "Save", "selector": "#save"}]}).status_code == 200
    assert client.post("/browser-extension/network", headers=headers, json={"url": "https://example.test/api", "event_type": "network_error", "error": "failed"}).status_code == 200
    assert client.post("/awareness-graph/answer", headers=headers, json={"question": "what is happening right now"}).status_code == 200
    assert client.post("/fix-loop/run", headers=headers, json={"log_text": "Error: failed test", "run_tests": False}).status_code == 200
    assert client.post("/browser-pro/guidance", headers=headers, json={"question": "what should I click"}).status_code == 200
    assert client.get("/android-companion/pro/status", headers=headers).status_code == 200
    assert client.post("/memory-review/pro/generate", headers=headers).status_code == 200
    assert client.post("/app-mastery/plan", headers=headers, json={"app": "chrome", "instruction": "summarize"}).status_code == 200
    assert client.post("/local-ai-search/index", headers=headers, json={"paths": [str(tmp_path)], "limit": 5}).status_code == 200
    assert client.post("/life-os/brief", headers=headers).status_code == 200
    assert client.post("/security-guardian-pro/scan", headers=headers, json={"root": str(tmp_path)}).status_code == 200
    assert client.post("/cloud-worker/submit", headers=headers, json={"job_type": "research", "title": "Research task"}).status_code == 200

import base64
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from api import server
from core import adaptive_attention, agency_mode, agent_blackboard, agent_council, agent_lifecycle, agent_memory, agent_office, agent_quality_manager, agent_scheduler, agent_simulation_sandbox, agent_thought_bus, android_companion, api_auth, app_apprenticeship, app_integrations, app_operators, app_state_memory, autobiographical_memory, autonomous_debugger, autonomous_learning, autonomous_qa_lab, backup_recovery, barge_in, browser_extension_bridge, capability_center, code_change_simulator, command_graph, context_aware_silence, continuity_brain, contextual_workspace, conversation_continuity, daily_companion, decision_memory, deep_project_autopilot, deployment_brain, desktop_tasks, dev_server_copilot, do_not_forget, emotion_tone, emotional_timing, environment_awareness, error_radar, evaluation_lab, event_nervous_system, executive_capabilities, failure_autopsy, focus_protection, goal_regulation, google_workspace, learning_coach, live_workspace_coach, local_file_intelligence, local_voice_brain, long_term_learning, meeting_study_companion, memory_constitution, memory_debate, mission_control, model_benchmark_lab, model_router_brain, notification_center, offline_survival, operating_rhythm, os_autopilot, pc_awareness, pc_timeline, permissions, personal_command_memory, personal_crm, personal_data_timeline, personal_finance, personal_knowledge_vault, personal_life_os, personal_safety_guardian, personal_taste_engine, phone_bridge, phone_mesh, private_embedding_memory, privacy_vault, project_autopilot, project_cto, project_memory, project_watchdog, proactive_guardian, reality_check, refactor_planner, release_manager, reliability_score, research_briefings, sandbox_simulation, self_debugger, self_reflection, self_update, semantic_search, skill_evolution, skill_improvement, skill_library, skill_training_studio, task_contracts, task_queue, test_build_monitor, trust_proof, version_guardian, vision_skill_learning, visual_monitor, voice_reliability, workspace_brain, world_model
from core import approval_inbox, audit_log, cloud_worker_mode, codebase_standards, company_runtime, competitive_benchmark, connector_runtime, friday_gateway, memory_governance, production_coding_autonomy


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_API_PASSWORD", "super-secret")
    monkeypatch.delenv("JARVIS_API_SECRET", raising=False)
    monkeypatch.setattr(api_auth, "SECRET_PATH", tmp_path / "api_secret.txt")
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(desktop_tasks, "DB_PATH", tmp_path / "desktop_tasks.sqlite3")
    monkeypatch.setattr(visual_monitor, "DB_PATH", tmp_path / "visual_monitor.sqlite3")
    monkeypatch.setattr(visual_monitor, "FRAME_ROOT", tmp_path / "visual_frames")
    monkeypatch.setattr(app_integrations, "DB_PATH", tmp_path / "app_integrations.sqlite3")
    monkeypatch.setattr(app_apprenticeship, "DB_PATH", tmp_path / "app_apprenticeship.sqlite3")
    monkeypatch.setattr(app_integrations, "OFFICE_DIR", tmp_path / "office_docs")
    monkeypatch.setattr(autobiographical_memory, "DB_PATH", tmp_path / "autobiographical.sqlite3")
    monkeypatch.setattr(permissions, "DB_PATH", tmp_path / "permissions.sqlite3")
    monkeypatch.setattr(pc_awareness, "DB_PATH", tmp_path / "pc_awareness.sqlite3")
    monkeypatch.setattr(phone_bridge, "DB_PATH", tmp_path / "phone_bridge.sqlite3")
    monkeypatch.setattr(capability_center, "DB_PATH", tmp_path / "capability_center.sqlite3")
    monkeypatch.setattr(capability_center, "REPORT_DIR", tmp_path / "reports")
    monkeypatch.setattr(skill_library, "SKILLS_PATH", tmp_path / "skills.json")
    monkeypatch.setattr(skill_library, "EXAMPLES_PATH", tmp_path / "skill_examples.json")
    monkeypatch.setattr(workspace_brain.app_integrations, "DB_PATH", tmp_path / "workspace_index.sqlite3")
    monkeypatch.setattr(personal_life_os, "DB_PATH", tmp_path / "personal_life_os.sqlite3")
    monkeypatch.setattr(backup_recovery, "DB_PATH", tmp_path / "backup_recovery.sqlite3")
    monkeypatch.setattr(backup_recovery, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(world_model, "DB_PATH", tmp_path / "world_model.sqlite3")
    monkeypatch.setattr(self_reflection, "DB_PATH", tmp_path / "self_reflection.sqlite3")
    monkeypatch.setattr(long_term_learning, "DB_PATH", tmp_path / "long_term_learning.sqlite3")
    monkeypatch.setattr(goal_regulation, "DB_PATH", tmp_path / "goal_regulation.sqlite3")
    monkeypatch.setattr(adaptive_attention, "DB_PATH", tmp_path / "adaptive_attention.sqlite3")
    monkeypatch.setattr(agent_blackboard, "DB_PATH", tmp_path / "agent_blackboard.sqlite3")
    monkeypatch.setattr(agent_memory, "DB_PATH", tmp_path / "agent_memory.sqlite3")
    monkeypatch.setattr(agent_thought_bus, "DB_PATH", tmp_path / "agent_thought_bus.sqlite3")
    monkeypatch.setattr(evaluation_lab, "DB_PATH", tmp_path / "evaluation_lab.sqlite3")
    monkeypatch.setattr(task_contracts, "DB_PATH", tmp_path / "task_contracts.sqlite3")
    monkeypatch.setattr(voice_reliability, "DB_PATH", tmp_path / "voice_reliability.sqlite3")
    monkeypatch.setattr(notification_center, "DB_PATH", tmp_path / "notification_center.sqlite3")
    monkeypatch.setattr(approval_inbox, "DB_PATH", tmp_path / "approval_inbox.sqlite3")
    monkeypatch.setattr(audit_log, "DB_PATH", tmp_path / "audit_log.sqlite3")
    monkeypatch.setattr(proactive_guardian, "DB_PATH", tmp_path / "proactive_guardian.sqlite3")
    monkeypatch.setattr(event_nervous_system, "DB_PATH", tmp_path / "event_nervous_system.sqlite3")
    monkeypatch.setattr(barge_in, "DB_PATH", tmp_path / "barge_in.sqlite3")
    monkeypatch.setattr(barge_in, "STOP_FLAG_PATH", tmp_path / "barge_in_stop.flag")
    monkeypatch.setattr(daily_companion, "DB_PATH", tmp_path / "daily_companion.sqlite3")
    monkeypatch.setattr(agency_mode, "DB_PATH", tmp_path / "agency_mode.sqlite3")
    monkeypatch.setattr(agency_mode, "config_value", lambda key, default=None: str(tmp_path / "Friday Agency") if key == "agency_workspace_dir" else default)
    monkeypatch.setattr(friday_gateway, "DB_PATH", tmp_path / "friday_gateway.sqlite3")
    monkeypatch.setattr(connector_runtime, "DB_PATH", tmp_path / "connector_runtime.sqlite3")
    monkeypatch.setattr(competitive_benchmark, "DB_PATH", tmp_path / "competitive_benchmark.sqlite3")
    monkeypatch.setattr(company_runtime, "DB_PATH", tmp_path / "company_runtime.sqlite3")
    monkeypatch.setattr(memory_governance, "DB_PATH", tmp_path / "memory_governance.sqlite3")
    monkeypatch.setattr(production_coding_autonomy, "FRIDAY_DIR", ".friday")
    monkeypatch.setattr(codebase_standards, "DB_PATH", tmp_path / "codebase_standards.sqlite3")
    monkeypatch.setattr(cloud_worker_mode, "DB_PATH", tmp_path / "cloud_worker_mode.sqlite3")
    monkeypatch.setattr(personal_finance, "DB_PATH", tmp_path / "personal_finance.sqlite3")
    monkeypatch.setattr(private_embedding_memory, "DB_PATH", tmp_path / "private_embedding_memory.sqlite3")
    monkeypatch.setattr(android_companion, "DB_PATH", tmp_path / "android_companion.sqlite3")
    monkeypatch.setattr(autonomous_debugger, "DB_PATH", tmp_path / "autonomous_debugger.sqlite3")
    monkeypatch.setattr(autonomous_learning, "DB_PATH", tmp_path / "autonomous_learning.sqlite3")
    monkeypatch.setattr(project_watchdog, "DB_PATH", tmp_path / "project_watchdog.sqlite3")
    monkeypatch.setattr(sandbox_simulation, "DB_PATH", tmp_path / "sandbox_simulation.sqlite3")
    monkeypatch.setattr(privacy_vault, "DB_PATH", tmp_path / "privacy_vault.sqlite3")
    monkeypatch.setattr(model_router_brain, "DB_PATH", tmp_path / "model_router_brain.sqlite3")
    monkeypatch.setattr(self_debugger, "DB_PATH", tmp_path / "self_debugger.sqlite3")
    monkeypatch.setattr(emotion_tone, "DB_PATH", tmp_path / "emotion_tone.sqlite3")
    monkeypatch.setattr(personal_crm, "DB_PATH", tmp_path / "personal_crm.sqlite3")
    monkeypatch.setattr(learning_coach, "DB_PATH", tmp_path / "learning_coach.sqlite3")
    monkeypatch.setattr(research_briefings, "DB_PATH", tmp_path / "research_briefings.sqlite3")
    monkeypatch.setattr(contextual_workspace, "DB_PATH", tmp_path / "contextual_workspace.sqlite3")
    monkeypatch.setattr(conversation_continuity, "DB_PATH", tmp_path / "conversation_continuity.sqlite3")
    monkeypatch.setattr(offline_survival, "DB_PATH", tmp_path / "offline_survival.sqlite3")
    monkeypatch.setattr(personal_data_timeline, "DB_PATH", tmp_path / "personal_data_timeline.sqlite3")
    monkeypatch.setattr(skill_training_studio, "DB_PATH", tmp_path / "skill_training_studio.sqlite3")
    monkeypatch.setattr(mission_control, "DB_PATH", tmp_path / "mission_control.sqlite3")
    monkeypatch.setattr(autonomous_qa_lab, "DB_PATH", tmp_path / "autonomous_qa_lab.sqlite3")
    monkeypatch.setattr(app_state_memory, "DB_PATH", tmp_path / "app_state_memory.sqlite3")
    monkeypatch.setattr(browser_extension_bridge, "DB_PATH", tmp_path / "browser_extension.sqlite3")
    monkeypatch.setattr(release_manager, "DB_PATH", tmp_path / "release_manager.sqlite3")
    monkeypatch.setattr(error_radar, "DB_PATH", tmp_path / "error_radar.sqlite3")
    monkeypatch.setattr(semantic_search, "DB_PATH", tmp_path / "semantic_search.sqlite3")
    monkeypatch.setattr(operating_rhythm, "DB_PATH", tmp_path / "operating_rhythm.sqlite3")
    monkeypatch.setattr(environment_awareness, "DB_PATH", tmp_path / "environment_awareness.sqlite3")
    monkeypatch.setattr(decision_memory, "DB_PATH", tmp_path / "decision_memory.sqlite3")
    monkeypatch.setattr(live_workspace_coach, "DB_PATH", tmp_path / "live_workspace_coach.sqlite3")
    monkeypatch.setattr(memory_debate, "DB_PATH", tmp_path / "memory_debate.sqlite3")
    monkeypatch.setattr(focus_protection, "DB_PATH", tmp_path / "focus_protection.sqlite3")
    monkeypatch.setattr(project_cto, "DB_PATH", tmp_path / "project_cto.sqlite3")
    monkeypatch.setattr(skill_improvement, "DB_PATH", tmp_path / "skill_improvement.sqlite3")
    monkeypatch.setattr(agent_quality_manager, "DB_PATH", tmp_path / "agent_quality.sqlite3")
    monkeypatch.setattr(agent_lifecycle, "DB_PATH", tmp_path / "agent_lifecycle.sqlite3")
    monkeypatch.setattr(agent_council, "DB_PATH", tmp_path / "agent_council.sqlite3")
    monkeypatch.setattr(do_not_forget, "DB_PATH", tmp_path / "do_not_forget.sqlite3")
    monkeypatch.setattr(dev_server_copilot, "DB_PATH", tmp_path / "dev_server_copilot.sqlite3")
    monkeypatch.setattr(code_change_simulator, "DB_PATH", tmp_path / "code_change_simulator.sqlite3")
    monkeypatch.setattr(refactor_planner, "DB_PATH", tmp_path / "refactor_planner.sqlite3")
    monkeypatch.setattr(personal_taste_engine, "DB_PATH", tmp_path / "personal_taste_engine.sqlite3")
    monkeypatch.setattr(memory_constitution, "DB_PATH", tmp_path / "memory_constitution.sqlite3")
    monkeypatch.setattr(reality_check, "DB_PATH", tmp_path / "reality_check.sqlite3")
    monkeypatch.setattr(agent_simulation_sandbox, "DB_PATH", tmp_path / "agent_simulation.sqlite3")
    monkeypatch.setattr(command_graph, "DB_PATH", tmp_path / "command_graph.sqlite3")
    monkeypatch.setattr(emotional_timing, "DB_PATH", tmp_path / "emotional_timing.sqlite3")
    monkeypatch.setattr(vision_skill_learning, "DB_PATH", tmp_path / "vision_skill_learning.sqlite3")
    monkeypatch.setattr(failure_autopsy, "DB_PATH", tmp_path / "failure_autopsy.sqlite3")
    monkeypatch.setattr(personal_command_memory, "DB_PATH", tmp_path / "personal_command_memory.sqlite3")
    monkeypatch.setattr(trust_proof, "DB_PATH", tmp_path / "trust_proof.sqlite3")
    monkeypatch.setattr(continuity_brain, "DB_PATH", tmp_path / "continuity_brain.sqlite3")
    monkeypatch.setattr(context_aware_silence, "DB_PATH", tmp_path / "context_aware_silence.sqlite3")
    monkeypatch.setattr(deep_project_autopilot, "DB_PATH", tmp_path / "deep_project_autopilot.sqlite3")
    monkeypatch.setattr(skill_evolution, "DB_PATH", tmp_path / "skill_evolution.sqlite3")
    monkeypatch.setattr(personal_safety_guardian, "DB_PATH", tmp_path / "personal_safety_guardian.sqlite3")
    monkeypatch.setattr(phone_mesh, "DB_PATH", tmp_path / "phone_mesh.sqlite3")
    monkeypatch.setattr(agent_scheduler, "DB_PATH", tmp_path / "agent_scheduler.sqlite3")
    monkeypatch.setattr(test_build_monitor, "DB_PATH", tmp_path / "test_build_monitor.sqlite3")
    monkeypatch.setattr(reliability_score, "DB_PATH", tmp_path / "reliability_score.sqlite3")
    monkeypatch.setattr(model_benchmark_lab, "DB_PATH", tmp_path / "model_benchmark_lab.sqlite3")
    monkeypatch.setattr(deployment_brain, "DB_PATH", tmp_path / "deployment_brain.sqlite3")
    monkeypatch.setattr(os_autopilot, "DB_PATH", tmp_path / "os_autopilot.sqlite3")
    monkeypatch.setattr(version_guardian, "DB_PATH", tmp_path / "version_guardian.sqlite3")
    monkeypatch.setattr(personal_knowledge_vault, "DB_PATH", tmp_path / "personal_knowledge_vault.sqlite3")
    monkeypatch.setattr(project_autopilot, "DB_PATH", tmp_path / "project_autopilot.sqlite3")
    monkeypatch.setattr(project_memory, "DB_PATH", tmp_path / "project_memory.sqlite3")
    monkeypatch.setattr(project_memory, "REFERENCE_IMAGE_DIR", tmp_path / "project_reference_images")
    monkeypatch.setattr(project_memory.workspace_brain, "analyze_project", lambda root: {"summary": "Project map ready.", "architecture": "simple"})
    monkeypatch.setattr(pc_timeline, "DB_PATH", tmp_path / "pc_timeline.sqlite3")
    monkeypatch.setattr(local_file_intelligence, "DB_PATH", tmp_path / "local_file_intelligence.sqlite3")
    monkeypatch.setattr(meeting_study_companion, "DB_PATH", tmp_path / "meeting_study_companion.sqlite3")
    monkeypatch.setattr(executive_capabilities, "DB_PATH", tmp_path / "executive_capabilities.sqlite3")
    monkeypatch.setattr(self_update, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(self_update, "DB_PATH", tmp_path / "self_updates.sqlite3")
    monkeypatch.setattr(self_update, "BACKUP_DIR", tmp_path / "self_update_backups")
    monkeypatch.setattr(google_workspace, "TOKEN_PATH", tmp_path / "google_oauth_token.json")
    monkeypatch.setattr(google_workspace, "STATE_PATH", tmp_path / "google_oauth_state.json")
    return TestClient(server.create_app())


def _token(client: TestClient) -> str:
    response = client.post("/auth/login", json={"username": "friday", "password": "super-secret"})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_api_requires_bearer_token(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    response = client.get("/tasks")

    assert response.status_code == 401


def test_api_allows_local_dashboard_cors_preflight(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    response = client.options(
        "/auth/login",
        headers={
            "Origin": "http://127.0.0.1:3001",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3001"


def test_api_login_create_list_and_get_task(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}

    created = client.post("/tasks", json={"title": "Research free APIs", "agent_id": "research_analyst"}, headers=headers)
    listing = client.get("/tasks", headers=headers)
    detail = client.get(f"/tasks/{created.json()['id']}", headers=headers)

    assert created.status_code == 200
    assert listing.status_code == 200
    assert detail.status_code == 200
    assert listing.json()[0]["title"] == "Research free APIs"
    assert detail.json()["messages"]


def test_api_decorates_task_progress_and_streams_tasks(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post("/tasks", json={"title": "Research free APIs", "agent_id": "research_analyst"}, headers=headers)
    task_id = int(created.json()["id"])
    task_queue.update_status(task_id, "active")
    task_queue.post_message(task_id, "office", "Progress 55%: specialist work is in progress.")

    listing = client.get("/tasks", headers=headers)
    snapshot = client.get("/dashboard/snapshot", headers=headers)
    with client.websocket_connect(f"/ws/tasks?token={token}") as websocket:
        payload = websocket.receive_json()
    with client.websocket_connect(f"/ws/dashboard?token={token}") as websocket:
        dashboard = websocket.receive_json()

    assert listing.status_code == 200
    assert listing.json()[0]["progress_percent"] == 55
    assert snapshot.status_code == 200
    assert snapshot.json()["tasks"][0]["progress_percent"] == 55
    assert "pcAwareness" in snapshot.json()
    assert "logs" in snapshot.json()
    assert "gateway" in snapshot.json()
    assert "controlRoom" in snapshot.json()
    assert payload["tasks"][0]["progress_percent"] == 55
    assert "offices" in payload
    assert "notifications" in payload
    assert "guardian" in payload
    assert "gateway" in payload
    assert dashboard["tasks"][0]["progress_percent"] == 55
    assert "agentQuality" in dashboard
    assert "skillsSummary" in dashboard


def test_api_streams_chat_and_notifications(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    token = _token(client)
    monkeypatch.setattr(server.orchestrator, "handle_command", lambda message: f"Echo: {message}")
    notification_center.add(
        source="test",
        category="dashboard",
        title="Realtime notice",
        message="Notification stream test.",
        severity=3,
    )

    with client.websocket_connect(f"/ws/chat?token={token}") as websocket:
        websocket.send_json({"id": "chat-1", "message": "hello friday"})
        ack = websocket.receive_json()
        reply = websocket.receive_json()

    with client.websocket_connect(f"/ws/notifications?token={token}") as websocket:
        notifications = websocket.receive_json()

    assert ack["type"] == "ack"
    assert reply["type"] == "reply"
    assert reply["reply"] == "Echo: hello friday"
    assert notifications["unread_count"] == 1
    assert notifications["items"][0]["title"] == "Realtime notice"


def test_api_gateway_and_control_room_endpoints(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}

    status_response = client.get("/gateway/status", headers=headers)
    event_response = client.post(
        "/gateway/events",
        headers=headers,
        json={"connector": "web", "event_type": "task_request", "title": "Plan support queue", "content": "Create a triage task."},
    )
    events_response = client.get("/gateway/events", headers=headers)
    room_response = client.get("/control-room/status", headers=headers)

    assert status_response.status_code == 200
    assert event_response.status_code == 200
    assert event_response.json()["task_id"] > 0
    assert events_response.status_code == 200
    assert events_response.json()[0]["title"] == "Plan support queue"
    assert room_response.status_code == 200
    assert "gateway" in room_response.json()


def test_api_connector_company_memory_benchmark_and_production_coding(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setattr(connector_runtime, "_post_json", lambda *args, **kwargs: {"ok": True, "status": 200, "summary": "sent"})
    monkeypatch.setattr(
        competitive_benchmark,
        "_readiness",
        lambda: {key: True for key in {
            "connector_runtime",
            "approval",
            "gateway",
            "signature",
            "approval_inbox",
            "audit",
            "desktop_sandbox",
            "ci",
            "proof",
            "company_runtime",
            "state_machine",
            "memory_governance",
            "control_room",
            "agency_mode",
            "playwright",
            "operator_skills",
            "skill_library",
            "model_router",
            "cloud_worker",
            "android_companion",
            "phone_mesh",
            "agency_business_layer",
            "evidence_required",
        }},
    )
    project = tmp_path / "client-app"
    project.mkdir()
    (project / "package.json").write_text('{"scripts":{"test":"vitest","build":"vite build"}}', encoding="utf-8")

    queued = client.post("/connectors/send", headers=headers, json={"connector": "telegram", "target": "123", "body": "Draft only"})
    approved = client.post(f"/connectors/outbox/{queued.json()['id']}/approve", headers=headers, json={"note": "ok", "dispatch": True})
    company = client.post("/company/worker-state", headers=headers, json={"agent_id": "sales_agent", "state": "working", "progress": 0.2})
    memory = client.post("/memory/governance/remember", headers=headers, json={"kind": "client", "title": "Ada tone", "content": "Likes short updates.", "confidence": 0.8})
    benchmark = client.post("/benchmark/run", headers=headers, json={"candidate": "friday", "baseline": "openclaw"})
    coding = client.post("/coding/production/prepare", headers=headers, json={"root": str(project), "request": "ship safely", "run_scans": False})

    assert queued.status_code == 200
    assert queued.json()["status"] == "pending_approval"
    assert approved.status_code == 200
    assert approved.json()["status"] == "sent"
    assert company.status_code == 200
    assert company.json()["agent_id"] == "sales_agent"
    assert memory.status_code == 200
    assert memory.json()["kind"] == "client"
    assert benchmark.status_code == 200
    assert benchmark.json()["metrics"]["completion_rate"] == 1.0
    assert coding.status_code == 200
    assert (project / ".friday" / "ci-plan.yml").exists()


def test_api_stores_and_serves_project_reference_images(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    repo = tmp_path / "repo"
    repo.mkdir()
    image_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="

    created = client.post(
        "/project-memory/reference-images",
        headers=headers,
        json={
            "root": str(repo),
            "title": "Sample UI",
            "note": "Use this screen as the visual direction.",
            "filename": "sample.png",
            "content_type": "image/png",
            "data_url": f"data:image/png;base64,{image_data}",
        },
    )
    listing = client.get("/project-memory/reference-images", headers=headers, params={"root": str(repo)})
    snapshot = client.get("/dashboard/snapshot", headers=headers)

    assert created.status_code == 200
    payload = created.json()
    assert payload["title"] == "Sample UI"
    assert payload["url"].startswith("/project-memory/reference-images/")
    assert listing.status_code == 200
    assert listing.json()[0]["note"] == "Use this screen as the visual direction."
    assert snapshot.status_code == 200
    assert snapshot.json()["projectReferences"][0]["title"] == "Sample UI"

    served = client.get(payload["url"], headers=headers)
    served_with_token = client.get(f"{payload['url']}?token={token}")

    assert served.status_code == 200
    assert served.content.startswith(b"\x89PNG")
    assert served_with_token.status_code == 200


def test_api_reassigns_task(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}

    created = client.post("/tasks", json={"title": "Read docs", "agent_id": "senior_developer"}, headers=headers)
    reassigned = client.post(f"/tasks/{created.json()['id']}/reassign", json={"agent_id": "research", "status": "pending"}, headers=headers)

    assert reassigned.status_code == 200
    assert reassigned.json()["agent_id"] == "research_analyst"
    assert reassigned.json()["status"] == "pending"


def test_api_starts_limited_worker_count(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    counts = []
    monkeypatch.setattr(server.background_agents, "start_workers", lambda count=None: counts.append(count) or count)

    response = client.post("/workers/start?count=1", headers=headers)

    assert response.status_code == 200
    assert response.json()["workers"] == 1
    assert counts == [1]


def test_api_exposes_command_center_expansion(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    sample = tmp_path / "safe.txt"
    sample.write_text("safe", encoding="utf-8")

    responses = [
        client.get("/agent-scheduler/status", headers=headers),
        client.post("/agent-scheduler/plan", json={"mode": "voice", "voice_active": True}, headers=headers),
        client.post("/test-build-monitor/run", json={"root": str(tmp_path), "command": f'"{sys.executable}" -c "print(4)"', "create_proof": False}, headers=headers),
        client.post("/reliability-score/snapshot", headers=headers),
        client.post("/model-benchmark/run", json={"task_types": ["coding"], "run_live": False}, headers=headers),
        client.post("/deployment-brain/inspect", json={"root": str(tmp_path), "create_proof": False}, headers=headers),
        client.post("/os-autopilot/recommend", headers=headers),
        client.post("/version-guardian/preflight", json={"instruction": "edit safely", "paths": [str(sample)]}, headers=headers),
    ]

    assert all(response.status_code == 200 for response in responses)
    assert responses[1].json()["desired_workers"] == 0
    assert responses[2].json()["status"] == "passed"


def test_api_chat_routes_to_friday_orchestrator(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    calls = []
    monkeypatch.setattr(server.orchestrator, "handle_command", lambda text: calls.append(text) or "Ready.")

    response = client.post("/chat", json={"message": " Friday, team status "}, headers=headers)

    assert response.status_code == 200
    assert response.json()["reply"] == "Ready."
    assert response.json()["message"] == "Friday, team status"
    assert calls == ["Friday, team status"]


def test_api_stores_chat_attachment(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "CHAT_UPLOAD_DIR", tmp_path / "chat_uploads")
    headers = {"Authorization": f"Bearer {_token(client)}"}
    encoded = base64.b64encode(b"hello").decode("ascii")

    response = client.post(
        "/chat/attachments",
        json={
            "filename": "brief.pdf",
            "content_type": "application/pdf",
            "data_url": f"data:application/pdf;base64,{encoded}",
        },
        headers=headers,
    )
    payload = response.json()
    rejected = client.post(
        "/chat/attachments",
        json={
            "filename": "installer.exe",
            "content_type": "application/octet-stream",
            "data_url": f"data:application/octet-stream;base64,{encoded}",
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert payload["filename"] == "brief.pdf"
    assert payload["kind"] == "document"
    assert Path(payload["path"]).read_bytes() == b"hello"
    assert rejected.status_code == 400


def test_api_exposes_agent_offices(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    monkeypatch.setattr(agent_office.competence, "get_agent_map", lambda agent_id: {"general": 0.6})

    client.post("/tasks", json={"title": "Write tests", "agent_id": "qa_engineer"}, headers=headers)
    response = client.get("/agents/offices", headers=headers)
    detail = client.get("/agents/qa_engineer/office", headers=headers)

    assert response.status_code == 200
    assert any(item["agent_id"] == "qa_engineer" for item in response.json())
    assert detail.status_code == 200
    assert detail.json()["room_name"] == "QA Lab"


def test_api_exposes_agent_thought_bus(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}

    created = client.post(
        "/thoughts",
        json={
            "source_agent_id": "research_analyst",
            "target_agent_id": "senior_developer",
            "packet_type": "finding",
            "summary": "Docs say use FastAPI Depends",
            "content": {"notes": "Bearer auth belongs in a dependency."},
            "confidence": 0.8,
            "priority": 2,
        },
        headers=headers,
    )
    listing = client.get("/thoughts?target_agent_id=senior_developer", headers=headers)
    context = client.get("/thoughts/context/senior_developer?query=FastAPI%20auth", headers=headers)
    resolved = client.post(f"/thoughts/{created.json()['id']}/resolve", json={"note": "used"}, headers=headers)

    assert created.status_code == 200
    assert listing.status_code == 200
    assert listing.json()[0]["summary"] == "Docs say use FastAPI Depends"
    assert "Silent thought bus context" in context.json()["context"]
    assert resolved.json()["status"] == "resolved"


def test_api_exposes_mission_control_and_autonomy_labs(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    project = tmp_path / "project"
    project.mkdir()
    (project / "package.json").write_text('{"version":"0.0.1","scripts":{"build":"next build"}}', encoding="utf-8")
    (project / "README.md").write_text("# Project", encoding="utf-8")

    mission = client.post("/missions", json={"goal": "Build a dashboard MVP", "root": str(project)}, headers=headers)
    mission_id = mission.json()["id"]
    detail = client.get(f"/missions/{mission_id}", headers=headers)
    qa = client.post("/qa-lab/run", json={"root": str(project), "mission_id": mission_id, "run_tests": False}, headers=headers)
    release = client.post("/release/prepare", json={"root": str(project), "mission_id": mission_id}, headers=headers)
    extension = client.post(
        "/browser-extension/context",
        json={"url": "https://example.com?token=secret", "title": "Token page", "forms": [{"fields": [{"name": "password", "type": "password"}]}]},
        headers=headers,
    )
    semantic = client.post("/semantic/index", json={"path": str(project)}, headers=headers)
    rhythm = client.post("/operating-rhythm/energy", json={"mood": "focused", "energy": 8, "focus": 8}, headers=headers)
    continuity = client.post("/continuity/threads", json={"topic": "pytest timeout", "summary": "Full pytest timed out after five minutes."}, headers=headers)
    fused = client.get("/context-fusion/status", headers=headers)
    silence = client.post("/silence/mode", json={"mode": "coding"}, headers=headers)
    deep = client.post("/deep-project-autopilot/run", json={"root": str(project), "run_tests": False}, headers=headers)
    skill = client.post("/skill-evolution/observe", json={"signature": "deploy next app", "description": "Deploy Next app"}, headers=headers)
    safety = client.post("/safety-guardian/preflight", json={"instruction": "delete .env"}, headers=headers)
    phone = client.post("/phone-mesh/handoff", json={"title": "continue on PC"}, headers=headers)
    stream = client.get("/semantic/status", headers=headers)

    assert mission.status_code == 200
    assert detail.status_code == 200
    assert detail.json()["phases"]
    assert qa.status_code == 200
    assert qa.json()["mission_id"] == mission_id
    assert release.status_code == 200
    assert release.json()["status"] == "pending_approval"
    assert extension.status_code == 200
    assert extension.json()["redactions"] >= 1
    assert semantic.status_code == 200
    assert rhythm.status_code == 200
    assert continuity.status_code == 200
    assert fused.status_code == 200
    assert silence.status_code == 200
    assert deep.status_code == 200
    assert skill.status_code == 200
    assert safety.status_code == 200
    assert phone.status_code == 200
    assert stream.json()["chunks"] >= 1


def test_api_status_exposes_source_pdf_and_ui_stack(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}

    response = client.get("/v2/status", headers=headers)

    assert response.status_code == 200
    assert response.json()["source_pdf"].endswith("JARVIS_v2_Phase_Planning_v3.pdf")
    assert response.json()["ui_stack"] == {"desktop": "Electron", "web": "Next.js"}
    assert "proactive_guardian_mode" in response.json()["implemented"]
    assert "continuity_brain" in response.json()["implemented"]
    assert "real_time_context_fusion" in response.json()["implemented"]


def test_api_exposes_awake_friday_layers(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}

    finance = client.post("/finance/budgets", json={"category": "food", "amount": 5000}, headers=headers)
    event = client.post("/events/run-once", headers=headers)
    simulation = client.post("/sandbox/simulate", json={"kind": "desktop", "instruction": "open Gmail"}, headers=headers)
    route = client.post("/model-router/choose", json={"task_type": "coding", "text": "fix tests"}, headers=headers)

    assert finance.status_code == 200
    assert event.status_code == 200
    assert simulation.status_code == 200
    assert route.status_code == 200
    assert simulation.json()["risk_level"] in {"low", "medium", "high"}
    assert route.json()["provider"]


def test_api_exposes_agency_mode(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}

    lead = client.post("/agency/leads", json={"name": "Ada Clinic", "email": "ada@example.test", "need": "Need booking automation."}, headers=headers)
    score = client.post("/agency/leads/score", headers=headers)
    draft = client.post("/agency/outreach/draft", json={"lead_id": lead.json()["id"], "service_offer": "booking automation"}, headers=headers)
    approval = client.post("/agency/outreach/approve", json={"ids": [draft.json()["id"]]}, headers=headers)
    invoice = client.post("/agency/invoices", json={"client_name": "Ada Clinic", "amount": 250, "currency": "USD"}, headers=headers)
    profit = client.get("/agency/profit", headers=headers)
    status = client.get("/agency/status", headers=headers)

    assert lead.status_code == 200
    assert score.json()["scored"] == 1
    assert draft.json()["status"] == "draft"
    assert approval.json()["approved"] == [draft.json()["id"]]
    assert invoice.json()["amount"] == 250
    assert profit.status_code == 200
    assert status.json()["lead_count"] == 1


def test_api_exposes_companion_growth_layers(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    monkeypatch.setattr(server.research_briefings.research, "research_topic", lambda topic, max_sources=3: {"notes": "- Fresh finding"})
    monkeypatch.setattr(server.contextual_workspace.project_autopilot, "inspect_project", lambda root, run_tests=False: {"issues": []})

    tone = client.post("/emotion/analyze", json={"text": "This is wrong and I am frustrated"}, headers=headers)
    person = client.post("/crm/people", json={"name": "Ada", "relationship": "friend"}, headers=headers)
    card = client.post("/learning-coach/cards", json={"topic": "Python", "prompt": "What is a dict?", "answer": "A key-value mapping."}, headers=headers)
    quiz = client.get("/learning-coach/quiz?topic=Python", headers=headers)
    brief = client.post("/research-briefings/generate", json={"topic": "free APIs"}, headers=headers)
    workspace = client.post("/workspace-context/prepare", json={"root": str(tmp_path)}, headers=headers)
    offline = client.post("/offline-survival/activate", headers=headers)
    note = client.post("/personal-timeline/notes", json={"title": "Worked on Friday"}, headers=headers)
    workflow = client.post("/skill-training/workflows", json={"name": "Deploy app"}, headers=headers)
    step = client.post(f"/skill-training/workflows/{workflow.json()['id']}/steps", json={"instruction": "Run build"}, headers=headers)
    published = client.post(f"/skill-training/workflows/{workflow.json()['id']}/publish", headers=headers)

    assert tone.json()["tone"] == "frustrated"
    assert person.json()["name"] == "Ada"
    assert card.json()["prompt"] == "What is a dict?"
    assert quiz.json()["cards"]
    assert "Fresh finding" in brief.json()["summary"]
    assert "summary" in workspace.json()
    assert offline.json()["mode"] == "offline_survival"
    assert note.json()["title"] == "Worked on Friday"
    assert step.json()["steps"]
    assert published.json()["skill_id"]


def test_api_exposes_executive_autonomy_layers(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    monkeypatch.setattr(server.executive_capabilities, "_http_status", lambda url: {"url": url, "status": 200, "ok": True})
    monkeypatch.setattr(server.executive_capabilities, "_dns_summary", lambda host: {"host": host, "addresses": ["127.0.0.1"]})
    monkeypatch.setattr(server.executive_capabilities.capability_center, "web_security_headers", lambda target: {"summary": "Headers checked."})
    monkeypatch.setattr(server.executive_capabilities.project_autopilot, "inspect_project", lambda root, run_tests=False: {"issues": []})

    personal_knowledge_vault.remember_preference("Reply style", "Keep it direct.")
    generated = client.post("/memory-review/generate", headers=headers)
    reviews = client.get("/memory-review/items", headers=headers)
    resolved = client.post(f"/memory-review/items/{reviews.json()[0]['id']}/resolve", json={"decision": "keep"}, headers=headers)
    autopilot = client.post("/task-autopilot/start", json={"goal": "Improve a Python API for speed and security", "sphere": "programming", "root": str(tmp_path)}, headers=headers)
    profile = client.post("/personality/profile", json={"profile": "debugger"}, headers=headers)
    recording = client.post("/skill-recorder/start", json={"name": "Check Render logs"}, headers=headers)
    step = client.post(f"/skill-recorder/{recording.json()['id']}/step", json={"narration": "First open Render, then check logs"}, headers=headers)
    finished = client.post(f"/skill-recorder/{recording.json()['id']}/finish", headers=headers)
    search = client.post("/personal-search", json={"query": "reply style"}, headers=headers)
    trust = client.post("/trust-meter/assess", json={"instruction": "delete old files", "domain": "desktop"}, headers=headers)
    firewall = client.post("/privacy-firewall/check", json={"instruction": "read my .env password"}, headers=headers)
    deploy = client.post("/deployment/inspect", json={"target": "https://example.com", "root": str(tmp_path)}, headers=headers)
    summary = client.get("/executive/summary", headers=headers)

    assert generated.status_code == 200
    assert resolved.json()["decision"] == "keep"
    assert autopilot.json()["sphere"] == "programming"
    assert len(autopilot.json()["task_ids"]) >= 5
    assert profile.json()["profile"] == "debugger"
    assert len(step.json()["steps"]) >= 2
    assert finished.json()["status"] == "published"
    assert search.json()["results"]
    assert trust.json()["requires_approval"] is True
    assert firewall.json()["sensitivity"] == "secret"
    assert deploy.json()["http"]["ok"] is True
    assert summary.json()["personality"]["profile"] == "debugger"


def test_api_exposes_benchmark(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}

    response = client.get("/metrics/api-benchmark", headers=headers)

    assert response.status_code == 200
    assert "checks" in response.json()


def test_api_exposes_desktop_task_sessions(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    session_id = desktop_tasks.create_session("open first email", max_steps=5)
    desktop_tasks.append_step(
        session_id,
        step_number=1,
        status="action",
        progress="Clicked inbox.",
        action={"action": "click", "x": 10, "y": 20},
        result="Clicked.",
        screenshot=str(tmp_path / "screen.png"),
    )

    listing = client.get("/desktop/tasks", headers=headers)
    detail = client.get(f"/desktop/tasks/{session_id}", headers=headers)

    assert listing.status_code == 200
    assert listing.json()[0]["goal"] == "open first email"
    assert detail.status_code == 200
    assert detail.json()["steps"][0]["screenshot_name"] == "screen.png"


def test_api_starts_desktop_task_session_without_blocking(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    started = []
    monkeypatch.setattr(server, "_start_desktop_task_thread", lambda task_id, instruction, max_steps: started.append((task_id, instruction, max_steps)))

    response = client.post("/desktop/tasks", json={"instruction": "open calculator", "max_steps": 7}, headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "active"
    assert payload["goal"] == "open calculator"
    assert payload["reply"].startswith("Desktop task #")
    assert started == [(payload["id"], "open calculator", 7)]


def test_api_desktop_task_controls(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    session_id = desktop_tasks.create_session("open settings", max_steps=5)
    monkeypatch.setattr(server.desktop_vision, "pause_desktop_task", lambda task_id: f"paused {task_id}")
    monkeypatch.setattr(server.desktop_vision, "resume_desktop_task", lambda task_id: f"resumed {task_id}")
    monkeypatch.setattr(server.desktop_vision, "confirm_desktop_task", lambda task_id: f"confirmed {task_id}")
    monkeypatch.setattr(server.desktop_vision, "cancel_desktop_task", lambda task_id: f"cancelled {task_id}")

    assert client.post(f"/desktop/tasks/{session_id}/pause", headers=headers).json()["reply"] == f"paused {session_id}"
    assert client.post(f"/desktop/tasks/{session_id}/resume", headers=headers).json()["reply"] == f"resumed {session_id}"
    assert client.post(f"/desktop/tasks/{session_id}/confirm", headers=headers).json()["reply"] == f"confirmed {session_id}"
    assert client.post(f"/desktop/tasks/{session_id}/cancel", headers=headers).json()["reply"] == f"cancelled {session_id}"


def test_api_exposes_dynamic_ui_control(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    started = []
    monkeypatch.setattr(server.ui_control, "status", lambda app="", limit=12: {"summary": "ui ready", "app": app, "actions": [{"id": "click"}], "desktop_sessions": []})
    monkeypatch.setattr(server.ui_control, "context", lambda app="", instruction="": {"summary": f"{app} context", "instruction": instruction})
    monkeypatch.setattr(server.ui_control, "execute", lambda action, **kwargs: {"summary": f"{action} ok", "action": action, "input": kwargs})
    monkeypatch.setattr(server.ui_control, "task_instruction", lambda app, instruction: f"{app}: {instruction}")
    monkeypatch.setattr(server, "_start_desktop_task_thread", lambda task_id, instruction, max_steps: started.append((task_id, instruction, max_steps)))

    status_response = client.get("/ui-control/status?app=chrome", headers=headers)
    context_response = client.post("/ui-control/context", json={"app": "chrome", "instruction": "inspect"}, headers=headers)
    action_response = client.post("/ui-control/action", json={"action": "click", "x": 10, "y": 20}, headers=headers)
    task_response = client.post("/ui-control/task", json={"action": "desktop_task", "app": "chrome", "instruction": "open settings", "max_steps": 6}, headers=headers)

    assert status_response.json()["summary"] == "ui ready"
    assert context_response.json()["summary"] == "chrome context"
    assert action_response.json()["summary"] == "click ok"
    assert task_response.json()["status"] == "active"
    assert started == [(task_response.json()["id"], "chrome: open settings", 6)]


def test_api_exposes_visual_monitor(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}

    monkeypatch.setattr(server.visual_monitor, "status", lambda: {"running": False, "source": "screen", "event_count": 0, "latest_event": None})
    monkeypatch.setattr(server.visual_monitor, "start_monitor", lambda source, realtime=False: {"running": True, "source": source, "realtime": realtime, "event_count": 1, "latest_event": None})
    monkeypatch.setattr(server.visual_monitor, "stop_monitor", lambda: {"running": False, "source": "screen", "event_count": 1, "latest_event": None})
    monkeypatch.setattr(
        server.visual_monitor,
        "capture_once",
        lambda source, analyze=None: [{"id": 7, "source": source, "event_type": "change", "summary": "Screen changed.", "frame_path": str(tmp_path / "screen.png"), "frame_name": "screen.png"}],
    )
    monkeypatch.setattr(
        server.visual_monitor,
        "recent_events",
        lambda limit=20, source="": [{"id": 7, "source": "screen", "event_type": "change", "summary": "Screen changed.", "frame_path": str(tmp_path / "screen.png"), "frame_name": "screen.png"}],
    )

    assert client.get("/vision/monitor", headers=headers).status_code == 200
    started = client.post("/vision/monitor/start", json={"source": "screen"}, headers=headers)
    captured = client.post("/vision/monitor/capture", json={"source": "screen"}, headers=headers)
    events = client.get("/vision/events", headers=headers)
    stopped = client.post("/vision/monitor/stop", headers=headers)

    assert started.json()["running"] is True
    assert captured.json()["events"][0]["frame_url"] == "/vision/frames/screen/screen.png"
    assert events.json()[0]["summary"] == "Screen changed."
    assert stopped.json()["running"] is False


def test_api_exposes_pc_awareness(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    payload = {
        "available": True,
        "summary": "active window: Figma",
        "active_window": "Active window: Figma",
        "running_apps": [{"name": "Figma", "pid": 11}],
        "installed_apps": [{"name": "Figma"}],
        "desktop_apps": [{"name": "Figma", "path": r"C:\Users\User\Desktop\Figma.lnk"}],
        "home_screen_apps": [{"name": "Figma"}],
        "shortcuts": [{"name": "Figma"}],
        "stats": {"running_apps": 1, "installed_apps": 1, "desktop_apps": 1, "shortcuts": 1},
    }
    monkeypatch.setattr(server.pc_awareness, "snapshot", lambda: payload)
    monkeypatch.setattr(server.pc_awareness, "refresh", lambda: payload | {"summary": "refreshed"})
    monkeypatch.setattr(server.pc_awareness, "running_apps", lambda limit=80: payload["running_apps"][:limit])
    monkeypatch.setattr(server.pc_awareness, "installed_apps", lambda limit=200: payload["installed_apps"][:limit])
    monkeypatch.setattr(server.pc_awareness, "desktop_apps", lambda limit=200: payload["desktop_apps"][:limit])
    monkeypatch.setattr(server.pc_awareness, "find_app", lambda query: {"found": True, "name": "Figma", "query": query})

    assert client.get("/pc/awareness", headers=headers).json()["active_window"].endswith("Figma")
    assert client.post("/pc/awareness/refresh", headers=headers).json()["summary"] == "refreshed"
    assert client.get("/pc/apps/running", headers=headers).json()[0]["name"] == "Figma"
    assert client.get("/pc/apps/installed", headers=headers).json()[0]["name"] == "Figma"
    assert client.get("/pc/apps/desktop", headers=headers).json()[0]["name"] == "Figma"
    assert client.get("/pc/apps/find?query=figma", headers=headers).json()["found"] is True


def test_api_exposes_android_phone_bridge(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    monkeypatch.setattr(server.phone_bridge, "_adb_path", lambda: "adb")
    monkeypatch.setattr(server.phone_bridge, "adb_devices", lambda: [{"serial": "abc123", "state": "device", "metadata": {"model": "Pixel"}}])
    monkeypatch.setattr(
        server.phone_bridge,
        "_run_adb",
        lambda args, serial="": {"ok": True, "stdout": "level: 66\nstatus: 2\nplugged: 1\n", "stderr": "", "returncode": 0},
    )
    monkeypatch.setattr(server.phone_bridge, "send_notification", lambda *args, **kwargs: {"ok": True, "summary": "Notification sent to phone."})

    registered = client.post("/phone/devices", json={"name": "Pixel", "adb_serial": "abc123", "ntfy_topic": "topic"}, headers=headers)
    status_payload = client.get("/phone/status", headers=headers)
    battery = client.get("/phone/battery", headers=headers)
    notify = client.post("/phone/notify", json={"message": "hello"}, headers=headers)
    ring = client.post("/phone/ring", json={"message": "wake up"}, headers=headers)
    opened = client.post("/phone/open-url", json={"url": "example.com"}, headers=headers)
    events = client.get("/phone/events", headers=headers)

    assert registered.json()["name"] == "Pixel"
    assert status_payload.json()["adb_connected"] is True
    assert battery.json()["level"] == 66
    assert notify.json()["ok"] is True
    assert "summary" in ring.json()
    assert opened.json()["ok"] is True
    assert events.status_code == 200


def test_api_exposes_capability_center_and_security_scope(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    monkeypatch.setattr(server.capability_center, "home_status", lambda: {"router": {"gateway": "192.168.1.1"}, "printers": [], "bluetooth": [], "smart_devices": [], "local_network_devices": [], "connection_quality": {}})
    monkeypatch.setattr(server.capability_center, "security_overview", lambda light=False: {"summary": "secure", "open_ports": {"open_ports": []}, "suspicious_processes": [], "startup_persistence": []})
    monkeypatch.setattr(server.capability_center, "maintenance_report", lambda light=False: {"summary": "maint", "suggestions": []})
    monkeypatch.setattr(server.capability_center, "workspace_project_map", lambda root="", max_files=None: {"summary": "mapped", "total_files_scanned": 3})
    monkeypatch.setattr(server.capability_center, "personal_brief", lambda: {"summary": "brief"})
    monkeypatch.setattr(server.capability_center, "personal_next_action", lambda: {"title": "Ship", "reason": "highest priority"})
    monkeypatch.setattr(server.capability_center, "scan_open_ports", lambda target, ports=None: {"ok": True, "target": target, "open_ports": [{"port": 8000}], "summary": "1 open"})

    overview = client.get("/capabilities/overview", headers=headers)
    scope = client.post("/security/scopes", json={"target": "127.0.0.1", "kind": "local"}, headers=headers)
    scopes = client.get("/security/scopes", headers=headers)
    ports = client.post("/security/open-ports", json={"target": "127.0.0.1", "ports": [8000]}, headers=headers)
    recipe = client.post("/automation/recipes", json={"name": "Ping phone", "action_type": "notify_phone", "action": {"message": "hi"}}, headers=headers)

    assert overview.json()["personal"]["summary"] == "brief"
    assert scope.json()["status"] == "verified"
    assert scopes.json()[0]["target"] == "127.0.0.1"
    assert ports.json()["open_ports"][0]["port"] == 8000
    assert recipe.json()["name"] == "Ping phone"


def test_api_exposes_power_modules(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    project = tmp_path / "project"
    project.mkdir()
    (project / "auth.py").write_text("# TODO auth\n", encoding="utf-8")
    monkeypatch.setattr(server.app_operators.pc_awareness, "snapshot", lambda: {"running_apps": []})
    monkeypatch.setattr(server.app_operators.desktop_tasks, "DB_PATH", tmp_path / "desktop_tasks.sqlite3")

    installed = client.post("/memory/skills/install", json={"key": "vscode_debugger"}, headers=headers)
    skill_id = installed.json()[0]["id"]
    toggled = client.post(f"/memory/skills/{skill_id}/toggle", json={"enabled": False}, headers=headers)
    analysis = client.post("/workspace-brain/analyze", json={"root": str(project)}, headers=headers)
    question = client.post("/workspace-brain/question", json={"question": "where is auth logic", "root": str(project)}, headers=headers)
    operators = client.get("/app-operators", headers=headers)
    coding = client.post("/coding/autonomous/start", json={"request": "add docs", "root": str(project)}, headers=headers)
    life = client.get("/personal/os/plan", headers=headers)
    ha = client.get("/home-assistant/status", headers=headers)
    backup = client.post("/backup/file", json={"path": str(project / "auth.py"), "label": "test"}, headers=headers)

    assert installed.status_code == 200
    assert toggled.json()["enabled"] is False
    assert analysis.json()["todos"]
    assert question.json()["results"]
    assert operators.json()
    assert coding.json()["ok"] is True
    assert "summary" in life.json()
    assert ha.status_code == 200
    assert backup.json()["ok"] is True


def test_api_exposes_guardian_os_modules(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("# TODO fix auth\nprint('hi')\n", encoding="utf-8")
    monkeypatch.setattr(server.proactive_guardian.capability_center, "maintenance_report", lambda light=True: {"health": {}, "disk": []})
    monkeypatch.setattr(server.proactive_guardian.capability_center, "security_overview", lambda light=True: {"suspicious_processes": [], "open_ports": {"open_ports": []}})
    monkeypatch.setattr(server.proactive_guardian.phone_bridge, "status", lambda: {"battery": {"available": False}})
    monkeypatch.setattr(server.proactive_guardian.task_queue, "list_tasks", lambda status="", limit=10: [])
    monkeypatch.setattr(server.proactive_guardian.app_integrations, "list_reminders", lambda include_done=False, limit=100: [])
    monkeypatch.setattr(server.project_autopilot.capability_center, "workspace_dependency_health", lambda root: {"audits": []})
    monkeypatch.setattr(server.pc_timeline.pc_awareness, "refresh", lambda: {"active_window": "VS Code", "running_apps": [], "summary": "VS Code active"})

    assert client.post("/guardian/scan", headers=headers).json()["summary"]
    assert client.get("/notifications/summary", headers=headers).status_code == 200
    assert client.post("/knowledge-vault/items", json={"kind": "preference", "title": "Quiet alerts"}, headers=headers).json()["kind"] == "preference"
    assert client.post("/voice/repair", json={"expected_text": "Friday reduce volume to 40", "heard_text": "Freddie reduce volume"}, headers=headers).json()["ok"] is True
    assert client.post("/project-autopilot/inspect", json={"root": str(project)}, headers=headers).json()["issues"]
    assert client.post("/pc/timeline/capture", headers=headers).json()["snapshot_event"]["event_type"] == "pc_snapshot"
    assert client.post("/goals/plan", json={"title": "Ship Guardian OS"}, headers=headers).json()["steps"]
    assert client.post("/files/local/index", json={"paths": [str(project)], "max_files": 10}, headers=headers).json()["indexed"] == 1
    assert client.post("/files/local/answer", json={"query": "fix auth"}, headers=headers).json()["results"]
    assert client.post("/study/sessions", json={"title": "Lesson", "transcript": "A variable is a named value. Need to review scope."}, headers=headers).json()["action_items"]
    assert client.post("/automation/from-text", json={"text": "When I open VS Code notify my phone"}, headers=headers).json()["ok"] is True


def test_api_serves_visual_frame_with_token(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    token = _token(client)
    root = tmp_path / "visual_frames" / "screen"
    root.mkdir(parents=True)
    (root / "frame.png").write_text("fake image", encoding="utf-8")

    response = client.get(f"/vision/frames/screen/frame.png?token={token}")

    assert response.status_code == 200
    assert response.text == "fake image"


def test_api_exposes_deep_app_integrations(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    (tmp_path / "main.py").write_text("print('calendar reminder')", encoding="utf-8")

    contact = client.post("/integrations/contacts", json={"name": "Ada", "email": "ada@example.com"}, headers=headers)
    reminder = client.post("/integrations/reminders", json={"title": "call Ada"}, headers=headers)
    event = client.post("/integrations/calendar/events", json={"title": "planning"}, headers=headers)
    doc = client.post("/integrations/docs", json={"title": "Notes", "body": "hello"}, headers=headers)
    index = client.post("/integrations/workspace/index", json={"root": str(tmp_path), "max_files": 10}, headers=headers)
    search = client.get("/integrations/workspace/search?query=calendar", headers=headers)

    assert contact.status_code == 200
    assert reminder.status_code == 200
    assert event.status_code == 200
    assert doc.json()["path"].endswith(".md")
    assert index.json()["indexed"] >= 1
    assert search.json()[0]["path"] == "main.py"


def test_api_exposes_google_workspace_oauth_layer(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    monkeypatch.setattr(google_workspace, "status", lambda: {"configured": True, "authorized": True, "mode": "oauth"})
    monkeypatch.setattr(google_workspace, "start_auth", lambda: {"auth_url": "https://accounts.google.com/o/oauth2/auth", "state": "abc"})
    monkeypatch.setattr(google_workspace, "recent_gmail_messages", lambda limit=10: [{"id": "m1", "subject": "Hello"}])
    monkeypatch.setattr(google_workspace, "list_calendar_events", lambda limit=10: [{"id": "e1", "title": "Planning"}])
    monkeypatch.setattr(google_workspace, "create_document", lambda title, body="": {"id": "doc1", "title": title, "url": "https://docs.google.com/document/d/doc1/edit"})
    monkeypatch.setattr(google_workspace, "create_sheet", lambda title, headers=None: {"id": "sheet1", "title": title, "url": "https://docs.google.com/spreadsheets/d/sheet1/edit"})

    status_payload = client.get("/integrations/google/status", headers=headers)
    start = client.post("/integrations/google/oauth/start", headers=headers)
    gmail = client.get("/integrations/google/gmail/messages", headers=headers)
    calendar = client.get("/integrations/google/calendar/events", headers=headers)
    doc = client.post("/integrations/google/docs", json={"title": "OAuth Notes", "body": "hello"}, headers=headers)
    sheet = client.post("/integrations/google/sheets", json={"title": "OAuth Sheet", "headers": ["A"]}, headers=headers)

    assert status_payload.json()["authorized"] is True
    assert start.json()["auth_url"].startswith("https://accounts.google.com/")
    assert gmail.json()[0]["subject"] == "Hello"
    assert calendar.json()[0]["title"] == "Planning"
    assert doc.json()["id"] == "doc1"
    assert sheet.json()["id"] == "sheet1"


def test_api_exposes_permission_control_center(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}

    listing = client.get("/permissions/rules", headers=headers)
    updated = client.put("/permissions/rules/send_email.send_email", json={"mode": "block"}, headers=headers)
    events = client.get("/permissions/events", headers=headers)
    reset = client.post("/permissions/reset", headers=headers)

    assert listing.status_code == 200
    assert any(rule["key"] == "send_email.send_email" for rule in listing.json())
    assert updated.json()["mode"] == "block"
    assert events.status_code == 200
    assert any(rule["mode"] == "ask" for rule in reset.json())


def test_api_exposes_cognition_endpoints(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    monkeypatch.setattr(world_model, "_active_window", lambda: "Friday Command Center")
    long_term_learning.record_learning("lesson", "attention", "Be stricter during background audio.")
    self_reflection.reflect_on_command("you lied, it did not work", "Done.")

    status_payload = client.get("/cognition/status", headers=headers)
    world_payload = client.get("/cognition/world", headers=headers)
    reflections = client.get("/cognition/reflections", headers=headers)
    learning = client.get("/cognition/learning", headers=headers)
    goal = client.post("/cognition/goals", json={"title": "Improve cognition"}, headers=headers)
    attention = client.post(
        "/cognition/attention/correction",
        json={"expected_text": "Friday how are you", "heard_text": "Freddie how are you"},
        headers=headers,
    )

    assert status_payload.status_code == 200
    assert world_payload.status_code == 200
    assert "summary" in world_payload.json()
    assert reflections.json()
    assert learning.json()
    assert goal.json()["title"] == "Improve cognition"
    assert "freddie" in attention.json()["profile"]["learned_aliases"]


def test_api_exposes_self_model_endpoints(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    autobiographical_memory.record_event("user_correction", "Volume correction", "The user said volume did not change.", importance=0.9)

    status_payload = client.get("/self/status", headers=headers)
    capabilities = client.get("/self/capabilities", headers=headers)
    access = client.get("/self/access", headers=headers)
    uncertainty = client.get("/self/uncertainty", headers=headers)
    failures = client.get("/self/failures", headers=headers)
    autobiography = client.get("/self/autobiography", headers=headers)
    identity_payload = client.get("/self/identity", headers=headers)
    why = client.get("/self/why-last-action", headers=headers)

    assert status_payload.status_code == 200
    assert status_payload.json()["identity"]["name"] == "Friday"
    assert capabilities.json()["tools"]
    assert "access" in access.json()
    assert "items" in uncertainty.json()
    assert "failures" in failures.json()
    assert autobiography.json()["events"][0]["title"] == "Volume correction"
    assert identity_payload.json()["must_never_pretend"]
    assert "summary" in why.json()


def test_api_exposes_self_update_dashboard_workflow(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    target = tmp_path / "sample.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setattr(self_update, "config_value", lambda key, default=None: False if key == "self_update_run_tests" else default)

    proposed = client.post("/self-updates", json={"request": "change sample value"}, headers=headers)
    update_id = proposed.json()["id"]
    listed = client.get("/self-updates", headers=headers)
    approved = client.post(
        f"/self-updates/{update_id}/approve",
        json={"confirmation": f"I authorize self update {update_id}"},
        headers=headers,
    )
    staged = client.post(
        f"/self-updates/{update_id}/stage",
        json={"path": "sample.py", "find_text": "VALUE = 1", "replace_text": "VALUE = 2", "summary": "Update sample."},
        headers=headers,
    )

    assert proposed.status_code == 200
    assert listed.json()[0]["id"] == update_id
    assert approved.json()["status"] == "approved"
    assert staged.json()["path"] == "sample.py"


def test_api_exports_neo4j_cypher(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    monkeypatch.setattr(server.neo4j_migration, "export_cypher", lambda: {"path": "data/knowledge_graph.cypher", "nodes": 0, "edges": 0})

    response = client.post("/graph/neo4j/export", headers=headers)

    assert response.status_code == 200
    assert response.json()["path"].endswith("knowledge_graph.cypher")


def test_api_exposes_blackboard_contracts_memory_eval_approvals_and_voice(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}
    created = client.post("/tasks", json={"title": "Research reliability", "agent_id": "research_analyst"}, headers=headers)
    task_id = int(created.json()["id"])
    task_contracts.ensure_contract(task_queue.get_task(task_id))
    agent_blackboard.post_item("research_analyst", "question", "Need QA", "What should QA verify?", task_id=task_id, target_agent_id="qa_engineer")
    agent_memory.remember("research_analyst", "fact", "Free API note", "Gemini has a free tier for testing.", tags=["api"])
    evaluation_lab.record_event("unsupported_claim", "Blocked a fake success claim.", source="test")
    voice_reliability.record_sample("Friady hello", expected_text="Friday hello", backend="test", accepted=False, correction_applied=True)

    blackboard = client.get("/blackboard/summary", headers=headers)
    items = client.get("/blackboard/items", headers=headers)
    contract = client.get(f"/contracts/{task_id}", headers=headers)
    memory_payload = client.get("/agent-memory/research_analyst", headers=headers)
    evaluation = client.get("/evaluation/summary", headers=headers)
    approvals = client.get("/approvals/summary", headers=headers)
    voice = client.get("/voice/reliability/summary", headers=headers)
    streaming_sample = client.post(
        "/voice/reliability/sample",
        json={"heard_text": "Friday hello", "backend": "browser-web-speech", "accepted": True},
        headers=headers,
    )

    assert blackboard.status_code == 200
    assert blackboard.json()["questions"]
    assert items.json()[0]["title"] == "Need QA"
    assert contract.json()["goal"] == "Research reliability"
    assert memory_payload.json()["items"][0]["title"] == "Free API note"
    assert evaluation.json()["counts"]["unsupported_claim"] == 1
    assert approvals.status_code == 200
    assert voice.json()["backends"]["test"]["mistakes"] == 1
    assert streaming_sample.json()["sample_id"]


def test_api_playwright_status_is_safe_when_not_installed(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    headers = {"Authorization": f"Bearer {_token(client)}"}

    response = client.get("/browser/playwright/status", headers=headers)

    assert response.status_code == 200
    assert "available" in response.json()

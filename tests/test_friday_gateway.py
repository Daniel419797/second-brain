from core import agency_mode, approval_inbox, audit_log, cloud_worker_mode, company_runtime, competitive_benchmark, connector_runtime, friday_gateway, memory_governance, notification_center, personal_knowledge_vault, production_coding_autonomy, project_memory, skill_library, task_queue, trust_proof


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(friday_gateway, "DB_PATH", tmp_path / "friday_gateway.sqlite3")
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(approval_inbox, "DB_PATH", tmp_path / "approval_inbox.sqlite3")
    monkeypatch.setattr(notification_center, "DB_PATH", tmp_path / "notifications.sqlite3")
    monkeypatch.setattr(audit_log, "DB_PATH", tmp_path / "audit.sqlite3")
    monkeypatch.setattr(personal_knowledge_vault, "DB_PATH", tmp_path / "knowledge.sqlite3")
    monkeypatch.setattr(skill_library, "SKILLS_PATH", tmp_path / "skills.json")
    monkeypatch.setattr(skill_library, "EXAMPLES_PATH", tmp_path / "examples.json")
    monkeypatch.setattr(agency_mode, "DB_PATH", tmp_path / "agency.sqlite3")
    monkeypatch.setattr(cloud_worker_mode, "DB_PATH", tmp_path / "cloud_worker.sqlite3")
    monkeypatch.setattr(connector_runtime, "DB_PATH", tmp_path / "connector_runtime.sqlite3")
    monkeypatch.setattr(competitive_benchmark, "DB_PATH", tmp_path / "benchmark.sqlite3")
    monkeypatch.setattr(company_runtime, "DB_PATH", tmp_path / "company.sqlite3")
    monkeypatch.setattr(memory_governance, "DB_PATH", tmp_path / "memory_governance.sqlite3")
    monkeypatch.setattr(project_memory, "DB_PATH", tmp_path / "project_memory.sqlite3")
    monkeypatch.setattr(trust_proof, "DB_PATH", tmp_path / "trust_proof.sqlite3")

    def fake_config(key, default=None):
        values = {
            "friday_gateway_enabled": True,
            "friday_gateway_enabled_connectors": "web,desktop,browser_extension,github,gmail",
            "gateway_auto_task_events": True,
            "agency_workspace_dir": str(tmp_path / "Friday Agency"),
            "agency_default_currency": "USD",
            "cloud_worker_url": "",
            "connector_runtime_default_approval_required": True,
        }
        return values.get(key, default)

    monkeypatch.setattr(friday_gateway, "config_value", fake_config)
    monkeypatch.setattr(agency_mode, "config_value", fake_config)
    monkeypatch.setattr(cloud_worker_mode, "config_value", fake_config)
    monkeypatch.setattr(connector_runtime, "config_value", fake_config)


def test_gateway_routes_low_risk_events_to_tasks(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    event = friday_gateway.ingest_event("web", "task_request", "Plan weekly ops", "Create a project status page.", actor="user")

    assert event["ok"] is True
    assert event["status"] == "queued"
    assert event["task_id"] > 0
    task = task_queue.get_task(event["task_id"])
    assert task["agent_id"] == "project_manager"
    assert "Gateway task_request" in task["title"]


def test_gateway_high_risk_events_go_to_approval_inbox(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    friday_gateway.configure_connector("whatsapp", enabled=True, trust_level="sandboxed")

    event = friday_gateway.ingest_event("whatsapp", "client_message", "Send proposal", "Client asked for a quote.", actor="client")
    approvals = approval_inbox.summary()

    assert event["status"] == "pending_approval"
    assert event["approval_id"] > 0
    assert approvals["by_kind"]["gateway_event"] == 1


def test_gateway_business_memory_and_control_room(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    friday_gateway.remember_business_context("client_preference", "Ada likes short updates", "Use concise Friday status notes.")

    memory = friday_gateway.business_memory()
    room = friday_gateway.control_room()

    assert memory["counts"]["client_preference"] == 1
    assert "gateway" in room
    assert "approvals" in room
    assert "Control room" in room["summary"]

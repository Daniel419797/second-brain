from core import audit_log, company_runtime, memory_governance, notification_center, personal_knowledge_vault


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(company_runtime, "DB_PATH", tmp_path / "company.sqlite3")
    monkeypatch.setattr(memory_governance, "DB_PATH", tmp_path / "memory_governance.sqlite3")
    monkeypatch.setattr(personal_knowledge_vault, "DB_PATH", tmp_path / "vault.sqlite3")
    monkeypatch.setattr(audit_log, "DB_PATH", tmp_path / "audit.sqlite3")
    monkeypatch.setattr(notification_center, "DB_PATH", tmp_path / "notifications.sqlite3")


def test_company_runtime_tracks_workers_and_handoffs(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    runbooks = company_runtime.runbooks()
    state = company_runtime.set_worker_state("qa_engineer", "blocked", task_id=7, blocker="Needs preview URL", progress=0.4)
    handoff = company_runtime.handoff("project_manager", "devops", "Deploy preview", "Create preview build.", task_id=7, evidence=["QA blocked"])
    status = company_runtime.status()

    assert len(runbooks) >= 10
    assert state["state"] == "blocked"
    assert handoff["to_agent"] == "devops"
    assert status["blockers"]


def test_memory_governance_queues_low_confidence_and_contradictions(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    first = memory_governance.remember("client", "Ada deployment preference", "Prefers Render.", confidence=0.5)
    second = memory_governance.remember("client", "Ada deployment preference", "Prefers Vercel.", confidence=0.8)
    reviews = memory_governance.reviews(status="pending")

    assert first["id"] > 0
    assert second["contradiction"]["has_contradiction"] is True
    assert {item["reason"] for item in reviews} >= {"low_confidence", "possible_contradiction"}

    resolved = memory_governance.resolve(reviews[0]["id"], "approve", note="checked")

    assert resolved["status"] == "resolved"

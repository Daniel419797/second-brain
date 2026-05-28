from core import (
    adaptive_attention,
    app_integrations,
    automation_builder,
    capability_center,
    goal_manager,
    goal_regulation,
    local_file_intelligence,
    meeting_study_companion,
    notification_center,
    pc_timeline,
    personal_knowledge_vault,
    personal_life_os,
    project_autopilot,
    proactive_guardian,
    task_queue,
    voice_command_repair,
    voice_reliability,
    workspace_brain,
)


def _isolate_common(monkeypatch, tmp_path):
    monkeypatch.setattr(notification_center, "DB_PATH", tmp_path / "notifications.sqlite3")
    monkeypatch.setattr(personal_knowledge_vault, "DB_PATH", tmp_path / "vault.sqlite3")
    monkeypatch.setattr(voice_reliability, "DB_PATH", tmp_path / "voice.sqlite3")
    monkeypatch.setattr(adaptive_attention, "DB_PATH", tmp_path / "attention.sqlite3")
    monkeypatch.setattr(capability_center, "DB_PATH", tmp_path / "capability.sqlite3")
    monkeypatch.setattr(capability_center, "REPORT_DIR", tmp_path / "reports")
    monkeypatch.setattr(app_integrations, "DB_PATH", tmp_path / "integrations.sqlite3")
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")


def test_notification_vault_and_voice_repair(monkeypatch, tmp_path):
    _isolate_common(monkeypatch, tmp_path)

    notice = notification_center.add(source="test", category="unit", severity=4, title="Check this", message="Needs attention")
    vault = personal_knowledge_vault.remember("weekly_priority", "Ship Friday", "Finish Guardian OS")
    repair = voice_command_repair.record_repair("Friday reduce volume to 40", "Freddie reduce volume")

    assert notice["status"] == "unread"
    assert notification_center.mark_all_read()["updated"] >= 1
    assert vault["kind"] == "weekly_priority"
    assert "Ship Friday" in personal_knowledge_vault.what_matters_this_week()["summary"]
    assert repair["ok"] is True
    assert voice_command_repair.repair_text("Freddie reduce volume")["text"] == "Friday reduce volume to 40"


def test_proactive_guardian_scan_creates_important_notifications(monkeypatch, tmp_path):
    _isolate_common(monkeypatch, tmp_path)
    monkeypatch.setattr(
        proactive_guardian.capability_center,
        "maintenance_report",
        lambda light=True: {"health": {"battery": {"percent": 9, "plugged": False}}, "disk": [{"path": "C:", "free_percent": 7}]},
    )
    monkeypatch.setattr(
        proactive_guardian.capability_center,
        "security_overview",
        lambda light=True: {"suspicious_processes": [{"name": "strange.exe"}], "open_ports": {"open_ports": [{"port": 4444}]}},
    )
    monkeypatch.setattr(proactive_guardian.background_agents, "worker_status", lambda: {"running": False})
    monkeypatch.setattr(proactive_guardian.phone_bridge, "status", lambda: {"battery": {"available": True, "level": 8}})
    monkeypatch.setattr(proactive_guardian.voice_reliability, "summary", lambda: {"backends": {"groq": {"samples": 4, "mistakes": 3}}, "learned_aliases": ["friady"]})
    monkeypatch.setattr(proactive_guardian.evaluation_lab, "summary", lambda: {"counts": {"slow_response": 3}})
    monkeypatch.setattr(proactive_guardian.task_queue, "counts", lambda: {"active": 0})
    monkeypatch.setattr(proactive_guardian.task_queue, "list_tasks", lambda status="", limit=10: [])
    monkeypatch.setattr(proactive_guardian.app_integrations, "list_reminders", lambda include_done=False, limit=100: [])
    monkeypatch.setattr(proactive_guardian, "DB_PATH", tmp_path / "guardian.sqlite3")

    result = proactive_guardian.run_scan(light=True, notify=True)

    assert result["alerts"]
    assert notification_center.summary()["unread_count"] >= 1
    assert proactive_guardian.latest_run()["alert_count"] == len(result["alerts"])


def test_project_autopilot_pc_timeline_goal_file_study_and_automation(monkeypatch, tmp_path):
    _isolate_common(monkeypatch, tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("# TODO tighten auth\nprint('hello')\n", encoding="utf-8")
    monkeypatch.setattr(project_autopilot, "DB_PATH", tmp_path / "autopilot.sqlite3")
    monkeypatch.setattr(project_autopilot.capability_center, "workspace_dependency_health", lambda root: {"audits": []})
    monkeypatch.setattr(workspace_brain.app_integrations, "DB_PATH", tmp_path / "workspace_index.sqlite3")

    report = project_autopilot.inspect_project(project, notify=True)

    assert report["issues"]
    assert project_autopilot.recent_reports(limit=1)[0]["id"] == report["id"]

    monkeypatch.setattr(pc_timeline, "DB_PATH", tmp_path / "pc_timeline.sqlite3")
    monkeypatch.setattr(pc_timeline.pc_awareness, "refresh", lambda: {"active_window": "VS Code", "running_apps": [{"name": "Code"}], "summary": "VS Code active"})
    timeline = pc_timeline.capture_snapshot()
    assert timeline["snapshot_event"]["event_type"] == "pc_snapshot"

    monkeypatch.setattr(goal_regulation, "DB_PATH", tmp_path / "goals.sqlite3")
    monkeypatch.setattr(goal_manager.personal_life_os, "DB_PATH", tmp_path / "life.sqlite3")
    plan = goal_manager.create_goal_plan("Finish project", "Build and test it")
    assert len(plan["steps"]) >= 4
    assert goal_manager.progress_summary()["active"]

    monkeypatch.setattr(local_file_intelligence, "DB_PATH", tmp_path / "files.sqlite3")
    indexed = local_file_intelligence.index_locations([str(project)], max_files=20)
    answer = local_file_intelligence.answer("tighten auth")
    assert indexed["indexed"] == 1
    assert "main.py" in answer["answer"]

    monkeypatch.setattr(meeting_study_companion, "DB_PATH", tmp_path / "study.sqlite3")
    session = meeting_study_companion.create_session("Class", transcript="Photosynthesis is how plants make food. Need to review chlorophyll.")
    assert session["flashcards"]
    assert session["action_items"]

    recipe = automation_builder.create_from_text("When I open VS Code notify my phone")
    monkeypatch.setattr(automation_builder.pc_awareness, "snapshot", lambda: {"active_window": "Visual Studio Code"})
    matched = automation_builder.evaluate_triggers(run=False)
    assert recipe["ok"] is True
    assert matched["matched"]

import sys

from core import (
    agent_scheduler,
    backup_recovery,
    deployment_brain,
    evaluation_lab,
    goal_manager,
    model_benchmark_lab,
    operating_rhythm,
    os_autopilot,
    pc_timeline,
    personal_safety_guardian,
    reliability_score,
    task_queue,
    test_build_monitor,
    trust_proof,
    version_guardian,
    voice_reliability,
)


def _patch_dbs(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(agent_scheduler, "DB_PATH", tmp_path / "agent_scheduler.sqlite3")
    monkeypatch.setattr(test_build_monitor, "DB_PATH", tmp_path / "test_build_monitor.sqlite3")
    monkeypatch.setattr(reliability_score, "DB_PATH", tmp_path / "reliability_score.sqlite3")
    monkeypatch.setattr(model_benchmark_lab, "DB_PATH", tmp_path / "model_benchmark_lab.sqlite3")
    monkeypatch.setattr(deployment_brain, "DB_PATH", tmp_path / "deployment_brain.sqlite3")
    monkeypatch.setattr(os_autopilot, "DB_PATH", tmp_path / "os_autopilot.sqlite3")
    monkeypatch.setattr(version_guardian, "DB_PATH", tmp_path / "version_guardian.sqlite3")
    monkeypatch.setattr(evaluation_lab, "DB_PATH", tmp_path / "evaluation_lab.sqlite3")
    monkeypatch.setattr(voice_reliability, "DB_PATH", tmp_path / "voice_reliability.sqlite3")
    monkeypatch.setattr(trust_proof, "DB_PATH", tmp_path / "trust_proof.sqlite3")
    monkeypatch.setattr(backup_recovery, "DB_PATH", tmp_path / "backup_recovery.sqlite3")
    monkeypatch.setattr(backup_recovery, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(personal_safety_guardian, "DB_PATH", tmp_path / "personal_safety_guardian.sqlite3")
    monkeypatch.setattr(operating_rhythm, "DB_PATH", tmp_path / "operating_rhythm.sqlite3")
    monkeypatch.setattr(goal_manager, "DB_PATH", tmp_path / "goal_manager.sqlite3", raising=False)
    monkeypatch.setattr(pc_timeline, "DB_PATH", tmp_path / "pc_timeline.sqlite3")


def test_agent_scheduler_plans_and_retries_failed_tasks(monkeypatch, tmp_path):
    _patch_dbs(monkeypatch, tmp_path)
    task_id = task_queue.create_task("Retry me", agent_id="research_analyst")
    task_queue.fail_task(task_id, "temporary failure")

    plan = agent_scheduler.plan("voice", voice_active=True)
    retry = agent_scheduler.retry_failed_tasks(limit=2)

    assert plan["desired_workers"] == 0
    assert retry["retried"][0]["id"] == task_id
    assert task_queue.get_task(task_id)["status"] == "pending"


def test_test_build_monitor_runs_command_and_creates_report(monkeypatch, tmp_path):
    _patch_dbs(monkeypatch, tmp_path)

    report = test_build_monitor.run_check(tmp_path, f'"{sys.executable}" -c "print(4)"', create_proof=False)

    assert report["status"] == "passed"
    assert "passed" in report["summary"].lower()


def test_reliability_model_deployment_os_and_version_modules(monkeypatch, tmp_path):
    _patch_dbs(monkeypatch, tmp_path)
    sample = tmp_path / "notes.txt"
    sample.write_text("safe note", encoding="utf-8")

    reliability = reliability_score.snapshot()
    benchmark = model_benchmark_lab.run_benchmark(["coding", "math"])
    deployment = deployment_brain.inspect(root=tmp_path, create_proof=False)
    operating = os_autopilot.recommendation()
    preflight = version_guardian.preflight("update a config", [str(sample)])

    assert 0 <= reliability["overall"] <= 100
    assert benchmark["results"]
    assert deployment["status"] in {"ok", "attention", "skipped"}
    assert operating["recommendation"]
    assert "summary" in preflight

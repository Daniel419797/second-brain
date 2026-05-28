from pathlib import Path

from core import app_operators, backup_recovery, home_assistant, personal_life_os, skill_library, workspace_brain
from tools import power_center


def test_builtin_skill_install_enable_disable(monkeypatch, tmp_path):
    monkeypatch.setattr(skill_library, "SKILLS_PATH", tmp_path / "skills.json")
    monkeypatch.setattr(skill_library, "EXAMPLES_PATH", tmp_path / "examples.json")

    installed = skill_library.install_builtin("figma_operator")
    disabled = skill_library.disable_skill(installed[0]["id"])
    results = skill_library.search("figma frame design", agent_id="ui_ux_designer")
    enabled = skill_library.enable_skill(installed[0]["id"], True)

    assert installed[0]["name"] == "Figma operator"
    assert disabled["enabled"] is False
    assert results == []
    assert enabled["enabled"] is True


def test_workspace_brain_maps_and_answers(monkeypatch, tmp_path):
    monkeypatch.setattr(workspace_brain, "ROOT_DIR", tmp_path)
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "auth.py").write_text("# TODO tighten auth\nclass Login: pass\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_auth.py").write_text("def test_login(): pass\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    monkeypatch.setattr(workspace_brain.app_integrations, "DB_PATH", tmp_path / "workspace.sqlite3")
    monkeypatch.setattr(workspace_brain.capability_center, "DB_PATH", tmp_path / "capability.sqlite3")
    monkeypatch.setattr(workspace_brain.capability_center, "REPORT_DIR", tmp_path / "reports")

    analysis = workspace_brain.analyze_project(tmp_path)
    answer = workspace_brain.answer_workspace_question("where is auth logic", tmp_path)
    docs = workspace_brain.generate_docs(tmp_path)

    assert "TODO" in analysis["todos"][0]["kind"]
    assert answer["results"]
    assert Path(docs["path"]).exists()


def test_app_operator_registry_and_session(monkeypatch, tmp_path):
    monkeypatch.setattr(app_operators.desktop_tasks, "DB_PATH", tmp_path / "desktop.sqlite3")
    monkeypatch.setattr(app_operators.pc_awareness, "snapshot", lambda: {"running_apps": [{"name": "Code.exe"}]})

    context = app_operators.operator_context("vscode")
    result = app_operators.operate("vscode", "inspect failing tests", max_steps=2)

    assert context["available"] is True
    assert result["ok"] is True
    assert result["task"]["max_steps"] == 2


def test_personal_life_os_plan_and_mood(monkeypatch, tmp_path):
    monkeypatch.setattr(personal_life_os, "DB_PATH", tmp_path / "life.sqlite3")
    monkeypatch.setattr(personal_life_os.app_integrations, "DB_PATH", tmp_path / "integrations.sqlite3")
    monkeypatch.setattr(personal_life_os.capability_center, "DB_PATH", tmp_path / "capability.sqlite3")
    monkeypatch.setattr(personal_life_os.capability_center, "REPORT_DIR", tmp_path / "reports")

    mood = personal_life_os.set_mood("focused", energy=8)
    routine = personal_life_os.create_routine("Review priorities", next_due_at="2000-01-01T09:00:00")
    plan = personal_life_os.daily_plan()

    assert mood["energy"] == 8
    assert routine["title"] == "Review priorities"
    assert plan["routines_due"]


def test_home_assistant_unconfigured(monkeypatch):
    monkeypatch.delenv("HOME_ASSISTANT_URL", raising=False)
    monkeypatch.delenv("HOME_ASSISTANT_TOKEN", raising=False)
    monkeypatch.setattr(home_assistant, "config_value", lambda key, default=None: "")

    assert home_assistant.status()["configured"] is False


def test_backup_recovery_snapshot_and_guard(monkeypatch, tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "config.json").write_text("{}", encoding="utf-8")
    (root / ".env").write_text("SECRET=x", encoding="utf-8")
    monkeypatch.setattr(backup_recovery, "ROOT_DIR", root)
    monkeypatch.setattr(backup_recovery, "DB_PATH", tmp_path / "backup.sqlite3")
    monkeypatch.setattr(backup_recovery, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(backup_recovery, "config_value", lambda key, default=None: False if key == "backup_allow_env_snapshot" else default)

    snapshot = backup_recovery.snapshot_config()
    guard = backup_recovery.risky_delete_guard(root / ".env")

    assert snapshot["items"]
    assert guard["protected"] is True


def test_power_center_tool_installs_skills(monkeypatch, tmp_path):
    monkeypatch.setattr(skill_library, "SKILLS_PATH", tmp_path / "skills.json")
    monkeypatch.setattr(skill_library, "EXAMPLES_PATH", tmp_path / "examples.json")

    reply = power_center.execute({"action": "install_builtin_skills", "key": "react_app_builder"})

    assert "Installed 1" in reply

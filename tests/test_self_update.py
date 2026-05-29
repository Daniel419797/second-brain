from pathlib import Path

import pytest

from core import self_update, task_queue


def _isolated(monkeypatch, tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(self_update, "ROOT_DIR", root)
    monkeypatch.setattr(self_update, "DB_PATH", tmp_path / "self_updates.sqlite3")
    monkeypatch.setattr(self_update, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")

    def fake_config(key, default=None):
        values = {
            "self_update_task_priority": 2,
            "self_update_run_tests": False,
            "self_update_max_file_bytes": 240000,
            "self_update_max_change_bytes": 120000,
            "self_update_max_repo_summary_files": 100,
            "self_update_max_file_candidates": 100,
        }
        return values.get(key, default)

    monkeypatch.setattr(self_update, "config_value", fake_config)
    return root


def test_self_update_proposal_and_approval_queue_task(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)

    proposal = self_update.create_proposal("add a safer code self-update workflow")
    assert proposal["status"] == "proposed"
    assert proposal["approval_phrase"] == f"I authorize self update {proposal['id']}"

    with pytest.raises(PermissionError):
        self_update.approve_update(proposal["id"], "yes do it")

    approved = self_update.approve_update(proposal["id"], proposal["approval_phrase"])

    assert approved["status"] == "approved"
    assert approved["task_id"]
    task = task_queue.get_task(int(approved["task_id"]))
    assert task is not None
    assert task["agent_id"] == "senior_developer"
    assert task["input"]["source"] == "self_update"


def test_self_update_stages_and_applies_exact_change(monkeypatch, tmp_path):
    root = _isolated(monkeypatch, tmp_path)
    target = root / "core" / "sample.py"
    target.parent.mkdir()
    target.write_text("VALUE = 'old'\n", encoding="utf-8")

    proposal = self_update.create_proposal("change sample value")
    approved = self_update.approve_update(proposal["id"], proposal["approval_phrase"])
    change = self_update.stage_change(
        approved["id"],
        "core/sample.py",
        "VALUE = 'old'\n",
        "VALUE = 'new'\n",
        "Update sample value.",
    )

    assert change["status"] == "staged"

    applied = self_update.apply_update(
        approved["id"],
        f"I authorize applying self update {approved['id']}",
        run_tests=False,
    )

    assert applied["status"] == "applied"
    assert target.read_text(encoding="utf-8") == "VALUE = 'new'\n"


def test_self_update_blocks_secret_and_outside_paths(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    proposal = self_update.create_proposal("try a blocked update")

    with pytest.raises(PermissionError):
        self_update.stage_change(proposal["id"], ".env", "", "SECRET=bad\n")

    with pytest.raises(PermissionError):
        self_update.stage_change(proposal["id"], str(tmp_path.parent / "outside.py"), "", "print('bad')\n")


def test_self_update_allows_non_python_source_files(monkeypatch, tmp_path):
    root = _isolated(monkeypatch, tmp_path)
    target = root / "lib" / "main.dart"
    target.parent.mkdir()
    target.write_text("const value = 'old';\n", encoding="utf-8")
    proposal = self_update.create_proposal("update flutter source")

    change = self_update.stage_change(
        proposal["id"],
        "lib/main.dart",
        "const value = 'old';\n",
        "const value = 'new';\n",
        "Update Dart source.",
    )

    assert change["status"] == "staged"

import json
from pathlib import Path

from core import audit_log, autonomous_coding, codebase_standards, project_memory, self_update, task_contracts, task_queue, trust_proof


def _isolate_common(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(task_contracts, "DB_PATH", tmp_path / "contracts.sqlite3")
    monkeypatch.setattr(project_memory, "DB_PATH", tmp_path / "project_memory.sqlite3")
    monkeypatch.setattr(codebase_standards, "DB_PATH", tmp_path / "standards.sqlite3")
    monkeypatch.setattr(trust_proof, "DB_PATH", tmp_path / "proof.sqlite3")
    monkeypatch.setattr(audit_log, "DB_PATH", tmp_path / "audit.sqlite3")


def test_autonomous_coding_scaffolds_new_app(monkeypatch, tmp_path):
    _isolate_common(monkeypatch, tmp_path)

    result = autonomous_coding.start("Build a web-app HackOnVibe AI-assisted everyday tool", root=str(tmp_path))

    project_root = Path(result["execution"]["metadata"]["project_root"])
    assert result["task"]["status"] == "done"
    assert (project_root / "package.json").exists()
    assert (project_root / "src" / "app" / "page.tsx").exists()
    assert (project_root / ".friday" / "ci-plan.yml").exists()
    assert result["execution"]["metadata"]["stack"]["stack"] == "nextjs"
    assert "Created a runnable Next.js web app" in result["summary"]


def test_autonomous_coding_scaffolds_flutter_mobile_app(monkeypatch, tmp_path):
    _isolate_common(monkeypatch, tmp_path)

    result = autonomous_coding.start("Build a mobile app for shop invoices", root=str(tmp_path))

    project_root = Path(result["execution"]["metadata"]["project_root"])
    assert result["task"]["status"] == "done"
    assert (project_root / "pubspec.yaml").exists()
    assert (project_root / "lib" / "main.dart").exists()
    assert result["execution"]["metadata"]["stack"]["stack"] == "flutter"


def test_approved_self_update_task_stages_llm_change(monkeypatch, tmp_path):
    _isolate_common(monkeypatch, tmp_path)
    root = tmp_path / "repo"
    target = root / "core" / "sample.py"
    target.parent.mkdir(parents=True)
    target.write_text("VALUE = 'old'\n", encoding="utf-8")
    monkeypatch.setattr(self_update, "ROOT_DIR", root)
    monkeypatch.setattr(self_update, "DB_PATH", tmp_path / "self_updates.sqlite3")
    monkeypatch.setattr(self_update, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(
        self_update,
        "config_value",
        lambda key, default=None: {
            "self_update_task_priority": 2,
            "self_update_run_tests": False,
            "self_update_max_file_bytes": 240000,
            "self_update_max_change_bytes": 120000,
            "self_update_max_repo_summary_files": 100,
            "self_update_max_file_candidates": 100,
        }.get(key, default),
    )
    monkeypatch.setattr(
        autonomous_coding.llm,
        "ask_simple_with_provider_chain",
        lambda prompt, providers, retries=1: json.dumps(
            {
                "changes": [
                    {
                        "path": "core/sample.py",
                        "find_text": "VALUE = 'old'\n",
                        "replace_text": "VALUE = 'new'\n",
                        "summary": "Update sample value.",
                    }
                ]
            }
        ),
    )

    proposal = self_update.create_proposal("change sample value")
    approved = self_update.approve_update(proposal["id"], proposal["approval_phrase"])
    task = task_queue.get_task(int(approved["task_id"]))

    result = autonomous_coding.run_task(task)

    update = self_update.get_update(proposal["id"])
    assert "Prepared 1 staged change" in result["summary"]
    assert update["changes"][0]["path"].replace("\\", "/") == "core/sample.py"
    assert target.read_text(encoding="utf-8") == "VALUE = 'old'\n"

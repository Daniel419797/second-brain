import json
from pathlib import Path

from core import app_state_memory, autonomous_qa_lab, autonomy_control, backup_recovery, browser_extension_bridge, error_radar, mission_control, operating_rhythm, release_manager, semantic_search, task_contracts, task_queue


def _patch_common(monkeypatch, tmp_path):
    monkeypatch.setattr(task_queue, "DB_PATH", tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(task_contracts, "DB_PATH", tmp_path / "contracts.sqlite3")
    monkeypatch.setattr(backup_recovery, "DB_PATH", tmp_path / "backup.sqlite3")
    monkeypatch.setattr(backup_recovery, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(mission_control, "DB_PATH", tmp_path / "missions.sqlite3")
    monkeypatch.setattr(autonomous_qa_lab, "DB_PATH", tmp_path / "qa.sqlite3")
    monkeypatch.setattr(app_state_memory, "DB_PATH", tmp_path / "app_state.sqlite3")
    monkeypatch.setattr(browser_extension_bridge, "DB_PATH", tmp_path / "browser.sqlite3")
    monkeypatch.setattr(release_manager, "DB_PATH", tmp_path / "release.sqlite3")
    monkeypatch.setattr(error_radar, "DB_PATH", tmp_path / "radar.sqlite3")
    monkeypatch.setattr(semantic_search, "DB_PATH", tmp_path / "semantic.sqlite3")
    monkeypatch.setattr(operating_rhythm, "DB_PATH", tmp_path / "rhythm.sqlite3")


def test_mission_control_creates_fixed_phases_and_contracts(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    (root / "config.json").write_text("{}", encoding="utf-8")

    mission = mission_control.create_mission("Build a small dashboard MVP", root=root)

    assert mission["status"] == "running"
    assert mission["mission_type"] == "project_builder"
    assert [phase["name"] for phase in mission["phases"]] == [phase["name"] for phase in mission_control.PHASES]
    assert mission["approvals"][0]["kind"] == "deploy"
    assert task_contracts.get_contract(mission["phases"][0]["task_id"])
    assert task_queue.get_task(mission["task_ids"]["implementation"])["scheduled_at"]


def test_mission_design_preview_gate_holds_implementation_until_approval(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    mission = mission_control.create_mission("Build a polished dashboard UI", root=root)

    for name in ("intake", "research", "architecture", "design"):
        task_queue.complete_task(mission["task_ids"][name], {"summary": f"Summary: {name}. Next step: continue. Risks: none."})

    refreshed = mission_control.refresh_mission(mission["id"])["missions"][0]
    implementation = task_queue.get_task(mission["task_ids"]["implementation"])

    assert refreshed["current_phase"] == "design_preview_approval"
    assert refreshed["design_preview"]["pending"] is True
    assert implementation["scheduled_at"]

    approved = mission_control.approve_mission(mission["id"], kind="design_preview", note="Looks good")
    implementation = task_queue.get_task(mission["task_ids"]["implementation"])

    assert approved["design_preview"]["approved"] is True
    assert implementation["scheduled_at"] == ""


def test_full_autonomy_mission_skips_design_and_deploy_approvals(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    root = tmp_path / "repo"
    root.mkdir()

    def fake_config(key, default=None):
        values = {
            "autonomy_control_enabled": True,
            "autonomy_mode": "full",
            "autonomy_trusted_roots": str(tmp_path),
            "autonomy_preapprove_deployments": True,
            "autonomy_preapprove_design_preview": True,
            "mission_default_authority_mode": "approval_gated",
            "mission_default_deploy_policy": "approve_step",
        }
        return values.get(key, default)

    monkeypatch.setattr(autonomy_control, "config_value", fake_config)

    mission = mission_control.create_mission("Build a polished dashboard UI", root=root)

    assert mission["authority_mode"] == "autonomous"
    assert mission["deploy_policy"] == "autonomous"
    assert mission["approvals"] == []
    assert mission["metadata"]["design_preview_gate"] is False


def test_full_autonomy_release_manager_marks_trusted_deploy_preapproved(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    root = tmp_path / "repo"
    root.mkdir()

    def fake_config(key, default=None):
        values = {
            "autonomy_control_enabled": True,
            "autonomy_mode": "full",
            "autonomy_trusted_roots": str(tmp_path),
            "autonomy_preapprove_deployments": True,
        }
        return values.get(key, default)

    monkeypatch.setattr(autonomy_control, "config_value", fake_config)

    release = release_manager.prepare_release(root)

    assert release["status"] == "deploy_approved"
    assert any(item["status"] == "preapproved" for item in release["checklist"])


def test_mission_final_proof_requires_qa_evidence(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    mission = mission_control.create_mission("Build app", root=root)
    task_queue.complete_task(mission["task_ids"]["design"], {"summary": "Summary: UI preview ready. Next step: approve. Risks: none."})
    mission_control.refresh_mission(mission["id"])
    mission_control.approve_mission(mission["id"], kind="design_preview", note="Approved for test")
    for task_id in mission["task_ids"].values():
        task_queue.complete_task(task_id, {"summary": "Summary: done. Next step: complete. Risks: none."})

    refreshed = mission_control.refresh_mission(mission["id"])["missions"][0]
    assert refreshed["status"] == "blocked"
    assert any(blocker["title"] == "QA evidence missing" for blocker in refreshed["blockers"])

    autonomous_qa_lab.run_qa(root, mission_id=mission["id"], run_tests=False)
    refreshed = mission_control.refresh_mission(mission["id"])["missions"][0]
    assert refreshed["status"] in {"completed", "blocked"}
    assert any(item["source"] == "qa_lab" for item in refreshed["evidence"])


def test_qa_lab_release_and_error_radar(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    (root / "package.json").write_text(json.dumps({"version": "1.2.3", "scripts": {"build": "next build"}}), encoding="utf-8")
    (root / "README.md").write_text("# App", encoding="utf-8")
    (root / "src.test.js").write_text("test('x', () => {})", encoding="utf-8")

    qa = autonomous_qa_lab.run_qa(root, run_tests=False)
    release = release_manager.prepare_release(root, version="")
    console = browser_extension_bridge.ingest_console({"level": "error", "message": "Unhandled error in app", "url": "https://example.com?token=secret"})
    radar = error_radar.watch(root, sources=["browser"])

    assert qa["checks"]
    assert qa["status"] in {"passed", "needs_review", "failed"}
    assert release["version"] == "1.2.3"
    assert release["status"] == "pending_approval"
    assert "?[redacted-query]" in console["url"]
    assert radar["created"] >= 1


def test_browser_extension_context_redacts_and_records_app_memory(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)

    item = browser_extension_bridge.ingest_context(
        {
            "browser": "chrome",
            "url": "https://example.com/login?token=abc",
            "title": "Password token page",
            "selected_text": "api_key=sk-secretsecretsecretsecret",
            "buttons": [{"text": "Submit", "selector": "#submit"}],
            "forms": [{"name": "login", "fields": [{"name": "password", "type": "password"}, {"name": "email", "type": "email"}]}],
        }
    )
    patterns = app_state_memory.search_patterns(app="browser")

    assert item["redactions"] >= 1
    assert item["forms"][0]["fields"][0]["sensitive"] is True
    assert patterns


def test_semantic_search_indexes_safe_files_and_hides_private_chunks(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    (root / "auth.py").write_text("def login(): return 'ok'\n", encoding="utf-8")
    (root / ".env").write_text("API_KEY=super-secret\n", encoding="utf-8")

    report = semantic_search.index_path(root)
    normal_results = semantic_search.search("login")
    private_results = semantic_search.search("API_KEY", include_sensitive=True)
    hidden_results = semantic_search.search("super-secret", include_sensitive=False)

    assert report["indexed"] == 1
    assert normal_results and normal_results[0]["title"] == "auth.py"
    assert private_results
    assert hidden_results == []


def test_operating_rhythm_records_energy(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)

    note = operating_rhythm.record_energy("focused", energy=8, focus=7)
    summary = operating_rhythm.summary()

    assert note["energy"] == 8
    assert "coding" in summary["summary"].lower()


def test_browser_extension_static_manifest_and_redaction_script():
    root = Path(__file__).resolve().parent.parent / "apps" / "browser-extension"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    content = (root / "content.js").read_text(encoding="utf-8")

    assert manifest["manifest_version"] == 3
    assert "http://127.0.0.1:8000/*" in manifest["host_permissions"]
    assert "password" in content.lower()
    assert "[redacted-token]" in content

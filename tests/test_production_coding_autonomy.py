import json

from core import audit_log, codebase_standards, production_coding_autonomy, project_memory, trust_proof


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(project_memory, "DB_PATH", tmp_path / "project_memory.sqlite3")
    monkeypatch.setattr(codebase_standards, "DB_PATH", tmp_path / "standards.sqlite3")
    monkeypatch.setattr(trust_proof, "DB_PATH", tmp_path / "proof.sqlite3")
    monkeypatch.setattr(audit_log, "DB_PATH", tmp_path / "audit.sqlite3")


def test_prepare_project_creates_ci_rollback_security_and_budget(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    root = tmp_path / "client-app"
    root.mkdir()
    (root / "package.json").write_text(json.dumps({"scripts": {"lint": "eslint .", "test": "vitest", "build": "vite build"}}), encoding="utf-8")
    (root / "tests").mkdir()

    result = production_coding_autonomy.prepare_project(root, request="Build client portal", run_scans=True)

    assert result["ok"] is True
    assert "npm run test" in result["test_commands"]
    assert (root / ".friday" / "ci-plan.yml").exists()
    assert (root / ".friday" / "rollback-plan.md").exists()
    assert (root / ".friday" / "security-preflight.json").exists()
    assert result["proof"]["id"] > 0


def test_discover_tests_handles_python_projects(tmp_path):
    root = tmp_path / "py-app"
    root.mkdir()
    (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\naddopts='-q'\n[tool.ruff]\n", encoding="utf-8")

    commands = production_coding_autonomy.discover_tests(root)

    assert "python -m pytest" in commands
    assert "python -m ruff check ." in commands


def test_discover_tests_handles_flutter_projects(tmp_path):
    root = tmp_path / "mobile-app"
    root.mkdir()
    (root / "pubspec.yaml").write_text("name: mobile_app\n", encoding="utf-8")

    commands = production_coding_autonomy.discover_tests(root)

    assert "flutter test" in commands
    assert "flutter analyze" in commands

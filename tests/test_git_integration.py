from types import SimpleNamespace

from core import git_integration
from tools import power_center


def _fake_run(calls, stdout="ok"):
    def run(command, cwd=None, text=True, capture_output=True, timeout=60, shell=False):
        calls.append({"command": command, "cwd": cwd, "timeout": timeout, "shell": shell})
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    return run


def test_git_status_runs_short_branch(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(git_integration.subprocess, "run", _fake_run(calls, stdout="## main\n M app.py\n"))

    result = git_integration.status(tmp_path)

    assert result["ok"] is True
    assert result["summary"].startswith("Git status ready.")
    assert calls[0]["command"] == ["git", "status", "--short", "--branch"]
    assert calls[0]["cwd"] == str(tmp_path.resolve())
    assert calls[0]["shell"] is False


def test_git_clone_expands_github_shorthand_under_coding_root(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(git_integration.subprocess, "run", _fake_run(calls, stdout="cloned"))
    monkeypatch.setattr(git_integration, "resolve_coding_root", lambda root="": (tmp_path / str(root)).resolve() if root else tmp_path.resolve())

    result = git_integration.clone("octo/demo", "demo")

    assert result["ok"] is True
    assert calls[0]["command"] == ["git", "clone", "https://github.com/octo/demo.git", str((tmp_path / "demo").resolve())]
    assert calls[0]["cwd"] == str(tmp_path.resolve())


def test_git_push_respects_config_circuit_breaker(monkeypatch, tmp_path):
    monkeypatch.setattr(git_integration, "config_value", lambda key, default=None: False if key == "git_integration_allow_push" else default)

    result = git_integration.push(tmp_path)

    assert result["ok"] is False
    assert "disabled" in result["summary"]


def test_github_pr_create_uses_gh_cli(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(git_integration.subprocess, "run", _fake_run(calls, stdout="https://github.com/octo/demo/pull/1"))

    result = git_integration.create_pr(tmp_path, title="Add reports", body="Ready for review", base="main", head="feature/reports")

    assert result["ok"] is True
    assert calls[0]["command"] == [
        "gh",
        "pr",
        "create",
        "--title",
        "Add reports",
        "--body",
        "Ready for review",
        "--base",
        "main",
        "--head",
        "feature/reports",
    ]


def test_power_center_git_status_action(monkeypatch):
    monkeypatch.setattr(power_center, "_permission_reply", lambda inputs: "")
    monkeypatch.setattr(git_integration, "status", lambda root="": {"summary": "Git status ready.\n## main"})

    assert power_center.execute({"action": "git_status"}) == "Git status ready.\n## main"

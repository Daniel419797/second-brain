from __future__ import annotations

import subprocess
import sys

import pytest

from core import command_runner


def test_parse_command_allows_managed_python_command():
    args = command_runner.parse_command(f"{sys.executable} -m pytest -q", extra_allowed={sys.executable})

    assert args[0] == sys.executable
    assert args[1:] == ["-m", "pytest", "-q"]


def test_parse_command_rejects_shell_metacharacters():
    with pytest.raises(command_runner.CommandRejected):
        command_runner.parse_command("python -m pytest -q && echo bad")


def test_parse_command_rejects_unallowlisted_executable():
    with pytest.raises(command_runner.CommandRejected):
        command_runner.parse_command("unknown-tool --version")


def test_run_times_out_managed_command():
    command = f"{sys.executable} -m timeit -n 1 -r 1 \"import time\" \"time.sleep(5)\""

    with pytest.raises(subprocess.TimeoutExpired):
        command_runner.run(command, timeout=0.1, extra_allowed={sys.executable})


def test_run_timeout_terminates_process_tree(monkeypatch):
    command = f"{sys.executable} -m timeit -n 1 -r 1 \"import time\" \"time.sleep(5)\""
    killed = []

    monkeypatch.setattr(command_runner, "terminate_process_tree", lambda pid: killed.append(pid))

    with pytest.raises(subprocess.TimeoutExpired):
        command_runner.run(command, timeout=0.1, extra_allowed={sys.executable})

    assert killed


def test_safe_environment_scrubs_secret_keys(monkeypatch):
    monkeypatch.setenv("STITCH_API_KEY", "secret")
    monkeypatch.setenv("PATH", "bin")

    env = command_runner.safe_environment({"CUSTOM_TOKEN": "secret", "PORT": "3000"})

    assert "STITCH_API_KEY" not in env
    assert "CUSTOM_TOKEN" not in env
    assert env["PORT"] == "3000"
    assert env["FRIDAY_ENV_SCRUBBED"] == "1"

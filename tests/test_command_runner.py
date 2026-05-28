from __future__ import annotations

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

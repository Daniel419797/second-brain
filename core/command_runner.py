"""Safe command parsing and execution for Friday-managed checks."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from core.config import config_value


DEFAULT_ALLOWLIST = {
    "python",
    "python.exe",
    "py",
    "py.exe",
    "pytest",
    "pytest.exe",
    "npm",
    "npm.cmd",
    "npx",
    "npx.cmd",
    "node",
    "node.exe",
    "git",
    "git.exe",
    "gh",
    "gh.exe",
    ".\\.venv\\scripts\\python.exe",
    ".venv\\scripts\\python.exe",
}
SHELL_META = {"&", "|", ";", "<", ">", "`"}


class CommandRejected(ValueError):
    """Raised when a command is outside Friday's safe command policy."""


def parse_command(command: str, *, extra_allowed: set[str] | None = None) -> list[str]:
    text = str(command or "").strip()
    if not text:
        raise CommandRejected("No command provided.")
    if any(char in text for char in SHELL_META):
        raise CommandRejected("Shell metacharacters are not allowed in managed commands.")
    try:
        args = [part.strip("\"'") for part in shlex.split(text, posix=(os.name != "nt"))]
    except ValueError as exc:
        raise CommandRejected(f"Could not parse command: {exc}") from exc
    if not args:
        raise CommandRejected("No command provided.")
    allowed = _allowed(extra_allowed)
    executable = args[0].replace("/", "\\").lower()
    basename = Path(executable).name.lower()
    if executable not in allowed and basename not in allowed:
        raise CommandRejected(f"Command executable is not allowlisted: {args[0]}")
    return args


def run(
    command: str,
    *,
    cwd: str | Path | None = None,
    timeout: int | float = 60,
    extra_allowed: set[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    args = parse_command(command, extra_allowed=extra_allowed)
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
        check=False,
    )


def _allowed(extra_allowed: set[str] | None = None) -> set[str]:
    raw = str(config_value("safe_command_allowlist", "") or "")
    configured = {item.strip().replace("/", "\\").lower() for item in raw.split(",") if item.strip()}
    extras = {item.strip().replace("/", "\\").lower() for item in (extra_allowed or set()) if item.strip()}
    return DEFAULT_ALLOWLIST | configured | extras

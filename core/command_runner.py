"""Safe command parsing and execution for Friday-managed checks."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
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
SAFE_ENV_KEYS = {
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "TMPDIR",
    "HOME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "ALLUSERSPROFILE",
    "LANG",
    "LC_ALL",
    "CI",
    "NODE_ENV",
    "PYTHONPATH",
}
SECRET_ENV_RE = re.compile(r"(secret|token|password|private|credential|api[_-]?key|access[_-]?key)", re.IGNORECASE)


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
    resolved = shutil.which(args[0])
    if resolved:
        args[0] = resolved
    return args


def run(
    command: str,
    *,
    cwd: str | Path | None = None,
    timeout: int | float = 60,
    extra_allowed: set[str] | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    args = parse_command(command, extra_allowed=extra_allowed)
    process = subprocess.Popen(
        args,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        start_new_session=not sys.platform.startswith("win"),
        env=safe_environment(env),
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        terminate_process_tree(process.pid)
        stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(args, timeout, output=stdout, stderr=stderr) from exc
    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)


def _allowed(extra_allowed: set[str] | None = None) -> set[str]:
    raw = str(config_value("safe_command_allowlist", "") or "")
    configured = {item.strip().replace("/", "\\").lower() for item in raw.split(",") if item.strip()}
    extras = {item.strip().replace("/", "\\").lower() for item in (extra_allowed or set()) if item.strip()}
    return DEFAULT_ALLOWLIST | configured | extras


def safe_environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return a scrubbed env for generated-project command execution."""

    if bool(config_value("managed_command_preserve_full_env", False)):
        base = {key: value for key, value in os.environ.items() if not SECRET_ENV_RE.search(key)}
    else:
        base = {key: os.environ[key] for key in SAFE_ENV_KEYS if key in os.environ and not SECRET_ENV_RE.search(key)}
    for key, value in (extra or {}).items():
        if SECRET_ENV_RE.search(str(key)):
            continue
        base[str(key)] = str(value)
    base["FRIDAY_MANAGED_COMMAND"] = "1"
    base["FRIDAY_ENV_SCRUBBED"] = "1"
    return base


def terminate_process_tree(pid: int) -> None:
    """Terminate a Friday-managed process and any children it spawned."""

    if sys.platform.startswith("win"):
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, check=False)
        return
    try:
        import os
        import signal

        os.killpg(pid, signal.SIGKILL)
    except Exception:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            return

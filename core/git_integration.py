"""Guarded Git and GitHub CLI integration for Friday projects."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from core.config import config_value, default_coding_root, resolve_coding_root

_REF_RE = re.compile(r"^[A-Za-z0-9._/\-]+$")


def status(root: str | Path = "") -> dict[str, Any]:
    return _run(["git", "status", "--short", "--branch"], cwd=_repo_root(root), success="Git status ready.")


def branches(root: str | Path = "") -> dict[str, Any]:
    return _run(["git", "branch", "--all", "--no-color"], cwd=_repo_root(root), success="Git branches ready.")


def log(root: str | Path = "", *, limit: int = 5) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 5), 50))
    return _run(["git", "log", "--oneline", "-n", str(safe_limit)], cwd=_repo_root(root), success="Git log ready.")


def diff(root: str | Path = "", *, staged: bool = False, path: str | Path = "") -> dict[str, Any]:
    command = ["git", "diff"]
    if staged:
        command.append("--staged")
    paths = _paths(path)
    if paths:
        command.extend(["--", *paths])
    return _run(command, cwd=_repo_root(root), success="Git diff ready.")


def clone(repo: str, destination: str | Path = "") -> dict[str, Any]:
    url = _repo_url(repo)
    if not url:
        return _error("Repository URL or owner/repo is required.")
    dest = _clone_destination(destination, url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    return _run(["git", "clone", url, str(dest)], cwd=dest.parent, success=f"Cloned repository to {dest}.")


def checkout(root: str | Path = "", *, branch: str, create: bool = False) -> dict[str, Any]:
    ref = _safe_ref(branch, "branch")
    if not ref:
        return _error("A valid branch name is required.")
    command = ["git", "checkout"]
    if create:
        command.append("-b")
    command.append(ref)
    return _run(command, cwd=_repo_root(root), success=f"Checked out {ref}.")


def pull(root: str | Path = "", *, remote: str = "", branch: str = "") -> dict[str, Any]:
    safe_remote = _safe_ref(remote or str(config_value("git_integration_default_remote", "origin")), "remote")
    if not safe_remote:
        return _error("A valid remote name is required.")
    command = ["git", "pull", safe_remote]
    safe_branch = _safe_ref(branch, "branch") if branch else ""
    if branch and not safe_branch:
        return _error("A valid branch name is required.")
    if safe_branch:
        command.append(safe_branch)
    return _run(command, cwd=_repo_root(root), success="Git pull completed.")


def add(root: str | Path = "", *, paths: str | Path | list[str] | tuple[str, ...] = ".") -> dict[str, Any]:
    items = _paths(paths) or ["."]
    return _run(["git", "add", "--", *items], cwd=_repo_root(root), success=f"Staged {len(items)} path(s).")


def commit(root: str | Path = "", *, message: str) -> dict[str, Any]:
    clean_message = str(message or "").strip()
    if not clean_message:
        return _error("A commit message is required.")
    if not bool(config_value("git_integration_allow_commit", True)):
        return _error("Git commits are disabled by git_integration_allow_commit.")
    return _run(["git", "commit", "-m", clean_message], cwd=_repo_root(root), success="Git commit completed.")


def push(
    root: str | Path = "",
    *,
    remote: str = "",
    branch: str = "",
    set_upstream: bool = False,
) -> dict[str, Any]:
    if not bool(config_value("git_integration_allow_push", True)):
        return _error("Git push is disabled by git_integration_allow_push.")
    safe_remote = _safe_ref(remote or str(config_value("git_integration_default_remote", "origin")), "remote")
    if not safe_remote:
        return _error("A valid remote name is required.")
    command = ["git", "push"]
    if set_upstream:
        command.append("-u")
    command.append(safe_remote)
    safe_branch = _safe_ref(branch, "branch") if branch else ""
    if branch and not safe_branch:
        return _error("A valid branch name is required.")
    if safe_branch:
        command.append(safe_branch)
    return _run(command, cwd=_repo_root(root), success="Git push completed.")


def github_status(root: str | Path = "") -> dict[str, Any]:
    return _run(["gh", "auth", "status"], cwd=_repo_root(root), success="GitHub CLI status ready.")


def create_pr(root: str | Path = "", *, title: str, body: str = "", base: str = "", head: str = "") -> dict[str, Any]:
    clean_title = str(title or "").strip()
    if not clean_title:
        return _error("A pull request title is required.")
    command = ["gh", "pr", "create", "--title", clean_title, "--body", str(body or "")]
    safe_base = _safe_ref(base, "base") if base else ""
    safe_head = _safe_ref(head, "head") if head else ""
    if base and not safe_base:
        return _error("A valid base branch is required.")
    if head and not safe_head:
        return _error("A valid head branch is required.")
    if safe_base:
        command.extend(["--base", safe_base])
    if safe_head:
        command.extend(["--head", safe_head])
    return _run(command, cwd=_repo_root(root), success="GitHub pull request created.")


def list_prs(root: str | Path = "", *, state: str = "open", limit: int = 10) -> dict[str, Any]:
    clean_state = str(state or "open").strip().lower()
    if clean_state not in {"open", "closed", "merged", "all"}:
        clean_state = "open"
    safe_limit = max(1, min(int(limit or 10), 100))
    return _run(
        ["gh", "pr", "list", "--state", clean_state, "--limit", str(safe_limit)],
        cwd=_repo_root(root),
        success="GitHub pull requests ready.",
    )


def create_issue(root: str | Path = "", *, title: str, body: str = "") -> dict[str, Any]:
    clean_title = str(title or "").strip()
    if not clean_title:
        return _error("An issue title is required.")
    return _run(
        ["gh", "issue", "create", "--title", clean_title, "--body", str(body or "")],
        cwd=_repo_root(root),
        success="GitHub issue created.",
    )


def _run(command: list[str], *, cwd: Path, success: str) -> dict[str, Any]:
    timeout = max(5, int(config_value("git_integration_timeout_seconds", 60)))
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
            shell=False,
        )
    except FileNotFoundError:
        return _error(f"{command[0]} is not installed or is not on PATH.", command=command, cwd=cwd)
    except subprocess.TimeoutExpired as exc:
        return _error(f"Command timed out after {timeout} seconds.", command=command, cwd=cwd, stderr=str(exc))
    ok = result.returncode == 0
    stdout = _bounded_text(result.stdout)
    stderr = _bounded_text(result.stderr)
    return {
        "ok": ok,
        "command": command,
        "cwd": str(cwd),
        "stdout": stdout,
        "stderr": stderr,
        "returncode": result.returncode,
        "summary": _summary(ok, success, stdout, stderr),
    }


def _repo_root(root: str | Path = "") -> Path:
    raw = str(root or "").strip()
    if raw:
        return resolve_coding_root(raw)
    cwd = Path.cwd()
    try:
        if (cwd / ".git").exists():
            return cwd.resolve()
    except Exception:
        pass
    return default_coding_root()


def _clone_destination(destination: str | Path, repo_url: str) -> Path:
    raw = str(destination or "").strip()
    if raw:
        return resolve_coding_root(raw)
    name = _repo_name(repo_url)
    return resolve_coding_root(name)


def _repo_url(repo: str) -> str:
    raw = str(repo or "").strip()
    if not raw:
        return ""
    if re.match(r"^(?:https?://|git@)", raw, flags=re.IGNORECASE):
        return raw
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", raw):
        owner, name = raw.split("/", 1)
        return f"https://github.com/{owner}/{name.removesuffix('.git')}.git"
    return raw


def _repo_name(repo_url: str) -> str:
    name = repo_url.rstrip("/").split("/")[-1]
    name = name.removesuffix(".git")
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip(".-")
    return clean or "cloned-repo"


def _safe_ref(value: str, label: str) -> str:
    ref = str(value or "").strip()
    if not ref or ref.startswith("-") or not _REF_RE.fullmatch(ref):
        return ""
    if ".." in ref or ref.endswith(".lock") or "@{" in ref:
        return ""
    return ref


def _paths(value: Any) -> list[str]:
    if value is None:
        return []
    raw_items = value if isinstance(value, (list, tuple)) else [value]
    items: list[str] = []
    for item in raw_items:
        text = str(item or "").strip()
        if text:
            items.append(text)
    return items


def _bounded_text(value: str, limit: int = 6000) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n... truncated ..."


def _summary(ok: bool, success: str, stdout: str, stderr: str) -> str:
    detail = stdout or stderr
    if detail:
        return f"{success if ok else 'Git/GitHub command failed.'}\n{detail}"
    return success if ok else "Git/GitHub command failed with no output."


def _error(message: str, *, command: list[str] | None = None, cwd: Path | None = None, stderr: str = "") -> dict[str, Any]:
    return {
        "ok": False,
        "command": command or [],
        "cwd": str(cwd or ""),
        "stdout": "",
        "stderr": stderr,
        "returncode": 1,
        "summary": message,
    }

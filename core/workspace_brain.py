"""Deeper workspace intelligence for Friday.

This module stays local and heuristic by design: it maps repositories, assigns
file roles, tracks TODO/test/dependency signals, answers "where is X?" style
questions from indexed project text, and can write/update lightweight docs.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from core import app_integrations, capability_center
from core.config import DATA_DIR, ROOT_DIR, config_value, ensure_runtime_dirs, resolve_coding_root

DOCS_DIR = DATA_DIR / "workspace_brain"


def map_repos(root: str | Path = "") -> dict[str, Any]:
    base = _safe_root(root)
    repos = []
    for path in [base, *[item for item in base.rglob("*") if item.is_dir()]]:
        if _skip(path, base):
            continue
        markers = [name for name in [".git", "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod"] if (path / name).exists()]
        if markers:
            repos.append({"path": str(path), "name": path.name, "markers": markers, "kind": _repo_kind(path)})
        if len(repos) >= int(config_value("workspace_brain_max_repos", 80)):
            break
    return {"root": str(base), "repos": repos, "summary": f"Found {len(repos)} repo/project roots."}


def analyze_project(root: str | Path = "") -> dict[str, Any]:
    base = _safe_root(root)
    indexed = app_integrations.index_workspace(base, max_files=int(config_value("workspace_brain_max_files", 1500)))
    project_map = capability_center.workspace_project_map(base, max_files=int(config_value("workspace_brain_max_files", 1500)))
    deps = capability_center.workspace_dependency_health(base)
    files = _file_roles(base)
    todos = track_todos(base)
    tests = track_tests(base)
    architecture = _architecture(files, deps)
    return {
        "root": str(base),
        "indexed": indexed,
        "project_map": project_map,
        "dependencies": deps,
        "architecture": architecture,
        "files": files[: int(config_value("workspace_brain_file_role_limit", 200))],
        "todos": todos["items"][:50],
        "tests": tests,
        "summary": f"{architecture['summary']} {todos['summary']} {tests['summary']}",
    }


def file_map(root: str | Path = "") -> dict[str, Any]:
    base = _safe_root(root)
    roles = _file_roles(base)
    return {"root": str(base), "files": roles, "summary": f"Mapped roles for {len(roles)} files."}


def track_todos(root: str | Path = "") -> dict[str, Any]:
    base = _safe_root(root)
    items = []
    pattern = re.compile(r"\b(TODO|FIXME|BUG|HACK|XXX)\b[:\-\s]*(.*)", re.IGNORECASE)
    for path in _iter_files(base):
        try:
            for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
                match = pattern.search(line)
                if match:
                    items.append({"path": _rel(path, base), "line": line_no, "kind": match.group(1).upper(), "text": match.group(2).strip()[:300]})
        except Exception:
            continue
        if len(items) >= 300:
            break
    return {"root": str(base), "items": items, "summary": f"Found {len(items)} TODO/bug markers."}


def track_tests(root: str | Path = "") -> dict[str, Any]:
    base = _safe_root(root)
    tests = []
    for path in _iter_files(base):
        name = path.name.lower()
        rel = _rel(path, base)
        if name.startswith("test_") or name.endswith(".test.js") or name.endswith(".spec.ts") or "/tests/" in rel.replace("\\", "/"):
            tests.append({"path": rel, "kind": _test_kind(path)})
    return {"root": str(base), "tests": tests[:200], "summary": f"Found {len(tests)} test files."}


def answer_workspace_question(question: str, root: str | Path = "") -> dict[str, Any]:
    base = _safe_root(root)
    if app_integrations.workspace_overview(base).get("total_files", 0) == 0:
        app_integrations.index_workspace(base)
    results = app_integrations.search_workspace(question, limit=8)
    if not results:
        for term in _question_terms(question):
            results = app_integrations.search_workspace(term, limit=8)
            if results:
                break
    answer = "I found likely relevant files." if results else "I could not find a strong match in the indexed workspace."
    return {"question": question, "root": str(base), "answer": answer, "results": results, "summary": f"{answer} {len(results)} matches."}


def generate_docs(root: str | Path = "") -> dict[str, Any]:
    base = _safe_root(root)
    analysis = analyze_project(base)
    docs_dir = base / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    out = docs_dir / "friday_workspace_brain.md"
    lines = [
        "# Friday Workspace Brain",
        "",
        f"Generated: {_now()}",
        f"Root: `{base}`",
        "",
        "## Architecture",
        analysis["architecture"]["summary"],
        "",
        "## Key File Roles",
    ]
    lines.extend(f"- `{item['path']}`: {item['role']}" for item in analysis["files"][:80])
    lines.extend(["", "## TODOs And Bugs"])
    lines.extend(f"- `{item['path']}:{item['line']}` {item['kind']}: {item['text']}" for item in analysis["todos"][:80])
    lines.extend(["", "## Tests", analysis["tests"]["summary"], "", "## Dependencies", analysis["dependencies"]["summary"]])
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"path": str(out), "summary": f"Workspace brain docs written to {out}."}


def _file_roles(base: Path) -> list[dict[str, Any]]:
    roles = []
    for path in _iter_files(base):
        rel = _rel(path, base)
        roles.append({"path": rel, "role": _role_for(path, rel), "size": path.stat().st_size})
        if len(roles) >= int(config_value("workspace_brain_file_role_limit", 200)):
            break
    return roles


def _architecture(files: list[dict[str, Any]], deps: dict[str, Any]) -> dict[str, Any]:
    roles = {}
    for item in files:
        roles[item["role"]] = roles.get(item["role"], 0) + 1
    likely = sorted(roles.items(), key=lambda item: item[1], reverse=True)[:6]
    return {"roles": roles, "summary": f"Architecture appears to include: {', '.join(name for name, _ in likely) or 'unknown'}."}


def _role_for(path: Path, rel: str) -> str:
    name = path.name.lower()
    text = rel.replace("\\", "/").lower()
    if name in {"package.json", "pyproject.toml", "requirements.txt", "config.json"}:
        return "configuration/dependencies"
    if "test" in name or "/tests/" in text:
        return "tests"
    if "api" in text or "server" in name:
        return "api/backend"
    if "page." in name or "component" in text or path.suffix.lower() in {".jsx", ".tsx", ".css"}:
        return "frontend/ui"
    if "auth" in text or "permission" in text or "security" in text:
        return "auth/security"
    if "memory" in text or "brain" in text or "agent" in text:
        return "agent/cognition"
    if path.suffix.lower() in {".md", ".txt"}:
        return "documentation"
    return "source"


def _repo_kind(path: Path) -> str:
    if (path / "package.json").exists():
        return "node/web"
    if (path / "pyproject.toml").exists() or (path / "requirements.txt").exists():
        return "python"
    if (path / ".git").exists():
        return "git"
    return "project"


def _test_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return "pytest/python"
    if suffix in {".js", ".jsx", ".ts", ".tsx"}:
        return "js/test"
    return "test"


def _question_terms(question: str) -> list[str]:
    preferred = ["auth", "authentication", "login", "token", "session", "permission", "api", "route", "database", "config", "test"]
    lowered = str(question or "").lower()
    terms = [term for term in preferred if term in lowered]
    terms.extend(part for part in re.split(r"[^a-z0-9_]+", lowered) if len(part) > 3 and part not in {"where", "logic", "codebase", "workspace"})
    return list(dict.fromkeys(terms))


def _iter_files(base: Path):
    skip = {item.strip().lower() for item in str(config_value("workspace_index_skip_dirs", "")).replace("\\", "/").split(",") if item.strip()}
    allowed = {item.strip().lower() for item in str(config_value("workspace_index_extensions", "")).split(",") if item.strip()}
    count = 0
    for path in base.rglob("*"):
        if count >= int(config_value("workspace_brain_max_files", 1500)):
            break
        if not path.is_file() or _skip(path, base, skip):
            continue
        if allowed and path.suffix.lower() not in allowed and path.name.lower() not in allowed:
            continue
        count += 1
        yield path


def _skip(path: Path, base: Path, skip: set[str] | None = None) -> bool:
    skip = skip or {".git", ".venv", "node_modules", "__pycache__", ".next", "dist", "build"}
    try:
        rel = path.relative_to(base)
    except Exception:
        return False
    rel_text = "/".join(part.lower() for part in rel.parts)
    return any(part.lower() in skip for part in rel.parts) or any(rel_text.startswith(item + "/") for item in skip if "/" in item)


def _safe_root(root: str | Path = "") -> Path:
    candidate = resolve_coding_root(root)
    try:
        resolved = candidate.resolve()
    except Exception:
        resolved = resolve_coding_root()
    fallback = resolve_coding_root()
    return resolved if resolved.exists() and resolved.is_dir() else fallback


def _rel(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except Exception:
        return str(path)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

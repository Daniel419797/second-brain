"""Production coding autonomy prep: sandboxes, tests, CI, rollback, and scans."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any

from core import audit_log, codebase_standards, project_memory, trust_proof
from core.config import config_value, resolve_coding_root

FRIDAY_DIR = ".friday"


def prepare_project(
    root: str | Path = "",
    *,
    request: str = "",
    create_files: bool = True,
    run_scans: bool = True,
) -> dict[str, Any]:
    project_root = _safe_root(root)
    project_root.mkdir(parents=True, exist_ok=True)
    tests = discover_tests(project_root)
    ci = _ci_plan(project_root, tests)
    rollback = _rollback_plan(project_root, tests, request)
    performance = _performance_budget(project_root)
    deploy = _deploy_preview_plan(project_root)
    security = _security_preflight(project_root)
    scan = codebase_standards.scan(project_root, focus="production coding autonomy", max_files=120) if run_scans else {}
    files: list[str] = []
    if create_files:
        friday_dir = project_root / FRIDAY_DIR
        friday_dir.mkdir(parents=True, exist_ok=True)
        writes = {
            "ci-plan.yml": ci["content"],
            "rollback-plan.md": rollback["content"],
            "performance-budget.json": _json_dumps(performance["budget"]),
            "deploy-preview-plan.md": deploy["content"],
            "security-preflight.json": _json_dumps(security["checks"]),
        }
        for name, content in writes.items():
            path = friday_dir / name
            path.write_text(content, encoding="utf-8")
            files.append(str(path))
    note = project_memory.remember(
        project_root,
        "production_autonomy",
        "Production coding autonomy prep",
        _clean(request) or "Friday prepared CI, rollback, security, performance, and deploy preview plans.",
        confidence=0.82,
        metadata={"source": "production_coding_autonomy", "created_files": files, "test_commands": tests},
    )
    proof = trust_proof.create_report(
        f"Production coding prep for {project_root.name}",
        changed=[f"Prepared {len(files)} production autonomy artifact(s) under {project_root / FRIDAY_DIR}" if files else "Prepared production autonomy plan in memory."],
        tested=tests or ["No test commands discovered yet."],
        evidence=[scan.get("summary", "Codebase scan was skipped.") if isinstance(scan, dict) else "Codebase scan unavailable."],
        risks=["Generated CI/deploy plans are local scaffolds until connected to the project repository and hosting provider."],
        confidence=0.78,
        metadata={"source": "production_coding_autonomy", "root": str(project_root)},
    )
    audit_log.record(category="production_coding", action="prepare_project", target=str(project_root), success=True, details={"files": files, "tests": tests})
    return {
        "ok": True,
        "root": str(project_root),
        "request": request,
        "test_commands": tests,
        "artifacts": files,
        "ci_plan": ci,
        "rollback_plan": rollback,
        "performance_budget": performance,
        "deploy_preview": deploy,
        "security_preflight": security,
        "scan": scan,
        "memory": note,
        "proof": proof,
        "summary": f"Prepared production coding autonomy for {project_root.name}: {len(tests)} test command(s), {len(files)} artifact(s), and security/performance gates.",
    }


def status(root: str | Path = "") -> dict[str, Any]:
    project_root = _safe_root(root)
    friday_dir = project_root / FRIDAY_DIR
    artifacts = []
    if friday_dir.exists():
        artifacts = [str(path) for path in sorted(friday_dir.glob("*")) if path.is_file()]
    return {
        "enabled": bool(config_value("production_coding_autonomy_enabled", True)),
        "root": str(project_root),
        "sandbox_root": str(resolve_coding_root()),
        "test_commands": discover_tests(project_root) if project_root.exists() else [],
        "artifacts": artifacts,
        "summary": f"Production coding autonomy root is {project_root}; {len(artifacts)} artifact(s) found.",
    }


def discover_tests(root: str | Path = "") -> list[str]:
    base = _safe_root(root)
    commands: list[str] = []
    package = _read_json(base / "package.json")
    scripts = package.get("scripts") if isinstance(package.get("scripts"), dict) else {}
    for name in ("lint", "typecheck", "test", "test:unit", "test:e2e", "build"):
        if name in scripts:
            commands.append(f"npm run {name}")
    if (base / "pnpm-lock.yaml").exists():
        commands = [cmd.replace("npm run ", "pnpm ") if cmd.startswith("npm run ") else cmd for cmd in commands]
    if (base / "yarn.lock").exists():
        commands = [cmd.replace("npm run ", "yarn ") if cmd.startswith("npm run ") else cmd for cmd in commands]
    pyproject = _read_text(base / "pyproject.toml")
    if (base / "pytest.ini").exists() or (base / "tests").exists() or "pytest" in pyproject:
        commands.append("python -m pytest")
    if "ruff" in pyproject or (base / "ruff.toml").exists():
        commands.append("python -m ruff check .")
    if "mypy" in pyproject or (base / "mypy.ini").exists():
        commands.append("python -m mypy .")
    if (base / "manage.py").exists():
        commands.append("python manage.py test")
    if (base / "go.mod").exists():
        commands.extend(["go test ./...", "go vet ./..."])
    if (base / "Cargo.toml").exists():
        commands.extend(["cargo test", "cargo clippy -- -D warnings"])
    if (base / "pom.xml").exists():
        commands.append("mvn test")
    return _dedupe(commands)


def wipe_all(root: str | Path = "") -> dict[str, Any]:
    project_root = _safe_root(root)
    friday_dir = project_root / FRIDAY_DIR
    if not friday_dir.exists():
        return {"removed": 0, "summary": "No production coding artifacts found."}
    removed = 0
    for path in friday_dir.glob("*"):
        if path.is_file() and path.name in {"ci-plan.yml", "rollback-plan.md", "performance-budget.json", "deploy-preview-plan.md", "security-preflight.json"}:
            path.unlink()
            removed += 1
    return {"removed": removed, "summary": f"Removed {removed} production coding artifact(s)."}


def _ci_plan(root: Path, tests: list[str]) -> dict[str, Any]:
    commands = tests or ["echo \"No tests discovered yet\""]
    content = "\n".join(
        [
            "name: Friday Production Guard",
            "on:",
            "  pull_request:",
            "  push:",
            "    branches: [main]",
            "jobs:",
            "  verify:",
            "    runs-on: ubuntu-latest",
            "    steps:",
            "      - uses: actions/checkout@v4",
            "      - name: Run discovered checks",
            "        shell: bash",
            "        run: |",
            *[f"          {cmd}" for cmd in commands],
            "",
        ]
    )
    return {"path": str(root / FRIDAY_DIR / "ci-plan.yml"), "commands": commands, "content": content}


def _rollback_plan(root: Path, tests: list[str], request: str) -> dict[str, Any]:
    content = "\n".join(
        [
            "# Rollback Plan",
            "",
            f"Project: {root.name}",
            f"Request: {_clean(request) or 'Production coding autonomy prep'}",
            "",
            "1. Capture the current commit hash before merge or deploy.",
            "2. Keep deploy preview URL and smoke-test proof attached to the task.",
            "3. If production breaks, revert the merge commit or redeploy the previous known-good build.",
            "4. Re-run the checks below before reattempting release:",
            *[f"   - `{cmd}`" for cmd in (tests or ["Add a project-specific smoke test command."])],
            "5. Record the failure in project memory before retrying.",
            "",
        ]
    )
    return {"path": str(root / FRIDAY_DIR / "rollback-plan.md"), "content": content}


def _performance_budget(root: Path) -> dict[str, Any]:
    budget = {
        "api_import_seconds_max": float(config_value("performance_budget_api_import_seconds_max", 8.0)),
        "web_build_seconds_max": float(config_value("performance_budget_web_build_seconds_max", 120.0)),
        "pytest_smoke_seconds_max": float(config_value("performance_budget_pytest_smoke_seconds_max", 60.0)),
        "dashboard_stream_interval_seconds_max": float(config_value("performance_budget_dashboard_stream_interval_seconds_max", 2.0)),
        "notes": "Budgets are enforced as warnings until CI wires them to real measurements.",
    }
    return {"path": str(root / FRIDAY_DIR / "performance-budget.json"), "budget": budget}


def _deploy_preview_plan(root: Path) -> dict[str, Any]:
    content = "\n".join(
        [
            "# Deploy Preview Plan",
            "",
            "Required before production deploy:",
            "- Environment variables are configured in the hosting provider.",
            "- Preview build completes successfully.",
            "- Auth, CORS, WebSocket, database, and provider integrations are smoke-tested.",
            "- A human approves production deploy if customer-visible or payment/outreach related.",
            "",
            "Evidence Friday must attach:",
            "- Build log summary.",
            "- Preview URL.",
            "- Smoke-test result.",
            "- Rollback target.",
            "",
        ]
    )
    return {"path": str(root / FRIDAY_DIR / "deploy-preview-plan.md"), "content": content}


def _security_preflight(root: Path) -> dict[str, Any]:
    checks = {
        "secret_scan": True,
        "dependency_scan": True,
        "shell_command_review": True,
        "cors_origin_review": True,
        "auth_required_for_admin_routes": True,
        "outreach_payment_deploy_approval_required": True,
        "evidence_required_before_success_claim": True,
    }
    return {"path": str(root / FRIDAY_DIR / "security-preflight.json"), "checks": checks}


def _safe_root(root: str | Path) -> Path:
    return resolve_coding_root(root)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = _clean(value)
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

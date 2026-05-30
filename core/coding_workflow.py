"""Reusable coding workflow discipline for Friday's autonomous builders."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from core.config import config_value

SKIP_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".turbo",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "data",
    "dist",
    "node_modules",
    "out",
    "target",
    "venv",
}

CODE_EXTENSIONS = {
    ".css",
    ".dart",
    ".go",
    ".html",
    ".js",
    ".jsx",
    ".md",
    ".py",
    ".rs",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}


def operating_rules() -> list[dict[str, str]]:
    return [
        {
            "id": "inspect_project_shape",
            "label": "Understand the shape first",
            "evidence": "Record project markers, languages, sample files, tests, and stack before writing files.",
        },
        {
            "id": "separate_responsibilities",
            "label": "Separate responsibilities",
            "evidence": "Map UI, state, API, validation, persistence, tests, and proof into explicit files or modules.",
        },
        {
            "id": "explicit_contract",
            "label": "Use explicit contracts",
            "evidence": "Attach success criteria, expected output, changed files, verification checks, and proof paths.",
        },
        {
            "id": "boring_names",
            "label": "Prefer boring names",
            "evidence": "Use direct names such as create_task, project_root, verify_artifact, and agent_result.",
        },
        {
            "id": "scoped_edits",
            "label": "Keep edits scoped",
            "evidence": "Declare whether the work is a new app scaffold, existing-project plan, or approved self-update.",
        },
        {
            "id": "close_verification_loop",
            "label": "Close the loop with verification",
            "evidence": "Do not mark done until local file checks or discovered tests are recorded, with any gaps named.",
        },
    ]


def inspect_project(root: str | Path, request: str = "", *, stack: dict[str, Any] | None = None) -> dict[str, Any]:
    base = Path(root).resolve()
    markers = _project_markers(base)
    files = _sample_files(base, int(config_value("autonomous_coding_inspection_file_limit", 80)))
    languages = _language_counts(files)
    tests = _discover_tests(base)
    stack_info = stack or _infer_stack_from_markers(markers)
    exists = base.exists()
    summary = (
        f"Inspected {base}: "
        f"{'exists' if exists else 'missing/new root'}, "
        f"{len(files)} sampled file(s), "
        f"{len(markers)} marker(s), "
        f"{len(tests)} discovered check(s)."
    )
    return {
        "root": str(base),
        "exists": exists,
        "request": _clean(request),
        "stack": stack_info,
        "markers": markers,
        "languages": languages,
        "files_sample": files[:24],
        "test_commands": tests,
        "responsibility_boundaries": responsibility_boundaries(stack_info, markers=markers),
        "summary": summary,
    }


def build_execution_plan(
    request: str,
    root: str | Path,
    *,
    stack: dict[str, Any] | None = None,
    inspection: dict[str, Any] | None = None,
    standards: dict[str, Any] | None = None,
    execution_kind: str = "",
) -> dict[str, Any]:
    stack_info = stack or {}
    inspected = inspection or inspect_project(root, request, stack=stack_info)
    findings = standards.get("findings") if isinstance(standards, dict) else []
    high_findings = [item for item in findings or [] if int(item.get("severity") or 0) >= 4]
    flow = [
        "inspect_project_shape",
        "capture_requirements_acceptance",
        "decide_architecture_stack",
        "identify_responsibility_boundaries",
        "prepare_scoped_change_set",
        "write_or_stage_files",
        "prepare_unit_integration_e2e_tests",
        "run_security_dependency_preflight",
        "define_performance_reliability_budget",
        "prepare_ux_browser_verification",
        "prepare_deployment_preview",
        "prepare_launch_assets_pricing_ads_docs",
        "prepare_operations_support_observability",
        "verify_artifact_or_plan",
        "report_final_proof_with_gaps",
    ]
    gates = [
        "required files exist",
        "changed files are recorded",
        "verification evidence is attached",
        "unrun checks are listed as risks",
        "product-studio phases and final proof gaps are attached",
        "market-ready is false until tests, security, browser proof, deployment preview, and launch approvals are complete",
    ]
    if high_findings:
        gates.append("high-severity standards findings are named before broad changes")
    return {
        "request": _clean(request),
        "root": str(Path(root).resolve()),
        "execution_kind": execution_kind or "coding_task",
        "stack": stack_info,
        "flow": flow,
        "responsibility_boundaries": inspected.get("responsibility_boundaries") or responsibility_boundaries(stack_info),
        "quality_gates": gates,
        "standards_summary": standards.get("summary") if isinstance(standards, dict) else "",
        "high_severity_findings": high_findings[:8],
        "scope_note": _scope_note(execution_kind),
    }


def responsibility_boundaries(stack: dict[str, Any] | None = None, *, markers: list[str] | None = None) -> list[dict[str, str]]:
    stack_id = str((stack or {}).get("stack") or "")
    if stack_id == "flutter":
        return [
            {"area": "presentation", "owner": "lib/home_screen.dart", "rule": "Screens render state and call store methods."},
            {"area": "state", "owner": "lib/workflow_store.dart", "rule": "Workflow state, brief generation, and item updates stay out of widgets."},
            {"area": "entrypoint", "owner": "lib/main.dart", "rule": "App bootstrap only."},
            {"area": "verification", "owner": "test/widget_test.dart", "rule": "Smoke tests prove the app renders."},
        ]
    if stack_id == "node_fastify":
        return _backend_boundaries("src/app.js", "src/routes", "src/services", "src/storage", "test")
    if stack_id == "python_fastapi":
        return _backend_boundaries("*/main.py", "*/routes.py", "*/services.py", "*/models.py", "tests")
    if stack_id == "go_api":
        return _backend_boundaries("main.go", "handlers.go", "services in functions", "models.go", "main_test.go")
    if stack_id == "rust_axum":
        return _backend_boundaries("src/main.rs", "src/routes.rs", "service functions", "src/models.rs", "cargo test")
    if stack_id == "nextjs":
        return [
            {"area": "routing", "owner": "src/app", "rule": "Route files stay thin and compose feature components from src/components."},
            {"area": "feature_ui", "owner": "src/components/<FeatureName>", "rule": "Product UI is grouped by feature, not dumped into route files."},
            {"area": "design_system", "owner": "src/components/ui", "rule": "Reusable primitives are shadcn-style building blocks with boring names."},
            {"area": "layout_shell", "owner": "src/components/layout", "rule": "Navigation, app shell, and top bar are isolated from feature screens."},
            {"area": "client_state", "owner": "src/store", "rule": "Shared browser state lives in stores instead of route components."},
            {"area": "hooks", "owner": "src/hooks", "rule": "Reusable client workflows are hooks, not repeated component code."},
            {"area": "api_clients", "owner": "src/services", "rule": "Backend calls and response normalization live outside UI components."},
            {"area": "domain_logic", "owner": "src/lib", "rule": "Product data, security helpers, utilities, and brief generation are reusable and testable."},
            {"area": "types", "owner": "src/types", "rule": "Shared DTOs and UI contracts are explicit TypeScript types."},
            {"area": "api", "owner": "src/app/api/brief/route.ts", "rule": "Backend-facing behavior uses a route handler, not UI-only stubs."},
            {"area": "verification", "owner": "src/test and colocated __tests__", "rule": "Services, stores, and UI helpers carry local tests."},
        ]
    if markers:
        return [
            {"area": "inspection", "owner": ", ".join(markers[:4]), "rule": "Existing project markers decide where changes belong."},
            {"area": "implementation", "owner": "candidate files", "rule": "Patch the smallest set of files tied to the request."},
            {"area": "verification", "owner": "discovered checks", "rule": "Run or record the closest available tests before claiming done."},
        ]
    return [
        {"area": "inspection", "owner": "project root", "rule": "Inspect before choosing files."},
        {"area": "implementation", "owner": "scoped files", "rule": "Keep each file responsible for one stable concern."},
        {"area": "verification", "owner": "task contract", "rule": "Attach evidence before success."},
    ]


def verify_project_artifact(root: str | Path, stack: dict[str, Any], written: list[str]) -> dict[str, Any]:
    base = Path(root).resolve()
    stack_id = stack.get("stack") or "nextjs"
    required = required_files_for_stack(stack_id, base)
    missing = [relative for relative in required if not (base / relative).exists()]
    written_missing = [path for path in written if path and not Path(path).exists()]
    empty = [
        str(Path(path))
        for path in written
        if _should_have_content(Path(path)) and Path(path).exists() and Path(path).is_file() and Path(path).stat().st_size <= 0
    ]
    errors: list[str] = []
    checks: list[str] = []
    if base.exists():
        checks.append(f"verified project root exists: {base}")
    checks.extend(f"verified file exists: {relative}" for relative in required if (base / relative).exists())
    errors.extend(_manifest_errors(base))
    errors.extend(_stack_shape_errors(base, stack_id))
    if not errors and not missing and not written_missing and not empty:
        status = "passed"
        summary = f"Artifact verification passed for {base}."
    else:
        status = "failed"
        problems = [*missing, *written_missing, *empty, *errors]
        summary = f"Artifact verification failed for {base}: {', '.join(str(item) for item in problems[:6])}."
    return {
        "status": status,
        "summary": summary,
        "checks": checks,
        "missing": [*missing, *written_missing],
        "empty_files": empty,
        "errors": errors,
        "project_root": str(base),
        "required_files": required,
        "responsibility_boundaries": responsibility_boundaries(stack),
    }


def required_files_for_stack(stack_id: str, root: Path | None = None) -> list[str]:
    if stack_id == "nextjs":
        return [
            "package.json",
            "README.md",
            "FRONTEND_STRUCTURE.md",
            "components.json",
            "vitest.config.ts",
            "src/app/page.tsx",
            "src/app/(dashboard)/layout.tsx",
            "src/app/(dashboard)/workspace/page.tsx",
            "src/app/api/brief/route.ts",
            "src/components/Landing/HomePage.tsx",
            "src/components/Workspace/WorkspaceConsole.tsx",
            "src/components/Workspace/WorkItemCard.tsx",
            "src/components/layout/AppShell.tsx",
            "src/components/ui/button.tsx",
            "src/hooks/useBriefDraft.ts",
            "src/lib/productPlan.ts",
            "src/services/api.ts",
            "src/services/BriefService.ts",
            "src/store/workspaceStore.ts",
            "src/test/setup.ts",
            "src/types/index.ts",
        ]
    if stack_id == "flutter":
        return ["pubspec.yaml", "README.md", "lib/main.dart", "lib/home_screen.dart", "lib/workflow_store.dart", "test/widget_test.dart"]
    if stack_id == "node_fastify":
        return ["package.json", "README.md", "src/app.js", "src/server.js", "src/routes/brief.js", "src/services/briefService.js", "test/health.test.js"]
    if stack_id == "python_fastapi":
        package = _python_package_name(root) if root else ""
        if package:
            return ["pyproject.toml", "README.md", f"{package}/main.py", f"{package}/models.py", f"{package}/routes.py", f"{package}/services.py", "tests/test_health.py"]
        return ["pyproject.toml", "README.md", "tests/test_health.py"]
    if stack_id == "go_api":
        return ["go.mod", "README.md", "main.go", "handlers.go", "models.go", "main_test.go"]
    if stack_id == "rust_axum":
        return ["Cargo.toml", "README.md", "src/main.rs", "src/models.rs", "src/routes.rs"]
    if stack_id == "plan":
        return []
    return ["README.md"]


def _backend_boundaries(entrypoint: str, routes: str, services: str, data: str, tests: str) -> list[dict[str, str]]:
    return [
        {"area": "entrypoint", "owner": entrypoint, "rule": "Bootstraps the server and wires routes only."},
        {"area": "routes", "owner": routes, "rule": "HTTP concerns, status codes, and request parsing live here."},
        {"area": "domain_logic", "owner": services, "rule": "Business logic is reusable outside handlers."},
        {"area": "validation_or_persistence", "owner": data, "rule": "Models, validation, and temporary persistence are not mixed into route handlers."},
        {"area": "verification", "owner": tests, "rule": "Health and core behavior are covered by a local smoke check."},
    ]


def _project_markers(base: Path) -> list[str]:
    names = [
        "package.json",
        "next.config.mjs",
        "vite.config.js",
        "pyproject.toml",
        "requirements.txt",
        "Cargo.toml",
        "go.mod",
        "pubspec.yaml",
        "Dockerfile",
        ".git",
    ]
    return [name for name in names if (base / name).exists()]


def _sample_files(base: Path, limit: int) -> list[str]:
    if not base.exists():
        return []
    files: list[str] = []
    for current, dirs, names in os.walk(base):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS and not name.startswith(".cache")]
        for name in names:
            path = Path(current) / name
            if path.suffix.lower() not in CODE_EXTENSIONS:
                continue
            try:
                files.append(str(path.resolve().relative_to(base)).replace("\\", "/"))
            except ValueError:
                files.append(str(path))
            if len(files) >= limit:
                return files
    return files


def _language_counts(files: list[str]) -> dict[str, int]:
    labels = {
        ".css": "css",
        ".dart": "dart",
        ".go": "go",
        ".js": "javascript",
        ".jsx": "javascript",
        ".py": "python",
        ".rs": "rust",
        ".ts": "typescript",
        ".tsx": "typescript",
    }
    counter = Counter(labels.get(Path(path).suffix.lower()) for path in files)
    counter.pop(None, None)
    return {key: int(counter[key]) for key in sorted(counter)}


def _discover_tests(base: Path) -> list[str]:
    try:
        from core import production_coding_autonomy

        return production_coding_autonomy.discover_tests(base)
    except Exception:
        return []


def _infer_stack_from_markers(markers: list[str]) -> dict[str, str]:
    if "pubspec.yaml" in markers:
        return {"kind": "mobile", "stack": "flutter", "language": "dart", "label": "Flutter mobile app"}
    if "Cargo.toml" in markers:
        return {"kind": "backend", "stack": "rust_axum", "language": "rust", "label": "Rust backend"}
    if "go.mod" in markers:
        return {"kind": "backend", "stack": "go_api", "language": "go", "label": "Go backend"}
    if "pyproject.toml" in markers or "requirements.txt" in markers:
        return {"kind": "backend", "stack": "python_fastapi", "language": "python", "label": "Python backend"}
    if "package.json" in markers:
        return {"kind": "web_app", "stack": "nextjs", "language": "typescript", "label": "JavaScript/TypeScript app"}
    return {"kind": "unknown", "stack": "unknown", "language": "unknown", "label": "project"}


def _scope_note(execution_kind: str) -> str:
    notes = {
        "scaffold_new_app": "New project: Friday may write a complete starter under the coding projects root and verify file evidence.",
        "self_update_proposal": "Friday codebase: create a proposal first; source changes need approval before staging/applying.",
        "existing_project_plan": "Existing project: inspect and prepare a plan unless a concrete approved patch workflow exists.",
    }
    return notes.get(execution_kind, "Use the smallest safe coding scope and attach proof.")


def _manifest_errors(base: Path) -> list[str]:
    errors: list[str] = []
    package = base / "package.json"
    if package.exists():
        try:
            data = json.loads(package.read_text(encoding="utf-8"))
            if not isinstance(data.get("scripts"), dict):
                errors.append("package.json scripts must be an object")
        except Exception as exc:
            errors.append(f"package.json is invalid JSON: {exc}")
    pubspec = base / "pubspec.yaml"
    if pubspec.exists() and "dependencies:" not in pubspec.read_text(encoding="utf-8", errors="ignore"):
        errors.append("pubspec.yaml is missing dependencies")
    return errors


def _stack_shape_errors(base: Path, stack_id: str) -> list[str]:
    errors: list[str] = []
    if stack_id == "nextjs":
        page = _read(base / "src/app/page.tsx")
        dashboard_page = _read(base / "src/app/(dashboard)/workspace/page.tsx")
        console = _read(base / "src/components/Workspace/WorkspaceConsole.tsx")
        service = _read(base / "src/services/BriefService.ts")
        store = _read(base / "src/store/workspaceStore.ts")
        components_config = _read(base / "components.json")
        vitest_config = _read(base / "vitest.config.ts")
        plan = _read(base / "src/lib/productPlan.ts")
        route = _read(base / "src/app/api/brief/route.ts")
        if "HomePage" not in page:
            errors.append("src/app/page.tsx must stay thin and compose components/Landing/HomePage")
        if "WorkspacePage" not in dashboard_page:
            errors.append("src/app/(dashboard)/workspace/page.tsx must compose components/Workspace/WorkspacePage")
        if "useWorkspaceStore" not in console or "useBriefDraft" not in console:
            errors.append("WorkspaceConsole must delegate shared state to src/store and async brief behavior to src/hooks")
        if "apiClient" not in service or "normalizeBrief" not in service:
            errors.append("src/services/BriefService.ts must own API calls and response normalization")
        if "create<" not in store or "markWorkItemReviewed" not in store:
            errors.append("src/store/workspaceStore.ts must own reusable client state")
        if "createDecisionBrief" not in plan:
            errors.append("src/lib/productPlan.ts must expose createDecisionBrief")
        if "POST" not in route or "NextResponse" not in route:
            errors.append("brief route handler must expose a POST response")
        if "@/components" not in components_config or "@/lib" not in components_config:
            errors.append("components.json must declare NexusForge-style src aliases")
        if "jsdom" not in vitest_config or "src/test/setup.ts" not in vitest_config:
            errors.append("vitest.config.ts must use jsdom and src/test setup")
    return errors


def _python_package_name(root: Path | None) -> str:
    if not root or not root.exists():
        return ""
    for child in root.iterdir():
        if child.is_dir() and (child / "main.py").exists():
            return child.name
    return ""


def _should_have_content(path: Path) -> bool:
    return path.name != "__init__.py" and path.suffix.lower() in CODE_EXTENSIONS | {".json"}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()

"""Reusable project inspection for Friday's operating system."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core import coding_workflow, project_scaffolds, style_profiles


def inspect_project(root: str | Path, request: str = "", *, stack: dict[str, Any] | None = None) -> dict[str, Any]:
    base = Path(root).resolve()
    stack_info = stack or project_scaffolds.detect_stack(request)
    workflow = coding_workflow.inspect_project(base, request, stack=stack_info)
    framework = _framework(base, stack_info)
    package = _package_json(base)
    profile = style_profiles.infer_profile(base, framework)
    style_evaluation = style_profiles.evaluate_project(base, profile["id"]) if profile else {}
    intelligence = {
        "root": str(base),
        "request": str(request or ""),
        "stack": stack_info,
        "framework": framework,
        "language": _language(stack_info, workflow),
        "package_manager": _package_manager(base),
        "test_commands": workflow.get("test_commands") or [],
        "route_conventions": _route_conventions(base),
        "component_structure": _component_structure(base),
        "api_conventions": _api_conventions(base),
        "database_layer": _database_layer(base, package),
        "auth_layer": _auth_layer(base, package),
        "deployment_target": _deployment_target(base),
        "style_profile": profile,
        "style_evaluation": style_evaluation,
        "workflow_inspection": workflow,
        "summary": "",
    }
    intelligence["summary"] = _summary(intelligence)
    return intelligence


def architecture_decision(intelligence: dict[str, Any], request: str = "") -> dict[str, Any]:
    stack = intelligence.get("stack") if isinstance(intelligence.get("stack"), dict) else {}
    profile = intelligence.get("style_profile") if isinstance(intelligence.get("style_profile"), dict) else {}
    return {
        "stack": stack,
        "framework": intelligence.get("framework") or "unknown",
        "package_manager": intelligence.get("package_manager") or "unknown",
        "style_profile_id": profile.get("id") or "",
        "source_root": "src" if (Path(intelligence.get("root", "")) / "src").exists() else ".",
        "routing": intelligence.get("route_conventions") or [],
        "state": "src/store" if "src/store" in intelligence.get("component_structure", []) else "local until shared state exists",
        "api_layer": "src/services" if "src/services" in intelligence.get("component_structure", []) else "route handlers or backend modules",
        "tests": intelligence.get("test_commands") or [],
        "request": request,
        "rationale": "Follow the discovered project shape first; for Next.js web apps, prefer the NexusForge profile unless the project already defines a stronger local convention.",
    }


def _framework(base: Path, stack: dict[str, Any]) -> str:
    if stack.get("stack") == "nextjs" or (base / "next.config.mjs").exists() or (base / "next.config.js").exists():
        return "nextjs"
    if stack.get("stack") == "flutter" or (base / "pubspec.yaml").exists():
        return "flutter"
    if stack.get("stack") == "node_fastify":
        return "fastify"
    if stack.get("stack") == "python_fastapi":
        return "fastapi"
    if stack.get("stack") == "go_api":
        return "go_http"
    if stack.get("stack") == "rust_axum":
        return "axum"
    return "unknown"


def _language(stack: dict[str, Any], workflow: dict[str, Any]) -> str:
    if stack.get("language"):
        return str(stack["language"])
    counts = workflow.get("languages") if isinstance(workflow.get("languages"), dict) else {}
    return max(counts, key=counts.get) if counts else "unknown"


def _package_manager(base: Path) -> str:
    if (base / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (base / "yarn.lock").exists():
        return "yarn"
    if (base / "bun.lockb").exists() or (base / "bun.lock").exists():
        return "bun"
    if (base / "package-lock.json").exists() or (base / "package.json").exists():
        return "npm"
    if (base / "pubspec.yaml").exists():
        return "flutter"
    if (base / "pyproject.toml").exists():
        return "python"
    if (base / "go.mod").exists():
        return "go"
    if (base / "Cargo.toml").exists():
        return "cargo"
    return "unknown"


def _route_conventions(base: Path) -> list[str]:
    conventions = []
    if (base / "src/app").exists():
        conventions.append("next_app_router_src")
    if (base / "app").exists():
        conventions.append("next_app_router_root")
    if (base / "src/app").exists() and any(child.is_dir() and child.name.startswith("(") and child.name.endswith(")") for child in (base / "src/app").iterdir()):
        conventions.append("route_groups")
    if (base / "src/routes").exists():
        conventions.append("backend_routes")
    if (base / "pages").exists() or (base / "src/pages").exists():
        conventions.append("pages_router")
    return conventions


def _component_structure(base: Path) -> list[str]:
    roots = []
    for relative in ("src/components", "src/components/ui", "src/components/layout", "src/services", "src/store", "src/hooks", "src/lib", "src/types", "src/test"):
        if (base / relative).exists():
            roots.append(relative)
    return roots


def _api_conventions(base: Path) -> list[str]:
    conventions = []
    if (base / "src/services").exists():
        conventions.append("frontend_services")
    if (base / "src/app/api").exists():
        conventions.append("next_route_handlers")
    if (base / "src/routes").exists():
        conventions.append("backend_route_modules")
    return conventions


def _database_layer(base: Path, package: dict[str, Any]) -> str:
    deps = _deps(package)
    for name in ("drizzle-orm", "@prisma/client", "prisma", "@neondatabase/serverless", "pg", "better-sqlite3"):
        if name in deps:
            return name
    if (base / "src/db").exists() or (base / "db").exists():
        return "local_db_layer"
    return "not_detected"


def _auth_layer(base: Path, package: dict[str, Any]) -> str:
    deps = _deps(package)
    for name in ("@clerk/nextjs", "@auth0/nextjs-auth0", "@descope/nextjs-sdk", "next-auth"):
        if name in deps:
            return name
    if any(path.exists() for path in (base / "src/components/Auth", base / "src/app/(auth)", base / "src/services/AuthService.ts")):
        return "local_auth_modules"
    return "not_detected"


def _deployment_target(base: Path) -> str:
    if (base / "vercel.json").exists():
        return "vercel"
    if (base / "render.yaml").exists():
        return "render"
    if (base / "fly.toml").exists():
        return "fly"
    if (base / "Dockerfile").exists():
        return "docker"
    return "not_detected"


def _package_json(base: Path) -> dict[str, Any]:
    path = base / "package.json"
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _deps(package: dict[str, Any]) -> set[str]:
    deps: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        value = package.get(key)
        if isinstance(value, dict):
            deps.update(value.keys())
    return deps


def _summary(intelligence: dict[str, Any]) -> str:
    profile = intelligence.get("style_profile") if isinstance(intelligence.get("style_profile"), dict) else {}
    style = intelligence.get("style_evaluation") if isinstance(intelligence.get("style_evaluation"), dict) else {}
    style_text = style.get("summary") if style else "No style profile applied."
    return (
        f"{intelligence.get('framework', 'unknown')} project using {intelligence.get('package_manager', 'unknown')} "
        f"at {intelligence.get('root')}. Style profile: {profile.get('id') or 'none'}; {style_text}"
    )

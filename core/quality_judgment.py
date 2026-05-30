"""Quality judgment for Friday's engineering results."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import evidence_judgment, project_intelligence, style_profiles


QUALITY_PRIORITIES = [
    "security",
    "speed_and_performance",
    "maintainability",
    "reliability",
    "practical_reusability",
    "readability",
    "good_coding_practices",
]


def judge_project(root: str | Path, request: str = "", *, profile_id: str = "") -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    intelligence = project_intelligence.inspect_project(base, request)
    profile = profile_id or ((intelligence.get("style_profile") or {}).get("id") if isinstance(intelligence.get("style_profile"), dict) else "")
    style = style_profiles.evaluate_project(base, profile or "nexus_forge_nextjs") if profile or _looks_next(base) else {}
    checks = _checks(base, intelligence, style)
    gaps = [check["summary"] for check in checks if check["status"] == "failed"]
    return {
        "ok": not gaps,
        "root": str(base),
        "priorities": QUALITY_PRIORITIES,
        "intelligence": intelligence,
        "style_evaluation": style,
        "checks": checks,
        "gaps": gaps,
        "score": _score(checks),
        "summary": "Quality judgment passed." if not gaps else f"Quality judgment found {len(gaps)} gap(s).",
    }


def judge_output(result: Any, *, root: str | Path = "") -> dict[str, Any]:
    evidence = evidence_judgment.judge(result, root=root)
    project_quality = judge_project(root, str(result)) if root and Path(root).exists() else {}
    gaps = [
        *(evidence.get("shallow_output", {}).get("reasons") or []),
        *(project_quality.get("gaps") or []),
    ]
    return {
        "ok": evidence.get("ok") and (not project_quality or project_quality.get("ok")),
        "evidence": evidence,
        "project_quality": project_quality,
        "gaps": _dedupe(gaps),
        "summary": "Output quality is acceptable." if not gaps else f"Output quality has {len(_dedupe(gaps))} gap(s).",
    }


def _checks(base: Path, intelligence: dict[str, Any], style: dict[str, Any]) -> list[dict[str, str]]:
    workflow = intelligence.get("workflow_inspection") if isinstance(intelligence.get("workflow_inspection"), dict) else {}
    component_structure = intelligence.get("component_structure") if isinstance(intelligence.get("component_structure"), list) else []
    test_commands = intelligence.get("test_commands") if isinstance(intelligence.get("test_commands"), list) else []
    checks = [
        _check("manifest", "Install manifest exists", _has_manifest(base), "No package/build manifest was found."),
        _check("tests", "Test command detected", bool(test_commands or _has_tests(base)), "No test command or test files detected."),
        _check("responsibility_split", "Responsibilities split by folders", len(component_structure) >= 3 or _responsibility_split(base), "Implementation shape is too flat."),
        _check("style_profile", "Style profile satisfied", not style or bool(style.get("ok")), (style.get("summary") if isinstance(style, dict) else "") or "Style profile has gaps."),
        _check("security_posture", "Security posture visible", _has_security_signal(base, workflow), "No security gate, audit script, or validation layer was detected."),
        _check("maintainability", "Maintainability structure visible", _maintainable(base), "No clear services/lib/types structure was detected."),
    ]
    return checks


def _check(check_id: str, label: str, passed: bool, failure: str) -> dict[str, str]:
    return {
        "id": check_id,
        "label": label,
        "status": "passed" if passed else "failed",
        "summary": label if passed else failure,
    }


def _has_manifest(base: Path) -> bool:
    return any((base / name).exists() for name in ("package.json", "pyproject.toml", "go.mod", "Cargo.toml", "pubspec.yaml"))


def _has_tests(base: Path) -> bool:
    return any(
        path.is_file()
        and (path.name.endswith((".test.ts", ".test.tsx", ".test.js", ".spec.ts", ".spec.tsx", "_test.py")) or "test" in path.parts or "tests" in path.parts or "__tests__" in path.parts)
        for path in base.rglob("*")
        if ".git" not in path.parts and "node_modules" not in path.parts
    )


def _responsibility_split(base: Path) -> bool:
    groups = ("src/app", "src/components", "src/services", "src/store", "src/hooks", "src/lib", "src/types", "src/routes", "tests")
    return sum(1 for group in groups if (base / group).exists()) >= 3


def _has_security_signal(base: Path, workflow: dict[str, Any]) -> bool:
    commands = " ".join(str(command) for command in workflow.get("test_commands") or [])
    if "audit" in commands or "bandit" in commands or "semgrep" in commands:
        return True
    return any((base / relative).exists() for relative in ("src/lib/security.ts", "src/lib/validation.ts", "src/middleware.ts", "Dockerfile"))


def _maintainable(base: Path) -> bool:
    return any((base / relative).exists() for relative in ("src/services", "src/lib", "src/types", "src/routes")) and not (base / "src/components/WorkspaceConsole.tsx").exists()


def _looks_next(base: Path) -> bool:
    return (base / "next.config.mjs").exists() or (base / "next.config.js").exists() or (base / "src/app").exists()


def _score(checks: list[dict[str, str]]) -> float:
    if not checks:
        return 0.0
    return round(sum(1 for check in checks if check.get("status") == "passed") / len(checks), 2)


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result

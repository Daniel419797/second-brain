"""Detect shallow autonomous-agent outputs that lack real proof."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

MEANINGFUL_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rs", ".dart", ".css", ".html", ".sql", ".json", ".toml", ".yaml", ".yml"}
SKIP_PARTS = {".git", "node_modules", ".next", "dist", "build", ".venv", "__pycache__", ".friday"}


def detect(result: Any, *, root: str | Path = "") -> dict[str, Any]:
    payload = result if isinstance(result, dict) else {"summary": str(result or "")}
    project_root = _project_root(payload, root)
    summary = _text(payload)
    reasons: list[str] = []
    signals: list[str] = []

    if _sounds_like_handoff(summary):
        signals.append("output asks user to install/run instead of attaching execution evidence")
    if not project_root or not project_root.exists():
        reasons.append("Project root does not exist.")
    else:
        files = _meaningful_files(project_root)
        if len(files) < 3:
            reasons.append("Not enough meaningful source files exist.")
        if not _has_manifest(project_root):
            reasons.append("No install/package manifest exists.")
        if not _has_tests(project_root):
            reasons.append("No tests are present.")
        if not _responsibility_split(project_root):
            reasons.append("Code is not split by responsibility.")
        if _frontend(project_root) and not _has_browser_or_preview(payload):
            reasons.append("No browser screenshot, preview URL, or browser gate evidence.")

    if not _has_test_evidence(payload):
        reasons.append("No build/test command evidence is attached.")
    if not _has_gate_logs(payload):
        reasons.append("No executable gate log evidence is attached.")
    if not _has_final_proof(payload, project_root):
        reasons.append("No final proof report exists.")

    shallow = bool(reasons)
    return {
        "shallow": shallow,
        "reasons": _dedupe(reasons),
        "signals": signals,
        "root": str(project_root) if project_root else "",
        "summary": "Output is shallow." if shallow else "Output has enough implementation evidence to review further.",
    }


def _project_root(payload: dict[str, Any], root: str | Path) -> Path | None:
    candidates = [
        root,
        payload.get("project_root"),
        payload.get("root"),
        (payload.get("metadata") or {}).get("project_root") if isinstance(payload.get("metadata"), dict) else "",
        (payload.get("execution") or {}).get("metadata", {}).get("project_root") if isinstance(payload.get("execution"), dict) and isinstance(payload.get("execution", {}).get("metadata"), dict) else "",
    ]
    for candidate in candidates:
        if candidate:
            return Path(candidate).expanduser().resolve()
    return None


def _text(payload: dict[str, Any]) -> str:
    fields = [payload.get("summary"), payload.get("actual_output"), payload.get("output"), payload.get("voice_summary")]
    if isinstance(payload.get("execution"), dict):
        fields.append(payload["execution"].get("summary"))
    return "\n".join(str(field or "") for field in fields)


def _sounds_like_handoff(text: str) -> bool:
    lowered = text.lower()
    return "install dependencies" in lowered or "run the readme" in lowered or "no dependency install" in lowered


def _meaningful_files(root: Path) -> list[Path]:
    files = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in MEANINGFUL_EXTENSIONS:
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        files.append(path)
        if len(files) >= 24:
            break
    return files


def _has_manifest(root: Path) -> bool:
    return any((root / name).exists() for name in ("package.json", "pyproject.toml", "go.mod", "Cargo.toml", "pubspec.yaml"))


def _has_tests(root: Path) -> bool:
    return any(part in path.parts or path.name.endswith((".test.ts", ".test.tsx", ".test.js", "_test.py")) for path in root.rglob("*") for part in ("tests", "test", "__tests__") if path.is_file())


def _responsibility_split(root: Path) -> bool:
    groups = ["src/app", "src/components", "src/services", "src/store", "src/hooks", "src/lib", "src/routes", "tests", "test", "lib"]
    return sum(1 for group in groups if (root / group).exists()) >= 3


def _frontend(root: Path) -> bool:
    return (root / "next.config.mjs").exists() or (root / "next.config.js").exists() or (root / "src/app").exists()


def _has_browser_or_preview(payload: dict[str, Any]) -> bool:
    text = _text(payload).lower()
    if "screenshot" in text or "preview" in text:
        return True
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    gates = metadata.get("product_studio_gates") or payload.get("gate_results") or {}
    if isinstance(gates, dict):
        if gates.get("preview_url"):
            return True
        for gate in gates.get("gates") or []:
            if gate.get("screenshot") or gate.get("group") in {"browser", "preview"} and gate.get("status") == "passed":
                return True
    return False


def _has_test_evidence(payload: dict[str, Any]) -> bool:
    tested = payload.get("tested")
    if isinstance(payload.get("execution"), dict):
        tested = payload["execution"].get("tested") or tested
    if isinstance(tested, list) and tested:
        return True
    return any(term in _text(payload).lower() for term in ("npm test", "pytest", "go test", "cargo test", "flutter test", "build -> passed"))


def _has_gate_logs(payload: dict[str, Any]) -> bool:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    gates = metadata.get("product_studio_gates") or payload.get("gate_results") or {}
    if isinstance(gates, dict):
        if gates.get("attempted") and gates.get("gates"):
            return True
        if gates.get("artifacts"):
            return True
    return False


def _has_final_proof(payload: dict[str, Any], root: Path | None) -> bool:
    text = _text(payload).lower()
    if "final proof" in text or "proof-report" in text:
        return True
    artifacts = payload.get("artifacts") or payload.get("changed") or []
    if isinstance(payload.get("execution"), dict):
        artifacts = [*artifacts, *(payload["execution"].get("changed") or [])]
    if any("final-proof-report" in str(item).lower() or "proof-report" in str(item).lower() for item in artifacts):
        return True
    if root:
        return any((root / relative).exists() for relative in (".friday/production/final-proof-report.md", ".friday/os/final-proof-report.md", ".friday/product-studio/proof-report.md"))
    return False


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        clean = re.sub(r"\s+", " ", str(value or "")).strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result

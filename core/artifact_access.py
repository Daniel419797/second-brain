"""Safe proof-artifact access for Friday UI viewers."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

ALLOWED_TEXT_SUFFIXES = {".log", ".txt", ".md", ".json"}
ALLOWED_BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_INLINE_BYTES = 1_500_000


class ArtifactAccessError(ValueError):
    """Raised when a requested artifact is not part of Friday proof evidence."""


def read_artifact(
    path: str,
    *,
    allowed_paths: list[str] | None = None,
    require_manifest_match: bool = False,
) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    allowed = _allowed_set(allowed_paths or [])
    if require_manifest_match and str(target) not in allowed:
        raise ArtifactAccessError("Artifact path is not in this run's manifest.")
    if not require_manifest_match and ".friday" not in target.parts and str(target) not in allowed:
        raise ArtifactAccessError("Only Friday proof artifacts can be opened here.")
    suffix = target.suffix.lower()
    if suffix not in ALLOWED_TEXT_SUFFIXES | ALLOWED_BINARY_SUFFIXES:
        raise ArtifactAccessError("Unsupported artifact type.")
    if not target.exists() or not target.is_file():
        raise FileNotFoundError("Artifact not found.")
    size = target.stat().st_size
    if size > MAX_INLINE_BYTES:
        raise OverflowError("Artifact is too large for inline viewing.")
    if suffix in ALLOWED_BINARY_SUFFIXES:
        return {"path": str(target), "size": size, "binary": True, "base64": base64.b64encode(target.read_bytes()).decode("ascii")}
    return {"path": str(target), "size": size, "binary": False, "content": target.read_text(encoding="utf-8", errors="replace")}


def collect_manifest_paths(run: dict[str, Any] | None) -> list[str]:
    if not isinstance(run, dict):
        return []
    paths: list[str] = []
    paths.extend(str(item) for item in (run.get("artifacts") or []) if str(item).strip())
    for key in ("gate_results", "product_studio", "production_run", "output"):
        value = run.get(key)
        if isinstance(value, dict):
            paths.extend(_paths_from_payload(value))
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    paths.extend(_paths_from_payload(metadata))
    return _dedupe(_expand_manifests(paths))


def _paths_from_payload(payload: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in ("artifacts", "screenshots", "logs", "changed"):
        paths.extend(str(item) for item in (payload.get(key) or []) if str(item).strip())
    gates = payload.get("gates") or payload.get("required_gate_statuses") or []
    for gate in gates if isinstance(gates, list) else []:
        if not isinstance(gate, dict):
            continue
        for key in ("log_path", "screenshot"):
            if gate.get(key):
                paths.append(str(gate[key]))
        paths.extend(str(item) for item in (gate.get("evidence") or []) if _looks_like_path(str(item)))
    for value in payload.values():
        if isinstance(value, dict):
            paths.extend(_paths_from_payload(value))
    return paths


def _expand_manifests(paths: list[str]) -> list[str]:
    expanded = list(paths)
    for item in paths:
        try:
            path = Path(item).expanduser().resolve()
        except Exception:
            continue
        if path.name != "artifact-manifest.json" or not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if isinstance(payload, dict):
            expanded.extend(_paths_from_payload(payload))
            for key in ("artifacts", "production_artifacts", "screenshots", "logs"):
                expanded.extend(str(value) for value in (payload.get(key) or []) if str(value).strip())
    return expanded


def _allowed_set(paths: list[str]) -> set[str]:
    allowed: set[str] = set()
    for item in paths:
        try:
            allowed.add(str(Path(item).expanduser().resolve()))
        except Exception:
            continue
    return allowed


def _looks_like_path(value: str) -> bool:
    text = str(value or "").strip()
    return bool(text) and not text.startswith(("http://", "https://")) and ("/" in text or "\\" in text or Path(text).suffix)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        try:
            text = str(Path(item).expanduser().resolve())
        except Exception:
            text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result

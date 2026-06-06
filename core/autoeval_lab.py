"""AutoResearch-style CPU-friendly evaluation loop for Friday projects.

Friday's AutoEval Lab uses objective project/product/design scores instead of
GPU training metrics. It snapshots constrained files, runs a candidate change,
keeps improvements, reverts regressions, and writes proof artifacts.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import command_runner, evaluation_lab, product_studio_gates, quality_taste_layer
from core.config import DATA_DIR, config_value, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "autoeval_lab.sqlite3"
FRIDAY_DIR = ".friday"
AUTOEVAL_DIR = "autoeval"
RUNS_DIR = "runs"
SNAPSHOT_DIR = "snapshots"
LOGS_DIR = "logs"
_LOCK = threading.Lock()

SKIP_DIRS = {
    ".friday",
    ".git",
    ".hg",
    ".svn",
    ".next",
    ".turbo",
    ".pytest_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "target",
    "__pycache__",
    "data",
    "friday-projects",
}
DEFAULT_SOURCE_DIRS = {
    "src",
    "app",
    "pages",
    "components",
    "lib",
    "hooks",
    "store",
    "stores",
    "types",
    "tests",
    "test",
}
ROOT_FILE_NAMES = {
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "tsconfig.json",
    "next.config.js",
    "next.config.mjs",
    "vite.config.ts",
    "pyproject.toml",
    "requirements.txt",
    "README.md",
}
SOURCE_SUFFIXES = {
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".css",
    ".scss",
    ".html",
    ".md",
    ".json",
    ".py",
    ".toml",
    ".yaml",
    ".yml",
}


def init_db(path: Path | None = None) -> None:
    ensure_runtime_dirs()
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=10) as conn:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS autoeval_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                root TEXT NOT NULL,
                request TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                baseline_score REAL NOT NULL,
                final_score REAL NOT NULL,
                improvement REAL NOT NULL,
                kept INTEGER NOT NULL,
                reverted INTEGER NOT NULL,
                summary TEXT NOT NULL,
                artifacts_json TEXT NOT NULL,
                scores_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_autoeval_root ON autoeval_runs(root, timestamp)")


def ensure_program(root: str | Path, request: str = "", *, mode: str = "product_quality") -> dict[str, Any]:
    """Create or refresh the AutoEval instruction file for a project."""

    project_root = resolve_coding_root(root)
    lab_root = _lab_root(project_root)
    lab_root.mkdir(parents=True, exist_ok=True)
    program_path = lab_root / "program.md"
    config_path = lab_root / "autoeval-config.json"
    program = _program_markdown(project_root, request, mode)
    program_path.write_text(program, encoding="utf-8")
    config = {
        "version": "friday_autoeval_v1",
        "mode": _clean(mode) or "product_quality",
        "metric": "friday_autoeval_score",
        "keep_rule": "Keep candidate changes only when final score improves by min_delta and no constrained-file violation is detected.",
        "default_min_delta": _min_delta(None),
        "no_gpu_required": True,
        "constrained_surface": sorted(DEFAULT_SOURCE_DIRS),
        "skip_dirs": sorted(SKIP_DIRS),
    }
    config_path.write_text(json.dumps(config, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "root": str(project_root),
        "program_path": str(program_path),
        "config_path": str(config_path),
        "summary": "AutoEval program and config are ready.",
    }


def score_project(
    root: str | Path,
    request: str,
    *,
    mode: str = "product_quality",
    stack: dict[str, Any] | None = None,
    run_gates: bool = False,
    install: bool = False,
    browser: bool = False,
    preview: bool = False,
    timeout: int = 180,
    create_files: bool = True,
) -> dict[str, Any]:
    """Score a project using cheap deterministic metrics and optional gates."""

    project_root = resolve_coding_root(root)
    stack = stack or _infer_stack(project_root)
    quality = quality_taste_layer.review_project(
        project_root,
        request,
        stack=stack,
        gate_results={},
        design_handoff={"ok": True, "status": "autoeval_static"},
        create_files=create_files,
    )
    structure = _structure_score(project_root)
    docs_tests = _docs_tests_score(project_root)
    interaction = _interaction_score(project_root)
    route_depth = _route_depth_score(project_root, request, stack)
    gate_results: dict[str, Any] = {}
    gate_score: float | None = None
    artifacts = list(quality.get("artifacts") or [])
    if run_gates:
        gate_results = product_studio_gates.execute_gates(
            project_root,
            stack=stack,
            install=install,
            tests=True,
            audits=True,
            browser=browser,
            preview=preview,
            timeout=timeout,
            request=request,
        )
        artifacts.extend(gate_results.get("artifacts") or [])
        gate_score = _gate_score(gate_results)
    weighted = [
        (float(quality.get("score") or 0), 0.52),
        (structure["score"], 0.18),
        (docs_tests["score"], 0.12),
        (interaction["score"], 0.10),
        (route_depth["score"], 0.08),
    ]
    if gate_score is not None:
        weighted = [(score, weight * 0.88) for score, weight in weighted]
        weighted.append((gate_score, 0.12))
    score = round(sum(score * weight for score, weight in weighted) / max(0.01, sum(weight for _, weight in weighted)), 2)
    blockers = [
        str(item.get("summary") or item.get("id") or "")
        for item in quality.get("issues") or []
        if isinstance(item, dict) and int(item.get("severity") or 0) >= 4
    ]
    if gate_results:
        blockers.extend(str(item) for item in product_studio_gates.gate_gaps(gate_results))
    report = {
        "ok": score >= 82 and not blockers,
        "score": score,
        "mode": _clean(mode) or "product_quality",
        "root": str(project_root),
        "request": _clean(request),
        "stack": stack,
        "quality_review": quality,
        "gate_results": gate_results,
        "breakdown": {
            "quality": quality.get("score"),
            "structure": structure,
            "docs_tests": docs_tests,
            "interaction": interaction,
            "route_depth": route_depth,
            "gates": gate_score,
        },
        "blockers": [item for item in blockers if item],
        "artifacts": artifacts,
        "summary": f"AutoEval score {score}/100 for {_clean(mode) or 'product_quality'}.",
    }
    if create_files:
        report["artifacts"] = [*artifacts, *_write_score_report(project_root, report)]
    return report


def run_experiment(
    root: str | Path,
    request: str,
    *,
    mode: str = "product_quality",
    target_files: list[str] | None = None,
    experiment_command: str = "",
    apply_fixes: bool = False,
    run_gates: bool = False,
    install: bool = False,
    browser: bool = False,
    preview: bool = False,
    min_delta: float | None = None,
    stack: dict[str, Any] | None = None,
    timeout: int = 180,
) -> dict[str, Any]:
    """Run one objective AutoEval experiment and keep only improvements."""

    init_db()
    project_root = resolve_coding_root(root)
    run_key = _run_key()
    program = ensure_program(project_root, request, mode=mode)
    lab_root = _lab_root(project_root)
    run_root = lab_root / RUNS_DIR / run_key
    log_root = run_root / LOGS_DIR
    run_root.mkdir(parents=True, exist_ok=True)
    log_root.mkdir(parents=True, exist_ok=True)
    stack = stack or _infer_stack(project_root)
    constrained = _collect_constrained_files(project_root, target_files)
    constrained_allowed = {_relative(path, project_root) for path in constrained}
    before_manifest = _project_manifest(project_root)
    snapshot = _snapshot(project_root, constrained, run_key)
    baseline = score_project(project_root, request, mode=mode, stack=stack, run_gates=False, create_files=True)
    mutation = _run_mutation(
        project_root,
        baseline,
        experiment_command=experiment_command,
        apply_fixes=apply_fixes,
        log_root=log_root,
        timeout=timeout,
    )
    mutation_attempted = bool(mutation.get("attempted"))
    final = (
        score_project(
            project_root,
            request,
            mode=mode,
            stack=stack,
            run_gates=run_gates,
            install=install,
            browser=browser,
            preview=preview,
            timeout=timeout,
            create_files=True,
        )
        if mutation_attempted
        else baseline
    )
    after_manifest = _project_manifest(project_root)
    violations = _constraint_violations(project_root, before_manifest, after_manifest, constrained_allowed)
    delta = round(float(final.get("score") or 0) - float(baseline.get("score") or 0), 2)
    required_delta = _min_delta(min_delta)
    kept = bool(mutation_attempted and delta >= required_delta and not violations and final.get("score", 0) >= baseline.get("score", 0))
    reverted = False
    if mutation_attempted and not kept:
        _restore_snapshot(project_root, snapshot, after_manifest)
        reverted = True
        final = score_project(project_root, request, mode=mode, stack=stack, run_gates=False, create_files=True)
        delta = round(float(final.get("score") or 0) - float(baseline.get("score") or 0), 2)
    status = "kept" if kept else "reverted" if reverted else "scored"
    summary = _run_summary(status, baseline, final, delta, violations, mutation_attempted)
    result = {
        "run_key": run_key,
        "timestamp": _now(),
        "root": str(project_root),
        "request": _clean(request),
        "mode": _clean(mode) or "product_quality",
        "status": status,
        "kept": kept,
        "reverted": reverted,
        "mutation_attempted": mutation_attempted,
        "min_delta": required_delta,
        "baseline_score": baseline.get("score"),
        "final_score": final.get("score"),
        "improvement": delta,
        "baseline": baseline,
        "final": final,
        "mutation": mutation,
        "constraint_violations": violations,
        "snapshot": snapshot,
        "program": program,
        "summary": summary,
        "artifacts": _dedupe([program["program_path"], program["config_path"], *(baseline.get("artifacts") or []), *(final.get("artifacts") or []), *(mutation.get("artifacts") or [])]),
    }
    run_artifacts = _write_run_artifacts(project_root, run_root, result)
    result["artifacts"] = _dedupe([*result["artifacts"], *run_artifacts])
    row = _record_run(result)
    result["id"] = row["id"]
    _append_history(project_root, result)
    _record_evaluation_event(result)
    return result


def history(limit: int = 20, *, root: str | Path = "") -> list[dict[str, Any]]:
    init_db()
    where = ""
    params: list[Any] = []
    if _clean(root):
        where = "WHERE root = ?"
        params.append(str(resolve_coding_root(root)))
    params.append(max(1, min(200, int(limit or 20))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM autoeval_runs {where} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_row(row) for row in rows]


def status(limit: int = 10) -> dict[str, Any]:
    runs = history(limit=limit)
    latest = runs[0] if runs else None
    return {
        "enabled": True,
        "latest": latest,
        "recent": runs,
        "summary": latest["summary"] if latest else "AutoEval Lab has not run yet.",
    }


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM autoeval_runs")


def _run_mutation(
    project_root: Path,
    baseline: dict[str, Any],
    *,
    experiment_command: str,
    apply_fixes: bool,
    log_root: Path,
    timeout: int,
) -> dict[str, Any]:
    if _clean(experiment_command):
        log_path = log_root / "experiment-command.log"
        try:
            completed = command_runner.run(
                experiment_command,
                cwd=project_root,
                timeout=timeout,
                extra_allowed=product_studio_gates.EXTRA_ALLOWED,
            )
            text = _command_log(completed.args, completed.returncode, completed.stdout, completed.stderr)
            log_path.write_text(text, encoding="utf-8", errors="ignore")
            return {
                "attempted": True,
                "kind": "command",
                "ok": completed.returncode == 0,
                "command": experiment_command,
                "returncode": completed.returncode,
                "artifacts": [str(log_path)],
                "summary": f"Experiment command exited with code {completed.returncode}.",
            }
        except Exception as exc:
            log_path.write_text(str(exc) + "\n", encoding="utf-8", errors="ignore")
            return {
                "attempted": True,
                "kind": "command",
                "ok": False,
                "command": experiment_command,
                "artifacts": [str(log_path)],
                "summary": f"Experiment command failed: {exc}",
            }
    if apply_fixes:
        fix = quality_taste_layer.apply_safe_fixes(project_root, baseline.get("quality_review") or {})
        return {
            "attempted": True,
            "kind": "deterministic_quality_fix",
            "ok": bool(fix.get("ok")),
            "fix": fix,
            "artifacts": [str(item) for item in (fix.get("changed") or [])],
            "summary": fix.get("summary") or "Deterministic quality fix attempted.",
        }
    return {"attempted": False, "kind": "score_only", "ok": True, "summary": "No candidate mutation requested; baseline was scored only.", "artifacts": []}


def _record_run(result: dict[str, Any]) -> dict[str, Any]:
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO autoeval_runs(timestamp, root, request, mode, status, baseline_score, final_score, improvement, kept, reverted, summary, artifacts_json, scores_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result["timestamp"],
                result["root"],
                result["request"],
                result["mode"],
                result["status"],
                float(result.get("baseline_score") or 0),
                float(result.get("final_score") or 0),
                float(result.get("improvement") or 0),
                1 if result.get("kept") else 0,
                1 if result.get("reverted") else 0,
                result["summary"],
                _json_dumps(result.get("artifacts") or []),
                _json_dumps({"baseline": result.get("baseline"), "final": result.get("final")}),
                _json_dumps({"run_key": result.get("run_key"), "mutation": result.get("mutation"), "constraint_violations": result.get("constraint_violations")}),
            ),
        )
        row = conn.execute("SELECT * FROM autoeval_runs WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def _record_evaluation_event(result: dict[str, Any]) -> None:
    category = "task_completed" if result.get("kept") or result.get("status") == "scored" else "agent_failure"
    severity = 1 if category == "task_completed" else 3
    try:
        evaluation_lab.record_event(
            category,
            result.get("summary") or "AutoEval run completed.",
            source="autoeval_lab",
            severity=severity,
            metric_value=float(result.get("final_score") or 0),
            metadata={"run_key": result.get("run_key"), "root": result.get("root"), "status": result.get("status")},
        )
    except Exception:
        return


def _write_score_report(project_root: Path, report: dict[str, Any]) -> list[str]:
    out_dir = _lab_root(project_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "latest-score.json"
    path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return [str(path)]


def _write_run_artifacts(project_root: Path, run_root: Path, result: dict[str, Any]) -> list[str]:
    json_path = run_root / "run.json"
    md_path = run_root / "run.md"
    json_path.write_text(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    md_path.write_text(_run_markdown(result), encoding="utf-8")
    latest_path = _lab_root(project_root) / "latest-run.json"
    latest_path.write_text(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return [str(json_path), str(md_path), str(latest_path)]


def _append_history(project_root: Path, result: dict[str, Any]) -> None:
    path = _lab_root(project_root) / "score-history.json"
    try:
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except Exception:
        existing = []
    row = {
        "id": result.get("id"),
        "run_key": result.get("run_key"),
        "timestamp": result.get("timestamp"),
        "status": result.get("status"),
        "baseline_score": result.get("baseline_score"),
        "final_score": result.get("final_score"),
        "improvement": result.get("improvement"),
        "kept": result.get("kept"),
        "summary": result.get("summary"),
    }
    existing.insert(0, row)
    path.write_text(json.dumps(existing[:200], ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _snapshot(project_root: Path, files: list[Path], run_key: str) -> dict[str, Any]:
    snap_root = _lab_root(project_root) / SNAPSHOT_DIR / run_key
    snap_root.mkdir(parents=True, exist_ok=True)
    max_bytes = int(config_value("autoeval_snapshot_max_file_bytes", 1_000_000) or 1_000_000)
    manifest: list[dict[str, Any]] = []
    for path in files:
        if not path.exists() or not path.is_file():
            continue
        relative = _relative(path, project_root)
        if path.stat().st_size > max_bytes:
            manifest.append({"relative_path": relative, "snapshotted": False, "reason": "too_large", "hash": _hash_file(path), "size": path.stat().st_size})
            continue
        target = snap_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        manifest.append({"relative_path": relative, "snapshotted": True, "hash": _hash_file(path), "size": path.stat().st_size})
    manifest_path = snap_root / "snapshot-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"root": str(snap_root), "manifest_path": str(manifest_path), "files": manifest}


def _restore_snapshot(project_root: Path, snapshot: dict[str, Any], after_manifest: dict[str, dict[str, Any]]) -> None:
    snap_root = Path(str(snapshot.get("root") or ""))
    snapshot_files = {item["relative_path"] for item in snapshot.get("files") or [] if item.get("snapshotted")}
    for item in snapshot.get("files") or []:
        if not item.get("snapshotted"):
            continue
        relative = str(item.get("relative_path") or "")
        source = snap_root / relative
        target = project_root / relative
        if source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    for relative, meta in after_manifest.items():
        if not _is_constrained_relative(relative):
            continue
        if relative in snapshot_files:
            continue
        path = project_root / relative
        if path.exists() and path.is_file():
            try:
                path.unlink()
            except Exception:
                pass


def _constraint_violations(project_root: Path, before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]], allowed: set[str]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for relative, meta in after.items():
        if relative.startswith(f"{FRIDAY_DIR}/{AUTOEVAL_DIR}/"):
            continue
        before_hash = (before.get(relative) or {}).get("hash")
        if before_hash == meta.get("hash"):
            continue
        if relative not in allowed and _is_source_relative(relative):
            violations.append({"path": str(project_root / relative), "reason": "changed outside constrained snapshot"})
    for relative in before:
        if relative not in after and relative not in allowed and _is_source_relative(relative):
            violations.append({"path": str(project_root / relative), "reason": "deleted outside constrained snapshot"})
    return violations[:20]


def _project_manifest(project_root: Path) -> dict[str, dict[str, Any]]:
    manifest: dict[str, dict[str, Any]] = {}
    max_files = int(config_value("autoeval_manifest_max_files", 2000) or 2000)
    for path in _walk_files(project_root, max_files=max_files):
        relative = _relative(path, project_root)
        manifest[relative] = {"hash": _hash_file(path), "size": path.stat().st_size}
    return manifest


def _collect_constrained_files(project_root: Path, target_files: list[str] | None) -> list[Path]:
    if target_files:
        return [_safe_project_path(project_root, item) for item in target_files]
    max_files = int(config_value("autoeval_snapshot_max_files", 400) or 400)
    return _walk_files(project_root, max_files=max_files, constrained_only=True)


def _walk_files(project_root: Path, *, max_files: int, constrained_only: bool = False) -> list[Path]:
    result: list[Path] = []
    for path in project_root.rglob("*"):
        if len(result) >= max_files:
            break
        if not path.is_file():
            continue
        relative = _relative(path, project_root)
        parts = relative.split("/")
        if any(part in SKIP_DIRS for part in parts):
            continue
        if relative.startswith(f"{FRIDAY_DIR}/{AUTOEVAL_DIR}/"):
            continue
        if path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        if constrained_only and not _is_constrained_relative(relative):
            continue
        result.append(path)
    return result


def _is_constrained_relative(relative: str) -> bool:
    parts = relative.replace("\\", "/").split("/")
    if not parts:
        return False
    return parts[0] in DEFAULT_SOURCE_DIRS or relative in ROOT_FILE_NAMES


def _is_source_relative(relative: str) -> bool:
    parts = relative.replace("\\", "/").split("/")
    if any(part in SKIP_DIRS for part in parts):
        return False
    return Path(relative).suffix.lower() in SOURCE_SUFFIXES


def _safe_project_path(project_root: Path, value: str) -> Path:
    raw = _clean(value)
    if not raw:
        raise ValueError("Target file path cannot be empty.")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"Target file is outside project root: {value}") from exc
    return resolved


def _structure_score(project_root: Path) -> dict[str, Any]:
    checks = {
        "src_app": (project_root / "src" / "app").exists(),
        "components": (project_root / "src" / "components").exists() or (project_root / "components").exists(),
        "lib": (project_root / "src" / "lib").exists() or (project_root / "lib").exists(),
        "package_scripts": _package_scripts(project_root),
        "thin_routes": _thin_routes(project_root),
    }
    score = 40
    score += 15 if checks["src_app"] else 0
    score += 15 if checks["components"] else 0
    score += 10 if checks["lib"] else 0
    score += 15 if checks["package_scripts"] else 0
    score += 10 if checks["thin_routes"] else -15
    return {"score": max(0, min(100, score)), "checks": checks}


def _docs_tests_score(project_root: Path) -> dict[str, Any]:
    tests = [path for path in _walk_files(project_root, max_files=500) if "test" in path.name.lower() or path.parent.name.lower() in {"tests", "test"}]
    docs = [path for path in project_root.glob("*.md") if path.name.lower() != "node_modules"]
    scripts = _package_scripts(project_root)
    score = 40
    score += 20 if tests else 0
    score += 20 if docs else 0
    score += 10 if scripts else 0
    score += 10 if any(name in scripts for name in ("test", "build", "lint", "typecheck")) else 0
    return {"score": max(0, min(100, score)), "test_file_count": len(tests), "doc_file_count": len(docs), "scripts": scripts}


def _interaction_score(project_root: Path) -> dict[str, Any]:
    text = _surface_text(project_root).lower()
    button_count = text.count("<button") + text.count("role=\"button") + text.count("href=")
    dead_link_count = text.count('href="#"') + text.count("href='#'") + text.count("javascript:")
    score = 82 if button_count else 68
    score -= min(50, dead_link_count * 15)
    return {"score": max(0, min(100, score)), "button_or_link_count": button_count, "dead_link_count": dead_link_count}


def _route_depth_score(project_root: Path, request: str, stack: dict[str, Any]) -> dict[str, Any]:
    request_lower = _clean(request).lower()
    routes = {
        "home": project_root / "src" / "app" / "page.tsx",
        "about": project_root / "src" / "app" / "about" / "page.tsx",
        "services": project_root / "src" / "app" / "services" / "page.tsx",
        "contact": project_root / "src" / "app" / "contact" / "page.tsx",
    }
    exists = {name: path.exists() for name, path in routes.items()}
    if "four" in request_lower or "4 page" in request_lower or "4-page" in request_lower:
        score = int(sum(1 for value in exists.values() if value) / 4 * 100)
    else:
        score = 90 if exists["home"] else 60
    return {"score": score, "routes": exists, "stack": stack}


def _gate_score(gate_results: dict[str, Any]) -> float:
    gates = [gate for gate in (gate_results.get("gates") or []) if isinstance(gate, dict) and gate.get("required")]
    if not gates:
        return 0.0
    passed = sum(1 for gate in gates if str(gate.get("status") or "").lower() == "passed")
    return round((passed / max(1, len(gates))) * 100, 2)


def _package_scripts(project_root: Path) -> dict[str, str]:
    path = project_root / "package.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}
    scripts = payload.get("scripts") if isinstance(payload, dict) else {}
    return {str(key): str(value) for key, value in scripts.items()} if isinstance(scripts, dict) else {}


def _thin_routes(project_root: Path) -> bool:
    route_files = list((project_root / "src" / "app").glob("**/page.tsx")) if (project_root / "src" / "app").exists() else []
    if not route_files:
        return True
    for path in route_files:
        try:
            line_count = len([line for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()])
        except Exception:
            continue
        if line_count > 35:
            return False
    return True


def _surface_text(project_root: Path) -> str:
    chunks: list[str] = []
    for relative in getattr(quality_taste_layer, "VISIBLE_SURFACE_CANDIDATES", ()):
        path = project_root / str(relative)
        if path.exists() and path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="ignore")[:120000])
    if not chunks:
        for path in _walk_files(project_root, max_files=120, constrained_only=True):
            chunks.append(path.read_text(encoding="utf-8", errors="ignore")[:20000])
    return "\n".join(chunks)


def _infer_stack(project_root: Path) -> dict[str, Any]:
    package = project_root / "package.json"
    if package.exists():
        text = package.read_text(encoding="utf-8", errors="ignore").lower()
        if '"next"' in text:
            return {"stack": "nextjs", "label": "Next.js web app"}
        if '"vite"' in text:
            return {"stack": "vite", "label": "Vite web app"}
    if (project_root / "pyproject.toml").exists() or (project_root / "requirements.txt").exists():
        return {"stack": "python", "label": "Python project"}
    return {"stack": "unknown", "label": "Unknown project"}


def _program_markdown(project_root: Path, request: str, mode: str) -> str:
    return "\n".join(
        [
            "# Friday AutoEval Program",
            "",
            "This project uses an AutoResearch-style loop without GPU training.",
            "",
            "## Objective",
            f"- Request: {_clean(request) or 'not provided'}",
            f"- Mode: {_clean(mode) or 'product_quality'}",
            "- Metric: `friday_autoeval_score` from deterministic quality, structure, route, interaction, docs/tests, and optional gate evidence.",
            "",
            "## Loop",
            "1. Inspect the project and constrained editable files.",
            "2. Snapshot constrained files before a candidate change.",
            "3. Score the baseline.",
            "4. Apply one candidate command or deterministic safe fix.",
            "5. Score the candidate.",
            "6. Keep only if the score improves by `min_delta` and no constrained-file violation appears.",
            "7. Revert failed candidates from snapshot.",
            "8. Write proof artifacts and score history.",
            "",
            "## Non-Negotiables",
            "- Do not claim improvement from text alone.",
            "- Do not use paid cloud/GPU work without explicit approval.",
            "- Do not mutate files outside the constrained surface for an experiment.",
            "- Prefer small, reviewable changes.",
            "- Treat screenshots, gates, tests, and quality reports as evidence.",
            "",
            f"Project root: {project_root}",
            "",
        ]
    )


def _run_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Friday AutoEval Run",
        "",
        str(result.get("summary") or ""),
        "",
        f"Status: {result.get('status')}",
        f"Baseline score: {result.get('baseline_score')}",
        f"Final score: {result.get('final_score')}",
        f"Improvement: {result.get('improvement')}",
        f"Kept: {bool(result.get('kept'))}",
        f"Reverted: {bool(result.get('reverted'))}",
        "",
        "## Mutation",
        f"- Kind: {(result.get('mutation') or {}).get('kind')}",
        f"- Summary: {(result.get('mutation') or {}).get('summary')}",
        "",
        "## Constraint Violations",
    ]
    violations = result.get("constraint_violations") if isinstance(result.get("constraint_violations"), list) else []
    if violations:
        lines.extend(f"- {item.get('path')}: {item.get('reason')}" for item in violations if isinstance(item, dict))
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def _run_summary(status: str, baseline: dict[str, Any], final: dict[str, Any], delta: float, violations: list[dict[str, Any]], mutation_attempted: bool) -> str:
    if not mutation_attempted:
        return f"AutoEval scored project at {final.get('score')}/100; no mutation was requested."
    if status == "kept":
        return f"AutoEval kept the candidate: score improved from {baseline.get('score')} to {final.get('score')} ({delta:+.2f})."
    reason = "constraint violation" if violations else "score did not improve enough"
    return f"AutoEval reverted the candidate: {reason}; baseline {baseline.get('score')}, final {final.get('score')} ({delta:+.2f})."


def _command_log(args: Any, returncode: int, stdout: str, stderr: str) -> str:
    return "\n".join(
        [
            f"args: {args}",
            f"returncode: {returncode}",
            "",
            "stdout:",
            stdout or "",
            "",
            "stderr:",
            stderr or "",
            "",
        ]
    )


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "root": str(row["root"]),
        "request": str(row["request"]),
        "mode": str(row["mode"]),
        "status": str(row["status"]),
        "baseline_score": float(row["baseline_score"]),
        "final_score": float(row["final_score"]),
        "improvement": float(row["improvement"]),
        "kept": bool(row["kept"]),
        "reverted": bool(row["reverted"]),
        "summary": str(row["summary"]),
        "artifacts": _json_loads(row["artifacts_json"], []),
        "scores": _json_loads(row["scores_json"], {}),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return path.name


def _lab_root(project_root: Path) -> Path:
    return project_root / FRIDAY_DIR / AUTOEVAL_DIR


def _run_key() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def _min_delta(value: float | None) -> float:
    if value is None:
        value = float(config_value("autoeval_min_delta", 1.0) or 1.0)
    return max(0.0, float(value))


def _dedupe(items: list[Any]) -> list[str]:
    result: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()

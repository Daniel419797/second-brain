"""Evidence-backed diagnostics for Friday.

This module is intentionally callable two ways:
- as a CLI: ``python scripts/friday_doctor.py --profile standard``
- as an import from the Doctor agent, which can pass a reporter callback.

The checks are explicit and bounded. Friday should use this instead of making
unsupported claims about "self diagnostics" or hidden system integrity checks.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "data" / "doctor_reports"
ReportFn = Callable[[str, str, int], None]

SECRET_VALUE_RE = re.compile(
    r"\b(?:sk-ant-[A-Za-z0-9_-]{8,}|sk-or-v1-[A-Za-z0-9_-]{8,}|nvapi-[A-Za-z0-9_-]{8,}|"
    r"AIza[A-Za-z0-9_-]{12,}|gsk_[A-Za-z0-9_-]{12,})\b"
)
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|authorization|cookie|credential)\s*[:=]\s*([^\s,;]+)"
)

PROFILE_CHECKS = {
    "quick": (
        "environment",
        "agent_runtime",
        "provider_readiness",
        "git_status",
        "repo_validation",
    ),
    "standard": (
        "environment",
        "agent_runtime",
        "provider_readiness",
        "git_status",
        "repo_validation",
        "smoke_tests",
        "web_build",
        "production_verify",
    ),
    "deep": (
        "environment",
        "agent_runtime",
        "provider_readiness",
        "git_status",
        "repo_validation",
        "smoke_tests",
        "web_build",
        "fast_tests",
        "production_verify",
    ),
}

DEFAULT_TIMEOUTS = {
    "version": 20.0,
    "git_status": 20.0,
    "repo_validation": 120.0,
    "smoke_tests": 150.0,
    "web_build": 240.0,
    "fast_tests": 480.0,
    "production_verify": 90.0,
}


def run_diagnostics(
    *,
    profile: str = "standard",
    root: str | Path = ROOT,
    task_id: int | None = None,
    reporter: ReportFn | None = None,
    include_web_build: bool | None = None,
    include_fast_tests: bool | None = None,
    command_timeout: float | None = None,
    write_report: bool = True,
) -> dict[str, Any]:
    """Run a diagnostic profile and return structured evidence."""

    root_path = Path(root or ROOT).expanduser().resolve()
    selected_profile = _profile(profile)
    checks_to_run = list(PROFILE_CHECKS[selected_profile])
    if include_web_build is False and "web_build" in checks_to_run:
        checks_to_run.remove("web_build")
    if include_web_build is True and "web_build" not in checks_to_run:
        checks_to_run.append("web_build")
    if include_fast_tests is True and "fast_tests" not in checks_to_run:
        checks_to_run.append("fast_tests")
    if include_fast_tests is False and "fast_tests" in checks_to_run:
        checks_to_run.remove("fast_tests")

    started_at = _now()
    started = time.perf_counter()
    decisions: list[str] = []
    checks: list[dict[str, Any]] = []

    def emit(phase: str, message: str, progress: int) -> None:
        if reporter:
            reporter(phase, message, progress)
        if task_id:
            _post_task_message(task_id, phase, message, progress)

    decision = (
        f"Doctor selected the {selected_profile} profile: "
        f"{', '.join(checks_to_run)}."
    )
    decisions.append(decision)
    emit("decision", decision, 22)

    total = max(1, len(checks_to_run))
    for index, check_name in enumerate(checks_to_run, start=1):
        progress = 22 + int((index - 1) / total * 64)
        emit("progress", f"Doctor is starting {check_name.replace('_', ' ')}.", progress)
        check = _run_named_check(
            check_name,
            root_path,
            command_timeout=command_timeout,
        )
        checks.append(check)
        emit(
            "progress",
            f"{check['name']}: {check['status']} - {check['summary']}",
            min(88, 22 + int(index / total * 64)),
        )

    overall = _overall_status(checks)
    duration_seconds = round(time.perf_counter() - started, 2)
    report: dict[str, Any] = {
        "ok": overall in {"pass", "warn"},
        "overall_status": overall,
        "profile": selected_profile,
        "root": str(root_path),
        "started_at": started_at,
        "completed_at": _now(),
        "duration_seconds": duration_seconds,
        "decisions": decisions,
        "checks": checks,
        "summary": _summary(overall, checks, duration_seconds),
        "next_step": _next_step(checks),
        "risks": _risks(checks),
    }
    report["markdown"] = render_markdown(report)
    if write_report:
        artifacts = write_report_files(report)
        report["artifacts"] = artifacts
    else:
        report["artifacts"] = []
    emit("result", report["summary"], 95)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Friday Doctor Report",
        "",
        f"- Status: {report.get('overall_status', 'unknown')}",
        f"- Profile: {report.get('profile', 'standard')}",
        f"- Root: {report.get('root', '')}",
        f"- Duration: {report.get('duration_seconds', 0)}s",
        f"- Summary: {report.get('summary', '')}",
        f"- Next step: {report.get('next_step', '')}",
        "",
        "## Checks",
    ]
    for check in report.get("checks") or []:
        lines.append(f"- {check.get('status', 'unknown').upper()} {check.get('name', '')}: {check.get('summary', '')}")
    risks = report.get("risks") or []
    if risks:
        lines.extend(["", "## Risks"])
        lines.extend(f"- {risk}" for risk in risks)
    decisions = report.get("decisions") or []
    if decisions:
        lines.extend(["", "## Doctor Decisions"])
        lines.extend(f"- {decision}" for decision in decisions)
    return "\n".join(lines).strip() + "\n"


def write_report_files(report: dict[str, Any], directory: str | Path = REPORT_DIR) -> list[str]:
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")
    base = target / f"friday-doctor-{stamp}"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    json_path.write_text(json.dumps(_without_markdown_copy(report), ensure_ascii=True, indent=2, default=str), encoding="utf-8")
    md_path.write_text(str(report.get("markdown") or render_markdown(report)), encoding="utf-8")
    return [str(json_path), str(md_path)]


def _run_named_check(name: str, root: Path, *, command_timeout: float | None) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        if name == "environment":
            check = _check_environment(root, command_timeout=command_timeout)
        elif name == "agent_runtime":
            check = _check_agent_runtime(root)
        elif name == "provider_readiness":
            check = _check_provider_readiness(root)
        elif name == "git_status":
            check = _run_command_check(
                "git_status",
                ["git", "status", "--short"],
                root,
                timeout=command_timeout or DEFAULT_TIMEOUTS["git_status"],
                pass_when=lambda result: result["returncode"] == 0,
                summary_from=lambda result: "Git working tree is clean." if not result["stdout_tail"] else f"Git working tree has {len(result['stdout_tail'].splitlines())} changed item(s).",
                warn_when=lambda result: result["returncode"] == 0 and bool(result["stdout_tail"].strip()),
            )
        elif name == "repo_validation":
            check = _run_command_check(
                "repo_validation",
                [_python_executable(root), "scripts/validate_repo.py"],
                root,
                timeout=command_timeout or DEFAULT_TIMEOUTS["repo_validation"],
            )
        elif name == "smoke_tests":
            check = _run_command_check(
                "smoke_tests",
                [_python_executable(root), "scripts/run_tests.py", "smoke"],
                root,
                timeout=command_timeout or DEFAULT_TIMEOUTS["smoke_tests"],
            )
        elif name == "web_build":
            check = _check_web_build(root, command_timeout=command_timeout)
        elif name == "fast_tests":
            check = _run_command_check(
                "fast_tests",
                [_python_executable(root), "scripts/run_tests.py", "fast"],
                root,
                timeout=command_timeout or DEFAULT_TIMEOUTS["fast_tests"],
            )
        elif name == "production_verify":
            check = _check_production_verify(root, command_timeout=command_timeout)
        else:
            check = {"name": name, "status": "skip", "summary": "Unknown check."}
    except Exception as exc:
        check = {
            "name": name,
            "status": "fail",
            "summary": f"Check crashed: {exc.__class__.__name__}: {exc}",
            "details": {"error": str(exc)},
        }
    check["duration_seconds"] = round(time.perf_counter() - started, 2)
    return check


def _check_environment(root: Path, *, command_timeout: float | None) -> dict[str, Any]:
    details: dict[str, Any] = {
        "platform": platform.platform(),
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "root_exists": root.exists(),
        "pyproject_exists": (root / "pyproject.toml").exists(),
        "package_json_exists": (root / "package.json").exists(),
    }
    version_checks = [
        ("repo_python", [_python_executable(root), "--version"]),
        ("node", ["node", "--version"]),
        ("npm", ["npm", "--version"]),
        ("pytest", [_python_executable(root), "-m", "pytest", "--version"]),
    ]
    missing: list[str] = []
    versions: dict[str, str] = {}
    for label, command in version_checks:
        binary = command[0]
        if not _command_available(binary):
            missing.append(label)
            continue
        result = _run_command(command, root, timeout=command_timeout or DEFAULT_TIMEOUTS["version"])
        versions[label] = _first_line(result["stdout_tail"] or result["stderr_tail"])
        if result["returncode"] != 0:
            missing.append(label)
    details["versions"] = versions
    if missing:
        return {
            "name": "environment",
            "status": "fail",
            "summary": f"Missing or failing runtime tools: {', '.join(missing)}.",
            "details": details,
        }
    python_label = versions.get("repo_python") or f"Python {details['python_version']}"
    return {
        "name": "environment",
        "status": "pass",
        "summary": f"{python_label}, Node {versions.get('node', 'unknown')}, npm {versions.get('npm', 'unknown')} are callable.",
        "details": details,
    }


def _check_agent_runtime(root: Path) -> dict[str, Any]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from core import agent_blackboard, agent_thought_bus, agents, background_agents, knowledge_graph, self_model, task_queue

    task_queue.init_db()
    agent_blackboard.init_db()
    agent_thought_bus.init_db()
    roster = agents.roster()
    worker_status = background_agents.worker_status()
    kg = knowledge_graph.summary()
    self_status = self_model.status(light=True)
    details = {
        "roster_count": len(roster),
        "doctor_in_roster": any(item.get("id") == "doctor" for item in roster),
        "workers": worker_status,
        "task_counts": task_queue.counts(),
        "knowledge_graph": kg,
        "self_model_summary": self_status.get("summary", ""),
    }
    if not details["doctor_in_roster"]:
        return {
            "name": "agent_runtime",
            "status": "fail",
            "summary": "Doctor agent is not registered in the active roster.",
            "details": details,
        }
    return {
        "name": "agent_runtime",
        "status": "pass",
        "summary": f"{len(roster)} agent role(s) registered; Doctor is available; {kg.get('summary', 'knowledge graph readable')}",
        "details": details,
    }


def _check_provider_readiness(root: Path) -> dict[str, Any]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from core import provider_readiness

    payload = provider_readiness.status(probe=False, root=root)
    missing = payload.get("missing") or []
    return {
        "name": "provider_readiness",
        "status": "pass" if payload.get("ok") else "warn",
        "summary": payload.get("summary") or ("Provider readiness complete." if not missing else "Some providers need setup."),
        "details": payload,
    }


def _check_web_build(root: Path, *, command_timeout: float | None) -> dict[str, Any]:
    if not (root / "package.json").exists():
        return {"name": "web_build", "status": "skip", "summary": "No package.json found at repo root."}
    return _run_command_check(
        "web_build",
        ["npm", "run", "web:build"],
        root,
        timeout=command_timeout or DEFAULT_TIMEOUTS["web_build"],
    )


def _check_production_verify(root: Path, *, command_timeout: float | None) -> dict[str, Any]:
    if not os.getenv("FRIDAY_PRODUCTION_URL", "").strip():
        return {
            "name": "production_verify",
            "status": "skip",
            "summary": "FRIDAY_PRODUCTION_URL is not set, so deployed API verification was skipped.",
        }
    if not os.getenv("JARVIS_API_PASSWORD", "").strip():
        return {
            "name": "production_verify",
            "status": "skip",
            "summary": "JARVIS_API_PASSWORD is not set in this shell, so deployed API verification was skipped.",
        }
    return _run_command_check(
        "production_verify",
        [_python_executable(root), "scripts/verify_production.py"],
        root,
        timeout=command_timeout or DEFAULT_TIMEOUTS["production_verify"],
    )


def _run_command_check(
    name: str,
    command: list[str],
    root: Path,
    *,
    timeout: float,
    pass_when: Callable[[dict[str, Any]], bool] | None = None,
    warn_when: Callable[[dict[str, Any]], bool] | None = None,
    summary_from: Callable[[dict[str, Any]], str] | None = None,
) -> dict[str, Any]:
    if not _command_available(command[0]):
        return {
            "name": name,
            "status": "skip",
            "summary": f"{command[0]} is not available on PATH or at the configured path.",
            "command": _display_command(command),
        }
    result = _run_command(command, root, timeout=timeout)
    ok = pass_when(result) if pass_when else result["returncode"] == 0
    status = "pass" if ok else "fail"
    if ok and warn_when and warn_when(result):
        status = "warn"
    summary = summary_from(result) if summary_from else _command_summary(name, result, ok)
    return {
        "name": name,
        "status": status,
        "summary": summary,
        "command": _display_command(command),
        "details": result,
    }


def _run_command(command: list[str], root: Path, *, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            _resolved_command(command),
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(1.0, float(timeout)),
            check=False,
        )
        return {
            "returncode": int(completed.returncode),
            "duration_seconds": round(time.perf_counter() - started, 2),
            "stdout_tail": _bounded_redacted(completed.stdout),
            "stderr_tail": _bounded_redacted(completed.stderr),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": 124,
            "duration_seconds": round(time.perf_counter() - started, 2),
            "stdout_tail": _bounded_redacted(exc.stdout or ""),
            "stderr_tail": _bounded_redacted(exc.stderr or f"Timed out after {timeout}s."),
            "timed_out": True,
        }
    except FileNotFoundError as exc:
        return {
            "returncode": 127,
            "duration_seconds": round(time.perf_counter() - started, 2),
            "stdout_tail": "",
            "stderr_tail": str(exc),
            "timed_out": False,
        }


def _command_summary(name: str, result: dict[str, Any], ok: bool) -> str:
    if ok:
        line = _first_line(result.get("stdout_tail") or result.get("stderr_tail"))
        if "passed" in str(result.get("stdout_tail", "")).lower():
            return line or f"{name} passed."
        return f"{name} passed." if not line else line[:240]
    if result.get("timed_out"):
        return f"{name} timed out after {result.get('duration_seconds')}s."
    line = _first_line(result.get("stderr_tail") or result.get("stdout_tail"))
    return f"{name} failed with exit code {result.get('returncode')}: {line}"[:500]


def _post_task_message(task_id: int, phase: str, message: str, progress: int) -> None:
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from core import task_queue

        prefix = "Doctor decision" if phase == "decision" else "Doctor result" if phase == "result" else "Progress"
        task_queue.post_message(int(task_id), "doctor", f"{prefix} {max(0, min(99, int(progress)))}%: {message}")
    except Exception:
        return


def _overall_status(checks: list[dict[str, Any]]) -> str:
    statuses = {str(check.get("status") or "") for check in checks}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses or "skip" in statuses:
        return "warn"
    return "pass"


def _summary(overall: str, checks: list[dict[str, Any]], duration_seconds: float) -> str:
    counts = _status_counts(checks)
    return (
        f"Summary: Friday Doctor finished in {duration_seconds}s with status {overall}. "
        f"Checks: {counts.get('pass', 0)} passed, {counts.get('warn', 0)} warned, "
        f"{counts.get('fail', 0)} failed, {counts.get('skip', 0)} skipped. "
        f"Next step: {_next_step(checks)} Risks: {'; '.join(_risks(checks)[:3]) or 'No major diagnostic risks found.'}"
    )


def _next_step(checks: list[dict[str, Any]]) -> str:
    for check in checks:
        if check.get("status") == "fail":
            return f"Fix or review {check.get('name')} first."
    for check in checks:
        if check.get("status") == "warn":
            return f"Review {check.get('name')} warning."
    for check in checks:
        if check.get("status") == "skip":
            return f"Provide missing configuration for {check.get('name')} if that surface matters."
    return "No immediate action required."


def _risks(checks: list[dict[str, Any]]) -> list[str]:
    risks: list[str] = []
    for check in checks:
        status = str(check.get("status") or "")
        if status in {"fail", "warn"}:
            risks.append(f"{check.get('name')}: {check.get('summary')}")
    return risks[:12]


def _status_counts(checks: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
    for check in checks:
        status = str(check.get("status") or "skip")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _profile(value: str) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {"all": "deep", "full": "deep", "normal": "standard", "default": "standard", "health": "quick"}
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in PROFILE_CHECKS else "standard"


def _python_executable(root: Path) -> str:
    venv = root / ".venv" / "Scripts" / "python.exe"
    if venv.exists():
        return str(venv)
    return sys.executable


def _command_available(command: str) -> bool:
    if not command:
        return False
    path = Path(command)
    if path.exists():
        return True
    return shutil.which(command) is not None


def _resolved_command(command: list[str]) -> list[str]:
    if not command:
        return command
    first = str(command[0])
    if Path(first).exists():
        return command
    resolved = shutil.which(first)
    if not resolved:
        return command
    return [resolved, *command[1:]]


def _display_command(command: list[str]) -> str:
    return " ".join(str(part) for part in command)


def _first_line(value: Any) -> str:
    for line in str(value or "").splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned
    return ""


def _bounded_redacted(value: Any, *, max_chars: int = 6000) -> str:
    text = str(value or "")
    text = SECRET_VALUE_RE.sub("[redacted-secret]", text)
    text = SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=[redacted]", text)
    if len(text) <= max_chars:
        return text.strip()
    return text[-max_chars:].strip()


def _without_markdown_copy(report: dict[str, Any]) -> dict[str, Any]:
    payload = dict(report)
    payload.pop("markdown", None)
    return payload


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run evidence-backed Friday diagnostics.")
    parser.add_argument("--profile", choices=sorted(PROFILE_CHECKS), default="standard")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    parser.add_argument("--no-web-build", action="store_true", help="Skip npm web build even when profile includes it.")
    parser.add_argument("--include-fast-tests", action="store_true", help="Include fast pytest profile.")
    parser.add_argument("--timeout", type=float, default=0.0, help="Override every command timeout in seconds.")
    parser.add_argument("--no-write-report", action="store_true", help="Do not write report artifacts under data/doctor_reports.")
    args = parser.parse_args(argv)

    report = run_diagnostics(
        profile=args.profile,
        root=args.root,
        include_web_build=False if args.no_web_build else None,
        include_fast_tests=True if args.include_fast_tests else None,
        command_timeout=args.timeout or None,
        write_report=not args.no_write_report,
    )
    if args.json:
        print(json.dumps(_without_markdown_copy(report), ensure_ascii=True, indent=2, default=str))
    else:
        print(report["markdown"])
        if report.get("artifacts"):
            print("Artifacts:")
            for path in report["artifacts"]:
                print(f"- {path}")
    return 0 if report.get("overall_status") in {"pass", "warn"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

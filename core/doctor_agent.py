"""Doctor agent execution for Friday diagnostics."""

from __future__ import annotations

import re
from typing import Any

from core import agent_blackboard, agent_thought_bus, notification_center, task_queue
from core.config import ROOT_DIR, config_value
from scripts import friday_doctor


def run_task(task: dict[str, Any]) -> dict[str, Any]:
    task_id = int(task.get("id") or 0)
    profile = _profile_from_task(task)
    root = _root_from_task(task)
    title = str(task.get("title") or "Run diagnostics")
    _record_decision(
        task_id,
        f"Doctor accepted diagnostic task '{title}' using profile {profile}.",
        {"profile": profile, "root": str(root), "title": title},
        progress=24,
    )

    report = friday_doctor.run_diagnostics(
        profile=profile,
        root=root,
        task_id=task_id or None,
        reporter=lambda phase, message, progress: _record_phase(task_id, phase, message, progress),
        command_timeout=_command_timeout(),
        write_report=True,
    )
    summary = str(report.get("summary") or "Summary: Doctor diagnostics completed. Next step: review the report. Risks: no summary was produced.")
    _record_completion(task_id, report)
    return {
        "agent_id": "doctor",
        "agent_name": "Doctor",
        "summary": summary,
        "mode": "diagnostic_runner",
        "capability": {
            "execution": "diagnostics",
            "can_write_files": True,
            "artifacts": report.get("artifacts") or [],
            "summary": "Doctor runs explicit diagnostic commands and writes evidence-backed reports.",
        },
        "diagnostic_status": report.get("overall_status"),
        "diagnostic_profile": profile,
        "diagnostic_report": _compact_report(report),
        "artifacts": report.get("artifacts") or [],
        "topics": ["diagnostics", "system_health", "agent_runtime"],
        "researched": False,
        "spawned_subtasks": [],
        "structured_feedback": {},
    }


def _record_phase(task_id: int, phase: str, message: str, progress: int) -> None:
    if task_id <= 0:
        return
    normalized = str(phase or "progress").lower()
    content = str(message or "").strip()
    if not content:
        return
    if normalized == "decision":
        _record_decision(task_id, content, {"phase": normalized}, progress=progress)
        return
    item_type = "evidence" if normalized == "result" else "progress"
    status = "resolved" if normalized == "result" else "active"
    try:
        agent_blackboard.post_item(
            "doctor",
            item_type,
            f"Diagnostic {normalized}",
            content,
            task_id=task_id,
            confidence=0.8 if normalized == "result" else 0.62,
            status=status,
            metadata={"progress": progress, "phase": normalized},
        )
    except Exception:
        pass
    try:
        agent_thought_bus.post_thought(
            "doctor",
            "result_summary" if normalized == "result" else "context",
            content[:500],
            {"phase": normalized, "progress": progress, "message": content},
            task_id=task_id,
            confidence=0.72,
            priority=2,
            visibility="debug",
            metadata={"source": "doctor_agent"},
        )
    except Exception:
        pass


def _record_decision(task_id: int, summary: str, content: dict[str, Any], *, progress: int = 25) -> None:
    if task_id <= 0:
        return
    try:
        task_queue.post_message(task_id, "doctor", f"Doctor decision {progress}%: {summary}")
    except Exception:
        pass
    try:
        agent_blackboard.post_item(
            "doctor",
            "decision",
            "Diagnostic routing decision",
            summary,
            task_id=task_id,
            confidence=0.82,
            status="resolved",
            metadata=content | {"progress": progress},
        )
    except Exception:
        pass
    try:
        agent_thought_bus.post_thought(
            "doctor",
            "decision",
            summary,
            content,
            task_id=task_id,
            confidence=0.84,
            priority=2,
            visibility="debug",
            metadata={"source": "doctor_agent"},
        )
    except Exception:
        pass


def _record_completion(task_id: int, report: dict[str, Any]) -> None:
    status = str(report.get("overall_status") or "unknown")
    summary = str(report.get("summary") or "Doctor diagnostics completed.")
    artifacts = [str(path) for path in report.get("artifacts") or []]
    message = _notification_message(report)
    if task_id > 0:
        try:
            task_queue.post_message(task_id, "doctor", f"Doctor result 98%: {summary}")
        except Exception:
            pass
    try:
        notification_center.add(
            source="doctor",
            category="diagnostics",
            severity=3 if status in {"warn", "fail"} else 2,
            title=f"Diagnostics complete: {status}",
            message=message,
            dedupe_key=f"doctor:task:{task_id}" if task_id > 0 else "",
            metadata={"task_id": task_id, "status": status, "artifacts": artifacts},
        )
    except Exception:
        pass
    try:
        agent_blackboard.post_item(
            "doctor",
            "evidence",
            f"Diagnostics complete: {status}",
            message,
            task_id=task_id if task_id > 0 else None,
            confidence=0.9,
            status="resolved",
            metadata={"artifacts": artifacts, "status": status},
        )
    except Exception:
        pass
    try:
        agent_thought_bus.post_thought(
            "doctor",
            "result_summary",
            f"Doctor diagnostics completed with status {status}.",
            {
                "summary": summary,
                "status": status,
                "failed": [check for check in report.get("checks") or [] if check.get("status") == "fail"],
                "warnings": [check for check in report.get("checks") or [] if check.get("status") == "warn"],
                "artifacts": artifacts,
            },
            task_id=task_id if task_id > 0 else None,
            confidence=0.9,
            priority=1 if status == "fail" else 2,
            visibility="surface",
            metadata={"source": "doctor_agent"},
        )
    except Exception:
        pass


def _notification_message(report: dict[str, Any]) -> str:
    lines = [str(report.get("summary") or "Doctor diagnostics completed.")]
    failed = [check for check in report.get("checks") or [] if check.get("status") == "fail"]
    warnings = [check for check in report.get("checks") or [] if check.get("status") == "warn"]
    skipped = [check for check in report.get("checks") or [] if check.get("status") == "skip"]
    if failed:
        lines.append("Failed: " + "; ".join(f"{item.get('name')}: {item.get('summary')}" for item in failed[:3]))
    if warnings:
        lines.append("Warnings: " + "; ".join(f"{item.get('name')}: {item.get('summary')}" for item in warnings[:3]))
    if skipped:
        lines.append("Skipped: " + "; ".join(str(item.get("name")) for item in skipped[:4]))
    artifacts = [str(path) for path in report.get("artifacts") or []]
    if artifacts:
        lines.append("Artifacts: " + "; ".join(artifacts[:2]))
    return " ".join(lines)[:1900]


def _compact_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "overall_status": report.get("overall_status"),
        "profile": report.get("profile"),
        "root": report.get("root"),
        "started_at": report.get("started_at"),
        "completed_at": report.get("completed_at"),
        "duration_seconds": report.get("duration_seconds"),
        "summary": report.get("summary"),
        "next_step": report.get("next_step"),
        "risks": report.get("risks") or [],
        "artifacts": report.get("artifacts") or [],
        "checks": [
            {
                "name": check.get("name"),
                "status": check.get("status"),
                "summary": check.get("summary"),
                "duration_seconds": check.get("duration_seconds"),
            }
            for check in report.get("checks") or []
        ],
    }


def _profile_from_task(task: dict[str, Any]) -> str:
    input_data = task.get("input") if isinstance(task.get("input"), dict) else {}
    raw = str(input_data.get("diagnostic_profile") or input_data.get("profile") or "")
    text = f"{raw} {task.get('title') or ''} {task.get('description') or ''}".lower()
    if re.search(r"\b(deep|full|all|everything|complete)\b", text):
        return "deep"
    if re.search(r"\b(quick|fast|light)\b", text):
        return "quick"
    return "standard"


def _root_from_task(task: dict[str, Any]) -> str:
    input_data = task.get("input") if isinstance(task.get("input"), dict) else {}
    root = str(input_data.get("root") or "").strip()
    return root or str(ROOT_DIR)


def _command_timeout() -> float | None:
    value = config_value("doctor_command_timeout_seconds", 0)
    try:
        timeout = float(value or 0)
    except Exception:
        return None
    return timeout if timeout > 0 else None

"""Tool wrapper for guarded Friday self-updates."""

from __future__ import annotations

from typing import Any

from core import self_update


def execute(inputs: dict[str, Any]) -> str:
    action = str(inputs.get("action") or "propose").strip().lower()
    try:
        if action == "propose":
            return _propose(inputs)
        if action == "list":
            return _list(inputs)
        if action == "get":
            return _get(inputs)
        if action == "approve":
            return _approve(inputs)
        if action == "cancel":
            return _cancel(inputs)
        if action == "stage_change":
            return _stage_change(inputs)
        if action == "apply":
            return _apply(inputs)
        if action == "brain":
            return self_update.explain_brain()
    except PermissionError as exc:
        return str(exc)
    except ValueError as exc:
        return str(exc)
    except Exception as exc:
        return f"Self-update failed: {exc}"
    return "Unknown self-update action."


def _propose(inputs: dict[str, Any]) -> str:
    request = str(inputs.get("request") or inputs.get("target") or "").strip()
    if not request:
        return "Tell me what you want Friday to improve in its codebase."
    update = self_update.create_proposal(request)
    files = ", ".join(update.get("plan", {}).get("candidate_files", [])[:4])
    return (
        f"Self-update {update['id']} proposed with {update['risk_level']} risk. "
        f"Likely files: {files or 'to be inspected'}. "
        f"To approve planning, say: {update['approval_phrase']}."
    )


def _list(inputs: dict[str, Any]) -> str:
    updates = self_update.list_updates(limit=_int(inputs.get("limit"), 8))
    if not updates:
        return "No self-updates found."
    return "\n".join(_format_update(update) for update in updates)


def _get(inputs: dict[str, Any]) -> str:
    update_id = _update_id(inputs)
    if update_id is None:
        return "Tell me which self-update ID."
    update = self_update.get_update(update_id)
    if not update:
        return f"Self-update {update_id} not found."
    changes = update.get("changes", [])
    pending = sum(1 for change in changes if change.get("status") == "staged")
    return (
        f"{_format_update(update)} "
        f"Staged changes: {pending}. "
        f"Next approval: I authorize applying self update {update_id}."
    )


def _approve(inputs: dict[str, Any]) -> str:
    update_id = _update_id(inputs)
    if update_id is None:
        return "Tell me which self-update ID to approve."
    update = self_update.approve_update(update_id, str(inputs.get("confirmation") or inputs.get("target") or ""))
    return f"Self-update {update_id} approved and queued as task {update.get('task_id')}."


def _cancel(inputs: dict[str, Any]) -> str:
    update_id = _update_id(inputs)
    if update_id is None:
        return "Tell me which self-update ID to cancel."
    update = self_update.cancel_update(update_id)
    return f"Self-update {update_id} is {update['status']}."


def _stage_change(inputs: dict[str, Any]) -> str:
    update_id = _update_id(inputs)
    if update_id is None:
        return "Tell me which self-update ID to stage changes for."
    change = self_update.stage_change(
        update_id,
        str(inputs.get("path") or inputs.get("file_path") or ""),
        str(inputs.get("find_text") or inputs.get("find") or ""),
        str(inputs.get("replace_text") or inputs.get("replace") or ""),
        str(inputs.get("summary") or ""),
    )
    return f"Staged change {change['id']} for self-update {update_id}: {change['path']}."


def _apply(inputs: dict[str, Any]) -> str:
    update_id = _update_id(inputs)
    if update_id is None:
        return "Tell me which self-update ID to apply."
    update = self_update.apply_update(
        update_id,
        str(inputs.get("confirmation") or inputs.get("target") or ""),
        run_tests=inputs.get("run_tests"),
    )
    result = update.get("result") or {}
    tests = result.get("tests") or {}
    if update["status"] == "applied":
        test_note = " Tests passed." if tests and not tests.get("skipped") else " Tests skipped."
        return f"Self-update {update_id} applied.{test_note}"
    if result.get("rolled_back"):
        return f"Self-update {update_id} failed tests and was rolled back."
    return f"Self-update {update_id} is {update['status']}."


def _format_update(update: dict[str, Any]) -> str:
    task = f" task {update['task_id']}" if update.get("task_id") else ""
    return f"#{update['id']} [{update['status']}] {update['risk_level']} risk{task}: {update['request']}"


def _update_id(inputs: dict[str, Any]) -> int | None:
    raw = inputs.get("update_id") or inputs.get("id") or inputs.get("target") or ""
    try:
        return int(raw)
    except (TypeError, ValueError):
        import re

        match = re.search(r"\d+", str(raw))
        return int(match.group(0)) if match else None


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

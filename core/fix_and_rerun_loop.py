"""Small helper facade for Friday OS fix-and-rerun workflows."""

from __future__ import annotations

from typing import Any

from core import friday_memory, friday_operating_system


def rerun_failed_gates(run_id: int) -> dict[str, Any]:
    result = friday_operating_system.rerun_gates(run_id, failed_only=True)
    friday_memory.remember(
        "failure_memory",
        f"Fix and rerun requested for run #{run_id}",
        result.get("summary") or "Friday reran failed gates.",
        tags=["fix_loop", "rerun_failed_gates"],
        metadata={"run_id": run_id, "status": result.get("status"), "gaps": result.get("gaps")},
    )
    return result


def rerun_all_gates(run_id: int) -> dict[str, Any]:
    result = friday_operating_system.rerun_gates(run_id, failed_only=False)
    friday_memory.remember(
        "verification_history",
        f"Full gate rerun requested for run #{run_id}",
        result.get("summary") or "Friday reran all gates.",
        tags=["fix_loop", "rerun_all_gates"],
        metadata={"run_id": run_id, "status": result.get("status"), "gaps": result.get("gaps")},
    )
    return result

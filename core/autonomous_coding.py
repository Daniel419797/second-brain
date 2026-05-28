"""Guarded autonomous coding mode built on task contracts and self-update."""

from __future__ import annotations

from typing import Any

from core import codebase_standards, task_contracts, task_queue
from core.config import resolve_coding_root


def start(request: str, *, root: str = "", risk_level: str = "medium") -> dict[str, Any]:
    """Create a safe coding task with an explicit contract.

    Friday does not directly patch files here. The task contract requires an
    expected output, tests, explanation, approval, and rollback/backup plan
    before any code is applied by the existing self-update or coding workflows.
    """

    project_root = resolve_coding_root(root)
    standards = codebase_standards.scan(project_root, max_files=120)
    title = f"Autonomous coding: {str(request or '').strip()[:120] or 'project improvement'}"
    task_id = task_queue.create_task(
        title,
        description="Guarded autonomous coding request.",
        agent_id="senior_developer",
        priority=3,
        input_data={
            "source": "autonomous_coding",
            "request": request,
            "root": str(project_root),
            "risk_level": risk_level,
            "quality_priorities": ["security", "speed_performance", "maintainability", "reliability", "portability"],
            "standards": standards,
            "required_flow": ["inspect", "standards_preflight", "plan", "propose_change_set", "run_tests", "explain", "wait_for_approval", "apply_or_rollback"],
        },
    )
    task = task_queue.get_task(task_id) or {"id": task_id, "title": title, "input": {}}
    contract = task_contracts.ensure_contract(task)
    return {
        "ok": True,
        "task": task,
        "contract": contract,
        "summary": f"Autonomous coding task #{task_id} created with a verification contract.",
    }

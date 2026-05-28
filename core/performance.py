"""Lightweight local performance checks for v2 API/dashboard requirements."""

from __future__ import annotations

import time
from typing import Any, Callable

from core import background_agents, task_queue
from core.config import config_value


def benchmark_api_core() -> dict[str, Any]:
    checks: list[tuple[str, Callable[[], Any]]] = [
        ("worker_status", background_agents.worker_status),
        ("task_list", lambda: task_queue.list_tasks(limit=20)),
        ("task_counts", task_queue.counts),
    ]
    results: list[dict[str, Any]] = []
    threshold = float(config_value("api_response_target_ms", 500))
    for name, func in checks:
        start = time.perf_counter()
        try:
            func()
            ok = True
            error = ""
        except Exception as exc:
            ok = False
            error = str(exc)
        duration_ms = round((time.perf_counter() - start) * 1000, 3)
        results.append({"name": name, "duration_ms": duration_ms, "ok": ok and duration_ms <= threshold, "error": error})
    return {
        "target_ms": threshold,
        "checks": results,
        "ok": all(item["ok"] for item in results),
    }

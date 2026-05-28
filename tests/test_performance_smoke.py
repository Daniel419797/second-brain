from __future__ import annotations

import subprocess
import sys
import time

import pytest

from core.config import config_value


@pytest.mark.smoke
def test_api_server_import_within_budget():
    budget = float(config_value("performance_budget_api_import_seconds", 8.0))
    elapsed = _timed_import("api.server")

    assert elapsed < budget


@pytest.mark.smoke
def test_orchestrator_import_within_budget():
    budget = float(config_value("performance_budget_orchestrator_import_seconds", 6.0))
    elapsed = _timed_import("core.orchestrator")

    assert elapsed < budget


def _timed_import(module: str) -> float:
    started = time.perf_counter()
    completed = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    elapsed = time.perf_counter() - started
    assert completed.returncode == 0, completed.stderr[-1000:]
    return elapsed

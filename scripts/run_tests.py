"""Run Friday test profiles with consistent commands."""

from __future__ import annotations

import argparse
import subprocess
import sys


SLOW_FILES = [
    "tests/test_advanced_friday_powers.py",
    "tests/test_agent_governance_reliability_layer.py",
    "tests/test_api_server.py",
    "tests/test_autonomy_brain_expansion.py",
    "tests/test_autonomy_expansion.py",
    "tests/test_awake_friday_capabilities.py",
    "tests/test_companion_growth_capabilities.py",
    "tests/test_companion_intelligence.py",
    "tests/test_cognition_modules.py",
    "tests/test_desktop_vision.py",
    "tests/test_executive_capabilities.py",
    "tests/test_jarvis.py",
    "tests/test_orchestrator.py",
    "tests/test_pc_control.py",
    "tests/test_preference_coach_trust_layer.py",
    "tests/test_self_model.py",
    "tests/test_stt.py",
    "tests/test_voice.py",
]

FAST_IGNORES = [f"--ignore={path}" for path in SLOW_FILES]

PROFILES = {
    "smoke": [
        "tests/test_performance_smoke.py",
        "tests/test_api_router_smoke.py",
        "tests/test_provider_readiness.py",
        "-q",
        "--maxfail=1",
        "--durations=20",
    ],
    "fast": [*FAST_IGNORES, "-m", "not slow", "-q", "--maxfail=5", "--durations=25"],
    "integration": ["-m", "integration", "-q", "--maxfail=5", "--durations=25"],
    "slow": ["-m", "slow", "-q", "--maxfail=5", "--durations=25"],
    "full": ["-q", "--durations=40"],
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Friday pytest profiles.")
    parser.add_argument("profile", choices=sorted(PROFILES), nargs="?", default="fast")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = [sys.executable, "-m", "pytest", *PROFILES[args.profile], *args.pytest_args]
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())

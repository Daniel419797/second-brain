from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items):
    slow_files = {
        "test_advanced_friday_powers.py",
        "test_agent_governance_reliability_layer.py",
        "test_api_server.py",
        "test_autonomy_brain_expansion.py",
        "test_autonomy_expansion.py",
        "test_awake_friday_capabilities.py",
        "test_companion_growth_capabilities.py",
        "test_companion_intelligence.py",
        "test_cognition_modules.py",
        "test_desktop_vision.py",
        "test_executive_capabilities.py",
        "test_jarvis.py",
        "test_orchestrator.py",
        "test_pc_control.py",
        "test_preference_coach_trust_layer.py",
        "test_self_model.py",
        "test_stt.py",
        "test_voice.py",
    }
    for item in items:
        path = str(item.path).replace("\\", "/")
        filename = path.rsplit("/", 1)[-1]
        if filename in slow_files:
            item.add_marker(pytest.mark.slow)
        if filename == "test_api_server.py" or "test_companion" in path or "test_autonomy" in path:
            item.add_marker(pytest.mark.integration)

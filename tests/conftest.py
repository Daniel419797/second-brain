from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        path = str(item.path).replace("\\", "/")
        if path.endswith("test_api_server.py") or "test_companion" in path or "test_autonomy" in path:
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.slow)

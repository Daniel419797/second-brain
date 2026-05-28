from __future__ import annotations

import pytest

from core import provider_readiness

pytestmark = pytest.mark.smoke


def test_production_readiness_reports_missing_required_env(monkeypatch):
    for key in ["FRIDAY_PRODUCTION_URL", "DATABASE_URL", "JARVIS_API_PASSWORD", "JARVIS_API_SECRET"]:
        monkeypatch.delenv(key, raising=False)

    result = provider_readiness.production_readiness()

    assert result["ok"] is False
    assert {item["name"] for item in result["checks"] if not item["ok"]} >= {
        "https",
        "database_url",
        "api_password",
        "api_jwt_secret",
    }


def test_provider_readiness_status_is_safe_and_actionable(monkeypatch):
    monkeypatch.setattr(provider_readiness, "github_status", lambda root="": {"github_authenticated": False})
    monkeypatch.setattr(provider_readiness, "production_readiness", lambda: {"ok": False, "checks": []})

    result = provider_readiness.status(probe=False)

    assert "providers" in result
    assert "search" in result["providers"]
    assert "image_generation" in result["providers"]
    assert "text_to_3d" in result["providers"]
    assert "model_3d" in result["providers"]
    assert "missing" in result

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import server
from core import api_auth, provider_readiness

pytestmark = pytest.mark.smoke


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("JARVIS_API_PASSWORD", "super-secret")
    monkeypatch.delenv("JARVIS_API_SECRET", raising=False)
    monkeypatch.setattr(api_auth, "SECRET_PATH", tmp_path / "api_secret.txt")
    return TestClient(server.create_app())


def _headers(client: TestClient) -> dict[str, str]:
    token = client.post("/auth/login", json={"username": "friday", "password": "super-secret"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_extracted_media_and_ops_routes(monkeypatch, tmp_path):
    monkeypatch.setattr(server.search_broker, "status", lambda: {"configured": [], "provider_chain": []})
    monkeypatch.setattr(server.image_generation, "status", lambda: {"ready": False, "provider": "auto"})
    monkeypatch.setattr(server.text_to_3d, "status", lambda: {"enabled": True, "configured": {}})
    monkeypatch.setattr(provider_readiness, "status", lambda probe=False: {"ok": False, "probe": probe})
    monkeypatch.setattr(provider_readiness, "production_readiness", lambda: {"ok": False, "checks": []})
    monkeypatch.setattr(provider_readiness, "github_status", lambda root="": {"github_authenticated": False})

    client = _client(monkeypatch, tmp_path)
    headers = _headers(client)

    assert client.get("/search/status", headers=headers).status_code == 200
    assert client.get("/images/status", headers=headers).json()["provider"] == "auto"
    assert client.get("/text-to-3d/status", headers=headers).status_code == 200
    assert client.get("/providers/readiness", headers=headers).json()["ok"] is False
    assert client.get("/production/readiness", headers=headers).json()["ok"] is False
    assert client.get("/github/status", headers=headers).json()["github_authenticated"] is False


def test_cors_origins_can_come_from_environment(monkeypatch):
    monkeypatch.setenv("FRIDAY_API_CORS_ORIGINS", "https://friday-web.example.com, http://localhost:3000")

    origins = server._cors_origins()

    assert "https://friday-web.example.com" in origins
    assert "http://localhost:3000" in origins

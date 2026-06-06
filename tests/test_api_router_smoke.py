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


def test_design_critique_endpoint_calls_provider_loop(monkeypatch, tmp_path):
    monkeypatch.setattr(
        server.design_providers,
        "run_design_critique_loop",
        lambda request, **kwargs: {
            "ok": False,
            "status": "planned",
            "summary": "Design critique planned.",
            "request": request,
            "kwargs": kwargs,
        },
    )
    monkeypatch.setattr(server.design_providers, "status", lambda probe=False, root="": {"ok": True, "probe": probe, "root": root})
    client = _client(monkeypatch, tmp_path)
    headers = _headers(client)

    status = client.get("/design/providers/status?probe=true", headers=headers)
    critique = client.post(
        "/design/critique/run",
        headers=headers,
        json={
            "request": "Design a university operations dashboard",
            "root": str(tmp_path),
            "product_name": "University Operations Command Center",
            "variant_count": 3,
            "dry_run": True,
        },
    )

    assert status.json()["probe"] is True
    assert critique.status_code == 200
    assert critique.json()["status"] == "planned"
    assert critique.json()["kwargs"]["variant_count"] == 3


def test_stitch_debug_endpoint_calls_provider_debug(monkeypatch, tmp_path):
    monkeypatch.setattr(server.design_providers, "stitch_debug", lambda root="", limit=12: {"ok": True, "root": root, "limit": limit, "summary": "debug loaded"})
    client = _client(monkeypatch, tmp_path)
    headers = _headers(client)

    response = client.get("/design/stitch/debug", params={"root": str(tmp_path), "limit": 5}, headers=headers)

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["limit"] == 5


def test_design_pipeline_endpoint_calls_pipeline(monkeypatch, tmp_path):
    monkeypatch.setattr(
        server.design_pipeline,
        "run",
        lambda request, **kwargs: {
            "ok": True,
            "status": "planned",
            "summary": "Design pipeline planned.",
            "request": request,
            "kwargs": kwargs,
        },
    )
    monkeypatch.setattr(server.design_pipeline, "pipeline_contract", lambda: {"version": "design_pipeline_v1", "stages": []})
    client = _client(monkeypatch, tmp_path)
    headers = _headers(client)

    contract = client.get("/design/pipeline/contract", headers=headers)
    response = client.post(
        "/design/pipeline/run",
        headers=headers,
        json={
            "request": "Design a Nexus Forge landing page",
            "root": str(tmp_path),
            "product_name": "Nexus Forge",
            "variant_count": 3,
            "dry_run": True,
            "apply_to_source": False,
            "run_browser": False,
        },
    )

    assert contract.json()["version"] == "design_pipeline_v1"
    assert response.status_code == 200
    assert response.json()["status"] == "planned"
    assert response.json()["kwargs"]["apply_to_source"] is False


def test_cors_origins_can_come_from_environment(monkeypatch):
    monkeypatch.setenv("FRIDAY_API_CORS_ORIGINS", "https://friday-web.example.com, http://localhost:3000")

    origins = server._cors_origins()

    assert "https://friday-web.example.com" in origins
    assert "http://localhost:3000" in origins

import pytest

from core import api_auth


def test_api_auth_login_and_token_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_API_PASSWORD", "super-secret")
    monkeypatch.delenv("JARVIS_API_SECRET", raising=False)
    monkeypatch.setattr(api_auth, "SECRET_PATH", tmp_path / "api_secret.txt")
    monkeypatch.setattr(
        api_auth,
        "config_value",
        lambda key, default=None: {
            "api_username": "friday",
            "api_password_env": "JARVIS_API_PASSWORD",
            "api_jwt_secret_env": "JARVIS_API_SECRET",
            "api_jwt_exp_hours": 24,
        }.get(key, default),
    )

    assert api_auth.authenticate("friday", "super-secret") is True
    token = api_auth.create_token("friday")
    payload = api_auth.decode_token(token)

    assert payload["sub"] == "friday"
    assert payload["type"] == "access"


def test_api_auth_rejects_missing_password(monkeypatch):
    monkeypatch.setenv("JARVIS_API_PASSWORD", "your_api_password_here")
    monkeypatch.setattr(
        api_auth,
        "config_value",
        lambda key, default=None: {
            "api_username": "friday",
            "api_password_env": "JARVIS_API_PASSWORD",
        }.get(key, default),
    )

    assert api_auth.authenticate("friday", "your_api_password_here") is False


def test_api_auth_wrong_token_type(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_API_PASSWORD", "super-secret")
    monkeypatch.setattr(api_auth, "SECRET_PATH", tmp_path / "api_secret.txt")
    monkeypatch.setattr(api_auth, "config_value", lambda key, default=None: 24 if key == "api_jwt_exp_hours" else default)
    token = api_auth.create_token("friday", token_type="refresh")

    with pytest.raises(api_auth.AuthError):
        api_auth.decode_token(token, token_type="access")

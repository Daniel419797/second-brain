"""JWT authentication helpers for Friday's local v2 API."""

from __future__ import annotations

import datetime as dt
import hmac
import os
import secrets
from pathlib import Path
from typing import Any

try:
    import jwt
except Exception:  # pragma: no cover - dependency is pinned, but keep imports soft
    jwt = None

from core.config import DATA_DIR, config_value, ensure_runtime_dirs

SECRET_PATH = DATA_DIR / "api_secret.txt"


class AuthError(RuntimeError):
    """Raised when API authentication cannot proceed."""


def authenticate(username: str, password: str) -> bool:
    expected_user = str(os.getenv("JARVIS_API_USERNAME") or config_value("api_username", "friday") or "friday")
    expected_password = os.getenv(str(config_value("api_password_env", "JARVIS_API_PASSWORD")), "")
    if _is_placeholder(expected_password):
        return False
    return hmac.compare_digest(str(username), expected_user) and hmac.compare_digest(str(password), expected_password)


def create_token(subject: str, *, token_type: str = "access", hours: float | None = None) -> str:
    if jwt is None:
        raise AuthError("PyJWT is not installed.")
    now = _now()
    if hours is None:
        hours = float(config_value("api_jwt_exp_hours", 24 if token_type == "access" else 24 * 7))
    payload = {
        "sub": str(subject),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(hours=float(hours))).timestamp()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def decode_token(token: str, *, token_type: str = "access") -> dict[str, Any]:
    if jwt is None:
        raise AuthError("PyJWT is not installed.")
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except Exception as exc:
        raise AuthError("Invalid or expired token.") from exc
    if payload.get("type") != token_type:
        raise AuthError("Wrong token type.")
    return payload


def token_expiry(hours: float | None = None) -> str:
    if hours is None:
        hours = float(config_value("api_jwt_exp_hours", 24))
    return (_now() + dt.timedelta(hours=float(hours))).isoformat(timespec="seconds")


def _jwt_secret() -> str:
    env_key = str(config_value("api_jwt_secret_env", "JARVIS_API_SECRET"))
    env_value = os.getenv(env_key, "")
    if not _is_placeholder(env_value):
        return env_value
    ensure_runtime_dirs()
    if SECRET_PATH.exists():
        secret = SECRET_PATH.read_text(encoding="utf-8").strip()
        if secret:
            return secret
    secret = secrets.token_urlsafe(48)
    SECRET_PATH.write_text(secret, encoding="utf-8")
    return secret


def _is_placeholder(value: str | None) -> bool:
    if not value:
        return True
    normalized = value.strip().lower()
    return normalized in {
        "your_api_password_here",
        "your_api_secret_here",
        "password",
        "changeme",
        "change_me",
        "placeholder",
    }


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).astimezone()

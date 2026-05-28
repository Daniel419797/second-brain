"""Verify a deployed Friday API without exposing secrets."""

from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urlencode, urljoin, urlparse, urlunparse

import requests
import websocket


CHECK_ENDPOINTS = [
    "/health",
    "/dashboard/snapshot",
    "/providers/readiness",
    "/production/readiness",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a deployed Friday API.")
    parser.add_argument("--url", default=os.getenv("FRIDAY_PRODUCTION_URL", ""), help="Base deployed API URL.")
    parser.add_argument("--username", default=os.getenv("JARVIS_API_USERNAME", "friday"))
    parser.add_argument("--password-env", default="JARVIS_API_PASSWORD")
    parser.add_argument("--allow-http", action="store_true", help="Allow non-HTTPS URLs for local staging only.")
    args = parser.parse_args()

    base_url = _base_url(args.url)
    if not base_url:
        print("FRIDAY_PRODUCTION_URL or --url is required.")
        return 2
    if not args.allow_http and not base_url.startswith("https://"):
        print("Production verification requires HTTPS. Use --allow-http only for local staging.")
        return 2
    password = os.getenv(args.password_env, "")
    if not password or password.lower().startswith("your_"):
        print(f"{args.password_env} must be set to the deployed API password.")
        return 2

    session = requests.Session()
    failures: list[str] = []
    try:
        token = _login(session, base_url, args.username, password)
    except Exception as exc:
        print(f"login failed: {exc}")
        return 1

    headers = {"Authorization": f"Bearer {token}"}
    for endpoint in CHECK_ENDPOINTS:
        ok, detail = _check_http(session, base_url, endpoint, headers)
        print(f"{'ok' if ok else 'fail'} {endpoint}: {detail}")
        if not ok:
            failures.append(endpoint)

    ok, detail = _check_tasks_websocket(base_url, token)
    print(f"{'ok' if ok else 'fail'} /ws/tasks: {detail}")
    if not ok:
        failures.append("/ws/tasks")

    if failures:
        print("Production verification failed: " + ", ".join(failures))
        return 1
    print("Production verification passed.")
    return 0


def _login(session: requests.Session, base_url: str, username: str, password: str) -> str:
    response = session.post(
        urljoin(base_url, "/auth/login"),
        json={"username": username, "password": password},
        timeout=20,
    )
    response.raise_for_status()
    token = str(response.json().get("access_token") or "")
    if not token:
        raise RuntimeError("login response did not include an access token")
    return token


def _check_http(session: requests.Session, base_url: str, endpoint: str, headers: dict[str, str]) -> tuple[bool, str]:
    try:
        response = session.get(urljoin(base_url, endpoint), headers=headers, timeout=30)
    except Exception as exc:
        return False, str(exc)
    if response.status_code >= 400:
        return False, f"HTTP {response.status_code}"
    try:
        payload = response.json()
    except Exception:
        return False, "response is not JSON"
    if isinstance(payload, dict) and payload.get("ok") is False and endpoint in {"/production/readiness", "/providers/readiness"}:
        return False, str(payload.get("summary") or "readiness check returned ok=false")
    return True, "ready"


def _check_tasks_websocket(base_url: str, token: str) -> tuple[bool, str]:
    ws_url = _ws_url(base_url, "/ws/tasks", {"token": token})
    try:
        connection = websocket.create_connection(ws_url, timeout=15)
        connection.settimeout(15)
        try:
            message = connection.recv()
        finally:
            connection.close()
    except Exception as exc:
        return False, str(exc)
    return (True, "received task stream payload") if message else (False, "no payload received")


def _base_url(value: str) -> str:
    text = str(value or "").strip().rstrip("/")
    if not text:
        return ""
    if not text.startswith(("http://", "https://")):
        text = "https://" + text
    return text


def _ws_url(base_url: str, path: str, query: dict[str, str]) -> str:
    parsed = urlparse(urljoin(base_url, path))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, parsed.path, "", urlencode(query), ""))


if __name__ == "__main__":
    raise SystemExit(main())

"""Google Workspace OAuth integrations for Gmail, Calendar, Docs, and Sheets."""

from __future__ import annotations

import datetime as dt
import json
import os
import secrets
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, config_value, ensure_runtime_dirs

TOKEN_PATH = DATA_DIR / "google_oauth_token.json"
STATE_PATH = DATA_DIR / "google_oauth_state.json"

DEFAULT_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
]


def status() -> dict[str, Any]:
    deps = _dependency_status()
    configured = _configured()
    authorized = bool(configured and deps["installed"] and _credentials(silent=True))
    return {
        "enabled": bool(config_value("google_oauth_enabled", True)),
        "configured": configured,
        "authorized": authorized,
        "dependencies": deps,
        "scopes": _scopes(),
        "redirect_uri": _redirect_uri(),
        "token_present": TOKEN_PATH.exists(),
        "client_id_env": _client_id_env(),
        "client_secret_env": _client_secret_env(),
        "mode": "oauth" if authorized else "not_connected",
    }


def start_auth() -> dict[str, Any]:
    _require_enabled()
    _require_configured()
    _allow_local_http_oauth()
    Flow, _, _ = _google_imports()
    flow = Flow.from_client_config(_client_config(), scopes=_scopes(), redirect_uri=_redirect_uri())
    state = secrets.token_urlsafe(24)
    auth_url, returned_state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    _write_json(STATE_PATH, {"state": returned_state or state, "created_at": _now()})
    return {"auth_url": auth_url, "state": returned_state or state, "redirect_uri": _redirect_uri()}


def finish_auth(code: str, state: str = "") -> dict[str, Any]:
    _require_enabled()
    _require_configured()
    _allow_local_http_oauth()
    expected = _read_json(STATE_PATH).get("state", "")
    if expected and state and secrets.compare_digest(str(expected), str(state)) is False:
        raise PermissionError("Google OAuth state did not match. Please restart the connection flow.")
    Flow, _, _ = _google_imports()
    flow = Flow.from_client_config(_client_config(), scopes=_scopes(), redirect_uri=_redirect_uri())
    flow.fetch_token(code=str(code or ""))
    credentials = flow.credentials
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(credentials.to_json(), encoding="utf-8")
    try:
        STATE_PATH.unlink(missing_ok=True)
    except TypeError:  # pragma: no cover - older Python fallback
        if STATE_PATH.exists():
            STATE_PATH.unlink()
    return {"authorized": True, "status": status()}


def disconnect() -> dict[str, Any]:
    for path in (TOKEN_PATH, STATE_PATH):
        try:
            path.unlink(missing_ok=True)
        except TypeError:  # pragma: no cover - older Python fallback
            if path.exists():
                path.unlink()
    return status()


def profile() -> dict[str, Any]:
    service = _service("gmail", "v1")
    return service.users().getProfile(userId="me").execute()


def recent_gmail_messages(limit: int = 10) -> list[dict[str, Any]]:
    service = _service("gmail", "v1")
    limit = max(1, min(25, int(limit)))
    listing = service.users().messages().list(userId="me", maxResults=limit).execute()
    messages = []
    for item in listing.get("messages", [])[:limit]:
        detail = service.users().messages().get(userId="me", id=item["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"]).execute()
        headers = {entry.get("name", "").lower(): entry.get("value", "") for entry in detail.get("payload", {}).get("headers", [])}
        messages.append(
            {
                "id": detail.get("id", ""),
                "thread_id": detail.get("threadId", ""),
                "from": headers.get("from", ""),
                "subject": headers.get("subject", "(no subject)"),
                "date": headers.get("date", ""),
                "snippet": detail.get("snippet", ""),
            }
        )
    return messages


def list_calendar_events(limit: int = 10) -> list[dict[str, Any]]:
    service = _service("calendar", "v3")
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    result = (
        service.events()
        .list(calendarId="primary", timeMin=now, maxResults=max(1, min(50, int(limit))), singleEvents=True, orderBy="startTime")
        .execute()
    )
    return [_calendar_event(item) for item in result.get("items", [])]


def create_calendar_event(title: str, *, start_at: str = "", end_at: str = "", location: str = "", notes: str = "") -> dict[str, Any]:
    service = _service("calendar", "v3")
    start = _event_time(start_at, minutes_from_now=15)
    end = _event_time(end_at, minutes_from_now=75)
    body = {
        "summary": _clean(title) or "Friday event",
        "location": _clean(location),
        "description": _clean(notes),
        "start": {"dateTime": start, "timeZone": _timezone()},
        "end": {"dateTime": end, "timeZone": _timezone()},
    }
    result = service.events().insert(calendarId="primary", body=body).execute()
    return _calendar_event(result)


def create_document(title: str, *, body: str = "") -> dict[str, Any]:
    service = _service("docs", "v1")
    doc = service.documents().create(body={"title": _clean(title) or "Friday document"}).execute()
    document_id = doc.get("documentId", "")
    content = str(body or "").strip()
    if content and document_id:
        service.documents().batchUpdate(
            documentId=document_id,
            body={"requests": [{"insertText": {"location": {"index": 1}, "text": content + "\n"}}]},
        ).execute()
    return {
        "id": document_id,
        "title": doc.get("title", _clean(title)),
        "url": f"https://docs.google.com/document/d/{document_id}/edit" if document_id else "",
        "kind": "google_doc",
    }


def create_sheet(title: str, *, headers: list[str] | None = None) -> dict[str, Any]:
    service = _service("sheets", "v4")
    sheet = service.spreadsheets().create(body={"properties": {"title": _clean(title) or "Friday sheet"}}).execute()
    spreadsheet_id = sheet.get("spreadsheetId", "")
    columns = [str(item).strip() for item in (headers or []) if str(item).strip()]
    if columns and spreadsheet_id:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="A1",
            valueInputOption="RAW",
            body={"values": [columns]},
        ).execute()
    return {
        "id": spreadsheet_id,
        "title": sheet.get("properties", {}).get("title", _clean(title)),
        "url": sheet.get("spreadsheetUrl") or (f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit" if spreadsheet_id else ""),
        "kind": "google_sheet",
    }


def _service(name: str, version: str) -> Any:
    _, _, build = _google_imports()
    credentials = _credentials()
    return build(name, version, credentials=credentials, cache_discovery=False)


def _credentials(*, silent: bool = False) -> Any:
    try:
        _, Credentials, _ = _google_imports()
        if not TOKEN_PATH.exists():
            if silent:
                return None
            raise PermissionError("Google Workspace is not connected. Use the dashboard Google Connect button first.")
        credentials = Credentials.from_authorized_user_file(str(TOKEN_PATH), _scopes())
        if credentials and credentials.expired and credentials.refresh_token:
            from google.auth.transport.requests import Request

            credentials.refresh(Request())
            TOKEN_PATH.write_text(credentials.to_json(), encoding="utf-8")
        return credentials
    except Exception:
        if silent:
            return None
        raise


def _dependency_status() -> dict[str, Any]:
    try:
        _google_imports()
        return {"installed": True, "missing": []}
    except Exception as exc:
        return {
            "installed": False,
            "missing": ["google-auth", "google-auth-oauthlib", "google-api-python-client"],
            "detail": str(exc),
        }


def _google_imports() -> tuple[Any, Any, Any]:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build

    return Flow, Credentials, build


def _require_enabled() -> None:
    if not bool(config_value("google_oauth_enabled", True)):
        raise RuntimeError("Google OAuth integrations are disabled in config.json.")


def _require_configured() -> None:
    if not _configured():
        raise RuntimeError(f"Missing {_client_id_env()} or {_client_secret_env()} in .env.")


def _configured() -> bool:
    return bool(_env(_client_id_env()) and _env(_client_secret_env()))


def _client_config() -> dict[str, Any]:
    return {
        "web": {
            "client_id": _env(_client_id_env()),
            "client_secret": _env(_client_secret_env()),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [_redirect_uri()],
        }
    }


def _scopes() -> list[str]:
    configured = config_value("google_oauth_scopes", DEFAULT_SCOPES)
    if isinstance(configured, str):
        return [part.strip() for part in configured.split(",") if part.strip()]
    if isinstance(configured, list):
        return [str(part).strip() for part in configured if str(part).strip()]
    return list(DEFAULT_SCOPES)


def _event_time(value: str, *, minutes_from_now: int) -> str:
    cleaned = _clean(value)
    if cleaned:
        try:
            parsed = dt.datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
            return parsed.isoformat()
        except Exception:
            pass
    return (dt.datetime.now().astimezone() + dt.timedelta(minutes=minutes_from_now)).isoformat(timespec="seconds")


def _calendar_event(item: dict[str, Any]) -> dict[str, Any]:
    start = item.get("start", {})
    end = item.get("end", {})
    return {
        "id": item.get("id", ""),
        "title": item.get("summary", "(untitled)"),
        "start_at": start.get("dateTime") or start.get("date") or "",
        "end_at": end.get("dateTime") or end.get("date") or "",
        "location": item.get("location", ""),
        "notes": item.get("description", ""),
        "url": item.get("htmlLink", ""),
        "kind": "google_calendar_event",
    }


def _redirect_uri() -> str:
    return str(config_value("google_oauth_redirect_uri", "http://127.0.0.1:8000/oauth/google/callback"))


def _allow_local_http_oauth() -> None:
    redirect = _redirect_uri().lower()
    if redirect.startswith("http://127.0.0.1") or redirect.startswith("http://localhost"):
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")


def _timezone() -> str:
    return str(config_value("google_oauth_timezone", "Africa/Lagos"))


def _client_id_env() -> str:
    return str(config_value("google_oauth_client_id_env", "GOOGLE_CLIENT_ID"))


def _client_secret_env() -> str:
    return str(config_value("google_oauth_client_secret_env", "GOOGLE_CLIENT_SECRET"))


def _env(name: str) -> str:
    value = os.getenv(name, "")
    if value.strip().lower() in {"", "your-key-here", "placeholder", "none", "null"}:
        return ""
    return value.strip()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_runtime_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _clean(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

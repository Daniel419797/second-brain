"""OAuth-backed calendar/email assistant helpers with safe draft-only behavior."""

from __future__ import annotations

import datetime as dt
from typing import Any

from core import app_integrations, google_workspace, personal_crm


def daily_brief(limit: int = 8) -> dict[str, Any]:
    google = google_workspace.status()
    gmail = _safe(lambda: google_workspace.recent_gmail_messages(limit=limit), [])
    gcal = _safe(lambda: google_workspace.list_calendar_events(limit=limit), [])
    local_events = _safe(lambda: app_integrations.list_calendar_events(limit=limit), [])
    reminders = _safe(lambda: app_integrations.list_reminders(limit=limit), [])
    followups = _safe(lambda: personal_crm.upcoming_followups(limit=limit), [])
    return {
        "google": google,
        "gmail": gmail,
        "calendar": gcal,
        "local_events": local_events,
        "reminders": reminders,
        "followups": followups,
        "summary": _brief_summary(google, gmail, gcal, reminders, followups),
        "policy": "Friday may draft replies and plan your day, but must ask before sending email or messages.",
    }


def status() -> dict[str, Any]:
    google = google_workspace.status()
    followups = followup_review(limit=4)
    connected = bool(google.get("connected") or google.get("authenticated"))
    return {
        "google": google,
        "followups": followups.get("items", []),
        "summary": ("Google OAuth connected. " if connected else "Google OAuth not connected. ") + followups.get("summary", ""),
    }


def draft_reply(to: str = "", subject: str = "", context: str = "", intent: str = "") -> dict[str, Any]:
    recipient = _clean(to) or "the recipient"
    goal = _clean(intent) or "reply clearly and politely"
    body = "\n".join(
        line
        for line in [
            f"Hi {recipient},",
            "",
            _draft_sentence(goal, context),
            "",
            "Best,",
        ]
        if line is not None
    )
    return {
        "to": _clean(to),
        "subject": _clean(subject) or "Re:",
        "body": body,
        "requires_approval": True,
        "summary": "Draft prepared. Friday will not send it without explicit approval.",
    }


def followup_review(limit: int = 10) -> dict[str, Any]:
    crm = _safe(lambda: personal_crm.upcoming_followups(limit=limit), [])
    reminders = [item for item in _safe(lambda: app_integrations.list_reminders(limit=limit), []) if not item.get("done")]
    items = []
    for item in crm:
        items.append({"source": "crm", "title": item.get("person_name") or item.get("name"), "summary": item.get("summary") or item.get("promise") or ""})
    for item in reminders:
        items.append({"source": "reminder", "title": item.get("title"), "summary": item.get("notes") or item.get("due_at") or ""})
    return {"items": items[:limit], "summary": f"{len(items[:limit])} follow-up item(s) need attention." if items else "No follow-ups found."}


def _brief_summary(google: dict[str, Any], gmail: list[dict[str, Any]], calendar: list[dict[str, Any]], reminders: list[dict[str, Any]], followups: list[dict[str, Any]]) -> str:
    connected = bool(google.get("connected") or google.get("authenticated"))
    prefix = "Google OAuth connected." if connected else "Google OAuth is not connected yet."
    return f"{prefix} {len(calendar)} calendar item(s), {len(gmail)} recent email(s), {len(reminders)} reminder(s), {len(followups)} follow-up(s)."


def _draft_sentence(intent: str, context: str) -> str:
    if context:
        return f"Thanks for the context. {intent[:1].upper() + intent[1:]}."
    return f"{intent[:1].upper() + intent[1:]}."


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def today() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().date().isoformat()

"""Deep local app integrations: office links, contacts, reminders, and workspace index."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core import app_integrations, google_workspace


def execute(inputs: dict[str, Any]) -> str:
    action = str(inputs.get("action") or "").strip().lower()
    permission_reply = _permission_reply(inputs)
    if permission_reply:
        return permission_reply
    try:
        if action == "open_app":
            return _open_app(inputs)
        if action == "google_status":
            status = google_workspace.status()
            if status.get("authorized"):
                return "Google Workspace OAuth is connected."
            if status.get("configured"):
                return "Google Workspace OAuth is configured but not connected. Use the dashboard Connect Google button."
            return f"Google Workspace OAuth is not configured. Add {status.get('client_id_env')} and {status.get('client_secret_env')} to .env."
        if action == "list_gmail_messages":
            return _format_gmail(google_workspace.recent_gmail_messages(limit=_limit(inputs)))
        if action == "create_contact":
            contact = app_integrations.create_contact(
                str(inputs.get("name") or inputs.get("target") or ""),
                email=str(inputs.get("email") or ""),
                phone=str(inputs.get("phone") or ""),
                notes=str(inputs.get("notes") or ""),
            )
            return f"Contact saved: #{contact['id']} {contact['name']}."
        if action == "search_contacts":
            return _format_items("contacts", app_integrations.search_contacts(str(inputs.get("query") or inputs.get("target") or ""), limit=_limit(inputs)))
        if action == "create_reminder":
            reminder = app_integrations.create_reminder(
                str(inputs.get("title") or inputs.get("target") or ""),
                due_at=str(inputs.get("due_at") or inputs.get("when") or ""),
                notes=str(inputs.get("notes") or ""),
            )
            due = f" due {reminder['due_at']}" if reminder.get("due_at") else ""
            return f"Reminder saved: #{reminder['id']} {reminder['title']}{due}."
        if action == "list_reminders":
            return _format_items("reminders", app_integrations.list_reminders(include_done=bool(inputs.get("include_done")), limit=_limit(inputs)))
        if action == "complete_reminder":
            reminder = app_integrations.complete_reminder(_int(inputs.get("reminder_id") or inputs.get("target")))
            return f"Reminder #{reminder['id']} completed." if reminder else "Reminder not found."
        if action == "create_calendar_event":
            if _prefer_google():
                event = google_workspace.create_calendar_event(
                    str(inputs.get("title") or inputs.get("target") or ""),
                    start_at=str(inputs.get("start_at") or inputs.get("when") or ""),
                    end_at=str(inputs.get("end_at") or ""),
                    location=str(inputs.get("location") or ""),
                    notes=str(inputs.get("notes") or ""),
                )
                start = f" at {event['start_at']}" if event.get("start_at") else ""
                return f"Google Calendar event created: {event['title']}{start}."
            event = app_integrations.create_calendar_event(
                str(inputs.get("title") or inputs.get("target") or ""),
                start_at=str(inputs.get("start_at") or inputs.get("when") or ""),
                end_at=str(inputs.get("end_at") or ""),
                location=str(inputs.get("location") or ""),
                notes=str(inputs.get("notes") or ""),
            )
            start = f" at {event['start_at']}" if event.get("start_at") else ""
            return f"Calendar event saved: #{event['id']} {event['title']}{start}."
        if action == "list_calendar_events":
            if _prefer_google():
                return _format_items("Google calendar events", google_workspace.list_calendar_events(limit=_limit(inputs)))
            return _format_items("calendar events", app_integrations.list_calendar_events(limit=_limit(inputs)))
        if action == "create_doc":
            if _prefer_google():
                doc = google_workspace.create_document(str(inputs.get("title") or inputs.get("target") or ""), body=str(inputs.get("body") or ""))
                return f"Google Doc created: {doc.get('url') or doc.get('id')}."
            doc = app_integrations.create_document(str(inputs.get("title") or inputs.get("target") or ""), body=str(inputs.get("body") or ""))
            return f"Document created: {doc['path']}."
        if action == "create_sheet":
            headers = inputs.get("headers")
            if isinstance(headers, str):
                headers = [part.strip() for part in headers.split(",") if part.strip()]
            if _prefer_google():
                sheet = google_workspace.create_sheet(str(inputs.get("title") or inputs.get("target") or ""), headers=headers if isinstance(headers, list) else None)
                return f"Google Sheet created: {sheet.get('url') or sheet.get('id')}."
            sheet = app_integrations.create_sheet(str(inputs.get("title") or inputs.get("target") or ""), headers=headers if isinstance(headers, list) else None)
            return f"Sheet created: {sheet['path']}."
        if action == "index_workspace":
            result = app_integrations.index_workspace(str(inputs.get("root") or inputs.get("target") or ""), max_files=_max_files(inputs))
            return f"Workspace indexed: {result['indexed']} files under {result['root']}."
        if action == "search_workspace":
            results = app_integrations.search_workspace(str(inputs.get("query") or inputs.get("target") or ""), limit=_limit(inputs))
            return _format_workspace_results(results)
        if action == "workspace_overview":
            return _format_workspace_overview(app_integrations.workspace_overview(str(inputs.get("root") or inputs.get("target") or "")))
    except ValueError as exc:
        return str(exc)
    except Exception as exc:
        return f"Integration action failed: {exc}"
    return "Unknown integration action."


def _permission_reply(inputs: dict[str, Any]) -> str:
    try:
        from core import permissions

        decision = permissions.evaluate("app_integrations", inputs)
        if decision["blocked"]:
            return f"Permission blocked: {decision['label']} is set to block."
        if decision["requires_confirmation"] and not inputs.get("_permission_confirmed"):
            return f"Permission required: {decision['label']} is set to ask first."
    except Exception:
        return ""
    return ""


def _open_app(inputs: dict[str, Any]) -> str:
    name = str(inputs.get("name") or inputs.get("target") or "").strip()
    link = app_integrations.app_link(name)
    if not link:
        return f"I do not have a deep link for {name}."
    try:
        from tools import pc_control

        return pc_control.execute({"action": "open_path", "target": link})
    except Exception as exc:
        return f"Could not open {name}: {exc}"


def _format_items(label: str, items: list[dict[str, Any]]) -> str:
    if not items:
        return f"No {label} found."
    lines = []
    for item in items[:10]:
        title = item.get("name") or item.get("title") or item.get("path") or f"#{item.get('id')}"
        extras = []
        for key in ("email", "phone", "due_at", "start_at", "status"):
            if item.get(key):
                extras.append(f"{key}={item[key]}")
        suffix = " | " + ", ".join(extras) if extras else ""
        lines.append(f"#{item.get('id', '-')}: {title}{suffix}")
    return "\n".join(lines)


def _format_gmail(items: list[dict[str, Any]]) -> str:
    if not items:
        return "No Gmail messages found."
    lines = []
    for item in items[:10]:
        sender = str(item.get("from") or "").split("<")[0].strip()
        subject = item.get("subject") or "(no subject)"
        lines.append(f"{sender}: {subject}")
    return "\n".join(lines)


def _format_workspace_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "No indexed workspace files matched."
    lines = []
    for item in results[:10]:
        summary = str(item.get("summary") or "").strip()
        if summary:
            summary = " - " + summary[:180]
        lines.append(f"{item.get('path')}{summary}")
    return "\n".join(lines)


def _format_workspace_overview(overview: dict[str, Any]) -> str:
    extensions = ", ".join(f"{ext}:{count}" for ext, count in list((overview.get("extensions") or {}).items())[:8])
    recent = ", ".join(str(Path(item.get("path", "")).name) for item in (overview.get("recent_files") or [])[:5])
    return (
        f"Workspace overview: {overview.get('total_files', 0)} indexed files under {overview.get('root')}. "
        f"Top types: {extensions or 'none'}. Recent: {recent or 'none'}."
    )


def _limit(inputs: dict[str, Any]) -> int:
    return max(1, min(50, _int(inputs.get("limit"), 10)))


def _max_files(inputs: dict[str, Any]) -> int | None:
    raw = inputs.get("max_files")
    return _int(raw, 0) or None


def _prefer_google() -> bool:
    try:
        status = google_workspace.status()
        return bool(status.get("authorized"))
    except Exception:
        return False


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def to_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=True, indent=2)

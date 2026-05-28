"""Gmail SMTP email sending tool with confirmation and daily limit."""

from __future__ import annotations

import datetime as _dt
import os
import smtplib
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from core.config import LOG_DIR, config_value, ensure_runtime_dirs
from input.speech_to_text import record_and_transcribe
from output.voice import speak

EMAIL_LOG = LOG_DIR / "email_log.txt"
YES_WORDS = ["yes", "send", "confirm", "do it", "go ahead"]
NO_WORDS = ["no", "cancel", "stop", "abort", "wait"]


def execute(inputs: dict[str, Any]) -> str:
    permission_reply = _permission_reply(inputs)
    if permission_reply:
        return permission_reply
    sender = os.getenv("GMAIL_ADDRESS")
    password = os.getenv("GMAIL_APP_PASSWORD")
    if not sender or not password:
        return "Email not configured."
    to = str(inputs.get("to", "")).strip()
    subject = str(inputs.get("subject", "")).strip()
    body = str(inputs.get("body", "")).strip()
    if not all([to, subject, body]):
        return "Missing recipient, subject, or body."
    limit = int(config_value("daily_email_limit", 20))
    if _daily_count() >= limit:
        return f"Daily email limit of {limit} reached. Not sent."
    speak(f"Ready to send to {to}. Subject: {subject}. Shall I send it?")
    if not _await_confirmation():
        return "Email cancelled."
    return _send(to, subject, body, sender=sender, password=password)


def _permission_reply(inputs: dict[str, Any]) -> str:
    try:
        from core import permissions

        decision = permissions.evaluate("send_email", {"action": "send_email"} | dict(inputs or {}))
        if decision["blocked"]:
            return f"Permission blocked: {decision['label']} is set to block."
    except Exception:
        return ""
    return ""


def _await_confirmation() -> bool:
    for attempt in range(2):
        response = (record_and_transcribe() or "").lower()
        if any(word in response for word in YES_WORDS):
            return True
        if any(word in response for word in NO_WORDS):
            return False
        if attempt == 0:
            speak("I did not catch that. Please say yes to send or no to cancel.")
    speak("Unclear response. Email cancelled for safety.")
    return False


def _send(to: str, subject: str, body: str, sender: str | None = None, password: str | None = None) -> str:
    sender = sender or os.getenv("GMAIL_ADDRESS")
    password = password or os.getenv("GMAIL_APP_PASSWORD")
    if not sender or not password:
        return "Email not configured."
    message = MIMEMultipart()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain"))
    try:
        socket.setdefaulttimeout(10)
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(sender, password)
            smtp.sendmail(sender, [to], message.as_string())
        _log_send(to, subject)
        return f"Email sent to {to}."
    except (smtplib.SMTPException, OSError):
        return "Email configuration error. Please check Gmail SMTP settings."


def _daily_count() -> int:
    today = _dt.date.today().isoformat()
    if not EMAIL_LOG.exists():
        return 0
    return sum(1 for line in EMAIL_LOG.read_text(encoding="utf-8").splitlines() if line.startswith(today))


def _log_send(to: str, subject: str) -> None:
    ensure_runtime_dirs()
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with Path(EMAIL_LOG).open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} | {to} | {subject}\n")
    try:
        from core import audit_log

        audit_log.record(
            actor="friday",
            category="email",
            action="send_email",
            target=to,
            success=True,
            details={"subject": subject},
        )
    except Exception:
        return

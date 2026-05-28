import smtplib

from core import audit_log
from tools import email_tool


def test_email_confirmation_yes_sends(monkeypatch):
    calls = []
    monkeypatch.setenv("GMAIL_ADDRESS", "me@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "password")
    monkeypatch.setattr(email_tool, "_daily_count", lambda: 0)
    monkeypatch.setattr(email_tool, "record_and_transcribe", lambda: "yes send it")
    monkeypatch.setattr(email_tool, "speak", lambda text: None)
    monkeypatch.setattr(email_tool, "_send", lambda to, subject, body, sender=None, password=None: calls.append((to, subject, body)) or "Email sent.")

    assert email_tool.execute({"to": "you@example.com", "subject": "Hi", "body": "Hello"}) == "Email sent."
    assert calls == [("you@example.com", "Hi", "Hello")]


def test_email_confirmation_no_cancels(monkeypatch):
    calls = []
    monkeypatch.setenv("GMAIL_ADDRESS", "me@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "password")
    monkeypatch.setattr(email_tool, "_daily_count", lambda: 0)
    monkeypatch.setattr(email_tool, "record_and_transcribe", lambda: "no")
    monkeypatch.setattr(email_tool, "speak", lambda text: None)
    monkeypatch.setattr(email_tool, "_send", lambda *args, **kwargs: calls.append(args) or "sent")

    assert email_tool.execute({"to": "you@example.com", "subject": "Hi", "body": "Hello"}) == "Email cancelled."
    assert calls == []


def test_smtp_failure_returns_configuration_error(monkeypatch):
    class BadSMTP:
        def __init__(self, *args, **kwargs):
            raise smtplib.SMTPException("bad credentials")

    monkeypatch.setattr(email_tool.smtplib, "SMTP", BadSMTP)

    assert "Email configuration error" in email_tool._send("to@example.com", "Subject", "Body", "me@example.com", "password")


def test_email_log_send_writes_audit(monkeypatch, tmp_path):
    monkeypatch.setattr(email_tool, "EMAIL_LOG", tmp_path / "email_log.txt")
    monkeypatch.setattr(email_tool, "ensure_runtime_dirs", lambda: None)
    monkeypatch.setattr(audit_log, "DB_PATH", tmp_path / "audit.sqlite3")

    email_tool._log_send("you@example.com", "Hi")

    events = audit_log.recent()
    assert events[0]["category"] == "email"
    assert events[0]["action"] == "send_email"


def test_daily_limit_blocks_send(monkeypatch):
    calls = []
    monkeypatch.setenv("GMAIL_ADDRESS", "me@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "password")
    monkeypatch.setattr(email_tool, "config_value", lambda key, default=None: 1)
    monkeypatch.setattr(email_tool, "_daily_count", lambda: 1)
    monkeypatch.setattr(email_tool, "_send", lambda *args, **kwargs: calls.append(args) or "sent")

    assert "Daily email limit" in email_tool.execute({"to": "you@example.com", "subject": "Hi", "body": "Hello"})
    assert calls == []

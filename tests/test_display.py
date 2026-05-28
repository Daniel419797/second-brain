import time

from output import display


def test_log_writes_to_session_file(tmp_path, monkeypatch):
    log_file = tmp_path / "session.log"
    monkeypatch.setattr(display, "LOG_FILE", log_file)
    display.set_log_level("DEBUG")

    display.log("INFO", "test")

    assert "[INFO" in log_file.read_text(encoding="utf-8")


def test_notify_returns_immediately(monkeypatch):
    monkeypatch.setattr(display, "_send_toast", lambda title, message: time.sleep(0.05))

    start = time.perf_counter()
    display.notify("Title", "Message")

    assert time.perf_counter() - start < 0.05


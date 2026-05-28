from core import phone_bridge
from tools import phone_bridge as phone_tool


def test_phone_bridge_register_status_and_battery(monkeypatch, tmp_path):
    monkeypatch.setattr(phone_bridge, "DB_PATH", tmp_path / "phone.sqlite3")
    monkeypatch.setattr(phone_bridge, "_adb_path", lambda: "adb")
    monkeypatch.setattr(
        phone_bridge,
        "_run_adb",
        lambda args, serial="": {
            "ok": True,
            "stdout": "List of devices attached\nabc123 device model:Pixel\n"
            if args[:2] == ["devices", "-l"]
            else "level: 87\nstatus: 2\nplugged: 1\ntemperature: 310\n",
            "stderr": "",
            "returncode": 0,
        },
    )

    device = phone_bridge.register_device("Pixel", adb_serial="abc123", ntfy_topic="topic")
    status = phone_bridge.status()
    battery = phone_bridge.battery_status()

    assert device["name"] == "Pixel"
    assert status["adb_connected"] is True
    assert status["ntfy_configured"] is True
    assert battery["level"] == 87
    assert battery["charging"] is True


def test_phone_bridge_sends_ntfy_notification(monkeypatch, tmp_path):
    monkeypatch.setattr(phone_bridge, "DB_PATH", tmp_path / "phone.sqlite3")
    phone_bridge.register_device("Pixel", ntfy_topic="private-topic")
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"id":"msg"}'

    def fake_urlopen(req, timeout=0):
        requests.append((req.full_url, dict(req.header_items()), timeout, req.data))
        return FakeResponse()

    monkeypatch.setattr(phone_bridge.request, "urlopen", fake_urlopen)

    result = phone_bridge.send_notification("Friday", "Hello", priority="urgent")

    assert result["ok"] is True
    assert requests[0][0].endswith("/private-topic")
    assert requests[0][3] == b"Hello"


def test_phone_tool_formats_ring(monkeypatch, tmp_path):
    monkeypatch.setattr(phone_bridge, "DB_PATH", tmp_path / "phone.sqlite3")
    monkeypatch.setattr(phone_bridge, "ring_phone", lambda message="": {"ok": True, "summary": "Phone ring alert sent."})

    assert phone_tool.execute({"action": "ring"}) == "Phone ring alert sent."


def test_phone_bridge_open_url_uses_adb(monkeypatch, tmp_path):
    monkeypatch.setattr(phone_bridge, "DB_PATH", tmp_path / "phone.sqlite3")
    phone_bridge.register_device("Pixel", adb_serial="abc123")
    calls = []
    monkeypatch.setattr(phone_bridge, "adb_devices", lambda: [{"serial": "abc123", "state": "device", "metadata": {}}])
    monkeypatch.setattr(phone_bridge, "_run_adb", lambda args, serial="": calls.append((args, serial)) or {"ok": True, "stdout": "", "stderr": "", "returncode": 0})

    result = phone_bridge.open_url("example.com")

    assert result["ok"] is True
    assert result["url"] == "https://example.com"
    assert calls[0][1] == "abc123"


def test_phone_bridge_sms_and_clipboard_use_adb(monkeypatch, tmp_path):
    monkeypatch.setattr(phone_bridge, "DB_PATH", tmp_path / "phone.sqlite3")
    phone_bridge.register_device("Pixel", adb_serial="abc123")
    calls = []
    monkeypatch.setattr(phone_bridge, "adb_devices", lambda: [{"serial": "abc123", "state": "device", "metadata": {}}])
    monkeypatch.setattr(phone_bridge, "_run_adb", lambda args, serial="": calls.append((args, serial)) or {"ok": True, "stdout": "", "stderr": "", "returncode": 0})

    sms = phone_bridge.sms_draft("+2348012345678", "hello")
    clip = phone_bridge.set_clipboard("copy this")

    assert sms["ok"] is True
    assert clip["ok"] is True
    assert any("SENDTO" in " ".join(call[0]) for call in calls)


def test_phone_bridge_file_transfer_uses_adb(monkeypatch, tmp_path):
    monkeypatch.setattr(phone_bridge, "DB_PATH", tmp_path / "phone.sqlite3")
    local_file = tmp_path / "note.txt"
    local_file.write_text("hello", encoding="utf-8")
    phone_bridge.register_device("Pixel", adb_serial="abc123")
    calls = []
    monkeypatch.setattr(phone_bridge, "adb_devices", lambda: [{"serial": "abc123", "state": "device", "metadata": {}}])
    monkeypatch.setattr(phone_bridge, "_run_adb", lambda args, serial="": calls.append((args, serial)) or {"ok": True, "stdout": "", "stderr": "", "returncode": 0})

    result = phone_bridge.push_file_to_phone(str(local_file), "/sdcard/Download/")

    assert result["ok"] is True
    assert calls[0][0][0] == "push"

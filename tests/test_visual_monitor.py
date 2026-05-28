import time

from core import visual_monitor


def isolate_visual_monitor(monkeypatch, tmp_path):
    visual_monitor.stop_monitor(timeout=0.1)
    monkeypatch.setattr(visual_monitor, "DB_PATH", tmp_path / "visual_monitor.sqlite3")
    monkeypatch.setattr(visual_monitor, "FRAME_ROOT", tmp_path / "frames")
    visual_monitor._STOP.clear()
    visual_monitor._THREAD = None
    visual_monitor._STATE.update({"running": False, "source": "", "started_at": "", "last_error": ""})
    visual_monitor._LATEST_FRAME_BYTES.clear()
    visual_monitor._LATEST_FRAME_META.clear()
    visual_monitor.init_db()


def test_capture_once_records_visual_events(monkeypatch, tmp_path):
    isolate_visual_monitor(monkeypatch, tmp_path)
    captures = []

    def fake_capture(source):
        path = tmp_path / f"{source}_{len(captures)}.txt"
        path.write_text(f"frame {len(captures)}", encoding="utf-8")
        captures.append(path)
        return path, f"{source} captured"

    monkeypatch.setattr(visual_monitor, "_capture_frame", fake_capture)
    monkeypatch.setattr(
        visual_monitor,
        "config_value",
        lambda key, default=None: {
            "visual_monitor_change_threshold": 0.01,
            "visual_monitor_analysis_enabled": False,
        }.get(key, default),
    )

    first = visual_monitor.capture_once("screen")[0]
    second = visual_monitor.capture_once("screen")[0]
    recent = visual_monitor.recent_events(limit=2)

    assert first["event_type"] == "change"
    assert second["source"] == "screen"
    assert len(recent) == 2
    assert recent[0]["frame_name"].startswith("screen_")


def test_monitor_thread_start_and_stop(monkeypatch, tmp_path):
    isolate_visual_monitor(monkeypatch, tmp_path)
    calls = []

    def fake_capture_and_record(source, analyze=None):
        calls.append(source)
        visual_monitor._STOP.set()
        return {"source": source, "event_type": "frame"}

    monkeypatch.setattr(visual_monitor, "_capture_and_record", fake_capture_and_record)
    monkeypatch.setattr(
        visual_monitor,
        "config_value",
        lambda key, default=None: 0.01 if key == "visual_monitor_interval_seconds" else default,
    )

    started = visual_monitor.start_monitor("screen")
    for _ in range(20):
        if calls:
            break
        time.sleep(0.01)
    stopped = visual_monitor.stop_monitor(timeout=1.0)

    assert started["running"] is True
    assert calls == ["screen"]
    assert stopped["running"] is False
    assert visual_monitor.latest_event()["event_type"] == "stopped"


def test_realtime_mjpeg_stream_yields_live_frame(monkeypatch, tmp_path):
    isolate_visual_monitor(monkeypatch, tmp_path)
    monkeypatch.setattr(visual_monitor, "_capture_frame_bytes", lambda source: (b"fake-jpeg", "image/jpeg"))
    monkeypatch.setattr(
        visual_monitor,
        "config_value",
        lambda key, default=None: 10.0 if key == "visual_monitor_realtime_fps" else default,
    )

    stream = visual_monitor.mjpeg_stream("screen")
    chunk = next(stream)
    stream.close()

    assert b"--frame" in chunk
    assert b"fake-jpeg" in chunk
    assert visual_monitor.latest_frames()["screen"]["content_type"] == "image/jpeg"

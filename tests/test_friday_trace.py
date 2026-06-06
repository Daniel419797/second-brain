from core import friday_trace


def test_friday_trace_records_events(monkeypatch, tmp_path):
    monkeypatch.setattr(friday_trace, "DB_PATH", tmp_path / "traces.sqlite3")

    trace_id, metadata = friday_trace.ensure_trace_id({"source": "test"}, prefix="unit")
    friday_trace.start_trace(trace_id, kind="unit_test", title="Trace me", root=tmp_path, metadata=metadata)
    event = friday_trace.record_event(trace_id, event_type="phase", title="inspect", summary="Inspected.", status="done")
    loaded = friday_trace.get_trace(trace_id)

    assert event["trace_id"] == trace_id
    assert loaded["trace_id"] == trace_id
    assert loaded["metadata"]["source"] == "test"
    assert loaded["events"][0]["event_type"] == "phase"
    assert friday_trace.recent(limit=1)[0]["trace_id"] == trace_id

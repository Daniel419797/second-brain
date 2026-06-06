from core import approval_inbox, friday_tool_registry, friday_trace


def test_tool_registry_executes_document_tool_with_trace(monkeypatch, tmp_path):
    monkeypatch.setattr(friday_trace, "DB_PATH", tmp_path / "traces.sqlite3")
    path = tmp_path / "brief.md"
    path.write_text("# Brief\n\nFriday should index proof documents.", encoding="utf-8")

    result = friday_tool_registry.execute_tool("documents.read", {"path": str(path), "max_chars": 500})
    trace = friday_trace.get_trace(result["trace_id"])

    assert result["ok"] is True
    assert result["tool"] == "documents.read"
    assert "Brief" in result["text"]
    assert any(event["event_type"] == "tool_finish" for event in trace["events"])


def test_tool_registry_blocks_approval_tools(monkeypatch, tmp_path):
    monkeypatch.setattr(friday_trace, "DB_PATH", tmp_path / "traces.sqlite3")
    monkeypatch.setattr(approval_inbox, "DB_PATH", tmp_path / "approvals.sqlite3")

    friday_tool_registry.register_tool(
        "danger.test",
        lambda _args: {"ok": True, "summary": "Should not run without approval."},
        description="Dangerous test tool.",
        input_schema={"required": ["target"], "properties": {"target": {"type": "string"}}},
        requires_approval=True,
        category="test",
    )

    result = friday_tool_registry.execute_tool("danger.test", {"target": "production"})

    assert result["ok"] is False
    assert result["status"] == "blocked_for_approval"
    assert result["approval"]["kind"] == "tool_approval"
    assert friday_trace.get_trace(result["trace_id"])["events"]


def test_tool_registry_rejects_invalid_payload(monkeypatch, tmp_path):
    monkeypatch.setattr(friday_trace, "DB_PATH", tmp_path / "traces.sqlite3")

    result = friday_tool_registry.execute_tool("documents.index", {"paths": []})

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert "Missing required field: paths" in result["errors"]

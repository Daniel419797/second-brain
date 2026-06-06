import time
from pathlib import Path

import pytest

from core import approval_inbox, artifact_access, friday_run_engine, friday_trace, langgraph_backbone


def test_friday_run_engine_records_events_and_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(friday_run_engine, "DB_PATH", tmp_path / "friday_runs.sqlite3")
    artifact = tmp_path / "project" / ".friday" / "proof.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("# Proof\n", encoding="utf-8")

    run = friday_run_engine.create_run("production_readiness", "Build a web app", root=tmp_path)
    updated = friday_run_engine.update_run(
        run["id"],
        status="blocked",
        phase="verifying",
        summary="Required gates failed.",
        artifacts=[str(artifact)],
        gaps=["Browser gate failed"],
    )
    loaded = friday_run_engine.get_run(run["id"])

    assert updated["status"] == "blocked"
    assert loaded["events"]
    assert str(artifact.resolve()) in artifact_access.collect_manifest_paths(loaded)


def test_artifact_access_requires_manifest_match(tmp_path):
    allowed = tmp_path / "project" / ".friday" / "proof.md"
    denied = tmp_path / "project" / ".friday" / "other.md"
    allowed.parent.mkdir(parents=True)
    allowed.write_text("# Allowed\n", encoding="utf-8")
    denied.write_text("# Denied\n", encoding="utf-8")

    opened = artifact_access.read_artifact(str(allowed), allowed_paths=[str(allowed)], require_manifest_match=True)

    assert opened["content"] == "# Allowed\n"
    with pytest.raises(artifact_access.ArtifactAccessError):
        artifact_access.read_artifact(str(denied), allowed_paths=[str(allowed)], require_manifest_match=True)


def test_background_run_captures_output(monkeypatch, tmp_path):
    monkeypatch.setattr(friday_run_engine, "DB_PATH", tmp_path / "friday_runs.sqlite3")

    run = friday_run_engine.start_background(
        "design_critique",
        "Design a screen",
        lambda: {"status": "done", "summary": "Finished.", "artifacts": []},
        root=tmp_path,
    )

    for _ in range(40):
        loaded = friday_run_engine.get_run(run["id"])
        if loaded and loaded["status"] == "done":
            break
        time.sleep(0.05)

    assert friday_run_engine.get_run(run["id"])["status"] == "done"


def test_langgraph_backbone_native_fallback(monkeypatch):
    monkeypatch.setattr(langgraph_backbone, "_load_langgraph", lambda: {"available": False, "error": "missing"})
    monkeypatch.setattr(langgraph_backbone, "config_value", lambda key, default=None: "auto" if key == "friday_workflow_backend" else default)
    order = []

    result = langgraph_backbone.run_phase_graph(
        [
            ("inspect", lambda state: order.append("inspect") or {"inspected": True}),
            ("prove", lambda state: order.append("prove") or {"proved": state.get("inspected")}),
        ],
        {"run_id": 1},
        thread_id="test-run",
    )

    assert result["workflow_backend"] == "native"
    assert result["workflow_backend_error"] == "missing"
    assert result["workflow_phases"] == ["inspect", "prove"]
    assert result["proved"] is True
    assert order == ["inspect", "prove"]


def test_langgraph_backbone_stops_native_workflow_on_approval(monkeypatch, tmp_path):
    monkeypatch.setattr(approval_inbox, "DB_PATH", tmp_path / "approvals.sqlite3")
    monkeypatch.setattr(friday_trace, "DB_PATH", tmp_path / "traces.sqlite3")
    monkeypatch.setattr(langgraph_backbone, "config_value", lambda key, default=None: "native" if key == "friday_workflow_backend" else default)
    order = []

    result = langgraph_backbone.run_phase_graph(
        [
            (
                "approval",
                lambda state: order.append("approval")
                or langgraph_backbone.request_approval(
                    state,
                    kind="deploy_production",
                    title="Approve production deploy",
                    summary="Production deploy requires a human decision.",
                    payload={"run_id": 1},
                ),
            ),
            ("after", lambda _state: order.append("after") or {"ran_after": True}),
        ],
        {"trace_id": "trace-approval-test"},
        thread_id="approval-test",
    )

    assert result["workflow_interrupted"] is True
    assert result["status"] == "blocked_for_approval"
    assert result["workflow_phases"] == ["approval"]
    assert order == ["approval"]


def test_langgraph_backbone_uses_langgraph_when_available(monkeypatch):
    class FakeCompiledGraph:
        def __init__(self, nodes):
            self.nodes = nodes

        def invoke(self, state, config=None):
            state = dict(state)
            state["thread_id"] = (config or {}).get("configurable", {}).get("thread_id")
            for handler in self.nodes.values():
                state = handler(state)
            return state

    class FakeStateGraph:
        def __init__(self, _schema):
            self.nodes = {}

        def add_node(self, name, handler):
            self.nodes[name] = handler

        def add_edge(self, _left, _right):
            return None

        def compile(self, checkpointer=None):
            return FakeCompiledGraph(self.nodes)

    monkeypatch.setattr(
        langgraph_backbone,
        "_load_langgraph",
        lambda: {
            "available": True,
            "StateGraph": FakeStateGraph,
            "START": "__start__",
            "END": "__end__",
            "MemorySaver": lambda: object(),
            "error": "",
        },
    )
    monkeypatch.setattr(langgraph_backbone, "config_value", lambda key, default=None: "auto" if key == "friday_workflow_backend" else default)

    result = langgraph_backbone.run_phase_graph(
        [
            ("inspect", lambda state: {"inspected": True}),
            ("prove", lambda state: {"proved": state.get("inspected")}),
        ],
        {"run_id": 2},
        thread_id="langgraph-test",
    )

    assert result["workflow_backend"] == "langgraph"
    assert result["workflow_phases"] == ["inspect", "prove"]
    assert result["thread_id"] == "langgraph-test"
    assert result["proved"] is True

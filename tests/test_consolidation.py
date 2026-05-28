from core import consolidation, episodic_store, knowledge_graph, memory


def test_consolidation_extracts_facts_and_decays(monkeypatch, tmp_path):
    monkeypatch.setattr(episodic_store, "DB_PATH", tmp_path / "events.sqlite3")
    monkeypatch.setattr(memory, "_local_memory_file", tmp_path / "memory_store.json")
    monkeypatch.setattr(memory, "_archive_file", tmp_path / "archived.jsonl")
    monkeypatch.setattr(memory, "_vector_store", lambda: (None, None))
    monkeypatch.setattr(knowledge_graph, "GRAPH_PATH", tmp_path / "graph.json")
    monkeypatch.setattr(knowledge_graph, "_GRAPH", None)
    monkeypatch.setattr(consolidation, "config_value", lambda key, default=None: False if key == "consolidation_use_llm" else default)

    episodic_store.insert_event(
        action_type="command",
        inputs={"user_text": "remember my favorite editor is VS Code"},
        outputs={"reply": "Remembered."},
    )

    result = consolidation.consolidate()

    assert result["events_processed"] == 1
    assert result["facts_extracted"] == 1
    assert memory.recall("favorite editor")
    assert knowledge_graph.spreading_recall("favorite editor")


def test_scheduler_can_start_and_stop(monkeypatch):
    calls = []

    class FakeScheduler:
        running = False

        def __init__(self, daemon=True):
            self.daemon = daemon

        def add_job(self, *args, **kwargs):
            calls.append(("add_job", args, kwargs))

        def start(self):
            self.running = True
            calls.append(("start",))

        def shutdown(self, wait=False):
            self.running = False
            calls.append(("shutdown", wait))

    monkeypatch.setattr(consolidation, "BackgroundScheduler", FakeScheduler)
    monkeypatch.setattr(consolidation, "config_value", lambda key, default=None: True if key == "memory_consolidation_enabled" else default)
    monkeypatch.setattr(consolidation, "_SCHEDULER", None)

    scheduler = consolidation.start_scheduler()
    consolidation.stop_scheduler()

    assert scheduler is not None
    assert calls[0][0] == "add_job"
    assert ("start",) in calls
    assert ("shutdown", False) in calls

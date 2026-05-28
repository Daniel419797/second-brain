from core import context_budget, episodic_store, knowledge_graph, memory


def test_memory_stores_and_recalls_remember_tags():
    memory.wipe_all()

    memory.add_assistant("[REMEMBER: user prefers dark mode]")

    assert "user prefers dark mode" in memory.recall("colour theme")


def test_strip_remember_tags_keeps_user_facing_text():
    assert memory.strip_remember_tags("Done. [REMEMBER: user likes Python]") == "Done."


def test_clear_session_keeps_long_term_memory():
    memory.wipe_all()
    memory.add_user("hello")
    memory.add_assistant("[REMEMBER: user likes Python]")

    memory.clear_session()

    assert memory.get_messages() == []
    assert "user likes Python" in memory.recall("programming language")


def test_memory_add_search_and_activation_decay(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "_local_memory_file", tmp_path / "memory_store.json")
    monkeypatch.setattr(memory, "_archive_file", tmp_path / "archived.jsonl")
    monkeypatch.setattr(memory, "_vector_store", lambda: (None, None))

    mem_id = memory.add("user prefers dark mode", metadata={"source": "test"})

    assert mem_id.startswith("mem_")
    assert memory.search("colour theme") == ["user prefers dark mode"]
    result = memory.decay_activation_scores(rate=0.95, prune_threshold=0.1)
    assert result == {"decayed": 1, "archived": 1}
    assert memory.all_memories() == []
    assert "user prefers dark mode" in memory.all_memories(include_archived=True)[0]["text"]


def test_build_context_includes_memory_graph_and_episodic(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "_local_memory_file", tmp_path / "memory_store.json")
    monkeypatch.setattr(memory, "_archive_file", tmp_path / "archived.jsonl")
    monkeypatch.setattr(memory, "_vector_store", lambda: (None, None))
    monkeypatch.setattr(knowledge_graph, "GRAPH_PATH", tmp_path / "graph.json")
    monkeypatch.setattr(knowledge_graph, "_GRAPH", None)
    monkeypatch.setattr(episodic_store, "DB_PATH", tmp_path / "episodic.sqlite3")

    memory.add("user prefers dark mode")
    knowledge_graph.add_edge("Jarvis", "LEARNED", "dark mode preference")
    episodic_store.insert_event(action_type="command", inputs={"user_text": "hello"}, outputs={"reply": "hi"})

    context = memory.build_context("dark mode", facts=memory.recall("colour theme"))

    assert "Semantic Memory" in context
    assert "user prefers dark mode" in context
    assert "Associative Knowledge Graph" in context
    assert context_budget.within_budget(context)

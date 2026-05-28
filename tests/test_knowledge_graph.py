from core import knowledge_graph


def test_knowledge_graph_add_edge_and_spreading_recall(monkeypatch, tmp_path):
    monkeypatch.setattr(knowledge_graph, "GRAPH_PATH", tmp_path / "graph.json")
    monkeypatch.setattr(knowledge_graph, "_GRAPH", None)

    knowledge_graph.add_edge("Jarvis", "BUILT", "auth.py")
    knowledge_graph.add_edge("auth.py", "USES", "bcrypt")

    assert knowledge_graph.node_count() == 3
    assert knowledge_graph.edge_count() == 2
    assert knowledge_graph.get_edges("auth.py")
    recall = knowledge_graph.spreading_recall("auth.py", hops=2)
    assert "Jarvis -[BUILT]-> auth.py" in recall
    assert "auth.py -[USES]-> bcrypt" in recall


def test_knowledge_graph_wipe_all(monkeypatch, tmp_path):
    monkeypatch.setattr(knowledge_graph, "GRAPH_PATH", tmp_path / "graph.json")
    monkeypatch.setattr(knowledge_graph, "_GRAPH", None)
    knowledge_graph.add_edge("A", "RELATED_TO", "B")

    knowledge_graph.wipe_all()

    assert knowledge_graph.edge_count() == 0

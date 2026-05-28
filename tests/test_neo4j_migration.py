from core import knowledge_graph, neo4j_migration


def test_neo4j_migration_exports_cypher(monkeypatch, tmp_path):
    monkeypatch.setattr(knowledge_graph, "get_edges", lambda node=None: [
        {"subject": "Friday", "predicate": "learned", "object": "Python", "metadata": {"score": 1}},
    ])

    result = neo4j_migration.export_cypher(tmp_path / "graph.cypher")
    text = (tmp_path / "graph.cypher").read_text(encoding="utf-8")

    assert result["nodes"] == 2
    assert "CREATE CONSTRAINT" in text
    assert "MERGE (:Concept {name: \"Friday\"});" in text
    assert "MERGE (a)-[r:LEARNED]->(b)" in text

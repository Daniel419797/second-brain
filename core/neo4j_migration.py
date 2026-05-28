"""Neo4j/Cypher export path for the local NetworkX knowledge graph."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from core import knowledge_graph
from core.config import DATA_DIR, ensure_runtime_dirs

DEFAULT_EXPORT_PATH = DATA_DIR / "knowledge_graph.cypher"


def export_cypher(path: str | Path | None = None) -> dict[str, Any]:
    """Write an idempotent Cypher migration file for the current graph."""
    ensure_runtime_dirs()
    export_path = Path(path) if path else DEFAULT_EXPORT_PATH
    export_path.parent.mkdir(parents=True, exist_ok=True)
    edges = knowledge_graph.get_edges()
    statements = [
        "// Friday knowledge graph export",
        f"// Generated: {dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec='seconds')}",
        "CREATE CONSTRAINT friday_concept_name IF NOT EXISTS FOR (n:Concept) REQUIRE n.name IS UNIQUE;",
    ]
    nodes = sorted({edge["subject"] for edge in edges} | {edge["object"] for edge in edges})
    for node in nodes:
        statements.append(f"MERGE (:Concept {{name: {_cypher_string(node)}}});")
    for edge in edges:
        predicate = _relation(edge.get("predicate", "RELATED_TO"))
        metadata = json.dumps(edge.get("metadata") or {}, ensure_ascii=True, default=str)
        statements.append(
            "MATCH (a:Concept {name: "
            + _cypher_string(edge["subject"])
            + "}), (b:Concept {name: "
            + _cypher_string(edge["object"])
            + "}) "
            + f"MERGE (a)-[r:{predicate}]->(b) "
            + f"SET r.metadata_json = {_cypher_string(metadata)};"
        )
    export_path.write_text("\n".join(statements) + "\n", encoding="utf-8")
    return {
        "path": str(export_path),
        "nodes": len(nodes),
        "edges": len(edges),
        "statements": len(statements),
    }


def preview(limit: int = 20) -> str:
    """Return a short Cypher preview without writing a file."""
    result = export_cypher()
    path = Path(result["path"])
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[: max(1, int(limit))])


def _relation(value: Any) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", str(value or "RELATED_TO").upper()).strip("_")
    if not cleaned or cleaned[0].isdigit():
        cleaned = "RELATED_TO"
    return cleaned[:64]


def _cypher_string(value: Any) -> str:
    return json.dumps(str(value or ""), ensure_ascii=True)

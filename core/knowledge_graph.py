"""Local knowledge graph with spreading activation recall."""

from __future__ import annotations

import datetime as dt
import json
import re
import threading
from pathlib import Path
from typing import Any

try:
    import networkx as nx
    from networkx.readwrite import json_graph
except Exception:  # pragma: no cover - dependency is pinned but optional at runtime
    nx = None
    json_graph = None

from core.config import DATA_DIR, ensure_runtime_dirs

GRAPH_PATH = DATA_DIR / "knowledge_graph.json"
_LOCK = threading.Lock()
_GRAPH: Any = None


def add_edge(subject: str, predicate: str, object_name: str, **metadata: Any) -> None:
    subject = _clean_node(subject)
    predicate = _clean_predicate(predicate)
    object_name = _clean_node(object_name)
    if not subject or not predicate or not object_name:
        return
    graph = _graph()
    if graph is None:
        return
    now = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    edge_data = {
        "predicate": predicate,
        "updated_at": now,
        "weight": float(metadata.pop("weight", 1.0)),
    }
    edge_data.update({key: _json_safe(value) for key, value in metadata.items()})
    with _LOCK:
        graph.add_node(subject, updated_at=now)
        graph.add_node(object_name, updated_at=now)
        graph.add_edge(subject, object_name, **edge_data)
        _save_graph(graph)


def get_edges(node: str | None = None) -> list[dict[str, Any]]:
    graph = _graph()
    if graph is None:
        return []
    if node:
        names = _matching_nodes(node)
        edge_iter = []
        for name in names:
            edge_iter.extend(graph.out_edges(name, data=True))
            edge_iter.extend(graph.in_edges(name, data=True))
    else:
        edge_iter = list(graph.edges(data=True))
    return [_edge_dict(source, target, data) for source, target, data in edge_iter]


def spreading_recall(query: str, hops: int = 2, limit: int = 12) -> list[str]:
    graph = _graph()
    if graph is None or not query:
        return []
    seeds = _matching_nodes(query)
    if not seeds:
        return []
    activated: set[str] = set()
    for seed in seeds:
        activated.add(seed)
        lengths = nx.single_source_shortest_path_length(graph.to_undirected(), seed, cutoff=max(0, hops))
        activated.update(lengths.keys())
    lines: list[str] = []
    for source, target, data in graph.edges(data=True):
        if source in activated or target in activated:
            lines.append(_format_edge(source, target, data))
        if len(lines) >= limit:
            break
    return lines


def query(query_text: str, limit: int = 12) -> dict[str, Any]:
    edges = get_edges(query_text)
    recall = spreading_recall(query_text, limit=limit)
    return {
        "query": query_text,
        "edges": edges[: max(1, min(100, int(limit or 12)))],
        "recall": recall,
        "summary": f"{len(edges)} direct edge(s), {len(recall)} recalled relationship(s).",
    }


def connect(subject: str, predicate: str, object_name: str, **metadata: Any) -> dict[str, Any]:
    add_edge(subject, predicate, object_name, **metadata)
    return {"subject": _clean_node(subject), "predicate": _clean_predicate(predicate), "object": _clean_node(object_name), "summary": "Knowledge graph relationship saved."}


def connect_context(*, people: list[str] | None = None, files: list[str] | None = None, projects: list[str] | None = None, goals: list[str] | None = None, apps: list[str] | None = None) -> dict[str, Any]:
    created = 0
    for project in projects or []:
        for file_name in files or []:
            add_edge(project, "CONTAINS_FILE", file_name, source="context_connect")
            created += 1
        for goal in goals or []:
            add_edge(project, "SUPPORTS_GOAL", goal, source="context_connect")
            created += 1
        for app in apps or []:
            add_edge(project, "USES_APP", app, source="context_connect")
            created += 1
    for person in people or []:
        for goal in goals or []:
            add_edge(person, "RELATED_TO_GOAL", goal, source="context_connect")
            created += 1
    return {"created": created, "summary": f"Added {created} graph relationship(s)."}


def summary() -> dict[str, Any]:
    return {"nodes": node_count(), "edges": edge_count(), "summary": f"{node_count()} knowledge node(s), {edge_count()} relationship(s)."}


def node_count() -> int:
    graph = _graph()
    return 0 if graph is None else int(graph.number_of_nodes())


def edge_count() -> int:
    graph = _graph()
    return 0 if graph is None else int(graph.number_of_edges())


def wipe_all() -> None:
    global _GRAPH
    if nx is None:
        return
    with _LOCK:
        _GRAPH = nx.DiGraph()
        _save_graph(_GRAPH)


def _graph() -> Any:
    global _GRAPH
    if nx is None:
        return None
    if _GRAPH is not None:
        return _GRAPH
    ensure_runtime_dirs()
    if GRAPH_PATH.exists():
        try:
            data = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
            _GRAPH = json_graph.node_link_graph(data, directed=True)
            return _GRAPH
        except Exception:
            pass
    _GRAPH = nx.DiGraph()
    return _GRAPH


def _save_graph(graph: Any) -> None:
    if json_graph is None:
        return
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = json_graph.node_link_data(graph)
    GRAPH_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")


def _matching_nodes(query: str, limit: int = 5) -> list[str]:
    graph = _graph()
    if graph is None:
        return []
    terms = _terms(query)
    if not terms:
        return []
    scored: list[tuple[int, str]] = []
    for node in graph.nodes:
        node_text = str(node).lower()
        node_terms = _terms(node_text)
        score = sum(1 for term in terms if term in node_terms or term in node_text)
        if score:
            scored.append((score, str(node)))
    return [node for _score, node in sorted(scored, key=lambda item: (-item[0], len(item[1]), item[1]))[:limit]]


def _edge_dict(source: str, target: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "subject": source,
        "predicate": data.get("predicate", "RELATED_TO"),
        "object": target,
        "metadata": {key: value for key, value in data.items() if key != "predicate"},
    }


def _format_edge(source: str, target: str, data: dict[str, Any]) -> str:
    predicate = data.get("predicate", "RELATED_TO")
    return f"{source} -[{predicate}]-> {target}"


def _terms(text: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9_+.-]+", str(text).lower()) if len(part) > 1}


def _clean_node(value: str) -> str:
    return " ".join(str(value or "").strip().split())[:240]


def _clean_predicate(value: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9_]+", "_", str(value or "").upper()).strip("_")
    return cleaned[:64] or "RELATED_TO"


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)

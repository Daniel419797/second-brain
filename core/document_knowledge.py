"""Document knowledge adapter for Friday project context.

LlamaIndex is useful for document parsing/chunking, but Friday should not need
paid embeddings or an external LLM just to read project briefs. This module uses
LlamaIndex when present for chunking, then applies Friday's local lexical
ranking so document search remains private and predictable.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.config import config_value, resolve_coding_root


def capabilities() -> dict[str, Any]:
    loaded = _load_llama_index()
    preferred = str(config_value("document_knowledge_backend", "auto") or "auto").strip().lower()
    active = "native"
    if preferred not in {"native", "off", "disabled"} and loaded.get("available"):
        active = "llama_index"
    return {
        "preferred_backend": preferred,
        "active_backend": active,
        "llama_index_available": bool(loaded.get("available")),
        "llama_index_error": loaded.get("error", ""),
        "uses_external_llm": False,
        "uses_paid_embeddings": False,
        "summary": "Friday indexes readable documents with LlamaIndex chunking when available, then ranks locally without external LLM or embedding spend.",
    }


def index_texts(
    documents: list[dict[str, Any]],
    *,
    root: str | Path = "",
    query: str = "",
    chunk_size: int = 1200,
    top_k: int = 6,
) -> dict[str, Any]:
    clean_docs = [
        {
            "path": str(item.get("path") or ""),
            "name": str(item.get("name") or Path(str(item.get("path") or "document")).name),
            "kind": str(item.get("kind") or "document"),
            "text": str(item.get("text") or ""),
        }
        for item in documents
        if str(item.get("text") or "").strip()
    ]
    loaded = _load_llama_index()
    preferred = str(config_value("document_knowledge_backend", "auto") or "auto").strip().lower()
    use_llama = preferred not in {"native", "off", "disabled"} and bool(loaded.get("available"))
    chunks = _llama_chunks(clean_docs, loaded, chunk_size=chunk_size) if use_llama else _native_chunks(clean_docs, chunk_size=chunk_size)
    ranked = _rank_chunks(chunks, query=query, top_k=top_k)
    artifact = _write_index_manifest(root, clean_docs, chunks, ranked, backend="llama_index" if use_llama else "native")
    return {
        "ok": bool(clean_docs),
        "backend": "llama_index" if use_llama else "native",
        "llama_index_available": bool(loaded.get("available")),
        "documents": len(clean_docs),
        "chunks": len(chunks),
        "query": str(query or ""),
        "top_chunks": ranked,
        "artifact": str(artifact) if artifact else "",
        "summary": _summary(clean_docs, chunks, ranked, use_llama=use_llama),
    }


def _llama_chunks(documents: list[dict[str, Any]], loaded: dict[str, Any], *, chunk_size: int) -> list[dict[str, Any]]:
    Document = loaded["Document"]
    SentenceSplitter = loaded["SentenceSplitter"]
    splitter = SentenceSplitter(chunk_size=max(300, int(chunk_size or 1200)), chunk_overlap=120)
    llama_docs = [
        Document(text=item["text"], metadata={"path": item["path"], "name": item["name"], "kind": item["kind"]})
        for item in documents
    ]
    nodes = splitter.get_nodes_from_documents(llama_docs)
    chunks: list[dict[str, Any]] = []
    for index, node in enumerate(nodes):
        metadata = dict(getattr(node, "metadata", {}) or {})
        text = _clean(node.get_content() if hasattr(node, "get_content") else getattr(node, "text", ""))
        if text:
            chunks.append(
                {
                    "id": f"chunk-{index + 1}",
                    "source": metadata.get("path") or "",
                    "name": metadata.get("name") or "",
                    "kind": metadata.get("kind") or "document",
                    "text": text,
                    "score": 0,
                }
            )
    return chunks


def _native_chunks(documents: list[dict[str, Any]], *, chunk_size: int) -> list[dict[str, Any]]:
    limit = max(300, int(chunk_size or 1200))
    chunks: list[dict[str, Any]] = []
    for item in documents:
        paragraphs = [part.strip() for part in re.split(r"\n{2,}|(?<=\.)\s+(?=[A-Z0-9#-])", item["text"]) if part.strip()]
        buffer = ""
        for paragraph in paragraphs or [item["text"]]:
            candidate = f"{buffer}\n\n{paragraph}".strip() if buffer else paragraph
            if len(candidate) > limit and buffer:
                chunks.append(_chunk(item, buffer, len(chunks) + 1))
                buffer = paragraph
            else:
                buffer = candidate
        if buffer:
            chunks.append(_chunk(item, buffer, len(chunks) + 1))
    return chunks


def _chunk(item: dict[str, Any], text: str, index: int) -> dict[str, Any]:
    return {
        "id": f"chunk-{index}",
        "source": item["path"],
        "name": item["name"],
        "kind": item["kind"],
        "text": _clean(text),
        "score": 0,
    }


def _rank_chunks(chunks: list[dict[str, Any]], *, query: str, top_k: int) -> list[dict[str, Any]]:
    terms = _terms(query)
    if not terms:
        ranked = chunks[: max(1, int(top_k or 6))]
        return [{**item, "score": 0} for item in ranked]
    scored: list[dict[str, Any]] = []
    for chunk in chunks:
        haystack = f"{chunk.get('name', '')} {chunk.get('kind', '')} {chunk.get('text', '')}".lower()
        score = sum(haystack.count(term) for term in terms)
        if score:
            scored.append({**chunk, "score": score})
    scored.sort(key=lambda item: (-int(item.get("score") or 0), str(item.get("name") or "")))
    return scored[: max(1, int(top_k or 6))]


def _write_index_manifest(
    root: str | Path,
    documents: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    ranked: list[dict[str, Any]],
    *,
    backend: str,
) -> Path | None:
    if not str(root or "").strip():
        return None
    base = resolve_coding_root(root) / ".friday" / "documents"
    base.mkdir(parents=True, exist_ok=True)
    path = base / "knowledge-index.json"
    path.write_text(
        json.dumps(
            {
                "backend": backend,
                "documents": [{"path": item["path"], "name": item["name"], "kind": item["kind"], "characters": len(item["text"])} for item in documents],
                "chunks": chunks,
                "top_chunks": ranked,
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _summary(documents: list[dict[str, Any]], chunks: list[dict[str, Any]], ranked: list[dict[str, Any]], *, use_llama: bool) -> str:
    backend = "LlamaIndex chunking" if use_llama else "native chunking"
    return f"Indexed {len(documents)} document(s) into {len(chunks)} chunk(s) with {backend}; {len(ranked)} relevant chunk(s) selected."


def _terms(query: str) -> list[str]:
    return [part for part in re.split(r"[^a-z0-9_]+", str(query or "").lower()) if len(part) > 2]


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _load_llama_index() -> dict[str, Any]:
    try:
        from llama_index.core import Document  # type: ignore
        from llama_index.core.node_parser import SentenceSplitter  # type: ignore

        return {"available": True, "Document": Document, "SentenceSplitter": SentenceSplitter, "error": ""}
    except Exception as exc:
        return {"available": False, "error": str(exc)}

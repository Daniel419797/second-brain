"""Private local search engine that federates Friday's safe stores."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core import browser_extension_bridge, local_file_intelligence, personal_data_timeline, personal_knowledge_vault, semantic_search
from core.config import ROOT_DIR


def index(paths: list[str] | None = None, *, include_private: bool = False, limit: int = 500) -> dict[str, Any]:
    roots = paths or [str(ROOT_DIR)]
    indexed = []
    for path in roots:
        indexed.append(semantic_search.index_path(path, include_private=include_private, limit=limit))
        try:
            local_file_intelligence.index_locations([path], max_files=min(limit, 500))
        except Exception:
            pass
    browser = browser_extension_bridge.latest_page_insight()
    if browser.get("ok"):
        page = browser.get("page") or {}
        semantic_search.index_text(page.get("title") or page.get("url") or "Browser page", page.get("selected_text") or browser.get("summary", ""), source=f"browser:{page.get('url')}", kind="browser", sensitive=False, tags="browser page")
    return {"indexed": indexed, "status": semantic_search.status(), "summary": f"Indexed {len(indexed)} local search root(s)."}


def search(query: str, *, limit: int = 10, include_sensitive: bool = False) -> dict[str, Any]:
    semantic = semantic_search.search(query, limit=limit, include_sensitive=include_sensitive)
    files = _safe(lambda: local_file_intelligence.search(query, limit=limit), [])
    vault = _safe(lambda: personal_knowledge_vault.search(query, limit=limit), [])
    timeline = _safe(lambda: personal_data_timeline.query(query, limit=limit), {})
    results = []
    results.extend({"source_type": "semantic", **item} for item in semantic)
    results.extend({"source_type": "file", **item} for item in files if isinstance(item, dict))
    results.extend({"source_type": "memory", **item} for item in vault if isinstance(item, dict))
    for item in timeline.get("items") or []:
        if isinstance(item, dict):
            results.append({"source_type": "timeline", **item})
    return {
        "query": query,
        "results": results[: max(1, min(50, int(limit or 10)))],
        "semantic": semantic,
        "files": files,
        "vault": vault,
        "timeline": timeline,
        "summary": f"Found {len(results)} result(s) across local search sources.",
    }


def answer(query: str, *, limit: int = 8) -> dict[str, Any]:
    result = search(query, limit=limit)
    top = result["results"][:5]
    if not top:
        return result | {"answer": "I could not find that in the local search index yet."}
    lines = [f"I found {len(result['results'])} related item(s):"]
    for item in top:
        title = item.get("title") or item.get("source") or item.get("summary") or item.get("path") or item.get("name") or "result"
        snippet = item.get("snippet") or item.get("summary") or item.get("content") or ""
        lines.append(f"- {title}: {str(snippet)[:180]}")
    return result | {"answer": "\n".join(lines)}


def status() -> dict[str, Any]:
    return {"semantic": semantic_search.status(), "summary": semantic_search.status().get("summary", "Local AI search ready.")}


def _safe(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except TypeError:
        try:
            return fn("")
        except Exception:
            return default
    except Exception:
        return default

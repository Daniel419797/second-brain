"""Web search and URL-opening tool backed by Friday's dedicated search broker."""

from __future__ import annotations

import html
import re
import webbrowser
from typing import Any

from core import search_broker
from core.config import config_value


def execute(inputs: dict[str, Any]) -> str:
    action = inputs.get("action", "search")
    if action == "open_url":
        url = str(inputs.get("url", ""))
        if not url:
            return "No URL provided."
        webbrowser.open(url)
        _audit("open_url", url, True)
        return "Opened in your browser."
    limit = _limit(inputs.get("limit") or config_value("search_broker_tool_results", 3))
    result = _search(str(inputs.get("query", "")), limit=limit, providers=inputs.get("providers") or "")
    return result


def _search(query: str, *, limit: int = 3, providers: str = "") -> str:
    payload = search_broker.search(query, limit=limit, providers=providers or None)
    _audit("search", query, bool(payload.get("ok")))
    return search_broker.format_results(payload)


def _format(results: list[dict[str, Any]]) -> str:
    """Format legacy DDG-shaped results for old tests and callers."""
    normalized = []
    for rank, item in enumerate(results, start=1):
        normalized.append(
            {
                "title": html.unescape(str(item.get("title", ""))),
                "url": str(item.get("url") or item.get("href") or ""),
                "snippet": re.sub(r"<[^>]+>", "", html.unescape(str(item.get("snippet") or item.get("body") or "")))[:300],
                "provider": str(item.get("provider") or "search"),
                "rank": rank,
                "score": 0.0,
                "domain": "",
            }
        )
    return search_broker.format_results({"query": "search", "results": normalized, "providers_succeeded": []}, max_chars=1000)


def _limit(value: Any) -> int:
    try:
        return max(1, min(10, int(value)))
    except Exception:
        return 3


def _audit(action: str, target: str, success: bool) -> None:
    try:
        from core import audit_log

        audit_log.record(
            actor="friday",
            category="web",
            action=action,
            target=target,
            success=success,
            details={},
        )
    except Exception:
        return

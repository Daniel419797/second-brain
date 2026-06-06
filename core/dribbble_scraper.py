"""Dribbble reference collector for Friday's design research.

This module intentionally behaves like a polite reference collector rather than
an aggressive crawler: it uses the existing search broker to discover public
Dribbble shot URLs, optionally fetches small public HTML metadata, rate-limits
requests, and writes a manifest Friday can cite in design briefs.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import design_asset_manager, search_broker
from core.config import config_value, resolve_coding_root


def collect(
    query: str,
    *,
    root: str | Path = "",
    limit: int = 6,
    create_artifact: bool = True,
) -> dict[str, Any]:
    """Collect Dribbble shot references for a design query."""

    result_limit = max(1, min(12, int(limit or 6)))
    search_query = f"site:dribbble.com/shots {query}".strip()
    artifacts: list[str] = []
    errors: list[str] = []
    try:
        search = search_broker.search(search_query, limit=result_limit, use_cache=True)
    except Exception as exc:
        search = {"ok": False, "results": [], "errors": [{"error": str(exc)}]}
    references: list[dict[str, Any]] = []
    seen: set[str] = set()
    delay = max(0.0, float(config_value("dribbble_scraper_delay_seconds", 0.4) or 0.0))
    fetch_pages = bool(config_value("dribbble_scraper_fetch_pages", True))
    for item in search.get("results") or []:
        url = str(item.get("url") or "").strip()
        if "dribbble.com/shots" not in url or url in seen:
            continue
        seen.add(url)
        reference = {
            "source": "dribbble",
            "title": _clean(item.get("title") or ""),
            "url": url,
            "snippet": _clean(item.get("snippet") or item.get("description") or ""),
            "image": "",
            "tags": _tags_from_text(f"{item.get('title') or ''} {item.get('snippet') or ''}"),
        }
        if fetch_pages:
            page = design_asset_manager.download_text(url, max_bytes=int(config_value("dribbble_scraper_page_max_bytes", 800_000) or 800_000))
            if page.get("ok"):
                metadata = _extract_page_metadata(str(page.get("text") or ""))
                reference.update({k: v for k, v in metadata.items() if v})
            else:
                errors.append(f"{url}: {page.get('reason') or 'fetch_failed'}")
            if delay:
                time.sleep(delay)
        references.append(reference)
        if len(references) >= result_limit:
            break
    payload = {
        "ok": bool(references),
        "status": "collected" if references else "empty",
        "provider": "dribbble_reference_collector",
        "query": query,
        "search_query": search_query,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "references": references,
        "errors": [*(str(err.get("error") or err) for err in (search.get("errors") or [])), *errors][:10],
        "usage_rule": "Use these as mood/reference evidence only. Do not copy protected assets or reproduce Dribbble work.",
    }
    if create_artifact:
        base = resolve_coding_root(root)
        out_dir = base / ".friday" / "design" / "research"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "dribbble-references.json"
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        artifacts.append(str(path))
    return {**payload, "artifacts": artifacts}


def _extract_page_metadata(html: str) -> dict[str, Any]:
    title = _meta(html, "og:title") or _title(html)
    description = _meta(html, "og:description") or _meta(html, "description")
    image = _meta(html, "og:image")
    return {
        "title": _clean(title),
        "snippet": _clean(description),
        "image": _clean(image),
        "tags": _tags_from_text(f"{title} {description}"),
    }


def _meta(html: str, name: str) -> str:
    pattern = rf"<meta\b(?=[^>]*(?:property|name)=['\"]{re.escape(name)}['\"])[^>]*content=['\"]([^'\"]+)['\"][^>]*>"
    match = re.search(pattern, html or "", flags=re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else ""


def _title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html or "", flags=re.IGNORECASE | re.DOTALL)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def _tags_from_text(text: str) -> list[str]:
    terms = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9+-]{2,}", str(text or "").lower()):
        if token in {"dribbble", "shot", "design", "website", "page", "work"}:
            continue
        if token not in terms:
            terms.append(token)
    return terms[:12]


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()

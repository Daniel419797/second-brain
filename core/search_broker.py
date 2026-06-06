"""Dedicated web-search broker for Friday.

The broker gives Friday one stable search interface while provider adapters handle
official search APIs, normalization, cache, dedupe, and ranking.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

try:
    import requests as _requests
except Exception:  # pragma: no cover - optional dependency during scaffold tests
    _requests = None

try:
    from duckduckgo_search import DDGS
except Exception:  # pragma: no cover - legacy fallback is optional
    DDGS = None

from core.config import DATA_DIR, config_value


DB_PATH = DATA_DIR / "search_broker.sqlite3"
TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "dclid",
    "gbraid",
    "wbraid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "igshid",
}
PROVIDER_ALIASES = {
    "brave_search": "brave",
    "google": "google_cse",
    "google_custom_search": "google_cse",
    "custom_search": "google_cse",
    "tavily_search": "tavily",
    "serp": "serpapi",
}


class SearchProviderError(RuntimeError):
    """Provider request failed in a way the broker can recover from."""


def search(
    query: str,
    *,
    limit: int | None = None,
    providers: str | list[str] | None = None,
    use_cache: bool = True,
    mode: str | None = None,
) -> dict[str, Any]:
    """Search the web through configured dedicated providers."""
    query = _clean(query)
    if not query:
        return _empty(query, "No search query provided.")
    if not bool(config_value("search_broker_enabled", True)):
        return _empty(query, "Dedicated search broker is disabled in config.json.")

    result_limit = _clamp_int(limit or config_value("search_broker_max_results", 5), 1, 20)
    provider_chain = _provider_chain(providers)
    if not provider_chain:
        return _empty(query, "No search providers are configured.")

    broker_mode = (mode or str(config_value("search_broker_mode", "fallback"))).strip().lower()
    if broker_mode not in {"fallback", "aggregate"}:
        broker_mode = "fallback"
    cache_key = _cache_key(query, result_limit, provider_chain, broker_mode)
    if use_cache and bool(config_value("search_broker_cache_enabled", True)):
        cached = _cache_get(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    attempted: list[str] = []
    succeeded: list[str] = []
    skipped: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    collected: list[dict[str, Any]] = []
    min_results = _clamp_int(config_value("search_broker_min_results_before_fallback", result_limit), 1, result_limit)

    for provider in provider_chain:
        available, reason = _provider_available(provider)
        if not available:
            skipped.append({"provider": provider, "reason": reason})
            continue
        attempted.append(provider)
        try:
            provider_results = _provider_functions()[provider](query, max(result_limit, min_results))
        except Exception as exc:
            errors.append({"provider": provider, "error": _short(str(exc), 220)})
            continue
        if provider_results:
            succeeded.append(provider)
            collected.extend(provider_results)
        ranked = _dedupe_and_rank(collected, query)
        if broker_mode == "fallback" and len(ranked) >= min_results:
            collected = ranked
            break

    results = _dedupe_and_rank(collected, query)[:result_limit]
    payload = {
        "ok": bool(results),
        "query": query,
        "results": results,
        "providers": provider_chain,
        "providers_attempted": attempted,
        "providers_succeeded": succeeded,
        "providers_skipped": skipped,
        "errors": errors,
        "cached": False,
        "message": _message(results, provider_chain, attempted, skipped, errors),
        "generated_at": int(time.time()),
    }
    if use_cache and results and bool(config_value("search_broker_cache_enabled", True)):
        _cache_put(cache_key, payload)
    return payload


def status() -> dict[str, Any]:
    """Return provider setup and cache state without revealing API keys."""
    providers = _provider_chain(None)
    provider_status = {}
    for provider in providers:
        available, reason = _provider_available(provider)
        provider_status[provider] = {"configured": available, "reason": reason}
    configured = [name for name, value in provider_status.items() if value["configured"]]
    return {
        "enabled": bool(config_value("search_broker_enabled", True)),
        "provider_chain": providers,
        "configured": configured,
        "providers": provider_status,
        "mode": str(config_value("search_broker_mode", "fallback")),
        "cache_enabled": bool(config_value("search_broker_cache_enabled", True)),
        "cache_ttl_seconds": _clamp_int(config_value("search_broker_cache_ttl_seconds", 900), 0, 86_400),
        "setup_hint": _setup_hint(configured),
    }


def format_results(payload: dict[str, Any], *, max_chars: int = 1200) -> str:
    """Format broker results for the existing chat/tool surface."""
    if not payload.get("query"):
        return "No query provided."
    results = payload.get("results") or []
    if not results:
        return str(payload.get("message") or "No results found for that query.")
    lines = []
    provider_label = ", ".join(payload.get("providers_succeeded") or payload.get("providers_attempted") or [])
    if provider_label:
        lines.append(f"Search results via {provider_label}:")
    for item in results:
        title = _clean(item.get("title") or "Untitled")
        snippet = _clean(item.get("snippet") or "")[:300]
        url = str(item.get("url") or "")
        provider = str(item.get("provider") or "")
        suffix = f" [{provider}]" if provider else ""
        lines.append(f"- {title}: {snippet} ({url}){suffix}")
    return "\n".join(lines)[:max_chars]


def _provider_functions() -> dict[str, Callable[[str, int], list[dict[str, Any]]]]:
    return {
        "brave": _search_brave,
        "google_cse": _search_google_cse,
        "tavily": _search_tavily,
        "serpapi": _search_serpapi,
        "duckduckgo": _search_duckduckgo,
    }


def _search_brave(query: str, limit: int) -> list[dict[str, Any]]:
    key = _env_key("search_broker_brave_api_key_env", "BRAVE_SEARCH_API_KEY")
    url = str(config_value("search_broker_brave_base_url", "https://api.search.brave.com/res/v1/web/search"))
    data = _request_json(
        "get",
        url,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": key,
        },
        params={
            "q": query,
            "count": min(20, max(1, limit)),
            "country": str(config_value("search_broker_country", "us")).lower(),
            "search_lang": str(config_value("search_broker_language", "en")).lower(),
            "safesearch": "strict" if bool(config_value("search_broker_safe_search", True)) else "off",
        },
    )
    items = ((data.get("web") or {}).get("results") or data.get("results") or []) if isinstance(data, dict) else []
    results = []
    for rank, item in enumerate(items, start=1):
        results.append(
            _result(
                title=item.get("title"),
                url=item.get("url"),
                snippet=item.get("description") or item.get("snippet"),
                provider="brave",
                rank=rank,
                published_at=item.get("age") or item.get("page_age") or "",
            )
        )
    return [item for item in results if item["url"]]


def _search_google_cse(query: str, limit: int) -> list[dict[str, Any]]:
    key = _env_key("search_broker_google_api_key_env", "GOOGLE_SEARCH_API_KEY")
    cx = _env_key("search_broker_google_cx_env", "GOOGLE_SEARCH_CX")
    url = str(config_value("search_broker_google_base_url", "https://www.googleapis.com/customsearch/v1"))
    data = _request_json(
        "get",
        url,
        params={
            "key": key,
            "cx": cx,
            "q": query,
            "num": min(10, max(1, limit)),
            "hl": str(config_value("search_broker_language", "en")).lower(),
            "gl": str(config_value("search_broker_country", "us")).lower(),
            "safe": "active" if bool(config_value("search_broker_safe_search", True)) else "off",
        },
    )
    items = data.get("items") or [] if isinstance(data, dict) else []
    results = []
    for rank, item in enumerate(items, start=1):
        results.append(
            _result(
                title=item.get("title"),
                url=item.get("link"),
                snippet=item.get("snippet"),
                provider="google_cse",
                rank=rank,
            )
        )
    return [item for item in results if item["url"]]


def _search_tavily(query: str, limit: int) -> list[dict[str, Any]]:
    key = _env_key("search_broker_tavily_api_key_env", "TAVILY_API_KEY")
    url = str(config_value("search_broker_tavily_base_url", "https://api.tavily.com/search"))
    body: dict[str, Any] = {
        "query": query,
        "max_results": min(20, max(1, limit)),
        "search_depth": str(config_value("search_broker_tavily_search_depth", "basic")),
        "topic": str(config_value("search_broker_tavily_topic", "general")),
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
        "include_favicon": True,
    }
    country = _clean(config_value("search_broker_tavily_country", ""))
    if country:
        body["country"] = country
    data = _request_json(
        "post",
        url,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        json_body=body,
    )
    items = data.get("results") or [] if isinstance(data, dict) else []
    results = []
    for rank, item in enumerate(items, start=1):
        results.append(
            _result(
                title=item.get("title"),
                url=item.get("url"),
                snippet=item.get("content"),
                provider="tavily",
                rank=rank,
                provider_score=item.get("score"),
            )
        )
    return [item for item in results if item["url"]]


def _search_serpapi(query: str, limit: int) -> list[dict[str, Any]]:
    key = _env_key("search_broker_serpapi_api_key_env", "SERPAPI_API_KEY")
    url = str(config_value("search_broker_serpapi_base_url", "https://serpapi.com/search.json"))
    data = _request_json(
        "get",
        url,
        params={
            "engine": "google",
            "q": query,
            "api_key": key,
            "num": min(10, max(1, limit)),
            "hl": str(config_value("search_broker_language", "en")).lower(),
            "gl": str(config_value("search_broker_country", "us")).lower(),
            "safe": "active" if bool(config_value("search_broker_safe_search", True)) else "off",
        },
    )
    items = data.get("organic_results") or [] if isinstance(data, dict) else []
    results = []
    for rank, item in enumerate(items, start=1):
        results.append(
            _result(
                title=item.get("title"),
                url=item.get("link"),
                snippet=item.get("snippet"),
                provider="serpapi",
                rank=int(item.get("position") or rank),
                published_at=item.get("date") or "",
            )
        )
    return [item for item in results if item["url"]]


def _search_duckduckgo(query: str, limit: int) -> list[dict[str, Any]]:
    if not _legacy_search_allowed():
        raise SearchProviderError("legacy DuckDuckGo fallback is disabled")
    if DDGS is not None:
        try:
            try:
                ddgs_context = DDGS(timeout=_clamp_int(config_value("research_search_timeout", 8), 1, 60))
            except TypeError:
                ddgs_context = DDGS()
            with ddgs_context as ddgs:
                items = list(ddgs.text(query, max_results=max(1, limit)))
        except Exception:
            items = []
    else:
        items = []
    if not items:
        return _search_duckduckgo_html(query, limit)
    results = []
    for rank, item in enumerate(items, start=1):
        results.append(
            _result(
                title=item.get("title"),
                url=item.get("href") or item.get("url"),
                snippet=item.get("body"),
                provider="duckduckgo",
                rank=rank,
            )
        )
    return [item for item in results if item["url"]]


def _search_duckduckgo_html(query: str, limit: int) -> list[dict[str, Any]]:
    if _requests is None:
        raise SearchProviderError("requests is not installed")
    timeout = _clamp_int(config_value("search_broker_request_timeout_seconds", 12), 1, 120)
    try:
        response = _requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": "Friday/0.2 (+local research broker)"},
            timeout=timeout,
        )
        status_code = int(getattr(response, "status_code", 200) or 200)
        if status_code >= 400:
            raise SearchProviderError(f"HTTP {status_code}")
        html_text = str(getattr(response, "text", "") or "")
    except Exception as exc:
        raise SearchProviderError(f"duckduckgo html fallback failed: {_short(str(exc), 180)}") from exc
    anchors = re.findall(
        r'<a[^>]+class=["\'][^"\']*result__a[^"\']*["\'][^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<title>.*?)</a>',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    results = []
    for rank, match in enumerate(anchors[: max(1, limit)], start=1):
        href, title_html = match
        url = _duckduckgo_result_url(href)
        if not url:
            continue
        results.append(
            _result(
                title=_strip_html(title_html),
                url=url,
                snippet=_duckduckgo_snippet_near(html_text, href),
                provider="duckduckgo",
                rank=rank,
            )
        )
    return [item for item in results if item["url"]]


def _request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if _requests is None:
        raise SearchProviderError("requests is not installed")
    timeout = _clamp_int(config_value("search_broker_request_timeout_seconds", 12), 1, 120)
    if method == "post":
        response = _requests.post(url, headers=headers or {}, json=json_body or {}, timeout=timeout)
    else:
        response = _requests.get(url, headers=headers or {}, params=params or {}, timeout=timeout)
    status_code = int(getattr(response, "status_code", 200) or 200)
    if status_code >= 400:
        raise SearchProviderError(f"HTTP {status_code}")
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise SearchProviderError("provider returned non-object JSON")
    return data


def _provider_chain(providers: str | list[str] | None) -> list[str]:
    raw = providers
    explicit = raw is not None and raw != ""
    if raw is None or raw == "":
        raw = str(config_value("search_broker_provider_chain", "brave>google_cse>tavily>serpapi"))
    if isinstance(raw, str):
        pieces = re.split(r"[>,;\s]+", raw)
    else:
        pieces = [str(item) for item in raw]
    output = []
    for piece in pieces:
        name = PROVIDER_ALIASES.get(piece.strip().lower(), piece.strip().lower())
        if name and name not in output:
            output.append(name)
    if not explicit and bool(config_value("search_broker_auto_legacy_fallback", True)) and "duckduckgo" not in output:
        output.append("duckduckgo")
    return [item for item in output if item in _provider_functions()]


def _provider_available(provider: str) -> tuple[bool, str]:
    if provider == "brave":
        return _has_env_key("search_broker_brave_api_key_env", "BRAVE_SEARCH_API_KEY")
    if provider == "google_cse":
        key_ok, key_reason = _has_env_key("search_broker_google_api_key_env", "GOOGLE_SEARCH_API_KEY")
        cx_ok, cx_reason = _has_env_key("search_broker_google_cx_env", "GOOGLE_SEARCH_CX")
        if key_ok and cx_ok:
            return True, "configured"
        return False, f"{key_reason}; {cx_reason}"
    if provider == "tavily":
        return _has_env_key("search_broker_tavily_api_key_env", "TAVILY_API_KEY")
    if provider == "serpapi":
        return _has_env_key("search_broker_serpapi_api_key_env", "SERPAPI_API_KEY")
    if provider == "duckduckgo":
        if not _legacy_search_allowed():
            return False, "legacy fallback disabled"
        return (DDGS is not None, "configured" if DDGS is not None else "duckduckgo-search not installed")
    return False, "unknown provider"


def _legacy_search_allowed() -> bool:
    return bool(config_value("search_broker_allow_legacy_fallback", False)) or bool(config_value("search_broker_auto_legacy_fallback", True))


def _has_env_key(config_key: str, default_env: str) -> tuple[bool, str]:
    env_name = str(config_value(config_key, default_env) or default_env)
    value = os.getenv(env_name, "")
    if _looks_configured_secret(value):
        return True, "configured"
    return False, f"missing {env_name}"


def _env_key(config_key: str, default_env: str) -> str:
    env_name = str(config_value(config_key, default_env) or default_env)
    value = os.getenv(env_name, "")
    if not _looks_configured_secret(value):
        raise SearchProviderError(f"missing {env_name}")
    return value


def _looks_configured_secret(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    lowered = text.lower()
    return not any(marker in lowered for marker in ("your_key", "placeholder", "insert_", "xxxx", "changeme"))


def _result(
    *,
    title: Any,
    url: Any,
    snippet: Any,
    provider: str,
    rank: int,
    published_at: Any = "",
    provider_score: Any = None,
) -> dict[str, Any]:
    clean_url = _clean_url(url)
    return {
        "title": _clean(title),
        "url": clean_url,
        "snippet": _clean(snippet)[:800],
        "provider": provider,
        "rank": max(1, int(rank or 1)),
        "score": 0.0,
        "published_at": _clean(published_at),
        "domain": _domain(clean_url),
        "_provider_score": _float(provider_score, 0.0),
    }


def _dedupe_and_rank(results: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    best_by_url: dict[str, dict[str, Any]] = {}
    for item in results:
        url = str(item.get("url") or "")
        if not url:
            continue
        key = _canonical_url(url)
        scored = dict(item)
        scored["domain"] = scored.get("domain") or _domain(url)
        scored["score"] = _rank_score(scored, query)
        previous = best_by_url.get(key)
        if previous is None or float(scored["score"]) > float(previous.get("score") or 0.0):
            best_by_url[key] = scored
    ranked = sorted(best_by_url.values(), key=lambda item: float(item.get("score") or 0.0), reverse=True)
    for item in ranked:
        item.pop("_provider_score", None)
        item["score"] = round(float(item.get("score") or 0.0), 4)
    return ranked


def _rank_score(item: dict[str, Any], query: str) -> float:
    rank = max(1, int(item.get("rank") or 1))
    score = max(0.05, 1.0 - (rank - 1) * 0.06)
    score += _float(item.get("_provider_score"), 0.0)
    if not bool(config_value("search_broker_rerank_enabled", True)):
        return score
    query_tokens = _tokens(query)
    title_tokens = _tokens(item.get("title"))
    snippet_tokens = _tokens(item.get("snippet"))
    if query_tokens:
        title_overlap = len(query_tokens & title_tokens) / len(query_tokens)
        snippet_overlap = len(query_tokens & snippet_tokens) / len(query_tokens)
        score += title_overlap * 0.35
        score += snippet_overlap * 0.15
    domain = str(item.get("domain") or "")
    if domain.endswith(".gov") or domain.endswith(".edu"):
        score += 0.14
    if any(part in domain for part in ("docs.", "developer.", "learn.", "support.")):
        score += 0.08
    boosts = config_value("search_broker_domain_boosts", {})
    if isinstance(boosts, dict):
        for suffix, boost in boosts.items():
            if domain.endswith(str(suffix).lower()):
                score += _float(boost, 0.0)
    if str(item.get("url") or "").lower().startswith("https://"):
        score += 0.02
    return score


def _cache_key(query: str, limit: int, providers: list[str], mode: str) -> str:
    key_data = {
        "query": query.lower(),
        "limit": limit,
        "providers": providers,
        "mode": mode,
        "country": str(config_value("search_broker_country", "us")),
        "language": str(config_value("search_broker_language", "en")),
        "safe": bool(config_value("search_broker_safe_search", True)),
    }
    raw = json.dumps(key_data, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(cache_key: str) -> dict[str, Any] | None:
    ttl = _clamp_int(config_value("search_broker_cache_ttl_seconds", 900), 0, 86_400)
    if ttl <= 0:
        return None
    try:
        with _connect() as conn:
            row = conn.execute("SELECT created_at, response_json FROM search_cache WHERE cache_key = ?", (cache_key,)).fetchone()
    except Exception:
        return None
    if not row:
        return None
    if time.time() - float(row[0] or 0.0) > ttl:
        return None
    try:
        payload = json.loads(row[1])
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _cache_put(cache_key: str, payload: dict[str, Any]) -> None:
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO search_cache(cache_key, created_at, response_json)
                VALUES (?, ?, ?)
                """,
                (cache_key, time.time(), json.dumps(payload, ensure_ascii=True)),
            )
    except Exception:
        return


def _connect() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS search_cache (
            cache_key TEXT PRIMARY KEY,
            created_at REAL NOT NULL,
            response_json TEXT NOT NULL
        )
        """
    )
    return conn


def _message(
    results: list[dict[str, Any]],
    providers: list[str],
    attempted: list[str],
    skipped: list[dict[str, str]],
    errors: list[dict[str, str]],
) -> str:
    if results:
        return f"Found {len(results)} result(s)."
    if not attempted:
        missing = ", ".join(item["provider"] for item in skipped[:4])
        return f"No dedicated search API keys are configured for: {missing or ', '.join(providers)}."
    if errors:
        return "Dedicated search providers failed: " + "; ".join(f"{item['provider']}: {item['error']}" for item in errors[:3])
    return "No results found for that query."


def _setup_hint(configured: list[str]) -> str:
    if configured:
        return f"Configured dedicated search provider(s): {', '.join(configured)}."
    return "Add BRAVE_SEARCH_API_KEY, GOOGLE_SEARCH_API_KEY plus GOOGLE_SEARCH_CX, TAVILY_API_KEY, or SERPAPI_API_KEY to .env."


def _empty(query: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "query": query,
        "results": [],
        "providers": [],
        "providers_attempted": [],
        "providers_succeeded": [],
        "providers_skipped": [],
        "errors": [],
        "cached": False,
        "message": message,
        "generated_at": int(time.time()),
    }


def _canonical_url(url: str) -> str:
    parsed = urlparse(url)
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=False)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
    ]
    cleaned = parsed._replace(
        scheme=parsed.scheme.lower() or "https",
        netloc=parsed.netloc.lower(),
        path=parsed.path.rstrip("/") or "/",
        query=urlencode(sorted(query_pairs), doseq=True),
        fragment="",
    )
    return urlunparse(cleaned)


def _clean_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if not parsed.scheme:
        text = "https://" + text
    return text


def _duckduckgo_result_url(href: str) -> str:
    raw = html.unescape(str(href or "").strip())
    if not raw:
        return ""
    if raw.startswith("//"):
        raw = "https:" + raw
    elif raw.startswith("/"):
        raw = "https://duckduckgo.com" + raw
    parsed = urlparse(raw)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    return query.get("uddg") or raw


def _duckduckgo_snippet_near(html_text: str, href: str) -> str:
    index = html_text.find(href)
    if index < 0:
        return ""
    window = html_text[index : index + 1800]
    snippet = re.search(
        r'<a[^>]+class=["\'][^"\']*result__snippet[^"\']*["\'][^>]*>(?P<text>.*?)</a>',
        window,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not snippet:
        snippet = re.search(
            r'<div[^>]+class=["\'][^"\']*result__snippet[^"\']*["\'][^>]*>(?P<text>.*?)</div>',
            window,
            flags=re.IGNORECASE | re.DOTALL,
        )
    return _strip_html(snippet.group("text")) if snippet else ""


def _strip_html(value: str) -> str:
    return _clean(value)


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _tokens(value: Any) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]{3,}", str(value or "").lower()) if token}


def _clean(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return " ".join(html.unescape(text).strip().split())


def _short(value: Any, limit: int = 160) -> str:
    text = _clean(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp_int(value: Any, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = low
    return max(low, min(high, parsed))

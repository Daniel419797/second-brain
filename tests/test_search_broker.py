from __future__ import annotations

from pathlib import Path

from core import search_broker


class FakeResponse:
    def __init__(self, data, status_code: int = 200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._data


def _config(extra: dict[str, object]):
    defaults = {
        "search_broker_enabled": True,
        "search_broker_provider_chain": "brave>google_cse>tavily>serpapi",
        "search_broker_mode": "fallback",
        "search_broker_max_results": 5,
        "search_broker_min_results_before_fallback": 1,
        "search_broker_cache_enabled": False,
        "search_broker_cache_ttl_seconds": 900,
        "search_broker_request_timeout_seconds": 5,
        "search_broker_country": "us",
        "search_broker_language": "en",
        "search_broker_safe_search": True,
    }
    defaults.update(extra)
    return lambda key, default=None: defaults.get(key, default)


def test_brave_provider_normalizes_results(monkeypatch, tmp_path: Path):
    calls = {}

    class FakeRequests:
        @staticmethod
        def get(url, headers=None, params=None, timeout=None):
            calls["url"] = url
            calls["headers"] = headers
            calls["params"] = params
            return FakeResponse({"web": {"results": [{"title": "<b>Docs</b>", "url": "https://example.com", "description": "Official &amp; useful"}]}})

    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "brave-key")
    monkeypatch.setattr(search_broker, "DB_PATH", tmp_path / "search.sqlite3")
    monkeypatch.setattr(search_broker, "_requests", FakeRequests)
    monkeypatch.setattr(search_broker, "config_value", _config({"search_broker_provider_chain": "brave"}))

    payload = search_broker.search("official docs", providers="brave", limit=3)

    assert payload["ok"] is True
    assert payload["providers_succeeded"] == ["brave"]
    assert payload["results"][0]["title"] == "Docs"
    assert payload["results"][0]["snippet"] == "Official & useful"
    assert calls["headers"]["X-Subscription-Token"] == "brave-key"
    assert calls["params"]["q"] == "official docs"


def test_google_cse_requires_key_and_engine_and_normalizes(monkeypatch, tmp_path: Path):
    class FakeRequests:
        @staticmethod
        def get(url, headers=None, params=None, timeout=None):
            assert params["key"] == "google-key"
            assert params["cx"] == "engine-id"
            return FakeResponse({"items": [{"title": "Result", "link": "https://example.org/page", "snippet": "Snippet"}]})

    monkeypatch.setenv("GOOGLE_SEARCH_API_KEY", "google-key")
    monkeypatch.setenv("GOOGLE_SEARCH_CX", "engine-id")
    monkeypatch.setattr(search_broker, "DB_PATH", tmp_path / "search.sqlite3")
    monkeypatch.setattr(search_broker, "_requests", FakeRequests)
    monkeypatch.setattr(search_broker, "config_value", _config({"search_broker_provider_chain": "google_cse"}))

    payload = search_broker.search("python", providers="google_cse", limit=2)

    assert payload["ok"] is True
    assert payload["results"][0]["provider"] == "google_cse"
    assert payload["results"][0]["url"] == "https://example.org/page"


def test_tavily_provider_uses_bearer_auth(monkeypatch, tmp_path: Path):
    calls = {}

    class FakeRequests:
        @staticmethod
        def post(url, headers=None, json=None, timeout=None):
            calls["headers"] = headers
            calls["json"] = json
            return FakeResponse({"results": [{"title": "Tavily", "url": "https://example.net", "content": "Content", "score": 0.7}]})

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-key")
    monkeypatch.setattr(search_broker, "DB_PATH", tmp_path / "search.sqlite3")
    monkeypatch.setattr(search_broker, "_requests", FakeRequests)
    monkeypatch.setattr(search_broker, "config_value", _config({"search_broker_provider_chain": "tavily"}))

    payload = search_broker.search("agent search", providers="tavily", limit=4)

    assert payload["ok"] is True
    assert calls["headers"]["Authorization"] == "Bearer tvly-key"
    assert calls["json"]["max_results"] == 4
    assert payload["results"][0]["provider"] == "tavily"


def test_dedupes_tracking_urls_and_prefers_higher_score(monkeypatch):
    monkeypatch.setattr(search_broker, "config_value", _config({}))
    ranked = search_broker._dedupe_and_rank(
        [
            {"title": "Weak", "url": "https://example.com/page?utm_source=x", "snippet": "nothing", "provider": "a", "rank": 5, "score": 0, "domain": "example.com", "_provider_score": 0},
            {"title": "Official Python Docs", "url": "https://example.com/page", "snippet": "python official docs", "provider": "b", "rank": 1, "score": 0, "domain": "example.com", "_provider_score": 0.2},
        ],
        "python docs",
    )

    assert len(ranked) == 1
    assert ranked[0]["title"] == "Official Python Docs"
    assert "_provider_score" not in ranked[0]


def test_cache_reuses_successful_payload(monkeypatch, tmp_path: Path):
    calls = {"count": 0}

    class FakeRequests:
        @staticmethod
        def get(url, headers=None, params=None, timeout=None):
            calls["count"] += 1
            return FakeResponse({"web": {"results": [{"title": "Cached", "url": "https://example.com", "description": "Once"}]}})

    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "brave-key")
    monkeypatch.setattr(search_broker, "DB_PATH", tmp_path / "search.sqlite3")
    monkeypatch.setattr(search_broker, "_requests", FakeRequests)
    monkeypatch.setattr(search_broker, "config_value", _config({"search_broker_provider_chain": "brave", "search_broker_cache_enabled": True}))

    first = search_broker.search("cache me", providers="brave", limit=2)
    second = search_broker.search("cache me", providers="brave", limit=2)

    assert first["ok"] is True
    assert second["cached"] is True
    assert calls["count"] == 1


def test_missing_dedicated_keys_reports_setup_hint(monkeypatch, tmp_path: Path):
    for key in ["BRAVE_SEARCH_API_KEY", "GOOGLE_SEARCH_API_KEY", "GOOGLE_SEARCH_CX", "TAVILY_API_KEY", "SERPAPI_API_KEY"]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(search_broker, "DB_PATH", tmp_path / "search.sqlite3")
    monkeypatch.setattr(search_broker, "config_value", _config({"search_broker_provider_chain": "brave>google_cse"}))

    payload = search_broker.search("anything", providers="brave>google_cse", limit=2)

    assert payload["ok"] is False
    assert "No dedicated search API keys" in payload["message"]
    assert "brave" in payload["providers_skipped"][0]["provider"]


def test_default_chain_adds_duckduckgo_fallback_without_api_keys(monkeypatch, tmp_path: Path):
    for key in ["BRAVE_SEARCH_API_KEY", "GOOGLE_SEARCH_API_KEY", "GOOGLE_SEARCH_CX", "TAVILY_API_KEY", "SERPAPI_API_KEY"]:
        monkeypatch.delenv(key, raising=False)

    class FakeDDGS:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def text(self, query, max_results=1):
            return [{"title": "Forum pain point", "href": "https://example.com/forum", "body": "Small teams need automation."}]

    monkeypatch.setattr(search_broker, "DB_PATH", tmp_path / "search.sqlite3")
    monkeypatch.setattr(search_broker, "DDGS", FakeDDGS)
    monkeypatch.setattr(search_broker, "config_value", _config({"search_broker_auto_legacy_fallback": True}))

    payload = search_broker.search("small team pain point", limit=2)

    assert payload["ok"] is True
    assert payload["providers_succeeded"] == ["duckduckgo"]
    assert payload["results"][0]["provider"] == "duckduckgo"

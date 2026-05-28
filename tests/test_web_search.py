from tools import web_search


def test_format_strips_html_and_limits_results():
    output = web_search._format([
        {"title": "Python", "body": "<b>Lists</b> are useful &amp; common.", "href": "https://example.com"}
    ])

    assert "<b>" not in output
    assert "Lists" in output
    assert "&amp;" not in output


def test_search_uses_search_broker(monkeypatch):
    calls = {"count": 0}

    def fake_search(query, limit=3, providers=None):
        calls["count"] += 1
        assert query == "python"
        assert limit == 3
        return {
            "ok": True,
            "query": query,
            "results": [{"title": "One", "snippet": "Body", "url": "https://example.com", "provider": "test"}],
            "providers_succeeded": ["test"],
        }

    monkeypatch.setattr(web_search.search_broker, "search", fake_search)

    output = web_search._search("python")

    assert "One" in output
    assert calls["count"] == 1


def test_search_returns_broker_setup_message(monkeypatch):
    monkeypatch.setattr(
        web_search.search_broker,
        "search",
        lambda query, limit=3, providers=None: {"ok": False, "query": query, "results": [], "message": "No dedicated search API keys are configured."},
    )

    assert "No dedicated search API keys" in web_search._search("python")

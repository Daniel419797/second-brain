from core import research


def test_read_html_strips_scripts():
    html = "<html><body><nav>menu</nav><h1>Title</h1><script>bad()</script><p>Hello world.</p></body></html>"

    text = research.read_html(html)

    assert "Title" in text
    assert "Hello world." in text
    assert "bad" not in text


def test_youtube_id_parses_common_urls():
    assert research._youtube_id("https://www.youtube.com/watch?v=abcdefghijk") == "abcdefghijk"
    assert research._youtube_id("https://youtu.be/abcdefghijk") == "abcdefghijk"


def test_research_topic_formats_search_results(monkeypatch):
    monkeypatch.setattr(
        research,
        "search_web",
        lambda query, limit=3: [{"title": "Docs", "url": "https://example.com", "snippet": "Official docs"}],
    )
    monkeypatch.setattr(research, "config_value", lambda key, default=None: False if key == "research_fetch_pages" else default)

    result = research.research_topic("official docs", limit=1)

    assert result["sources"][0]["title"] == "Docs"
    assert "Official docs" in result["notes"]

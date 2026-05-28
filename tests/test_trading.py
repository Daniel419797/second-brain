from tools import trading_tool


def test_get_price_formats_and_caches_yfinance(monkeypatch):
    trading_tool._price_cache.clear()
    calls = {"count": 0}

    class FakeYF:
        def Ticker(self, ticker):
            calls["count"] += 1
            return type(
                "Ticker",
                (),
                {"fast_info": {"last_price": 182.43, "regular_market_change_percent": 0.4, "last_volume": 1000}},
            )()

    monkeypatch.setattr(trading_tool, "yf", FakeYF())

    first = trading_tool._get_price("AAPL")
    second = trading_tool._get_price("AAPL")

    assert "AAPL" in first
    assert "$182.43" in first
    assert second == first
    assert calls["count"] == 1


def test_alpha_vantage_price_fallback(monkeypatch):
    trading_tool._price_cache.clear()

    class BadYF:
        def Ticker(self, ticker):
            raise RuntimeError("down")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"Global Quote": {"05. price": "10.5", "10. change percent": "1.2%", "06. volume": "50"}}

    class FakeRequests:
        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setenv("ALPHA_VANTAGE_KEY", "key")
    monkeypatch.setattr(trading_tool, "yf", BadYF())
    monkeypatch.setattr(trading_tool, "requests", FakeRequests())

    assert "$10.50" in trading_tool._get_price("AAPL")


def test_news_uses_alpha_vantage_and_llm(monkeypatch):
    trading_tool._news_cache.clear()

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"feed": [{"title": "AAPL rises", "summary": "Shares moved higher."}]}

    class FakeRequests:
        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setenv("ALPHA_VANTAGE_KEY", "key")
    monkeypatch.setattr(trading_tool, "requests", FakeRequests())
    monkeypatch.setattr(trading_tool.llm, "ask_simple", lambda prompt: "Apple shares moved higher.")

    assert trading_tool._get_news("AAPL") == "Apple shares moved higher."


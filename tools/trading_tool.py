"""Read-only market data tool."""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any

# TODO FR-12: RSI and moving average technical analysis - DEFERRED to v1.1

try:
    import yfinance as yf
except Exception:  # pragma: no cover - optional in scaffold tests
    yf = None

try:
    import requests
except Exception:  # pragma: no cover - optional in scaffold tests
    requests = None

from core import llm

_price_cache: dict[str, tuple[dict[str, Any], float]] = {}
_news_cache: dict[str, tuple[str, float]] = {}
PRICE_TTL = 60
NEWS_TTL = 600


def execute(inputs: dict[str, Any]) -> str:
    action = inputs.get("action", "price")
    ticker = str(inputs.get("ticker", "")).upper().strip()
    if action == "price":
        return _get_price(ticker)
    if action == "news":
        return _get_news(ticker)
    return "Unknown trading action."


def _get_price(ticker: str) -> str:
    if not ticker:
        return "No ticker provided."
    cached = _price_cache.get(ticker)
    if cached and time.time() - cached[1] < PRICE_TTL:
        return _format_price(ticker, cached[0])
    if yf is None:
        return _alpha_vantage_price(ticker)
    try:
        info = yf.Ticker(ticker).fast_info
        data = {
            "price": _field(info, "last_price", "lastPrice"),
            "change": _field(info, "regular_market_change_percent", "regularMarketChangePercent", default=0.0),
            "volume": _field(info, "last_volume", "shares", "regularMarketVolume", default=0),
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }
        _price_cache[ticker] = (data, time.time())
        return _format_price(ticker, data)
    except Exception:
        return _alpha_vantage_price(ticker)


def _get_news(ticker: str) -> str:
    if not ticker:
        return "No ticker provided."
    cached = _news_cache.get(ticker)
    if cached and time.time() - cached[1] < NEWS_TTL:
        return cached[0]
    if requests is None:
        return "News is unavailable because requests is not installed."
    key = os.getenv("ALPHA_VANTAGE_KEY")
    if not key:
        return "Alpha Vantage key is not configured."
    try:
        response = requests.get(
            "https://www.alphavantage.co/query",
            params={"function": "NEWS_SENTIMENT", "tickers": ticker, "limit": 5, "apikey": key},
            timeout=10,
        )
        response.raise_for_status()
        feed = response.json().get("feed", [])[:5]
        if not feed:
            return f"No market news found for {ticker}."
        raw = "\n".join(f"{item.get('title', '')}: {item.get('summary', '')}" for item in feed)
        brief = llm.ask_simple(f"Summarise these {ticker} market headlines in 2 sentences:\n{raw}") or raw[:500]
        _news_cache[ticker] = (brief, time.time())
        return brief
    except Exception:
        return "Market news is temporarily unavailable."


def _alpha_vantage_price(ticker: str) -> str:
    if requests is None:
        return "Market data is unavailable because requests is not installed."
    key = os.getenv("ALPHA_VANTAGE_KEY")
    if not key:
        return "Alpha Vantage key is not configured."
    try:
        response = requests.get(
            "https://www.alphavantage.co/query",
            params={"function": "GLOBAL_QUOTE", "symbol": ticker, "apikey": key},
            timeout=10,
        )
        response.raise_for_status()
        quote = response.json().get("Global Quote", {})
        price = float(quote.get("05. price", 0.0))
        change = float(str(quote.get("10. change percent", "0")).rstrip("%") or 0.0)
        volume = int(float(quote.get("06. volume", 0) or 0))
        data = {"price": price, "change": change, "volume": volume, "timestamp": datetime.now().strftime("%H:%M:%S")}
        _price_cache[ticker] = (data, time.time())
        return _format_price(ticker, data)
    except Exception:
        return f"Could not fetch market data for {ticker}."


def _format_price(ticker: str, data: dict[str, Any]) -> str:
    price = float(data.get("price") or 0.0)
    change = float(data.get("change") or 0.0)
    volume = data.get("volume") or 0
    ts = data.get("timestamp") or datetime.now().strftime("%H:%M:%S")
    return f"{ticker}: ${price:,.2f} ({change:+.2f}%) volume {volume:,} - as of {ts}"


def _field(source: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(source, dict) and name in source:
            return source[name]
        if hasattr(source, name):
            return getattr(source, name)
    return default


"""Research helpers for v2 agents: brokered web snippets, pages, PDFs, and YouTube transcripts."""

from __future__ import annotations

import io
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except Exception:  # pragma: no cover
    YouTubeTranscriptApi = None

from core import search_broker
from core.config import config_value


def research_topic(query: str, *, limit: int | None = None) -> dict[str, Any]:
    """Collect lightweight free context for an agent task."""
    query = _clean(query)
    if not query:
        return {"query": "", "sources": [], "notes": "No research query provided."}
    max_sources = int(limit or config_value("research_max_sources", 2))
    results = search_web(query, limit=max_sources)
    sources: list[dict[str, Any]] = []
    for result in results:
        url = str(result.get("url") or "")
        source = {
            "title": result.get("title", ""),
            "url": url,
            "snippet": result.get("snippet", ""),
            "text": "",
        }
        if url and bool(config_value("research_fetch_pages", False)):
            source["text"] = read_url(url, max_chars=int(config_value("research_page_chars", 1500)))
        sources.append(source)
    return {"query": query, "sources": sources, "notes": format_findings(sources)}


def search_web(query: str, *, limit: int = 3) -> list[dict[str, str]]:
    query = _clean(query)
    if not query:
        return []
    payload = search_broker.search(query, limit=max(1, int(limit)))
    if not payload.get("ok"):
        return []
    output: list[dict[str, str]] = []
    for item in (payload.get("results") or [])[:limit]:
        output.append(
            {
                "title": _clean(item.get("title", "")),
                "url": _clean(item.get("url") or ""),
                "snippet": _clean(item.get("snippet", ""))[:500],
            }
        )
    return output


def read_url(url: str, *, max_chars: int = 3000) -> str:
    if requests is None:
        return ""
    url = _clean(url)
    if not url:
        return ""
    try:
        response = requests.get(url, timeout=int(config_value("research_page_timeout", 10)), headers={"User-Agent": "Friday/0.2"})
        response.raise_for_status()
    except Exception:
        return ""
    content_type = response.headers.get("content-type", "").lower()
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        return read_pdf_bytes(response.content, max_chars=max_chars)
    return read_html(response.text, max_chars=max_chars)


def read_html(html: str, *, max_chars: int = 3000) -> str:
    if BeautifulSoup is None:
        text = re.sub(r"<(script|style|nav|footer|header)\b[^>]*>.*?</\1>", " ", html or "", flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        return _clean(text)[:max_chars]
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return _clean(soup.get_text(" "))[:max_chars]


def read_pdf_bytes(data: bytes, *, max_chars: int = 3000) -> str:
    if PdfReader is None or not data:
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        chunks = [(page.extract_text() or "") for page in reader.pages[:5]]
    except Exception:
        return ""
    return _clean(" ".join(chunks))[:max_chars]


def youtube_transcript(url_or_id: str, *, max_chars: int = 4000) -> str:
    if YouTubeTranscriptApi is None:
        return ""
    video_id = _youtube_id(url_or_id)
    if not video_id:
        return ""
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
    except Exception:
        return ""
    text = " ".join(_clean(item.get("text", "")) for item in transcript)
    return _clean(text)[:max_chars]


def format_findings(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return "No fresh research sources were found."
    lines = ["Fresh research context:"]
    for source in sources:
        title = source.get("title") or "Untitled"
        url = source.get("url") or ""
        snippet = source.get("text") or source.get("snippet") or ""
        lines.append(f"- {title}: {_clean(snippet)[:360]} ({url})")
    return "\n".join(lines)


def _youtube_id(url_or_id: str) -> str:
    value = _clean(url_or_id)
    if re.fullmatch(r"[\w-]{11}", value):
        return value
    parsed = urlparse(value)
    if parsed.hostname in {"youtu.be", "www.youtu.be"}:
        return parsed.path.strip("/")[:11]
    if "youtube" in str(parsed.hostname):
        query = parse_qs(parsed.query)
        if query.get("v"):
            return query["v"][0][:11]
        match = re.search(r"/(?:shorts|embed)/([\w-]{11})", parsed.path)
        if match:
            return match.group(1)
    return ""


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())

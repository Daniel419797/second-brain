"""Token-budget helpers for assembling compact LLM context."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.config import config_value

try:
    import tiktoken
except Exception:  # pragma: no cover - optional fallback
    tiktoken = None

Summarizer = Callable[[str], str | None]


def count_tokens(text: str) -> int:
    text = str(text or "")
    if not text:
        return 0
    if tiktoken is not None:
        try:
            encoding = tiktoken.get_encoding(str(config_value("context_token_encoding", "cl100k_base")))
            return len(encoding.encode(text))
        except Exception:
            pass
    return max(1, len(text.split()))


def fit_text(text: str, token_budget: int, summarizer: Summarizer | None = None) -> str:
    text = str(text or "").strip()
    if not text:
        return ""
    budget = max(1, int(token_budget))
    if count_tokens(text) <= budget:
        return text
    if summarizer is not None:
        try:
            summary = (summarizer(text) or "").strip()
        except Exception:
            summary = ""
        if summary and count_tokens(summary) <= budget:
            return summary
        if summary:
            text = summary
    return _rough_truncate(text, budget)


def build_context_sections(
    sections: list[dict[str, Any]],
    *,
    max_tokens: int | None = None,
    summarizer: Summarizer | None = None,
) -> str:
    total_budget = int(max_tokens or config_value("context_budget_max_tokens", 180000))
    remaining = max(1, total_budget)
    rendered: list[str] = []
    for section in sections:
        title = str(section.get("title") or "Context").strip()
        text = str(section.get("text") or "").strip()
        if not text:
            continue
        budget = min(int(section.get("budget") or remaining), remaining)
        if budget <= 0:
            break
        body = fit_text(text, budget, summarizer=summarizer)
        if not body:
            continue
        block = f"{title}:\n{body}"
        block_tokens = count_tokens(block)
        if block_tokens > remaining:
            block = fit_text(block, remaining, summarizer=summarizer)
            block_tokens = count_tokens(block)
        rendered.append(block)
        remaining -= block_tokens
        if remaining <= 0:
            break
    return "\n\n".join(rendered)


def within_budget(text: str, max_tokens: int | None = None) -> bool:
    return count_tokens(text) <= int(max_tokens or config_value("context_budget_max_tokens", 180000))


def _rough_truncate(text: str, token_budget: int) -> str:
    words = text.split()
    if not words:
        return text[: max(1, token_budget * 4)]
    # English text averages under 1.5 tokens per word for this use; keep margin.
    word_budget = max(1, int(token_budget * 0.65))
    if len(words) <= word_budget:
        return " ".join(words)
    return " ".join(words[:word_budget]) + " ..."

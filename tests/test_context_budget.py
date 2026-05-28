from core import context_budget


def test_fit_text_uses_summarizer_before_truncating(monkeypatch):
    monkeypatch.setattr(context_budget, "count_tokens", lambda text: len(str(text).split()))

    result = context_budget.fit_text("one two three four five", 2, summarizer=lambda text: "short text")

    assert result == "short text"


def test_build_context_sections_stays_under_budget(monkeypatch):
    monkeypatch.setattr(context_budget, "count_tokens", lambda text: len(str(text).split()))

    context = context_budget.build_context_sections(
        [
            {"title": "A", "text": "one two three four five", "budget": 3},
            {"title": "B", "text": "six seven", "budget": 4},
        ],
        max_tokens=10,
    )

    assert "A:" in context
    assert context_budget.count_tokens(context) <= 10

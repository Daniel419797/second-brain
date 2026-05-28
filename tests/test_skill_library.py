from core import skill_library


def test_skill_library_add_search_and_reinforce(monkeypatch, tmp_path):
    monkeypatch.setattr(skill_library, "SKILLS_PATH", tmp_path / "skills.json")
    monkeypatch.setattr(skill_library, "EXAMPLES_PATH", tmp_path / "examples.json")

    skill_id = skill_library.add_skill(
        "research free api",
        "Find free API options",
        "Search official docs, compare limits, then summarize tradeoffs.",
        agent_id="research_analyst",
        tags=["api", "research"],
    )

    results = skill_library.search("free API research", agent_id="research_analyst")

    assert results[0]["id"] == skill_id
    assert skill_library.get_skill(skill_id)["usage_count"] == 1


def test_record_examples_promotes_procedural_skill(monkeypatch, tmp_path):
    monkeypatch.setattr(skill_library, "SKILLS_PATH", tmp_path / "skills.json")
    monkeypatch.setattr(skill_library, "EXAMPLES_PATH", tmp_path / "examples.json")
    monkeypatch.setattr(skill_library, "config_value", lambda key, default=None: 2 if key == "procedural_skill_min_examples" else default)

    assert skill_library.record_example("qa_engineer", "write pytest tests", "Summary: first pass") is None
    promoted = skill_library.record_example("qa_engineer", "write pytest tests", "Summary: second pass")

    assert promoted is not None
    assert promoted["agent_id"] == "qa_engineer"
    assert "pytest" in promoted["pattern"].lower()

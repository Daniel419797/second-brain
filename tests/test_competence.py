from core import competence


def test_competence_infers_topics_and_flags_weakness(monkeypatch, tmp_path):
    monkeypatch.setattr(competence, "COMPETENCE_PATH", tmp_path / "competence.json")
    monkeypatch.setattr(
        competence,
        "config_value",
        lambda key, default=None: {"general": 0.5, "python": 0.4} if key == "competence_map_template" else 0.5 if key == "competence_research_threshold" else default,
    )

    weak = competence.weakest_topics("junior_developer", "write a Python pytest test")

    assert weak[0]["topic"] == "python"
    assert weak[0]["score"] == 0.4


def test_competence_record_result_updates_scores(monkeypatch, tmp_path):
    monkeypatch.setattr(competence, "COMPETENCE_PATH", tmp_path / "competence.json")
    monkeypatch.setattr(
        competence,
        "config_value",
        lambda key, default=None: {"general": 0.5, "python": 0.5} if key == "competence_map_template" else 0.2 if key == "competence_learning_rate" else default,
    )

    updated = competence.record_result("senior_developer", "fix Python code", success_score=1.0)

    assert updated["python"] == 0.6
    assert competence.get_agent_map("senior_developer")["python"] == 0.6

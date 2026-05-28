from core import (
    contextual_workspace,
    emotion_tone,
    learning_coach,
    offline_survival,
    personal_crm,
    personal_data_timeline,
    research_briefings,
    skill_library,
    skill_training_studio,
)


def _isolate(monkeypatch, tmp_path):
    modules = [
        contextual_workspace,
        emotion_tone,
        learning_coach,
        offline_survival,
        personal_crm,
        personal_data_timeline,
        research_briefings,
        skill_training_studio,
    ]
    for module in modules:
        monkeypatch.setattr(module, "DB_PATH", tmp_path / f"{module.__name__.split('.')[-1]}.sqlite3")
    monkeypatch.setattr(skill_library, "SKILLS_PATH", tmp_path / "skills.json")
    monkeypatch.setattr(skill_library, "EXAMPLES_PATH", tmp_path / "skill_examples.json")


def test_emotion_tone_detects_frustration_and_adjusts(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    result = emotion_tone.analyze_text("This is wrong and it did not work!")
    adjusted = emotion_tone.adjust_reply("This is wrong and it did not work!", "I will check it.")

    assert result["tone"] == "frustrated"
    assert result["should_adjust_reply"] is True
    assert adjusted.startswith("I hear you.")


def test_emotion_tone_avoids_common_false_positives(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    current = emotion_tone.analyze_text("what is going on right now")
    debugging = emotion_tone.analyze_text("what is wrong with this code?")
    short_reply = emotion_tone.adjust_reply("please answer quickly", "It is 4:20 PM.")

    assert current["tone"] == "neutral"
    assert debugging["tone"] in {"confused", "neutral"}
    assert short_reply == "It is 4:20 PM."


def test_emotion_tone_tracks_confused_and_tired_guidance(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    confused = emotion_tone.response_guidance("Wait what do you mean?")
    tired = emotion_tone.analyze_text("I'm exhausted, please keep it simple.")

    assert confused["tone"] == "confused"
    assert "clarify" in confused["need"]
    assert tired["tone"] == "tired"
    assert "light" in tired["need"]


def test_personal_crm_tracks_people_and_followups(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    person = personal_crm.remember_person("Ada", relationship="friend", notes="Likes design")
    interaction = personal_crm.record_interaction("Ada", "Promised to send mockups", follow_up_at="2999-01-01T09:00:00", promise="Send mockups")
    overdue = personal_crm.record_interaction("Ada", "Promised to reply yesterday", follow_up_at="2000-01-01T09:00:00", promise="Reply")

    assert person["name"] == "Ada"
    assert interaction["promise"] == "Send mockups"
    followups = personal_crm.upcoming_followups()
    assert followups[0]["person_name"] == "Ada"
    assert followups[0]["follow_up_state"] == "overdue"
    assert overdue["promise"] == "Reply"


def test_learning_coach_spaced_repetition(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    card = learning_coach.add_card("Python", "What is a list?", "An ordered mutable collection.")
    quiz = learning_coach.quiz("Python")
    updated = learning_coach.record_answer(card["id"], "collection", correct=True)
    grade = learning_coach.grade_answer(card["id"], "An ordered mutable collection")

    assert quiz["cards"][0]["prompt"] == "What is a list?"
    assert updated["interval_days"] >= 2
    assert grade["correct"] is True


def test_learning_coach_rejects_empty_cards(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    try:
        learning_coach.add_card("Python", "", "answer")
    except ValueError as exc:
        assert "prompt" in str(exc)
    else:
        raise AssertionError("empty prompt should fail")


def test_research_briefing_can_generate_without_network(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(research_briefings.research, "research_topic", lambda topic, max_sources=3: {"notes": "- Finding one\n- Finding two"})

    research_briefings.subscribe("free AI APIs")
    briefing = research_briefings.generate("free AI APIs")

    assert "Finding one" in briefing["summary"]
    assert research_briefings.summary()["topics"]


def test_contextual_workspace_and_offline_survival(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    (project / "package.json").write_text('{"scripts":{"dev":"next dev"}}', encoding="utf-8")
    (project / "README.md").write_text("TODO: document auth", encoding="utf-8")
    monkeypatch.setattr(contextual_workspace.project_autopilot, "inspect_project", lambda root, run_tests=False: {"issues": [{"summary": "Docs stale"}]})

    context = contextual_workspace.prepare_context(project)
    mode = offline_survival.activate("test")

    assert context["next_tasks"]
    assert mode["mode"] == "offline_survival"


def test_personal_data_timeline_and_skill_training(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    note = personal_data_timeline.record_note("Worked on Friday", "Implemented skill training.")
    found = personal_data_timeline.query("what did I work on today")
    workflow = skill_training_studio.start_workflow("Deploy Next.js", description="Deploy my web app", tags=["deploy"])
    workflow = skill_training_studio.add_step(workflow["id"], "Run npm build", expected_result="Build passes")
    published = skill_training_studio.finish_workflow(workflow["id"])

    assert note["title"] == "Worked on Friday"
    assert found["items"]
    assert published["skill_id"]
    assert skill_library.search("deploy next")[0]["id"] == published["skill_id"]

from tools import coding_tool


def test_answer_question_uses_llm(monkeypatch):
    monkeypatch.setattr(coding_tool.llm, "ask_simple", lambda prompt: "Use sorted().")

    assert coding_tool._answer_question("How do I sort a list?") == "Use sorted()."


def test_review_file_rejects_exe():
    assert "Cannot review" in coding_tool._review_file("C:\\Users\\me\\tool.exe")


def test_review_file_rejects_large_file(tmp_path, monkeypatch):
    path = tmp_path / "large.py"
    path.write_text("x" * (coding_tool.MAX_FILE_BYTES + 1), encoding="utf-8")
    monkeypatch.setattr(coding_tool, "_is_safe_path", lambda value: True)

    assert "exceeds 50KB" in coding_tool._review_file(str(path))


def test_review_file_returns_llm_review(tmp_path, monkeypatch):
    path = tmp_path / "script.py"
    path.write_text("print('hello')", encoding="utf-8")
    monkeypatch.setattr(coding_tool, "_is_safe_path", lambda value: True)
    monkeypatch.setattr(coding_tool.llm, "ask_simple", lambda prompt: "Looks fine.")

    assert coding_tool._review_file(str(path)) == "Looks fine."


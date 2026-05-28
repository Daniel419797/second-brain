"""Coding question and file review tool."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core import llm

ALLOWED_EXTENSIONS = {".py", ".js", ".ts", ".html", ".css", ".json", ".md", ".txt", ".yaml", ".yml", ".sql", ".sh", ".bat"}
MAX_FILE_BYTES = 50 * 1024


def execute(inputs: dict[str, Any]) -> str:
    action = inputs.get("action", "qa")
    if action == "qa":
        return _answer_question(str(inputs.get("question", "")))
    if action == "review":
        return _review_file(str(inputs.get("file_path", "")))
    return "Unknown coding action."


def _answer_question(question: str) -> str:
    if not question.strip():
        return "No coding question provided."
    prompt = "Answer concisely in under 150 words. No markdown, no code blocks - this will be spoken aloud.\n\n" + question
    return llm.ask_simple(prompt) or "Could not get an answer."


def _review_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        _audit("review_file", path, False, {"reason": "extension"})
        return f"Cannot review {ext or 'files without extensions'} files. Allowed: {allowed}"
    if not _is_safe_path(path):
        _audit("review_file", path, False, {"reason": "path"})
        return "Access denied: path is outside home directory."
    target = Path(path)
    if not target.exists():
        _audit("review_file", path, False, {"reason": "missing"})
        return f"File not found: {path}"
    size = target.stat().st_size
    if size > MAX_FILE_BYTES:
        _audit("review_file", path, False, {"reason": "size", "bytes": size})
        return f"File is {size // 1024}KB - exceeds 50KB limit. Please pass a smaller file."
    code = target.read_text(encoding="utf-8", errors="ignore")
    prompt = "Review this code for bugs, style issues, and improvements:\n\n" + code
    result = llm.ask_simple(prompt) or "Could not review file."
    _audit("review_file", path, bool(result), {"bytes": size})
    return result


def _is_safe_path(path: str) -> bool:
    try:
        real = Path(path).expanduser().resolve()
        home = Path.home().resolve()
        return str(real).lower().startswith(str(home).lower())
    except Exception:
        return False


def _audit(action: str, target: str, success: bool, details: dict[str, Any] | None = None) -> None:
    try:
        from core import audit_log

        audit_log.record(
            actor="friday",
            category="coding",
            action=action,
            target=target,
            success=success,
            details=details or {},
        )
    except Exception:
        return

"""Per-agent competence maps for v2 metacognitive memory."""

from __future__ import annotations

import datetime as dt
import json
import re
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, config_value, ensure_runtime_dirs

COMPETENCE_PATH = DATA_DIR / "competence_map.json"
_LOCK = threading.Lock()

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "python": ("python", "pytest", "script", "code", "function", "class", "bug", "refactor"),
    "windows_pc_control": ("windows", "app", "chrome", "gmail", "camera", "mouse", "keyboard", "desktop", "screen"),
    "web_research": ("research", "search", "web", "docs", "documentation", "blog", "paper", "pdf", "youtube"),
    "testing": ("test", "qa", "regression", "pytest", "coverage", "acceptance"),
    "security": ("security", "vulnerability", "threat", "cve", "auth", "jwt", "password", "owasp"),
    "devops": ("deploy", "docker", "ci", "server", "railway", "render", "postgres", "fastapi"),
    "ui_ux": ("ui", "ux", "frontend", "design", "wireframe", "layout", "accessibility"),
    "product": ("requirements", "roadmap", "feature", "user story", "priority", "product"),
    "project_management": ("schedule", "deadline", "status", "blocker", "sprint", "task queue"),
    "data_analysis": ("data", "dataset", "analysis", "chart", "model", "metric", "csv"),
    "speech_to_text": ("speech", "stt", "transcription", "whisper", "groq", "microphone", "audio"),
    "llm_routing": ("llm", "ollama", "gemini", "openrouter", "anthropic", "model", "prompt"),
}


def get_agent_map(agent_id: str) -> dict[str, float]:
    maps = _load()
    agent = _clean_agent(agent_id)
    if agent not in maps:
        maps[agent] = _template()
        _save(maps)
    return {key: float(value) for key, value in maps.get(agent, {}).items()}


def infer_topics(text: str) -> list[str]:
    lowered = str(text or "").lower()
    topics: list[str] = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            topics.append(topic)
    return topics or ["general"]


def weakest_topics(agent_id: str, text: str, *, threshold: float | None = None) -> list[dict[str, Any]]:
    agent_map = get_agent_map(agent_id)
    cutoff = float(threshold if threshold is not None else config_value("competence_research_threshold", 0.5))
    weak: list[dict[str, Any]] = []
    for topic in infer_topics(text):
        score = float(agent_map.get(topic, agent_map.get("general", 0.5)))
        if score < cutoff:
            weak.append({"topic": topic, "score": round(score, 3), "threshold": cutoff})
    return weak


def update_score(agent_id: str, topic: str, delta: float, *, reason: str = "") -> float:
    agent = _clean_agent(agent_id)
    cleaned_topic = _clean_topic(topic)
    with _LOCK:
        maps = _load()
        agent_map = maps.setdefault(agent, _template())
        current = float(agent_map.get(cleaned_topic, agent_map.get("general", 0.5)))
        updated = max(0.0, min(1.0, round(current + float(delta), 4)))
        agent_map[cleaned_topic] = updated
        meta = maps.setdefault("_metadata", {})
        meta[f"{agent}:{cleaned_topic}"] = {
            "updated_at": _now(),
            "reason": str(reason or "")[:240],
        }
        _save(maps)
    return updated


def record_result(agent_id: str, text: str, *, success_score: float = 1.0) -> dict[str, float]:
    delta = (max(0.0, min(1.0, float(success_score))) - 0.5) * float(config_value("competence_learning_rate", 0.1))
    updated: dict[str, float] = {}
    for topic in infer_topics(text):
        updated[topic] = update_score(agent_id, topic, delta, reason="task_result")
    return updated


def prompt_summary(agent_id: str, text: str) -> str:
    topics = infer_topics(text)
    agent_map = get_agent_map(agent_id)
    weak = weakest_topics(agent_id, text)
    scores = ", ".join(f"{topic}={agent_map.get(topic, agent_map.get('general', 0.5)):.2f}" for topic in topics)
    if weak:
        gaps = ", ".join(f"{item['topic']}={item['score']:.2f}" for item in weak)
        return f"Competence map: {scores}. Knowledge gaps below threshold: {gaps}. Research or verify before acting."
    return f"Competence map: {scores}."


def all_maps() -> dict[str, Any]:
    return _load()


def wipe_all() -> None:
    with _LOCK:
        if COMPETENCE_PATH.exists():
            COMPETENCE_PATH.unlink()


def _template() -> dict[str, float]:
    raw = config_value("competence_map_template", {"general": 0.5})
    if not isinstance(raw, dict):
        return {"general": 0.5}
    return {_clean_topic(key): float(value) for key, value in raw.items()}


def _load() -> dict[str, Any]:
    ensure_runtime_dirs()
    if not COMPETENCE_PATH.exists():
        return {}
    try:
        data = json.loads(COMPETENCE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(value: dict[str, Any]) -> None:
    ensure_runtime_dirs()
    COMPETENCE_PATH.write_text(json.dumps(value, indent=2, ensure_ascii=True), encoding="utf-8")


def _clean_agent(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_]+", "_", str(value or "jarvis").lower()).strip("_")
    return cleaned or "jarvis"


def _clean_topic(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_]+", "_", str(value or "general").lower()).strip("_")
    return cleaned or "general"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

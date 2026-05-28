"""Named app-screen memory on top of vision skill learning."""

from __future__ import annotations

from typing import Any

from core import vision_skill_learning


def learn_screen(
    app: str,
    screen_label: str,
    *,
    cues: list[str] | str | None = None,
    meaning: str = "",
    action_hint: str = "",
    source: str = "manual",
) -> dict[str, Any]:
    item = vision_skill_learning.learn_pattern(
        app or "unknown_app",
        screen_label or "unknown screen",
        pattern_type="screen",
        visual_cues=cues,
        meaning=meaning or f"{screen_label} screen in {app}",
        action_hint=action_hint,
        confidence=0.72,
        metadata={"source": source, "v2": True},
    )
    item["summary"] = f"Learned screen memory for {item['app']}: {item['label']}."
    return item


def recognize(app: str = "", query: str = "", limit: int = 10) -> dict[str, Any]:
    result = vision_skill_learning.recognize(app=app, query=query, limit=limit)
    result["summary"] = result.get("summary") or "No screen memory matched."
    return result


def status() -> dict[str, Any]:
    base = vision_skill_learning.summary()
    return {"patterns": base.get("recent", []), "by_app": base.get("by_app", {}), "summary": f"Visual Skill Memory v2: {base.get('summary', 'ready')}"}


def wipe_all() -> None:
    vision_skill_learning.wipe_all()

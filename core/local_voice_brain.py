"""Free/offline voice intelligence: wake aliases, command style, and transcript repairs."""

from __future__ import annotations

from typing import Any

from core import barge_in, personal_command_memory, voice_command_repair, voice_reliability

FRIDAY_ALIASES = ["freddie", "freddy", "fred", "friady", "friiday", "friyday", "fryday", "friday"]


def install_defaults() -> dict[str, Any]:
    command_defaults = personal_command_memory.install_default_language()
    repairs = []
    for alias in FRIDAY_ALIASES:
        repairs.append(voice_command_repair.record_repair("Friday", alias, backend="local_voice_brain", context="default wake-name alias"))
    return {"command_defaults": command_defaults, "wake_alias_repairs": repairs, "summary": f"Installed voice defaults and {len(repairs)} wake-name aliases."}


def repair(heard: str, expected: str, *, source: str = "local_voice_brain") -> dict[str, Any]:
    result = voice_command_repair.record_repair(expected, heard, backend=source, context="local voice brain repair")
    if expected and heard and expected.lower() != heard.lower():
        _maybe_learn_command(heard, expected)
    return result


def tune_wake_name(alias: str) -> dict[str, Any]:
    clean_alias = _clean(alias)
    if not clean_alias:
        return {"ok": False, "summary": "No wake-name alias was provided."}
    return voice_command_repair.record_repair("Friday", clean_alias, backend="local_voice_brain", context="manual wake-name tuning")


def status() -> dict[str, Any]:
    reliability = voice_reliability.summary()
    commands = personal_command_memory.summary(limit=8)
    repairs = voice_command_repair.suggestions(limit=12)
    return {
        "voice_reliability": reliability,
        "command_memory": commands,
        "repairs": repairs,
        "barge_in_requested": barge_in.is_requested(),
        "summary": f"Local voice brain ready: {len(repairs.get('corrections') or [])} corrections, {commands.get('count', 0)} command shortcut(s).",
    }


def _maybe_learn_command(heard: str, expected: str) -> None:
    heard_clean = _clean(heard)
    expected_clean = _clean(expected)
    if not heard_clean or not expected_clean:
        return
    if any(word in expected_clean.lower() for word in ("volume", "brightness", "start work", "check friday", "ship it")):
        try:
            personal_command_memory.learn(heard_clean, expected_clean, notes="learned from voice repair", confidence=0.68)
        except Exception:
            return


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())

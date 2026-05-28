"""Shared data contracts for Friday's brain-inspired cognition layer."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorldEntity:
    entity_type: str
    name: str
    state: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    last_seen_at: str = ""


@dataclass
class ActiveGoal:
    title: str
    description: str = ""
    status: str = "active"
    priority: int = 5
    progress: float = 0.0
    source: str = "user"
    id: int | None = None


@dataclass
class AttentionState:
    name_strictness: float = 0.5
    followup_window_seconds: float = 8.0
    false_positive_rate: float = 0.0
    false_negative_rate: float = 0.0
    background_noise_score: float = 0.0
    profile: dict[str, Any] = field(default_factory=dict)


@dataclass
class AffectiveState:
    state: str = "calm"
    arousal: float = 0.2
    confidence: float = 0.7
    frustration: float = 0.0
    focus: float = 0.5
    reason: str = ""


@dataclass
class ReflectionRecord:
    category: str
    finding: str
    severity: int = 1
    evidence: dict[str, Any] = field(default_factory=dict)
    recommended_change: str = ""


@dataclass
class LearningRecord:
    kind: str
    topic: str
    content: str
    confidence: float = 0.5
    evidence_count: int = 1
    source: str = "reflection"


@dataclass
class CognitiveSnapshot:
    timestamp: str
    source: str
    summary: str
    active_app: str = ""
    active_window: str = ""
    visible_state: dict[str, Any] = field(default_factory=dict)
    user_state: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def clamp01(value: Any, default: float = 0.5) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def to_dict(value: Any) -> dict[str, Any]:
    if dataclasses.is_dataclass(value):
        return _json_safe(dataclasses.asdict(value))
    if isinstance(value, dict):
        return _json_safe(value)
    return {"value": _json_safe(value)}


def to_json(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=True, sort_keys=True, default=str)


def from_json(value: str, default: Any = None) -> Any:
    try:
        return json.loads(value or "{}")
    except Exception:
        return {} if default is None else default


def _json_safe(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return _json_safe(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)

"""Emotion and tone awareness for Friday's conversation layer."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "emotion_tone.sqlite3"
_LOCK = threading.Lock()

TONE_PROFILES: dict[str, dict[str, Any]] = {
    "frustrated": {
        "need": "acknowledge the problem, verify before claiming success, and avoid defensiveness",
        "prefix": "I hear you. ",
        "keywords": (
            ("frustrated", 1.4),
            ("annoyed", 1.2),
            ("angry", 1.2),
            ("mad", 1.0),
            ("upset", 1.0),
            ("lying", 1.8),
            ("you lied", 2.0),
            ("friday is lying", 2.2),
            ("not what i said", 1.8),
            ("i said", 0.9),
            ("that's wrong", 1.5),
            ("that is wrong", 1.5),
            ("wrong answer", 1.2),
            ("didn't work", 1.5),
            ("did not work", 1.5),
            ("not working", 1.4),
            ("still didn't", 1.4),
            ("still did not", 1.4),
            ("stupid", 1.0),
            ("hate", 1.0),
            ("fuck", 1.2),
            ("damn", 0.9),
        ),
    },
    "confused": {
        "need": "slow down, clarify assumptions, and explain the next step plainly",
        "prefix": "Let me clarify. ",
        "keywords": (
            ("wait what", 1.8),
            ("what do you mean", 1.6),
            ("i don't understand", 1.8),
            ("i do not understand", 1.8),
            ("confused", 1.5),
            ("not clear", 1.2),
            ("explain again", 1.3),
            ("why", 0.45),
            ("how come", 0.7),
        ),
    },
    "tired": {
        "need": "keep it light, reduce cognitive load, and offer one concrete next step",
        "prefix": "I'll keep this light. ",
        "keywords": (
            ("tired", 1.5),
            ("sleepy", 1.4),
            ("exhausted", 1.6),
            ("drained", 1.4),
            ("burnt out", 1.5),
            ("burned out", 1.5),
            ("weak", 0.8),
            ("no energy", 1.4),
            ("stressful", 0.9),
            ("stressed", 1.1),
        ),
    },
    "rushed": {
        "need": "be brief, lead with the answer, and postpone optional detail",
        "prefix": "Short version: ",
        "keywords": (
            ("quickly", 1.4),
            ("quick answer", 1.4),
            ("fast answer", 1.3),
            ("hurry", 1.5),
            ("urgent", 1.5),
            ("asap", 1.5),
            ("now now", 1.2),
            ("immediately", 1.2),
            ("don't stop until", 1.1),
            ("do not stop until", 1.1),
        ),
    },
    "worried": {
        "need": "be steady, avoid alarmism, and separate facts from uncertainty",
        "prefix": "Steady. ",
        "keywords": (
            ("worried", 1.4),
            ("scared", 1.4),
            ("afraid", 1.2),
            ("anxious", 1.3),
            ("panic", 1.4),
            ("i'm scared", 1.6),
            ("i am scared", 1.6),
        ),
    },
    "excited": {
        "need": "match positive energy briefly while staying useful",
        "prefix": "",
        "keywords": (
            ("i love it", 1.5),
            ("amazing", 1.1),
            ("awesome", 1.1),
            ("perfect", 0.8),
            ("great", 0.7),
            ("nice", 0.7),
            ("let's go", 0.8),
        ),
    },
    "calm": {
        "need": "respond normally and stay concise",
        "prefix": "",
        "keywords": (
            ("thanks", 0.9),
            ("thank you", 1.0),
            ("okay", 0.55),
            ("sure", 0.55),
            ("cool", 0.6),
            ("good", 0.45),
        ),
    },
}


def init_db(path: Path | None = None) -> None:
    ensure_runtime_dirs()
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=10) as conn:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tone_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                text TEXT NOT NULL,
                tone TEXT NOT NULL,
                confidence REAL NOT NULL,
                intensity REAL NOT NULL,
                signals_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tone_events_time ON tone_events(timestamp)")


def analyze_text(text: str, *, store: bool = True) -> dict[str, Any]:
    cleaned = _clean(text)
    lowered = cleaned.lower()
    scores = {tone: 0.0 for tone in TONE_PROFILES}
    signals: dict[str, list[dict[str, Any]]] = {tone: [] for tone in TONE_PROFILES}
    for tone, profile in TONE_PROFILES.items():
        for keyword, weight in profile["keywords"]:
            if _contains_phrase(lowered, keyword):
                scores[tone] += float(weight)
                signals[tone].append({"signal": keyword, "weight": float(weight)})
    _add_punctuation_signals(cleaned, scores, signals)
    _add_shape_signals(cleaned, lowered, scores, signals)
    scores = _apply_context_guards(cleaned, lowered, scores, signals)
    tone, raw_score = max(scores.items(), key=lambda item: item[1])
    sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    runner_up = sorted_scores[1][1] if len(sorted_scores) > 1 else 0.0
    if raw_score <= 0.05:
        tone = "neutral"
        raw_score = 0.0
        runner_up = 0.0
        confidence = 0.5
    else:
        confidence = _confidence(raw_score, runner_up, scores)
    intensity = min(1.0, raw_score / 4.0)
    secondary = [
        {"tone": name, "score": round(score, 3)}
        for name, score in sorted_scores
        if name != tone and score >= 0.7
    ][:3]
    policy = response_policy_for_tone(tone, confidence, intensity, secondary_tones=secondary)
    result = {
        "timestamp": _now(),
        "text": cleaned,
        "tone": tone,
        "confidence": round(confidence, 3),
        "intensity": round(intensity, 3),
        "scores": {key: round(value, 3) for key, value in scores.items() if value > 0},
        "signals": {key: value for key, value in signals.items() if value},
        "secondary_tones": secondary,
        "need": policy["need"],
        "response_style": policy["response_style"],
        "should_adjust_reply": policy["should_adjust_reply"],
        "summary": _summary(tone, confidence, intensity, policy["need"]),
    }
    if store and bool(config_value("emotion_tone_enabled", True)):
        _store(result)
    return result


def response_policy_for_tone(tone: str, confidence: float, intensity: float, *, secondary_tones: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    profile = TONE_PROFILES.get(tone) or {}
    minimum_confidence = float(config_value("emotion_tone_adjust_min_confidence", 0.72))
    minimum_intensity = float(config_value("emotion_tone_adjust_min_intensity", 0.25))
    should_adjust = bool(tone not in {"neutral", "calm", "excited"} and confidence >= minimum_confidence and intensity >= minimum_intensity)
    style = {
        "tone": tone,
        "pace": "brief" if tone == "rushed" else "normal",
        "warmth": "high" if tone in {"frustrated", "tired", "worried", "confused"} else "normal",
        "do": profile.get("need") or "respond normally and stay concise",
        "avoid": "Do not diagnose feelings; say what the signal suggests and stay evidence-based.",
        "secondary_tones": secondary_tones or [],
    }
    return {
        "need": profile.get("need") or "respond normally and stay concise",
        "prefix": str(profile.get("prefix") or ""),
        "response_style": style,
        "should_adjust_reply": should_adjust,
    }


def adjust_reply(user_text: str, reply: str) -> str:
    """Make high-signal tone adjustments without bloating normal replies."""
    if not bool(config_value("emotion_tone_adjust_replies", True)):
        return reply
    tone = analyze_text(user_text, store=False)
    if not tone.get("should_adjust_reply"):
        return reply
    label = tone.get("tone")
    policy = response_policy_for_tone(str(label), float(tone.get("confidence") or 0), float(tone.get("intensity") or 0), secondary_tones=tone.get("secondary_tones") or [])
    prefix = str(policy.get("prefix") or "")
    if not prefix:
        return reply
    if label == "rushed" and len(str(reply or "")) < int(config_value("emotion_tone_rushed_prefix_min_chars", 80)):
        return reply
    if _looks_like_sensitive_direct_result(reply):
        return reply
    return _prefix_once(reply, prefix)


def response_guidance(user_text: str) -> dict[str, Any]:
    """Return a non-diagnostic style policy that callers can pass to an LLM."""
    analysis = analyze_text(user_text, store=False)
    return {
        "tone": analysis["tone"],
        "confidence": analysis["confidence"],
        "intensity": analysis["intensity"],
        "need": analysis["need"],
        "response_style": analysis["response_style"],
        "should_adjust_reply": analysis["should_adjust_reply"],
        "summary": analysis["summary"],
    }
    return reply


def latest() -> dict[str, Any] | None:
    events = recent(limit=1)
    return events[0] if events else None


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM tone_events ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit))),)).fetchall()
    return [_row(row) for row in rows]


def summary() -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT tone, COUNT(*), AVG(confidence), AVG(intensity) FROM tone_events GROUP BY tone").fetchall()
    tones = {str(row[0]): {"count": int(row[1]), "avg_confidence": round(float(row[2] or 0), 3), "avg_intensity": round(float(row[3] or 0), 3)} for row in rows}
    latest_event = latest()
    trend = _trend(recent(limit=int(config_value("emotion_tone_recent_window", 12))))
    return {
        "enabled": bool(config_value("emotion_tone_enabled", True)),
        "tones": tones,
        "latest": latest_event,
        "trend": trend,
        "summary": f"Latest tone: {latest_event['tone']}; recent trend: {trend['dominant']}." if latest_event else "No tone events yet.",
    }


def tone_context() -> str:
    item = latest()
    if not item:
        return ""
    if float(item.get("confidence") or 0) < float(config_value("emotion_tone_context_min_confidence", 0.6)):
        return ""
    guidance = response_policy_for_tone(str(item.get("tone")), float(item.get("confidence") or 0), float(item.get("intensity") or 0), secondary_tones=item.get("secondary_tones") or [])
    return (
        f"User tone signal: {item['tone']} at {float(item['confidence']):.0%} confidence. "
        f"Style guidance: {guidance['need']}. Do not diagnose emotion; adapt gently."
    )


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM tone_events")


def _store(event: dict[str, Any]) -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            "INSERT INTO tone_events(timestamp, text, tone, confidence, intensity, signals_json) VALUES (?, ?, ?, ?, ?, ?)",
            (event["timestamp"], event["text"][:2000], event["tone"], float(event["confidence"]), float(event["intensity"]), _json_dumps(event.get("signals") or {})),
        )


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "text": str(row["text"]),
        "tone": str(row["tone"]),
        "confidence": float(row["confidence"]),
        "intensity": float(row["intensity"]),
        "signals": _json_loads(row["signals_json"], {}),
    }


def _prefix_once(reply: str, prefix: str) -> str:
    text = str(reply or "")
    return text if text.startswith(prefix.strip()) else prefix + text


def _contains_phrase(text: str, phrase: str) -> bool:
    phrase = str(phrase or "").lower().strip()
    if not phrase:
        return False
    if re.fullmatch(r"[a-z0-9_]+", phrase):
        return bool(re.search(rf"\b{re.escape(phrase)}\b", text))
    return phrase in text


def _add_punctuation_signals(cleaned: str, scores: dict[str, float], signals: dict[str, list[dict[str, Any]]]) -> None:
    exclamations = cleaned.count("!")
    question_marks = cleaned.count("?")
    if exclamations:
        weight = min(1.2, exclamations * 0.25)
        scores["frustrated"] += weight
        signals["frustrated"].append({"signal": "exclamation", "weight": round(weight, 3)})
    if question_marks >= 2:
        weight = min(0.7, question_marks * 0.15)
        scores["confused"] += weight
        signals["confused"].append({"signal": "repeated_question_marks", "weight": round(weight, 3)})


def _add_shape_signals(cleaned: str, lowered: str, scores: dict[str, float], signals: dict[str, list[dict[str, Any]]]) -> None:
    words = cleaned.split()
    if len(words) <= 3 and lowered in {"ok", "okay", "sure", "thanks", "thank you"}:
        scores["calm"] += 0.7
        signals["calm"].append({"signal": "short_acknowledgement", "weight": 0.7})
    if re.search(r"\b(?:please|pls)\b", lowered) and re.search(r"\b(?:quickly|hurry|urgent|asap|immediately)\b", lowered):
        scores["rushed"] += 0.8
        signals["rushed"].append({"signal": "polite_urgency", "weight": 0.8})
    uppercase_words = [word for word in re.findall(r"\b[A-Z]{3,}\b", cleaned) if word not in {"API", "STT", "TTS", "CPU", "GPU", "PDF"}]
    if len(uppercase_words) >= 2:
        scores["frustrated"] += 0.5
        signals["frustrated"].append({"signal": "multiple_uppercase_words", "weight": 0.5})


def _apply_context_guards(cleaned: str, lowered: str, scores: dict[str, float], signals: dict[str, list[dict[str, Any]]]) -> dict[str, float]:
    guarded = dict(scores)
    if re.search(r"\bwhat\s+(?:is|'s|are)\b", lowered) and "right now" in lowered:
        guarded["rushed"] = min(guarded.get("rushed", 0.0), 0.2)
    if re.search(r"\bwhat(?:'s| is)\s+wrong\s+with\b", lowered):
        guarded["frustrated"] = max(0.0, guarded.get("frustrated", 0.0) - 0.9)
        guarded["confused"] += 0.6
        signals["confused"].append({"signal": "debugging_question", "weight": 0.6})
    if re.search(r"\bright now\b", lowered) and not re.search(r"\b(?:quickly|hurry|urgent|asap|immediately)\b", lowered):
        guarded["rushed"] = max(0.0, guarded.get("rushed", 0.0) - 0.4)
    return guarded


def _confidence(raw_score: float, runner_up: float, scores: dict[str, float]) -> float:
    total = sum(max(0.0, value) for value in scores.values()) or raw_score
    margin = max(0.0, raw_score - runner_up)
    confidence = 0.38 + (raw_score / (raw_score + 2.0)) * 0.38 + (margin / max(1.0, total)) * 0.2
    return round(max(0.35, min(0.96, confidence)), 3)


def _summary(tone: str, confidence: float, intensity: float, need: str) -> str:
    if tone == "neutral":
        return "Tone looks neutral; respond normally."
    confidence_word = "high" if confidence >= 0.82 else "medium" if confidence >= 0.65 else "low"
    return f"Tone signal: {tone} ({confidence_word} confidence, intensity {intensity:.0%}); {need}."


def _trend(items: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    weighted: dict[str, float] = {}
    for item in items:
        tone = str(item.get("tone") or "neutral")
        counts[tone] = counts.get(tone, 0) + 1
        weighted[tone] = weighted.get(tone, 0.0) + float(item.get("confidence") or 0) * max(0.25, float(item.get("intensity") or 0.25))
    dominant = max(weighted.items(), key=lambda pair: pair[1])[0] if weighted else "unknown"
    return {"dominant": dominant, "counts": counts, "weighted": {key: round(value, 3) for key, value in weighted.items()}}


def _looks_like_sensitive_direct_result(reply: str) -> bool:
    text = str(reply or "").strip().lower()
    if len(text) <= 80 and re.search(r"\b(?:volume set|current volume|it is|opened successfully|mode set|shutdown complete)\b", text):
        return True
    return False


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

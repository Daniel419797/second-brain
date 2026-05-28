"""Voice command repair layer for user corrections like 'No, I said ...'."""

from __future__ import annotations

import re
from typing import Any

from core import notification_center, personal_knowledge_vault, voice_reliability

CORRECTION_PATTERNS = [
    re.compile(r"^\s*(?:no|nah|actually|correction)[,\s]+(?:i\s+said\s+)?(?P<expected>.+)$", re.IGNORECASE),
    re.compile(r"^\s*i\s+said[,\s]+(?P<expected>.+)$", re.IGNORECASE),
    re.compile(r"^\s*what\s+i\s+said\s+was[,\s]+(?P<expected>.+)$", re.IGNORECASE),
]


def record_repair(expected_text: str, heard_text: str = "", *, backend: str = "voice_repair", context: str = "") -> dict[str, Any]:
    expected = _clean(expected_text)
    heard = _clean(heard_text)
    if not expected:
        return {"ok": False, "summary": "No corrected phrase was provided."}
    sample_id = voice_reliability.record_correction(expected, heard, backend=backend, metadata={"context": context})
    vault_item = personal_knowledge_vault.remember_correction(expected, heard, source="voice_repair")
    notification = notification_center.add(
        source="voice_repair",
        category="voice",
        severity=2,
        title="Voice correction learned",
        message=f"When Friday hears '{heard or 'a wrong phrase'}', prefer '{expected}'.",
        dedupe_key=f"voice-repair:{expected.lower()}:{heard.lower()}",
        metadata={"sample_id": sample_id, "vault_id": vault_item.get("id")},
    )
    return {
        "ok": True,
        "expected_text": expected,
        "heard_text": heard,
        "sample_id": sample_id,
        "vault_item": vault_item,
        "notification": notification,
        "summary": f"I learned the correction: {expected}.",
    }


def parse_and_record(user_text: str, *, last_heard: str = "") -> dict[str, Any]:
    text = _clean(user_text)
    for pattern in CORRECTION_PATTERNS:
        match = pattern.match(text)
        if match:
            expected = _strip_quotes(match.group("expected"))
            return record_repair(expected, last_heard, context=text)
    return {"ok": False, "summary": "That did not look like a voice correction.", "text": text}


def repair_text(text: str) -> dict[str, Any]:
    """Suggest a repaired transcript using stored voice corrections."""

    raw = _clean(text)
    if not raw:
        return {"changed": False, "text": raw, "summary": "No transcript to repair."}
    candidates = personal_knowledge_vault.search(raw, kind="correction", limit=50)
    best = None
    best_score = 0
    lowered = raw.lower()
    for item in candidates:
        metadata = item.get("metadata") or {}
        expected = _clean(metadata.get("expected") or "")
        heard = _clean(metadata.get("heard") or "")
        if not expected:
            continue
        score = 0
        if heard and heard.lower() in lowered:
            score = 100
        elif heard and _levenshtein(heard.lower(), lowered) <= max(2, len(heard) // 4):
            score = 80
        elif expected.lower() in lowered:
            score = 60
        if score > best_score:
            best = {"expected": expected, "heard": heard, "item": item}
            best_score = score
    if not best:
        return {"changed": False, "text": raw, "summary": "No learned repair matched."}
    repaired = best["expected"]
    return {"changed": repaired != raw, "text": repaired, "original": raw, "match": best, "summary": f"Repaired transcript to: {repaired}"}


def suggestions(limit: int = 20) -> dict[str, Any]:
    corrections = personal_knowledge_vault.list_items("correction", limit=limit)
    aliases = voice_reliability.learned_aliases(limit=limit)
    return {"corrections": corrections, "learned_aliases": aliases, "summary": f"{len(corrections)} command corrections stored."}


def _strip_quotes(value: str) -> str:
    text = _clean(value)
    if len(text) >= 2 and text[0] in {"'", '"'} and text[-1] == text[0]:
        return text[1:-1].strip()
    return text


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())

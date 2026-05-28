"""Learn and apply the user's design, coding, voice, and behavior taste."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import decision_memory, personal_knowledge_vault
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "personal_taste_engine.sqlite3"
_LOCK = threading.Lock()


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
            CREATE TABLE IF NOT EXISTS taste_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                domain TEXT NOT NULL,
                correction TEXT NOT NULL,
                rule TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence_json TEXT NOT NULL
            )
            """
        )


def learn_from_correction(correction: str, *, domain: str = "general", evidence: list[str] | None = None) -> dict[str, Any]:
    init_db()
    clean = _clean(correction)
    inferred_domain = _domain(clean, domain)
    rule = _rule(clean, inferred_domain)
    confidence = 0.82 if rule else 0.55
    rule = rule or f"When working in {inferred_domain}, ask for preference if the taste is ambiguous."
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO taste_rules(timestamp, domain, correction, rule, confidence, evidence_json) VALUES (?, ?, ?, ?, ?, ?)",
            (_now(), inferred_domain, clean[:2000], rule, confidence, _json_dumps(evidence or ["user_correction"])),
        )
        row = conn.execute("SELECT * FROM taste_rules WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    item = _row(row)
    _safe(lambda: decision_memory.remember(f"taste:{inferred_domain}", rule, evidence=evidence or [clean], confidence=confidence, source="taste_engine"), None)
    _safe(lambda: personal_knowledge_vault.remember_preference(f"Taste: {inferred_domain}", rule, confidence=confidence, tags=["taste", inferred_domain]), None)
    item["summary"] = f"Learned {inferred_domain} taste: {rule}"
    return item


def guidance(domain: str = "general", *, context: str = "", limit: int = 8) -> dict[str, Any]:
    items = search(domain=domain, query=context, limit=limit)
    rules = [item["rule"] for item in items]
    summary = "; ".join(rules[:3]) if rules else f"No strong {domain or 'general'} taste rules yet."
    return {"domain": domain or "general", "rules": rules, "items": items, "summary": summary}


def search(domain: str = "", query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    where: list[str] = []
    params: list[Any] = []
    if domain and domain != "general":
        where.append("domain=?")
        params.append(_clean(domain).lower())
    if query:
        like = f"%{_clean(query)}%"
        where.append("(correction LIKE ? OR rule LIKE ?)")
        params.extend([like, like])
    params.append(max(1, min(100, int(limit or 20))))
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM taste_rules {clause} ORDER BY confidence DESC, id DESC LIMIT ?", params).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT domain, COUNT(*) FROM taste_rules GROUP BY domain").fetchall()
    counts = {str(domain): int(count) for domain, count in rows}
    return {"counts": counts, "recent": search(limit=8), "summary": f"{sum(counts.values())} taste rule(s) learned."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM taste_rules")


def _domain(text: str, fallback: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ("ui", "design", "cleaner", "dashboard", "layout")):
        return "ui"
    if any(term in lowered for term in ("voice", "robotic", "sounds", "tts")):
        return "voice"
    if any(term in lowered for term in ("code", "readable", "performance", "maintainable")):
        return "coding"
    if any(term in lowered for term in ("talk", "reply", "ask", "too much", "direct")):
        return "behavior"
    return _clean(fallback).lower() or "general"


def _rule(text: str, domain: str) -> str:
    lowered = text.lower()
    if "too robotic" in lowered or "robotic" in lowered:
        return "Prefer natural, brief, human-sounding replies over stiff wording."
    if "too slow" in lowered or "slow" in lowered:
        return "Prefer fast, direct paths and avoid unnecessary model/tool calls."
    if "don't like this ui" in lowered or "dont like this ui" in lowered or "cleaner" in lowered:
        return "Prefer cleaner, denser, calmer UI with less decorative clutter."
    if "free" in lowered or "broke" in lowered:
        return "Prefer free/local tools first and avoid paid services unless approved."
    if "ask first" in lowered:
        return "Ask before risky, paid, private, or irreversible actions."
    return ""


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "domain": str(row["domain"]),
        "correction": str(row["correction"]),
        "rule": str(row["rule"]),
        "confidence": float(row["confidence"]),
        "evidence": _json_loads(row["evidence_json"], []),
    }


def _safe(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

"""Computer-vision skill memory for recurring UI patterns."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import app_state_memory, browser_extension_bridge, visual_monitor
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "vision_skill_learning.sqlite3"
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
            CREATE TABLE IF NOT EXISTS ui_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                app TEXT NOT NULL,
                label TEXT NOT NULL,
                pattern_type TEXT NOT NULL,
                visual_cues_json TEXT NOT NULL,
                dom_cues_json TEXT NOT NULL,
                accessibility_cues_json TEXT NOT NULL,
                meaning TEXT NOT NULL,
                action_hint TEXT NOT NULL,
                confidence REAL NOT NULL,
                successes INTEGER NOT NULL,
                failures INTEGER NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ui_patterns_app ON ui_patterns(app, pattern_type, confidence)")


def learn_pattern(
    app: str,
    label: str,
    *,
    pattern_type: str = "screen",
    visual_cues: list[Any] | str | None = None,
    dom_cues: list[Any] | str | None = None,
    accessibility_cues: list[Any] | str | None = None,
    meaning: str = "",
    action_hint: str = "",
    confidence: float = 0.65,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    app_id = _norm(app)
    label_text = _clean(label)[:300] or "unknown UI pattern"
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO ui_patterns(timestamp, app, label, pattern_type, visual_cues_json, dom_cues_json, accessibility_cues_json, meaning, action_hint, confidence, successes, failures, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
            """,
            (
                _now(),
                app_id,
                label_text,
                _clean(pattern_type).lower()[:80] or "screen",
                _json_dumps(_list(visual_cues)),
                _json_dumps(_list(dom_cues)),
                _json_dumps(_list(accessibility_cues)),
                _clean(meaning)[:1000] or label_text,
                _clean(action_hint)[:1000],
                _confidence(confidence),
                _json_dumps(metadata or {}),
            ),
        )
        row = conn.execute("SELECT * FROM ui_patterns WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    if action_hint:
        try:
            app_state_memory.remember_success(app_id, label_text, action_hint, context=meaning, notes="learned from vision skill memory")
        except Exception:
            pass
    return _row(row)


def observe_from_context(app: str = "", context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Learn obvious reusable UI anchors from browser/vision context."""

    context = dict(context or {})
    if not context:
        context = _safe(browser_extension_bridge.latest_page_insight, {})
    app_id = app or context.get("app") or context.get("title") or context.get("url") or "browser"
    learned: list[dict[str, Any]] = []
    for button in context.get("buttons") or []:
        label = button.get("text") or button.get("aria") or button.get("selector") or "button"
        learned.append(
            learn_pattern(
                app_id,
                label,
                pattern_type="button",
                dom_cues=[button.get("selector") or "", button.get("text") or ""],
                meaning=f"{label} button on {context.get('title') or context.get('url') or app_id}",
                action_hint=f"click {label}",
                confidence=0.72,
                metadata={"source": "browser_context"},
            )
        )
    for form in context.get("forms") or []:
        label = form.get("name") or form.get("id") or "form"
        learned.append(
            learn_pattern(
                app_id,
                label,
                pattern_type="form",
                dom_cues=[label, form.get("selector") or ""],
                meaning=f"Form usually needs safe DOM-level filling.",
                action_hint="inspect fields before filling; never fill passwords without approval",
                confidence=0.68,
                metadata={"source": "browser_context"},
            )
        )
    return {"learned": learned, "summary": f"Learned {len(learned)} UI pattern(s)."}


def recognize(app: str = "", query: str = "", limit: int = 10) -> dict[str, Any]:
    patterns = search(app=app, query=query, limit=limit)
    if patterns:
        top = patterns[0]
        summary = f"I recognize {top['label']} in {top['app']}: {top['meaning']}"
    else:
        summary = "No learned UI pattern matched yet."
    return {"patterns": patterns, "summary": summary}


def record_outcome(pattern_id: int, success: bool, notes: str = "") -> dict[str, Any]:
    init_db()
    field = "successes" if success else "failures"
    delta = 0.04 if success else -0.08
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            f"UPDATE ui_patterns SET {field}={field}+1, confidence=max(0.0, min(1.0, confidence + ?)), metadata_json=? WHERE id=?",
            (delta, _json_dumps({"last_note": _clean(notes)}), int(pattern_id)),
        )
        row = conn.execute("SELECT * FROM ui_patterns WHERE id=?", (int(pattern_id),)).fetchone()
    return _row(row) if row else {}


def search(app: str = "", query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    where: list[str] = []
    params: list[Any] = []
    if app:
        where.append("app=?")
        params.append(_norm(app))
    if query:
        like = f"%{_clean(query)}%"
        where.append("(label LIKE ? OR meaning LIKE ? OR action_hint LIKE ? OR visual_cues_json LIKE ? OR dom_cues_json LIKE ?)")
        params.extend([like, like, like, like, like])
    params.append(max(1, min(100, int(limit or 20))))
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM ui_patterns {clause} ORDER BY confidence DESC, id DESC LIMIT ?", params).fetchall()
    return [_row(row) for row in rows]


def summary(limit: int = 8) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT app, COUNT(*) FROM ui_patterns GROUP BY app ORDER BY COUNT(*) DESC").fetchall()
    by_app = {str(app): int(count) for app, count in rows}
    latest_visual = _safe(visual_monitor.status, {})
    return {"by_app": by_app, "recent": search(limit=limit), "visual_monitor": latest_visual, "summary": f"{sum(by_app.values())} learned UI pattern(s)."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM ui_patterns")


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "app": str(row["app"]),
        "label": str(row["label"]),
        "pattern_type": str(row["pattern_type"]),
        "visual_cues": _json_loads(row["visual_cues_json"], []),
        "dom_cues": _json_loads(row["dom_cues_json"], []),
        "accessibility_cues": _json_loads(row["accessibility_cues_json"], []),
        "meaning": str(row["meaning"]),
        "action_hint": str(row["action_hint"]),
        "confidence": float(row["confidence"]),
        "successes": int(row["successes"]),
        "failures": int(row["failures"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _safe(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _list(value: list[Any] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    return [_clean(value)] if _clean(value) else []


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", _clean(value).lower()).strip("_") or "unknown_app"


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.5


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

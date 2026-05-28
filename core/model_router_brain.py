"""Model router brain that chooses free/cheap/local providers per task."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import llm
from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "model_router_brain.sqlite3"
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
            CREATE TABLE IF NOT EXISTS model_route_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                task_type TEXT NOT NULL,
                provider TEXT NOT NULL,
                ok INTEGER NOT NULL,
                latency_ms INTEGER NOT NULL,
                quality REAL NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def choose_provider(task_type: str = "general", text: str = "", *, online: bool = True) -> dict[str, Any]:
    init_db()
    task_type = _clean(task_type).lower() or _infer_task_type(text)
    configured = _configured_route(task_type)
    chain = llm.provider_sequence(configured)
    if not online:
        chain = [provider for provider in chain if not llm.provider_is_online(provider)] or ["ollama"]
    usable = [provider for provider in chain if llm.provider_has_credentials(provider)]
    if not usable:
        usable = ["ollama"]
    scores = _provider_scores(task_type)
    usable.sort(key=lambda provider: (-scores.get(provider, 0.5), 0 if not llm.provider_is_online(provider) else -1))
    provider = usable[0]
    return {
        "task_type": task_type,
        "provider": provider,
        "chain": usable,
        "configured_route": configured,
        "provider_limits": llm.provider_limit_status(),
        "summary": f"Route {task_type} to {provider}, fallback chain: {' > '.join(usable)}.",
    }


def record_result(provider: str, task_type: str, *, ok: bool, latency_ms: int = 0, quality: float = 0.5, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            "INSERT INTO model_route_events(timestamp, task_type, provider, ok, latency_ms, quality, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), _clean(task_type).lower() or "general", _clean(provider).lower(), 1 if ok else 0, max(0, int(latency_ms or 0)), max(0.0, min(1.0, float(quality))), _json_dumps(metadata or {})),
        )
    return {"id": int(cursor.lastrowid), "summary": f"Recorded {provider} route result."}


def recent_events(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM model_route_events ORDER BY id DESC LIMIT ?", (max(1, min(500, int(limit))),)).fetchall()
    return [_row(row) for row in rows]


def summary() -> dict[str, Any]:
    scores = _provider_scores("general")
    status = llm.provider_limit_status()
    return {
        "scores": scores,
        "provider_limits": status,
        "routes": _routes(),
        "recent": recent_events(limit=10),
        "summary": "Model router is choosing online free/cheap providers first, with Ollama as local fallback.",
    }


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM model_route_events")


def _configured_route(task_type: str) -> str:
    routes = _routes()
    return str(routes.get(task_type) or routes.get("default") or config_value("v2_api_agent_online_providers", "nvidia>gemini>openrouter>anthropic") + ">ollama")


def _routes() -> dict[str, Any]:
    raw = config_value("model_router_routes", {})
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw or "{}"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {"default": "nvidia>gemini>openrouter>anthropic>ollama"}


def _provider_scores(task_type: str) -> dict[str, float]:
    events = recent_events(limit=300)
    scores: dict[str, list[float]] = {}
    for event in events:
        if event["task_type"] not in {task_type, "general"}:
            continue
        base = 1.0 if event["ok"] else 0.2
        latency_penalty = min(0.4, float(event["latency_ms"]) / 60000.0)
        score = max(0.0, min(1.0, (base + float(event["quality"])) / 2.0 - latency_penalty))
        scores.setdefault(event["provider"], []).append(score)
    defaults = {"nvidia": 0.82, "gemini": 0.78, "openrouter": 0.66, "anthropic": 0.76, "ollama": 0.55}
    for provider, values in scores.items():
        defaults[provider] = round(sum(values) / len(values), 3)
    return defaults


def _infer_task_type(text: str) -> str:
    lowered = str(text or "").lower()
    if any(term in lowered for term in ["code", "debug", "test", "python", "react"]):
        return "coding"
    if any(term in lowered for term in ["write", "email", "document", "summarize"]):
        return "writing"
    if any(term in lowered for term in ["math", "calculate", "solve"]):
        return "math"
    return "general"


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "task_type": str(row["task_type"]),
        "provider": str(row["provider"]),
        "ok": bool(row["ok"]),
        "latency_ms": int(row["latency_ms"]),
        "quality": float(row["quality"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


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

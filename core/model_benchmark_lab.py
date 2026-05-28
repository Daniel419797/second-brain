"""Local model benchmark lab for routing decisions without wasting quota by default."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import llm, model_router_brain
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "model_benchmark_lab.sqlite3"
_LOCK = threading.Lock()

DEFAULT_TASKS = {
    "coding": "Explain how to fix a failing Python test.",
    "writing": "Draft a concise project status update.",
    "math": "Solve 17 * 23 and explain briefly.",
    "fast_reply": "Answer 'what time is it?' style queries quickly.",
    "tool_planning": "Choose a safe tool plan for opening Gmail and reading visible state.",
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
            CREATE TABLE IF NOT EXISTS model_benchmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                task_type TEXT NOT NULL,
                provider TEXT NOT NULL,
                status TEXT NOT NULL,
                latency_ms INTEGER NOT NULL,
                quality REAL NOT NULL,
                summary TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def run_benchmark(task_types: list[str] | None = None, *, run_live: bool = False) -> dict[str, Any]:
    init_db()
    selected = [_clean(item).lower() for item in (task_types or list(DEFAULT_TASKS.keys())) if _clean(item)]
    results = [_benchmark_one(task_type, run_live=run_live) for task_type in selected]
    best = {item["task_type"]: item["provider"] for item in results}
    return {
        "ok": True,
        "run_live": bool(run_live),
        "results": results,
        "best_routes": best,
        "summary": f"Benchmarked {len(results)} task route(s); live API calls {'enabled' if run_live else 'skipped'}."
    }


def status() -> dict[str, Any]:
    recent = recent_results(limit=20)
    latest_by_task: dict[str, dict[str, Any]] = {}
    for item in recent:
        latest_by_task.setdefault(item["task_type"], item)
    return {
        "recent": recent[:8],
        "best_routes": {task: item["provider"] for task, item in latest_by_task.items()},
        "summary": f"{len(latest_by_task)} benchmark task type(s) have recent routes." if latest_by_task else "Model benchmark lab is ready.",
    }


def recent_results(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM model_benchmarks ORDER BY id DESC LIMIT ?", (max(1, min(200, int(limit or 50))),)).fetchall()
    return [_row(row) for row in rows]


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM model_benchmarks")


def _benchmark_one(task_type: str, *, run_live: bool) -> dict[str, Any]:
    route = model_router_brain.choose_provider(task_type, DEFAULT_TASKS.get(task_type, task_type))
    provider = route.get("provider") or "ollama"
    status = "simulated"
    latency_ms = _estimated_latency(provider, task_type)
    quality = _estimated_quality(provider, task_type)
    metadata = {"route": route, "run_live": run_live}
    if run_live:
        started = dt.datetime.now(dt.timezone.utc)
        text = llm.ask_simple_with_provider_chain(f"Benchmark task ({task_type}): {DEFAULT_TASKS.get(task_type, task_type)}", [provider], retries=1)
        latency_ms = int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000)
        status = "passed" if text else "failed"
        quality = 0.75 if text else 0.2
        metadata["sample"] = (text or "")[:500]
    model_router_brain.record_result(provider, task_type, ok=status != "failed", latency_ms=latency_ms, quality=quality, metadata={"source": "model_benchmark_lab"})
    summary = f"{task_type}: {provider} scored {quality:.2f} with {latency_ms}ms estimated latency."
    return _store(task_type, provider, status, latency_ms, quality, summary, metadata)


def _estimated_quality(provider: str, task_type: str) -> float:
    base = {"nvidia": 0.86, "gemini": 0.82, "anthropic": 0.80, "openrouter": 0.68, "ollama": 0.58}.get(str(provider), 0.55)
    if task_type == "fast_reply" and provider == "ollama":
        base += 0.08
    if task_type == "coding" and provider in {"nvidia", "anthropic"}:
        base += 0.04
    if task_type == "math" and provider in {"nvidia", "gemini"}:
        base += 0.03
    return round(max(0.0, min(1.0, base)), 3)


def _estimated_latency(provider: str, task_type: str) -> int:
    base = {"nvidia": 1800, "gemini": 1400, "anthropic": 2400, "openrouter": 2200, "ollama": 5500}.get(str(provider), 3000)
    return int(base * (0.65 if task_type == "fast_reply" else 1.0))


def _store(task_type: str, provider: str, status: str, latency_ms: int, quality: float, summary: str, metadata: dict[str, Any]) -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO model_benchmarks(timestamp, task_type, provider, status, latency_ms, quality, summary, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (_now(), task_type, provider, status, int(latency_ms), float(quality), summary, _json_dumps(metadata)),
        )
        row = conn.execute("SELECT * FROM model_benchmarks WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "task_type": str(row["task_type"]),
        "provider": str(row["provider"]),
        "status": str(row["status"]),
        "latency_ms": int(row["latency_ms"]),
        "quality": float(row["quality"]),
        "summary": str(row["summary"]),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


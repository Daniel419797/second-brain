"""Central durable run engine for Friday execution flows.

This module is intentionally small and boring: it gives every major Friday
workflow one shared run record, event log, artifact list, and status vocabulary.
Specialized modules can still own their domain logic, but they should register
their work here so Friday has one spine for truth, status, and proof.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
import traceback
from pathlib import Path
from typing import Any, Callable

from core import friday_trace, langgraph_backbone
from core.config import DATA_DIR, ensure_runtime_dirs

DB_PATH = DATA_DIR / "friday_runs.sqlite3"
STATUSES = {
    "created",
    "queued",
    "inspecting",
    "planning",
    "building",
    "verifying",
    "fixing",
    "blocked",
    "planned",
    "ready_to_patch",
    "technical_ready",
    "market_ready_blocked",
    "market_ready",
    "failed",
    "done",
}
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
            CREATE TABLE IF NOT EXISTS friday_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                request TEXT NOT NULL,
                root TEXT NOT NULL,
                target TEXT NOT NULL,
                status TEXT NOT NULL,
                phase TEXT NOT NULL,
                summary TEXT NOT NULL,
                output_json TEXT NOT NULL,
                artifacts_json TEXT NOT NULL,
                gaps_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS friday_run_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                phase TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES friday_runs(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_friday_runs_kind_status ON friday_runs(kind, status, updated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_friday_run_events_run ON friday_run_events(run_id, id)")


def create_run(
    kind: str,
    request: str,
    *,
    root: str | Path = "",
    target: str | Path = "",
    status: str = "created",
    phase: str = "created",
    summary: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    now = _now()
    normalized_status = _status(status)
    trace_id, trace_metadata = friday_trace.ensure_trace_id(metadata or {}, prefix=f"friday-{_clean(kind) or 'run'}")
    friday_trace.start_trace(trace_id, kind=_clean(kind) or "run", title=_clean(request), root=root, metadata=trace_metadata)
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO friday_runs(created_at, updated_at, kind, request, root, target, status, phase, summary, output_json, artifacts_json, gaps_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', '[]', '[]', ?)
            """,
            (
                now,
                now,
                _clean(kind) or "run",
                _clean(request),
                str(root or ""),
                str(target or ""),
                normalized_status,
                _clean(phase) or normalized_status,
                _clean(summary) or f"{_clean(kind) or 'Run'} queued.",
                _json_dumps(trace_metadata),
            ),
        )
        run_id = int(cursor.lastrowid)
        conn.execute(
            "INSERT INTO friday_run_events(run_id, timestamp, phase, status, summary, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, now, _clean(phase) or normalized_status, normalized_status, _clean(summary) or "Run created.", _json_dumps(trace_metadata)),
        )
        row = conn.execute("SELECT * FROM friday_runs WHERE id=?", (run_id,)).fetchone()
    friday_trace.record_event(
        trace_id,
        event_type="run_created",
        title=f"{_clean(kind) or 'run'} #{run_id}",
        summary=_clean(summary) or "Run created.",
        status=normalized_status,
        metadata={"run_id": run_id, "kind": _clean(kind) or "run"},
    )
    return _row(row)


def update_run(
    run_id: int,
    *,
    status: str | None = None,
    phase: str | None = None,
    summary: str | None = None,
    output: dict[str, Any] | None = None,
    artifacts: list[str] | None = None,
    gaps: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    init_db()
    current = get_run(run_id)
    if not current:
        return None
    merged_metadata = {**(current.get("metadata") or {}), **(metadata or {})}
    trace_id, merged_metadata = friday_trace.ensure_trace_id(merged_metadata, prefix=f"friday-run-{run_id}")
    friday_trace.start_trace(trace_id, kind=current.get("kind") or "run", title=current.get("request") or f"Friday run {run_id}", root=current.get("root") or "", metadata=merged_metadata)
    next_status = _status(status or current.get("status") or "created")
    next_phase = _clean(phase if phase is not None else current.get("phase")) or next_status
    next_summary = _clean(summary if summary is not None else current.get("summary"))
    next_output = output if output is not None else current.get("output") or {}
    next_artifacts = _dedupe([*(current.get("artifacts") or []), *(artifacts or [])])
    next_gaps = _dedupe(gaps if gaps is not None else current.get("gaps") or [])
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            UPDATE friday_runs
            SET updated_at=?, status=?, phase=?, summary=?, output_json=?, artifacts_json=?, gaps_json=?, metadata_json=?
            WHERE id=?
            """,
            (
                now,
                next_status,
                next_phase,
                next_summary,
                _json_dumps(next_output),
                _json_dumps(next_artifacts),
                _json_dumps(next_gaps),
                _json_dumps(merged_metadata),
                int(run_id),
            ),
        )
        conn.execute(
            "INSERT INTO friday_run_events(run_id, timestamp, phase, status, summary, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
            (int(run_id), now, next_phase, next_status, next_summary, _json_dumps({**(metadata or {}), "trace_id": trace_id})),
        )
        row = conn.execute("SELECT * FROM friday_runs WHERE id=?", (int(run_id),)).fetchone()
    friday_trace.record_event(
        trace_id,
        event_type="run_update",
        title=next_phase,
        summary=next_summary,
        status=next_status,
        metadata={"run_id": int(run_id), "phase": next_phase, **(metadata or {})},
    )
    return _row(row)


def start_background(
    kind: str,
    request: str,
    executor: Callable[[], dict[str, Any]],
    *,
    root: str | Path = "",
    target: str | Path = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run = create_run(kind, request, root=root, target=target, status="queued", phase="queued", summary=f"{kind} queued.", metadata=metadata)
    run_id = int(run["id"])
    run_metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else metadata or {}

    def _worker() -> None:
        try:
            _run_background_workflow(run_id, kind, request, executor, root=root, target=target, metadata=run_metadata)
        except Exception as exc:  # pragma: no cover - defensive background boundary
            update_run(
                run_id,
                status="failed",
                phase="failed",
                summary=f"{kind} failed: {exc}",
                output={"error": str(exc), "traceback": traceback.format_exc(limit=8)},
                gaps=[str(exc)],
            )

    thread = threading.Thread(target=_worker, name=f"friday-run-{run_id}", daemon=True)
    thread.start()
    return get_run(run_id) or run


def _run_background_workflow(
    run_id: int,
    kind: str,
    request: str,
    executor: Callable[[], dict[str, Any]],
    *,
    root: str | Path = "",
    target: str | Path = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a Friday background task through the shared phase contract."""

    def _phase_metadata(state: dict[str, Any], phase: str) -> dict[str, Any]:
        state_metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
        return {
            "workflow_backend": state.get("workflow_backend") or "native",
            "workflow_phase": phase,
            "workflow_backend_error": state.get("workflow_backend_error") or "",
            "trace_id": state.get("trace_id") or state_metadata.get("trace_id") or "",
        }

    def _inspect(state: dict[str, Any]) -> dict[str, Any]:
        update_run(
            run_id,
            status="inspecting",
            phase="inspect",
            summary=f"{kind} is inspecting workspace context.",
            metadata=_phase_metadata(state, "inspect"),
        )
        return {"inspected": True}

    def _plan(state: dict[str, Any]) -> dict[str, Any]:
        update_run(
            run_id,
            status="planning",
            phase="plan",
            summary=f"{kind} is planning the execution path.",
            metadata=_phase_metadata(state, "plan"),
        )
        return {"planned": True}

    def _build(state: dict[str, Any]) -> dict[str, Any]:
        update_run(
            run_id,
            status="building",
            phase="build",
            summary=f"{kind} is running implementation work.",
            metadata=_phase_metadata(state, "build"),
        )
        output = executor() or {}
        return {"output": output}

    def _verify(state: dict[str, Any]) -> dict[str, Any]:
        output = state.get("output") if isinstance(state.get("output"), dict) else {}
        status = _status_from_output(output)
        artifacts = _extract_artifacts(output)
        gaps = _extract_gaps(output)
        update_run(
            run_id,
            status="verifying",
            phase="verify",
            summary=f"{kind} is verifying output evidence.",
            artifacts=artifacts,
            gaps=gaps,
            metadata={**_phase_metadata(state, "verify"), "candidate_status": status},
        )
        return {"candidate_status": status, "artifacts": artifacts, "gaps": gaps}

    def _fix(state: dict[str, Any]) -> dict[str, Any]:
        gaps = list(state.get("gaps") or [])
        status = _status(str(state.get("candidate_status") or "done"))
        if gaps or status in {"blocked", "failed"}:
            update_run(
                run_id,
                status="fixing",
                phase="fix",
                summary=f"{kind} found gaps; domain fix loop remains with the product-studio executor.",
                gaps=gaps,
                metadata={**_phase_metadata(state, "fix"), "fix_applied": False},
            )
            return {"fix_applied": False, "fix_note": "No generic cross-domain patch was applied by the run backbone."}
        return {"fix_applied": False, "fix_note": "No fix needed."}

    def _prove(state: dict[str, Any]) -> dict[str, Any]:
        output = state.get("output") if isinstance(state.get("output"), dict) else {}
        status = _status(str(state.get("candidate_status") or _status_from_output(output)))
        artifacts = list(state.get("artifacts") or _extract_artifacts(output))
        gaps = list(state.get("gaps") or _extract_gaps(output))
        workflow_metadata = {
            **_phase_metadata(state, "prove"),
            "workflow_phases": list(state.get("workflow_phases") or []),
            "fix_note": state.get("fix_note") or "",
        }
        update_run(
            run_id,
            status=status,
            phase="complete",
            summary=_clean(output.get("summary") or f"{kind} finished."),
            output=output,
            artifacts=artifacts,
            gaps=gaps,
            metadata=workflow_metadata,
        )
        return {"final_status": status, "proof_recorded": True}

    phases = [
        ("inspect", _inspect),
        ("plan", _plan),
        ("build", _build),
        ("verify", _verify),
        ("fix", _fix),
        ("prove", _prove),
    ]
    return langgraph_backbone.run_phase_graph(
        phases,
        {
            "run_id": run_id,
            "kind": kind,
            "request": request,
            "root": str(root or ""),
            "target": str(target or ""),
            "metadata": metadata or {},
            "trace_id": (metadata or {}).get("trace_id") or "",
        },
        thread_id=f"friday-run-{run_id}",
    )


def get_run(run_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM friday_runs WHERE id=?", (int(run_id),)).fetchone()
        if not row:
            return None
        events = conn.execute("SELECT * FROM friday_run_events WHERE run_id=? ORDER BY id ASC", (int(run_id),)).fetchall()
    item = _row(row)
    item["events"] = [_event_row(event) for event in events]
    return item


def status(limit: int = 12) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM friday_runs ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 12))),)).fetchall()
    runs = [_row(row) for row in rows]
    return {
        "runs": runs,
        "latest": runs[0] if runs else None,
        "active": [run for run in runs if run.get("status") in {"queued", "inspecting", "planning", "building", "verifying", "fixing"}],
        "workflow": langgraph_backbone.capabilities(),
        "summary": f"{len(runs)} central Friday run(s) recorded.",
    }


def _status(value: str) -> str:
    cleaned = _clean(value).lower()
    return cleaned if cleaned in STATUSES else "created"


def _status_from_output(output: dict[str, Any]) -> str:
    execution = output.get("execution") if isinstance(output.get("execution"), dict) else {}
    if execution.get("task_status"):
        return _status(str(execution.get("task_status")))
    task = output.get("task") if isinstance(output.get("task"), dict) else {}
    if task.get("status"):
        return _status(str(task.get("status")))
    raw = str(output.get("status") or output.get("task_status") or "").lower()
    if raw in STATUSES:
        return raw
    if output.get("market_ready"):
        return "market_ready"
    if output.get("technical_ready"):
        return "technical_ready"
    if output.get("ok") is False or output.get("failed"):
        return "blocked"
    return "done"


def _extract_artifacts(output: dict[str, Any]) -> list[str]:
    artifacts: list[str] = []
    for key in ("artifacts", "changed"):
        artifacts.extend(str(item) for item in (output.get(key) or []) if str(item).strip())
    metadata = output.get("metadata") if isinstance(output.get("metadata"), dict) else {}
    for key in ("product_studio", "product_studio_gates", "gate_results"):
        value = metadata.get(key) if key in metadata else output.get(key)
        if isinstance(value, dict):
            artifacts.extend(str(item) for item in (value.get("artifacts") or []) if str(item).strip())
    return _dedupe(artifacts)


def _extract_gaps(output: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    for key in ("gaps", "failed", "failed_required"):
        gaps.extend(str(item) for item in (output.get(key) or []) if str(item).strip())
    metadata = output.get("metadata") if isinstance(output.get("metadata"), dict) else {}
    gate_results = metadata.get("product_studio_gates") if isinstance(metadata.get("product_studio_gates"), dict) else output.get("gate_results")
    if isinstance(gate_results, dict):
        gaps.extend(str(item) for item in (gate_results.get("failed_required") or []) if str(item).strip())
    return _dedupe(gaps)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "kind": row["kind"],
        "request": row["request"],
        "root": row["root"],
        "target": row["target"],
        "status": row["status"],
        "phase": row["phase"],
        "summary": row["summary"],
        "output": _json_loads(row["output_json"], {}),
        "artifacts": _json_loads(row["artifacts_json"], []),
        "gaps": _json_loads(row["gaps_json"], []),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _event_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "run_id": int(row["run_id"]),
        "timestamp": row["timestamp"],
        "phase": row["phase"],
        "status": row["status"],
        "summary": row["summary"],
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return fallback


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = _clean(item)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result

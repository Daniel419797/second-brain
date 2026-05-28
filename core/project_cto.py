"""Personal CTO layer: roadmap, risks, release state, security posture, next engineering task."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import deployment_brain, project_memory, project_watchdog, security_guardian_pro, workspace_brain
from core.config import DATA_DIR, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "project_cto.sqlite3"
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
            CREATE TABLE IF NOT EXISTS project_cto_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                root TEXT NOT NULL,
                project_name TEXT NOT NULL,
                roadmap_json TEXT NOT NULL,
                risks_json TEXT NOT NULL,
                technical_debt_json TEXT NOT NULL,
                release_status TEXT NOT NULL,
                security_posture TEXT NOT NULL,
                next_best_task TEXT NOT NULL,
                summary TEXT NOT NULL,
                evidence_json TEXT NOT NULL
            )
            """
        )


def report(root: str | Path = "", *, refresh: bool = True) -> dict[str, Any]:
    init_db()
    base = _safe_root(root)
    profile = _safe(lambda: project_memory.profile(base, refresh=refresh), {})
    architecture = _safe(lambda: workspace_brain.analyze_project(str(base)), {})
    watchdog = _safe(lambda: project_watchdog.run_once(str(base), notify=False), {})
    security = _safe(lambda: security_guardian_pro.scan(str(base), light=True), {})
    deployment = _safe(lambda: deployment_brain.inspect(root=str(base), create_proof=False), {})
    issues = list(watchdog.get("issues") or [])
    security_findings = security.get("findings") or security.get("issues") or []
    risks = _risks(issues, security_findings, deployment)
    debt = _technical_debt(issues, architecture)
    roadmap = _roadmap(profile, risks, debt)
    release_status = _release_status(watchdog, deployment)
    security_posture = _security_posture(security_findings, risks)
    next_task = _next_task(risks, debt, roadmap)
    summary = f"CTO report for {base.name}: {len(risks)} risk(s), next task: {next_task}"
    item = _store(base, roadmap, risks, debt, release_status, security_posture, next_task, summary, {"profile": profile, "architecture": architecture, "watchdog": watchdog, "security": security, "deployment": deployment})
    _safe(lambda: project_memory.remember(base, "cto_report", "Project CTO report", summary, confidence=0.82, metadata={"report_id": item["id"], "risks": risks[:8], "next_task": next_task}), None)
    return item


def recent(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM project_cto_reports ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    items = recent(limit=8)
    latest = items[0] if items else None
    return {"latest": latest, "recent": items, "summary": latest["summary"] if latest else "Project CTO is ready."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM project_cto_reports")


def _store(base: Path, roadmap: list[str], risks: list[str], debt: list[str], release_status: str, security_posture: str, next_task: str, summary: str, evidence: dict[str, Any]) -> dict[str, Any]:
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO project_cto_reports(timestamp, root, project_name, roadmap_json, risks_json, technical_debt_json, release_status, security_posture, next_best_task, summary, evidence_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_now(), str(base), base.name, _json_dumps(roadmap), _json_dumps(risks), _json_dumps(debt), release_status, security_posture, next_task, summary, _json_dumps(evidence)),
        )
        row = conn.execute("SELECT * FROM project_cto_reports WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def _risks(issues: list[Any], security_findings: list[Any], deployment: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    for item in issues[:10]:
        if isinstance(item, dict):
            risks.append(str(item.get("title") or item.get("kind") or item))
        else:
            risks.append(str(item))
    for item in security_findings[:10]:
        risks.append(f"Security: {item}")
    if deployment.get("status") == "attention":
        risks.append(deployment.get("summary") or "Deployment report needs attention.")
    return _unique(risks)


def _technical_debt(issues: list[Any], architecture: dict[str, Any]) -> list[str]:
    debt = []
    blob = json.dumps({"issues": issues, "architecture": architecture}, ensure_ascii=True, default=str).lower()
    if "todo" in blob:
        debt.append("TODOs need triage into real tasks.")
    if "missing" in blob and "test" in blob:
        debt.append("Test coverage or test runner evidence may be missing.")
    if "dependency" in blob or "outdated" in blob:
        debt.append("Dependencies need a health check.")
    return debt or ["No major technical debt signal found in the latest local scan."]


def _roadmap(profile: dict[str, Any], risks: list[str], debt: list[str]) -> list[str]:
    roadmap = ["Keep the project runnable with documented setup commands."]
    commands = profile.get("commands") or []
    if commands:
        roadmap.append(f"Verify core commands: {', '.join(commands[:4])}.")
    if risks:
        roadmap.append("Resolve highest severity risk before feature expansion.")
    if debt:
        roadmap.append("Convert technical debt notes into small, testable tasks.")
    roadmap.append("Prepare release proof before any deployment.")
    return _unique(roadmap)


def _release_status(watchdog: dict[str, Any], deployment: dict[str, Any]) -> str:
    if watchdog.get("issues"):
        return "not_ready: project issues exist"
    if deployment.get("status") == "attention":
        return "not_ready: deployment checks need attention"
    return "candidate: local checks found no blocking issue"


def _security_posture(security_findings: list[Any], risks: list[str]) -> str:
    if security_findings:
        return "attention: security findings exist"
    if any("secret" in item.lower() or "vulnerab" in item.lower() for item in risks):
        return "attention: security risk signals exist"
    return "baseline: no obvious local security finding in latest scan"


def _next_task(risks: list[str], debt: list[str], roadmap: list[str]) -> str:
    if risks:
        return f"Investigate: {risks[0]}"
    if debt:
        return f"Reduce debt: {debt[0]}"
    return roadmap[0] if roadmap else "Run project health checks."


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "root": str(row["root"]),
        "project_name": str(row["project_name"]),
        "roadmap": _json_loads(row["roadmap_json"], []),
        "risks": _json_loads(row["risks_json"], []),
        "technical_debt": _json_loads(row["technical_debt_json"], []),
        "release_status": str(row["release_status"]),
        "security_posture": str(row["security_posture"]),
        "next_best_task": str(row["next_best_task"]),
        "summary": str(row["summary"]),
        "evidence": _json_loads(row["evidence_json"], {}),
    }


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        clean = _clean(item)
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            out.append(clean)
    return out


def _safe_root(value: str | Path) -> Path:
    try:
        return resolve_coding_root(value)
    except Exception:
        return resolve_coding_root()


def _safe(fn: Any, default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


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

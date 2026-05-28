"""Release preparation and deployment approval records."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "release_manager.sqlite3"
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
            CREATE TABLE IF NOT EXISTS release_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                root TEXT NOT NULL,
                mission_id INTEGER,
                status TEXT NOT NULL,
                version TEXT NOT NULL,
                summary TEXT NOT NULL,
                changelog TEXT NOT NULL,
                checklist_json TEXT NOT NULL,
                risks_json TEXT NOT NULL,
                rollback_json TEXT NOT NULL,
                approved_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_release_runs_status ON release_runs(status, updated_at)")


def prepare_release(root: str | Path = "", *, mission_id: int | None = None, version: str = "") -> dict[str, Any]:
    init_db()
    project_root = _safe_root(root)
    version = _clean(version) or _detect_version(project_root)
    deploy_preapproved = _deploy_preapproved(project_root)
    checklist = _checklist(project_root, deploy_preapproved=deploy_preapproved)
    risks = _risks(project_root, mission_id=mission_id, deploy_preapproved=deploy_preapproved)
    rollback = _rollback(project_root)
    changelog = _changelog(project_root, mission_id=mission_id)
    status = "deploy_approved" if deploy_preapproved else "pending_approval"
    approved_at = _now() if deploy_preapproved else ""
    summary = (
        f"Release plan ready for {project_root.name} {version}. Deploy is pre-approved by full autonomy policy."
        if deploy_preapproved
        else f"Release plan ready for {project_root.name} {version}. Deploy remains approval-gated."
    )
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO release_runs(timestamp, updated_at, root, mission_id, status, version, summary, changelog, checklist_json, risks_json, rollback_json, approved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_now(), _now(), str(project_root), int(mission_id) if mission_id else None, status, version, summary, changelog, _json_dumps(checklist), _json_dumps(risks), _json_dumps(rollback), approved_at),
        )
        row = conn.execute("SELECT * FROM release_runs WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    report = _row(row)
    if mission_id:
        try:
            from core import mission_control

            mission_control.add_evidence(int(mission_id), "release_prep", "release_manager", "Release plan", summary, {"release_id": report["id"]})
        except Exception:
            pass
    return report


def approve_deploy(release_id: int, note: str = "") -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            "UPDATE release_runs SET status='deploy_approved', approved_at=?, updated_at=? WHERE id=?",
            (_now(), _now(), int(release_id)),
        )
        row = conn.execute("SELECT * FROM release_runs WHERE id=?", (int(release_id),)).fetchone()
    release = _row(row) if row else {}
    mission_id = release.get("mission_id")
    if mission_id:
        try:
            from core import mission_control

            mission_control.approve_deploy(int(mission_id), note=note or f"Release #{release_id} approved.")
        except Exception:
            pass
    return release


def get_release(release_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM release_runs WHERE id=?", (int(release_id),)).fetchone()
    return _row(row) if row else None


def recent_releases(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM release_runs ORDER BY id DESC LIMIT ?", (max(1, min(200, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        rows = conn.execute("SELECT status, COUNT(*) FROM release_runs GROUP BY status").fetchall()
    counts = {str(status): int(count) for status, count in rows}
    recent = recent_releases(limit=6)
    return {"counts": counts, "recent": recent, "summary": f"{sum(counts.values())} release plan(s) recorded."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM release_runs")


def _detect_version(root: Path) -> str:
    package = root / "package.json"
    if package.exists():
        try:
            return str(json.loads(package.read_text(encoding="utf-8")).get("version") or "0.1.0")
        except Exception:
            return "0.1.0"
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8", errors="ignore"))
        if match:
            return match.group(1)
    return "0.1.0"


def _checklist(root: Path, *, deploy_preapproved: bool = False) -> list[dict[str, Any]]:
    has_package = (root / "package.json").exists()
    has_tests = (root / "tests").exists() or any(root.glob("**/*.test.*")) or any(root.glob("**/*_test.py"))
    has_docs = (root / "README.md").exists() or (root / "docs").exists()
    return [
        {"item": "Build succeeds", "status": "pending", "command_hint": "npm run build" if has_package else "project-specific build"},
        {"item": "Tests pass", "status": "pending" if has_tests else "needs_test_plan", "command_hint": "npm test or pytest"},
        {"item": "QA Lab evidence attached", "status": "pending"},
        {"item": "Docs updated", "status": "pending" if has_docs else "needs_docs"},
        {"item": "Secrets scan clean", "status": "pending"},
        {"item": "Rollback plan reviewed", "status": "pending"},
        {"item": "Deploy approval policy satisfied", "status": "preapproved" if deploy_preapproved else "blocked_until_approval"},
    ]


def _risks(root: Path, mission_id: int | None, *, deploy_preapproved: bool = False) -> list[dict[str, str]]:
    risks = [
        {
            "risk": "Deployment changes production state.",
            "mitigation": "Full autonomy pre-approval applies only to trusted scopes." if deploy_preapproved else "Require explicit approve-deploy action before any deploy command.",
        }
    ]
    if not (root / ".git").exists():
        risks.append({"risk": "No Git repository detected.", "mitigation": "Create a backup/snapshot before changing files."})
    if mission_id:
        risks.append({"risk": "Mission may still have blockers.", "mitigation": f"Check Mission #{mission_id} blockers before deploy."})
    return risks


def _deploy_preapproved(root: Path) -> bool:
    try:
        from core import autonomy_control

        return autonomy_control.preapprove_deployments({"root": str(root)})
    except Exception:
        return False


def _rollback(root: Path) -> dict[str, Any]:
    return {
        "strategy": "Prefer git revert or redeploy previous known-good build. Keep config snapshots before edits.",
        "root": str(root),
        "notes": ["Do not include .env values in release reports.", "Record exact deploy command only after approval."],
    }


def _changelog(root: Path, mission_id: int | None) -> str:
    lines = [f"# Release Notes for {root.name}", "", "- Prepared by Friday Release Manager.", "- Deployment is blocked until explicit approval."]
    if mission_id:
        lines.append(f"- Linked mission: #{mission_id}.")
    return "\n".join(lines)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "updated_at": str(row["updated_at"]),
        "root": str(row["root"]),
        "mission_id": int(row["mission_id"]) if row["mission_id"] is not None else None,
        "status": str(row["status"]),
        "version": str(row["version"]),
        "summary": str(row["summary"]),
        "changelog": str(row["changelog"]),
        "checklist": _json_loads(row["checklist_json"], []),
        "risks": _json_loads(row["risks_json"], []),
        "rollback": _json_loads(row["rollback_json"], {}),
        "approved_at": str(row["approved_at"] or ""),
    }


def _safe_root(value: str | Path) -> Path:
    try:
        return resolve_coding_root(value)
    except Exception:
        return resolve_coding_root()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, default=str)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=True)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return default

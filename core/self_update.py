"""Guarded self-update workflow for Friday's own codebase."""

from __future__ import annotations

import datetime as dt
import json
import shutil
import sqlite3
import subprocess
import threading
from pathlib import Path
from typing import Any

from core import command_runner, task_queue
from core.config import DATA_DIR, ROOT_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "self_updates.sqlite3"
BACKUP_DIR = DATA_DIR / "self_updates" / "backups"
VALID_SESSION_STATUSES = {"proposed", "approved", "applied", "cancelled", "failed"}
VALID_CHANGE_STATUSES = {"staged", "applied", "rolled_back"}
ALLOWED_EXTENSIONS = {
    ".bat",
    ".c",
    ".clj",
    ".cljs",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".dart",
    ".erl",
    ".ex",
    ".exs",
    ".fs",
    ".go",
    ".graphql",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".kts",
    ".lua",
    ".m",
    ".md",
    ".mm",
    ".php",
    ".proto",
    ".ps1",
    ".py",
    ".r",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
ALLOWED_NAMES = {"Dockerfile", "Makefile", "Procfile", "Gemfile", "Rakefile"}
BLOCKED_PARTS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".next", "data"}
BLOCKED_NAMES = {".env"}
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
            CREATE TABLE IF NOT EXISTS self_update_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request TEXT NOT NULL,
                status TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                task_id INTEGER,
                approval_phrase TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                approved_at TEXT,
                applied_at TEXT,
                result_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS self_update_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                update_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                find_text TEXT NOT NULL,
                replace_text TEXT NOT NULL,
                summary TEXT NOT NULL,
                status TEXT NOT NULL,
                backup_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                applied_at TEXT,
                FOREIGN KEY(update_id) REFERENCES self_update_sessions(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_self_updates_status ON self_update_sessions(status, updated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_self_update_changes_update ON self_update_changes(update_id, status)")


def create_proposal(request: str) -> dict[str, Any]:
    init_db()
    cleaned = _clean(request)
    if not cleaned:
        raise ValueError("Self-update request is empty.")
    plan = _build_plan(cleaned)
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO self_update_sessions (
                request, status, risk_level, plan_json, task_id, approval_phrase,
                created_at, updated_at, approved_at, applied_at, result_json
            )
            VALUES (?, 'proposed', ?, ?, NULL, '', ?, ?, NULL, NULL, '{}')
            """,
            (cleaned, plan["risk_level"], _json_dumps(plan), now, now),
        )
        update_id = int(cursor.lastrowid)
        phrase = f"I authorize self update {update_id}"
        conn.execute(
            "UPDATE self_update_sessions SET approval_phrase=? WHERE id=?",
            (phrase, update_id),
        )
    return get_update(update_id) or {}


def list_updates(limit: int = 10) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM self_update_sessions ORDER BY id DESC LIMIT ?",
            (max(1, min(100, int(limit))),),
        ).fetchall()
    return [_row_to_session(row, include_changes=False) for row in rows]


def get_update(update_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM self_update_sessions WHERE id=?", (int(update_id),)).fetchone()
    if not row:
        return None
    session = _row_to_session(row, include_changes=True)
    return session


def approve_update(update_id: int, confirmation: str) -> dict[str, Any]:
    init_db()
    update = get_update(update_id)
    if not update:
        raise ValueError(f"Self-update {update_id} not found.")
    if update["status"] != "proposed":
        raise ValueError(f"Self-update {update_id} is {update['status']}, not proposed.")
    phrase = f"i authorize self update {int(update_id)}"
    if phrase not in str(confirmation or "").lower():
        raise PermissionError(f"Say or type: I authorize self update {int(update_id)}.")
    task_id = _queue_implementation_task(update)
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            """
            UPDATE self_update_sessions
            SET status='approved', task_id=?, approved_at=?, updated_at=?
            WHERE id=?
            """,
            (task_id, now, now, int(update_id)),
        )
    return get_update(update_id) or {}


def cancel_update(update_id: int) -> dict[str, Any]:
    init_db()
    update = get_update(update_id)
    if not update:
        raise ValueError(f"Self-update {update_id} not found.")
    if update["status"] in {"applied", "cancelled"}:
        return update
    if update.get("task_id"):
        try:
            task_queue.cancel_task(int(update["task_id"]))
        except Exception:
            pass
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            "UPDATE self_update_sessions SET status='cancelled', updated_at=? WHERE id=?",
            (now, int(update_id)),
        )
    return get_update(update_id) or {}


def stage_change(update_id: int, path: str, find_text: str, replace_text: str, summary: str = "") -> dict[str, Any]:
    init_db()
    update = get_update(update_id)
    if not update:
        raise ValueError(f"Self-update {update_id} not found.")
    if update["status"] not in {"proposed", "approved"}:
        raise ValueError(f"Self-update {update_id} cannot accept changes while {update['status']}.")
    target = _safe_target(path)
    find_value = str(find_text or "")
    replace_value = str(replace_text or "")
    if target.exists() and not find_value:
        raise ValueError("find_text is required when modifying an existing file.")
    if len(replace_value.encode("utf-8")) > int(config_value("self_update_max_change_bytes", 120000)):
        raise ValueError("Replacement text is too large for one self-update change.")
    if target.exists():
        current = target.read_text(encoding="utf-8", errors="ignore")
        count = current.count(find_value)
        if count != 1:
            raise ValueError(f"find_text must match exactly once; matched {count} times.")
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO self_update_changes (
                update_id, path, find_text, replace_text, summary, status,
                backup_path, created_at, applied_at
            )
            VALUES (?, ?, ?, ?, ?, 'staged', '', ?, NULL)
            """,
            (int(update_id), str(target.relative_to(_root())), find_value, replace_value, _clean(summary), now),
        )
        change_id = int(cursor.lastrowid)
        conn.execute("UPDATE self_update_sessions SET updated_at=? WHERE id=?", (now, int(update_id)))
    return get_change(change_id) or {}


def get_change(change_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM self_update_changes WHERE id=?", (int(change_id),)).fetchone()
    return _row_to_change(row) if row else None


def apply_update(update_id: int, confirmation: str, *, run_tests: bool | None = None) -> dict[str, Any]:
    init_db()
    update = get_update(update_id)
    if not update:
        raise ValueError(f"Self-update {update_id} not found.")
    if update["status"] != "approved":
        raise ValueError(f"Self-update {update_id} must be approved before applying changes.")
    phrase = f"i authorize applying self update {int(update_id)}"
    if phrase not in str(confirmation or "").lower():
        raise PermissionError(f"Say or type: I authorize applying self update {int(update_id)}.")
    changes = [change for change in update["changes"] if change["status"] == "staged"]
    if not changes:
        raise ValueError(f"Self-update {update_id} has no staged changes.")

    applied: list[dict[str, Any]] = []
    try:
        for change in changes:
            applied.append(_apply_change(change))
        tests = _run_tests() if (bool(config_value("self_update_run_tests", True)) if run_tests is None else run_tests) else {"skipped": True}
        if tests.get("failed") and bool(config_value("self_update_rollback_on_test_failure", True)):
            _rollback_changes(applied)
            result = {"applied": False, "rolled_back": True, "tests": tests, "changes": applied}
            _finish_update(update_id, "failed", result)
            return get_update(update_id) or {}
        result = {"applied": True, "rolled_back": False, "tests": tests, "changes": applied}
        _finish_update(update_id, "applied", result)
        return get_update(update_id) or {}
    except Exception as exc:
        _rollback_changes(applied)
        result = {"applied": False, "rolled_back": bool(applied), "error": str(exc), "changes": applied}
        _finish_update(update_id, "failed", result)
        raise


def explain_brain() -> str:
    return (
        "Friday's brain is a brain-inspired software stack: speech and vision inputs feed an attention gate, "
        "an orchestrator acts like executive function, tools are motor skills, and SQLite/JSON/graph stores are episodic, semantic, and procedural memory. "
        "It is not conscious or human-equivalent yet; it is a practical cognitive architecture scaffold."
    )


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM self_update_changes")
        conn.execute("DELETE FROM self_update_sessions")


def _build_plan(request: str) -> dict[str, Any]:
    risk = _risk_level(request)
    candidates = _candidate_files(request)
    return {
        "request": request,
        "risk_level": risk,
        "repo": _repo_summary(),
        "candidate_files": candidates,
        "steps": [
            "Inspect the relevant files and existing tests before changing code.",
            "Stage exact, minimal file replacements instead of broad rewrites.",
            "Apply only after explicit user approval and permission checks.",
            "Run the configured test command after applying changes.",
            "Rollback automatically if tests fail, then report the failure.",
        ],
        "safety_rules": [
            "Never modify .env, data stores, .venv, node_modules, or hidden runtime directories.",
            "Never delete files through self-update.",
            "Do not claim code changed unless apply_update reports success.",
            "Use the smallest patch that satisfies the request.",
        ],
    }


def _queue_implementation_task(update: dict[str, Any]) -> int:
    plan = update.get("plan") or {}
    description = (
        f"Self-update request #{update['id']}:\n{update['request']}\n\n"
        "Prepare a minimal implementation plan and exact staged replacements if this runtime is controlling tools. "
        "Do not modify secrets or runtime data. Add/update tests where appropriate. "
        "Approval phrase already received for planning, but applying code still requires: "
        f"I authorize applying self update {update['id']}.\n\n"
        f"Plan: {_json_dumps(plan)}"
    )
    task_id = task_queue.create_task(
        f"Self-update #{update['id']}: {update['request'][:80]}",
        description=description,
        agent_id="senior_developer",
        priority=int(config_value("self_update_task_priority", 2)),
        input_data={"source": "self_update", "update_id": update["id"], "plan": plan},
    )
    task_queue.post_message(task_id, "friday", f"Self-update #{update['id']} approved for implementation planning.")
    return task_id


def _apply_change(change: dict[str, Any]) -> dict[str, Any]:
    target = _safe_target(change["path"])
    backup = _backup_path(int(change["update_id"]), target)
    backup.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    if existed:
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)
        current = target.read_text(encoding="utf-8", errors="ignore")
        find_text = str(change.get("find_text") or "")
        if current.count(find_text) != 1:
            raise ValueError(f"{change['path']} no longer matches the staged replacement.")
        updated = current.replace(find_text, str(change.get("replace_text") or ""), 1)
    else:
        backup.write_text("", encoding="utf-8")
        updated = str(change.get("replace_text") or "")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(updated, encoding="utf-8")
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            "UPDATE self_update_changes SET status='applied', backup_path=?, applied_at=? WHERE id=?",
            (str(backup), now, int(change["id"])),
        )
    return {"id": change["id"], "path": change["path"], "backup_path": str(backup), "existed": existed}


def _rollback_changes(applied: list[dict[str, Any]]) -> None:
    for change in reversed(applied):
        backup = Path(str(change.get("backup_path") or ""))
        target = _safe_target(str(change.get("path") or ""))
        if not backup.exists():
            continue
        backup_text = backup.read_text(encoding="utf-8", errors="ignore")
        if not bool(change.get("existed")) and target.exists():
            target.unlink()
        else:
            target.write_text(backup_text, encoding="utf-8")
        with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
            conn.execute("UPDATE self_update_changes SET status='rolled_back' WHERE id=?", (int(change["id"]),))


def _run_tests() -> dict[str, Any]:
    command = str(config_value("self_update_test_command", r".\.venv\Scripts\python.exe -m pytest -q"))
    timeout = float(config_value("self_update_test_timeout_seconds", 300))
    try:
        completed = command_runner.run(command, cwd=_root(), timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return {"failed": True, "timeout": True, "command": command, "output": str(exc)[:1200]}
    except command_runner.CommandRejected as exc:
        return {"failed": True, "blocked": True, "command": command, "output": str(exc)[:1200]}
    output = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
    return {
        "failed": completed.returncode != 0,
        "returncode": int(completed.returncode),
        "command": command,
        "output": output[-2000:],
    }


def _finish_update(update_id: int, status: str, result: dict[str, Any]) -> None:
    now = _now()
    normalized = status if status in VALID_SESSION_STATUSES else "failed"
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            """
            UPDATE self_update_sessions
            SET status=?, updated_at=?, applied_at=CASE WHEN ?='applied' THEN ? ELSE applied_at END, result_json=?
            WHERE id=?
            """,
            (normalized, now, normalized, now, _json_dumps(result), int(update_id)),
        )


def _repo_summary() -> dict[str, Any]:
    root = _root()
    counts: dict[str, int] = {}
    total = 0
    for path in _iter_repo_files(limit=int(config_value("self_update_max_repo_summary_files", 2500))):
        total += 1
        suffix = path.suffix.lower() or "[no_ext]"
        counts[suffix] = counts.get(suffix, 0) + 1
    return {"root": str(root), "file_count_sample": total, "extensions": dict(sorted(counts.items())[:20])}


def _candidate_files(request: str) -> list[str]:
    terms = {word for word in _words(request) if len(word) >= 4}
    scored: list[tuple[int, str]] = []
    for path in _iter_repo_files(limit=int(config_value("self_update_max_file_candidates", 700))):
        rel = str(path.relative_to(_root())).replace("\\", "/")
        lowered = rel.lower()
        score = sum(1 for term in terms if term in lowered)
        if "self" in terms and "update" in terms and ("self_update" in lowered or "orchestrator" in lowered):
            score += 3
        if score:
            scored.append((score, rel))
    scored.sort(key=lambda item: (-item[0], item[1]))
    defaults = ["core/orchestrator.py", "core/llm.py", "tools", "tests", "config.json"]
    result = [item[1] for item in scored[:8]]
    for item in defaults:
        if item not in result:
            result.append(item)
    return result[:12]


def _iter_repo_files(limit: int) -> list[Path]:
    root = _root()
    files: list[Path] = []
    for path in root.rglob("*"):
        if len(files) >= limit:
            break
        if not path.is_file():
            continue
        rel_parts = set(path.relative_to(root).parts)
        if rel_parts & BLOCKED_PARTS:
            continue
        if path.name in BLOCKED_NAMES:
            continue
        if path.suffix.lower() not in ALLOWED_EXTENSIONS and path.name not in ALLOWED_NAMES:
            continue
        files.append(path)
    return files


def _safe_target(path: str) -> Path:
    raw = Path(str(path or "").strip().strip('"'))
    root = _root()
    target = raw if raw.is_absolute() else root / raw
    resolved = target.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PermissionError("Self-update can only modify files inside this project.") from exc
    rel_parts = set(resolved.relative_to(root).parts)
    if rel_parts & BLOCKED_PARTS or resolved.name in BLOCKED_NAMES:
        raise PermissionError("Self-update cannot modify secrets, runtime data, dependencies, or hidden build folders.")
    if resolved.suffix.lower() not in ALLOWED_EXTENSIONS and resolved.name not in ALLOWED_NAMES:
        raise PermissionError(f"Self-update cannot modify {resolved.suffix or 'extensionless'} files.")
    if resolved.exists() and resolved.stat().st_size > int(config_value("self_update_max_file_bytes", 240000)):
        raise PermissionError("Target file is too large for guarded self-update.")
    return resolved


def _backup_path(update_id: int, target: Path) -> Path:
    rel = target.relative_to(_root())
    return BACKUP_DIR / str(update_id) / rel


def _row_to_session(row: sqlite3.Row, *, include_changes: bool) -> dict[str, Any]:
    session = {
        "id": int(row["id"]),
        "request": str(row["request"]),
        "status": str(row["status"]),
        "risk_level": str(row["risk_level"]),
        "plan": _json_loads(row["plan_json"]),
        "task_id": row["task_id"],
        "approval_phrase": str(row["approval_phrase"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "approved_at": str(row["approved_at"] or ""),
        "applied_at": str(row["applied_at"] or ""),
        "result": _json_loads(row["result_json"]),
    }
    if include_changes:
        session["changes"] = _changes_for_session(session["id"])
    return session


def _changes_for_session(update_id: int) -> list[dict[str, Any]]:
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM self_update_changes WHERE update_id=? ORDER BY id ASC",
            (int(update_id),),
        ).fetchall()
    return [_row_to_change(row) for row in rows]


def _row_to_change(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "update_id": int(row["update_id"]),
        "path": str(row["path"]),
        "find_text": str(row["find_text"]),
        "replace_text": str(row["replace_text"]),
        "summary": str(row["summary"]),
        "status": str(row["status"]),
        "backup_path": str(row["backup_path"]),
        "created_at": str(row["created_at"]),
        "applied_at": str(row["applied_at"] or ""),
    }


def _risk_level(request: str) -> str:
    lowered = request.lower()
    high_terms = {"delete", "remove", "credential", "password", "secret", "shell", "command", "email", "message", "security", "payment"}
    medium_terms = {"tool", "permission", "api", "desktop", "browser", "voice", "agent", "memory", "self"}
    words = set(_words(lowered))
    if words & high_terms:
        return "high"
    if words & medium_terms:
        return "medium"
    return "low"


def _words(text: str) -> list[str]:
    return [part for part in "".join(ch if ch.isalnum() else " " for ch in text.lower()).split() if part]


def _root() -> Path:
    return Path(ROOT_DIR).resolve()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str) -> Any:
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


def _clean(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

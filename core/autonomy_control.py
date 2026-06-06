"""Central autonomy policy for trusted Friday workspaces."""

from __future__ import annotations

import os
import sqlite3
import threading
import datetime as dt
from pathlib import Path
from typing import Any

from core.config import DATA_DIR, config_value, default_coding_root, ensure_runtime_dirs, resolve_coding_root

MODES = {"manual", "supervised", "full", "full_access"}
AUTHORITY_MODES = {"approval_gated", "full_access"}
DB_PATH = DATA_DIR / "autonomy_control.sqlite3"
_LOCK = threading.Lock()

LOCAL_PROJECT_KEYS = {
    "power_center.agent_scheduler_apply",
    "power_center.autonomous_coding",
    "power_center.autonomy_engine",
    "power_center.deep_project_autopilot",
    "power_center.fix_loop",
    "power_center.git_write",
    "power_center.project_autopilot",
    "power_center.project_watchdog",
    "power_center.release_manager",
    "power_center.task_autopilot",
    "power_center.test_build_monitor",
}

REMOTE_WRITE_KEYS = {
    "power_center.git_push",
    "power_center.github",
}

DEPLOYMENT_KEYS = {
    "power_center.agency_deploy",
    "power_center.deployment_commander",
    "power_center.mission_deploy",
    "power_center.release_engine",
}

SELF_UPDATE_KEYS = {
    "self_update.approve",
    "self_update.apply",
    "self_update.stage_change",
}

DEFAULT_HARD_STOP_KEYS = {
    "capability_center.automation",
    "capability_center.device_control",
    "capability_center.security_scan",
    "capability_center.security_scope",
    "pc_control.delete_file",
    "pc_control.run_command",
    "phone_bridge.dial",
    "phone_bridge.file_transfer",
    "phone_bridge.register_device",
    "phone_bridge.sms_draft",
    "power_center.agency_outreach_send",
    "power_center.agency_payment",
    "power_center.agent_lifecycle",
    "power_center.android_companion",
    "power_center.automation_builder",
    "power_center.backup",
    "power_center.home_assistant",
    "power_center.privacy_firewall",
    "power_center.privacy_firewall_pro",
    "power_center.privacy_vault",
    "power_center.security_guardian_pro",
    "power_center.security_lab",
    "send_email.send_email",
}

PATH_FIELDS = {
    "cwd",
    "destination",
    "directory",
    "file",
    "folder",
    "output_dir",
    "path",
    "project_root",
    "repo",
    "repository",
    "root",
    "target_path",
    "workdir",
    "workspace",
}


def init_db() -> None:
    ensure_runtime_dirs()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS autonomy_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                updated_by TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS autonomy_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )


def set_authority_mode(authority_mode: str, *, actor: str = "user") -> dict[str, Any]:
    """Persist the one-click Friday authority mode exposed in Studio."""

    normalized = normalize_authority_mode(authority_mode)
    internal = "full_access" if normalized == "full_access" else "supervised"
    init_db()
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            """
            INSERT INTO autonomy_settings(key, value, updated_at, updated_by)
            VALUES ('authority_mode', ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, updated_by=excluded.updated_by
            """,
            (normalized, now, str(actor or "user")[:120]),
        )
        conn.execute(
            """
            INSERT INTO autonomy_events(timestamp, event_type, summary, metadata_json)
            VALUES (?, 'authority_mode_changed', ?, ?)
            """,
            (
                now,
                f"Authority mode set to {normalized}.",
                f'{{"authority_mode":"{normalized}","internal_mode":"{internal}"}}',
            ),
        )
    return status()


def normalize_authority_mode(authority_mode: str) -> str:
    value = str(authority_mode or "").strip().lower().replace("-", "_")
    if value in {"full", "full_autonomy", "autonomous", "no_babysitting", "ungated"}:
        return "full_access"
    if value in {"approval", "approval_gated", "gated", "supervised", "ask", "manual"}:
        return "approval_gated"
    return value if value in AUTHORITY_MODES else "approval_gated"


def authority_mode() -> str:
    raw_env = os.getenv("FRIDAY_AUTHORITY_MODE")
    if raw_env:
        return normalize_authority_mode(raw_env)
    raw_autonomy_env = os.getenv("FRIDAY_AUTONOMY_MODE")
    if raw_autonomy_env and raw_autonomy_env.strip().lower().replace("-", "_") in {"off", "disabled", "false", "0", "manual"}:
        return "approval_gated"
    stored = _stored_value("authority_mode")
    if stored:
        return normalize_authority_mode(stored)
    raw = raw_autonomy_env or str(config_value("autonomy_mode", "supervised") or "supervised")
    normalized = raw.strip().lower().replace("-", "_")
    if normalized in {"full_access", "ungated"}:
        return "full_access"
    return "approval_gated"


def mode() -> str:
    raw = os.getenv("FRIDAY_AUTONOMY_MODE") or str(config_value("autonomy_mode", "supervised") or "supervised")
    normalized = raw.strip().lower().replace("-", "_")
    if normalized in {"off", "disabled", "false", "0"}:
        return "manual"
    stored_authority = authority_mode()
    if stored_authority == "full_access":
        return "full_access"
    if normalized in {"auto", "autonomous", "full_autonomy", "no_babysitting"}:
        return "full"
    return normalized if normalized in MODES else "supervised"


def enabled() -> bool:
    return _bool_config("autonomy_control_enabled", True) and mode() != "manual"


def full_autonomy_enabled() -> bool:
    return enabled() and mode() in {"full", "full_access"}


def full_access_enabled() -> bool:
    return enabled() and authority_mode() == "full_access"


def full_autonomy_for_scope(tool_input: dict[str, Any] | None = None) -> bool:
    return full_autonomy_enabled() and is_trusted_scope(tool_input or {})


def preapprove_deployments(tool_input: dict[str, Any] | None = None) -> bool:
    return (
        full_autonomy_for_scope(tool_input)
        and _bool_config("autonomy_preapprove_deployments", True)
    )


def preapprove_design_preview(tool_input: dict[str, Any] | None = None) -> bool:
    return (
        full_autonomy_for_scope(tool_input)
        and _bool_config("autonomy_preapprove_design_preview", True)
    )


def override_decision(
    tool_name: str,
    tool_input: dict[str, Any] | None,
    *,
    key: str,
    mode: str,
) -> dict[str, Any] | None:
    """Return a permission override for full autonomy, or None to keep the rule."""

    tool_input = tool_input or {}
    if not enabled():
        return None

    hard_stops = hard_stop_keys()
    if key in hard_stops:
        if mode == "block":
            return None
        if full_access_enabled():
            bypass = _allow_if_trusted(key, tool_input, "Full-access authority mode.")
            if bypass:
                bypass["autonomy_hard_stop_bypassed"] = True
                return bypass
        return {
            "mode": "ask",
            "allowed": False,
            "requires_confirmation": True,
            "blocked": False,
            "autonomy_hard_stop": True,
            "autonomy_reason": "Core safety floor: this action still needs explicit approval.",
        }

    if mode != "ask" or not full_autonomy_enabled():
        return None

    if full_access_enabled():
        return _allow_if_trusted(key, tool_input, "Full-access authority mode.")

    if key == "power_center.git_write" and not _bool_config("autonomy_preapprove_git_writes", True):
        return None
    if key in LOCAL_PROJECT_KEYS and _bool_config("autonomy_preapprove_local_project_work", True):
        return _allow_if_trusted(key, tool_input, "Trusted local project autonomy.")
    if key in REMOTE_WRITE_KEYS and _bool_config("autonomy_preapprove_remote_writes", True):
        return _allow_if_trusted(key, tool_input, "Trusted Git/GitHub project write.")
    if key in DEPLOYMENT_KEYS and _bool_config("autonomy_preapprove_deployments", True):
        return _allow_if_trusted(key, tool_input, "Trusted deployment/release autonomy.")
    if key in SELF_UPDATE_KEYS and _bool_config("autonomy_preapprove_self_updates", True):
        return _allow_if_trusted(key, tool_input, "Trusted self-update autonomy with existing tests and rollback guards.")
    return None


def status() -> dict[str, Any]:
    authority = authority_mode()
    return {
        "mode": mode(),
        "authority_mode": authority,
        "enabled": enabled(),
        "full_autonomy": full_autonomy_enabled(),
        "full_access": authority == "full_access" and enabled(),
        "approval_gated": authority != "full_access" or not enabled(),
        "available_modes": [
            {
                "id": "approval_gated",
                "label": "Approval gated",
                "description": "Friday pauses at ask-first rules and approval gates before acting.",
            },
            {
                "id": "full_access",
                "label": "Full access",
                "description": "Friday can run trusted work without ask-first approvals; block rules still stop execution.",
            },
        ],
        "trusted_roots": [str(path) for path in trusted_roots()],
        "preapproved_local_keys": sorted(LOCAL_PROJECT_KEYS),
        "preapproved_remote_keys": sorted(REMOTE_WRITE_KEYS),
        "preapproved_deployment_keys": sorted(DEPLOYMENT_KEYS),
        "preapproved_self_update_keys": sorted(SELF_UPDATE_KEYS),
        "hard_stop_keys": sorted(hard_stop_keys()),
        "events": recent_events(limit=8),
        "summary": _summary(),
    }


def recent_events(limit: int = 20) -> list[dict[str, Any]]:
    try:
        init_db()
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM autonomy_events ORDER BY id DESC LIMIT ?",
                (max(1, min(100, int(limit))),),
            ).fetchall()
    except Exception:
        return []
    return [
        {
            "id": int(row["id"]),
            "timestamp": str(row["timestamp"]),
            "event_type": str(row["event_type"]),
            "summary": str(row["summary"]),
            "metadata": str(row["metadata_json"] or "{}"),
        }
        for row in rows
    ]


def trusted_roots() -> list[Path]:
    raw = os.getenv("FRIDAY_AUTONOMY_TRUSTED_ROOTS") or str(config_value("autonomy_trusted_roots", "Desktop") or "Desktop")
    paths: list[Path] = []
    for token in _split(raw):
        lowered = token.lower()
        if lowered in {"desktop", "~/desktop", "%userprofile%\\desktop"}:
            candidate = Path.home() / "Desktop"
        elif lowered in {"coding_projects_root", "project_root", "projects"}:
            candidate = default_coding_root()
        else:
            candidate = Path(token).expanduser()
            if not candidate.is_absolute():
                candidate = Path.home() / candidate
        paths.append(_resolve(candidate))
    default_root = _resolve(default_coding_root())
    if default_root not in paths:
        paths.append(default_root)
    return _dedupe(paths)


def hard_stop_keys() -> set[str]:
    raw = str(config_value("autonomy_hard_stop_keys", "") or "").strip()
    if not raw:
        return set(DEFAULT_HARD_STOP_KEYS)
    return {item for item in _split(raw) if item}


def is_trusted_scope(tool_input: dict[str, Any] | None = None) -> bool:
    paths = scope_paths(tool_input or {})
    return bool(paths) and all(_is_trusted_path(path) for path in paths)


def scope_paths(tool_input: dict[str, Any] | None = None) -> list[Path]:
    tool_input = tool_input or {}
    paths: list[Path] = []
    for field in PATH_FIELDS:
        if field in tool_input:
            paths.extend(_paths_from_value(tool_input.get(field), path_hint=True))
    if not paths:
        paths.append(resolve_coding_root())
    return _dedupe([_resolve(path) for path in paths])


def _allow_if_trusted(key: str, tool_input: dict[str, Any], reason: str) -> dict[str, Any] | None:
    paths = scope_paths(tool_input)
    if not paths or not all(_is_trusted_path(path) for path in paths):
        return None
    return {
        "mode": "allow",
        "allowed": True,
        "requires_confirmation": False,
        "blocked": False,
        "autonomy_override": True,
        "autonomy_reason": reason,
        "autonomy_scope": [str(path) for path in paths],
        "autonomy_permission_key": key,
    }


def _is_trusted_path(path: Path) -> bool:
    candidate = _resolve(path)
    for root in trusted_roots():
        if _same_or_child(candidate, root):
            return True
    return False


def _same_or_child(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        candidate_text = str(candidate).lower().rstrip("\\/")
        root_text = str(root).lower().rstrip("\\/")
        return candidate_text == root_text or candidate_text.startswith(f"{root_text}{os.sep}")


def _paths_from_value(value: Any, *, path_hint: bool = False) -> list[Path]:
    if value is None:
        return []
    if isinstance(value, Path):
        return [value]
    if isinstance(value, (list, tuple, set)):
        paths: list[Path] = []
        for item in value:
            paths.extend(_paths_from_value(item, path_hint=path_hint))
        return paths
    if isinstance(value, dict):
        paths: list[Path] = []
        for key, item in value.items():
            paths.extend(_paths_from_value(item, path_hint=str(key).lower() in PATH_FIELDS))
        return paths
    text = str(value or "").strip()
    if not text:
        return []
    if not path_hint and not _looks_like_path(text):
        return []
    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        candidate = resolve_coding_root(candidate)
    return [candidate]


def _looks_like_path(text: str) -> bool:
    return (
        text.startswith((".", "~"))
        or "\\" in text
        or "/" in text
        or (len(text) > 2 and text[1] == ":")
    )


def _resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except Exception:
        return path


def _dedupe(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _split(raw: str) -> list[str]:
    text = str(raw or "")
    pieces = []
    for chunk in text.replace(";", ",").split(","):
        item = chunk.strip()
        if item:
            pieces.append(item)
    return pieces


def _bool_config(key: str, default: bool = False) -> bool:
    env_key = f"FRIDAY_{key.upper()}"
    if env_key in os.environ:
        return _truthy(os.environ.get(env_key), default)
    return _truthy(config_value(key, default), default)


def _truthy(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "enabled", "full"}:
        return True
    if text in {"0", "false", "no", "off", "disabled", "manual"}:
        return False
    return default


def _summary() -> str:
    if not enabled():
        return "Autonomy control is disabled."
    if full_access_enabled():
        return "Full access is enabled for trusted project scopes; block rules still stop execution."
    if full_autonomy_enabled():
        return "Full autonomy is enabled for trusted Desktop/project scopes; hard-stop actions still require approval."
    return "Supervised autonomy is enabled; ask-first rules remain active."


def _stored_value(key: str) -> str:
    try:
        init_db()
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            row = conn.execute("SELECT value FROM autonomy_settings WHERE key = ?", (key,)).fetchone()
    except Exception:
        return ""
    return str(row[0]) if row else ""


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

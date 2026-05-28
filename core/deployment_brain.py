"""Deployment brain for passive uptime, headers, DNS, and rollback notes."""

from __future__ import annotations

import datetime as dt
import json
import socket
import sqlite3
import ssl
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core import release_manager, trust_proof
from core.config import DATA_DIR, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "deployment_brain.sqlite3"
_LOCK = threading.Lock()
SECURITY_HEADERS = ["strict-transport-security", "content-security-policy", "x-frame-options", "x-content-type-options", "referrer-policy", "permissions-policy"]


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
            CREATE TABLE IF NOT EXISTS deployment_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                target TEXT NOT NULL,
                root TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                proof_report_id INTEGER
            )
            """
        )


def inspect(target: str = "", *, root: str | Path = "", create_proof: bool = True) -> dict[str, Any]:
    init_db()
    base = _safe_root(root) if root else None
    checks: dict[str, Any] = {}
    status = "ok"
    if _clean(target):
        checks["target"] = _inspect_url(_clean(target))
        if not checks["target"].get("ok"):
            status = "attention"
    if base:
        checks["release_plan"] = release_manager.prepare_release(str(base), version="")
    if not checks:
        checks["note"] = "No URL or project root was provided."
        status = "skipped"
    risks = _risks(checks)
    if risks and status == "ok":
        status = "attention"
    summary = f"Deployment brain checked {target or (str(base) if base else 'nothing')}: {len(risks)} risk/hint(s)."
    proof_id = None
    if create_proof:
        report = trust_proof.create_report(
            "Deployment brain inspection",
            changed=["No deployment command was run."],
            tested=[summary],
            failed=risks,
            evidence=[json.dumps(checks, ensure_ascii=True, default=str)[:4000]],
            risks=risks or ["External deploy still requires explicit approval."],
            confidence=0.82 if status == "ok" else 0.6,
            metadata={"target": target, "root": str(base or "")},
        )
        proof_id = int(report.get("id") or 0) or None
    return _store(target, str(base or ""), status, summary, checks, proof_id)


def recent_reports(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM deployment_reports ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 20))),)).fetchall()
    return [_row(row) for row in rows]


def status() -> dict[str, Any]:
    reports = recent_reports(limit=8)
    attention = [item for item in reports if item["status"] == "attention"]
    return {
        "recent": reports,
        "attention_count": len(attention),
        "summary": f"{len(attention)} deployment report(s) need attention." if attention else "Deployment brain is ready.",
    }


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM deployment_reports")


def _inspect_url(target: str) -> dict[str, Any]:
    url = target if target.startswith(("http://", "https://")) else f"https://{target}"
    parsed = urlparse(url)
    host = parsed.hostname or ""
    started = time.perf_counter()
    result: dict[str, Any] = {"url": url, "host": host, "ok": False}
    try:
        result["ip"] = socket.gethostbyname(host) if host else ""
    except Exception as exc:
        result["dns_error"] = exc.__class__.__name__
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "FridayDeploymentBrain/1.0"})
        with urllib.request.urlopen(req, timeout=12) as response:
            headers = {key.lower(): value for key, value in response.headers.items()}
            result.update(
                {
                    "ok": True,
                    "status_code": int(response.status),
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "security_headers": {name: headers.get(name, "") for name in SECURITY_HEADERS},
                    "missing_security_headers": [name for name in SECURITY_HEADERS if not headers.get(name)],
                    "server": headers.get("server", ""),
                }
            )
    except Exception as exc:
        result.update({"ok": False, "error": exc.__class__.__name__, "latency_ms": int((time.perf_counter() - started) * 1000)})
    if parsed.scheme == "https" and host:
        result["ssl"] = _ssl_hint(host)
    return result


def _ssl_hint(host: str) -> dict[str, Any]:
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=8) as sock:
            with context.wrap_socket(sock, server_hostname=host) as wrapped:
                cert = wrapped.getpeercert()
        return {"ok": True, "subject": cert.get("subject", []), "not_after": cert.get("notAfter", "")}
    except Exception as exc:
        return {"ok": False, "error": exc.__class__.__name__}


def _risks(checks: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    target = checks.get("target") if isinstance(checks.get("target"), dict) else {}
    if target:
        if not target.get("ok"):
            risks.append(f"URL check failed: {target.get('error') or target.get('dns_error') or 'unknown'}")
        missing = target.get("missing_security_headers") or []
        if missing:
            risks.append("Missing security headers: " + ", ".join(missing[:6]))
        if str(target.get("url", "")).startswith("http://"):
            risks.append("Target is HTTP, not HTTPS.")
    if checks.get("note"):
        risks.append(str(checks["note"]))
    return risks


def _store(target: str, root: str, status: str, summary: str, payload: dict[str, Any], proof_report_id: int | None) -> dict[str, Any]:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "INSERT INTO deployment_reports(timestamp, target, root, status, summary, payload_json, proof_report_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), _clean(target), root, status, summary, _json_dumps(payload), proof_report_id),
        )
        row = conn.execute("SELECT * FROM deployment_reports WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _row(row)


def _safe_root(root: str | Path) -> Path:
    return resolve_coding_root(root)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "timestamp": str(row["timestamp"]),
        "target": str(row["target"]),
        "root": str(row["root"]),
        "status": str(row["status"]),
        "summary": str(row["summary"]),
        "payload": _json_loads(row["payload_json"], {}),
        "proof_report_id": row["proof_report_id"],
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

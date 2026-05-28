"""Self-reflection journal for Friday's recent behavior."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import cognitive_state, episodic_store, llm, long_term_learning, permissions
from core.config import DATA_DIR, config_value, ensure_runtime_dirs

DB_PATH = DATA_DIR / "self_reflection.sqlite3"
_LOCK = threading.Lock()

CORRECTION_TERMS = (
    "didn't work",
    "did not work",
    "still lied",
    "you lied",
    "not accurate",
    "i said",
    "you got",
    "wrong",
    "failed",
    "not what i asked",
)


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
            CREATE TABLE IF NOT EXISTS reflection_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                trigger TEXT NOT NULL,
                summary TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reflection_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                category TEXT NOT NULL,
                finding TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                severity INTEGER NOT NULL,
                recommended_change TEXT NOT NULL,
                promoted INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES reflection_runs(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reflection_findings_time ON reflection_findings(created_at)")


def reflect_on_command(user_text: str, reply: str = "", success_score: float = 1.0) -> dict[str, Any]:
    init_db()
    category = _classify(user_text, reply, success_score)
    if not category:
        return {}
    severity = 3 if category in {"tool_failure", "unverified_claim"} else 2
    finding = _finding_for(category, user_text, reply)
    recommended = _recommendation_for(category)
    item = _insert_finding(None, category, finding, {"user_text": user_text, "reply": reply, "success_score": success_score}, severity, recommended)
    _maybe_record_learning(item)
    return item


def run_reflection(trigger: str = "scheduled", *, minutes: int | None = None) -> dict[str, Any]:
    init_db()
    window_minutes = int(minutes if minutes is not None else config_value("self_reflection_window_minutes", 60))
    end = dt.datetime.now(dt.timezone.utc).astimezone()
    start = end - dt.timedelta(minutes=max(1, window_minutes))
    started_at = cognitive_state.now_iso()
    run_id = _insert_run(start, end, trigger, "running")
    findings: list[dict[str, Any]] = []

    for event in episodic_store.query_events(date_from=start, date_to=end, limit=100):
        if float(event.get("success_score", 1.0)) < 0.5:
            findings.append(
                _insert_finding(
                    run_id,
                    "tool_failure" if event.get("action_type") == "tool_use" else "failed_action",
                    f"Recent {event.get('action_type')} had low success.",
                    {"event": event},
                    3,
                    "Before retrying, inspect the last tool result and verify the claimed outcome.",
                )
            )
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        latency = float(metadata.get("latency_ms") or 0.0)
        if latency >= float(config_value("self_reflection_slow_latency_ms", 15000)):
            findings.append(
                _insert_finding(
                    run_id,
                    "slow_response",
                    f"Recent action was slow at {latency:.0f} ms.",
                    {"event_id": event.get("id"), "latency_ms": latency},
                    2,
                    "Prefer a direct route or local deterministic handler before using a slow model/tool path.",
                )
            )

    for event in permissions.recent_events(limit=50):
        if str(event.get("decision")) in {"blocked", "cancelled"}:
            findings.append(
                _insert_finding(
                    run_id,
                    "permission_block",
                    f"Permission decision was {event.get('decision')} for {event.get('key')}.",
                    {"permission_event": event},
                    2,
                    "Respect the configured permission and ask for a safer alternative.",
                )
            )

    llm_finding = _llm_reflection_finding(run_id, start, end, findings)
    if llm_finding:
        findings.append(llm_finding)

    for item in findings:
        _maybe_record_learning(item)
    try:
        long_term_learning.auto_promote_self_updates(limit=10)
    except Exception:
        pass
    summary = f"Reflection found {len(findings)} notable item{'s' if len(findings) != 1 else ''}."
    _finish_run(run_id, summary, "done")
    return {"id": run_id, "started_at": started_at, "summary": summary, "findings": findings}


def recent_findings(limit: int = 20, *, promoted: bool | None = None) -> list[dict[str, Any]]:
    init_db()
    where = ""
    params: list[Any] = []
    if promoted is not None:
        where = "WHERE promoted=?"
        params.append(1 if promoted else 0)
    params.append(max(1, min(200, int(limit))))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM reflection_findings {where} ORDER BY id DESC LIMIT ?",
            params,
        ).fetchall()
    return [_finding_from_row(row) for row in rows]


def promote_finding(finding_id: int) -> dict[str, Any]:
    init_db()
    finding = _get_finding(finding_id)
    if not finding:
        raise ValueError(f"Reflection finding {finding_id} not found.")
    learning_id = long_term_learning.record_learning(
        "reflection",
        finding["category"],
        f"{finding['finding']} Recommendation: {finding['recommended_change']}",
        source="self_reflection",
        confidence=0.65,
    )
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE reflection_findings SET promoted=1 WHERE id=?", (int(finding_id),))
    finding["promoted"] = True
    finding["learning_id"] = learning_id
    return finding


def reflection_context(limit: int = 5) -> str:
    findings = recent_findings(limit=limit, promoted=False)
    if not findings:
        return ""
    return "Recent self-reflection:\n" + "\n".join(f"- {item['category']}: {item['finding']}" for item in findings)


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM reflection_findings")
        conn.execute("DELETE FROM reflection_runs")


def _classify(user_text: str, reply: str, success_score: float) -> str:
    lowered = str(user_text or "").lower()
    if any(term in lowered for term in CORRECTION_TERMS):
        if "lied" in lowered or "still" in lowered:
            return "unverified_claim"
        if "i said" in lowered or "not accurate" in lowered:
            return "misheard_command"
        return "user_correction"
    if success_score < 0.5:
        return "tool_failure"
    if "i cannot" in str(reply or "").lower() and "could not" in str(reply or "").lower():
        return "blocked_or_uncertain"
    return ""


def _finding_for(category: str, user_text: str, reply: str) -> str:
    if category == "misheard_command":
        return "The user corrected what Friday heard; attention/STT should treat this as evidence."
    if category == "unverified_claim":
        return "The user reported that Friday claimed success without the real-world effect happening."
    if category == "tool_failure":
        return "A command or tool path appears to have failed."
    if category == "user_correction":
        return "The user corrected Friday's behavior or answer."
    return f"Reflection triggered by user text: {_clean(user_text)[:180]}"


def _recommendation_for(category: str) -> str:
    return {
        "misheard_command": "Record an attention correction and prefer explicit verification before acting on uncertain transcripts.",
        "unverified_claim": "Verify device/app state before saying an action succeeded.",
        "tool_failure": "Inspect the failure and use a more direct deterministic tool path.",
        "user_correction": "Store the correction as low-confidence learning until repeated.",
        "permission_block": "Offer a safer alternative that respects the user's permission settings.",
    }.get(category, "Use this finding as context before repeating the behavior.")


def _insert_run(start: dt.datetime, end: dt.datetime, trigger: str, status: str) -> int:
    now = cognitive_state.now_iso()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO reflection_runs(started_at, completed_at, window_start, window_end, trigger, summary, status)
            VALUES (?, NULL, ?, ?, ?, '', ?)
            """,
            (now, start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds"), _clean(trigger), status),
        )
        return int(cursor.lastrowid)


def _finish_run(run_id: int, summary: str, status: str) -> None:
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute(
            "UPDATE reflection_runs SET completed_at=?, summary=?, status=? WHERE id=?",
            (cognitive_state.now_iso(), _clean(summary), _clean(status), int(run_id)),
        )


def _insert_finding(run_id: int | None, category: str, finding: str, evidence: dict[str, Any], severity: int, recommended_change: str) -> dict[str, Any]:
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO reflection_findings(run_id, category, finding, evidence_json, severity, recommended_change, promoted, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                run_id,
                _clean(category) or "general",
                _clean(finding),
                cognitive_state.to_json(evidence),
                max(1, min(5, int(severity))),
                _clean(recommended_change),
                cognitive_state.now_iso(),
            ),
        )
        finding_id = int(cursor.lastrowid)
    return _get_finding(finding_id) or {}


def _get_finding(finding_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM reflection_findings WHERE id=?", (int(finding_id),)).fetchone()
    return _finding_from_row(row) if row else None


def _finding_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "run_id": row["run_id"],
        "category": str(row["category"]),
        "finding": str(row["finding"]),
        "evidence": cognitive_state.from_json(row["evidence_json"]),
        "severity": int(row["severity"]),
        "recommended_change": str(row["recommended_change"]),
        "promoted": bool(row["promoted"]),
        "created_at": str(row["created_at"]),
    }


def _maybe_record_learning(finding: dict[str, Any]) -> None:
    if not finding or int(finding.get("severity") or 0) < 2:
        return
    try:
        item_id = long_term_learning.record_learning(
            "reflection",
            str(finding.get("category") or "general"),
            f"{finding.get('finding')} Recommendation: {finding.get('recommended_change')}",
            source="self_reflection",
            confidence=0.55,
        )
        long_term_learning.maybe_propose_self_update(item_id)
    except Exception:
        return


def _llm_reflection_finding(
    run_id: int,
    start: dt.datetime,
    end: dt.datetime,
    existing_findings: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not bool(config_value("self_reflection_use_llm", False)):
        return None
    try:
        recent_events = episodic_store.query_events(date_from=start, date_to=end, limit=12)
    except Exception:
        recent_events = []
    try:
        permission_events = permissions.recent_events(limit=8)
    except Exception:
        permission_events = []
    payload = {
        "window": {"start": start.isoformat(timespec="seconds"), "end": end.isoformat(timespec="seconds")},
        "events": [_compact_event(item) for item in recent_events],
        "permission_events": permission_events[:8],
        "existing_findings": [
            {
                "category": item.get("category"),
                "finding": item.get("finding"),
                "severity": item.get("severity"),
                "recommended_change": item.get("recommended_change"),
            }
            for item in existing_findings[-8:]
        ],
    }
    prompt = (
        "You are Friday's self-reflection module. Review this compact telemetry and return only JSON. "
        "If there is a useful extra finding, return an object with keys category, finding, severity, recommended_change. "
        "If there is nothing useful, return {}. Prefer concrete, verifiable improvements. "
        f"Telemetry: {json.dumps(payload, ensure_ascii=True, default=str)[:9000]}"
    )
    try:
        text = llm.ask_simple(prompt, retries=1) or ""
        parsed = _json_object(text)
    except Exception:
        return None
    if not parsed:
        return None
    finding = _clean(parsed.get("finding"))
    recommended = _clean(parsed.get("recommended_change"))
    if not finding or not recommended:
        return None
    return _insert_finding(
        run_id,
        _clean(parsed.get("category")) or "llm_reflection",
        finding,
        {"llm_reflection": parsed, "event_count": len(recent_events)},
        int(parsed.get("severity") or 2),
        recommended,
    )


def _compact_event(event: dict[str, Any]) -> dict[str, Any]:
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    return {
        "id": event.get("id"),
        "action_type": event.get("action_type"),
        "success_score": event.get("success_score"),
        "summary": _clean(event.get("summary") or event.get("outputs"))[:300],
        "latency_ms": metadata.get("latency_ms"),
    }


def _json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.replace("json\n", "", 1).replace("JSON\n", "", 1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end >= start:
        raw = raw[start : end + 1]
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())

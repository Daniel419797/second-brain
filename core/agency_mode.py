"""Friday Agency Mode: leads, outreach approvals, projects, invoices, and profit tracking."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
import threading
from pathlib import Path
from typing import Any

from core import autonomous_qa_lab, autonomous_release_engine, command_runner, deployment_brain, git_integration, mission_control, search_broker, task_queue
from core.config import DATA_DIR, config_value, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "agency_mode.sqlite3"
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
            CREATE TABLE IF NOT EXISTS agency_leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                name TEXT NOT NULL,
                company TEXT NOT NULL,
                email TEXT NOT NULL,
                website TEXT NOT NULL,
                source_url TEXT NOT NULL,
                niche TEXT NOT NULL,
                location TEXT NOT NULL,
                need TEXT NOT NULL,
                status TEXT NOT NULL,
                fit_score REAL NOT NULL,
                score_reason TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agency_leads_status ON agency_leads(status, fit_score)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agency_outreach (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                channel TEXT NOT NULL,
                recipient TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL,
                approval_note TEXT NOT NULL,
                approved_at TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                send_result TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agency_outreach_status ON agency_outreach(status, lead_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agency_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                name TEXT NOT NULL,
                root TEXT NOT NULL,
                status TEXT NOT NULL,
                brief TEXT NOT NULL,
                budget REAL NOT NULL,
                currency TEXT NOT NULL,
                task_id INTEGER,
                mission_id INTEGER,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agency_invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                client_name TEXT NOT NULL,
                client_email TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                status TEXT NOT NULL,
                due_at TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                paid_at TEXT NOT NULL,
                line_items_json TEXT NOT NULL,
                path TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agency_invoices_status ON agency_invoices(status, due_at)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agency_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                kind TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                related_id INTEGER,
                metadata_json TEXT NOT NULL
            )
            """
        )


def status() -> dict[str, Any]:
    init_db()
    summary = profit_summary()
    pending_outreach = list_outreach(status="draft", limit=10)
    approved_outreach = list_outreach(status="approved", limit=10)
    open_projects = list_projects(status="active", limit=10)
    return {
        "enabled": bool(config_value("agency_mode_enabled", True)),
        "lead_count": _count("agency_leads"),
        "draft_outreach": pending_outreach,
        "approved_outreach": approved_outreach,
        "open_projects": open_projects,
        "finance": summary,
        "summary": f"Agency has {_count('agency_leads')} lead(s), {len(pending_outreach)} draft outreach item(s), {len(approved_outreach)} approved item(s), and {summary['profit']:.2f} {summary['currency']} tracked profit.",
    }


def search_leads(query: str = "", *, niche: str = "", location: str = "", limit: int = 5) -> dict[str, Any]:
    init_db()
    if not bool(config_value("agency_mode_enabled", True)):
        return {"ok": False, "leads": [], "summary": "Agency Mode is disabled."}
    search_query = _lead_query(query, niche=niche, location=location)
    payload = search_broker.search(search_query, limit=limit)
    leads = []
    for item in payload.get("results") or []:
        lead = add_lead(
            name=str(item.get("title") or "Untitled lead"),
            company=_company_from_title(str(item.get("title") or "")),
            website=str(item.get("url") or ""),
            source_url=str(item.get("url") or ""),
            niche=niche,
            location=location,
            need=str(item.get("snippet") or ""),
            metadata={"source": "search_broker", "provider": item.get("provider"), "rank": item.get("rank"), "query": search_query},
        )
        leads.append(score_lead(int(lead["id"])))
    return {
        "ok": bool(leads),
        "query": search_query,
        "leads": leads,
        "search": payload,
        "summary": f"Found and stored {len(leads)} lead(s) for {search_query}.",
    }


def add_lead(
    name: str,
    *,
    company: str = "",
    email: str = "",
    website: str = "",
    source_url: str = "",
    niche: str = "",
    location: str = "",
    need: str = "",
    status: str = "new",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    clean_name = _clean(name) or _clean(company) or _domain_name(website) or "Untitled lead"
    clean_company = _clean(company) or clean_name
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO agency_leads(created_at, updated_at, name, company, email, website, source_url, niche, location, need, status, fit_score, score_reason, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, '', ?)
            """,
            (
                now,
                now,
                clean_name,
                clean_company,
                _clean(email),
                _clean_url(website),
                _clean_url(source_url),
                _clean(niche),
                _clean(location),
                _clean(need)[:4000],
                _status(status, {"new", "qualified", "contacted", "replied", "won", "lost", "paused"}),
                _json_dumps(metadata or {}),
            ),
        )
        row = conn.execute("SELECT * FROM agency_leads WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _lead_row(row)


def get_lead(lead_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM agency_leads WHERE id=?", (int(lead_id),)).fetchone()
    return _lead_row(row) if row else None


def list_leads(status: str = "", limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    params: list[Any] = []
    where = ""
    if _clean(status):
        where = "WHERE status=?"
        params.append(_clean(status))
    params.append(_limit(limit, 200))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM agency_leads {where} ORDER BY fit_score DESC, id DESC LIMIT ?", params).fetchall()
    return [_lead_row(row) for row in rows]


def score_lead(lead_id: int, *, service_keywords: str = "") -> dict[str, Any]:
    lead = _require_lead(lead_id)
    keywords = _keywords(service_keywords or str(config_value("agency_service_keywords", "website,web app,automation,ai,chatbot,dashboard,ecommerce,booking,crm,invoice,portfolio")))
    text = " ".join(str(lead.get(key) or "") for key in ("name", "company", "niche", "need", "website")).lower()
    score = 35.0
    reasons = []
    if lead.get("email"):
        score += 18
        reasons.append("direct email available")
    if lead.get("website"):
        score += 12
        reasons.append("website/source found")
    hits = [word for word in keywords if word and word in text]
    if hits:
        score += min(30, 8 * len(hits))
        reasons.append(f"matches services: {', '.join(hits[:5])}")
    if any(term in text for term in ("hire", "looking for", "need", "build", "redesign", "automate", "launch")):
        score += 18
        reasons.append("need signal present")
    if any(term in text for term in ("free", "internship", "volunteer")):
        score -= 15
        reasons.append("weak budget signal")
    score = max(0.0, min(100.0, round(score, 2)))
    reason = "; ".join(reasons) or "Basic lead stored; needs qualification."
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE agency_leads SET fit_score=?, score_reason=?, updated_at=? WHERE id=?", (score, reason, _now(), int(lead_id)))
    updated = get_lead(lead_id) or lead
    updated["summary"] = f"{updated['company']} scored {score:.0f}/100: {reason}"
    return updated


def score_all_leads(limit: int = 100) -> dict[str, Any]:
    leads = [score_lead(int(item["id"])) for item in list_leads(limit=limit)]
    return {"scored": len(leads), "leads": leads, "summary": f"Scored {len(leads)} lead(s)."}


def draft_outreach(
    lead_id: int,
    *,
    channel: str = "email",
    service_offer: str = "",
    tone: str = "professional",
    portfolio_url: str = "",
    call_to_action: str = "",
) -> dict[str, Any]:
    lead = _require_lead(lead_id)
    clean_channel = _status(channel, {"email", "linkedin", "whatsapp", "twitter", "manual"})
    subject = _draft_subject(lead, service_offer)
    body = _draft_body(lead, service_offer=service_offer, tone=tone, portfolio_url=portfolio_url, call_to_action=call_to_action)
    recipient = str(lead.get("email") or "")
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO agency_outreach(lead_id, created_at, updated_at, channel, recipient, subject, body, status, approval_note, approved_at, sent_at, send_result, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', '', '', '', '', ?)
            """,
            (
                int(lead_id),
                now,
                now,
                clean_channel,
                recipient,
                subject,
                body,
                _json_dumps({"tone": tone, "portfolio_url": portfolio_url, "service_offer": service_offer}),
            ),
        )
        row = conn.execute("SELECT * FROM agency_outreach WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    outreach = _outreach_row(row)
    outreach["lead"] = lead
    outreach["summary"] = f"Drafted {clean_channel} outreach #{outreach['id']} for {lead['company']}. It is not approved or sent."
    return outreach


def list_outreach(status: str = "", limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    params: list[Any] = []
    where = ""
    if _clean(status):
        where = "WHERE status=?"
        params.append(_clean(status))
    params.append(_limit(limit, 200))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM agency_outreach {where} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_outreach_row(row) for row in rows]


def approve_outreach(ids: int | list[int], *, note: str = "") -> dict[str, Any]:
    outreach_ids = _ids(ids)
    approved = []
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        for outreach_id in outreach_ids:
            row = conn.execute("SELECT * FROM agency_outreach WHERE id=?", (int(outreach_id),)).fetchone()
            if not row:
                continue
            item = _outreach_row(row)
            if item["status"] == "sent":
                continue
            conn.execute(
                "UPDATE agency_outreach SET status='approved', approval_note=?, approved_at=?, updated_at=? WHERE id=?",
                (_clean(note), _now(), _now(), int(outreach_id)),
            )
            approved.append(int(outreach_id))
    return {"approved": approved, "summary": f"Approved {len(approved)} outreach draft(s). Sending is a separate action."}


def send_outreach(ids: int | list[int]) -> dict[str, Any]:
    outreach_ids = _ids(ids)
    sent = []
    failed = []
    limit = int(config_value("agency_outreach_daily_limit", 20))
    already_sent_today = _sent_today_count()
    for outreach_id in outreach_ids:
        item = get_outreach(outreach_id)
        if not item:
            failed.append({"id": outreach_id, "reason": "not found"})
            continue
        if item["status"] != "approved":
            failed.append({"id": outreach_id, "reason": "not approved"})
            continue
        if already_sent_today + len(sent) >= limit:
            failed.append({"id": outreach_id, "reason": f"agency daily outreach limit {limit} reached"})
            continue
        if item["channel"] != "email":
            failed.append({"id": outreach_id, "reason": f"{item['channel']} sending is manual-only"})
            continue
        if not item["recipient"]:
            failed.append({"id": outreach_id, "reason": "recipient email missing"})
            continue
        blocked = _send_permission_blocked(item)
        if blocked:
            failed.append({"id": outreach_id, "reason": blocked})
            continue
        result = _send_email(item)
        if result.lower().startswith("email sent"):
            _mark_outreach_sent(outreach_id, result)
            sent.append({"id": outreach_id, "result": result})
            _record_lead_status(int(item["lead_id"]), "contacted")
        else:
            _mark_outreach_failed(outreach_id, result)
            failed.append({"id": outreach_id, "reason": result})
    return {"sent": sent, "failed": failed, "summary": f"Sent {len(sent)} approved outreach item(s); {len(failed)} failed or skipped."}


def get_outreach(outreach_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM agency_outreach WHERE id=?", (int(outreach_id),)).fetchone()
    return _outreach_row(row) if row else None


def draft_proposal(lead_id: int, *, scope: str = "", price: float = 0.0, currency: str = "") -> dict[str, Any]:
    lead = _require_lead(lead_id)
    text = _proposal_text(lead, scope=scope, price=price, currency=currency or _currency())
    path = _write_document("proposals", f"proposal-{lead['id']}-{_slug(lead['company'])}.md", text)
    return {"lead": lead, "path": str(path), "content": text, "summary": f"Proposal draft saved to {path}."}


def draft_contract(lead_id: int, *, scope: str = "", price: float = 0.0, currency: str = "") -> dict[str, Any]:
    lead = _require_lead(lead_id)
    text = _contract_text(lead, scope=scope, price=price, currency=currency or _currency())
    path = _write_document("contracts", f"contract-draft-{lead['id']}-{_slug(lead['company'])}.md", text)
    return {"lead": lead, "path": str(path), "content": text, "summary": f"Contract draft saved to {path}. Human/legal review required before signing."}


def draft_project_plan(lead_id: int, *, scope: str = "", timeline: str = "") -> dict[str, Any]:
    lead = _require_lead(lead_id)
    text = _project_plan_text(lead, scope=scope, timeline=timeline)
    path = _write_document("project-plans", f"project-plan-{lead['id']}-{_slug(lead['company'])}.md", text)
    return {"lead": lead, "path": str(path), "content": text, "summary": f"Project plan draft saved to {path}."}


def start_client_project(
    lead_id: int = 0,
    *,
    name: str = "",
    brief: str = "",
    budget: float = 0.0,
    currency: str = "",
) -> dict[str, Any]:
    lead = get_lead(lead_id) if lead_id else None
    project_name = _clean(name) or (f"{lead['company']} project" if lead else "Client project")
    root = _agency_workspace() / "projects" / _slug(project_name)
    root.mkdir(parents=True, exist_ok=True)
    project_brief = _clean(brief) or (str(lead.get("need") or "") if lead else "")
    readme = _project_readme(project_name, project_brief, lead)
    (root / "README.md").write_text(readme, encoding="utf-8")
    task_id = task_queue.create_task(
        f"Client project: {project_name}",
        description=project_brief or "Build the client project from Agency Mode.",
        agent_id="senior_developer",
        priority=2,
        input_data={"source": "agency_mode", "lead_id": lead_id, "root": str(root), "brief": project_brief},
    )
    mission = mission_control.create_mission(f"Build client project: {project_name}", root=root, mission_type="project_builder", metadata={"source": "agency_mode", "lead_id": lead_id})
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO agency_projects(lead_id, created_at, updated_at, name, root, status, brief, budget, currency, task_id, mission_id, metadata_json)
            VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
            """,
            (int(lead_id) if lead_id else None, now, now, project_name, str(root), project_brief, float(budget or 0), _clean(currency).upper() or _currency(), int(task_id), int(mission.get("id") or 0), _json_dumps({"lead": lead or {}})),
        )
        row = conn.execute("SELECT * FROM agency_projects WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    project = _project_row(row)
    return project | {"mission": mission, "task_id": task_id, "summary": f"Client project #{project['id']} started at {root}."}


def get_project(project_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM agency_projects WHERE id=?", (int(project_id),)).fetchone()
    return _project_row(row) if row else None


def list_projects(status: str = "", limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    params: list[Any] = []
    where = ""
    if _clean(status):
        where = "WHERE status=?"
        params.append(_clean(status))
    params.append(_limit(limit, 200))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM agency_projects {where} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_project_row(row) for row in rows]


def run_project_workflow(project_id: int, *, commit: bool = False, push: bool = False, deploy: bool = False, deploy_command: str = "", target_url: str = "") -> dict[str, Any]:
    project = _require_project(project_id)
    root = Path(project["root"])
    qa = autonomous_qa_lab.run_qa(root, run_tests=bool(config_value("agency_project_run_tests", True)))
    release = autonomous_release_engine.prepare(root, run_tests=False)
    git_status = git_integration.status(root)
    git_add = git_commit = git_push = {}
    deployment = {}
    if commit:
        git_add = git_integration.add(root, paths=".")
        git_commit = git_integration.commit(root, message=f"Agency project update: {project['name']}")
    if push:
        git_push = git_integration.push(root)
    if deploy:
        deployment = _run_configured_deploy(root, deploy_command=deploy_command, target_url=target_url)
    return {
        "project": project,
        "qa": qa,
        "release": release,
        "git_status": git_status,
        "git_add": git_add,
        "git_commit": git_commit,
        "git_push": git_push,
        "deployment": deployment,
        "summary": f"Project workflow checked {project['name']}: QA={qa.get('status')}, release={release.get('status')}.",
    }


def create_invoice(
    project_id: int = 0,
    *,
    client_name: str = "",
    client_email: str = "",
    amount: float = 0.0,
    currency: str = "",
    due_at: str = "",
    line_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    project = get_project(project_id) if project_id else None
    lead = get_lead(int(project.get("lead_id") or 0)) if project and project.get("lead_id") else None
    items = line_items or [{"description": project["name"] if project else "Client services", "amount": float(amount or 0)}]
    total = float(amount or sum(float(item.get("amount") or 0) for item in items))
    name = _clean(client_name) or (str(lead.get("company") or "") if lead else "Client")
    email = _clean(client_email) or (str(lead.get("email") or "") if lead else "")
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO agency_invoices(project_id, created_at, updated_at, client_name, client_email, amount, currency, status, due_at, issued_at, paid_at, line_items_json, path, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, '', ?, '', '{}')
            """,
            (int(project_id) if project_id else None, now, now, name, email, total, _clean(currency).upper() or _currency(), _clean(due_at), now, _json_dumps(items)),
        )
        invoice_id = int(cursor.lastrowid)
        path = _write_invoice(invoice_id, name, email, total, _clean(currency).upper() or _currency(), items, due_at)
        conn.execute("UPDATE agency_invoices SET path=? WHERE id=?", (str(path), invoice_id))
        row = conn.execute("SELECT * FROM agency_invoices WHERE id=?", (invoice_id,)).fetchone()
    invoice = _invoice_row(row)
    return invoice | {"summary": f"Invoice #{invoice['id']} generated for {invoice['amount']:.2f} {invoice['currency']} at {invoice['path']}."}


def mark_invoice_paid(invoice_id: int, *, amount: float = 0.0) -> dict[str, Any]:
    invoice = _require_invoice(invoice_id)
    paid_amount = float(amount or invoice["amount"])
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE agency_invoices SET status='paid', paid_at=?, updated_at=? WHERE id=?", (_now(), _now(), int(invoice_id)))
    record_ledger("revenue", paid_amount, currency=invoice["currency"], category="client_payment", description=f"Invoice #{invoice_id} paid", related_id=invoice_id)
    return get_invoice(invoice_id) or invoice


def get_invoice(invoice_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM agency_invoices WHERE id=?", (int(invoice_id),)).fetchone()
    return _invoice_row(row) if row else None


def list_invoices(status: str = "", limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    params: list[Any] = []
    where = ""
    if _clean(status):
        where = "WHERE status=?"
        params.append(_clean(status))
    params.append(_limit(limit, 200))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM agency_invoices {where} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_invoice_row(row) for row in rows]


def record_ledger(
    kind: str,
    amount: float,
    *,
    currency: str = "",
    category: str = "",
    description: str = "",
    status: str = "recorded",
    related_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_db()
    normalized_kind = _status(kind, {"revenue", "expense", "api_usage", "payment_recommendation", "payment_approved", "payment_triggered"})
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            INSERT INTO agency_ledger(timestamp, kind, amount, currency, category, description, status, related_id, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_now(), normalized_kind, float(amount), _clean(currency).upper() or _currency(), _clean(category) or normalized_kind, _clean(description)[:2000], _clean(status) or "recorded", related_id, _json_dumps(metadata or {})),
        )
        row = conn.execute("SELECT * FROM agency_ledger WHERE id=?", (int(cursor.lastrowid),)).fetchone()
    return _ledger_row(row)


def list_ledger(kind: str = "", limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    params: list[Any] = []
    where = ""
    if _clean(kind):
        where = "WHERE kind=?"
        params.append(_clean(kind))
    params.append(_limit(limit, 500))
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM agency_ledger {where} ORDER BY id DESC LIMIT ?", params).fetchall()
    return [_ledger_row(row) for row in rows]


def profit_summary(currency: str = "") -> dict[str, Any]:
    target_currency = (_clean(currency).upper() or _currency())
    ledger = list_ledger(limit=500)
    revenue = sum(float(item["amount"]) for item in ledger if item["currency"] == target_currency and item["kind"] == "revenue")
    expenses = sum(float(item["amount"]) for item in ledger if item["currency"] == target_currency and item["kind"] in {"expense", "api_usage", "payment_triggered"})
    pending_payments = [item for item in ledger if item["kind"] == "payment_recommendation" and item["status"] == "pending_approval"]
    return {
        "currency": target_currency,
        "revenue": round(revenue, 2),
        "expenses": round(expenses, 2),
        "profit": round(revenue - expenses, 2),
        "pending_payment_recommendations": pending_payments,
        "summary": f"Agency revenue {revenue:.2f}, expenses {expenses:.2f}, profit {revenue - expenses:.2f} {target_currency}.",
    }


def recommend_payment(provider: str, amount: float, *, reason: str = "", currency: str = "") -> dict[str, Any]:
    item = record_ledger(
        "payment_recommendation",
        amount,
        currency=currency or _currency(),
        category="api_keys",
        description=f"{_clean(provider) or 'Provider'}: {_clean(reason) or 'API subscription/top-up recommended'}",
        status="pending_approval",
        metadata={"provider": provider, "requires_human_payment_account": True},
    )
    return item | {"summary": f"Payment recommendation #{item['id']} is pending approval; Friday will not pay without approval."}


def approve_payment(recommendation_id: int, *, note: str = "") -> dict[str, Any]:
    item = _require_ledger(recommendation_id)
    if item["kind"] != "payment_recommendation":
        raise ValueError("ledger item is not a payment recommendation")
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE agency_ledger SET status='approved', description=description || ? WHERE id=?", (f" Approved: {_clean(note)}" if note else " Approved.", int(recommendation_id)))
    approved = record_ledger("payment_approved", item["amount"], currency=item["currency"], category=item["category"], description=f"Approved payment recommendation #{recommendation_id}", related_id=recommendation_id, metadata=item["metadata"])
    return approved | {"summary": f"Payment recommendation #{recommendation_id} approved. Actual payment still needs the configured payment provider or manual checkout."}


def trigger_approved_payment(recommendation_id: int) -> dict[str, Any]:
    item = _require_ledger(recommendation_id)
    if item["status"] != "approved":
        return {"ok": False, "summary": "Payment recommendation is not approved."}
    triggered = record_ledger("payment_triggered", item["amount"], currency=item["currency"], category=item["category"], description=f"Manual/API-key payment action queued for recommendation #{recommendation_id}", related_id=recommendation_id, metadata=item["metadata"])
    return triggered | {"ok": True, "summary": "Approved payment was recorded as triggered. Friday does not enter card/bank details or bypass payment-provider approval."}


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        for table in ("agency_outreach", "agency_projects", "agency_invoices", "agency_ledger", "agency_leads"):
            conn.execute(f"DELETE FROM {table}")


def _require_lead(lead_id: int) -> dict[str, Any]:
    lead = get_lead(lead_id)
    if not lead:
        raise ValueError("lead not found")
    return lead


def _require_project(project_id: int) -> dict[str, Any]:
    project = get_project(project_id)
    if not project:
        raise ValueError("project not found")
    return project


def _require_invoice(invoice_id: int) -> dict[str, Any]:
    invoice = get_invoice(invoice_id)
    if not invoice:
        raise ValueError("invoice not found")
    return invoice


def _require_ledger(item_id: int) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM agency_ledger WHERE id=?", (int(item_id),)).fetchone()
    if not row:
        raise ValueError("ledger item not found")
    return _ledger_row(row)


def _send_permission_blocked(item: dict[str, Any]) -> str:
    try:
        from core import permissions

        decision = permissions.evaluate("send_email", {"action": "send_email", "to": item["recipient"], "subject": item["subject"]})
        if decision.get("blocked"):
            return f"Permission blocked: {decision.get('label')}."
    except Exception:
        return ""
    return ""


def _send_email(item: dict[str, Any]) -> str:
    try:
        from tools import email_tool

        sender = os.getenv("GMAIL_ADDRESS")
        password = os.getenv("GMAIL_APP_PASSWORD")
        if not sender or not password:
            return "Email not configured."
        return email_tool._send(item["recipient"], item["subject"], item["body"], sender=sender, password=password)
    except Exception as exc:
        return f"Email send failed: {exc}"


def _mark_outreach_sent(outreach_id: int, result: str) -> None:
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE agency_outreach SET status='sent', sent_at=?, send_result=?, updated_at=? WHERE id=?", (_now(), _clean(result), _now(), int(outreach_id)))


def _mark_outreach_failed(outreach_id: int, result: str) -> None:
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE agency_outreach SET status='failed', send_result=?, updated_at=? WHERE id=?", (_clean(result), _now(), int(outreach_id)))


def _record_lead_status(lead_id: int, status: str) -> None:
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE agency_leads SET status=?, updated_at=? WHERE id=?", (_clean(status), _now(), int(lead_id)))


def _run_configured_deploy(root: Path, *, deploy_command: str = "", target_url: str = "") -> dict[str, Any]:
    if not bool(config_value("agency_deploy_enabled", False)):
        return {"ok": False, "status": "skipped", "summary": "Agency deployment is disabled. Set agency_deploy_enabled and a deploy command first."}
    command = _clean(deploy_command) or str(config_value("agency_default_deploy_command", "") or "").strip()
    if not command:
        return {"ok": False, "status": "skipped", "summary": "No agency deploy command is configured."}
    timeout = max(30, int(float(config_value("agency_deploy_timeout_seconds", 600))))
    try:
        completed = command_runner.run(command, cwd=root, timeout=timeout)
        ok = completed.returncode == 0
        result: dict[str, Any] = {
            "ok": ok,
            "status": "deployed" if ok else "failed",
            "command": command,
            "cwd": str(root),
            "returncode": completed.returncode,
            "stdout": _bounded_text(completed.stdout),
            "stderr": _bounded_text(completed.stderr),
            "summary": "Agency deploy command completed." if ok else "Agency deploy command failed.",
        }
    except command_runner.CommandRejected as exc:
        result = {"ok": False, "status": "rejected", "command": command, "cwd": str(root), "summary": f"Deploy command rejected: {exc}"}
    except subprocess.TimeoutExpired as exc:
        result = {"ok": False, "status": "timeout", "command": command, "cwd": str(root), "summary": f"Deploy command timed out after {timeout} seconds.", "stderr": _bounded_text(str(exc))}
    except Exception as exc:
        result = {"ok": False, "status": "error", "command": command, "cwd": str(root), "summary": f"Deploy command failed: {exc}"}
    check_url = _clean(target_url) or str(config_value("agency_deploy_target_url", "") or "").strip()
    if check_url:
        result["deployment_check"] = deployment_brain.inspect(check_url, root=root, create_proof=True)
    return result


def _sent_today_count() -> int:
    today = dt.datetime.now(dt.timezone.utc).astimezone().date().isoformat()
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM agency_outreach WHERE status='sent' AND sent_at LIKE ?", (f"{today}%",)).fetchone()[0])


def _lead_query(query: str, *, niche: str, location: str) -> str:
    if _clean(query):
        return _clean(query)
    parts = [_clean(niche) or "small businesses", "needing website app automation developer"]
    if _clean(location):
        parts.append(_clean(location))
    return " ".join(parts)


def _draft_subject(lead: dict[str, Any], service_offer: str) -> str:
    offer = _clean(service_offer) or "a faster website and automation workflow"
    return f"Idea for {lead['company']}: {offer}"


def _draft_body(lead: dict[str, Any], *, service_offer: str, tone: str, portfolio_url: str, call_to_action: str) -> str:
    offer = _clean(service_offer) or "a clean website, client portal, automation, or AI assistant workflow"
    cta = _clean(call_to_action) or "Would it be useful if I sent a 1-page plan for how this could work?"
    lines = [
        f"Hi {lead['company']} team,",
        "",
        f"I came across {lead.get('website') or lead.get('source_url') or 'your business'} and noticed a possible opportunity to improve {offer}.",
        "",
        "I help small teams turn messy manual work into simple web apps, dashboards, automations, and client-facing tools.",
    ]
    if lead.get("need"):
        lines.extend(["", f"What caught my eye: {lead['need'][:320]}"])
    if portfolio_url:
        lines.extend(["", f"Portfolio: {portfolio_url}"])
    lines.extend(["", cta, "", "Best,", "Friday Agency"])
    if _clean(tone).lower() == "short":
        return "\n".join([lines[0], "", lines[2], "", cta, "", "Best,\nFriday Agency"])
    return "\n".join(lines)


def _proposal_text(lead: dict[str, Any], *, scope: str, price: float, currency: str) -> str:
    scope_text = _clean(scope) or "Discovery, design, implementation, QA, deployment support, and handoff documentation."
    price_text = f"{price:.2f} {currency}" if price else "To be confirmed after discovery"
    return f"""# Proposal Draft: {lead['company']}

## Goal
Help {lead['company']} improve revenue operations with a focused software/content/research deliverable.

## Proposed Scope
{scope_text}

## Deliverables
- Requirements and success criteria
- Working project under the Friday Desktop project root
- QA evidence and release notes
- Deployment/runbook support when configured
- Final handoff documentation

## Estimated Price
{price_text}

## Next Step
Confirm scope, timeline, acceptance criteria, and payment terms before work starts.
"""


def _contract_text(lead: dict[str, Any], *, scope: str, price: float, currency: str) -> str:
    return f"""# Service Agreement Draft: {lead['company']}

This is a draft for review, not legal advice.

## Parties
- Client: {lead['company']}
- Service Provider: Friday Agency / business owner

## Scope
{_clean(scope) or 'Software, content, research, automation, or deployment services described in the approved proposal.'}

## Fees
{f'{price:.2f} {currency}' if price else 'Fees to be confirmed in the invoice/proposal.'}

## Approval And Payment
Work begins after written client approval and payment terms are accepted by the human business owner.

## Client Responsibilities
Client provides accurate requirements, brand assets, credentials through secure channels, and timely feedback.

## Provider Responsibilities
Provider builds, tests, documents, and reports limitations honestly.

## Signatures
Human review and signature required before this agreement is valid.
"""


def _project_plan_text(lead: dict[str, Any], *, scope: str, timeline: str) -> str:
    return f"""# Project Plan: {lead['company']}

## Scope
{_clean(scope) or lead.get('need') or 'Define requirements, build the solution, verify quality, and prepare handoff.'}

## Timeline
{_clean(timeline) or 'Discovery -> build -> QA -> review -> deployment/handoff.'}

## Milestones
1. Discovery and acceptance criteria
2. Prototype or first implementation
3. QA, fixes, and documentation
4. Client review
5. Release or handoff

## Risks
- Missing client content or credentials
- Provider/API costs
- Deployment access delays
- Scope creep without updated approval
"""


def _project_readme(name: str, brief: str, lead: dict[str, Any] | None) -> str:
    return f"""# {name}

Client: {lead.get('company') if lead else 'Unassigned'}

## Brief
{brief or 'Client project created from Friday Agency Mode.'}

## Operating Notes
- Keep implementation, QA evidence, deployment notes, and invoice references in this folder.
- Do not store client secrets or payment details in the repository.
"""


def _write_invoice(invoice_id: int, client_name: str, client_email: str, amount: float, currency: str, items: list[dict[str, Any]], due_at: str) -> Path:
    lines = [
        f"# Invoice #{invoice_id}",
        "",
        f"Client: {client_name}",
        f"Email: {client_email}",
        f"Issued: {_now()}",
        f"Due: {_clean(due_at) or 'Upon receipt'}",
        "",
        "## Line Items",
    ]
    for item in items:
        lines.append(f"- {item.get('description') or 'Service'}: {float(item.get('amount') or 0):.2f} {currency}")
    lines.extend(["", f"Total: {amount:.2f} {currency}", "", "Payment instructions must be provided by the human business owner."])
    return _write_document("invoices", f"invoice-{invoice_id}.md", "\n".join(lines))


def _write_document(folder: str, filename: str, content: str) -> Path:
    root = _agency_workspace() / folder
    root.mkdir(parents=True, exist_ok=True)
    target = root / Path(filename).name
    target.write_text(content, encoding="utf-8")
    return target


def _agency_workspace() -> Path:
    raw = str(config_value("agency_workspace_dir", "Friday Agency") or "Friday Agency").strip()
    return resolve_coding_root(raw)


def _lead_row(row: sqlite3.Row) -> dict[str, Any]:
    data = {key: row[key] for key in row.keys() if key != "metadata_json"}
    data["id"] = int(data["id"])
    data["fit_score"] = float(data["fit_score"])
    data["metadata"] = _json_loads(row["metadata_json"], {})
    return data


def _outreach_row(row: sqlite3.Row) -> dict[str, Any]:
    data = {key: row[key] for key in row.keys() if key != "metadata_json"}
    data["id"] = int(data["id"])
    data["lead_id"] = int(data["lead_id"])
    data["metadata"] = _json_loads(row["metadata_json"], {})
    return data


def _project_row(row: sqlite3.Row) -> dict[str, Any]:
    data = {key: row[key] for key in row.keys() if key != "metadata_json"}
    data["id"] = int(data["id"])
    data["lead_id"] = int(data["lead_id"] or 0)
    data["budget"] = float(data["budget"])
    data["task_id"] = int(data["task_id"] or 0)
    data["mission_id"] = int(data["mission_id"] or 0)
    data["metadata"] = _json_loads(row["metadata_json"], {})
    return data


def _invoice_row(row: sqlite3.Row) -> dict[str, Any]:
    data = {key: row[key] for key in row.keys() if key not in {"line_items_json", "metadata_json"}}
    data["id"] = int(data["id"])
    data["project_id"] = int(data["project_id"] or 0)
    data["amount"] = float(data["amount"])
    data["line_items"] = _json_loads(row["line_items_json"], [])
    data["metadata"] = _json_loads(row["metadata_json"], {})
    return data


def _ledger_row(row: sqlite3.Row) -> dict[str, Any]:
    data = {key: row[key] for key in row.keys() if key != "metadata_json"}
    data["id"] = int(data["id"])
    data["amount"] = float(data["amount"])
    data["related_id"] = int(data["related_id"] or 0)
    data["metadata"] = _json_loads(row["metadata_json"], {})
    return data


def _count(table: str) -> int:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _ids(value: int | list[int]) -> list[int]:
    items = value if isinstance(value, list) else [value]
    return [int(item) for item in items if int(item or 0) > 0]


def _keywords(raw: str) -> list[str]:
    return [item.strip().lower() for item in str(raw or "").replace(";", ",").split(",") if item.strip()]


def _company_from_title(title: str) -> str:
    text = re.sub(r"\s*[-|:]\s*.*$", "", _clean(title))
    return text[:120] or "Unknown company"


def _domain_name(url: str) -> str:
    match = re.search(r"https?://(?:www\.)?([^/]+)", str(url or ""), re.IGNORECASE)
    return match.group(1).split(".")[0].title() if match else ""


def _clean_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text if re.match(r"^https?://", text, flags=re.IGNORECASE) else f"https://{text}"


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", _clean(value).lower()).strip(".-")
    return slug[:80] or "item"


def _status(value: str, allowed: set[str]) -> str:
    normalized = _clean(value).lower().replace(" ", "_")
    return normalized if normalized in allowed else sorted(allowed)[0]


def _limit(value: int, maximum: int) -> int:
    return max(1, min(maximum, int(value or 20)))


def _currency() -> str:
    return str(config_value("agency_default_currency", "USD") or "USD").strip().upper()


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _bounded_text(value: str, limit: int = 4000) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "\n...<truncated>"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

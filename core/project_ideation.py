"""Research-backed project ideation for Friday."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core import friday_memory, research
from core.config import DATA_DIR, ensure_runtime_dirs, resolve_coding_root

DB_PATH = DATA_DIR / "project_ideation.sqlite3"
IDEA_DIR = ".friday/project-ideas"
_LOCK = threading.Lock()

DEMAND_TERMS = (
    "pain point",
    "problem",
    "need",
    "looking for",
    "struggle",
    "manual",
    "time-consuming",
    "spreadsheet",
    "workflow",
    "customer",
    "small business",
    "founder",
    "freelancer",
    "support",
    "invoice",
    "onboarding",
    "scheduling",
    "content",
    "lead",
)

SIGNALS = {
    "higher_ed_operations": {
        "keywords": ("university", "higher ed", "campus", "registrar", "enrollment", "admissions", "faculty", "lecturer", "student records", "course"),
        "title": "Campus Operations Dashboard",
        "problem": "University administrators lose time coordinating student records, course approvals, enrollment issues, fees, and faculty workflows across disconnected systems.",
        "wedge": "Role-based dashboards for registrar, finance, faculty, and student-services teams with approval queues, alerts, and source-backed admin summaries.",
    },
    "higher_ed_scheduling": {
        "keywords": ("scheduler", "scheduling", "timetable", "class schedule", "room allocation", "academic calendar", "course planning"),
        "title": "Academic Scheduling Copilot",
        "problem": "Universities struggle with timetable conflicts, room allocation, academic-calendar changes, and slow schedule communication.",
        "wedge": "Conflict detection, room/course timetable planning, approval workflows, and change notifications for staff and students.",
    },
    "higher_ed_it_consolidation": {
        "keywords": ("integrated system", "silo", "silos", "student information system", "administrative system", "higher ed it", "data integration"),
        "title": "Higher-Ed Workflow Integration Desk",
        "problem": "Higher-education teams work across fragmented systems, making reporting, approvals, and student support slower than they should be.",
        "wedge": "Connect SIS, finance, forms, email, and spreadsheets into one operations layer with searchable records and tracked handoffs.",
    },
    "higher_ed_reporting": {
        "keywords": ("reporting", "manual reporting", "data collection", "analysis software", "power bi", "banner", "metrics", "student populations"),
        "title": "University Reporting Automation Desk",
        "problem": "University staff spend too much time collecting, cleaning, and reporting operational data from disconnected student, finance, and academic systems.",
        "wedge": "Automated dashboards, recurring report generation, anomaly flags, and plain-English summaries for administrators.",
    },
    "higher_ed_admin_load": {
        "keywords": ("administrative bloat", "administrative staff", "burnout", "efficiency", "reduce costs", "managed services", "student-centered"),
        "title": "Administrative Load Reducer",
        "problem": "Administrative teams face rising workload, email overload, burnout, and pressure to reduce costs while keeping student services responsive.",
        "wedge": "Queue triage, task routing, approval reminders, workload visibility, and AI-written status updates for admin teams.",
    },
    "customer_support": {
        "keywords": ("support", "customer", "ticket", "reply", "inbox", "faq", "complaint"),
        "title": "Customer Reply Copilot",
        "problem": "Small teams lose time turning repeated customer questions into accurate replies and follow-ups.",
        "wedge": "Shared inbox triage, suggested replies, tone checks, and follow-up reminders.",
    },
    "document_ops": {
        "keywords": ("document", "pdf", "contract", "proposal", "form", "paperwork", "invoice"),
        "title": "Document Ops Assistant",
        "problem": "Operators waste time extracting, checking, and rewriting routine business documents.",
        "wedge": "Upload documents, extract action items, flag missing fields, and draft next-step messages.",
    },
    "scheduling": {
        "keywords": ("schedule", "booking", "calendar", "appointment", "availability", "meeting"),
        "title": "Schedule Follow-up Agent",
        "problem": "Service businesses lose leads and revenue when appointment coordination stays manual.",
        "wedge": "Availability capture, follow-up nudges, reschedule handling, and no-show recovery.",
    },
    "content_repurposing": {
        "keywords": ("content", "post", "social", "newsletter", "video", "marketing", "caption"),
        "title": "Content Repurposing Desk",
        "problem": "Founders and small teams struggle to turn one idea into consistent channel-ready content.",
        "wedge": "Turn notes, calls, or links into posts, emails, captions, and launch snippets.",
    },
    "finance_admin": {
        "keywords": ("invoice", "receipt", "payment", "expense", "cash flow", "bookkeeping", "quote"),
        "title": "Invoice and Cashflow Watcher",
        "problem": "Small businesses lose time tracking unpaid invoices, expenses, and payment follow-ups.",
        "wedge": "Invoice tracking, reminder drafts, receipt summaries, and weekly cashflow briefing.",
    },
    "client_onboarding": {
        "keywords": ("onboarding", "client", "handoff", "intake", "checklist", "requirements"),
        "title": "Client Onboarding Command Center",
        "problem": "Teams start client work with scattered requirements, files, approvals, and status updates.",
        "wedge": "Intake forms, requirement summaries, missing-info detection, and client-ready status reports.",
    },
    "knowledge_search": {
        "keywords": ("knowledge", "notes", "search", "wiki", "sop", "documentation", "policy"),
        "title": "Team Knowledge Finder",
        "problem": "Small teams repeat answers because policies, SOPs, and decisions are hard to find.",
        "wedge": "Private searchable knowledge base with cited answers and stale-document warnings.",
    },
    "lead_followup": {
        "keywords": ("lead", "sales", "crm", "follow up", "prospect", "pipeline", "outreach"),
        "title": "Lead Follow-up Assistant",
        "problem": "Founders miss revenue because leads are not researched, prioritized, and followed up consistently.",
        "wedge": "Lead research, follow-up drafts, next-best action, and pipeline hygiene reminders.",
    },
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
            CREATE TABLE IF NOT EXISTS project_idea_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                context TEXT NOT NULL,
                audience TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                research_sufficient INTEGER NOT NULL,
                sources_json TEXT NOT NULL,
                signals_json TEXT NOT NULL,
                ideas_json TEXT NOT NULL,
                artifacts_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )


def research_project_ideas(
    context: str = "",
    *,
    audience: str = "individuals, small teams, and SMBs",
    root: str | Path = "",
    limit: int = 5,
    max_sources: int = 8,
    create_files: bool = True,
) -> dict[str, Any]:
    init_db()
    cleaned = _clean(context) or "AI-assisted everyday tools for small businesses"
    audience_text = _clean(audience) or "individuals, small teams, and SMBs"
    sources = _collect_sources(cleaned, audience_text, max_sources=max_sources)
    signals = _extract_signals(sources)
    research_sufficient = _research_sufficient(sources, signals)
    ideas = _ideas_from_signals(signals, sources, audience_text, limit=limit) if research_sufficient else []
    status = "researched" if research_sufficient else "research_incomplete"
    summary = _summary(research_sufficient, ideas, sources, signals)
    artifacts: list[str] = []
    run_id = _insert_run(
        cleaned,
        audience_text,
        status=status,
        summary=summary,
        research_sufficient=research_sufficient,
        sources=sources,
        signals=signals,
        ideas=ideas,
        artifacts=[],
        metadata={"queries": _queries(cleaned, audience_text), "source_count": len(sources)},
    )
    if create_files:
        artifacts = _write_artifacts(
            resolve_coding_root(root),
            run_id=run_id,
            context=cleaned,
            audience=audience_text,
            research_sufficient=research_sufficient,
            sources=sources,
            signals=signals,
            ideas=ideas,
            summary=summary,
        )
        _update_artifacts(run_id, artifacts)
    friday_memory.remember(
        "project_ideation",
        f"Project idea research #{run_id}",
        summary,
        root=resolve_coding_root(root),
        tags=["research", "project_ideas"],
        confidence=0.82 if research_sufficient else 0.45,
        metadata={"run_id": run_id, "research_sufficient": research_sufficient, "idea_count": len(ideas)},
    )
    return get_run(run_id) or {}


def get_run(run_id: int) -> dict[str, Any] | None:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM project_idea_runs WHERE id=?", (int(run_id),)).fetchone()
    return _row(row) if row else None


def recent(limit: int = 10) -> list[dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM project_idea_runs ORDER BY id DESC LIMIT ?", (max(1, min(100, int(limit or 10))),)).fetchall()
    return [_row(row) for row in rows]


def status(limit: int = 6) -> dict[str, Any]:
    runs = recent(limit=limit)
    latest = runs[0] if runs else None
    return {
        "latest": latest,
        "recent": runs,
        "research_policy": {
            "no_guessing": "Friday must not recommend project ideas unless source-backed demand signals are present.",
            "minimum_evidence": "At least three demand-bearing sources and two detected signal categories.",
            "outputs": ["research-brief.md", "source-register.json", "demand-signals.json", "idea-shortlist.md", "recommendation.md"],
        },
        "summary": latest.get("summary") if latest else "No project-idea research runs yet.",
    }


def wipe_all() -> None:
    init_db()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("DELETE FROM project_idea_runs")


def _collect_sources(context: str, audience: str, *, max_sources: int) -> list[dict[str, Any]]:
    per_query = max(2, min(5, int(max_sources or 8)))
    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query in _queries(context, audience):
        for item in research.search_web(query, limit=per_query):
            url = _clean(item.get("url") or "")
            key = url or _clean(item.get("title") or "").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            snippet = _clean(item.get("snippet") or "")
            source = {
                "id": f"s{len(collected) + 1}",
                "query": query,
                "title": _clean(item.get("title") or "Untitled"),
                "url": url,
                "snippet": snippet,
                "provider": _clean(item.get("provider") or ""),
                "published_at": _clean(item.get("published_at") or ""),
                "demand_terms": [term for term in DEMAND_TERMS if term in f"{item.get('title', '')} {snippet}".lower()],
            }
            collected.append(source)
            if len(collected) >= max(3, int(max_sources or 8)):
                return collected
    return collected


def _queries(context: str, audience: str) -> list[str]:
    base = f"{context} {audience}"
    return [
        f"{base} pain points recurring problems software",
        f"{base} manual workflow spreadsheet problem",
        f"{base} small business forum need automation",
        f"site:reddit.com small business {context} pain point automation",
        f"site:indiehackers.com {context} problem founders need tool",
    ]


def _extract_signals(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for signal_id, definition in SIGNALS.items():
        matched_sources = []
        matched_terms = []
        for source in sources:
            text = f"{source.get('title', '')} {source.get('snippet', '')}".lower()
            terms = [term for term in definition["keywords"] if term in text]
            if terms:
                matched_sources.append(source["id"])
                matched_terms.extend(terms)
        if matched_sources:
            signals.append(
                {
                    "id": signal_id,
                    "label": definition["title"],
                    "evidence_count": len(matched_sources),
                    "source_ids": matched_sources,
                    "matched_terms": sorted(set(matched_terms)),
                    "problem": definition["problem"],
                    "wedge": definition["wedge"],
                }
            )
    return sorted(signals, key=lambda item: (int(item["evidence_count"]), len(item["matched_terms"])), reverse=True)


def _research_sufficient(sources: list[dict[str, Any]], signals: list[dict[str, Any]]) -> bool:
    demand_sources = [source for source in sources if source.get("demand_terms") or _has_need_language(source)]
    return len(demand_sources) >= 3 and len(signals) >= 2


def _ideas_from_signals(signals: list[dict[str, Any]], sources: list[dict[str, Any]], audience: str, *, limit: int) -> list[dict[str, Any]]:
    by_id = {source["id"]: source for source in sources}
    ideas: list[dict[str, Any]] = []
    for signal in signals[: max(1, min(8, int(limit or 5)))]:
        evidence = [by_id[source_id] for source_id in signal.get("source_ids", []) if source_id in by_id][:5]
        ideas.append(
            {
                "id": signal["id"],
                "title": signal["label"],
                "target_audience": audience,
                "problem": signal["problem"],
                "product_wedge": signal["wedge"],
                "why_people_would_use_it": _why_use(signal),
                "business_model": "Start with a free trial, then charge a small monthly team plan once saved time or recovered revenue is visible.",
                "first_users": "Recruit from the source communities and adjacent small-business/operator groups represented in the evidence.",
                "evidence_count": signal["evidence_count"],
                "evidence_sources": evidence,
                "confidence": _confidence(signal, evidence),
                "must_validate": [
                    "Interview at least five users from the source communities.",
                    "Confirm willingness to pay before building complex automation.",
                    "Run a landing-page or concierge test before production build.",
                ],
            }
        )
    return ideas


def _write_artifacts(
    root: Path,
    *,
    run_id: int,
    context: str,
    audience: str,
    research_sufficient: bool,
    sources: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    ideas: list[dict[str, Any]],
    summary: str,
) -> list[str]:
    artifact_root = root / IDEA_DIR / f"run-{run_id}"
    artifact_root.mkdir(parents=True, exist_ok=True)
    files = {
        "research-brief.md": _research_brief_md(context, audience, research_sufficient, summary, sources),
        "source-register.json": _json_dumps(sources),
        "demand-signals.json": _json_dumps(signals),
        "idea-shortlist.md": _idea_shortlist_md(ideas, research_sufficient),
        "recommendation.md": _recommendation_md(ideas, research_sufficient, summary),
        "manifest.json": _json_dumps(
            {
                "run_id": run_id,
                "created_at": _now(),
                "context": context,
                "audience": audience,
                "research_sufficient": research_sufficient,
                "files": ["research-brief.md", "source-register.json", "demand-signals.json", "idea-shortlist.md", "recommendation.md"],
            }
        ),
    }
    written: list[str] = []
    for name, content in files.items():
        path = artifact_root / name
        path.write_text(content, encoding="utf-8")
        written.append(str(path))
    return written


def _research_brief_md(context: str, audience: str, research_sufficient: bool, summary: str, sources: list[dict[str, Any]]) -> str:
    lines = [
        "# Project Idea Research Brief",
        "",
        f"Context: {context}",
        f"Audience: {audience}",
        f"Research sufficient: {research_sufficient}",
        "",
        f"Summary: {summary}",
        "",
        "## Sources",
    ]
    if not sources:
        lines.append("- No sources found. Friday must not recommend an idea from this run.")
    for source in sources:
        terms = ", ".join(source.get("demand_terms") or []) or "general relevance"
        lines.append(f"- [{source['id']}] {source['title']} - {terms} - {source.get('url') or 'no url'}")
    return "\n".join(lines) + "\n"


def _idea_shortlist_md(ideas: list[dict[str, Any]], research_sufficient: bool) -> str:
    if not research_sufficient:
        return "# Idea Shortlist\n\nNo ideas recommended because research evidence was insufficient.\n"
    lines = ["# Idea Shortlist", ""]
    for idea in ideas:
        lines.extend(
            [
                f"## {idea['title']}",
                "",
                f"Problem: {idea['problem']}",
                f"Product wedge: {idea['product_wedge']}",
                f"Evidence count: {idea['evidence_count']}",
                f"Confidence: {idea['confidence']}",
                "",
            ]
        )
    return "\n".join(lines)


def _recommendation_md(ideas: list[dict[str, Any]], research_sufficient: bool, summary: str) -> str:
    if not research_sufficient or not ideas:
        return f"# Recommendation\n\nDo not pick a project from this run yet.\n\nReason: {summary}\n"
    top = ideas[0]
    return (
        "# Recommendation\n\n"
        f"Recommended next build: {top['title']}\n\n"
        f"Why: {top['why_people_would_use_it']}\n\n"
        f"First validation step: {top['must_validate'][0]}\n\n"
        "This is a research-backed recommendation, not a market-ready certification.\n"
    )


def _insert_run(
    context: str,
    audience: str,
    *,
    status: str,
    summary: str,
    research_sufficient: bool,
    sources: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    ideas: list[dict[str, Any]],
    artifacts: list[str],
    metadata: dict[str, Any],
) -> int:
    now = _now()
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.execute(
            """
            INSERT INTO project_idea_runs(created_at, context, audience, status, summary, research_sufficient, sources_json, signals_json, ideas_json, artifacts_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (now, context, audience, status, summary, 1 if research_sufficient else 0, _json_dumps(sources), _json_dumps(signals), _json_dumps(ideas), _json_dumps(artifacts), _json_dumps(metadata)),
        )
        return int(cursor.lastrowid)


def _update_artifacts(run_id: int, artifacts: list[str]) -> None:
    with _LOCK, sqlite3.connect(DB_PATH, timeout=10) as conn:
        conn.execute("UPDATE project_idea_runs SET artifacts_json=? WHERE id=?", (_json_dumps(artifacts), int(run_id)))


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": str(row["created_at"]),
        "context": str(row["context"]),
        "audience": str(row["audience"]),
        "status": str(row["status"]),
        "summary": str(row["summary"]),
        "research_sufficient": bool(row["research_sufficient"]),
        "sources": _json_loads(row["sources_json"], []),
        "signals": _json_loads(row["signals_json"], []),
        "ideas": _json_loads(row["ideas_json"], []),
        "artifacts": _json_loads(row["artifacts_json"], []),
        "metadata": _json_loads(row["metadata_json"], {}),
    }


def _summary(research_sufficient: bool, ideas: list[dict[str, Any]], sources: list[dict[str, Any]], signals: list[dict[str, Any]]) -> str:
    if not sources:
        return "No sources were found, so Friday cannot recommend a project idea."
    if not research_sufficient:
        return f"Research found {len(sources)} source(s), but not enough demand signals to recommend a project."
    top = ideas[0]["title"] if ideas else "No top idea"
    return f"Research found {len(sources)} source(s) and {len(signals)} demand signal(s). Top idea: {top}."


def _why_use(signal: dict[str, Any]) -> str:
    terms = ", ".join(signal.get("matched_terms") or []) or "recurring workflow terms"
    return f"The evidence cluster repeatedly mentions {terms}, suggesting a recurring workflow where automation can save time."


def _confidence(signal: dict[str, Any], evidence: list[dict[str, Any]]) -> float:
    score = 0.45 + min(0.35, 0.08 * int(signal.get("evidence_count") or 0)) + min(0.15, 0.03 * len(evidence))
    return round(min(0.9, score), 2)


def _has_need_language(source: dict[str, Any]) -> bool:
    text = f"{source.get('title', '')} {source.get('snippet', '')}".lower()
    return any(term in text for term in DEMAND_TERMS)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n"


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", " ")).strip()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

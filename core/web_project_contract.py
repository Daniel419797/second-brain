"""Request-derived web project contracts for Friday builds.

The point of this module is to stop Friday from treating "web-app" as a
generic landing/workspace scaffold. A web request may name concrete pages,
routes, and dashboard previews; those become a contract that scaffolding,
quality review, browser smoke, and product gates can all share.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PAGE_KEYWORDS = {
    "home": ("home", "landing"),
    "product": ("product", "platform", "features"),
    "features": ("features",),
    "pricing": ("pricing", "plans"),
    "contact": ("contact", "demo", "inquiry", "inquire", "book"),
    "about": ("about", "company", "story"),
    "services": ("services", "service"),
    "dashboard-preview": ("dashboard preview", "dashboard", "operations dashboard", "preview route"),
    "docs": ("docs", "documentation"),
    "marketplace": ("marketplace",),
}

PUBLIC_ROUTE_ORDER = ("home", "product", "features", "pricing", "about", "services", "docs", "marketplace", "contact")

STOP_WORDS = {
    "about",
    "also",
    "and",
    "app",
    "b2b",
    "build",
    "called",
    "company",
    "create",
    "dashboard",
    "design",
    "for",
    "from",
    "goal",
    "home",
    "help",
    "helps",
    "implementation",
    "market",
    "marketing",
    "next",
    "nextjs",
    "page",
    "pages",
    "preview",
    "pricing",
    "product",
    "production",
    "project",
    "quality",
    "ready",
    "real",
    "requirements",
    "route",
    "routes",
    "screen",
    "screens",
    "studio",
    "that",
    "the",
    "this",
    "typescript",
    "use",
    "web",
    "webapp",
    "website",
    "with",
}


def build_contract(request: str, product_name: str = "", *, stack: dict[str, Any] | None = None) -> dict[str, Any]:
    text = _clean(request)
    routes = expected_routes(text, stack=stack)
    domain_terms = domain_terms_from_request(text)
    name = _clean(product_name) or _name_from_request(text) or "Friday Web Product"
    pages = [_page_spec(route, name, text, domain_terms) for route in routes if route["id"] != "dashboard-preview"]
    dashboard = _dashboard_spec(name, text, domain_terms) if any(route["id"] == "dashboard-preview" for route in routes) else {}
    archetype = design_archetype(text)
    return {
        "version": "friday_web_contract_v1",
        "product_name": name,
        "request_summary": _request_summary(text),
        "archetype": archetype,
        "tone": _tone_for_archetype(archetype),
        "domain_terms": domain_terms,
        "routes": routes,
        "nav": [route for route in routes if route["id"] != "dashboard-preview"],
        "pages": pages,
        "dashboard_preview": dashboard,
        "acceptance": [
            "Every requested page/route has a real Next.js App Router file.",
            "Route files stay thin and compose feature/page components.",
            "Visible copy uses product-domain terms, not scaffold filler.",
            "Primary links route to existing pages or change visible state.",
            "Browser smoke checks all contract routes.",
        ],
    }


def expected_routes(request: str, *, stack: dict[str, Any] | None = None) -> list[dict[str, str]]:
    raw_text = str(request or "").replace("\r", "\n")
    text = _clean(raw_text)
    stack_id = str((stack or {}).get("stack") or "").lower()
    if stack_id and stack_id != "nextjs":
        return []
    if _single_page_landing(text):
        return [{"id": "home", "label": "Home", "route": "/", "kind": "public"}]

    route_ids: list[str] = []
    explicit_labels = _explicit_page_labels(text)
    explicit_route_ids: list[str] = []
    for label in explicit_labels:
        route_id = _route_id(label, explicit=True)
        _add(route_ids, route_id)
        _add(explicit_route_ids, route_id)

    lower = text.lower()
    in_required_block = "required screens/routes" in lower or "required routes" in lower or "required screens" in lower
    if not explicit_route_ids:
        for route_id, keywords in PAGE_KEYWORDS.items():
            if _route_keyword_negated(lower, route_id):
                continue
            if any(_contains_keyword(lower, keyword) for keyword in keywords):
                if route_id == "dashboard-preview" and not any(term in lower for term in ("dashboard preview", "dashboard preview route", "operations dashboard", "lightweight operations dashboard")):
                    continue
                if route_id == "product" and "product page" not in lower and "platform page" not in lower:
                    continue
                _add(route_ids, route_id)

    if any(term in lower for term in ("four-page", "four page", "4-page", "4 page", "multi-page", "multipage")) and len(route_ids) <= 1:
        for route_id in ("home", "about", "services", "contact"):
            _add(route_ids, route_id)

    if in_required_block:
        for item in _required_route_items(raw_text):
            line_route = _route_from_line(item)
            if line_route:
                _add(route_ids, line_route)

    if not route_ids:
        return []
    _add(route_ids, "home")
    if explicit_route_ids:
        ordered = route_ids
    else:
        ordered = [route_id for route_id in [*PUBLIC_ROUTE_ORDER, "dashboard-preview"] if route_id in route_ids]
        ordered.extend(route_id for route_id in route_ids if route_id not in ordered)
    return [_route_spec(route_id) for route_id in ordered]


def expected_route_paths(project_root: str | Path, request: str, *, stack: dict[str, Any] | None = None) -> dict[str, Path]:
    root = Path(project_root)
    paths: dict[str, Path] = {}
    for route in expected_routes(request, stack=stack):
        route_id = route["id"]
        route_path = route["route"]
        if route_path == "/":
            paths[route_id] = root / "src" / "app" / "page.tsx"
        else:
            paths[route_id] = root / "src" / "app" / route_path.strip("/") / "page.tsx"
    return paths


def has_route_contract(request: str, *, stack: dict[str, Any] | None = None) -> bool:
    return len(expected_routes(request, stack=stack)) > 1


def contract_ts(contract: dict[str, Any]) -> str:
    return "export const webProject = " + json.dumps(contract, ensure_ascii=True, indent=2, sort_keys=True) + " as const;\n\nexport type WebProject = typeof webProject;\n"


def route_component_name(route_id: str) -> str:
    return "".join(part.capitalize() for part in str(route_id or "page").split("-")) + "Page"


def design_archetype(request: str) -> str:
    text = str(request or "").lower()
    intent_text = _strip_negative_constraints(text)
    if any(term in text for term in ("government", "civic", "city", "permit", "public sector", "municipal")):
        return "civic_operations"
    if _energy_climate_request(text):
        return "energy_climate"
    if _contains_any(intent_text, ("developer", "api", "sdk", "cli", "web3", "backend", "open-source", "opensource")):
        return "developer_tool"
    if any(term in text for term in ("luxury", "fashion", "jewelry", "watch", "atelier")):
        return "luxury_editorial"
    if any(term in text for term in ("construction", "builder", "jobsite", "real estate", "architecture")):
        return "built_environment"
    if any(term in text for term in ("healthcare", "clinic", "patient", "medical", "hospital")):
        return "clinical_operations"
    if any(term in text for term in ("game", "gaming", "esports")):
        return "game_like"
    if any(term in text for term in ("education", "school", "university", "student", "course")):
        return "education_operations"
    if any(term in text for term in ("marketplace", "commerce", "shop", "store")):
        return "marketplace"
    return "product_studio"


def _page_spec(route: dict[str, str], name: str, request: str, terms: list[str]) -> dict[str, Any]:
    route_id = route["id"]
    label = route["label"]
    term_line = _term_line(terms)
    custom_focus = _route_focus_terms(route_id, label, terms)
    custom_focus_line = _term_line(custom_focus)
    if _energy_climate_request(request):
        return _energy_page_spec(route, name, request, terms)
    title_map = {
        "home": f"{name} turns {term_line} into accountable work.",
        "product": f"How {name} manages {term_line}.",
        "features": f"Features built around {term_line}.",
        "pricing": "Pricing that fits teams before it fits procurement.",
        "about": f"Why {name} exists.",
        "services": f"Services and workflows {name} supports.",
        "docs": f"{name} documentation and implementation path.",
        "marketplace": f"{name} marketplace and integration surface.",
        "contact": "Book a focused product walkthrough.",
    }
    summary_map = {
        "home": _request_summary(request),
        "product": f"Connect intake, queue ownership, scheduling, updates, and proof so every stakeholder can see what moved and what is blocked.",
        "features": f"Core workflows stay specific to {term_line}: triage, assignment, status updates, audit trails, and exception handling.",
        "pricing": "Start with a pilot, then scale by workspace, data volume, and support needs without hiding approval-sensitive costs.",
        "about": f"{name} is designed for teams that need operational clarity, public trust, and evidence before claims.",
        "services": f"Use {name} to structure daily operations, reporting, customer updates, and review workflows.",
        "docs": "Implementation notes, data model guidance, security expectations, and rollout sequencing stay visible.",
        "marketplace": "Connect calendars, messaging, records, analytics, and approval systems without burying integration risk.",
        "contact": "Capture the team, workflow pressure, timeline, and data constraints needed for a real pilot conversation.",
    }
    custom_actions = {
        "intake": ("Triage intake", "View fee holds"),
        "reviews": ("Assign reviewer", "Open SLA risk"),
        "inspections": ("Schedule inspection", "View capacity"),
        "applicants": ("Draft applicant update", "View message log"),
        "settings": ("Review controls", "Open audit trail"),
    }
    primary, secondary = custom_actions.get(route_id, ("Book walkthrough", "View audit trail"))
    return {
        "id": route_id,
        "label": label,
        "route": route["route"],
        "title": title_map.get(route_id, f"{label} command view for {custom_focus_line}."),
        "summary": summary_map.get(route_id, f"Track {custom_focus_line}, owners, blockers, handoffs, aging, public updates, and audit proof for {name}."),
        "primary_action": "Open dashboard preview" if route_id == "home" else primary,
        "secondary_action": "See pricing" if route_id == "pricing" else secondary,
        "sections": _sections_for(route_id, terms, label=label),
    }


def _energy_page_spec(route: dict[str, str], name: str, request: str, terms: list[str]) -> dict[str, Any]:
    route_id = route["id"]
    label = route["label"]
    term_line = _term_line(terms or ["microgrid telemetry", "solar production", "battery state", "demand spikes", "outage risk"])
    title_map = {
        "home": f"{name} makes building energy risk visible before outages.",
        "platform": f"{name} platform monitors microgrids, solar, batteries, and demand.",
        "case-studies": "Commercial building resilience, proven in operating data.",
        "contact": "Request an energy review for your building portfolio.",
    }
    summary_map = {
        "home": _request_summary(request),
        "platform": "Monitor microgrid telemetry, solar production, battery state, demand spikes, building load, outage risk, and facility next actions in one operating view.",
        "case-studies": "Review portfolio outcomes across peak-demand reduction, outage resilience, solar utilization, battery dispatch, and clean-energy reliability.",
        "contact": "Capture building count, energy assets, resilience goals, telemetry sources, and timeline for a practical energy-risk review.",
    }
    primary_map = {
        "home": "View platform",
        "platform": "Model outage risk",
        "case-studies": "Explore case studies",
        "contact": "Request energy review",
    }
    secondary_map = {
        "home": "Explore case studies",
        "platform": "See case studies",
        "case-studies": "Request energy review",
        "contact": "View platform",
    }
    return {
        "id": route_id,
        "label": label,
        "route": route["route"],
        "title": title_map.get(route_id, f"{label} view for {term_line}."),
        "summary": summary_map.get(route_id, f"Show {term_line}, facility owners, energy risk, and resilience proof for {name}."),
        "primary_action": primary_map.get(route_id, "Request energy review"),
        "secondary_action": secondary_map.get(route_id, "View platform"),
        "sections": _sections_for(route_id, terms, label=label),
    }


def _dashboard_spec(name: str, request: str, terms: list[str]) -> dict[str, Any]:
    terms = terms or ["intake", "review", "schedule", "updates"]
    return {
        "id": "dashboard-preview",
        "label": "Dashboard Preview",
        "route": "/dashboard-preview",
        "title": f"{name} operations dashboard",
        "summary": f"A working preview for {', '.join(terms[:4])}, owner workload, urgent blockers, and proof history.",
        "metrics": [
            {"label": f"{terms[0]} open", "value": "42", "tone": "urgent"},
            {"label": f"{terms[1] if len(terms) > 1 else 'review'} due today", "value": "17", "tone": "warning"},
            {"label": f"{terms[2] if len(terms) > 2 else 'schedule'} capacity", "value": "86%", "tone": "good"},
            {"label": "public updates ready", "value": "23", "tone": "info"},
        ],
        "queue": [
            {"title": f"{term.title()} review", "owner": owner, "status": status}
            for term, owner, status in zip(terms[:4], ["Intake desk", "Reviewer", "Scheduler", "Public counter"], ["urgent", "active", "ready", "blocked"])
        ],
    }


def _sections_for(route_id: str, terms: list[str], *, label: str = "") -> list[dict[str, str]]:
    terms = terms or ["intake", "review", "schedule"]
    if _energy_terms_present(terms):
        if route_id == "contact":
            return [
                {"title": "Portfolio context", "body": "Share building count, operating regions, peak demand windows, and resilience goals."},
                {"title": "Energy assets", "body": "Map solar production, battery capacity, microgrid controls, utility feeds, and telemetry sources."},
                {"title": "Pilot proof", "body": "Leave with a specific pilot plan, outage-risk model, security notes, and acceptance criteria."},
            ]
        if route_id == "platform":
            return [
                {"title": "Microgrid telemetry", "body": "Show live grid state, building load, battery charge, solar production, and control readiness."},
                {"title": "Demand-risk forecast", "body": "Forecast demand spikes, peak-cost exposure, and resilience windows before they become urgent."},
                {"title": "Operator alerts", "body": "Route outage-risk alerts, asset anomalies, and next actions to facility and sustainability teams."},
            ]
        if route_id == "case-studies":
            return [
                {"title": "Peak-demand reduction", "body": "Compare before/after load curves, battery dispatch, and facility savings for commercial portfolios."},
                {"title": "Outage resilience", "body": "Show how microgrid readiness, solar state, and battery reserves changed incident response."},
                {"title": "Building portfolio proof", "body": "Group case studies by facility type, energy asset mix, and measurable resilience outcome."},
            ]
        return [
            {"title": "Microgrid visibility", "body": "Commercial buildings see microgrid state, solar production, battery reserves, and grid dependency in one view."},
            {"title": "Demand spike control", "body": "Facility teams model peak load, demand spikes, and outage risk before costs or downtime spread."},
            {"title": "Clean-energy proof", "body": "Case-study metrics connect building load, battery dispatch, solar generation, and resilience outcomes."},
        ]
    if route_id == "pricing":
        return [
            {"title": "Pilot", "body": f"One workspace for validating {terms[0]} and reporting flow."},
            {"title": "Operations", "body": f"Team workflows, dashboard preview, integrations, and support for {', '.join(terms[:3])}."},
            {"title": "Enterprise", "body": "Custom deployment, compliance review, procurement support, and rollout governance."},
        ]
    if route_id == "contact":
        return [
            {"title": "Workflow pressure", "body": f"Tell us where {terms[0]} stalls and who owns the next decision."},
            {"title": "Data sources", "body": "Share the systems, spreadsheets, calendars, or inboxes that need to connect."},
            {"title": "Pilot proof", "body": "Leave with a specific pilot plan, security notes, and acceptance criteria."},
        ]
    if route_id not in {"home", "product", "features", "about", "services", "docs", "marketplace"}:
        focus = _route_focus_terms(route_id, label, terms)
        focus_line = _term_line(focus)
        owner = label or route_id.replace("-", " ").title()
        return [
            {"title": f"{owner} queue pressure", "body": f"Separate new, aging, blocked, and ownerless {focus_line} work before it drifts into another inbox."},
            {"title": "Owner and handoff clarity", "body": f"Show the reviewer, counter staff, inspector, or approver responsible for the next {focus[0] if focus else 'workflow'} decision."},
            {"title": "Risk and SLA controls", "body": f"Surface due dates, fee holds, missing documents, capacity conflicts, and public-update risk for {focus_line}."},
            {"title": "Audit proof", "body": f"Attach notes, status changes, applicant messages, and decision history so {focus_line} claims can be verified."},
        ]
    return [
        {"title": f"{term.title()} without spreadsheet drift", "body": f"{term.title()} gets an owner, status, blocker, public/customer impact, and proof trail."}
        for term in terms[:4]
    ]


def _route_focus_terms(route_id: str, label: str, terms: list[str]) -> list[str]:
    route_words = set(re.split(r"[^a-z0-9]+", f"{route_id} {label}".lower()))
    hint_words = {
        "intake": {"intake", "submission", "application", "fee", "document"},
        "reviews": {"review", "reviewer", "plan", "sla", "queue"},
        "inspections": {"inspection", "inspector", "calendar", "schedule", "capacity"},
        "applicants": {"applicant", "message", "public", "update", "citizen"},
        "settings": {"setting", "control", "audit", "security", "approval", "transparency"},
    }.get(route_id, set())
    words = {word for word in [*route_words, *hint_words] if word}
    matches = [
        term
        for term in terms
        if any(word in term.lower() or term.lower() in word for word in words)
    ]
    if matches:
        return _dedupe(matches)[:4]
    fallback = [label.lower().strip() or route_id.replace("-", " ")]
    fallback.extend(terms[:3])
    return _dedupe(fallback)[:4]


def _energy_terms_present(terms: list[str]) -> bool:
    joined = " ".join(str(term or "").lower() for term in terms)
    return any(term in joined for term in ("microgrid", "solar", "battery", "demand", "outage", "energy", "building load"))


def _explicit_page_labels(request: str) -> list[str]:
    patterns = [
        r"(?:^|[.\n])\s*pages?\s+must\s+be\s+([^.\n]+)",
        r"(?:^|[.\n])\s*pages?\s+should\s+be\s+([^.\n]+)",
        r"(?:^|[.\n])\s*pages?\s+(?:include|including)\s+([^.\n]+)",
        r"\bwith\s+(?:the\s+)?(?:following\s+)?(?:four|4)[-\s ]?pages?\s*:?\s+([^.\n]+)",
        r"\b(?:four|4)[-\s ]?pages?\s*:?\s+([^.\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, request, flags=re.IGNORECASE)
        if not match:
            continue
        labels = _split_labels(match.group(1))
        if len(labels) >= 2:
            return labels[:8]
    return []


def _split_labels(raw: str) -> list[str]:
    text = re.sub(r"\([^)]*\)", " ", str(raw or ""))
    parts = re.split(r",|/|\s+\band\b\s+", text)
    labels: list[str] = []
    for part in parts:
        label = _clean(part).strip(" .:;-\"'")
        label = re.sub(r"^(?:and|plus|including)\s+", "", label, flags=re.IGNORECASE).strip()
        if label and len(label) <= 48:
            labels.append(label.title() if label.islower() else label)
    return _dedupe(labels)


def _route_from_line(line: str) -> str:
    lower = line.lower()
    for route_id, keywords in PAGE_KEYWORDS.items():
        if any(_contains_keyword(lower, keyword) for keyword in keywords):
            return route_id
    before = re.split(r"\b(?:page|route|screen)\b", _clean(line).lstrip("-* "), maxsplit=1, flags=re.IGNORECASE)[0]
    return _route_id(before) if before else ""


def _required_route_items(raw_text: str) -> list[str]:
    lines = [line.strip() for line in str(raw_text or "").splitlines() if line.strip().startswith(("-", "*"))]
    if lines:
        return _dedupe(lines)

    text = _clean(raw_text)
    match = re.search(
        r"\brequired\s+(?:screens/routes|screens|routes)\s*:\s*(.+?)(?=\b(?:dashboard|website|page|design|implementation|acceptance|quality|navigation|browser|run)\s+requirements?\s*:|$)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return []

    body = match.group(1).strip()
    bullet_items = [
        re.sub(r"^[\-*]\s*", "", part).strip(" .;:")
        for part in re.split(r"\s+(?=[-*]\s+)", body)
        if part.strip(" .;:")
    ]
    if len(bullet_items) > 1:
        return _dedupe([item for item in bullet_items if item])

    labels = _split_page_labels(body)
    return _dedupe(labels)


def _route_keyword_negated(text: str, route_id: str) -> bool:
    terms = {
        "services": r"services?|service studio",
        "contact": r"contact|demo|inquiry|inquire",
        "pricing": r"pricing|plans?",
        "product": r"product page|platform page",
        "about": r"about page|company page|story page",
    }.get(route_id)
    if not terms:
        return False
    return bool(re.search(rf"\b(?:not|no|never|avoid|do not|don't|is not|isn't)\b[^.\n]*\b(?:{terms})\b", text))


def _energy_climate_request(text: str) -> bool:
    lower = str(text or "").lower()
    return any(
        term in lower
        for term in (
            "climate-tech",
            "climatetech",
            "clean energy",
            "energy management",
            "microgrid",
            "microgrids",
            "solar",
            "battery",
            "batteries",
            "demand spike",
            "demand spikes",
            "outage risk",
            "building load",
            "building energy",
            "commercial building",
            "commercial buildings",
            "grid monitoring",
            "renewable",
            "decarbonization",
        )
    )


def _strip_negative_constraints(text: str) -> str:
    cleaned = f" {str(text or '').lower()} "
    for pattern in (
        r"\b(?:no|not|never)\s+[^.;,\n]{0,120}",
        r"\b(?:do\s+not|don't|dont)\s+[^.;,\n]{0,120}",
    ):
        cleaned = re.sub(pattern, " ", cleaned)
    return cleaned


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        if " " in term or "-" in term:
            if term in text:
                return True
            continue
        if re.search(rf"\b{re.escape(term)}\b", text):
            return True
    return False


def _contains_keyword(text: str, keyword: str) -> bool:
    key = str(keyword or "").strip().lower()
    if not key:
        return False
    if " " in key:
        return key in text
    return bool(re.search(rf"\b{re.escape(key)}\b", text))


def _route_id(label: str, *, explicit: bool = False) -> str:
    lower = _clean(label).lower()
    if not lower:
        return ""
    if "home" in lower or "landing" in lower:
        return "home"
    if "dashboard" in lower and "preview" in lower:
        return "dashboard-preview"
    if "contact" in lower or "demo" in lower or "inquiry" in lower:
        return "contact"
    if "price" in lower or "plan" in lower:
        return "pricing"
    if "product" in lower:
        return "product"
    if "platform" in lower:
        return "platform" if explicit else "product"
    if "feature" in lower:
        return "features"
    if "service" in lower:
        return "services"
    if "about" in lower or "story" in lower:
        return "about"
    return re.sub(r"[^a-z0-9]+", "-", lower).strip("-")[:48]


def _route_spec(route_id: str) -> dict[str, str]:
    label = {
        "home": "Home",
        "product": "Product",
        "features": "Features",
        "pricing": "Pricing",
        "about": "About",
        "services": "Services",
        "contact": "Contact",
        "dashboard-preview": "Dashboard Preview",
        "docs": "Docs",
        "marketplace": "Marketplace",
    }.get(route_id, route_id.replace("-", " ").title())
    return {"id": route_id, "label": label, "route": "/" if route_id == "home" else f"/{route_id}", "kind": "dashboard" if route_id == "dashboard-preview" else "public"}


def domain_terms_from_request(request: str, *, limit: int = 10) -> list[str]:
    phrases: list[str] = []
    for pattern in (
        r"\bmonitor\s+([^.\n]+)",
        r"\bhelps\s+[^.\n]+?\s+monitor\s+([^.\n]+)",
        r"\bmanage\s+([^.\n]+)",
        r"\bhelps\s+[^.\n]+?\s+manage\s+([^.\n]+)",
        r"\bfor\s+([^.\n]+?)\s+without\s+",
        r"\bexplaining\s+([^.\n]+)",
    ):
        for match in re.finditer(pattern, request, flags=re.IGNORECASE):
            phrases.extend(_split_workflows(match.group(1)))
    words = [word for word in re.split(r"[^a-z0-9]+", request.lower()) if len(word) > 3 and word not in STOP_WORDS]
    for word in words:
        if len(phrases) >= limit:
            break
        if word not in phrases:
            phrases.append(word)
    return _dedupe([_clean(term).lower() for term in phrases if _clean(term)])[:limit]


def _split_workflows(raw: str) -> list[str]:
    text = re.sub(r"\b(?:and|or)\b", ",", str(raw or ""), flags=re.IGNORECASE)
    parts = [part.strip(" .:;-\"'") for part in text.split(",")]
    return [part.lower() for part in parts if 3 <= len(part) <= 54]


def _request_summary(request: str) -> str:
    terms = domain_terms_from_request(request, limit=5)
    if _energy_climate_request(request):
        return f"Designed around {', '.join(terms[:5] or ['microgrid telemetry', 'solar production', 'battery state', 'demand spikes', 'outage risk'])} with visible energy telemetry, risk signals, facility owners, and resilience proof."
    if terms:
        return f"Designed around {', '.join(terms)} with visible owners, status, blockers, updates, and proof."
    text = _clean(request)
    return text[:220] + ("..." if len(text) > 220 else "")


def _term_line(terms: list[str]) -> str:
    if not terms:
        return "daily operations"
    if len(terms) == 1:
        return terms[0]
    return ", ".join(terms[:3])


def _tone_for_archetype(archetype: str) -> str:
    return {
        "civic_operations": "trustworthy, accessible, calm, public-service operational",
        "developer_tool": "technical, precise, fast, command-line credible",
        "luxury_editorial": "quiet, premium, tactile, spacious",
        "built_environment": "grounded, structural, project-led, confident",
        "clinical_operations": "clear, safe, high-trust, operational",
        "game_like": "kinetic, playful, immersive, bold",
        "education_operations": "organized, supportive, institutional, clear",
        "marketplace": "search-first, comparative, commercial, trustworthy",
        "energy_climate": "technical, resilient, climate-aware, telemetry-led",
    }.get(archetype, "specific, polished, useful, evidence-led")


def _single_page_landing(request: str) -> bool:
    text = request.lower()
    single = any(term in text for term in ("single-page", "single page", "one-page", "one page"))
    multi = any(term in text for term in ("four-page", "four page", "4-page", "4 page", "multi-page", "multipage", "required screens/routes"))
    negated_multi = bool(re.search(r"\b(?:not|no|never|do not|don't|is not|isn't)\s+(?:a\s+)?(?:four|4|multi)[-\s]?pages?\b", text))
    if single and negated_multi:
        return True
    explicit_page_labels = bool(_explicit_page_labels(request))
    explicit_extra_page = bool(
        re.search(
            r"\b(?:pricing|about|services?|contact|docs|documentation|platform|features?|case\s+studies|marketplace)\s+page\b",
            text,
        )
    )
    plain_landing = "landing page" in text or "product landing" in text or "marketing landing" in text
    return (single or plain_landing) and not multi and not explicit_page_labels and not explicit_extra_page


def _name_from_request(request: str) -> str:
    match = re.search(r"\b(?:called|named)\s+([A-Z][A-Za-z0-9&'. -]{2,80}?)(?:[.;,\n]|$)", request)
    return _clean(match.group(1)) if match else ""


def _add(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = str(item).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(str(item).strip())
    return result


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\r", "\n")).strip()

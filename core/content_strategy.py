"""Project-specific content strategy for generated product surfaces."""

from __future__ import annotations

import re
from typing import Any


def website_content(product_name: str, request: str) -> dict[str, Any]:
    """Return domain-aware website copy from the task brief.

    This keeps visible copy out of static scaffold templates. The result is
    deterministic and non-secret, so it is safe to persist in generated apps.
    """

    name = _clean(product_name) or "The Company"
    text = _clean(request)
    lower = text.lower()
    industry = _industry(lower)
    audience = _audience(lower, industry)
    offer = _offer(industry)
    proof = _proof(industry)
    return {
        "brand": name,
        "request": text,
        "nav": [
            {"label": "Home", "href": "/"},
            {"label": "About", "href": "/about"},
            {"label": "Services", "href": "/services"},
            {"label": "Contact", "href": "/contact"},
        ],
        "hero": {
            "eyebrow": offer["eyebrow"],
            "title": offer["title"].format(name=name),
            "summary": offer["summary"].format(name=name, audience=audience),
            "primaryAction": offer["primary_action"],
            "secondaryAction": "View services",
        },
        "proof": proof,
        "about": {
            "title": offer["about_title"].format(name=name),
            "body": offer["about_body"].format(name=name, audience=audience),
            "principles": offer["principles"],
        },
        "services": offer["services"],
        "contact": {
            "title": offer["contact_title"],
            "detail": offer["contact_detail"].format(audience=audience),
            "email": "hello@example.com",
        },
    }


def _industry(text: str) -> str:
    if any(term in text for term in ("construction", "contractor", "builder", "building", "civil")):
        return "construction"
    if any(term in text for term in ("dental", "clinic", "healthcare", "patient", "care")):
        return "healthcare"
    if any(term in text for term in ("school", "university", "student", "campus", "education")):
        return "education"
    if any(term in text for term in ("restaurant", "food", "cafe", "hospitality")):
        return "hospitality"
    return "service"


def _audience(text: str, industry: str) -> str:
    match = re.search(r"\bfor\s+([^.;,\n]{4,80})", text, re.IGNORECASE)
    if match:
        return _clean(match.group(1))
    return {
        "construction": "property owners, developers, and project teams",
        "healthcare": "patients and care teams",
        "education": "students, staff, and administrators",
        "hospitality": "local guests and event planners",
    }.get(industry, "clients who need a clear next step")


def _offer(industry: str) -> dict[str, Any]:
    if industry == "construction":
        return {
            "eyebrow": "Construction services",
            "title": "{name} builds dependable spaces from plan to handover",
            "summary": "{name} helps {audience} move construction projects forward with disciplined planning, safety-first execution, transparent updates, and clean closeout.",
            "primary_action": "Request a consultation",
            "about_title": "A construction partner built around coordination and accountability",
            "about_body": "{name} focuses on practical planning, field communication, site safety, schedule control, and handover quality for {audience}.",
            "principles": ["Safety before speed", "Clear project communication", "Quality visible at handover"],
            "services": [
                {"title": "Pre-construction planning", "detail": "Scope review, budget alignment, schedule planning, risk checks, and buildability guidance before work starts."},
                {"title": "General contracting", "detail": "Coordinated site execution, subcontractor management, quality control, and progress reporting."},
                {"title": "Renovation and fit-out", "detail": "Occupied-space upgrades, commercial interiors, phased delivery, and clean closeout documentation."},
            ],
            "contact_title": "Talk through the build before the site gets busy",
            "contact_detail": "Send the project type, location, timeline, budget range, and decision date so the first reply can be specific.",
        }
    if industry == "healthcare":
        return {
            "eyebrow": "Care experience",
            "title": "{name} makes care access clearer and calmer",
            "summary": "{name} helps {audience} understand services, book confidently, and get timely follow-up without confusing handoffs.",
            "primary_action": "Book an appointment",
            "about_title": "Built for trust, clarity, and patient confidence",
            "about_body": "{name} presents care options, team credentials, visit expectations, and follow-up paths clearly for {audience}.",
            "principles": ["Plain-language care", "Fast booking path", "Privacy-aware communication"],
            "services": [
                {"title": "Consultations", "detail": "Clear appointment paths with visit expectations, preparation details, and next-step guidance."},
                {"title": "Ongoing care", "detail": "Service information, follow-up reminders, and practical patient support."},
                {"title": "Care coordination", "detail": "Referral guidance, documentation support, and transparent status updates."},
            ],
            "contact_title": "Ask a care question or book a visit",
            "contact_detail": "Share the service needed, preferred time, and any urgency so the team can respond appropriately.",
        }
    return {
        "eyebrow": "Business services",
        "title": "{name} helps clients make confident decisions",
        "summary": "{name} gives {audience} a clear explanation of services, process, proof, and the fastest route to a useful conversation.",
        "primary_action": "Start an inquiry",
        "about_title": "A focused team with a practical delivery process",
        "about_body": "{name} explains the offer, engagement model, proof points, and communication rhythm for {audience}.",
        "principles": ["Specific offer", "Evidence before claims", "Fast inquiry path"],
        "services": [
            {"title": "Discovery", "detail": "Clarify goals, constraints, timeline, and the decision the client needs to make."},
            {"title": "Delivery", "detail": "Execute scoped work with updates, review points, and practical handoff material."},
            {"title": "Ongoing support", "detail": "Keep the work useful after launch with maintenance, improvements, and clear reporting."},
        ],
        "contact_title": "Tell us what needs to move forward",
        "contact_detail": "Share the goal, timeline, budget range, and decision point so the first reply can be useful.",
    }


def _proof(industry: str) -> list[dict[str, str]]:
    if industry == "construction":
        return [
            {"label": "Project focus", "value": "Safety and schedule"},
            {"label": "Core pages", "value": "4"},
            {"label": "Client path", "value": "Consultation request"},
        ]
    return [
        {"label": "Response target", "value": "1 business day"},
        {"label": "Core pages", "value": "4"},
        {"label": "Launch focus", "value": "Trust and conversion"},
    ]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())

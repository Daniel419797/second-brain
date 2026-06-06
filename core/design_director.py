"""Art-direction strategy for Friday's design generation loop."""

from __future__ import annotations

import re
from typing import Any


def design_strategy(request: str, product_name: str = "", *, page_label: str = "", stack: dict[str, Any] | None = None) -> dict[str, Any]:
    text = _clean(request)
    lower = text.lower()
    surface = _surface(lower, stack or {})
    industry = _industry(lower, product_name)
    route = _clean(page_label).lower() or "primary"
    strategy = _strategy_for(industry, surface)
    variants = _variant_directions(industry, surface, route)
    composition = _composition_strategy(industry, surface, route, lower)
    experience = _experience_strategy(industry, surface, route, lower, composition)
    anti_patterns = _anti_patterns(industry, surface)
    return {
        "surface": surface,
        "industry": industry,
        "route": route,
        "message": strategy["message"],
        "emotional_feel": strategy["emotional_feel"],
        "direction": strategy["direction"],
        "visual_language": strategy["visual_language"],
        "layout_signature": strategy["layout_signature"],
        "palette": strategy["palette"],
        "typography": strategy["typography"],
        "imagery": strategy["imagery"],
        "interaction_model": strategy["interaction_model"],
        "copy_voice": strategy["copy_voice"],
        "composition": composition,
        "experience": experience,
        "variant_directions": variants,
        "anti_patterns": anti_patterns,
        "quality_bar": _quality_bar(surface),
        "prompt_block": prompt_block(
            {
                **strategy,
                "surface": surface,
                "industry": industry,
                "route": route,
                "composition": composition,
                "experience": experience,
                "variant_directions": variants,
                "anti_patterns": anti_patterns,
                "quality_bar": _quality_bar(surface),
            }
        ),
    }


def prompt_block(strategy: dict[str, Any]) -> str:
    variants = "\n".join(f"- Variant {index}: {item}" for index, item in enumerate(strategy.get("variant_directions") or [], start=1))
    anti = "\n".join(f"- {item}" for item in strategy.get("anti_patterns") or [])
    bar = "\n".join(f"- {item}" for item in strategy.get("quality_bar") or [])
    composition = strategy.get("composition") if isinstance(strategy.get("composition"), dict) else {}
    primary = composition.get("primary") if isinstance(composition.get("primary"), dict) else {}
    options = composition.get("allowed_archetypes") if isinstance(composition.get("allowed_archetypes"), list) else []
    option_lines = "\n".join(
        f"- {item.get('name') or item.get('id')}: {item.get('first_viewport') or item.get('why') or ''}"
        for item in options[:4]
        if isinstance(item, dict)
    )
    composition_rules = "\n".join(f"- {item}" for item in composition.get("rules") or [])
    experience = strategy.get("experience") if isinstance(strategy.get("experience"), dict) else {}
    mode = experience.get("primary") if isinstance(experience.get("primary"), dict) else {}
    mode_options = experience.get("allowed_modes") if isinstance(experience.get("allowed_modes"), list) else []
    mode_lines = "\n".join(
        f"- {item.get('name') or item.get('id')}: {item.get('intent') or item.get('when_to_use') or ''}"
        for item in mode_options[:4]
        if isinstance(item, dict)
    )
    verification_lines = "\n".join(f"- {item}" for item in mode.get("verification") or [])
    return "\n".join(
        [
            "Art direction:",
            f"- Surface: {strategy.get('surface')}",
            f"- Industry/context: {strategy.get('industry')}",
            f"- Message to communicate: {strategy.get('message')}",
            f"- Emotional feel: {strategy.get('emotional_feel')}",
            f"- Creative direction: {strategy.get('direction')}",
            f"- Visual language: {strategy.get('visual_language')}",
            f"- Layout signature: {strategy.get('layout_signature')}",
            f"- Palette: {strategy.get('palette')}",
            f"- Typography: {strategy.get('typography')}",
            f"- Imagery: {strategy.get('imagery')}",
            f"- Interaction model: {strategy.get('interaction_model')}",
            f"- Copy voice: {strategy.get('copy_voice')}",
            "",
            "Composition direction:",
            f"- Primary archetype: {primary.get('name') or primary.get('id') or 'domain-specific composition'}",
            f"- Why this archetype: {primary.get('why') or ''}",
            f"- First viewport pattern: {primary.get('first_viewport') or ''}",
            "- Alternative archetypes to explore:",
            option_lines or "- Use a genuinely different hierarchy and first viewport composition.",
            "- Composition rules:",
            composition_rules or "- Do not default to the same split hero/card pattern unless the archetype explicitly calls for it.",
            "",
            "Experience mode:",
            f"- Primary mode: {mode.get('name') or mode.get('id') or 'static polished'}",
            f"- Intent: {mode.get('intent') or ''}",
            f"- Recommended libraries: {', '.join(mode.get('libraries') or [])}",
            f"- Motion/interaction rules: {'; '.join(mode.get('rules') or [])}",
            "- Alternative experience modes to explore:",
            mode_lines or "- Keep interaction purposeful and appropriate to the domain.",
            "- Verification requirements:",
            verification_lines or "- Browser screenshot, accessibility, dead-button, and performance checks.",
            "",
            "Generate distinct explorations, not small color swaps:",
            variants or "- Variant 1: clear, domain-specific, production-ready composition.",
            "",
            "Reject these visual/copy anti-patterns:",
            anti or "- Generic SaaS cards, placeholder copy, and decorative filler.",
            "",
            "Quality bar:",
            bar,
        ]
    )


def variant_direction_prompt(strategy: dict[str, Any], index: int) -> str:
    variants = list(strategy.get("variant_directions") or [])
    direction = variants[(max(1, index) - 1) % len(variants)] if variants else "change the composition, hierarchy, and content emphasis."
    return (
        f"Alternative design {index}: {direction} "
        "Keep the product/domain exact, use a genuinely different layout system, and avoid repeating the base screen."
    )


def art_direction_score(html: str, visible_text: str, request: str, strategy: dict[str, Any]) -> int:
    text = f"{visible_text} {html}".lower()
    industry = str(strategy.get("industry") or _industry(request.lower(), "")).lower()
    score = 0
    for term in _positive_terms(industry, str(strategy.get("surface") or "")):
        if re.search(rf"\b{re.escape(term)}s?\b", text):
            score += 2
    for term in _layout_terms(str(strategy.get("surface") or "")):
        if term in text:
            score += 1
    for finding in style_findings(html, visible_text, request, strategy):
        score -= int(finding.get("severity") or 2)
    return max(0, min(10, score))


def style_findings(html: str, visible_text: str, request: str, strategy: dict[str, Any]) -> list[dict[str, Any]]:
    text = _clean(visible_text).lower()
    raw = f"{visible_text} {html}".lower()
    industry = str(strategy.get("industry") or _industry(request.lower(), "")).lower()
    findings: list[dict[str, Any]] = []
    generic_phrases = [
        "independent service studio",
        "clear four-page website",
        "command workspace",
        "scale your service business through smarter operations",
        "what visitors can understand quickly",
        "launch path",
        "home focus",
    ]
    for phrase in generic_phrases:
        if phrase in text:
            findings.append({"id": "generic_design_copy", "severity": 5, "message": f"Visible copy repeats generic Friday/Stitch phrasing: {phrase}."})
    if _incoherent_visible_copy(text):
        findings.append({"id": "incoherent_visible_copy", "severity": 5, "message": "Visible headline/copy is grammatically incoherent and must be regenerated before implementation."})
    if industry != "general_business":
        terms = _positive_terms(industry, str(strategy.get("surface") or ""))
        matches = sum(1 for term in terms if re.search(rf"\b{re.escape(term)}s?\b", text))
        minimum = 3 if len(terms) >= 8 else 2
        if matches < minimum:
            findings.append(
                {
                    "id": "weak_taxonomy_signal",
                    "severity": 3,
                    "message": f"Design lacks enough {industry} message/visual-language signals.",
                }
            )
    if industry == "energy_climate":
        required = (
            "climate", "risk", "property", "portfolio", "wildfire", "flood", "heat",
            "insurance", "tenant", "maintenance", "microgrid", "energy", "solar",
            "battery", "grid", "demand", "outage", "building", "load", "resilience",
        )
        matches = sum(1 for term in required if re.search(rf"\b{re.escape(term)}s?\b", text))
        if matches < 3:
            findings.append({"id": "weak_industry_art_direction", "severity": 4, "message": "Climate/energy design lacks enough climate risk, property, wildfire, flood, energy, grid, building, load, or resilience signals."})
        wrong_domain = (
            "construction services", "contractor", "jobsite", "handover", "crane",
            "concrete", "bid package", "atelier", "collections", "private inquiry",
            "private clients", "private client", "concierge", "concierge access",
            "permanent legacy", "craftsmanship", "provenance", "notice the difference",
            "crafted for private", "quiet confidence", "material integrity",
        )
        if any(term in text for term in wrong_domain):
            findings.append({"id": "wrong_domain_art_direction", "severity": 5, "message": "Climate/energy software design drifted into construction, luxury, or concierge copy."})
    if industry in {"construction", "real_estate"}:
        required = ("construction", "infrastructure", "project", "safety", "development")
        matches = sum(1 for term in required if re.search(rf"\b{re.escape(term)}s?\b", text))
        if matches < 3:
            findings.append({"id": "weak_industry_art_direction", "severity": 4, "message": "Construction-company design lacks enough construction, infrastructure, project, safety, or development signals."})
        if all(term not in raw for term in ("project", "bridge", "site", "civil", "safety", "steel", "concrete", "infrastructure")):
            findings.append({"id": "missing_industry_visual_language", "severity": 3, "message": "Construction-company design lacks material/project visual language."})
    if _looks_like_plain_saas(raw, industry):
        findings.append({"id": "samey_saas_visual_grammar", "severity": 4, "message": "Design falls back to generic SaaS card/hero visual grammar for a non-SaaS brand."})
    if industry in {"developer_tools", "ai_saas"} and _uses_stock_person_hero(raw):
        findings.append({"id": "stock_person_hero_for_developer_tool", "severity": 5, "message": "Developer-tool design uses stock/person portrait imagery instead of product, code, docs, or architecture proof."})
    return _dedupe_findings(findings)


def _incoherent_visible_copy(text: str) -> bool:
    lowered = _clean(text).lower()
    return any(
        re.search(pattern, lowered)
        for pattern in (
            r"\bfor\s+the\s+of\b",
            r"\b(?:the|a|an)\s+of\b",
            r"\bof\s+(?:the\s+)?of\b",
            r"\bfor\s+for\b",
            r"\bthe\s+the\b",
        )
    )


def _uses_stock_person_hero(raw: str) -> bool:
    text = str(raw or "").lower()
    if "<img" not in text:
        return False
    person_alt = re.search(r"\balt\s*=\s*['\"][^'\"]*(?:contributor|portrait|avatar|person|people|woman|man|face|founder|team)[^'\"]*['\"]", text)
    stock_terms = any(term in text for term in ("stock photo", "headshot", "portrait", "contributor"))
    return bool(person_alt or stock_terms)


def _surface(text: str, stack: dict[str, Any]) -> str:
    if any(term in text for term in ("website", "site", "landing", "four-page", "4 page", "4-page", "marketing")):
        return "marketing_website"
    if any(term in text for term in ("dashboard", "command center", "portal", "management", "workspace", "admin")):
        return "operational_dashboard"
    if stack.get("stack") == "flutter" or any(term in text for term in ("mobile app", "ios app", "android app", "flutter app", "native app")):
        return "mobile_app"
    return "product_app"


def _industry(text: str, product_name: str) -> str:
    combined = f"{text} {product_name}".lower()
    if _contains_any_term(
        combined,
        (
            "climate-tech",
            "climatetech",
            "climate-risk",
            "climate risk",
            "property risk",
            "portfolio risk",
            "wildfire",
            "flood",
            "heat risk",
            "insurance risk",
            "tenant-impact",
            "tenant impact",
            "clean energy",
            "energy management",
            "energy grid",
            "microgrid",
            "microgrids",
            "solar",
            "battery",
            "batteries",
            "demand spike",
            "demand spikes",
            "outage risk",
            "building energy",
            "commercial buildings monitor",
            "grid monitoring",
            "renewable",
            "decarbonization",
        )
    ):
        return "energy_climate"
    if _contains_any_term(
        combined,
        (
            "developer tool",
            "devtool",
            "api platform",
            "backend-as-a-service",
            "backend as a service",
            "baas",
            "self-hosted",
            "no-code backend",
            "api monetization",
            "api keys",
            "websocket",
            "plugin marketplace",
            "sdk",
            "cli",
            "docs",
            "observability",
            "infrastructure as code",
        )
    ):
        return "developer_tools"
    if _contains_any_term(combined, ("ai saas", "ai platform", "ai agent", "copilot", "llm", "automation platform", "machine learning", "model ops")):
        return "ai_saas"
    mapping = [
        ("luxury", ("luxury", "quiet luxury", "high-end", "private club", "concierge", "jewelry", "watch", "boutique hotel", "luxury estate", "private estate")),
        ("fintech", ("fintech", "neobank", "digital bank", "wealth app", "trading", "investment", "crypto", "wallet", "remittance")),
        ("gaming", ("game", "gaming", "esports", "streaming", "quest", "guild", "player", "arcade")),
        ("developer_tools", ("developer tool", "devtool", "api platform", "sdk", "cli", "docs", "observability", "infrastructure as code")),
        ("logistics", ("logistics", "supply chain", "fleet", "warehouse", "freight", "delivery", "dispatch", "inventory routing")),
        ("ngo", ("ngo", "nonprofit", "charity", "donation", "fundraising", "impact organization", "community program")),
        ("fashion", ("fashion", "apparel", "clothing", "runway", "lookbook", "streetwear", "beauty", "cosmetic")),
        ("portfolio", ("portfolio", "personal site", "photographer", "artist", "case study", "resume", "cv")),
        ("government", ("government", "public sector", "civic", "municipal", "city council", "permit", "public service")),
        ("ai_saas", ("ai saas", "ai platform", "ai agent", "copilot", "llm", "automation platform", "machine learning", "model ops")),
        ("marketplace", ("marketplace", "two-sided", "buyers and sellers", "vendor", "seller", "listing platform", "booking marketplace")),
        ("energy_climate", ("climate-tech", "climatetech", "climate-risk", "climate risk", "property risk", "portfolio risk", "wildfire", "flood", "heat risk", "insurance risk", "tenant-impact", "tenant impact", "clean energy", "microgrid", "microgrids", "solar", "battery", "batteries", "grid monitoring", "renewable", "decarbonization", "outage risk")),
        ("construction", ("construction", "contractor", "infrastructure", "civil", "skanska", "turner", "building company")),
        ("healthcare", ("clinic", "healthcare", "patient", "dental", "hospital", "care")),
        ("education", ("university", "school", "student", "lecturer", "campus", "course")),
        ("restaurant", ("restaurant", "kitchen", "waitlist", "shift", "menu", "food")),
        ("field_service", ("field service", "technician", "hvac", "plumbing", "electrical", "dispatch")),
        ("finance", ("bank", "finance", "invoice", "billing", "payment", "paystack", "stripe", "accounting")),
        ("creative", ("studio", "agency", "portfolio", "designer", "creative")),
        ("real_estate", ("real estate", "property", "development", "commercial development")),
        ("commerce", ("commerce", "store", "retail", "shop", "ecommerce")),
    ]
    for industry, terms in mapping:
        if _contains_any_term(combined, terms):
            return industry
    return "general_business"


def _contains_any_term(text: str, terms: tuple[str, ...]) -> bool:
    return any(_contains_term(text, term) for term in terms)


def _contains_term(text: str, term: str) -> bool:
    value = str(text or "").lower()
    key = str(term or "").strip().lower()
    if not key:
        return False
    if re.fullmatch(r"[a-z0-9]+", key):
        return bool(re.search(rf"\b{re.escape(key)}\b", value))
    return key in value


_DASHBOARD_STRATEGY = {
    "message": "This workspace helps operators see what matters, decide quickly, and act with proof.",
    "emotional_feel": "calm control, speed, confidence, low cognitive load",
    "direction": "operator cockpit with dense, calm decision surfaces",
    "visual_language": "quiet utility, visible data hierarchy, clear ownership and status states",
    "layout_signature": "persistent navigation, metric rail, work queue, detail panel, action drawer",
    "palette": "neutral base with purposeful status colors, not decorative gradients",
    "typography": "compact interface scale, tabular numbers, readable labels",
    "imagery": "no stock hero imagery; use icons, status chips, charts, and data objects",
    "interaction_model": "filters, tabs, row actions, modals, empty/error/loading states",
    "copy_voice": "specific operational language from the domain",
}


_GENERAL_STRATEGY = {
    "message": "This product or website solves a specific problem and gives the visitor a clear next step.",
    "emotional_feel": "clear, useful, credible, quietly polished",
    "direction": "domain-specific product storytelling with practical conversion paths",
    "visual_language": "clear hierarchy, original content, useful proof, restrained polish",
    "layout_signature": "specific hero, proof band, feature/service sections, primary action path",
    "palette": "balanced neutral system with domain-appropriate accents, not one-note purple or beige",
    "typography": "production web scale with readable headings and compact sections",
    "imagery": "realistic product/domain visuals, not abstract blobs or generic dashboards",
    "interaction_model": "real links, forms, states, and expected user actions",
    "copy_voice": "specific, useful, non-generic",
    "positive_terms": ["proof", "service", "contact", "process", "trust", "client", "outcome", "project"],
    "anti_patterns": ["Do not use vague startup filler, placeholder proof, or abstract decorative visuals as the main evidence."],
    "variant_directions": [
        "Editorial brand/product page with strong first impression, proof band, and specific conversion path.",
        "Practical service/product layout with comparison sections, process, outcomes, and contact action.",
        "Trust-led layout with case proof, customer questions, credibility signals, and focused CTA.",
    ],
}


_DESIGN_TAXONOMY: dict[str, dict[str, Any]] = {
    "luxury": {
        "message": "The brand is scarce, crafted, and worth slowing down for.",
        "emotional_feel": "desire, restraint, intimacy, confidence, exclusivity",
        "direction": "quiet luxury with editorial restraint and tactile detail",
        "visual_language": "large negative space, close-up materials, elegant asymmetry, slow reveal",
        "layout_signature": "immersive hero, provenance story, product/editorial modules, appointment or concierge path",
        "palette": "warm ivory, ink, charcoal, metallic or jewel accent used sparingly",
        "typography": "refined serif or high-contrast display paired with quiet readable body type",
        "imagery": "macro product details, craftsmanship, architecture, human service moments",
        "interaction_model": "concierge CTAs, appointment flows, lookbook navigation, restrained micro-interactions",
        "copy_voice": "spare, sensorial, confident, never loud",
        "positive_terms": ["craft", "atelier", "private", "concierge", "collection", "heritage", "appointment", "bespoke"],
        "anti_patterns": ["Do not use loud gradients, badge-heavy SaaS cards, discount language, or cluttered grids."],
        "variant_directions": [
            "Editorial luxury lookbook with immersive imagery, provenance, and discreet concierge action.",
            "Boutique product story with material close-ups, collection modules, and appointment path.",
            "Private-client service page with restrained typography, trust cues, and high-touch contact flow.",
        ],
    },
    "fintech": {
        "message": "Money is safer, clearer, and easier to control here.",
        "emotional_feel": "trust, speed, control, modern confidence",
        "direction": "high-trust financial interface with clarity and momentum",
        "visual_language": "precise data surfaces, secure cues, clean account/card/payment patterns",
        "layout_signature": "value proposition, trust/security proof, product flows, pricing/compliance notes, signup path",
        "palette": "deep navy, white, cool gray, green/blue confidence accent; avoid casino neon",
        "typography": "crisp sans, tabular numbers, strong contrast for balances and metrics",
        "imagery": "cards, payment flows, account snapshots, compliance badges, people using finance tools",
        "interaction_model": "calculators, account states, verification steps, transparent fees, secure CTAs",
        "copy_voice": "precise, transparent, reassuring, benefit-led",
        "positive_terms": ["secure", "payment", "account", "wallet", "compliance", "transfer", "fee", "balance"],
        "anti_patterns": ["Do not imply guaranteed returns, use gambling visuals, hide risk, or use vague money hype."],
        "variant_directions": [
            "Trust-first fintech page with security proof, transparent fees, and account flow previews.",
            "Product-led finance dashboard story with balances, transfers, controls, and compliance notes.",
            "Conversion-focused money movement page with calculator, testimonials, and secure signup path.",
        ],
    },
    "gaming": {
        "message": "This experience is alive, competitive, and worth playing now.",
        "emotional_feel": "energy, mastery, anticipation, immersion",
        "direction": "immersive game world with strong momentum and player identity",
        "visual_language": "dynamic scenes, depth, motion cues, bold contrast, faction/player motifs",
        "layout_signature": "gameplay-first hero, modes/features, progression loop, media gallery, download/join action",
        "palette": "genre-specific high contrast with one electric accent; avoid generic purple-only gradients",
        "typography": "bold display for titles, compact readable UI labels for stats and modes",
        "imagery": "real gameplay, characters, maps, items, UI states, cinematic scenes",
        "interaction_model": "trailers, mode tabs, player stats, download/join buttons, platform badges",
        "copy_voice": "short, vivid, active, player-centered",
        "positive_terms": ["play", "mode", "level", "quest", "player", "match", "arena", "reward"],
        "anti_patterns": ["Do not use corporate SaaS layouts, bland stock art, or explain gameplay only in paragraphs."],
        "variant_directions": [
            "Gameplay-first landing page with cinematic scene, mode cards, and immediate play CTA.",
            "Community/esports page with player stats, events, leaderboards, and join flow.",
            "World-building page with characters, maps, progression loop, and media gallery.",
        ],
    },
    "developer_tools": {
        "message": "Developers can understand, try, and trust the tool quickly.",
        "emotional_feel": "competence, speed, clarity, technical credibility",
        "direction": "developer-first product page with proof in code and workflow",
        "visual_language": "docs-grade clarity, code samples, terminal/API surfaces, integration diagrams",
        "layout_signature": "hero with code, install path, docs links, use cases, architecture proof, community/support",
        "palette": "near-white or dark terminal base with restrained accent and syntax colors",
        "typography": "readable sans plus monospace for commands, code, and identifiers",
        "imagery": "code blocks, CLI output, API requests, repo/CI states, architecture diagrams",
        "interaction_model": "copy buttons, tabs, quickstart, SDK selectors, docs/search links",
        "copy_voice": "specific, direct, technical, no marketing fog",
        "positive_terms": ["api", "sdk", "cli", "docs", "deploy", "github", "terminal", "integration"],
        "anti_patterns": [
            "Do not hide the product behind vague AI language; show concrete code, commands, and integration proof.",
            "Do not use stock portraits, contributor headshots, abstract faces, or decorative people as the hero visual; use product UI, code, docs, CLI, or architecture proof.",
            "Do not ship awkward generated headlines; every headline must read like a human wrote it.",
        ],
        "variant_directions": [
            "Docs-first developer page with quickstart command, code tabs, and API proof.",
            "Architecture-led page with integration diagram, reliability claims, and examples.",
            "Open-source/community page with GitHub signals, install path, and use-case cards.",
        ],
    },
    "logistics": {
        "message": "Movement, capacity, timing, and exceptions are visible and under control.",
        "emotional_feel": "precision, urgency, reliability, operational calm",
        "direction": "supply-chain control surface with route and exception visibility",
        "visual_language": "maps, timelines, route lines, capacity cards, exception alerts",
        "layout_signature": "operations map, shipment/fleet board, status timeline, exception queue, contact/demo path",
        "palette": "industrial neutral, blue/teal, amber status accent, high-contrast maps",
        "typography": "compact labels, tabular metrics, clear status hierarchy",
        "imagery": "warehouses, trucks, routes, containers, dispatch rooms, package flows",
        "interaction_model": "filters, ETA states, route details, exception triage, tracking/search",
        "copy_voice": "direct, operational, time-aware",
        "positive_terms": ["route", "fleet", "shipment", "warehouse", "eta", "dispatch", "capacity", "inventory"],
        "anti_patterns": ["Do not make logistics look like a generic CRM; show movement, timing, and exceptions."],
        "variant_directions": [
            "Map-led logistics page with route visibility, ETA proof, and exception handling.",
            "Warehouse/fleet operations dashboard with capacity, delays, and action queues.",
            "Customer-facing delivery trust page with tracking, reliability proof, and contact path.",
        ],
    },
    "ngo": {
        "message": "This mission matters, donations/actions are trustworthy, and impact is visible.",
        "emotional_feel": "empathy, urgency, hope, accountability",
        "direction": "mission-first impact story with transparent calls to action",
        "visual_language": "human photography, impact metrics, story modules, transparent donation paths",
        "layout_signature": "mission hero, problem/solution, impact proof, stories, donation/volunteer action",
        "palette": "warm human neutrals with optimistic accent; avoid tragedy-only dark treatment",
        "typography": "clear editorial hierarchy, accessible body copy, strong action labels",
        "imagery": "real communities, volunteers, field work, outcomes, respectful portraits",
        "interaction_model": "donate, volunteer, campaign filters, impact reports, newsletter/contact",
        "copy_voice": "human, specific, transparent, action-oriented",
        "positive_terms": ["impact", "donate", "volunteer", "community", "program", "mission", "fund", "outcome"],
        "anti_patterns": ["Do not use guilt-heavy manipulation, vague impact claims, or hidden donation paths."],
        "variant_directions": [
            "Mission-first homepage with human story, impact proof, and donation path.",
            "Campaign page with urgent need, transparent funding goal, and volunteer options.",
            "Impact report page with metrics, field stories, and accountability sections.",
        ],
    },
    "fashion": {
        "message": "The brand has a point of view, a silhouette, and a lifestyle people want to enter.",
        "emotional_feel": "aspiration, identity, taste, cultural energy",
        "direction": "editorial fashion system with strong visual rhythm and product desire",
        "visual_language": "lookbook grids, model/editorial photography, collection rhythm, material detail",
        "layout_signature": "collection hero, category/editorial modules, product/story mix, shop/contact path",
        "palette": "brand-led palette with strong contrast; avoid generic ecommerce blue",
        "typography": "fashion-forward display with simple commerce-readable labels",
        "imagery": "models, garments, texture close-ups, campaign imagery, product details",
        "interaction_model": "lookbook navigation, size/product states, collection filters, shop or inquiry CTAs",
        "copy_voice": "evocative, concise, trend-aware, not overexplained",
        "positive_terms": ["collection", "lookbook", "style", "atelier", "fabric", "silhouette", "season", "shop"],
        "anti_patterns": ["Do not use generic grid-only ecommerce, fake discounts, or bland service-business copy."],
        "variant_directions": [
            "Campaign-led fashion page with full-bleed editorial image, collection story, and shop path.",
            "Lookbook grid with product detail rhythm, category navigation, and brand statement.",
            "Boutique commerce page with featured pieces, material notes, and inquiry/shop action.",
        ],
    },
    "portfolio": {
        "message": "This person or studio has taste, range, and credible work worth hiring.",
        "emotional_feel": "personality, confidence, clarity, creative trust",
        "direction": "work-first portfolio with sharp case-study storytelling",
        "visual_language": "large work previews, case-study rhythm, personal voice, intentional whitespace",
        "layout_signature": "intro, selected work, case studies, capabilities/about, contact path",
        "palette": "personality-led but restrained enough to let work lead",
        "typography": "distinctive headings with readable project metadata",
        "imagery": "real project images, process artifacts, portraits, mockups, outcomes",
        "interaction_model": "case-study links, filters, resume/contact, project detail navigation",
        "copy_voice": "personal, specific, confident, outcome-aware",
        "positive_terms": ["work", "case study", "project", "selected", "creative", "client", "process", "contact"],
        "anti_patterns": ["Do not make the portfolio look like a generic agency landing page without actual work."],
        "variant_directions": [
            "Case-study-led portfolio with large work previews and concise project metadata.",
            "Personal editorial portfolio with intro, process, selected work, and direct contact.",
            "Studio-style portfolio with capability filters, outcomes, and client proof.",
        ],
    },
    "government": {
        "message": "Public services are clear, accessible, trustworthy, and easy to complete.",
        "emotional_feel": "trust, order, accessibility, civic reliability",
        "direction": "public-service interface with clarity, compliance, and task completion",
        "visual_language": "plain-language hierarchy, service cards, official proof, accessible forms",
        "layout_signature": "service finder, announcement/status area, task cards, documents, contact/help routes",
        "palette": "civic blues/neutrals with clear contrast and status colors",
        "typography": "high readability, plain labels, accessible sizes",
        "imagery": "citizens, public buildings, service contexts; avoid decorative stock",
        "interaction_model": "search, service filters, forms, document downloads, language/accessibility controls",
        "copy_voice": "plain, official, helpful, non-promotional",
        "positive_terms": ["service", "permit", "public", "resident", "form", "application", "office", "civic"],
        "anti_patterns": ["Do not use flashy startup language, low-contrast text, or hidden public-service actions."],
        "variant_directions": [
            "Service-finder government page with search, popular tasks, and announcement status.",
            "Permit/application page with step-by-step forms, documents, and help routes.",
            "Civic information page with official proof, accessibility controls, and contact channels.",
        ],
    },
    "ai_saas": {
        "message": "AI turns a painful workflow into a reliable, explainable, controllable system.",
        "emotional_feel": "intelligent, calm, capable, trustworthy, not magical hype",
        "direction": "AI product experience with workflow proof and human control",
        "visual_language": "before/after workflow, prompt/result panels, automation paths, audit/approval cues",
        "layout_signature": "problem-to-workflow hero, product UI preview, integrations, proof, security/trust, pricing/demo",
        "palette": "clean neutral with one vivid intelligence accent; avoid purple-blue gradient sameness",
        "typography": "modern sans, clear product labels, readable AI output examples",
        "imagery": "real product screens, agent traces, workflow diagrams, integration states",
        "interaction_model": "demo prompts, output previews, approval controls, integration selectors",
        "copy_voice": "clear, concrete, responsible, outcome-led",
        "positive_terms": ["ai", "workflow", "agent", "automation", "approval", "integration", "audit", "prompt"],
        "anti_patterns": [
            "Do not use vague 'AI magic' claims, orb backgrounds, fake chat bubbles only, or unverifiable outcomes.",
            "Do not use decorative robot/person portraits as the primary proof; show agent traces, workflow states, integrations, or real product screens.",
            "Do not ship awkward generated headlines; every headline must read like a human wrote it.",
        ],
        "variant_directions": [
            "Product-led AI SaaS page with workflow before/after, agent trace, and approval controls.",
            "Integration-led AI platform page with systems, automation paths, and security proof.",
            "Use-case-led AI page with role-specific outcomes, demo prompt, and pricing/demo path.",
        ],
    },
    "marketplace": {
        "message": "The right supply and demand can find each other with trust and less friction.",
        "emotional_feel": "choice, confidence, momentum, trust",
        "direction": "two-sided marketplace with discovery, trust, and transaction clarity",
        "visual_language": "listing cards, filters, trust badges, map/category discovery, seller/buyer paths",
        "layout_signature": "search/discovery hero, category/listing grid, how it works, trust proof, buyer/seller CTA",
        "palette": "clean neutral with category-coded accents and high-contrast actions",
        "typography": "commerce-readable hierarchy with strong listing metadata",
        "imagery": "real listings, providers/products, map/location context, reviews",
        "interaction_model": "search, filters, saved listings, compare, seller signup, booking/contact",
        "copy_voice": "clear, reassuring, action-oriented",
        "positive_terms": ["listing", "seller", "buyer", "vendor", "search", "filter", "review", "booking"],
        "anti_patterns": ["Do not hide either side of the marketplace; show discovery, trust, and transaction flow."],
        "variant_directions": [
            "Discovery-first marketplace with search hero, category filters, and listing cards.",
            "Trust-first marketplace with reviews, verified sellers, and buyer/seller paths.",
            "Transaction-focused marketplace with compare, booking/contact flow, and onboarding CTA.",
        ],
    },
    "energy_climate": {
        "message": "Property portfolios and buildings can understand climate risk, wildfire, flood, heat, grid state, and clean-power decisions before losses, outages, or costs spike.",
        "emotional_feel": "technical confidence, momentum, resilience, climate seriousness",
        "direction": "climate and property-risk intelligence story with visible portfolio, grid, and resilience proof",
        "visual_language": "property portfolio maps, energy grid lines, building silhouettes, wildfire/flood/heat risk layers, solar/battery states, load curves, outage-risk signals, control-room precision",
        "layout_signature": "immersive climate-risk hero, property/asset telemetry proof, platform modules, case-study metrics, resilience/contact path",
        "palette": "deep graphite or night-grid base with electric cyan, solar amber, battery green, and warning orange used as status colors",
        "typography": "precise modern sans with tabular metrics and restrained technical labels",
        "imagery": "commercial property portfolios, wildfire/flood/heat overlays, microgrids, solar arrays, battery storage, building systems, control diagrams, climate-risk telemetry",
        "interaction_model": "metric toggles, grid-status panels, load forecasts, outage-risk alerts, case-study filters, contact/demo form",
        "copy_voice": "specific, technical, climate-aware, operational, never construction-company language",
        "positive_terms": ["climate", "risk", "property", "portfolio", "wildfire", "flood", "heat", "insurance", "microgrid", "energy", "solar", "battery", "grid", "demand", "outage", "building", "load", "resilience"],
        "anti_patterns": [
            "Do not turn climate/energy software into construction, contractor, real-estate, or generic consulting copy.",
            "Do not use CLI/API/Web3/developer-tool copy unless the product is actually a developer tool.",
            "Do not show beige service cards or generic dashboards without energy telemetry, grid state, or building context.",
        ],
        "variant_directions": [
            "Immersive energy-grid landing page with live microgrid lines, building silhouettes, demand spikes, and battery/solar metrics.",
            "Platform-led climate operations page with monitoring modules, outage-risk scoring, facility portfolio, and case-study proof.",
            "Resilience story page with before/after grid events, cost/risk metrics, commercial building proof, and demo contact path.",
        ],
    },
    "construction": {
        "message": "This company can deliver complex physical projects safely, credibly, and at scale.",
        "emotional_feel": "authority, solidity, confidence, safety, momentum",
        "direction": "infrastructure authority with editorial project proof",
        "visual_language": "large project photography, structural grids, material confidence, safety/proof signals",
        "layout_signature": "split hero, project proof band, capabilities grid, case-study teasers, inquiry path",
        "palette": "concrete/off-white base, deep blue or forest/black, steel gray, one safety accent",
        "typography": "confident but restrained display headings, strong section labels, no giant page labels",
        "imagery": "bridges, job sites, cranes, structural details, teams, real project contexts",
        "interaction_model": "clear project inquiry CTAs, capability navigation, proof cards, contact pathways",
        "copy_voice": "credible, concise, evidence-led, procurement-friendly",
        "positive_terms": ["construction", "infrastructure", "project", "safety", "development", "civil", "site", "building", "commercial", "engineering"],
        "anti_patterns": ["Do not make a construction company look like a generic consulting SaaS landing page.", "Do not show fake analytics dashboards as the primary visual; use project/site/material context.", "Do not use vague service-business automation copy."],
        "variant_directions": [
            "Editorial project authority: split hero with infrastructure imagery, safety/proof band, and capability cards.",
            "Portfolio-led construction story: case-study grid, market sectors, regional proof, and inquiry path.",
            "Procurement-ready capabilities page: services, delivery process, risk/safety commitments, and contact routes.",
        ],
    },
    "healthcare": {
        "message": "Care is competent, private, accessible, and easy to start.",
        "emotional_feel": "calm, trust, reassurance, dignity",
        "direction": "trusted care operations with warm clarity",
        "visual_language": "calm surfaces, clinical hierarchy, accessible forms, human trust cues",
        "layout_signature": "care promise, patient/admin pathways, service blocks, privacy reassurance, contact flow",
        "palette": "soft neutral base with teal/blue/green accents and high contrast text",
        "typography": "clear humanist type scale, strong readability, no decorative drama",
        "imagery": "care teams, reception workflow, treatment rooms, respectful patient context",
        "interaction_model": "appointment/request actions, privacy notes, intake forms, status reassurance",
        "copy_voice": "plain, reassuring, precise",
        "positive_terms": ["patient", "care", "clinic", "privacy", "appointment", "health", "intake", "provider"],
        "anti_patterns": ["Do not use cold corporate copy, scary imagery, low-contrast text, or unclear appointment paths."],
        "variant_directions": [
            "Warm trust-led page with care/team cues, service paths, privacy reassurance, and clear request flow.",
            "Clinical operations layout with intake steps, response expectations, service cards, and contact options.",
            "Patient/admin split journey with role cards, proof signals, and low-friction form path.",
        ],
    },
    "education": {
        "message": "Students, staff, and institutions can navigate academic work clearly and fairly.",
        "emotional_feel": "institutional trust, clarity, support, progress",
        "direction": "campus operations with institutional clarity",
        "visual_language": "structured academic navigation, trustworthy admin workflows, status visibility",
        "layout_signature": "role paths, calendar/approval signals, student/service sections, reporting proof",
        "palette": "institutional neutrals with one confident school accent",
        "typography": "readable, formal, information-first",
        "imagery": "campus, classrooms, admin offices, student service counters",
        "interaction_model": "role tabs, approvals, forms, reporting cards",
        "copy_voice": "clear, administrative, helpful",
        "positive_terms": ["student", "course", "campus", "registrar", "lecturer", "approval", "academic"],
        "anti_patterns": ["Do not make education feel like generic SaaS; show roles, services, academic workflows, and support paths."],
        "variant_directions": [
            "Role-path education page with students, staff, and admin journeys clearly separated.",
            "Campus operations page with approvals, calendars, service counters, and reporting proof.",
            "Institutional trust page with programs/services, support paths, and contact or application flow.",
        ],
    },
    "restaurant": {
        "message": "Service runs smoother, guests feel cared for, and the floor stays in rhythm.",
        "emotional_feel": "warmth, energy, pace, hospitality",
        "direction": "service-floor energy with operational precision",
        "visual_language": "warm, high-contrast service rhythm with inventory/shift cues",
        "layout_signature": "busy-hour hero, shift proof, menu/order pressure, team handoff, booking/contact",
        "palette": "warm neutrals with one sharp service accent, avoid beige monotone",
        "typography": "bold compact headings with readable body copy",
        "imagery": "kitchen line, dining floor, staff coordination, ingredients, ticket rails",
        "interaction_model": "shift actions, waitlist/order states, booking/contact CTAs",
        "copy_voice": "direct, energetic, practical",
        "positive_terms": ["shift", "kitchen", "table", "order", "staff", "service", "inventory", "guest"],
        "anti_patterns": ["Do not use generic office-dashboard visuals for restaurant work; show food, staff, guests, timing, or service pressure."],
        "variant_directions": [
            "Service-floor energy page with busy-hour imagery, shift proof, quick actions, and booking/contact path.",
            "Operations-first layout with queue/ticket pressure, staff handoff, inventory cues, and outcomes.",
            "Hospitality brand page with menu/service narrative, customer proof, and direct inquiry path.",
        ],
    },
    "field_service": {
        "message": "Field teams can respond faster, assign smarter, and keep customers informed.",
        "emotional_feel": "readiness, control, reliability, practical urgency",
        "direction": "dispatch-grade field operations with route and technician clarity",
        "visual_language": "maps, job cards, technician states, SLA/status chips, inventory readiness",
        "layout_signature": "dispatch board, route map, technician panel, job detail, customer update actions",
        "palette": "workwear neutrals, blue/green action colors, amber/red priority accents",
        "typography": "compact interface labels, strong job/ETA hierarchy",
        "imagery": "technicians, vans, tools, jobsites, route maps, service equipment",
        "interaction_model": "assign, reroute, notify, escalate, inventory check, invoice handoff",
        "copy_voice": "operational, specific, dispatch-ready",
        "positive_terms": ["technician", "dispatch", "job", "route", "sla", "parts", "invoice", "customer"],
        "anti_patterns": ["Do not make field service look like a generic CRM; show jobs, routes, technicians, and urgent states."],
        "variant_directions": [
            "Dispatch-board layout with urgent jobs, technician availability, and route proof.",
            "Technician-first field app view with tasks, parts, safety, and customer updates.",
            "Operations dashboard with SLA risks, invoices, inventory readiness, and escalation actions.",
        ],
    },
    "finance": {
        "message": "Financial work is organized, accurate, auditable, and easier to complete.",
        "emotional_feel": "trust, order, clarity, accountability",
        "direction": "financial operations interface with transparent controls",
        "visual_language": "ledgers, invoice/payment states, audit trails, clear exception handling",
        "layout_signature": "summary metrics, transaction table, exception queue, approvals, reports",
        "palette": "neutral financial base with blue/green trust accents and status colors",
        "typography": "tabular numbers, compact tables, strong labels",
        "imagery": "financial dashboards, documents, invoices, secure account contexts",
        "interaction_model": "approve, reconcile, export, filter, audit, payment status",
        "copy_voice": "precise, compliant, no hype",
        "positive_terms": ["invoice", "payment", "account", "audit", "reconcile", "report", "approval", "balance"],
        "anti_patterns": ["Do not use vague money promises, fake performance claims, or low-detail finance visuals."],
        "variant_directions": [
            "Finance operations dashboard with invoice/payment queues, audit trail, and approvals.",
            "Trust-led finance website with transparent process, compliance proof, and contact path.",
            "Reporting-first page with metrics, exports, reconciliation states, and secure CTAs.",
        ],
    },
    "creative": {
        "message": "This studio has taste, strategy, and a clear creative point of view.",
        "emotional_feel": "expressive, confident, curated, intelligent",
        "direction": "creative studio presence with distinctive editorial rhythm",
        "visual_language": "case-study previews, bold composition, art-directed imagery, confident whitespace",
        "layout_signature": "point-of-view hero, selected work, services, process, client proof, inquiry",
        "palette": "brand-led palette with deliberate contrast, not default SaaS colors",
        "typography": "expressive display paired with clean project metadata",
        "imagery": "work samples, campaign visuals, process boards, studio/team context",
        "interaction_model": "case-study links, service inquiry, filters, contact/brief form",
        "copy_voice": "sharp, original, strategic, not fluffy",
        "positive_terms": ["studio", "brand", "campaign", "creative", "work", "strategy", "case", "client"],
        "anti_patterns": ["Do not make a creative studio look like a generic automation consultancy."],
        "variant_directions": [
            "Editorial studio page with point of view, large work previews, and brief inquiry.",
            "Case-study-first page with campaign results, services, and process.",
            "Brand-system page with expressive type, selected clients, and contact path.",
        ],
    },
    "real_estate": {
        "message": "People can trust the place, numbers, location, and next step.",
        "emotional_feel": "confidence, aspiration, grounded trust",
        "direction": "property/investment story with location and proof",
        "visual_language": "property photography, maps, amenity/proof cards, neighborhood context",
        "layout_signature": "property hero, stats/location band, gallery, details, inquiry/booking",
        "palette": "architectural neutrals with premium accent and clear map/status colors",
        "typography": "elegant but readable real-estate listing hierarchy",
        "imagery": "exteriors, interiors, maps, floorplans, neighborhood scenes",
        "interaction_model": "gallery, map, inquiry form, schedule tour, compare/save",
        "copy_voice": "specific, location-aware, credible",
        "positive_terms": ["property", "location", "development", "floorplan", "amenity", "tour", "listing", "investment"],
        "anti_patterns": ["Do not use generic SaaS visuals; show place, space, location, and decision details."],
        "variant_directions": [
            "Property-led page with gallery, location proof, amenities, and tour inquiry.",
            "Development/investment page with project stats, timeline, and stakeholder proof.",
            "Listing marketplace page with filters, map, cards, and contact path.",
        ],
    },
    "commerce": {
        "message": "Products are easy to understand, desire, compare, and buy.",
        "emotional_feel": "clarity, desire, confidence, momentum",
        "direction": "commerce experience with product desire and buying clarity",
        "visual_language": "product photography, category cards, reviews, detail modules, clear prices/actions",
        "layout_signature": "product/category hero, featured products, trust/reviews, detail proof, checkout/shop CTA",
        "palette": "brand-led commerce palette with high-contrast purchase actions",
        "typography": "clear product names, prices, labels, and readable details",
        "imagery": "real products, use cases, close-ups, lifestyle contexts",
        "interaction_model": "filters, variants, add-to-cart, reviews, comparison, checkout path",
        "copy_voice": "specific, benefit-led, concrete",
        "positive_terms": ["product", "shop", "cart", "price", "review", "category", "delivery", "checkout"],
        "anti_patterns": ["Do not use fake ecommerce grids without product detail, pricing logic, or trust signals."],
        "variant_directions": [
            "Product-led commerce page with strong hero, product detail, reviews, and shop path.",
            "Category discovery page with filters, collections, product cards, and trust proof.",
            "Brand commerce page with lifestyle imagery, featured products, and checkout-focused CTA.",
        ],
    },
}


_COMPOSITION_ARCHETYPES: dict[str, dict[str, str]] = {
    "split_product_proof": {
        "name": "Split Product Proof",
        "why": "Use when the user must compare a clear promise with an inspectable product or domain proof object.",
        "first_viewport": "Two-column hero is allowed only when the right side carries real proof: UI, code, map, product, case image, or workflow state.",
        "visual_objects": "product UI, code panel, domain image, proof card, status panel",
        "avoid": "Do not use a decorative empty card, generic analytics dashboard, or vague launch-path panel.",
    },
    "docs_terminal": {
        "name": "Docs And Terminal First",
        "why": "Developer tools need immediate proof that builders can run, inspect, and trust the product.",
        "first_viewport": "Navigation, direct technical H1, quickstart command, docs/GitHub CTAs, and a compact terminal/API/schema proof band.",
        "visual_objects": "terminal command, API route, schema table, SDK tabs, deploy status",
        "avoid": "Do not lead with stock people, vague AI copy, or a generic split card.",
    },
    "architecture_diagram": {
        "name": "Architecture Diagram Hero",
        "why": "Infrastructure products often need system shape before marketing claims feel credible.",
        "first_viewport": "Product promise paired with a full-width or asymmetric architecture diagram showing modules, flows, trust boundaries, and deploy path.",
        "visual_objects": "nodes, connectors, modules, request flow, data/auth boundaries",
        "avoid": "Do not draw meaningless boxes; every node must map to a real feature.",
    },
    "centered_statement": {
        "name": "Centered Statement Hero",
        "why": "Strong brands or simple offers can lead with one confident statement and proof visible below.",
        "first_viewport": "Centered or left-anchored headline over a quiet background system, with CTAs and the next proof section peeking into view.",
        "visual_objects": "texture, subtle product backdrop, proof strip, brand mark, secondary content hint",
        "avoid": "Do not leave the viewport empty, poster-like, or disconnected from the next section.",
    },
    "full_bleed_media": {
        "name": "Full-Bleed Media Hero",
        "why": "Physical, visual, luxury, fashion, construction, real estate, and story-led brands need place, material, or people to carry the first impression.",
        "first_viewport": "Full-bleed image, video, rendered scene, or strong visual background with text anchored directly on the media, not inside a floating card.",
        "visual_objects": "real photography, editorial image, material detail, environment, cinematic scene",
        "avoid": "Do not crop the meaningful subject away or hide the page behind a dark generic overlay.",
    },
    "immersive_scene": {
        "name": "Immersive Scene",
        "why": "Games, interactive products, and experiential launches should feel alive before explaining features.",
        "first_viewport": "Full-viewport scene or animated visual world with concise action copy, platform/action buttons, and visible gameplay or interaction cues.",
        "visual_objects": "3D/canvas scene, gameplay capture, character/world layer, live stats, motion cue",
        "avoid": "Do not use a corporate hero grid or explain the experience only with paragraphs.",
    },
    "dashboard_shell": {
        "name": "Dashboard Shell",
        "why": "Operational tools must show the actual work surface, not a landing page pretending to be an app.",
        "first_viewport": "Persistent nav, search/filter controls, metric strip, main queue/table/board, detail inspector, and action buttons.",
        "visual_objects": "sidebar, filters, table, cards, inspector, timeline, statuses",
        "avoid": "Do not use a marketing hero, decorative metric cards, or controls with no implied workflow.",
    },
    "map_or_route": {
        "name": "Map Or Route Hero",
        "why": "Logistics, field service, real estate, and local services depend on location, movement, ETA, and territory.",
        "first_viewport": "Map/route/work-area first, with jobs/listings/locations layered beside it and urgent state visible.",
        "visual_objects": "map, route lines, pins, ETA cards, territory bands, dispatch queue",
        "avoid": "Do not show unrelated dashboards when location is the real decision object.",
    },
    "search_first": {
        "name": "Search-First Marketplace",
        "why": "Marketplaces and directories must show discovery, filtering, trust, and listing quality quickly.",
        "first_viewport": "Search bar or finder, category filters, featured listings, trust/safety signals, and buyer/seller paths above the fold.",
        "visual_objects": "search input, filters, listing cards, map/category preview, rating/trust badges",
        "avoid": "Do not hide the inventory or make the page a one-sided brochure.",
    },
    "editorial_asymmetric": {
        "name": "Editorial Asymmetric",
        "why": "Premium, creative, portfolio, fashion, and construction pages often need a composed editorial rhythm instead of a default grid.",
        "first_viewport": "Asymmetric headline, image crop, metadata, and proof arranged like a designed editorial spread.",
        "visual_objects": "large crop, caption, metadata, proof strip, case teaser",
        "avoid": "Do not make all sections equal cards or repeat the same grid rhythm.",
    },
    "service_pathways": {
        "name": "Service Pathways",
        "why": "Government, education, healthcare, and service businesses must get people to the right task without friction.",
        "first_viewport": "Plain-language promise plus role/service task cards, search/help affordance, trust note, and clear next action.",
        "visual_objects": "task cards, role paths, service finder, forms, help status",
        "avoid": "Do not lead with vague brand storytelling when visitors need to complete a task.",
    },
    "impact_story": {
        "name": "Impact Story",
        "why": "NGOs and mission-led brands need human stakes, transparent proof, and a clear action path.",
        "first_viewport": "Human/field story, specific mission, impact metric, donation/volunteer CTA, and accountability proof.",
        "visual_objects": "community photo, impact metric, campaign progress, story card, action buttons",
        "avoid": "Do not use manipulative tragedy imagery or vague impact claims.",
    },
    "product_grid": {
        "name": "Product Or Collection Grid",
        "why": "Commerce and fashion need desire, comparison, product detail, and purchase/inquiry clarity.",
        "first_viewport": "Collection/product story with featured items, material/detail imagery, category filters, price/inquiry cues, and shop path.",
        "visual_objects": "product cards, lookbook image, detail crop, price/status labels, collection nav",
        "avoid": "Do not use fake product grids without detail, pricing logic, or trust signals.",
    },
    "workflow_stage": {
        "name": "Workflow Stage",
        "why": "AI SaaS and automation tools must show before, during, after, and human control rather than magic.",
        "first_viewport": "Problem state, AI/action state, approval/audit state, and outcome are staged as one product workflow.",
        "visual_objects": "prompt, generated result, approval queue, integration state, audit trail",
        "avoid": "Do not rely on one chat bubble or abstract AI glow as the proof.",
    },
}


_COMPOSITION_BY_INDUSTRY: dict[str, list[str]] = {
    "developer_tools": ["docs_terminal", "architecture_diagram", "split_product_proof", "centered_statement"],
    "ai_saas": ["workflow_stage", "architecture_diagram", "split_product_proof", "centered_statement"],
    "luxury": ["full_bleed_media", "editorial_asymmetric", "centered_statement"],
    "fashion": ["full_bleed_media", "product_grid", "editorial_asymmetric"],
    "gaming": ["immersive_scene", "full_bleed_media", "centered_statement"],
    "marketplace": ["search_first", "product_grid", "split_product_proof"],
    "energy_climate": ["immersive_scene", "architecture_diagram", "split_product_proof", "dashboard_shell"],
    "logistics": ["map_or_route", "dashboard_shell", "split_product_proof"],
    "field_service": ["map_or_route", "dashboard_shell", "split_product_proof"],
    "construction": ["full_bleed_media", "editorial_asymmetric", "split_product_proof"],
    "real_estate": ["full_bleed_media", "map_or_route", "search_first"],
    "government": ["service_pathways", "search_first", "centered_statement"],
    "education": ["service_pathways", "dashboard_shell", "editorial_asymmetric"],
    "healthcare": ["service_pathways", "centered_statement", "split_product_proof"],
    "ngo": ["impact_story", "full_bleed_media", "service_pathways"],
    "portfolio": ["editorial_asymmetric", "full_bleed_media", "centered_statement"],
    "creative": ["editorial_asymmetric", "full_bleed_media", "centered_statement"],
    "fintech": ["workflow_stage", "split_product_proof", "centered_statement"],
    "finance": ["workflow_stage", "split_product_proof", "dashboard_shell"],
    "restaurant": ["full_bleed_media", "service_pathways", "product_grid"],
    "commerce": ["product_grid", "full_bleed_media", "search_first"],
    "general_business": ["centered_statement", "service_pathways", "split_product_proof"],
}


_SURFACE_COMPOSITION_DEFAULTS: dict[str, list[str]] = {
    "operational_dashboard": ["dashboard_shell", "map_or_route", "workflow_stage"],
    "mobile_app": ["workflow_stage", "service_pathways", "centered_statement"],
    "product_app": ["workflow_stage", "dashboard_shell", "split_product_proof"],
    "marketing_website": ["centered_statement", "full_bleed_media", "editorial_asymmetric", "split_product_proof"],
}


_EXPERIENCE_MODES: dict[str, dict[str, Any]] = {
    "static_polished": {
        "name": "Static Polished",
        "intent": "Ship a refined, fast, content-led interface where hierarchy, copy, imagery, and spacing carry the experience.",
        "when_to_use": "Default for serious business, public-service, finance, healthcare, and documentation pages where speed and clarity matter more than spectacle.",
        "libraries": [],
        "implementation": ["semantic HTML", "responsive CSS", "image optimization", "accessible focus states"],
        "rules": [
            "Do not add motion just because it is available.",
            "Use restraint, clear hierarchy, strong copy, and high-quality assets.",
            "Prioritize Core Web Vitals and accessibility.",
        ],
        "verification": ["browser screenshots", "responsive layout audit", "accessibility semantics", "dead-button check"],
        "rejection_rules": ["Reject if the page feels like a scaffold, has blank hero space, or uses decorative filler as proof."],
    },
    "editorial_luxury": {
        "name": "Editorial Luxury",
        "intent": "Create a premium, art-directed experience with restraint, asymmetry, tactile imagery, and slow confidence.",
        "when_to_use": "Luxury, fashion, portfolio, creative, hospitality, architecture, and visual brands.",
        "libraries": ["Framer Motion optional", "CSS transitions"],
        "implementation": ["full-bleed media", "editorial grid", "material/detail imagery", "subtle reveal transitions"],
        "rules": [
            "Motion should feel slow, intentional, and expensive, not busy.",
            "Never bury text inside cards when the hero should be media-led.",
            "Use imagery, texture, and type rhythm as the main signal.",
        ],
        "verification": ["screenshot composition audit", "image rendering check", "reduced-motion fallback", "viewport scale check"],
        "rejection_rules": ["Reject if it looks like generic SaaS, ecommerce template clutter, or loud discount marketing."],
    },
    "cinematic_scroll": {
        "name": "Cinematic Scroll",
        "intent": "Use scroll progression, layered sections, pinned moments, and reveal timing to tell a product or brand story.",
        "when_to_use": "Launch pages, campaigns, construction/project stories, high-end product stories, AI product demos, and immersive marketing pages.",
        "libraries": ["GSAP optional", "Framer Motion", "CSS scroll-driven animations where supported"],
        "implementation": ["scroll sections", "pinned scenes", "layered media", "progressive narrative", "reduced-motion path"],
        "rules": [
            "Scroll effects must explain progression, not hide content.",
            "Always provide a reduced-motion alternative.",
            "Avoid scroll-jacking that blocks normal reading or keyboard navigation.",
        ],
        "verification": ["desktop/mobile screenshots across scroll positions", "reduced-motion fallback", "performance budget", "no horizontal overflow"],
        "rejection_rules": ["Reject if animation causes clipped text, unreadable sections, or huge blank gaps."],
    },
    "parallax_story": {
        "name": "Parallax Story",
        "intent": "Use depth, foreground/background motion, and anchored content to create visual drama without requiring full 3D.",
        "when_to_use": "Travel, real estate, construction, fashion, portfolio, NGO field stories, and visual company sites.",
        "libraries": ["Framer Motion optional", "CSS transforms", "IntersectionObserver"],
        "implementation": ["parallax layers", "foreground subject", "background media", "section depth", "reduced-motion path"],
        "rules": [
            "Parallax must preserve readability at every scroll position.",
            "Keep layer count modest for performance.",
            "Disable or simplify parallax for reduced-motion users.",
        ],
        "verification": ["scroll screenshot audit", "performance budget", "reduced-motion fallback", "mobile no-overlap check"],
        "rejection_rules": ["Reject if parallax is decorative noise or text overlaps media."],
    },
    "interactive_3d": {
        "name": "Interactive 3D",
        "intent": "Use a real 3D scene as the primary product/brand signal, with interaction and motion that reveals meaning.",
        "when_to_use": "3D websites, product configurators, technical products, games, architecture, spatial portfolios, and immersive launch pages.",
        "libraries": ["Three.js", "@react-three/fiber", "@react-three/drei", "Framer Motion optional"],
        "implementation": ["full-bleed canvas", "camera/framing", "lighting", "interactive object states", "fallback image/static path"],
        "rules": [
            "The 3D canvas must be visible, nonblank, framed, and meaningful.",
            "Do not put the primary 3D scene inside a decorative card.",
            "Include reduced-motion and non-WebGL fallback content.",
            "Keep geometry/textures performant and avoid blocking page content.",
        ],
        "verification": ["Playwright screenshot", "canvas-pixel/nonblank check", "desktop/mobile framing check", "interaction smoke", "performance budget"],
        "rejection_rules": ["Reject if canvas is blank, tiny, hidden, decorative only, or breaks mobile layout."],
    },
    "immersive_scene": {
        "name": "Immersive Scene",
        "intent": "Make the first viewport feel like a world, environment, or live state before conventional sections begin.",
        "when_to_use": "Games, entertainment, AI demos, product launches, campaigns, spatial/creative portfolios, and high-impact brand pages.",
        "libraries": ["Three.js optional", "Canvas/WebGL optional", "Framer Motion", "GSAP optional"],
        "implementation": ["full-viewport scene", "layered media", "ambient motion", "clear CTA overlay", "fallback scene poster"],
        "rules": [
            "The scene must carry the product/domain meaning, not just atmosphere.",
            "Keep a clear CTA and next section visible or reachable.",
            "Do not let visual spectacle harm text readability.",
        ],
        "verification": ["screenshot and scene framing", "motion/reduced-motion check", "asset rendering", "performance budget"],
        "rejection_rules": ["Reject if the scene is generic, dark/blurred, or hides the actual offer."],
    },
    "game_like": {
        "name": "Game-Like",
        "intent": "Use gameplay, progression, stats, world UI, inventory, or player identity as the design language.",
        "when_to_use": "Gaming sites, gamified products, esports, quests, communities, and interactive learning products.",
        "libraries": ["Three.js optional", "Canvas optional", "Framer Motion", "Howler optional for games only"],
        "implementation": ["gameplay/media first", "mode cards", "progression loop", "stats", "join/play action"],
        "rules": [
            "Show gameplay or game-system proof quickly.",
            "Use vivid motion, but preserve readable UI labels.",
            "Do not make it look like a corporate SaaS dashboard.",
        ],
        "verification": ["screenshot scene check", "interaction smoke", "asset rendering", "performance budget"],
        "rejection_rules": ["Reject if it lacks gameplay/world/progression signals or reads like enterprise software."],
    },
    "product_demo_motion": {
        "name": "Product Demo Motion",
        "intent": "Show how the product changes state: before, action, approval, result, and proof.",
        "when_to_use": "Developer tools, AI SaaS, fintech, productivity, automation, and technical product pages.",
        "libraries": ["Framer Motion", "CSS transitions", "Lottie optional only when asset-backed"],
        "implementation": ["stateful demo panel", "tabs", "command/result flow", "status transitions", "copyable examples"],
        "rules": [
            "Motion must clarify product workflow and state change.",
            "Use code/product proof rather than stock illustration.",
            "Keep animations interruptible and accessible.",
        ],
        "verification": ["browser screenshot", "interaction smoke", "reduced-motion fallback", "dead-button check"],
        "rejection_rules": ["Reject if motion is just decorative floating cards or fake dashboard numbers."],
    },
    "dashboard_operational": {
        "name": "Dashboard Operational",
        "intent": "Create a work surface for repeated use with dense information, fast decisions, and clear actions.",
        "when_to_use": "Dashboards, portals, admin systems, command centers, internal tools, and management apps.",
        "libraries": ["CSS transitions", "Framer Motion only for drawers/toasts"],
        "implementation": ["application shell", "tables/boards", "filters", "detail inspector", "modals/drawers", "empty/error/loading states"],
        "rules": [
            "Avoid cinematic or decorative motion in daily-use tools.",
            "Every control must imply a real action.",
            "Preserve density, alignment, keyboard/focus paths, and status clarity.",
        ],
        "verification": ["browser screenshot", "dead-button check", "accessibility labels", "responsive operational layout"],
        "rejection_rules": ["Reject if it looks like a marketing landing page or has decorative cards without workflow."],
    },
    "data_viz_motion": {
        "name": "Data Visualization Motion",
        "intent": "Use animated charts/maps/timelines to make data, trends, or operational state understandable.",
        "when_to_use": "Analytics, finance, logistics, dashboards, market intelligence, climate/impact reports, and monitoring products.",
        "libraries": ["Recharts", "D3 optional", "Framer Motion optional"],
        "implementation": ["charts", "maps", "timeline", "filters", "legend", "drill-down states"],
        "rules": [
            "Animation should support data comprehension, not obscure values.",
            "Use accessible labels, legends, and tabular alternatives where possible.",
            "Avoid fake meaningless charts.",
        ],
        "verification": ["chart rendering check", "label/legend check", "browser screenshot", "performance budget"],
        "rejection_rules": ["Reject if charts are decorative, unlabeled, or unrelated to the domain."],
    },
    "accessible_public_service": {
        "name": "Accessible Public Service",
        "intent": "Make task completion, readability, trust, and accessibility the design experience.",
        "when_to_use": "Government, education, healthcare, NGO services, civic forms, and public-facing support tools.",
        "libraries": [],
        "implementation": ["plain-language task cards", "forms", "service finder", "status/help", "accessible contrast and focus"],
        "rules": [
            "Do not use flashy animation where users need clarity.",
            "Prioritize keyboard navigation, contrast, readable type, and plain-language action paths.",
            "Use motion only for essential feedback.",
        ],
        "verification": ["accessibility semantics", "keyboard/focus path", "browser screenshot", "dead-button check"],
        "rejection_rules": ["Reject if visual polish makes public tasks harder to complete."],
    },
}


_EXPERIENCE_BY_INDUSTRY: dict[str, list[str]] = {
    "developer_tools": ["product_demo_motion", "static_polished", "interactive_3d"],
    "ai_saas": ["product_demo_motion", "cinematic_scroll", "interactive_3d"],
    "luxury": ["editorial_luxury", "cinematic_scroll", "parallax_story"],
    "fashion": ["editorial_luxury", "parallax_story", "cinematic_scroll"],
    "gaming": ["game_like", "immersive_scene", "interactive_3d"],
    "marketplace": ["static_polished", "product_demo_motion", "data_viz_motion"],
    "energy_climate": ["data_viz_motion", "immersive_scene", "product_demo_motion", "parallax_story"],
    "logistics": ["data_viz_motion", "dashboard_operational", "product_demo_motion"],
    "field_service": ["dashboard_operational", "data_viz_motion", "product_demo_motion"],
    "construction": ["cinematic_scroll", "parallax_story", "editorial_luxury"],
    "real_estate": ["parallax_story", "cinematic_scroll", "interactive_3d"],
    "government": ["accessible_public_service", "static_polished"],
    "education": ["accessible_public_service", "dashboard_operational", "static_polished"],
    "healthcare": ["accessible_public_service", "static_polished", "dashboard_operational"],
    "ngo": ["accessible_public_service", "parallax_story", "cinematic_scroll"],
    "portfolio": ["editorial_luxury", "parallax_story", "interactive_3d"],
    "creative": ["editorial_luxury", "cinematic_scroll", "interactive_3d"],
    "fintech": ["product_demo_motion", "static_polished", "data_viz_motion"],
    "finance": ["data_viz_motion", "dashboard_operational", "static_polished"],
    "restaurant": ["parallax_story", "static_polished", "cinematic_scroll"],
    "commerce": ["editorial_luxury", "static_polished", "product_demo_motion"],
    "general_business": ["static_polished", "product_demo_motion", "cinematic_scroll"],
}


_SURFACE_EXPERIENCE_DEFAULTS: dict[str, list[str]] = {
    "operational_dashboard": ["dashboard_operational", "data_viz_motion", "product_demo_motion"],
    "mobile_app": ["product_demo_motion", "static_polished"],
    "product_app": ["product_demo_motion", "dashboard_operational", "static_polished"],
    "marketing_website": ["static_polished", "cinematic_scroll", "parallax_story"],
}


def _experience_strategy(industry: str, surface: str, route: str, request_text: str, composition: dict[str, Any]) -> dict[str, Any]:
    option_ids = _experience_option_ids(industry, surface, request_text, composition)
    primary_id = option_ids[0] if option_ids else "static_polished"
    options = [_experience_mode(item) for item in option_ids]
    primary = options[0] if options else _experience_mode(primary_id)
    governance = [
        "Pick interaction libraries from the mode; do not add heavy animation libraries unless the mode benefits from them.",
        "Every motion/3D/parallax effect must have a user-facing purpose and a reduced-motion or fallback path.",
        "Friday implementation must verify screenshots, responsiveness, interaction smoke, and performance before claiming visual quality.",
    ]
    if primary_id in {"interactive_3d", "immersive_scene", "game_like"}:
        governance.append("Primary immersive scenes must be full-bleed or unframed, nonblank, correctly framed, and meaningful.")
    if surface == "operational_dashboard":
        governance.append("Operational surfaces should prefer clarity and fast action over spectacle.")
    return {
        "primary": primary,
        "allowed_modes": options,
        "rules": governance,
        "route": route,
    }


def _experience_option_ids(industry: str, surface: str, request_text: str, composition: dict[str, Any]) -> list[str]:
    intent_text = _strip_negative_design_constraints(request_text)
    requested: list[str] = []
    if _contains_any_intent(intent_text, ("3d", "three.js", "webgl", "react-three", "react three", "interactive 3d", "spatial")):
        requested.append("interactive_3d")
    if _contains_any_intent(intent_text, ("parallax", "scroll animation", "scroll-driven", "scroll driven", "pinned scroll", "scroll story")):
        requested.append("parallax_story" if "parallax" in intent_text else "cinematic_scroll")
    if _contains_any_intent(intent_text, ("immersive", "scene", "world", "cinematic", "hero background", "animated background")):
        requested.append("immersive_scene" if "3d" in intent_text or "world" in intent_text else "cinematic_scroll")
    if _contains_any_intent(intent_text, ("game", "gaming", "esports", "quest", "arcade", "player")):
        requested.append("game_like")
    if _contains_any_intent(intent_text, ("motion", "animation", "animated", "microinteraction", "micro-interaction")):
        requested.append("product_demo_motion")
    if _contains_any_intent(intent_text, ("chart", "analytics", "data visualization", "data viz", "map", "timeline")):
        requested.append("data_viz_motion")

    primary_composition = composition.get("primary") if isinstance(composition.get("primary"), dict) else {}
    composition_id = str(primary_composition.get("id") or "")
    if composition_id == "immersive_scene":
        requested.append("immersive_scene")
    if composition_id == "dashboard_shell":
        requested.append("dashboard_operational")
    if composition_id == "map_or_route":
        requested.append("data_viz_motion")
    if composition_id in {"full_bleed_media", "editorial_asymmetric"} and industry in {"luxury", "fashion", "portfolio", "creative"}:
        requested.append("editorial_luxury")
    if composition_id == "workflow_stage":
        requested.append("product_demo_motion")

    industry_options = list(_EXPERIENCE_BY_INDUSTRY.get(industry) or [])
    surface_options = list(_SURFACE_EXPERIENCE_DEFAULTS.get(surface) or [])
    return _dedupe_strings([*requested, *industry_options, *surface_options])[:5]


def _experience_mode(mode_id: str) -> dict[str, Any]:
    entry = _EXPERIENCE_MODES.get(mode_id) or _EXPERIENCE_MODES["static_polished"]
    return {"id": mode_id if mode_id in _EXPERIENCE_MODES else "static_polished", **entry}


def _composition_strategy(industry: str, surface: str, route: str, request_text: str) -> dict[str, Any]:
    option_ids = _composition_option_ids(industry, surface, request_text)
    primary_id = option_ids[0] if option_ids else "centered_statement"
    options = [_composition_archetype(item) for item in option_ids]
    primary = options[0] if options else _composition_archetype(primary_id)
    rules = [
        "Choose the composition before visual styling; colors and cards must not be the main differentiator.",
        "Do not default to a left-text/right-card split hero unless Split Product Proof is the selected archetype.",
        "Each generated variant must change the first viewport structure, not just copy, palette, or card styling.",
        "If the archetype uses media or a scene, the media must carry real product/domain meaning.",
    ]
    if surface == "operational_dashboard":
        rules.append("For dashboards, first viewport must be an application shell with workflow controls, not a marketing hero.")
    if industry in {"luxury", "fashion", "gaming", "construction", "real_estate", "energy_climate"}:
        rules.append("For visual/physical brands, use image, material, scene, or place as the first-viewport evidence.")
    return {
        "primary": primary,
        "allowed_archetypes": options,
        "rules": rules,
        "route": route,
    }


def _composition_option_ids(industry: str, surface: str, request_text: str) -> list[str]:
    if surface == "operational_dashboard":
        base = list(_SURFACE_COMPOSITION_DEFAULTS["operational_dashboard"])
        if industry in {"logistics", "field_service", "real_estate"}:
            base.insert(0, "map_or_route")
        return _dedupe_strings(base)

    intent_text = _strip_negative_design_constraints(request_text)
    requested: list[str] = []
    if _contains_any_intent(intent_text, ("full bleed", "full-bleed", "background image", "hero background", "photo", "cinematic")):
        requested.append("full_bleed_media")
    if _contains_any_intent(intent_text, ("3d", "three.js", "interactive scene", "gameplay", "immersive")):
        requested.append("immersive_scene")
    if _contains_any_intent(intent_text, ("docs", "cli", "sdk", "api", "terminal", "quickstart")):
        requested.append("docs_terminal")
    if industry in {"marketplace", "commerce", "real_estate"} and _contains_any_intent(intent_text, ("search", "listing", "directory", "marketplace", "booking")):
        requested.append("search_first")
    if industry in {"logistics", "field_service", "real_estate"} and _contains_any_intent(intent_text, ("map", "route", "fleet", "dispatch", "location")):
        requested.append("map_or_route")
    if _contains_any_intent(intent_text, ("workflow", "automation", "approval", "agent trace")):
        requested.append("workflow_stage")

    industry_options = list(_COMPOSITION_BY_INDUSTRY.get(industry) or [])
    surface_options = list(_SURFACE_COMPOSITION_DEFAULTS.get(surface) or [])
    return _dedupe_strings([*requested, *industry_options, *surface_options])[:5]


def _strip_negative_design_constraints(text: str) -> str:
    """Remove common "do not/no X" spans so forbidden words do not become positive design intent."""

    cleaned = f" {str(text or '').lower()} "
    patterns = (
        r"\b(?:no|not|never)\s+[^.;,\n]{0,120}",
        r"\b(?:do\s+not|don't|dont)\s+[^.;,\n]{0,120}",
        r"\bwithout\s+[^.;,\n]{0,90}",
    )
    for pattern in patterns:
        cleaned = re.sub(pattern, " ", cleaned)
    return cleaned


def _contains_any_intent(text: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        if " " in term or "-" in term or "." in term:
            if term in text:
                return True
            continue
        if re.search(rf"\b{re.escape(term)}\b", text):
            return True
    return False


def _composition_archetype(archetype_id: str) -> dict[str, str]:
    entry = _COMPOSITION_ARCHETYPES.get(archetype_id) or _COMPOSITION_ARCHETYPES["centered_statement"]
    return {"id": archetype_id if archetype_id in _COMPOSITION_ARCHETYPES else "centered_statement", **entry}


def _taxonomy_entry(industry: str) -> dict[str, Any]:
    entry = _DESIGN_TAXONOMY.get(industry) or _GENERAL_STRATEGY
    merged = {**_GENERAL_STRATEGY, **entry}
    return merged


def _strategy_for(industry: str, surface: str) -> dict[str, str]:
    if surface == "operational_dashboard":
        industry_entry = _taxonomy_entry(industry)
        return {
            **_DASHBOARD_STRATEGY,
            "message": industry_entry["message"],
            "emotional_feel": f"{industry_entry['emotional_feel']}; calm enough for repeated daily use",
            "copy_voice": f"{industry_entry['copy_voice']}; specific operational language from the domain",
        }
    return dict(_taxonomy_entry(industry))


def _variant_directions(industry: str, surface: str, route: str) -> list[str]:
    if surface == "operational_dashboard":
        industry_entry = _taxonomy_entry(industry)
        return [
            "Dense command cockpit with metric rail, queue table, side detail panel, and action drawer.",
            "Role-based workspace with tabs, live status cards, timeline, and exception handling.",
            f"Board-and-inspector layout tuned for {industry_entry['message'].lower()} with filters, grouped work states, and approval controls.",
        ]
    if industry == "construction":
        base = [
            "Editorial project authority: split hero with infrastructure imagery, safety/proof band, and capability cards.",
            "Portfolio-led construction story: case-study grid, market sectors, regional proof, and inquiry path.",
            "Procurement-ready capabilities page: services, delivery process, risk/safety commitments, and contact routes.",
        ]
        if route == "contact":
            base[0] = "Inquiry-first contact page with regional routes, project type selector, response promise, and trust/privacy note."
        return base
    if industry == "healthcare":
        return [
            "Warm trust-led page with care/team cues, service paths, privacy reassurance, and clear request flow.",
            "Clinical operations layout with intake steps, response expectations, service cards, and contact options.",
            "Patient/admin split journey with role cards, proof signals, and low-friction form path.",
        ]
    if industry == "restaurant":
        return [
            "Service-floor energy page with busy-hour imagery, shift proof, quick actions, and booking/contact path.",
            "Operations-first layout with queue/ticket pressure, staff handoff, inventory cues, and outcomes.",
            "Hospitality brand page with menu/service narrative, customer proof, and direct inquiry path.",
        ]
    return list(_taxonomy_entry(industry).get("variant_directions") or _GENERAL_STRATEGY["variant_directions"])


def _anti_patterns(industry: str, surface: str) -> list[str]:
    patterns = [
        "Do not use generic SaaS dashboard imagery for a non-SaaS company website.",
        "Do not use huge empty hero sections or headings that consume the viewport.",
        "Do not repeat page labels as section titles.",
        "Do not use placeholder copy, raw prompts, debug labels, or Friday proof language.",
        "Do not rely on only beige/cream cards unless the domain truly calls for it.",
    ]
    patterns.extend(_taxonomy_entry(industry).get("anti_patterns") or [])
    if surface == "operational_dashboard":
        patterns.append("Do not make an app dashboard look like a marketing landing page.")
    return _dedupe_strings(patterns)


def _quality_bar(surface: str) -> list[str]:
    if surface == "operational_dashboard":
        return [
            "Every visible control should imply a real action.",
            "The main screen must support repeated daily use, not just presentation.",
            "Use compact, scannable hierarchy and preserve whitespace for work, not decoration.",
        ]
    return [
        "The first viewport must immediately communicate the specific brand/domain.",
        "Every page must contain more than a hero: proof, services/features, trust, and next action.",
        "Links and forms must have real destinations or preview-safe behavior.",
        "Friday may adapt Stitch scale to professional production proportions.",
    ]


def _positive_terms(industry: str, surface: str) -> list[str]:
    terms = list(_taxonomy_entry(industry).get("positive_terms") or _GENERAL_STRATEGY["positive_terms"])
    if surface == "operational_dashboard":
        terms.extend(["queue", "status", "owner", "priority", "approval", "filter", "action", "timeline"])
    return _dedupe_strings(terms)


def _layout_terms(surface: str) -> list[str]:
    if surface == "operational_dashboard":
        return ["table", "aside", "nav", "button", "aria-", "role=", "filter", "tab"]
    return ["section", "article", "form", "nav", "img", "figure", "grid"]


def _looks_like_plain_saas(raw: str, industry: str) -> bool:
    if industry in {"general_business", "finance", "fintech", "developer_tools", "ai_saas"}:
        return False
    saaS_terms = ("workflow automation", "command workspace", "launch path", "dashboard", "smarter operations", "business day")
    return sum(1 for term in saaS_terms if term in raw) >= 2


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = _clean(value)
        if not cleaned or cleaned.lower() in seen:
            continue
        seen.add(cleaned.lower())
        result.append(cleaned)
    return result


def _dedupe_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for finding in findings:
        key = f"{finding.get('id')}::{finding.get('message')}"
        if key in seen:
            continue
        seen.add(key)
        result.append(finding)
    return result


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()

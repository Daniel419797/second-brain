from core import design_director


def test_design_taxonomy_covers_named_archetypes():
    cases = [
        ("luxury", "Build a luxury jewelry website with private concierge appointments."),
        ("fintech", "Build a fintech landing page for a digital wallet and secure transfers."),
        ("gaming", "Build a gaming website for an esports quest arena."),
        ("developer_tools", "Build a developer tool website for an API platform with SDK docs and CLI."),
        ("logistics", "Build a logistics dashboard for fleet, warehouse, freight, ETA, and delivery routing."),
        ("education", "Build an education website for a university campus admissions office."),
        ("ngo", "Build an NGO website for donations, volunteers, community programs, and impact reports."),
        ("fashion", "Build a fashion ecommerce lookbook for a streetwear apparel collection."),
        ("portfolio", "Build a portfolio website for a photographer with case studies and contact."),
        ("government", "Build a government public service website for permits and resident forms."),
        ("ai_saas", "Build an AI SaaS website for an AI agent copilot automation platform."),
        ("marketplace", "Build a marketplace website for buyers, sellers, listings, vendors, and bookings."),
        ("energy_climate", "Build a climate-tech website for microgrid, solar, battery, demand spike, and outage-risk monitoring."),
    ]

    for expected, request in cases:
        strategy = design_director.design_strategy(request, "Demo", stack={"stack": "nextjs"})

        assert strategy["industry"] == expected
        assert strategy["message"]
        assert strategy["emotional_feel"]
        assert strategy["visual_language"]
        assert strategy["copy_voice"]
        assert strategy["composition"]["primary"]["id"]
        assert len(strategy["composition"]["allowed_archetypes"]) >= 3
        assert "Composition direction:" in strategy["prompt_block"]
        assert strategy["experience"]["primary"]["id"]
        assert len(strategy["experience"]["allowed_modes"]) >= 2
        assert "Experience mode:" in strategy["prompt_block"]
        assert strategy["anti_patterns"]
        assert len(strategy["variant_directions"]) >= 3
        assert "Message to communicate" in strategy["prompt_block"]
        assert "Emotional feel" in strategy["prompt_block"]


def test_operational_dashboard_keeps_operator_cockpit_but_preserves_domain_message():
    strategy = design_director.design_strategy(
        "Build a logistics dashboard for fleet routing, warehouse capacity, freight delays, delivery ETAs, and exception handling.",
        "FleetOps",
        stack={"stack": "nextjs"},
    )

    assert strategy["surface"] == "operational_dashboard"
    assert strategy["industry"] == "logistics"
    assert "operator cockpit" in strategy["direction"]
    assert "Movement, capacity, timing" in strategy["message"]
    assert "calm enough for repeated daily use" in strategy["emotional_feel"]


def test_taxonomy_rejects_generic_saas_copy_for_non_saas_domains():
    strategy = design_director.design_strategy(
        "Build a luxury website for a private jewelry atelier.",
        "Atelier Demo",
        stack={"stack": "nextjs"},
    )
    findings = design_director.style_findings(
        "<main><h1>Atelier Demo Command Workspace</h1><p>Scale your service business through smarter operations with a launch path.</p></main>",
        "Atelier Demo Command Workspace Scale your service business through smarter operations with a launch path.",
        "Build a luxury website for a private jewelry atelier.",
        strategy,
    )

    assert any(item["id"] == "samey_saas_visual_grammar" for item in findings)
    assert any(item["id"] == "generic_design_copy" for item in findings)


def test_taxonomy_scores_domain_specific_ai_saas_without_punishing_workflow_language():
    strategy = design_director.design_strategy(
        "Build an AI SaaS website for an AI agent copilot automation platform.",
        "FlowPilot AI",
        stack={"stack": "nextjs"},
    )
    html = """
    <main>
      <section><h1>FlowPilot AI</h1><p>AI agents automate approval workflows with audit trails, integrations, prompts, and human control.</p></section>
      <section><article>Agent trace</article><article>Integration controls</article><article>Approval review</article></section>
    </main>
    """

    assert strategy["industry"] == "ai_saas"
    assert design_director.art_direction_score(html, "AI agents automate approval workflows with audit trails integrations prompts and human control", "AI SaaS automation platform", strategy) >= 7
    assert not any(item["id"] == "samey_saas_visual_grammar" for item in design_director.style_findings(html, html, "AI SaaS automation platform", strategy))


def test_nexus_forge_landing_page_uses_developer_tools_marketing_strategy():
    request = """
    Build a polished production-quality landing page for Nexus Forge as a fresh Next.js web-app project.
    Nexus Forge is an open-source, self-hosted no-code Backend-as-a-Service with WebSockets,
    API keys, plugin marketplace, AI integrations, Web3 modules, and x402 API monetization.
    The design should feel premium, readable, and product-led.
    """

    strategy = design_director.design_strategy(request, "Nexus Forge", stack={"stack": "nextjs"})

    assert strategy["surface"] == "marketing_website"
    assert strategy["industry"] == "developer_tools"
    assert "developer" in strategy["direction"].lower()
    assert "luxury" not in strategy["prompt_block"].lower()


def test_developer_tool_design_rejects_incoherent_copy_and_stock_portrait():
    request = "Build a landing page for Nexus Forge, an open-source backend-as-a-service developer tool with SDK docs and CLI."
    strategy = design_director.design_strategy(request, "Nexus Forge", stack={"stack": "nextjs"})
    html = """
    <main>
      <section>
        <h1>The backend for the of indie hackers. next generation</h1>
        <p>Open-source self-hosted backend-as-a-service for API, SDK, CLI, docs, auth, and database workflows.</p>
        <img alt="Contributor portrait" src="/friday-assets/person.png" />
      </section>
    </main>
    """
    findings = design_director.style_findings(
        html,
        "The backend for the of indie hackers. next generation Open-source self-hosted backend-as-a-service for API SDK CLI docs auth database workflows.",
        request,
        strategy,
    )
    ids = {item["id"] for item in findings}

    assert "incoherent_visible_copy" in ids
    assert "stock_person_hero_for_developer_tool" in ids


def test_composition_archetypes_change_by_domain_and_surface():
    developer = design_director.design_strategy(
        "Build a landing page for Nexus Forge, an open-source backend-as-a-service developer tool with CLI, SDK docs, API routes, and Web3 modules.",
        "Nexus Forge",
        stack={"stack": "nextjs"},
    )
    fashion = design_director.design_strategy(
        "Build a fashion landing page for a streetwear collection with campaign photography and a lookbook.",
        "Aster Row",
        stack={"stack": "nextjs"},
    )
    dashboard = design_director.design_strategy(
        "Build a logistics dashboard for fleet dispatch, ETA risks, route maps, warehouse capacity, and exception handling.",
        "FleetOps",
        stack={"stack": "nextjs"},
    )

    assert developer["composition"]["primary"]["id"] == "docs_terminal"
    assert any(item["id"] == "architecture_diagram" for item in developer["composition"]["allowed_archetypes"])
    assert fashion["composition"]["primary"]["id"] == "full_bleed_media"
    assert dashboard["composition"]["primary"]["id"] == "map_or_route"
    assert "Do not default to a left-text/right-card split hero" in developer["prompt_block"]


def test_experience_modes_select_3d_scroll_game_and_dashboard_contracts():
    three_d = design_director.design_strategy(
        "Build a 3D interactive WebGL landing page with a full-bleed scene for a spatial AI product.",
        "SceneOS",
        stack={"stack": "nextjs"},
    )
    parallax = design_director.design_strategy(
        "Build a cinematic scroll animation and parallax website for a real estate development.",
        "Harbor Place",
        stack={"stack": "nextjs"},
    )
    game = design_director.design_strategy(
        "Build a gaming website for an esports quest arena with player stats and game-like motion.",
        "Quest Arena",
        stack={"stack": "nextjs"},
    )
    dashboard = design_director.design_strategy(
        "Build an operations dashboard for clinic triage and urgent approvals.",
        "CareFlow",
        stack={"stack": "nextjs"},
    )

    assert three_d["experience"]["primary"]["id"] == "interactive_3d"
    assert "Three.js" in three_d["prompt_block"]
    assert parallax["experience"]["primary"]["id"] == "parallax_story"
    assert game["experience"]["primary"]["id"] == "game_like"
    assert dashboard["experience"]["primary"]["id"] == "dashboard_operational"
    assert "reduced-motion" in three_d["prompt_block"]


def test_energy_responsive_website_is_not_misclassified_as_mobile_or_developer_tools():
    request = (
        "Build a production-quality 4-page Next.js marketing website for KineticGrid Energy, "
        "a B2B climate-tech company that helps commercial buildings monitor microgrids, solar, "
        "batteries, demand spikes, and outage risk. It must be mobile responsive."
    )

    strategy = design_director.design_strategy(request, "KineticGrid Energy", stack={"stack": "nextjs"})

    assert strategy["surface"] == "marketing_website"
    assert strategy["industry"] == "energy_climate"
    assert strategy["composition"]["primary"]["id"] == "immersive_scene"
    prompt = strategy["prompt_block"].lower()
    assert "microgrid" in prompt
    assert "battery" in prompt
    assert "developer-first" not in prompt
    assert "mobile_app" not in prompt


def test_premium_climate_property_risk_is_not_misclassified_as_luxury():
    request = (
        "Build a production-quality landing page for EmberVault, a premium climate-risk "
        "intelligence platform for commercial property owners and real estate teams covering "
        "wildfire, flood, heat, insurance risk, tenant impact, and portfolio risk."
    )

    strategy = design_director.design_strategy(request, "EmberVault", stack={"stack": "nextjs"})

    assert strategy["surface"] == "marketing_website"
    assert strategy["industry"] == "energy_climate"
    prompt = strategy["prompt_block"].lower()
    assert "climate" in prompt
    assert "property" in prompt
    assert "luxury" not in prompt
    assert "concierge" not in prompt


def test_energy_design_rejects_construction_and_developer_tool_drift():
    request = "Build a climate-tech website for KineticGrid Energy with microgrid, solar, battery, demand, outage, and building telemetry."
    strategy = design_director.design_strategy(request, "KineticGrid Energy", stack={"stack": "nextjs"})
    visible = (
        "KineticGrid Energy construction services contractor handover jobsite. "
        "Self-hosted backend with CLI install and Web3 modules."
    )

    findings = design_director.style_findings("<main>" + visible + "</main>", visible, request, strategy)
    ids = {item["id"] for item in findings}

    assert "wrong_domain_art_direction" in ids
    assert "weak_industry_art_direction" in ids

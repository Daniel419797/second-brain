from core import coding_workflow, project_scaffolds, web_project_contract
from core import production_coding_autonomy, production_readiness


def _package(files):
    import json

    return json.loads(files["package.json"])


def test_web_app_keyword_generates_nextjs_app_router_files():
    stack = project_scaffolds.detect_stack("build a web-app for client invoices")
    files = project_scaffolds.files_for_stack(stack, "InvoicePilot", "build a web-app for client invoices")

    assert stack["stack"] == "nextjs"
    assert "next" in files["package.json"]
    assert "src/app/page.tsx" in files
    assert "src/app/layout.tsx" in files
    assert "src/app/(dashboard)/workspace/page.tsx" in files
    assert "src/components/Landing/HomePage.tsx" in files
    assert "src/components/Workspace/WorkspaceConsole.tsx" in files
    assert "src/components/ui/button.tsx" in files
    assert "src/services/BriefService.ts" in files
    assert "src/store/workspaceStore.ts" in files
    assert "FRONTEND_STRUCTURE.md" in files
    assert "src/lib/productPlan.ts" in files
    assert "src/app/api/brief/route.ts" in files


def test_web_app_required_routes_generate_contract_pages():
    request = """
    web-app: Build CivicPermit Studio.
    Required screens/routes:
    - Home landing page
    - Product page
    - Pricing page
    - Contact/demo page
    - Dashboard preview route
    """.strip()
    stack = project_scaffolds.detect_stack(request)
    files = project_scaffolds.files_for_stack(stack, "CivicPermit Studio", request)

    assert "src/lib/webProjectContract.ts" in files
    assert "src/components/WebContract/WebContractPage.tsx" in files
    assert "src/components/WebContract/DashboardPreviewPage.tsx" in files
    assert "src/app/product/page.tsx" in files
    assert "src/app/pricing/page.tsx" in files
    assert "src/app/contact/page.tsx" in files
    assert "src/app/dashboard-preview/page.tsx" in files
    assert "src/app/(auth)/login/page.tsx" not in files
    assert "src/app/(dashboard)/workspace/page.tsx" not in files
    assert "signal-panel" not in files["src/components/Landing/HomePage.tsx"]
    assert "WebContractPage" in files["src/components/Landing/HomePage.tsx"]


def test_dashboard_required_routes_ignore_instruction_sentences():
    request = """
    web-app: Build PermitFlow Command Center, a production-quality Next.js dashboard for city building-permit teams.

    Product: PermitFlow helps planning departments manage permit intake, plan review queues, inspection scheduling, applicant messages, fee holds, reviewer workload, public transparency updates, and audit trail proof.

    Required screens/routes:
    - Home dashboard overview
    - Intake page
    - Reviews page
    - Inspections page
    - Applicants page
    - Settings page

    Dashboard requirements: each page must be a real route with a thin app route and feature component.
    """.strip()
    stack = project_scaffolds.detect_stack(request)

    routes = web_project_contract.expected_routes(request, stack=stack)
    flattened_routes = web_project_contract.expected_routes(" ".join(request.split()), stack=stack)
    route_ids = [route["id"] for route in routes]
    flattened_route_ids = [route["id"] for route in flattened_routes]
    contract = web_project_contract.build_contract(request, "PermitFlow Command Center", stack=stack)
    files = project_scaffolds.files_for_stack(stack, "PermitFlow Command Center", request)

    assert route_ids == ["home", "intake", "reviews", "inspections", "applicants", "settings"]
    assert flattened_route_ids == route_ids
    assert [item["route"] for item in contract["nav"]] == ["/", "/intake", "/reviews", "/inspections", "/applicants", "/settings"]
    page_summaries = {page["id"]: page["summary"] for page in contract["pages"]}
    assert "permit intake" in page_summaries["intake"].lower()
    assert "plan review" in page_summaries["reviews"].lower()
    assert "inspection scheduling" in page_summaries["inspections"].lower()
    assert "applicant messages" in page_summaries["applicants"].lower()
    assert len(set(page_summaries.values())) > 2
    assert "a-real-route-with-a-thin-app-route" not in route_ids
    for route in ("intake", "reviews", "inspections", "applicants", "settings"):
        assert f"src/app/{route}/page.tsx" in files
    assert "src/app/a-real-route-with-a-thin-app-route/page.tsx" not in files
    assert "src/app/(auth)/login/page.tsx" not in files
    assert "src/app/(dashboard)/workspace/page.tsx" not in files
    assert 'href="/contact"' not in files["src/components/WebContract/ContractShell.tsx"]
    assert 'href="/pricing"' not in files["src/components/WebContract/WebContractPage.tsx"]


def test_normal_four_page_website_generates_marketing_site_not_dashboard(tmp_path):
    request = "Build a normal website called Lumora Studio: four pages for Home, About, Services, and Contact. No dashboard, no login, no app workspace."
    stack = project_scaffolds.detect_stack(request)
    files = project_scaffolds.files_for_stack(stack, project_scaffolds.product_name(request), request)

    assert stack["stack"] == "nextjs"
    for path in [
        "src/app/page.tsx",
        "src/app/about/page.tsx",
        "src/app/services/page.tsx",
        "src/app/contact/page.tsx",
        "src/components/Marketing/SiteShell.tsx",
        "src/lib/siteContent.ts",
    ]:
        assert path in files
    assert "src/app/(dashboard)/workspace/page.tsx" not in files
    assert "src/app/(auth)/login/page.tsx" not in files
    assert "src/app/privacy/page.tsx" not in files
    assert "src/app/terms/page.tsx" not in files
    assert "src/components/layout/AppShell.tsx" not in files
    assert "src/components/Workspace/WorkspaceConsole.tsx" not in files
    assert "src/lib/authTokens.ts" not in files
    assert "src/lib/productPlan.ts" not in files
    assert '"Lumora Studio"' not in files["src/components/Marketing/SiteHeader.tsx"]
    assert '"Lumora Studio"' not in files["src/components/Marketing/SiteFooter.tsx"]
    assert '"href": "/about"' in files["src/lib/siteContent.ts"]
    assert '"href": "/services"' in files["src/lib/siteContent.ts"]
    assert '"href": "/contact"' in files["src/lib/siteContent.ts"]

    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    verification = coding_workflow.verify_project_artifact(tmp_path, stack, [str(tmp_path / relative) for relative in files])

    assert verification["status"] == "passed"


def test_nextjs_production_profile_uses_vitest_and_does_not_trigger_pytest(tmp_path):
    stack = project_scaffolds.detect_stack("build a web-app for client invoices")
    files = project_scaffolds.files_for_stack(stack, "InvoicePilot", "build a web-app for client invoices")
    files.update(production_readiness._production_profile_files(stack, "InvoicePilot", "build a web-app for client invoices"))

    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    commands = production_coding_autonomy.discover_tests(tmp_path)

    assert "tests/health.test.ts" in files
    assert "vitest" in files["tests/health.test.ts"]
    assert "python -m pytest" not in commands


def test_product_names_ignore_prompt_filler_words():
    request = "Build a web-app for a university management dashboard for registrar staff, lecturers, students, fees, course approvals, and admin reporting"

    assert project_scaffolds.product_name(request) == "University Management Dashboard"
    assert project_scaffolds.project_slug(request, {"stack": "nextjs"}) == "university-management-registrar-staff-lecturers-web"


def test_called_single_token_product_name_beats_framework_words():
    request = (
        "Build a Next.js landing page for a fintech app called VaultPilot. "
        "VaultPilot helps freelancers track income, taxes, invoices, and emergency savings from one calm dashboard."
    )

    assert project_scaffolds.product_name(request) == "VaultPilot"
    assert project_scaffolds.project_slug(request, {"stack": "nextjs"}) == "vaultpilot-web"


def test_landing_page_with_pricing_section_has_home_only_route_contract():
    request = (
        "Build a Next.js landing page for a fintech product called ReserveMate. "
        "The page should include product proof, pricing, security notes, and a clear start path."
    )

    routes = web_project_contract.expected_routes(request, stack={"stack": "nextjs"})

    assert routes == [{"id": "home", "label": "Home", "route": "/", "kind": "public"}]


def test_field_service_scaffold_contains_dispatch_specific_product_model():
    request = "Build a web-app for Field Service Dispatch OS for HVAC plumbing electrical companies with incoming jobs, technician availability, emergency dispatch, parts readiness, invoices, SLA risk, and schedule changes"
    stack = project_scaffolds.detect_stack(request)
    files = project_scaffolds.files_for_stack(stack, project_scaffolds.product_name(request), request)
    plan = files["src/lib/productPlan.ts"]

    assert project_scaffolds.product_name(request) == "Field Service Dispatch OS"
    for term in ["Emergency dispatch queue", "technician", "HVAC", "plumbing", "electrical", "parts", "SLA", "invoice"]:
        assert term.lower() in plan.lower()
    assert "Field Service Dispatch OS" in plan
    assert "A dispatch-grade board" in plan
    assert "tracking requests, owners, approvals" not in plan.lower()
    assert "operators', 'team leads" not in plan.lower()


def test_restaurant_shift_scaffold_contains_domain_specific_product_model():
    request = "Build a web-app for Restaurant Shift Command OS: a production-quality operations dashboard for independent restaurants to manage table waitlist pressure, kitchen ticket backlog, staff coverage, inventory shortages, delivery app orders, customer complaints, refunds, food safety checks, and daily cash close."
    stack = project_scaffolds.detect_stack(request)
    files = project_scaffolds.files_for_stack(stack, project_scaffolds.product_name(request), request)
    plan = files["src/lib/productPlan.ts"]

    assert project_scaffolds.product_name(request) == "Restaurant Shift Command OS"
    for term in ["table waitlist", "kitchen ticket backlog", "staff coverage", "inventory shortages", "delivery", "refund", "food safety", "cash close"]:
        assert term.lower() in plan.lower()
    assert "Restaurant Shift Command OS" in plan
    assert "A shift-grade dashboard" in plan
    assert "tracking requests, owners, approvals" not in plan.lower()
    assert "operators', 'team leads" not in plan.lower()


def test_dynamic_scaffold_extracts_unknown_domain_workflows():
    request = "Build a web-app for Dental Clinic Front Desk OS: manage appointment confirmations, insurance eligibility, chair availability, hygienist handoffs, patient intake forms, treatment plan followups, lab case tracking, and end-of-day collections."
    stack = project_scaffolds.detect_stack(request)
    files = project_scaffolds.files_for_stack(stack, project_scaffolds.product_name(request), request)
    plan = files["src/lib/productPlan.ts"]

    assert project_scaffolds.product_name(request) == "Dental Clinic Front Desk OS"
    for term in ["appointment confirmations", "insurance eligibility", "chair availability", "hygienist handoffs", "patient intake forms", "treatment plan followups"]:
        assert term.lower() in plan.lower()
    assert "A focused dental clinic front desk command workspace" in plan
    assert "tracking requests, owners, approvals" not in plan.lower()


def test_university_scaffold_contains_domain_specific_product_model():
    request = "Build a web-app for a university management dashboard for registrar staff, lecturers, students, fees, course approvals, and admin reporting"
    stack = project_scaffolds.detect_stack(request)
    files = project_scaffolds.files_for_stack(stack, project_scaffolds.product_name(request), request)
    plan = files["src/lib/productPlan.ts"]
    home = files["src/components/Landing/HomePage.tsx"]

    for term in ["Registrar", "lecturers", "students", "fees", "course approvals", "Admin reporting"]:
        assert term.lower() in plan.lower()
    assert "summary:" in plan
    assert "A registrar-grade dashboard" in plan
    assert "customer asked for status" not in plan.lower()
    assert "designer is blocked" not in plan.lower()
    assert "service businesses" not in plan.lower()
    assert "productPlan.valueProps" in home
    assert "productPlan.summary" in home
    assert "productPlan.request" not in home


def test_nextjs_scaffold_uses_pinned_package_versions():
    stack = project_scaffolds.detect_stack("build a web-app for client invoices")
    files = project_scaffolds.files_for_stack(stack, "InvoicePilot", "build a web-app for client invoices")
    package = _package(files)

    versions = {
        **package["dependencies"],
        **package["devDependencies"],
    }
    assert versions
    assert "latest" not in set(versions.values())
    assert all(version and version[0].isdigit() for version in versions.values())
    assert package["overrides"]["postcss"] == package["devDependencies"]["postcss"]
    assert package["devDependencies"]["eslint"].startswith("9.")
    assert package["devDependencies"]["typescript"].startswith("5.")


def test_nextjs_scaffold_matches_nexus_forge_frontend_shape():
    stack = project_scaffolds.detect_stack("build a web-app for client invoices")
    files = project_scaffolds.files_for_stack(stack, "InvoicePilot", "build a web-app for client invoices")

    expected_roots = [
        "src/app/(auth)/login/page.tsx",
        "src/app/(dashboard)/layout.tsx",
        "src/components/Auth/LoginPage.tsx",
        "src/components/Workspace/WorkspaceConsole.tsx",
        "src/components/layout/AppShell.tsx",
        "src/components/ui/card.tsx",
        "src/hooks/useBriefDraft.ts",
        "src/services/api.ts",
        "src/store/workspaceStore.ts",
        "src/test/setup.ts",
        "src/types/index.ts",
    ]
    for path in expected_roots:
        assert path in files

    assert "@/components" in files["components.json"]
    assert "vitest" in files["package.json"]
    assert "WorkspaceConsole" not in files["src/app/page.tsx"]
    assert "HomePage" in files["src/app/page.tsx"]
    assert "disabled={reviewed}" in files["src/components/Workspace/WorkItemCard.tsx"]


def test_mobile_keyword_generates_flutter_files():
    stack = project_scaffolds.detect_stack("build a mobile app for client invoices")
    files = project_scaffolds.files_for_stack(stack, "InvoicePilot", "build a mobile app for client invoices")

    assert stack["stack"] == "flutter"
    assert "pubspec.yaml" in files
    assert "lib/main.dart" in files
    assert "lib/home_screen.dart" in files
    assert "lib/workflow_store.dart" in files
    assert "flutter" in files["pubspec.yaml"]


def test_website_with_mobile_screenshot_requirement_stays_nextjs():
    request = (
        "Build a normal website for a real construction company: Turner Construction Company. "
        "Build it as a polished Next.js marketing website with Home, About, Services, Contact. "
        "Run browser visual review with desktop and mobile screenshots."
    )

    stack = project_scaffolds.detect_stack(request)

    assert stack["stack"] == "nextjs"
    assert project_scaffolds.product_name(request) == "Turner Construction Company"
    assert project_scaffolds.project_slug(request, stack) == "turner-construction-company-web"


def test_real_company_name_from_for_clause_and_brand_exactly():
    request = (
        "Build a polished four-page Next.js company website for Skanska USA, "
        "a real construction and development company. Keep visible brand text as exactly Skanska USA."
    )
    stack = project_scaffolds.detect_stack(request)

    assert project_scaffolds.product_name(request) == "Skanska USA"
    assert project_scaffolds.project_slug(request, stack) == "skanska-usa-web"


def test_fictional_luxury_brand_name_from_for_clause():
    request = (
        "Build a polished four-page Next.js website for Maison Noire Atelier, "
        "a fictional luxury watch and jewelry atelier. Pages must be Home, Atelier, Collections, and Concierge Contact."
    )
    stack = project_scaffolds.detect_stack(request)

    assert project_scaffolds.product_name(request) == "Maison Noire Atelier"
    assert project_scaffolds.project_slug(request, stack) == "maison-noire-atelier-web"


def test_marketing_website_explicit_pages_use_web_route_contract():
    request = (
        "Build a production-quality 4-page Next.js marketing website for KineticGrid Energy. "
        "KineticGrid Energy helps commercial buildings monitor microgrids, solar production, battery state, demand spikes, building load, and outage risk. "
        "Pages must be Home, Platform, Case Studies, and Contact."
    )
    stack = project_scaffolds.detect_stack(request)

    files = project_scaffolds.files_for_stack(stack, "KineticGrid Energy", request)

    assert "src/app/platform/page.tsx" in files
    assert "src/app/case-studies/page.tsx" in files
    assert "src/app/about/page.tsx" not in files
    assert "src/app/services/page.tsx" not in files
    assert "src/lib/webProjectContract.ts" in files
    contract_text = files["src/lib/webProjectContract.ts"].lower()
    assert "microgrid" in contract_text
    assert "solar" in contract_text
    assert "battery" in contract_text
    assert "demand" in contract_text
    assert "production, marketing, website" not in contract_text
    assert "concrete pilot plan" not in contract_text


def test_landing_page_brand_name_from_for_as_clause():
    request = "Build a polished production-quality landing page for Nexus Forge as a fresh Next.js web-app project."

    assert project_scaffolds.product_name(request) == "Nexus Forge"
    assert project_scaffolds.project_slug(request, {"stack": "nextjs"}) == "nexus-forge-web"


def test_single_landing_page_request_does_not_generate_app_shell():
    request = (
        "Build a polished production-quality single-page landing page for Nexus Forge as a fresh Next.js web-app project. "
        "Single landing page only, no login portal, no dashboard, no generic workspace."
    )
    stack = project_scaffolds.detect_stack(request)

    files = project_scaffolds.files_for_stack(stack, "Nexus Forge", request)

    assert "src/app/page.tsx" in files
    assert "src/components/Landing/SingleLandingPage.tsx" in files
    assert "src/lib/landingContent.ts" in files
    assert "src/components/Landing/__tests__/landingContent.test.ts" in files
    assert "src/app/(dashboard)/workspace/page.tsx" not in files
    assert "src/app/(auth)/login/page.tsx" not in files
    assert "src/components/Workspace/WorkspaceConsole.tsx" not in files
    assert "src/lib/productPlan.ts" not in files
    assert "SingleLandingPage" in files["src/app/page.tsx"]
    assert "landingContent.nav.every" in files["src/components/Landing/__tests__/landingContent.test.ts"]


def test_backend_defaults_to_fastify_and_honors_language_requests():
    default_stack = project_scaffolds.detect_stack("build a backend for client invoices")
    rust_stack = project_scaffolds.detect_stack("build a rust backend for client invoices")
    go_stack = project_scaffolds.detect_stack("build a go backend for client invoices")
    python_stack = project_scaffolds.detect_stack("build a python backend for client invoices")

    assert default_stack["stack"] == "node_fastify"
    default_files = project_scaffolds.files_for_stack(default_stack, "InvoicePilot", "backend")
    assert "src/server.js" in default_files
    assert "src/app.js" in default_files
    assert "src/routes/brief.js" in default_files
    assert rust_stack["stack"] == "rust_axum"
    rust_files = project_scaffolds.files_for_stack(rust_stack, "InvoicePilot", "backend")
    assert "src/main.rs" in rust_files
    assert "src/routes.rs" in rust_files
    assert go_stack["stack"] == "go_api"
    go_files = project_scaffolds.files_for_stack(go_stack, "InvoicePilot", "backend")
    assert "main.go" in go_files
    assert "handlers.go" in go_files
    assert python_stack["stack"] == "python_fastapi"
    python_files = project_scaffolds.files_for_stack(python_stack, "InvoicePilot", "backend")
    assert "invoicepilot/main.py" in python_files
    assert "invoicepilot/routes.py" in python_files


def test_backend_only_request_is_not_misclassified_as_web_app():
    request = "Build a backend API with Node.js Fastify for clinic intake. This is backend only, not a web-app."

    stack = project_scaffolds.detect_stack(request)

    assert stack["kind"] == "backend"
    assert stack["stack"] == "node_fastify"


def test_field_service_web_app_is_not_misclassified_by_service_word():
    request = "Build a web-app for Field Service Dispatch OS for HVAC teams"

    stack = project_scaffolds.detect_stack(request)

    assert stack["kind"] == "web_app"
    assert stack["stack"] == "nextjs"


def test_node_backend_scaffold_uses_pinned_package_versions():
    stack = project_scaffolds.detect_stack("build a backend for client invoices")
    files = project_scaffolds.files_for_stack(stack, "InvoicePilot", "build a backend for client invoices")
    package = _package(files)

    versions = {
        **package["dependencies"],
        **package["devDependencies"],
    }
    assert versions
    assert "latest" not in set(versions.values())
    assert all(version and version[0].isdigit() for version in versions.values())
    assert package["dependencies"]["fastify"] == "5.8.5"


def test_supported_scaffolds_pass_file_shape_verification(tmp_path):
    requests = [
        "build a web-app for client invoices",
        "build a mobile app for client invoices",
        "build a backend for client invoices",
        "build a python backend for client invoices",
        "build a go backend for client invoices",
        "build a rust backend for client invoices",
    ]

    for index, request in enumerate(requests):
        stack = project_scaffolds.detect_stack(request)
        files = project_scaffolds.files_for_stack(stack, "InvoicePilot", request)
        target = tmp_path / f"project-{index}"
        written = []
        for relative, content in files.items():
            path = target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            written.append(str(path))

        verified = coding_workflow.verify_project_artifact(target, stack, written)

        assert verified["status"] == "passed", verified

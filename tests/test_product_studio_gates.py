import json

from core import browser_playwright, codebase_standards, product_studio_gates


def test_product_studio_gates_execute_real_project_checks(tmp_path, monkeypatch):
    monkeypatch.setattr(product_studio_gates.trust_proof, "DB_PATH", tmp_path / "proof.sqlite3")
    monkeypatch.setattr(codebase_standards, "DB_PATH", tmp_path / "standards.sqlite3")
    package = {
        "name": "gate-smoke",
        "private": True,
        "version": "0.1.0",
        "scripts": {
            "test": "node -e \"console.log('test gate passed')\"",
            "build": "node -e \"console.log('build gate passed')\"",
        },
    }
    (tmp_path / "package.json").write_text(json.dumps(package), encoding="utf-8")

    result = product_studio_gates.execute_gates(
        tmp_path,
        stack={"kind": "web_app", "stack": "nextjs"},
        install=True,
        tests=True,
        audits=True,
        browser=False,
        preview=False,
        create_proof=False,
    )

    statuses = {gate["id"]: gate["status"] for gate in result["gates"]}
    assert result["attempted"] is True
    assert statuses["dependencies_install"] == "passed"
    assert statuses["dependency_audit"] == "passed"
    assert any(status == "passed" for gate_id, status in statuses.items() if gate_id.startswith("test_"))
    assert (tmp_path / ".friday" / "product-studio" / "gates" / "gate-results.json").exists()


def test_node_install_gate_uses_bounded_npm_install_command(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"name": "bounded-install"}), encoding="utf-8")

    command = product_studio_gates._install_command(tmp_path, {"kind": "web_app", "stack": "nextjs"})

    assert command == "npm install --ignore-scripts --no-audit --no-fund --prefer-online"


def test_web_route_contract_gate_blocks_missing_requested_web_app_pages(tmp_path):
    request = """
    web-app: Build CivicPermit Studio.
    Required screens/routes:
    - Home landing page
    - Product page
    - Pricing page
    - Contact/demo page
    - Dashboard preview route
    """.strip()
    app = tmp_path / "src" / "app"
    app.mkdir(parents=True)
    (app / "page.tsx").write_text("export default function Page(){ return null; }\n", encoding="utf-8")
    log_root = tmp_path / ".friday" / "product-studio" / "gates" / "logs"
    log_root.mkdir(parents=True)

    gate = product_studio_gates._web_route_contract_gate(tmp_path, request, {"stack": "nextjs"}, log_root)

    assert gate["status"] == "failed"
    assert gate["required"] is True
    assert "product" in gate["summary"]
    assert "dashboard-preview" in gate["summary"]


def test_web_route_contract_gate_passes_generated_contract_routes(tmp_path):
    request = "web-app with Product page, Pricing page, Contact/demo page, and Dashboard preview route"
    app = tmp_path / "src" / "app"
    for route in ("product", "pricing", "contact", "dashboard-preview"):
        (app / route).mkdir(parents=True)
        (app / route / "page.tsx").write_text("import { X } from '@/x';\nexport default function Page(){ return <X />; }\n", encoding="utf-8")
    app.mkdir(parents=True, exist_ok=True)
    (app / "page.tsx").write_text("export default function Page(){ return null; }\n", encoding="utf-8")
    log_root = tmp_path / ".friday" / "product-studio" / "gates" / "logs"
    log_root.mkdir(parents=True)

    gate = product_studio_gates._web_route_contract_gate(tmp_path, request, {"stack": "nextjs"}, log_root)

    assert gate["status"] == "passed"


def test_web_route_contract_respects_explicit_platform_page_name(tmp_path):
    request = "Build a 4-page website: Home, Platform, Case Studies, Contact."
    app = tmp_path / "src" / "app"
    for route in ("platform", "case-studies", "contact"):
        (app / route).mkdir(parents=True)
        (app / route / "page.tsx").write_text("import { X } from '@/x';\nexport default function Page(){ return <X />; }\n", encoding="utf-8")
    app.mkdir(parents=True, exist_ok=True)
    (app / "page.tsx").write_text("export default function Page(){ return null; }\n", encoding="utf-8")
    log_root = tmp_path / ".friday" / "product-studio" / "gates" / "logs"
    log_root.mkdir(parents=True)

    gate = product_studio_gates._web_route_contract_gate(tmp_path, request, {"stack": "nextjs"}, log_root)

    assert gate["status"] == "passed"
    assert "product" not in gate["metadata"]["checked"]
    assert "platform" in gate["metadata"]["checked"]


def test_secret_scan_skips_friday_evidence_artifacts(tmp_path):
    log_root = tmp_path / ".friday" / "product-studio" / "gates" / "logs"
    log_root.mkdir(parents=True)
    runner = tmp_path / ".friday" / "design" / "stitch-runner.mjs"
    runner.parent.mkdir(parents=True)
    runner.write_text("const toolClient = new StitchToolClient({ apiKey: process.env.STITCH_API_KEY });", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text("export const ok = true;", encoding="utf-8")

    result = product_studio_gates._secret_scan_gate(tmp_path, log_root)

    assert result["status"] == "passed"
    assert result["metadata"]["findings"] == []


def test_failed_dependency_install_blocks_downstream_runtime_gates(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "npm-not-run", "build": "npm-not-run"}, "dependencies": {"next": "16.2.6"}}),
        encoding="utf-8",
    )

    def fake_command_gate(base, gate_id, label, command, group, log_root, timeout_seconds):
        return {
            "id": gate_id,
            "label": label,
            "group": group,
            "status": "timeout" if gate_id == "dependencies_install" else "passed",
            "required": True,
            "executed": True,
            "summary": "install timed out" if gate_id == "dependencies_install" else "unexpected downstream run",
            "command": command,
            "evidence": [],
        }

    monkeypatch.setattr(product_studio_gates, "_command_gate", fake_command_gate)

    result = product_studio_gates.execute_gates(
        tmp_path,
        stack={"kind": "web_app", "stack": "nextjs"},
        install=True,
        tests=True,
        audits=True,
        browser=True,
        preview=True,
        create_proof=False,
    )
    statuses = {gate["id"]: gate["status"] for gate in result["gates"]}

    assert statuses["dependencies_install"] == "timeout"
    assert statuses["tests"] == "blocked"
    assert statuses["dependency_audit"] == "blocked"
    assert statuses["local_preview"] == "blocked"
    assert statuses["browser_check"] == "blocked"
    assert result["technical_ready"] is False


def test_fastify_preview_uses_health_endpoint(tmp_path):
    package = {
        "scripts": {"start": "node src/server.js"},
        "dependencies": {"fastify": "5.8.5", "@fastify/cors": "11.1.0"},
    }
    (tmp_path / "package.json").write_text(json.dumps(package), encoding="utf-8")

    command = product_studio_gates._preview_command(tmp_path, {"kind": "backend", "stack": "node_fastify"})

    assert command["kind"] == "node_start"
    assert command["path"] == "/health"


def test_operations_gate_detects_nextjs_health_route_folder(tmp_path):
    health_route = tmp_path / "src" / "app" / "api" / "health" / "route.ts"
    health_route.parent.mkdir(parents=True)
    health_route.write_text("export async function GET() { return Response.json({ status: 'ok' }); }", encoding="utf-8")
    docs = tmp_path / "docs" / "OPERATIONS.md"
    docs.parent.mkdir()
    docs.write_text("# Operations\n\nRollback and health checks are documented.", encoding="utf-8")

    gate = product_studio_gates._operations_gate(tmp_path, tmp_path)

    assert gate["status"] == "passed"
    assert "src/app/api/health/route.ts" in [path.replace("\\", "/") for path in gate["metadata"]["health_files"]]


def test_product_fit_gate_rejects_generic_scaffold_for_specific_domain(tmp_path):
    product_plan = tmp_path / "src" / "lib" / "productPlan.ts"
    product_plan.parent.mkdir(parents=True)
    product_plan.write_text(
        """
export const productPlan = {
  request: 'Build a web-app for a university management dashboard for registrar staff, lecturers, students, fees, course approvals, and admin reporting',
  sampleNote: 'Customer asked for status, invoice is pending, designer is blocked on brand assets.',
  targetUsers: ['service businesses', 'SMB operators'],
};
""",
        encoding="utf-8",
    )

    gate = product_studio_gates._product_fit_gate(
        tmp_path,
        "Build a web-app for a university management dashboard for registrar staff, lecturers, students, fees, course approvals, and admin reporting",
        tmp_path,
    )

    assert gate["status"] == "failed"
    assert "invoice" in gate["metadata"]["stale_generic_copy"]


def test_product_fit_gate_accepts_university_domain_surfaces(tmp_path):
    product_plan = tmp_path / "src" / "lib" / "productPlan.ts"
    product_plan.parent.mkdir(parents=True)
    product_plan.write_text(
        """
export const productPlan = {
  sampleNote: 'Registrar has pending course approvals, student fee exceptions, lecturer timetable changes, and admin reporting due.',
  targetUsers: ['registrar offices', 'lecturers', 'students', 'bursary teams'],
};
""",
        encoding="utf-8",
    )

    gate = product_studio_gates._product_fit_gate(
        tmp_path,
        "Build a web-app for a university management dashboard for registrar staff, lecturers, students, fees, course approvals, and admin reporting",
        tmp_path,
    )

    assert gate["status"] == "passed"
    assert "registrar" in gate["metadata"]["matched_keywords"]


def test_product_fit_gate_ignores_raw_request_and_requires_field_dispatch_terms(tmp_path):
    product_plan = tmp_path / "src" / "lib" / "productPlan.ts"
    product_plan.parent.mkdir(parents=True)
    product_plan.write_text(
        """
export const productPlan = {
  request: 'Build a web-app for Field Service Dispatch OS for HVAC plumbing electrical companies with incoming jobs, technician availability, emergency dispatch, parts readiness, invoices, SLA risk, and schedule changes',
  name: 'Field Service Workspace',
  summary: 'A focused field service workspace for tracking requests, owners, approvals, decision briefs, and launch proof.',
  sampleNote: 'Field Service request is waiting on owner review, one approval, and a customer-ready update.',
};
""",
        encoding="utf-8",
    )

    gate = product_studio_gates._product_fit_gate(
        tmp_path,
        "Build a web-app for Field Service Dispatch OS for HVAC plumbing electrical companies with incoming jobs, technician availability, emergency dispatch, parts readiness, invoices, SLA risk, and schedule changes",
        tmp_path,
    )

    assert gate["status"] == "failed"
    assert "technician" in gate["metadata"]["missing_specific_terms"]
    assert "invoice" in gate["metadata"]["missing_specific_terms"]


def test_product_fit_gate_accepts_field_dispatch_surfaces(tmp_path):
    product_plan = tmp_path / "src" / "lib" / "productPlan.ts"
    product_plan.parent.mkdir(parents=True)
    product_plan.write_text(
        """
export const productPlan = {
  name: 'Field Service Dispatch OS',
  summary: 'A dispatch-grade board for incoming jobs, technician availability, emergency calls, parts readiness, SLA risk, customer updates, and invoice handoff.',
  sampleNote: 'Emergency HVAC job needs a technician, plumbing parts are delayed, and an invoice is waiting for closeout.',
};
""",
        encoding="utf-8",
    )

    gate = product_studio_gates._product_fit_gate(
        tmp_path,
        "Build a web-app for Field Service Dispatch OS for HVAC plumbing electrical companies with incoming jobs, technician availability, emergency dispatch, parts readiness, invoices, SLA risk, and schedule changes",
        tmp_path,
    )

    assert gate["status"] == "passed"
    assert not gate["metadata"]["missing_specific_terms"]


def test_product_fit_gate_accepts_restaurant_shift_surfaces(tmp_path):
    product_plan = tmp_path / "src" / "lib" / "productPlan.ts"
    product_plan.parent.mkdir(parents=True)
    product_plan.write_text(
        """
export const productPlan = {
  name: 'Restaurant Shift Command OS',
  summary: 'Restaurant shift command center for table waitlist pressure, kitchen ticket backlog, staff coverage, inventory shortages, delivery app orders, customer complaints, refunds, food safety checks, and daily cash close.',
  workItems: ['Table waitlist pressure', 'Kitchen ticket backlog', 'Staff coverage gaps', 'Inventory shortages', 'Delivery refunds', 'Food safety and cash close']
};
""",
        encoding="utf-8",
    )

    gate = product_studio_gates._product_fit_gate(
        tmp_path,
        "Build a web-app for Restaurant Shift Command OS: table waitlist pressure, kitchen ticket backlog, staff coverage, inventory shortages, delivery app orders, customer complaints, refunds, food safety checks, and daily cash close.",
        tmp_path,
    )

    assert gate["status"] == "passed"
    assert "restaurant" in gate["metadata"]["matched_keywords"]
    assert gate["metadata"]["missing_specific_terms"] == []


def test_product_fit_gate_rejects_climate_risk_luxury_drift(tmp_path):
    content = tmp_path / "src" / "lib" / "stitchNativeContent.ts"
    content.parent.mkdir(parents=True)
    content.write_text(
        """
export const stitchNativeContent = {
  pages: {
    home: {
      title: 'EmberVault',
      bodyHtml: '<main><nav>Atelier Collections Process Concierge</nav><h1>Crafted for private clients who notice the difference.</h1><p>EmberVault climate risk intelligence for commercial property owners, wildfire, flood, heat, insurance, maintenance, and portfolio risk.</p><a>Request Concierge Access</a></main>'
    }
  }
};
""",
        encoding="utf-8",
    )

    gate = product_studio_gates._product_fit_gate(
        tmp_path,
        "Build a landing page for EmberVault, a premium climate-risk intelligence platform for commercial property owners covering wildfire, flood, heat, insurance, maintenance, tenant-impact risk, and property portfolios.",
        tmp_path,
    )

    assert gate["status"] == "failed"
    assert "atelier" in gate["metadata"]["stale_generic_copy"]
    assert "concierge" in gate["metadata"]["stale_generic_copy"]


def test_product_fit_gate_accepts_dynamic_unknown_domain_surfaces(tmp_path):
    product_plan = tmp_path / "src" / "lib" / "productPlan.ts"
    product_plan.parent.mkdir(parents=True)
    product_plan.write_text(
        """
export const productPlan = {
  name: 'Dental Clinic Front Desk OS',
  summary: 'Dental clinic front desk command workspace for appointment confirmations, insurance eligibility, chair availability, hygienist handoffs, patient intake forms, treatment plan followups, lab case tracking, and end-of-day collections.',
  workItems: ['Appointment confirmations', 'Insurance eligibility', 'Chair availability', 'Patient intake forms']
};
""",
        encoding="utf-8",
    )

    gate = product_studio_gates._product_fit_gate(
        tmp_path,
        "Build a web-app for Dental Clinic Front Desk OS: manage appointment confirmations, insurance eligibility, chair availability, hygienist handoffs, patient intake forms, treatment plan followups, lab case tracking, and end-of-day collections.",
        tmp_path,
    )

    assert gate["status"] == "passed"
    assert "dental" in gate["metadata"]["matched_keywords"]
    assert "appointment" in gate["metadata"]["matched_keywords"]


def test_browser_quality_gate_exercises_workspace_controls(tmp_path, monkeypatch):
    calls = []

    def fake_run_steps(url, steps, screenshot=True):
        calls.append((url, steps, screenshot))
        return {
            "ok": True,
            "steps": [{"ok": True, "action": step["action"], "selector": step.get("selector", "")} for step in steps],
            "screenshot": str(tmp_path / "workspace.png"),
            "context": {"url": f"{url.rstrip('/')}/workspace", "elements": []},
        }

    monkeypatch.setattr(product_studio_gates.browser_playwright, "run_steps", fake_run_steps)
    gates = [
        {
            "id": "browser_check",
            "status": "passed",
            "url": "http://127.0.0.1:3000/",
            "metadata": {
                "context": {
                    "url": "http://127.0.0.1:3000/",
                    "elements": [{"tag": "a", "text": "Open workspace"}],
                }
            },
        }
    ]

    gate = product_studio_gates._browser_quality_gate(tmp_path, gates, tmp_path, required=True)

    assert gate["status"] == "passed"
    assert calls
    selectors = [step.get("selector") for step in calls[0][1]]
    assert "text=Open workspace" in selectors
    assert "text=Draft brief" in selectors
    assert "text=Mark reviewed" in selectors
    assert gate["metadata"]["route_smoke"]["status"] == "passed"


def test_browser_quality_gate_fails_dead_workspace_controls(tmp_path, monkeypatch):
    monkeypatch.setattr(
        product_studio_gates.browser_playwright,
        "run_steps",
        lambda url, steps, screenshot=True: {
            "ok": False,
            "steps": [{"ok": False, "action": "click", "selector": "text=Draft brief", "result": "not found"}],
            "screenshot": "",
        },
    )
    gates = [
        {
            "id": "browser_check",
            "status": "passed",
            "url": "http://127.0.0.1:3000/",
            "metadata": {
                "context": {
                    "url": "http://127.0.0.1:3000/",
                    "elements": [{"tag": "a", "text": "Open workspace"}],
                }
            },
        }
    ]

    gate = product_studio_gates._browser_quality_gate(tmp_path, gates, tmp_path, required=True)

    assert gate["status"] == "failed"
    assert gate["metadata"]["route_smoke"]["status"] == "failed"


def test_browser_quality_gate_checks_custom_website_routes(tmp_path, monkeypatch):
    checked = []

    def fake_fetch(url):
        checked.append(url)
        if url.endswith("/inquire"):
            return 404, "not found"
        return 200, "ok"

    monkeypatch.setattr(product_studio_gates, "_fetch_url_status", fake_fetch)
    request = (
        "Build a polished four-page Next.js website for Maison Noire Atelier. "
        "Pages must be Home, Atelier, Collections, and Concierge Contact."
    )
    gates = [
        {
            "id": "browser_check",
            "status": "passed",
            "url": "http://127.0.0.1:3000/",
            "metadata": {
                "context": {
                    "url": "http://127.0.0.1:3000/",
                    "elements": [
                        {"tag": "a", "text": "Atelier", "href": "/atelier"},
                        {"tag": "a", "text": "Collections", "href": "/collections"},
                        {"tag": "a", "text": "Inquire", "href": "/inquire"},
                    ],
                }
            },
        }
    ]

    gate = product_studio_gates._browser_quality_gate(tmp_path, gates, tmp_path, required=True, request=request)

    assert gate["status"] == "failed"
    assert gate["metadata"]["route_smoke"]["status"] == "failed"
    routes = {step["route"] for step in gate["metadata"]["route_smoke"]["steps"]}
    assert {"/", "/atelier", "/collections", "/contact", "/inquire"}.issubset(routes)
    assert any(url.endswith("/inquire") for url in checked)
    assert (tmp_path / "browser-site-route-smoke.json").exists()


def test_browser_routes_to_check_uses_custom_site_map_and_same_origin_links():
    request = (
        "Build a polished four-page Next.js website for Maison Noire Atelier. "
        "Pages must be Home, Atelier, Collections, and Concierge Contact."
    )
    routes = product_studio_gates._browser_routes_to_check(
        "http://127.0.0.1:3000/",
        [
            {"tag": "a", "text": "Inquire", "href": "/inquire"},
            {"tag": "a", "text": "External", "href": "https://example.com/offsite"},
            {"tag": "a", "text": "Email", "href": "mailto:hello@example.com"},
        ],
        request=request,
    )

    assert routes[:4] == ["/", "/atelier", "/collections", "/contact"]
    assert "/inquire" in routes
    assert "/offsite" not in routes


def test_browser_routes_to_check_ignores_invisible_generated_links():
    routes = product_studio_gates._browser_routes_to_check(
        "http://127.0.0.1:3000/",
        [
            {"tag": "a", "text": "Start inquiry", "href": "/contact", "visible": False},
            {"tag": "a", "text": "Docs", "href": "/docs", "rect": {"visible": False}},
        ],
        request="Build a single-page landing page for Nexus Forge, not a four-page website.",
    )

    assert routes == ["/"]


def test_browser_hash_anchors_to_check_collects_same_page_nav():
    anchors = product_studio_gates._browser_hash_anchors_to_check(
        "http://127.0.0.1:3000/",
        [
            {"tag": "a", "text": "Process", "href": "#process"},
            {"tag": "a", "text": "Concierge", "href": "http://127.0.0.1:3000/#concierge"},
            {"tag": "a", "text": "Email", "href": "mailto:hello@example.com"},
            {"tag": "a", "text": "Offsite", "href": "https://example.com/#bad"},
        ],
    )

    assert anchors == [
        {"anchor": "#process", "text": "Process"},
        {"anchor": "#concierge", "text": "Concierge"},
    ]


def test_browser_quality_gate_fails_blank_hash_anchor(tmp_path, monkeypatch):
    screenshot = tmp_path / "anchor.png"
    screenshot.write_bytes(b"png")

    monkeypatch.setattr(
        product_studio_gates.browser_playwright,
        "visual_audit",
        lambda url, screenshot_dir=None, viewports=None: {
            "ok": True,
            "screenshots": [str(screenshot)],
            "findings": [],
            "contexts": [
                {
                    "viewport": {"label": "anchor-process", "width": 1440, "height": 900},
                    "context": {"page_text": "EmberVault Atelier Collections Process Concierge"},
                    "visual": {
                        "firstViewportTextLength": 48,
                        "bodyHeight": 2800,
                        "viewport": {"width": 1440, "height": 900},
                        "headings": [],
                    },
                }
            ],
        },
    )
    gates = [
        {
            "id": "browser_check",
            "status": "passed",
            "url": "http://127.0.0.1:3000/",
            "metadata": {
                "context": {
                    "url": "http://127.0.0.1:3000/",
                    "elements": [
                        {"tag": "a", "text": "Process", "href": "#process"},
                        {"tag": "a", "text": "Concierge", "href": "#concierge"},
                    ],
                }
            },
        }
    ]

    gate = product_studio_gates._browser_quality_gate(
        tmp_path,
        gates,
        tmp_path,
        required=True,
        request="Build a landing page for EmberVault.",
    )

    assert gate["status"] == "failed"
    assert gate["metadata"]["route_smoke"]["status"] == "failed"
    assert any("blank or weak" in step["detail"] for step in gate["metadata"]["route_smoke"]["steps"])


def test_contract_route_smoke_uses_web_project_contract_not_acceptance_text(tmp_path):
    log_root = tmp_path / ".friday" / "product-studio" / "gates" / "logs"
    log_root.mkdir(parents=True)
    contract = tmp_path / "src" / "lib" / "webProjectContract.ts"
    contract.parent.mkdir(parents=True)
    contract.write_text(
        """
export const webProject = {
  acceptance: ['Every requested page/route has a real Next.js App Router file.', 'Route files stay thin and compose feature/page components.'],
  routes: [
    { id: 'home', route: '/' },
    { id: 'intake', route: '/intake' },
    { id: 'reviews', route: '/reviews' }
  ]
} as const;
""",
        encoding="utf-8",
    )

    routes = product_studio_gates._contract_routes_from_log_root(log_root)

    assert routes == ["/", "/intake", "/reviews"]
    assert "/a-real-with-a-thin-app" not in routes
    assert "/feature-component" not in routes


def test_browser_check_recovers_from_passing_visual_review(tmp_path):
    screenshot = tmp_path / "desktop.png"
    screenshot.write_bytes(b"png")
    browser_gate = {
        "id": "browser_check",
        "label": "Browser check",
        "group": "browser",
        "status": "failed",
        "required": True,
        "executed": True,
        "summary": "BrowserType.launch: Connection closed while reading from the driver",
        "url": "http://127.0.0.1:3000/",
        "evidence": [str(tmp_path / "browser-check.json")],
        "metadata": {"ok": False, "detail": "BrowserType.launch: Connection closed while reading from the driver"},
    }
    visual_gate = {
        "id": "browser_visual_review",
        "status": "passed",
        "url": "http://127.0.0.1:3000/",
        "screenshot": str(screenshot),
        "evidence": [str(screenshot)],
        "metadata": {
            "screenshots": [str(screenshot)],
            "contexts": [
                {
                    "context": {
                        "url": "http://127.0.0.1:3000/",
                        "elements": [{"tag": "a", "text": "Nexus Forge", "href": "/", "visible": True}],
                    }
                }
            ],
        },
    }

    recovered = product_studio_gates._recover_browser_gate_from_visual_review(browser_gate, visual_gate, tmp_path)

    assert recovered is not None
    assert recovered["status"] == "passed"
    assert recovered["metadata"]["source"] == "browser_visual_review_recovery"
    assert recovered["metadata"]["context"]["elements"][0]["text"] == "Nexus Forge"
    assert str(screenshot) in recovered["evidence"]
    assert (tmp_path / "browser-check-recovered.json").exists()


def test_browser_visual_review_gate_fails_incoherent_developer_tool_hero(tmp_path, monkeypatch):
    screenshot = tmp_path / "desktop.png"
    screenshot.write_bytes(b"png")

    monkeypatch.setattr(
        product_studio_gates.browser_playwright,
        "visual_audit",
        lambda url, screenshot_dir=None: {
            "ok": True,
            "screenshots": [str(screenshot)],
            "findings": [],
            "contexts": [
                {
                    "viewport": {"label": "desktop", "width": 1440, "height": 900},
                    "visual": {
                        "headings": [
                            {"tag": "h1", "text": "The backend for the of indie hackers. next generation", "fontSize": 58, "height": 180, "bottom": 450}
                        ],
                        "images": [
                            {
                                "alt": "Contributor",
                                "complete": True,
                                "naturalWidth": 512,
                                "naturalHeight": 512,
                                "rect": {"visible": True, "top": 140, "width": 580, "height": 580},
                            }
                        ],
                    },
                }
            ],
        },
    )

    gate = product_studio_gates._browser_visual_review_gate(
        tmp_path,
        "http://127.0.0.1:3000",
        tmp_path,
        required=True,
        request="Build a landing page for Nexus Forge, an open-source backend-as-a-service developer tool with SDK docs.",
    )

    assert gate["status"] == "failed"
    assert "incoherent visible headline" in gate["summary"]
    assert any("stock/person portrait" in item for item in gate["metadata"]["findings"])


def test_browser_visual_review_gate_fails_bad_rendered_ui(tmp_path, monkeypatch):
    screenshot = tmp_path / "desktop.png"
    screenshot.write_bytes(b"png")

    monkeypatch.setattr(
        product_studio_gates.browser_playwright,
        "visual_audit",
        lambda url, screenshot_dir=None: {
            "ok": False,
            "screenshots": [str(screenshot)],
            "findings": ["desktop: H1 font is too large (112px)."],
            "contexts": [],
        },
    )

    gate = product_studio_gates._browser_visual_review_gate(tmp_path, "http://127.0.0.1:3000", tmp_path, required=True)

    assert gate["status"] == "failed"
    assert "H1 font is too large" in gate["summary"]
    assert str(screenshot) in gate["evidence"]
    assert (tmp_path / "browser-visual-review.md").exists()


def test_browser_visual_review_gate_fails_shallow_requested_landing_page(tmp_path, monkeypatch):
    screenshot = tmp_path / "desktop.png"
    screenshot.write_bytes(b"png")

    monkeypatch.setattr(
        product_studio_gates.browser_playwright,
        "visual_audit",
        lambda url, screenshot_dir=None: {
            "ok": True,
            "screenshots": [str(screenshot)],
            "findings": [],
            "contexts": [
                {
                    "viewport": {"label": "desktop", "width": 1440, "height": 900},
                    "context": {
                        "page_text": "Nexus Forge Docs Marketplace Pricing The AI + Web3 Backend You Own. Self-hosted open-source BaaS."
                    },
                    "visual": {
                        "bodyHeight": 900,
                        "viewport": {"width": 1440, "height": 900},
                        "headings": [
                            {"tag": "h1", "text": "The AI + Web3 Backend You Own.", "visible": True},
                            {"tag": "h2", "text": "Nexus Forge", "visible": True},
                        ],
                        "images": [],
                    },
                }
            ],
        },
    )

    gate = product_studio_gates._browser_visual_review_gate(
        tmp_path,
        "http://127.0.0.1:3000",
        tmp_path,
        required=True,
        request="Build a landing page for Nexus Forge with product proof, capabilities, how it works, security, marketplace story, and CTAs.",
    )

    assert gate["status"] == "failed"
    assert any("insufficient landing-page depth" in item for item in gate["metadata"]["findings"])


def test_browser_visual_review_does_not_treat_internal_proof_report_as_landing_sections(tmp_path, monkeypatch):
    screenshot = tmp_path / "desktop.png"
    screenshot.write_bytes(b"png")

    monkeypatch.setattr(
        product_studio_gates.browser_playwright,
        "visual_audit",
        lambda url, screenshot_dir=None: {
            "ok": True,
            "screenshots": [str(screenshot)],
            "findings": [],
            "contexts": [
                {
                    "viewport": {"label": "desktop", "width": 1440, "height": 900},
                    "context": {"page_text": "KineticGrid Energy Home Platform Case Studies Contact Microgrid solar battery demand outage building telemetry."},
                    "visual": {
                        "bodyHeight": 900,
                        "viewport": {"width": 1440, "height": 900},
                        "headings": [{"tag": "h1", "text": "Energy risk before outages", "visible": True}],
                        "images": [],
                    },
                }
            ],
        },
    )

    gate = product_studio_gates._browser_visual_review_gate(
        tmp_path,
        "http://127.0.0.1:3000",
        tmp_path,
        required=True,
        request=(
            "Build a production-quality 4-page website for KineticGrid Energy with final proof report, "
            "artifacts, screenshots, and market readiness gates. Pages must be Home, Platform, Case Studies, and Contact."
        ),
    )

    assert gate["status"] == "passed"
    assert not any("insufficient landing-page depth" in item for item in gate["metadata"]["findings"])


def test_browser_visual_review_gate_fails_energy_wrong_domain_copy(tmp_path, monkeypatch):
    screenshot = tmp_path / "desktop.png"
    screenshot.write_bytes(b"png")

    monkeypatch.setattr(
        product_studio_gates.browser_playwright,
        "visual_audit",
        lambda url, screenshot_dir=None: {
            "ok": True,
            "screenshots": [str(screenshot)],
            "findings": [],
            "contexts": [
                {
                    "viewport": {"label": "desktop", "width": 1440, "height": 900},
                    "context": {
                        "page_text": (
                            "KineticGrid Energy Home About Services Contact "
                            "Construction Services for contractor handover and jobsite safety."
                        )
                    },
                    "visual": {
                        "bodyHeight": 1400,
                        "viewport": {"width": 1440, "height": 900},
                        "headings": [{"tag": "h1", "text": "Construction services", "visible": True}],
                        "images": [],
                    },
                }
            ],
        },
    )

    gate = product_studio_gates._browser_visual_review_gate(
        tmp_path,
        "http://127.0.0.1:3000",
        tmp_path,
        required=True,
        request=(
            "Build a production-quality 4-page Next.js website for KineticGrid Energy, a climate-tech company "
            "for commercial building microgrids, solar, batteries, demand spikes, and outage risk. "
            "Pages must be Home, Platform, Case Studies, and Contact."
        ),
    )

    assert gate["status"] == "failed"
    assert any("wrong-domain copy" in item for item in gate["metadata"]["findings"])
    assert any("missing requested page labels" in item for item in gate["metadata"]["findings"])


def test_browser_visual_review_gate_fails_climate_risk_luxury_nav_and_cta(tmp_path, monkeypatch):
    screenshot = tmp_path / "desktop.png"
    screenshot.write_bytes(b"png")

    monkeypatch.setattr(
        product_studio_gates.browser_playwright,
        "visual_audit",
        lambda url, screenshot_dir=None: {
            "ok": True,
            "screenshots": [str(screenshot)],
            "findings": [],
            "contexts": [
                {
                    "viewport": {"label": "desktop", "width": 1440, "height": 900},
                    "context": {
                        "page_text": (
                            "EmberVault Atelier Collections Process Concierge Private Inquiry "
                            "Crafted for private clients who notice the difference. "
                            "EmberVault provides production-quality climate-risk intelligence for the permanent legacy. "
                            "Quiet confidence in every detail. Request Concierge Access."
                        )
                    },
                    "visual": {
                        "bodyHeight": 3212,
                        "viewport": {"width": 1440, "height": 900},
                        "headings": [
                            {
                                "tag": "h1",
                                "text": "Crafted for private clients who notice the difference.",
                                "visible": True,
                            }
                        ],
                        "images": [],
                    },
                }
            ],
        },
    )

    gate = product_studio_gates._browser_visual_review_gate(
        tmp_path,
        "http://127.0.0.1:3000",
        tmp_path,
        required=True,
        request=(
            "Build a production-quality landing page for EmberVault, a premium climate-risk intelligence "
            "platform for commercial property owners covering wildfire, flood, heat, insurance risk, "
            "maintenance, tenant-impact risk, and property portfolios."
        ),
    )

    assert gate["status"] == "failed"
    assert any("wrong-domain copy" in item for item in gate["metadata"]["findings"])
    assert any("private inquiry" in item.lower() or "concierge" in item.lower() for item in gate["metadata"]["findings"])


def test_browser_visual_review_gate_passes_with_screenshots(tmp_path, monkeypatch):
    screenshot = tmp_path / "desktop.png"
    screenshot.write_bytes(b"png")

    monkeypatch.setattr(
        product_studio_gates.browser_playwright,
        "visual_audit",
        lambda url, screenshot_dir=None: {
            "ok": True,
            "screenshots": [str(screenshot)],
            "findings": [],
            "contexts": [],
        },
    )

    gate = product_studio_gates._browser_visual_review_gate(tmp_path, "http://127.0.0.1:3000", tmp_path, required=True)

    assert gate["status"] == "passed"
    assert str(screenshot) in gate["evidence"]


def test_ux_copy_quality_gate_rejects_raw_prompt_and_machined_title(tmp_path):
    product_plan = tmp_path / "src" / "lib" / "productPlan.ts"
    home_page = tmp_path / "src" / "components" / "Landing" / "HomePage.tsx"
    workspace = tmp_path / "src" / "components" / "Workspace" / "WorkspaceConsole.tsx"
    css = tmp_path / "src" / "app" / "globals.css"
    for path in [product_plan, home_page, workspace, css]:
        path.parent.mkdir(parents=True, exist_ok=True)
    product_plan.write_text(
        """
export const productPlan = {
  name: 'UniversityManagementPilot',
  request: 'Build a web-app for a university management dashboard',
};
""",
        encoding="utf-8",
    )
    home_page.write_text("<h1>{productPlan.name}</h1><p>{productPlan.request}</p><h2>Launch signal</h2>", encoding="utf-8")
    workspace.write_text("<Badge>AI everyday tool</Badge><p>{plan.request}</p>", encoding="utf-8")
    css.write_text("h1 { font-size: clamp(2.4rem, 6vw, 5rem); }", encoding="utf-8")

    gate = product_studio_gates._ux_copy_quality_gate(tmp_path, tmp_path)

    assert gate["status"] == "failed"
    assert any("raw user request" in issue for issue in gate["metadata"]["issues"])
    assert any("not human-readable" in issue for issue in gate["metadata"]["issues"])


def test_ux_copy_quality_gate_rejects_climate_risk_luxury_drift(tmp_path):
    native_content = tmp_path / "src" / "lib" / "stitchNativeContent.ts"
    native_content.parent.mkdir(parents=True, exist_ok=True)
    native_content.write_text(
        """
export const stitchNativeContent = {
  productName: "EmberVault",
  summary: "Climate-risk intelligence for commercial property owners.",
  pages: {
    home: {
      title: "EmberVault",
      bodyHtml: "<main><nav>Atelier Collections Process Concierge</nav><h1>Crafted for private clients who notice the difference.</h1><p>EmberVault provides production-quality climate-risk intelligence for the permanent legacy. Quiet confidence in every detail.</p><button>Private Inquiry</button><button>Request Concierge Access</button></main>"
    }
  }
};
""",
        encoding="utf-8",
    )

    gate = product_studio_gates._ux_copy_quality_gate(
        tmp_path,
        tmp_path,
        request=(
            "Build a production-quality landing page for EmberVault, a premium climate-risk intelligence "
            "platform for commercial property owners covering wildfire, flood, heat, insurance risk, "
            "maintenance, tenant-impact risk, and property portfolios."
        ),
    )

    assert gate["status"] == "failed"
    assert any("wrong-domain language" in issue for issue in gate["metadata"]["issues"])
    assert any("concierge" in issue.lower() for issue in gate["metadata"]["issues"])


def test_ux_copy_quality_gate_rejects_generic_field_service_copy(tmp_path):
    product_plan = tmp_path / "src" / "lib" / "productPlan.ts"
    home_page = tmp_path / "src" / "components" / "Landing" / "HomePage.tsx"
    workspace = tmp_path / "src" / "components" / "Workspace" / "WorkspaceConsole.tsx"
    css = tmp_path / "src" / "app" / "globals.css"
    for path in [product_plan, home_page, workspace, css]:
        path.parent.mkdir(parents=True, exist_ok=True)
    product_plan.write_text(
        """
export const productPlan = {
  name: 'Field Service Workspace',
  summary: 'A focused field service workspace for tracking requests, owners, approvals, decision briefs, and launch proof.',
};
""",
        encoding="utf-8",
    )
    home_page.write_text("<h1>{productPlan.name}</h1><p>{productPlan.summary}</p>", encoding="utf-8")
    workspace.write_text("<Badge>{plan.workspaceLabel}</Badge><p>{plan.summary}</p>", encoding="utf-8")
    css.write_text("h1 { overflow-wrap: anywhere; }", encoding="utf-8")

    gate = product_studio_gates._ux_copy_quality_gate(tmp_path, tmp_path)

    assert gate["status"] == "failed"
    assert any("Field service UI copy is too generic" in issue for issue in gate["metadata"]["issues"])


def test_ux_copy_quality_gate_rejects_generic_restaurant_copy(tmp_path):
    product_plan = tmp_path / "src" / "lib" / "productPlan.ts"
    home_page = tmp_path / "src" / "components" / "Landing" / "HomePage.tsx"
    workspace = tmp_path / "src" / "components" / "Workspace" / "WorkspaceConsole.tsx"
    css = tmp_path / "src" / "app" / "globals.css"
    for path in [product_plan, home_page, workspace, css]:
        path.parent.mkdir(parents=True, exist_ok=True)
    product_plan.write_text("export const productPlan = { name: 'Restaurant Shift Command OS', summary: 'A restaurant workspace for requests and approvals.' };", encoding="utf-8")
    home_page.write_text("export function HomePage() { return <p>{productPlan.summary}</p>; }", encoding="utf-8")
    workspace.write_text("export function WorkspaceConsole() { return <p>{plan.summary}</p>; }", encoding="utf-8")
    css.write_text("h1 { overflow-wrap: anywhere; }", encoding="utf-8")

    gate = product_studio_gates._ux_copy_quality_gate(tmp_path, tmp_path)

    assert gate["status"] == "failed"
    assert any("Restaurant UI copy is too generic" in issue for issue in gate["metadata"]["issues"])


def test_ux_copy_quality_gate_accepts_readable_dynamic_surfaces(tmp_path):
    product_plan = tmp_path / "src" / "lib" / "productPlan.ts"
    home_page = tmp_path / "src" / "components" / "Landing" / "HomePage.tsx"
    workspace = tmp_path / "src" / "components" / "Workspace" / "WorkspaceConsole.tsx"
    css = tmp_path / "src" / "app" / "globals.css"
    for path in [product_plan, home_page, workspace, css]:
        path.parent.mkdir(parents=True, exist_ok=True)
    product_plan.write_text(
        """
export const productPlan = {
  name: 'University Management Dashboard',
  summary: 'Registrar-grade dashboard for approvals, fees, lecturers, and reporting.',
};
""",
        encoding="utf-8",
    )
    home_page.write_text("<h1>{productPlan.name}</h1><p>{productPlan.summary}</p>", encoding="utf-8")
    workspace.write_text("<Badge>{plan.workspaceLabel}</Badge><p>{plan.summary}</p>", encoding="utf-8")
    css.write_text("h1 { overflow-wrap: anywhere; }", encoding="utf-8")

    gate = product_studio_gates._ux_copy_quality_gate(tmp_path, tmp_path)

    assert gate["status"] == "passed"


def test_ux_copy_quality_gate_accepts_stitch_native_content_surface(tmp_path):
    native_content = tmp_path / "src" / "lib" / "stitchNativeContent.ts"
    native_component = tmp_path / "src" / "components" / "Stitch" / "StitchNativePage.tsx"
    css = tmp_path / "src" / "app" / "globals.css"
    for path in [native_content, native_component, css]:
        path.parent.mkdir(parents=True, exist_ok=True)
    native_content.write_text(
        """
export const stitchNativeContent = {
  "meta": { "productName": "Nexus Forge" },
  "pages": {
    "home": {
      "summary": "Self-hosted backend forge for auth, schema, API routes, AI agents, Web3 modules, pricing, CLI install, and docs.",
      "title": "Build the backend your AI app needs without giving up control."
    }
  }
} as const;
""",
        encoding="utf-8",
    )
    native_component.write_text("export function StitchNativePage(){ return <main>Nexus Forge</main>; }\n", encoding="utf-8")
    css.write_text("h1 { overflow-wrap: anywhere; }\n", encoding="utf-8")

    gate = product_studio_gates._ux_copy_quality_gate(tmp_path, tmp_path)

    assert gate["status"] == "passed"
    assert gate["metadata"]["product_name"] == "Nexus Forge"


def test_ux_copy_quality_gate_accepts_web_contract_surface(tmp_path):
    contract = tmp_path / "src" / "lib" / "webProjectContract.ts"
    contract.parent.mkdir(parents=True)
    contract.write_text(
        """
export const webProject = {
  product_name: 'PermitFlow Command Center',
  request_summary: 'Designed around permit intake, plan reviews, inspections, applicant updates, and audit proof.',
  pages: [
    { id: 'intake', summary: 'Track permit intake, fee holds, blockers, owners, and proof.', route: '/intake' }
  ]
} as const;
""",
        encoding="utf-8",
    )
    component = tmp_path / "src" / "components" / "WebContract" / "WebContractPage.tsx"
    component.parent.mkdir(parents=True)
    component.write_text("export function WebContractPage(){ return <main>Permit intake proof</main>; }\n", encoding="utf-8")
    css = tmp_path / "src" / "app" / "globals.css"
    css.parent.mkdir(parents=True)
    css.write_text("h1 { overflow-wrap: anywhere; }\n", encoding="utf-8")

    gate = product_studio_gates._ux_copy_quality_gate(tmp_path, tmp_path)

    assert gate["status"] == "passed"
    assert gate["metadata"]["product_name"] == "PermitFlow Command Center"
    assert "src\\lib\\webProjectContract.ts" in gate["metadata"]["files_checked"]


def test_browser_gate_attaches_playwright_install_logs_when_blocked(tmp_path, monkeypatch):
    install_log = tmp_path / "playwright-install.log"

    monkeypatch.setattr(
        product_studio_gates.browser_playwright,
        "ensure_available",
        lambda log_root: {
            "available": False,
            "reason": "playwright_install_failed",
            "install_logs": [str(install_log)],
        },
    )

    gate = product_studio_gates._browser_gate(tmp_path, "http://127.0.0.1:3000", tmp_path, required=True)

    assert gate["status"] == "blocked"
    assert str(install_log) in gate["evidence"]


def test_stop_process_terminates_preview_process_tree(monkeypatch):
    killed = []

    class FakeProcess:
        pid = 12345
        returncode = None

        def poll(self):
            return None

        def wait(self, timeout):
            return 0

        def kill(self):
            raise AssertionError("process tree termination should run first")

    monkeypatch.setattr(product_studio_gates.command_runner, "terminate_process_tree", lambda pid: killed.append(pid))

    product_studio_gates._stop_process({"process": FakeProcess(), "log_handle": None})

    assert killed == [12345]


def test_request_visual_findings_rejects_missing_requested_brand():
    result = {
        "contexts": [
            {
                "viewport": {"label": "desktop", "width": 1440, "height": 900},
                "context": {
                    "page_text": "CLIMATE INTEL OPERATIONS Operations Overview microgrid wildfire flood heat portfolio resilience."
                },
                "visual": {
                    "headings": [{"tag": "h1", "text": "Operations Overview", "visible": True}],
                    "viewport": {"width": 1440, "height": 900},
                    "bodyHeight": 1600,
                    "firstViewportTextLength": 180,
                },
            }
        ]
    }

    findings = product_studio_gates._request_visual_findings(
        result,
        "Build a production-quality landing page for TerraScope Risk, a climate and property-risk intelligence platform.",
    )

    assert any("TerraScope Risk" in finding for finding in findings)


def test_visual_findings_reject_uncompiled_utility_class_layout():
    contexts = [
        {
            "viewport": {"label": "desktop", "width": 1440, "height": 900},
            "visual": {
                "viewport": {"width": 1440, "height": 900},
                "bodyHeight": 1500,
                "firstViewportTextLength": 400,
                "headings": [{"tag": "h1", "text": "Operations Overview", "fontSize": 64, "height": 80, "bottom": 120}],
                "interactives": [],
                "images": [],
                "canvases": [],
                "clipped": [],
                "styleHealth": {
                    "classedVisible": 42,
                    "utilityStyledChecks": 60,
                    "utilityStyledMisses": 42,
                    "utilityMissRatio": 0.7,
                    "largeWhiteBorderBoxes": 9,
                    "unstyledUtilityElements": 18,
                },
            },
        }
    ]

    findings = browser_playwright._visual_findings(contexts)

    assert any("utility-class styling appears uncompiled" in finding for finding in findings)
    assert any("raw bordered boxes" in finding for finding in findings)

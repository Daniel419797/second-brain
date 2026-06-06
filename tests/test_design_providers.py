import json
from pathlib import Path

from core import design_director, design_providers, provider_readiness, style_profiles


def _config(values):
    defaults = {
        "design_provider_chain": "stitch>local_style_memory>v0",
        "design_stitch_enabled": True,
        "design_stitch_api_key_env": "STITCH_API_KEY",
        "design_stitch_sdk_package": "@google/stitch-sdk",
        "design_stitch_project_id": "",
        "design_stitch_model_id": "GEMINI_3_1_PRO",
        "design_stitch_timeout_seconds": 420,
        "design_stitch_prompt_budget_chars": 12000,
        "design_stitch_request_timeout_ms": 360000,
        "design_stitch_generate_attempts": 1,
        "design_stitch_fallback_variants": True,
        "design_external_calls_require_approval": True,
        "design_critique_enabled": True,
        "design_critique_auto_run": False,
        "design_variant_count": 3,
        "design_critique_min_score": 72,
        "design_variant_visual_review_enabled": False,
        "design_download_remote_assets": True,
        "design_frontend_handoff_required": True,
        "design_local_fallback_on_stitch_failure": True,
        "design_stitch_required_for_web": True,
        "design_v0_enabled": True,
        "design_v0_api_key_env": "V0_API_KEY",
        "design_v0_free_only": True,
        "design_v0_free_verified": False,
        "design_style_memory_enabled": True,
        "design_style_memory_allow_paid_sources": False,
    }
    return lambda key, default=None: {**defaults, **values}.get(key, default)


def test_design_provider_policy_defaults_to_stitch_then_free_local_style(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    monkeypatch.delenv("STITCH_API_KEY", raising=False)
    monkeypatch.delenv("V0_API_KEY", raising=False)
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: False)

    status = design_providers.status(root=tmp_path)

    assert status["providers"]["stitch"]["ready"] is False
    assert status["providers"]["v0"]["ready"] is False
    assert status["providers"]["v0"]["free_only"] is True
    assert status["providers"]["local_style_memory"]["ready"] is True
    assert status["selected"]["ui_design_agent"] == "local_style_memory"
    assert status["selected"]["frontend_agent"] == "local_style_memory"


def test_stitch_becomes_ui_design_provider_when_key_and_sdk_exist(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    monkeypatch.setenv("STITCH_API_KEY", "configured")
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: True)

    status = design_providers.status(probe=True, root=tmp_path)

    assert status["providers"]["stitch"]["ready"] is True
    assert status["selected"]["ui_design_agent"] == "stitch"
    assert status["providers"]["stitch"]["approval_required"] is True


def test_stitch_key_can_be_read_from_local_env_file(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    monkeypatch.delenv("STITCH_API_KEY", raising=False)
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: True)
    (tmp_path / ".env").write_text("STITCH_API_KEY=configured-from-file\n", encoding="utf-8")

    status = design_providers.status(probe=True, root=tmp_path)

    assert status["providers"]["stitch"]["credential_configured"] is True
    assert status["selected"]["ui_design_agent"] == "stitch"


def test_stitch_runner_receives_key_from_local_env_file(monkeypatch, tmp_path):
    monkeypatch.setattr(design_providers, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(design_providers, "config_value", _config({"design_stitch_timeout_seconds": 1}))
    monkeypatch.delenv("STITCH_API_KEY", raising=False)
    (tmp_path / ".env").write_text("STITCH_API_KEY=configured-from-file\n", encoding="utf-8")
    captured = {}

    class Process:
        returncode = 0
        args = ["node"]
        pid = 123

        def communicate(self, timeout=None):
            return (
                '{"ok":true,"projectId":"project-1","htmlUrl":"https://example.com/html","imageUrl":"https://example.com/image"}\n',
                "",
            )

    def fake_popen(*args, **kwargs):
        captured["env"] = kwargs.get("env") or {}
        return Process()

    monkeypatch.setattr(design_providers.subprocess, "Popen", fake_popen)

    result = design_providers._run_stitch_sdk({"root": str(tmp_path), "stitch_prompt": "Design", "product_name": "Demo", "design_context": {"product_goal": "Demo goal"}})

    assert result["ok"] is True
    assert captured["env"]["STITCH_API_KEY"] == "configured-from-file"
    assert captured["env"]["FRIDAY_STITCH_VARIANT_TIMEOUT_MS"] == "60000"
    assert captured["env"]["FRIDAY_STITCH_FALLBACK_VARIANTS"] == "1"
    assert captured["env"]["FRIDAY_STITCH_COMPILED_PROMPT"] == "Design"
    assert captured["env"]["FRIDAY_STITCH_PROMPT_BUDGET_CHARS"] == "12000"
    assert captured["env"]["FRIDAY_STITCH_PROMPT_FULL_LENGTH"] == "6"
    assert json.loads(captured["env"]["FRIDAY_STITCH_CONTEXT_JSON"])["product_goal"] == "Demo goal"
    assert (tmp_path / ".friday" / "design" / "stitch-result.json").exists()


def test_stitch_runner_writes_sanitized_raw_generate_response(monkeypatch, tmp_path):
    monkeypatch.setattr(design_providers, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(design_providers, "config_value", _config({"design_stitch_timeout_seconds": 1}))
    raw_payload = {
        "ok": False,
        "status": "no_screen",
        "provider": "stitch",
        "modelId": "GEMINI_3_1_PRO",
        "projectId": "project-1",
        "error": "Stitch generate_screen_from_text returned no screen in known projection paths.",
        "projectionPathsTried": ["outputComponents[0].design.screens", "screens"],
        "rawGenerate": {
            "apiKey": "secret-key",
            "outputComponents": [
                {
                    "text": "Try a narrower prompt.",
                    "debugUrl": "https://stitch.example/raw?token=signed",
                }
            ],
        },
    }

    class Process:
        returncode = 2
        args = ["node"]
        pid = 124

        def communicate(self, timeout=None):
            return (design_providers.json.dumps(raw_payload) + "\n", "")

    monkeypatch.setattr(design_providers.subprocess, "Popen", lambda *args, **kwargs: Process())

    result = design_providers._run_stitch_sdk({"root": str(tmp_path), "stitch_prompt": "Design", "product_name": "Demo"})
    raw_path = tmp_path / ".friday" / "design" / "stitch-raw-generate-response.json"
    raw = design_providers.json.loads(raw_path.read_text(encoding="utf-8"))

    assert result["ok"] is False
    assert result["status"] == "no_screen"
    assert "no screen" in result["summary"]
    assert raw["apiKey"] == "[redacted]"
    assert raw["outputComponents"][0]["debugUrl"] == "https://stitch.example/raw?[redacted]"
    assert str(raw_path) in result["artifacts"]


def test_stitch_payload_sanitizer_redacts_secrets_and_url_queries():
    sanitized = design_providers._sanitize_stitch_payload(
        {
            "accessToken": "secret",
            "htmlCode": {"downloadUrl": "https://example.com/file.html?X-Goog-Signature=secret"},
            "nested": [{"authorization": "Bearer secret"}],
        }
    )

    assert sanitized["accessToken"] == "[redacted]"
    assert sanitized["htmlCode"]["downloadUrl"] == "https://example.com/file.html?[redacted]"
    assert sanitized["nested"][0]["authorization"] == "[redacted]"


def test_stitch_runner_timeout_returns_failed_result(monkeypatch, tmp_path):
    monkeypatch.setattr(design_providers, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(design_providers, "config_value", _config({"design_stitch_timeout_seconds": 1}))
    killed = {}

    class Process:
        returncode = None
        args = ["node"]
        pid = 456

        def communicate(self, timeout=None):
            if timeout is not None:
                raise design_providers.subprocess.TimeoutExpired(self.args, timeout)
            return ("", "")

    monkeypatch.setattr(design_providers.subprocess, "Popen", lambda *args, **kwargs: Process())
    monkeypatch.setattr(design_providers.command_runner, "terminate_process_tree", lambda pid: killed.setdefault("pid", pid))

    result = design_providers._run_stitch_sdk({"root": str(tmp_path), "stitch_prompt": "Design", "product_name": "Demo"})

    assert result["status"] == "timeout"
    assert killed["pid"] == 456
    assert (tmp_path / ".friday" / "design" / "stitch-run.log").exists()


def test_stitch_reliability_retries_timeout_and_writes_report(monkeypatch, tmp_path):
    monkeypatch.setattr(design_providers, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(
        design_providers,
        "config_value",
        _config({"design_stitch_max_attempts": 2, "design_stitch_retry_backoff_seconds": 0, "design_stitch_required_for_web": False}),
    )
    calls = []

    def fake_run(brief, *, variant_count=1):
        calls.append(brief.get("stitch_attempt") or {})
        if len(calls) == 1:
            return {
                "ok": False,
                "status": "timeout",
                "provider": "stitch",
                "summary": "Stitch SDK timed out after 300 seconds.",
                "artifacts": [str(tmp_path / ".friday" / "design" / "stitch-run-base-attempt-1.log")],
            }
        return {
            "ok": True,
            "status": "generated",
            "provider": "stitch",
            "summary": "Stitch SDK generated a UI screen.",
            "result": {"ok": True, "modelId": "GEMINI_3_1_PRO", "projectId": "p1", "screenId": "s1"},
            "artifacts": [str(tmp_path / ".friday" / "design" / "stitch-result-base-attempt-2.json")],
        }

    monkeypatch.setattr(design_providers, "_run_stitch_sdk", fake_run)

    result = design_providers._run_stitch_reliable(
        {"root": str(tmp_path), "stitch_prompt": "Design", "product_name": "Demo", "provider_status": {"providers": {"stitch": {"ready": True}}}},
        variant_count=2,
        purpose="base",
    )

    report_path = tmp_path / ".friday" / "design" / "stitch-reliability-report-base.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert len(calls) == 2
    assert calls[0]["attempt"] == 1
    assert calls[1]["attempt"] == 2
    assert report["attempt_count"] == 2
    assert report["project_id"] == "p1"
    assert report["screen_id"] == "s1"
    assert str(report_path) in result["artifacts"]


def test_stitch_debug_reads_latest_reliability_report(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_stitch_required_for_web": False}))
    monkeypatch.setenv("STITCH_API_KEY", "configured")
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: True)
    design_root = tmp_path / ".friday" / "design"
    design_root.mkdir(parents=True)
    (design_root / "stitch-reliability-report.json").write_text(
        json.dumps({"ok": False, "status": "timeout", "attempt_count": 2, "failure_reason": "Request timed out"}),
        encoding="utf-8",
    )
    (design_root / "stitch-attempt-base-attempt-1.json").write_text(
        json.dumps({"status": "timeout", "attempt": 1}),
        encoding="utf-8",
    )

    debug = design_providers.stitch_debug(root=tmp_path)

    assert debug["provider_status"]["ready"] is True
    assert debug["latest"]["status"] == "timeout"
    assert debug["attempts"][0]["data"]["attempt"] == 1
    assert "timeout" in debug["summary"].lower() or "did not produce" in debug["summary"].lower()


def test_stitch_runner_script_retries_and_falls_back_to_generated_alternatives():
    script = design_providers._stitch_runner_script()

    assert "generateWithRetry" in script
    assert 'callTool("generate_screen_from_text"' in script
    assert "rawGenerate" in script
    assert "projectionPathsTried" in script
    assert "GEMINI_3_1_PRO" in script
    assert "variant API failed" in script
    assert "withTimeout" in script
    assert "FRIDAY_STITCH_VARIANT_TIMEOUT_MS" in script
    assert "Continuing with the base Stitch screen" in script
    assert "base Stitch screen remains eligible for critique" in script
    assert "Generated alternative" in script
    assert "FRIDAY_STITCH_MODEL_ID" in script
    assert "StitchToolClient" in script
    assert "FRIDAY_STITCH_REQUEST_TIMEOUT_MS" in script
    assert "FRIDAY_STITCH_VARIANT_DIRECTIONS" in script
    assert "FRIDAY_STITCH_CONTEXT_JSON" in script
    assert "FRIDAY_STITCH_COMPILED_PROMPT" in script
    assert "FRIDAY_STITCH_PROMPT_BUDGET_CHARS" in script
    assert "compilePromptFromContext" in script
    assert "fitPromptBudget" in script
    assert "seenVariantKeys" in script
    assert "variantCount <= 1" in script
    assert 'status: "base_generated"' in script
    assert "Base Stitch generation checkpoint captured" in script
    assert "variants.length < variantCount" in script
    assert "prompt.slice(0, 5000)" not in script
    assert "variantDirections" in script
    assert "Create genuinely distinct alternatives" in script
    assert "[friday-stitch]" in script
    assert "toolClient.close" in script
    assert "process.exitCode" in script


def test_v0_is_blocked_until_free_usage_is_verified(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setenv("V0_API_KEY", "configured")
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: False)

    monkeypatch.setattr(design_providers, "config_value", _config({"design_v0_free_verified": False}))
    blocked = design_providers.status(root=tmp_path)
    assert blocked["providers"]["v0"]["ready"] is False
    assert "free-only" in blocked["providers"]["v0"]["reason"]

    monkeypatch.setattr(design_providers, "config_value", _config({"design_v0_free_verified": True}))
    allowed = design_providers.status(root=tmp_path)
    assert allowed["providers"]["v0"]["ready"] is True


def test_design_brief_writes_provider_plan_and_style_memory(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    monkeypatch.delenv("STITCH_API_KEY", raising=False)
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: False)

    brief = design_providers.design_brief(
        "Build a web-app for university management",
        root=tmp_path,
        product_name="University Management Dashboard",
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )

    assert "Use Stitch SDK" in brief["instructions"][0]
    assert "never render them as product branding" in " ".join(brief["instructions"])
    assert "do not render NexusForge" in brief["stitch_prompt"]
    assert "NexusForge" in brief["style_profile"]["name"]
    assert brief["design_strategy"]["surface"] == "operational_dashboard"
    assert "operator cockpit" in brief["design_strategy"]["direction"]
    assert "Art direction:" in brief["stitch_prompt"]
    assert (tmp_path / ".friday" / "design" / "design-provider-plan.json").exists()
    assert (tmp_path / ".friday" / "design" / "design-brief.md").exists()
    assert (tmp_path / ".friday" / "design" / "design-context.json").exists()
    assert (tmp_path / ".friday" / "design" / "DESIGN.md").exists()


def test_design_brief_autopilot_expands_vague_website_prompt(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    monkeypatch.delenv("STITCH_API_KEY", raising=False)
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: False)

    brief = design_providers.design_brief(
        "build a website",
        root=tmp_path,
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )

    autopilot = brief["brief_autopilot"]
    assert autopilot["active"] is True
    assert autopilot["vague"] is True
    assert autopilot["product_missing"] is True
    assert autopilot["ask_only_when_needed"]["needs_user_question"] is True
    assert brief["product_name"] == "Nocturne Audio"
    assert brief["expanded_request"] != brief["request"]
    assert "FRIDAY INTENT EXPANSION" in brief["expanded_request"]
    assert autopilot["intent_expansion"]["product_company_type"]
    assert autopilot["intent_expansion"]["target_users"]
    assert autopilot["intent_expansion"]["content_sections"]
    assert any("generic SaaS" in item for item in autopilot["intent_expansion"]["rejection_rules"])
    assert autopilot["smart_defaults"]["selected_default"] == "luxury_editorial_tactile"
    assert autopilot["design_direction_generator"]["selected"] == "cinematic_product_led"
    assert autopilot["research_before_design"]["queries"]
    assert autopilot["research_before_design"]["live_research"] is False
    assert "Brief Autopilot:" in brief["stitch_prompt"]
    assert "Treat vague prompts as incomplete briefs" in brief["stitch_prompt"]
    assert "Critique before code" in brief["stitch_prompt"]
    design_doc = (tmp_path / ".friday" / "design" / "DESIGN.md").read_text(encoding="utf-8")
    assert "## Brief Autopilot" in design_doc
    assert "Nocturne Audio" in design_doc


def test_design_brief_autopilot_applies_fintech_smart_defaults(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    monkeypatch.delenv("STITCH_API_KEY", raising=False)
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: False)

    brief = design_providers.design_brief(
        "Build a website for a fintech app called Ledgerly",
        root=tmp_path,
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )

    autopilot = brief["brief_autopilot"]
    assert autopilot["active"] is True
    assert autopilot["style_missing"] is True
    assert autopilot["product_missing"] is False
    assert autopilot["industry"] == "fintech"
    assert brief["product_name"] == "Ledgerly"
    assert autopilot["smart_defaults"]["selected_default"] == "trust_clarity_precision"
    assert "trust" in autopilot["intent_expansion"]["emotional_feel"]
    assert "security" in brief["stitch_prompt"].lower()
    assert "transparent" in brief["stitch_prompt"].lower()


def test_design_brief_autopilot_keeps_fintech_landing_page_as_marketing(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    monkeypatch.delenv("STITCH_API_KEY", raising=False)
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: False)
    request = (
        "Build a Next.js landing page for a fintech app called VaultPilot. "
        "VaultPilot helps freelancers track income, taxes, invoices, and emergency savings from one calm dashboard. "
        "The page should explain the product, show trust/security proof, pricing, and a clear sign-up path."
    )

    brief = design_providers.design_brief(
        request,
        root=tmp_path,
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )

    autopilot = brief["brief_autopilot"]
    assert brief["product_name"] == "VaultPilot"
    assert brief["design_strategy"]["surface"] == "marketing_website"
    assert brief["design_context"]["user_intent"]["surface"] == "marketing_website"
    assert autopilot["surface"] == "marketing_website"
    assert autopilot["smart_defaults"]["selected_default"] == "trust_clarity_precision"
    assert autopilot["design_direction_generator"]["selected"] != "dense_operational_cockpit"
    assert "transparent fees" in brief["stitch_prompt"].lower() or "transparent" in brief["stitch_prompt"].lower()


def test_fintech_client_income_does_not_trigger_cli_developer_direction(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    monkeypatch.delenv("STITCH_API_KEY", raising=False)
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: False)
    request = (
        "Build a Next.js landing page for a fintech product called TaxNest. "
        "TaxNest helps independent consultants separate client income, quarterly taxes, invoices, retirement savings, and emergency cash before money gets messy."
    )

    assert design_director.design_strategy(request, "TaxNest", stack={"stack": "nextjs"})["industry"] == "fintech"
    brief = design_providers.design_brief(
        request,
        root=tmp_path,
        product_name="TaxNest",
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )

    autopilot = brief["brief_autopilot"]
    assert brief["design_context"]["user_intent"]["industry"] == "fintech"
    assert autopilot["smart_defaults"]["selected_default"] == "trust_clarity_precision"
    assert autopilot["design_direction_generator"]["selected"] != "terminal_product_proof"


def test_design_brief_autopilot_preserves_specific_nocturne_style(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    monkeypatch.delenv("STITCH_API_KEY", raising=False)
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: False)

    request = (
        "Build a cinematic luxury landing page for Nocturne Audio, a premium spatial-audio headphone brand. "
        "It should feel immersive, tactile, nocturnal, editorial, and product-led."
    )
    brief = design_providers.design_brief(
        request,
        root=tmp_path,
        product_name="Nocturne Audio",
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )

    autopilot = brief["brief_autopilot"]
    assert autopilot["active"] is False
    assert autopilot["style_missing"] is False
    assert autopilot["product_missing"] is False
    assert brief["expanded_request"] == brief["request"]
    assert autopilot["smart_defaults"]["selected_default"] == "luxury_editorial_tactile"
    assert autopilot["design_direction_generator"]["selected"] == "cinematic_product_led"
    assert "generic SaaS" in brief["stitch_prompt"]
    assert "full-bleed product/media hero" in brief["stitch_prompt"]


def test_design_brief_builds_rich_stitch_context(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    monkeypatch.delenv("STITCH_API_KEY", raising=False)
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: False)
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "nexus-forge",
                "scripts": {"dev": "next dev", "build": "next build", "test": "vitest"},
                "dependencies": {"next": "latest", "react": "latest"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "src" / "app").mkdir(parents=True)
    (tmp_path / "src" / "components" / "ui").mkdir(parents=True)

    request = (
        "Build a polished production-quality landing page for Nexus Forge as a fresh Next.js web-app project. "
        "Nexus Forge is an open-source, self-hosted no-code Backend-as-a-Service with auth, databases, "
        "API routes, AI agents, Web3 modules, plugin marketplace, CLI install, docs, and x402 API monetization."
    )
    brief = design_providers.design_brief(
        request,
        root=tmp_path,
        product_name="Nexus Forge",
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )

    context = brief["design_context"]
    assert context["product_goal"]
    assert context["user_intent"]["industry"] == "developer_tools"
    assert "technical founders" in context["target_audience"]
    assert context["emotional_intent"]
    assert any(item["name"] == "Docs-first developer landing page" for item in context["inspiration_references"])
    assert "Start building" in context["content_model"]["primary_ctas"]
    assert "schema builder" in context["content_model"]["proof_objects"]
    assert context["code_context"]["package_manager"] == ""
    assert context["code_context"]["scripts"]["build"] == "next build"
    assert "src/app" in context["code_context"]["existing_paths"]
    assert context["design_system_context"]["style_profile"]["id"] == "nexus_forge_nextjs"
    assert context["creative_brief"]["primary_objection"]
    assert context["composition_spec"]["archetype"] == "docs_terminal"
    assert "Docs And Terminal First" in context["composition_spec"]["archetype_name"]
    assert "Hero left" not in " ".join(context["composition_spec"]["first_viewport"])
    assert any(item["id"] == "architecture_diagram" for item in context["composition_spec"]["allowed_archetypes"])
    assert context["experience_mode"]["mode"] == "product_demo_motion"
    assert "Framer Motion" in context["experience_mode"]["recommended_libraries"]
    assert any(item["section"] == "Backend capabilities" for item in context["section_blueprint"])
    assert "Build the backend your AI app needs without giving up control." in context["copy_bank"]["headline_directions"]
    assert "CLI command block with copy affordance" in context["component_inventory"]
    assert context["output_contract"]["rejection_if"]
    assert context["brand_system"]["tokens"]["accent"]
    assert context["site_continuity"]["site_design_system"]["product_name"] == "Nexus Forge"
    assert "visual_reference_memory" in context
    assert context["taxonomy_prompt_profile"]["message"]

    prompt = brief["stitch_prompt"]
    assert len(prompt) <= 12000
    assert brief["stitch_prompt_compilation"]["budget"] == 12000
    assert brief["stitch_prompt_compilation"]["compiled_length"] <= 12000
    assert brief["stitch_prompt_compilation"]["raw_length"] >= brief["stitch_prompt_compilation"]["compiled_length"]
    assert "Design context package:" in prompt
    assert "Creative brief:" in prompt
    assert "Concrete page composition:" in prompt
    assert "Composition archetype:" in prompt
    assert "Do not default to a left-text/right-card split hero" in prompt
    assert "Experience mode and motion/3D contract:" in prompt
    assert "Product Demo Motion" in prompt
    assert "Brand system:" in prompt
    assert "Section-by-section blueprint:" in prompt
    assert "Copy and content requirements:" in prompt
    assert "Component inventory to design:" in prompt
    assert "Output contract:" in prompt
    assert "Product goal:" in prompt
    assert "Emotional intent:" in prompt
    assert "Inspiration references" in prompt
    assert "Code/product signals:" in prompt
    assert "Design-system context:" in prompt
    assert "DESIGN.md" in prompt
    assert (tmp_path / ".friday" / "design" / "design-context.json").exists()
    assert (tmp_path / ".friday" / "design" / "stitch-prompt.md").exists()
    assert (tmp_path / ".friday" / "design" / "site-design-system.json").exists()
    design_doc = (tmp_path / ".friday" / "design" / "DESIGN.md").read_text(encoding="utf-8")
    assert "Docs-first developer landing page" in design_doc
    assert "## Brand System" in design_doc
    assert "## Site Continuity" in design_doc
    assert "## Visual Reference Memory" in design_doc
    assert "## Composition" in design_doc
    assert "## Experience Mode" in design_doc
    assert "## Section Blueprint" in design_doc
    assert "## Copy Bank" in design_doc
    assert "## Output Contract" in design_doc


def test_design_brief_uses_full_bleed_composition_for_fashion(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    monkeypatch.delenv("STITCH_API_KEY", raising=False)
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: False)

    brief = design_providers.design_brief(
        "Build a polished landing page for Aster Row, a fashion label with campaign photography, lookbook, collection, and shop inquiry.",
        root=tmp_path,
        product_name="Aster Row",
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )

    composition = brief["design_context"]["composition_spec"]
    assert composition["archetype"] == "full_bleed_media"
    assert any(item["id"] == "product_grid" for item in composition["allowed_archetypes"])
    assert "Full-Bleed Media Hero" in brief["stitch_prompt"]
    assert "Use real-feeling media" in " ".join(composition["first_viewport"])


def test_design_brief_uses_dashboard_shell_for_operational_dashboard(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    monkeypatch.delenv("STITCH_API_KEY", raising=False)
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: False)

    brief = design_providers.design_brief(
        "Build a healthcare operations dashboard for clinic triage, lab queues, urgent messages, staffing, and approvals.",
        root=tmp_path,
        product_name="CareFlow",
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )

    composition = brief["design_context"]["composition_spec"]
    assert composition["archetype"] == "dashboard_shell"
    assert "Application shell" in " ".join(composition["first_viewport"])
    assert "Do not render a landing-page hero" in " ".join(composition["first_viewport"])
    assert brief["design_context"]["experience_mode"]["mode"] == "dashboard_operational"


def test_design_brief_builds_interactive_3d_experience_contract(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    monkeypatch.delenv("STITCH_API_KEY", raising=False)
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: False)

    brief = design_providers.design_brief(
        "Build a 3D interactive WebGL landing page for OrbitForge with a full-bleed product scene, parallax scroll, and cinematic animation.",
        root=tmp_path,
        product_name="OrbitForge",
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )

    experience = brief["design_context"]["experience_mode"]
    assert experience["mode"] == "interactive_3d"
    assert "Three.js" in experience["recommended_libraries"]
    assert experience["requires_canvas_check"] is True
    assert experience["requires_reduced_motion"] is True
    assert "canvas-pixel/nonblank check" in experience["verification_requirements"]
    assert "no-WebGL/static fallback" in experience["fallback_requirement"]
    assert "Interactive 3D" in brief["stitch_prompt"]
    assert "canvas/WebGL or scene layer" in brief["stitch_prompt"]
    assert any("canvas" in item.lower() for item in brief["design_context"]["component_inventory"])


def test_design_brief_adds_construction_art_direction(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    monkeypatch.delenv("STITCH_API_KEY", raising=False)
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: False)

    brief = design_providers.design_brief(
        "Build a polished four-page website for Skanska USA, a real construction and development company.",
        root=tmp_path,
        product_name="Skanska USA",
        stack={"stack": "nextjs", "label": "Next.js web app"},
        artifact_scope="pages/home",
    )
    markdown = (tmp_path / ".friday" / "design" / "pages" / "home" / "design-brief.md").read_text(encoding="utf-8")

    assert brief["design_strategy"]["industry"] == "construction"
    assert brief["design_strategy"]["surface"] == "marketing_website"
    assert "infrastructure authority" in brief["design_strategy"]["direction"]
    assert "large project photography" in brief["stitch_prompt"]
    assert "Do not make a construction company look like a generic consulting SaaS landing page" in brief["stitch_prompt"]
    assert "## Art Direction" in markdown


def test_design_brief_adds_energy_climate_art_direction_without_developer_copy(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    monkeypatch.delenv("STITCH_API_KEY", raising=False)
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: False)

    request = (
        "Build a production-quality 4-page Next.js marketing website for KineticGrid Energy, "
        "a B2B climate-tech company that helps commercial buildings monitor microgrids, solar, "
        "batteries, demand spikes, and outage risk. Pages must be Home, Platform, Case Studies, and Contact. "
        "It must be mobile responsive."
    )
    brief = design_providers.design_brief(
        request,
        root=tmp_path,
        product_name="KineticGrid Energy",
        stack={"stack": "nextjs", "label": "Next.js web app"},
        artifact_scope="pages/home",
    )

    context = brief["design_context"]
    prompt = brief["stitch_prompt"].lower()

    assert brief["design_strategy"]["surface"] == "marketing_website"
    assert brief["design_strategy"]["industry"] == "energy_climate"
    assert context["user_intent"]["surface"] == "marketing_website"
    assert context["user_intent"]["industry"] == "energy_climate"
    assert context["content_model"]["navigation"] == ["Home", "Platform", "Case Studies", "Contact"]
    assert "microgrid telemetry" in context["content_model"]["proof_objects"]
    assert "facility managers" in context["target_audience"]
    assert "energy-grid hero" in context["component_inventory"]
    assert "microgrid intelligence for commercial buildings" in " ".join(context["copy_bank"]["headline_directions"]).lower()
    assert "construction services" in prompt
    assert "never use construction-company phrases" in prompt
    assert "developer-first product page" not in prompt
    assert "build the backend your ai app needs" not in prompt
    assert "cli command block" not in prompt


def test_design_brief_keeps_premium_climate_property_risk_out_of_luxury_lane(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    monkeypatch.delenv("STITCH_API_KEY", raising=False)
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: False)
    request = (
        "Build a production-quality Next.js landing page for EmberVault, a premium climate-risk intelligence "
        "platform for commercial property owners. EmberVault helps real estate teams see wildfire, flood, heat, "
        "insurance, maintenance, and tenant-impact risk across property portfolios before losses happen."
    )

    brief = design_providers.design_brief(
        request,
        root=tmp_path,
        product_name="EmberVault",
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )

    context = brief["design_context"]
    prompt = brief["stitch_prompt"].lower()

    assert brief["design_strategy"]["industry"] == "energy_climate"
    assert context["brief_autopilot"]["industry"] == "energy_climate"
    assert context["user_intent"]["industry"] == "energy_climate"
    assert "energy-risk hero" in context["brief_autopilot"]["intent_expansion"]["content_sections"]
    assert "property" in prompt
    assert "wildfire" in prompt
    assert "private clients" not in prompt
    assert "concierge access" not in prompt
    assert "atelier/craft" not in prompt


def test_design_variant_rejects_energy_project_wrong_domain_copy():
    brief = {
        "request": (
            "Build a climate-tech website for KineticGrid Energy with microgrid, solar, battery, "
            "demand spikes, outage risk, and commercial building telemetry."
        ),
        "product_name": "KineticGrid Energy",
        "style_profile": {"name": "", "id": ""},
        "design_strategy": {
            "surface": "marketing_website",
            "industry": "energy_climate",
            "message": "Buildings understand energy risk before outages or cost spikes.",
            "emotional_feel": "technical confidence and climate seriousness",
        },
    }
    variant = {
        "id": "bad-domain",
        "html": """
        <main>
          <header><nav>Home Platform Case Studies Contact</nav></header>
          <section>
            <h1>KineticGrid Energy builds dependable spaces from plan to handover.</h1>
            <p>Construction services for contractors, jobsite safety, concrete, and project closeout.</p>
            <a href="/contact">Start inquiry</a>
          </section>
        </main>
        """,
    }

    scored = design_providers.score_design_variant(variant, brief)

    assert scored["score"] < scored["threshold"]
    assert any("off-domain" in item.lower() or "mismatched" in item.lower() for item in scored["rejection_reasons"])
    assert any("construction services" in item.lower() for item in scored["gaps"])


def test_design_variant_rejects_climate_risk_luxury_copy_and_empty_button():
    brief = {
        "request": (
            "Build a production-quality landing page for EmberVault, a premium climate-risk intelligence "
            "platform for commercial property owners covering wildfire, flood, heat, insurance, maintenance, "
            "tenant impact, and property portfolio risk."
        ),
        "product_name": "EmberVault",
        "style_profile": {"name": "", "id": ""},
        "design_strategy": {
            "surface": "marketing_website",
            "industry": "energy_climate",
            "message": "Property owners see climate risk before losses happen.",
            "emotional_feel": "serious, premium, evidence-led climate intelligence",
        },
    }
    variant = {
        "id": "luxury-drift",
        "html": """
        <main aria-label="EmberVault">
          <nav>Atelier Collections Process Concierge</nav>
          <section>
            <h1>Crafted for private clients who notice the difference.</h1>
            <p>EmberVault provides climate-risk intelligence for the permanent legacy.</p>
            <button></button>
            <a href="/demo">Request Concierge Access</a>
          </section>
          <section><h2>Wildfire and flood portfolio risk</h2><p>Commercial property owners see heat, insurance, and maintenance risk.</p></section>
        </main>
        """,
    }

    scored = design_providers.score_design_variant(variant, brief)

    assert scored["score"] < scored["threshold"]
    assert any("off-domain" in item.lower() for item in scored["rejection_reasons"])
    assert any("interactive controls" in item.lower() for item in scored["rejection_reasons"])
    assert any("atelier" in item.lower() for item in scored["gaps"])
    assert any("button has no visible text" in item.lower() for item in scored["gaps"])


def test_design_brief_uses_taxonomy_for_fashion_and_visual_references(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    reference_dir = tmp_path / ".friday" / "design" / "references"
    reference_dir.mkdir(parents=True)
    (reference_dir / "approved-lookbook.png").write_bytes(b"fake-image")

    brief = design_providers.design_brief(
        "Build a polished four-page website for Aster Row, a fashion label with campaign, collection, lookbook, and shop inquiry pages.",
        root=tmp_path,
        product_name="Aster Row",
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )

    context = brief["design_context"]
    assert context["user_intent"]["industry"] == "fashion"
    assert any(item["section"] == "Campaign hero" for item in context["section_blueprint"])
    assert "lookbook grid" in context["component_inventory"]
    assert "A collection with a point of view." in context["copy_bank"]["headline_directions"]
    assert context["visual_reference_memory"]["available"] is True
    assert context["visual_reference_memory"]["assets"][0]["path"].endswith("approved-lookbook.png")
    assert "Campaign hero" in brief["stitch_prompt"]
    assert "Visual reference memory:" in brief["stitch_prompt"]


def test_visual_composition_review_rejects_shallow_marketing_screen(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 72}))
    brief = design_providers.design_brief(
        "Build a polished marketing website for Harbor Legal.",
        root=tmp_path,
        product_name="Harbor Legal",
        stack={"stack": "nextjs", "label": "Next.js web app"},
        create_files=False,
    )

    scored = design_providers.score_design_variant(
        {"id": "shallow", "label": "Shallow", "html": "<main><h1>Harbor Legal</h1></main>"},
        brief,
    )

    assert scored["visual_review"]["passed"] is False
    assert any("Visual composition review failed" in item for item in scored["rejection_reasons"])


def test_stitch_generation_defaults_to_dry_run_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    monkeypatch.setenv("STITCH_API_KEY", "configured")
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: True)

    result = design_providers.generate_with_stitch("Design a dashboard", root=tmp_path, product_name="Dash", dry_run=True)

    assert result["status"] == "planned"
    assert result["provider"] == "stitch"
    assert any(path.endswith("design-brief.md") for path in result["artifacts"])


def test_design_critique_scores_variants_and_selects_best(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 60}))
    brief = design_providers.design_brief(
        "Build a university operations dashboard for registrar queues, course allocation, student issue triage, payments, approvals, SLA risks, and audit trail.",
        root=tmp_path,
        product_name="University Operations Command Center",
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )
    variants = [
        {
            "id": "generic",
            "label": "Generic",
            "html": "<main><h1>NexusForge Operations</h1><p>Sample text placeholder dashboard title.</p></main>",
        },
        {
            "id": "registrar",
            "label": "Registrar command center",
            "html": """
            <main aria-label="University Operations Command Center">
              <nav>Dashboard Enrollment Finance Academics Audit</nav>
              <section><h1>University Operations Command Center</h1><button>Review enrollment queue</button></section>
              <section><table><tr><th>Student</th><th>Department</th><th>SLA risk</th><th>Status</th></tr></table></section>
              <section>Registrar queue, course conflicts, payment exceptions, approvals, audit trail, system health, triage actions.</section>
            </main>
            """,
        },
    ]

    report = design_providers.critique_design_variants(variants, brief)
    artifacts = design_providers._write_design_critique_artifacts(tmp_path / ".friday" / "design", report)

    assert report["frontend_handoff_allowed"] is True
    assert report["selected_variant"]["id"] == "registrar"
    assert any(item["id"] == "generic" for item in report["rejected_variants"])
    assert (tmp_path / ".friday" / "design" / "frontend-handoff.md").exists()
    assert (tmp_path / ".friday" / "design" / "selected-design.html").exists()
    assert any(path.endswith("design-critique-report.json") for path in artifacts)


def test_single_strong_stitch_projection_can_pass_without_diversity(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 72, "design_variant_count": 1}))
    brief = design_providers.design_brief(
        "Build a polished landing page for Nexus Forge, a self-hosted developer backend platform with API routes, auth, WebSockets, CLI, docs, Web3 modules, and plugin marketplace.",
        root=tmp_path,
        product_name="Nexus Forge",
        stack={"stack": "nextjs", "label": "Next.js web app"},
        create_files=False,
    )
    html = """
    <header><nav aria-label="Primary"><a>Nexus Forge</a><a>Docs</a><a>GitHub</a></nav></header>
    <main aria-label="Nexus Forge">
      <section><h1>Build the backend your AI app needs without giving up control.</h1><p>Nexus Forge gives builders auth, database schema, API routes, WebSockets, AI agents, plugin marketplace, Base modules, x402 payments, CLI install, docs, and self-hosted deployment proof.</p><a href="/docs">Start building</a></section>
      <section><h2>Schema and API proof</h2><pre><code>GET /v1/agents/process</code></pre><article>Deployment active</article><article>Module marketplace</article></section>
      <section><h2>Open-source control</h2><p>Inspect the generated API, connect auth, review logs, and run the backend on your own infrastructure.</p></section>
    </main>
    """
    variants = [
        {"id": "screen-1", "screenId": "screen-1", "label": "Base direction", "html": html, "htmlUrl": "https://example.com/screen.html", "imageUrl": "https://example.com/screen.png"},
        {"id": "screen-1", "screenId": "screen-1", "label": "Duplicate projection", "html": html, "htmlUrl": "https://example.com/screen.html", "imageUrl": "https://example.com/screen.png"},
    ]

    report = design_providers.critique_design_variants(variants, brief)

    assert design_providers._variant_count(1) == 1
    assert report["frontend_handoff_allowed"] is True
    assert report["diversity"]["required"] is False
    assert len(report["variants"]) == 1


def test_design_critique_rejects_samey_saas_for_construction(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 50}))
    brief = design_providers.design_brief(
        "Build a polished four-page website for Skanska USA, a real construction and development company.",
        root=tmp_path,
        product_name="Skanska USA",
        stack={"stack": "nextjs", "label": "Next.js web app"},
        artifact_scope="pages/home",
    )
    variants = [
        {
            "id": "generic_saas",
            "label": "Generic SaaS",
            "html": """
            <main aria-label="Skanska USA">
              <nav>Home About Services Contact</nav>
              <section><h1>Skanska USA Command Workspace</h1><p>Scale your service business through smarter operations with a launch path and dashboard cards.</p></section>
              <section><article>Workflow automation</article><article>What visitors can understand quickly</article></section>
            </main>
            """,
        },
            {
                "id": "construction_authority",
                "label": "Construction authority",
                "html": """
                <main aria-label="Skanska USA">
                  <nav>Home About Services Contact</nav>
                  <section><h1>Building for a Better Society</h1><p>Skanska USA delivers construction, civil infrastructure, commercial development, safety-led project delivery, and sustainable building work.</p><a href="/contact">Start project inquiry</a></section>
                  <section><h2>Project proof</h2><article>Construction</article><article>Civil infrastructure</article><article>Commercial development</article></section>
                  <section><h2>Safety and delivery</h2><p>Project teams plan jobsite safety, schedule risk, sustainable materials, and owner communication before construction starts.</p></section>
                  <section><h2>Regional expertise</h2><p>Commercial, civic, and infrastructure partners can review relevant work and contact the right development team.</p></section>
                </main>
                """,
            },
    ]

    report = design_providers.critique_design_variants(variants, brief)

    assert report["frontend_handoff_allowed"] is True
    assert report["selected_variant"]["id"] == "construction_authority"
    rejected = next(item for item in report["rejected_variants"] if item["id"] == "generic_saas")
    assert "generic" in " ".join(rejected["rejection_reasons"]).lower()
    assert any(item["id"] == "art_direction_fit" for item in report["selected_variant"]["criteria"])


def test_design_critique_blocks_samey_variant_sets(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 40}))
    brief = design_providers.design_brief(
        "Build a polished four-page website for Skanska USA, a real construction and development company.",
        root=tmp_path,
        product_name="Skanska USA",
        stack={"stack": "nextjs", "label": "Next.js web app"},
        artifact_scope="pages/home",
    )
    html = """
    <main aria-label="Skanska USA">
      <nav>Home About Services Contact</nav>
      <section><h1>Building for a Better Society</h1><p>Skanska USA delivers construction, civil infrastructure, commercial development, safety-led project delivery, and sustainable building work.</p><a href="/contact">Start project inquiry</a></section>
      <section><h2>Project proof</h2><article>Construction</article><article>Civil infrastructure</article><article>Commercial development</article></section>
    </main>
    """

    report = design_providers.critique_design_variants(
        [
            {"id": "same_1", "label": "Same 1", "html": html},
            {"id": "same_2", "label": "Same 2", "html": html},
        ],
        brief,
    )

    assert report["frontend_handoff_allowed"] is False
    assert report["diversity"]["samey"] is True
    assert "samey variants" in " ".join(report["rejected_variants"][0]["rejection_reasons"]).lower()


def test_design_critique_allows_excellent_samey_best_variant(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 72}))
    brief = {"request": "Build a fintech landing page for TaxNest.", "product_name": "TaxNest"}
    html = """
    <main aria-label="TaxNest">
      <header><nav aria-label="Primary">TaxNest Pricing Security</nav></header>
      <section><h1>Separate income, taxes, and emergency cash before money gets messy.</h1><p>TaxNest helps consultants track client income, quarterly taxes, invoices, retirement savings, and emergency reserves.</p><a>Start clean</a></section>
      <section><h2>Financial proof</h2><article>Tax reserve</article><article>Invoice paid</article><article>Emergency fund</article></section>
      <section><h2>Security and pricing</h2><p>Transparent plans, audit-ready records, and clear money movement controls.</p></section>
    </main>
    """

    def fake_score(variant, brief, *, index=1):
        return {
            **variant,
            "score": variant["score"],
            "threshold": 72,
            "criteria": [],
            "gaps": [],
            "rejection_reasons": list(variant.get("rejection_reasons") or []),
        }

    monkeypatch.setattr(design_providers, "score_design_variant", fake_score)

    report = design_providers.critique_design_variants(
        [
            {"id": "same_1", "label": "Same 1", "html": html, "score": 92},
            {"id": "same_2", "label": "Same 2", "html": html, "score": 91},
        ],
        brief,
    )

    assert report["frontend_handoff_allowed"] is True
    assert report["selected_variant"]["id"] == "same_1"
    assert report["diversity"]["samey"] is True
    assert report["diversity"]["excellent_samey_handoff_allowed"] is True
    assert "samey variants" not in " ".join(report["selected_variant"]["rejection_reasons"]).lower()


def test_design_critique_duplicate_group_keeps_best_representative(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 72}))
    brief = {"request": "Build a fintech landing page for SafeLedger.", "product_name": "SafeLedger"}
    shared_html = """
    <main aria-label="SafeLedger">
      <header><nav aria-label="Primary">SafeLedger Pricing Security</nav></header>
      <section><h1>Move money with clarity and control.</h1><p>SafeLedger tracks income, taxes, invoices, savings, and freelancer cashflow.</p><a>Open account</a></section>
      <section><h2>Income, tax, invoice, and savings proof</h2><article>Tax reserve</article><article>Invoice paid</article></section>
      <section><h2>Transparent pricing</h2><p>Clear plans, bank-grade controls, and audit-ready records.</p></section>
    </main>
    """

    def fake_score(variant, brief, *, index=1):
        return {
            **variant,
            "score": variant["score"],
            "threshold": 72,
            "criteria": [],
            "gaps": [],
            "rejection_reasons": list(variant.get("rejection_reasons") or []),
        }

    monkeypatch.setattr(design_providers, "score_design_variant", fake_score)

    report = design_providers.critique_design_variants(
        [
            {"id": "base", "label": "Base", "html": shared_html, "score": 81, "rejection_reasons": ["landing page is too shallow"]},
            {"id": "improved", "label": "Improved", "html": shared_html, "score": 93},
            {"id": "alternate", "label": "Alternate", "html": "<main><section><h1>SafeLedger pricing</h1></section><aside>Taxes invoices savings trust</aside></main>", "score": 74},
        ],
        brief,
    )

    assert report["frontend_handoff_allowed"] is True
    assert report["selected_variant"]["id"] == "improved"
    base = next(item for item in report["rejected_variants"] if item["id"] == "base")
    assert "strongest representative" in " ".join(base["rejection_reasons"]).lower()


def test_apply_selected_design_to_nextjs_wires_stitch_surface(tmp_path):
    app_page = tmp_path / "src" / "app" / "page.tsx"
    workspace_page = tmp_path / "src" / "app" / "(dashboard)" / "workspace" / "page.tsx"
    app_page.parent.mkdir(parents=True)
    workspace_page.parent.mkdir(parents=True)
    app_page.write_text("export default function Home() { return <main>Scaffold</main>; }\n", encoding="utf-8")
    workspace_page.write_text("export default function Workspace() { return <main>Scaffold</main>; }\n", encoding="utf-8")
    design_root = tmp_path / ".friday" / "design"
    design_root.mkdir(parents=True)
    selected = design_root / "selected-design.html"
    selected.write_text(
        """<!DOCTYPE html><html><head><script src="https://cdn.tailwindcss.com"></script><script>alert('nope')</script></head><body onload="bad()"><main><h1>Stitch Only Hero</h1><a href="javascript:bad()">Open</a></main></body></html>""",
        encoding="utf-8",
    )
    (design_root / "frontend-handoff.json").write_text(
        json.dumps(
            {
                "selected_variant_id": "screen",
                "selected_variant_label": "Screen",
                "score": 91,
                "html_path": str(selected),
            }
        ),
        encoding="utf-8",
    )

    result = design_providers.apply_selected_design_to_nextjs(tmp_path, request="Build a web-app called CareFlow", product_name="CareFlow")

    html_module = (tmp_path / "src" / "lib" / "stitchNativeContent.ts").read_text(encoding="utf-8")
    component = (tmp_path / "src" / "components" / "Stitch" / "StitchNativePage.tsx").read_text(encoding="utf-8")
    assert result["ok"] is True
    assert "Stitch Only Hero" in html_module
    assert "alert('nope')" not in html_module
    assert "onload=" not in html_module
    assert "javascript:" not in html_module.lower()
    assert "bodyHtml" in html_module
    assert "usesTailwindCdn" in html_module
    assert "dangerouslySetInnerHTML" in component
    assert '"renderMode": "stitch_html"' in html_module
    assert '"renderMode": "stitch_document"' not in html_module
    assert "StitchPageSurface" in app_page.read_text(encoding="utf-8")
    assert "StitchPageSurface" in workspace_page.read_text(encoding="utf-8")
    assert (tmp_path / "src" / "components" / "Stitch" / "StitchNativePage.module.css").exists()
    assert (tmp_path / "package.json").exists()
    assert (tmp_path / "tsconfig.json").exists()
    assert (tmp_path / "src" / "app" / "layout.tsx").exists()
    assert (design_root / "applied-design.json").exists()


def test_stitch_legacy_surface_uses_dynamic_default_page():
    component = design_providers._stitch_legacy_component()

    assert "function defaultPage()" in component
    assert "'website_home' in pages" in component
    assert 'page="home"' not in component


def test_failed_design_critique_clears_stale_stitch_handoff_and_applied_manifest(tmp_path):
    design_root = tmp_path / ".friday" / "design"
    design_root.mkdir(parents=True)
    for name in ("frontend-handoff.json", "frontend-handoff.md", "selected-design.html", "applied-design.json"):
        (design_root / name).write_text("stale", encoding="utf-8")

    design_providers._write_design_critique_artifacts(
        design_root,
        {
            "status": "failed",
            "summary": "fetch failed",
            "frontend_handoff_allowed": False,
            "frontend_handoff_required": True,
            "score_threshold": 72,
            "selected_variant": None,
            "variants": [],
        },
    )

    assert not (design_root / "frontend-handoff.json").exists()
    assert not (design_root / "frontend-handoff.md").exists()
    assert not (design_root / "selected-design.html").exists()
    assert not (design_root / "applied-design.json").exists()


def test_apply_selected_developer_tool_design_preserves_stitch_terminal_html(tmp_path):
    design_root = tmp_path / ".friday" / "design"
    design_root.mkdir(parents=True)
    selected = design_root / "selected-design.html"
    selected.write_text(
        """
        <!DOCTYPE html>
        <html class="dark" lang="en">
          <head>
            <script src="https://cdn.tailwindcss.com?plugins=forms"></script>
            <script id="tailwind-config">tailwind.config = { darkMode: 'class' }</script>
            <style>.terminal-glass{background:#0B0E14;border:1px solid #30363D}</style>
          </head>
          <body>
            <main class="bg-[#0B0E14] text-white">
              <section class="grid grid-cols-2 gap-8">
                <div>
                  <h1>The AI + Web3 Backend You Own.</h1>
                  <a href="#quickstart">Start Building</a>
                  <a href="#docs">Read Docs</a>
                </div>
                <div class="terminal-glass">
                  <pre><code>npx nexus-forge init
GET /v1/agents/process
schema User { id uuid @primary }</code></pre>
                </div>
              </section>
            </main>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    (design_root / "frontend-handoff.json").write_text(
        json.dumps(
            {
                "selected_variant_id": "devtool",
                "selected_variant_label": "Developer Tool",
                "score": 94,
                "html_path": str(selected),
            }
        ),
        encoding="utf-8",
    )

    result = design_providers.apply_selected_design_to_nextjs(
        tmp_path,
        request="Build a landing page for Nexus Forge, a developer tool with CLI, API, schema, docs, and Web3 modules.",
        product_name="Nexus Forge",
    )

    pages_module = (tmp_path / "src" / "lib" / "stitchNativeContent.ts").read_text(encoding="utf-8")
    component = (tmp_path / "src" / "components" / "Stitch" / "StitchNativePage.tsx").read_text(encoding="utf-8")
    assert result["ok"] is True
    assert "terminal-glass" in pages_module
    assert "npx nexus-forge init" in pages_module
    assert "GET /v1/agents/process" in pages_module
    assert "schema User" in pages_module
    assert "Start Building" in pages_module
    assert "stitch_html" in pages_module
    assert "StitchHtmlRuntime" in component


def test_apply_selected_design_preserves_stitch_fidelity_with_runtime_tailwind_config(tmp_path):
    design_root = tmp_path / ".friday" / "design"
    design_root.mkdir(parents=True)
    selected = design_root / "selected-design.html"
    selected.write_text(
        """
        <!DOCTYPE html>
        <html lang="en">
          <head>
            <script src="https://cdn.tailwindcss.com"></script>
            <script id="tailwind-config">
              tailwind.config = {
                theme: {
                  extend: {
                    colors: { surface: '#071111', 'on-surface': '#ecfeff' },
                    fontSize: { 'display-xl': '72px' },
                    spacing: { md: '16px' }
                  }
                }
              }
            </script>
          </head>
          <body>
            <main class="bg-surface text-on-surface p-md rounded-DEFAULT">
              <h1 class="font-display-xl text-display-xl">TerraScope Risk</h1>
              <p>Climate risk, wildfire, flood, heat, insurance exposure, and resilience proof across property portfolios.</p>
            </main>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    (design_root / "frontend-handoff.json").write_text(
        json.dumps(
            {
                "selected_variant_id": "climate",
                "selected_variant_label": "Climate",
                "score": 92,
                "html_path": str(selected),
            }
        ),
        encoding="utf-8",
    )

    result = design_providers.apply_selected_design_to_nextjs(
        tmp_path,
        request="Build a landing page for TerraScope Risk, a climate and property-risk intelligence platform.",
        product_name="TerraScope Risk",
    )

    pages_module = (tmp_path / "src" / "lib" / "stitchNativeContent.ts").read_text(encoding="utf-8")
    component = (tmp_path / "src" / "components" / "Stitch" / "StitchNativePage.tsx").read_text(encoding="utf-8")
    app_page = (tmp_path / "src" / "app" / "page.tsx").read_text(encoding="utf-8")
    static_document = tmp_path / "public" / "friday-stitch" / "home.html"
    assert result["ok"] is True
    assert '"renderMode": "stitch_html"' in pages_module
    assert "runtime_tailwind_config_allowed_for_stitch_fidelity" in pages_module
    assert "bg-surface" in pages_module
    assert "StitchDocumentRuntime" in component
    assert "StitchHtmlRuntime" in component
    assert "srcDoc" in component
    assert static_document.exists()
    assert "StitchPageSurface" in app_page
    assert "redirect(" not in app_page
    assert "next/navigation" not in app_page


def test_multipage_website_design_generates_and_applies_each_route(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 20, "design_download_remote_assets": False}))
    monkeypatch.setenv("STITCH_API_KEY", "configured")
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: True)
    calls = []

    def fake_run(brief, *, variant_count=1):
        calls.append(brief["artifact_scope"])
        page = brief["artifact_scope"].split("/")[-1]
        return {
            "ok": True,
            "status": "generated",
            "summary": f"Generated {page}.",
            "artifacts": [str(Path(brief["design_root"]) / "stitch-result.json")],
            "result": {
                "ok": True,
                "variants": [
                    {
                        "id": page,
                        "label": page.title(),
                        "html": f"<html><head><script src='https://cdn.tailwindcss.com'></script><script id='tailwind-config'>tailwind.config={{}}</script></head><body><main aria-label='Lumora Studio'><nav>Home About Services Contact</nav><h1 class='text-[120px] tracking-[-0.02em'>{page.title()} offer for Lumora Studio</h1><section><p>Lumora Studio is a normal four page website for boutique operations automation consultancy work with small service businesses, trust, offer, process, services, contact, inquiry, and client outcomes.</p><a href='/contact'>Start inquiry</a></section></main></body></html>",
                    }
                ],
            },
        }

    monkeypatch.setattr(design_providers, "_run_stitch_sdk", fake_run)

    report = design_providers.run_multipage_website_design_critique(
        "Build a normal website called Lumora Studio with 4 pages: Home, About, Services, Contact.",
        root=tmp_path,
        product_name="Lumora Studio",
        stack={"stack": "nextjs", "label": "Next.js web app"},
        dry_run=False,
    )
    applied = design_providers.apply_website_designs_to_nextjs(
        tmp_path,
        request="Build a normal website called Lumora Studio with 4 pages: Home, About, Services, Contact.",
        product_name="Lumora Studio",
    )

    assert calls == ["pages/home", "pages/about", "pages/services", "pages/contact"]
    assert report["frontend_handoff_allowed"] is True
    assert applied["ok"] is True
    assert (tmp_path / "src" / "app" / "page.tsx").exists()
    assert (tmp_path / "src" / "app" / "about" / "page.tsx").exists()
    assert (tmp_path / "src" / "app" / "services" / "page.tsx").exists()
    assert (tmp_path / "src" / "app" / "contact" / "page.tsx").exists()
    assert (tmp_path / "package.json").exists()
    assert (tmp_path / "tsconfig.json").exists()
    assert (tmp_path / "src" / "app" / "globals.css").exists()
    pages_module = (tmp_path / "src" / "lib" / "stitchNativeContent.ts").read_text(encoding="utf-8")
    component = (tmp_path / "src" / "components" / "Stitch" / "StitchNativePage.tsx").read_text(encoding="utf-8")
    css = (tmp_path / "src" / "components" / "Stitch" / "StitchNativePage.module.css").read_text(encoding="utf-8")
    home_brief = (tmp_path / ".friday" / "design" / "pages" / "home" / "design-brief.md").read_text(encoding="utf-8")
    assert '"about"' in pages_module
    assert "text-[120px]" not in pages_module
    assert "bodyHtml" in pages_module
    assert "Home 1" not in pages_module
    assert "Services 2" not in pages_module
    assert "dangerouslySetInnerHTML" in component
    assert "data.score" not in component
    assert "meta.scalePolicy" not in component
    assert "Friday keeps" not in component
    assert "Project type, location, timing, and contact path" in component
    assert "'use client'" in component
    assert 'button type="submit"' in component
    assert "role=\"status\"" in component
    assert "font-size: clamp(2.55rem, 4vw, 3.6rem)" in css
    assert "7vw" not in css
    assert "{data.kicker ? <p className={styles.eyebrow}>{data.kicker}</p> : null}" in component
    assert "<p className={styles.eyebrow}>{data.label}</p>" not in component
    assert "Product: Lumora Studio\n" in home_brief
    assert "Visible UI branding must use \"Lumora Studio\"" in home_brief
    assert "Product: Lumora Studio Home" not in home_brief
    assert "Visible UI branding must use \"Lumora Studio Home\"" not in home_brief
    assert "Design a production-quality interface for: Lumora Studio Home" not in home_brief
    assert "Do not label sections as Page 1, Home 1, Services 2" in home_brief
    assert "Design only this route's page content" in home_brief


def test_multipage_website_design_stops_after_provider_transport_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 20}))
    monkeypatch.setenv("STITCH_API_KEY", "configured")
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: True)
    calls = []

    def fake_run(brief, *, variant_count=1):
        calls.append(brief["artifact_scope"])
        return {
            "ok": False,
            "status": "failed",
            "summary": "Stitch SDK failed: fetch failed",
            "artifacts": [str(Path(brief["design_root"]) / "stitch-run.log")],
            "result": {"ok": False, "status": "failed", "error": "fetch failed"},
        }

    monkeypatch.setattr(design_providers, "_run_stitch_sdk", fake_run)

    report = design_providers.run_multipage_website_design_critique(
        "Build a normal website called Lumora Studio with 4 pages: Home, About, Services, Contact.",
        root=tmp_path,
        product_name="Lumora Studio",
        stack={"stack": "nextjs", "label": "Next.js web app"},
        dry_run=False,
    )

    assert calls == ["pages/home"]
    assert report["frontend_handoff_allowed"] is False
    assert report["pages"][0]["status"] == "failed"
    assert [page["status"] for page in report["pages"][1:]] == ["skipped", "skipped", "skipped"]
    assert "configured design provider failed earlier" in report["pages"][1]["summary"]


def test_stitch_native_converter_skips_hero_duplicate_menu_and_wrapper_cards(tmp_path):
    html = """
    <main>
      <nav><a href="/">Lumora Studio</a><a href="/about">About</a></nav>
      <button>menu</button>
      <section>
        <h1>Scale your service business through smarter operations.</h1>
        <p>Lumora Studio turns chaotic workflows into streamlined automated systems for owner-led service teams.</p>
        <a href="/contact">Book a Discovery Call</a>
      </section>
      <section>
        <div>
          <h2>Precision Engineering for Your Business</h2>
          <p>We architect operational foundations designed for scale.</p>
          <div><h3>Process Optimization</h3><p>Identify bottlenecks and simplify the handoff.</p></div>
          <div><h3>Workflow Automation</h3><p>Replace repetitive work with reliable automations.</p></div>
        </div>
      </section>
    </main>
    """
    page = design_providers._selected_design_page_payload(
        "home",
        "/",
        "Home",
        html,
        handoff={"selected_variant": {"score": 90}},
        product_name="Lumora Studio",
    )

    result = design_providers._apply_design_pages_to_nextjs(
        tmp_path,
        [page],
        request="Build a normal website called Lumora Studio with 4 pages.",
        product_name="Lumora Studio",
    )

    pages_module = (tmp_path / "src" / "lib" / "stitchNativeContent.ts").read_text(encoding="utf-8")
    assert result["ok"] is True
    assert pages_module.count('"title": "Scale your service business through smarter operations."') == 1
    assert pages_module.count('"title": "Process Optimization"') == 1
    assert '"label": "menu"' not in pages_module
    assert '"label": "Lumora Studio"' not in pages_module


def test_stitch_native_converter_strips_icon_tokens_and_route_section_labels(tmp_path):
    html = """
    <main>
      <section>
        <h1>Skanska USA</h1>
        <p>Building civil infrastructure, commercial projects, and safety-led construction delivery across the United States.</p>
      </section>
      <section>
        <h2>Home</h2>
        <span class="material-symbols-outlined">health_and_safety</span>
        <span class="material-symbols-outlined">eco</span>
        <p>135+ years of construction experience across infrastructure, commercial development, safety, and sustainable project delivery.</p>
      </section>
    </main>
    """
    page = design_providers._selected_design_page_payload(
        "home",
        "/",
        "Home",
        html,
        handoff={"selected_variant": {"score": 90}},
        product_name="Skanska USA",
    )

    result = design_providers._apply_design_pages_to_nextjs(
        tmp_path,
        [page],
        request="Build a normal website for Skanska USA.",
        product_name="Skanska USA",
    )

    pages_module = (tmp_path / "src" / "lib" / "stitchNativeContent.ts").read_text(encoding="utf-8")
    assert result["ok"] is True
    assert "health_and_safety" not in pages_module
    assert '"eco"' not in pages_module
    assert '"title": "Home"' not in pages_module
    assert "Proof of scale" in pages_module


def test_stitch_action_links_use_nearest_real_route_when_provider_returns_home_href():
    assert design_providers._normalize_design_href("/", "Get a Quote") == "/contact"
    assert design_providers._normalize_design_href("/", "View Our Projects") == "/services"
    assert design_providers._normalize_design_href("#", "Read Full History") == "/about"
    assert design_providers._normalize_design_href("/", "Home") == "/"


def test_stitch_action_links_honor_custom_site_map_routes():
    request = (
        "Build a polished four-page Next.js website for Maison Noire Atelier. "
        "Pages must be Home, Atelier, Collections, and Concierge Contact."
    )
    site_routes = design_providers._site_route_context(request)

    assert design_providers._normalize_design_href("/inquire", "Inquire", site_routes=site_routes) == "/contact"
    assert design_providers._normalize_design_href("/", "Concierge", site_routes=site_routes) == "/contact"
    assert design_providers._normalize_design_href("/", "Collections", site_routes=site_routes) == "/collections"
    assert design_providers._normalize_design_href("/", "Atelier", site_routes=site_routes) == "/atelier"
    assert design_providers._normalize_design_href("/services", "Services", site_routes=site_routes) == "/"


def test_stitch_native_converter_rewrites_custom_site_map_links(tmp_path):
    request = (
        "Build a polished four-page Next.js website for Maison Noire Atelier. "
        "Pages must be Home, Atelier, Collections, and Concierge Contact."
    )
    html = """
    <main>
      <nav>
        <a href="/">Home</a>
        <a href="/">Atelier</a>
        <a href="/">Collections</a>
        <a href="/">Concierge</a>
      </nav>
      <section>
        <h1>The Art of Slow Time</h1>
        <p>Private watch and jewelry commissions shaped by craft, scarcity, and quiet appointment-led service.</p>
        <a href="/inquire">Inquire</a>
        <a href="#">Explore collections</a>
      </section>
    </main>
    """
    page = design_providers._selected_design_page_payload(
        "home",
        "/",
        "Home",
        html,
        handoff={"selected_variant": {"score": 94}},
        product_name="Maison Noire Atelier",
    )

    design_providers._apply_design_pages_to_nextjs(
        tmp_path,
        [page],
        request=request,
        product_name="Maison Noire Atelier",
    )

    pages_module = (tmp_path / "src" / "lib" / "stitchNativeContent.ts").read_text(encoding="utf-8")
    assert '"label": "Atelier"' in pages_module
    assert '"href": "/atelier"' in pages_module
    assert '"label": "Collections"' in pages_module
    assert '"href": "/collections"' in pages_module
    assert '"label": "Concierge"' in pages_module
    assert '"label": "Inquire"' in pages_module
    assert '"href": "/contact"' in pages_module
    assert "/inquire" not in pages_module


def test_stitch_native_converter_localizes_remote_visuals(monkeypatch, tmp_path):
    def fake_download(url, path):
        path.write_bytes(b"image-bytes")
        return True

    monkeypatch.setattr(design_providers, "_download_binary", fake_download)
    html = """
    <main>
      <section>
        <h1>Operational clarity for service teams</h1>
        <p>Lumora Studio helps service businesses simplify workflows and launch better systems.</p>
        <img src="https://example.com/stitch-image.png" alt="Operations dashboard" />
      </section>
    </main>
    """
    page = design_providers._selected_design_page_payload(
        "home",
        "/",
        "Home",
        html,
        handoff={"selected_variant": {"score": 90}},
        product_name="Lumora Studio",
    )

    design_providers._apply_design_pages_to_nextjs(
        tmp_path,
        [page],
        request="Build a normal website called Lumora Studio with 4 pages.",
        product_name="Lumora Studio",
    )

    pages_module = (tmp_path / "src" / "lib" / "stitchNativeContent.ts").read_text(encoding="utf-8")
    assert "https://example.com/stitch-image.png" not in pages_module
    assert "/friday-assets/" in pages_module
    assert list((tmp_path / "public" / "friday-assets").glob("*.png"))


def test_stitch_native_converter_drops_remote_visuals_when_download_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(design_providers, "_download_binary", lambda url, path: False)
    html = """
    <main>
      <section>
        <h1>Operational clarity for service teams</h1>
        <p>Lumora Studio helps service businesses simplify workflows and launch better systems.</p>
        <img src="https://example.com/missing.png" alt="Missing visual" />
      </section>
    </main>
    """
    page = design_providers._selected_design_page_payload(
        "home",
        "/",
        "Home",
        html,
        handoff={"selected_variant": {"score": 90}},
        product_name="Lumora Studio",
    )

    design_providers._apply_design_pages_to_nextjs(
        tmp_path,
        [page],
        request="Build a normal website called Lumora Studio with 4 pages.",
        product_name="Lumora Studio",
    )

    pages_module = (tmp_path / "src" / "lib" / "stitchNativeContent.ts").read_text(encoding="utf-8")
    assert "https://example.com/missing.png" not in pages_module
    assert '"visuals": []' in pages_module


def test_design_critique_rejects_off_domain_stitch_copy(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 55}))
    brief = design_providers.design_brief(
        "Build a university operations dashboard for registrar queues and student issue triage.",
        root=tmp_path,
        product_name="University Operations Command Center",
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )
    variant = {
        "id": "confused",
        "label": "Confused",
        "html": "<main aria-label='University Operations Command Center'><h1>University Operations Command Center</h1><p>Central Intelligence Agency network attack detected.</p><button>Deploy emergency services</button><table><tr><td>Registrar queue</td><td>Student issue triage</td></tr></table></main>",
    }

    report = design_providers.critique_design_variants([variant], brief)

    assert report["frontend_handoff_allowed"] is False
    assert report["selected_variant"] is None
    assert "off-domain" in " ".join(report["rejected_variants"][0]["rejection_reasons"])


def test_robotics_website_rejects_backend_web3_fallback_copy(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 55}))
    request = (
        "Build a polished four-page Next.js company website for OrbitFoundry Robotics. "
        "OrbitFoundry Robotics helps 3PL warehouses coordinate robot fleets, route optimization, "
        "pick waves, exception queues, dock congestion, and fulfillment throughput. "
        "Use the NexusForge Next.js style profile internally but avoid Web3/backend developer language."
    )
    page_request = design_providers._website_page_request(
        request,
        "OrbitFoundry Robotics",
        {"id": "home", "label": "Home", "route": "/", "focus": "robotics platform, fleet visibility, proof, primary call to action"},
    )
    brief = design_providers.design_brief(
        page_request,
        root=tmp_path,
        product_name="OrbitFoundry Robotics",
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )
    variant = {
        "id": "wrong_domain",
        "label": "Wrong domain",
        "html": """
        <header><nav><a>Product</a><a>AI + Web3</a><a>Docs</a></nav></header>
        <main>
          <section><h1>Build the backend your AI app needs without giving up control.</h1><p>Self-hosted backend, schema builder, API routes, Web3 modules, CLI install, Base wallet actions, x402 monetization, and plugin marketplace.</p><a>Start building</a></section>
          <section><h2>Schema builder</h2><p>Generate auth, database schema, API keys, and WebSocket routes.</p></section>
          <section><h2>Web3 module active</h2><p>Base wallet transaction proof for developers.</p></section>
        </main>
        """,
    }

    report = design_providers.critique_design_variants([variant], brief)

    reasons = " ".join(report["rejected_variants"][0]["rejection_reasons"]).lower()
    assert report["frontend_handoff_allowed"] is False
    assert "off-domain" in reasons
    assert "web3" in reasons or "backend" in reasons or "nexus" in reasons


def test_robotics_home_rejects_generic_ai_copy_and_shallow_hero(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 55}))
    request = (
        "Build a polished four-page Next.js company website for OrbitFoundry Robotics. "
        "Pages must be Home, Platform, Robotics Network, and Contact. "
        "OrbitFoundry Robotics helps warehouses coordinate robot fleets, route optimization, exceptions, and fulfillment throughput."
    )
    page_request = design_providers._website_page_request(
        request,
        "OrbitFoundry Robotics",
        {"id": "home", "label": "Home", "route": "/", "focus": "brand, robot fleet proof, conversion"},
    )
    brief = design_providers.design_brief(
        page_request,
        root=tmp_path,
        product_name="OrbitFoundry Robotics",
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )
    variant = {
        "id": "thin_home",
        "label": "Thin home",
        "html": """
        <header><nav><a>Home</a><a>Platform</a><a>Robotics Network</a><a>Contact</a></nav></header>
        <main>
          <section><h1>AI workflows your team can inspect and control.</h1><p>Designed for teams that need transparent approval workflows and reliable operations.</p><a>Book demo</a></section>
        </main>
        <footer>OrbitFoundry Robotics</footer>
        """,
    }

    report = design_providers.critique_design_variants([variant], brief)

    reasons = " ".join(report["rejected_variants"][0]["rejection_reasons"]).lower()
    assert report["frontend_handoff_allowed"] is False
    assert "generic" in reasons or "warehouse robotics" in reasons
    assert "meaningful section" in reasons or "footer" in reasons


def test_hero_background_with_low_opacity_image_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 55}))
    page_request = design_providers._website_page_request(
        "Build a polished four-page website for OrbitFoundry Robotics with pages Home, Platform, Robotics Network, Contact.",
        "OrbitFoundry Robotics",
        {"id": "home", "label": "Home", "route": "/", "focus": "warehouse robotics platform proof"},
    )
    brief = design_providers.design_brief(
        page_request,
        root=tmp_path,
        product_name="OrbitFoundry Robotics",
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )
    variant = {
        "id": "washed_out",
        "label": "Washed out",
        "html": """
        <header><nav><a>Home</a><a>Platform</a><a>Robotics Network</a><a>Contact</a></nav></header>
        <main>
          <section class="hero"><div style="background-image:url('warehouse.jpg'); opacity: 0.15"></div><h1>Robot fleet visibility for every warehouse shift.</h1><p>Warehouse teams see robot routes, exceptions, throughput, dock congestion, inventory handoffs, and operator overrides.</p><a>View platform</a></section>
          <section><h2>Fleet telemetry</h2><p>Robots, routes, batteries, pick waves, and WMS handoffs stay visible.</p></section>
          <section><h2>Exception control</h2><p>Human operators resolve route conflicts, dock queues, and throughput risk.</p></section>
          <section><h2>Fulfillment proof</h2><p>Facility owners can inspect uptime, utilization, and safety overrides.</p></section>
        </main>
        """,
    }

    report = design_providers.critique_design_variants([variant], brief)

    reasons = " ".join(report["rejected_variants"][0]["rejection_reasons"]).lower()
    assert report["frontend_handoff_allowed"] is False
    assert "washed out" in reasons or "image" in reasons or "media" in reasons


def test_fallback_domain_robotics_ignores_nexusforge_style_profile():
    domain = design_providers._fallback_domain(
        "Build a website for OrbitFoundry Robotics, a warehouse robotics company. "
        "Use the NexusForge Next.js style profile internally and avoid Web3/backend developer language."
    )

    assert domain.get("mode") == "robotics_logistics"
    assert "robot" in domain["summary"].lower()
    assert "web3" not in domain["summary"].lower()
    assert "backend" not in domain["summary"].lower()


def test_design_critique_rejects_page_label_branding_for_website(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 55}))
    page_request = design_providers._website_page_request(
        "Build a normal website called Lumora Studio with 4 pages: Home, About, Services, Contact.",
        "Lumora Studio",
        {"id": "home", "label": "Home", "route": "/", "focus": "brand, offer, proof, primary call to action"},
    )
    brief = design_providers.design_brief(
        page_request,
        root=tmp_path,
        product_name="Lumora Studio",
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )
    variant = {
        "id": "bad_page_brand",
        "label": "Bad page brand",
        "html": "<main><h1>Lumora Studio Home</h1><section><h2>Services</h2><p>Lumora Studio Home helps service businesses with automation, trust, offer, process, contact, inquiry, and outcomes.</p></section></main>",
    }

    report = design_providers.critique_design_variants([variant], brief)

    reasons = " ".join(report["rejected_variants"][0]["rejection_reasons"]).lower()
    assert report["frontend_handoff_allowed"] is False
    assert "route label" in reasons


def test_design_critique_rejects_route_label_headline(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 55}))
    page_request = design_providers._website_page_request(
        "Build a normal website called Lumora Studio with 4 pages: Home, About, Services, Contact.",
        "Lumora Studio",
        {"id": "home", "label": "Home", "route": "/", "focus": "brand, offer, proof, primary call to action"},
    )
    brief = design_providers.design_brief(
        page_request,
        root=tmp_path,
        product_name="Lumora Studio",
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )
    variant = {
        "id": "route_label",
        "label": "Route label",
        "html": "<main><h1>Home</h1><section><p>Lumora Studio helps small service businesses improve operations, trust, services, contact, inquiry, process, proof, and outcomes.</p></section></main>",
    }

    report = design_providers.critique_design_variants([variant], brief)

    reasons = " ".join(report["rejected_variants"][0]["rejection_reasons"]).lower()
    assert report["frontend_handoff_allowed"] is False
    assert "route label" in reasons


def test_design_critique_scores_normal_website_as_website_not_dashboard(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 72}))
    brief = design_providers.design_brief(
        "Build a normal website called Lumora Studio: four pages for Home, About, Services, and Contact for a boutique operations and automation consultancy for small service businesses.",
        root=tmp_path,
        product_name="Lumora Studio",
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )
    variant = {
        "id": "site",
        "label": "Website",
        "html": """
        <header><nav><a>Home</a><a>About</a><a>Services</a><a>Contact</a></nav></header>
        <main aria-label="Lumora Studio website">
          <section><h1>Lumora Studio</h1><p>Boutique operations and automation consultancy for small service businesses.</p><a href="/contact">Start an inquiry</a></section>
          <section><h2>About</h2><p>Trust, process, and practical client outcomes.</p></section>
          <section><h2>Services</h2><article>Discovery</article><article>Execution support</article><article>Launch readiness</article></section>
          <section><h2>Contact</h2><form><label>Name</label><input /><button>Send inquiry</button></form></section>
        </main>
        """,
    }

    report = design_providers.critique_design_variants([variant], brief)

    assert report["frontend_handoff_allowed"] is True
    assert report["selected_variant"]["id"] == "site"
    assert any(item["id"] == "website_content_depth" for item in report["selected_variant"]["criteria"])


def test_contact_page_domain_fit_uses_contact_and_domain_terms(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 72}))
    page_request = design_providers._website_page_request(
        "Build a polished four-page Next.js company website for Skanska USA, a real construction and development company. Skanska USA is known for construction, civil infrastructure, and commercial development work.",
        "Skanska USA",
        {"id": "contact", "label": "Contact", "route": "/contact", "focus": "inquiry form, response promise, qualification, contact options"},
    )
    brief = design_providers.design_brief(
        page_request,
        root=tmp_path,
        product_name="Skanska USA",
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )
    variant = {
        "id": "contact",
        "label": "Contact",
        "html": """
        <header><nav><a href="/">Home</a><a href="/about">About</a><a href="/services">Services</a><a href="/contact">Contact</a></nav></header>
        <main aria-label="Skanska USA contact">
          <section><h1>Contact Skanska USA</h1><p>Send an inquiry about construction, civil infrastructure, commercial development, project opportunities, safety, or partnership needs.</p></section>
          <section><h2>Send an inquiry</h2><form><label>Email</label><input /><label>Message</label><textarea></textarea><button>Submit inquiry</button></form></section>
          <section><h2>Headquarters</h2><p>Project teams respond to contact requests with the right regional construction contact.</p></section>
        </main>
        """,
    }

    report = design_providers.critique_design_variants([variant], brief)

    assert report["frontend_handoff_allowed"] is True
    assert not report["rejected_variants"]


def test_custom_website_pages_are_parsed_for_stitch_briefs(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    request = (
        "Build a polished four-page Next.js website for Maison Noire Atelier, "
        "a fictional luxury watch and jewelry atelier. Pages must be Home, Atelier, Collections, and Concierge Contact."
    )

    pages = design_providers._website_page_specs(request)
    page_request = design_providers._website_page_request(request, "Maison Noire Atelier", pages[-1])
    brief = design_providers.design_brief(
        page_request,
        root=tmp_path,
        product_name="",
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )

    assert [page["label"] for page in pages] == ["Home", "Atelier", "Collections", "Concierge Contact"]
    assert [page["route"] for page in pages] == ["/", "/atelier", "/collections", "/contact"]
    assert brief["product_name"] == "Maison Noire Atelier"
    assert "Home (/); Atelier (/atelier); Collections (/collections); Concierge Contact (/contact)" in page_request
    assert "concierge inquiry form" in ", ".join(brief["design_contract"]["required_sections"])
    assert "quiet luxury" in brief["stitch_prompt"].lower()


def test_luxury_website_scores_as_website_not_dashboard(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 72}))
    request = (
        "Build a polished four-page Next.js website for Maison Noire Atelier, "
        "a fictional luxury watch and jewelry atelier. Pages must be Home, Atelier, Collections, and Concierge Contact. "
        "This should feel like quiet luxury: scarce, crafted, intimate, editorial, and concierge-led."
    )
    page = design_providers._website_page_specs(request)[0]
    page_request = design_providers._website_page_request(request, "Maison Noire Atelier", page)
    brief = design_providers.design_brief(
        page_request,
        root=tmp_path,
        product_name="Maison Noire Atelier",
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )
    variant = {
        "id": "luxury_home",
        "label": "Luxury home",
        "html": """
        <header><nav aria-label="Primary"><a href="/">Home</a><a href="/atelier">Atelier</a><a href="/collections">Collections</a><a href="/contact">Concierge Contact</a></nav></header>
        <main aria-label="Maison Noire Atelier">
          <section><h1>Maison Noire Atelier</h1><p>Private horology and high jewelry shaped through craft, heritage, scarcity, and quiet luxury.</p><a href="/contact">Request a private appointment</a></section>
          <section><h2>Crafted in small editions</h2><p>Collectors enter a restrained atelier experience with bespoke watch details, jewelry provenance, and concierge guidance.</p></section>
          <section><h2>Private Collections Preview</h2><article>Horology pieces with material notes, movement detail, and limited availability.</article><article>High jewelry selected through an intimate appointment path.</article></section>
          <section><h2>Concierge introduction</h2><form><label>Name</label><input /><label>Inquiry</label><textarea></textarea><button>Inquire privately</button></form></section>
        </main>
        <footer>Maison Noire Atelier private client office</footer>
        """,
    }

    report = design_providers.critique_design_variants([variant], brief)

    assert report["frontend_handoff_allowed"] is True
    assert report["selected_variant"]["id"] == "luxury_home"
    assert any(item["id"] == "website_content_depth" for item in report["selected_variant"]["criteria"])
    assert all(item["id"] != "operational_density" for item in report["selected_variant"]["criteria"])


def test_nexus_forge_landing_brief_is_marketing_developer_tools_not_dashboard():
    request = (
        "Build a polished production-quality landing page for Nexus Forge as a fresh Next.js web-app project. "
        "Nexus Forge is an open-source, self-hosted no-code Backend-as-a-Service with WebSockets, "
        "API keys, plugin marketplace, AI integrations, Web3 modules, project dashboards, and x402 API monetization."
    )
    brief = design_providers.design_brief(
        request,
        root=".",
        product_name="Nexus Forge",
        stack={"stack": "nextjs"},
        create_files=False,
    )

    assert brief["design_contract"]["surface"] == "marketing_website"
    assert brief["design_strategy"]["surface"] == "marketing_website"
    assert brief["design_strategy"]["industry"] == "developer_tools"
    assert "landing page" in brief["design_contract"]["objective"]
    assert "operational dashboard" not in brief["stitch_prompt"].lower()
    assert "luxury" not in brief["stitch_prompt"].lower()
    pages = design_providers._website_page_specs(request)
    assert len(pages) == 1
    assert pages[0]["route"] == "/"
    assert "complete product landing page" in pages[0]["focus"]
    assert design_providers._is_multipage_website_request(request) is False


def test_nexus_forge_stitch_variant_scores_as_domain_fit_and_feasible(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 72}))
    request = (
        "Build a polished production-quality landing page for Nexus Forge as a fresh Next.js web-app project. "
        "Nexus Forge is an open-source, self-hosted no-code Backend-as-a-Service with WebSockets, "
        "API keys, plugin marketplace, AI integrations, Web3 modules, Base chain wallets, and x402 API monetization."
    )
    brief = design_providers.design_brief(
        request,
        root=tmp_path,
        product_name="Nexus Forge",
        stack={"stack": "nextjs"},
        create_files=False,
    )
    variant = {
        "id": "nexus_forge_landing",
        "label": "Developer landing",
        "html": """
        <header><nav aria-label="Primary"><a href="/">Nexus Forge</a><a href="/docs">Docs</a><a href="/login">Login</a></nav></header>
        <main aria-label="Nexus Forge">
          <section>
            <p>Open-source self-hosted BaaS</p>
            <h1>Forge your backend. No code. Full power.</h1>
            <p>Nexus Forge gives AI builders and indie teams visual backend APIs, auth, database schema, WebSockets, AI agents, Web3 Base wallets, x402 payments, API keys, deployments, and a GitHub-reviewed plugin marketplace.</p>
            <a href="/docs/quickstart">Start forging</a>
            <a href="/docs">Read docs</a>
          </section>
          <section id="capabilities">
            <article><h2>Backend APIs</h2><p>Ship auth, database tables, schema permissions, API keys, and deployment controls without hand-rolled boilerplate.</p></article>
            <article><h2>Realtime and agents</h2><p>Coordinate WebSocket rooms, AI providers, agents, and streaming product workflows from one builder.</p></article>
            <article><h2>Web3 monetization</h2><p>Connect Base wallets, transactions, smart contracts, NFT flows, and x402 API monetization.</p></article>
          </section>
          <section><h2>Developer proof</h2><p>Install the CLI, copy the SDK snippet, open documentation, then deploy a self-hosted project with observable logs.</p><button>Copy install command</button></section>
        </main>
        <footer>Nexus Forge documentation, marketplace, and support</footer>
        """,
    }

    report = design_providers.critique_design_variants([variant], brief)

    assert report["frontend_handoff_allowed"] is True
    selected = report["selected_variant"]
    assert selected["id"] == "nexus_forge_landing"
    criteria = {item["id"]: item for item in selected["criteria"]}
    assert criteria["domain_fit"]["score"] >= 18
    assert criteria["frontend_feasibility"]["score"] >= 11


def test_nexus_forge_landing_rejects_shallow_hero_only_stitch_variant(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 72}))
    request = (
        "Build a polished production-quality landing page for Nexus Forge as a fresh Next.js web-app project. "
        "Nexus Forge is an open-source, self-hosted no-code Backend-as-a-Service with API routes, auth, database schema, "
        "AI agents, Web3 modules, marketplace, security notes, pricing, and conversion CTAs."
    )
    brief = design_providers.design_brief(
        request,
        root=tmp_path,
        product_name="Nexus Forge",
        stack={"stack": "nextjs"},
        create_files=False,
    )
    variant = {
        "id": "hero_only",
        "label": "Hero only",
        "html": """
        <nav><a>Nexus Forge</a><a>Docs</a><a>Marketplace</a><a>Pricing</a></nav>
        <main>
          <section>
            <h1>The AI + Web3 Backend You Own.</h1>
            <p>Self-hosted, open-source BaaS with built-in AI agents, API routes, auth, database schema, Web3 modules, marketplace, and x402 monetization.</p>
            <a href="/docs">Start Building</a>
            <pre><code>npx nexus-forge init</code></pre>
          </section>
        </main>
        <footer>Nexus Forge docs and support</footer>
        """,
    }

    report = design_providers.critique_design_variants([variant], brief)

    reasons = " ".join(report["rejected_variants"][0]["rejection_reasons"]).lower()
    assert report["frontend_handoff_allowed"] is False
    assert "meaningful section" in reasons


def test_stitch_runner_ranks_full_pages_before_logo_assets():
    script = design_providers._stitch_runner_script()

    assert "function screenQuality" in script
    assert "rankedBaseScreens" in script
    assert "const base = baseExtraction.screens[0]" not in script


def test_cached_multipage_design_critique_reuses_stitch_results(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 20, "design_download_remote_assets": False}))
    request = "Build a normal website called Lumora Studio with 4 pages: Home, About, Services, Contact."
    for page in design_providers._website_page_specs(request):
        root = tmp_path / ".friday" / "design" / "pages" / page["id"]
        root.mkdir(parents=True)
        brief = design_providers.design_brief(
            design_providers._website_page_request(request, "Lumora Studio", page),
            root=tmp_path,
            product_name="Lumora Studio",
            stack={"stack": "nextjs", "label": "Next.js web app"},
            artifact_scope=f"pages/{page['id']}",
        )
        (root / "stitch-result.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "variants": [
                        {
                            "id": page["id"],
                            "label": page["label"],
                            "html": "<main aria-label='Lumora Studio'><nav>Home About Services Contact</nav><h1>Lumora Studio</h1><section><p>Lumora Studio supports boutique operations automation, services, contact, inquiry, trust, process, and project outcomes.</p><a href='/contact'>Start inquiry</a></section></main>",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )

    report = design_providers.rerun_cached_multipage_website_design_critique(
        tmp_path,
        product_name="Lumora Studio",
        request=request,
        stack={"stack": "nextjs", "label": "Next.js web app"},
    )

    assert report["frontend_handoff_allowed"] is True
    assert report["selected_page_count"] == 4
    assert (tmp_path / ".friday" / "design" / "pages" / "contact" / "frontend-handoff.json").exists()


def test_design_critique_removes_stale_handoff_when_no_variant_passes(monkeypatch, tmp_path):
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    design_root = tmp_path / ".friday" / "design"
    design_root.mkdir(parents=True)
    for name in ("frontend-handoff.json", "frontend-handoff.md", "selected-design.html"):
        (design_root / name).write_text("stale", encoding="utf-8")
    report = {
        "status": "needs_revision",
        "summary": "No acceptable design.",
        "frontend_handoff_allowed": False,
        "variants": [],
    }

    design_providers._write_design_critique_artifacts(design_root, report)

    assert not (design_root / "frontend-handoff.md").exists()
    assert not (design_root / "selected-design.html").exists()


def test_design_critique_loop_runs_stitch_variants_and_handoff(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 60, "design_download_remote_assets": False}))
    monkeypatch.setenv("STITCH_API_KEY", "configured")
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: True)
    captured = {}

    def fake_run(brief, *, variant_count=1):
        captured["variant_count"] = variant_count
        return {
            "ok": True,
            "status": "generated",
            "summary": "Generated variants.",
            "artifacts": [str(tmp_path / ".friday" / "design" / "stitch-result.json")],
            "result": {
                "ok": True,
                "variants": [
                    {"id": "weak", "label": "Weak", "html": "<main><h1>Dashboard</h1><p>Coming soon placeholder</p></main>"},
                    {
                        "id": "strong",
                        "label": "Strong",
                        "html": "<main aria-label='University Operations Command Center'><nav>Registrar Finance Audit</nav><section><h1>University Operations Command Center</h1><button>Approve course allocation</button><table><tr><td>Student enrollment queue</td><td>SLA risk</td><td>Payment exception</td></tr></table></section></main>",
                    },
                ],
            },
        }

    monkeypatch.setattr(design_providers, "_run_stitch_sdk", fake_run)

    result = design_providers.run_design_critique_loop(
        "Build a university operations dashboard for enrollment, finance, course allocation, student triage, approvals, SLA risk, and audit.",
        root=tmp_path,
        product_name="University Operations Command Center",
        variant_count=2,
        dry_run=False,
    )

    assert captured["variant_count"] == 2
    assert result["ok"] is True
    assert result["selected_variant"]["id"] == "strong"
    assert result["frontend_handoff_allowed"] is True
    assert (tmp_path / ".friday" / "design" / "frontend-handoff.json").exists()


def test_design_critique_loop_reprompts_stitch_after_failed_critique(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(
        design_providers,
        "config_value",
        _config({"design_critique_min_score": 72, "design_download_remote_assets": False, "design_critique_revision_attempts": 1}),
    )
    monkeypatch.setenv("STITCH_API_KEY", "configured")
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: True)
    calls = []

    def fake_run(brief, *, variant_count=1):
        calls.append(brief)
        if len(calls) == 1:
            return {
                "ok": True,
                "status": "generated",
                "artifacts": [],
                "result": {
                    "ok": True,
                    "variants": [
                        {
                            "id": "shallow",
                            "label": "Shallow",
                            "html": "<main><header><nav>QuarterVault Pricing</nav></header><section><h1>QuarterVault</h1><p>Client income, taxes, invoices, and emergency cash.</p><a href='/start'>Start</a></section></main>",
                        }
                    ],
                },
            }
        return {
            "ok": True,
            "status": "generated",
            "artifacts": [],
            "result": {
                "ok": True,
                "variants": [
                    {
                        "id": "revised",
                        "label": "Revised",
                        "html": """
                        <main aria-label="QuarterVault">
                          <header><nav aria-label="Primary">QuarterVault Security Pricing</nav></header>
                          <section><h1>Separate client income before tax season turns loud.</h1><p>QuarterVault helps independent consultants separate client income, quarterly taxes, invoices, retirement savings, and emergency cash.</p><a href="/start">Start clean</a></section>
                          <section><h2>Money-flow proof</h2><figure>Tax reserve account preview</figure><article>Invoice paid</article><article>Emergency reserve</article></section>
                          <section><h2>Security and transparent pricing</h2><p>Clear plans, audit-ready records, secure transfers, and practical controls for consultants.</p></section>
                        </main>
                        """,
                    }
                ],
            },
        }

    monkeypatch.setattr(design_providers, "_run_stitch_sdk", fake_run)

    result = design_providers.run_design_critique_loop(
        "Build a Next.js landing page for a fintech product called QuarterVault. QuarterVault helps consultants separate client income, quarterly taxes, invoices, retirement savings, and emergency cash.",
        root=tmp_path,
        product_name="QuarterVault",
        stack={"stack": "nextjs", "label": "Next.js web app"},
        variant_count=1,
        dry_run=False,
    )

    assert len(calls) == 2
    assert "FRIDAY DESIGN REVISION REQUIRED" in calls[1]["stitch_prompt"]
    assert result["ok"] is True
    assert result["selected_variant"]["id"] == "revised"
    assert result["revision_attempts"][1]["frontend_handoff_allowed"] is True


def test_design_critique_falls_back_to_local_style_when_stitch_times_out(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 60, "design_download_remote_assets": False, "design_stitch_required_for_web": False}))
    monkeypatch.setenv("STITCH_API_KEY", "configured")
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: True)
    monkeypatch.setattr(
        design_providers,
        "_run_stitch_sdk",
        lambda brief, *, variant_count=1: {
            "ok": False,
            "status": "timeout",
            "summary": "Stitch SDK timed out after 300 seconds.",
            "artifacts": [str(tmp_path / ".friday" / "design" / "stitch-run.log")],
        },
    )

    result = design_providers.run_design_critique_loop(
        "Build a web-app for Field Service Dispatch OS with HVAC/plumbing/electrical technician dispatch, emergency jobs, parts readiness, invoices, SLA risk, and customer updates.",
        root=tmp_path,
        product_name="Field Service Dispatch OS",
        variant_count=3,
        dry_run=False,
    )

    assert result["ok"] is True
    assert result["provider_fallback"] == "local_style_memory"
    assert result["generation_status"] == "timeout"
    assert result["selected_variant"]["id"].startswith("local-")
    assert "technician" in (tmp_path / ".friday" / "design" / "selected-design.html").read_text(encoding="utf-8").lower()
    assert "selected-design.html" in (tmp_path / ".friday" / "design" / "design-critique-report.md").read_text(encoding="utf-8")


def test_stitch_required_policy_blocks_fallback_even_when_legacy_flag_allows_it(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(
        design_providers,
        "config_value",
        _config(
            {
                "design_critique_min_score": 60,
                "design_download_remote_assets": False,
                "design_stitch_required_for_web": False,
                "design_stitch_fallback_policy": "stitch_required",
            }
        ),
    )
    monkeypatch.setenv("STITCH_API_KEY", "configured")
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: True)
    monkeypatch.setattr(
        design_providers,
        "_run_stitch_sdk",
        lambda brief, *, variant_count=1: {
            "ok": False,
            "status": "timeout",
            "summary": "Stitch SDK timed out after 300 seconds.",
            "artifacts": [str(tmp_path / ".friday" / "design" / "stitch-run.log")],
        },
    )

    result = design_providers.run_design_critique_loop(
        "Build a website for a premium logistics company.",
        root=tmp_path,
        product_name="Atlas Freight",
        stack={"stack": "nextjs", "label": "Next.js web app"},
        variant_count=2,
        dry_run=False,
    )

    assert result["ok"] is False
    assert result["frontend_handoff_allowed"] is False
    assert result["stitch_fallback_policy"] == "stitch_required"
    assert result["provider_fallback"] == "local_style_memory_supporting_only"
    assert result["fallback_label"] if "fallback_label" in result else True


def test_local_fallback_for_developer_tool_is_landing_not_command_dashboard():
    variants = design_providers._local_fallback_design_variants(
        {
            "request": "Build a single-page landing page for Nexus Forge, a self-hosted open-source backend platform for AI apps, Web3 modules, API routes, CLI install, and docs.",
            "product_name": "Nexus Forge",
        },
        1,
        reason="fetch failed",
    )
    html = variants[0]["html"].lower()

    assert "npx nexus-forge init" in html
    assert "get /v1/agents/process" in html
    assert "base wallet" in html
    assert "pricing" in html
    assert "generated from local style memory after provider fallback" not in html


def test_design_critique_blocks_local_handoff_when_stitch_is_required(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({"design_critique_min_score": 60, "design_download_remote_assets": False, "design_stitch_required_for_web": True}))
    monkeypatch.setenv("STITCH_API_KEY", "configured")
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: True)
    monkeypatch.setattr(
        design_providers,
        "_run_stitch_sdk",
        lambda brief, *, variant_count=1: {
            "ok": False,
            "status": "timeout",
            "summary": "Stitch SDK timed out after 300 seconds.",
            "artifacts": [str(tmp_path / ".friday" / "design" / "stitch-run.log")],
        },
    )

    result = design_providers.run_design_critique_loop(
        "Build a web-app for Field Service Dispatch OS with technician dispatch, emergency jobs, parts readiness, invoices, SLA risk, and customer updates.",
        root=tmp_path,
        product_name="Field Service Dispatch OS",
        stack={"stack": "nextjs", "label": "Next.js web app"},
        variant_count=3,
        dry_run=False,
    )

    assert result["ok"] is False
    assert result["frontend_handoff_allowed"] is False
    assert result["selected_variant"] is None
    assert result["provider_fallback"] == "local_style_memory_supporting_only"
    assert result["stitch_required"] is True
    assert not (tmp_path / ".friday" / "design" / "frontend-handoff.md").exists()


def test_stitch_timeout_uses_captured_success_payload(monkeypatch, tmp_path):
    monkeypatch.setattr(design_providers, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(design_providers, "config_value", _config({"design_stitch_timeout_seconds": 1}))
    killed = {}

    class Process:
        returncode = None
        args = ["node"]
        pid = 789

        def communicate(self, timeout=None):
            if timeout is not None:
                raise design_providers.subprocess.TimeoutExpired(self.args, timeout)
            return ('{"ok":true,"projectId":"p1","screenId":"s1","variants":[]}\n', "")

    monkeypatch.setattr(design_providers.subprocess, "Popen", lambda *args, **kwargs: Process())
    monkeypatch.setattr(design_providers.command_runner, "terminate_process_tree", lambda pid: killed.setdefault("pid", pid))

    result = design_providers._run_stitch_sdk({"root": str(tmp_path), "stitch_prompt": "Design", "product_name": "Demo"})

    assert result["ok"] is True
    assert result["status"] == "generated"
    assert killed["pid"] == 789
    assert (tmp_path / ".friday" / "design" / "stitch-result.json").exists()


def test_stitch_failure_summary_extracts_mcp_error():
    summary = design_providers._stitch_failure_summary(
        "[friday-stitch] generate:base:error MCP error -32001: Request timed out 62896ms\nStitchError: MCP error -32001: Request timed out\n",
        fallback="Stitch SDK exited with code 1.",
    )

    assert summary == "Stitch SDK failed: MCP error -32001: Request timed out"


def test_provider_readiness_includes_design_generation(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: False)
    monkeypatch.setattr(provider_readiness, "github_status", lambda root="": {"github_authenticated": False})
    monkeypatch.setattr(provider_readiness, "production_readiness", lambda: {"ok": False, "checks": []})

    status = provider_readiness.status(probe=False, root=tmp_path)

    assert "design_generation" in status["providers"]
    assert status["providers"]["design_generation"]["providers"]["local_style_memory"]["ready"] is True


def test_design_agent_context_names_stitch_and_v0_policy(monkeypatch, tmp_path):
    monkeypatch.setattr(style_profiles, "DB_PATH", tmp_path / "style_profiles.sqlite3")
    monkeypatch.setattr(design_providers, "config_value", _config({}))
    monkeypatch.delenv("STITCH_API_KEY", raising=False)
    monkeypatch.setattr(design_providers, "_node_package_available", lambda package, probe: False)

    context = design_providers.agent_context("ui_ux_designer", "Design a dashboard", root=tmp_path)

    assert "Google Stitch SDK first" in context
    assert "v0 only when Friday has verified it is free" in context
    assert "Local style profile count" in context

from core import coding_workflow, project_scaffolds


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


def test_mobile_keyword_generates_flutter_files():
    stack = project_scaffolds.detect_stack("build a mobile app for client invoices")
    files = project_scaffolds.files_for_stack(stack, "InvoicePilot", "build a mobile app for client invoices")

    assert stack["stack"] == "flutter"
    assert "pubspec.yaml" in files
    assert "lib/main.dart" in files
    assert "lib/home_screen.dart" in files
    assert "lib/workflow_store.dart" in files
    assert "flutter" in files["pubspec.yaml"]


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

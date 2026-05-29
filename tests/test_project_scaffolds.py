from core import project_scaffolds


def test_web_app_keyword_generates_nextjs_app_router_files():
    stack = project_scaffolds.detect_stack("build a web-app for client invoices")
    files = project_scaffolds.files_for_stack(stack, "InvoicePilot", "build a web-app for client invoices")

    assert stack["stack"] == "nextjs"
    assert "next" in files["package.json"]
    assert "src/app/page.tsx" in files
    assert "src/app/layout.tsx" in files


def test_mobile_keyword_generates_flutter_files():
    stack = project_scaffolds.detect_stack("build a mobile app for client invoices")
    files = project_scaffolds.files_for_stack(stack, "InvoicePilot", "build a mobile app for client invoices")

    assert stack["stack"] == "flutter"
    assert "pubspec.yaml" in files
    assert "lib/main.dart" in files
    assert "flutter" in files["pubspec.yaml"]


def test_backend_defaults_to_fastify_and_honors_language_requests():
    default_stack = project_scaffolds.detect_stack("build a backend for client invoices")
    rust_stack = project_scaffolds.detect_stack("build a rust backend for client invoices")
    go_stack = project_scaffolds.detect_stack("build a go backend for client invoices")
    python_stack = project_scaffolds.detect_stack("build a python backend for client invoices")

    assert default_stack["stack"] == "node_fastify"
    assert "src/server.js" in project_scaffolds.files_for_stack(default_stack, "InvoicePilot", "backend")
    assert rust_stack["stack"] == "rust_axum"
    assert "src/main.rs" in project_scaffolds.files_for_stack(rust_stack, "InvoicePilot", "backend")
    assert go_stack["stack"] == "go_api"
    assert "main.go" in project_scaffolds.files_for_stack(go_stack, "InvoicePilot", "backend")
    assert python_stack["stack"] == "python_fastapi"
    assert "invoicepilot/main.py" in project_scaffolds.files_for_stack(python_stack, "InvoicePilot", "backend")

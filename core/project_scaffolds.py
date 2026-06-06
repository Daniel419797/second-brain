"""Stack-aware starter project scaffolds for autonomous coding."""

from __future__ import annotations

import json
import re
from typing import Any

from core import content_strategy, web_project_contract


def detect_stack(request: str) -> dict[str, str]:
    text = str(request or "").lower()
    words = set(_words(text))
    web_requested = _wants_web_app(text, words)
    if web_requested:
        return {"kind": "web_app", "stack": "nextjs", "language": "typescript", "label": "Next.js web app"}
    if _wants_mobile_app(text, words):
        return {"kind": "mobile", "stack": "flutter", "language": "dart", "label": "Flutter mobile app"}
    if _wants_backend(text, words):
        if "rust" in words or "axum" in words:
            return {"kind": "backend", "stack": "rust_axum", "language": "rust", "label": "Rust Axum backend"}
        if "go" in words or "golang" in words or "gin" in words:
            return {"kind": "backend", "stack": "go_api", "language": "go", "label": "Go HTTP backend"}
        if "python" in words or "fastapi" in words or "flask" in words or "django" in words:
            return {"kind": "backend", "stack": "python_fastapi", "language": "python", "label": "Python FastAPI backend"}
        return {"kind": "backend", "stack": "node_fastify", "language": "javascript", "label": "Node.js Fastify backend"}
    return {"kind": "web_app", "stack": "nextjs", "language": "typescript", "label": "Next.js web app"}


def _wants_web_app(text: str, words: set[str]) -> bool:
    return bool(
        "nextjs" in words
        or "next.js" in text
        or _affirmative_web_app(text)
        or "website" in words
        or "frontend" in words
        or "dashboard" in words
        or "portal" in words
        or "site" in words
        or any(
            phrase in text
            for phrase in (
                "marketing website",
                "normal website",
                "company website",
                "business website",
                "landing page",
                "landing website",
            )
        )
    )


def _wants_mobile_app(text: str, words: set[str]) -> bool:
    if "flutter" in words:
        return True
    if _wants_web_app(text, words):
        return False
    if re.search(r"\b(?:mobile|android|ios|iphone|ipad)\s+(?:app|application)\b", text):
        return True
    if re.search(r"\b(?:app|application)\s+(?:for\s+)?(?:mobile|android|ios|iphone|ipad)\b", text):
        return True
    if "android" in words or "ios" in words:
        return True
    if "mobile" in words:
        viewport_context = re.search(r"\b(?:screenshot|screenshots|viewport|viewports|responsive|breakpoint|browser|desktop\s+and\s+mobile|mobile\s+and\s+desktop)\b", text)
        return viewport_context is None
    return False


def _wants_backend(text: str, words: set[str]) -> bool:
    if any(phrase in text for phrase in ("backend only", "api only", "server only", "not a web-app", "not a web app", "not web-app", "not web app")):
        return True
    if "fastify" in words or "axum" in words or "gin" in words or "fastapi" in words:
        return True
    if "backend" in words or "microservice" in words:
        return True
    if "api" in words and not _affirmative_web_app(text):
        return True
    if "server" in words and not _affirmative_web_app(text):
        return True
    if "service" in words and any(word in words for word in {"endpoint", "endpoints", "route", "routes", "fastify", "api", "server"}):
        return True
    return False


def _affirmative_web_app(text: str) -> bool:
    normalized = str(text or "").lower()
    negated = ("not a web-app", "not a web app", "not web-app", "not web app", "backend only", "api only")
    cleaned = normalized
    for phrase in negated:
        cleaned = cleaned.replace(phrase, " ")
    return "web-app" in cleaned or "web app" in cleaned


def product_name(request: str) -> str:
    raw = str(request or "")
    text = raw.lower()
    if "hackonvibe" in text or "hack on vibe" in text:
        return "VibeOps"
    company = _explicit_company_name(raw)
    if company:
        return company
    explicit = _explicit_product_name(raw)
    if explicit:
        return explicit
    if any(term in text for term in ("university", "campus", "registrar", "lecturer", "student", "course approval", "bursary")):
        return "University Management Dashboard"
    if _is_field_service_request(text):
        return "Field Service Dispatch OS"
    if _is_restaurant_shift_request(text):
        return "Restaurant Shift Command OS"
    words = [word.capitalize() for word in _keywords(request)[:2]]
    return f"{' '.join(words)} Workspace" if words else "FlowPilot"


def project_slug(request: str, stack: dict[str, str] | None = None) -> str:
    text = str(request or "").lower()
    if "hackonvibe" in text or "hack on vibe" in text:
        return "vibeops-hackathon-mvp"
    company = _explicit_company_name(request)
    if company:
        suffix = {
            "flutter": "mobile",
            "nextjs": "web",
            "node_fastify": "api",
            "python_fastapi": "api",
            "go_api": "api",
            "rust_axum": "api",
        }.get((stack or {}).get("stack", ""), "")
        base = _slug(company)
        return f"{base}-{suffix}" if suffix and not base.endswith(suffix) else base
    explicit = _explicit_product_name(request)
    if explicit:
        suffix = {
            "flutter": "mobile",
            "nextjs": "web",
            "node_fastify": "api",
            "python_fastapi": "api",
            "go_api": "api",
            "rust_axum": "api",
        }.get((stack or {}).get("stack", ""), "")
        base = _slug(explicit)
        return f"{base}-{suffix}" if suffix and not base.endswith(suffix) else base
    words = _keywords(request)[:5] or ["ai", "workflow", "app"]
    suffix = {
        "flutter": "mobile",
        "nextjs": "web",
        "node_fastify": "api",
        "python_fastapi": "api",
        "go_api": "api",
        "rust_axum": "api",
    }.get((stack or {}).get("stack", ""), "")
    base = _slug("-".join(words))
    return f"{base}-{suffix}" if suffix and not base.endswith(suffix) else base


def _explicit_product_name(request: str) -> str:
    text = _clean(request)
    patterns = [
        r"\bfor\s+(?:an?\s+)?([A-Z][A-Za-z0-9&' -]{3,80}?\s(?:OS|Dashboard|Portal|Studio|Atelier|Command Center|Command|Manager|Pilot|Console|Workspace|App))\s*:",
        r"\bcalled\s+(?:an?\s+)?([A-Z][A-Za-z0-9&' -]{3,80}?\s(?:OS|Dashboard|Portal|Studio|Atelier|Command Center|Command|Manager|Pilot|Console|Workspace|App))\b",
        r"\bnamed\s+(?:an?\s+)?([A-Z][A-Za-z0-9&' -]{3,80}?\s(?:OS|Dashboard|Portal|Studio|Atelier|Command Center|Command|Manager|Pilot|Console|Workspace|App))\b",
        r"\bcalled\s+(?:an?\s+)?([A-Z][A-Za-z0-9&'-]{2,64}(?:\s+[A-Z][A-Za-z0-9&'-]{1,40}){0,3})(?=\s*(?:[:.;,]|$|\s+(?:is|helps|offers|builds|provides|for|as|that|which)\b))",
        r"\bnamed\s+(?:an?\s+)?([A-Z][A-Za-z0-9&'-]{2,64}(?:\s+[A-Z][A-Za-z0-9&'-]{1,40}){0,3})(?=\s*(?:[:.;,]|$|\s+(?:is|helps|offers|builds|provides|for|as|that|which)\b))",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        name = re.sub(r"\s+", " ", match.group(1)).strip(" -:")
        if name and not _looks_like_prompt_fragment(name):
            return name
    return ""


def _explicit_company_name(request: str) -> str:
    text = _clean(request)
    patterns = [
        r"\bbrand(?:\s+text|\s+name)?\s+as\s+exactly\s+([A-Z][A-Za-z0-9&'. -]{2,80}?)(?:[.;,\n]|$)",
        r"\bvisible\s+brand\s+text\s+as\s+exactly\s+([A-Z][A-Za-z0-9&'. -]{2,80}?)(?:[.;,\n]|$)",
        r"\blanding\s+page\s+for\s+([A-Z][A-Za-z0-9&'. -]{2,80}?)(?:\s+as\s+(?:a|an)\s+|[.;,\n]|$)",
        r"\bwebsite\s+for\s+([A-Z][A-Za-z0-9&'. -]{2,80}?)(?:\s+as\s+(?:a|an)\s+|[.;,\n]|$)",
        r"\bfor\s+([A-Z][A-Za-z0-9&'. -]{2,80}?)(?:\s+as\s+(?:a|an)\s+)",
        r"\bfor\s+([A-Z][A-Za-z0-9&'. -]{2,80}?)(?:,\s+(?:a|an)\s+fictional\b)",
        r"\bfor\s+([A-Z][A-Za-z0-9&'. -]{2,80}?)(?:,\s+(?:a|an)\s+real\b|,\s+(?:a|an)\s+[a-z]+(?:\s+[a-z]+){0,4}\s+company\b)",
        r"\b(?:real\s+)?(?:construction\s+)?company\s*:\s*([A-Z][A-Za-z0-9&'. -]{2,100}?)(?:[.;\n]|$)",
        r"\b(?:business|brand|organization|organisation)\s*:\s*([A-Z][A-Za-z0-9&'. -]{2,100}?)(?:[.;\n]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        name = re.sub(r"\s+", " ", match.group(1)).strip(" -:")
        if name and not _looks_like_prompt_fragment(name):
            return name
    return ""


def _looks_like_prompt_fragment(value: str) -> bool:
    lowered = str(value or "").lower()
    bad = ("for ", "with ", "that ", "use next", "make the copy", "follow the")
    return any(term in lowered for term in bad)


def files_for_stack(stack: dict[str, str], name: str, request: str) -> dict[str, str]:
    stack_id = stack.get("stack") or "nextjs"
    if stack_id == "flutter":
        files = _flutter_files(name, request)
    elif stack_id == "node_fastify":
        files = _fastify_files(name, request)
    elif stack_id == "python_fastapi":
        files = _fastapi_files(name, request)
    elif stack_id == "go_api":
        files = _go_files(name, request)
    elif stack_id == "rust_axum":
        files = _rust_files(name, request)
    else:
        files = _nextjs_files(name, request)
    for path, content in _production_support_files(stack, name, request).items():
        files.setdefault(path, content)
    return files


def _nextjs_files(name: str, request: str) -> dict[str, str]:
    slug = _slug(name)
    files = {
        "package.json": _json(
            {
                "name": slug,
                "private": True,
                "version": "0.1.0",
                "scripts": {
                    "dev": "next dev",
                    "build": "next build",
                    "start": "next start",
                    "lint": "eslint .",
                    "typecheck": "tsc --noEmit",
                    "test": "vitest run",
                    "test:watch": "vitest",
                    "test:coverage": "vitest run --coverage",
                    "audit": "npm audit --audit-level=moderate",
                },
                "dependencies": {
                    "@tanstack/react-query": "5.100.14",
                    "axios": "1.16.1",
                    "class-variance-authority": "0.7.1",
                    "clsx": "2.1.1",
                    "lucide-react": "0.468.0",
                    "next": "16.2.6",
                    "react": "19.2.6",
                    "react-dom": "19.2.6",
                    "tailwind-merge": "3.6.0",
                    "zustand": "5.0.14",
                },
                "devDependencies": {
                    "@tailwindcss/postcss": "4.3.0",
                    "@testing-library/jest-dom": "6.9.1",
                    "@testing-library/react": "16.3.2",
                    "@testing-library/user-event": "14.6.1",
                    "@types/node": "25.9.1",
                    "@types/react": "19.2.15",
                    "@types/react-dom": "19.2.3",
                    "@vitejs/plugin-react": "6.0.2",
                    "eslint": "9.39.4",
                    "eslint-config-next": "16.2.6",
                    "jsdom": "29.1.1",
                    "postcss": "8.5.10",
                    "tailwindcss": "4.3.0",
                    "typescript": "5.9.3",
                    "vitest": "4.1.7",
                },
                "overrides": {"postcss": "8.5.10"},
            }
        ),
        "tsconfig.json": _json(
            {
                "compilerOptions": {
                    "target": "ES2017",
                    "lib": ["dom", "dom.iterable", "esnext"],
                    "allowJs": True,
                    "skipLibCheck": True,
                    "strict": True,
                    "noEmit": True,
                    "esModuleInterop": True,
                    "module": "esnext",
                    "moduleResolution": "bundler",
                    "resolveJsonModule": True,
                    "isolatedModules": True,
                    "jsx": "react-jsx",
                    "incremental": True,
                    "plugins": [{"name": "next"}],
                    "paths": {"@/*": ["./src/*"]},
                },
                "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts", ".next/dev/types/**/*.ts"],
                "exclude": ["node_modules"],
            }
        ),
        "next-env.d.ts": "/// <reference types=\"next\" />\n/// <reference types=\"next/image-types/global\" />\n\n",
        "next.config.mjs": "/** @type {import('next').NextConfig} */\nconst nextConfig = {};\n\nexport default nextConfig;\n",
        "eslint.config.mjs": "import nextVitals from 'eslint-config-next/core-web-vitals';\nimport nextTypescript from 'eslint-config-next/typescript';\n\nconst eslintConfig = [\n  ...nextVitals,\n  ...nextTypescript,\n  {\n    ignores: ['.next/**', 'out/**', 'build/**', 'coverage/**'],\n  },\n];\n\nexport default eslintConfig;\n",
        "postcss.config.mjs": "const config = { plugins: { '@tailwindcss/postcss': {} } };\n\nexport default config;\n",
        "vitest.config.ts": "import { fileURLToPath } from 'node:url';\nimport { defineConfig } from 'vitest/config';\nimport react from '@vitejs/plugin-react';\n\nexport default defineConfig({\n  plugins: [react()],\n  test: {\n    environment: 'jsdom',\n    globals: true,\n    setupFiles: './src/test/setup.ts',\n  },\n  resolve: {\n    alias: {\n      '@': fileURLToPath(new URL('./src', import.meta.url)),\n    },\n  },\n});\n",
        "components.json": _json(
            {
                "$schema": "https://ui.shadcn.com/schema.json",
                "style": "new-york",
                "rsc": True,
                "tsx": True,
                "tailwind": {
                    "config": "",
                    "css": "src/app/globals.css",
                    "baseColor": "slate",
                    "cssVariables": True,
                    "prefix": "",
                },
                "iconLibrary": "lucide",
                "aliases": {
                    "components": "@/components",
                    "utils": "@/lib/utils",
                    "ui": "@/components/ui",
                    "lib": "@/lib",
                    "hooks": "@/hooks",
                },
            }
        ),
        "proxy.ts": "import { NextResponse } from 'next/server';\n\nexport function proxy() {\n  const response = NextResponse.next();\n  response.headers.set('x-friday-project', 'production-ready-nextjs');\n  return response;\n}\n\nexport const config = {\n  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],\n};\n",
        "src/app/layout.tsx": f"import './globals.css';\n\nexport const metadata = {{ title: {_json_value(name)}, description: 'AI-assisted everyday workflow tool' }};\n\nexport default function RootLayout({{ children }}: {{ children: React.ReactNode }}) {{\n  return <html lang=\"en\"><body>{{children}}</body></html>;\n}}\n",
        "src/app/page.tsx": _next_page(name, request),
        "src/app/error.tsx": _next_error_boundary(),
        "src/app/(auth)/layout.tsx": "export default function AuthLayout({ children }: { children: React.ReactNode }) {\n  return <main className=\"auth-shell\">{children}</main>;\n}\n",
        "src/app/(auth)/login/page.tsx": "import { LoginPage } from '@/components/Auth/LoginPage';\n\nexport default function Page() {\n  return <LoginPage />;\n}\n",
        "src/app/(dashboard)/layout.tsx": "import { AppShell } from '@/components/layout/AppShell';\n\nexport default function DashboardLayout({ children }: { children: React.ReactNode }) {\n  return <AppShell>{children}</AppShell>;\n}\n",
        "src/app/(dashboard)/workspace/page.tsx": "import { WorkspacePage } from '@/components/Workspace/WorkspacePage';\n\nexport default function Page() {\n  return <WorkspacePage />;\n}\n",
        "src/app/privacy/page.tsx": _policy_page(name, "Privacy Policy", "Privacy, retention, and customer-data handling are reviewed before market readiness."),
        "src/app/terms/page.tsx": _policy_page(name, "Terms of Service", "Terms, support expectations, billing, and launch obligations are approved before public release."),
        "src/app/api/health/route.ts": "import { NextResponse } from 'next/server';\n\nexport async function GET() {\n  return NextResponse.json({ status: 'ok', service: 'friday-production-app' });\n}\n",
        "src/app/api/brief/route.ts": _next_brief_route(),
        "src/components/Auth/LoginPage.tsx": _next_login_page(name),
        "src/components/Landing/HomePage.tsx": _next_home_page(),
        "src/components/Workspace/WorkspacePage.tsx": _next_workspace_page(),
        "src/components/Workspace/WorkspaceConsole.tsx": _next_workspace_console(),
        "src/components/Workspace/WorkItemCard.tsx": _next_work_item_card(),
        "src/components/Shared/Footer.tsx": _next_footer(name),
        "src/components/layout/AppShell.tsx": _next_app_shell(),
        "src/components/layout/Sidebar.tsx": _next_sidebar(),
        "src/components/layout/TopBar.tsx": _next_topbar(name),
        "src/components/layout/nav-items.tsx": _next_nav_items(),
        "src/components/ui/badge.tsx": _next_ui_badge(),
        "src/components/ui/button.tsx": _next_ui_button(),
        "src/components/ui/card.tsx": _next_ui_card(),
        "src/components/ui/input.tsx": _next_ui_input(),
        "src/components/ui/textarea.tsx": _next_ui_textarea(),
        "src/hooks/useAccessToken.ts": _next_use_access_token(),
        "src/hooks/useBriefDraft.ts": _next_use_brief_draft(),
        "src/lib/security/csp.ts": _next_csp(),
        "src/lib/authTokens.ts": _next_auth_tokens(),
        "src/lib/utils.ts": _next_utils(),
        "src/lib/productPlan.ts": _next_product_plan(name, request),
        "src/services/api.ts": _next_api_service(),
        "src/services/BriefService.ts": _next_brief_service(),
        "src/services/__tests__/BriefService.test.ts": _next_brief_service_test(),
        "src/store/workspaceStore.ts": _next_workspace_store(),
        "src/store/__tests__/workspaceStore.test.ts": _next_workspace_store_test(),
        "src/test/setup.ts": "import '@testing-library/jest-dom/vitest';\n",
        "src/test/test-utils.tsx": "import { render, type RenderOptions } from '@testing-library/react';\nimport type { ReactElement } from 'react';\n\nexport function renderWithApp(ui: ReactElement, options?: RenderOptions) {\n  return render(ui, options);\n}\n",
        "src/types/index.ts": _next_types(),
        "src/app/globals.css": _next_css(),
        "FRONTEND_STRUCTURE.md": _next_frontend_structure(),
        "README.md": _product_readme(name, request, "Next.js web app", "npm install\nnpm run dev"),
        ".gitignore": "node_modules\n.next\nout\n.env\n.env.local\n.DS_Store\n",
    }
    if _is_single_landing_page_request(request):
        files = _as_single_landing_files(files, name, request)
    elif _is_marketing_website_request(request) and _uses_standard_marketing_pages(request):
        files = _as_marketing_website_files(files, name, request)
    elif web_project_contract.has_route_contract(request, stack={"stack": "nextjs"}):
        files = _with_web_route_contract_files(files, name, request)
    else:
        files = _with_web_route_contract_files(files, name, request)
    return files


def _production_support_files(stack: dict[str, str], name: str, request: str) -> dict[str, str]:
    stack_id = stack.get("stack") or "nextjs"
    files = {
        "SECURITY.md": f"# Security\n\n{name} keeps deploys, outbound messaging, billing, ads, and customer data access approval-gated until explicitly cleared.\n",
        "docs/OPERATIONS.md": "# Operations\n\n- Keep a health check online.\n- Record preview URL, rollback target, and owner for every release.\n- Monitor errors, latency, dependency spend, and failed automations.\n",
        "docs/LAUNCH.md": f"# Launch\n\nProduct: {name}\n\nRequest: {_clean(request)}\n\nPricing, ads, outreach, billing, and production deploy must be approved before public launch.\n",
        ".github/workflows/friday-production.yml": _production_workflow(stack_id),
    }
    if stack_id == "nextjs":
        files.update(
            {
                ".env.example": "APP_ENV=development\nFRIDAY_APPROVAL_REQUIRED=true\n",
                "Dockerfile": "FROM node:22-alpine AS deps\nWORKDIR /app\nCOPY package*.json ./\nRUN npm ci || npm install\nCOPY . .\nRUN npm run build\nEXPOSE 3000\nCMD [\"npm\", \"run\", \"start\", \"--\", \"--hostname\", \"0.0.0.0\"]\n",
                "vercel.json": "{\n  \"framework\": \"nextjs\",\n  \"buildCommand\": \"npm run build\",\n  \"devCommand\": \"npm run dev\"\n}\n",
            }
        )
    elif stack_id == "node_fastify":
        files["Dockerfile"] = "FROM node:22-alpine\nWORKDIR /app\nCOPY package*.json ./\nRUN npm ci || npm install\nCOPY . .\nEXPOSE 3000\nCMD [\"npm\", \"run\", \"start\"]\n"
    elif stack_id == "python_fastapi":
        package = _slug(name).replace("-", "_")
        files["Dockerfile"] = f"FROM python:3.12-slim\nWORKDIR /app\nCOPY pyproject.toml ./\nRUN python -m pip install --no-cache-dir -e .[dev]\nCOPY . .\nEXPOSE 8000\nCMD [\"python\", \"-m\", \"uvicorn\", \"{package}.main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"8000\"]\n"
    elif stack_id == "go_api":
        files["Dockerfile"] = "FROM golang:1.22-alpine AS build\nWORKDIR /src\nCOPY . .\nRUN go test ./... && go build -o /app/server .\nFROM alpine:3.20\nCOPY --from=build /app/server /server\nEXPOSE 8080\nCMD [\"/server\"]\n"
    elif stack_id == "rust_axum":
        files["Dockerfile"] = "FROM rust:1.78 AS build\nWORKDIR /src\nCOPY . .\nRUN cargo test && cargo build --release\nFROM debian:bookworm-slim\nCOPY --from=build /src/target/release/* /app/server\nEXPOSE 3000\nCMD [\"/app/server\"]\n"
    else:
        files["docs/MOBILE_RELEASE.md"] = "# Mobile Release\n\n- Run flutter test and flutter analyze.\n- Verify Android/iOS signing outside source control.\n- Attach store screenshots and privacy labels before release.\n"
    return files


def _is_marketing_website_request(request: str) -> bool:
    text = str(request or "").lower()
    app_text = text
    for phrase in ("no dashboard", "not a dashboard", "no login", "no login portal", "not a login portal", "not a portal", "no portal", "no app workspace", "no workspace", "not an app workspace"):
        app_text = app_text.replace(phrase, " ")
    wants_site = any(
        phrase in text
        for phrase in (
            "normal website",
            "marketing website",
            "multi-page website",
            "multipage website",
            "website with",
            "four pages",
            "4 pages",
            "landing website",
            "company website",
            "business website",
        )
    )
    app_intent = any(
        phrase in app_text
        for phrase in (
            "dashboard",
            "portal",
            "command center",
            "workspace",
            "web-app dashboard",
            "management app",
            "admin app",
        )
    )
    return wants_site and not app_intent


def _uses_standard_marketing_pages(request: str) -> bool:
    routes = web_project_contract.expected_routes(request, stack={"stack": "nextjs"})
    if not routes:
        return True
    route_ids = {route.get("id", "") for route in routes}
    return route_ids.issubset({"home", "about", "services", "contact"})


def _is_single_landing_page_request(request: str) -> bool:
    text = str(request or "").lower()
    single_landing = any(term in text for term in ("single-page landing", "single page landing", "landing page", "one-page landing", "one page landing"))
    multi = any(term in text for term in ("four-page", "four page", "4-page", "4 page", "multi-page", "multipage", "required screens/routes"))
    dashboard_allowed = not any(term in text for term in ("no dashboard", "no workspace", "no login", "no login portal", "single landing page only", "single-page landing page only"))
    if not single_landing or multi:
        return False
    if any(term in text for term in ("dashboard preview", "operations dashboard", "admin dashboard")) and dashboard_allowed:
        return False
    return True


def _as_single_landing_files(files: dict[str, str], name: str, request: str) -> dict[str, str]:
    blocked_prefixes = (
        "src/app/(auth)/",
        "src/app/(dashboard)/",
        "src/app/privacy/",
        "src/app/terms/",
        "src/components/Auth/",
        "src/components/Landing/HomePage.tsx",
        "src/components/layout/",
        "src/components/Shared/",
        "src/components/Workspace/",
        "src/hooks/useAccessToken.ts",
        "src/hooks/useBriefDraft.ts",
        "src/lib/authTokens.ts",
        "src/services/api.ts",
        "src/services/BriefService.ts",
        "src/services/__tests__/",
        "src/store/",
        "src/lib/productPlan.ts",
        "src/app/api/brief/",
    )
    next_files = {
        path: content
        for path, content in files.items()
        if not any(path.startswith(prefix) for prefix in blocked_prefixes)
    }
    content = _single_landing_content(name, request)
    next_files.update(
        {
            "src/app/layout.tsx": f"import './globals.css';\n\nexport const metadata = {{ title: {_json_value(name)}, description: {_json_value(content['summary'])} }};\n\nexport default function RootLayout({{ children }}: {{ children: React.ReactNode }}) {{\n  return <html lang=\"en\"><body>{{children}}</body></html>;\n}}\n",
            "src/app/page.tsx": "import { SingleLandingPage } from '@/components/Landing/SingleLandingPage';\n\nexport default function Home() {\n  return <SingleLandingPage />;\n}\n",
            "src/components/Landing/SingleLandingPage.tsx": _single_landing_page(),
            "src/lib/landingContent.ts": "export const landingContent = " + json.dumps(content, ensure_ascii=True, indent=2, sort_keys=True) + " as const;\n",
            "src/components/Landing/__tests__/landingContent.test.ts": _single_landing_content_test(),
            "FRONTEND_STRUCTURE.md": "# Frontend Structure\n\n- `src/app/page.tsx` is the only product route for this single landing page.\n- `src/components/Landing/SingleLandingPage.tsx` owns the landing composition.\n- `src/lib/landingContent.ts` owns product-specific copy, nav anchors, pricing, docs, and final CTA text.\n- No dashboard, login portal, workspace shell, or scaffold app routes are generated for single landing requests.\n",
            "README.md": _product_readme(name, request, "Next.js single landing page", "npm install\nnpm run dev"),
        }
    )
    next_files["src/app/globals.css"] = next_files.get("src/app/globals.css", "") + _single_landing_css()
    return next_files


def _single_landing_content(name: str, request: str) -> dict[str, Any]:
    terms = web_project_contract.domain_terms_from_request(request, limit=8)
    lower = str(request or "").lower()
    developer = any(term in lower for term in ("developer", "api", "cli", "sdk", "web3", "backend", "open-source", "self-hosted"))
    sections = [
        {"id": "product", "label": "Product", "title": "Backend primitives without losing control", "body": f"{name} keeps auth, schema, API routes, realtime workflows, and proof close to the codebase."},
        {"id": "ai-web3", "label": "AI + Web3", "title": "Agents, modules, and payments in one forge", "body": "AI workflows, Web3 modules, wallet actions, and x402 monetization are treated as backend capabilities, not bolt-on demos."},
        {"id": "marketplace", "label": "Marketplace", "title": "A plugin surface builders can inspect", "body": "Teams can extend the platform through reviewed plugins, integration modules, and reusable backend blocks."},
        {"id": "self-hosting", "label": "Self-hosting", "title": "Self-host first, cloud when it earns trust", "body": "Run locally or self-hosted, then move to managed infrastructure only when security, operations, and pricing are clear."},
        {"id": "pricing", "label": "Pricing", "title": "Pricing for makers and production teams", "body": "Start open source, upgrade for managed hosting, monitoring, and compliance support."},
        {"id": "docs", "label": "Docs", "title": "Docs that start with the CLI", "body": "Installation, API routes, schema examples, and deployment proof stay visible before the first integration call."},
    ]
    if not developer:
        sections = [
            {"id": "product", "label": "Product", "title": f"{name} makes the offer understandable", "body": "The landing page explains what the product does, who it helps, and why a visitor should act now."},
            {"id": "proof", "label": "Proof", "title": "Proof before persuasion", "body": "Claims are paired with practical outcomes, workflow examples, and concrete next steps."},
            {"id": "pricing", "label": "Pricing", "title": "Pricing stays visible", "body": "Visitors can understand the likely buying path before booking a call."},
            {"id": "docs", "label": "Docs", "title": "Launch notes and support path", "body": "Docs, support, privacy, and launch expectations stay easy to find."},
        ]
    return {
        "brand": name,
        "summary": web_project_contract._request_summary(request),
        "tone": web_project_contract._tone_for_archetype(web_project_contract.design_archetype(request)),
        "domainTerms": terms,
        "nav": [{"href": f"#{section['id']}", "label": section["label"]} for section in sections],
        "hero": {
            "eyebrow": "developer backend forge" if developer else "focused landing page",
            "title": f"Build the backend your AI app needs without giving up control." if developer else f"{name} turns visitors into qualified conversations.",
            "body": web_project_contract._request_summary(request),
            "primary": "Start building" if developer else "Start a project",
            "secondary": "CLI install" if developer else "See proof",
        },
        "terminal": [
            "npx nexus-forge init",
            "schema User { id uuid @primary }",
            "GET /v1/agents/process",
            "web3 module active: Base wallet",
        ] if developer else [
            "lead captured",
            "offer clarified",
            "pricing reviewed",
            "demo request ready",
        ],
        "sections": sections,
        "pricing": [
            {"name": "Open Source", "price": "$0", "items": ["Self-hosted", "Local database", "Basic auth", "Community plugins"]},
            {"name": "Pro", "price": "$29/mo", "items": ["Managed hosting", "Realtime WebSockets", "Web3 modules", "Monitoring"]},
            {"name": "Enterprise", "price": "Custom", "items": ["Dedicated clusters", "Compliance support", "Private registry", "SLA support"]},
        ] if developer else [
            {"name": "Starter", "price": "$900", "items": ["Landing page", "Copy pass", "Analytics", "Launch checklist"]},
            {"name": "Growth", "price": "$2,400", "items": ["4 sections", "Lead form", "SEO", "Support notes"]},
            {"name": "Custom", "price": "Talk to us", "items": ["Custom design", "Integrations", "Content system", "Launch support"]},
        ],
    }


def _single_landing_page() -> str:
    return """import Link from 'next/link';
import { ArrowRight, CheckCircle2, Copy, Terminal } from 'lucide-react';
import { landingContent } from '@/lib/landingContent';

export function SingleLandingPage() {
  return (
    <main className="single-landing">
      <header className="single-nav">
        <Link href="/" className="single-brand">{landingContent.brand}</Link>
        <nav aria-label="Landing sections">
          {landingContent.nav.map((item) => <a key={item.href} href={item.href}>{item.label}</a>)}
        </nav>
        <a href="#pricing" className="single-nav-cta">Start building <ArrowRight size={15} /></a>
      </header>

      <section className="single-hero">
        <div className="single-copy">
          <p className="single-eyebrow">{landingContent.hero.eyebrow}</p>
          <h1>{landingContent.hero.title}</h1>
          <p>{landingContent.hero.body}</p>
          <div className="single-actions">
            <a href="#product" className="single-button primary">{landingContent.hero.primary}<ArrowRight size={16} /></a>
            <a href="#docs" className="single-button secondary"><Terminal size={16} />{landingContent.hero.secondary}</a>
          </div>
        </div>
        <aside className="forge-console" aria-label="Live product console">
          <div className="console-top"><span /> <span /> <span /><strong>deployment: active</strong></div>
          <div className="console-lines">
            {landingContent.terminal.map((line) => <code key={line}>{line}</code>)}
          </div>
        </aside>
      </section>

      <section className="signal-rail" aria-label="Product signals">
        {landingContent.domainTerms.slice(0, 6).map((term) => (
          <span key={term}><CheckCircle2 size={16} />{term}</span>
        ))}
      </section>

      {landingContent.sections.map((section, index) => (
        <section className="landing-band" id={section.id} key={section.id}>
          <div>
            <p className="single-eyebrow">{section.label}</p>
            <h2>{section.title}</h2>
          </div>
          <p>{section.body}</p>
          <Copy className="band-icon" aria-hidden="true" />
          <span className="band-index">{String(index + 1).padStart(2, '0')}</span>
        </section>
      ))}

      <section className="pricing-grid" id="pricing" aria-label="Pricing">
        {landingContent.pricing.map((tier) => (
          <article key={tier.name} className="price-card">
            <h2>{tier.name}</h2>
            <strong>{tier.price}</strong>
            <ul>{tier.items.map((item) => <li key={item}>{item}</li>)}</ul>
            <a href="#docs">Choose path</a>
          </article>
        ))}
      </section>
    </main>
  );
}
"""


def _single_landing_content_test() -> str:
    return """import { describe, expect, it } from 'vitest';
import { landingContent } from '@/lib/landingContent';

describe('landingContent', () => {
  it('uses anchor navigation for a single landing page', () => {
    expect(landingContent.nav.every((item) => item.href.startsWith('#'))).toBe(true);
  });
});
"""


def _single_landing_css() -> str:
    return """

/* Friday single-landing mode: no dashboard/login scaffold. */
.single-landing { min-height: 100vh; background: #080909; color: #f7f3ea; }
.single-nav { position: sticky; top: 0; z-index: 20; min-height: 70px; display: flex; align-items: center; gap: 22px; padding: 0 clamp(18px, 5vw, 64px); border-bottom: 1px solid #252525; background: rgba(8, 9, 9, .92); backdrop-filter: blur(12px); }
.single-brand { font-weight: 900; font-size: 1.1rem; }
.single-nav nav { margin-left: auto; display: flex; flex-wrap: wrap; gap: 18px; color: #c8b8a4; font-size: .92rem; }
.single-nav-cta, .single-button { min-height: 42px; display: inline-flex; align-items: center; gap: 8px; border: 1px solid #333; padding: 0 16px; font-weight: 850; }
.single-nav-cta, .single-button.primary { background: #ff8a00; color: #090909; border-color: #ff8a00; }
.single-button.secondary { color: #f7f3ea; background: #111; }
.single-hero { min-height: calc(100vh - 70px); display: grid; grid-template-columns: minmax(0, 1fr) minmax(340px, 0.9fr); align-items: center; gap: clamp(28px, 5vw, 74px); padding: clamp(42px, 7vw, 96px) clamp(18px, 5vw, 64px); }
.single-copy h1 { max-width: 850px; font-size: clamp(2.25rem, 5vw, 4.75rem); line-height: 1.03; overflow-wrap: anywhere; letter-spacing: 0; }
.single-copy p { max-width: 720px; color: #d7c8b5; font-size: clamp(1rem, 1.8vw, 1.24rem); line-height: 1.75; }
.single-eyebrow { color: #ffb56b; font-size: .78rem; font-weight: 900; letter-spacing: .16em; text-transform: uppercase; }
.single-actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 30px; }
.forge-console { border: 1px solid #363636; background: linear-gradient(145deg, #101010, #0d1416); box-shadow: 0 30px 80px rgba(0,0,0,.45); }
.console-top { min-height: 54px; display: flex; align-items: center; gap: 9px; border-bottom: 1px solid #292929; padding: 0 18px; }
.console-top span { width: 10px; height: 10px; border-radius: 99px; background: #ff8a00; }
.console-top strong { margin-left: auto; color: #38d7ff; font-family: ui-monospace, monospace; font-size: .78rem; letter-spacing: .08em; text-transform: uppercase; }
.console-lines { display: grid; gap: 14px; padding: 24px; }
.console-lines code { display: block; border: 1px solid #252525; background: #090909; padding: 16px; color: #f7f3ea; font-family: ui-monospace, monospace; }
.signal-rail { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); border-block: 1px solid #252525; }
.signal-rail span { min-height: 76px; display: flex; align-items: center; justify-content: center; gap: 8px; border-right: 1px solid #252525; color: #ffcf91; text-transform: capitalize; }
.landing-band { position: relative; display: grid; grid-template-columns: minmax(0, .85fr) minmax(0, 1.15fr); gap: 34px; padding: clamp(42px, 7vw, 92px) clamp(18px, 5vw, 64px); border-bottom: 1px solid #252525; overflow: hidden; }
.landing-band h2 { font-size: clamp(2rem, 4.6vw, 4.8rem); line-height: 1; }
.landing-band p { color: #d7c8b5; font-size: clamp(1rem, 1.6vw, 1.2rem); line-height: 1.75; }
.band-icon { position: absolute; right: 8%; bottom: 18%; color: rgba(255,138,0,.18); width: 100px; height: 100px; }
.band-index { position: absolute; right: 5vw; top: 24px; color: rgba(255,255,255,.2); font-size: 3rem; font-weight: 900; }
.pricing-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; padding: clamp(42px, 7vw, 92px) clamp(18px, 5vw, 64px); }
.price-card { border: 1px solid #2d2d2d; background: #111; padding: 28px; }
.price-card strong { display: block; margin: 18px 0; font-size: 2.4rem; }
.price-card ul { display: grid; gap: 12px; margin: 0 0 28px; padding-left: 20px; color: #d7c8b5; }
.price-card a { display: inline-flex; min-height: 42px; align-items: center; border: 1px solid #383838; padding: 0 16px; font-weight: 850; }
@media (max-width: 900px) {
  .single-nav { align-items: flex-start; flex-direction: column; padding-top: 16px; padding-bottom: 16px; }
  .single-nav nav { margin-left: 0; }
  .single-hero, .landing-band, .pricing-grid, .signal-rail { grid-template-columns: 1fr; }
}
"""


def _as_marketing_website_files(files: dict[str, str], name: str, request: str) -> dict[str, str]:
    blocked_prefixes = (
        "src/app/(auth)/",
        "src/app/(dashboard)/",
        "src/app/privacy/",
        "src/app/terms/",
        "src/components/Auth/",
        "src/components/layout/",
        "src/components/Shared/",
        "src/components/Workspace/",
        "src/hooks/useAccessToken.ts",
        "src/hooks/useBriefDraft.ts",
        "src/lib/authTokens.ts",
        "src/services/api.ts",
        "src/services/BriefService.ts",
        "src/services/__tests__/",
        "src/store/",
        "src/lib/productPlan.ts",
        "src/app/api/brief/",
    )
    next_files = {
        path: content
        for path, content in files.items()
        if not any(path.startswith(prefix) for prefix in blocked_prefixes)
    }
    next_files.update(
        {
            "src/app/layout.tsx": f"import './globals.css';\n\nexport const metadata = {{ title: {_json_value(name)}, description: 'Four-page business website generated by Friday' }};\n\nexport default function RootLayout({{ children }}: {{ children: React.ReactNode }}) {{\n  return <html lang=\"en\"><body>{{children}}</body></html>;\n}}\n",
            "src/app/page.tsx": "import { HomePage } from '@/components/Landing/HomePage';\n\nexport default function Home() {\n  return <HomePage />;\n}\n",
            "src/app/about/page.tsx": "import { AboutPage } from '@/components/Marketing/AboutPage';\n\nexport default function Page() {\n  return <AboutPage />;\n}\n",
            "src/app/services/page.tsx": "import { ServicesPage } from '@/components/Marketing/ServicesPage';\n\nexport default function Page() {\n  return <ServicesPage />;\n}\n",
            "src/app/contact/page.tsx": "import { ContactPage } from '@/components/Marketing/ContactPage';\n\nexport default function Page() {\n  return <ContactPage />;\n}\n",
            "src/components/Landing/HomePage.tsx": _marketing_home_page(),
            "src/components/Marketing/AboutPage.tsx": _marketing_about_page(),
            "src/components/Marketing/ServicesPage.tsx": _marketing_services_page(),
            "src/components/Marketing/ContactPage.tsx": _marketing_contact_page(),
            "src/components/Marketing/SiteShell.tsx": _marketing_site_shell(),
            "src/components/Marketing/SiteHeader.tsx": _marketing_site_header(name),
            "src/components/Marketing/SiteFooter.tsx": _marketing_site_footer(name),
            "src/components/Marketing/SectionHeader.tsx": _marketing_section_header(),
            "src/components/Marketing/__tests__/siteContent.test.ts": _marketing_site_content_test(),
            "src/lib/siteContent.ts": _marketing_site_content(name, request),
            "FRONTEND_STRUCTURE.md": _marketing_frontend_structure(),
            "README.md": _product_readme(name, request, "Next.js four-page website", "npm install\nnpm run dev"),
        }
    )
    return next_files


def _with_web_route_contract_files(files: dict[str, str], name: str, request: str) -> dict[str, str]:
    routes = web_project_contract.expected_routes(request, stack={"stack": "nextjs"})
    if len(routes) <= 1:
        return files
    contract = web_project_contract.build_contract(request, name, stack={"stack": "nextjs"})
    blocked_prefixes = (
        "src/app/(auth)/",
        "src/app/(dashboard)/",
        "src/app/privacy/",
        "src/app/terms/",
        "src/components/Auth/",
        "src/components/Shared/",
        "src/components/Workspace/",
        "src/components/layout/",
        "src/app/api/brief/",
    )
    next_files = {
        path: content
        for path, content in files.items()
        if not any(path.startswith(prefix) for prefix in blocked_prefixes)
    }
    next_files.update(
        {
            "src/lib/webProjectContract.ts": web_project_contract.contract_ts(contract),
            "src/components/WebContract/ContractShell.tsx": _contract_shell_component(),
            "src/components/WebContract/WebContractPage.tsx": _contract_page_component(),
            "src/components/WebContract/DashboardPreviewPage.tsx": _contract_dashboard_component(),
            "src/components/WebContract/__tests__/webProjectContract.test.ts": _contract_test(),
            "src/components/Landing/HomePage.tsx": "import { WebContractPage } from '@/components/WebContract/WebContractPage';\n\nexport function HomePage() {\n  return <WebContractPage pageId=\"home\" />;\n}\n",
            "src/app/page.tsx": "import { HomePage } from '@/components/Landing/HomePage';\n\nexport default function Home() {\n  return <HomePage />;\n}\n",
            "FRONTEND_STRUCTURE.md": _next_frontend_structure()
            + "\n## Web Route Contract\n\n- `src/lib/webProjectContract.ts` stores requested pages, nav, dashboard preview content, domain terms, and acceptance criteria.\n- `src/components/WebContract` renders contract pages from data instead of scattering page copy through route files.\n- Requested pages/routes must exist before product gates can pass.\n",
        }
    )
    for route in routes:
        route_id = route["id"]
        if route_id == "home":
            continue
        relative = f"src/app/{route['route'].strip('/')}/page.tsx"
        if route_id == "dashboard-preview":
            next_files[relative] = "import { DashboardPreviewPage } from '@/components/WebContract/DashboardPreviewPage';\n\nexport default function Page() {\n  return <DashboardPreviewPage />;\n}\n"
        else:
            next_files[relative] = f"import {{ WebContractPage }} from '@/components/WebContract/WebContractPage';\n\nexport default function Page() {{\n  return <WebContractPage pageId={_json_value(route_id)} />;\n}}\n"
    next_files["src/app/globals.css"] = next_files.get("src/app/globals.css", "") + _web_contract_css()
    return next_files


def _contract_shell_component() -> str:
    return """import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { webProject } from '@/lib/webProjectContract';

type ContractNavItem = { id: string; label: string; route: string };

export function ContractShell({ children }: { children: React.ReactNode }) {
  const nav = webProject.nav as readonly ContractNavItem[];
  const contactRoute = nav.find((item) => item.id === 'contact')?.route;
  const ctaRoute = contactRoute ?? nav[1]?.route ?? '/';
  const ctaLabel = contactRoute ? 'Book demo' : 'Open workflow';
  return (
    <div className={`contract-site contract-site-${webProject.archetype}`}>
      <header className="contract-nav">
        <Link href="/" className="contract-brand">{webProject.product_name}</Link>
        <nav aria-label="Primary navigation">
          {nav.map((item) => (
            <Link key={item.id} href={item.route}>{item.label}</Link>
          ))}
        </nav>
        <Link href={ctaRoute} className="contract-nav-cta">
          {ctaLabel} <ArrowRight size={15} aria-hidden="true" />
        </Link>
      </header>
      {children}
      <footer className="contract-footer">
        <strong>{webProject.product_name}</strong>
        <span>{webProject.tone}</span>
      </footer>
    </div>
  );
}
"""


def _contract_page_component() -> str:
    return """import Link from 'next/link';
import { ArrowRight, CheckCircle2, ClipboardList, FileCheck2, MapPinned } from 'lucide-react';
import { ContractShell } from '@/components/WebContract/ContractShell';
import { webProject } from '@/lib/webProjectContract';

type ContractNavItem = { id: string; label: string; route: string };

export function WebContractPage({ pageId }: { pageId: string }) {
  const page = webProject.pages.find((item) => item.id === pageId) ?? webProject.pages[0];
  const dashboard = webProject.dashboard_preview;
  const nav = webProject.nav as readonly ContractNavItem[];
  const currentPageId = String(page.id);
  const showDashboardAction = Boolean(dashboard && 'route' in dashboard);
  const navIndex = Math.max(0, nav.findIndex((item) => item.id === currentPageId));
  const nextRoute = nav[(navIndex + 1) % nav.length]?.route ?? '/';
  const previousRoute = nav[Math.max(0, navIndex - 1)]?.route ?? '/';
  const pricingRoute = nav.find((item) => item.id === 'pricing')?.route;
  const productRoute = nav.find((item) => item.id === 'product')?.route;
  const primaryHref = showDashboardAction ? '/dashboard-preview' : nextRoute;
  const secondaryHref = currentPageId === 'pricing' ? (productRoute ?? previousRoute) : (pricingRoute ?? previousRoute);
  return (
    <ContractShell>
      <section className="contract-hero">
        <div className="contract-hero-grid" aria-hidden="true">
          {webProject.domain_terms.slice(0, 6).map((term, index) => (
            <span key={term} style={{ '--i': index } as React.CSSProperties}>{term}</span>
          ))}
        </div>
        <div className="contract-hero-copy">
          <p className="contract-eyebrow">{webProject.archetype.replace(/_/g, ' ')}</p>
          <h1>{page.title}</h1>
          <p>{page.summary}</p>
          <div className="contract-actions">
            <Link href={primaryHref} className="contract-button primary">
              {page.primary_action} <ArrowRight size={16} aria-hidden="true" />
            </Link>
            <Link href={secondaryHref} className="contract-button secondary">
              {page.secondary_action}
            </Link>
          </div>
        </div>
      </section>

      <section className="contract-proof-strip" aria-label="Contract proof">
        {webProject.acceptance.slice(0, 4).map((item) => (
          <div key={item}><CheckCircle2 size={18} aria-hidden="true" />{item}</div>
        ))}
      </section>

      <section className="contract-section-grid">
        {page.sections.map((section, index) => {
          const Icon = [ClipboardList, MapPinned, FileCheck2][index % 3];
          return (
            <article key={section.title} className="contract-panel">
              <Icon size={22} aria-hidden="true" />
              <h2>{section.title}</h2>
              <p>{section.body}</p>
            </article>
          );
        })}
      </section>

      {currentPageId === 'contact' ? <ContactCapture /> : null}
    </ContractShell>
  );
}

function ContactCapture() {
  return (
    <section className="contract-contact" aria-label="Demo request">
      <div>
        <p className="contract-eyebrow">pilot intake</p>
        <h2>Turn the first call into a scoped pilot.</h2>
        <p>Friday should collect the workflow pressure, systems involved, approval needs, and proof required before anyone claims launch readiness.</p>
      </div>
      <form>
        <label>Team name<input name="team" /></label>
        <label>Workflows to fix<textarea name="workflows" /></label>
        <button type="button">Save demo request</button>
      </form>
    </section>
  );
}
"""


def _contract_dashboard_component() -> str:
    return """import { AlertTriangle, CalendarDays, CheckCircle2, UsersRound } from 'lucide-react';
import { ContractShell } from '@/components/WebContract/ContractShell';
import { webProject } from '@/lib/webProjectContract';

type DashboardMetric = { label: string; value: string; tone: string };
type DashboardQueueItem = { title: string; owner: string; status: string };
type DashboardPreview = {
  title?: string;
  summary?: string;
  metrics?: DashboardMetric[];
  queue?: DashboardQueueItem[];
};

export function DashboardPreviewPage() {
  const dashboard = webProject.dashboard_preview as DashboardPreview;
  const metrics = Array.isArray(dashboard.metrics) ? dashboard.metrics : [];
  const queue = Array.isArray(dashboard.queue) ? dashboard.queue : [];
  return (
    <ContractShell>
      <main className="contract-dashboard">
        <section className="contract-dashboard-head">
          <p className="contract-eyebrow">operations dashboard preview</p>
          <h1>{dashboard.title ?? `${webProject.product_name} dashboard`}</h1>
          <p>{dashboard.summary ?? webProject.request_summary}</p>
        </section>
        <section className="contract-metrics" aria-label="Operational metrics">
          {metrics.map((metric) => (
            <article key={metric.label} className={`contract-metric ${metric.tone}`}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </article>
          ))}
        </section>
        <section className="contract-dashboard-grid">
          <article className="contract-board">
            <div className="contract-board-title"><AlertTriangle size={20} />Urgent queue</div>
            {queue.map((item) => (
              <div key={item.title} className="contract-queue-row">
                <strong>{item.title}</strong>
                <span>{item.owner}</span>
                <em>{item.status}</em>
              </div>
            ))}
          </article>
          <article className="contract-board">
            <div className="contract-board-title"><CalendarDays size={20} />Schedule load</div>
            <div className="contract-calendar">
              {['Mon', 'Tue', 'Wed', 'Thu', 'Fri'].map((day, index) => (
                <span key={day} style={{ '--load': `${50 + index * 9}%` } as React.CSSProperties}>{day}</span>
              ))}
            </div>
          </article>
          <article className="contract-board">
            <div className="contract-board-title"><UsersRound size={20} />Reviewer workload</div>
            {webProject.domain_terms.slice(0, 4).map((term) => (
              <div key={term} className="contract-workload"><span>{term}</span><CheckCircle2 size={16} /></div>
            ))}
          </article>
        </section>
      </main>
    </ContractShell>
  );
}
"""


def _contract_test() -> str:
    return """import { describe, expect, it } from 'vitest';
import { webProject } from '@/lib/webProjectContract';

describe('web project contract', () => {
  it('keeps requested routes explicit', () => {
    expect(webProject.routes.length).toBeGreaterThan(1);
    expect(webProject.routes[0].route).toBe('/');
  });

  it('keeps product-domain terms available for gates', () => {
    expect(webProject.domain_terms.length).toBeGreaterThan(2);
  });
});
"""


def _web_contract_css() -> str:
    return """

/* Friday web-route contract layer: product pages come from a request contract, not the starter scaffold. */
.contract-site { min-height: 100vh; background: #f4f1e8; color: #151713; }
.contract-nav { position: sticky; top: 0; z-index: 20; min-height: 72px; display: flex; align-items: center; gap: 22px; padding: 0 clamp(18px, 5vw, 72px); border-bottom: 1px solid #d8d1c4; background: rgba(244, 241, 232, .94); backdrop-filter: blur(12px); }
.contract-brand { font-weight: 900; font-size: 1.05rem; }
.contract-nav nav { margin-left: auto; display: flex; flex-wrap: wrap; align-items: center; gap: 18px; color: #465047; font-size: .94rem; }
.contract-nav-cta, .contract-button { min-height: 42px; display: inline-flex; align-items: center; justify-content: center; gap: 8px; border-radius: 8px; padding: 0 16px; font-weight: 800; }
.contract-nav-cta, .contract-button.primary { background: #134e45; color: #fff; }
.contract-button.secondary { border: 1px solid #b8afa1; color: #151713; background: rgba(255,255,255,.55); }
.contract-hero { position: relative; min-height: min(640px, calc(100vh - 72px)); display: grid; align-items: end; overflow: hidden; padding: clamp(36px, 5vw, 72px) clamp(18px, 5vw, 72px); border-bottom: 1px solid #d8d1c4; }
.contract-hero::before { content: ""; position: absolute; inset: 0; background: radial-gradient(circle at 18% 20%, rgba(49, 107, 91, .22), transparent 32%), linear-gradient(135deg, rgba(255,255,255,.55), rgba(206, 219, 205, .55)); }
.contract-hero-grid { position: absolute; inset: 9% 4% auto auto; width: min(640px, 50vw); min-height: 420px; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; opacity: .9; transform: rotate(-2deg); }
.contract-hero-grid span { min-height: 82px; display: flex; align-items: end; border: 1px solid rgba(19, 78, 69, .24); background: rgba(255,255,255,.58); padding: 14px; color: #134e45; font-weight: 850; text-transform: capitalize; box-shadow: 0 18px 50px rgba(30, 41, 31, .08); }
.contract-hero-copy { position: relative; max-width: 860px; }
.contract-eyebrow { margin-bottom: 14px; color: #8a3d2d; font-size: .78rem; font-weight: 900; letter-spacing: .14em; text-transform: uppercase; }
.contract-hero h1, .contract-dashboard h1 { max-width: 900px; font-size: clamp(2.1rem, 4.8vw, 4.5rem); line-height: 1.04; letter-spacing: 0; overflow-wrap: anywhere; }
.contract-hero p, .contract-dashboard-head p, .contract-contact p { max-width: 760px; color: #4d554d; font-size: clamp(1.02rem, 2vw, 1.35rem); line-height: 1.7; }
.contract-actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 28px; }
.contract-proof-strip { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1px; background: #d8d1c4; border-bottom: 1px solid #d8d1c4; }
.contract-proof-strip div { min-height: 88px; display: flex; align-items: center; gap: 10px; background: #e6eee3; padding: 18px; color: #134e45; font-weight: 750; }
.contract-section-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; padding: clamp(32px, 5vw, 72px); }
.contract-panel, .contract-board, .contract-contact { border: 1px solid #d8d1c4; background: rgba(255,255,255,.78); border-radius: 8px; padding: 24px; box-shadow: 0 18px 40px rgba(30, 41, 31, .06); }
.contract-panel h2, .contract-contact h2 { font-size: clamp(1.28rem, 2vw, 1.85rem); }
.contract-panel p { color: #4d554d; line-height: 1.7; }
.contract-contact { margin: 0 clamp(18px, 5vw, 72px) clamp(40px, 6vw, 80px); display: grid; grid-template-columns: .8fr 1.2fr; gap: 24px; }
.contract-contact form, .contract-contact label { display: grid; gap: 10px; }
.contract-contact input, .contract-contact textarea { width: 100%; min-height: 44px; border: 1px solid #b8afa1; border-radius: 8px; background: #fff; padding: 10px 12px; color: #151713; }
.contract-contact textarea { min-height: 118px; }
.contract-contact button { min-height: 44px; border: 0; border-radius: 8px; background: #134e45; color: #fff; font-weight: 850; }
.contract-dashboard { padding: clamp(32px, 5vw, 72px); }
.contract-dashboard-head { margin-bottom: 26px; }
.contract-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }
.contract-metric { min-height: 118px; display: grid; align-content: space-between; border: 1px solid #d8d1c4; border-radius: 8px; background: #fff; padding: 18px; }
.contract-metric span { color: #4d554d; text-transform: capitalize; }
.contract-metric strong { font-size: 2.2rem; }
.contract-metric.urgent strong { color: #9d2f22; }
.contract-metric.warning strong { color: #9b5d00; }
.contract-metric.good strong { color: #12694f; }
.contract-dashboard-grid { display: grid; grid-template-columns: 1.2fr .8fr .8fr; gap: 18px; }
.contract-board-title { display: flex; align-items: center; gap: 10px; margin-bottom: 18px; font-weight: 900; }
.contract-queue-row, .contract-workload { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 12px; border-top: 1px solid #ebe4d8; padding: 13px 0; }
.contract-queue-row span, .contract-queue-row em { color: #4d554d; }
.contract-calendar { display: grid; gap: 12px; }
.contract-calendar span { --load: 60%; min-height: 40px; display: flex; align-items: center; justify-content: space-between; border-radius: 8px; background: linear-gradient(90deg, #134e45 var(--load), #e5ded2 var(--load)); color: #fff; padding: 0 12px; font-weight: 800; }
.contract-footer { min-height: 96px; display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 0 clamp(18px, 5vw, 72px); background: #151713; color: #fff; }
.contract-footer span { color: #cbd5c6; }

@media (max-width: 920px) {
  .contract-nav { align-items: flex-start; flex-direction: column; padding-top: 16px; padding-bottom: 16px; }
  .contract-nav nav { margin-left: 0; }
  .contract-hero { min-height: auto; }
  .contract-hero-grid { position: relative; inset: auto; width: 100%; min-height: 0; grid-template-columns: 1fr; margin-bottom: 24px; transform: none; }
  .contract-hero-copy { order: -1; }
  .contract-proof-strip, .contract-section-grid, .contract-metrics, .contract-dashboard-grid, .contract-contact { grid-template-columns: 1fr; }
  .contract-contact { margin-inline: 18px; }
  .contract-footer { align-items: flex-start; flex-direction: column; padding-top: 24px; padding-bottom: 24px; }
}
"""


def _marketing_site_content(name: str, request: str) -> str:
    strategy = content_strategy.website_content(name, request)
    return f"export const siteContent = {json.dumps(strategy, ensure_ascii=True, indent=2)} as const;\n"


def _marketing_site_shell() -> str:
    return """import { SiteFooter } from '@/components/Marketing/SiteFooter';
import { SiteHeader } from '@/components/Marketing/SiteHeader';

export function SiteShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[#f7f5ef] text-[#151713]">
      <SiteHeader />
      <main>{children}</main>
      <SiteFooter />
    </div>
  );
}
"""


def _marketing_site_header(name: str) -> str:
    return f"""import Link from 'next/link';
import {{ ArrowRight }} from 'lucide-react';
import {{ siteContent }} from '@/lib/siteContent';

export function SiteHeader() {{
  return (
    <header className="border-b border-[#d9d4c8] bg-[#f7f5ef]/95">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <Link href="/" className="text-base font-semibold tracking-normal text-[#151713]">
          {{siteContent.brand}}
        </Link>
        <nav className="hidden items-center gap-6 text-sm text-[#4d5148] md:flex" aria-label="Primary navigation">
          {{siteContent.nav.map((item) => (
            <Link key={{item.href}} href={{item.href}} className="transition hover:text-[#151713]">
              {{item.label}}
            </Link>
          ))}}
        </nav>
        <Link href="/contact" className="inline-flex min-h-10 items-center gap-2 rounded-md bg-[#1f4f46] px-4 text-sm font-semibold text-white">
          Contact <ArrowRight className="size-4" aria-hidden="true" />
        </Link>
      </div>
    </header>
  );
}}
"""


def _marketing_site_footer(name: str) -> str:
    return f"""import Link from 'next/link';
import {{ siteContent }} from '@/lib/siteContent';

export function SiteFooter() {{
  return (
    <footer className="border-t border-[#d9d4c8] bg-[#151713] text-white">
      <div className="mx-auto grid max-w-6xl gap-8 px-6 py-10 md:grid-cols-[1.2fr_0.8fr]">
        <div>
          <p className="text-base font-semibold">{{siteContent.brand}}</p>
          <p className="mt-3 max-w-xl text-sm leading-6 text-[#d7dfd5]">
            A focused website structure for credibility, services, and qualified inbound conversations.
          </p>
        </div>
        <nav className="grid gap-2 text-sm" aria-label="Footer navigation">
          {{siteContent.nav.map((item) => (
            <Link key={{item.href}} href={{item.href}} className="text-[#d7dfd5] hover:text-white">
              {{item.label}}
            </Link>
          ))}}
        </nav>
      </div>
    </footer>
  );
}}
"""


def _marketing_section_header() -> str:
    return """export function SectionHeader({ eyebrow, title, body }: { eyebrow: string; title: string; body: string }) {
  return (
    <div className="max-w-3xl">
      <p className="text-sm font-semibold uppercase tracking-[0.14em] text-[#9a3d2f]">{eyebrow}</p>
      <h1 className="mt-3 text-4xl font-semibold tracking-normal text-[#151713] md:text-5xl">{title}</h1>
      <p className="mt-4 text-lg leading-8 text-[#555a51]">{body}</p>
    </div>
  );
}
"""


def _marketing_home_page() -> str:
    return """import Link from 'next/link';
import { ArrowRight, CheckCircle2 } from 'lucide-react';
import { SiteShell } from '@/components/Marketing/SiteShell';
import { siteContent } from '@/lib/siteContent';

export function HomePage() {
  return (
    <SiteShell>
      <section className="mx-auto grid max-w-6xl gap-12 px-6 py-16 lg:grid-cols-[1.1fr_0.9fr] lg:py-20">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.14em] text-[#9a3d2f]">{siteContent.hero.eyebrow}</p>
          <h1 className="mt-4 text-5xl font-semibold tracking-normal text-[#151713] md:text-6xl">{siteContent.hero.title}</h1>
          <p className="mt-6 max-w-2xl text-xl leading-9 text-[#555a51]">{siteContent.hero.summary}</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/contact" className="inline-flex min-h-11 items-center gap-2 rounded-md bg-[#1f4f46] px-5 text-sm font-semibold text-white">
              {siteContent.hero.primaryAction} <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
            <Link href="/services" className="inline-flex min-h-11 items-center rounded-md border border-[#b7b0a4] px-5 text-sm font-semibold text-[#151713]">
              {siteContent.hero.secondaryAction}
            </Link>
          </div>
        </div>
        <aside className="border border-[#d0c8ba] bg-white p-6 shadow-sm" aria-label="Website proof points">
          <p className="text-sm font-semibold text-[#1f4f46]">What visitors can understand quickly</p>
          <div className="mt-6 grid gap-4">
            {siteContent.proof.map((item) => (
              <div key={item.label} className="flex items-start justify-between gap-4 border-b border-[#ece7dd] pb-4 last:border-b-0 last:pb-0">
                <span className="text-sm text-[#555a51]">{item.label}</span>
                <strong className="text-xl text-[#151713]">{item.value}</strong>
              </div>
            ))}
          </div>
        </aside>
      </section>
      <section className="border-y border-[#d9d4c8] bg-[#e8f0e7]">
        <div className="mx-auto grid max-w-6xl gap-4 px-6 py-10 md:grid-cols-3">
          {siteContent.about.principles.map((item) => (
            <div key={item} className="flex items-center gap-3 text-sm font-semibold text-[#1f4f46]">
              <CheckCircle2 className="size-5" aria-hidden="true" />
              {item}
            </div>
          ))}
        </div>
      </section>
    </SiteShell>
  );
}
"""


def _marketing_about_page() -> str:
    return """import { SectionHeader } from '@/components/Marketing/SectionHeader';
import { SiteShell } from '@/components/Marketing/SiteShell';
import { siteContent } from '@/lib/siteContent';

export function AboutPage() {
  return (
    <SiteShell>
      <section className="mx-auto max-w-6xl px-6 py-16">
        <SectionHeader eyebrow="About" title={siteContent.about.title} body={siteContent.about.body} />
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {siteContent.about.principles.map((principle) => (
            <div key={principle} className="border border-[#d9d4c8] bg-white p-5">
              <p className="text-base font-semibold text-[#151713]">{principle}</p>
              <p className="mt-3 text-sm leading-6 text-[#555a51]">Every page supports this principle with specific copy and a clear next step.</p>
            </div>
          ))}
        </div>
      </section>
    </SiteShell>
  );
}
"""


def _marketing_services_page() -> str:
    return """import { SectionHeader } from '@/components/Marketing/SectionHeader';
import { SiteShell } from '@/components/Marketing/SiteShell';
import { siteContent } from '@/lib/siteContent';

export function ServicesPage() {
  return (
    <SiteShell>
      <section className="mx-auto max-w-6xl px-6 py-16">
        <SectionHeader eyebrow="Services" title="Services are explained before anyone has to ask" body="Each service area describes the practical outcome, not a vague capability list." />
        <div className="mt-10 grid gap-5 md:grid-cols-3">
          {siteContent.services.map((service) => (
            <article key={service.title} className="border border-[#d9d4c8] bg-white p-6">
              <h2 className="text-xl font-semibold text-[#151713]">{service.title}</h2>
              <p className="mt-4 text-sm leading-7 text-[#555a51]">{service.detail}</p>
            </article>
          ))}
        </div>
      </section>
    </SiteShell>
  );
}
"""


def _marketing_contact_page() -> str:
    return """import { Mail } from 'lucide-react';
import { SectionHeader } from '@/components/Marketing/SectionHeader';
import { SiteShell } from '@/components/Marketing/SiteShell';
import { siteContent } from '@/lib/siteContent';

export function ContactPage() {
  return (
    <SiteShell>
      <section className="mx-auto grid max-w-6xl gap-10 px-6 py-16 lg:grid-cols-[0.9fr_1.1fr]">
        <SectionHeader eyebrow="Contact" title={siteContent.contact.title} body={siteContent.contact.detail} />
        <form className="grid gap-4 border border-[#d9d4c8] bg-white p-6" aria-label="Project inquiry form">
          <label className="grid gap-2 text-sm font-semibold text-[#151713]">
            Name
            <input className="min-h-11 rounded-md border border-[#b7b0a4] px-3 font-normal" name="name" />
          </label>
          <label className="grid gap-2 text-sm font-semibold text-[#151713]">
            Email
            <input className="min-h-11 rounded-md border border-[#b7b0a4] px-3 font-normal" name="email" type="email" />
          </label>
          <label className="grid gap-2 text-sm font-semibold text-[#151713]">
            What do you need help with?
            <textarea className="min-h-32 rounded-md border border-[#b7b0a4] p-3 font-normal" name="message" />
          </label>
          <button className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md bg-[#1f4f46] px-5 text-sm font-semibold text-white" type="button">
            <Mail className="size-4" aria-hidden="true" />
            Draft inquiry
          </button>
        </form>
      </section>
    </SiteShell>
  );
}
"""


def _marketing_site_content_test() -> str:
    return """import { describe, expect, it } from 'vitest';
import { siteContent } from '@/lib/siteContent';

describe('siteContent', () => {
  it('defines exactly four primary website pages', () => {
    expect(siteContent.nav.map((item) => item.href)).toEqual(['/', '/about', '/services', '/contact']);
  });
});
"""


def _marketing_frontend_structure() -> str:
    return """# Frontend Structure

- `src/app` contains thin route files for the four public pages plus policy and health routes.
- `src/components/Marketing` contains page sections, shell, header, footer, and reusable website components.
- `src/components/ui` keeps reusable primitives available without turning the website into a dashboard app.
- `src/lib/siteContent.ts` owns website copy and navigation so visible text is not scattered through route files.
- `src/test` and component tests verify the four-page contract.
"""


def _production_workflow(stack_id: str) -> str:
    commands = {
        "nextjs": ["npm install", "npm run typecheck", "npm test", "npm run build", "npm audit --audit-level=moderate"],
        "node_fastify": ["npm install", "npm test", "npm audit --audit-level=moderate"],
        "python_fastapi": ["python -m pip install -e .[dev]", "python -m pytest -q"],
        "go_api": ["go test ./...", "go vet ./..."],
        "rust_axum": ["cargo test", "cargo clippy -- -D warnings"],
        "flutter": ["flutter pub get", "flutter test", "flutter analyze"],
    }.get(stack_id, ["echo Add production checks"])
    return "\n".join(
        [
            "name: Friday Production Readiness",
            "on:",
            "  pull_request:",
            "  push:",
            "    branches: [main]",
            "jobs:",
            "  verify:",
            "    runs-on: ubuntu-latest",
            "    steps:",
            "      - uses: actions/checkout@v4",
            "      - name: Run readiness gates",
            "        run: |",
            *[f"          {command}" for command in commands],
            "",
        ]
    )


def _flutter_files(name: str, request: str) -> dict[str, str]:
    package = _slug(name).replace("-", "_")
    return {
        "pubspec.yaml": f"name: {package}\ndescription: AI-assisted mobile workflow app generated by Friday.\npublish_to: 'none'\nversion: 0.1.0+1\nenvironment:\n  sdk: '>=3.4.0 <4.0.0'\ndependencies:\n  flutter:\n    sdk: flutter\n  cupertino_icons: ^1.0.8\ndev_dependencies:\n  flutter_test:\n    sdk: flutter\n  flutter_lints: ^4.0.0\nflutter:\n  uses-material-design: true\n",
        "lib/main.dart": _flutter_main(name, request),
        "lib/home_screen.dart": _flutter_home_screen(name, request),
        "lib/workflow_store.dart": _flutter_workflow_store(),
        "test/widget_test.dart": "import 'package:flutter_test/flutter_test.dart';\nimport 'package:flutter/material.dart';\nimport 'package:" + package + "/main.dart';\n\nvoid main() {\n  testWidgets('renders product name', (tester) async {\n    await tester.pumpWidget(const FridayApp());\n    expect(find.byType(MaterialApp), findsOneWidget);\n  });\n}\n",
        "README.md": _product_readme(name, request, "Flutter mobile app", "flutter pub get\nflutter run"),
        ".gitignore": ".dart_tool\nbuild\n.flutter-plugins\n.flutter-plugins-dependencies\n.packages\npubspec.lock\n.env\n",
    }


def _fastify_files(name: str, request: str) -> dict[str, str]:
    slug = _slug(name)
    return {
        "package.json": _json(
            {
                "name": slug,
                "private": True,
                "version": "0.1.0",
                "type": "module",
                "scripts": {"dev": "node --watch src/server.js", "start": "node src/server.js", "test": "node --test"},
                "dependencies": {"@fastify/cors": "11.1.0", "fastify": "5.8.5"},
                "devDependencies": {},
            }
        ),
        "src/app.js": _fastify_app(name, request),
        "src/server.js": _fastify_server(name, request),
        "src/routes/brief.js": _fastify_brief_route(name, request),
        "src/routes/workItems.js": _fastify_work_items_route(),
        "src/services/briefService.js": _fastify_brief_service(name, request),
        "src/storage/memoryStore.js": _fastify_memory_store(),
        "src/validation/workItem.js": _fastify_work_item_validation(),
        "test/health.test.js": "import test from 'node:test';\nimport assert from 'node:assert/strict';\nimport { buildApp } from '../src/app.js';\n\ntest('health endpoint responds', async () => {\n  const app = buildApp();\n  const response = await app.inject({ method: 'GET', url: '/health' });\n  assert.equal(response.statusCode, 200);\n  assert.equal(response.json().status, 'ok');\n});\n",
        ".env.example": "PORT=3000\n",
        "README.md": _product_readme(name, request, "Node.js Fastify backend", "npm install\nnpm run dev"),
        ".gitignore": "node_modules\n.env\n.DS_Store\ncoverage\n",
    }


def _fastapi_files(name: str, request: str) -> dict[str, str]:
    package = _slug(name).replace("-", "_")
    return {
        "pyproject.toml": f"[project]\nname = \"{_slug(name)}\"\nversion = \"0.1.0\"\ndescription = \"AI-assisted backend generated by Friday\"\nrequires-python = \">=3.11\"\ndependencies = [\"fastapi\", \"uvicorn[standard]\", \"pydantic\"]\n\n[project.optional-dependencies]\ndev = [\"pytest\", \"httpx\"]\n\n[tool.pytest.ini_options]\ntestpaths = [\"tests\"]\npythonpath = [\".\"]\n",
        f"{package}/__init__.py": "",
        f"{package}/main.py": _fastapi_main(name, request),
        f"{package}/models.py": _fastapi_models(),
        f"{package}/routes.py": _fastapi_routes(name, request),
        f"{package}/services.py": _fastapi_services(name, request),
        "tests/test_health.py": f"from fastapi.testclient import TestClient\n\nfrom {package}.main import app\n\n\ndef test_health():\n    response = TestClient(app).get('/health')\n    assert response.status_code == 200\n",
        ".env.example": "APP_ENV=development\n",
        "README.md": _product_readme(name, request, "Python FastAPI backend", "python -m pip install -e .[dev]\nuvicorn " + package + ".main:app --reload"),
        ".gitignore": "__pycache__\n.pytest_cache\n.venv\n.env\n",
    }


def _go_files(name: str, request: str) -> dict[str, str]:
    module = f"friday/{_slug(name)}"
    return {
        "go.mod": f"module {module}\n\ngo 1.22\n",
        "main.go": _go_main(name, request),
        "handlers.go": _go_handlers(name, request),
        "models.go": _go_models(),
        "main_test.go": "package main\n\nimport \"testing\"\n\nfunc TestHealthPayload(t *testing.T) {\n\tpayload := healthPayload()\n\tif payload[\"status\"] != \"ok\" {\n\t\tt.Fatalf(\"expected ok status\")\n\t}\n}\n",
        "README.md": _product_readme(name, request, "Go HTTP backend", "go test ./...\ngo run ."),
        ".gitignore": ".env\nbin\n",
    }


def _rust_files(name: str, request: str) -> dict[str, str]:
    package = _slug(name).replace("-", "_")
    return {
        "Cargo.toml": f"[package]\nname = \"{package}\"\nversion = \"0.1.0\"\nedition = \"2021\"\n\n[dependencies]\naxum = \"0.7\"\ntokio = {{ version = \"1\", features = [\"macros\", \"rt-multi-thread\"] }}\nserde = {{ version = \"1\", features = [\"derive\"] }}\nserde_json = \"1\"\n",
        "src/main.rs": _rust_main(name, request),
        "src/models.rs": _rust_models(),
        "src/routes.rs": _rust_routes(name, request),
        "README.md": _product_readme(name, request, "Rust Axum backend", "cargo run\ncargo test"),
        ".gitignore": "target\n.env\n",
    }


def _next_page(name: str, request: str) -> str:
    return """import { HomePage } from '@/components/Landing/HomePage';

export default function Home() {
  return <HomePage />;
}
"""


def _web_product_blueprint(name: str, request: str) -> dict[str, Any]:
    text = str(request or "").lower()
    if any(term in text for term in ("university", "campus", "registrar", "lecturer", "student", "course approval", "bursary")):
        return {
            "hero_label": "Campus operations command center",
            "summary": "A registrar-grade dashboard for course approvals, student fee exceptions, lecturer workload changes, and admin reporting.",
            "workspace_label": "Registrar operations",
            "brief_title": "Registrar Decision Brief",
            "brief_action": "Generate registrar brief",
            "brief_empty": "Generate a registrar brief from the latest approvals, fee exceptions, and timetable changes.",
            "launch_title": "Campus launch path",
            "sample_note": "Registrar has 18 pending course approvals, bursary flagged 6 fee exceptions, and two lecturers need timetable changes reflected before Friday's admin report.",
            "work_items": [
                {
                    "id": "course-approval-queue",
                    "title": "Course approval queue",
                    "detail": "Track add/drop requests, prerequisite exceptions, departmental sign-off, and registrar approval in one review lane.",
                    "owner": "Registrar",
                    "status": "Captured",
                    "priority": "high",
                },
                {
                    "id": "student-fee-exceptions",
                    "title": "Student fee exceptions",
                    "detail": "Surface students with unpaid balances, scholarship holds, installment promises, and bursary decisions before registration closes.",
                    "owner": "Bursary team",
                    "status": "AI Brief",
                    "priority": "high",
                },
                {
                    "id": "lecturer-workload-change",
                    "title": "Lecturer workload changes",
                    "detail": "Flag timetable conflicts, lecturer capacity changes, and course allocation updates that affect student cohorts.",
                    "owner": "Academic affairs",
                    "status": "Ready",
                    "priority": "medium",
                },
                {
                    "id": "admin-report-pack",
                    "title": "Admin reporting pack",
                    "detail": "Prepare enrollment, approval, fees, lecturer workload, and student-services metrics for management review.",
                    "owner": "Admin reporting",
                    "status": "Captured",
                    "priority": "medium",
                },
            ],
            "metric_cards": [
                {"label": "pending approvals", "value": 18},
                {"label": "fee exceptions", "value": 6},
                {"label": "reports due", "value": 4},
            ],
            "value_props": [
                {
                    "title": "Registrar-first queues",
                    "detail": "Course approvals, add/drop requests, and student record issues are grouped by owner, urgency, and next decision.",
                },
                {
                    "title": "Fees and academic work together",
                    "detail": "Bursary exceptions, lecturer workload changes, and student registration blockers sit in the same operational view.",
                },
                {
                    "title": "Admin reports without spreadsheet hunts",
                    "detail": "Leadership gets enrollment, approvals, fees, lecturer, and student-service signals from one verified dashboard.",
                },
            ],
            "target_users": [
                "registrar offices",
                "department administrators",
                "lecturers",
                "bursary and finance teams",
                "academic affairs leaders",
            ],
            "integrations": [
                "student information system",
                "learning management system",
                "payment gateway",
                "Google Workspace",
                "CSV import/export",
            ],
            "pricing": [
                "Campus pilot: free for one department",
                "$99/month Small College",
                "$299/month Multi-department Campus",
            ],
            "launch_plan": [
                "Validate registrar workflow",
                "Import sample student/course/fee data",
                "Run course approval pilot",
                "Review privacy and FERPA-style controls",
                "Approve campus launch",
            ],
        }
    if _is_field_service_request(text):
        return {
            "hero_label": "Field service dispatch command center",
            "summary": "A dispatch-grade board for incoming jobs, technician availability, emergency calls, parts readiness, SLA risk, customer updates, and invoice handoff.",
            "workspace_label": "Dispatch operations",
            "brief_title": "Dispatch Decision Brief",
            "brief_action": "Generate dispatch brief",
            "brief_empty": "Generate a dispatch brief from today’s jobs, technician capacity, parts blockers, and customer update risks.",
            "launch_title": "Field service launch path",
            "sample_note": "Emergency HVAC call on Maple Street needs a certified technician by 2:30 PM, water-heater parts are delayed, and two customers need ETA updates before invoices can be closed.",
            "work_items": [
                {
                    "id": "emergency-dispatch-queue",
                    "title": "Emergency dispatch queue",
                    "detail": "Prioritize no-heat, burst-pipe, electrical outage, and same-day repair calls by SLA window, distance, and technician certification.",
                    "owner": "Dispatch lead",
                    "status": "Captured",
                    "priority": "high",
                },
                {
                    "id": "technician-capacity-board",
                    "title": "Technician capacity board",
                    "detail": "Match HVAC, plumbing, and electrical jobs to available technicians using location, skill tags, shift load, and emergency override status.",
                    "owner": "Service manager",
                    "status": "AI Brief",
                    "priority": "high",
                },
                {
                    "id": "parts-readiness-check",
                    "title": "Parts readiness check",
                    "detail": "Flag jobs blocked by compressor, breaker, valve, or water-heater parts before a truck is sent without the right inventory.",
                    "owner": "Parts coordinator",
                    "status": "Ready",
                    "priority": "high",
                },
                {
                    "id": "customer-eta-updates",
                    "title": "Customer ETA updates",
                    "detail": "Draft customer messages for late arrivals, technician swaps, emergency reprioritization, and completed repair follow-up.",
                    "owner": "Customer operations",
                    "status": "Captured",
                    "priority": "medium",
                },
                {
                    "id": "invoice-closeout-lane",
                    "title": "Invoice closeout lane",
                    "detail": "Move completed jobs from technician notes to invoice review with parts used, photos, warranty notes, and payment status.",
                    "owner": "Finance desk",
                    "status": "Ready",
                    "priority": "medium",
                },
            ],
            "metric_cards": [
                {"label": "urgent jobs open", "value": 9},
                {"label": "technicians available", "value": 14},
                {"label": "parts blockers", "value": 5},
            ],
            "value_props": [
                {
                    "title": "Dispatch sees the day clearly",
                    "detail": "Emergency jobs, technician capacity, SLA clocks, and same-day schedule changes live in one dispatch view.",
                },
                {
                    "title": "Technicians are assigned with context",
                    "detail": "Skill tags, truck inventory, location, and job urgency guide HVAC, plumbing, and electrical dispatch decisions.",
                },
                {
                    "title": "Customers get timely updates",
                    "detail": "ETA changes, technician swaps, parts delays, and invoice closeout messages are drafted before the phone starts ringing.",
                },
            ],
            "target_users": [
                "dispatch managers",
                "HVAC service coordinators",
                "plumbing operations teams",
                "electrical service desks",
                "field technicians",
                "finance and invoice staff",
            ],
            "integrations": [
                "Google Calendar dispatch board",
                "QuickBooks invoices",
                "Twilio/SMS customer updates",
                "parts inventory CSV",
                "technician mobile app",
            ],
            "pricing": [
                "Solo dispatcher pilot: free for one board",
                "$79/month Field Team",
                "$199/month Multi-crew Operations",
            ],
            "launch_plan": [
                "Import sample job and technician roster",
                "Validate emergency dispatch workflow",
                "Connect calendar and customer update templates",
                "Review PII, payment, and technician safety controls",
                "Approve field service launch",
            ],
        }
    if _is_restaurant_shift_request(text):
        return {
            "hero_label": "Restaurant shift command center",
            "summary": "A shift-grade dashboard for table waitlist pressure, kitchen ticket backlog, staff coverage, inventory shortages, delivery orders, customer complaints, refunds, food safety checks, and daily cash close.",
            "workspace_label": "Shift operations",
            "brief_title": "Shift Decision Brief",
            "brief_action": "Generate shift brief",
            "brief_empty": "Generate a shift brief from waitlist pressure, kitchen backlog, staff gaps, inventory shortages, complaints, refunds, and cash-close risk.",
            "launch_title": "Restaurant operations launch path",
            "sample_note": "Friday dinner service has 17 parties on the waitlist, grill tickets are 14 minutes behind, expo is short one runner, avocados are low, and two delivery refunds need manager approval before cash close.",
            "work_items": [
                {
                    "id": "waitlist-pressure-board",
                    "title": "Table waitlist pressure",
                    "detail": "Track party size, quoted wait, VIP flags, seating zones, and host stand decisions before the lobby spills into bad reviews.",
                    "owner": "Host lead",
                    "status": "Captured",
                    "priority": "high",
                },
                {
                    "id": "kitchen-ticket-backlog",
                    "title": "Kitchen ticket backlog",
                    "detail": "Monitor grill, fry, salad, expo, and delivery ticket age so managers can move staff before service quality drops.",
                    "owner": "Kitchen manager",
                    "status": "AI Brief",
                    "priority": "high",
                },
                {
                    "id": "staff-coverage-gaps",
                    "title": "Staff coverage gaps",
                    "detail": "Spot missing servers, runners, bartenders, dish coverage, and overtime risk across lunch, dinner, and closing shifts.",
                    "owner": "Floor manager",
                    "status": "Ready",
                    "priority": "high",
                },
                {
                    "id": "inventory-shortage-alerts",
                    "title": "Inventory shortage alerts",
                    "detail": "Flag low prep, eighty-sixed menu items, supplier delays, and substitution decisions before guests order unavailable dishes.",
                    "owner": "Prep lead",
                    "status": "Captured",
                    "priority": "medium",
                },
                {
                    "id": "delivery-refund-lane",
                    "title": "Delivery, complaints, and refunds",
                    "detail": "Group DoorDash/Uber Eats issues, missing items, guest complaints, comp decisions, and refund approvals by manager owner.",
                    "owner": "Guest recovery",
                    "status": "Ready",
                    "priority": "medium",
                },
                {
                    "id": "cash-close-safety-check",
                    "title": "Food safety and cash close",
                    "detail": "Keep temperature logs, sanitation checks, drawer variance, tip-out notes, and end-of-day cash close proof in one lane.",
                    "owner": "Closing manager",
                    "status": "Captured",
                    "priority": "medium",
                },
            ],
            "metric_cards": [
                {"label": "parties waiting", "value": 17},
                {"label": "tickets over SLA", "value": 9},
                {"label": "staff gaps", "value": 3},
            ],
            "value_props": [
                {
                    "title": "Managers see service pressure early",
                    "detail": "Waitlist, kitchen ticket backlog, delivery orders, and table turns sit in one shift command view.",
                },
                {
                    "title": "Staffing decisions use real signals",
                    "detail": "Coverage gaps, section load, runner needs, and closing tasks are tied to current restaurant demand.",
                },
                {
                    "title": "Guest recovery and closeout stop slipping",
                    "detail": "Complaints, refunds, food safety checks, inventory shortages, and daily cash close stay visible until resolved.",
                },
            ],
            "target_users": [
                "restaurant general managers",
                "shift managers",
                "host stand leads",
                "kitchen managers",
                "floor supervisors",
                "independent restaurant owners",
            ],
            "integrations": [
                "Toast or Square POS",
                "OpenTable/Resy waitlist",
                "DoorDash/Uber Eats orders",
                "inventory CSV",
                "staff schedule import",
            ],
            "pricing": [
                "Single-location pilot: free for one shift board",
                "$69/month Independent Restaurant",
                "$179/month Multi-location Group",
            ],
            "launch_plan": [
                "Import sample menu, staff, table, and delivery data",
                "Validate dinner rush workflow with a manager",
                "Connect POS/waitlist/delivery exports",
                "Review payment, refund, food safety, and employee-data controls",
                "Approve restaurant operations launch",
            ],
        }
    return _dynamic_web_product_blueprint(name, request)


def _is_field_service_request(text: str) -> bool:
    lowered = str(text or "").lower()
    terms = (
        "field service",
        "dispatch",
        "technician",
        "technicians",
        "hvac",
        "plumbing",
        "electrical",
        "same-day schedule",
        "parts readiness",
        "sla risk",
    )
    return "field service" in lowered or sum(1 for term in terms if term in lowered) >= 2


def _is_restaurant_shift_request(text: str) -> bool:
    lowered = str(text or "").lower()
    terms = (
        "restaurant",
        "restaurants",
        "shift",
        "waitlist",
        "kitchen ticket",
        "staff coverage",
        "inventory shortage",
        "delivery app",
        "customer complaint",
        "refund",
        "food safety",
        "cash close",
    )
    return "restaurant" in lowered or sum(1 for term in terms if term in lowered) >= 3


def _dynamic_web_product_blueprint(name: str, request: str) -> dict[str, Any]:
    phrases = _workflow_phrases(request)
    keywords = _keywords(request)
    subject = _product_subject(name, request)
    if len(phrases) < 3:
        phrases.extend(_keyword_phrases(keywords, existing=phrases))
    phrases = _dedupe_text(phrases)[:6] or [subject, "operational queue", "customer updates"]
    primary = phrases[0]
    secondary = phrases[1] if len(phrases) > 1 else "handoff risk"
    tertiary = phrases[2] if len(phrases) > 2 else "daily proof"
    launch_context = _join_phrases(phrases[:5])
    work_items = []
    owners = ["Operations lead", "AI coordinator", "Team lead", "Customer desk", "Finance owner", "Launch owner"]
    statuses = ["Captured", "AI Brief", "Ready", "Captured", "Ready", "AI Brief"]
    priorities = ["high", "high", "medium", "medium", "medium", "low"]
    for index, phrase in enumerate(phrases):
        title = _phrase_title(phrase)
        work_items.append(
            {
                "id": _slug(f"{phrase}-lane"),
                "title": title,
                "detail": f"Track {phrase} with status, urgency, owner, blocker, next action, customer impact, and proof before the workflow slips.",
                "owner": owners[index % len(owners)],
                "status": statuses[index % len(statuses)],
                "priority": priorities[index % len(priorities)],
            }
        )
    return {
        "hero_label": f"{subject} command workspace",
        "summary": f"A focused {subject.lower()} command workspace for {launch_context}.",
        "workspace_label": f"{subject} operations",
        "brief_title": f"{subject} Decision Brief",
        "brief_action": "Generate operational brief",
        "brief_empty": f"Generate a brief from {primary}, {secondary}, {tertiary}, blockers, and next actions.",
        "launch_title": f"{subject} launch path",
        "sample_note": f"{subject} needs attention on {primary}, {secondary}, and {tertiary} before the next operational review.",
        "work_items": work_items,
        "metric_cards": [
            {"label": _metric_label(primary), "value": 12},
            {"label": _metric_label(secondary), "value": 5},
            {"label": _metric_label(tertiary), "value": 3},
        ],
        "value_props": [
            {
                "title": f"{subject} pressure becomes visible",
                "detail": f"{_phrase_title(primary)}, {_phrase_title(secondary)}, and {_phrase_title(tertiary)} are tracked by urgency, owner, and next action.",
            },
            {
                "title": "Decisions carry context",
                "detail": f"Friday turns {launch_context} into concise briefs with risk, customer impact, and proof for the next operator.",
            },
            {
                "title": "Proof stays attached",
                "detail": "Tests, audits, preview checks, launch approvals, and unresolved gaps stay visible before readiness claims.",
            },
        ],
        "target_users": _target_users_for_subject(subject),
        "integrations": _dynamic_integrations(request),
        "pricing": [
            f"{subject} pilot: free for one workspace",
            "$49/month Operator",
            "$149/month Team Operations",
        ],
        "launch_plan": [
            f"Validate {primary} workflow",
            f"Import sample {subject.lower()} data",
            f"Connect {secondary} source",
            "Review privacy, security, and approval controls",
            f"Approve {subject.lower()} launch",
        ],
    }


def _workflow_phrases(request: str) -> list[str]:
    text = _clean(request)
    candidates: list[str] = []
    patterns = [
        r"\b(?:manage|managing|track|tracking|coordinate|coordinating|handle|handling|monitor|monitoring)\s+([^.;]+)",
        r"\bfor\s+[^:]{0,80}:\s+([^.;]+)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            candidates.extend(_split_workflow_list(match.group(1)))
    return _dedupe_text([phrase for phrase in candidates if _useful_phrase(phrase)])


def _split_workflow_list(value: str) -> list[str]:
    cleaned = re.sub(r"\b(?:and|plus)\b", ",", value, flags=re.IGNORECASE)
    parts = [re.sub(r"\s+", " ", part).strip(" ,:-") for part in cleaned.split(",")]
    return [part.lower() for part in parts if part and not _looks_like_prompt_fragment(part)]


def _useful_phrase(value: str) -> bool:
    text = str(value or "").strip().lower()
    if len(text) < 4:
        return False
    blocked = {
        "real gates",
        "google stitch for design handoff",
        "requirements/system design/implementation/features docs",
        "technical-ready or market-ready without proof",
    }
    return text not in blocked and not any(term in text for term in ("next.js", "nextjs", "web-app", "technical-ready", "market-ready", "google stitch"))


def _keyword_phrases(keywords: list[str], *, existing: list[str]) -> list[str]:
    phrases = []
    for keyword in keywords:
        if any(keyword in phrase for phrase in existing):
            continue
        phrases.append(keyword)
    return phrases


def _product_subject(name: str, request: str) -> str:
    raw = _clean(name)
    if raw and raw not in {"FlowPilot"}:
        subject = re.sub(r"\b(OS|Dashboard|Portal|Studio|Command Center|Command|Manager|Pilot|Console|Workspace|App)\b", "", raw, flags=re.IGNORECASE)
        subject = re.sub(r"\s+", " ", subject).strip()
        if subject:
            return subject
    keywords = _keywords(request)
    return " ".join(keywords[:2]).title() if keywords else "Operations"


def _phrase_title(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).title()


def _metric_label(value: str) -> str:
    words = _words(value)[:3]
    return " ".join(words) if words else "open items"


def _join_phrases(phrases: list[str]) -> str:
    clean = [phrase for phrase in phrases if phrase]
    if not clean:
        return "operational queues, handoffs, and launch proof"
    if len(clean) == 1:
        return clean[0]
    return ", ".join(clean[:-1]) + f", and {clean[-1]}"


def _target_users_for_subject(subject: str) -> list[str]:
    clean = subject.lower()
    return [
        f"{clean} operators",
        f"{clean} managers",
        "team leads",
        "customer-facing staff",
        "operations owners",
    ]


def _dynamic_integrations(request: str) -> list[str]:
    text = str(request or "").lower()
    integrations = ["CSV import/export", "Google Calendar", "Slack"]
    if any(term in text for term in ("payment", "refund", "invoice", "cash", "billing")):
        integrations.append("payments/accounting export")
    if any(term in text for term in ("customer", "sms", "eta", "complaint", "delivery")):
        integrations.append("customer messaging")
    if any(term in text for term in ("inventory", "stock", "parts", "menu")):
        integrations.append("inventory system")
    return _dedupe_text(integrations)[:5]


def _dedupe_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = re.sub(r"\s+", " ", str(value or "").strip().lower())
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _next_product_plan(name: str, request: str) -> str:
    blueprint = _web_product_blueprint(name, request)
    return f"""export type WorkStatus = 'Captured' | 'AI Brief' | 'Ready' | 'Reviewed';

export type WorkItem = {{
  id: string;
  title: string;
  detail: string;
  owner: string;
  status: WorkStatus;
  priority: 'high' | 'medium' | 'low';
}};

export type ProductPlan = {{
  name: string;
  request: string;
  heroLabel: string;
  summary: string;
  workspaceLabel: string;
  briefTitle: string;
  briefAction: string;
  briefEmpty: string;
  launchTitle: string;
  sampleNote: string;
  workItems: WorkItem[];
  metricCards: Array<{{ label: string; value: number }}>;
  valueProps: Array<{{ title: string; detail: string }}>;
  targetUsers: string[];
  integrations: string[];
  pricing: string[];
  launchPlan: string[];
}};

export type DecisionBrief = {{
  summary: string;
  nextAction: string;
  risks: string;
}};

export const productPlan: ProductPlan = {{
  name: {_json_value(name)},
  request: {_json_value(_clean(request))},
  heroLabel: {_json_value(blueprint["hero_label"])},
  summary: {_json_value(blueprint["summary"])},
  workspaceLabel: {_json_value(blueprint["workspace_label"])},
  briefTitle: {_json_value(blueprint["brief_title"])},
  briefAction: {_json_value(blueprint["brief_action"])},
  briefEmpty: {_json_value(blueprint["brief_empty"])},
  launchTitle: {_json_value(blueprint["launch_title"])},
  sampleNote: {_json_value(blueprint["sample_note"])},
  workItems: {_json(blueprint["work_items"]).rstrip()},
  metricCards: {_json(blueprint["metric_cards"]).rstrip()},
  valueProps: {_json(blueprint["value_props"]).rstrip()},
  targetUsers: {_json(blueprint["target_users"]).rstrip()},
  integrations: {_json(blueprint["integrations"]).rstrip()},
  pricing: {_json(blueprint["pricing"]).rstrip()},
  launchPlan: {_json(blueprint["launch_plan"]).rstrip()},
}};

export function createDecisionBrief(note: string, items: WorkItem[]): DecisionBrief {{
  const cleanNote = note.trim() || productPlan.sampleNote;
  const highestPriority = items.find((item) => item.priority === 'high') ?? items[0];
  const blockers = items.filter((item) => item.status !== 'Reviewed').map((item) => item.owner);
  return {{
    summary: `Summary: ${{cleanNote}}`,
    nextAction: `Next action: ${{highestPriority?.owner ?? 'Operator'}} should move "${{highestPriority?.title ?? 'the active workflow'}}" forward.`,
    risks: blockers.length ? `Risks: unresolved handoffs for ${{Array.from(new Set(blockers)).join(', ')}}.` : 'Risks: no open blockers recorded.',
  }};
}}

export function markWorkItemReviewed(items: WorkItem[], id: string): WorkItem[] {{
  return items.map((item) => (item.id === id ? {{ ...item, status: 'Reviewed' }} : item));
}}
"""


def _next_workspace_console() -> str:
    return """'use client';

import { Bot, ClipboardList, PlugZap, Users, Sparkles } from 'lucide-react';
import { useMemo, useState } from 'react';
import { WorkItemCard } from '@/components/Workspace/WorkItemCard';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { useBriefDraft } from '@/hooks/useBriefDraft';
import { useWorkspaceStore } from '@/store/workspaceStore';
import type { ProductPlan } from '@/lib/productPlan';

type WorkspaceConsoleProps = {
  plan: ProductPlan;
};

export function WorkspaceConsole({ plan }: WorkspaceConsoleProps) {
  const items = useWorkspaceStore((state) => state.items);
  const reviewItem = useWorkspaceStore((state) => state.reviewItem);
  const [note, setNote] = useState(plan.sampleNote);
  const { brief, draftBrief, loading, error } = useBriefDraft();
  const reviewed = items.filter((item) => item.status === 'Reviewed').length;
  const metrics = useMemo(
    () => plan.metricCards.map((metric, index) => ({
      ...metric,
      value: metric.value + (index === 0 ? reviewed : 0),
    })),
    [plan.metricCards, reviewed],
  );

  return (
    <section className="workspace" id="workspace">
      <header className="workspace-header">
        <div>
          <Badge>{plan.workspaceLabel}</Badge>
          <h1>{plan.name}</h1>
          <p>{plan.summary}</p>
        </div>
        <Button type="button" onClick={() => draftBrief(note, items)} disabled={loading}>
          <Bot size={18} /> {loading ? 'Drafting...' : plan.briefAction}
        </Button>
      </header>

      <section className="metrics" aria-label="workflow metrics">
        {metrics.map((metric) => (
          <Card key={metric.label}><b>{metric.value}</b><span>{metric.label}</span></Card>
        ))}
      </section>

      <section className="board" aria-label="work board">
        {items.map((item) => (
          <WorkItemCard key={item.id} item={item} onReview={() => reviewItem(item.id)} />
        ))}
      </section>

      <section className="assistant" id="assistant">
        <Card>
          <h2><ClipboardList size={18} /> {plan.briefTitle}</h2>
          <Textarea value={note} onChange={(event) => setNote(event.target.value)} aria-label="Source note" />
          <Button type="button" onClick={() => draftBrief(note, items)} disabled={loading}>
            <Sparkles size={16} /> Draft brief
          </Button>
          {error ? <p className="error-copy">{error}</p> : null}
          <p className="brief">{brief ? `${brief.summary} ${brief.nextAction} ${brief.risks}` : plan.briefEmpty}</p>
        </Card>
        <Card id="market">
          <h2><Users size={18} /> Target Users</h2>
          <p>{plan.targetUsers.join(', ')}</p>
          <h2><PlugZap size={18} /> Integrations</h2>
          <p>{plan.integrations.join(', ')}</p>
        </Card>
      </section>
    </section>
  );
}
"""


def _next_work_item_card() -> str:
    return """import { CheckCircle2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import type { WorkItem } from '@/lib/productPlan';

type WorkItemCardProps = {
  item: WorkItem;
  onReview: () => void;
};

export function WorkItemCard({ item, onReview }: WorkItemCardProps) {
  const reviewed = item.status === 'Reviewed';

  return (
    <Card className="work-card">
      <Badge>{item.status}</Badge>
      <h2>{item.title}</h2>
      <p>{item.detail}</p>
      <small>{item.owner} / {item.priority} priority</small>
      <Button type="button" variant="secondary" onClick={onReview} disabled={reviewed}>
        <CheckCircle2 size={16} /> {reviewed ? 'Reviewed' : 'Mark reviewed'}
      </Button>
    </Card>
  );
}
"""


def _next_brief_route() -> str:
    return """import { NextResponse } from 'next/server';
import { createDecisionBrief, productPlan } from '@/lib/productPlan';

export async function GET() {
  return NextResponse.json(createDecisionBrief(productPlan.sampleNote, productPlan.workItems));
}

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const note = typeof body.note === 'string' ? body.note : productPlan.sampleNote;
  const items = Array.isArray(body.items) ? body.items : productPlan.workItems;
  return NextResponse.json(createDecisionBrief(note, items));
}
"""


def _next_home_page() -> str:
    return """import Link from 'next/link';
import { ArrowRight, CheckCircle2, ShieldCheck, Sparkles, Zap } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { productPlan } from '@/lib/productPlan';

const icons = [ShieldCheck, Zap, CheckCircle2];

export function HomePage() {
  return (
    <main className="landing-shell">
      <section className="landing-hero">
        <div className="hero-copy">
          <Badge>{productPlan.heroLabel}</Badge>
          <h1>{productPlan.name}</h1>
          <p>{productPlan.summary}</p>
          <div className="hero-actions">
            <Button asChild>
              <Link href="/workspace">
                Open workspace <ArrowRight size={16} />
              </Link>
            </Button>
            <Button asChild variant="secondary">
              <Link href="/login">Sign in</Link>
            </Button>
          </div>
        </div>
        <Card className="signal-panel">
          <Sparkles size={22} />
          <h2>{productPlan.launchTitle}</h2>
          <p>{productPlan.launchPlan.join(' / ')}</p>
        </Card>
      </section>

      <section className="pillar-grid" aria-label="Product priorities">
        {productPlan.valueProps.map((pillar, index) => {
          const Icon = icons[index % icons.length];
          return (
          <Card key={pillar.title}>
            <Icon size={20} />
            <h2>{pillar.title}</h2>
            <p>{pillar.detail}</p>
          </Card>
          );
        })}
      </section>
    </main>
  );
}
"""


def _next_error_boundary() -> str:
    return """'use client';

import { Button } from '@/components/ui/button';

export default function Error({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="error-state">
      <h1>Something needs attention</h1>
      <p>The app caught an error before it could finish this view.</p>
      <Button type="button" onClick={reset}>Try again</Button>
    </main>
  );
}
"""


def _policy_page(name: str, title: str, body: str) -> str:
    return f"""import type {{ Metadata }} from 'next';

export const metadata: Metadata = {{
  title: {_json_value(f"{title} | {name}")},
}};

export default function Page() {{
  return (
    <main className="policy-page">
      <h1>{_clean(title)}</h1>
      <p>{_clean(body)}</p>
    </main>
  );
}}
"""


def _next_login_page(name: str) -> str:
    return f"""'use client';

import {{ useState }} from 'react';
import {{ Button }} from '@/components/ui/button';
import {{ Input }} from '@/components/ui/input';
import {{ useAccessToken }} from '@/hooks/useAccessToken';

export function LoginPage() {{
  const [email, setEmail] = useState('');
  const {{ token, setToken }} = useAccessToken();

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {{
    event.preventDefault();
    setToken(`preview-token:${{email || 'operator'}}`);
  }}

  return (
    <section className="auth-panel">
      <p className="eyebrow">{_clean(name)}</p>
      <h1>Operator sign in</h1>
      <form onSubmit={{handleSubmit}}>
        <label htmlFor="email">Email</label>
        <Input id="email" type="email" value={{email}} onChange={{(event) => setEmail(event.target.value)}} placeholder="you@example.com" />
        <Button type="submit">Continue</Button>
      </form>
      {{token ? <p className="subtle">Preview session stored locally.</p> : null}}
    </section>
  );
}}
"""


def _next_workspace_page() -> str:
    return """import { WorkspaceConsole } from '@/components/Workspace/WorkspaceConsole';
import { productPlan } from '@/lib/productPlan';

export function WorkspacePage() {
  return <WorkspaceConsole plan={productPlan} />;
}
"""


def _next_app_shell() -> str:
    return """import { Sidebar } from '@/components/layout/Sidebar';
import { TopBar } from '@/components/layout/TopBar';

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="app-main">
        <TopBar />
        {children}
      </div>
    </div>
  );
}
"""


def _next_sidebar() -> str:
    return """import Link from 'next/link';
import { Sparkles } from 'lucide-react';
import { navItems } from '@/components/layout/nav-items';

export function Sidebar() {
  return (
    <aside className="sidebar">
      <strong><Sparkles size={18} /> Friday Studio</strong>
      <nav aria-label="Primary">
        {navItems.map((item) => (
          <Link key={item.href} href={item.href}>
            <item.icon size={16} /> {item.label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
"""


def _next_topbar(name: str) -> str:
    return f"""export function TopBar() {{
  return (
    <header className="topbar">
      <p>{_clean(name)} workspace</p>
      <span>Preview environment</span>
    </header>
  );
}}
"""


def _next_nav_items() -> str:
    return """import { LayoutDashboard, MessageSquare, Settings } from 'lucide-react';

export const navItems = [
  { href: '/workspace', label: 'Workspace', icon: LayoutDashboard },
  { href: '/workspace#assistant', label: 'AI brief', icon: MessageSquare },
  { href: '/workspace#market', label: 'Launch', icon: Settings },
];
"""


def _next_footer(name: str) -> str:
    return f"""export function Footer() {{
  return <footer className="footer">Copyright {{new Date().getFullYear()}} {_clean(name)}. All rights reserved.</footer>;
}}
"""


def _next_ui_button() -> str:
    return """import Link from 'next/link';
import * as React from 'react';
import { cn } from '@/lib/utils';

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  asChild?: boolean;
  href?: string;
  variant?: 'primary' | 'secondary' | 'ghost';
};

export function Button({ asChild = false, className, href, variant = 'primary', children, ...props }: ButtonProps) {
  const classes = cn('button', `button-${variant}`, className);
  if (asChild && React.isValidElement(children)) {
    return React.cloneElement(children as React.ReactElement<{ className?: string }>, {
      className: cn(classes, (children.props as { className?: string }).className),
    });
  }
  if (href) {
    return <Link className={classes} href={href}>{children}</Link>;
  }
  return <button className={classes} {...props}>{children}</button>;
}
"""


def _next_ui_badge() -> str:
    return """import type { HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn('badge', className)} {...props} />;
}
"""


def _next_ui_card() -> str:
    return """import type { HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export function Card({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return <article className={cn('card', className)} {...props} />;
}
"""


def _next_ui_input() -> str:
    return """import type { InputHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn('input', className)} {...props} />;
}
"""


def _next_ui_textarea() -> str:
    return """import type { TextareaHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn('textarea', className)} {...props} />;
}
"""


def _next_use_access_token() -> str:
    return """'use client';

import { useCallback, useState } from 'react';
import { clearAccessToken, readAccessToken, writeAccessToken } from '@/lib/authTokens';

export function useAccessToken() {
  const [token, setCurrentToken] = useState(readAccessToken);

  const setToken = useCallback((value: string) => {
    writeAccessToken(value);
    setCurrentToken(value);
  }, []);

  const clearToken = useCallback(() => {
    clearAccessToken();
    setCurrentToken('');
  }, []);

  return { token, setToken, clearToken };
}
"""


def _next_use_brief_draft() -> str:
    return """'use client';

import { useState } from 'react';
import { BriefService } from '@/services/BriefService';
import type { DecisionBrief, WorkItem } from '@/lib/productPlan';

export function useBriefDraft() {
  const [brief, setBrief] = useState<DecisionBrief | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function draftBrief(note: string, items: WorkItem[]) {
    setLoading(true);
    setError('');
    try {
      setBrief(await BriefService.draft({ note, items }));
    } catch {
      setError('Local fallback used because the brief API did not respond.');
      setBrief(await BriefService.localDraft({ note, items }));
    } finally {
      setLoading(false);
    }
  }

  return { brief, draftBrief, error, loading };
}
"""


def _next_auth_tokens() -> str:
    return """const ACCESS_TOKEN_KEY = 'friday.access-token';

export function readAccessToken() {
  if (typeof window === 'undefined') return '';
  return window.localStorage.getItem(ACCESS_TOKEN_KEY) ?? '';
}

export function writeAccessToken(value: string) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(ACCESS_TOKEN_KEY, value);
}

export function clearAccessToken() {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
}
"""


def _next_api_service() -> str:
    return """import axios from 'axios';
import { readAccessToken } from '@/lib/authTokens';

export const apiClient = axios.create({
  baseURL: '/api',
  withCredentials: true,
  timeout: 15000,
});

apiClient.interceptors.request.use((config) => {
  const token = readAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
"""


def _next_brief_service() -> str:
    return """import { apiClient } from '@/services/api';
import { createDecisionBrief, productPlan, type DecisionBrief, type WorkItem } from '@/lib/productPlan';

export type DraftBriefRequest = {
  note: string;
  items: WorkItem[];
};

export function normalizeBrief(value: unknown): DecisionBrief {
  const body = value && typeof value === 'object' ? value as Record<string, unknown> : {};
  return {
    summary: typeof body.summary === 'string' ? body.summary : 'Summary: no brief returned.',
    nextAction: typeof body.nextAction === 'string' ? body.nextAction : 'Next action: verify the source workflow.',
    risks: typeof body.risks === 'string' ? body.risks : 'Risks: missing API evidence.',
  };
}

export const BriefService = {
  async fetch() {
    const response = await apiClient.get('/brief');
    return normalizeBrief(response.data);
  },

  async draft(payload: DraftBriefRequest) {
    const response = await apiClient.post('/brief', payload);
    return normalizeBrief(response.data);
  },

  async localDraft(payload: DraftBriefRequest) {
    return createDecisionBrief(payload.note || productPlan.sampleNote, payload.items.length ? payload.items : productPlan.workItems);
  },
};
"""


def _next_brief_service_test() -> str:
    return """import { describe, expect, it } from 'vitest';
import { normalizeBrief } from '@/services/BriefService';

describe('normalizeBrief', () => {
  it('keeps structured brief fields', () => {
    expect(normalizeBrief({ summary: 'Summary: ok', nextAction: 'Next action: ship', risks: 'Risks: none' })).toEqual({
      summary: 'Summary: ok',
      nextAction: 'Next action: ship',
      risks: 'Risks: none',
    });
  });
});
"""


def _next_workspace_store() -> str:
    return """import { create } from 'zustand';
import { markWorkItemReviewed, productPlan, type WorkItem } from '@/lib/productPlan';

type WorkspaceState = {
  items: WorkItem[];
  reviewItem: (id: string) => void;
  reset: () => void;
};

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  items: productPlan.workItems,
  reviewItem: (id) => set((state) => ({ items: markWorkItemReviewed(state.items, id) })),
  reset: () => set({ items: productPlan.workItems }),
}));
"""


def _next_workspace_store_test() -> str:
    return """import { describe, expect, it } from 'vitest';
import { markWorkItemReviewed, productPlan } from '@/lib/productPlan';

describe('workspace state helpers', () => {
  it('marks a work item reviewed without mutating the original list', () => {
    const updated = markWorkItemReviewed(productPlan.workItems, productPlan.workItems[0].id);
    expect(updated[0].status).toBe('Reviewed');
    expect(productPlan.workItems[0].status).not.toBe('Reviewed');
  });
});
"""


def _next_utils() -> str:
    return """import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
"""


def _next_csp() -> str:
    return """export const contentSecurityPolicy = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "connect-src 'self'",
].join('; ');
"""


def _next_types() -> str:
    return """export type ApiResult<T> = {
  data: T;
  message?: string;
};

export type ReadinessState = 'not_built' | 'gates_running' | 'technical_ready' | 'market_blocked' | 'market_ready';
"""


def _next_frontend_structure() -> str:
    return """# Frontend Folder Structure

This scaffold follows the NexusForge-style Next.js frontend layout.

## Project Identity

- Framework: Next.js App Router
- Language: TypeScript, strict mode
- Main source root: `src`
- Import alias: `@/*` -> `src/*`
- Styling/UI: Tailwind-ready CSS, shadcn-style primitives, lucide-react
- Data/API layer: services in `src/services`
- Client state: Zustand stores in `src/store`
- Tests: Vitest, Testing Library, colocated `__tests__`, and `src/test`

## Structure

```txt
src/
|-- app/                         Route groups, layouts, route handlers
|   |-- (auth)/
|   |-- (dashboard)/
|   `-- api/
|-- components/                  Feature UI and reusable primitives
|   |-- Auth/
|   |-- Landing/
|   |-- Workspace/
|   |-- Shared/
|   |-- layout/
|   `-- ui/
|-- hooks/                       Cross-feature React hooks
|-- lib/                         Shared utilities, security, domain helpers
|-- services/                    Backend API clients and service tests
|-- store/                       Client stores
|-- test/                        Test setup and render helpers
`-- types/                       Shared TypeScript contracts
```

## Replication Rules

1. Keep route files thin.
2. Put real feature UI in `src/components/<FeatureName>`.
3. Put generic primitives in `src/components/ui`.
4. Put API clients in `src/services`.
5. Put shared client state in `src/store`.
6. Put reusable hooks in `src/hooks`.
7. Put shared utilities and framework helpers in `src/lib`.
8. Put shared DTOs and contracts in `src/types`.
9. Keep tests close to the code they validate.
10. Use `@/` imports for anything inside `src`.
"""


def _next_css() -> str:
    return """@import "tailwindcss";

:root {
  --surface: #0f1115;
  --surface-low: #151a21;
  --surface-card: #1d232c;
  --text: #f5f7fb;
  --muted: #a9b1bf;
  --line: #313846;
  --primary: #64e4d7;
  --secondary: #f0c36a;
  --danger: #ff7a7a;
}

* { box-sizing: border-box; }
html { color-scheme: dark; }
body {
  margin: 0;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif;
  color: var(--text);
  background: var(--surface);
}
a { color: inherit; text-decoration: none; }
button, input, textarea { font: inherit; }
h1, h2, p { margin-top: 0; }
h1 { font-size: clamp(2.2rem, 5vw, 4.2rem); line-height: 1.02; margin-bottom: 16px; overflow-wrap: anywhere; }
h2 { font-size: 1.05rem; }

.landing-shell, .workspace, .policy-page, .error-state { width: min(1180px, calc(100% - 32px)); margin: 0 auto; }
.landing-hero { min-height: 72vh; display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(280px, .7fr); align-items: center; gap: 24px; padding: 56px 0 28px; }
.hero-copy { min-width: 0; }
.hero-copy p { max-width: 720px; color: var(--muted); line-height: 1.7; }
.hero-actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 24px; }
.pillar-grid, .metrics, .board, .assistant { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
.signal-panel { min-height: 220px; align-content: end; }

.app-shell { display: grid; grid-template-columns: 244px minmax(0, 1fr); min-height: 100vh; }
.app-main { min-width: 0; }
.sidebar { border-right: 1px solid var(--line); background: #11161d; padding: 22px; }
.sidebar strong, .sidebar a, .topbar { display: flex; align-items: center; gap: 10px; }
.sidebar nav { display: grid; gap: 8px; margin-top: 24px; }
.sidebar a { color: var(--muted); padding: 10px 0; }
.topbar { justify-content: space-between; border-bottom: 1px solid var(--line); padding: 18px 24px; color: var(--muted); }
.workspace { padding: 32px 0; }
.workspace-header { display: flex; align-items: end; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
.workspace-header p { max-width: 740px; color: var(--muted); line-height: 1.6; }
.metrics { margin-bottom: 16px; }
.metrics b { display: block; font-size: 2rem; }
.metrics span, .card p, .work-card small { color: var(--muted); }
.assistant { grid-template-columns: 1.4fr .6fr; margin-top: 16px; }

.card { background: var(--surface-card); border: 1px solid var(--line); border-radius: 8px; padding: 18px; }
.badge { display: inline-flex; width: fit-content; align-items: center; border: 1px solid color-mix(in srgb, var(--primary) 45%, var(--line)); border-radius: 999px; padding: 5px 9px; color: var(--primary); font-size: .74rem; font-weight: 700; letter-spacing: 0; }
.button { display: inline-flex; min-height: 40px; align-items: center; justify-content: center; gap: 8px; border-radius: 8px; border: 1px solid transparent; padding: 9px 13px; cursor: pointer; font-weight: 700; }
.button-primary { background: var(--primary); color: #061212; }
.button-secondary { border-color: var(--line); background: transparent; color: var(--text); }
.button-ghost { background: transparent; color: var(--muted); }
.button:disabled { cursor: not-allowed; opacity: .65; }
.input, .textarea { width: 100%; border: 1px solid var(--line); border-radius: 8px; background: #10161d; color: var(--text); padding: 11px 12px; }
.textarea { min-height: 120px; resize: vertical; margin-bottom: 12px; }
.brief { border-left: 3px solid var(--primary); padding-left: 12px; margin-top: 14px; color: var(--muted); }
.error-copy { color: var(--danger); }
.auth-shell, .error-state { min-height: 100vh; display: grid; place-items: center; padding: 24px; }
.auth-panel { width: min(420px, 100%); display: grid; gap: 14px; }
.auth-panel form { display: grid; gap: 10px; }
.eyebrow, .subtle { color: var(--muted); font-size: .86rem; }
.policy-page { padding: 72px 0; color: var(--muted); }
.footer { padding: 28px; color: var(--muted); }

@media (max-width: 900px) {
  .landing-hero, .app-shell, .pillar-grid, .metrics, .board, .assistant { grid-template-columns: 1fr; }
  .sidebar { border-right: 0; border-bottom: 1px solid var(--line); }
  .workspace-header { align-items: start; flex-direction: column; }
}
"""


def _flutter_main(name: str, request: str) -> str:
    return f"""import 'package:flutter/material.dart';
import 'home_screen.dart';

void main() => runApp(const FridayApp());

class FridayApp extends StatelessWidget {{
  const FridayApp({{super.key}});

  @override
  Widget build(BuildContext context) {{
    return MaterialApp(
      title: '{name}',
      theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF2B7A78)), useMaterial3: true),
      home: const HomeScreen(productName: '{name}', requestText: {_json_value(_clean(request))}),
    );
  }}
}}
"""


def _flutter_home_screen(name: str, request: str) -> str:
    return """import 'package:flutter/material.dart';
import 'workflow_store.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.productName, required this.requestText});

  final String productName;
  final String requestText;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final WorkflowStore store = WorkflowStore();
  int reviewed = 0;
  String brief = 'Generate a brief to see the AI workflow.';

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.productName)),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(widget.requestText, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 20),
          FilledButton.icon(onPressed: () => setState(() => brief = store.generateBrief()), icon: const Icon(Icons.auto_awesome), label: const Text('Generate daily brief')),
          const SizedBox(height: 16),
          Text(brief),
          const SizedBox(height: 20),
          Wrap(spacing: 12, runSpacing: 12, children: store.items.map((item) => Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(item.title, style: Theme.of(context).textTheme.titleLarge), Text(item.detail), TextButton(onPressed: () => setState(() => reviewed++), child: const Text('Mark reviewed'))])))).toList()),
          const SizedBox(height: 20),
          Text('Reviewed: $reviewed'),
        ],
      ),
    );
  }
}
"""


def _flutter_workflow_store() -> str:
    return """class WorkItem {
  const WorkItem({required this.title, required this.detail});

  final String title;
  final String detail;
}

class WorkflowStore {
  final List<WorkItem> items = const [
    WorkItem(title: 'Capture recurring work', detail: 'Turn repeat requests into a clear queue.'),
    WorkItem(title: 'AI action brief', detail: 'Summarize risks, owners, and next actions.'),
    WorkItem(title: 'Team handoff', detail: 'Prepare a status update someone can send.'),
  ];

  String generateBrief() {
    return 'Today: triage, unblock one owner, send one customer-ready update, and validate with one real user.';
  }
}
"""


def _fastify_server(name: str, request: str) -> str:
    return """import { buildApp } from './app.js';

const app = buildApp();
const port = Number(process.env.PORT || 3000);

app.listen({ port, host: '127.0.0.1' });
"""


def _fastify_app(name: str, request: str) -> str:
    return f"""import Fastify from 'fastify';
import cors from '@fastify/cors';
import {{ briefRoutes }} from './routes/brief.js';
import {{ workItemRoutes }} from './routes/workItems.js';

export function buildApp() {{
  const app = Fastify({{ logger: true }});
  app.register(cors, {{ origin: true }});

  app.get('/health', async () => ({{ status: 'ok', service: {_json_value(name)} }}));
  app.register(briefRoutes, {{ prefix: '/api', product: {_json_value(name)}, requestText: {_json_value(request)} }});
  app.register(workItemRoutes, {{ prefix: '/api' }});

  return app;
}}
"""


def _fastify_brief_route(name: str, request: str) -> str:
    return """import { createDecisionBrief } from '../services/briefService.js';

export async function briefRoutes(app, options) {
  const product = options.product;
  const requestText = options.requestText;

  app.get('/brief', async () => createDecisionBrief({ product, requestText }));
}
"""


def _fastify_work_items_route() -> str:
    return """import { saveWorkItem } from '../storage/memoryStore.js';
import { validateWorkItem } from '../validation/workItem.js';

export async function workItemRoutes(app) {
  app.post('/work-items', async (request, reply) => {
    const item = validateWorkItem(request.body);
    const saved = saveWorkItem(item);
    return reply.code(201).send(saved);
  });
}
"""


def _fastify_brief_service(name: str, request: str) -> str:
    return """export function createDecisionBrief({ product, requestText }) {
  return {
    product,
    request: requestText,
    summary: 'Capture repeat work, name the owner, and send one customer-ready update.',
    nextActions: ['triage queue', 'assign owner', 'send status update'],
    risks: ['No external AI provider is configured yet', 'Outbound actions should remain approval-gated'],
  };
}
"""


def _fastify_memory_store() -> str:
    return """const workItems = [];

export function saveWorkItem(item) {
  const saved = { id: Date.now(), ...item, status: item.status || 'captured' };
  workItems.push(saved);
  return saved;
}

export function listWorkItems() {
  return [...workItems];
}
"""


def _fastify_work_item_validation() -> str:
    return """export function validateWorkItem(value) {
  const body = value && typeof value === 'object' ? value : {};
  const title = String(body.title || '').trim();
  if (!title) {
    throw new Error('title is required');
  }
  return {
    title,
    owner: String(body.owner || 'operator').trim(),
    priority: String(body.priority || 'normal').trim(),
  };
}
"""


def _fastapi_main(name: str, request: str) -> str:
    package = _slug(name).replace("-", "_")
    return f"""from fastapi import FastAPI

from {package}.routes import router

app = FastAPI(title={_json_value(name)})
app.include_router(router)
"""


def _fastapi_models() -> str:
    return """from pydantic import BaseModel, Field


class WorkItem(BaseModel):
    title: str = Field(min_length=1)
    owner: str = ""
    priority: str = "normal"
"""


def _fastapi_routes(name: str, request: str) -> str:
    return f"""from fastapi import APIRouter

from .models import WorkItem
from .services import brief_payload, capture_work_item

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {{"status": "ok", "service": {_json_value(name)}}}


@router.get("/api/brief")
def brief() -> dict[str, object]:
    return brief_payload()


@router.post("/api/work-items", status_code=201)
def create_work_item(item: WorkItem) -> dict[str, object]:
    return capture_work_item(item)
"""


def _fastapi_services(name: str, request: str) -> str:
    return f"""from .models import WorkItem


def brief_payload() -> dict[str, object]:
    return {{
        "product": {_json_value(name)},
        "request": {_json_value(request)},
        "next_actions": ["triage queue", "assign owner", "send status update"],
        "risks": ["No external AI provider is configured yet", "Outbound actions should remain approval-gated"],
    }}


def capture_work_item(item: WorkItem) -> dict[str, object]:
    return {{"status": "captured", "item": item.model_dump()}}
"""


def _go_main(name: str, request: str) -> str:
    return """package main

import (
	"log"
	"net/http"
	"os"
)

func main() {
	mux := http.NewServeMux()
	registerRoutes(mux)
	port := os.Getenv("PORT")
	if port == "" {
		port = "3000"
	}
	log.Fatal(http.ListenAndServe("127.0.0.1:"+port, mux))
}
"""


def _go_handlers(name: str, request: str) -> str:
    return f"""package main

import (
	"encoding/json"
	"net/http"
)

func registerRoutes(mux *http.ServeMux) {{
	mux.HandleFunc("/health", healthHandler)
	mux.HandleFunc("/api/brief", briefHandler)
}}

func healthPayload() map[string]string {{
	return map[string]string{{"status": "ok", "service": "{name}"}}
}}

func healthHandler(w http.ResponseWriter, r *http.Request) {{
	writeJSON(w, healthPayload())
}}

func briefHandler(w http.ResponseWriter, r *http.Request) {{
	writeJSON(w, BriefPayload{{
		Product: "{name}",
		Request: {_json_value(request)},
		NextActions: []string{{"triage queue", "assign owner", "send status update"}},
		Risks: []string{{"No external AI provider is configured yet", "Outbound actions should remain approval-gated"}},
	}})
}}

func writeJSON(w http.ResponseWriter, value any) {{
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(value)
}}
"""


def _go_models() -> str:
    return """package main

type BriefPayload struct {
	Product     string   `json:"product"`
	Request     string   `json:"request"`
	NextActions []string `json:"nextActions"`
	Risks       []string `json:"risks"`
}
"""


def _rust_main(name: str, request: str) -> str:
    return """mod models;
mod routes;

use std::net::SocketAddr;

#[tokio::main]
async fn main() {
    let app = routes::router();
    let addr: SocketAddr = "127.0.0.1:3000".parse().unwrap();
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
"""


def _rust_models() -> str:
    return """use serde::Serialize;

#[derive(Serialize)]
pub struct BriefPayload {
    pub product: &'static str,
    pub request: &'static str,
    #[serde(rename = "nextActions")]
    pub next_actions: [&'static str; 3],
    pub risks: [&'static str; 2],
}
"""


def _rust_routes(name: str, request: str) -> str:
    return f"""use axum::{{routing::get, Json, Router}};
use serde_json::json;

use crate::models::BriefPayload;

pub fn router() -> Router {{
    Router::new()
        .route("/health", get(health))
        .route("/api/brief", get(brief))
}}

async fn health() -> Json<serde_json::Value> {{
    Json(json!({{"status": "ok", "service": {_rust_string(name)}}}))
}}

async fn brief() -> Json<BriefPayload> {{
    Json(BriefPayload {{
        product: {_rust_string(name)},
        request: {_rust_string(request)},
        next_actions: ["triage queue", "assign owner", "send status update"],
        risks: ["No external AI provider is configured yet", "Outbound actions should remain approval-gated"],
    }})
}}
"""


def _product_readme(name: str, request: str, stack: str, run: str) -> str:
    return f"""# {name}

Generated by Friday autonomous coding.

## Stack

{stack}

## Request

{_clean(request)}

## Run

```bash
{run}
```

## Product Notes

- Core flow: capture work, generate AI briefs, route next actions, and report proof.
- Target users: individuals, small teams, agencies, operators, and SMBs.
- External posting, payments, deploys, and outbound messages should stay approval-gated.
- Code is split by responsibility so routes/screens, state, domain logic, validation, persistence, and tests do not live in one blob.
"""


def _keywords(value: str) -> list[str]:
    stop = {
        "about", "after", "also", "and", "any", "app", "apps", "application", "backend", "build", "can",
        "create", "dashboard", "everyday", "for", "from", "flutter", "frontend", "generate", "hackathon",
        "into", "make", "mobile", "next", "nextjs", "project", "prototype", "server", "should", "small",
        "system", "that", "the", "this", "tool", "using", "want", "web", "webapp", "website", "with",
    }
    return [word for word in _words(value) if len(word) > 2 and word not in stop][:8]


def _words(value: str) -> list[str]:
    return [part for part in re.split(r"[^a-z0-9.]+", str(value or "").lower()) if part]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-") or "friday-app"


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True, default=str) + "\n"


def _json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, default=str)


def _rust_string(value: Any) -> str:
    return json.dumps(str(value or ""), ensure_ascii=False)

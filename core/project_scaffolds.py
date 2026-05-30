"""Stack-aware starter project scaffolds for autonomous coding."""

from __future__ import annotations

import json
import re
from typing import Any


def detect_stack(request: str) -> dict[str, str]:
    text = str(request or "").lower()
    words = set(_words(text))
    if "flutter" in words or "mobile" in words or "android" in words or "ios" in words:
        return {"kind": "mobile", "stack": "flutter", "language": "dart", "label": "Flutter mobile app"}
    if "nextjs" in words or "next.js" in text or "next" in words or "web-app" in text or "web app" in text:
        return {"kind": "web_app", "stack": "nextjs", "language": "typescript", "label": "Next.js web app"}
    if any(word in words for word in {"backend", "api", "server", "service", "microservice"}):
        if "rust" in words or "axum" in words:
            return {"kind": "backend", "stack": "rust_axum", "language": "rust", "label": "Rust Axum backend"}
        if "go" in words or "golang" in words or "gin" in words:
            return {"kind": "backend", "stack": "go_api", "language": "go", "label": "Go HTTP backend"}
        if "python" in words or "fastapi" in words or "flask" in words or "django" in words:
            return {"kind": "backend", "stack": "python_fastapi", "language": "python", "label": "Python FastAPI backend"}
        return {"kind": "backend", "stack": "node_fastify", "language": "javascript", "label": "Node.js Fastify backend"}
    if "website" in words or "frontend" in words or "dashboard" in words or "portal" in words or "site" in words:
        return {"kind": "web_app", "stack": "nextjs", "language": "typescript", "label": "Next.js web app"}
    return {"kind": "web_app", "stack": "nextjs", "language": "typescript", "label": "Next.js web app"}


def product_name(request: str) -> str:
    text = str(request or "").lower()
    if "hackonvibe" in text or "hack on vibe" in text:
        return "VibeOps"
    words = [word.capitalize() for word in _keywords(request)[:2]]
    return "".join(words) + "Pilot" if words else "FlowPilot"


def project_slug(request: str, stack: dict[str, str] | None = None) -> str:
    text = str(request or "").lower()
    if "hackonvibe" in text or "hack on vibe" in text:
        return "vibeops-hackathon-mvp"
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
    return {
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
                    "@tanstack/react-query": "latest",
                    "axios": "latest",
                    "class-variance-authority": "latest",
                    "clsx": "latest",
                    "lucide-react": "latest",
                    "next": "latest",
                    "react": "latest",
                    "react-dom": "latest",
                    "tailwind-merge": "latest",
                    "zustand": "latest",
                },
                "devDependencies": {
                    "@eslint/eslintrc": "latest",
                    "@tailwindcss/postcss": "latest",
                    "@testing-library/jest-dom": "latest",
                    "@testing-library/react": "latest",
                    "@testing-library/user-event": "latest",
                    "@types/node": "latest",
                    "@types/react": "latest",
                    "@types/react-dom": "latest",
                    "@vitejs/plugin-react": "latest",
                    "eslint": "latest",
                    "eslint-config-next": "latest",
                    "jsdom": "latest",
                    "tailwindcss": "latest",
                    "typescript": "latest",
                    "vitest": "latest",
                },
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
        "eslint.config.mjs": "import { dirname } from 'node:path';\nimport { fileURLToPath } from 'node:url';\nimport { FlatCompat } from '@eslint/eslintrc';\n\nconst __filename = fileURLToPath(import.meta.url);\nconst __dirname = dirname(__filename);\nconst compat = new FlatCompat({ baseDirectory: __dirname });\n\nconst eslintConfig = [...compat.extends('next/core-web-vitals', 'next/typescript')];\n\nexport default eslintConfig;\n",
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
        "proxy.ts": "import type { NextRequest } from 'next/server';\nimport { NextResponse } from 'next/server';\n\nexport function proxy(request: NextRequest) {\n  const response = NextResponse.next();\n  response.headers.set('x-friday-project', 'production-ready-nextjs');\n  return response;\n}\n\nexport const config = {\n  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],\n};\n",
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
                "dependencies": {"@fastify/cors": "latest", "fastify": "latest"},
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


def _next_product_plan(name: str, request: str) -> str:
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
  sampleNote: string;
  workItems: WorkItem[];
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
  sampleNote: 'Customer asked for status, invoice is pending, designer is blocked on brand assets.',
  workItems: [
    {{
      id: 'capture-recurring-work',
      title: 'Capture recurring work',
      detail: 'Turn messy daily requests into a structured queue with owner, risk, and next action.',
      owner: 'Operator',
      status: 'Captured',
      priority: 'high',
    }},
    {{
      id: 'ai-action-brief',
      title: 'AI action brief',
      detail: 'Summarize context, blockers, suggested reply, and one decision the team needs.',
      owner: 'Friday',
      status: 'AI Brief',
      priority: 'high',
    }},
    {{
      id: 'team-handoff',
      title: 'Team handoff',
      detail: 'Prepare a customer-ready update and a private internal handoff.',
      owner: 'Team lead',
      status: 'Ready',
      priority: 'medium',
    }},
  ],
  targetUsers: ['solo makers', 'small teams', 'service businesses', 'agencies', 'SMB operators'],
  integrations: ['Gmail', 'Google Calendar', 'Slack', 'Notion', 'CSV import/export'],
  pricing: ['Free personal workspace', '$12/month Pro', '$39/month Team'],
  launchPlan: ['Confirm acceptance criteria', 'Ship technical preview', 'Collect first users', 'Approve launch assets', 'Open public release'],
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

import { Bot, ClipboardList, PlugZap, Users } from 'lucide-react';
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
    () => [
      { label: 'tasks triaged', value: items.length + 9 },
      { label: 'handoffs drafted', value: 4 + reviewed },
      { label: 'minutes saved', value: 31 + reviewed * 4 },
    ],
    [items.length, reviewed],
  );

  return (
    <section className="workspace" id="workspace">
      <header className="workspace-header">
        <div>
          <Badge>AI everyday tool</Badge>
          <h1>{plan.name}</h1>
          <p>{plan.request}</p>
        </div>
        <Button type="button" onClick={() => draftBrief(note, items)} disabled={loading}>
          <Bot size={18} /> {loading ? 'Drafting...' : 'Generate daily brief'}
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
          <h2><ClipboardList size={18} /> AI Decision Brief</h2>
          <Textarea value={note} onChange={(event) => setNote(event.target.value)} aria-label="Source note" />
          <Button type="button" onClick={() => draftBrief(note, items)} disabled={loading}>
            <Sparkles size={16} /> Draft brief
          </Button>
          {error ? <p className="error-copy">{error}</p> : null}
          <p className="brief">{brief ? `${brief.summary} ${brief.nextAction} ${brief.risks}` : 'Generate a brief to see the AI workflow.'}</p>
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
  return (
    <Card className="work-card">
      <Badge>{item.status}</Badge>
      <h2>{item.title}</h2>
      <p>{item.detail}</p>
      <small>{item.owner} / {item.priority} priority</small>
      <Button type="button" variant="secondary" onClick={onReview}><CheckCircle2 size={16} /> Mark reviewed</Button>
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

const pillars = [
  { icon: ShieldCheck, title: 'Safe by default', detail: 'Approvals gate deploys, billing, outbound messages, and ads.' },
  { icon: Zap, title: 'Fast to operate', detail: 'Daily work is reduced into owners, next actions, and proof.' },
  { icon: CheckCircle2, title: 'Ready for verification', detail: 'Every release path includes tests, scans, browser checks, and preview evidence.' },
];

export function HomePage() {
  return (
    <main className="landing-shell">
      <section className="landing-hero">
        <div className="hero-copy">
          <Badge>AI-assisted workflow studio</Badge>
          <h1>{productPlan.name}</h1>
          <p>{productPlan.request}</p>
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
          <h2>Launch signal</h2>
          <p>{productPlan.launchPlan.join(' / ')}</p>
        </Card>
      </section>

      <section className="pillar-grid" aria-label="Product priorities">
        {pillars.map((pillar) => (
          <Card key={pillar.title}>
            <pillar.icon size={20} />
            <h2>{pillar.title}</h2>
            <p>{pillar.detail}</p>
          </Card>
        ))}
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

import { useCallback, useEffect, useState } from 'react';
import { clearAccessToken, readAccessToken, writeAccessToken } from '@/lib/authTokens';

export function useAccessToken() {
  const [token, setCurrentToken] = useState('');

  useEffect(() => {
    setCurrentToken(readAccessToken());
  }, []);

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
h1 { font-size: clamp(2.4rem, 6vw, 5rem); line-height: .95; margin-bottom: 16px; }
h2 { font-size: 1.05rem; }

.landing-shell, .workspace, .policy-page, .error-state { width: min(1180px, calc(100% - 32px)); margin: 0 auto; }
.landing-hero { min-height: 72vh; display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(280px, .7fr); align-items: center; gap: 24px; padding: 56px 0 28px; }
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
        "about", "application", "backend", "build", "create", "dashboard", "everyday", "flutter", "frontend",
        "generate", "hackathon", "mobile", "nextjs", "project", "prototype", "server", "should", "small",
        "system", "that", "this", "tool", "want", "web", "webapp", "website", "with",
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

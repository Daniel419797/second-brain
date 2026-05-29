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
        return _flutter_files(name, request)
    if stack_id == "node_fastify":
        return _fastify_files(name, request)
    if stack_id == "python_fastapi":
        return _fastapi_files(name, request)
    if stack_id == "go_api":
        return _go_files(name, request)
    if stack_id == "rust_axum":
        return _rust_files(name, request)
    return _nextjs_files(name, request)


def _nextjs_files(name: str, request: str) -> dict[str, str]:
    slug = _slug(name)
    return {
        "package.json": _json(
            {
                "name": slug,
                "private": True,
                "version": "0.1.0",
                "scripts": {"dev": "next dev", "build": "next build", "start": "next start", "lint": "next lint"},
                "dependencies": {"next": "latest", "react": "latest", "react-dom": "latest", "lucide-react": "latest"},
                "devDependencies": {"typescript": "latest", "@types/node": "latest", "@types/react": "latest", "@types/react-dom": "latest"},
            }
        ),
        "tsconfig.json": _json(
            {
                "compilerOptions": {
                    "target": "es5",
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
                    "jsx": "preserve",
                    "incremental": True,
                    "plugins": [{"name": "next"}],
                    "paths": {"@/*": ["./src/*"]},
                },
                "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
                "exclude": ["node_modules"],
            }
        ),
        "next-env.d.ts": "/// <reference types=\"next\" />\n/// <reference types=\"next/image-types/global\" />\n\n",
        "next.config.mjs": "/** @type {import('next').NextConfig} */\nconst nextConfig = {};\n\nexport default nextConfig;\n",
        "src/app/layout.tsx": f"import './globals.css';\n\nexport const metadata = {{ title: '{name}', description: 'AI-assisted everyday workflow tool' }};\n\nexport default function RootLayout({{ children }}: {{ children: React.ReactNode }}) {{\n  return <html lang=\"en\"><body>{{children}}</body></html>;\n}}\n",
        "src/app/page.tsx": _next_page(name, request),
        "src/app/globals.css": _next_css(),
        "README.md": _product_readme(name, request, "Next.js web app", "npm install\nnpm run dev"),
        ".gitignore": "node_modules\n.next\nout\n.env\n.env.local\n.DS_Store\n",
    }


def _flutter_files(name: str, request: str) -> dict[str, str]:
    package = _slug(name).replace("-", "_")
    return {
        "pubspec.yaml": f"name: {package}\ndescription: AI-assisted mobile workflow app generated by Friday.\npublish_to: 'none'\nversion: 0.1.0+1\nenvironment:\n  sdk: '>=3.4.0 <4.0.0'\ndependencies:\n  flutter:\n    sdk: flutter\n  cupertino_icons: ^1.0.8\ndev_dependencies:\n  flutter_test:\n    sdk: flutter\n  flutter_lints: ^4.0.0\nflutter:\n  uses-material-design: true\n",
        "lib/main.dart": _flutter_main(name, request),
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
        "src/server.js": _fastify_server(name, request),
        "test/health.test.js": "import test from 'node:test';\nimport assert from 'node:assert/strict';\nimport { buildApp } from '../src/server.js';\n\ntest('health endpoint responds', async () => {\n  const app = buildApp();\n  const response = await app.inject({ method: 'GET', url: '/health' });\n  assert.equal(response.statusCode, 200);\n});\n",
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
        "main_test.go": "package main\n\nimport \"testing\"\n\nfunc TestHealthPayload(t *testing.T) {\n\tpayload := healthPayload()\n\tif payload[\"status\"] != \"ok\" {\n\t\tt.Fatalf(\"expected ok status\")\n\t}\n}\n",
        "README.md": _product_readme(name, request, "Go HTTP backend", "go test ./...\ngo run ."),
        ".gitignore": ".env\nbin\n",
    }


def _rust_files(name: str, request: str) -> dict[str, str]:
    package = _slug(name).replace("-", "_")
    return {
        "Cargo.toml": f"[package]\nname = \"{package}\"\nversion = \"0.1.0\"\nedition = \"2021\"\n\n[dependencies]\naxum = \"0.7\"\ntokio = {{ version = \"1\", features = [\"macros\", \"rt-multi-thread\"] }}\nserde = {{ version = \"1\", features = [\"derive\"] }}\nserde_json = \"1\"\n",
        "src/main.rs": _rust_main(name, request),
        "README.md": _product_readme(name, request, "Rust Axum backend", "cargo run\ncargo test"),
        ".gitignore": "target\n.env\n",
    }


def _next_page(name: str, request: str) -> str:
    return f"""'use client';

import {{ Bot, CheckCircle2, ClipboardList, Sparkles, Users }} from 'lucide-react';
import {{ useState }} from 'react';

const initialItems = [
  {{ title: 'Capture recurring work', detail: 'Turn messy daily requests into a structured queue.', status: 'Live' }},
  {{ title: 'AI action brief', detail: 'Summarize context, risks, owners, and suggested next steps.', status: 'AI' }},
  {{ title: 'Team handoff', detail: 'Share decisions, blockers, and customer-ready updates.', status: 'Ready' }},
];

export default function Home() {{
  const [items, setItems] = useState(initialItems);
  const [note, setNote] = useState('Customer asked for status, invoice is pending, designer is blocked on brand assets.');
  const [brief, setBrief] = useState('Generate a brief to see the AI workflow.');
  const reviewed = items.filter((item) => item.status === 'Reviewed').length;

  return (
    <main className=\"shell\">
      <aside>
        <strong><Sparkles size={{18}} /> {name}</strong>
        <a href=\"#workspace\">Workspace</a>
        <a href=\"#assistant\">AI Assist</a>
        <a href=\"#market\">Market</a>
      </aside>
      <section className=\"workspace\" id=\"workspace\">
        <header>
          <p className=\"eyebrow\">AI everyday tool</p>
          <h1>{name}</h1>
          <p>{_clean(request)}</p>
          <button type=\"button\" onClick={{() => setBrief('Today: triage the queue, unblock one owner, send one customer-ready update, and validate with a real user.')}}><Bot size={{18}} /> Generate daily brief</button>
        </header>
        <section className=\"metrics\">
          <article><b>{{items.length + 9}}</b><span>tasks triaged</span></article>
          <article><b>{{4 + reviewed}}</b><span>handoffs drafted</span></article>
          <article><b>{{31 + reviewed * 4}}m</b><span>saved today</span></article>
        </section>
        <section className=\"board\">
          {{items.map((item) => (
            <article key={{item.title}}>
              <span>{{item.status}}</span>
              <h2>{{item.title}}</h2>
              <p>{{item.detail}}</p>
              <button type=\"button\" onClick={{() => setItems((rows) => rows.map((row) => row.title === item.title ? {{ ...row, status: 'Reviewed' }} : row))}}><CheckCircle2 size={{16}} /> Mark reviewed</button>
            </article>
          ))}}
        </section>
        <section className=\"assistant\" id=\"assistant\">
          <article>
            <h2><ClipboardList size={{18}} /> AI Decision Brief</h2>
            <textarea value={{note}} onChange={{(event) => setNote(event.target.value)}} />
            <button type=\"button\" onClick={{() => setBrief(`Summary: ${{note}} Next action: assign an owner, clear the blocker, and send a concise status update.`)}}><Sparkles size={{16}} /> Draft brief</button>
            <p className=\"brief\">{{brief}}</p>
          </article>
          <article id=\"market\">
            <h2><Users size={{18}} /> Target Users</h2>
            <p>Solo makers, small teams, service businesses, agencies, and operators who repeat coordination work every day.</p>
          </article>
        </section>
      </section>
    </main>
  );
}}
"""


def _next_css() -> str:
    return """* { box-sizing: border-box; }
body { margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif; color: #1d2730; background: #f6f7f2; }
button, textarea { font: inherit; }
button { display: inline-flex; align-items: center; gap: 8px; border: 1px solid #18222b; background: #18222b; color: white; border-radius: 8px; padding: 10px 14px; cursor: pointer; }
.shell { display: grid; grid-template-columns: 240px 1fr; min-height: 100vh; }
aside { display: grid; align-content: start; gap: 12px; background: #18222b; color: white; padding: 24px; }
aside strong { display: flex; align-items: center; gap: 10px; margin-bottom: 18px; }
aside a { color: #d6ece5; text-decoration: none; padding: 8px 0; }
.workspace { padding: 32px; }
header { display: grid; justify-items: start; gap: 12px; margin-bottom: 24px; }
.eyebrow { color: #2b7a78; font-size: .78rem; font-weight: 800; text-transform: uppercase; margin: 0; }
h1 { font-size: clamp(2rem, 6vw, 4.2rem); line-height: 1; margin: 0; }
h2, p { margin-top: 0; }
header p:not(.eyebrow) { max-width: 760px; color: #46535f; line-height: 1.6; }
.metrics, .board, .assistant { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin-bottom: 20px; }
.metrics article, .board article, .assistant article { background: white; border: 1px solid #dde2da; border-radius: 8px; padding: 18px; }
.metrics b { display: block; font-size: 2rem; }
.metrics span, .board p, .assistant p { color: #59656f; }
.board span { color: #2b7a78; font-size: .78rem; font-weight: 800; }
.board button { background: white; color: #18222b; }
.assistant article:first-child { grid-column: span 2; }
textarea { width: 100%; min-height: 120px; border: 1px solid #c8d0c8; border-radius: 8px; padding: 12px; margin-bottom: 12px; }
.brief { border-left: 3px solid #2b7a78; padding-left: 12px; margin-top: 14px; }
@media (max-width: 840px) { .shell, .metrics, .board, .assistant { grid-template-columns: 1fr; } .assistant article:first-child { grid-column: auto; } }
"""


def _flutter_main(name: str, request: str) -> str:
    return f"""import 'package:flutter/material.dart';

void main() => runApp(const FridayApp());

class FridayApp extends StatelessWidget {{
  const FridayApp({{super.key}});

  @override
  Widget build(BuildContext context) {{
    return MaterialApp(
      title: '{name}',
      theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF2B7A78)), useMaterial3: true),
      home: const HomeScreen(),
    );
  }}
}}

class HomeScreen extends StatefulWidget {{
  const HomeScreen({{super.key}});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}}

class _HomeScreenState extends State<HomeScreen> {{
  int reviewed = 0;
  String brief = 'Generate a brief to see the AI workflow.';

  @override
  Widget build(BuildContext context) {{
    final cards = ['Capture recurring work', 'AI action brief', 'Team handoff'];
    return Scaffold(
      appBar: AppBar(title: const Text('{name}')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text('{_clean(request)}', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 20),
          FilledButton.icon(onPressed: () => setState(() => brief = 'Today: triage, unblock one owner, and validate with one real user.'), icon: const Icon(Icons.auto_awesome), label: const Text('Generate daily brief')),
          const SizedBox(height: 16),
          Text(brief),
          const SizedBox(height: 20),
          Wrap(spacing: 12, runSpacing: 12, children: cards.map((title) => Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(title, style: Theme.of(context).textTheme.titleLarge), const Text('Review this workflow item and move it forward.'), TextButton(onPressed: () => setState(() => reviewed++), child: const Text('Mark reviewed'))])))).toList()),
          const SizedBox(height: 20),
          Text('Reviewed: $reviewed'),
        ],
      ),
    );
  }}
}}
"""


def _fastify_server(name: str, request: str) -> str:
    return f"""import Fastify from 'fastify';
import cors from '@fastify/cors';

export function buildApp() {{
  const app = Fastify({{ logger: true }});
  app.register(cors, {{ origin: true }});

  app.get('/health', async () => ({{ status: 'ok', service: '{name}' }}));
  app.get('/api/brief', async () => ({{
    product: '{name}',
    request: {_json_value(request)},
    nextActions: ['triage queue', 'assign owner', 'send status update'],
  }}));
  app.post('/api/work-items', async (request, reply) => {{
    return reply.code(201).send({{ id: Date.now(), ...request.body, status: 'captured' }});
  }});

  return app;
}}

if (import.meta.url === `file://${{process.argv[1]}}`) {{
  const app = buildApp();
  const port = Number(process.env.PORT || 3000);
  app.listen({{ port, host: '127.0.0.1' }});
}}
"""


def _fastapi_main(name: str, request: str) -> str:
    return f"""from pydantic import BaseModel
from fastapi import FastAPI

app = FastAPI(title={_json_value(name)})


class WorkItem(BaseModel):
    title: str
    owner: str = ""
    priority: str = "normal"


@app.get("/health")
def health() -> dict[str, str]:
    return {{"status": "ok", "service": {_json_value(name)}}}


@app.get("/api/brief")
def brief() -> dict[str, object]:
    return {{
        "product": {_json_value(name)},
        "request": {_json_value(request)},
        "next_actions": ["triage queue", "assign owner", "send status update"],
    }}


@app.post("/api/work-items", status_code=201)
def create_work_item(item: WorkItem) -> dict[str, object]:
    return {{"status": "captured", "item": item.model_dump()}}
"""


def _go_main(name: str, request: str) -> str:
    return f"""package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
)

func healthPayload() map[string]string {{
	return map[string]string{{"status": "ok", "service": "{name}"}}
}}

func main() {{
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {{
		writeJSON(w, healthPayload())
	}})
	mux.HandleFunc("/api/brief", func(w http.ResponseWriter, r *http.Request) {{
		writeJSON(w, map[string]any{{"product": "{name}", "request": {_json_value(request)}, "nextActions": []string{{"triage queue", "assign owner", "send status update"}}}})
	}})
	port := os.Getenv("PORT")
	if port == "" {{
		port = "3000"
	}}
	log.Fatal(http.ListenAndServe("127.0.0.1:"+port, mux))
}}

func writeJSON(w http.ResponseWriter, value any) {{
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(value)
}}
"""


def _rust_main(name: str, request: str) -> str:
    return f"""use axum::{{routing::get, Json, Router}};
use serde_json::json;
use std::net::SocketAddr;

#[tokio::main]
async fn main() {{
    let app = Router::new()
        .route("/health", get(health))
        .route("/api/brief", get(brief));
    let addr: SocketAddr = "127.0.0.1:3000".parse().unwrap();
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}}

async fn health() -> Json<serde_json::Value> {{
    Json(json!({{"status": "ok", "service": "{name}"}}))
}}

async fn brief() -> Json<serde_json::Value> {{
    Json(json!({{"product": "{name}", "request": {_json_value(request)}, "nextActions": ["triage queue", "assign owner", "send status update"]}}))
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

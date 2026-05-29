"""Guarded autonomous coding mode with real implementation handoffs."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from core import codebase_standards, llm, production_coding_autonomy, project_memory, project_scaffolds, self_update, task_contracts, task_queue, trust_proof
from core.config import ROOT_DIR, config_value, resolve_coding_root

SKIP_PARTS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".next", "dist", "build", "data"}
TEXT_EXTENSIONS = {
    ".bat", ".c", ".clj", ".cljs", ".cpp", ".cs", ".css", ".csv", ".dart", ".erl", ".ex", ".exs", ".fs", ".go",
    ".graphql", ".h", ".hpp", ".html", ".ini", ".java", ".js", ".json", ".jsx", ".kt", ".kts", ".lua", ".m",
    ".md", ".mm", ".php", ".proto", ".ps1", ".py", ".r", ".rb", ".rs", ".scala", ".sh", ".sql", ".swift",
    ".toml", ".ts", ".tsx", ".txt", ".yaml", ".yml",
}


def start(request: str, *, root: str = "", risk_level: str = "medium") -> dict[str, Any]:
    """Create and kick off a safe coding task with an explicit contract.

    Local project scaffolds can be written immediately under the coding root.
    Friday's own codebase still goes through self-update approval and staged
    replacements before any patch is applied.
    """

    project_root = _task_project_root(root)
    standards = codebase_standards.scan(project_root, max_files=120)
    cleaned_request = _clean(request) or "project improvement"
    execution_kind = _execution_kind(cleaned_request, project_root)
    title = f"Autonomous coding: {cleaned_request[:120]}"
    task_id = task_queue.create_task(
        title,
        description="Guarded autonomous coding request.",
        agent_id="senior_developer",
        priority=3,
        input_data={
            "source": "autonomous_coding",
            "request": request,
            "root": str(project_root),
            "risk_level": risk_level,
            "execution_kind": execution_kind,
            "quality_priorities": ["security", "speed_performance", "maintainability", "reliability", "portability"],
            "standards": standards,
            "required_flow": [
                "inspect",
                "standards_preflight",
                "prepare_or_stage_change_set",
                "discover_tests",
                "explain",
                "approval_gate_if_needed",
                "apply_or_rollback",
            ],
        },
    )
    task = task_queue.get_task(task_id) or {"id": task_id, "title": title, "input": {}}
    contract = task_contracts.ensure_contract(task)
    execution = run_task(task)
    task_status = str(execution.get("task_status") or "done")
    if task_status == "blocked":
        task_queue.update_status(task_id, "blocked", output=execution)
    elif task_status == "pending":
        task_queue.update_status(task_id, "pending", output=execution)
    else:
        contract = task_contracts.verify_contract(task, execution)
        task_queue.complete_task(task_id, execution)
    task = task_queue.get_task(task_id) or task
    return {
        "ok": True,
        "task": task,
        "contract": contract,
        "execution": execution,
        "summary": execution.get("voice_summary")
        or f"Autonomous coding task #{task_id} kicked off with a verification contract.",
    }


def should_handle_task(task: dict[str, Any]) -> bool:
    input_data = task.get("input") if isinstance(task.get("input"), dict) else {}
    return str(input_data.get("source") or "") in {"autonomous_coding", "self_update"}


def run_task(task: dict[str, Any]) -> dict[str, Any]:
    input_data = task.get("input") if isinstance(task.get("input"), dict) else {}
    source = str(input_data.get("source") or "")
    if source == "self_update":
        return prepare_self_update_task(task)

    request = _clean(input_data.get("request") or task.get("description") or task.get("title") or "")
    project_root = _task_project_root(input_data.get("root") or "")
    risk_level = str(input_data.get("risk_level") or "medium")
    task_id = int(task.get("id") or 0)
    _post(task_id, "autonomous_coding", "Progress 35%: project inspected and coding executor selected.")
    if _looks_like_new_app_request(request, project_root):
        return _scaffold_new_app(project_root, request, task_id=task_id, risk_level=risk_level)
    if _is_friday_root(project_root):
        return _open_self_update_proposal(request, task_id=task_id, risk_level=risk_level)
    return _prepare_existing_project(project_root, request, task_id=task_id, risk_level=risk_level)


def prepare_self_update_task(task: dict[str, Any]) -> dict[str, Any]:
    input_data = task.get("input") if isinstance(task.get("input"), dict) else {}
    update_id = _int(input_data.get("update_id"), 0)
    task_id = int(task.get("id") or 0)
    update = self_update.get_update(update_id) if update_id else None
    if not update:
        return _result(
            task_id,
            "failed",
            "Self-update request was missing or no longer exists.",
            next_step="Create a fresh self-update proposal.",
            risks=["No code was staged."],
            failed=["Self-update record not found."],
        )
    if update.get("status") != "approved":
        return _result(
            task_id,
            "blocked",
            f"Self-update #{update_id} is {update.get('status')}, not approved.",
            next_step=f"Approve it with: {update.get('approval_phrase')}",
            risks=["No changes are staged until planning is approved."],
        )
    existing = [change for change in update.get("changes") or [] if change.get("status") == "staged"]
    if existing:
        return _result(
            task_id,
            "done",
            f"Self-update #{update_id} already has {len(existing)} staged change(s).",
            next_step=f"Review the staged changes, then apply with: I authorize applying self update {update_id}.",
            risks=["Applying still modifies files and should run tests."],
            changed=[f"Staged: {change.get('path')}" for change in existing],
            metadata={"self_update_id": update_id, "staged_changes": existing},
        )

    _post(task_id, "autonomous_coding", "Progress 55%: generating exact self-update replacements.")
    prepared = _generate_self_update_changes(update, task_id=task_id)
    staged = prepared.get("staged_changes") or []
    errors = prepared.get("errors") or []
    if staged:
        return _result(
            task_id,
            "done",
            f"Prepared {len(staged)} staged change(s) for self-update #{update_id}.",
            next_step=f"Review the staged changes, then apply with: I authorize applying self update {update_id}.",
            risks=["Generated patches can still be wrong; apply_update will back up files and run configured tests."],
            changed=[f"Staged: {change.get('path')}" for change in staged],
            failed=errors,
            metadata={"self_update_id": update_id, **prepared},
        )
    return _result(
        task_id,
        "done",
        f"Self-update #{update_id} was approved, but no exact change set could be staged automatically.",
        next_step="Stage changes manually or ask Friday for a narrower coding request.",
        risks=["No files were changed; LLM output was missing, invalid, or unsafe."],
        failed=errors or ["No staged changes generated."],
        metadata={"self_update_id": update_id, **prepared},
    )


def _scaffold_new_app(base_root: Path, request: str, *, task_id: int, risk_level: str) -> dict[str, Any]:
    stack = project_scaffolds.detect_stack(request)
    target = _target_project_root(base_root, request, stack=stack)
    target.mkdir(parents=True, exist_ok=True)
    product_name = project_scaffolds.product_name(request)
    files = project_scaffolds.files_for_stack(stack, product_name, request)
    written: list[str] = []
    for relative, content in files.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(str(path))
    scaffold_verification = _verify_scaffold(target, stack, written)
    prep = production_coding_autonomy.prepare_project(target, request=request, create_files=True, run_scans=True)
    note = project_memory.remember(
        target,
        "autonomous_coding_scaffold",
        f"Created {product_name} starter app",
        f"Request: {request}",
        confidence=0.82,
        metadata={"task_id": task_id, "files": written, "production_prep": prep.get("artifacts", [])},
    )
    proof = trust_proof.create_report(
        f"Autonomous coding scaffold for {product_name}",
        task_id=task_id or None,
        changed=[f"Created {len(written)} {stack.get('label')} starter file(s) under {target}.", *[f"Created guard artifact: {item}" for item in prep.get("artifacts") or []]],
        tested=scaffold_verification["checks"] + (prep.get("test_commands") or []),
        evidence=[scaffold_verification["summary"], prep.get("summary", "Production prep completed.")],
        risks=["Dependencies are not installed until npm install is run.", "AI integrations are represented as UI/product flow stubs until provider credentials are configured."],
        confidence=0.78,
        metadata={"source": "autonomous_coding", "root": str(target), "risk_level": risk_level, "scaffold_verification": scaffold_verification},
    )
    _post(task_id, "autonomous_coding", f"Progress 90%: starter app written to {target}.")
    return _result(
        task_id,
        "done" if scaffold_verification["status"] == "passed" else "failed",
        f"Created and file-verified a runnable {stack.get('label')} for {product_name} at {target}." if scaffold_verification["status"] == "passed" else f"Created scaffold for {product_name}, but file verification failed at {target}.",
        next_step=f"Open {target}, install dependencies for {stack.get('label')}, then run the README command.",
        risks=["No dependency install or browser verification has run yet.", "Generated business assumptions should be reviewed before demo submission."],
        changed=[*written, *(prep.get("artifacts") or [])],
        tested=scaffold_verification["checks"] + (prep.get("test_commands") or []),
        failed=scaffold_verification["missing"],
        metadata={"project_root": str(target), "project_name": product_name, "stack": stack, "production_prep": prep, "memory": note, "proof": proof, "scaffold_verification": scaffold_verification},
    )


def _open_self_update_proposal(request: str, *, task_id: int, risk_level: str) -> dict[str, Any]:
    proposal = self_update.create_proposal(request)
    _post(task_id, "autonomous_coding", f"Self-update proposal #{proposal.get('id')} opened. Approval phrase: {proposal.get('approval_phrase')}")
    proof = trust_proof.create_report(
        f"Autonomous coding proposal #{proposal.get('id')}",
        task_id=task_id or None,
        changed=["No files changed yet; self-update proposal created."],
        tested=["Tests will run when staged changes are applied."],
        evidence=[f"Self-update proposal #{proposal.get('id')} is {proposal.get('status')}."],
        risks=["Friday codebase changes require approval before staging/applying."],
        confidence=0.72,
        metadata={"source": "autonomous_coding", "self_update_id": proposal.get("id"), "risk_level": risk_level},
    )
    return _result(
        task_id,
        "blocked",
        f"Opened self-update proposal #{proposal.get('id')} for Friday's codebase.",
        next_step=f"Approve planning with: {proposal.get('approval_phrase')}. After that the coding executor will stage exact replacements.",
        risks=["No Friday source files were changed yet.", "Applying staged changes still needs a second approval phrase."],
        changed=["Created self-update proposal."],
        metadata={"self_update": proposal, "proof": proof},
    )


def _prepare_existing_project(project_root: Path, request: str, *, task_id: int, risk_level: str) -> dict[str, Any]:
    prep = production_coding_autonomy.prepare_project(project_root, request=request, create_files=True, run_scans=True)
    plan_path = project_root / ".friday" / "implementation-plan.md"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan = _implementation_plan(project_root, request, prep)
    plan_path.write_text(plan, encoding="utf-8")
    note = project_memory.remember(
        project_root,
        "autonomous_coding_plan",
        "Prepared implementation plan",
        request,
        confidence=0.76,
        metadata={"task_id": task_id, "plan_path": str(plan_path), "production_prep": prep.get("artifacts", [])},
    )
    proof = trust_proof.create_report(
        f"Autonomous coding prep for {project_root.name}",
        task_id=task_id or None,
        changed=[f"Wrote implementation plan: {plan_path}", *[f"Created guard artifact: {item}" for item in prep.get("artifacts") or []]],
        tested=prep.get("test_commands") or ["No test commands discovered yet."],
        evidence=[prep.get("summary", "Production coding prep completed.")],
        risks=["Existing project source files were not patched automatically because no project-specific approval/apply workflow exists for this root."],
        confidence=0.74,
        metadata={"source": "autonomous_coding", "root": str(project_root), "risk_level": risk_level},
    )
    return _result(
        task_id,
        "done",
        f"Prepared coding workspace for {project_root.name} and wrote an implementation plan.",
        next_step=f"Review {plan_path}, then approve a concrete patch request or run the discovered checks.",
        risks=["No existing app source files were changed by this prep step.", "Manual review is still needed before modifying an existing project."],
        changed=[str(plan_path), *(prep.get("artifacts") or [])],
        tested=prep.get("test_commands") or [],
        metadata={"project_root": str(project_root), "plan_path": str(plan_path), "production_prep": prep, "memory": note, "proof": proof},
    )


def _generate_self_update_changes(update: dict[str, Any], *, task_id: int) -> dict[str, Any]:
    plan = update.get("plan") if isinstance(update.get("plan"), dict) else {}
    root = Path(getattr(self_update, "ROOT_DIR", ROOT_DIR)).resolve()
    context = _candidate_context(root, plan.get("candidate_files") or [])
    prompt = (
        "You are Friday's autonomous coding executor. Return only JSON, no markdown.\n"
        "Create the smallest safe staged replacements for the approved self-update request.\n"
        "JSON schema: {\"changes\":[{\"path\":\"relative/path\",\"find_text\":\"exact old text or empty for new file\",\"replace_text\":\"new full text or replacement\",\"summary\":\"short reason\"}],\"tests\":[\"command\"],\"notes\":\"short\"}.\n"
        "Rules: existing-file find_text must match exactly once; never edit .env, data, .venv, node_modules, .git, __pycache__, .next, dist, or build; keep each replace_text focused.\n\n"
        f"Request: {update.get('request')}\n"
        f"Plan: {_json_dumps(plan)}\n"
        f"Repository context:\n{context}"
    )
    raw = ""
    try:
        providers = _coding_provider_chain()
        raw = llm.ask_simple_with_provider_chain(prompt, providers, retries=1) or ""
    except Exception as exc:
        return {"staged_changes": [], "errors": [f"LLM change generation failed: {exc}"], "raw_excerpt": raw[:800]}
    changes = _parse_change_set(raw)
    staged: list[dict[str, Any]] = []
    errors: list[str] = []
    for change in changes[: int(config_value("autonomous_coding_max_staged_changes", 6))]:
        try:
            staged_change = self_update.stage_change(
                int(update["id"]),
                str(change.get("path") or ""),
                str(change.get("find_text") or ""),
                str(change.get("replace_text") or ""),
                str(change.get("summary") or "Autonomous coding staged replacement."),
            )
            staged.append(staged_change)
            _post(task_id, "autonomous_coding", f"Staged change #{staged_change.get('id')} for {staged_change.get('path')}.")
        except Exception as exc:
            errors.append(f"{change.get('path') or 'unknown path'}: {exc}")
    return {"staged_changes": staged, "errors": errors, "raw_excerpt": raw[:800]}


def _candidate_context(root: Path, candidates: list[Any]) -> str:
    chunks: list[str] = []
    max_total = int(config_value("autonomous_coding_context_chars", 24000))
    max_file = int(config_value("autonomous_coding_context_file_chars", 6000))
    paths = _candidate_paths(root, candidates)
    total = 0
    for path in paths:
        try:
            resolved = path.resolve()
            resolved.relative_to(root)
        except Exception:
            continue
        if not resolved.exists() or not resolved.is_file() or _blocked_path(resolved, root):
            continue
        if resolved.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            text = resolved.read_text(encoding="utf-8", errors="ignore")[:max_file]
        except Exception:
            continue
        rel = str(resolved.relative_to(root)).replace("\\", "/")
        chunk = f"\n--- {rel} ---\n{text}\n"
        if total + len(chunk) > max_total:
            break
        chunks.append(chunk)
        total += len(chunk)
    return "".join(chunks) or "No safe candidate file context was available."


def _candidate_paths(root: Path, candidates: list[Any]) -> list[Path]:
    paths: list[Path] = []
    for item in candidates:
        raw = str(item or "").strip()
        if not raw:
            continue
        path = Path(raw)
        if not path.is_absolute():
            path = root / raw
        if path.is_dir():
            paths.extend(child for child in sorted(path.rglob("*")) if child.is_file())
        else:
            paths.append(path)
    if not paths:
        for child in root.rglob("*"):
            if child.is_file() and not _blocked_path(child, root) and child.suffix.lower() in TEXT_EXTENSIONS:
                paths.append(child)
            if len(paths) >= 12:
                break
    return paths[:20]


def _parse_change_set(raw: str) -> list[dict[str, Any]]:
    text = str(raw or "").strip()
    if not text:
        return []
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.MULTILINE).strip()
    data: Any
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return []
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
    changes = data.get("changes") if isinstance(data, dict) else data
    if not isinstance(changes, list):
        return []
    parsed: list[dict[str, Any]] = []
    for item in changes:
        if not isinstance(item, dict):
            continue
        path = _clean(item.get("path") or "")
        replace_text = str(item.get("replace_text") or "")
        if not path or not replace_text:
            continue
        parsed.append(
            {
                "path": path,
                "find_text": str(item.get("find_text") or ""),
                "replace_text": replace_text,
                "summary": _clean(item.get("summary") or "Autonomous coding staged replacement."),
            }
        )
    return parsed


def _implementation_plan(project_root: Path, request: str, prep: dict[str, Any]) -> str:
    analysis = prep.get("scan") if isinstance(prep.get("scan"), dict) else {}
    tests = prep.get("test_commands") or []
    lines = [
        "# Autonomous Coding Implementation Plan",
        "",
        f"Generated: {_now()}",
        f"Project: `{project_root}`",
        f"Request: {_clean(request)}",
        "",
        "## Proposed Flow",
        "1. Inspect the files most related to the request.",
        "2. Make the smallest source change that satisfies the requested user flow.",
        "3. Add or update focused tests where the project already has a test runner.",
        "4. Run the discovered checks and attach the result before claiming completion.",
        "5. Keep rollback simple: revert the touched files or restore from version control.",
        "",
        "## Discovered Checks",
    ]
    if tests:
        lines.extend(f"- `{command}`" for command in tests)
    else:
        lines.append("- No test command was discovered yet; add one before production release.")
    lines.extend(
        [
            "",
            "## Codebase Scan",
            str(analysis.get("summary") or "No scan summary available."),
            "",
            "## Approval Gate",
            "Existing source files were not changed in this prep step. Ask Friday for a concrete patch request after reviewing this plan.",
            "",
        ]
    )
    return "\n".join(lines)


def _starter_files(product_name: str, request: str) -> dict[str, str]:
    slug = _slug(product_name)
    return {
        "package.json": _json_dumps(
            {
                "name": slug,
                "private": True,
                "version": "0.1.0",
                "type": "module",
                "scripts": {"dev": "vite --host 127.0.0.1", "build": "vite build", "preview": "vite preview --host 127.0.0.1"},
                "dependencies": {"@vitejs/plugin-react": "latest", "vite": "latest", "react": "latest", "react-dom": "latest", "lucide-react": "latest"},
                "devDependencies": {},
            },
            indent=2,
        )
        + "\n",
        "index.html": '<!doctype html>\n<html lang="en">\n  <head>\n    <meta charset="UTF-8" />\n    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n    <title>'
        + product_name
        + '</title>\n  </head>\n  <body>\n    <div id="root"></div>\n    <script type="module" src="/src/main.jsx"></script>\n  </body>\n</html>\n',
        "src/main.jsx": "import React from 'react';\nimport { createRoot } from 'react-dom/client';\nimport App from './App.jsx';\nimport './styles.css';\n\ncreateRoot(document.getElementById('root')).render(<App />);\n",
        "src/App.jsx": _app_jsx(product_name, request),
        "src/styles.css": _app_css(),
        "README.md": _readme(product_name, request),
        ".gitignore": "node_modules\n.DS_Store\ndist\n.env\n.env.local\n",
    }


def _app_jsx(product_name: str, request: str) -> str:
    clean_request = _clean(request)
    return f"""import {{ useState }} from 'react';
import {{ Bot, CalendarCheck, CheckCircle2, ClipboardList, Sparkles, Users }} from 'lucide-react';

const initialWorkItems = [
  {{ title: 'Capture recurring work', detail: 'Turn messy daily requests into a structured queue.', status: 'Live' }},
  {{ title: 'AI action brief', detail: 'Summarize context, risks, owners, and suggested next steps.', status: 'AI' }},
  {{ title: 'Team handoff', detail: 'Share decisions, blockers, and customer-ready updates.', status: 'Ready' }},
];

const launchPlan = ['Ship a focused MVP', 'Validate with 10 first users', 'Add Gmail, Calendar, Slack, and Notion integrations', 'Offer solo and team pricing'];

export default function App() {{
  const [workItems, setWorkItems] = useState(initialWorkItems);
  const [brief, setBrief] = useState('Daily brief will appear here after you generate it.');
  const [rawNote, setRawNote] = useState('Customer asked for status, invoice is pending, designer is blocked on brand assets.');
  const reviewedCount = workItems.filter((item) => item.status === 'Reviewed').length;
  const markReviewed = (title) => setWorkItems((items) => items.map((item) => item.title === title ? {{ ...item, status: 'Reviewed' }} : item));
  const generateBrief = () => setBrief('Today: triage the queue, unblock one owner, send one customer-ready update, and validate the MVP with a real user.');
  const draftBrief = () => setBrief(`Summary: ${{rawNote}} Next action: assign an owner, clear the blocker, and send a concise status update.`);

  return (
    <main className="app-shell">
      <aside className="side-panel">
        <div className="brand-mark"><Sparkles size={{20}} /> {product_name}</div>
        <nav>
          <a href="#workspace">Workspace</a>
          <a href="#assistant">AI Assist</a>
          <a href="#launch">Launch</a>
        </nav>
      </aside>

      <section className="workspace" id="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Hackathon MVP</p>
            <h1>{product_name}</h1>
            <p className="subcopy">{clean_request}</p>
          </div>
          <button type="button" onClick={{generateBrief}}><Bot size={{18}} /> Generate daily brief</button>
        </header>

        <section className="metrics" aria-label="workflow metrics">
          <article><strong>{{workItems.length + 9}}</strong><span>tasks triaged</span></article>
          <article><strong>4</strong><span>handoffs drafted</span></article>
          <article><strong>{{31 + reviewedCount * 4}}m</strong><span>saved today</span></article>
        </section>

        <section className="board">
          {{workItems.map((item) => (
            <article className="task-card" key={{item.title}}>
              <span>{{item.status}}</span>
              <h2>{{item.title}}</h2>
              <p>{{item.detail}}</p>
              <button type="button" onClick={{() => markReviewed(item.title)}}><CheckCircle2 size={{16}} /> Mark reviewed</button>
            </article>
          ))}}
        </section>

        <section className="assistant-grid" id="assistant">
          <article className="assistant-panel">
            <h2><ClipboardList size={{18}} /> AI Decision Brief</h2>
            <p>Friday-style intelligence turns scattered notes into action items, owners, priority, and risks.</p>
            <textarea value={{rawNote}} onChange={{(event) => setRawNote(event.target.value)}} />
            <button type="button" onClick={{draftBrief}}><Sparkles size={{16}} /> Draft brief</button>
            <p className="brief-output">{{brief}}</p>
          </article>
          <article className="assistant-panel">
            <h2><Users size={{18}} /> Target Users</h2>
            <p>Solo makers, small teams, service businesses, agencies, and operators who repeat the same coordination work every day.</p>
          </article>
          <article className="assistant-panel">
            <h2><CalendarCheck size={{18}} /> Pricing</h2>
            <p>Free personal plan, $12/month Pro, and $39/month Team for shared workflows and integrations.</p>
          </article>
        </section>

        <section className="launch" id="launch">
          <h2>Path to market</h2>
          <div>
            {{launchPlan.map((item, index) => <p key={{item}}><strong>{{index + 1}}</strong>{{item}}</p>)}}
          </div>
        </section>
      </section>
    </main>
  );
}}
"""


def _app_css() -> str:
    return """* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color: #1d2730;
  background: #f6f7f2;
}

button,
textarea {
  font: inherit;
}

button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: 1px solid #18222b;
  background: #18222b;
  color: #ffffff;
  border-radius: 8px;
  padding: 10px 14px;
  cursor: pointer;
}

.app-shell {
  display: grid;
  grid-template-columns: 240px 1fr;
  min-height: 100vh;
}

.side-panel {
  background: #18222b;
  color: #ffffff;
  padding: 24px;
}

.brand-mark {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 800;
  margin-bottom: 32px;
}

nav {
  display: grid;
  gap: 10px;
}

nav a {
  color: #d6ece5;
  text-decoration: none;
  padding: 10px 0;
}

.workspace {
  padding: 32px;
}

.topbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 24px;
}

.eyebrow {
  color: #2b7a78;
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: uppercase;
  margin: 0 0 8px;
}

h1,
h2,
p {
  margin-top: 0;
}

h1 {
  font-size: clamp(2rem, 6vw, 4.2rem);
  line-height: 1;
  margin-bottom: 12px;
}

.subcopy {
  max-width: 760px;
  color: #46535f;
  font-size: 1.05rem;
  line-height: 1.6;
}

.metrics,
.board,
.assistant-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.metrics article,
.task-card,
.assistant-panel,
.launch {
  background: #ffffff;
  border: 1px solid #dde2da;
  border-radius: 8px;
  padding: 18px;
}

.metrics strong {
  display: block;
  font-size: 2rem;
}

.metrics span,
.task-card p,
.assistant-panel p,
.launch p {
  color: #59656f;
}

.task-card span {
  display: inline-block;
  color: #2b7a78;
  font-size: 0.78rem;
  font-weight: 800;
  margin-bottom: 16px;
}

.task-card button {
  background: #ffffff;
  color: #18222b;
}

.assistant-panel h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 1.05rem;
}

textarea {
  width: 100%;
  min-height: 110px;
  resize: vertical;
  border: 1px solid #c8d0c8;
  border-radius: 8px;
  padding: 12px;
  margin: 8px 0 12px;
}

.brief-output {
  border-left: 3px solid #2b7a78;
  padding-left: 12px;
  margin: 14px 0 0;
}

.launch div {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.launch strong {
  display: inline-grid;
  place-items: center;
  width: 28px;
  height: 28px;
  margin-right: 8px;
  border-radius: 50%;
  color: #ffffff;
  background: #2b7a78;
}

@media (max-width: 840px) {
  .app-shell {
    grid-template-columns: 1fr;
  }

  .side-panel {
    position: static;
  }

  .topbar {
    display: grid;
  }

  .metrics,
  .board,
  .assistant-grid,
  .launch div {
    grid-template-columns: 1fr;
  }
}
"""


def _readme(product_name: str, request: str) -> str:
    return f"""# {product_name}

Autonomous coding starter generated by Friday.

## Request

{_clean(request)}

## Product Vision

{product_name} is an AI-assisted everyday workflow tool for individuals, small teams, and SMB operators. It helps users turn scattered recurring work into clear tasks, daily briefs, decisions, handoffs, and launch-ready updates.

## Core Functionality

- Capture tasks, notes, blockers, and customer requests.
- Generate AI summaries, risks, owners, and next actions.
- Prepare team handoffs and status updates.
- Track product vision, integrations, pricing, and first-user strategy.

## AI Features

- Daily work brief.
- Decision and risk summarizer.
- Customer/status reply drafter.
- Workflow recommendations from repeated patterns.

## Integrations

Start with Gmail, Google Calendar, Slack, Notion, and CSV import/export. Keep all outbound actions approval-gated.

## Business Model

- Free: personal workspace.
- Pro: $12/month for solo operators.
- Team: $39/month for shared workflows, integrations, and admin review.

## Run Locally

```bash
npm install
npm run dev
```
"""


def _target_project_root(base_root: Path, request: str, *, stack: dict[str, str] | None = None) -> Path:
    base_root = base_root.resolve()
    slug = project_scaffolds.project_slug(request, stack)
    target = base_root / slug
    if not target.exists():
        return target
    for index in range(2, 100):
        candidate = base_root / f"{slug}-{index}"
        if not candidate.exists():
            return candidate
    return base_root / f"{slug}-{int(dt.datetime.now().timestamp())}"


def _task_project_root(raw_root: Any = "") -> Path:
    raw_text = str(raw_root or "").replace("\\", "/").lower().rstrip("/")
    if raw_text in {"/root", "/root/desktop"} or raw_text.startswith("/root/desktop/"):
        return (ROOT_DIR.parent / "friday-projects").resolve()
    root = resolve_coding_root(raw_root or "")
    normalized = root.as_posix().lower()
    if normalized.startswith("/root/desktop") or normalized == "/root":
        return (ROOT_DIR.parent / "friday-projects").resolve()
    return root


def _verify_scaffold(target: Path, stack: dict[str, str], written: list[str]) -> dict[str, Any]:
    stack_id = stack.get("stack") or "nextjs"
    required_by_stack = {
        "nextjs": ["package.json", "README.md", "src/app/page.tsx"],
        "flutter": ["pubspec.yaml", "README.md", "lib/main.dart"],
        "node_fastify": ["package.json", "README.md", "src/server.js"],
        "python_fastapi": ["pyproject.toml", "README.md"],
        "go_api": ["go.mod", "README.md", "main.go"],
        "rust_axum": ["Cargo.toml", "README.md", "src/main.rs"],
    }
    required = required_by_stack.get(stack_id, ["README.md"])
    missing = [relative for relative in required if not (target / relative).exists()]
    written_missing = [path for path in written if not Path(path).exists()]
    all_missing = [*missing, *written_missing]
    checks = [f"verified file exists: {relative}" for relative in required if (target / relative).exists()]
    if not all_missing:
        summary = f"Scaffold file verification passed for {target}."
    else:
        summary = f"Scaffold file verification failed for {target}: missing {', '.join(all_missing[:5])}."
    return {
        "status": "passed" if not all_missing else "failed",
        "summary": summary,
        "checks": checks,
        "missing": all_missing,
        "project_root": str(target),
    }


def _looks_like_new_app_request(request: str, project_root: Path) -> bool:
    text = request.lower()
    build_words = {"build", "create", "make", "generate", "scaffold", "ship"}
    app_words = {"api", "app", "application", "backend", "cli", "dashboard", "flutter", "frontend", "mobile", "mvp", "portal", "prototype", "server", "service", "site", "tool", "web-app", "website", "hackathon"}
    if not (set(_words(text)) & build_words and set(_words(text)) & app_words):
        return False
    markers = {".git", "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod"}
    return not any((project_root / marker).exists() for marker in markers)


def _execution_kind(request: str, project_root: Path) -> str:
    if _looks_like_new_app_request(request, project_root):
        return "scaffold_new_app"
    if _is_friday_root(project_root):
        return "self_update_proposal"
    return "existing_project_plan"


def _is_friday_root(path: Path) -> bool:
    try:
        return path.resolve() == Path(ROOT_DIR).resolve()
    except Exception:
        return False


def _blocked_path(path: Path, root: Path) -> bool:
    try:
        parts = set(path.resolve().relative_to(root.resolve()).parts)
    except Exception:
        return True
    return bool(parts & SKIP_PARTS) or path.name == ".env"


def _product_name(request: str) -> str:
    return project_scaffolds.product_name(request)


def _project_slug(request: str) -> str:
    return project_scaffolds.project_slug(request)


def _keywords(value: str) -> list[str]:
    stop = {
        "about",
        "application",
        "build",
        "create",
        "dashboard",
        "everyday",
        "finally",
        "generate",
        "hackathon",
        "make",
        "prototype",
        "should",
        "small",
        "something",
        "that",
        "this",
        "tool",
        "want",
        "with",
    }
    return [word for word in _words(value) if len(word) > 2 and word not in stop][:8]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-") or "friday-app"


def _result(
    task_id: int,
    task_status: str,
    summary: str,
    *,
    next_step: str,
    risks: list[str],
    changed: list[str] | None = None,
    tested: list[str] | None = None,
    failed: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = task_status if task_status in {"done", "blocked", "pending", "failed"} else "done"
    risk_text = "; ".join(risks) if risks else "No major risk recorded."
    structured = f"Summary: {summary} Next step: {next_step} Risks: {risk_text}"
    return {
        "agent_id": "senior_developer",
        "agent_name": "Senior Developer",
        "mode": "autonomous_coding",
        "task_status": status,
        "summary": structured,
        "voice_summary": summary if status == "done" else f"{summary} {next_step}",
        "next_step": next_step,
        "risks": risks,
        "changed": changed or [],
        "tested": tested or [],
        "failed": failed or [],
        "metadata": metadata or {},
        "task_id": task_id,
    }


def _post(task_id: int, sender: str, message: str) -> None:
    if task_id <= 0:
        return
    try:
        task_queue.post_message(task_id, sender, message)
    except Exception:
        return


def _coding_provider_chain() -> Any:
    route = config_value("autonomous_coding_provider_chain", "")
    if route:
        return route
    routes = config_value("model_router_routes", {})
    if isinstance(routes, dict) and routes.get("coding"):
        return routes.get("coding")
    return [config_value("llm_provider", "nvidia"), config_value("llm_fallback_provider", "ollama")]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())


def _words(value: str) -> list[str]:
    return [part for part in re.split(r"[^a-z0-9]+", str(value or "").lower()) if part]


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _json_dumps(value: Any, *, indent: int | None = None) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str, indent=indent)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

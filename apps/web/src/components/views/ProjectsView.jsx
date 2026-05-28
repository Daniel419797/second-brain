"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Bug,
  Clock,
  ExternalLink,
  FileText,
  Folder,
  GitBranch,
  HeartPulse,
  ImagePlus,
  KeyRound,
  Loader2,
  Search,
  ShieldCheck,
  TerminalSquare,
  Upload,
  Wrench
} from "lucide-react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";
import { API_URL } from "@/lib/config";

const MAX_REFERENCE_BYTES = 12 * 1024 * 1024;

const FALLBACK_PROJECTS = [
  {
    root_hash: "friday-core-engine",
    root: "/src/backend/core",
    name: "friday-core-engine",
    architecture: { summary: "Core orchestration service for Friday's local command center." },
    commands: ["make test-all", "docker-compose up -d", "poetry install"],
    env_names: ["FRIDAY_DB_URL", "OPENAI_API_KEY", "REDIS_HOST", "LOG_LEVEL"],
    common_bugs: ["Fix memory leak in websocket connections", "Update Redis client dependency"],
    past_fixes: ["Merged PR #490: Analytics Pipeline", "Deploy to Staging successful"],
    metadata: { has_pyproject: true, has_tests: true }
  },
  {
    root_hash: "friday-ui-dashboard",
    root: "/src/frontend/ui",
    name: "friday-ui-dashboard",
    architecture: { summary: "React command surface for Friday's operations dashboard." },
    commands: ["npm run build", "npm run dev", "npm run test"],
    env_names: ["NEXT_PUBLIC_API_URL", "NODE_ENV"],
    common_bugs: ["Tighten mobile layout spacing"],
    past_fixes: ["Refined governance command page"],
    metadata: { has_package_json: true, has_tests: true }
  },
  {
    root_hash: "agent-orchestrator",
    root: "/services/orchestrator",
    name: "agent-orchestrator",
    architecture: { summary: "Task routing and background worker coordination layer." },
    commands: ["go test ./...", "go run ./cmd/server"],
    env_names: ["QUEUE_URL", "WORKER_COUNT"],
    common_bugs: ["Dependency update required"],
    past_fixes: ["Worker heartbeat tuned"],
    metadata: { has_tests: true }
  }
];

export function ProjectsView() {
  const { api, token, data, refresh } = useDashboard();
  const sourceProjects = data.projectMemory?.projects || data.projects || [];
  const [selectedRoot, setSelectedRoot] = useState("");
  const [localReferences, setLocalReferences] = useState([]);
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  const projects = useMemo(() => normalizeProjects(sourceProjects), [sourceProjects]);
  const selected = projects.find((project) => project.root === selectedRoot) || projects[0];
  const references = useMemo(() => dedupeReferences([...localReferences, ...(data.projectReferences || [])]), [data.projectReferences, localReferences]);
  const selectedReferences = useMemo(() => references.filter((item) => !selected?.root || item.root === selected.root), [references, selected?.root]);

  useEffect(() => {
    if (!selectedRoot && projects[0]?.root) setSelectedRoot(projects[0].root);
  }, [projects, selectedRoot]);

  useEffect(() => {
    if (!file) {
      setPreview("");
      return undefined;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  async function submitReference(event) {
    event.preventDefault();
    if (!file || busy || !selected) return;
    if (file.size > MAX_REFERENCE_BYTES) {
      setStatus("Image is larger than 12MB.");
      return;
    }
    setBusy(true);
    setStatus("");
    try {
      const dataUrl = await readFileAsDataUrl(file);
      const created = await api("/project-memory/reference-images", {
        method: "POST",
        body: JSON.stringify({
          root: selected.root,
          title: title || file.name,
          note,
          filename: file.name,
          content_type: file.type,
          data_url: dataUrl,
          metadata: { source: "dashboard_projects" }
        })
      });
      setTitle("");
      setNote("");
      setFile(null);
      setLocalReferences((items) => [created, ...items]);
      setStatus("Reference image added.");
      void refresh();
    } catch (err) {
      setStatus(err.message || "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="friday-scroll h-full overflow-y-auto overflow-x-hidden bg-friday-bg px-2 py-2 text-white" aria-label="Projects operations board">
      <div className="min-w-0 max-w-[980px]">
        <div className="grid min-w-0 gap-3 lg:grid-cols-[340px_minmax(0,1fr)]">
          <aside className="grid min-w-0 content-start gap-3 overflow-hidden">
            <GlobalActions />
            <ActiveProjects projects={projects} selected={selected} references={references} onSelect={setSelectedRoot} />
          </aside>

          <main className="grid min-w-0 content-start gap-3 overflow-hidden">
          <ProjectHero project={selected} data={data} />
          <div className="grid min-w-0 gap-3 lg:grid-cols-[minmax(0,300px)_minmax(0,1fr)]">
            <div className="grid min-w-0 content-start gap-3 overflow-hidden">
              <CliActions project={selected} />
              <EnvironmentVars project={selected} />
            </div>
            <div className="grid min-w-0 content-start gap-3 overflow-hidden">
              <InsightCard project={selected} data={data} />
              <ImportantFiles project={selected} />
            </div>
          </div>
          <div className="grid min-w-0 gap-3 lg:grid-cols-2">
            <ActiveIssues project={selected} data={data} />
            <RecentChanges project={selected} references={selectedReferences} />
          </div>
          </main>
        </div>

        <div className="mt-3 max-w-[340px]">
          <ReferenceDock
            selected={selected}
            references={selectedReferences}
            token={token}
            file={file}
            preview={preview}
            title={title}
            note={note}
            status={status}
            busy={busy}
            onFile={setFile}
            onTitle={setTitle}
            onNote={setNote}
            onSubmit={submitReference}
          />
        </div>
      </div>
    </section>
  );
}

function GlobalActions() {
  const actions = [
    { label: "Run Health Check", icon: <ShieldCheck size={13} />, active: true },
    { label: "Search Codebase", icon: <Search size={13} /> },
    { label: "Generate Docs", icon: <FileText size={13} /> },
    { label: "Prepare Fix", icon: <Wrench size={13} /> }
  ];
  return (
    <Panel>
      <h2 className="mb-3 font-mono text-[10px] font-bold uppercase tracking-[.16em] text-[#cbd5e2]">Global Actions</h2>
      <div className="grid grid-cols-2 gap-2">
        {actions.map((action) => (
          <button
            className={`inline-flex min-h-[44px] min-w-0 items-center justify-center gap-2 rounded-[4px] border px-2 font-mono text-[10px] font-bold leading-tight transition-colors ${
              action.active ? "border-[#47627e] bg-[#213044] text-friday-accent" : "border-friday-line bg-[#222830] text-white hover:border-friday-accent"
            }`}
            type="button"
            key={action.label}
          >
            <span className="shrink-0">{action.icon}</span>
            <span className="min-w-0 max-w-[92px] leading-snug">{action.label}</span>
          </button>
        ))}
      </div>
    </Panel>
  );
}

function ActiveProjects({ projects, selected, references, onSelect }) {
  return (
    <Panel className="min-h-[730px] p-0">
      <header className="flex min-h-[48px] items-center gap-3 border-b border-friday-line px-3">
        <h2 className="text-[15px] font-extrabold text-white">Active Projects</h2>
        <span className="ml-auto rounded-full border border-[#3d4857] bg-[#303743] px-2 py-0.5 font-mono text-[9px] text-[#dce6f2]">{projects.length} Total</span>
      </header>
      <div className="grid gap-2 p-2">
        {projects.map((project) => (
          <button
            className={`grid min-h-[90px] min-w-0 gap-2 rounded-[5px] border p-3 text-left transition-colors ${
              selected?.root === project.root ? "border-friday-accent bg-[#202832] shadow-[inset_4px_0_0_#9fcaff]" : "border-transparent bg-transparent hover:bg-[#202832]"
            }`}
            type="button"
            onClick={() => onSelect(project.root)}
            key={project.root_hash || project.root}
          >
            <div className="flex min-w-0 items-center gap-2">
              <strong className="min-w-0 truncate font-mono text-[12px] text-white">{project.name}</strong>
              {selected?.root === project.root ? <GitBranch className="text-friday-accent" size={12} /> : null}
            </div>
            <span className="min-w-0 truncate font-mono text-[12px] text-[#c4cfdd]">{prettyRoot(project.root)}</span>
            <div className="flex min-w-0 flex-wrap gap-1.5">
              {projectTags(project, references).map((tag) => <Tag tag={tag} key={tag.label} />)}
            </div>
          </button>
        ))}
      </div>
    </Panel>
  );
}

function ProjectHero({ project, data }) {
  return (
    <section
      className="relative grid min-h-[190px] overflow-hidden rounded-[6px] border border-friday-line bg-[#1a2028] p-5"
      style={{ backgroundImage: "radial-gradient(circle at 1px 1px, rgba(159,202,255,.16) 1px, transparent 0)", backgroundSize: "32px 32px" }}
    >
      <div className="absolute right-4 top-4 rounded-[2px] border border-friday-line bg-[#10161d] px-2 py-1.5 font-mono text-[10px] text-white">
        <span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-[#34d36e]" />
        Service: {data.status?.running ? "Healthy" : "Standby"}
      </div>
      <div className="mt-auto flex min-w-0 flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-[26px] font-extrabold leading-none text-white">{project?.name || "No Project"}</h1>
          <p className="mt-2 truncate font-mono text-[12px] text-friday-accent">{prettyRoot(project?.root)} - {projectStack(project)}</p>
        </div>
        <button className="grid h-11 w-11 place-items-center rounded-[4px] border border-friday-line bg-[#303743] text-white" type="button" aria-label="Open project">
          <ExternalLink size={17} />
        </button>
        <button className="inline-flex min-h-11 items-center gap-2 rounded-[5px] border border-[#8bbcff] bg-[#8bbcff] px-5 text-[13px] font-semibold text-[#061420]" type="button">
          <TerminalSquare size={15} />
          Connect
        </button>
      </div>
    </section>
  );
}

function CliActions({ project }) {
  const commands = commandRows(project);
  return (
    <Panel className="min-h-[238px]">
      <PanelTitle icon={<TerminalSquare size={13} />} title="CLI Actions" />
      <div className="mt-3 grid gap-2">
        {commands.map((command) => (
          <button className="block min-h-[36px] min-w-0 overflow-hidden rounded-[4px] border border-friday-line bg-[#0b1117] px-3 text-left font-mono text-[12px] text-white hover:border-friday-accent" type="button" key={command}>
            <span className="mr-2 text-friday-accent">&gt;</span>
            <span className="inline-block max-w-[calc(100%-24px)] truncate align-middle">{shortCommand(command)}</span>
          </button>
        ))}
      </div>
    </Panel>
  );
}

function InsightCard({ project, data }) {
  const issue = activeIssueRows(project, data)[0]?.title || "the current project health scan";
  const file = importantFileRows(project)[2]?.name || "the active module";
  return (
    <Panel className="min-h-[238px] border-[#58708a] bg-[#202832]">
      <PanelTitle icon={<HeartPulse size={13} />} title="Friday's Insight" accent />
      <p className="mt-4 min-w-0 break-words text-[13px] leading-relaxed text-[#eaf2fb]">
        The recent signal around <Code>{issue}</Code> appears connected to <Code>{file}</Code>. I have enough project memory to prepare a targeted fix path without touching unrelated files.
      </p>
      <button className="mt-4 min-h-10 w-full rounded-[4px] border border-friday-accent bg-[#405063] text-[13px] text-friday-accent" type="button">
        Review Proposed Fix
      </button>
    </Panel>
  );
}

function EnvironmentVars({ project }) {
  const env = (project?.env_names || []).slice(0, 5);
  return (
    <Panel className="min-h-[118px]">
      <PanelTitle icon={<KeyRound size={13} />} title="Environment Vars" />
      <div className="mt-3 grid min-w-0 grid-cols-[repeat(auto-fit,minmax(88px,1fr))] gap-2">
        {env.length ? env.map((item) => <span className="min-w-0 truncate rounded-[2px] bg-[#343b46] px-2 py-1.5 font-mono text-[10px] text-white" title={item} key={item}>{item}</span>) : <span className="text-[12px] text-friday-muted">No environment references indexed.</span>}
        {(project?.env_names || []).length > 5 ? <span className="min-w-0 truncate rounded-[2px] bg-[#343b46] px-2 py-1.5 font-mono text-[10px] text-friday-muted">+ {(project.env_names.length - 5)} more</span> : null}
      </div>
    </Panel>
  );
}

function ImportantFiles({ project }) {
  return (
    <Panel className="min-h-[148px]">
      <PanelTitle icon={<Folder size={13} />} title="Important Files" />
      <div className="mt-3 grid">
        {importantFileRows(project).map((file) => (
          <div className="grid min-h-[31px] min-w-0 grid-cols-[16px_minmax(0,1fr)_minmax(46px,auto)] items-center gap-2 border-b border-friday-line last:border-b-0" key={file.name}>
            {file.warning ? <AlertTriangle size={12} className="text-[#ffaaa6]" /> : <FileText size={12} className="text-[#aeb9c7]" />}
            <span className={`truncate font-mono text-[11px] ${file.warning ? "text-[#ffb5b8]" : "text-white"}`}>{file.name}</span>
            <span className="truncate text-right text-[9px] text-friday-muted">{file.meta}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function ActiveIssues({ project, data }) {
  return (
    <Panel className="min-h-[218px]">
      <PanelTitle icon={<Bug size={13} />} title="Active Issues (Todos)" />
      <div className="mt-4 grid gap-3">
        {activeIssueRows(project, data).map((issue) => (
          <div className="grid grid-cols-[12px_minmax(0,1fr)] gap-2" key={issue.title}>
            <span className={`mt-1 h-2 w-2 rounded-full ${issue.tone === "warn" ? "bg-[#f7c42f]" : "bg-[#ffaaa6]"}`} />
            <div className="min-w-0">
              <strong className="block truncate text-[12px] font-medium text-white">{issue.title}</strong>
              <span className="mt-1 block truncate font-mono text-[10px] text-friday-muted">{issue.meta}</span>
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function RecentChanges({ project, references }) {
  return (
    <Panel className="min-h-[218px]">
      <PanelTitle icon={<Clock size={13} />} title="Recent Changes" />
      <div className="mt-4 grid gap-4 border-l border-friday-line pl-4">
        {recentChangeRows(project, references).map((change, index) => (
          <div className="relative min-w-0" key={`${index}-${change.title}`}>
            <span className={`absolute -left-[21px] top-1 h-3 w-3 rounded-full border-2 ${index === 0 ? "border-friday-accent bg-[#1a2028]" : "border-[#8a97a8] bg-[#1a2028]"}`} />
            <strong className="block truncate text-[12px] font-medium text-white">{change.title}</strong>
            <span className="mt-1 block truncate text-[11px] text-friday-muted">{change.meta}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function ReferenceDock({ selected, references, token, file, preview, title, note, status, busy, onFile, onTitle, onNote, onSubmit }) {
  return (
    <Panel>
      <PanelTitle icon={<ImagePlus size={13} />} title="Visual References" />
      <form className="mt-4 grid gap-3" onSubmit={onSubmit}>
        <div className="grid grid-cols-[92px_minmax(0,1fr)] gap-3">
          <label className="grid min-h-[92px] cursor-pointer place-items-center rounded-[4px] border border-dashed border-[#4b5a6b] bg-[#10161d] text-center hover:border-friday-accent">
            <input className="sr-only" type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={(event) => onFile(event.target.files?.[0] || null)} />
            {preview ? <img className="h-[82px] w-[82px] object-cover" src={preview} alt="Selected reference preview" /> : <ImagePlus size={24} className="text-friday-muted" />}
          </label>
          <div className="grid gap-2">
            <input className="min-h-10 min-w-0 rounded-[4px] border border-friday-line bg-[#0c1218] px-3 text-[13px] text-white outline-none focus:border-friday-accent" value={title} onChange={(event) => onTitle(event.target.value)} placeholder="Reference title" />
            <input className="min-h-10 min-w-0 rounded-[4px] border border-friday-line bg-[#0c1218] px-3 text-[13px] text-white outline-none focus:border-friday-accent" value={note} onChange={(event) => onNote(event.target.value)} placeholder="What should Friday copy?" />
          </div>
        </div>
        <button className="inline-flex min-h-10 items-center justify-center gap-2 rounded-[4px] border border-friday-blue bg-friday-blue px-4 font-mono text-[12px] font-bold text-[#061420] disabled:opacity-45" type="submit" disabled={!file || busy || !selected}>
          {busy ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
          Add Reference
        </button>
        {status ? <p className="m-0 text-[12px] text-[#dce7f4]">{status}</p> : null}
      </form>
      <div className="mt-4 grid grid-cols-3 gap-2">
        {references.slice(0, 3).map((item) => <ReferenceThumb item={item} token={token} key={item.id || item.url} />)}
        {!references.length ? <p className="col-span-3 m-0 text-[12px] text-friday-muted">No visual references attached to this project yet.</p> : null}
      </div>
    </Panel>
  );
}

function ReferenceThumb({ item, token }) {
  const src = referenceImageSrc(item, token);
  return (
    <article className="min-w-0 overflow-hidden rounded-[4px] border border-friday-line bg-[#10161d]">
      <div className="grid h-[70px] place-items-center bg-[#080d11]">
        {src ? <img className="h-full w-full object-cover" src={src} alt={item.title || "Project reference"} /> : <ImagePlus size={18} className="text-friday-muted" />}
      </div>
      <p className="truncate px-2 py-1.5 text-[10px] text-[#dce6f2]">{item.title || item.filename}</p>
    </article>
  );
}

function Panel({ children, className = "" }) {
  return <section className={`min-w-0 overflow-hidden rounded-[6px] border border-friday-line bg-[#1a2028] p-3 ${className}`}>{children}</section>;
}

function PanelTitle({ icon, title, accent }) {
  return (
    <h2 className={`flex min-w-0 items-center gap-2 font-mono text-[11px] font-bold uppercase tracking-[.12em] ${accent ? "text-friday-accent" : "text-[#dbe4ef]"}`}>
      <span className="shrink-0">{icon}</span>
      <span className="min-w-0 truncate">{title}</span>
    </h2>
  );
}

function Tag({ tag }) {
  const styles = {
    neutral: "border-[#3d4857] bg-[#303743] text-[#dce6f2]",
    ok: "border-[#2f6a57] bg-[#11251f] text-[#4dffb0]",
    warn: "border-[#6a5d2a] bg-[#292815] text-[#f7c42f]",
    danger: "border-[#6e3038] bg-[#30171c] text-[#ff8d96]",
    blue: "border-[#466b91] bg-[#17263a] text-friday-accent"
  };
  return <span className={`max-w-full truncate rounded-[2px] border px-2 py-1 font-mono text-[9px] ${styles[tag.tone || "neutral"]}`}>{tag.label}</span>;
}

function Code({ children }) {
  return <code className="inline break-all rounded-[2px] bg-[#152233] px-1.5 py-0.5 font-mono text-friday-accent">{children}</code>;
}

function normalizeProjects(projects) {
  const rows = projects?.length ? projects : FALLBACK_PROJECTS;
  return rows.map((project, index) => ({
    ...project,
    root_hash: project.root_hash || project.root || `project-${index}`,
    root: project.root || `/project/${index + 1}`,
    name: project.name || lastPathSegment(project.root) || `Project ${index + 1}`,
    commands: Array.isArray(project.commands) ? project.commands : [],
    env_names: Array.isArray(project.env_names) ? project.env_names : [],
    common_bugs: Array.isArray(project.common_bugs) ? project.common_bugs : [],
    past_fixes: Array.isArray(project.past_fixes) ? project.past_fixes : [],
    metadata: project.metadata || {},
    architecture: project.architecture || {}
  }));
}

function dedupeReferences(items) {
  const seen = new Set();
  return items.filter((item) => {
    const key = item?.id || item?.url || item?.filename;
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function projectTags(project, references) {
  const refs = references.filter((item) => item.root === project.root).length;
  const tags = [{ label: projectStack(project).split(" ")[0] || "Project", tone: "neutral" }];
  tags.push({ label: project.metadata?.has_tests ? "Tests: Passing" : "Tests: Unknown", tone: project.metadata?.has_tests ? "ok" : "warn" });
  tags.push({ label: refs ? `Refs: ${refs}` : "Docs: Stale", tone: refs ? "blue" : "warn" });
  return tags;
}

function projectStack(project) {
  if (project?.metadata?.has_package_json) return "React / Next.js";
  if (project?.metadata?.has_pyproject) return "Python 3.11 / Fast API";
  if ((project?.commands || []).some((command) => command.includes("go "))) return "Go service";
  return "Project";
}

function shortCommand(command) {
  return String(command || "").replace(/^npm --workspace apps\/web run /, "npm web:").replace(/^npm --workspace apps\/desktop run /, "npm desktop:");
}

function commandRows(project) {
  const commands = project?.commands || [];
  if (commands.length) return commands.slice(0, 4);
  if (project?.metadata?.has_package_json) return ["npm run build", "npm run dev", "npm run test"];
  if (project?.metadata?.has_pyproject) return ["python -m pytest", "python -m pip install -e .", "python -m compileall ."];
  return ["make test-all", "docker-compose up -d", "poetry install"];
}

function importantFileRows(project) {
  const rows = [];
  if (project?.metadata?.has_package_json) rows.push({ name: "package.json", meta: "Updated 2h ago" });
  if (project?.metadata?.has_pyproject) rows.push({ name: "pyproject.toml", meta: "Updated 1d ago" });
  rows.push({ name: "README.md", meta: "Docs" });
  rows.push({ name: project?.metadata?.has_package_json ? "src/app/page.tsx" : "core/engine.py", meta: "Core" });
  rows.push({ name: "session_manager.py", meta: "High Churn", warning: true });
  return rows.slice(0, 4);
}

function activeIssueRows(project, data) {
  const bugs = project?.common_bugs || [];
  const logIssue = (data.logs?.lines || []).find((line) => /error|fail|todo/i.test(line));
  const rows = bugs.map((bug, index) => ({ title: bug, meta: `#${492 - index} - Assigned to AI`, tone: index ? "warn" : "danger" }));
  if (logIssue && rows.length < 2) rows.push({ title: String(logIssue).slice(0, 90), meta: "Recent reliability log", tone: "warn" });
  return rows.length ? rows.slice(0, 3) : [
    { title: "Fix memory leak in websocket connections", meta: "#492 - Assigned to AI", tone: "danger" },
    { title: "Update Redis client dependency", meta: "#488 - Security patch", tone: "warn" }
  ];
}

function recentChangeRows(project, references) {
  const fixes = (project?.past_fixes || []).map((item) => ({ title: item, meta: "Project memory" }));
  const refs = references.slice(0, 2).map((item) => ({ title: `Added reference: ${item.title || item.filename}`, meta: timeAgo(item.timestamp) }));
  const rows = [...fixes, ...refs];
  return rows.length ? rows.slice(0, 4) : [
    { title: "Merged PR #490: Analytics Pipeline", meta: "by J. Doe - 2 hours ago" },
    { title: "Deploy to Staging successful", meta: "System - Yesterday" }
  ];
}

function prettyRoot(root) {
  const parts = String(root || "").replace(/\\/g, "/").split("/").filter(Boolean);
  if (!parts.length) return "/project";
  return `/${parts.slice(-3).join("/")}`;
}

function lastPathSegment(root) {
  const parts = String(root || "").replace(/\\/g, "/").split("/").filter(Boolean);
  return parts[parts.length - 1] || "";
}

function referenceImageSrc(item, token) {
  const url = item?.url || item?.image_url;
  if (!url) return "";
  const separator = url.includes("?") ? "&" : "?";
  return `${API_URL}${url}${separator}token=${encodeURIComponent(token || "")}`;
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Could not read selected image."));
    reader.readAsDataURL(file);
  });
}

function timeAgo(value) {
  const date = value ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) return "Recently";
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return "Just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "Yesterday" : `${days}d ago`;
}

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

export function ProjectsView() {
  const { api, token, data, refresh, interfaceFor } = useDashboard();
  const copy = interfaceFor?.("projects") || {};
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

  async function runProjectAction(label, action) {
    if (!selected || busy) return;
    setBusy(label);
    setStatus("");
    try {
      const result = await action(selected);
      setStatus(result?.summary || result?.message || `${labelize(label)} completed.`);
      void refresh();
    } catch (err) {
      setStatus(err.message || `${labelize(label)} failed.`);
    } finally {
      setBusy(false);
    }
  }

  function openProject() {
    runProjectAction("open project", () => api("/integrations/open", { method: "POST", body: JSON.stringify({ target: "vscode" }) }));
  }

  function connectProject() {
    runProjectAction("connect", (project) => api("/workspace-brain/analyze", { method: "POST", body: JSON.stringify({ root: project.root }) }));
  }

  function runCommand(command) {
    runProjectAction("command", (project) =>
      api("/desktop/tasks", {
        method: "POST",
        body: JSON.stringify({ instruction: `Open ${project.root} and run: ${command}`, max_steps: 8 })
      })
    );
  }

  function reviewFix() {
    const issue = window.prompt("Issue or bug to prepare a fix for", activeIssueRows(selected, data)[0]?.title || "");
    if (issue == null) return;
    runProjectAction("prepare fix", (project) => api("/project-autopilot/prepare-fixes", { method: "POST", body: JSON.stringify({ root: project.root, issue_query: issue }) }));
  }

  return (
    <section className="friday-scroll h-full overflow-y-auto overflow-x-hidden bg-friday-bg px-2 py-2 text-white" aria-label="Projects operations board">
      <div className="min-w-0 max-w-[980px]">
        <div className="grid min-w-0 gap-3 lg:grid-cols-[340px_minmax(0,1fr)]">
          <aside className="grid min-w-0 content-start gap-3 overflow-hidden">
            <GlobalActions project={selected} busy={busy} onRun={runProjectAction} />
            <ActiveProjects projects={projects} selected={selected} references={references} onSelect={setSelectedRoot} />
          </aside>

          <main className="grid min-w-0 content-start gap-3 overflow-hidden">
          <ProjectHero project={selected} copy={copy} data={data} busy={busy} onOpen={openProject} onConnect={connectProject} />
          <div className="grid min-w-0 gap-3 lg:grid-cols-[minmax(0,300px)_minmax(0,1fr)]">
            <div className="grid min-w-0 content-start gap-3 overflow-hidden">
              <CliActions project={selected} copy={copy} busy={busy} onCommand={runCommand} />
              <EnvironmentVars project={selected} />
            </div>
            <div className="grid min-w-0 content-start gap-3 overflow-hidden">
              <InsightCard project={selected} copy={copy} onReviewFix={reviewFix} busy={busy} />
              <ImportantFiles project={selected} copy={copy} />
            </div>
          </div>
          <div className="grid min-w-0 gap-3 lg:grid-cols-2">
            <ActiveIssues project={selected} data={data} copy={copy} />
            <RecentChanges project={selected} references={selectedReferences} copy={copy} />
          </div>
          </main>
        </div>

        <div className="mt-3 max-w-[340px]">
            <ReferenceDock
            copy={copy}
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
        {status ? <div className="fixed bottom-5 right-5 z-20 max-w-[380px] rounded-[4px] border border-[#45678c] bg-[#9fcaff] px-4 py-3 text-[13px] font-semibold text-[#07111d] shadow-[0_16px_40px_rgba(0,0,0,.32)]">{status}</div> : null}
      </div>
    </section>
  );
}

function GlobalActions({ project, busy, onRun }) {
  const actions = [
    { key: "health", label: "Run Health Check", icon: <ShieldCheck size={13} />, active: true, run: (api, item) => api("/project-autopilot/inspect", { method: "POST", body: JSON.stringify({ root: item.root, run_tests: false }) }) },
    { key: "search", label: "Search Codebase", icon: <Search size={13} />, run: (api, item) => {
      const query = window.prompt("Search project memory for", "recent failures");
      if (query == null) return Promise.resolve({ summary: "Search cancelled." });
      return api("/project-memory/search", { method: "POST", body: JSON.stringify({ root: item.root, query, limit: 8 }) });
    } },
    { key: "docs", label: "Generate Docs", icon: <FileText size={13} />, run: (api, item) => api("/workspace-brain/docs", { method: "POST", body: JSON.stringify({ root: item.root }) }) },
    { key: "fix", label: "Prepare Fix", icon: <Wrench size={13} />, run: (api, item) => {
      const issue = window.prompt("Issue or bug to prepare a fix for", "");
      if (issue == null) return Promise.resolve({ summary: "Prepare fix cancelled." });
      return api("/project-autopilot/prepare-fixes", { method: "POST", body: JSON.stringify({ root: item.root, issue_query: issue }) });
    } }
  ];
  const { api } = useDashboard();
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
            onClick={() => onRun(action.key, () => action.run(api, project))}
            disabled={!project || Boolean(busy)}
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
        {projects.length ? projects.map((project) => (
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
        )) : (
          <p className="m-0 rounded-[4px] border border-dashed border-friday-line bg-[#10161d] px-3 py-4 text-[12px] leading-relaxed text-friday-muted">
            No project profile is loaded yet. Ask Friday to inspect the workspace and backend project memory will fill this list.
          </p>
        )}
      </div>
    </Panel>
  );
}

function ProjectHero({ project, copy, data, busy, onOpen, onConnect }) {
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
          <h1 className="truncate text-[26px] font-extrabold leading-none text-white">{project?.name || copy?.title || "Friday has no project selected"}</h1>
          <p className="mt-2 truncate font-mono text-[12px] text-friday-accent">{prettyRoot(project?.root)} - {projectStack(project)}</p>
        </div>
        <button className="grid h-11 w-11 place-items-center rounded-[4px] border border-friday-line bg-[#303743] text-white hover:border-friday-accent disabled:opacity-50" type="button" aria-label="Open project" onClick={onOpen} disabled={!project || Boolean(busy)}>
          <ExternalLink size={17} />
        </button>
        <button className="inline-flex min-h-11 items-center gap-2 rounded-[5px] border border-[#8bbcff] bg-[#8bbcff] px-5 text-[13px] font-semibold text-[#061420] disabled:opacity-50" type="button" onClick={onConnect} disabled={!project || Boolean(busy)}>
          <TerminalSquare size={15} />
          Connect
        </button>
      </div>
    </section>
  );
}

function CliActions({ project, copy, busy, onCommand }) {
  const commands = commandRows(project);
  return (
    <Panel className="min-h-[238px]">
      <PanelTitle icon={<TerminalSquare size={13} />} title="CLI Actions" />
      <div className="mt-3 grid gap-2">
        {commands.length ? commands.map((command) => (
          <button className="block min-h-[36px] min-w-0 overflow-hidden rounded-[4px] border border-friday-line bg-[#0b1117] px-3 text-left font-mono text-[12px] text-white hover:border-friday-accent disabled:opacity-50" type="button" key={command} onClick={() => onCommand(command)} disabled={Boolean(busy)}>
            <span className="mr-2 text-friday-accent">&gt;</span>
            <span className="inline-block max-w-[calc(100%-24px)] truncate align-middle">{shortCommand(command)}</span>
          </button>
        )) : <EmptyLine>{copy?.empty?.projects || "Friday has no project command hints from backend memory yet."}</EmptyLine>}
      </div>
    </Panel>
  );
}

function InsightCard({ copy, onReviewFix, busy }) {
  const insight = copy?.insight || {};
  const action = copy?.actions?.find?.((item) => item.id === "review-project-insight");
  return (
    <Panel className="min-h-[238px] border-[#58708a] bg-[#202832]">
      <PanelTitle icon={<HeartPulse size={13} />} title={insight.title || "Friday's Project Read"} accent />
      <p className="mt-4 min-w-0 break-words text-[13px] leading-relaxed text-[#eaf2fb]">
        {insight.summary || copy?.empty?.insight || "Friday has not produced a project insight for this snapshot yet."}
      </p>
      {insight.evidence?.length ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {insight.evidence.slice(0, 4).map((item) => <Code key={item}>{item}</Code>)}
        </div>
      ) : null}
      <button className="mt-4 min-h-10 w-full rounded-[4px] border border-friday-accent bg-[#405063] text-[13px] text-friday-accent disabled:opacity-50" type="button" onClick={onReviewFix} disabled={Boolean(busy)}>
        {action?.label || insight.action_label || "Review Project Read"}
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

function ImportantFiles({ project, copy }) {
  const files = importantFileRows(project);
  return (
    <Panel className="min-h-[148px]">
      <PanelTitle icon={<Folder size={13} />} title="Important Files" />
      <div className="mt-3 grid">
        {files.length ? files.map((file) => (
          <div className="grid min-h-[31px] min-w-0 grid-cols-[16px_minmax(0,1fr)_minmax(46px,auto)] items-center gap-2 border-b border-friday-line last:border-b-0" key={file.name}>
            {file.warning ? <AlertTriangle size={12} className="text-[#ffaaa6]" /> : <FileText size={12} className="text-[#aeb9c7]" />}
            <span className={`truncate font-mono text-[11px] ${file.warning ? "text-[#ffb5b8]" : "text-white"}`}>{file.name}</span>
            <span className="truncate text-right text-[9px] text-friday-muted">{file.meta}</span>
          </div>
        )) : <EmptyLine>{copy?.empty?.projects || "Friday has no important files indexed for this project yet."}</EmptyLine>}
      </div>
    </Panel>
  );
}

function ActiveIssues({ project, data, copy }) {
  const issues = activeIssueRows(project, data);
  return (
    <Panel className="min-h-[218px]">
      <PanelTitle icon={<Bug size={13} />} title="Active Issues (Todos)" />
      <div className="mt-4 grid gap-3">
        {issues.length ? issues.map((issue) => (
          <div className="grid grid-cols-[12px_minmax(0,1fr)] gap-2" key={issue.title}>
            <span className={`mt-1 h-2 w-2 rounded-full ${issue.tone === "warn" ? "bg-[#f7c42f]" : "bg-[#ffaaa6]"}`} />
            <div className="min-w-0">
              <strong className="block truncate text-[12px] font-medium text-white">{issue.title}</strong>
              <span className="mt-1 block truncate font-mono text-[10px] text-friday-muted">{issue.meta}</span>
            </div>
          </div>
        )) : <EmptyLine>{copy?.empty?.projects || "Friday has no active project issue from backend memory yet."}</EmptyLine>}
      </div>
    </Panel>
  );
}

function RecentChanges({ project, references, copy }) {
  const changes = recentChangeRows(project, references);
  return (
    <Panel className="min-h-[218px]">
      <PanelTitle icon={<Clock size={13} />} title="Recent Changes" />
      <div className="mt-4 grid gap-4 border-l border-friday-line pl-4">
        {changes.length ? changes.map((change, index) => (
          <div className="relative min-w-0" key={`${index}-${change.title}`}>
            <span className={`absolute -left-[21px] top-1 h-3 w-3 rounded-full border-2 ${index === 0 ? "border-friday-accent bg-[#1a2028]" : "border-[#8a97a8] bg-[#1a2028]"}`} />
            <strong className="block truncate text-[12px] font-medium text-white">{change.title}</strong>
            <span className="mt-1 block truncate text-[11px] text-friday-muted">{change.meta}</span>
          </div>
        )) : <EmptyLine>{copy?.empty?.projects || "Friday has no recent project change from backend memory yet."}</EmptyLine>}
      </div>
    </Panel>
  );
}

function ReferenceDock({ selected, copy, references, token, file, preview, title, note, status, busy, onFile, onTitle, onNote, onSubmit }) {
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
        {!references.length ? <p className="col-span-3 m-0 text-[12px] text-friday-muted">{copy?.empty?.projects || "Friday has no visual reference attached to this project yet."}</p> : null}
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

function EmptyLine({ children }) {
  return <p className="m-0 rounded-[3px] border border-dashed border-friday-line bg-[#10161d] px-3 py-3 text-[12px] leading-relaxed text-friday-muted">{children}</p>;
}

function normalizeProjects(projects) {
  const rows = Array.isArray(projects) ? projects : [];
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
  tags.push({ label: project.metadata?.has_tests ? "Tests indexed" : "Tests unknown", tone: project.metadata?.has_tests ? "ok" : "neutral" });
  tags.push({ label: `Refs: ${refs}`, tone: refs ? "blue" : "neutral" });
  return tags;
}

function projectStack(project) {
  if (project?.metadata?.has_package_json) return "Node / web project";
  if (project?.metadata?.has_pyproject) return "Python project";
  if ((project?.commands || []).some((command) => command.includes("go "))) return "Go service";
  return "Project";
}

function shortCommand(command) {
  return String(command || "").replace(/^npm --workspace apps\/web run /, "npm web:").replace(/^npm --workspace apps\/desktop run /, "npm desktop:");
}

function commandRows(project) {
  const commands = project?.commands || [];
  if (commands.length) return commands.slice(0, 4);
  return [];
}

function importantFileRows(project) {
  const explicit = [
    ...(Array.isArray(project?.important_files) ? project.important_files : []),
    ...(Array.isArray(project?.key_files) ? project.key_files : []),
    ...(Array.isArray(project?.files) ? project.files : [])
  ];
  const rows = explicit.map((file) => {
    if (typeof file === "string") return { name: file, meta: "Indexed" };
    return {
      name: file?.name || file?.path || file?.filename || "Indexed file",
      meta: file?.meta || file?.role || file?.reason || "Indexed",
      warning: Boolean(file?.warning || file?.risk)
    };
  });
  if (!rows.length && project?.metadata?.has_package_json) rows.push({ name: "package.json", meta: "Detected" });
  if (!rows.length && project?.metadata?.has_pyproject) rows.push({ name: "pyproject.toml", meta: "Detected" });
  return rows.slice(0, 4);
}

function activeIssueRows(project, data) {
  const bugs = project?.common_bugs || [];
  const logIssue = (data.logs?.lines || []).find((line) => /error|fail|todo/i.test(line));
  const rows = bugs.map((bug, index) => ({ title: bug, meta: index ? "Project memory" : "Project memory priority", tone: index ? "warn" : "danger" }));
  if (logIssue && rows.length < 2) rows.push({ title: String(logIssue).slice(0, 90), meta: "Recent reliability log", tone: "warn" });
  return rows.slice(0, 3);
}

function recentChangeRows(project, references) {
  const fixes = (project?.past_fixes || []).map((item) => ({ title: item, meta: "Project memory" }));
  const refs = references.slice(0, 2).map((item) => ({ title: `Added reference: ${item.title || item.filename}`, meta: timeAgo(item.timestamp) }));
  const rows = [...fixes, ...refs];
  return rows.slice(0, 4);
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

function labelize(value) {
  return String(value || "").replace(/[-_]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
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
  if (!date || Number.isNaN(date.getTime())) return "Time not captured";
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return "Just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "Yesterday" : `${days}d ago`;
}

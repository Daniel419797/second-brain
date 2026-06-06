"use client";

import { AlertTriangle, Brain, CheckCircle2, ClipboardCheck, Database, ExternalLink, FileText, GitBranch, KeyRound, Lightbulb, Loader2, Pause, Play, RefreshCw, Rocket, Save, Search, ShieldCheck, SlidersHorizontal, XCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";

const APPROVALS = [
  { id: "deploy_preview", label: "Preview Deploy" },
  { id: "deploy_production", label: "Production Deploy" },
  { id: "post_ads", label: "Post Ads" },
  { id: "enable_billing", label: "Billing" },
  { id: "send_outreach", label: "Outreach" }
];

const TABS = [
  ["runs", "Operating Runs"],
  ["spine", "Execution Spine"],
  ["providers", "Provider Debug"],
  ["autoeval", "AutoEval"],
  ["ideas", "Ideas"],
  ["judgment", "Judgment"],
  ["gates", "Gate Results"],
  ["proof", "Artifacts"],
  ["memory", "Memory"],
  ["styles", "Style Profiles"],
  ["integrations", "Integrations"],
  ["authority", "Authority"],
  ["approvals", "Approvals"],
  ["launch", "Launch"]
];

const FIELD_CLASS = "min-h-10 border border-friday-line bg-[#0c1218] px-3 py-2 text-[13px] text-white outline-none focus:border-friday-accent";
const ACTION_PRIMARY = "inline-flex min-h-9 items-center justify-center gap-2 border border-friday-blue bg-friday-blue px-3 font-mono text-[11px] font-bold text-[#061420] disabled:opacity-50";
const ACTION_SECONDARY = "inline-flex min-h-9 items-center justify-center gap-2 border border-friday-line bg-[#151b22] px-3 font-mono text-[11px] text-[#dfe9f6] hover:border-friday-accent disabled:opacity-50";

export function FridayStudioView() {
  const { api, data, refresh } = useDashboard();
  const fridayOs = data.fridayOs || {};
  const judgment = data.judgment || {};
  const projectIdeas = data.projectIdeas || {};
  const autoeval = data.autoeval || {};
  const toolRegistry = data.toolRegistry || {};
  const traceState = data.traces || {};
  const modelGateway = data.modelGateway || {};
  const autonomyControl = data.autonomyControl || {};
  const [runs, setRuns] = useState(() => fridayOs.runs || []);
  const mergedRuns = useMemo(() => dedupeRuns([...(runs || []), ...(fridayOs.runs || [])]), [runs, fridayOs.runs]);
  const [selectedId, setSelectedId] = useState(fridayOs.latest?.id || mergedRuns[0]?.id || 0);
  const selected = mergedRuns.find((run) => Number(run.id) === Number(selectedId)) || mergedRuns[0] || fridayOs.latest || null;
  const [tab, setTab] = useState("runs");
  const [busy, setBusy] = useState("");
  const [status, setStatus] = useState("");
  const [artifact, setArtifact] = useState(null);
  const [traceDetail, setTraceDetail] = useState(null);
  const [toolResult, setToolResult] = useState(null);
  const [contractResult, setContractResult] = useState(null);
  const [providerDebug, setProviderDebug] = useState(null);
  const [judgmentResult, setJudgmentResult] = useState(null);
  const [ideaResult, setIdeaResult] = useState(projectIdeas.latest || null);
  const [form, setForm] = useState({ request: "", root: "", target: "", production_profile: "auto", risk_level: "medium", max_fix_attempts: 0 });
  const [toolForm, setToolForm] = useState({ name: "documents.read", payload: "{\n  \"path\": \"\"\n}" });
  const [contractForm, setContractForm] = useState({ kind: "agent_result", payload: "{\n  \"summary\": \"Verified with evidence.\",\n  \"status\": \"done\"\n}" });
  const [styleForm, setStyleForm] = useState({ name: "", framework: "nextjs", description: "", required_paths: "src/app\nsrc/components\nsrc/services\nsrc/store\nsrc/hooks\nsrc/lib\nsrc/types", rules: "" });
  const [ideaForm, setIdeaForm] = useState({ context: "", audience: "individuals, small teams, and SMBs", limit: 5, max_sources: 8 });
  const [autoevalForm, setAutoevalForm] = useState({
    root: "",
    request: "",
    mode: "product_quality",
    target_files: "src/app/page.tsx\nsrc/app/globals.css",
    experiment_command: "",
    min_delta: 1,
    apply_fixes: false,
    run_gates: false
  });
  const [autoevalResult, setAutoevalResult] = useState(autoeval.latest || null);
  const [judgmentForm, setJudgmentForm] = useState({
    text: "",
    result: "",
    claims: "done\ntested\nverified",
    failure: "",
    lesson: "",
    domain: "coding"
  });

  async function startRun(event) {
    event.preventDefault();
    if (!form.request.trim()) return;
    setBusy("start");
    setStatus("");
    try {
      const run = await api("/friday-os/runs/start", { method: "POST", body: JSON.stringify({ ...form, max_fix_attempts: Number(form.max_fix_attempts || 0) }) });
      setRuns((items) => [run, ...items]);
      setSelectedId(run.id);
      setTab("runs");
      setStatus(run.summary || "Friday OS run started.");
      await refresh();
    } catch (err) {
      setStatus(err.message || "Friday OS run failed.");
    } finally {
      setBusy("");
    }
  }

  async function setAuthorityMode(mode) {
    setBusy(`authority:${mode}`);
    setStatus("");
    try {
      const result = await api("/autonomy-control/mode", { method: "PUT", body: JSON.stringify({ mode }) });
      setStatus(result.summary || `Authority mode set to ${labelize(mode)}.`);
      await refresh();
    } catch (err) {
      setStatus(err.message || "Authority mode update failed.");
    } finally {
      setBusy("");
    }
  }

  async function runAction(action, body = {}) {
    if (!selected?.id) return;
    setBusy(action);
    setStatus("");
    try {
      const run = await api(`/friday-os/runs/${selected.id}/${action}`, { method: "POST", body: JSON.stringify(body) });
      setRuns((items) => replaceRun(items, run));
      setStatus(run.summary || `${labelize(action)} complete.`);
      await refresh();
    } catch (err) {
      setStatus(err.message || `${labelize(action)} failed.`);
    } finally {
      setBusy("");
    }
  }

  async function approve(action) {
    await runAction("approve", { action, note: "Approved from Friday Studio" });
  }

  async function openArtifact(path) {
    if (!path) return;
    setBusy(path);
    try {
      const result = await api(`/friday-os/artifact?path=${encodeURIComponent(path)}`);
      setArtifact(result);
      setTab("proof");
    } catch (err) {
      setStatus(err.message || "Could not open artifact.");
    } finally {
      setBusy("");
    }
  }

  async function openTrace(traceId) {
    const id = String(traceId || "").trim();
    if (!id) return;
    setBusy(`trace:${id}`);
    setStatus("");
    try {
      const result = await api(`/traces/${encodeURIComponent(id)}`);
      setTraceDetail(result);
      setTab("spine");
    } catch (err) {
      setStatus(err.message || "Could not open trace.");
    } finally {
      setBusy("");
    }
  }

  async function refreshProviderDebug() {
    const root = selected?.root || form.root || "";
    setBusy("provider-debug");
    setStatus("");
    try {
      const result = await api(`/design/stitch/debug?root=${encodeURIComponent(root)}&limit=12`);
      setProviderDebug(result);
      setTab("providers");
      setStatus(result.summary || "Stitch provider debug loaded.");
    } catch (err) {
      setStatus(err.message || "Could not load Stitch provider debug.");
    } finally {
      setBusy("");
    }
  }

  async function executeSharedTool(event) {
    event.preventDefault();
    setBusy("tool-execute");
    setStatus("");
    try {
      const payload = parseResult(toolForm.payload);
      const result = await api("/tools/execute", {
        method: "POST",
        body: JSON.stringify({ name: toolForm.name, payload })
      });
      setToolResult(result);
      if (result.trace_id) await openTrace(result.trace_id);
      setStatus(result.summary || "Tool execution recorded.");
      await refresh();
    } catch (err) {
      setStatus(err.message || "Tool execution failed.");
    } finally {
      setBusy("");
    }
  }

  async function validateContract(event) {
    event.preventDefault();
    setBusy("contract-validate");
    setStatus("");
    try {
      const result = await api("/structured-output/validate", {
        method: "POST",
        body: JSON.stringify({ kind: contractForm.kind, payload: parseResult(contractForm.payload) })
      });
      setContractResult(result);
      setStatus(result.ok ? "Structured output contract passed." : "Structured output contract failed.");
    } catch (err) {
      setStatus(err.message || "Structured output validation failed.");
    } finally {
      setBusy("");
    }
  }

  async function saveStyleProfile(event) {
    event.preventDefault();
    setBusy("style");
    try {
      const profile = await api("/friday-os/style-profiles", {
        method: "POST",
        body: JSON.stringify({
          ...styleForm,
          required_paths: lines(styleForm.required_paths),
          forbidden_paths: [],
          rules: lines(styleForm.rules),
          evidence: ["Saved from Friday Studio"]
        })
      });
      setStatus(`Saved style profile: ${profile.name || profile.id}`);
      await refresh();
    } catch (err) {
      setStatus(err.message || "Style profile save failed.");
    } finally {
      setBusy("");
    }
  }

  async function applyStyle(profileId) {
    const root = selected?.root || form.root;
    if (!root) return setStatus("Select a run or enter a root before applying a style profile.");
    setBusy(profileId);
    try {
      const result = await api("/friday-os/style-profiles/apply", { method: "POST", body: JSON.stringify({ root, profile_id: profileId }) });
      setStatus(result.summary || "Style profile applied.");
      await refresh();
    } catch (err) {
      setStatus(err.message || "Style profile apply failed.");
    } finally {
      setBusy("");
    }
  }

  async function runJudgment(endpoint, body, label) {
    setBusy(endpoint);
    setStatus("");
    try {
      const result = await api(endpoint, { method: "POST", body: JSON.stringify(body) });
      setJudgmentResult({ endpoint, result });
      setTab("judgment");
      setStatus(result.summary || `${label} complete.`);
      await refresh();
    } catch (err) {
      setStatus(err.message || `${label} failed.`);
    } finally {
      setBusy("");
    }
  }

  async function reviewOutput() {
    await runJudgment("/judgment/review", judgmentPayload(), "Judgment review");
  }

  async function challengeClaim() {
    await runJudgment("/judgment/claims", judgmentPayload(), "Claim challenge");
  }

  async function runSelfReview() {
    await runJudgment("/judgment/self-review", judgmentPayload(), "Self-review");
  }

  async function debugFailure() {
    await runJudgment("/judgment/debug", { failure: judgmentForm.failure || judgmentForm.text, root: selected?.root || form.root, remember: true }, "Failure autopsy");
  }

  async function saveLesson() {
    if (!judgmentForm.lesson.trim()) return;
    await runJudgment("/judgment/taste", { correction: judgmentForm.lesson, domain: judgmentForm.domain || "coding", root: selected?.root || form.root, evidence: ["Friday Studio Judgment Center"] }, "Taste lesson");
  }

  async function researchIdeas(event) {
    event.preventDefault();
    setBusy("ideas");
    setStatus("");
    try {
      const result = await api("/project-ideas/research", {
        method: "POST",
        body: JSON.stringify({
          ...ideaForm,
          root: selected?.root || form.root,
          limit: Number(ideaForm.limit || 5),
          max_sources: Number(ideaForm.max_sources || 8),
          create_files: true
        })
      });
      setIdeaResult(result);
      setTab("ideas");
      setStatus(result.summary || "Project idea research complete.");
      await refresh();
    } catch (err) {
      setStatus(err.message || "Project idea research failed.");
    } finally {
      setBusy("");
    }
  }

  async function runAutoEval(action) {
    setBusy(`autoeval-${action}`);
    setStatus("");
    const payload = {
      ...autoevalForm,
      root: autoevalForm.root || selected?.root || form.root,
      request: autoevalForm.request || selected?.request || form.request || "Improve this project using objective AutoEval evidence.",
      target_files: lines(autoevalForm.target_files),
      min_delta: Number(autoevalForm.min_delta || 0),
      stack: selected?.stack || selected?.architecture?.stack || {},
      timeout: 180
    };
    try {
      const endpoint = action === "program" ? "/autoeval/program" : action === "score" ? "/autoeval/score" : "/autoeval/run";
      const result = await api(endpoint, { method: "POST", body: JSON.stringify(payload) });
      setAutoevalResult(result);
      setTab("autoeval");
      setStatus(result.summary || `AutoEval ${action} complete.`);
      await refresh();
    } catch (err) {
      setStatus(err.message || `AutoEval ${action} failed.`);
    } finally {
      setBusy("");
    }
  }

  function judgmentPayload() {
    return {
      text: judgmentForm.text,
      root: selected?.root || form.root,
      result: parseResult(judgmentForm.result, judgmentForm.text),
      claims: lines(judgmentForm.claims),
      remember: true,
      context: { selected_run_id: selected?.id || null }
    };
  }

  const gates = selected?.gate_results?.gates || selected?.production_run?.gate_results?.gates || [];
  const artifacts = selected?.artifacts || selected?.production_run?.artifacts || [];
  const screenshots = gates.map((gate) => gate.screenshot).filter(Boolean);
  const approvals = selected?.approvals || selected?.production_run?.approvals || {};
  const memory = fridayOs.memory || {};
  const integrations = fridayOs.integrations?.integrations || [];
  const profiles = fridayOs.style_profiles || [];

  return (
    <section className="friday-scroll h-full overflow-y-auto bg-friday-bg p-3 text-white" aria-label="Friday Studio">
      <div className="grid max-w-[1240px] gap-4">
        <header className="flex min-h-10 flex-wrap items-center gap-3">
          <Rocket size={18} className="text-friday-accent" />
          <h1 className="text-[18px] font-extrabold">Friday Studio</h1>
          <span className="font-mono text-[11px] text-friday-muted">{fridayOs.summary || "Persistent engineering/product studio"}</span>
          <span className="ml-auto font-mono text-[11px] text-friday-muted">{mergedRuns.length} run(s)</span>
        </header>

        <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
          <aside className="grid content-start gap-3">
            <Panel title="Start Operating Run" icon={Play}>
              <form className="grid gap-2" onSubmit={startRun}>
                <textarea className={`${FIELD_CLASS} min-h-[104px] resize-y`} value={form.request} onChange={(event) => setForm((current) => ({ ...current, request: event.target.value }))} placeholder="Build or improve a production-ready product..." required />
                <input className={FIELD_CLASS} value={form.root} onChange={(event) => setForm((current) => ({ ...current, root: event.target.value }))} placeholder="Workspace root" />
                <input className={FIELD_CLASS} value={form.target} onChange={(event) => setForm((current) => ({ ...current, target: event.target.value }))} placeholder="Target project path" />
                <div className="grid grid-cols-3 gap-2">
                  <select className={FIELD_CLASS} value={form.production_profile} onChange={(event) => setForm((current) => ({ ...current, production_profile: event.target.value }))}>
                    <option value="auto">Auto</option>
                    <option value="web-app">Web App</option>
                    <option value="mobile">Mobile</option>
                    <option value="backend">Backend</option>
                  </select>
                  <select className={FIELD_CLASS} value={form.risk_level} onChange={(event) => setForm((current) => ({ ...current, risk_level: event.target.value }))}>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                    <option value="high">High</option>
                  </select>
                  <input className={FIELD_CLASS} type="number" min="0" max="3" value={form.max_fix_attempts} onChange={(event) => setForm((current) => ({ ...current, max_fix_attempts: event.target.value }))} title="Max fix attempts" />
                </div>
                <button className={ACTION_PRIMARY} type="submit" disabled={busy === "start" || !form.request.trim()}>
                  {busy === "start" ? <Loader2 className="animate-spin" size={14} /> : <Play size={14} />}
                  Start Run
                </button>
              </form>
            </Panel>

            <Panel title="Runs" icon={GitBranch}>
              <div className="grid gap-2">
                {mergedRuns.length ? mergedRuns.map((run) => (
                  <button className={`border p-3 text-left ${selected?.id === run.id ? "border-friday-accent bg-[#202832]" : "border-friday-line bg-[#10161d] hover:border-friday-accent"}`} key={run.id} type="button" onClick={() => setSelectedId(run.id)}>
                    <span className="font-mono text-[10px] text-friday-muted">#{run.id} / {labelize(run.status)}</span>
                    <strong className="mt-1 line-clamp-2 block text-[12px]">{run.summary || run.request}</strong>
                  </button>
                )) : <p className="text-[12px] text-friday-muted">No operating run has been recorded yet.</p>}
              </div>
            </Panel>
          </aside>

          <main className="grid content-start gap-3">
            <Panel>
              <div className="grid gap-3 lg:grid-cols-[1fr_auto]">
                <div>
                  <div className="mb-2 flex flex-wrap gap-2">
                    <ReadinessBadge status={selected?.status} />
                    {selected?.architecture?.style_profile_id ? <Badge>{selected.architecture.style_profile_id}</Badge> : null}
                  </div>
                  <h2 className="text-[20px] font-extrabold">{selected?.request || "No run selected"}</h2>
                  <p className="mt-2 break-words font-mono text-[11px] text-friday-muted">{selected?.root || "Select or start a run to see proof."}</p>
                </div>
                <div className="flex flex-wrap items-start gap-2">
                  <button className={ACTION_SECONDARY} type="button" onClick={() => runAction("pause", { note: "Paused from Friday Studio" })} disabled={!selected || Boolean(busy)}><Pause size={13} /> Pause</button>
                  <button className={ACTION_SECONDARY} type="button" onClick={() => runAction("resume")} disabled={!selected || Boolean(busy)}><Play size={13} /> Resume</button>
                  <button className={ACTION_SECONDARY} type="button" onClick={() => runAction("rerun-gates", { failed_only: true })} disabled={!selected || Boolean(busy)}><RefreshCw size={13} /> Rerun Failed</button>
                  {selected?.metadata?.trace_id ? <button className={ACTION_SECONDARY} type="button" onClick={() => openTrace(selected.metadata.trace_id)} disabled={Boolean(busy)}><GitBranch size={13} /> Trace</button> : null}
                  {selected?.preview_url ? <a className={ACTION_PRIMARY} href={selected.preview_url} target="_blank" rel="noreferrer"><ExternalLink size={13} /> Preview</a> : null}
                </div>
              </div>
            </Panel>

            <div className="grid gap-2 md:grid-cols-4">
              <Metric label="Technical" value={selected?.technical_ready ? "ready" : "not ready"} warn={!selected?.technical_ready} />
              <Metric label="Market" value={selected?.market_ready ? "ready" : "blocked"} warn={!selected?.market_ready} />
              <Metric label="Gates" value={String(gates.length)} warn={!gates.length} />
              <Metric label="Gaps" value={String((selected?.gaps || []).length)} warn={(selected?.gaps || []).length > 0} />
            </div>

            <nav className="flex flex-wrap gap-2" aria-label="Friday Studio sections">
              {TABS.map(([id, label]) => (
                <button className={`min-h-9 border px-3 font-mono text-[11px] ${tab === id ? "border-friday-accent bg-[#202832] text-friday-accent" : "border-friday-line bg-[#10161d] text-[#dfe9f6] hover:border-friday-accent"}`} key={id} type="button" onClick={() => setTab(id)}>
                  {label}
                </button>
              ))}
            </nav>

            {tab === "runs" ? <RunSteps run={selected} /> : null}
            {tab === "spine" ? <ExecutionSpineCenter modelGateway={modelGateway} toolRegistry={toolRegistry} traceState={traceState} traceDetail={traceDetail} toolForm={toolForm} setToolForm={setToolForm} toolResult={toolResult} contractForm={contractForm} setContractForm={setContractForm} contractResult={contractResult} onExecuteTool={executeSharedTool} onValidateContract={validateContract} onOpenTrace={openTrace} busy={busy} /> : null}
            {tab === "providers" ? <ProviderDebugCenter debug={providerDebug} selected={selected} onRefresh={refreshProviderDebug} onOpenArtifact={openArtifact} busy={busy} /> : null}
            {tab === "autoeval" ? <AutoEvalCenter autoeval={autoeval} form={autoevalForm} setForm={setAutoevalForm} result={autoevalResult} onRun={runAutoEval} onOpenArtifact={openArtifact} busy={busy} /> : null}
            {tab === "ideas" ? <ProjectIdeasCenter projectIdeas={projectIdeas} form={ideaForm} setForm={setIdeaForm} result={ideaResult} onResearch={researchIdeas} onOpenArtifact={openArtifact} busy={busy} /> : null}
            {tab === "judgment" ? <JudgmentCenter judgment={judgment} form={judgmentForm} setForm={setJudgmentForm} result={judgmentResult} onReview={reviewOutput} onChallenge={challengeClaim} onSelfReview={runSelfReview} onDebug={debugFailure} onSaveLesson={saveLesson} busy={busy} /> : null}
            {tab === "gates" ? <GateResults gates={gates} /> : null}
            {tab === "proof" ? <ArtifactViewer artifacts={artifacts} screenshots={screenshots} artifact={artifact} onOpen={openArtifact} busy={busy} /> : null}
            {tab === "memory" ? <MemoryCenter memory={memory} /> : null}
            {tab === "styles" ? <StyleProfiles profiles={profiles} form={styleForm} setForm={setStyleForm} onSave={saveStyleProfile} onApply={applyStyle} busy={busy} /> : null}
            {tab === "integrations" ? <IntegrationCenter integrations={integrations} /> : null}
            {tab === "authority" ? <AuthorityCenter control={autonomyControl} onSetMode={setAuthorityMode} busy={busy} /> : null}
            {tab === "approvals" ? <ApprovalCenter approvals={approvals} onApprove={approve} busy={busy} /> : null}
            {tab === "launch" ? <LaunchCenter run={selected} /> : null}
          </main>
        </div>
      </div>
      {status ? <div className="fixed bottom-5 right-5 z-20 max-w-[440px] border border-[#45678c] bg-[#9fcaff] px-4 py-3 text-[13px] font-semibold text-[#07111d] shadow-[0_16px_40px_rgba(0,0,0,.32)]">{status}</div> : null}
    </section>
  );
}

function ProjectIdeasCenter({ projectIdeas, form, setForm, result, onResearch, onOpenArtifact, busy }) {
  const run = result || projectIdeas?.latest || {};
  const ideas = run.ideas || [];
  const sources = run.sources || [];
  const artifacts = run.artifacts || [];
  return (
    <div className="grid gap-3 xl:grid-cols-[420px_minmax(0,1fr)]">
      <div className="grid content-start gap-3">
        <Panel title="Research Project Ideas" icon={Lightbulb}>
          <form className="grid gap-2" onSubmit={onResearch}>
            <textarea className={`${FIELD_CLASS} min-h-28 resize-y`} value={form.context} onChange={(event) => setForm((current) => ({ ...current, context: event.target.value }))} placeholder="What kind of products should Friday research? Example: AI tools for SMB operations, founders, freelancers..." />
            <input className={FIELD_CLASS} value={form.audience} onChange={(event) => setForm((current) => ({ ...current, audience: event.target.value }))} placeholder="Target audience" />
            <div className="grid grid-cols-2 gap-2">
              <input className={FIELD_CLASS} type="number" min="1" max="8" value={form.limit} onChange={(event) => setForm((current) => ({ ...current, limit: event.target.value }))} title="Idea limit" />
              <input className={FIELD_CLASS} type="number" min="3" max="20" value={form.max_sources} onChange={(event) => setForm((current) => ({ ...current, max_sources: event.target.value }))} title="Max sources" />
            </div>
            <button className={ACTION_PRIMARY} type="submit" disabled={busy === "ideas"}>
              {busy === "ideas" ? <Loader2 className="animate-spin" size={14} /> : <Search size={14} />}
              Research Ideas
            </button>
          </form>
        </Panel>

        <Panel title="Research Policy" icon={ShieldCheck}>
          <InfoBlock label="No Guessing" value={projectIdeas?.research_policy?.no_guessing || "Friday must source demand before recommending project ideas."} />
          <InfoBlock label="Minimum Evidence" value={projectIdeas?.research_policy?.minimum_evidence || "At least three demand-bearing sources and two signal categories."} />
        </Panel>

        <Panel title="Idea Artifacts" icon={FileText}>
          <div className="grid gap-2">
            {artifacts.map((path) => (
              <button className="flex min-h-10 items-center gap-2 border border-friday-line bg-[#10161d] px-3 text-left font-mono text-[10px] text-[#dfe9f6] hover:border-friday-accent" key={path} type="button" onClick={() => onOpenArtifact(path)} disabled={busy === path}>
                {busy === path ? <Loader2 className="animate-spin" size={13} /> : <FileText size={13} />}
                <span className="truncate">{path}</span>
              </button>
            ))}
            {!artifacts.length ? <p className="text-[12px] text-friday-muted">No idea research artifacts yet.</p> : null}
          </div>
        </Panel>
      </div>

      <div className="grid content-start gap-3">
        <Panel title="Research Result" icon={Search}>
          <div className="grid gap-3 md:grid-cols-3">
            <InfoBlock label="Status" value={run.status || "not researched"} />
            <InfoBlock label="Sources" value={String(sources.length)} />
            <InfoBlock label="Signals" value={String((run.signals || []).length)} />
          </div>
          <p className="mt-3 text-[13px] text-[#dfe9f6]">{run.summary || "Run research before Friday recommends what to build next."}</p>
        </Panel>

        <Panel title="Idea Shortlist" icon={Lightbulb}>
          <div className="grid gap-2">
            {ideas.map((idea) => (
              <div className="grid gap-2 border border-friday-line bg-[#10161d] p-3" key={idea.id}>
                <div className="flex flex-wrap items-center gap-2">
                  <strong className="text-[14px]">{idea.title}</strong>
                  <Badge>{String(idea.confidence || "0")} confidence</Badge>
                  <Badge>{idea.evidence_count} source(s)</Badge>
                </div>
                <p className="text-[12px] text-[#dfe9f6]">{idea.problem}</p>
                <p className="text-[12px] text-friday-muted">{idea.product_wedge}</p>
              </div>
            ))}
            {!ideas.length ? <p className="text-[12px] text-friday-muted">No project ideas recommended until research evidence is sufficient.</p> : null}
          </div>
        </Panel>

        <Panel title="Source Register" icon={Database}>
          <div className="grid gap-2">
            {sources.slice(0, 8).map((source) => (
              <div className="border border-friday-line bg-[#10161d] p-3" key={source.id}>
                <strong className="text-[12px]">{source.title}</strong>
                <p className="mt-1 text-[12px] text-friday-muted">{source.snippet}</p>
                {source.url ? <a className="mt-2 inline-flex text-[11px] text-friday-accent" href={source.url} target="_blank" rel="noreferrer">Open source</a> : null}
              </div>
            ))}
            {!sources.length ? <p className="text-[12px] text-friday-muted">No sources collected yet.</p> : null}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function AutoEvalCenter({ autoeval, form, setForm, result, onRun, onOpenArtifact, busy }) {
  const latest = result || autoeval?.latest || {};
  const recent = autoeval?.recent || [];
  const artifacts = [latest.program_path, latest.config_path, ...(latest.artifacts || [])].filter(Boolean);
  return (
    <div className="grid gap-3 xl:grid-cols-[420px_minmax(0,1fr)]">
      <div className="grid content-start gap-3">
        <Panel title="AutoEval Lab" icon={Brain}>
          <div className="grid gap-3">
            <textarea className={`${FIELD_CLASS} min-h-24 resize-y`} value={form.request} onChange={(event) => setForm((current) => ({ ...current, request: event.target.value }))} placeholder="Objective for the experiment or score run" />
            <input className={FIELD_CLASS} value={form.root} onChange={(event) => setForm((current) => ({ ...current, root: event.target.value }))} placeholder="Project root; selected run root is used when blank" />
            <select className={FIELD_CLASS} value={form.mode} onChange={(event) => setForm((current) => ({ ...current, mode: event.target.value }))}>
              <option value="product_quality">Product Quality</option>
              <option value="design_quality">Design Quality</option>
              <option value="frontend_quality">Frontend Quality</option>
              <option value="coding_quality">Coding Quality</option>
            </select>
            <textarea className={`${FIELD_CLASS} min-h-20 resize-y font-mono`} value={form.target_files} onChange={(event) => setForm((current) => ({ ...current, target_files: event.target.value }))} placeholder="Constrained files, one per line" />
            <input className={FIELD_CLASS} value={form.experiment_command} onChange={(event) => setForm((current) => ({ ...current, experiment_command: event.target.value }))} placeholder="Optional safe command, e.g. python improve.py" />
            <div className="grid grid-cols-3 gap-2">
              <input className={FIELD_CLASS} type="number" min="0" max="100" step="0.5" value={form.min_delta} onChange={(event) => setForm((current) => ({ ...current, min_delta: event.target.value }))} title="Minimum improvement" />
              <label className="flex min-h-10 items-center gap-2 border border-friday-line bg-[#10161d] px-3 font-mono text-[11px] text-[#dfe9f6]">
                <input type="checkbox" checked={Boolean(form.apply_fixes)} onChange={(event) => setForm((current) => ({ ...current, apply_fixes: event.target.checked }))} />
                Fixes
              </label>
              <label className="flex min-h-10 items-center gap-2 border border-friday-line bg-[#10161d] px-3 font-mono text-[11px] text-[#dfe9f6]">
                <input type="checkbox" checked={Boolean(form.run_gates)} onChange={(event) => setForm((current) => ({ ...current, run_gates: event.target.checked }))} />
                Gates
              </label>
            </div>
            <div className="flex flex-wrap gap-2">
              <button className={ACTION_SECONDARY} type="button" onClick={() => onRun("program")} disabled={busy === "autoeval-program"}>{busy === "autoeval-program" ? <Loader2 className="animate-spin" size={14} /> : <FileText size={14} />} Program</button>
              <button className={ACTION_SECONDARY} type="button" onClick={() => onRun("score")} disabled={busy === "autoeval-score"}>{busy === "autoeval-score" ? <Loader2 className="animate-spin" size={14} /> : <ClipboardCheck size={14} />} Score</button>
              <button className={ACTION_PRIMARY} type="button" onClick={() => onRun("run")} disabled={busy === "autoeval-run"}>{busy === "autoeval-run" ? <Loader2 className="animate-spin" size={14} /> : <Play size={14} />} Run Experiment</button>
            </div>
          </div>
        </Panel>
        <Panel title="Recent Runs" icon={GitBranch}>
          <div className="grid gap-2">
            {recent.length ? recent.map((item) => (
              <div className="border border-friday-line bg-[#10161d] p-3" key={item.id || item.run_key || item.timestamp}>
                <div className="flex items-center gap-2">
                  <Badge>{item.status || "recorded"}</Badge>
                  <span className="font-mono text-[10px] text-friday-muted">{item.timestamp}</span>
                </div>
                <p className="mt-2 text-[12px] text-[#dfe9f6]">{item.summary}</p>
              </div>
            )) : <p className="text-[12px] text-friday-muted">No AutoEval runs yet.</p>}
          </div>
        </Panel>
      </div>
      <div className="grid content-start gap-3">
        <Panel title="Latest Result" icon={ClipboardCheck}>
          <div className="grid gap-3 md:grid-cols-4">
            <Metric label="Status" value={latest.status || "none"} warn={latest.status === "reverted"} />
            <Metric label="Baseline" value={scoreLabel(latest.baseline_score ?? latest.baseline?.score)} warn={false} />
            <Metric label="Final" value={scoreLabel(latest.final_score ?? latest.score ?? latest.final?.score)} warn={false} />
            <Metric label="Delta" value={scoreDelta(latest.improvement)} warn={Number(latest.improvement || 0) < 0} />
          </div>
          <p className="mt-3 text-[13px] text-[#dfe9f6]">{latest.summary || autoeval?.summary || "Create an AutoEval program or score a project to start."}</p>
        </Panel>
        <Panel title="Score Breakdown" icon={SlidersHorizontal}>
          <pre className="max-h-[360px] overflow-auto whitespace-pre-wrap border border-friday-line bg-[#080d12] p-3 font-mono text-[11px] text-[#dfe9f6]">{JSON.stringify(latest.breakdown || latest.final?.breakdown || latest.scores || {}, null, 2)}</pre>
        </Panel>
        <Panel title="Artifacts" icon={FileText}>
          <div className="flex flex-wrap gap-2">
            {artifacts.length ? artifacts.map((path) => (
              <button className="flex min-h-10 items-center gap-2 border border-friday-line bg-[#10161d] px-3 text-left font-mono text-[10px] text-[#dfe9f6] hover:border-friday-accent" key={path} type="button" onClick={() => onOpenArtifact(path)} disabled={busy === path}>
                <FileText size={13} />
                <span className="max-w-[260px] truncate">{path}</span>
              </button>
            )) : <p className="text-[12px] text-friday-muted">No AutoEval artifacts yet.</p>}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function scoreLabel(value) {
  if (value === undefined || value === null || value === "") return "n/a";
  return `${Number(value).toFixed(1)}`;
}

function scoreDelta(value) {
  const numeric = Number(value || 0);
  return `${numeric >= 0 ? "+" : ""}${numeric.toFixed(1)}`;
}

function ProviderDebugCenter({ debug, selected, onRefresh, onOpenArtifact, busy }) {
  const latest = debug?.latest || {};
  const provider = debug?.provider_status || {};
  const reports = debug?.reports || [];
  const attempts = debug?.attempts || [];
  const rawManifests = debug?.raw_manifests || [];
  const artifactItems = [
    ...reports.map((item) => item.path),
    ...attempts.map((item) => item.path),
    ...rawManifests.map((item) => item.path),
    ...((latest?.artifacts || []).filter(Boolean))
  ];
  return (
    <div className="grid gap-3 xl:grid-cols-[420px_minmax(0,1fr)]">
      <div className="grid content-start gap-3">
        <Panel title="Stitch Health" icon={SlidersHorizontal}>
          <div className="grid gap-3">
            <button className={ACTION_PRIMARY} type="button" onClick={onRefresh} disabled={busy === "provider-debug"}>
              {busy === "provider-debug" ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />}
              Refresh Stitch Debug
            </button>
            <InfoBlock label="Selected Root" value={debug?.root || selected?.root || "No root selected."} />
            <InfoBlock label="Configured" value={provider?.ready ? "ready" : provider?.reason || "unknown"} />
            <InfoBlock label="Fallback Policy" value={debug?.fallback_policy || "not loaded"} />
            <InfoBlock label="Summary" value={debug?.summary || "Refresh to inspect Stitch timing, raw responses, and fallback state."} />
          </div>
        </Panel>

        <Panel title="Latest Provider Result" icon={ClipboardCheck}>
          <div className="grid gap-3">
            <Metric label="Status" value={latest?.status || "none"} warn={!latest?.ok} />
            <Metric label="Attempts" value={String(latest?.attempt_count || 0)} warn={Number(latest?.attempt_count || 0) > 1 || !latest?.attempt_count} />
            <InfoBlock label="Source" value={latest?.ok ? "Google Stitch" : latest?.failure_reason ? "Stitch failed or returned unusable output" : "No run recorded"} />
            <InfoBlock label="Model" value={latest?.model_id || provider?.model || "unknown"} />
            <InfoBlock label="Project ID" value={latest?.project_id || "not returned"} />
            <InfoBlock label="Screen ID" value={latest?.screen_id || "not returned"} />
            <InfoBlock label="Failure Reason" value={latest?.failure_reason || "none"} />
          </div>
        </Panel>
      </div>

      <div className="grid content-start gap-3">
        <Panel title="Attempt Timeline" icon={GitBranch}>
          <div className="grid gap-2">
            {(latest?.attempts || attempts.map((item) => item.data) || []).map((attempt, index) => (
              <StatusRow
                key={`${attempt?.attempt || index}-${attempt?.status || "attempt"}`}
                label={`Attempt ${attempt?.attempt || index + 1}: ${attempt?.purpose || "base"}`}
                status={attempt?.status || "recorded"}
                summary={`${attempt?.summary || attempt?.failure_reason || "No summary."} ${attempt?.duration_ms ? `(${attempt.duration_ms}ms)` : ""}`}
              />
            ))}
            {!latest?.attempts?.length && !attempts.length ? <p className="text-[12px] text-friday-muted">No Stitch attempts recorded for this root yet.</p> : null}
          </div>
        </Panel>

        <Panel title="Provider Artifacts" icon={FileText}>
          <div className="grid gap-2">
            {dedupeStrings(artifactItems).slice(0, 32).map((path) => (
              <button className="flex min-h-10 items-center gap-2 border border-friday-line bg-[#10161d] px-3 text-left font-mono text-[10px] text-[#dfe9f6] hover:border-friday-accent" key={path} type="button" onClick={() => onOpenArtifact(path)} disabled={busy === path}>
                {busy === path ? <Loader2 className="animate-spin" size={13} /> : <FileText size={13} />}
                <span className="truncate">{path}</span>
              </button>
            ))}
            {!artifactItems.length ? <p className="text-[12px] text-friday-muted">No Stitch debug artifacts found yet.</p> : null}
          </div>
        </Panel>

        <Panel title="Raw Debug Payload" icon={Database}>
          <JsonBlock value={debug || {}} />
        </Panel>
      </div>
    </div>
  );
}

function ExecutionSpineCenter({
  modelGateway,
  toolRegistry,
  traceState,
  traceDetail,
  toolForm,
  setToolForm,
  toolResult,
  contractForm,
  setContractForm,
  contractResult,
  onExecuteTool,
  onValidateContract,
  onOpenTrace,
  busy
}) {
  const tools = toolRegistry?.tools || [];
  const traces = traceState?.traces || [];
  const nativeProviders = Object.entries(modelGateway?.native_gateway?.provider_limits || {});
  const adapters = Object.values(modelGateway?.langchain_adapters?.adapters || {});
  return (
    <div className="grid gap-3 xl:grid-cols-[420px_minmax(0,1fr)]">
      <div className="grid content-start gap-3">
        <Panel title="Model Gateway" icon={Brain}>
          <div className="grid gap-3">
            <InfoBlock label="Active Layer" value={modelGateway?.layer || "friday_internal_model_gateway"} />
            <InfoBlock label="Decision" value={modelGateway?.summary || "Friday uses its native model gateway, with LangChain adapters only where useful."} />
            <div className="grid gap-2">
              {(modelGateway?.architecture || []).map((item, index) => (
                <StatusRow key={`${index}-${item}`} label={`${index + 1}. ${item}`} status={index < 2 ? "passed" : "planned"} summary={index === 1 ? "Provider routing, fallback, approval, logs, and traces stay custom." : ""} />
              ))}
            </div>
          </div>
        </Panel>

        <Panel title="Shared Tool Executor" icon={SlidersHorizontal}>
          <form className="grid gap-2" onSubmit={onExecuteTool}>
            <select className={FIELD_CLASS} value={toolForm.name} onChange={(event) => setToolForm((current) => ({ ...current, name: event.target.value }))}>
              {tools.map((tool) => <option key={tool.name} value={tool.name}>{tool.name}</option>)}
              {!tools.length ? <option value="documents.read">documents.read</option> : null}
            </select>
            <textarea className={`${FIELD_CLASS} min-h-28 resize-y font-mono`} value={toolForm.payload} onChange={(event) => setToolForm((current) => ({ ...current, payload: event.target.value }))} />
            <button className={ACTION_PRIMARY} type="submit" disabled={busy === "tool-execute"}>
              {busy === "tool-execute" ? <Loader2 className="animate-spin" size={14} /> : <Play size={14} />}
              Execute Tool
            </button>
          </form>
          {toolResult ? <JsonBlock value={toolResult} /> : null}
        </Panel>

        <Panel title="Structured Output Contract" icon={ClipboardCheck}>
          <form className="grid gap-2" onSubmit={onValidateContract}>
            <select className={FIELD_CLASS} value={contractForm.kind} onChange={(event) => setContractForm((current) => ({ ...current, kind: event.target.value }))}>
              <option value="agent_result">agent_result</option>
              <option value="design_brief">design_brief</option>
              <option value="gate_report">gate_report</option>
              <option value="fix_plan">fix_plan</option>
            </select>
            <textarea className={`${FIELD_CLASS} min-h-28 resize-y font-mono`} value={contractForm.payload} onChange={(event) => setContractForm((current) => ({ ...current, payload: event.target.value }))} />
            <button className={ACTION_SECONDARY} type="submit" disabled={busy === "contract-validate"}>
              {busy === "contract-validate" ? <Loader2 className="animate-spin" size={14} /> : <ShieldCheck size={14} />}
              Validate
            </button>
          </form>
          {contractResult ? <JsonBlock value={contractResult} /> : null}
        </Panel>
      </div>

      <div className="grid content-start gap-3">
        <Panel title="Provider Routing" icon={GitBranch}>
          <div className="grid gap-2 md:grid-cols-2">
            {nativeProviders.map(([provider, payload]) => (
              <ProviderCard key={provider} provider={provider} payload={payload} />
            ))}
            {!nativeProviders.length ? <p className="text-[12px] text-friday-muted">No provider routing snapshot loaded.</p> : null}
          </div>
        </Panel>

        <Panel title="LangChain Adapter Layer" icon={Database}>
          <div className="mb-3 grid gap-3 md:grid-cols-2">
            <InfoBlock label="Ready" value={String(Boolean(modelGateway?.langchain_adapters?.ready))} />
            <InfoBlock label="Core" value={modelGateway?.langchain_adapters?.langchain_core_available ? "installed" : "not installed"} />
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            {adapters.map((adapter) => (
              <div className="border border-friday-line bg-[#10161d] p-3" key={adapter.provider}>
                <div className="flex items-center gap-2">
                  <strong className="text-[12px]">{adapter.provider}</strong>
                  <Badge>{adapter.ready ? "ready" : "blocked"}</Badge>
                </div>
                <p className="mt-2 text-[12px] text-friday-muted">{adapter.reason}</p>
                <p className="mt-2 font-mono text-[10px] text-friday-muted">{adapter.package} / {adapter.model}</p>
              </div>
            ))}
            {!adapters.length ? <p className="text-[12px] text-friday-muted">No LangChain adapter status loaded.</p> : null}
          </div>
        </Panel>

        <Panel title="Trace Explorer" icon={Search}>
          <div className="grid gap-2 lg:grid-cols-[280px_minmax(0,1fr)]">
            <div className="grid content-start gap-2">
              {traces.map((trace) => (
                <button className="grid gap-1 border border-friday-line bg-[#10161d] p-3 text-left hover:border-friday-accent" key={trace.trace_id} type="button" onClick={() => onOpenTrace(trace.trace_id)} disabled={busy === `trace:${trace.trace_id}`}>
                  <span className="truncate font-mono text-[10px] text-friday-accent">{trace.trace_id}</span>
                  <strong className="line-clamp-2 text-[12px]">{trace.title || trace.kind}</strong>
                  <span className="font-mono text-[10px] text-friday-muted">{trace.kind}</span>
                </button>
              ))}
              {!traces.length ? <p className="text-[12px] text-friday-muted">No traces recorded yet.</p> : null}
            </div>
            <div className="min-w-0 border border-friday-line bg-[#10161d] p-3">
              {traceDetail ? (
                <div className="grid gap-3">
                  <InfoBlock label="Trace" value={traceDetail.trace_id} />
                  <InfoBlock label="Root" value={traceDetail.root || "No root recorded."} />
                  <div className="grid gap-2">
                    {(traceDetail.events || []).map((event) => (
                      <StatusRow key={event.id} label={`${event.event_type}: ${event.title}`} status={event.status || "recorded"} summary={event.summary} />
                    ))}
                  </div>
                </div>
              ) : <p className="text-[12px] text-friday-muted">Open a trace to inspect phase, tool, approval, and proof events.</p>}
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function JudgmentCenter({ judgment, form, setForm, result, onReview, onChallenge, onSelfReview, onDebug, onSaveLesson, busy }) {
  const payload = result?.result || {};
  const trace = judgment?.loop || [];
  const intent = payload.intent || payload.judgment || judgment?.sample_judgment || {};
  const evidence = payload.evidence || payload.output_review?.evidence || {};
  const gaps = payload.gaps || payload.blocked || payload.self_review?.gaps || [];
  const hypothesis = payload.hypothesis || payload.autopsy?.metadata?.hypothesis || {};
  return (
    <div className="grid gap-3 xl:grid-cols-[420px_minmax(0,1fr)]">
      <div className="grid content-start gap-3">
        <Panel title="Judgment Trace" icon={Brain}>
          <div className="grid gap-2">
            {trace.map((step, index) => <StatusRow key={step} label={`${index + 1}. ${labelize(step)}`} status="passed" summary={step === "infer_real_intent" ? "Intent is classified before action." : "Judgment step active."} />)}
            {!trace.length ? <p className="text-[12px] text-friday-muted">{judgment?.summary || "Judgment kernel has no snapshot yet."}</p> : null}
          </div>
        </Panel>

        <Panel title="Run Judgment" icon={ClipboardCheck}>
          <div className="grid gap-2">
            <textarea className={`${FIELD_CLASS} min-h-24 resize-y`} value={form.text} onChange={(event) => setForm((current) => ({ ...current, text: event.target.value }))} placeholder="User request, final answer, or agent output" />
            <textarea className={`${FIELD_CLASS} min-h-28 resize-y font-mono`} value={form.result} onChange={(event) => setForm((current) => ({ ...current, result: event.target.value }))} placeholder='{"summary":"...","artifacts":[],"gate_results":{}}' />
            <textarea className={`${FIELD_CLASS} min-h-20 resize-y font-mono`} value={form.claims} onChange={(event) => setForm((current) => ({ ...current, claims: event.target.value }))} placeholder="Claims, one per line" />
            <div className="grid grid-cols-3 gap-2">
              <button className={ACTION_PRIMARY} type="button" onClick={onReview} disabled={Boolean(busy)}>{busy === "/judgment/review" ? <Loader2 className="animate-spin" size={14} /> : <Search size={14} />} Review</button>
              <button className={ACTION_SECONDARY} type="button" onClick={onChallenge} disabled={Boolean(busy)}>{busy === "/judgment/claims" ? <Loader2 className="animate-spin" size={14} /> : <AlertTriangle size={14} />} Challenge</button>
              <button className={ACTION_SECONDARY} type="button" onClick={onSelfReview} disabled={Boolean(busy)}>{busy === "/judgment/self-review" ? <Loader2 className="animate-spin" size={14} /> : <ShieldCheck size={14} />} Self Review</button>
            </div>
          </div>
        </Panel>

        <Panel title="Failure Autopsy" icon={Lightbulb}>
          <div className="grid gap-2">
            <textarea className={`${FIELD_CLASS} min-h-24 resize-y font-mono`} value={form.failure} onChange={(event) => setForm((current) => ({ ...current, failure: event.target.value }))} placeholder="Paste a failing build, test, audit, or browser log" />
            <button className={ACTION_SECONDARY} type="button" onClick={onDebug} disabled={Boolean(busy) || (!form.failure.trim() && !form.text.trim())}>{busy === "/judgment/debug" ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />} Debug</button>
          </div>
        </Panel>

        <Panel title="Save Lesson" icon={Save}>
          <div className="grid gap-2">
            <textarea className={`${FIELD_CLASS} min-h-20 resize-y`} value={form.lesson} onChange={(event) => setForm((current) => ({ ...current, lesson: event.target.value }))} placeholder="Preference, convention, or never-again rule" />
            <select className={FIELD_CLASS} value={form.domain} onChange={(event) => setForm((current) => ({ ...current, domain: event.target.value }))}>
              <option value="coding">Coding</option>
              <option value="ui">UI</option>
              <option value="behavior">Behavior</option>
              <option value="general">General</option>
            </select>
            <button className={ACTION_SECONDARY} type="button" onClick={onSaveLesson} disabled={Boolean(busy) || !form.lesson.trim()}>{busy === "/judgment/taste" ? <Loader2 className="animate-spin" size={14} /> : <Save size={14} />} Save Lesson</button>
          </div>
        </Panel>
      </div>

      <div className="grid content-start gap-3">
        <Panel title="Intent Inference" icon={Brain}>
          <div className="grid gap-3 md:grid-cols-2">
            <InfoBlock label="Intent" value={intent.user_intent || intent.intent || "No judgment run yet."} />
            <InfoBlock label="Action" value={intent.recommended_action || "No action selected."} />
            <InfoBlock label="Style" value={intent.project_style || intent.referenced_style || "No style profile inferred."} />
            <InfoBlock label="Risk" value={intent.risk_level || "unknown"} />
          </div>
        </Panel>

        <Panel title="Shallow Output Review" icon={Search}>
          <div className="grid gap-3 md:grid-cols-2">
            <InfoBlock label="Evidence" value={evidence.summary || payload.summary || "No evidence review yet."} />
            <InfoBlock label="Accepted" value={String(payload.ok ?? payload.accepted ?? false)} />
          </div>
          <ListBlock items={payload.output_review?.gaps || evidence.shallow_output?.reasons || []} empty="No shallow-output gaps recorded." />
        </Panel>

        <Panel title="Readiness Claims" icon={ShieldCheck}>
          <ListBlock items={payload.honesty?.blocked || payload.claim_review?.blocked || payload.blocked || []} empty="No blocked readiness claims recorded." />
        </Panel>

        <Panel title="Debug Hypotheses" icon={Lightbulb}>
          <div className="grid gap-3 md:grid-cols-2">
            <InfoBlock label="Next Probe" value={hypothesis.next_probe || "No failure analyzed."} />
            <InfoBlock label="Rerun Gate" value={hypothesis.rerun_gate || "No gate selected."} />
          </div>
          <ListBlock items={hypothesis.likely_causes || []} empty="No likely causes recorded." />
        </Panel>

        <Panel title="Final Proof" icon={FileText}>
          <ListBlock items={gaps} empty="No proof gaps in the latest judgment result." />
          <JsonBlock value={payload.safe_result || payload} />
        </Panel>
      </div>
    </div>
  );
}

function RunSteps({ run }) {
  return (
    <Panel title="Operating Loop" icon={SlidersHorizontal}>
      <div className="grid gap-2 md:grid-cols-2">
        {(run?.steps || []).map((step) => <StatusRow key={step.id} label={step.label || step.id} status={step.status} summary={step.summary} />)}
      </div>
    </Panel>
  );
}

function GateResults({ gates }) {
  return (
    <Panel title="Gate Results" icon={ShieldCheck}>
      <div className="grid gap-2 lg:grid-cols-2">
        {gates.length ? gates.map((gate, index) => <GateRow key={`${gate.id}-${index}`} gate={gate} />) : <p className="text-[12px] text-friday-muted">No gate results attached.</p>}
      </div>
    </Panel>
  );
}

function ArtifactViewer({ artifacts, screenshots, artifact, onOpen, busy }) {
  return (
    <div className="grid gap-3 lg:grid-cols-[360px_minmax(0,1fr)]">
      <Panel title="Artifacts" icon={FileText}>
        <div className="grid gap-2">
          {[...screenshots, ...artifacts].slice(-24).map((path) => (
            <button className="flex min-h-10 items-center gap-2 border border-friday-line bg-[#10161d] px-3 text-left font-mono text-[10px] text-[#dfe9f6] hover:border-friday-accent" key={path} type="button" onClick={() => onOpen(path)} disabled={busy === path}>
              {busy === path ? <Loader2 className="animate-spin" size={13} /> : <FileText size={13} />}
              <span className="truncate">{path}</span>
            </button>
          ))}
          {!artifacts.length && !screenshots.length ? <p className="text-[12px] text-friday-muted">No proof artifact path recorded.</p> : null}
        </div>
      </Panel>
      <Panel title="Artifact Viewer" icon={Search}>
        {artifact ? artifact.binary ? <img alt={artifact.path} className="max-h-[520px] max-w-full border border-friday-line" src={`data:${imageMime(artifact.path)};base64,${artifact.base64}`} /> : <pre className="friday-scroll max-h-[520px] overflow-auto whitespace-pre-wrap text-[11px] text-[#dfe9f6]">{artifact.content}</pre> : <p className="text-[12px] text-friday-muted">Open an artifact to inspect proof, logs, screenshots, or launch assets.</p>}
      </Panel>
    </div>
  );
}

function MemoryCenter({ memory }) {
  return (
    <Panel title="Memory Center" icon={Database}>
      <div className="grid gap-2">
        {(memory.recent || []).map((item) => (
          <div className="border border-friday-line bg-[#10161d] p-3" key={item.id}>
            <span className="font-mono text-[10px] uppercase text-friday-muted">{item.memory_type}</span>
            <strong className="mt-1 block text-[13px]">{item.title}</strong>
            <p className="mt-1 text-[12px] text-friday-muted">{item.content}</p>
          </div>
        ))}
        {!(memory.recent || []).length ? <p className="text-[12px] text-friday-muted">No Friday OS memory events yet.</p> : null}
      </div>
    </Panel>
  );
}

function StyleProfiles({ profiles, form, setForm, onSave, onApply, busy }) {
  return (
    <div className="grid gap-3 lg:grid-cols-[1fr_380px]">
      <Panel title="Style Profiles" icon={SlidersHorizontal}>
        <div className="grid gap-2">
          {profiles.map((profile) => (
            <div className="grid gap-2 border border-friday-line bg-[#10161d] p-3" key={profile.id}>
              <strong className="text-[13px]">{profile.name || profile.id}</strong>
              <p className="text-[12px] text-friday-muted">{profile.description}</p>
              <button className={`${ACTION_SECONDARY} w-fit`} type="button" onClick={() => onApply(profile.id)} disabled={busy === profile.id}>Apply Style</button>
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="Save Profile" icon={Save}>
        <form className="grid gap-2" onSubmit={onSave}>
          <input className={FIELD_CLASS} value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} placeholder="Profile name" required />
          <input className={FIELD_CLASS} value={form.framework} onChange={(event) => setForm((current) => ({ ...current, framework: event.target.value }))} placeholder="Framework" />
          <textarea className={`${FIELD_CLASS} min-h-20`} value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} placeholder="Description" />
          <textarea className={`${FIELD_CLASS} min-h-28`} value={form.required_paths} onChange={(event) => setForm((current) => ({ ...current, required_paths: event.target.value }))} placeholder="Required paths, one per line" />
          <textarea className={`${FIELD_CLASS} min-h-28`} value={form.rules} onChange={(event) => setForm((current) => ({ ...current, rules: event.target.value }))} placeholder="Rules, one per line" />
          <button className={ACTION_PRIMARY} type="submit" disabled={busy === "style"}>{busy === "style" ? <Loader2 className="animate-spin" size={14} /> : <Save size={14} />} Save Profile</button>
        </form>
      </Panel>
    </div>
  );
}

function IntegrationCenter({ integrations }) {
  return (
    <Panel title="Integration Center" icon={KeyRound}>
      <div className="grid gap-2 md:grid-cols-2">
        {integrations.map((item) => (
          <div className="border border-friday-line bg-[#10161d] p-3" key={item.id}>
            <div className="flex items-center gap-2">
              <strong className="text-[13px]">{item.label}</strong>
              <Badge>{item.status}</Badge>
            </div>
            <p className="mt-2 text-[12px] text-friday-muted">{(item.capabilities || []).join(", ")}</p>
            <p className="mt-2 font-mono text-[10px] text-friday-muted">Secrets: {item.secret_storage}</p>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function AuthorityCenter({ control, onSetMode, busy }) {
  const current = control?.authority_mode || "approval_gated";
  const modes = control?.available_modes?.length ? control.available_modes : [
    { id: "approval_gated", label: "Approval gated", description: "Friday pauses at approval gates before acting." },
    { id: "full_access", label: "Full access", description: "Friday can run trusted work without ask-first approvals." }
  ];
  const trustedRoots = control?.trusted_roots || [];
  const recent = control?.events || [];
  return (
    <div className="grid gap-3 xl:grid-cols-[420px_minmax(0,1fr)]">
      <div className="grid content-start gap-3">
        <Panel title="Authority Mode" icon={ShieldCheck}>
          <div className="grid gap-3">
            <Metric label="Current Mode" value={labelize(current)} warn={current !== "full_access"} />
            <InfoBlock label="Summary" value={control?.summary || "Authority control is not loaded yet."} />
            <div className="grid gap-2">
              {modes.map((mode) => {
                const active = current === mode.id;
                return (
                  <button
                    className={`grid min-h-[92px] gap-2 border p-3 text-left ${active ? "border-friday-accent bg-[#202832]" : "border-friday-line bg-[#10161d] hover:border-friday-accent"}`}
                    key={mode.id}
                    type="button"
                    onClick={() => onSetMode(mode.id)}
                    disabled={busy === `authority:${mode.id}` || active}
                  >
                    <span className="flex items-center gap-2">
                      {busy === `authority:${mode.id}` ? <Loader2 className="animate-spin text-friday-accent" size={15} /> : mode.id === "full_access" ? <KeyRound className="text-friday-accent" size={15} /> : <ShieldCheck className="text-friday-accent" size={15} />}
                      <strong className="text-[13px]">{mode.label}</strong>
                      {active ? <Badge>active</Badge> : null}
                    </span>
                    <span className="text-[12px] text-friday-muted">{mode.description}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </Panel>

        <Panel title="Trusted Scope" icon={Database}>
          <div className="grid gap-2">
            {trustedRoots.map((root) => <InfoBlock key={root} label="Root" value={root} />)}
            {!trustedRoots.length ? <p className="text-[12px] text-friday-muted">No trusted roots reported.</p> : null}
          </div>
        </Panel>
      </div>

      <div className="grid content-start gap-3">
        <Panel title="Authority Facts" icon={ClipboardCheck}>
          <div className="grid gap-3 md:grid-cols-3">
            <Metric label="Enabled" value={control?.enabled ? "yes" : "no"} warn={!control?.enabled} />
            <Metric label="Full Access" value={control?.full_access ? "on" : "off"} warn={!control?.full_access} />
            <Metric label="Hard Stops" value={String((control?.hard_stop_keys || []).length)} warn={false} />
          </div>
          <p className="mt-3 text-[12px] text-friday-muted">Block rules remain absolute. Full access only bypasses ask-first gates inside trusted project scopes.</p>
        </Panel>

        <Panel title="Ask-First Keys" icon={AlertTriangle}>
          <div className="grid gap-2 md:grid-cols-2">
            {(control?.hard_stop_keys || []).slice(0, 16).map((key) => <StatusRow key={key} label={key} status={control?.full_access ? "verified" : "blocked"} summary={control?.full_access ? "Ask gate can be bypassed in trusted full-access scope unless the permission rule is block." : "Approval-gated mode keeps this ask-first."} />)}
            {!(control?.hard_stop_keys || []).length ? <p className="text-[12px] text-friday-muted">No hard-stop keys reported.</p> : null}
          </div>
        </Panel>

        <Panel title="Mode Events" icon={GitBranch}>
          <div className="grid gap-2">
            {recent.map((event) => <StatusRow key={event.id} label={event.event_type || "authority event"} status="verified" summary={`${event.summary || ""} ${event.timestamp || ""}`} />)}
            {!recent.length ? <p className="text-[12px] text-friday-muted">No authority mode changes recorded yet.</p> : null}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function ApprovalCenter({ approvals, onApprove, busy }) {
  return (
    <Panel title="Approval Center" icon={CheckCircle2}>
      <div className="grid gap-2 md:grid-cols-2">
        {APPROVALS.map((approval) => {
          const item = approvals?.[approval.id] || {};
          return (
            <button className={`flex min-h-11 items-center gap-2 border px-3 text-left font-mono text-[11px] ${item.approved ? "border-[#2f6a57] bg-[#11251f] text-[#4dffb0]" : "border-friday-line bg-[#10161d] text-[#dfe9f6] hover:border-friday-accent"}`} key={approval.id} type="button" onClick={() => onApprove(approval.id)} disabled={item.approved || Boolean(busy)}>
              {item.approved ? <CheckCircle2 size={14} /> : <ShieldCheck size={14} />}
              {approval.label}
              <span className="ml-auto">{item.approved ? "approved" : "blocked"}</span>
            </button>
          );
        })}
      </div>
    </Panel>
  );
}

function LaunchCenter({ run }) {
  const productStudio = run?.production_run?.product_studio || run?.metadata?.production_run?.product_studio || {};
  const launchAssets = productStudio.launch_assets || {};
  return (
    <Panel title="Launch Center" icon={Rocket}>
      <div className="grid gap-3 md:grid-cols-2">
        <InfoBlock label="Summary" value={run?.summary || "No launch proof recorded."} />
        <InfoBlock label="Positioning" value={launchAssets.positioning || "Launch positioning has not been generated yet."} />
        <InfoBlock label="Preview" value={run?.preview_url || "No preview URL recorded."} />
        <InfoBlock label="Gaps" value={(run?.gaps || []).join(" / ") || "No gaps recorded."} />
      </div>
    </Panel>
  );
}

function Panel({ title, icon: Icon, children }) {
  return (
    <section className="min-w-0 overflow-hidden border border-friday-line bg-[#1a2028] p-3">
      {title ? <h2 className="mb-3 flex items-center gap-2 font-mono text-[11px] font-bold uppercase tracking-[.12em] text-[#cbd7e6]">{Icon ? <Icon size={14} className="text-friday-accent" /> : null}{title}</h2> : null}
      {children}
    </section>
  );
}

function Metric({ label, value, warn }) {
  return <section className="border border-friday-line bg-[#1a2028] p-3"><span className="font-mono text-[10px] uppercase tracking-[.08em] text-friday-muted">{label}</span><strong className={`mt-1 block text-[18px] ${warn ? "text-[#ffb56d]" : "text-friday-accent"}`}>{value}</strong></section>;
}

function ProviderCard({ provider, payload }) {
  const blocked = !payload?.configured || Number(payload?.backoff_seconds || 0) > 0;
  return (
    <div className="border border-friday-line bg-[#10161d] p-3">
      <div className="flex items-center gap-2">
        <strong className="text-[12px]">{provider}</strong>
        <Badge>{payload?.online ? "online" : "local"}</Badge>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
        <InfoBlock label="Configured" value={payload?.configured ? "yes" : "no"} />
        <InfoBlock label="Backoff" value={`${payload?.backoff_seconds || 0}s`} />
        <InfoBlock label="Concurrency" value={String(payload?.max_concurrency || 0)} />
        <InfoBlock label="Failures" value={String(payload?.failure_streak || 0)} />
      </div>
      {blocked ? <p className="mt-2 text-[11px] text-[#ffb56d]">Provider is not currently a clean first choice.</p> : null}
    </div>
  );
}

function GateRow({ gate }) {
  return <div className="grid gap-1 border border-friday-line bg-[#10161d] p-3"><div className="flex gap-2"><StatusIcon status={gate.status} /><strong className="text-[12px]">{gate.label || gate.id}</strong><Badge>{gate.group || "gate"}</Badge></div><p className="text-[12px] text-friday-muted">{gate.summary || gate.command || "No gate summary."}</p></div>;
}

function StatusRow({ label, status, summary }) {
  return <div className="grid gap-1 border border-friday-line bg-[#10161d] p-3"><div className="flex items-center gap-2"><StatusIcon status={status} /><strong className="text-[12px]">{label}</strong><span className="ml-auto font-mono text-[10px] text-friday-muted">{labelize(status)}</span></div><p className="text-[12px] text-friday-muted">{summary || "No summary recorded."}</p></div>;
}

function InfoBlock({ label, value }) {
  return <div className="border border-friday-line bg-[#10161d] p-3"><span className="font-mono text-[10px] uppercase text-friday-muted">{label}</span><p className="mt-2 text-[12px] text-[#dfe9f6]">{value}</p></div>;
}

function ListBlock({ items, empty }) {
  const list = (items || []).filter(Boolean);
  return (
    <div className="mt-3 grid gap-2">
      {list.map((item, index) => <div className="border border-friday-line bg-[#10161d] p-2 text-[12px] text-[#dfe9f6]" key={`${item}-${index}`}>{String(item)}</div>)}
      {!list.length ? <p className="text-[12px] text-friday-muted">{empty}</p> : null}
    </div>
  );
}

function JsonBlock({ value }) {
  if (!value || !Object.keys(value || {}).length) return <p className="mt-3 text-[12px] text-friday-muted">No judgment payload yet.</p>;
  return <pre className="friday-scroll mt-3 max-h-[360px] overflow-auto border border-friday-line bg-[#10161d] p-3 text-[11px] text-[#dfe9f6]">{JSON.stringify(value, null, 2)}</pre>;
}

function StatusIcon({ status }) {
  if (["passed", "verified", "market_ready", "technical_ready"].includes(status)) return <CheckCircle2 size={14} className="text-friday-accent" />;
  if (["failed", "blocked"].includes(status)) return <XCircle size={14} className="text-[#ffaaa0]" />;
  return <Loader2 size={14} className="text-[#ffb56d]" />;
}

function ReadinessBadge({ status }) {
  const ok = status === "market_ready" || status === "technical_ready";
  return <span className={`inline-flex items-center gap-2 border px-2 py-1 font-mono text-[10px] uppercase ${ok ? "border-[#2f6a57] bg-[#11251f] text-[#4dffb0]" : "border-[#6a4215] bg-[#2a2115] text-[#ffb56d]"}`}>{ok ? <CheckCircle2 size={12} /> : <XCircle size={12} />}{labelize(status || "not built")}</span>;
}

function Badge({ children }) {
  return <span className="inline-flex w-fit border border-[#415169] bg-[#172235] px-2 py-1 font-mono text-[10px] uppercase text-friday-accent">{children}</span>;
}

function dedupeRuns(items) {
  const seen = new Set();
  return (items || []).filter((item) => {
    if (!item?.id || seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  });
}

function replaceRun(items, run) {
  const next = dedupeRuns([run, ...(items || [])]);
  return next.sort((a, b) => Number(b.id || 0) - Number(a.id || 0));
}

function labelize(value) {
  return String(value || "").replace(/[_-]+/g, " ");
}

function lines(value) {
  return String(value || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
}

function dedupeStrings(items) {
  return Array.from(new Set((items || []).map((item) => String(item || "").trim()).filter(Boolean)));
}

function parseResult(value, fallbackText = "") {
  const text = String(value || "").trim();
  if (!text) return fallbackText ? { summary: fallbackText } : {};
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : { summary: text, value: parsed };
  } catch {
    return { summary: text };
  }
}

function imageMime(path) {
  const suffix = String(path || "").split(".").pop()?.toLowerCase();
  if (suffix === "jpg" || suffix === "jpeg") return "image/jpeg";
  if (suffix === "webp") return "image/webp";
  if (suffix === "gif") return "image/gif";
  return "image/png";
}

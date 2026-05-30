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
  ["ideas", "Ideas"],
  ["judgment", "Judgment"],
  ["gates", "Gate Results"],
  ["proof", "Artifacts"],
  ["memory", "Memory"],
  ["styles", "Style Profiles"],
  ["integrations", "Integrations"],
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
  const [runs, setRuns] = useState(() => fridayOs.runs || []);
  const mergedRuns = useMemo(() => dedupeRuns([...(runs || []), ...(fridayOs.runs || [])]), [runs, fridayOs.runs]);
  const [selectedId, setSelectedId] = useState(fridayOs.latest?.id || mergedRuns[0]?.id || 0);
  const selected = mergedRuns.find((run) => Number(run.id) === Number(selectedId)) || mergedRuns[0] || fridayOs.latest || null;
  const [tab, setTab] = useState("runs");
  const [busy, setBusy] = useState("");
  const [status, setStatus] = useState("");
  const [artifact, setArtifact] = useState(null);
  const [judgmentResult, setJudgmentResult] = useState(null);
  const [ideaResult, setIdeaResult] = useState(projectIdeas.latest || null);
  const [form, setForm] = useState({ request: "", root: "", target: "", production_profile: "auto", risk_level: "medium", max_fix_attempts: 0 });
  const [styleForm, setStyleForm] = useState({ name: "", framework: "nextjs", description: "", required_paths: "src/app\nsrc/components\nsrc/services\nsrc/store\nsrc/hooks\nsrc/lib\nsrc/types", rules: "" });
  const [ideaForm, setIdeaForm] = useState({ context: "", audience: "individuals, small teams, and SMBs", limit: 5, max_sources: 8 });
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
            {tab === "ideas" ? <ProjectIdeasCenter projectIdeas={projectIdeas} form={ideaForm} setForm={setIdeaForm} result={ideaResult} onResearch={researchIdeas} onOpenArtifact={openArtifact} busy={busy} /> : null}
            {tab === "judgment" ? <JudgmentCenter judgment={judgment} form={judgmentForm} setForm={setJudgmentForm} result={judgmentResult} onReview={reviewOutput} onChallenge={challengeClaim} onSelfReview={runSelfReview} onDebug={debugFailure} onSaveLesson={saveLesson} busy={busy} /> : null}
            {tab === "gates" ? <GateResults gates={gates} /> : null}
            {tab === "proof" ? <ArtifactViewer artifacts={artifacts} screenshots={screenshots} artifact={artifact} onOpen={openArtifact} busy={busy} /> : null}
            {tab === "memory" ? <MemoryCenter memory={memory} /> : null}
            {tab === "styles" ? <StyleProfiles profiles={profiles} form={styleForm} setForm={setStyleForm} onSave={saveStyleProfile} onApply={applyStyle} busy={busy} /> : null}
            {tab === "integrations" ? <IntegrationCenter integrations={integrations} /> : null}
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

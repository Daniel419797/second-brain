"use client";

import { CheckCircle2, ExternalLink, FileText, FolderOpen, Loader2, Palette, Play, RefreshCw, Rocket, ShieldCheck, XCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";

const APPROVALS = [
  { id: "deploy_preview", label: "Preview Deploy" },
  { id: "deploy_production", label: "Production Deploy" },
  { id: "post_ads", label: "Post Ads" },
  { id: "enable_billing", label: "Enable Billing" },
  { id: "send_outreach", label: "Send Outreach" }
];

export function ProductionStudioView() {
  const { api, data, refresh } = useDashboard();
  const production = data.productionReadiness || {};
  const centralProductionRuns = (data.fridayRuns?.runs || []).filter((run) => run?.kind === "production_readiness");
  const [runs, setRuns] = useState(() => production.runs || []);
  const [selectedId, setSelectedId] = useState(production.latest?.id || runs[0]?.id || 0);
  const [form, setForm] = useState({ request: "", root: "", target: "", production_profile: "auto", risk_level: "medium" });
  const [busy, setBusy] = useState("");
  const [status, setStatus] = useState("");
  const [designPipeline, setDesignPipeline] = useState(null);
  const [designImport, setDesignImport] = useState(null);
  const [designImportForm, setDesignImportForm] = useState({
    source_type: "raw_html",
    product_name: "",
    project_slug: "",
    source: "",
    source_path: "",
    source_url: "",
    verify: true,
    install: true,
    tests: true,
    browser: true,
    preview: true
  });
  const [artifact, setArtifact] = useState(null);

  const mergedRuns = useMemo(() => dedupeRuns([...(runs || []), ...centralProductionRuns, ...(production.runs || [])]), [runs, centralProductionRuns, production.runs]);
  const selectedRun = mergedRuns.find((run) => Number(run.id) === Number(selectedId)) || mergedRuns[0] || production.latest || null;
  const selected = unwrapProductionRun(selectedRun);
  const gates = selected?.gate_results?.gates || [];
  const gaps = selected?.gaps || [];

  async function startRun(event) {
    event.preventDefault();
    if (!form.request.trim()) return;
    setBusy("start");
    setStatus("");
    try {
      const run = await api("/coding/production/start", {
        method: "POST",
        body: JSON.stringify({ ...form, max_fix_attempts: 0, background: true })
      });
      setRuns((items) => [run, ...items]);
      setSelectedId(run.id);
      setStatus(run.summary || "Production readiness run started.");
      await refresh();
    } catch (err) {
      setStatus(err.message || "Production readiness run failed.");
    } finally {
      setBusy("");
    }
  }

  async function rerunGates(failedOnly = true) {
    if (!selected?.id) return;
    if (selectedRun?.kind === "production_readiness" && !selectedRun?.output?.id) {
      setStatus("This production run is still executing. Refresh the run before rerunning gates.");
      return;
    }
    setBusy("rerun");
    setStatus("");
    try {
      const run = await api(`/coding/production/runs/${selected.id}/rerun-gates`, {
        method: "POST",
        body: JSON.stringify({ failed_only: failedOnly })
      });
      setRuns((items) => replaceRun(items, run));
      setStatus(run.summary || "Gates rerun.");
      await refresh();
    } catch (err) {
      setStatus(err.message || "Gate rerun failed.");
    } finally {
      setBusy("");
    }
  }

  async function approve(action) {
    if (!selected?.id) return;
    if (selectedRun?.kind === "production_readiness" && !selectedRun?.output?.id) {
      setStatus("This production run is still executing. Refresh the run before approving launch actions.");
      return;
    }
    setBusy(action);
    setStatus("");
    try {
      const run = await api(`/coding/production/runs/${selected.id}/approve`, {
        method: "POST",
        body: JSON.stringify({ action, note: "Approved from Production Studio" })
      });
      setRuns((items) => replaceRun(items, run));
      setStatus(run.summary || "Approval recorded.");
      await refresh();
    } catch (err) {
      setStatus(err.message || "Approval failed.");
    } finally {
      setBusy("");
    }
  }

  async function runDesignPipeline({ dryRun = true, applyToSource = false, runBrowser = false } = {}) {
    const requestText = selected?.request || form.request;
    if (!requestText?.trim()) return;
    setBusy(runBrowser ? "design-verify" : dryRun ? "design-plan" : "design-run");
    setStatus("");
    try {
      const result = await api("/design/pipeline/run", {
        method: "POST",
        body: JSON.stringify({
          request: requestText,
          root: selected?.root || form.root,
          product_name: selected?.product_studio?.product_name || selected?.product_name || "",
          stack: selected?.stack || {},
          variant_count: 3,
          dry_run: dryRun,
          apply_to_source: applyToSource,
          run_browser: runBrowser,
          max_fix_attempts: runBrowser ? 1 : 0
        })
      });
      setDesignPipeline(result);
      setStatus(result.summary || "Design pipeline updated.");
      if (!dryRun) await refresh();
    } catch (err) {
      setStatus(err.message || "Design pipeline failed.");
    } finally {
      setBusy("");
    }
  }

  async function importExternalDesign(event) {
    event.preventDefault();
    const requestText = form.request || selected?.request || designImportForm.product_name || "External design import";
    const hasSource = designImportForm.source.trim() || designImportForm.source_path.trim() || designImportForm.source_url.trim();
    if (!hasSource) return;
    setBusy("design-import");
    setStatus("");
    try {
      const result = await api("/design/import/implement", {
        method: "POST",
        body: JSON.stringify({
          request: requestText,
          root: form.root || selected?.root || "",
          product_name: designImportForm.product_name || selected?.product_studio?.product_name || selected?.product_name || "",
          project_slug: designImportForm.project_slug,
          source_type: designImportForm.source_type,
          source: designImportForm.source,
          source_path: designImportForm.source_path,
          source_url: designImportForm.source_url,
          verify: designImportForm.verify,
          install: designImportForm.install,
          tests: designImportForm.tests,
          browser: designImportForm.browser,
          preview: designImportForm.preview
        })
      });
      setDesignImport(result);
      setStatus(result.summary || "External design imported and implemented.");
      await refresh();
    } catch (err) {
      setStatus(err.message || "External design import failed.");
    } finally {
      setBusy("");
    }
  }

  async function refreshSelectedRun() {
    if (!selectedRun?.id || !selectedRun?.kind) {
      await refresh();
      return;
    }
    setBusy("refresh-run");
    setStatus("");
    try {
      const run = await api(`/friday-runs/${selectedRun.id}`);
      setRuns((items) => replaceRun(items, run));
      setStatus(run.summary || "Run refreshed.");
      await refresh();
    } catch (err) {
      setStatus(err.message || "Run refresh failed.");
    } finally {
      setBusy("");
    }
  }

  async function openArtifact(path, options = {}) {
    if (!path) return;
    setBusy(`artifact:${path}`);
    setStatus("");
    try {
      const endpoint = selectedRun?.kind && options.run !== false
        ? `/friday-runs/${selectedRun.id}/artifact?path=${encodeURIComponent(path)}`
        : `/friday-os/artifact?path=${encodeURIComponent(path)}${selected?.id ? `&run_id=${encodeURIComponent(selected.id)}` : ""}`;
      const result = await api(endpoint);
      setArtifact(result);
    } catch (err) {
      setStatus(err.message || "Could not open artifact.");
    } finally {
      setBusy("");
    }
  }

  async function openFolder(path) {
    const target = path || selected?.root || selectedRun?.root;
    if (!target) return;
    setBusy("open-folder");
    setStatus("");
    try {
      await api("/friday-os/open-folder", {
        method: "POST",
        body: JSON.stringify({ path: target, run_id: Number(selectedRun?.kind ? selectedRun.id : selected?.id || 0) })
      });
      setStatus("Folder open request sent.");
    } catch (err) {
      setStatus(err.message || "Could not open folder.");
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="friday-scroll h-full overflow-y-auto overflow-x-hidden bg-friday-bg p-3 text-white" aria-label="Production Studio">
      <div className="grid max-w-[1180px] gap-4">
        <header className="flex min-h-10 items-center gap-3">
          <Rocket size={18} className="text-friday-accent" />
          <h1 className="text-[18px] font-extrabold">Production Studio</h1>
          <span className="ml-auto font-mono text-[11px] text-friday-muted">{mergedRuns.length} run(s)</span>
        </header>

        <div className="grid gap-4 xl:grid-cols-[340px_minmax(0,1fr)]">
          <aside className="grid content-start gap-3">
            <Panel>
              <h2 className="mb-3 font-mono text-[11px] font-bold uppercase tracking-[.12em] text-[#cbd7e6]">Start Run</h2>
              <form className="grid gap-3" onSubmit={startRun}>
                <textarea className="min-h-[108px] resize-y border border-friday-line bg-[#0c1218] px-3 py-2 text-[13px] text-white outline-none focus:border-friday-accent" value={form.request} onChange={(event) => setForm((current) => ({ ...current, request: event.target.value }))} placeholder="Production-ready product request" required />
                <input className="min-h-10 border border-friday-line bg-[#0c1218] px-3 text-[13px] text-white outline-none focus:border-friday-accent" value={form.root} onChange={(event) => setForm((current) => ({ ...current, root: event.target.value }))} placeholder="Root workspace" />
                <input className="min-h-10 border border-friday-line bg-[#0c1218] px-3 text-[13px] text-white outline-none focus:border-friday-accent" value={form.target} onChange={(event) => setForm((current) => ({ ...current, target: event.target.value }))} placeholder="Target project path" />
                <div className="grid grid-cols-2 gap-2">
                  <select className="min-h-10 border border-friday-line bg-[#0c1218] px-3 text-[13px] text-white outline-none focus:border-friday-accent" value={form.production_profile} onChange={(event) => setForm((current) => ({ ...current, production_profile: event.target.value }))}>
                    <option value="auto">Auto Profile</option>
                    <option value="web-app">Web App</option>
                    <option value="mobile">Mobile</option>
                    <option value="backend">Backend</option>
                  </select>
                  <select className="min-h-10 border border-friday-line bg-[#0c1218] px-3 text-[13px] text-white outline-none focus:border-friday-accent" value={form.risk_level} onChange={(event) => setForm((current) => ({ ...current, risk_level: event.target.value }))}>
                    <option value="medium">Medium Risk</option>
                    <option value="low">Low Risk</option>
                    <option value="high">High Risk</option>
                  </select>
                </div>
                <button className="inline-flex min-h-10 items-center justify-center gap-2 border border-friday-blue bg-friday-blue font-mono text-[12px] font-bold text-[#061420] disabled:opacity-50" type="submit" disabled={busy === "start" || !form.request.trim()}>
                  {busy === "start" ? <Loader2 className="animate-spin" size={14} /> : <Play size={14} />}
                  Start Production Run
                </button>
              </form>
            </Panel>

            <Panel>
              <h2 className="mb-3 font-mono text-[11px] font-bold uppercase tracking-[.12em] text-[#cbd7e6]">Import Design</h2>
              <form className="grid gap-3" onSubmit={importExternalDesign}>
                <div className="grid grid-cols-2 gap-2">
                  <select className="min-h-10 border border-friday-line bg-[#0c1218] px-3 text-[13px] text-white outline-none focus:border-friday-accent" value={designImportForm.source_type} onChange={(event) => setDesignImportForm((current) => ({ ...current, source_type: event.target.value }))}>
                    <option value="raw_html">Raw HTML</option>
                    <option value="stitch_output">Stitch Output</option>
                    <option value="v0_output">v0 Output</option>
                    <option value="ai_design">Other AI Design</option>
                    <option value="screenshot">Screenshot/Image</option>
                    <option value="figma_export">Figma Export</option>
                    <option value="uploaded_file">Uploaded File</option>
                    <option value="design_brief">Design Brief</option>
                    <option value="existing_url">Existing URL</option>
                  </select>
                  <input className="min-h-10 border border-friday-line bg-[#0c1218] px-3 text-[13px] text-white outline-none focus:border-friday-accent" value={designImportForm.project_slug} onChange={(event) => setDesignImportForm((current) => ({ ...current, project_slug: event.target.value }))} placeholder="Project slug" />
                </div>
                <input className="min-h-10 border border-friday-line bg-[#0c1218] px-3 text-[13px] text-white outline-none focus:border-friday-accent" value={designImportForm.product_name} onChange={(event) => setDesignImportForm((current) => ({ ...current, product_name: event.target.value }))} placeholder="Product or company name" />
                <textarea className="min-h-[120px] resize-y border border-friday-line bg-[#0c1218] px-3 py-2 text-[12px] text-white outline-none focus:border-friday-accent" value={designImportForm.source} onChange={(event) => setDesignImportForm((current) => ({ ...current, source: event.target.value }))} placeholder="Paste HTML, v0/Stitch output, design brief, or URL" />
                <input className="min-h-10 border border-friday-line bg-[#0c1218] px-3 text-[12px] text-white outline-none focus:border-friday-accent" value={designImportForm.source_path} onChange={(event) => setDesignImportForm((current) => ({ ...current, source_path: event.target.value }))} placeholder="Optional local design file path" />
                <input className="min-h-10 border border-friday-line bg-[#0c1218] px-3 text-[12px] text-white outline-none focus:border-friday-accent" value={designImportForm.source_url} onChange={(event) => setDesignImportForm((current) => ({ ...current, source_url: event.target.value }))} placeholder="Optional design URL" />
                <div className="grid grid-cols-2 gap-2 font-mono text-[10px] text-[#cbd7e6]">
                  {[
                    ["verify", "Verify"],
                    ["install", "Install"],
                    ["tests", "Build/Test"],
                    ["browser", "Browser"],
                    ["preview", "Preview"]
                  ].map(([key, label]) => (
                    <label className="flex min-h-8 items-center gap-2 border border-friday-line bg-[#10161d] px-2" key={key}>
                      <input type="checkbox" checked={Boolean(designImportForm[key])} onChange={(event) => setDesignImportForm((current) => ({ ...current, [key]: event.target.checked }))} />
                      {label}
                    </label>
                  ))}
                </div>
                <button className="inline-flex min-h-10 items-center justify-center gap-2 border border-[#7a574d] bg-[#271916] font-mono text-[12px] font-bold text-[#ffd3c6] hover:border-[#ff9e7c] disabled:opacity-50" type="submit" disabled={busy === "design-import" || !(designImportForm.source.trim() || designImportForm.source_path.trim() || designImportForm.source_url.trim())}>
                  {busy === "design-import" ? <Loader2 className="animate-spin" size={14} /> : <FileText size={14} />}
                  Implement Source Design
                </button>
              </form>
            </Panel>

            <Panel>
              <h2 className="mb-3 font-mono text-[11px] font-bold uppercase tracking-[.12em] text-[#cbd7e6]">Runs</h2>
              <div className="grid gap-2">
                {mergedRuns.length ? mergedRuns.map((run) => (
                  <button className={`grid gap-1 border p-3 text-left ${selected?.id === run.id ? "border-friday-accent bg-[#202832]" : "border-friday-line bg-[#10161d] hover:border-friday-accent"}`} type="button" key={run.id} onClick={() => setSelectedId(run.id)}>
                    <span className="font-mono text-[10px] text-friday-muted">#{run.id} / {run.status}</span>
                    <strong className="line-clamp-2 text-[12px] text-white">{run.summary || run.request}</strong>
                  </button>
                )) : <p className="text-[12px] text-friday-muted">No production readiness run has been recorded yet.</p>}
              </div>
            </Panel>
          </aside>

          <main className="grid content-start gap-3">
            <Panel>
              <div className="grid gap-3 lg:grid-cols-[1fr_auto]">
                <div>
                  <div className="mb-2 flex flex-wrap gap-2">
                    <ReadinessBadge run={selected} />
                    {selected?.stack?.label ? <Badge>{selected.stack.label}</Badge> : null}
                  </div>
                  <h2 className="text-[20px] font-extrabold leading-tight">{selected?.request || "No run selected"}</h2>
                  <p className="mt-2 break-words font-mono text-[11px] text-friday-muted">{selected?.root || "No root recorded"}</p>
                </div>
                <div className="flex flex-wrap items-start gap-2">
                  <button className="inline-flex min-h-9 items-center gap-2 border border-friday-line bg-[#151b22] px-3 font-mono text-[11px] text-[#dfe9f6] hover:border-friday-accent disabled:opacity-50" type="button" onClick={refreshSelectedRun} disabled={!selectedRun || busy === "refresh-run"}>
                    {busy === "refresh-run" ? <Loader2 className="animate-spin" size={13} /> : <RefreshCw size={13} />}
                    Refresh Run
                  </button>
                  <button className="inline-flex min-h-9 items-center gap-2 border border-friday-line bg-[#151b22] px-3 font-mono text-[11px] text-[#dfe9f6] hover:border-friday-accent disabled:opacity-50" type="button" onClick={() => rerunGates(true)} disabled={!selected || busy === "rerun"}>
                    {busy === "rerun" ? <Loader2 className="animate-spin" size={13} /> : <RefreshCw size={13} />}
                    Rerun Failed
                  </button>
                  {selected?.root || selectedRun?.root ? (
                    <button className="inline-flex min-h-9 items-center gap-2 border border-friday-line bg-[#151b22] px-3 font-mono text-[11px] text-[#dfe9f6] hover:border-friday-accent disabled:opacity-50" type="button" onClick={() => openFolder(selected?.root || selectedRun?.root)} disabled={busy === "open-folder"}>
                      {busy === "open-folder" ? <Loader2 className="animate-spin" size={13} /> : <FolderOpen size={13} />}
                      Folder
                    </button>
                  ) : null}
                  {selected?.preview_url ? (
                    <a className="inline-flex min-h-9 items-center gap-2 border border-friday-blue bg-friday-blue px-3 font-mono text-[11px] font-bold text-[#061420]" href={selected.preview_url} target="_blank" rel="noreferrer">
                      <ExternalLink size={13} />
                      Preview
                    </a>
                  ) : null}
                  <button className="inline-flex min-h-9 items-center gap-2 border border-friday-line bg-[#151b22] px-3 font-mono text-[11px] text-[#dfe9f6] hover:border-friday-accent disabled:opacity-50" type="button" onClick={() => runDesignPipeline({ dryRun: true })} disabled={busy === "design-plan" || (!selected && !form.request.trim())}>
                    {busy === "design-plan" ? <Loader2 className="animate-spin" size={13} /> : <Palette size={13} />}
                    Plan Design
                  </button>
                  <button className="inline-flex min-h-9 items-center gap-2 border border-[#5d4a22] bg-[#211b11] px-3 font-mono text-[11px] text-[#ffd99a] hover:border-[#ffb56d] disabled:opacity-50" type="button" onClick={() => runDesignPipeline({ dryRun: false, applyToSource: true })} disabled={busy === "design-run" || (!selected && !form.request.trim())}>
                    {busy === "design-run" ? <Loader2 className="animate-spin" size={13} /> : <Palette size={13} />}
                    Run + Apply
                  </button>
                  <button className="inline-flex min-h-9 items-center gap-2 border border-[#275f67] bg-[#10272d] px-3 font-mono text-[11px] text-[#9eeaf2] hover:border-[#65dce8] disabled:opacity-50" type="button" onClick={() => runDesignPipeline({ dryRun: false, applyToSource: true, runBrowser: true })} disabled={busy === "design-verify" || (!selected && !form.request.trim())}>
                    {busy === "design-verify" ? <Loader2 className="animate-spin" size={13} /> : <Palette size={13} />}
                    Verify UI
                  </button>
                </div>
              </div>
            </Panel>

            <div className="grid gap-3 lg:grid-cols-3">
              <Metric label="Technical Ready" value={selected?.technical_ready ? "yes" : "no"} warn={!selected?.technical_ready} />
              <Metric label="Market Ready" value={selected?.market_ready ? "yes" : "no"} warn={!selected?.market_ready} />
              <Metric label="Required Gaps" value={String(gaps.length || 0)} warn={gaps.length > 0} />
            </div>

            <Panel>
              <PanelTitle title="Phases" />
              <div className="mt-3 grid gap-2 md:grid-cols-3">
                {(selected?.phases || []).map((phase) => <StatusRow key={phase.id} label={phase.label || phase.id} status={phase.status} />)}
              </div>
            </Panel>

            <Panel>
              <PanelTitle title="Design Pipeline" />
              <div className="mt-3 grid gap-3 lg:grid-cols-[240px_minmax(0,1fr)]">
                <div className="grid gap-2">
                  <StatusRow label="Pipeline status" status={designPipeline?.status || selected?.product_studio?.final_proof_report?.evidence?.design_pipeline?.status || "planned"} />
                  <StatusRow label="Frontend handoff" status={designPipeline?.frontend_handoff_allowed ? "verified" : "blocked"} />
                  <StatusRow label="Applied source" status={designPipeline?.applied_to_source ? "verified" : "planned"} />
                  <StatusRow label="Browser proof" status={designPipeline?.browser_verified ? "verified" : "planned"} />
                </div>
                <div className="grid gap-2">
                  <p className="m-0 text-[12px] text-[#dce7f4]">{designPipeline?.summary || selected?.product_studio?.final_proof_report?.evidence?.design_pipeline?.summary || "Brief, research, direction, tokens, page contracts, variants, critique, implementation, browser verification, fix loop, and final proof."}</p>
                  {designPipeline?.selected_variant ? <p className="m-0 font-mono text-[11px] text-friday-accent">Selected: {designPipeline.selected_variant.label || designPipeline.selected_variant.id} / {designPipeline.selected_variant.score}/100</p> : null}
                  <DesignStageList stages={designPipeline?.stages || []} />
                  <ArtifactList items={(designPipeline?.artifacts || []).slice(-8)} empty="No design pipeline artifact opened in this session." onOpen={openArtifact} />
                </div>
              </div>
            </Panel>

            <Panel>
              <PanelTitle title="External Design Import" />
              <div className="mt-3 grid gap-3 lg:grid-cols-[260px_minmax(0,1fr)]">
                <div className="grid gap-2">
                  <StatusRow label="Import status" status={designImport?.status || "planned"} />
                  <StatusRow label="Pages" status={designImport?.page_count ? `${designImport.page_count} imported` : "planned"} />
                  <StatusRow label="Verification" status={designImport?.gate_results?.status || (designImport ? "recorded" : "planned")} />
                  {designImport?.preview_url ? (
                    <a className="inline-flex min-h-9 items-center justify-center gap-2 border border-friday-blue bg-friday-blue px-3 font-mono text-[11px] font-bold text-[#061420]" href={designImport.preview_url} target="_blank" rel="noreferrer">
                      <ExternalLink size={13} />
                      Preview
                    </a>
                  ) : null}
                </div>
                <div className="grid gap-2">
                  <p className="m-0 break-words text-[12px] text-[#dce7f4]">{designImport?.summary || "Paste HTML, a Stitch/v0 export, screenshot path, Figma export, design brief, URL, or another AI design. Friday will save the source, create frontend-handoff.json, implement Next.js, and attach verification proof."}</p>
                  {designImport?.project_root ? <p className="m-0 font-mono text-[11px] text-friday-accent">{designImport.project_root}</p> : null}
                  {designImport?.pages?.length ? (
                    <div className="grid gap-2 md:grid-cols-2">
                      {designImport.pages.map((page) => (
                        <div className="border border-friday-line bg-[#10161d] p-2" key={page.id}>
                          <div className="flex items-center gap-2">
                            <strong className="text-[12px] text-white">{page.label}</strong>
                            <span className="ml-auto font-mono text-[10px] text-friday-muted">{page.route}</span>
                          </div>
                          <p className="m-0 mt-1 font-mono text-[10px] text-[#9fb0c5]">{page.source_type} / {page.fidelity}</p>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  <ArtifactList items={[...(designImport?.screenshots || []), ...(designImport?.artifacts || [])].slice(-10)} empty="No imported design artifact has been recorded in this session." onOpen={(path) => openArtifact(path, { run: false })} />
                </div>
              </div>
            </Panel>

            <Panel>
              <PanelTitle title="Executable Gates" />
              <div className="mt-3 grid gap-2 lg:grid-cols-2">
                {gates.length ? gates.map((gate, index) => <GateRow gate={gate} key={`${index}-${gate.id}`} onOpenArtifact={openArtifact} />) : <p className="text-[12px] text-friday-muted">No gate result is attached.</p>}
              </div>
            </Panel>

            <div className="grid gap-3 lg:grid-cols-2">
              <Panel>
                <PanelTitle title="Approvals" />
                <div className="mt-3 grid gap-2">
                  {APPROVALS.map((approval) => {
                    const item = selected?.approvals?.[approval.id] || {};
                    return (
                      <button className={`flex min-h-10 items-center gap-2 border px-3 text-left font-mono text-[11px] ${item.approved ? "border-[#2f6a57] bg-[#11251f] text-[#4dffb0]" : "border-friday-line bg-[#10161d] text-[#dfe9f6] hover:border-friday-accent"}`} type="button" key={approval.id} onClick={() => approve(approval.id)} disabled={!selected || item.approved || Boolean(busy)}>
                        {item.approved ? <CheckCircle2 size={14} /> : <ShieldCheck size={14} />}
                        {approval.label}
                        <span className="ml-auto">{item.approved ? "approved" : "blocked"}</span>
                      </button>
                    );
                  })}
                </div>
              </Panel>
              <Panel>
                <PanelTitle title="Gaps And Artifacts" />
                <div className="mt-3 grid gap-3">
                  <ChipList items={gaps.slice(0, 10)} empty="No readiness gaps recorded." />
                  <ArtifactList items={(selected?.artifacts || selectedRun?.artifacts || []).slice(-10)} empty="No artifacts recorded." onOpen={openArtifact} />
                </div>
              </Panel>
            </div>
            <Panel>
              <PanelTitle title="Artifact Viewer" />
              <div className="mt-3 min-h-40 border border-friday-line bg-[#10161d] p-3">
                {artifact ? artifact.binary ? <img alt={artifact.path} className="max-h-[520px] max-w-full border border-friday-line" src={`data:${imageMime(artifact.path)};base64,${artifact.base64}`} /> : <pre className="friday-scroll max-h-[520px] overflow-auto whitespace-pre-wrap text-[11px] text-[#dfe9f6]">{artifact.content}</pre> : <p className="text-[12px] text-friday-muted">Open a log, screenshot, or proof report to inspect evidence.</p>}
              </div>
            </Panel>
          </main>
        </div>
        {status ? <div className="fixed bottom-5 right-5 z-20 max-w-[420px] border border-[#45678c] bg-[#9fcaff] px-4 py-3 text-[13px] font-semibold text-[#07111d] shadow-[0_16px_40px_rgba(0,0,0,.32)]">{status}</div> : null}
      </div>
    </section>
  );
}

function Panel({ children }) {
  return <section className="min-w-0 overflow-hidden border border-friday-line bg-[#1a2028] p-3">{children}</section>;
}

function PanelTitle({ title }) {
  return <h2 className="font-mono text-[11px] font-bold uppercase tracking-[.12em] text-[#cbd7e6]">{title}</h2>;
}

function Metric({ label, value, warn }) {
  return (
    <Panel>
      <span className="block font-mono text-[10px] uppercase tracking-[.08em] text-friday-muted">{label}</span>
      <strong className={`mt-2 block text-[20px] ${warn ? "text-[#ffb56d]" : "text-friday-accent"}`}>{value}</strong>
    </Panel>
  );
}

function ReadinessBadge({ run }) {
  const status = run?.status || "not built";
  const ok = status === "market_ready" || status === "technical_ready";
  return (
    <span className={`inline-flex items-center gap-2 border px-2 py-1 font-mono text-[10px] uppercase ${ok ? "border-[#2f6a57] bg-[#11251f] text-[#4dffb0]" : "border-[#6a4215] bg-[#2a2115] text-[#ffb56d]"}`}>
      {ok ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
      {labelize(status)}
    </span>
  );
}

function Badge({ children }) {
  return <span className="inline-flex border border-[#415169] bg-[#172235] px-2 py-1 font-mono text-[10px] uppercase text-friday-accent">{children}</span>;
}

function StatusRow({ label, status }) {
  return (
    <div className="grid min-h-12 grid-cols-[1fr_auto] gap-2 border border-friday-line bg-[#10161d] p-2 font-mono text-[10px]">
      <span className="truncate text-[#dce7f4]">{label}</span>
      <span className={status === "verified" ? "text-friday-accent" : status === "blocked" || status === "failed" ? "text-[#ffaaa0]" : "text-[#ffb56d]"}>{status || "planned"}</span>
    </div>
  );
}

function GateRow({ gate, onOpenArtifact }) {
  const proofPaths = [gate.screenshot, gate.log_path, ...(gate.evidence || []).filter((item) => looksLikePath(item))].filter(Boolean);
  return (
    <div className="grid gap-1 border border-friday-line bg-[#10161d] p-3">
      <div className="grid grid-cols-[1fr_auto] gap-2 font-mono text-[10px]">
        <strong className="truncate text-[#dce7f4]">{gate.label || gate.id}</strong>
        <span className={gate.status === "passed" ? "text-friday-accent" : gate.status === "failed" || gate.status === "blocked" || gate.status === "timeout" ? "text-[#ffaaa0]" : "text-[#ffb56d]"}>{gate.status || "unknown"}</span>
      </div>
      <p className="m-0 line-clamp-2 text-[11px] text-friday-muted">{gate.summary || gate.command || "No summary recorded."}</p>
      {proofPaths.length ? <ArtifactList items={proofPaths.slice(0, 4)} empty="" onOpen={onOpenArtifact} /> : null}
    </div>
  );
}

function DesignStageList({ stages }) {
  const rows = (stages || []).filter(Boolean);
  if (!rows.length) {
    return <p className="m-0 text-[12px] text-friday-muted">No design pipeline stages have run in this session.</p>;
  }
  return (
    <div className="grid gap-1 md:grid-cols-2">
      {rows.map((stage) => (
        <div className="grid min-h-10 grid-cols-[1fr_auto] gap-2 border border-friday-line bg-[#10161d] p-2 font-mono text-[10px]" key={stage.id}>
          <span className="truncate text-[#dce7f4]" title={stage.summary || stage.id}>{labelize(stage.id)}</span>
          <span className={stage.status === "completed" || stage.status === "passed" || stage.status === "verified" ? "text-friday-accent" : stage.status === "blocked" || stage.status === "failed" || stage.status === "needs_revision" ? "text-[#ffaaa0]" : "text-[#ffb56d]"}>{stage.status || "planned"}</span>
        </div>
      ))}
    </div>
  );
}

function ChipList({ items, empty }) {
  const rows = (items || []).filter(Boolean);
  return (
    <div className="flex flex-wrap gap-2">
      {rows.length ? rows.map((item, index) => <span className="max-w-full truncate border border-friday-line bg-[#151b22] px-2 py-1 font-mono text-[10px]" key={`${index}-${item}`}>{item}</span>) : <span className="text-[12px] text-friday-muted">{empty}</span>}
    </div>
  );
}

function ArtifactList({ items, empty, onOpen }) {
  const rows = (items || []).filter(Boolean);
  return (
    <div className="flex flex-wrap gap-2">
      {rows.length ? rows.map((item, index) => (
        <button className="inline-flex max-w-full items-center gap-1 truncate border border-friday-line bg-[#151b22] px-2 py-1 font-mono text-[10px] text-[#dfe9f6] hover:border-friday-accent" type="button" key={`${index}-${item}`} onClick={() => onOpen?.(item)} title={item}>
          <FileText size={11} />
          <span className="truncate">{shortPath(item)}</span>
        </button>
      )) : <span className="text-[12px] text-friday-muted">{empty}</span>}
    </div>
  );
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
  const replaced = (items || []).map((item) => (item.id === run.id ? run : item));
  return replaced.some((item) => item.id === run.id) ? replaced : [run, ...replaced];
}

function unwrapProductionRun(run) {
  if (!run) return null;
  if (run.kind === "production_readiness" && run.output?.id) return run.output;
  return run;
}

function labelize(value) {
  return String(value || "").replace(/[-_]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function shortPath(value) {
  const text = String(value || "");
  const parts = text.split(/[\\/]/).filter(Boolean);
  return parts.slice(-3).join("/") || text;
}

function looksLikePath(value) {
  const text = String(value || "");
  return Boolean(text) && !/^https?:\/\//i.test(text) && (text.includes("/") || text.includes("\\") || /\.[a-z0-9]+$/i.test(text));
}

function imageMime(path) {
  const lower = String(path || "").toLowerCase();
  if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
  if (lower.endsWith(".webp")) return "image/webp";
  if (lower.endsWith(".gif")) return "image/gif";
  return "image/png";
}

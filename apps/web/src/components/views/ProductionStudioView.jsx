"use client";

import { CheckCircle2, ExternalLink, Loader2, Play, RefreshCw, Rocket, ShieldCheck, XCircle } from "lucide-react";
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
  const [runs, setRuns] = useState(() => production.runs || []);
  const [selectedId, setSelectedId] = useState(production.latest?.id || runs[0]?.id || 0);
  const [form, setForm] = useState({ request: "", root: "", target: "", production_profile: "auto", risk_level: "medium" });
  const [busy, setBusy] = useState("");
  const [status, setStatus] = useState("");

  const mergedRuns = useMemo(() => dedupeRuns([...(runs || []), ...(production.runs || [])]), [runs, production.runs]);
  const selected = mergedRuns.find((run) => Number(run.id) === Number(selectedId)) || mergedRuns[0] || production.latest || null;
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
        body: JSON.stringify({ ...form, max_fix_attempts: 0 })
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
                  <button className="inline-flex min-h-9 items-center gap-2 border border-friday-line bg-[#151b22] px-3 font-mono text-[11px] text-[#dfe9f6] hover:border-friday-accent disabled:opacity-50" type="button" onClick={() => rerunGates(true)} disabled={!selected || busy === "rerun"}>
                    {busy === "rerun" ? <Loader2 className="animate-spin" size={13} /> : <RefreshCw size={13} />}
                    Rerun Failed
                  </button>
                  {selected?.preview_url ? (
                    <a className="inline-flex min-h-9 items-center gap-2 border border-friday-blue bg-friday-blue px-3 font-mono text-[11px] font-bold text-[#061420]" href={selected.preview_url} target="_blank" rel="noreferrer">
                      <ExternalLink size={13} />
                      Preview
                    </a>
                  ) : null}
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
              <PanelTitle title="Executable Gates" />
              <div className="mt-3 grid gap-2 lg:grid-cols-2">
                {gates.length ? gates.map((gate, index) => <GateRow gate={gate} key={`${index}-${gate.id}`} />) : <p className="text-[12px] text-friday-muted">No gate result is attached.</p>}
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
                  <ChipList items={(selected?.artifacts || []).slice(-10)} empty="No artifacts recorded." />
                </div>
              </Panel>
            </div>
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

function GateRow({ gate }) {
  return (
    <div className="grid gap-1 border border-friday-line bg-[#10161d] p-3">
      <div className="grid grid-cols-[1fr_auto] gap-2 font-mono text-[10px]">
        <strong className="truncate text-[#dce7f4]">{gate.label || gate.id}</strong>
        <span className={gate.status === "passed" ? "text-friday-accent" : gate.status === "failed" || gate.status === "blocked" || gate.status === "timeout" ? "text-[#ffaaa0]" : "text-[#ffb56d]"}>{gate.status || "unknown"}</span>
      </div>
      <p className="m-0 line-clamp-2 text-[11px] text-friday-muted">{gate.summary || gate.command || "No summary recorded."}</p>
      {gate.screenshot ? <p className="m-0 truncate font-mono text-[10px] text-[#dce7f4]">Screenshot: {gate.screenshot}</p> : null}
      {gate.log_path ? <p className="m-0 truncate font-mono text-[10px] text-[#dce7f4]">Log: {gate.log_path}</p> : null}
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

function labelize(value) {
  return String(value || "").replace(/[-_]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

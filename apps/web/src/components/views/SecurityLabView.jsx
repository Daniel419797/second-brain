"use client";

import { AlertTriangle, CheckCircle2, ClipboardCheck, Database, FileText, Loader2, Play, RefreshCw, ShieldCheck, Terminal, XCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";

const ACTION_PRIMARY = "inline-flex min-h-9 items-center justify-center gap-2 border border-friday-blue bg-friday-blue px-3 font-mono text-[11px] font-bold text-[#061420] disabled:opacity-50";
const ACTION_SECONDARY = "inline-flex min-h-9 items-center justify-center gap-2 border border-friday-line bg-[#151b22] px-3 font-mono text-[11px] text-[#dfe9f6] hover:border-friday-accent disabled:opacity-50";
const FIELD = "min-h-10 border border-friday-line bg-[#0c1218] px-3 py-2 text-[13px] text-white outline-none focus:border-friday-accent";

export function SecurityLabView() {
  const { api, data, refresh } = useDashboard();
  const [lab, setLab] = useState(data.securityLab || null);
  const [runs, setRuns] = useState(data.securityLab?.recent_runs || []);
  const [selected, setSelected] = useState(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState("");
  const [form, setForm] = useState({
    root: "",
    target: "",
    profile: "code_audit",
    tools: "secret_scan\ndependency_summary\nauth_session_review\nsemgrep\nbandit\ngitleaks\ntrivy_fs\nnpm_audit\npip_audit",
    intensity: "safe",
    execution_mode: "host",
    timeout: 180,
    ctf_lab: false,
    scope_id: 0,
    authorization_note: "",
    apply_fixes: false
  });

  const load = useCallback(async () => {
    setBusy("load");
    try {
      const [snapshot, runRows] = await Promise.all([
        api("/security-lab/status"),
        api("/security-lab/runs?limit=20")
      ]);
      setLab(snapshot);
      setRuns(Array.isArray(runRows) ? runRows : []);
      setStatus("");
    } catch (err) {
      setStatus(err.message || "Security Lab could not load.");
    } finally {
      setBusy("");
    }
  }, [api]);

  useEffect(() => {
    void load();
  }, [load]);

  async function runScan(event) {
    event.preventDefault();
    setBusy("run");
    setStatus("");
    try {
      const payload = {
        ...form,
        tools: lines(form.tools),
        timeout: Number(form.timeout || 180),
        scope_id: Number(form.scope_id || 0)
      };
      const result = await api("/security-lab/run", { method: "POST", body: JSON.stringify(payload) });
      setSelected(result);
      setStatus(result.summary || "Security Lab run complete.");
      await load();
      await refresh();
    } catch (err) {
      setStatus(err.message || "Security Lab run failed.");
    } finally {
      setBusy("");
    }
  }

  async function openRun(runId) {
    setBusy(`run:${runId}`);
    try {
      setSelected(await api(`/security-lab/runs/${runId}`));
    } catch (err) {
      setStatus(err.message || "Could not open Security Lab run.");
    } finally {
      setBusy("");
    }
  }

  const tools = lab?.tools || [];
  const profiles = lab?.profiles || [];
  const scopes = lab?.scopes || [];
  const available = tools.filter((tool) => tool.available).length;
  const unavailable = tools.length - available;
  const latest = selected || runs[0] || {};

  return (
    <section className="friday-scroll h-full min-h-0 overflow-y-auto bg-friday-bg p-3 text-[#eaf2fb]" aria-label="Security Lab">
      <div className="grid max-w-[1240px] gap-4">
        <header className="flex min-h-10 flex-wrap items-center gap-3">
          <ShieldCheck size={18} className="text-friday-accent" />
          <h1 className="text-[18px] font-extrabold">Security Lab</h1>
          <span className="font-mono text-[11px] text-friday-muted">{lab?.summary || "Scoped offensive-security tooling for authorized defensive work"}</span>
          <button className={`${ACTION_SECONDARY} ml-auto`} type="button" onClick={load} disabled={busy === "load"}>
            {busy === "load" ? <Loader2 className="animate-spin" size={13} /> : <RefreshCw size={13} />}
            Refresh
          </button>
        </header>

        {status ? <div className="border border-[#45678c] bg-[#172334] px-4 py-3 text-[13px] text-[#dfe9f6]">{status}</div> : null}

        <div className="grid gap-3 md:grid-cols-4">
          <Metric label="Tools Ready" value={`${available}/${tools.length || 0}`} warn={!available} />
          <Metric label="Unavailable" value={String(unavailable)} warn={unavailable > 0} />
          <Metric label="Scopes" value={String(scopes.length)} warn={!scopes.length} />
          <Metric label="Runs" value={String(runs.length)} warn={!runs.length} />
        </div>

        <div className="grid gap-4 xl:grid-cols-[420px_minmax(0,1fr)]">
          <div className="grid content-start gap-3">
            <Panel title="Run Scoped Scan" icon={Terminal}>
              <form className="grid gap-2" onSubmit={runScan}>
                <input className={FIELD} value={form.root} onChange={(event) => setForm((current) => ({ ...current, root: event.target.value }))} placeholder="Project root for code scans" />
                <input className={FIELD} value={form.target} onChange={(event) => setForm((current) => ({ ...current, target: event.target.value }))} placeholder="Authorized target, e.g. 127.0.0.1 or owned domain" />
                <select className={FIELD} value={form.profile} onChange={(event) => setForm((current) => ({ ...current, profile: event.target.value }))}>
                  <option value="auto">Auto</option>
                  {profiles.map((profile) => <option key={profile.id} value={profile.id}>{labelize(profile.id)}</option>)}
                </select>
                <textarea className={`${FIELD} min-h-36 font-mono`} value={form.tools} onChange={(event) => setForm((current) => ({ ...current, tools: event.target.value }))} placeholder="Tools, one per line" />
                <div className="grid grid-cols-3 gap-2">
                  <select className={FIELD} value={form.execution_mode} onChange={(event) => setForm((current) => ({ ...current, execution_mode: event.target.value }))}>
                    <option value="host">Host</option>
                    <option value="sandbox">Sandbox</option>
                  </select>
                  <input className={FIELD} type="number" min="5" max="1800" value={form.timeout} onChange={(event) => setForm((current) => ({ ...current, timeout: event.target.value }))} title="Timeout seconds" />
                  <input className={FIELD} type="number" min="0" value={form.scope_id} onChange={(event) => setForm((current) => ({ ...current, scope_id: event.target.value }))} title="Scope ID" />
                </div>
                <textarea className={`${FIELD} min-h-20`} value={form.authorization_note} onChange={(event) => setForm((current) => ({ ...current, authorization_note: event.target.value }))} placeholder="Authorization note or ticket reference" />
                <div className="grid grid-cols-2 gap-2">
                  <label className="flex min-h-10 items-center gap-2 border border-friday-line bg-[#10161d] px-3 font-mono text-[11px] text-[#dfe9f6]">
                    <input type="checkbox" checked={form.ctf_lab} onChange={(event) => setForm((current) => ({ ...current, ctf_lab: event.target.checked }))} />
                    CTF/lab
                  </label>
                  <label className="flex min-h-10 items-center gap-2 border border-friday-line bg-[#10161d] px-3 font-mono text-[11px] text-[#dfe9f6]">
                    <input type="checkbox" checked={form.apply_fixes} onChange={(event) => setForm((current) => ({ ...current, apply_fixes: event.target.checked }))} />
                    Fix plan
                  </label>
                </div>
                <button className={ACTION_PRIMARY} type="submit" disabled={busy === "run"}>
                  {busy === "run" ? <Loader2 className="animate-spin" size={14} /> : <Play size={14} />}
                  Run Security Lab
                </button>
              </form>
            </Panel>

            <Panel title="Verified Scopes" icon={ShieldCheck}>
              <div className="grid gap-2">
                {scopes.map((scope) => <ScopeRow key={scope.id} scope={scope} />)}
                {!scopes.length ? <p className="text-[12px] text-friday-muted">Create or verify scopes from Safety before public-target scans.</p> : null}
              </div>
            </Panel>
          </div>

          <div className="grid content-start gap-3">
            <Panel title="Latest Run" icon={ClipboardCheck}>
              <div className="grid gap-3 md:grid-cols-3">
                <Metric label="Status" value={latest.status || "none"} warn={!["done", "passed"].includes(latest.status)} />
                <Metric label="Results" value={String(latest.result_count || latest.results?.length || 0)} warn={false} />
                <Metric label="Target" value={latest.target || "none"} warn={false} />
              </div>
              <p className="mt-3 text-[13px] text-[#dfe9f6]">{latest.summary || "Run a scan to attach proof, logs, findings, and remediation."}</p>
              {latest.report_path ? <p className="mt-2 font-mono text-[10px] text-friday-muted">{latest.report_path}</p> : null}
            </Panel>

            <Panel title="Run Results" icon={FileText}>
              <div className="grid gap-2">
                {(latest.results || []).map((result) => <ResultRow key={`${result.tool}-${result.status}`} result={result} />)}
                {!(latest.results || []).length ? <p className="text-[12px] text-friday-muted">Open a run to inspect results.</p> : null}
              </div>
            </Panel>

            <Panel title="Recent Runs" icon={Database}>
              <div className="grid gap-2">
                {runs.map((run) => (
                  <button className="grid gap-1 border border-friday-line bg-[#10161d] p-3 text-left hover:border-friday-accent" key={run.id} type="button" onClick={() => openRun(run.id)} disabled={busy === `run:${run.id}`}>
                    <span className="font-mono text-[10px] text-friday-muted">#{run.id} / {run.profile}</span>
                    <strong className="text-[12px]">{run.summary}</strong>
                    <span className="font-mono text-[10px] text-friday-muted">{run.target || run.root}</span>
                  </button>
                ))}
                {!runs.length ? <p className="text-[12px] text-friday-muted">No Security Lab runs yet.</p> : null}
              </div>
            </Panel>

            <Panel title="Tool Registry" icon={Terminal}>
              <div className="grid gap-2 md:grid-cols-2">
                {tools.map((tool) => <ToolRow key={tool.id} tool={tool} />)}
              </div>
            </Panel>
          </div>
        </div>
      </div>
    </section>
  );
}

function Panel({ title, icon: Icon, children }) {
  return (
    <section className="min-w-0 overflow-hidden border border-friday-line bg-[#1a2028] p-3">
      <h2 className="mb-3 flex items-center gap-2 font-mono text-[11px] font-bold uppercase tracking-[.12em] text-[#cbd7e6]">{Icon ? <Icon size={14} className="text-friday-accent" /> : null}{title}</h2>
      {children}
    </section>
  );
}

function Metric({ label, value, warn }) {
  return <section className="border border-friday-line bg-[#1a2028] p-3"><span className="font-mono text-[10px] uppercase tracking-[.08em] text-friday-muted">{label}</span><strong className={`mt-1 block truncate text-[18px] ${warn ? "text-[#ffb56d]" : "text-friday-accent"}`}>{value}</strong></section>;
}

function ToolRow({ tool }) {
  return (
    <div className="border border-friday-line bg-[#10161d] p-3">
      <div className="flex items-center gap-2">
        {tool.available ? <CheckCircle2 size={14} className="text-friday-accent" /> : <XCircle size={14} className="text-[#ffaaa0]" />}
        <strong className="text-[12px]">{tool.label}</strong>
        <span className="ml-auto font-mono text-[10px] text-friday-muted">{tool.risk}</span>
      </div>
      <p className="mt-2 text-[12px] text-friday-muted">{tool.description}</p>
      <p className="mt-2 font-mono text-[10px] text-friday-muted">{tool.executable || "internal"} / {tool.category}</p>
    </div>
  );
}

function ResultRow({ result }) {
  const ok = result.ok || result.status === "passed";
  return (
    <div className="border border-friday-line bg-[#10161d] p-3">
      <div className="flex items-center gap-2">
        {ok ? <CheckCircle2 size={14} className="text-friday-accent" /> : <AlertTriangle size={14} className="text-[#ffb56d]" />}
        <strong className="text-[12px]">{result.label || result.tool}</strong>
        <span className="ml-auto font-mono text-[10px] text-friday-muted">{result.status}</span>
      </div>
      <p className="mt-2 text-[12px] text-friday-muted">{result.summary}</p>
      {result.artifact || result.stderr ? <p className="mt-2 truncate font-mono text-[10px] text-friday-muted">{result.artifact || result.stderr}</p> : null}
    </div>
  );
}

function ScopeRow({ scope }) {
  return (
    <div className="border border-friday-line bg-[#10161d] p-3">
      <div className="flex items-center gap-2">
        <ShieldCheck size={14} className={scope.status === "verified" ? "text-friday-accent" : "text-[#ffb56d]"} />
        <strong className="text-[12px]">{scope.target}</strong>
        <span className="ml-auto font-mono text-[10px] text-friday-muted">#{scope.id}</span>
      </div>
      <p className="mt-2 font-mono text-[10px] text-friday-muted">{scope.kind} / {scope.status}</p>
    </div>
  );
}

function lines(value) {
  return String(value || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
}

function labelize(value) {
  return String(value || "").replace(/[_-]+/g, " ");
}

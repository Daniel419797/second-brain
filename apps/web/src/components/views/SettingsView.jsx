"use client";

import { Archive, Cloud, GitBranch, Loader2, RefreshCw, ShieldCheck, UploadCloud, Wifi } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";

export function SettingsView() {
  const { api, interfaceFor } = useDashboard();
  const copy = interfaceFor?.("settings") || {};
  const [state, setState] = useState({});
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setBusy("refresh");
    setMessage("");
    const results = await Promise.allSettled([
      api("/providers/readiness"),
      api("/production/readiness"),
      api("/github/status"),
      api("/backup/list?limit=8"),
      api("/cloud-worker/status"),
      api("/cloud-worker/jobs?limit=8"),
      api("/metrics/api-benchmark")
    ]);
    const [providers, production, github, backups, cloud, jobs, benchmark] = results.map((result) => result.status === "fulfilled" ? result.value : null);
    setState({ providers, production, github, backups: backups || [], cloud, jobs: jobs || [], benchmark });
    const failed = results.find((result) => result.status === "rejected");
    if (failed) setMessage(failed.reason?.message || copy?.subtitle || "Some settings data could not be loaded.");
    setBusy("");
  }, [api, copy?.subtitle]);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(label, action, done) {
    setBusy(label);
    setMessage("");
    try {
      const result = await action();
      setMessage(result?.summary || done || `${labelize(label)} complete.`);
      await load();
    } catch (err) {
      setMessage(err.message || `${labelize(label)} failed.`);
      setBusy("");
    }
  }

  function probeProviders() {
    run("probe", () => api("/providers/readiness?probe=true"), "Provider readiness probe finished.");
  }

  function backupConfig() {
    run("backup", () => api("/backup/config", { method: "POST", body: JSON.stringify({ label: "dashboard settings backup" }) }), "Config backup created.");
  }

  function runSync() {
    run("sync", () => api("/sync/run", { method: "POST", body: JSON.stringify({}) }), "Cloud sync run finished.");
  }

  function submitCloudJob() {
    const title = window.prompt("Cloud worker job title", "Research latest project status");
    if (!title) return;
    run("cloud", () => api("/cloud-worker/submit", { method: "POST", body: JSON.stringify({ job_type: "research", title, payload: { source: "settings_dashboard" }, prefer_cloud: true }) }), "Cloud worker job submitted.");
  }

  return (
    <section className="grid w-full max-w-[1080px] min-w-0 content-start gap-4 text-[#eaf2fb]" aria-label="Settings">
      <header className="flex min-w-0 flex-wrap items-end gap-3">
        <div className="min-w-0">
          <h1 className="m-0 text-[26px] font-extrabold leading-tight text-white">{copy?.title || "Settings"}</h1>
          <p className="mt-1 text-[13px] text-friday-muted">{copy?.subtitle || "Operational configuration, readiness, backups, cloud sync, and worker controls."}</p>
        </div>
        <button className="ml-auto inline-flex min-h-9 items-center gap-2 rounded-[4px] border border-friday-line bg-[#151b22] px-3 text-[12px] font-bold text-white hover:border-friday-accent disabled:opacity-50" type="button" onClick={load} disabled={Boolean(busy)}>
          {busy === "refresh" ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />}
          {copy?.labels?.refresh || "Refresh"}
        </button>
      </header>

      {message ? <div className="rounded-[4px] border border-[#405063] bg-[#101820] px-4 py-3 text-[13px] text-[#dce9f8]">{message}</div> : null}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatusPanel icon={<Wifi size={17} />} title="Providers" value={providerReadyCount(state.providers)} detail={state.providers?.summary || "Provider readiness"} action="Probe" busy={busy === "probe"} onAction={probeProviders} />
        <StatusPanel icon={<ShieldCheck size={17} />} title="Production" value={readinessValue(state.production)} detail={state.production?.summary || "Production readiness"} />
        <StatusPanel icon={<GitBranch size={17} />} title="GitHub" value={state.github?.configured ? "Ready" : "Setup"} detail={state.github?.summary || "Repository status"} />
        <StatusPanel icon={<Cloud size={17} />} title="Cloud Worker" value={state.cloud?.enabled ? "Enabled" : "Local"} detail={state.cloud?.summary || "Worker runtime"} action="Submit" busy={busy === "cloud"} onAction={submitCloudJob} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Panel title="Backup And Sync" icon={<Archive size={15} />}>
          <div className="mb-4 flex flex-wrap gap-2">
            <ActionButton icon={<Archive size={14} />} label="Backup Config" busy={busy === "backup"} onClick={backupConfig} disabled={Boolean(busy)} />
            <ActionButton icon={<UploadCloud size={14} />} label="Run Sync" busy={busy === "sync"} onClick={runSync} disabled={Boolean(busy)} primary />
          </div>
          <div className="grid gap-2">
            {(state.backups || []).length ? state.backups.map((item) => (
              <div className="grid min-h-[50px] grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-[4px] border border-[#303b48] bg-[#101820] px-3" key={item.id}>
                <div className="min-w-0">
                  <strong className="block truncate text-[13px] text-white">{item.label || item.path || `Backup #${item.id}`}</strong>
                  <span className="mt-1 block truncate font-mono text-[10px] text-friday-muted">{item.created_at || item.timestamp || "saved"}</span>
                </div>
                <span className="font-mono text-[10px] uppercase text-friday-accent">{item.kind || "backup"}</span>
              </div>
            )) : <Empty text={copy?.empty?.evidence || "Friday has no backup record in this settings read."} />}
          </div>
        </Panel>

        <Panel title="API Benchmark" icon={<Wifi size={15} />}>
          <pre className="max-h-[254px] overflow-auto rounded-[4px] border border-friday-line bg-[#070c11] p-3 font-mono text-[11px] leading-relaxed text-[#dce6f2]">{stringify(state.benchmark || {})}</pre>
        </Panel>
      </div>

      <Panel title="Cloud Jobs" icon={<Cloud size={15} />}>
        <div className="grid gap-2">
          {(state.jobs || []).length ? state.jobs.map((job) => (
            <div className="grid min-h-[52px] grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-[4px] border border-[#303b48] bg-[#101820] px-3" key={job.id}>
              <div className="min-w-0">
                <strong className="block truncate text-[13px] text-white">{job.title || `Job #${job.id}`}</strong>
                <span className="mt-1 block truncate text-[11px] text-friday-muted">{job.job_type || job.kind || "worker job"}</span>
              </div>
              <span className="rounded-[3px] border border-[#405063] bg-[#202936] px-2 py-1 font-mono text-[10px] uppercase text-[#dce8f7]">{job.status || "queued"}</span>
            </div>
          )) : <Empty text={copy?.empty?.tasks || "Friday has no cloud worker job queued."} />}
        </div>
      </Panel>
    </section>
  );
}

function StatusPanel({ icon, title, value, detail, action, busy, onAction }) {
  return (
    <article className="grid min-h-[132px] content-between rounded-[5px] border border-friday-line bg-[#151b22] p-4">
      <header className="flex items-center gap-2">
        <span className="grid h-8 w-8 place-items-center rounded-[4px] border border-[#405063] bg-[#202936] text-friday-accent">{icon}</span>
        <h2 className="truncate text-[14px] font-extrabold text-white">{title}</h2>
      </header>
      <div>
        <strong className="block truncate text-[22px] leading-none text-white">{value}</strong>
        <p className="mt-2 line-clamp-2 text-[12px] leading-relaxed text-friday-muted">{detail}</p>
      </div>
      {action ? <button className="mt-3 inline-flex min-h-8 items-center justify-center gap-2 rounded-[3px] border border-friday-line bg-[#10161d] px-3 text-[12px] text-white hover:border-friday-accent disabled:opacity-50" type="button" onClick={onAction} disabled={busy}>{busy ? <Loader2 className="animate-spin" size={13} /> : null}{action}</button> : null}
    </article>
  );
}

function Panel({ title, icon, children }) {
  return (
    <section className="rounded-[5px] border border-friday-line bg-[#151b22] p-4">
      <div className="mb-3 flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-[.08em] text-white">{icon}{title}</div>
      {children}
    </section>
  );
}

function ActionButton({ icon, label, busy, disabled, primary, onClick }) {
  return (
    <button className={`inline-flex min-h-9 items-center gap-2 rounded-[4px] border px-3 text-[12px] font-bold disabled:opacity-50 ${primary ? "border-friday-blue bg-friday-blue text-[#061420]" : "border-friday-line bg-[#101820] text-white hover:border-friday-accent"}`} type="button" onClick={onClick} disabled={disabled}>
      {busy ? <Loader2 className="animate-spin" size={14} /> : icon}
      {label}
    </button>
  );
}

function Empty({ text }) {
  return <div className="grid min-h-[80px] place-items-center rounded-[4px] border border-[#303b48] bg-[#101820] px-3 text-center text-[12px] text-friday-muted">{text}</div>;
}

function providerReadyCount(providers) {
  const rows = Object.values(providers?.providers || {});
  if (!rows.length) return "n/a";
  return `${rows.filter((item) => item?.configured || item?.available || item?.ready).length}/${rows.length}`;
}

function readinessValue(production) {
  if (!production) return "n/a";
  if (production.ready != null) return production.ready ? "Ready" : "Review";
  if (production.score != null) return `${Math.round(Number(production.score) * 100)}%`;
  return production.status || "Loaded";
}

function labelize(value) {
  return String(value || "").replace(/[-_]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function stringify(value) {
  try {
    return JSON.stringify(value || {}, null, 2);
  } catch {
    return String(value || "");
  }
}

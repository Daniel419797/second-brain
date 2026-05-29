"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Bot, CheckCircle2, CircleAlert, FlaskConical, Loader2, ShieldCheck } from "lucide-react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";
import { wsUrl } from "@/services/fridayApi";

export function ReliabilityView() {
  const { api, data, refresh, token, interfaceFor } = useDashboard();
  const copy = interfaceFor?.("reliability") || {};
  const [lab, setLab] = useState(data.reliability || null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");

  useEffect(() => {
    if (data.reliability) {
      setLab(data.reliability);
      setLoading(false);
    }
  }, [data.reliability]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    let socket = null;
    let reconnectTimer = null;

    const connect = () => {
      socket = new WebSocket(wsUrl("/ws/reliability", token));
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          setLab(payload);
          setLoading(false);
        } catch {
          return;
        }
      };
      socket.onclose = () => {
        if (!cancelled) reconnectTimer = window.setTimeout(connect, 2500);
      };
      socket.onerror = () => {
        socket?.close();
      };
    };

    connect();
    return () => {
      cancelled = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [token]);

  async function refreshLab() {
    if (busy) return;
    setBusy(true);
    setStatus("");
    try {
      const payload = await api("/reliability/dashboard/refresh", { method: "POST", body: JSON.stringify({}) });
      setLab(payload);
      setStatus("Reliability snapshot refreshed.");
      await refresh();
    } catch (err) {
      setStatus(err.message || "Reliability refresh failed.");
    } finally {
      setBusy(false);
      setLoading(false);
    }
  }

  const metrics = lab?.metrics || [];
  const voiceSamples = lab?.voice?.samples || [];
  const events = lab?.evaluation?.events || [];
  const benchmarkRows = lab?.benchmark?.rows || [];
  const activeBackend = lab?.voice?.backend_active || "";
  const monitors = lab?.active_monitors || { count: 0, sources: [] };
  const thought = lab?.thought_summary || copy?.subtitle || "Reliability telemetry is warming up.";

  return (
    <section className="friday-scroll h-full min-h-0 overflow-y-auto bg-[#080d11] px-4 py-4 text-[#eaf2fb]" aria-label="Reliability lab">
      <main className="grid w-full min-w-0 content-start gap-4 pb-4">
        <div className="grid min-w-0 grid-cols-[repeat(auto-fit,minmax(126px,1fr))] gap-3 2xl:grid-cols-7">
          {(metrics.length ? metrics : skeletonMetrics()).map((metric) => <MetricTile metric={metric} loading={loading && !lab} key={metric.id} />)}
        </div>

        <div className="grid min-w-0 gap-3 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="grid min-w-0 content-start gap-3">
            <VoiceReliabilityLab samples={voiceSamples} copy={copy} activeBackend={activeBackend} loading={loading && !lab} />
            <EvaluationLog events={events} copy={copy} loading={loading && !lab} />
          </div>

          <aside className="grid min-w-0 content-start gap-3">
            <BenchmarkPanel rows={benchmarkRows} summary={lab?.benchmark?.summary} copy={copy} />
            <ThoughtPanel thought={thought} monitors={monitors} />
            <ReliabilityArt onRefresh={refreshLab} busy={busy} />
          </aside>
        </div>

        {status ? (
          <div className="fixed bottom-5 right-5 z-20 max-w-[380px] rounded-[4px] border border-[#45678c] bg-[#9fcaff] px-4 py-3 text-[13px] font-semibold text-[#07111d] shadow-[0_16px_40px_rgba(0,0,0,.32)]">
            {status}
          </div>
        ) : null}
      </main>
    </section>
  );
}

function MetricTile({ metric, loading }) {
  const tone = metricTone(metric.tone, metric.id);
  return (
    <article className={`min-h-[88px] rounded-[7px] border bg-[#151a21] px-3 py-4 ${tone.border}`}>
      <h3 className="m-0 truncate text-[12px] font-bold tracking-[.04em] text-[#cfd8e5]">{metric.label}</h3>
      <div className="mt-2 flex min-w-0 items-end gap-1">
        <strong className={`min-w-0 font-mono text-[25px] font-black leading-none ${tone.text}`}>
          {loading ? "--" : formatMetricValue(metric.value)}
          {metric.unit ? <span>{metric.unit}</span> : null}
        </strong>
        {metric.delta ? <span className="mb-1 truncate font-mono text-[11px] text-friday-accent">{metric.delta}</span> : null}
        {metric.badge ? <span className="mb-0.5 ml-auto rounded-[2px] border border-[#53677f] bg-[#253143] px-1.5 py-0.5 font-mono text-[9px] text-[#cfe2fb]">{metric.badge}</span> : null}
      </div>
    </article>
  );
}

function VoiceReliabilityLab({ samples, copy, activeBackend, loading }) {
  return (
    <Panel>
      <header className="flex min-h-[56px] items-center gap-3 border-b border-friday-line px-4">
        <h2 className="text-[18px] font-extrabold text-white">Voice Reliability Lab</h2>
        <span className="ml-auto rounded-[3px] border border-[#4f6680] bg-[#263347] px-2.5 py-1 font-mono text-[10px] font-bold uppercase text-friday-accent">
          {activeBackend ? `${backendBadge(activeBackend)} active` : "backend not reported"}
        </span>
      </header>
      <div className="friday-scroll overflow-x-auto">
        <div className="min-w-[640px]">
          <div className="grid min-w-0 grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)_96px_112px_64px] border-b border-friday-line px-4 py-2.5 font-mono text-[11px] font-bold tracking-[.06em] text-[#c8d2df]">
            <span>Heard Text</span>
            <span>Corrected Text</span>
            <span>Backend</span>
            <span>Confidence</span>
            <span>Duration</span>
          </div>
          <div className="grid">
            {loading ? (
              <LabEmpty label="Loading voice reliability samples..." />
            ) : samples.length ? (
              samples.slice(0, 3).map((sample) => <VoiceSampleRow sample={sample} key={sample.id} />)
            ) : (
              <LabEmpty label={copy?.empty?.evidence || "Friday has no voice reliability sample in this read yet."} />
            )}
          </div>
        </div>
      </div>
    </Panel>
  );
}

function VoiceSampleRow({ sample }) {
  const confidence = confidencePercent(sample.confidence, sample.accepted);
  const corrected = sample.correction_applied || !sample.accepted ? sample.expected_text || "--" : "--";
  return (
    <article className="grid min-h-[64px] min-w-0 grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)_96px_112px_64px] items-center gap-3 border-b border-friday-line px-4 last:border-b-0">
      <p className="m-0 line-clamp-2 text-[13px] leading-snug text-white">"{sample.heard_text || sample.raw_text || "--"}"</p>
      <p className="m-0 line-clamp-2 text-[13px] italic leading-snug text-friday-accent">{corrected === "--" ? "--" : `"${corrected}"`}</p>
      <span className="break-all font-mono text-[11px] text-white">{shortBackend(sample.backend)}</span>
      <span className="flex items-center gap-2">
        <span className="h-1.5 w-10 overflow-hidden rounded-full bg-[#28313b]">
          <span className={`block h-full ${confidence.value >= 90 ? "bg-friday-accent" : "bg-[#ffb277]"}`} style={{ width: `${confidence.value}%` }} />
        </span>
        <b className={`font-mono text-[11px] ${confidence.value >= 90 ? "text-white" : "text-[#ffb277]"}`}>{confidence.label}</b>
      </span>
      <span className="font-mono text-[12px] text-white">{durationLabel(sample.audio_seconds)}</span>
    </article>
  );
}

function EvaluationLog({ events, copy, loading }) {
  return (
    <Panel className="p-4">
      <h2 className="mb-4 text-[18px] font-extrabold text-white">Evaluation Events Log</h2>
      <div className="grid gap-3">
        {loading ? (
          <LabEmpty label="Loading evaluation events..." />
        ) : events.length ? (
          events.slice(0, 3).map((event) => <EventRow event={event} key={event.id} />)
        ) : (
          <LabEmpty label={copy?.empty?.activity || "Friday has no reliability event in this read yet."} />
        )}
      </div>
    </Panel>
  );
}

function EventRow({ event }) {
  const meta = eventMeta(event.category);
  const Icon = meta.icon;
  const mod = event.model || event.backend || event.source || "system";
  return (
    <article className={`grid min-h-[92px] min-w-0 grid-cols-[40px_minmax(0,1fr)_66px] gap-3 border-l-4 py-3 pl-4 ${meta.border}`}>
      <span className={`mt-1 grid h-6 w-6 place-items-center ${meta.text}`}>
        <Icon size={20} />
      </span>
      <div className="min-w-0">
        <strong className="block font-mono text-[12px] uppercase tracking-[.08em] text-white">{meta.label}</strong>
        <p className="mt-1 line-clamp-2 text-[13px] leading-snug text-[#d8e2ee]">{event.summary}</p>
        <div className="mt-2 flex flex-wrap gap-2">
          <span className="rounded-[2px] bg-[#202733] px-2 py-1 font-mono text-[10px] uppercase text-[#cbd7e6]">ID: EV-{event.id}</span>
          <span className="rounded-[2px] bg-[#202733] px-2 py-1 font-mono text-[10px] uppercase text-[#cbd7e6]">MOD: {mod}</span>
        </div>
      </div>
      <span className="font-mono text-[11px] text-white">{formatClock(event.timestamp)}</span>
    </article>
  );
}

function BenchmarkPanel({ rows, summary, copy }) {
  return (
    <Panel className="p-4">
      <div className="mb-4 flex items-center gap-3">
        <h2 className="text-[18px] font-extrabold text-white">Capabilities Benchmark</h2>
      </div>
      <div className="grid gap-4">
        {rows.length ? rows.map((row) => <BenchmarkRow row={row} key={row.id} />) : <LabEmpty label={copy?.empty?.evidence || "No benchmark rows came back from the backend yet."} />}
      </div>
      <p className="mt-5 border-t border-friday-line pt-4 text-[12px] leading-relaxed text-[#d6e0ed]">
        {summary || "Friday has no benchmark summary from the backend yet."}
      </p>
    </Panel>
  );
}

function BenchmarkRow({ row }) {
  const score = Math.max(0, Math.min(100, Math.round(Number(row.score) || 0)));
  return (
    <div>
      <div className="mb-2 flex items-center gap-3">
        <strong className="min-w-0 flex-1 truncate text-[13px] text-white">{row.label}</strong>
        <span className="font-mono text-[12px] text-friday-accent">{score}/100</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-[#28313b]">
        <span className="block h-full bg-friday-accent" style={{ width: `${score}%` }} />
      </div>
    </div>
  );
}

function ThoughtPanel({ thought, monitors }) {
  const sources = monitors.sources || [];
  return (
    <Panel className="p-4">
      <h2 className="mb-4 flex items-center gap-3 font-mono text-[14px] font-bold uppercase tracking-[.12em] text-[#ffb277]">
        <Bot size={20} />
        Friday's Thought Summary
      </h2>
      <blockquote className="m-0 rounded-[2px] bg-[#303743] p-3 text-[13px] leading-relaxed text-[#e4edf8]">"{thought}"</blockquote>
      <div className="mt-4 flex min-w-0 items-center gap-3">
        <span className="flex shrink-0 -space-x-2">
          {sources.length ? sources.slice(0, 3).map((source, index) => (
            <span className={`grid h-7 w-7 place-items-center rounded-full text-[10px] font-bold text-white ${index % 2 ? "bg-[#f28b24]" : "bg-friday-blue"}`} key={source}>
              {initials(source)}
            </span>
          )) : <span className="grid h-7 w-7 place-items-center rounded-full border border-dashed border-friday-line text-[10px] text-friday-muted">--</span>}
        </span>
        <span className="truncate text-[12px] text-[#d8e2ee]">Active monitoring by {monitors.count || sources.length || 0} system agent{(monitors.count || sources.length) === 1 ? "" : "s"}.</span>
      </div>
    </Panel>
  );
}

function ReliabilityArt({ onRefresh, busy }) {
  return (
    <section className="relative min-h-[104px] overflow-hidden rounded-[8px] border border-friday-line bg-[#07131b]">
      <div className="absolute inset-0 opacity-90" style={{ backgroundImage: "linear-gradient(160deg, rgba(9,29,42,.96), rgba(7,15,22,.78)), repeating-linear-gradient(170deg, rgba(159,202,255,.10) 0 1px, transparent 1px 18px)", backgroundSize: "100% 100%, 100% 28px" }} />
      <span className="absolute left-[-18%] top-[28%] h-[2px] w-[136%] -rotate-[7deg] rounded-full bg-[#0ea5e9]/45 shadow-[0_0_18px_rgba(14,165,233,.45)]" />
      <span className="absolute left-[-8%] top-[52%] h-[2px] w-[126%] rotate-[5deg] rounded-full bg-[#38bdf8]/40 shadow-[0_0_16px_rgba(56,189,248,.38)]" />
      <span className="absolute left-[10%] bottom-[21%] h-[2px] w-[102%] -rotate-[11deg] rounded-full bg-[#0284c7]/55 shadow-[0_0_18px_rgba(2,132,199,.45)]" />
      <button className="absolute bottom-0 right-0 grid h-14 w-14 place-items-center rounded-tl-[14px] bg-friday-accent text-[#07111d] shadow-[0_0_32px_rgba(159,202,255,.28)] disabled:opacity-60" type="button" onClick={onRefresh} disabled={busy} title="Run reliability lab snapshot">
        {busy ? <Loader2 className="animate-spin" size={22} /> : <FlaskConical size={24} />}
      </button>
    </section>
  );
}

function Panel({ className = "", children }) {
  return <section className={`min-w-0 overflow-hidden rounded-[8px] border border-[#3b4654] bg-[#151a21] ${className}`}>{children}</section>;
}

function LabEmpty({ label }) {
  return <div className="grid min-h-[120px] place-items-center p-6 text-center text-[13px] text-friday-muted">{label}</div>;
}

function metricTone(tone, id) {
  if (id === "false_claims") return { border: "border-[#644247]", text: "text-white" };
  if (tone === "danger") return { border: "border-[#6d4549]", text: "text-[#ffaaa6]" };
  if (tone === "warn") return { border: "border-[#69503b]", text: "text-[#ffb277]" };
  if (tone === "blue") return { border: "border-[#3f5369]", text: "text-friday-accent" };
  return { border: "border-friday-line", text: "text-white" };
}

function eventMeta(category) {
  const value = String(category || "").toLowerCase();
  if (value === "failed_tool" || value === "agent_failure") return { label: "Failed Tool Call", border: "border-[#ffaaa6]", text: "text-[#ffaaa6]", icon: CircleAlert };
  if (value === "unsupported_claim") return { label: "Unsupported Claim", border: "border-[#ffb277]", text: "text-[#ffb277]", icon: AlertTriangle };
  if (value === "task_completed") return { label: "Recovered Failure", border: "border-friday-accent", text: "text-friday-accent", icon: CheckCircle2 };
  if (value === "stt_mistake") return { label: "STT Correction", border: "border-[#ffb277]", text: "text-[#ffb277]", icon: AlertTriangle };
  if (value === "task_stuck") return { label: "Agent Stuck", border: "border-[#ffaaa6]", text: "text-[#ffaaa6]", icon: CircleAlert };
  return { label: value.replace(/_/g, " ") || "Reliability Event", border: "border-friday-accent", text: "text-friday-accent", icon: ShieldCheck };
}

function confidencePercent(value, accepted) {
  const num = Number(value);
  if (Number.isFinite(num)) return { value: Math.round(Math.max(0, Math.min(1, num)) * 100), label: `${Math.round(Math.max(0, Math.min(1, num)) * 100)}%` };
  return { value: 0, label: accepted ? "OK" : "Fix" };
}

function durationLabel(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value <= 0) return "--";
  return `${value.toFixed(value >= 10 ? 0 : 1)}s`;
}

function formatMetricValue(value) {
  if (value == null || value === "") return "--";
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);
  return Number.isInteger(num) ? String(num) : num.toFixed(1);
}

function formatClock(value) {
  if (!value) return "--:--";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "--:--";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

function shortBackend(value) {
  return String(value || "voice").replace("deepgram-realtime-web", "deepgram").replace("browser-web-speech", "web-speech");
}

function backendBadge(value) {
  return String(value || "").replace(/[^a-z0-9]+/gi, "_").replace(/^_+|_+$/g, "").toUpperCase() || "NOT_REPORTED";
}

function initials(value) {
  return String(value || "AI").split(/[_\s-]+/).filter(Boolean).map((part) => part[0]).join("").slice(0, 2).toUpperCase() || "AI";
}

function skeletonMetrics() {
  return [
    { id: "stt_accuracy", label: "STT Accuracy", value: null, unit: "%", tone: "blue" },
    { id: "avg_latency", label: "Avg Latency", value: null, unit: "ms", tone: "blue" },
    { id: "tool_success", label: "Tool Success", value: null, unit: "%", tone: "blue" },
    { id: "false_claims", label: "False Claims", value: null, unit: "", tone: "neutral" },
    { id: "failed_commands", label: "Failed Cmds", value: null, unit: "", tone: "danger" },
    { id: "slow_responses", label: "Slow Resp", value: null, unit: "", tone: "warn" },
    { id: "agent_stuck", label: "Agent Stuck", value: null, unit: "", tone: "danger" }
  ];
}

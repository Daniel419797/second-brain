"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  Camera,
  Eye,
  Loader2,
  Maximize2,
  Monitor,
  Plus,
  RefreshCw,
  ScanLine,
  StopCircle,
  Video,
  ZoomIn
} from "lucide-react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";
import { API_URL } from "@/lib/config";

export function VisionView() {
  const { api, token, data, refresh, interfaceFor } = useDashboard();
  const copy = interfaceFor?.("vision") || {};
  const [monitor, setMonitor] = useState(null);
  const [events, setEvents] = useState([]);
  const [pc, setPc] = useState(null);
  const [skills, setSkills] = useState(null);
  const [screenMemory, setScreenMemory] = useState(null);
  const [desktopTasks, setDesktopTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [status, setStatus] = useState("");
  const [streamKey, setStreamKey] = useState(0);
  const [inspecting, setInspecting] = useState("");

  const loadVision = useCallback(async () => {
    setLoading(true);
    setStatus("");
    const [monitorResult, eventsResult, pcResult, skillsResult, memoryResult, tasksResult] = await Promise.allSettled([
      api("/vision/monitor"),
      api("/vision/events?limit=12"),
      api("/pc/awareness"),
      api("/vision-skills/status"),
      api("/visual-skill-memory/status"),
      api("/desktop/tasks?limit=8")
    ]);
    if (monitorResult.status === "fulfilled") setMonitor(monitorResult.value);
    if (eventsResult.status === "fulfilled") setEvents(Array.isArray(eventsResult.value) ? eventsResult.value : []);
    if (pcResult.status === "fulfilled") setPc(pcResult.value);
    if (skillsResult.status === "fulfilled") setSkills(skillsResult.value);
    if (memoryResult.status === "fulfilled") setScreenMemory(memoryResult.value);
    if (tasksResult.status === "fulfilled") setDesktopTasks(Array.isArray(tasksResult.value) ? tasksResult.value : []);
    const failed = [monitorResult, eventsResult, pcResult, skillsResult, memoryResult, tasksResult].find((result) => result.status === "rejected");
    if (failed) setStatus(failed.reason?.message || "Some vision data could not be loaded.");
    setLoading(false);
  }, [api]);

  useEffect(() => {
    loadVision();
  }, [loadVision]);

  const awareness = pc || data.pcAwareness || {};
  const runningApps = useMemo(() => importantApps(awareness.running_apps || []), [awareness.running_apps]);
  const patterns = useMemo(() => normalizePatterns(skills, screenMemory), [skills, screenMemory]);
  const latestEvent = events[0] || monitor?.latest_event || null;
  const streamPath = monitor?.running ? monitor.live_stream_url || "/vision/live/screen" : "";
  const stillPath = latestEvent?.frame_url || "";
  const displaySrc = streamPath ? assetUrl(streamPath, token, streamKey) : assetUrl(stillPath, token, streamKey);
  const activeWindow = parseActiveWindow(awareness.active_window);
  const displays = Math.max(1, Number(awareness.displays?.length || awareness.display_count || 1));

  async function refreshAwareness() {
    setBusy("awareness");
    setStatus("");
    try {
      const fresh = await api("/pc/awareness/refresh", { method: "POST", body: JSON.stringify({}) });
      setPc(fresh);
      setStatus("PC awareness refreshed.");
      await refresh();
    } catch (err) {
      setStatus(err.message || "PC awareness refresh failed.");
    } finally {
      setBusy("");
    }
  }

  async function toggleMonitor() {
    const running = Boolean(monitor?.running);
    setBusy("monitor");
    setStatus("");
    try {
      const next = await api(running ? "/vision/monitor/stop" : "/vision/monitor/start", {
        method: "POST",
        body: JSON.stringify(running ? {} : { source: "screen", realtime: true })
      });
      setMonitor(next);
      setStreamKey((value) => value + 1);
      setStatus(running ? "Screen monitor stopped." : "Screen monitor started.");
    } catch (err) {
      setStatus(err.message || "Screen monitor action failed.");
    } finally {
      setBusy("");
    }
  }

  async function captureFrame() {
    setBusy("capture");
    setStatus("");
    try {
      const result = await api("/vision/monitor/capture", {
        method: "POST",
        body: JSON.stringify({ source: "screen", analyze: false })
      });
      setMonitor(result.status || monitor);
      setEvents((items) => [...(result.events || []), ...items].slice(0, 12));
      setStreamKey((value) => value + 1);
      setStatus("Screen frame captured.");
    } catch (err) {
      setStatus(err.message || "Frame capture failed.");
    } finally {
      setBusy("");
    }
  }

  async function addVisualPattern() {
    const label = window.prompt("Pattern label", activeWindow.title || "Useful screen pattern");
    if (!label) return;
    const meaning = window.prompt("What should Friday remember about it?", "Recognize this screen and suggest the next action.") || "";
    setBusy("pattern");
    setStatus("");
    try {
      await api("/visual-skill-memory/screen", {
        method: "POST",
        body: JSON.stringify({
          app: activeWindow.title,
          screen_label: label,
          cues: [activeWindow.title, latestEvent?.summary || ""].filter(Boolean),
          meaning,
          action_hint: meaning,
          source: "dashboard_vision"
        })
      });
      setStatus("Visual pattern saved.");
      await loadVision();
      void refresh();
    } catch (err) {
      setStatus(err.message || "Visual pattern could not be saved.");
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="min-h-full bg-[#0a0f14] text-[#eaf2fb]" aria-label="PC and Live Vision">
      <main className="grid min-w-0 content-start gap-3">
          <header className="flex min-h-[58px] min-w-0 flex-wrap items-start gap-3">
            <div className="min-w-0">
              <h2 className="m-0 text-[24px] font-extrabold tracking-normal text-white">{copy?.title || "PC & Live Vision"}</h2>
              <p className="mt-1 text-[13px] leading-snug text-[#c5d0de]">
                {copy?.subtitle || `Monitoring ${displays} display${displays === 1 ? "" : "s"} - ${monitor?.running ? "Active pattern recognition" : "Screen monitor idle"}`}
              </p>
            </div>
            <div className="ml-auto flex shrink-0 flex-wrap items-center justify-end gap-2">
              <ToolbarButton
                icon={busy === "awareness" ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />}
                label="Refresh PC awareness"
                onClick={refreshAwareness}
                disabled={Boolean(busy)}
              />
              <ToolbarButton
                icon={busy === "monitor" ? <Loader2 className="animate-spin" size={14} /> : monitor?.running ? <StopCircle size={14} /> : <Video size={14} />}
                label={monitor?.running ? "Stop screen monitor" : "Start screen monitor"}
                onClick={toggleMonitor}
                disabled={Boolean(busy)}
                primary
              />
            </div>
          </header>

          <div className="grid min-w-0 gap-3 xl:grid-cols-[minmax(560px,1fr)_322px]">
            <div className="grid min-w-0 content-start gap-3">
              <LiveDisplay
                loading={loading}
                displaySrc={displaySrc}
                monitor={monitor}
                latestEvent={latestEvent}
                activeWindow={activeWindow}
                onCapture={captureFrame}
                onInspect={() => setInspecting(displaySrc)}
                busy={busy}
                copy={copy}
              />
              <div className="grid min-w-0 gap-3 md:grid-cols-[minmax(0,1fr)_322px]">
                <RunningApps apps={runningApps} copy={copy} activeWindow={activeWindow} total={awareness.stats?.running_apps || awareness.running_apps?.length || 0} />
                <MonitorStatus monitor={monitor} onCapture={captureFrame} busy={busy} />
              </div>
              <CaptureTimeline events={events} copy={copy} token={token} />
            </div>

            <PatternPanel patterns={patterns} copy={copy} onAdd={addVisualPattern} busy={busy} />
          </div>

          {status ? (
            <div className="fixed bottom-5 right-5 z-20 max-w-[360px] rounded-[4px] border border-[#45678c] bg-[#9fcaff] px-4 py-3 text-[13px] font-semibold text-[#07111d] shadow-[0_16px_40px_rgba(0,0,0,.32)]">
              {status}
            </div>
          ) : null}
          {inspecting ? <FrameInspector src={inspecting} onClose={() => setInspecting("")} /> : null}
        </main>
    </section>
  );
}

function LiveDisplay({ loading, displaySrc, monitor, latestEvent, activeWindow, onCapture, onInspect, busy, copy }) {
  return (
    <section className="min-w-0 overflow-hidden rounded-[6px] border border-[#0f7fab] bg-[#05080b] p-3 shadow-[0_0_28px_rgba(36,152,238,.12)]">
      <div className="relative h-[344px] overflow-hidden rounded-[4px] border border-[#13202c] bg-[#080d11]">
        {displaySrc ? (
          <img className="h-full w-full object-cover opacity-80" src={displaySrc} alt="Live screen monitor frame" />
        ) : (
          <div className="grid h-full place-items-center bg-[radial-gradient(circle_at_center,#182331,#080d11_62%)]">
            <div className="grid justify-items-center gap-3 text-center">
              {loading ? <Loader2 className="animate-spin text-friday-accent" size={28} /> : <Monitor className="text-friday-accent" size={32} />}
              <div>
                <strong className="block font-mono text-[12px] uppercase tracking-[.16em] text-friday-accent">
                  {loading ? "Loading vision feed" : copy?.empty?.frames || "Friday has no captured frame in this read"}
                </strong>
                <span className="mt-2 block max-w-[320px] text-[12px] leading-relaxed text-[#c2cedd]">{copy?.subtitle || "Start the screen monitor or capture a frame to populate the live vision surface."}</span>
              </div>
            </div>
          </div>
        )}
        <div className="absolute left-4 top-4 rounded-[3px] border border-[#33404d] bg-[#10161d]/90 px-3 py-2 font-mono text-[11px] uppercase tracking-[.14em] text-friday-accent">
          DISPLAY_01_{monitor?.running ? "ACTIVE" : "IDLE"}
        </div>
        <div className="absolute right-4 top-4 rounded-[3px] border border-[#765a55] bg-[#3a2b28]/90 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[.1em] text-[#ffd0c9]">
          {monitor?.running ? "Live Feed" : latestEvent ? "Latest Frame" : "Standby"}
        </div>
        <div className="absolute bottom-4 left-4 max-w-[360px] rounded-[3px] border border-[#263341] bg-[#05080b]/92 px-3 py-3">
          <strong className="block truncate text-[12px] text-white">Active Window: {activeWindow.title}</strong>
          <span className="mt-2 block truncate font-mono text-[10px] text-[#cbd7e6]">
            PID: {activeWindow.pid || "n/a"} | Focus Time: {latestEvent ? timeAgo(latestEvent.timestamp) : "live"}
          </span>
        </div>
        <div className="absolute bottom-4 right-4 flex gap-2">
          <button className="grid h-10 w-10 place-items-center rounded-[3px] border border-friday-line bg-[#202733]/90 text-white transition-colors hover:border-friday-accent" type="button" onClick={onCapture} disabled={Boolean(busy)} title="Capture frame">
            {busy === "capture" ? <Loader2 className="animate-spin" size={17} /> : <Maximize2 size={17} />}
          </button>
          <button className="grid h-10 w-10 place-items-center rounded-[3px] border border-friday-line bg-[#202733]/90 text-white transition-colors hover:border-friday-accent disabled:opacity-50" type="button" title="Inspect frame" onClick={onInspect} disabled={!displaySrc}>
            <ZoomIn size={17} />
          </button>
        </div>
      </div>
    </section>
  );
}

function RunningApps({ apps, copy, activeWindow, total }) {
  return (
    <Panel className="h-[192px] p-3">
      <div className="mb-3 flex items-center gap-3">
        <PanelTitle title="Running Apps" />
        <span className="ml-auto font-mono text-[10px] uppercase text-friday-accent">{total || apps.length} total</span>
      </div>
      <div className="grid gap-1.5">
        {apps.length ? apps.slice(0, 3).map((app) => {
          const inFocus = appMatchesWindow(app, activeWindow);
          return (
            <div className="grid min-h-[39px] grid-cols-[20px_minmax(0,1fr)_auto] items-center gap-2 rounded-[3px] border border-friday-line bg-[#252b34] px-2" key={`${app.pid || app.name}-${app.launch_target || app.exe}`}>
              <Monitor size={13} className={inFocus ? "text-friday-accent" : "text-[#cbd7e6]"} />
              <span className="min-w-0 truncate text-[13px] text-white">{cleanAppName(app.name)}</span>
              <span className="font-mono text-[10px] text-[#cbd7e6]">{inFocus ? "In Focus" : app.pid ? `PID ${app.pid}` : "Background"}</span>
            </div>
          );
        }) : (
          <p className="m-0 border border-friday-line bg-[#10161d] p-3 text-[12px] text-friday-muted">{copy?.empty?.evidence || "Friday has no running app inventory in this read."}</p>
        )}
      </div>
    </Panel>
  );
}

function MonitorStatus({ monitor, onCapture, busy }) {
  const source = monitor?.source || "screen";
  const tiles = [
    { label: "Screen", icon: <Monitor size={20} />, active: source === "screen" || source === "both" },
    { label: "Display", icon: <ScanLine size={20} />, active: Boolean(monitor?.running) },
    { label: "Camera", icon: <Camera size={20} />, active: source === "camera" || source === "both" },
    { label: "Realtime", icon: <Activity size={20} />, active: Boolean(monitor?.realtime) }
  ];
  return (
    <Panel className="h-[192px] p-3">
      <PanelTitle title="Live Monitor Status" />
      <div className="mt-4 grid grid-cols-4 gap-2">
        {tiles.map((tile) => (
          <div className={`grid h-[66px] place-items-center rounded-[3px] border ${tile.active ? "border-[#45678c] bg-[#172334] text-friday-accent" : "border-friday-line bg-[#303743] text-[#c2cedd]"}`} key={tile.label} title={tile.label}>
            {tile.icon}
          </div>
        ))}
      </div>
      <button
        className="mt-4 inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-[3px] border border-friday-line bg-[#303743] text-[13px] font-semibold text-[#eaf2fb] transition-colors hover:border-friday-accent disabled:opacity-50"
        type="button"
        onClick={onCapture}
        disabled={Boolean(busy)}
      >
        {busy === "capture" ? <Loader2 className="animate-spin" size={15} /> : <Camera size={15} />}
        Capture frame
      </button>
    </Panel>
  );
}

function PatternPanel({ patterns, copy, onAdd, busy }) {
  return (
    <Panel className="min-h-[760px] p-0">
      <header className="flex min-h-[76px] items-center gap-3 border-b border-friday-line px-4">
        <div className="min-w-0">
          <h3 className="m-0 text-[16px] font-extrabold text-white">Learned Visual Patterns</h3>
          <p className="mt-1 text-[13px] text-[#c2cedd]">Active recognition profiles</p>
        </div>
        <button className="ml-auto grid h-8 w-8 place-items-center rounded-full border border-friday-accent text-friday-accent transition-colors hover:bg-[#172334] disabled:opacity-50" type="button" title="Add visual pattern" onClick={onAdd} disabled={Boolean(busy)}>
          {busy === "pattern" ? <Loader2 className="animate-spin" size={16} /> : <Plus size={16} />}
        </button>
      </header>
      <div className="friday-scroll grid max-h-[680px] gap-3 overflow-y-auto p-4">
        {patterns.length ? patterns.map((pattern) => <PatternCard pattern={pattern} key={pattern.id || `${pattern.app}-${pattern.label}`} />) : (
          <div className="grid min-h-[220px] place-items-center rounded-[4px] border border-friday-line bg-[#10161d] p-4 text-center">
            <div>
              <Eye className="mx-auto text-friday-accent" size={24} />
              <strong className="mt-3 block text-[13px] text-white">{copy?.empty?.patterns || "Friday has no learned visual pattern in this view yet"}</strong>
              <p className="mt-2 text-[12px] leading-relaxed text-[#c2cedd]">{copy?.subtitle || "Friday will list UI patterns here after visual-skill learning records screens or reusable interface cues."}</p>
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}

function FrameInspector({ src, onClose }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4" role="dialog" aria-modal="true" aria-label="Inspect captured frame">
      <section className="grid max-h-[92dvh] w-[920px] max-w-[calc(100dvw-32px)] grid-rows-[auto_minmax(0,1fr)] overflow-hidden rounded-[6px] border border-[#334154] bg-[#111821]">
        <header className="flex items-center gap-3 border-b border-friday-line px-4 py-3">
          <h2 className="text-[16px] font-extrabold text-white">Frame Inspector</h2>
          <button className="ml-auto min-h-8 border border-friday-line bg-[#151b22] px-3 text-[12px] text-white hover:border-friday-accent" type="button" onClick={onClose}>Close</button>
        </header>
        <div className="min-h-0 overflow-auto bg-[#05080b] p-3">
          <img className="mx-auto max-h-[76dvh] max-w-full object-contain" src={src} alt="Inspected vision frame" />
        </div>
      </section>
    </div>
  );
}

function PatternCard({ pattern }) {
  const confidence = confidencePercent(pattern.confidence);
  return (
    <article className="grid min-h-[94px] grid-cols-[64px_minmax(0,1fr)_auto] gap-3 rounded-[4px] border border-friday-line bg-[#1c222b] p-3">
      <div className="grid h-12 place-items-center overflow-hidden rounded-[2px] border border-[#3a4654] bg-[#0b1117]">
        <ScanLine className="text-[#8da0b4]" size={20} />
      </div>
      <div className="min-w-0">
        <strong className="block truncate text-[13px] text-white">{pattern.label || pattern.screen_label || "Visual pattern"}</strong>
        <span className="mt-1 block truncate text-[11px] text-[#c2cedd]">{pattern.app || pattern.pattern_type || "screen"}</span>
        <p className="mt-2 line-clamp-2 text-[11px] leading-relaxed text-[#c2cedd]">{pattern.meaning || pattern.action_hint || "Friday has no note stored for this pattern yet."}</p>
      </div>
      <span className={`h-fit rounded-[3px] border px-2 py-1 font-mono text-[10px] ${confidence.tone}`}>{confidence.label}</span>
    </article>
  );
}

function CaptureTimeline({ events, copy, token }) {
  return (
    <Panel className="h-[170px] p-3">
      <PanelTitle title="Chronological Captures" />
      <div className="friday-scroll mt-4 flex gap-3 overflow-x-auto pb-1">
        {events.length ? events.slice(0, 8).map((event) => (
          <div className="grid w-[128px] shrink-0 gap-2" key={event.id || event.frame_name || event.timestamp}>
            <div className="grid h-[72px] place-items-center overflow-hidden rounded-[2px] border border-[#3a4654] bg-[#0b1117]">
              {event.frame_url ? <img className="h-full w-full object-cover" src={assetUrl(event.frame_url, token)} alt={event.summary || "Captured vision frame"} /> : <Monitor className="text-friday-accent" size={18} />}
            </div>
            <span className="truncate text-center font-mono text-[10px] text-[#cbd7e6]">{formatTime(event.timestamp)}</span>
          </div>
        )) : (
          <div className="grid min-h-[92px] min-w-full place-items-center text-center text-[12px] text-friday-muted">{copy?.empty?.frames || "Friday has no visual capture yet. Capture one frame to create the first timeline entry."}</div>
        )}
      </div>
    </Panel>
  );
}

function ToolbarButton({ icon, label, primary, disabled, onClick }) {
  return (
    <button
      className={`inline-flex min-h-[38px] items-center gap-2 rounded-[2px] border px-4 text-[13px] font-semibold transition-colors disabled:opacity-50 ${
        primary ? "border-[#97c8f8] bg-[#97c8f8] text-[#05111d] hover:bg-[#b2d8ff]" : "border-friday-line bg-[#151b22] text-[#eaf2fb] hover:border-friday-accent"
      }`}
      type="button"
      disabled={disabled}
      onClick={onClick}
    >
      {icon}
      {label}
    </button>
  );
}

function Panel({ className = "", children }) {
  return <section className={`min-w-0 rounded-[6px] border border-friday-line bg-[#151b22] ${className}`}>{children}</section>;
}

function PanelTitle({ title }) {
  return <h3 className="m-0 font-mono text-[11px] font-bold uppercase tracking-[.16em] text-white">{title}</h3>;
}

function assetUrl(path, token, cacheKey = 0) {
  if (!path || !token) return "";
  const separator = path.includes("?") ? "&" : "?";
  const cache = cacheKey ? `&v=${encodeURIComponent(cacheKey)}` : "";
  return `${API_URL}${path}${separator}token=${encodeURIComponent(token)}${cache}`;
}

function normalizePatterns(skills, screenMemory) {
  const rows = [...(screenMemory?.patterns || []), ...(skills?.recent || [])];
  const seen = new Set();
  return rows.filter((item) => {
    const key = `${item.id || ""}:${item.app || ""}:${item.label || item.screen_label || ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 8);
}

function importantApps(apps) {
  const priority = ["code", "chrome", "powershell", "windowsterminal", "cmd", "python", "node", "docker", "figma"];
  const unique = [];
  const seen = new Set();
  for (const app of apps) {
    const name = cleanAppName(app.name).toLowerCase();
    if (!name || seen.has(name)) continue;
    seen.add(name);
    unique.push(app);
  }
  return unique
    .sort((left, right) => scoreApp(right, priority) - scoreApp(left, priority))
    .slice(0, 6);
}

function scoreApp(app, priority) {
  const name = cleanAppName(app.name).toLowerCase().replace(/\s+/g, "");
  const index = priority.findIndex((item) => name.includes(item));
  return index === -1 ? 0 : 100 - index;
}

function cleanAppName(name) {
  return String(name || "Unknown app").replace(/\.exe$/i, "").replace(/\s+-\s+Insiders$/i, " Insiders");
}

function parseActiveWindow(value) {
  const text = String(value || "");
  const title = text.replace(/^Active window:\s*/i, "").split(" at ")[0] || "No active window captured";
  const pid = text.match(/\bpid[:=]\s*(\d+)/i)?.[1] || "";
  return { title, pid };
}

function appMatchesWindow(app, activeWindow) {
  const appName = cleanAppName(app.name).toLowerCase();
  const title = String(activeWindow.title || "").toLowerCase();
  return appName && title.includes(appName.replace("code insiders", "code"));
}

function confidencePercent(value) {
  if (typeof value !== "number") return { label: "Training", tone: "border-friday-line bg-[#202733] text-[#cbd7e6]" };
  const percent = Math.round(Math.max(0, Math.min(1, value)) * 100);
  const tone = percent >= 85 ? "border-[#45678c] bg-[#172334] text-friday-accent" : percent >= 65 ? "border-[#6a4215] bg-[#2a2115] text-[#ffb56d]" : "border-[#59323c] bg-[#28171d] text-[#ff9fa7]";
  return { label: `${percent}% Match`, tone };
}

function timeAgo(value) {
  const then = new Date(value).getTime();
  if (!Number.isFinite(then)) return "unknown";
  const seconds = Math.max(1, Math.floor((Date.now() - then) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return new Date(value).toLocaleDateString([], { month: "short", day: "numeric" });
}

function formatTime(value) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "--:--";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Box,
  Calendar,
  Code2,
  ExternalLink,
  FileText,
  GitBranch,
  Home,
  Layers,
  Lightbulb,
  Loader2,
  Mail,
  MessageSquare,
  Monitor,
  Music,
  Network,
  PackageCheck,
  Send,
  Server,
  Table2,
  Video
} from "lucide-react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";
import { wsUrl } from "@/services/fridayApi";

export function IntegrationsView() {
  const { api, data, token, interfaceFor } = useDashboard();
  const copy = interfaceFor?.("integrations") || {};
  const [dashboard, setDashboard] = useState(data.integrations || null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [status, setStatus] = useState("");
  const liveRef = useRef(false);

  const loadIntegrationsOnce = useCallback(async ({ silent = true } = {}) => {
    if (!silent) setLoading(true);
    try {
      const payload = await api("/integrations/dashboard");
      setDashboard(payload);
      liveRef.current = true;
    } catch (err) {
      setStatus(err.message || copy?.empty?.connectors || "Integrations dashboard could not be loaded.");
    } finally {
      if (!silent) setLoading(false);
    }
  }, [api, copy?.empty?.connectors]);

  useEffect(() => {
    if (data.integrations) {
      setDashboard(data.integrations);
      setLoading(false);
    }
  }, [data.integrations]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    let socket = null;
    let reconnectTimer = null;

    const connect = () => {
      socket = new WebSocket(wsUrl("/ws/integrations", token));
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          liveRef.current = true;
          setDashboard(payload);
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

  async function connectGoogle() {
    if (busy) return;
    const connected = Boolean(dashboard?.google?.connected);
    const googleStatus = dashboard?.google?.status || {};
    const deps = googleStatus.dependencies || {};
    setBusy("google");
    setStatus("");
    try {
      let shouldRefresh = false;
      if (connected) {
        const payload = await api("/integrations/google/disconnect", { method: "POST", body: JSON.stringify({}) });
        setDashboard((current) => ({ ...(current || {}), google: { ...(current?.google || {}), status: payload, connected: Boolean(payload.authorized), configured: Boolean(payload.configured) } }));
        setStatus("Google Workspace disconnected.");
        shouldRefresh = true;
      } else if (!dashboard?.google?.configured) {
        const clientIdEnv = googleStatus.client_id_env || "GOOGLE_CLIENT_ID";
        const secretEnv = googleStatus.client_secret_env || "GOOGLE_CLIENT_SECRET";
        setStatus(`Add ${clientIdEnv} and ${secretEnv} to .env, then restart the backend.`);
      } else if (deps.installed === false) {
        setStatus(`Install Google OAuth dependencies: ${(deps.missing || []).join(", ") || "google-auth, google-auth-oauthlib, google-api-python-client"}.`);
      } else {
        const payload = await api("/integrations/google/oauth/start", { method: "POST", body: JSON.stringify({}) });
        if (payload?.auth_url) window.open(payload.auth_url, "_blank", "noopener,noreferrer");
        setStatus("Google OAuth opened in a new tab.");
        shouldRefresh = true;
      }
      if (shouldRefresh && !liveRef.current) await loadIntegrationsOnce({ silent: true });
    } catch (err) {
      setStatus(err.message || "Google Workspace action failed.");
    } finally {
      setBusy("");
    }
  }

  async function launchApp(target) {
    if (!target || busy) return;
    setBusy(`open-${target}`);
    setStatus("");
    try {
      await api("/integrations/open", { method: "POST", body: JSON.stringify({ target }) });
      setStatus(`Opening ${target}.`);
      if (!liveRef.current) await loadIntegrationsOnce({ silent: true });
    } catch (err) {
      setStatus(err.message || `Could not open ${target}.`);
    } finally {
      setBusy("");
    }
  }

  const google = dashboard?.google || { modules: [] };
  const appLaunch = dashboard?.app_launch || { items: [], total: 0 };
  const homeAssistant = dashboard?.home_assistant || { cards: [] };
  const operations = dashboard?.operations_log || [];
  const browser = dashboard?.browser || {};

  return (
    <section className="grid w-full max-w-[1180px] min-w-0 content-start gap-4 text-[#eaf2fb]" aria-label="Integrations">
      <header className="grid min-w-0 gap-1">
        <h2 className="m-0 text-[26px] font-extrabold leading-tight text-white">{copy?.title || "Integrations"}</h2>
        <p className="m-0 text-[15px] text-[#d8e2ee]">{copy?.subtitle || "Connect and manage external data streams and system controllers."}</p>
      </header>

      <div className="grid min-w-0 gap-3 2xl:grid-cols-[minmax(0,1fr)_320px]">
        <GoogleWorkspaceCard google={google} loading={loading && !dashboard} busy={busy === "google"} onConnect={connectGoogle} />
        <BrowserBridgeCard browser={browser} />
      </div>

      <div className="grid min-w-0 gap-3 xl:grid-cols-[minmax(0,508px)_minmax(0,1fr)]">
        <AppLaunchGrid apps={appLaunch.items || []} total={appLaunch.total || 0} busy={busy} copy={copy} onLaunch={launchApp} />
        <HomeAssistantPanel homeAssistant={homeAssistant} />
      </div>

      <OperationsLog rows={operations} copy={copy} />

      {status ? (
        <div className="fixed bottom-5 right-5 z-20 max-w-[380px] rounded-[4px] border border-[#45678c] bg-[#9fcaff] px-4 py-3 text-[13px] font-semibold text-[#07111d] shadow-[0_16px_40px_rgba(0,0,0,.32)]">
          {status}
        </div>
      ) : null}
    </section>
  );
}

function GoogleWorkspaceCard({ google, loading, busy, onConnect }) {
  const connected = Boolean(google.connected);
  const configured = Boolean(google.configured);
  const depsInstalled = google.status?.dependencies?.installed !== false;
  const modules = google.modules || [];
  const visibleModules = modules.length ? modules : loading ? skeletonGoogleModules() : [];
  const actionLabel = busy ? "WORKING" : connected ? "CONNECTED" : !configured ? "CONFIGURE" : !depsInstalled ? "INSTALL DEPS" : "CONNECT";
  return (
    <Panel className="min-h-[360px] p-5">
      <header className="grid min-w-0 grid-cols-[44px_minmax(0,1fr)_auto] gap-4">
        <span className="grid h-11 w-11 place-items-center rounded-[3px] border border-[#6f3434] bg-[#3a2528] text-[#ff635f]">
          <Mail size={24} />
        </span>
        <div className="min-w-0">
          <h3 className="m-0 text-[19px] font-extrabold text-white">Google Workspace</h3>
          <p className="m-0 text-[12px] font-semibold text-[#aeb8c6]">{connected ? "Authenticated via OAuth 2.0" : configured ? "OAuth configured, awaiting authorization" : "Missing Google OAuth environment keys"}</p>
        </div>
        <button
          className={`h-8 min-w-[106px] rounded-[3px] border px-3 font-mono text-[11px] font-black uppercase tracking-[.08em] ${connected ? "border-[#2ea65a] bg-[#1b3b2a] text-[#54df7b]" : "border-[#4f6680] bg-[#263347] text-friday-accent"}`}
          type="button"
          onClick={onConnect}
          disabled={busy || loading}
        >
          {actionLabel}
        </button>
      </header>

      <div className="mt-10 grid min-w-0 gap-3 md:grid-cols-2 xl:grid-cols-4">
        {visibleModules.length ? visibleModules.map((module) => (
          <GoogleModule module={module} key={module.id} />
        )) : <div className="rounded-[4px] border border-dashed border-friday-line bg-[#111820] p-4 text-[13px] text-friday-muted md:col-span-2 xl:col-span-4">Google module status has not been returned by the backend yet.</div>}
      </div>
    </Panel>
  );
}

function GoogleModule({ module }) {
  const Icon = googleIcon(module.id);
  const active = Boolean(module.active);
  return (
    <article className="grid min-h-[144px] min-w-0 content-start gap-3 rounded-[4px] border border-[#3b4654] bg-[#151a21] p-4">
      <div className="flex min-w-0 items-center gap-3">
        <Icon className="h-5 w-5 shrink-0 text-[#dce7f5]" />
        <Switch active={active} />
      </div>
      <div className="min-w-0">
        <strong className="block truncate text-[14px] font-extrabold text-white">{module.label}</strong>
        <span className="mt-1 block truncate text-[12px] text-[#c9d2df]">{module.detail}</span>
      </div>
      <span className={`mt-auto inline-flex items-center gap-2 font-mono text-[10px] font-bold uppercase ${active ? "text-[#54df7b]" : "text-[#747f8e]"}`}>
        <i className={`h-2 w-2 rounded-full ${active ? "bg-[#28cf73]" : "bg-[#4d5764]"}`} />
        {module.status}
      </span>
    </article>
  );
}

function BrowserBridgeCard({ browser }) {
  const contexts = browser.contexts || [];
  const consoleRows = browser.console || [];
  const actions = browser.actions || [];
  const latest = contexts[0] || {};
  const queued = actions.filter((item) => item.status === "queued").length;
  const active = Boolean(contexts.length);
  return (
    <Panel className="min-h-[360px] p-5">
      <header className="grid min-w-0 grid-cols-[44px_minmax(0,1fr)] gap-4">
        <span className="grid h-11 w-11 place-items-center rounded-[3px] border border-[#45678c] bg-[#172334] text-friday-accent">
          <Network size={23} />
        </span>
        <div className="min-w-0">
          <h3 className="m-0 text-[18px] font-extrabold text-white">Browser Extension</h3>
          <p className="m-0 truncate text-[12px] font-semibold text-[#aeb8c6]">{browser.summary || "Waiting for browser context"}</p>
        </div>
      </header>

      <div className="mt-7 grid min-w-0 gap-3">
        <div className="grid grid-cols-3 gap-2">
          <MiniStat label="Contexts" value={contexts.length} active={active} />
          <MiniStat label="Console" value={consoleRows.length} active={!consoleRows.length} />
          <MiniStat label="Queued" value={queued} active={!queued} />
        </div>

        <article className="min-w-0 rounded-[4px] border border-[#3b4654] bg-[#151a21] p-4">
          <div className="mb-3 flex items-center gap-2">
            <Monitor className="h-4 w-4 shrink-0 text-friday-accent" />
            <strong className="min-w-0 truncate text-[13px] text-white">{latest.title || "No active browser page"}</strong>
          </div>
          <p className="m-0 line-clamp-3 text-[12px] leading-relaxed text-[#c9d2df]">
            {latest.url || "Install or open the local extension to stream page context, console events, and safe web actions."}
          </p>
          <div className="mt-4 flex min-w-0 items-center gap-2 font-mono text-[10px] uppercase text-[#8fa3b8]">
            <ExternalLink size={13} />
            <span className="truncate">{browser.extension_path || "apps/browser-extension"}</span>
          </div>
        </article>

        <div className="grid min-w-0 gap-2">
          {(actions.length ? actions : [{ id: "idle", action: "no queued action", status: "idle", reason: "Bridge is standing by." }]).slice(0, 2).map((action) => (
            <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-[3px] border border-[#303743] bg-[#111820] px-3 py-2" key={action.id}>
              <span className="truncate text-[12px] text-white">{action.action || "browser action"}</span>
              <span className={`font-mono text-[10px] font-bold uppercase ${statusTone(action.status)}`}>{action.status || "idle"}</span>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );
}

function AppLaunchGrid({ apps, total, busy, copy, onLaunch }) {
  return (
    <Panel className="min-h-[310px] p-5">
      <header className="mb-5 flex items-center gap-3">
        <h3 className="m-0 text-[18px] font-extrabold text-white">App Launch Grid</h3>
        <span className="ml-auto font-mono text-[11px] uppercase text-friday-accent">{total || apps.length} total</span>
      </header>
      <div className="grid min-w-0 grid-cols-3 gap-x-3 gap-y-4 sm:grid-cols-4 xl:grid-cols-6">
        {apps.length ? apps.slice(0, 12).map((app) => {
          const Icon = appIcon(app.id);
          const opening = busy === `open-${app.id}`;
          return (
            <button
              className="group grid min-h-[74px] min-w-0 place-items-center gap-2 rounded-[7px] border border-[#3b4654] bg-[#1b2028] p-1 text-center transition hover:border-friday-accent disabled:opacity-50"
              type="button"
              key={app.id}
              onClick={() => onLaunch(app.id)}
              disabled={!app.available || opening}
              title={app.available ? `Open ${app.label}` : `${app.label} is not configured`}
            >
              <span className="grid h-[52px] w-full max-w-[52px] place-items-center rounded-[7px] border border-[#3d4857] bg-[#262d37] text-[#dce7f5] group-hover:text-friday-accent">
                {opening ? <Loader2 className="animate-spin" size={20} /> : <Icon size={21} />}
              </span>
              <span className="max-w-full truncate text-[11px] font-bold text-white">{app.label}</span>
            </button>
          );
        }) : <div className="col-span-full grid min-h-[150px] place-items-center rounded-[4px] border border-dashed border-friday-line bg-[#111820] px-4 text-center text-[13px] text-friday-muted">{copy?.empty?.connectors || "No app launch targets came back from the backend yet."}</div>}
      </div>
    </Panel>
  );
}

function HomeAssistantPanel({ homeAssistant }) {
  const cards = homeAssistant.cards?.length ? homeAssistant.cards : [];
  return (
    <Panel className="min-h-[310px] p-5">
      <header className="mb-6 flex items-center gap-4">
        <span className="grid h-11 w-11 place-items-center rounded-[3px] border border-[#6d4d2c] bg-[#3b2a18] text-[#ffb277]">
          <Home size={22} />
        </span>
        <div className="min-w-0">
          <h3 className="m-0 text-[18px] font-extrabold text-white">Home Assistant</h3>
          <p className="m-0 truncate text-[12px] text-[#aeb8c6]">{homeAssistant.reachable ? "Local controller online" : homeAssistant.configured ? "Configured but not reachable" : "Local controller not configured"}</p>
        </div>
      </header>
      <div className="grid min-w-0 gap-3 md:grid-cols-2">
        {cards.map((card) => (
          <HomeCard card={card} key={card.id} />
        ))}
      </div>
    </Panel>
  );
}

function HomeCard({ card }) {
  const Icon = homeIcon(card.domain);
  return (
    <article className="grid min-h-[150px] content-start gap-4 rounded-[4px] border border-[#3b4654] bg-[#151a21] p-4">
      <div className="flex items-start gap-3">
        <Icon className="mt-1 h-6 w-6 shrink-0 text-[#ffb277]" />
        <span className="ml-auto font-mono text-[10px] font-bold uppercase text-[#54df7b]">{card.state_label}</span>
      </div>
      <div className="min-w-0">
        <strong className="block truncate text-[14px] font-extrabold text-white">{card.title}</strong>
        <span className="block truncate text-[12px] text-[#c9d2df]">{card.subtitle}</span>
      </div>
      {Number.isFinite(Number(card.level)) ? (
        <div className="h-1.5 overflow-hidden rounded-full bg-[#28313b]">
          <span className="block h-full bg-[#ffb277]" style={{ width: `${Math.max(0, Math.min(100, Number(card.level)))}%` }} />
        </div>
      ) : card.value ? (
        <span className="font-mono text-[12px] text-friday-accent">{card.value}</span>
      ) : null}
    </article>
  );
}

function OperationsLog({ rows, copy }) {
  return (
    <Panel>
      <header className="border-b border-friday-line px-5 py-4">
        <h3 className="m-0 text-[18px] font-extrabold text-white">Operations Log</h3>
      </header>
      <div className="friday-scroll overflow-x-auto">
        <div className="min-w-[820px]">
          <div className="grid min-h-11 grid-cols-[160px_210px_minmax(0,1fr)_110px_220px] items-center border-b border-friday-line px-4 font-mono text-[11px] font-bold uppercase tracking-[.06em] text-[#c8d2df]">
            <span>Timestamp</span>
            <span>System</span>
            <span>Event</span>
            <span>Status</span>
            <span>Payload</span>
          </div>
          {rows.length ? rows.slice(0, 3).map((row) => (
            <div className="grid min-h-[58px] grid-cols-[160px_210px_minmax(0,1fr)_110px_220px] items-center gap-3 border-b border-friday-line px-4 last:border-b-0" key={row.id}>
              <span className="font-mono text-[12px] text-white">{formatTime(row.timestamp)}</span>
              <strong className="truncate text-[13px] text-white">{row.system}</strong>
              <span className="truncate text-[13px] text-[#d8e2ee]">{row.event}</span>
              <span className={`font-mono text-[11px] font-bold uppercase ${statusTone(row.status)}`}>{row.status}</span>
              <code className="truncate rounded-[2px] bg-[#111820] px-2 py-1 font-mono text-[10px] text-[#b8c4d2]">{payloadText(row.payload)}</code>
            </div>
          )) : <div className="grid min-h-[90px] place-items-center px-4 text-center text-[13px] text-friday-muted">{copy?.empty?.connectors || "Friday has no integration operation in this read yet."}</div>}
        </div>
      </div>
    </Panel>
  );
}

function Panel({ className = "", children }) {
  return <section className={`min-w-0 overflow-hidden rounded-[8px] border border-[#3b4654] bg-[#171c23] ${className}`}>{children}</section>;
}

function MiniStat({ label, value, active }) {
  return (
    <div className="min-w-0 rounded-[3px] border border-[#303743] bg-[#111820] px-2 py-2">
      <strong className={`block truncate font-mono text-[14px] ${active ? "text-friday-accent" : "text-[#ffaaa6]"}`}>{value}</strong>
      <span className="block truncate text-[10px] uppercase text-[#9aa8ba]">{label}</span>
    </div>
  );
}

function Switch({ active }) {
  return (
    <span className={`ml-auto flex h-5 w-9 items-center rounded-full px-0.5 ${active ? "justify-end bg-friday-accent" : "justify-start bg-[#303743]"}`}>
      <span className="h-4 w-4 rounded-full bg-white shadow" />
    </span>
  );
}

function googleIcon(id) {
  if (id === "gmail") return Mail;
  if (id === "calendar") return Calendar;
  if (id === "docs") return FileText;
  if (id === "sheets") return Table2;
  return PackageCheck;
}

function appIcon(id) {
  if (id === "vscode") return Code2;
  if (id === "discord" || id === "whatsapp" || id === "slack") return MessageSquare;
  if (id === "spotify") return Music;
  if (id === "github") return GitBranch;
  if (id === "zoom") return Video;
  if (id === "linear" || id === "notion") return Layers;
  if (id === "postman") return Send;
  if (id === "calendar") return Calendar;
  if (id === "gmail") return Mail;
  if (id === "docs") return FileText;
  if (id === "figma") return Box;
  return Monitor;
}

function homeIcon(domain) {
  if (domain === "light") return Lightbulb;
  if (domain === "sensor" || domain === "switch") return Server;
  return Home;
}

function statusTone(status) {
  const value = String(status || "").toLowerCase();
  if (["success", "active", "connected", "read", "info"].includes(value)) return "text-[#54df7b]";
  if (["trigger", "setup", "queued"].includes(value)) return "text-friday-accent";
  if (["error", "offline", "failed"].includes(value)) return "text-[#ffaaa6]";
  return "text-[#ffb277]";
}

function formatTime(value) {
  const date = value ? new Date(value) : null;
  if (!date || !Number.isFinite(date.getTime())) return "--:--";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

function payloadText(payload) {
  try {
    return JSON.stringify(payload || {});
  } catch {
    return "{}";
  }
}

function skeletonGoogleModules() {
  return [
    { id: "gmail", label: "Gmail", detail: "Loading", active: false, status: "CHECKING" },
    { id: "calendar", label: "Calendar", detail: "Loading", active: false, status: "CHECKING" },
    { id: "docs", label: "Docs", detail: "Loading", active: false, status: "CHECKING" },
    { id: "sheets", label: "Sheets", detail: "Loading", active: false, status: "CHECKING" }
  ];
}

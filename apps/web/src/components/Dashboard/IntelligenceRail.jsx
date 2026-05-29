import { Bell, Brain, Crosshair, FileText, Power, ShieldCheck, X } from "lucide-react";
import Link from "next/link";
import { interfaceFor } from "@/lib/dynamicInterface";

export function IntelligenceRail({ activeView, data, activeMission, approvalCount, liveTimestamp, onClose }) {
  const copy = interfaceFor(data, activeView);
  const rail = copy.rail || {};
  const labels = copy.labels || {};
  const primary = copy.primaryAction || copy.actions?.[0] || {};
  if (activeView === "chat") {
    const activeWindow = data.pcAwareness?.active_window || "No active window captured";
    const workerText = data.status?.running ? `${data.status.workers || 0} workers online` : "workers stopped";
    const thoughts = data.thoughts?.recent || [];
    const continuity = data.conversationContinuity?.summary || data.contextFusion?.summary || "No unfinished thread summary loaded.";
    const unsupported = data.evaluation?.counts?.unsupported_claim || 0;
    return (
      <aside className="grid h-full animate-friday-slide-left grid-rows-[auto_minmax(0,1fr)_auto] gap-[18px] overflow-hidden bg-[#151b22] px-5 py-[18px]">
        <RailHeader title={rail.title || "SESSION TELEMETRY"} subtitle={rail.subtitle || ""} onClose={onClose} />
        <div className="grid min-h-0 content-start gap-7 overflow-hidden">
          <TelemetryBlock title="CURRENT CONTEXT">
            <ContextRow label="Active Window" value={activeWindow} />
            <ContextRow label="Agent Workers" value={workerText} />
            <ContextRow label="Approvals" value={`${approvalCount || 0} waiting`} />
          </TelemetryBlock>

          <TelemetryBlock title="ACTIVE MEMORY" action="manage" actionHref="/memory">
            <MemoryItem icon={<FileText size={14} />} title="Conversation Continuity" detail={continuity} />
            {thoughts.slice(0, 2).map((thought) => (
              <MemoryItem key={thought.id} title={thought.packet_type || "thought"} detail={thought.summary} />
            ))}
          </TelemetryBlock>

          <TelemetryBlock title="HONESTY / SAFETY">
            <ContextRow label="Evidence Gate" value={unsupported ? `${unsupported} alerts` : "quiet"} />
            <ContextRow label="Risky Actions" value="approval-gated" />
            <ContextRow label="Private Data" value="permission required" />
          </TelemetryBlock>
        </div>
        <RailFooter lines={[`> SYNC_RATE: ${liveTimestamp ? "live" : "polling"}`, "> CHAT: /chat orchestrator"]} />
      </aside>
    );
  }

  if (activeView === "safety") {
    const safetyPaths = (copy.actions || []).map((item) => item.label).filter(Boolean).slice(0, 3);
    return (
      <aside className="grid h-full animate-friday-slide-left grid-rows-[auto_minmax(0,1fr)_auto] gap-[18px] overflow-hidden bg-[#151b22] px-4 py-[18px]">
        <RailHeader title={rail.title || "SYSTEM INTELLIGENCE"} subtitle={rail.subtitle || "Friday's Thought Summary"} onClose={onClose} />
        <p className="m-0 text-[14px] leading-relaxed text-[#b7c1cf]">{copy.subtitle || "Friday is reading current safety state."}</p>
        <div className="grid min-h-0 content-start gap-7 overflow-hidden">
          <div className="grid gap-5">
            <RailMenuItem icon={<Brain size={17} />} label="Thoughts" href="/agents" active />
            <RailMenuItem icon={<Bell size={17} />} label="Notifications" href="/notifications" />
            <RailMenuItem icon={<ShieldCheck size={17} />} label="Decisions" href="/approvals" badge={approvalCount || null} />
            <RailMenuItem icon={<Crosshair size={17} />} label="Missions" href="/mission-control" />
          </div>
          <TelemetryBlock title="LIVE REASONING">
            <article className="rounded-[4px] border border-friday-line bg-[#111820] p-4">
              <p className="m-0 font-mono text-[13px] italic leading-relaxed text-white">
                "{rail.focus || copy.summary || "Friday is watching risky actions and will hold anything external for approval."}"
              </p>
            </article>
          </TelemetryBlock>
          <TelemetryBlock title="SAFETY PATHS">
            <div className="flex flex-wrap gap-2">
              {safetyPaths.length ? safetyPaths.map((item) => (
                <span className="rounded-[3px] border border-friday-line bg-[#303743] px-3 py-2 font-mono text-[11px] font-bold text-white" key={item}>{item}</span>
              )) : <span className="rounded-[3px] border border-dashed border-friday-line bg-[#111820] px-3 py-2 text-[12px] text-friday-muted">{copy.empty?.highRisk || "No safety path labels came back in this snapshot."}</span>}
            </div>
          </TelemetryBlock>
        </div>
        <article className="rounded-[4px] border border-friday-line bg-[#303743] p-4">
          <h3 className="mb-2 font-semibold text-white">Audit Integrity</h3>
          <p className="m-0 text-[12px] leading-relaxed text-[#d8e2ee]">{copy.empty?.errors || "Friday will attach the next failed audit event here with evidence."}</p>
        </article>
      </aside>
    );
  }

  if (activeView === "android") {
    const mesh = data.android || {};
    const notifications = mesh.phone_notifications || (data.notifications?.items || []).filter((item) => /phone|android|handoff/i.test(`${item.category || ""} ${item.source || ""}`));
    const handoffs = mesh.handoffs || mesh.phone_mesh?.recent || [];
    const analysis = androidRailAnalysis(mesh);
    return (
      <aside className="grid h-full animate-friday-slide-left grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden bg-[#151b22] px-4 py-[18px]">
        <header className="flex items-start gap-3">
          <div className="min-w-0">
            <strong className="block font-mono text-[11px] font-bold uppercase tracking-[.2em] text-[#ffbf7b]">{rail.title || "System Intelligence"}</strong>
            <span className="mt-1.5 block text-[13px] text-white">{rail.subtitle || "Friday's Thought Summary"}</span>
          </div>
          <button className="ml-auto grid h-7 w-7 place-items-center rounded-[3px] text-[#c9d3df] transition-colors hover:bg-[#202832] hover:text-white" type="button" title="Close System Intelligence" onClick={onClose}>
            <X size={17} />
          </button>
        </header>

        <div className="friday-scroll grid min-h-0 content-start gap-7 overflow-y-auto pt-8">
          <section>
            <div className="mb-3 flex items-center gap-2 font-mono text-[11px] font-bold text-friday-accent">
              <Brain size={14} />
              <span>Active Analysis</span>
            </div>
            <article className="rounded-[6px] border border-friday-line bg-[#111820] p-4">
              <p className="m-0 text-[13px] leading-relaxed text-white">"{analysis}"</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <span className="rounded-[3px] border border-[#45678c] bg-[#172334] px-2 py-1 font-mono text-[10px] uppercase text-friday-accent">Reasoning</span>
                <span className="rounded-[3px] border border-[#6a4215] bg-[#2a2115] px-2 py-1 font-mono text-[10px] uppercase text-[#ffb56d]">Android</span>
              </div>
            </article>
          </section>

          <section>
            <h3 className="mb-3 font-mono text-[12px] font-bold uppercase tracking-[.08em] text-[#9aa8ba]">Phone Notifications</h3>
            <div className="grid gap-2">
              {notifications.length ? notifications.slice(0, 3).map((item) => <AndroidNotificationCard item={item} key={item.id || `${item.title}-${item.timestamp}`} />) : (
                <article className="rounded-[4px] border border-friday-line bg-[#111820] p-4">
                  <strong className="block text-[13px] text-white">No phone notifications</strong>
                  <span className="mt-1 block text-[11px] text-friday-muted">Android companion notification sync is waiting for device input.</span>
                </article>
              )}
            </div>
          </section>

          <section>
            <h3 className="mb-4 font-mono text-[12px] font-bold uppercase tracking-[.08em] text-[#9aa8ba]">Handoff Timeline</h3>
            <div className="grid gap-0 border-l border-[#3d4857] pl-5">
              {handoffs.length ? handoffs.slice(0, 5).map((item, index) => <AndroidTimelineItem item={item} active={index === 0} key={item.id || `${item.title}-${index}`} />) : (
                <AndroidTimelineItem item={{ title: "No handoffs queued", created_at: mesh.timestamp, summary: "Waiting for Android companion activity." }} active />
              )}
            </div>
          </section>
        </div>

        <div className="grid grid-cols-2 gap-2 border-t border-friday-line pt-4">
          <button className="min-h-10 rounded-[2px] border border-[#303743] bg-[#303743] text-[13px] text-white transition-colors hover:border-friday-line" type="button" onClick={onClose}>{labels.dismiss || "Dismiss"}</button>
          <a className="grid min-h-10 place-items-center rounded-[2px] border border-[#ffb277] bg-[#ffb277] text-[13px] font-bold text-[#130a03] transition-colors hover:bg-[#ffc491]" href={primary.href || "/android"}>{labels.execute || primary.label || "Execute"}</a>
        </div>
      </aside>
    );
  }

  if (activeView === "vision") {
    const analysis = visionAnalysisText(data);
    const missionTitle = activeMission?.title || activeMission?.goal || rail.focus || copy.subtitle || "No active vision mission";
    return (
      <aside className="grid h-full animate-friday-slide-left grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden bg-[#151b22] px-4 py-[18px]">
        <header className="flex items-start gap-3">
          <div className="min-w-0">
            <strong className="block font-mono text-[11px] font-bold uppercase tracking-[.2em] text-[#ffbf7b]">{rail.title || "System Intelligence"}</strong>
            <span className="mt-1.5 block text-[13px] text-white">{rail.subtitle || "Friday's Thought Summary"}</span>
          </div>
            <button className="ml-auto grid h-7 w-7 place-items-center rounded-[3px] text-[#c9d3df] transition-colors hover:bg-[#202832] hover:text-white" type="button" title="Close System Intelligence" onClick={onClose}>
              <X size={17} />
            </button>
        </header>

        <div className="grid min-h-0 content-start gap-8 overflow-hidden pt-7">
          <section>
            <div className="mb-3 flex items-center gap-2 font-mono text-[11px] font-bold text-friday-accent">
              <Brain size={14} />
              <span>Active Analysis</span>
            </div>
            <article className="rounded-[6px] border border-friday-line bg-[#111820] p-4">
              <p className="m-0 text-[13px] leading-relaxed text-white">"{analysis}"</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <span className="rounded-[3px] border border-[#45678c] bg-[#172334] px-2 py-1 font-mono text-[10px] uppercase text-friday-accent">Reasoning</span>
                <span className="rounded-[3px] border border-[#6a4215] bg-[#2a2115] px-2 py-1 font-mono text-[10px] uppercase text-[#ffb56d]">Vision</span>
              </div>
            </article>
          </section>

          <div className="grid gap-5">
            <VisionRailRow icon={<Power size={18} />} title={missionTitle} detail={data.status?.running ? "Screen monitoring optimized" : "Screen monitor ready"} active />
            <VisionRailRow icon={<Bell size={18} />} title="Pattern Verification" detail={`${data.thoughts?.open_count || 0} open reasoning packet(s)`} />
            <VisionRailRow icon={<ShieldCheck size={18} />} title="Screen Safety" detail="Screenshots remain token-protected and local." />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 border-t border-friday-line pt-4">
          <button className="min-h-10 rounded-[2px] border border-[#303743] bg-[#303743] text-[13px] text-white transition-colors hover:border-friday-line" type="button" onClick={onClose}>{labels.dismiss || "Dismiss"}</button>
          <a className="grid min-h-10 place-items-center rounded-[2px] border border-[#ffb277] bg-[#ffb277] text-[13px] font-bold text-[#130a03] transition-colors hover:bg-[#ffc491]" href={primary.href || "/chat"}>{labels.execute || primary.label || "Execute"}</a>
        </div>
      </aside>
    );
  }

  if (activeView === "memory") {
    const thoughts = data.thoughts?.recent || [];
    const currentFocus = data.contextFusion?.summary || data.conversationContinuity?.summary || "Memory systems are watching for stale facts and unresolved preferences.";
    const load = memoryLoadPercent(data, thoughts, approvalCount);
    return (
      <aside className="grid h-full animate-friday-slide-left grid-rows-[auto_minmax(0,1fr)_auto] gap-[18px] overflow-hidden bg-[#151b22] px-4 py-[18px]">
        <RailHeader title={rail.title || "SYSTEM INTELLIGENCE"} subtitle={rail.subtitle || "Friday's Thought Summary"} onClose={onClose} />
        <div className="grid min-h-0 content-start gap-6 overflow-hidden pt-1">
          <div className="grid grid-cols-2 gap-3">
            <RailMenuItem icon={<Brain size={17} />} label="Thoughts" href="/agents" active />
            <RailMenuItem icon={<Bell size={17} />} label="Alerts" href="/notifications" />
            <RailMenuItem icon={<ShieldCheck size={17} />} label="Decisions" href="/approvals" badge={approvalCount || null} />
            <RailMenuItem icon={<Crosshair size={17} />} label="Missions" href="/mission-control" />
          </div>

          <TelemetryBlock title="Recent Reasoning">
            {thoughts.length ? (
              thoughts.slice(0, 2).map((thought, index) => (
                <RailEvent label={`> ${String(thought.packet_type || "memory_signal").toUpperCase()}`} badge={`#${thought.id || index + 1}`} key={thought.id || index}>
                  {thought.summary || thought.content?.summary || "Open thought packet awaiting review."}
                </RailEvent>
              ))
            ) : (
              <RailEvent label="> MEMORY_IDLE" badge="live">No recent reasoning packets are open.</RailEvent>
            )}
          </TelemetryBlock>

          <RailFocus focus={currentFocus} live={Boolean(liveTimestamp)} />
        </div>
        <MemoryLoadCard value={load} />
      </aside>
    );
  }

  if (activeView === "integrations") {
    const integrations = data.integrations || {};
    const google = integrations.google || {};
    const home = integrations.home_assistant || {};
    const browser = integrations.browser || {};
    const operations = integrations.operations_log || [];
    const contexts = browser.contexts || [];
    const consoleRows = browser.console || [];
    const actions = browser.actions || [];
    const queuedActions = actions.filter((item) => item.status === "queued").length;
    const thought = integrations.thought_summary || "Integration streams are waiting for the next backend snapshot.";

    return (
      <aside className="grid h-full animate-friday-slide-left grid-rows-[auto_minmax(0,1fr)_auto] gap-[18px] overflow-hidden bg-[#151b22] px-4 py-[18px]">
        <RailHeader title={rail.title || "SYSTEM INTELLIGENCE"} subtitle={rail.subtitle || "Friday's Thought Summary"} onClose={onClose} />
        <div className="friday-scroll grid min-h-0 content-start gap-5 overflow-y-auto pr-1">
          <section>
            <div className="mb-3 flex items-center gap-2 font-mono text-[11px] font-bold text-friday-accent">
              <Brain size={14} />
              <span>Integration Analysis</span>
            </div>
            <article className="rounded-[6px] border border-friday-line bg-[#111820] p-4">
              <p className="m-0 text-[13px] leading-relaxed text-white">"{thought}"</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <span className="rounded-[3px] border border-[#45678c] bg-[#172334] px-2 py-1 font-mono text-[10px] uppercase text-friday-accent">Backend</span>
                <span className="rounded-[3px] border border-[#6a4215] bg-[#2a2115] px-2 py-1 font-mono text-[10px] uppercase text-[#ffb56d]">Integrations</span>
              </div>
            </article>
          </section>

          <TelemetryBlock title="Live Connectors">
            <ContextRow label="Google Workspace" value={google.connected ? "connected" : google.configured ? "ready" : "setup"} />
            <ContextRow label="Home Assistant" value={home.reachable ? "online" : home.configured ? "unreachable" : "setup"} />
            <ContextRow label="Browser Extension" value={contexts.length ? `${contexts.length} context(s)` : "waiting"} />
            <ContextRow label="Queued Web Actions" value={`${queuedActions}`} />
          </TelemetryBlock>

          <TelemetryBlock title="Recent Operations">
            {operations.length ? (
              operations.slice(0, 3).map((row, index) => (
                <RailEvent label={`> ${String(row.system || "integration").toUpperCase()}`} badge={String(row.status || "INFO").toUpperCase()} warning={String(row.status || "").toLowerCase() === "error"} key={row.id || index}>
                  {row.event || "Integration event recorded."}
                </RailEvent>
              ))
            ) : (
              <RailEvent label="> INTEGRATION_IDLE" badge="live">No integration operations have been recorded yet.</RailEvent>
            )}
          </TelemetryBlock>

          <TelemetryBlock title="Browser Bridge">
            <ContextRow label="Console Events" value={`${consoleRows.length}`} />
            <ContextRow label="Extension Path" value={browser.extension_path || "apps/browser-extension"} />
          </TelemetryBlock>
        </div>
        <div className="grid grid-cols-2 gap-2 border-t border-friday-line pt-4">
          <button className="min-h-10 rounded-[2px] border border-[#303743] bg-[#303743] text-[13px] text-white transition-colors hover:border-friday-line" type="button" onClick={onClose}>{labels.dismiss || "Dismiss"}</button>
          <a className="grid min-h-10 place-items-center rounded-[2px] border border-[#ffb277] bg-[#ffb277] text-[13px] font-bold text-[#130a03] transition-colors hover:bg-[#ffc491]" href={primary.href || "/integrations"}>{labels.execute || primary.label || "Execute"}</a>
        </div>
      </aside>
    );
  }

  const currentFocus = rail.focus || activeMission?.title || data.thoughts?.recent?.[0]?.summary || "Monitoring governance, approvals, and agent performance.";

  return (
    <aside className="grid h-full animate-friday-slide-left grid-rows-[auto_minmax(0,1fr)_auto] gap-[18px] overflow-hidden bg-[#151b22] px-4 py-[18px]">
      <RailHeader title={rail.title || "SYSTEM INTELLIGENCE"} subtitle={rail.subtitle || "Friday's Thought Summary"} onClose={onClose} />
      <div className="grid min-h-0 content-start gap-5 overflow-hidden pt-1">
        <RailMenuItem icon={<Brain size={17} />} label="Thoughts" href="/agents" active />
        <RailMenuItem icon={<Bell size={17} />} label="Notifications" href="/notifications" />
        <RailMenuItem icon={<ShieldCheck size={17} />} label="Decisions" href="/approvals" badge={approvalCount || null} />
        <RailMenuItem icon={<Crosshair size={17} />} label="Missions" href="/mission-control" />
      </div>
      <RailFocus focus={currentFocus} live={Boolean(liveTimestamp)} />
    </aside>
  );
}

function RailHeader({ title, subtitle, onClose }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <strong className="block font-mono text-xs tracking-[.12em] text-[#ffbf7b]">{title}</strong>
        {subtitle ? <span className="mt-1.5 block text-[13px] text-white">{subtitle}</span> : null}
      </div>
      {onClose ? (
        <button className="ml-auto grid h-7 w-7 shrink-0 place-items-center rounded-[3px] text-[#c9d3df] transition-colors hover:bg-[#202832] hover:text-white" type="button" title="Close System Intelligence" onClick={onClose}>
          <X size={17} />
        </button>
      ) : null}
    </div>
  );
}

function TelemetryBlock({ title, action, actionHref, children }) {
  return (
    <section>
      <div className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[.08em] text-[#cbd7e6]">
        <span>{title}</span>
        {action && actionHref ? <Link className="ml-auto border-0 bg-transparent text-[11px] text-friday-accent" href={actionHref}>{action}</Link> : null}
      </div>
      <div className="grid gap-0">{children}</div>
    </section>
  );
}

function ContextRow({ label, value }) {
  return (
    <div className="grid min-h-10 grid-cols-[minmax(0,1fr)_auto] items-center border border-friday-line border-b-0 bg-[#151b22] px-3 last:border-b">
      <span className="truncate text-[13px] text-[#eef6ff]">{label}</span>
      <span className="min-w-0 max-w-[132px] truncate text-right font-mono text-[12px] text-white">{value}</span>
    </div>
  );
}

function MemoryItem({ icon, title, detail }) {
  return (
    <div className="grid grid-cols-[18px_minmax(0,1fr)] gap-2 border-l border-friday-line pb-3 pl-2 last:pb-0">
      <span className="mt-0.5 text-friday-muted">{icon || "<>"}</span>
      <div>
        <strong className="block truncate text-[13px] text-white">{title}</strong>
        <span className="block truncate text-[11px] text-friday-muted">{detail}</span>
      </div>
    </div>
  );
}

function PermissionBadge({ allowed, label }) {
  return (
    <span className={`inline-flex min-h-7 items-center justify-center border px-2 font-mono text-[11px] ${allowed ? "border-[#2f6a57] bg-[#11251f] text-[#8df0c6]" : "border-[#4a3f45] bg-[#211a1e] text-[#7d8794]"}`}>
      {allowed ? "OK " : "NO "}
      {label}
    </span>
  );
}

function RailMenuItem({ icon, label, href = "/dashboard", active, badge }) {
  return (
    <Link
      className={`flex min-h-[48px] w-full items-center gap-3 rounded-lg px-4 text-left text-[14px] transition-[background-color,color,transform] duration-150 ease-out hover:translate-x-0.5 active:scale-[.99] motion-reduce:transition-none ${
        active ? "bg-[#e68100] text-[#160b00]" : "bg-transparent text-[#e5edf8] hover:bg-[#202832]"
      }`}
      href={href}
    >
      {icon}
      <span>{label}</span>
      {badge ? <span className="ml-auto rounded bg-[#303946] px-2 py-0.5 text-xs text-white">{badge}</span> : null}
    </Link>
  );
}

function RailEvent({ label, badge, warning, children }) {
  return (
    <article className={`border p-3 font-mono ${warning ? "border-red-400/35 bg-red-950/30" : "border-friday-line bg-[#111820]"}`}>
      <header className="mb-2 flex justify-between gap-2 text-[11px] text-[#eaf2ff]"><span>{label}</span><b className="text-[10px] tracking-widest text-[#ffbf7b]">{badge}</b></header>
      <p className="m-0 text-xs leading-relaxed text-[#e0e8f4]">{children}</p>
    </article>
  );
}

function RailFooter({ lines }) {
  return (
    <div className="grid gap-1 border-t border-friday-line pt-3.5 font-mono text-[11px] text-friday-muted">
      {lines.map((line, index) => <span key={`${index}-${line}`}>{line}</span>)}
    </div>
  );
}

function RailFocus({ focus, live }) {
  return (
    <div className="border-t border-friday-line pt-4">
      <article className="rounded-[4px] border border-friday-line bg-[#111820] p-3">
        <header className="mb-2 flex items-center justify-between gap-3 text-[11px] text-[#dfe8f4]">
          <span>Current Focus</span>
          <Crosshair size={13} className="text-[#ffbf7b]" />
        </header>
        <p className="max-h-[72px] overflow-hidden font-mono text-[12px] leading-relaxed text-white">
          &gt; {focus}
        </p>
        <span className="mt-2 block font-mono text-[10px] uppercase tracking-[.12em] text-friday-muted">{live ? "live telemetry" : "idle telemetry"}</span>
      </article>
    </div>
  );
}

function VisionRailRow({ icon, title, detail, active }) {
  return (
    <article className="grid min-h-[58px] grid-cols-[42px_minmax(0,1fr)] items-center gap-3">
      <span className={`grid h-10 w-10 place-items-center rounded-[2px] ${active ? "bg-[#6a4215] text-[#ffb56d]" : "bg-[#303743] text-[#cbd7e6]"}`}>
        {icon}
      </span>
      <div className="min-w-0">
        <strong className="block truncate text-[14px] text-white">{title}</strong>
        <span className="mt-1 block truncate text-[11px] text-friday-muted">{detail}</span>
      </div>
    </article>
  );
}

function AndroidNotificationCard({ item }) {
  return (
    <article className="rounded-[4px] border border-friday-line bg-[#1a2028] p-3">
      <header className="mb-2 flex items-center gap-2">
        <strong className="min-w-0 flex-1 truncate text-[12px] text-friday-accent">{item.source || item.category || "Android"}</strong>
        <span className="shrink-0 text-[11px] text-friday-muted">{railTimeAgo(item.updated_at || item.timestamp)}</span>
      </header>
      <strong className="block truncate text-[13px] text-white">{item.title || "Phone notification"}</strong>
      <p className="mt-1 line-clamp-2 text-[12px] leading-snug text-[#d8e2ee]">{item.message || item.summary || "Notification received from Android."}</p>
    </article>
  );
}

function AndroidTimelineItem({ item, active }) {
  return (
    <article className="relative pb-5 last:pb-0">
      <span className={`absolute -left-[25px] top-1 h-3 w-3 rounded-full border ${active ? "border-friday-accent bg-friday-accent" : "border-[#5f6b79] bg-[#151b22]"}`} />
      <div className="grid gap-1">
        <span className={`font-mono text-[13px] ${active ? "text-friday-accent" : "text-[#8d99a8]"}`}>{railClock(item.created_at || item.timestamp || item.updated_at)}</span>
        <strong className="block truncate text-[13px] font-medium text-white">{item.title || "Android handoff"}</strong>
        <span className="line-clamp-2 text-[12px] leading-snug text-friday-muted">{item.summary || item.kind || "Phone mesh handoff event."}</span>
      </div>
    </article>
  );
}

function MemoryLoadCard({ value }) {
  return (
    <article className="rounded-[6px] border border-friday-line bg-[#303743] p-4">
      <div className="grid grid-cols-[44px_minmax(0,1fr)_auto] items-center gap-3">
        <span className="grid h-11 w-11 place-items-center rounded-[8px] bg-[#d5a7ff] text-[#14091f]">
          <Brain size={21} />
        </span>
        <div className="min-w-0">
          <strong className="block truncate text-[13px] text-white">Memory Load</strong>
          <span className="mt-2 block h-1.5 w-full bg-[#1b232d]">
            <span className="block h-full bg-friday-accent" style={{ width: `${value}%` }} />
          </span>
        </div>
        <span className="font-mono text-[13px] text-friday-accent">{value}%</span>
      </div>
    </article>
  );
}

function memoryLoadPercent(data, thoughts, approvalCount) {
  const projects = data.projectMemory?.projects?.length || data.projects?.length || 0;
  const tasks = data.tasks?.length || 0;
  const openThoughts = data.thoughts?.open_count || thoughts.length || 0;
  const raw = projects * 9 + tasks * 0.5 + openThoughts * 3 + (approvalCount || 0) * 2;
  return Math.max(12, Math.min(96, Math.round(raw)));
}

function visionAnalysisText(data) {
  const observation = data.contextFusion?.observations?.[0]?.summary;
  if (observation) return observation;
  const activeWindow = data.pcAwareness?.active_window;
  if (activeWindow) return `Friday is monitoring the active desktop context: ${trimRailText(activeWindow, 110)}`;
  return "Vision monitoring is ready. Start the screen monitor to capture frames and learn recurring UI patterns.";
}

function androidRailAnalysis(mesh) {
  if (mesh?.summary) return trimRailText(mesh.summary, 150);
  const pending = mesh?.phone_mesh?.pending?.length || mesh?.device_mesh?.pending?.length || 0;
  if (pending) return `${pending} Android handoff item(s) are waiting for review on the PC mesh.`;
  return "Android mesh is ready. Connect the companion app or ADB bridge to activate phone notifications, captures, and handoffs.";
}

function railTimeAgo(value) {
  const then = new Date(value).getTime();
  if (!Number.isFinite(then)) return "now";
  const seconds = Math.max(1, Math.floor((Date.now() - then) / 1000));
  if (seconds < 60) return "now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function railClock(value) {
  const date = value ? new Date(value) : new Date();
  if (!Number.isFinite(date.getTime())) return "--:--:--";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

function trimRailText(value, limit) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, Math.max(0, limit - 1)).trim()}...`;
}

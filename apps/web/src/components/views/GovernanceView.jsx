"use client";

import {
  BarChart3,
  Bot,
  ChevronRight,
  Filter,
  MessageSquareText,
  Power,
  ShieldCheck,
  SlidersHorizontal,
  TrendingUp,
  UserPlus,
  UsersRound
} from "lucide-react";
import { useMemo, useState } from "react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";

export function GovernanceView() {
  const { data, interfaceFor } = useDashboard();
  const copy = interfaceFor?.("governance") || {};
  const [leaderFilter, setLeaderFilter] = useState("all");
  const leadersRaw = useMemo(() => governanceLeaders(data), [data]);
  const leaders = useMemo(() => filterLeaders(leadersRaw, leaderFilter), [leadersRaw, leaderFilter]);
  const council = useMemo(() => councilSession(data, leaders, copy), [data, leaders, copy]);
  const rosterCount = (data.offices?.length || data.agents?.length || leaders.length || 0);
  const pendingDecisions = data.approvalSummary?.count || data.approvals?.length || 0;

  return (
    <section className="min-h-full bg-friday-bg text-[#eaf2fb]" aria-label="Governance command surface">
      <div className="mx-auto grid w-full max-w-[980px] gap-4">
        <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(260px,1fr)]">
          <AgentLeaderboard leaders={leaders} copy={copy} filter={leaderFilter} onFilter={() => setLeaderFilter((value) => value === "all" ? "strong" : value === "strong" ? "needs_review" : "all")} />
          <DynamicRoster rosterCount={rosterCount} pendingDecisions={pendingDecisions} copy={copy} />
        </div>

        <CouncilSession council={council} />
        <GovernanceStream data={data} copy={copy} />
      </div>
    </section>
  );
}

function AgentLeaderboard({ leaders, copy, filter, onFilter }) {
  return (
    <Panel className="min-h-[430px]" title={copy?.title || "Agent Leaderboard"} icon={<BarChart3 size={24} />} action={<InlineAction icon={<Filter size={14} />} label={filter === "all" ? "All" : filter === "strong" ? "Strong" : "Review"} onClick={onFilter} />}>
      <div className="grid min-h-12 grid-cols-[minmax(120px,1fr)_minmax(150px,1fr)_90px] items-center border-b border-friday-line px-4 text-[12px] text-[#d8e2ee]">
        <span>Agent</span>
        <span>Best Task Type</span>
        <span className="text-right">Accuracy</span>
      </div>
      <div>
        {leaders.length ? leaders.slice(0, 6).map((agent, index) => (
          <div className="grid min-h-[64px] grid-cols-[minmax(120px,1fr)_minmax(150px,1fr)_90px] items-center border-b border-friday-line px-4 last:border-b-0" key={`${agent.agent_id || "agent"}-${index}`}>
            <div className="flex min-w-0 items-center gap-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-[6px] border border-[#465363] bg-[#303846] font-mono text-[14px] text-friday-accent">{initials(agent.agent_name || agent.agent_id)}</span>
              <strong className="min-w-0 truncate text-[14px] text-white">{agent.agent_name || titleize(agent.agent_id)}</strong>
            </div>
            <span className="min-w-0 truncate text-[13px] text-[#d9e2ee]">{taskLabel(agent)}</span>
            <span className={`font-mono text-[14px] text-right ${accuracyTone(agent.accuracy)}`}>{formatPercent(agent.accuracy)}</span>
          </div>
        )) : (
          <div className="grid min-h-[150px] place-items-center px-4 text-center text-[13px] text-friday-muted">
            {copy?.empty?.agents || "No agent quality rows came back from the backend yet."}
          </div>
        )}
      </div>
    </Panel>
  );
}

function DynamicRoster({ rosterCount, pendingDecisions, copy }) {
  const actions = [
    { title: "Hire Specialist", detail: "Spin up a new targeted agent", icon: <UserPlus size={18} />, tone: "blue", href: "/agents" },
    { title: "Promote Agent", detail: "Increase autonomy level", icon: <TrendingUp size={18} />, tone: "amber", href: "/agents" },
    { title: "Rewrite Role", detail: "Modify system prompt directives", icon: <SlidersHorizontal size={18} />, tone: "muted", href: "/memory" },
    { title: "Retire Agent", detail: "Decommission underperforming instance", icon: <Power size={18} />, tone: "danger", href: "/approvals" }
  ];
  return (
    <Panel title="Dynamic Roster" icon={<UsersRound size={24} />} iconTone="pink">
      <div className="grid gap-5 p-4">
        <p className="m-0 max-w-[260px] text-[14px] leading-relaxed text-[#d9e2ee]">{copy?.subtitle || "Manage autonomous agent lifecycle and operational scope."}</p>
        <div className="grid grid-cols-2 gap-2 text-[12px]">
          <MetricTile label="Roster" value={rosterCount} />
          <MetricTile label="Pending" value={pendingDecisions} />
        </div>
        <div className="grid gap-2">
          {actions.map((action) => <RosterAction action={action} key={action.title} />)}
        </div>
      </div>
    </Panel>
  );
}

function CouncilSession({ council }) {
  return (
    <Panel
      title="Active Council Session"
      icon={<MessageSquareText size={24} />}
      action={<span className="inline-flex min-h-7 items-center gap-2 rounded-full border border-[#3d4b59] bg-[#0d1218] px-3 text-[12px] text-friday-accent"><span className="h-2 w-2 rounded-full bg-friday-accent" />Deliberating</span>}
    >
      <div className="grid gap-5 p-4">
        <div>
          <h3 className="mb-2 font-mono text-[11px] font-bold uppercase tracking-[.16em] text-[#cdd7e4]">Directive Query</h3>
          <div className="min-w-0 overflow-hidden rounded-[3px] border border-[#3a4654] bg-[#080d11] px-4 py-3 font-mono text-[13px] text-white">
            <span className="mr-2 text-friday-accent">&gt;</span>
            <span className="break-words">{council.query}</span>
          </div>
        </div>

        <div className="grid gap-3 lg:grid-cols-3">
          {council.positions.length ? council.positions.map((position, index) => (
            <CouncilPosition position={position} highlighted={index === 1} key={`${position.agent}-${index}`} />
          )) : (
            <div className="grid min-h-[110px] place-items-center rounded-[4px] border border-dashed border-friday-line bg-[#10161d] px-4 text-center text-[13px] text-friday-muted lg:col-span-3">
              No council positions were returned in this governance read.
            </div>
          )}
        </div>

        <div className="grid gap-4 rounded-[4px] border border-[#466178] bg-[#19212b] p-4 md:grid-cols-[minmax(0,1fr)_180px]">
          <div className="min-w-0">
            <h3 className="mb-3 font-mono text-[12px] uppercase tracking-[.16em] text-friday-accent">Final Council Recommendation</h3>
            <p className="m-0 text-[14px] leading-relaxed text-[#eaf2fb]">{council.recommendation}</p>
          </div>
          <div className="grid content-center gap-2">
            <div className="flex items-center justify-between text-[12px] text-[#d8e2ee]">
              <span>Confidence</span>
              <strong className="font-mono text-friday-accent">{formatPercent(council.confidence)}</strong>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-[#0b1117]">
              <span className="block h-full bg-friday-accent" style={{ width: `${Math.round(council.confidence * 100)}%` }} />
            </div>
          </div>
        </div>
      </div>
    </Panel>
  );
}

function GovernanceStream({ data, copy }) {
  const rows = governanceRows(data);
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_280px]">
      <Panel title="Governance Event Stream" icon={<ShieldCheck size={22} />}>
        <div className="grid">
          {rows.length ? rows.map((row, index) => (
            <div className="grid min-h-[54px] grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-friday-line px-4 py-3 last:border-b-0" key={row.id || index}>
              <div className="min-w-0">
                <strong className="block truncate text-[13px] text-white">{row.title}</strong>
                <span className="block truncate text-[12px] text-friday-muted">{row.detail}</span>
              </div>
              <StatusBadge label={row.status} />
            </div>
          )) : (
            <div className="grid min-h-[110px] place-items-center px-4 text-center text-[13px] text-friday-muted">{copy?.empty?.activity || "Friday has no governance event in this read yet."}</div>
          )}
        </div>
      </Panel>

      <Panel title="Guardrails" icon={<Bot size={22} />}>
        <div className="grid gap-3 p-4">
          <Guardrail label="Risky actions" value="Approval gated" active />
          <Guardrail label="Private data" value="Permission required" active />
          <Guardrail label="Agent lifecycle" value="Governed" active />
        </div>
      </Panel>
    </div>
  );
}

function Panel({ title, icon, iconTone = "blue", action, children, className = "" }) {
  const tones = {
    blue: "text-friday-accent",
    pink: "text-[#f59cff]"
  };
  return (
    <section className={`min-w-0 overflow-hidden rounded-[8px] border border-friday-line bg-[#181e26] shadow-[0_14px_30px_rgba(0,0,0,.18)] ${className}`}>
      <header className="flex min-h-[58px] items-center gap-3 border-b border-friday-line px-4">
        <span className={tones[iconTone] || tones.blue}>{icon}</span>
        <h2 className="min-w-0 flex-1 truncate text-[18px] font-extrabold leading-none text-white">{title}</h2>
        {action}
      </header>
      {children}
    </section>
  );
}

function InlineAction({ icon, label, onClick }) {
  return (
    <button className="inline-flex min-h-8 items-center gap-1.5 rounded-[4px] border border-transparent px-2 text-[12px] text-[#d8e2ee] hover:border-friday-line hover:bg-[#10161d]" type="button" onClick={onClick}>
      {icon}
      {label}
    </button>
  );
}

function RosterAction({ action }) {
  const tone = {
    blue: "border-[#465363] bg-[#313946] text-friday-accent",
    amber: "border-[#594a38] bg-[#40362d] text-[#ffbf7b]",
    muted: "border-[#465363] bg-[#303743] text-[#d9e2ee]",
    danger: "border-[#77565b] bg-[#392f37] text-[#ffb5b8]"
  }[action.tone];
  return (
    <a className={`grid min-h-[70px] grid-cols-[40px_minmax(0,1fr)_18px] items-center gap-3 rounded-[4px] border px-3 transition-colors hover:border-friday-accent ${tone}`} href={action.href}>
      <span className="grid h-9 w-9 place-items-center rounded-[3px] bg-[#222a34]">{action.icon}</span>
      <span className="min-w-0">
        <strong className="block truncate text-[14px] text-white">{action.title}</strong>
        <span className="block truncate text-[12px] text-[#d6dfeb]">{action.detail}</span>
      </span>
      <ChevronRight size={16} />
    </a>
  );
}

function CouncilPosition({ position, highlighted }) {
  return (
    <article className={`min-w-0 rounded-[4px] border bg-[#0a0f14] p-4 ${highlighted ? "border-t-[#ffbf7b] border-friday-line border-t-2" : "border-friday-line"}`}>
      <div className="mb-3 flex min-w-0 items-center gap-2 border-b border-friday-line pb-3">
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-[3px] bg-[#303846] font-mono text-[10px] text-friday-accent">{initials(position.agent)}</span>
        <strong className="min-w-0 truncate text-[13px] text-white">{position.agent}</strong>
      </div>
      {position.stance ? <strong className="mb-1 block text-[13px] text-[#ffbf7b]">{position.stance}</strong> : null}
      <p className="m-0 text-[14px] leading-relaxed text-[#dfe8f4]">{position.detail}</p>
    </article>
  );
}

function MetricTile({ label, value }) {
  return (
    <div className="rounded-[4px] border border-friday-line bg-[#10161d] px-3 py-2">
      <span className="block font-mono text-[10px] uppercase tracking-[.12em] text-friday-muted">{label}</span>
      <strong className="mt-1 block text-[18px] leading-none text-white">{value}</strong>
    </div>
  );
}

function Guardrail({ label, value, active }) {
  return (
    <div className="grid min-h-12 grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-[4px] border border-friday-line bg-[#10161d] px-3">
      <span className="min-w-0 truncate text-[13px] text-[#dfe8f4]">{label}</span>
      <span className={`rounded-full border px-2 py-1 font-mono text-[10px] ${active ? "border-[#315c48] bg-[#12251f] text-[#8df0c6]" : "border-[#3a4654] bg-[#202733] text-friday-muted"}`}>{value}</span>
    </div>
  );
}

function StatusBadge({ label }) {
  return <span className="rounded-full border border-[#3a4654] bg-[#202733] px-2 py-1 font-mono text-[10px] uppercase tracking-[.08em] text-friday-accent">{label || "event"}</span>;
}

function governanceLeaders(data) {
  const quality = data.agentQuality?.leaderboard || [];
  if (quality.length) {
    return quality.map((item) => ({
      agent_id: item.agent_id,
      agent_name: titleize(item.agent_id),
      task_type: item.task_type || "General",
      accuracy: numberOrNull(item.accuracy ?? item.avg_score ?? item.score),
      summary: item.summary || item.note
    }));
  }
  const offices = data.offices || [];
  if (offices.length) {
    return offices.map((office, index) => ({
      agent_id: office.agent_id,
      agent_name: office.agent_name || office.room_name || titleize(office.agent_id),
      task_type: office.purpose || office.current_focus || "Agent Operations",
      accuracy: numberOrNull(office.accuracy ?? office.avg_score ?? office.score),
      summary: office.summary || office.current_focus || office.purpose
    }));
  }
  return [];
}

function filterLeaders(leaders, filter) {
  if (filter === "strong") return leaders.filter((agent) => clamp01(agent.accuracy) >= 0.85);
  if (filter === "needs_review") return leaders.filter((agent) => clamp01(agent.accuracy) < 0.85);
  return leaders;
}

function councilSession(data, leaders, copy) {
  const thought = data.thoughts?.recent?.[0];
  const approval = data.approvals?.[0];
  const query = approval?.title || thought?.summary || copy?.subtitle || "No council query is active in this snapshot.";
  const named = leaders.slice(0, 3);
  const positions = named.length ? named.map((agent, index) => ({
    agent: `${agent.agent_name || titleize(agent.agent_id)} (${taskLabel(agent)})`,
    stance: index === 1 ? `Challenges ${named[0]?.agent_name || "the lead"}.` : "",
    detail: councilDetail(agent, index)
  })) : [];
  return {
    query,
    positions,
    recommendation: approval?.summary || copy?.summary || copy?.subtitle || "Friday has no council recommendation from backend evidence yet.",
    confidence: clamp01(named[0]?.accuracy)
  };
}

function councilDetail(agent, index) {
  if (agent.summary) return agent.summary;
  const accuracy = formatPercent(agent.accuracy);
  if (accuracy !== "--") return `Backend quality score for this agent is ${accuracy}.`;
  return index === 0 ? "This agent is in the governance roster, but no scored council note came back." : "No detailed council note was returned for this agent.";
}

function governanceRows(data) {
  const audit = (data.audit || []).map((item) => ({
    id: item.id,
    title: item.title || item.action || item.event_type || "Governance event",
    detail: item.summary || item.detail || item.actor || item.category || "Recorded by audit log",
    status: item.status || item.category || "audit"
  }));
  const approvals = (data.approvals || []).map((item) => ({
    id: `approval-${item.id}`,
    title: item.title || "Approval required",
    detail: item.summary || item.action_hint || item.kind || "Decision waiting",
    status: "approval"
  }));
  return [...approvals, ...audit].slice(0, 5);
}

function taskLabel(agent) {
  return agent.task_type || agent.best_task_type || "General";
}

function initials(value) {
  const words = String(value || "AG").replace(/[_-]+/g, " ").split(" ").filter(Boolean);
  return words.slice(0, 2).map((word) => word[0]).join("").toUpperCase();
}

function titleize(value) {
  return String(value || "Agent")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatPercent(value) {
  if (value == null || value === "") return "--";
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  return `${(clamp01(value) * 100).toFixed(1)}%`;
}

function accuracyTone(value) {
  if (value == null || value === "" || !Number.isFinite(Number(value))) return "text-friday-muted";
  const number = clamp01(value);
  if (number >= 0.9) return "text-friday-accent";
  if (number >= 0.75) return "text-[#ffbf7b]";
  return "text-[#ffb5b8]";
}

function clamp01(value) {
  return Math.max(0, Math.min(1, Number(value) || 0));
}

function numberOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

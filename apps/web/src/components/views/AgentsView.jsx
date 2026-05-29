"use client";

import {
  Bot,
  Code2,
  FilePenLine,
  Filter,
  Plus,
  SquareTerminal,
  Target,
  X
} from "lucide-react";
import { useMemo, useState } from "react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";

const ICONS = [SquareTerminal, Code2, FilePenLine, Bot];

export function AgentsView() {
  const { data, interfaceFor } = useDashboard();
  const copy = interfaceFor?.("agents") || {};
  const [filter, setFilter] = useState("all");
  const allOffices = useMemo(() => normalizeOffices(data.offices, data.agents), [data.offices, data.agents]);
  const offices = useMemo(() => filterOffices(allOffices, filter), [allOffices, filter]);
  const [selectedId, setSelectedId] = useState("");
  const [detailOpen, setDetailOpen] = useState(true);
  const selected = offices.find((office) => office.agent_id === selectedId) || offices[0] || null;

  function cycleFilter() {
    const next = { all: "active", active: "blocked", blocked: "idle", idle: "all" };
    setFilter(next[filter] || "all");
    setDetailOpen(true);
  }

  return (
    <section className="friday-scroll h-full overflow-y-auto overflow-x-hidden bg-friday-bg text-[#eaf2fb]" aria-label="Active Agents">
      <div className="grid min-h-full min-w-0 grid-cols-[minmax(0,1fr)_360px]">
        <main className="min-w-0 p-6">
          <header className="mb-5 flex min-w-0 items-end justify-between gap-4 border-b border-friday-line pb-5">
            <div className="min-w-0">
              <h1 className="text-[26px] font-extrabold leading-none text-white">{copy?.title || "Active Agents"}</h1>
              <p className="mt-2 text-[14px] text-[#c4d2e2]">{copy?.subtitle || "Office floor grid and operational status"}</p>
            </div>
            <div className="flex shrink-0 gap-2">
              <button className="flex min-h-9 items-center gap-2 border border-friday-line bg-[#151c25] px-5 text-[13px] font-semibold text-[#dce8f7] hover:border-friday-accent" type="button" onClick={cycleFilter} title="Cycle agent status filter">
                <Filter size={15} />
                {filter === "all" ? "All Agents" : titleize(filter)}
              </button>
              <a className="flex min-h-9 items-center gap-2 border border-friday-blue bg-friday-blue px-5 text-[13px] font-bold text-[#061420]" href="/tasks">
                <Plus size={16} />
                New Task
              </a>
            </div>
          </header>

          <div className="grid min-w-0 grid-cols-2 gap-4">
            {offices.length ? offices.map((office, index) => (
              <AgentCard agent={office} index={index} key={`${office.agent_id || "agent"}-${index}`} selected={detailOpen && office.agent_id === selected?.agent_id} onSelect={() => { setSelectedId(office.agent_id); setDetailOpen(true); }} />
            )) : (
              <div className="col-span-2 grid min-h-[220px] place-items-center border border-friday-line bg-[#151b22] text-friday-muted">
                {copy?.empty?.agents || "Friday has no agent office rows in this read."}
              </div>
            )}
          </div>
        </main>

        {detailOpen ? <AgentDetail agent={selected} data={data} copy={copy} onClose={() => setDetailOpen(false)} /> : <AgentSummary offices={offices} copy={copy} onOpen={() => setDetailOpen(true)} />}
      </div>
    </section>
  );
}

function AgentCard({ agent, index, selected, onSelect }) {
  const Icon = ICONS[index % ICONS.length];
  const progress = Number(agent.progress_percent || 0);
  return (
    <button
      className={`grid min-h-[196px] min-w-0 overflow-hidden border bg-gradient-to-b from-[#171d25] to-[#10161d] text-left ${selected ? "border-friday-accent shadow-[inset_0_0_0_1px_rgba(159,202,255,.25)]" : "border-friday-line"} ${lower(agent.status) === "idle" ? "opacity-75" : ""}`}
      type="button"
      onClick={onSelect}
    >
      <header className="flex min-w-0 items-center gap-3 border-b border-friday-line px-4 py-4">
        <span className="grid h-10 w-10 shrink-0 place-items-center border border-friday-line bg-[#0f151d] text-friday-accent">
          <Icon size={19} />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="flex min-w-0 items-center gap-2 text-[19px] font-extrabold leading-none">
            <span className="min-w-0 truncate">{agent.agent_name || agent.agent_id}</span>
            {selected ? <span className="h-2 w-2 shrink-0 rounded-full bg-friday-accent" /> : null}
          </h2>
          <p className="mt-1 truncate font-mono text-[12px] uppercase tracking-[.12em] text-[#cfd9e6]">{agent.room_name || agent.purpose || "Agent Office"}</p>
        </div>
        <StatusPill label={agent.status || "idle"} tone={statusTone(agent.status)} />
      </header>

      <div className="grid min-w-0 gap-4 p-4">
        <Field label="Current Focus" value={agent.current_task?.title || agent.current_focus || "Waiting for assignment"} muted={!agent.current_task && lower(agent.status) === "idle"} />
        <div className="min-w-0">
          <div className="mb-2 flex min-w-0 items-center justify-between gap-3 text-[13px] text-[#cfd9e6]">
            <span className="min-w-0 truncate">Task Progress</span>
            <strong className="shrink-0 text-friday-accent">{progress}%</strong>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-[#303946]">
            <span className="block h-full max-w-full rounded-full bg-friday-accent" style={{ width: `${Math.max(0, Math.min(100, progress))}%` }} />
          </div>
        </div>
        <div className="min-w-0 truncate border border-[#263341] bg-[#090e13] px-3 py-3 font-mono text-[12px] text-[#d8e2ee]">{providerChain(agent)}</div>
      </div>

      <footer className="mt-auto min-w-0 truncate border-t border-friday-line px-4 py-3 font-mono text-[12px] text-[#cdd8e6]">{taskCountLine(agent)}</footer>
    </button>
  );
}

function Field({ label, value, muted }) {
  return (
    <div className="min-w-0">
      <h3 className="mb-2 text-[13px] font-bold text-[#cfd9e6]">{label}</h3>
      <p className={`block w-full min-w-0 max-w-full overflow-hidden text-ellipsis whitespace-nowrap border border-[#263341] bg-[#1d222b] px-3 py-3 text-[13px] ${muted ? "italic text-[#aab4c1]" : "text-[#f0f6ff]"}`}>{value}</p>
    </div>
  );
}

function AgentDetail({ agent, data, copy, onClose }) {
  const thoughts = (data.thoughts?.recent || []).filter((thought) => !agent || !thought.target_agent_id || thought.target_agent_id === agent.agent_id);
  const quality = qualityForAgent(data.agentQuality, agent?.agent_id);
  const contextRows = loadedContext(agent);
  return (
    <aside className="grid min-w-0 grid-rows-[auto_1fr_auto] overflow-hidden border-l border-friday-line bg-[#151b23]">
      <header className="flex min-w-0 items-start gap-4 border-b border-friday-line p-5">
        <span className="grid h-12 w-12 shrink-0 place-items-center border border-friday-accent bg-[#0f151d] text-friday-accent">
          <SquareTerminal size={23} />
        </span>
        <div className="min-w-0">
          <h2 className="flex min-w-0 items-center gap-2 text-[24px] font-extrabold leading-none text-white">
            <span className="truncate">{agent?.agent_name || copy?.empty?.agents || "No Agent"}</span>
            {agent ? <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-friday-accent" /> : null}
          </h2>
          <p className="mt-2 truncate font-mono text-[13px] font-bold uppercase tracking-[.18em] text-friday-accent">{agent?.purpose || agent?.room_name || "Agent detail"}</p>
        </div>
        <button className="ml-auto shrink-0 text-[#d5dfeb] hover:text-white" type="button" aria-label="Close agent detail" onClick={onClose}>
          <X size={20} />
        </button>
      </header>

      <div className="friday-scroll grid min-w-0 content-start gap-6 overflow-y-auto overflow-x-hidden p-5">
        <DetailSection icon={<Target size={16} />} title="Active Operation">
          <div className="border border-friday-line bg-[#0d1218] p-4">
            <p className="text-[16px] leading-relaxed text-[#f2f7ff]">{agent?.current_task?.title || agent?.current_focus || copy?.empty?.tasks || "No active operation."}</p>
            <div className="mt-4 flex min-w-0 flex-wrap gap-2">
              <Chip label={`Agent: ${agent?.agent_id || "none"}`} />
              <Chip label={`Status: ${agent?.status || "unknown"}`} active />
            </div>
          </div>
        </DetailSection>

        <DetailSection title="Working Memory">
          <MemoryList rows={workingMemoryRows(agent)} />
        </DetailSection>

        <DetailSection title="Agent Queries / Thoughts">
          <div className="border border-[#6a4215] bg-[#17131a] p-4">
            {thoughts.length ? (
              <>
                <p className="mb-4 line-clamp-4 text-[16px] leading-relaxed text-white">"{thoughts[0].summary}"</p>
                <div className="grid grid-cols-2 gap-2">
                  <a className="grid min-h-10 place-items-center border border-friday-line bg-[#343a44] text-[13px] text-white" href="/approvals">Review</a>
                  <a className="grid min-h-10 place-items-center border border-friday-blue bg-friday-blue text-[13px] text-[#061420]" href="/chat">Ask Friday</a>
                </div>
              </>
            ) : (
              <p className="text-[14px] text-friday-muted">{copy?.empty?.activity || "Friday has no open thought packet or agent question for this agent."}</p>
            )}
          </div>
        </DetailSection>

        <div className="grid min-w-0 grid-cols-2 gap-4">
          <DetailCard title="Loaded Context">
            <div className="flex flex-wrap gap-2">
              {contextRows.length ? contextRows.map((item, index) => <Chip label={item} key={`${index}-${item}`} />) : <p className="m-0 text-[12px] text-friday-muted">{copy?.empty?.evidence || "No provider, topic, or peer context is attached to this agent yet."}</p>}
            </div>
          </DetailCard>
          <DetailCard title="Output Quality">
            {quality ? (
              <>
                <div className="flex items-end gap-2">
                  {[quality.accuracy, quality.usefulness, quality.speed, quality.evidence, 1 - quality.mistakes].map((value, index) => <span className="w-7 bg-friday-accent" style={{ height: Math.max(12, Number(value || 0) * 70) }} key={index} />)}
                </div>
                <div className="mt-3 flex justify-between font-mono text-[12px] text-friday-accent">
                  <span>{Math.round((quality.avg_score || 0) * 100)}%</span>
                  <span>{quality.samples || 0} sample(s)</span>
                </div>
              </>
            ) : (
              <p className="text-[12px] text-friday-muted">{copy?.empty?.evidence || "Friday has not learned a quality profile for this agent yet."}</p>
            )}
          </DetailCard>
        </div>
      </div>

      <footer className="grid grid-cols-2 gap-3 border-t border-friday-line p-5">
        <a className="grid min-h-11 place-items-center border border-friday-line bg-[#10161d] font-mono text-[13px] font-bold text-[#dfe9f6]" href="/tasks">Tasks</a>
        <a className="grid min-h-11 place-items-center border border-friday-line bg-[#10161d] font-mono text-[13px] font-bold text-[#dfe9f6]" href="/memory">Memory</a>
      </footer>
    </aside>
  );
}

function AgentSummary({ offices, copy, onOpen }) {
  const active = offices.filter((office) => ["active", "working", "running"].includes(lower(office.status))).length;
  return (
    <aside className="grid min-w-0 content-center border-l border-friday-line bg-[#151b23] p-6 text-center">
      <div className="grid gap-3">
        <Bot className="mx-auto text-friday-accent" size={28} />
        <strong className="text-[17px] text-white">{copy?.rail?.title || "Agent detail is hidden"}</strong>
        <p className="text-[13px] leading-relaxed text-friday-muted">{active} active agent(s) in the current filter. {copy?.rail?.focus || "Select an agent or reopen the side panel."}</p>
        <button className="mx-auto min-h-9 border border-friday-line bg-[#10161d] px-4 text-[12px] text-[#dfe9f6] hover:border-friday-accent" type="button" onClick={onOpen}>Open Detail</button>
      </div>
    </aside>
  );
}

function DetailSection({ icon, title, children }) {
  return (
    <section className="min-w-0">
      <h3 className="mb-3 flex items-center gap-2 text-[14px] font-bold uppercase tracking-[.08em] text-[#cfd9e6]">
        {icon}
        {title}
      </h3>
      {children}
    </section>
  );
}

function DetailCard({ title, children }) {
  return (
    <section className="min-w-0 overflow-hidden border border-friday-line bg-[#10161d] p-4">
      <h3 className="mb-4 font-mono text-[12px] uppercase tracking-[.12em] text-[#e4edf8]">{title}</h3>
      {children}
    </section>
  );
}

function MemoryList({ rows }) {
  return (
    <div className="min-w-0 overflow-hidden border border-friday-line bg-[#0d1218]">
      {rows.length ? rows.map((row, index) => (
        <p className="break-words border-b border-friday-line px-4 py-3 font-mono text-[12px] leading-relaxed text-[#dfe8f4] last:border-b-0" key={`${index}-${row.slice(0, 32)}`}>{row}</p>
      )) : <p className="px-4 py-3 text-[12px] text-friday-muted">Friday has no recent task message or office memory in this read.</p>}
    </div>
  );
}

function StatusPill({ label, tone }) {
  const styles = {
    blue: "border-[#466b91] bg-[#20344a] text-friday-accent",
    orange: "border-[#6a4215] bg-[#2d2114] text-[#ffb56d]",
    green: "border-[#315c48] bg-[#163126] text-[#90efc9]",
    muted: "border-[#3a4654] bg-[#202733] text-[#aab4c1]"
  };
  return <span className={`ml-auto shrink-0 border px-2 py-1 font-mono text-[11px] ${styles[tone]}`}>{label}</span>;
}

function Chip({ label, active }) {
  return <span className={`inline-block max-w-full truncate whitespace-nowrap border px-2 py-1 font-mono text-[11px] ${active ? "border-[#34516c] bg-[#132235] text-friday-accent" : "border-friday-line bg-[#202733] text-[#dce7f4]"}`}>{label}</span>;
}

function normalizeOffices(offices, agents) {
  if (offices?.length) return offices;
  return (agents || []).map((agent) => ({
    agent_id: agent.id,
    agent_name: agent.name,
    purpose: agent.purpose,
    room_name: agent.name,
    status: "idle",
    current_focus: "Waiting for assignment",
    progress_percent: 0,
    task_counts: {},
    provider_chain: [],
    recent_messages: [],
    recent_tasks: []
  }));
}

function filterOffices(offices, filter) {
  if (filter === "all") return offices;
  return offices.filter((office) => {
    const status = lower(office.status);
    if (filter === "active") return ["active", "working", "running"].includes(status);
    if (filter === "blocked") return ["blocked", "failed"].includes(status);
    return status === filter;
  });
}

function providerChain(agent) {
  return (agent.provider_chain || []).length ? agent.provider_chain.join(" > ") : "Provider chain is not attached to this snapshot";
}

function taskCountLine(agent) {
  const counts = agent.task_counts || {};
  return `${counts.active || 0} active / ${counts.pending || 0} pending / ${counts.done || 0} done`;
}

function workingMemoryRows(agent) {
  const messages = (agent?.recent_messages || []).map((message) => `> ${message.sender || "agent"}: ${message.message || message.task_title || ""}`);
  const tasks = (agent?.recent_tasks || []).map((task) => `> ${task.status}: ${task.title}`);
  return [...messages, ...tasks].filter(Boolean).slice(0, 4);
}

function loadedContext(agent) {
  const providers = agent?.provider_chain || [];
  const topics = (agent?.competence || []).map((item) => item.topic).filter(Boolean);
  const peers = agent?.known_peers?.length ? [`${agent.known_peers.length} peer(s)`] : [];
  return [...providers, ...topics, ...peers].slice(0, 6);
}

function qualityForAgent(agentQuality, agentId) {
  return (agentQuality?.leaderboard || []).find((item) => item.agent_id === agentId) || null;
}

function statusTone(status) {
  const value = lower(status);
  if (["active", "working", "running"].includes(value)) return "blue";
  if (["blocked", "failed"].includes(value)) return "orange";
  if (["done", "complete", "completed"].includes(value)) return "green";
  return "muted";
}

function lower(value) {
  return String(value || "").toLowerCase();
}

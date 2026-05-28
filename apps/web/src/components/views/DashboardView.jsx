"use client";

import {
  Activity,
  Battery,
  Check,
  ClipboardList,
  Database,
  Inbox,
  Plus,
  RefreshCcw,
  Rocket,
  Server,
  Wifi
} from "lucide-react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";

export function DashboardView() {
  const { data } = useDashboard();
  const approvals = approvalItems(data);
  const tasks = data.tasks || [];
  const offices = data.offices || [];
  const missions = data.missions || [];

  return (
    <section className="friday-scroll h-full overflow-y-auto bg-friday-bg px-2 py-2 text-white" aria-label="Dashboard operations board">
      <div className="grid max-w-100dvw gap-3">
        <NowStrip data={data} />
        <CommandStrip />

        <div className="grid grid-cols-[minmax(0,1fr)_314px] gap-3">
          <div className="grid content-start gap-3">
            <div className="grid grid-cols-2 gap-3">
              <RecommendedAction data={data} tasks={tasks} approvals={approvals} />
              <ActiveMissions missions={missions} missionStatus={data.missionStatus} />
            </div>
            <TaskQueue tasks={tasks} />
            <BackgroundAgents offices={offices} workerStatus={data.status} />
          </div>

          <div className="grid content-start gap-3">
            <PendingApprovals approvals={approvals} summary={data.approvalSummary} />
            <Telemetry data={data} />
            <RecentActivity data={data} />
          </div>
        </div>
      </div>
    </section>
  );
}

function NowStrip({ data }) {
  const activeWindow = data.pcAwareness?.active_window || "No active window captured";
  const workers = data.status?.running ? `${data.status.workers || 0} workers` : "workers stopped";
  const mode = data.status?.mode || (data.status?.running ? "agent mode" : "idle");
  const runningApps = data.pcAwareness?.stats?.running_apps;

  return (
    <div className="flex min-h-12 items-center gap-2 overflow-hidden border border-friday-line bg-[#090e13] px-4 text-[12px]">
      <span className="shrink-0 font-mono font-bold uppercase tracking-[.08em] text-white">Now:</span>
      <StatusChip icon={<Server size={11} />} label={activeWindow} />
      <StatusChip icon={<Inbox size={11} />} label={`Friday: ${mode}`} active={data.status?.running} />
      <StatusChip icon={<Rocket size={11} />} label={`Agents: ${workers}`} />
      <div className="ml-auto flex shrink-0 items-center gap-2 font-mono text-[12px] text-white">
        <span className={`h-2 w-2 rounded-full ${data.status?.running ? "bg-friday-ok" : "bg-[#667386]"}`} />
        <span className="h-2 w-2 rounded-full bg-friday-ok" />
        <Battery size={13} />
        <span>{runningApps == null ? "PC" : `${runningApps} apps`}</span>
      </div>
    </div>
  );
}

function StatusChip({ icon, label, active }) {
  return (
    <span className={`inline-flex min-h-[30px] min-w-0 items-center gap-1.5 border px-3 font-mono text-[12px] ${active ? "border-[#31587f] bg-[#101d2b] text-friday-accent" : "border-[#303b48] bg-[#111820] text-[#e4edf8]"}`}>
      {icon}
      <span className="truncate">{label}</span>
    </span>
  );
}

function CommandStrip() {
  return (
    <div className="flex min-h-[54px] items-center gap-3 rounded border border-friday-line bg-[#151b22] px-4">
      <span className="font-mono text-friday-accent">&gt;</span>
      <span className="flex-1 font-mono text-[12px] tracking-[.08em] text-[#7f8da0]">Use Chat or voice to command Friday. This strip reflects the same orchestrator.</span>
      <a className="grid min-h-7 place-items-center border border-[#465365] bg-[#1a2028] px-3 font-mono text-[11px] uppercase tracking-[.12em] text-white" href="/chat">
        Chat
      </a>
    </div>
  );
}

function RecommendedAction({ data, tasks, approvals }) {
  const observation = data.contextFusion?.observations?.[0];
  const notification = data.notifications?.items?.[0];
  const task = tasks.find((item) => ["active", "pending", "blocked"].includes(lower(item.status)));
  const approval = approvals[0];
  const item = observation
    ? { title: "Review Live Context Signal", detail: observation.summary, href: "/vision", action: "Open Context" }
    : approval
      ? { title: approval.title, detail: approval.summary || approval.action_hint, href: "/approvals", action: "Open Approval" }
      : task
        ? { title: task.title, detail: task.description || task.status, href: "/tasks", action: "Open Task" }
        : notification
          ? { title: notification.title, detail: notification.message, href: "/approvals", action: "Open Inbox" }
          : { title: "No urgent action", detail: "Friday has no active mission, approval, or queued task needing attention.", href: "/chat", action: "Ask Friday" };

  return (
    <article className="grid min-h-[230px] content-between rounded border border-friday-line bg-gradient-to-b from-friday-panel to-[#0a0f14] p-4">
      <div className="min-w-0">
        <CardTitle icon={<ClipboardList size={13} />} label="Next Recommended Action" />
        <h2 className="mt-5 line-clamp-2 text-[20px] font-extrabold leading-tight">{item.title}</h2>
        <p className="mt-3 line-clamp-3 max-w-[270px] text-[13px] leading-relaxed text-[#dce7f3]">{item.detail || "No extra detail available."}</p>
      </div>
      <div className="grid grid-cols-[1fr_86px] gap-2">
        <a className="grid min-h-9 place-items-center border border-[#97c8f8] bg-[#97c8f8] text-[12px] text-[#04111f]" href={item.href}>{item.action}</a>
        <a className="grid min-h-9 place-items-center border border-friday-line bg-[#151b23] text-[12px] text-white" href="/chat">Ask</a>
      </div>
    </article>
  );
}

function ActiveMissions({ missions, missionStatus }) {
  const rows = missions.slice(0, 2);
  return (
    <article className="min-h-[230px] rounded border border-friday-line bg-gradient-to-b from-friday-panel to-[#0a0f14] p-4">
      <div className="mb-4 flex items-center gap-2">
        <CardTitle icon={<Rocket size={13} />} label="Active Missions" />
        <a className="ml-auto text-[11px] font-semibold text-friday-accent" href="/mission-control">View All</a>
      </div>
      <div className="grid gap-3">
        {rows.length ? rows.map((mission, index) => <MissionRow mission={mission} key={mission.id || `${index}-${mission.goal}`} />) : (
          <EmptyBox text={missionStatus?.summary || "No mission running. Start one from Mission Control or Chat."} />
        )}
      </div>
    </article>
  );
}

function MissionRow({ mission }) {
  const progress = Number(mission.progress_percent || 0);
  const done = ["completed", "done"].includes(lower(mission.status));
  return (
    <div className={`border bg-[#171d24] p-3 ${done ? "border-l-friday-ok" : "border-l-friday-accent"} border-l-2 border-y-friday-line border-r-friday-line`}>
      <div className="mb-3 flex items-center gap-2">
        <strong className="truncate text-[12px]">{mission.goal || mission.summary || `Mission #${mission.id}`}</strong>
        <span className={`ml-auto shrink-0 border px-1.5 py-0.5 font-mono text-[10px] ${done ? "border-[#315c48] bg-[#163126] text-[#90efc9]" : "border-[#31587f] bg-[#122033] text-friday-accent"}`}>{mission.status || "unknown"}</span>
      </div>
      <div className="h-1.5 overflow-hidden bg-[#303945]"><span className="block h-full bg-[#97c8f8]" style={{ width: `${Math.max(0, Math.min(100, progress))}%` }} /></div>
      <div className="mt-2 flex justify-between font-mono text-[10px] text-[#c8d4e2]"><span>{mission.current_phase || mission.mission_type || "mission"}</span><span>{progress}%</span></div>
    </div>
  );
}

function PendingApprovals({ approvals, summary }) {
  return (
    <article className="rounded border border-friday-line bg-gradient-to-b from-friday-panel to-[#0a0f14] p-4">
      <div className="mb-4 flex items-center">
        <CardTitle icon={<Inbox size={13} />} label="Pending Approvals" />
        <span className="ml-auto rounded bg-[#303946] px-2 py-0.5 font-mono text-[10px]">{summary?.count || approvals.length}</span>
      </div>
      <div className="grid gap-3">
        {approvals.length ? approvals.slice(0, 2).map((approval) => <ApprovalCard approval={approval} key={`${approval.kind}-${approval.id}`} />) : (
          <EmptyBox text="No approval decisions are waiting." />
        )}
      </div>
    </article>
  );
}

function ApprovalCard({ approval }) {
  return (
    <div className="border border-friday-line bg-[#151b22] p-3">
      <div className="mb-2 flex items-center gap-2">
        <strong className="truncate text-[12px]">{approval.title || approval.kind}</strong>
        <span className="ml-auto shrink-0 font-mono text-[11px] text-[#cbd7e6]">{approval.agent_id || approval.kind}</span>
      </div>
      <p className="m-0 min-h-[34px] text-[11px] leading-relaxed text-[#dce6f2]">{approval.summary || approval.action_hint || "Waiting for a decision."}</p>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <a className="grid min-h-[27px] place-items-center border border-[#7edfae] bg-transparent font-mono text-[11px] text-[#a4f0c1]" href="/approvals">Review</a>
        <a className="grid min-h-[27px] place-items-center border border-[#c47a6d] bg-transparent font-mono text-[11px] text-[#ffaaa0]" href="/safety">Policy</a>
      </div>
    </div>
  );
}

function TaskQueue({ tasks }) {
  const rows = tasks.filter((item) => !["done", "cancelled"].includes(lower(item.status))).slice(0, 3);
  const fallback = tasks.slice(0, 3);
  const display = rows.length ? rows : fallback;
  return (
    <article className="rounded border border-friday-line bg-gradient-to-b from-friday-panel to-[#0a0f14]">
      <div className="flex h-[56px] items-center border-b border-friday-line px-4">
        <CardTitle icon={<ClipboardList size={13} />} label="Task Queue Priorities" />
        <Plus className="ml-auto text-friday-accent" size={18} />
      </div>
      {display.length ? display.map((task, index) => <PriorityRow task={task} key={task.id || `${index}-${task.title}`} />) : (
        <div className="px-4 py-5 text-[12px] text-friday-muted">No queued task records are loaded.</div>
      )}
    </article>
  );
}

function PriorityRow({ task }) {
  const done = ["done", "completed"].includes(lower(task.status));
  return (
    <div className="grid min-h-[45px] grid-cols-[18px_minmax(0,1fr)_auto] items-center gap-2 border-b border-friday-line px-3 last:border-b-0">
      <span className={`grid h-3.5 w-3.5 place-items-center border ${done ? "border-[#97c8f8] bg-[#97c8f8]" : "border-[#33404d] bg-[#0c1218]"}`}>
        {done ? <Check size={10} className="text-[#061420]" /> : null}
      </span>
      <div className={done ? "min-w-0 text-friday-muted line-through" : "min-w-0"}>
        <strong className="block truncate text-[12px]">{task.title || `Task #${task.id}`}</strong>
        <span className="block truncate text-[10px] text-[#cbd7e6]">{task.agent_id || "agent"} · {task.description || task.status}</span>
      </div>
      <StatusTag label={task.status || "unknown"} />
    </div>
  );
}

function BackgroundAgents({ offices, workerStatus }) {
  const rows = offices.slice(0, 4);
  return (
    <section>
      <CardTitle icon={<Database size={13} />} label="Background Agents" />
      <div className="mt-2 grid grid-cols-4 gap-1.5">
        {rows.length ? rows.map((office, index) => (
          <a className="flex min-h-[26px] min-w-0 items-center justify-between gap-2 border border-friday-line bg-[#151b22] px-2 font-mono text-[10px] text-[#cfd9e6]" href="/agents" key={`${office.agent_id || "agent"}-${index}`}>
            <span className="truncate">{office.agent_name || office.agent_id}</span>
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${statusDot(office.status)}`} />
          </a>
        )) : (
          <div className="col-span-4 border border-friday-line bg-[#151b22] px-2 py-2 font-mono text-[10px] text-friday-muted">
            {workerStatus?.running ? "Workers running, no office snapshots loaded." : "Workers stopped."}
          </div>
        )}
      </div>
    </section>
  );
}

function Telemetry({ data }) {
  const status = data.status || {};
  const counts = status.tasks || {};
  const providers = status.runtime?.provider_limits || {};
  const providerCount = Object.values(providers).filter((item) => item?.configured).length;
  const unsupported = data.evaluation?.counts?.unsupported_claim || 0;
  const gateway = data.gateway || {};
  return (
    <article className="rounded border border-friday-line bg-gradient-to-b from-friday-panel to-[#0a0f14] p-4">
      <div className="flex items-center gap-2 text-[12px] font-extrabold uppercase tracking-[.11em] text-white">
        <Activity size={14} className="text-friday-accent" />
        Telemetry
      </div>
      <div className="mt-4 grid grid-cols-2 gap-1.5">
        <MetricBox label="Workers" value={String(status.workers || 0)} detail={status.mode || "agent mode"} />
        <MetricBox label="Tasks" value={String(counts.total || data.tasks?.length || 0)} detail={`${counts.active || 0} active`} />
        <MetricBox label="Gateway" value={String(gateway.enabled_count || 0)} detail={`${gateway.pending_high_risk || 0} high-risk`} />
        <div className="col-span-2 grid min-h-[47px] grid-cols-[minmax(0,1fr)_auto] items-center gap-3 overflow-hidden border border-friday-line bg-[#171d24] px-3">
          <div className="min-w-0">
            <span className="block font-mono text-[10px] uppercase text-[#cbd7e6]">Reliability</span>
            <span className="block truncate font-mono text-[12px]">{providerCount} provider(s) configured · {unsupported} unsupported claim alert(s)</span>
          </div>
          <Wifi className="shrink-0 text-[#79e8af]" size={22} />
        </div>
      </div>
    </article>
  );
}

function MetricBox({ label, value, detail }) {
  return (
    <div className="border border-friday-line bg-[#171d24] p-3">
      <span className="block font-mono text-[10px] uppercase text-[#cbd7e6]">{label}</span>
      <div className="mt-1 grid grid-cols-[auto_minmax(0,1fr)] items-end gap-3">
        <strong className="text-[20px] leading-none">{value}</strong>
        <span className="mb-0.5 grid min-w-0 grid-cols-4 gap-1 overflow-hidden">
          {[0, 1, 2, 3].map((item) => <i className="block h-1.5 min-w-0 bg-[#80d9ac]" key={item} />)}
        </span>
      </div>
      <span className="mt-1 block truncate text-[10px] text-friday-muted">{detail}</span>
    </div>
  );
}

function RecentActivity({ data }) {
  const notificationRows = (data.notifications?.items || []).map((item) => ({
    color: item.severity >= 3 ? "bg-[#c58f88]" : "bg-[#97c8f8]",
    time: formatTime(item.timestamp),
    text: `${item.title}: ${item.message || item.category || ""}`
  }));
  const auditRows = (data.audit || []).map((item) => ({
    color: "bg-[#607084]",
    time: formatTime(item.timestamp),
    text: item.summary || item.action || item.category || "Audit event"
  }));
  const rows = [...notificationRows, ...auditRows].slice(0, 3);
  return (
    <article className="rounded border border-friday-line bg-gradient-to-b from-friday-panel to-[#0a0f14] p-4">
      <CardTitle icon={<RefreshCcw size={13} />} label="Recent Activity" />
      <div className="mt-4 grid gap-3 border-l border-[#34404d] pl-3">
        {rows.length ? rows.map((item, index) => <ActivityItem {...item} key={`${item.time}-${index}`} />) : <p className="text-[11px] text-friday-muted">No recent notification or audit events loaded.</p>}
      </div>
    </article>
  );
}

function ActivityItem({ color, time, text }) {
  return (
    <div className="relative min-w-0">
      <span className={`absolute -left-[17px] top-1 h-2 w-2 rounded-full ${color}`} />
      <span className="block font-mono text-[11px] text-[#dce6f2]">{time}</span>
      <p className="m-0 mt-1 line-clamp-2 text-[11px] leading-relaxed text-[#e6edf7]">{text}</p>
    </div>
  );
}

function EmptyBox({ text }) {
  return <div className="grid min-h-[74px] place-items-center border border-friday-line bg-[#151b22] px-3 text-center text-[12px] leading-relaxed text-friday-muted">{text}</div>;
}

function CardTitle({ icon, label }) {
  return (
    <div className="flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-[.08em] text-white">
      {icon}
      {label}
    </div>
  );
}

function StatusTag({ label }) {
  const value = lower(label);
  const warn = ["blocked", "failed", "cancelled"].includes(value);
  return (
    <span className={`border px-2 py-1 font-mono text-[10px] ${warn ? "border-[#59323c] bg-[#28171d] text-[#ffb2bc]" : value === "pending" ? "border-[#5c4327] bg-[#261c11] text-[#ffc98c]" : "border-[#465365] bg-[#2a3039] text-[#dce6f2]"}`}>
      {label}
    </span>
  );
}

function approvalItems(data) {
  return data.approvalSummary?.items || data.approvals || [];
}

function statusDot(status) {
  const value = lower(status);
  if (value === "active" || value === "working") return "bg-[#97c8f8]";
  if (value === "blocked") return "bg-[#ffb26f]";
  if (value === "idle") return "bg-[#475263]";
  if (value === "done" || value === "complete") return "bg-[#5ee0a4]";
  return "bg-[#667386]";
}

function lower(value) {
  return String(value || "").toLowerCase();
}

function formatTime(value) {
  if (!value) return "--:--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(11, 16) || "--:--";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

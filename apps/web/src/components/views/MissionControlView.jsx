"use client";

import { AlertTriangle, BarChart3, Briefcase, CheckCircle2, Code2, Eye, FileText, Lock, Pause, Search, Square } from "lucide-react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";

const PHASES = [
  ["intake", "Product Manager"],
  ["research", "Research Analyst"],
  ["architecture", "Senior Developer"],
  ["design", "UI/UX Designer"],
  ["design_preview_approval", "Project Manager"],
  ["implementation", "Junior Developer"],
  ["autonomous_qa", "QA Engineer"],
  ["documentation", "Brand & Content"],
  ["release_prep", "DevOps"],
  ["deployment_approval", "Project Manager"],
  ["deployment_runbook", "DevOps"],
  ["final_proof", "CEO / Friday"]
];

export function MissionControlView() {
  const { data, post, refresh, busy } = useDashboard();
  const missionStatus = data.missionStatus || {};
  const missions = Array.isArray(data.missions) ? data.missions : [];
  const activeMission = missions.find((mission) => ["running", "blocked", "paused"].includes(lower(mission.status))) || missionStatus.active?.[0] || missions[0] || null;

  async function approveDesignPreview(missionId) {
    if (!missionId) return;
    await post(`/missions/${missionId}/approve`, { kind: "design_preview", note: "Design preview approved from Mission Control." });
    await refresh();
  }

  return (
    <section className="friday-scroll h-full overflow-y-auto bg-friday-bg p-3 text-white" aria-label="Mission Control">
      <div className="grid max-w-[1000px] gap-5">
        <div className="grid grid-cols-[minmax(0,1fr)_320px] gap-5">
          <MissionDetail mission={activeMission} missionStatus={missionStatus} onApproveDesignPreview={approveDesignPreview} busy={busy} />
          <FinalProof mission={activeMission} missionStatus={missionStatus} />
        </div>
        <MissionRegistry missions={missions} />
      </div>
    </section>
  );
}

function MissionDetail({ mission, missionStatus, onApproveDesignPreview, busy }) {
  const phase = lower(mission?.current_phase || "intake");
  const blockers = blockerItems(mission, missionStatus);
  const designPreview = designPreviewState(mission, missionStatus);
  return (
    <article className="rounded border border-friday-line bg-gradient-to-b from-friday-panel to-[#0a0f14]">
      <header className="flex min-h-[68px] items-center gap-3 border-b border-friday-line px-4">
        <span className="shrink-0 border border-[#7d542b] bg-[#35210f] px-2 py-1 font-mono text-[11px] text-[#ffb76d]">{mission ? `M-${mission.id}` : "NO-MISSION"}</span>
        <div className="min-w-0">
          <h2 className="truncate text-[19px] font-extrabold">{mission?.goal || "No autonomous mission selected"}</h2>
          <p className="mt-1 truncate font-mono text-[12px] text-[#d9e4f0]">&gt; {mission?.summary || missionStatus.summary || "Start a mission from Chat or the Mission Control API."}</p>
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-2">
          <IconButton icon={<Pause size={13} />} disabled={!mission} />
          <IconButton icon={<Square size={12} />} disabled={!mission} />
          <a className={`grid min-h-10 place-items-center border px-5 text-[12px] ${mission ? "border-friday-blue bg-friday-blue text-[#061420]" : "border-friday-line bg-[#151b22] text-friday-muted"}`} href="/approvals">
            Approvals
          </a>
        </div>
      </header>

      <div className="grid min-h-[426px] grid-cols-[170px_minmax(0,1fr)]">
        <aside className="border-r border-friday-line p-4">
          <h3 className="mb-5 font-mono text-[11px] uppercase tracking-[.08em] text-[#dce7f4]">Phases</h3>
          <ol className="grid gap-3">
            {PHASES.map(([name]) => (
              <PhaseItem active={phase === name} done={phaseDone(name, phase)} key={name} name={name} />
            ))}
          </ol>
        </aside>

        <main className="grid grid-cols-2 gap-4 p-4">
          <AgentCard title={agentForPhase(phase)} subtitle="Current phase owner" icon={<Briefcase size={18} />} />
          <AgentCard title={mission?.deploy_policy || "approval gated"} subtitle="Deploy policy" icon={<Code2 size={18} />} color="blue" />
          <DesignPreviewCard mission={mission} preview={designPreview} onApprove={onApproveDesignPreview} busy={busy} />
          <EvidenceCard mission={mission} />
          <BlockerCard blockers={blockers} />
        </main>
      </div>
    </article>
  );
}

function PhaseItem({ name, active, done }) {
  return (
    <li className={`flex items-center gap-3 text-[12px] ${active ? "border border-[#35506b] bg-[#172437] px-3 py-2 font-semibold text-friday-accent" : "text-[#dce7f4]"}`}>
      <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${active ? "bg-friday-accent" : done ? "bg-[#ffb36d]" : "bg-[#4a5563]"}`} />
      <span className="truncate">{labelize(name)}</span>
    </li>
  );
}

function DesignPreviewCard({ mission, preview, onApprove, busy }) {
  const status = preview?.approved ? "approved" : preview?.pending ? "waiting" : preview?.required ? "preparing" : "not required";
  const previewText = preview?.preview || preview?.approval?.summary || "The UI/UX Designer has not posted a preview artifact yet.";
  return (
    <section className="col-span-2 grid min-h-[176px] grid-cols-[minmax(0,1fr)_150px] gap-4 overflow-hidden border border-[#315a4a] bg-[#0c1514] p-4">
      <div className="min-w-0">
        <CardHeader icon={<Eye size={13} />} label="Design Preview Gate" />
        <p className="mt-3 line-clamp-4 font-mono text-[12px] leading-relaxed text-[#eaf8f3]">&gt; {previewText}</p>
        <div className="mt-3 flex flex-wrap gap-2 font-mono text-[10px] uppercase tracking-[.08em]">
          <span className="border border-[#41685a] bg-[#10201c] px-2 py-1 text-[#9ff0c4]">{status}</span>
          <span className="border border-friday-line bg-[#111820] px-2 py-1 text-[#cbd7e6]">Before Implementation</span>
        </div>
      </div>
      <div className="grid content-center gap-2">
        <button
          className={`grid min-h-10 place-items-center border px-3 text-[12px] font-semibold disabled:opacity-45 ${preview?.pending ? "border-[#7edfae] bg-[#163126] text-[#a4f0c1]" : "border-friday-line bg-[#151b22] text-[#8f9bad]"}`}
          type="button"
          disabled={!preview?.pending || busy || !mission}
          onClick={() => onApprove?.(mission?.id)}
        >
          <span><CheckCircle2 className="mr-2 inline" size={13} />{preview?.approved ? "Approved" : "Approve"}</span>
        </button>
      </div>
    </section>
  );
}

function IconButton({ icon, disabled }) {
  return (
    <button className="grid h-10 w-10 place-items-center border border-friday-line bg-[#1b222c] text-[#d9e4f0] disabled:opacity-40" type="button" disabled={disabled}>
      {icon}
    </button>
  );
}

function AgentCard({ color, title, subtitle, icon }) {
  return (
    <div className="grid min-h-[76px] min-w-0 grid-cols-[42px_minmax(0,1fr)] items-center gap-3 border border-friday-line bg-[#171d24] px-4">
      <span className={`grid h-9 w-9 place-items-center ${color === "blue" ? "bg-[#102d4a] text-friday-accent" : "bg-[#421a4a] text-[#f1a2ff]"}`}>{icon}</span>
      <div className="min-w-0">
        <strong className="block truncate text-[13px]">{title}</strong>
        <span className="truncate text-[12px] text-[#d9e4f0]">{subtitle}</span>
      </div>
    </div>
  );
}

function EvidenceCard({ mission }) {
  const evidence = mission?.evidence || [];
  return (
    <section className="min-h-[228px] overflow-hidden border border-friday-line bg-[#080d11] p-4">
      <CardHeader icon={<FileText size={13} />} label={`Evidence (${mission?.evidence_count || evidence.length || 0})`} />
      <div className="mt-4 grid gap-3 font-mono text-[12px] leading-relaxed text-[#eef6ff]">
        {evidence.length ? evidence.slice(0, 4).map((item) => <p className="line-clamp-2" key={item.id}>&gt; {item.title}: {item.summary}</p>) : (
          <p className="text-friday-muted">&gt; No mission evidence loaded yet. Friday cannot mark a mission complete without proof.</p>
        )}
      </div>
    </section>
  );
}

function BlockerCard({ blockers }) {
  return (
    <section className="min-h-[228px] overflow-hidden border border-[#4b2030] bg-[#20121b] p-4">
      <CardHeader warning icon={<AlertTriangle size={13} />} label={`Blockers (${blockers.length})`} />
      <div className="mt-5 grid gap-3 font-mono text-[12px] leading-relaxed text-[#ffb6b6]">
        {blockers.length ? blockers.slice(0, 3).map((blocker) => <p className="line-clamp-3" key={blocker.id}>&gt; {blocker.title}: {blocker.summary}</p>) : (
          <p className="text-[#d7a6ac]">&gt; No open mission blockers.</p>
        )}
      </div>
    </section>
  );
}

function FinalProof({ mission, missionStatus }) {
  const pendingDeploy = (missionStatus.pending_approvals || []).find((item) => lower(item.kind) === "deploy" && (!mission || item.mission_id === mission.id));
  const pendingDesignPreview = designPreviewState(mission, missionStatus)?.pending;
  const blockers = blockerItems(mission, missionStatus);
  return (
    <aside className="grid rounded border border-[#6a4215] bg-gradient-to-b from-[#1c1711] to-[#080d11]">
      <header className="flex min-h-[54px] items-center gap-2 border-b border-[#6a4215] bg-[#2b2117] px-4 text-[#ffbf70]">
        <BarChart3 size={17} />
        <strong>Final Proof Preview</strong>
      </header>
      <div className="grid content-start gap-5 p-4">
        <ProofSection title="Mission State">
          <p>Status: {mission?.status || "none"}<br />Phase: {mission?.current_phase || "none"}<br />Authority: {mission?.authority_mode || "approval-gated"}</p>
        </ProofSection>
        <ProofSection title="What Is Verified">
          <div className="grid grid-cols-2 gap-2">
            <ProofPill label={`${mission?.progress_percent || 0}% progress`} />
            <ProofPill label={`${mission?.deploy_policy || "deploy approval"} policy`} />
            <ProofPill label={`${missionStatus.pending_approvals?.length || 0} approval(s)`} />
          </div>
        </ProofSection>
        <ProofSection title="Failures / Anomalies">
          <p>{blockers.length ? `${blockers.length} open blocker(s) must be resolved first.` : "No open blocker reported by mission control."}</p>
        </ProofSection>
        <ProofSection title="Remaining Risks" warning>
          <p>{pendingDesignPreview ? "Implementation is paused until the UI preview is approved." : pendingDeploy ? pendingDeploy.summary : "Friday still requires evidence and explicit approval before deploy/final completion."}</p>
        </ProofSection>
      </div>
      <footer className="mt-auto border-t border-friday-line p-4">
        <a className="grid min-h-10 w-full place-items-center border border-friday-line bg-[#151b22] text-[12px] text-[#8f9bad]" href="/approvals">
          <span><Lock className="mr-2 inline" size={13} />Approve / Review Gates</span>
        </a>
      </footer>
    </aside>
  );
}

function ProofSection({ title, warning, children }) {
  return (
    <section>
      <h3 className="mb-2 font-mono text-[11px] uppercase tracking-[.12em] text-[#e9edf4]">{title}</h3>
      <div className={`border p-3 font-mono text-[11px] leading-relaxed ${warning ? "border-[#7d542b] bg-[#34230f] text-[#ffbf70]" : "border-friday-line bg-[#111820] text-[#e6edf7]"}`}>{children}</div>
    </section>
  );
}

function ProofPill({ label }) {
  return <span className="truncate border border-friday-line bg-[#111820] px-2 py-2 font-mono text-[11px] text-[#e6edf7]">{label}</span>;
}

function MissionRegistry({ missions }) {
  return (
    <section className="rounded border border-friday-line bg-gradient-to-b from-friday-panel to-[#0a0f14]">
      <header className="flex min-h-[54px] items-center border-b border-friday-line px-4">
        <h2 className="text-[17px] font-extrabold">Active Missions Registry</h2>
        <label className="ml-auto flex h-8 w-[255px] items-center gap-2 border border-friday-line bg-[#111820] px-3 font-mono text-[11px] text-[#7f8da0]">
          <Search size={13} />
          Filter &gt;
        </label>
      </header>
      {missions.length ? (
        <table className="w-full border-collapse text-left font-mono text-[11px]">
          <thead className="text-[#c9d5e4]">
            <tr className="border-b border-friday-line">
              {["Goal", "Status", "Phase", "Progress", "Risk", "Evid.", "Blockers", "Root"].map((heading) => (
                <th className="px-4 py-3 uppercase tracking-[.12em]" key={heading}>{heading}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {missions.map((mission, index) => <RegistryRow key={mission.id || `${index}-${mission.goal}`} mission={mission} selected={index === 0} />)}
          </tbody>
        </table>
      ) : (
        <div className="grid min-h-[150px] place-items-center px-4 text-center text-[13px] text-friday-muted">
          No mission records loaded. Use Chat: "start mission ..." or POST /missions to create one.
        </div>
      )}
    </section>
  );
}

function RegistryRow({ mission, selected }) {
  return (
    <tr className={`border-b border-friday-line last:border-b-0 ${selected ? "border-l-2 border-l-friday-accent bg-[#121a24]" : "bg-[#0a0f14]"}`}>
      <td className="max-w-[220px] truncate px-4 py-4 font-semibold">{mission.goal || `Mission #${mission.id}`}</td>
      <td className="px-4 py-4"><Badge label={mission.status || "unknown"} /></td>
      <td className="px-4 py-4">{mission.current_phase || "n/a"}</td>
      <td className="px-4 py-4"><MiniProgress value={mission.progress_percent || 0} /></td>
      <td className="px-4 py-4"><RiskBadge label={riskFromMission(mission)} /></td>
      <td className="px-4 py-4">{mission.evidence_count || 0}</td>
      <td className="px-4 py-4 text-[#ffaaa0]">{mission.blocker_count || 0}</td>
      <td className="max-w-[120px] truncate px-4 py-4 text-right">{mission.root || "-"}</td>
    </tr>
  );
}

function MiniProgress({ value }) {
  return <div className="h-1.5 w-[82px] overflow-hidden bg-[#333d49]"><span className="block h-full bg-[#97c8f8]" style={{ width: `${Math.max(0, Math.min(100, Number(value) || 0))}%` }} /></div>;
}

function Badge({ label }) {
  return <span className="border border-[#415169] bg-[#172235] px-2 py-1 text-[10px] text-friday-accent">{label}</span>;
}

function RiskBadge({ label }) {
  const value = lower(label);
  const low = value === "low";
  const medium = value === "medium";
  return <span className={`border px-2 py-1 text-[10px] ${low ? "border-[#31506d] bg-[#102031] text-friday-accent" : medium ? "border-[#675022] bg-[#2b2112] text-[#ffbf70]" : "border-[#5b2930] bg-[#281319] text-[#ff9fa7]"}`}>{label}</span>;
}

function CardHeader({ icon, label, warning }) {
  return (
    <div className={`flex items-center gap-2 text-[12px] font-extrabold ${warning ? "text-[#ffb6b6]" : "text-[#e6edf7]"}`}>
      {icon}
      {label}
    </div>
  );
}

function blockerItems(mission, missionStatus) {
  const all = mission?.blockers || missionStatus.open_blockers || [];
  return mission ? all.filter((item) => !item.mission_id || item.mission_id === mission.id) : all;
}

function designPreviewState(mission, missionStatus) {
  const base = mission?.design_preview || {};
  const pendingApproval = (missionStatus.pending_approvals || []).find((item) => lower(item.kind) === "design_preview" && (!mission || item.mission_id === mission.id));
  const approval = base.approval || pendingApproval || null;
  const payload = approval?.payload || {};
  const status = lower(base.status || approval?.status);
  return {
    ...base,
    approval,
    required: Boolean(base.required || pendingApproval),
    pending: Boolean(base.pending || pendingApproval || status === "pending"),
    approved: Boolean(base.approved || status === "approved"),
    preview: base.preview || payload.preview || approval?.summary || ""
  };
}

function phaseDone(name, current) {
  const currentIndex = PHASES.findIndex(([phase]) => phase === current);
  const index = PHASES.findIndex(([phase]) => phase === name);
  return currentIndex > index;
}

function agentForPhase(phase) {
  return PHASES.find(([name]) => name === phase)?.[1] || "Mission Control";
}

function labelize(value) {
  return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function riskFromMission(mission) {
  if (lower(mission.deploy_policy).includes("approve")) return "medium";
  if (lower(mission.status) === "blocked") return "high";
  return "low";
}

function lower(value) {
  return String(value || "").toLowerCase();
}

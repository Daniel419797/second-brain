"use client";

import { CheckSquare, Filter, Loader2, MoreHorizontal, Plus, ShieldAlert, X } from "lucide-react";
import { useState } from "react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";

const LANES = [
  { id: "pending", label: "Pending", statuses: ["pending", "scheduled", "blocked"] },
  { id: "active", label: "Active", statuses: ["active", "running", "in_progress", "in progress"] },
  { id: "completed", label: "Completed", statuses: ["done", "completed", "failed", "cancelled"] }
];

export function TasksView() {
  const { api, data, post, refresh, interfaceFor } = useDashboard();
  const copy = interfaceFor?.("tasks") || {};
  const [laneFilter, setLaneFilter] = useState("all");
  const [priorityFilter, setPriorityFilter] = useState("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [createBusy, setCreateBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailBusy, setDetailBusy] = useState(false);
  const tasks = filterTasks(data.tasks || [], laneFilter, priorityFilter);

  async function openTask(task) {
    setSelected(task);
    setDetail(task);
    if (!api || !task?.id) return;
    setDetailBusy(true);
    try {
      setDetail(await api(`/tasks/${task.id}`));
    } catch {
      setDetail(task);
    } finally {
      setDetailBusy(false);
    }
  }

  async function cancelTask(task) {
    if (!task?.id) return;
    await post(`/tasks/${task.id}/cancel`);
    setSelected(null);
    setDetail(null);
  }

  async function createTask(values) {
    setCreateBusy(true);
    setStatus("");
    try {
      await api("/tasks", {
        method: "POST",
        body: JSON.stringify(values)
      });
      setCreateOpen(false);
      setStatus(copy?.primaryAction?.label ? `${copy.primaryAction.label}: queued.` : "Task queued.");
      await refresh();
    } catch (err) {
      setStatus(err.message || "Task could not be created.");
    } finally {
      setCreateBusy(false);
    }
  }

  function cycleLaneFilter() {
    const next = { all: "pending", pending: "active", active: "completed", completed: "all" };
    setLaneFilter(next[laneFilter] || "all");
  }

  function cyclePriorityFilter() {
    const next = { all: "high", high: "medium", medium: "low", low: "all" };
    setPriorityFilter(next[priorityFilter] || "all");
  }

  return (
    <section className="friday-scroll h-full overflow-y-auto overflow-x-hidden bg-friday-bg p-3 text-white" aria-label="Active Operations">
      <div className="grid max-w-[1000px] gap-4">
        <header className="flex min-h-10 items-center gap-2">
          <h1 className="mr-3 text-[18px] font-extrabold">{copy?.title || "Active Operations"}</h1>
          <button className="inline-flex min-h-7 items-center gap-2 border border-friday-line bg-[#151b22] px-3 font-mono text-[11px] text-[#cfd9e6] hover:border-friday-accent" type="button" onClick={cycleLaneFilter} title="Cycle task lane filter">
            <Filter size={12} />
            {laneFilter === "all" ? "All Lanes" : labelize(laneFilter)}
          </button>
          <button className="inline-flex min-h-7 items-center gap-2 border border-friday-line bg-[#151b22] px-3 font-mono text-[11px] text-[#cfd9e6] hover:border-friday-accent" type="button" onClick={cyclePriorityFilter} title="Cycle priority filter">
            <ShieldAlert size={12} />
            {priorityFilter === "all" ? "All Priority" : labelize(priorityFilter)}
          </button>
          <button className="inline-flex min-h-7 items-center gap-2 border border-friday-blue bg-friday-blue px-3 font-mono text-[11px] font-bold text-[#061420]" type="button" onClick={() => setCreateOpen(true)}>
            <Plus size={12} />
            {copy?.actions?.find?.((action) => action.id === "create-task")?.label || "New Task"}
          </button>
          <span className="ml-auto font-mono text-[11px] text-friday-muted">{tasks.length} task(s)</span>
        </header>
        {status ? <div className="border border-[#405063] bg-[#101820] px-3 py-2 text-[12px] text-[#dce9f8]">{status}</div> : null}

        <div className="grid min-w-0 grid-cols-3 gap-4">
          {LANES.map((lane) => (
            <TaskLane lane={lane} tasks={tasksForLane(tasks, lane)} copy={copy} key={lane.id} onOpen={openTask} />
          ))}
        </div>
      </div>

      {selected ? (
        <TaskDetailModal
          task={detail || selected}
          copy={copy}
          busy={detailBusy}
          onClose={() => {
            setSelected(null);
            setDetail(null);
          }}
          onCancel={() => cancelTask(detail || selected)}
        />
      ) : null}
      {createOpen ? (
        <TaskCreateModal
          agents={data.agents || []}
          copy={copy}
          busy={createBusy}
          onClose={() => setCreateOpen(false)}
          onCreate={createTask}
        />
      ) : null}
    </section>
  );
}

function TaskLane({ lane, tasks, copy, onOpen }) {
  return (
    <section className="min-w-0">
      <div className="mb-3 flex items-center gap-2 border-b border-friday-line pb-2">
        <span className={`h-1.5 w-1.5 rounded-full ${lane.id === "active" ? "bg-friday-accent" : lane.id === "completed" ? "bg-friday-ok" : "bg-[#6b7480]"}`} />
        <h2 className="font-mono text-[12px] font-bold uppercase tracking-[.08em] text-[#dce7f4]">{lane.label}</h2>
        <span className="rounded bg-[#303946] px-2 py-0.5 font-mono text-[10px]">{tasks.length}</span>
        <MoreHorizontal className="ml-auto text-friday-muted" size={15} />
      </div>
      <div className="grid gap-3">
        {tasks.length ? tasks.slice(0, 8).map((task, index) => <TaskCard task={task} key={task.id || `${lane.id}-${index}-${task.title}`} onOpen={() => onOpen(task)} />) : (
          <div className="grid min-h-[88px] place-items-center border border-friday-line bg-[#10161d] px-3 text-center text-[12px] text-friday-muted">
            {copy?.empty?.tasks || `Friday has no ${lane.label.toLowerCase()} task in this lane.`}
          </div>
        )}
      </div>
    </section>
  );
}

function TaskCard({ task, onOpen }) {
  const contract = task.contract || {};
  const priority = priorityLabel(task.priority);
  const progress = Math.max(0, Math.min(100, Number(task.progress_percent || 0)));
  return (
    <button className="grid min-h-[116px] min-w-0 gap-3 border border-friday-line bg-gradient-to-b from-[#171d25] to-[#10161d] p-3 text-left transition-colors hover:border-friday-accent" type="button" onClick={onOpen}>
      <div className="flex min-w-0 items-start gap-2">
        <PriorityBadge label={priority} />
        <span className="ml-auto shrink-0 font-mono text-[10px] text-friday-muted">#{task.id}</span>
      </div>
      <div className="min-w-0">
        <h3 className="line-clamp-2 text-[13px] font-extrabold leading-snug">{task.title || "Friday task"}</h3>
        <p className="mt-1 truncate text-[11px] text-friday-muted">{contract.risk_level ? `${contract.risk_level} risk` : task.description || "No description"}</p>
      </div>
      <div>
        <div className="mb-1 h-1.5 overflow-hidden bg-[#303946]">
          <span className="block h-full bg-friday-accent" style={{ width: `${progress}%` }} />
        </div>
        <div className="flex items-center gap-2 font-mono text-[10px] text-[#cbd7e6]">
          <span className="truncate">{task.agent_id || "unassigned"}</span>
          <span className="ml-auto shrink-0">{task.status || "unknown"}</span>
        </div>
      </div>
    </button>
  );
}

function TaskDetailModal({ task, copy, busy, onClose, onCancel }) {
  const contract = task.contract || {};
  const output = normalizeOutput(task.output);
  const outputData = task.output && typeof task.output === "object" ? task.output : {};
  const metadata = outputData.metadata || {};
  const workflow = metadata.workflow || {};
  const inspection = metadata.project_inspection || workflow.inspection || {};
  const executionPlan = metadata.execution_plan || workflow.execution_plan || {};
  const productStudio = metadata.product_studio || workflow.product_studio || {};
  const studioGates = metadata.product_studio_gates || workflow.product_studio_gates || productStudio.gate_results || {};
  const studioReport = productStudio.final_proof_report || {};
  const studioPhases = asArray(productStudio.phases);
  const gateItems = asArray(studioGates.gates || studioGates.required_gate_statuses);
  const studioGaps = asArray(studioReport.critical_gaps?.length ? studioReport.critical_gaps : productStudio.gaps || studioReport.gaps);
  const boundaries = asArray(metadata.responsibility_boundaries || workflow.responsibility_boundaries);
  const verification = metadata.scaffold_verification || metadata.artifact_verification || workflow.verification || {};
  const executionFlow = asArray(executionPlan.flow);
  const changedFiles = asArray(outputData.changed);
  const checkItems = [...asArray(outputData.tested), ...asArray(outputData.failed).map((item) => `gap: ${item}`)];
  const codingEvidenceVisible = outputData.mode === "autonomous_coding" || metadata.project_root || executionFlow.length || boundaries.length || verification.status;
  const studioVisible = studioPhases.length || studioReport.next_step || studioGaps.length || gateItems.length;
  const messages = task.messages || [];
  const canCancel = !["done", "completed", "cancelled", "failed"].includes(lower(task.status));
  return (
    <div className="fixed inset-0 z-50 grid justify-end bg-black/45 p-3" role="dialog" aria-modal="true" aria-label="Task details">
      <aside className="friday-scroll grid h-full w-[386px] max-w-[calc(100dvw-24px)] grid-rows-[auto_minmax(0,1fr)_auto] overflow-y-auto border border-[#334154] bg-[#111821] shadow-2xl">
        <header className="border-b border-friday-line p-4">
          <div className="mb-3 flex items-start gap-2">
            <PriorityBadge label={priorityLabel(task.priority)} />
            <StatusBadge label={task.status || "unknown"} />
            <button className="ml-auto text-[#d6e1ee]" type="button" onClick={onClose} aria-label="Close task details">
              <X size={18} />
            </button>
          </div>
          <h2 className="text-[18px] font-extrabold leading-tight">{task.title || "Friday task"}</h2>
          <p className="mt-2 font-mono text-[11px] text-friday-muted">ID: {task.id || "n/a"} / Updated: {formatTime(task.updated_at)}</p>
        </header>

        <div className="grid content-start gap-4 p-4">
          <div className="grid grid-cols-2 gap-3">
            <InfoBox label="Assigned Agent" value={task.agent_id || "unassigned"} />
            <InfoBox label="Risk Level" value={contract.risk_level || "not assessed"} warn={["high", "medium"].includes(lower(contract.risk_level))} />
          </div>

          <DetailSection title="Goal Alignment">
            <p>{contract.goal || task.description || copy?.empty?.tasks || "Friday has no goal text attached to this task yet."}</p>
          </DetailSection>

          <DetailSection title="Expected Output">
            <CodeBlock value={contract.expected_output || copy?.empty?.evidence || "Friday has no expected-output contract attached yet."} />
          </DetailSection>

          <DetailSection title="Actual Output / Evidence">
            <p>{output || copy?.empty?.evidence || "Friday has no task output recorded yet."}</p>
          </DetailSection>

          {codingEvidenceVisible ? (
            <DetailSection title="Autonomous Coding Evidence">
              <div className="grid gap-3">
                <InfoBox label="Project Root" value={metadata.project_root || metadata.root || "not reported"} />
                <InfoBox label="Verification" value={verification.status || outputData.contract?.status || "not verified"} warn={lower(verification.status || outputData.contract?.status) !== "passed" && lower(outputData.contract?.status) !== "verified"} />
                <p className="text-friday-muted">{inspection.summary || "No project inspection summary was recorded."}</p>
                <ChipList items={executionFlow} empty="No execution flow recorded" />
                <BoundaryList items={boundaries} />
              </div>
            </DetailSection>
          ) : null}

          {studioVisible ? (
            <DetailSection title="Product Studio">
              <div className="grid gap-3">
                <div className="grid grid-cols-2 gap-3">
                  <InfoBox label="Readiness" value={readinessLabel(studioReport, studioGates)} warn={!studioReport.market_ready} />
                  <InfoBox label="Market Ready" value={studioReport.market_ready ? "yes" : "not yet"} warn={!studioReport.market_ready} />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <InfoBox label="Technical Gates" value={studioGates.technical_ready ? "passed" : studioGates.status || studioReport.gate_status || "not ready"} warn={!studioGates.technical_ready} />
                  <InfoBox label="Phase Count" value={`${studioPhases.length || 0} phases`} />
                </div>
                <p className="text-friday-muted">{productStudio.summary || studioReport.next_step || "Product-studio proof is attached."}</p>
                <GateList gates={gateItems} previewUrl={studioGates.preview_url} />
                <PhaseList phases={studioPhases} />
                <ChipList items={studioGaps.slice(0, 8)} empty="No critical gaps recorded" />
              </div>
            </DetailSection>
          ) : null}

          {codingEvidenceVisible ? (
            <div className="grid grid-cols-2 gap-3">
              <DetailSection title="Changed Files">
                <ChipList items={changedFiles} empty="No changed files reported" />
              </DetailSection>
              <DetailSection title="Checks / Limits">
                <ChipList items={checkItems} empty="No checks reported" />
              </DetailSection>
            </div>
          ) : null}

          <DetailSection title="Success Criteria">
            <Checklist items={contract.success_criteria || []} satisfied={contract.status === "verified" || contract.satisfied} />
          </DetailSection>

          <div className="grid grid-cols-2 gap-3">
            <DetailSection title="Tools Provisioned">
              <ChipList items={contract.tools_needed || []} empty="No tools listed" />
            </DetailSection>
            <DetailSection title="Verification">
              <ChipList items={[contract.status || "no contract", contract.verification_method || "no method"]} />
            </DetailSection>
          </div>

          <DetailSection title="Execution Log">
            <div className="border border-friday-line bg-[#070c11]">
              {busy ? <LogLine text="Loading task detail..." /> : null}
              {messages.length ? messages.slice(-5).map((message) => <LogLine text={`${message.sender || "system"}: ${message.message || ""}`} key={message.id || message.timestamp} />) : (
                <>
                  <LogLine text={`Task created: ${formatTime(task.created_at)}`} />
                  <LogLine text={`Current status: ${task.status || "unknown"}`} />
                  <LogLine text={`Last update: ${formatTime(task.updated_at)}`} />
                </>
              )}
            </div>
          </DetailSection>
        </div>

        <footer className="grid grid-cols-2 gap-3 border-t border-friday-line p-4">
          <button className="min-h-10 border border-[#c47a6d] bg-[#1b1114] font-mono text-[12px] text-[#ffaaa0] disabled:opacity-40" type="button" disabled={!canCancel} onClick={onCancel}>
            Halt Execution
          </button>
          <a className="grid min-h-10 place-items-center border border-friday-blue bg-friday-blue font-mono text-[12px] text-[#061420]" href="/chat">
            Intervene
          </a>
        </footer>
      </aside>
    </div>
  );
}

function TaskCreateModal({ agents, copy, busy, onClose, onCreate }) {
  const [form, setForm] = useState({ title: "", description: "", agent_id: "", priority: 5, scheduled_at: "" });
  function update(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }
  function submit(event) {
    event.preventDefault();
    if (!form.title.trim()) return;
    onCreate({ ...form, priority: Number(form.priority || 5) });
  }
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/55 p-4" role="dialog" aria-modal="true" aria-label="Create task">
      <form className="grid w-[420px] max-w-[calc(100dvw-32px)] gap-4 border border-[#334154] bg-[#111821] p-4 shadow-2xl" onSubmit={submit}>
        <header className="flex items-center gap-3 border-b border-friday-line pb-3">
          <h2 className="text-[18px] font-extrabold">{copy?.actions?.find?.((action) => action.id === "create-task")?.label || "Queue New Task"}</h2>
          <button className="ml-auto text-[#d6e1ee]" type="button" onClick={onClose} aria-label="Close task form">
            <X size={18} />
          </button>
        </header>
        <label className="grid gap-1">
          <span className="font-mono text-[10px] uppercase text-friday-muted">Title</span>
          <input className="min-h-10 border border-friday-line bg-[#0c1218] px-3 text-[13px] text-white outline-none focus:border-friday-accent" value={form.title} onChange={(event) => update("title", event.target.value)} maxLength={500} required />
        </label>
        <label className="grid gap-1">
          <span className="font-mono text-[10px] uppercase text-friday-muted">Description</span>
          <textarea className="min-h-[88px] resize-y border border-friday-line bg-[#0c1218] px-3 py-2 text-[13px] text-white outline-none focus:border-friday-accent" value={form.description} onChange={(event) => update("description", event.target.value)} />
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="grid gap-1">
            <span className="font-mono text-[10px] uppercase text-friday-muted">Agent</span>
            <select className="min-h-10 border border-friday-line bg-[#0c1218] px-3 text-[13px] text-white outline-none focus:border-friday-accent" value={form.agent_id} onChange={(event) => update("agent_id", event.target.value)}>
              <option value="">Unassigned</option>
              {agents.map((agent) => <option value={agent.id || agent.agent_id} key={agent.id || agent.agent_id}>{agent.name || agent.agent_name || agent.id}</option>)}
            </select>
          </label>
          <label className="grid gap-1">
            <span className="font-mono text-[10px] uppercase text-friday-muted">Priority</span>
            <input className="min-h-10 border border-friday-line bg-[#0c1218] px-3 text-[13px] text-white outline-none focus:border-friday-accent" type="number" min="0" max="20" value={form.priority} onChange={(event) => update("priority", event.target.value)} />
          </label>
        </div>
        <footer className="grid grid-cols-2 gap-3 border-t border-friday-line pt-3">
          <button className="min-h-10 border border-friday-line bg-[#151b22] font-mono text-[12px] text-[#dfe9f6]" type="button" onClick={onClose}>Cancel</button>
          <button className="inline-flex min-h-10 items-center justify-center gap-2 border border-friday-blue bg-friday-blue font-mono text-[12px] font-bold text-[#061420] disabled:opacity-50" type="submit" disabled={busy || !form.title.trim()}>
            {busy ? <Loader2 className="animate-spin" size={14} /> : <Plus size={14} />}
            Create
          </button>
        </footer>
      </form>
    </div>
  );
}

function DetailSection({ title, children }) {
  return (
    <section>
      <h3 className="mb-2 font-mono text-[11px] font-bold uppercase tracking-[.12em] text-[#cbd7e6]">{title}</h3>
      <div className="text-[12px] leading-relaxed text-[#e6edf7]">{children}</div>
    </section>
  );
}

function InfoBox({ label, value, warn }) {
  return (
    <div className="min-w-0 border border-friday-line bg-[#151b22] p-3">
      <span className="block font-mono text-[10px] uppercase tracking-[.08em] text-friday-muted">{label}</span>
      <strong className={`mt-2 block truncate text-[12px] ${warn ? "text-[#ffb56d]" : "text-friday-accent"}`}>{value}</strong>
    </div>
  );
}

function CodeBlock({ value }) {
  return <pre className="max-h-[108px] overflow-auto border border-friday-line bg-[#070c11] p-3 font-mono text-[11px] text-[#e6edf7]">{stringify(value)}</pre>;
}

function Checklist({ items, satisfied }) {
  if (!items.length) return <p className="text-friday-muted">No success criteria listed.</p>;
  return (
    <div className="grid gap-2">
      {items.map((item, index) => (
        <label className="flex items-start gap-2 font-mono text-[11px]" key={`${index}-${item}`}>
          <span className={`mt-0.5 grid h-3.5 w-3.5 shrink-0 place-items-center border ${satisfied ? "border-friday-accent bg-friday-accent text-[#061420]" : "border-friday-line bg-[#10161d]"}`}>
            {satisfied ? <CheckSquare size={10} /> : null}
          </span>
          <span>{item}</span>
        </label>
      ))}
    </div>
  );
}

function ChipList({ items, empty }) {
  const rows = items.filter(Boolean);
  return (
    <div className="flex flex-wrap gap-2">
      {rows.length ? rows.map((item, index) => <span className="max-w-full truncate border border-friday-line bg-[#151b22] px-2 py-1 font-mono text-[10px]" key={`${index}-${item}`}>{item}</span>) : <span className="text-friday-muted">{empty}</span>}
    </div>
  );
}

function BoundaryList({ items }) {
  if (!items.length) return <p className="text-friday-muted">No responsibility boundaries recorded.</p>;
  return (
    <div className="grid gap-2">
      {items.slice(0, 6).map((item, index) => (
        <div className="border border-friday-line bg-[#0c1218] p-2 font-mono text-[10px]" key={`${index}-${item.owner || item.area}`}>
          <strong className="block text-[#dce7f4]">{item.owner || item.area || "scope"}</strong>
          <span className="text-friday-muted">{item.rule || item.area || stringify(item)}</span>
        </div>
      ))}
    </div>
  );
}

function PhaseList({ phases }) {
  if (!phases.length) return <p className="text-friday-muted">No product-studio phases recorded.</p>;
  return (
    <div className="grid gap-2">
      {phases.slice(0, 8).map((phase, index) => (
        <div className="grid grid-cols-[1fr_auto] gap-2 border border-friday-line bg-[#0c1218] p-2 font-mono text-[10px]" key={`${index}-${phase.id || phase.label}`}>
          <span className="truncate text-[#dce7f4]">{phase.label || phase.id || "phase"}</span>
          <span className={phase.status === "verified" ? "text-friday-accent" : phase.status === "blocked" ? "text-[#ffaaa0]" : "text-[#ffb56d]"}>{phase.status || "planned"}</span>
        </div>
      ))}
    </div>
  );
}

function GateList({ gates, previewUrl }) {
  if (!gates.length && !previewUrl) return <p className="text-friday-muted">No executable gate evidence recorded.</p>;
  const screenshot = gates.find((gate) => gate?.screenshot)?.screenshot;
  return (
    <div className="grid gap-2 border border-friday-line bg-[#070c11] p-2">
      {previewUrl ? <p className="truncate font-mono text-[10px] text-friday-accent">Preview: {previewUrl}</p> : null}
      {screenshot ? <p className="truncate font-mono text-[10px] text-[#dce7f4]">Screenshot: {screenshot}</p> : null}
      {gates.slice(0, 8).map((gate, index) => (
        <div className="grid grid-cols-[1fr_auto] gap-2 border border-[#202b37] bg-[#0c1218] p-2 font-mono text-[10px]" key={`${index}-${gate.id || gate.label}`}>
          <span className="truncate text-[#dce7f4]">{gate.label || gate.id || "gate"}</span>
          <span className={gate.status === "passed" ? "text-friday-accent" : gate.status === "failed" || gate.status === "blocked" || gate.status === "timeout" ? "text-[#ffaaa0]" : "text-[#ffb56d]"}>{gate.status || "unknown"}</span>
          <span className="col-span-2 line-clamp-2 text-friday-muted">{gate.command || gate.summary || "No command recorded"}</span>
        </div>
      ))}
    </div>
  );
}

function LogLine({ text }) {
  return <p className="border-b border-friday-line px-3 py-2 font-mono text-[11px] text-[#dce6f2] last:border-b-0">[{new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}] {text}</p>;
}

function PriorityBadge({ label }) {
  const high = lower(label).includes("high");
  const medium = lower(label).includes("medium");
  return <span className={`shrink-0 border px-2 py-1 font-mono text-[10px] uppercase ${high ? "border-[#59323c] bg-[#28171d] text-[#ff9fa7]" : medium ? "border-[#6a4215] bg-[#2a2115] text-[#ffb56d]" : "border-[#415169] bg-[#172235] text-friday-accent"}`}>{label}</span>;
}

function StatusBadge({ label }) {
  return <span className="shrink-0 border border-[#31587f] bg-[#122033] px-2 py-1 font-mono text-[10px] uppercase text-friday-accent">{label}</span>;
}

function tasksForLane(tasks, lane) {
  return tasks.filter((task) => lane.statuses.includes(lower(task.status)));
}

function filterTasks(tasks, laneFilter, priorityFilter) {
  return tasks.filter((task) => {
    const laneMatch = laneFilter === "all" || LANES.find((lane) => lane.id === laneFilter)?.statuses.includes(lower(task.status));
    const priority = priorityLabel(task.priority);
    const priorityMatch = priorityFilter === "all" || lower(priority).includes(priorityFilter);
    return laneMatch && priorityMatch;
  });
}

function priorityLabel(value) {
  const number = Number(value || 5);
  if (number <= 2) return "high priority";
  if (number <= 5) return "medium";
  return "low";
}

function normalizeOutput(output) {
  if (!output) return "";
  if (typeof output === "string") return output;
  return output.summary || output.result || output.message || stringify(output);
}

function stringify(value) {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value || "");
  }
}

function formatTime(value) {
  if (!value) return "n/a";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString([], { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function lower(value) {
  return String(value || "").toLowerCase();
}

function labelize(value) {
  return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function readinessLabel(report, gates) {
  if (report?.market_ready) return "Market ready";
  if (report?.technical_ready || gates?.technical_ready) return "Market blocked";
  if (gates?.status === "attention" || gates?.status === "failed") return "Gates blocked";
  if (gates?.attempted) return "Gates running";
  return "Not built";
}

function asArray(value) {
  if (Array.isArray(value)) return value;
  if (value) return [value];
  return [];
}

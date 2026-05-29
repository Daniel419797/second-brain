"use client";

import {
  AlertTriangle,
  Ban,
  Check,
  CheckCircle2,
  Database,
  Filter,
  Lock,
  Server,
  ShieldAlert,
  X
} from "lucide-react";
import { useMemo, useState } from "react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";

const FILTERS = [
  { id: "all", label: "All Pending" },
  { id: "risky_action", label: "Risky Action" },
  { id: "private_data", label: "Private Data" },
  { id: "deploy_approval", label: "Deploy Approval" },
  { id: "agent_question", label: "Agent Question" },
  { id: "self_update", label: "Self-Update" }
];

export function ApprovalsView({ approvals, summary }) {
  const { api, busy, refresh, interfaceFor } = useDashboard();
  const copy = interfaceFor?.("approvals") || {};
  const [filter, setFilter] = useState("all");
  const [pendingKey, setPendingKey] = useState("");
  const [actionStatus, setActionStatus] = useState("");
  const [evidenceItem, setEvidenceItem] = useState(null);
  const rows = useMemo(() => normalizeApprovals(approvals, summary), [approvals, summary]);
  const filtered = useMemo(() => rows.filter((item) => filter === "all" || item.category === filter), [filter, rows]);
  const urgentCount = rows.filter((item) => item.risk === "high").length;
  const standardCount = Math.max(0, rows.length - urgentCount);

  async function decide(item, decision) {
    const key = `${item.kind}-${item.id}-${decision}`;
    setPendingKey(key);
    setActionStatus("");
    try {
      if (decision === "allow" && item.kind === "mission_approval" && item.metadata?.mission_approval?.mission_id) {
        const approval = item.metadata?.mission_approval || {};
        await api(`/missions/${approval.mission_id}/approve`, {
          method: "POST",
          body: JSON.stringify({
            kind: approval.kind || "next_step",
            note: "Approved from the Decision Inbox."
          })
        });
      } else {
        const result = await api(`/approvals/${encodeURIComponent(item.kind)}/${item.id}/resolve`, {
          method: "POST",
          body: JSON.stringify({ note: `${decisionLabel(decision)} from the Decision Inbox.` })
        });
        if (result?.resolved === false) {
          setActionStatus("That approval type needs its source workflow to finish the decision.");
        }
      }
      await refresh();
    } catch (err) {
      setActionStatus(err.message || "Could not update this approval.");
    } finally {
      setPendingKey("");
    }
  }

  return (
    <section className="friday-scroll h-full overflow-y-auto overflow-x-hidden bg-friday-bg px-6 py-7 text-[#eaf2fb]" aria-label="Decision Inbox">
      <div className="mx-auto grid w-full max-w-[1240px] gap-6">
        <header className="flex min-w-0 flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-[28px] font-extrabold leading-none text-white">{copy?.title || "Decision Inbox"}</h1>
            <p className="mt-2 text-[13px] text-friday-muted">{copy?.subtitle || "Human authorization queue for risky actions, private data, deploys, and agent questions."}</p>
          </div>
          <a className="inline-flex min-h-9 items-center gap-2 rounded-[6px] border border-friday-line bg-[#151b22] px-4 text-[13px] font-semibold text-[#dce8f7] hover:border-friday-accent" href="/safety">
            <Filter size={15} />
            Review Policy
          </a>
        </header>

        <DecisionSummary count={rows.length} urgentCount={urgentCount} standardCount={standardCount} copy={copy} />

        <div className="flex min-w-0 flex-wrap gap-2">
          {FILTERS.map((item) => {
            const count = item.id === "all" ? rows.length : rows.filter((row) => row.category === item.id).length;
            const active = filter === item.id;
            return (
              <button
                className={`min-h-9 rounded-[999px] border px-4 text-[13px] font-bold tracking-[.04em] transition-colors ${
                  active ? "border-friday-accent bg-[#17263a] text-friday-accent" : "border-[#3d4857] bg-[#151b22] text-[#d6dfeb] hover:border-friday-accent"
                }`}
                type="button"
                onClick={() => setFilter(item.id)}
                key={item.id}
              >
                {item.label}{item.id === "all" ? ` (${count})` : count ? ` (${count})` : ""}
              </button>
            );
          })}
        </div>

        {actionStatus ? <div className="rounded-[4px] border border-[#7a5638] bg-[#2b2118] px-4 py-3 text-[13px] text-[#ffbf7b]">{actionStatus}</div> : null}

        <div className="grid gap-4">
          {filtered.length ? filtered.map((item) => (
            <ApprovalCard
              item={item}
              busy={busy || Boolean(pendingKey)}
              pendingKey={pendingKey}
              onDecision={decide}
              onEvidence={setEvidenceItem}
              key={`${item.kind}-${item.id}`}
            />
          )) : (
            <EmptyApprovals rows={rows} filter={filter} copy={copy} />
          )}
        </div>
        {evidenceItem ? <EvidenceModal item={evidenceItem} onClose={() => setEvidenceItem(null)} /> : null}
      </div>
    </section>
  );
}

function DecisionSummary({ count, urgentCount, standardCount, copy }) {
  return (
    <section className="grid min-h-[92px] grid-cols-[48px_minmax(0,1fr)_auto] items-center gap-4 rounded-[8px] border border-friday-line bg-[#1a2028] px-5 py-4">
      <span className={`grid h-12 w-12 place-items-center rounded-[8px] border ${count ? "border-[#79434b] bg-[#3a1f27] text-[#ffb5b8]" : "border-[#315c48] bg-[#163126] text-[#90efc9]"}`}>
        {count ? <AlertTriangle size={23} /> : <CheckCircle2 size={23} />}
      </span>
      <div className="min-w-0">
        <h2 className="truncate text-[22px] font-extrabold leading-tight text-white">
          {count ? `Friday has ${count} decision${count === 1 ? "" : "s"} waiting` : copy?.empty?.approvals || "Friday has no decision gate waiting"}
        </h2>
        <p className="mt-1 truncate text-[14px] text-[#d8e2ee]">
          {count ? "Friday execution is paused pending human authorization." : copy?.empty?.approvals || "Friday has no approval-gated work paused right now."}
        </p>
      </div>
      <div className="hidden items-center gap-4 font-mono text-[12px] uppercase md:flex">
        <SummaryCount value={urgentCount} label="Urgent (High Risk)" tone="danger" />
        <span className="h-10 w-px bg-friday-line" />
        <SummaryCount value={standardCount} label="Standard Review" tone="warn" />
      </div>
    </section>
  );
}

function SummaryCount({ value, label, tone }) {
  return (
    <div className="text-right">
      <strong className={`block text-[18px] leading-none ${tone === "danger" ? "text-[#ffb5b8]" : "text-[#ffbf7b]"}`}>{value}</strong>
      <span className="mt-1 block text-[#d9e2ee]">{label}</span>
    </div>
  );
}

function ApprovalCard({ item, busy, pendingKey, onDecision, onEvidence }) {
  const risk = riskStyle(item.risk);
  const compact = item.risk === "info";
  return (
    <article className={`overflow-hidden rounded-[8px] border bg-[#1a2028] ${risk.border} ${risk.shadow}`}>
      <header className="grid min-h-[64px] grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-friday-line bg-[#1b2028] px-4">
        <div className="flex min-w-0 items-center gap-3">
          <RiskBadge item={item} />
          <h2 className={`min-w-0 truncate font-extrabold text-white ${compact ? "text-[18px]" : "text-[20px]"}`}>{item.title}</h2>
        </div>
        <span className="shrink-0 font-mono text-[12px] text-[#c9d4e2]">{timeAgo(item.updated_at || item.timestamp)}</span>
      </header>

      {compact ? (
        <div className="grid min-h-[88px] grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-4 py-4">
          <p className="m-0 text-[14px] leading-relaxed text-[#c9d4e2]"><strong className="text-white">Why:</strong> {item.summary}</p>
          <div className="flex items-center gap-3">
            <IconDecision icon={<X size={17} />} label="Deny" disabled={busy} onClick={() => onDecision(item, "deny")} />
            <IconDecision icon={<Check size={18} />} label="Allow" disabled={busy} onClick={() => onDecision(item, "allow")} />
          </div>
        </div>
      ) : (
        <>
          <div className="grid gap-3 border-b border-friday-line p-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(260px,1fr)]">
            <InfoCell title="Why Friday Needs Approval">
              <p className="m-0 text-[14px] leading-relaxed text-[#e6edf7]">{item.summary}</p>
            </InfoCell>
            <InfoCell title={item.category === "private_data" ? "Data/Tool Involved" : "Involved Infrastructure"}>
              <InvolvedList item={item} />
            </InfoCell>
            <InfoCell title="Evidence Snippet" action="Full Evidence" onAction={() => onEvidence(item)}>
              <EvidenceSnippet item={item} />
            </InfoCell>
          </div>
          <footer className="flex min-h-[68px] flex-wrap items-center justify-end gap-2 px-4 py-3">
            <button className="min-h-9 rounded-[4px] border border-transparent px-4 text-[13px] font-bold text-white hover:border-friday-line" type="button" onClick={() => onEvidence(item)}>
              View Evidence
            </button>
            <button className="min-h-9 rounded-[4px] border border-[#3d4857] bg-[#151b22] px-5 text-[13px] font-bold text-white disabled:opacity-45" type="button" disabled={busy} onClick={() => onDecision(item, "allow")}>
              {pendingKey === `${item.kind}-${item.id}-allow` ? "Allowing..." : "Allow Once"}
            </button>
            <button className="inline-flex min-h-9 items-center gap-2 rounded-[4px] border border-[#ffaaa6] bg-[#ffaaa6] px-5 text-[13px] font-bold text-[#351313] disabled:opacity-45" type="button" disabled={busy} onClick={() => onDecision(item, "deny")}>
              <Ban size={16} />
              {pendingKey === `${item.kind}-${item.id}-deny` ? "Denying..." : "Deny Action"}
            </button>
            {item.category === "private_data" ? (
              <button className="min-h-9 rounded-[4px] border border-[#8bbcff] bg-[#8bbcff] px-5 text-[13px] font-bold text-[#061420] disabled:opacity-45" type="button" disabled={busy} onClick={() => onDecision(item, "always_allow")}>
                Always Allow
              </button>
            ) : null}
          </footer>
        </>
      )}
    </article>
  );
}

function RiskBadge({ item }) {
  const risk = riskStyle(item.risk);
  return (
    <span className={`inline-flex min-h-8 shrink-0 items-center gap-1.5 rounded-[2px] border px-3 font-mono text-[11px] font-bold uppercase tracking-[.08em] ${risk.badge}`}>
      <span className="h-2 w-2 rounded-full bg-current" />
      {risk.label}
    </span>
  );
}

function InfoCell({ title, action, onAction, children }) {
  return (
    <section className="min-w-0 rounded-[4px] border border-[#283441] bg-[#080d11] p-4">
      <header className="mb-3 flex min-w-0 items-center justify-between gap-3">
        <h3 className="truncate text-[12px] font-semibold uppercase tracking-[.04em] text-[#cbd5e2]">{title}</h3>
        {action ? <button className="shrink-0 text-[12px] text-friday-accent" type="button" onClick={onAction}>{action}</button> : null}
      </header>
      {children}
    </section>
  );
}

function EvidenceModal({ item, onClose }) {
  const payload = item.metadata || {};
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/55 p-4" role="dialog" aria-modal="true" aria-label="Approval evidence">
      <section className="grid max-h-[88dvh] w-[720px] max-w-[calc(100dvw-32px)] grid-rows-[auto_minmax(0,1fr)] overflow-hidden rounded-[8px] border border-[#334154] bg-[#111821] shadow-2xl">
        <header className="flex items-start gap-3 border-b border-friday-line p-4">
          <div className="min-w-0">
            <h2 className="truncate text-[18px] font-extrabold text-white">{item.title}</h2>
            <p className="mt-1 truncate font-mono text-[11px] text-friday-muted">{item.kind} / #{item.id}</p>
          </div>
          <button className="ml-auto text-[#d6e1ee]" type="button" onClick={onClose} aria-label="Close evidence">
            <X size={18} />
          </button>
        </header>
        <div className="friday-scroll min-h-0 overflow-y-auto p-4">
          <p className="mb-4 text-[13px] leading-relaxed text-[#dce6f2]">{item.summary || item.action_hint || "No summary was attached to this approval."}</p>
          <pre className="max-h-[56dvh] overflow-auto rounded-[4px] border border-friday-line bg-[#070c11] p-4 font-mono text-[11px] leading-relaxed text-[#dce6f2]">{stringify(payload)}</pre>
        </div>
      </section>
    </div>
  );
}

function InvolvedList({ item }) {
  const lines = involvedLines(item);
  return (
    <div className="grid gap-2 font-mono text-[13px] text-[#dce6f2]">
      {lines.map((line, index) => (
        <div className="flex min-w-0 items-center gap-2" key={`${index}-${line.text}`}>
          <span className={line.tone === "danger" ? "text-[#ffaaa6]" : "text-[#9aa8ba]"}>{line.icon}</span>
          <span className={`min-w-0 truncate ${line.tone === "danger" ? "text-[#ffb5a8]" : ""}`}>{line.text}</span>
        </div>
      ))}
    </div>
  );
}

function EvidenceSnippet({ item }) {
  const lines = evidenceLines(item);
  if (item.category === "private_data" && !lines.length) {
    return (
      <div className="grid min-h-[90px] place-items-center border border-dashed border-[#283441] text-center text-[12px] text-friday-muted">
        <ShieldAlert size={24} className="mb-2 opacity-60" />
        Policy Trigger: Privacy Layer 2
      </div>
    );
  }
  return (
    <pre className="max-h-[108px] overflow-hidden rounded-[3px] border border-[#1e2a36] bg-[#0b1117] p-3 font-mono text-[11px] leading-relaxed text-[#dce6f2]">
      {lines.join("\n")}
    </pre>
  );
}

function IconDecision({ icon, label, disabled, onClick }) {
  return (
    <button className="grid h-9 w-9 place-items-center rounded-[4px] border border-transparent text-[#aeb9c7] hover:border-friday-line hover:text-white disabled:opacity-40" type="button" aria-label={label} title={label} disabled={disabled} onClick={onClick}>
      {icon}
    </button>
  );
}

function EmptyApprovals({ rows, filter, copy }) {
  return (
    <section className="grid min-h-[220px] place-items-center rounded-[8px] border border-friday-line bg-[#151b22] px-6 text-center">
      <div>
        <CheckCircle2 className="mx-auto mb-3 text-[#90efc9]" size={30} />
        <h2 className="text-[20px] font-extrabold text-white">{rows.length ? "No decisions match this filter" : copy?.empty?.approvals || "Friday has no decision gate waiting"}</h2>
        <p className="mt-2 max-w-[520px] text-[13px] leading-relaxed text-friday-muted">
          {rows.length ? `The ${FILTERS.find((item) => item.id === filter)?.label || "selected"} queue is clear.` : copy?.empty?.approvals || "Friday has no approval-gated work paused right now."}
        </p>
      </div>
    </section>
  );
}

function normalizeApprovals(approvals, summary) {
  const rows = approvals?.length ? approvals : summary?.items || [];
  return rows.map((item) => {
    const category = categoryFor(item);
    const risk = riskFor(item, category);
    return {
      ...item,
      title: item.title || titleForKind(item.kind),
      summary: item.summary || item.action_hint || "Waiting for a decision.",
      category,
      risk
    };
  });
}

function categoryFor(item) {
  const text = searchable(item);
  if (text.includes("self_update") || text.includes("self-update") || text.includes("self update")) return "self_update";
  if (text.includes("deploy") || text.includes("release") || text.includes("production")) return "deploy_approval";
  if (text.includes("privacy") || text.includes("private") || text.includes("calendar") || text.includes("permission") || text.includes("confidential")) return "private_data";
  if (text.includes("blackboard") || text.includes("agent_question") || text.includes("blocker") || text.includes("question")) return "agent_question";
  return "risky_action";
}

function riskFor(item, category) {
  const text = searchable(item);
  if (category === "deploy_approval" || text.includes("admin") || text.includes("delete") || text.includes("production") || text.includes("cluster")) return "high";
  if (category === "private_data" || text.includes("private") || text.includes("blocked") || text.includes("desktop")) return "medium";
  if (category === "self_update") return "info";
  return "medium";
}

function riskStyle(risk) {
  if (risk === "high") {
    return {
      label: "High Risk",
      border: "border-[#9b5f64]",
      shadow: "shadow-[inset_4px_0_0_#ffaaa6]",
      badge: "border-[#99646a] bg-[#3a2028] text-[#ffb5b8]"
    };
  }
  if (risk === "medium") {
    return {
      label: "Med Risk",
      border: "border-[#8a6236]",
      shadow: "shadow-[inset_4px_0_0_#ffbf7b]",
      badge: "border-[#8a6236] bg-[#332516] text-[#ffbf7b]"
    };
  }
  return {
    label: "Info",
    border: "border-friday-line",
    shadow: "",
    badge: "border-[#3d4857] bg-[#202733] text-friday-muted"
  };
}

function involvedLines(item) {
  const metadata = item.metadata || {};
  const mission = metadata.mission_approval || metadata.mission_blocker || {};
  const task = metadata.task || {};
  const permission = metadata.permission_event || {};
  const selfUpdate = metadata.self_update || {};
  const lines = [
    { icon: <Server size={14} />, text: item.agent_id ? `agent: ${item.agent_id}` : `kind: ${item.kind}` },
    { icon: <Database size={14} />, text: task.id ? `task: #${task.id}` : mission.mission_id ? `mission: #${mission.mission_id}` : selfUpdate.id ? `self-update: #${selfUpdate.id}` : permission.key ? `permission: ${permission.key}` : `source: ${metadata.source || "friday"}` }
  ];
  if (item.category === "private_data") lines.push({ icon: <Lock size={14} />, text: permission.target || "scope: read_only" });
  if (item.risk === "high") lines.push({ icon: <AlertTriangle size={14} />, text: item.action_hint || "requires explicit authorization", tone: "danger" });
  return lines;
}

function evidenceLines(item) {
  const metadata = item.metadata || {};
  const payload = metadata.payload || metadata.self_update || metadata.mission_approval || metadata.desktop_session || metadata.task || {};
  const entries = Object.entries(payload).filter(([, value]) => ["string", "number", "boolean"].includes(typeof value)).slice(0, 5);
  if (entries.length) return entries.map(([key, value], index) => `${index ? "+" : "-"} ${key}: ${String(value).slice(0, 80)}`);
  return [];
}

function searchable(item) {
  return `${item.kind || ""} ${item.title || ""} ${item.summary || ""} ${item.action_hint || ""}`.toLowerCase();
}

function stringify(value) {
  try {
    return JSON.stringify(value || {}, null, 2);
  } catch {
    return String(value || "");
  }
}

function titleForKind(kind) {
  return String(kind || "Approval").replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function decisionLabel(decision) {
  if (decision === "allow") return "Allowed once";
  if (decision === "always_allow") return "Always allowed";
  return "Denied";
}

function timeAgo(value) {
  const date = value ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) return "Pending";
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return "Just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "Yesterday" : `${days} days ago`;
}

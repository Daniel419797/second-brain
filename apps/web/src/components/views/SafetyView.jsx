"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Info,
  LockKeyhole,
  Shield,
  XCircle
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";

export function SafetyView() {
  const { api, data, interfaceFor } = useDashboard();
  const copy = interfaceFor?.("safety") || {};
  const [rules, setRules] = useState([]);
  const [events, setEvents] = useState([]);
  const [guardian, setGuardian] = useState(null);
  const [securityPro, setSecurityPro] = useState(null);
  const [status, setStatus] = useState("");
  const [ruleModalOpen, setRuleModalOpen] = useState(false);

  const loadSafety = useCallback(async () => {
      try {
        const [ruleRows, eventRows, safetyStatus, securityStatus] = await Promise.all([
          api("/permissions/rules"),
          api("/permissions/events?limit=24"),
          api("/safety-guardian/status"),
          api("/security-guardian-pro/status")
        ]);
        setRules(Array.isArray(ruleRows) ? ruleRows : []);
        setEvents(Array.isArray(eventRows) ? eventRows : []);
        setGuardian(safetyStatus || null);
        setSecurityPro(securityStatus || null);
        setStatus("");
      } catch (err) {
        setStatus(err.message || "Could not load safety data.");
      }
  }, [api]);

  useEffect(() => {
    let cancelled = false;
    async function run() {
      if (cancelled) return;
      await loadSafety();
    }
    run();
    return () => {
      cancelled = true;
    };
  }, [loadSafety]);

  async function addRule(rule) {
    setStatus("");
    try {
      const updated = await api(`/permissions/rules/${encodeURIComponent(rule.key)}`, {
        method: "PUT",
        body: JSON.stringify({ mode: rule.mode })
      });
      setRules((items) => [updated, ...items.filter((item) => item.key !== updated.key)]);
      setRuleModalOpen(false);
      setStatus(`Rule ${updated.key} set to ${updated.mode}.`);
    } catch (err) {
      setStatus(err.message || "Could not save permission rule.");
    }
  }

  async function resetPolicy() {
    setStatus("");
    try {
      const reset = await api("/permissions/reset", { method: "POST", body: JSON.stringify({}) });
      setRules(Array.isArray(reset) ? reset : []);
      setStatus("Permission policy reset to defaults.");
    } catch (err) {
      setStatus(err.message || "Could not reset permission policy.");
    }
  }

  function exportPolicy() {
    const payload = JSON.stringify({ exported_at: new Date().toISOString(), rules, events: events.slice(0, 100) }, null, 2);
    const blob = new Blob([payload], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `friday-permission-policy-${Date.now()}.json`;
    link.click();
    URL.revokeObjectURL(url);
    setStatus("Permission policy exported.");
  }

  const policyRows = useMemo(() => selectPolicyRows(rules), [rules]);
  const auditRows = useMemo(() => selectAuditRows(events, guardian), [events, guardian]);
  const decisionRows = useMemo(() => selectDecisionRows(events), [events]);
  const automationRate = automationPercent(events);
  const approvalCount = Number(data.approvalSummary?.count || data.approvals?.length || 0);
  const blockedCount = events.filter((event) => ["blocked", "cancelled", "deny", "denied"].includes(String(event.decision).toLowerCase())).length;

  return (
    <section className="min-h-full bg-friday-bg text-[#eaf2fb]" aria-label="Safety Center">
      <div className="mx-auto grid w-full max-w-[860px] gap-3">
        <SafetyHeader copy={copy} />
        {status ? <div className="rounded-[4px] border border-[#7a5638] bg-[#2b2118] px-4 py-3 text-[13px] text-[#ffbf7b]">{status}</div> : null}

        <div className="grid min-w-0 grid-cols-[repeat(auto-fit,minmax(210px,1fr))] gap-3">
          <StatusCard
            title="Permission Rules"
            badge={policyRows.length ? "Loaded" : "Waiting"}
            metric={policyRows.length}
            detail={policyRows.length ? `${policyRows.length} backend rule${policyRows.length === 1 ? "" : "s"} visible in this safety read.` : "No backend permission rows are loaded in this read yet."}
            visual={<span className="block h-2 w-full rounded-full bg-[#1f2d3a]"><span className="block h-full rounded-full bg-[#9fcaff]" style={{ width: policyRows.length ? `${Math.min(100, policyRows.length * 25)}%` : "0%" }} /></span>}
          />
          <StatusCard
            title="Approval Gates"
            badge={approvalCount ? "Waiting" : "Clear"}
            metric={approvalCount}
            detail={approvalCount ? `${approvalCount} approval gate${approvalCount === 1 ? "" : "s"} waiting before risky work continues.` : copy?.empty?.highRisk || "No approval gate is waiting in the current snapshot."}
            visual={<LockKeyhole className="text-friday-accent" size={24} />}
          />
          <GuardianCard guardian={guardian} securityPro={securityPro} blockedCount={blockedCount} />
        </div>

        <PermissionFramework rows={policyRows} onExport={exportPolicy} onAdd={() => setRuleModalOpen(true)} />

        <div className="grid min-w-0 gap-3 2xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <RiskAuditLog rows={auditRows} onReset={resetPolicy} />
          <RecentPermissionDecisions rows={decisionRows} automationRate={automationRate} />
        </div>
      </div>
      {ruleModalOpen ? <RuleModal onClose={() => setRuleModalOpen(false)} onSave={addRule} /> : null}
    </section>
  );
}

function SafetyHeader({ copy }) {
  return (
    <header className="flex min-h-[42px] items-center justify-between gap-3 border-b border-friday-line pb-2">
      <div className="flex min-w-0 items-center gap-3">
        <h1 className="text-[18px] font-extrabold uppercase leading-tight text-white">{copy?.title || "Safety Center"}</h1>
        <span className="h-7 w-px bg-friday-line" />
        <div className="flex min-w-0 items-center gap-3 font-mono text-[11px] font-bold">
          <span className="border-b-2 border-friday-accent pb-1.5 text-friday-accent">Internal Security</span>
          <span className="pb-1.5 text-[#cbd5e2]">Audit Logs</span>
        </div>
      </div>
      <span className="shrink-0 rounded-[4px] border border-friday-blue bg-friday-blue px-3 py-1.5 font-mono text-[11px] text-[#061420]">{copy?.modeLabel || "Safety Gates"}</span>
    </header>
  );
}

function StatusCard({ title, badge, metric, detail, visual }) {
  return (
    <article className="grid min-h-[138px] content-between rounded-[6px] border border-friday-line bg-[#1a2028] p-3">
      <div className="flex min-w-0 items-start justify-between gap-2">
        <h2 className="min-w-0 truncate font-mono text-[11px] font-bold uppercase tracking-[.12em] text-[#9aa8ba]">{title}</h2>
        <span className="shrink-0 rounded-[2px] border border-[#2e8b45] bg-[#15321f] px-2 py-0.5 font-mono text-[9px] font-bold uppercase text-[#45e06d]">{badge}</span>
      </div>
      <div className="grid gap-2">
        <div className="flex min-w-0 items-center gap-3">
          <strong className="text-[24px] font-extrabold leading-none text-white">{metric}</strong>
          <div className="min-w-[72px] flex-1">{visual}</div>
        </div>
        <p className="m-0 text-[12px] leading-relaxed text-[#dce6f2]">{detail}</p>
      </div>
    </article>
  );
}

function GuardianCard({ guardian, securityPro, blockedCount }) {
  const summary = securityPro?.summary || guardian?.summary || "No guardian summary returned in this safety read.";
  const statusLabel = securityPro?.enabled || guardian?.enabled ? "Online" : guardian || securityPro ? "Ready" : "Waiting";
  const lastSync = securityPro?.timestamp || guardian?.timestamp || guardian?.latest?.timestamp;
  return (
    <article className="grid min-h-[138px] grid-cols-[minmax(0,1fr)_70px] items-end gap-3 rounded-[6px] border border-friday-line bg-[#1a2028] p-3">
      <div className="min-w-0 self-start">
        <h2 className="font-mono text-[11px] font-bold uppercase tracking-[.12em] text-[#9aa8ba]">Guardian Backup</h2>
        <strong className="mt-2 block truncate text-[16px] font-extrabold text-white">{statusLabel}</strong>
        <p className="mt-5 font-mono text-[10px] text-[#cbd5e2]">Last Signal<br />{lastSync ? timeAgo(lastSync) : "Not reported"}</p>
      </div>
      <div className="grid place-items-center">
        <div className="grid h-[58px] w-[58px] place-items-center rounded-full border-[5px] border-[#ffb277] bg-[#111820] text-center font-mono text-[10px] font-bold leading-tight text-white">{blockedCount}<br />held</div>
      </div>
      <span className="col-span-2 truncate text-[10px] text-friday-muted">{summary}</span>
    </article>
  );
}

function PermissionFramework({ rows, onExport, onAdd }) {
  return (
    <section className="rounded-[6px] border border-friday-line bg-[#1a2028] p-3">
      <header className="mb-3 flex min-w-0 flex-wrap items-center gap-2">
        <h2 className="min-w-0 flex-1 text-[15px] font-extrabold text-white">Permission Policy Framework</h2>
        <button className="min-h-8 rounded-[2px] border border-friday-line bg-[#202733] px-3 font-mono text-[10px] text-white hover:border-friday-accent" type="button" onClick={onExport}>Export Policy</button>
        <button className="min-h-8 rounded-[2px] border border-[#8bbcff] bg-[#8bbcff] px-4 font-mono text-[11px] uppercase text-[#061420]" type="button" onClick={onAdd}>Add Rule</button>
      </header>

      <div className="grid min-w-0">
        <div className="grid min-h-8 grid-cols-[minmax(130px,1fr)_88px_68px_minmax(170px,1.2fr)] items-center border-b border-friday-line px-1 font-mono text-[10px] font-bold uppercase tracking-[.1em] text-[#9aa8ba] max-xl:hidden">
          <span>Capability</span>
          <span>Category</span>
          <span>Mode</span>
          <span>Description</span>
        </div>
        {rows.length ? rows.map((row) => <PolicyRow row={row} key={row.key} />) : <EmptyState>Friday has no permission rule rows from the backend yet.</EmptyState>}
      </div>
    </section>
  );
}

function PolicyRow({ row }) {
  return (
    <div className="grid min-h-[50px] min-w-0 grid-cols-[minmax(130px,1fr)_88px_68px_minmax(170px,1.2fr)] items-center gap-2 border-b border-friday-line px-1 py-2 last:border-b-0 max-xl:grid-cols-1 max-xl:gap-1.5">
      <span className="min-w-0 truncate font-mono text-[11px] uppercase text-friday-accent">{capabilityName(row)}</span>
      <span className="truncate text-[11px] text-white">{row.category || "Other"}</span>
      <ModeBadge mode={row.mode} />
      <p className="m-0 min-w-0 text-[11px] leading-relaxed text-[#dce6f2]">{row.description || "Permission rule managed by Friday safety policies."}</p>
    </div>
  );
}

function RiskAuditLog({ rows, onReset }) {
  return (
    <section className="rounded-[6px] border border-friday-line bg-[#1a2028] p-3">
      <header className="mb-3 flex items-center gap-3">
        <h2 className="text-[15px] font-extrabold text-white">Risky Action Audit Log</h2>
        <button className="ml-auto font-mono text-[10px] text-[#ffb5b8] underline" type="button" onClick={onReset}>Reset Policy</button>
      </header>
      <div className="grid gap-2">
        {rows.length ? rows.map((row, index) => <AuditItem row={row} index={index} key={row.id || `${row.key}-${index}`} />) : <EmptyState>No risky action audit row is present in this safety read.</EmptyState>}
      </div>
    </section>
  );
}

function RuleModal({ onClose, onSave }) {
  const [key, setKey] = useState("");
  const [mode, setMode] = useState("ask");
  function submit(event) {
    event.preventDefault();
    if (!key.trim()) return;
    onSave({ key: key.trim(), mode });
  }
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/55 p-4" role="dialog" aria-modal="true" aria-label="Add permission rule">
      <form className="grid w-[390px] max-w-[calc(100dvw-32px)] gap-4 rounded-[6px] border border-[#334154] bg-[#111821] p-4 shadow-2xl" onSubmit={submit}>
        <header className="flex items-center gap-3 border-b border-friday-line pb-3">
          <h2 className="text-[17px] font-extrabold text-white">Add Permission Rule</h2>
          <button className="ml-auto text-[#d6e1ee]" type="button" onClick={onClose} aria-label="Close rule form">x</button>
        </header>
        <label className="grid gap-1">
          <span className="font-mono text-[10px] uppercase text-friday-muted">Rule key</span>
          <input className="min-h-10 rounded-[3px] border border-friday-line bg-[#0c1218] px-3 text-[13px] text-white outline-none focus:border-friday-accent" value={key} onChange={(event) => setKey(event.target.value)} placeholder="pc_control.run_command" required />
        </label>
        <label className="grid gap-1">
          <span className="font-mono text-[10px] uppercase text-friday-muted">Mode</span>
          <select className="min-h-10 rounded-[3px] border border-friday-line bg-[#0c1218] px-3 text-[13px] text-white outline-none focus:border-friday-accent" value={mode} onChange={(event) => setMode(event.target.value)}>
            <option value="ask">Ask</option>
            <option value="allow">Allow</option>
            <option value="block">Block</option>
          </select>
        </label>
        <footer className="grid grid-cols-2 gap-3 border-t border-friday-line pt-3">
          <button className="min-h-10 rounded-[3px] border border-friday-line bg-[#151b22] text-[12px] text-[#dfe9f6]" type="button" onClick={onClose}>Cancel</button>
          <button className="min-h-10 rounded-[3px] border border-[#8bbcff] bg-[#8bbcff] text-[12px] font-bold text-[#061420]" type="submit">Save Rule</button>
        </footer>
      </form>
    </div>
  );
}

function AuditItem({ row, index }) {
  const Icon = row.decision === "blocked" || row.decision === "cancelled" ? AlertTriangle : index === 1 ? Shield : Info;
  const tone = row.decision === "blocked" || row.decision === "cancelled" ? "text-[#ffaaa6]" : index === 1 ? "text-[#ffb277]" : "text-friday-muted";
  return (
    <article className="grid min-h-[72px] min-w-0 grid-cols-[30px_minmax(0,1fr)_auto] gap-2 border border-friday-line bg-[#0d1218] p-3">
      <Icon className={tone} size={19} />
      <div className="min-w-0">
        <h3 className="truncate font-mono text-[13px] uppercase tracking-[.1em] text-white">{eventTitle(row)}</h3>
        <p className="m-0 mt-1 text-[11px] leading-relaxed text-[#cbd5e2]">{eventSummary(row)}</p>
      </div>
      <span className="font-mono text-[10px] text-friday-muted">{timeAgo(row.timestamp, index)}</span>
    </article>
  );
}

function RecentPermissionDecisions({ rows, automationRate }) {
  return (
    <section className="rounded-[6px] border border-friday-line bg-[#1a2028] p-3">
      <h2 className="mb-3 text-[15px] font-extrabold text-white">Recent Permission Decisions</h2>
      <div className="grid">
        {rows.length ? rows.map((row, index) => <DecisionItem row={row} index={index} key={row.id || `${row.key}-${index}`} />) : <EmptyState>No permission decision has been recorded yet.</EmptyState>}
      </div>
      <div className="mt-3 border border-dashed border-[#405063] bg-[#151b22] px-3 py-3 text-center">
        <h3 className="font-mono text-[11px] font-bold uppercase tracking-[.1em] text-friday-accent">System Analytics</h3>
        <p className="m-0 mt-1 text-[12px] text-white">{automationRate == null ? "Automation rate will appear after permission events are recorded." : `${automationRate}% of recorded permission decisions were resolved automatically.`}</p>
      </div>
    </section>
  );
}

function DecisionItem({ row, index }) {
  const allowed = ["allowed", "allow"].includes(String(row.decision).toLowerCase());
  const blocked = ["blocked", "cancelled", "deny", "denied"].includes(String(row.decision).toLowerCase());
  const Icon = allowed ? CheckCircle2 : blocked ? XCircle : Clock;
  const color = allowed ? "text-friday-accent" : blocked ? "text-[#ffaaa6]" : "text-[#ffb277]";
  return (
    <div className="grid min-h-[38px] min-w-0 grid-cols-[18px_minmax(0,1fr)_74px] items-center gap-2 border-b border-friday-line last:border-b-0">
      <Icon className={color} size={13} />
      <span className="truncate text-[12px] text-white">{decisionTitle(row, index)}</span>
      <span className="text-right text-[10px] text-friday-muted">{timeAgo(row.timestamp, index)}</span>
    </div>
  );
}

function ModeBadge({ mode }) {
  const value = String(mode || "ask").toLowerCase();
  const styles = {
    allow: "border-[#2e8b45] bg-[#15321f] text-[#45e06d]",
    ask: "border-[#a37b13] bg-[#2e260f] text-[#ffc13b]",
    block: "border-[#ab2c2c] bg-[#351515] text-[#ff5d5d]"
  };
  return <span className={`w-fit rounded-[2px] border px-2 py-0.5 font-mono text-[9px] font-bold uppercase ${styles[value] || styles.ask}`}>{value}</span>;
}

function selectPolicyRows(rules) {
  if (!rules.length) return [];
  const priority = ["pc_control.read_file", "capability_center.security_scan", "pc_control.run_command", "power_center.privacy_firewall_pro", "pc_control.screenshot", "power_center.personal_safety_guardian"];
  const picked = [];
  for (const key of priority) {
    const item = rules.find((rule) => rule.key === key);
    if (item) picked.push(item);
  }
  for (const rule of rules) {
    if (picked.length >= 4) break;
    if (!picked.some((item) => item.key === rule.key) && ["Files", "Safety", "Security Lab", "System", "Desktop"].includes(rule.category)) picked.push(rule);
  }
  return picked.slice(0, 4);
}

function selectAuditRows(events, guardian) {
  const risky = events.filter((event) => ["blocked", "cancelled", "ask"].includes(String(event.decision).toLowerCase())).slice(0, 3);
  if (risky.length) return risky;
  const findings = guardian?.latest?.findings || guardian?.reports?.[0]?.findings || [];
  if (findings.length) {
    return findings.slice(0, 3).map((finding, index) => ({
      id: `finding-${index}`,
      key: finding.kind || "SAFETY_FINDING",
      decision: Number(finding.severity || 0) >= 3 ? "blocked" : "ask",
      timestamp: guardian?.latest?.timestamp || "",
      details: { summary: finding.summary || "Safety guardian finding." }
    }));
  }
  return [];
}

function selectDecisionRows(events) {
  if (events.length) return events.slice(0, 4);
  return [];
}

function automationPercent(events) {
  if (!events.length) return null;
  const automated = events.filter((event) => ["allowed", "blocked"].includes(String(event.decision).toLowerCase())).length;
  return ((automated / events.length) * 100).toFixed(1);
}

function capabilityName(row) {
  if (row.label && /^[A-Z0-9_]+$/.test(row.label)) return row.label;
  return String(row.key || row.label || "CAPABILITY").replace(/^[a-z]+_center\./, "").replace(/pc_control\./, "").replace(/[.-]+/g, "_").toUpperCase();
}

function eventTitle(row) {
  return String(row.key || row.action || "SAFETY_EVENT").replace(/[.-]+/g, "_").toUpperCase();
}

function eventSummary(row) {
  return row.details?.summary || row.details?.reason || row.target || `${row.action || "Action"} was ${row.decision || "recorded"}.`;
}

function decisionTitle(row, index) {
  const action = String(row.decision || "Review").toLowerCase();
  const label = String(row.key || row.action || "Permission").replace(/[_\-.]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  if (action.includes("allow")) return `Allow ${label}`;
  if (action.includes("block") || action.includes("cancel")) return `Block ${label}`;
  return `Escalate ${label}`;
}

function timeAgo(value, index = 0) {
  const date = value ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) return "No timestamp";
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return "Just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `Today, ${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
  return "Yesterday";
}

function EmptyState({ children }) {
  return <div className="grid min-h-[74px] place-items-center rounded-[4px] border border-dashed border-friday-line bg-[#10161d] p-4 text-center text-[12px] text-friday-muted">{children}</div>;
}

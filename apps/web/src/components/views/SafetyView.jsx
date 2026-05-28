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
import { useEffect, useMemo, useState } from "react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";

const FALLBACK_RULES = [
  { key: "fs_root_read", label: "FS_ROOT_READ", category: "FileSystem", mode: "allow", description: "Global read access to system root for diagnostic reporting." },
  { key: "net_outbound_external", label: "NET_OUTBOUND_EXTERNAL", category: "Network", mode: "ask", description: "Requires manual admin approval for any non-whitelisted domain." },
  { key: "exec_untrusted_bin", label: "EXEC_UNTRUSTED_BIN", category: "Runtime", mode: "block", description: "Execution of binaries without valid cryptographic signature." },
  { key: "mic_stream_always", label: "MIC_STREAM_ALWAYS", category: "Media", mode: "ask", description: "Active listening for hotword detection and voice commands." }
];

const FALLBACK_EVENTS = [
  { id: "ssh", key: "SSH_ATTEMPT_SUDO", decision: "blocked", action: "sudo", target: "localhost", timestamp: "", details: { summary: "Unauthorized elevation attempt by Agent 'Alpha-7' on Localhost." } },
  { id: "api", key: "API_KEY_LEAK_SCAN", decision: "ask", action: "secret_scan", target: "/logs/temp.txt", timestamp: "", details: { summary: "Detected potential secret in /logs/temp.txt. Quarantined file." } },
  { id: "cert", key: "CERT_ROTATION_INIT", decision: "allowed", action: "cert_rotation", target: "ssl", timestamp: "", details: { summary: "Routine SSL certificate rotation completed successfully." } }
];

export function SafetyView() {
  const { api, data } = useDashboard();
  const [rules, setRules] = useState([]);
  const [events, setEvents] = useState([]);
  const [guardian, setGuardian] = useState(null);
  const [securityPro, setSecurityPro] = useState(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function loadSafety() {
      try {
        const [ruleRows, eventRows, safetyStatus, securityStatus] = await Promise.all([
          api("/permissions/rules"),
          api("/permissions/events?limit=24"),
          api("/safety-guardian/status"),
          api("/security-guardian-pro/status")
        ]);
        if (cancelled) return;
        setRules(Array.isArray(ruleRows) ? ruleRows : []);
        setEvents(Array.isArray(eventRows) ? eventRows : []);
        setGuardian(safetyStatus || null);
        setSecurityPro(securityStatus || null);
        setStatus("");
      } catch (err) {
        if (!cancelled) setStatus(err.message || "Could not load safety data.");
      }
    }
    loadSafety();
    return () => {
      cancelled = true;
    };
  }, [api]);

  const policyRows = useMemo(() => selectPolicyRows(rules), [rules]);
  const auditRows = useMemo(() => selectAuditRows(events, guardian), [events, guardian]);
  const decisionRows = useMemo(() => selectDecisionRows(events), [events]);
  const automationRate = automationPercent(events);

  return (
    <section className="min-h-full bg-friday-bg text-[#eaf2fb]" aria-label="Safety Center">
      <div className="mx-auto grid w-full max-w-[860px] gap-3">
        <SafetyHeader />
        {status ? <div className="rounded-[4px] border border-[#7a5638] bg-[#2b2118] px-4 py-3 text-[13px] text-[#ffbf7b]">{status}</div> : null}

        <div className="grid min-w-0 grid-cols-[repeat(auto-fit,minmax(210px,1fr))] gap-3">
          <StatusCard
            title="Environment Protection"
            badge="Active"
            metric="99.9%"
            detail="Zero-trust encapsulation running for all active missions."
            visual={<span className="block h-2 w-full rounded-full bg-[#9fcaff]" />}
          />
          <StatusCard
            title="Private File Protection"
            badge="Locked"
            metric="AES-256"
            detail="Biometric verification required for core memory access."
            visual={<LockKeyhole className="text-friday-accent" size={24} />}
          />
          <GuardianCard guardian={guardian} securityPro={securityPro} />
        </div>

        <PermissionFramework rows={policyRows} />

        <div className="grid min-w-0 gap-3 2xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <RiskAuditLog rows={auditRows} />
          <RecentPermissionDecisions rows={decisionRows} automationRate={automationRate} />
        </div>
      </div>
    </section>
  );
}

function SafetyHeader() {
  return (
    <header className="flex min-h-[42px] items-center justify-between gap-3 border-b border-friday-line pb-2">
      <div className="flex min-w-0 items-center gap-3">
        <h1 className="text-[18px] font-extrabold uppercase leading-tight text-white">Safety Center</h1>
        <span className="h-7 w-px bg-friday-line" />
        <div className="flex min-w-0 items-center gap-3 font-mono text-[11px] font-bold">
          <span className="border-b-2 border-friday-accent pb-1.5 text-friday-accent">Internal Security</span>
          <span className="pb-1.5 text-[#cbd5e2]">Audit Logs</span>
        </div>
      </div>
      <span className="shrink-0 rounded-[4px] border border-friday-blue bg-friday-blue px-3 py-1.5 font-mono text-[11px] text-[#061420]">9+ Approvals</span>
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

function GuardianCard({ guardian, securityPro }) {
  const summary = securityPro?.summary || guardian?.summary || "Guardian backup is stable.";
  return (
    <article className="grid min-h-[138px] grid-cols-[minmax(0,1fr)_70px] items-end gap-3 rounded-[6px] border border-friday-line bg-[#1a2028] p-3">
      <div className="min-w-0 self-start">
        <h2 className="font-mono text-[11px] font-bold uppercase tracking-[.12em] text-[#9aa8ba]">Guardian Backup</h2>
        <strong className="mt-2 block truncate text-[16px] font-extrabold text-white">v14.2.9-stable</strong>
        <p className="mt-5 font-mono text-[10px] text-[#cbd5e2]">Last Sync<br />{new Date().toLocaleTimeString([], { hour12: false })} UTC</p>
      </div>
      <div className="grid place-items-center">
        <div className="grid h-[58px] w-[58px] place-items-center rounded-full border-[5px] border-[#ffb277] bg-[#111820] font-mono text-[11px] font-bold text-white">85%</div>
      </div>
      <span className="col-span-2 truncate text-[10px] text-friday-muted">{summary}</span>
    </article>
  );
}

function PermissionFramework({ rows }) {
  return (
    <section className="rounded-[6px] border border-friday-line bg-[#1a2028] p-3">
      <header className="mb-3 flex min-w-0 flex-wrap items-center gap-2">
        <h2 className="min-w-0 flex-1 text-[15px] font-extrabold text-white">Permission Policy Framework</h2>
        <button className="min-h-8 rounded-[2px] border border-friday-line bg-[#202733] px-3 font-mono text-[10px] text-white" type="button">Export Policy</button>
        <button className="min-h-8 rounded-[2px] border border-[#8bbcff] bg-[#8bbcff] px-4 font-mono text-[11px] uppercase text-[#061420]" type="button">Add Rule</button>
      </header>

      <div className="grid min-w-0">
        <div className="grid min-h-8 grid-cols-[minmax(130px,1fr)_88px_68px_minmax(170px,1.2fr)] items-center border-b border-friday-line px-1 font-mono text-[10px] font-bold uppercase tracking-[.1em] text-[#9aa8ba] max-xl:hidden">
          <span>Capability</span>
          <span>Category</span>
          <span>Mode</span>
          <span>Description</span>
        </div>
        {rows.map((row) => <PolicyRow row={row} key={row.key} />)}
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

function RiskAuditLog({ rows }) {
  return (
    <section className="rounded-[6px] border border-friday-line bg-[#1a2028] p-3">
      <header className="mb-3 flex items-center gap-3">
        <h2 className="text-[15px] font-extrabold text-white">Risky Action Audit Log</h2>
        <button className="ml-auto font-mono text-[10px] text-[#ffb5b8] underline" type="button">Purge History</button>
      </header>
      <div className="grid gap-2">
        {rows.map((row, index) => <AuditItem row={row} index={index} key={row.id || `${row.key}-${index}`} />)}
      </div>
    </section>
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
        {rows.map((row, index) => <DecisionItem row={row} index={index} key={row.id || `${row.key}-${index}`} />)}
      </div>
      <div className="mt-3 border border-dashed border-[#405063] bg-[#151b22] px-3 py-3 text-center">
        <h3 className="font-mono text-[11px] font-bold uppercase tracking-[.1em] text-friday-accent">System Analytics</h3>
        <p className="m-0 mt-1 text-[12px] text-white">{automationRate}% of decisions automated by Friday AI core.</p>
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
  if (!rules.length) return FALLBACK_RULES;
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
  return picked.length ? picked.slice(0, 4) : FALLBACK_RULES;
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
  return FALLBACK_EVENTS;
}

function selectDecisionRows(events) {
  if (events.length) return events.slice(0, 4);
  return [
    { id: "allow-file", key: "file_access", decision: "allowed", timestamp: "" },
    { id: "block-camera", key: "camera_sync", decision: "blocked", timestamp: "" },
    { id: "allow-memory", key: "memory_read", decision: "allowed", timestamp: "" },
    { id: "escalate-network", key: "network_request", decision: "ask", timestamp: "" }
  ];
}

function automationPercent(events) {
  if (!events.length) return "98.4";
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
  if (!row.key && index === 3) return "Escalate Network Request";
  const action = String(row.decision || "Review").toLowerCase();
  const label = String(row.key || row.action || "Permission").replace(/[_\-.]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  if (action.includes("allow")) return `Allow ${label}`;
  if (action.includes("block") || action.includes("cancel")) return `Block ${label}`;
  return `Escalate ${label}`;
}

function timeAgo(value, index = 0) {
  const date = value ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) return ["2m ago", "14m ago", "1h ago", "Yesterday"][index] || "Today";
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return "Just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `Today, ${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
  return "Yesterday";
}

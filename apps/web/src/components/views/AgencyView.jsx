"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CheckSquare,
  DollarSign,
  FileText,
  FolderPlus,
  Loader2,
  MailCheck,
  Receipt,
  RefreshCcw,
  Search,
  Send,
  Square,
  UserPlus
} from "lucide-react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";

const EMPTY_LEAD = { company: "", email: "", website: "", niche: "", need: "" };
const EMPTY_SEARCH = { query: "", niche: "", location: "" };
const EMPTY_OUTREACH = { lead_id: "", service_offer: "", portfolio_url: "", call_to_action: "" };
const EMPTY_INVOICE = { project_id: "", client_name: "", client_email: "", amount: "", currency: "USD" };

export function AgencyView() {
  const { api, data, refresh } = useDashboard();
  const [status, setStatus] = useState(data.agency || null);
  const [leads, setLeads] = useState([]);
  const [outreach, setOutreach] = useState([]);
  const [projects, setProjects] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [profit, setProfit] = useState(null);
  const [selectedOutreach, setSelectedOutreach] = useState([]);
  const [searchForm, setSearchForm] = useState(EMPTY_SEARCH);
  const [leadForm, setLeadForm] = useState(EMPTY_LEAD);
  const [outreachForm, setOutreachForm] = useState(EMPTY_OUTREACH);
  const [invoiceForm, setInvoiceForm] = useState(EMPTY_INVOICE);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");

  const selectedLead = useMemo(() => {
    const id = Number(outreachForm.lead_id || 0);
    return leads.find((lead) => Number(lead.id) === id) || leads[0] || null;
  }, [leads, outreachForm.lead_id]);

  useEffect(() => {
    if (data.agency) setStatus(data.agency);
  }, [data.agency]);

  useEffect(() => {
    void loadAgency();
  }, []);

  async function loadAgency() {
    setBusy("refresh");
    setMessage("");
    try {
      const [nextStatus, nextLeads, nextOutreach, nextProjects, nextInvoices, nextProfit] = await Promise.all([
        api("/agency/status"),
        api("/agency/leads?limit=40"),
        api("/agency/outreach?limit=60"),
        api("/agency/projects?limit=30"),
        api("/agency/invoices?limit=30"),
        api("/agency/profit")
      ]);
      setStatus(nextStatus);
      setLeads(Array.isArray(nextLeads) ? nextLeads : []);
      setOutreach(Array.isArray(nextOutreach) ? nextOutreach : []);
      setProjects(Array.isArray(nextProjects) ? nextProjects : []);
      setInvoices(Array.isArray(nextInvoices) ? nextInvoices : []);
      setProfit(nextProfit);
      setSelectedOutreach((ids) => ids.filter((id) => (nextOutreach || []).some((item) => Number(item.id) === Number(id))));
    } catch (err) {
      setMessage(err.message || "Agency data failed to load.");
    } finally {
      setBusy("");
    }
  }

  async function run(label, action, after = loadAgency) {
    setBusy(label);
    setMessage("");
    try {
      const result = await action();
      setMessage(result?.summary || "Done.");
      await after();
      void refresh();
    } catch (err) {
      setMessage(err.message || "Action failed.");
    } finally {
      setBusy("");
    }
  }

  async function searchLeads(event) {
    event.preventDefault();
    await run("search", () => api("/agency/leads/search", { method: "POST", body: JSON.stringify({ ...searchForm, limit: 8 }) }));
  }

  async function addLead(event) {
    event.preventDefault();
    await run("lead", () => api("/agency/leads", { method: "POST", body: JSON.stringify({ name: leadForm.company, ...leadForm }) }), async () => {
      setLeadForm(EMPTY_LEAD);
      await loadAgency();
    });
  }

  async function scoreLeads() {
    await run("score", () => api("/agency/leads/score", { method: "POST", body: JSON.stringify({}) }));
  }

  async function draftOutreach(event) {
    event.preventDefault();
    const leadId = Number(outreachForm.lead_id || selectedLead?.id || 0);
    if (!leadId) {
      setMessage("Select a lead first.");
      return;
    }
    await run("draft", () => api("/agency/outreach/draft", { method: "POST", body: JSON.stringify({ ...outreachForm, lead_id: leadId }) }), async () => {
      setOutreachForm(EMPTY_OUTREACH);
      await loadAgency();
    });
  }

  async function draftProposal(leadId) {
    await run(`proposal-${leadId}`, () => api("/agency/documents/proposal", { method: "POST", body: JSON.stringify({ lead_id: leadId }) }));
  }

  async function startProject(leadId) {
    const lead = leads.find((item) => Number(item.id) === Number(leadId));
    await run(`project-${leadId}`, () => api("/agency/projects", {
      method: "POST",
      body: JSON.stringify({ lead_id: leadId, name: `${lead?.company || "Client"} project`, brief: lead?.need || "" })
    }));
  }

  async function approveSelected() {
    await run("approve", () => api("/agency/outreach/approve", { method: "POST", body: JSON.stringify({ ids: selectedOutreach }) }), async () => {
      setSelectedOutreach([]);
      await loadAgency();
    });
  }

  async function sendSelected() {
    await run("send", () => api("/agency/outreach/send", { method: "POST", body: JSON.stringify({ ids: selectedOutreach }) }), async () => {
      setSelectedOutreach([]);
      await loadAgency();
    });
  }

  async function createInvoice(event) {
    event.preventDefault();
    await run("invoice", () => api("/agency/invoices", {
      method: "POST",
      body: JSON.stringify({
        project_id: Number(invoiceForm.project_id || 0),
        client_name: invoiceForm.client_name,
        client_email: invoiceForm.client_email,
        amount: Number(invoiceForm.amount || 0),
        currency: invoiceForm.currency || "USD"
      })
    }), async () => {
      setInvoiceForm(EMPTY_INVOICE);
      await loadAgency();
    });
  }

  function toggleOutreach(id) {
    setSelectedOutreach((ids) => ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id]);
  }

  return (
    <section className="friday-scroll h-full overflow-y-auto overflow-x-hidden bg-friday-bg px-4 py-4 text-[#eef5ff]" aria-label="Agency Mode">
      <div className="mx-auto grid max-w-[1240px] gap-4">
        <header className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
          <div className="min-w-0">
            <h1 className="text-[26px] font-extrabold leading-tight text-white">Agency Mode</h1>
            <p className="mt-2 max-w-[720px] text-[13px] leading-relaxed text-friday-muted">{status?.summary || "Agency status is loading."}</p>
          </div>
          <button className="inline-flex min-h-10 items-center justify-center gap-2 rounded-[5px] border border-friday-line bg-[#151b22] px-4 text-[13px] font-bold text-white" type="button" onClick={loadAgency} disabled={Boolean(busy)}>
            {busy === "refresh" ? <Loader2 className="animate-spin" size={15} /> : <RefreshCcw size={15} />}
            Refresh
          </button>
        </header>

        <MetricGrid status={status} profit={profit} leads={leads} outreach={outreach} projects={projects} invoices={invoices} />
        {message ? <div className="rounded-[5px] border border-[#405063] bg-[#101820] px-4 py-3 text-[13px] text-[#dce9f8]">{message}</div> : null}

        <div className="grid gap-4 xl:grid-cols-[370px_minmax(0,1fr)]">
          <aside className="grid content-start gap-4">
            <LeadSearch form={searchForm} setForm={setSearchForm} busy={busy} onSubmit={searchLeads} onScore={scoreLeads} />
            <LeadIntake form={leadForm} setForm={setLeadForm} busy={busy} onSubmit={addLead} />
            <InvoiceForm form={invoiceForm} setForm={setInvoiceForm} projects={projects} busy={busy} onSubmit={createInvoice} />
          </aside>

          <main className="grid content-start gap-4">
            <LeadBoard leads={leads} busy={busy} onSelect={(id) => setOutreachForm((form) => ({ ...form, lead_id: String(id) }))} onProposal={draftProposal} onProject={startProject} />
            <OutreachComposer form={outreachForm} setForm={setOutreachForm} selectedLead={selectedLead} leads={leads} busy={busy} onSubmit={draftOutreach} />
            <OutreachQueue outreach={outreach} selected={selectedOutreach} busy={busy} onToggle={toggleOutreach} onApprove={approveSelected} onSend={sendSelected} />
            <ProjectInvoiceBoard projects={projects} invoices={invoices} />
          </main>
        </div>
      </div>
    </section>
  );
}

function MetricGrid({ status, profit, leads, outreach, projects, invoices }) {
  const draftCount = outreach.filter((item) => item.status === "draft").length || status?.draft_outreach?.length || 0;
  const approvedCount = outreach.filter((item) => item.status === "approved").length || status?.approved_outreach?.length || 0;
  return (
    <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
      <Metric icon={<Search size={16} />} label="Leads" value={String(leads.length || status?.lead_count || 0)} detail="CRM" />
      <Metric icon={<MailCheck size={16} />} label="Drafts" value={String(draftCount)} detail="Needs review" />
      <Metric icon={<Send size={16} />} label="Approved" value={String(approvedCount)} detail="Send queue" />
      <Metric icon={<FolderPlus size={16} />} label="Projects" value={String(projects.length)} detail="Client work" />
      <Metric icon={<Receipt size={16} />} label="Invoices" value={String(invoices.length)} detail="Billing" />
      <Metric icon={<DollarSign size={16} />} label="Profit" value={`${Number(profit?.profit || status?.finance?.profit || 0).toFixed(0)}`} detail={profit?.currency || status?.finance?.currency || "USD"} />
    </div>
  );
}

function Metric({ icon, label, value, detail }) {
  return (
    <div className="grid min-h-[82px] grid-cols-[32px_minmax(0,1fr)] items-center gap-3 rounded-[5px] border border-friday-line bg-[#151b22] px-3">
      <span className="grid h-8 w-8 place-items-center rounded-[4px] border border-[#405063] bg-[#202936] text-friday-accent">{icon}</span>
      <div className="min-w-0">
        <span className="block font-mono text-[10px] uppercase tracking-[.08em] text-friday-muted">{label}</span>
        <strong className="mt-1 block truncate text-[22px] leading-none text-white">{value}</strong>
        <span className="mt-1 block truncate text-[11px] text-[#ccd9e8]">{detail}</span>
      </div>
    </div>
  );
}

function LeadSearch({ form, setForm, busy, onSubmit, onScore }) {
  return (
    <Panel title="Lead Search" icon={<Search size={15} />}>
      <form className="grid gap-2" onSubmit={onSubmit}>
        <Input label="Query" value={form.query} onChange={(value) => setForm({ ...form, query: value })} />
        <div className="grid gap-2 sm:grid-cols-2">
          <Input label="Niche" value={form.niche} onChange={(value) => setForm({ ...form, niche: value })} />
          <Input label="Location" value={form.location} onChange={(value) => setForm({ ...form, location: value })} />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <ActionButton icon={<Search size={14} />} label="Search" active busy={busy === "search"} />
          <button className="inline-flex min-h-10 items-center justify-center gap-2 rounded-[4px] border border-friday-line bg-[#101820] px-3 text-[12px] font-bold text-white" type="button" onClick={onScore} disabled={Boolean(busy)}>
            <CheckSquare size={14} />
            Score
          </button>
        </div>
      </form>
    </Panel>
  );
}

function LeadIntake({ form, setForm, busy, onSubmit }) {
  return (
    <Panel title="Lead Intake" icon={<UserPlus size={15} />}>
      <form className="grid gap-2" onSubmit={onSubmit}>
        <Input label="Company" value={form.company} onChange={(value) => setForm({ ...form, company: value })} required />
        <Input label="Email" value={form.email} onChange={(value) => setForm({ ...form, email: value })} />
        <Input label="Website" value={form.website} onChange={(value) => setForm({ ...form, website: value })} />
        <Input label="Niche" value={form.niche} onChange={(value) => setForm({ ...form, niche: value })} />
        <TextArea label="Need" value={form.need} onChange={(value) => setForm({ ...form, need: value })} />
        <ActionButton icon={<UserPlus size={14} />} label="Save Lead" active busy={busy === "lead"} />
      </form>
    </Panel>
  );
}

function InvoiceForm({ form, setForm, projects, busy, onSubmit }) {
  return (
    <Panel title="Invoice" icon={<Receipt size={15} />}>
      <form className="grid gap-2" onSubmit={onSubmit}>
        <Select label="Project" value={form.project_id} onChange={(value) => setForm({ ...form, project_id: value })}>
          <option value="">No project</option>
          {projects.map((project) => <option value={project.id} key={project.id}>{project.name}</option>)}
        </Select>
        <Input label="Client" value={form.client_name} onChange={(value) => setForm({ ...form, client_name: value })} />
        <Input label="Email" value={form.client_email} onChange={(value) => setForm({ ...form, client_email: value })} />
        <div className="grid gap-2 sm:grid-cols-[1fr_92px]">
          <Input label="Amount" value={form.amount} onChange={(value) => setForm({ ...form, amount: value })} type="number" />
          <Input label="Currency" value={form.currency} onChange={(value) => setForm({ ...form, currency: value })} />
        </div>
        <ActionButton icon={<Receipt size={14} />} label="Generate" active busy={busy === "invoice"} />
      </form>
    </Panel>
  );
}

function LeadBoard({ leads, busy, onSelect, onProposal, onProject }) {
  return (
    <Panel title="Prospects" icon={<Search size={15} />} count={leads.length}>
      <div className="grid gap-2 lg:grid-cols-2">
        {leads.length ? leads.slice(0, 10).map((lead) => (
          <article className="grid min-h-[132px] gap-3 rounded-[5px] border border-[#34404d] bg-[#101820] p-3" key={lead.id}>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <strong className="truncate text-[14px] text-white">{lead.company || lead.name}</strong>
                <span className="ml-auto shrink-0 rounded-[4px] border border-[#405063] bg-[#1c2632] px-2 py-0.5 font-mono text-[10px] text-friday-accent">{Math.round(Number(lead.fit_score || 0))}</span>
              </div>
              <p className="mt-2 line-clamp-2 text-[12px] leading-relaxed text-[#cbd8e6]">{lead.need || lead.score_reason || lead.website || "No note yet."}</p>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <SmallButton label="Select" icon={<MailCheck size={13} />} disabled={Boolean(busy)} onClick={() => onSelect(lead.id)} />
              <SmallButton label="Proposal" icon={<FileText size={13} />} disabled={Boolean(busy)} onClick={() => onProposal(lead.id)} />
              <SmallButton label="Project" icon={<FolderPlus size={13} />} disabled={Boolean(busy)} onClick={() => onProject(lead.id)} />
            </div>
          </article>
        )) : <Empty text="No leads stored." />}
      </div>
    </Panel>
  );
}

function OutreachComposer({ form, setForm, selectedLead, leads, busy, onSubmit }) {
  return (
    <Panel title="Cold Draft" icon={<MailCheck size={15} />}>
      <form className="grid gap-2 lg:grid-cols-[220px_minmax(0,1fr)_180px] lg:items-end" onSubmit={onSubmit}>
        <Select label="Lead" value={form.lead_id || selectedLead?.id || ""} onChange={(value) => setForm({ ...form, lead_id: value })}>
          <option value="">Select lead</option>
          {leads.map((lead) => <option value={lead.id} key={lead.id}>{lead.company || lead.name}</option>)}
        </Select>
        <Input label="Offer" value={form.service_offer} onChange={(value) => setForm({ ...form, service_offer: value })} />
        <ActionButton icon={<MailCheck size={14} />} label="Draft" active busy={busy === "draft"} />
        <Input label="Portfolio" value={form.portfolio_url} onChange={(value) => setForm({ ...form, portfolio_url: value })} />
        <Input label="Call To Action" value={form.call_to_action} onChange={(value) => setForm({ ...form, call_to_action: value })} className="lg:col-span-2" />
      </form>
    </Panel>
  );
}

function OutreachQueue({ outreach, selected, busy, onToggle, onApprove, onSend }) {
  const rows = outreach.filter((item) => ["draft", "approved", "failed"].includes(item.status)).slice(0, 16);
  return (
    <Panel title="Outreach Queue" icon={<Send size={15} />} count={rows.length}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <button className="inline-flex min-h-9 items-center gap-2 rounded-[4px] border border-[#405063] bg-[#101820] px-3 text-[12px] font-bold text-white disabled:opacity-50" type="button" onClick={onApprove} disabled={!selected.length || Boolean(busy)}>
          {busy === "approve" ? <Loader2 className="animate-spin" size={14} /> : <CheckSquare size={14} />}
          Approve Selected
        </button>
        <button className="inline-flex min-h-9 items-center gap-2 rounded-[4px] border border-[#7aa6d8] bg-[#9fcaff] px-3 text-[12px] font-extrabold text-[#071421] disabled:opacity-50" type="button" onClick={onSend} disabled={!selected.length || Boolean(busy)}>
          {busy === "send" ? <Loader2 className="animate-spin" size={14} /> : <Send size={14} />}
          Send Selected
        </button>
        <span className="font-mono text-[11px] text-friday-muted">{selected.length} selected</span>
      </div>
      <div className="grid gap-2">
        {rows.length ? rows.map((item) => (
          <article className="grid gap-3 rounded-[5px] border border-[#34404d] bg-[#101820] p-3 lg:grid-cols-[28px_minmax(0,1fr)_110px]" key={item.id}>
            <button className="mt-1 grid h-7 w-7 place-items-center rounded-[4px] border border-[#405063] bg-[#151d26] text-friday-accent" type="button" onClick={() => onToggle(item.id)} aria-label={`Select outreach ${item.id}`}>
              {selected.includes(item.id) ? <CheckSquare size={17} /> : <Square size={17} />}
            </button>
            <div className="min-w-0">
              <div className="flex min-w-0 items-center gap-2">
                <strong className="truncate text-[13px] text-white">{item.subject || `Draft #${item.id}`}</strong>
                <span className="shrink-0 rounded-[4px] border border-[#405063] px-2 py-0.5 font-mono text-[10px] text-[#dce8f7]">{item.channel}</span>
              </div>
              <p className="mt-2 whitespace-pre-wrap text-[12px] leading-relaxed text-[#cbd8e6]">{item.body}</p>
            </div>
            <div className="flex items-start justify-end">
              <StatusPill value={item.status} />
            </div>
          </article>
        )) : <Empty text="No outreach drafts waiting." />}
      </div>
    </Panel>
  );
}

function ProjectInvoiceBoard({ projects, invoices }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel title="Client Projects" icon={<FolderPlus size={15} />} count={projects.length}>
        <MiniRows rows={projects.map((item) => ({ id: item.id, title: item.name, detail: item.root, status: item.status }))} empty="No client projects." />
      </Panel>
      <Panel title="Invoices" icon={<Receipt size={15} />} count={invoices.length}>
        <MiniRows rows={invoices.map((item) => ({ id: item.id, title: `${item.client_name} ${Number(item.amount || 0).toFixed(2)} ${item.currency}`, detail: item.path || item.client_email, status: item.status }))} empty="No invoices." />
      </Panel>
    </div>
  );
}

function MiniRows({ rows, empty }) {
  return (
    <div className="grid gap-2">
      {rows.length ? rows.slice(0, 8).map((item) => (
        <div className="grid min-h-[52px] grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-[4px] border border-[#34404d] bg-[#101820] px-3" key={item.id}>
          <div className="min-w-0">
            <strong className="block truncate text-[13px] text-white">{item.title}</strong>
            <span className="mt-1 block truncate text-[11px] text-friday-muted">{item.detail}</span>
          </div>
          <StatusPill value={item.status} />
        </div>
      )) : <Empty text={empty} />}
    </div>
  );
}

function Panel({ title, icon, count, children }) {
  return (
    <section className="rounded-[6px] border border-friday-line bg-[#151b22]">
      <header className="flex min-h-[46px] items-center gap-2 border-b border-friday-line px-3">
        <span className="text-friday-accent">{icon}</span>
        <h2 className="text-[14px] font-extrabold text-white">{title}</h2>
        {count != null ? <span className="ml-auto rounded-[4px] border border-[#405063] bg-[#202936] px-2 py-0.5 font-mono text-[10px] text-[#dce8f7]">{count}</span> : null}
      </header>
      <div className="p-3">{children}</div>
    </section>
  );
}

function Input({ label, value, onChange, type = "text", required = false, className = "" }) {
  return (
    <label className={`grid gap-1 ${className}`}>
      <span className="font-mono text-[10px] uppercase tracking-[.08em] text-friday-muted">{label}</span>
      <input className="min-h-10 rounded-[4px] border border-[#405063] bg-[#0d141b] px-3 text-[13px] text-white outline-none focus:border-friday-accent" type={type} value={value} onChange={(event) => onChange(event.target.value)} required={required} />
    </label>
  );
}

function TextArea({ label, value, onChange }) {
  return (
    <label className="grid gap-1">
      <span className="font-mono text-[10px] uppercase tracking-[.08em] text-friday-muted">{label}</span>
      <textarea className="min-h-[84px] resize-y rounded-[4px] border border-[#405063] bg-[#0d141b] px-3 py-2 text-[13px] text-white outline-none focus:border-friday-accent" value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function Select({ label, value, onChange, children }) {
  return (
    <label className="grid gap-1">
      <span className="font-mono text-[10px] uppercase tracking-[.08em] text-friday-muted">{label}</span>
      <select className="min-h-10 rounded-[4px] border border-[#405063] bg-[#0d141b] px-3 text-[13px] text-white outline-none focus:border-friday-accent" value={value} onChange={(event) => onChange(event.target.value)}>
        {children}
      </select>
    </label>
  );
}

function ActionButton({ icon, label, active, busy }) {
  return (
    <button className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-[4px] border px-3 text-[12px] font-extrabold disabled:opacity-50 ${active ? "border-[#9fcaff] bg-[#9fcaff] text-[#061420]" : "border-friday-line bg-[#101820] text-white"}`} type="submit" disabled={Boolean(busy)}>
      {busy ? <Loader2 className="animate-spin" size={14} /> : icon}
      {label}
    </button>
  );
}

function SmallButton({ icon, label, disabled, onClick }) {
  return (
    <button className="inline-flex min-h-8 items-center justify-center gap-1 rounded-[4px] border border-[#405063] bg-[#151d26] px-2 text-[11px] font-bold text-[#e6f0fb] disabled:opacity-50" type="button" disabled={disabled} onClick={onClick}>
      {icon}
      {label}
    </button>
  );
}

function StatusPill({ value }) {
  const status = String(value || "unknown").toLowerCase();
  const tone = status === "sent" || status === "paid" || status === "active" ? "border-[#315c48] bg-[#163126] text-[#a4f0c1]" : status === "approved" ? "border-[#41628a] bg-[#142237] text-[#9fcaff]" : status === "failed" ? "border-[#6d3942] bg-[#27171d] text-[#ffb2bc]" : "border-[#5c4327] bg-[#261c11] text-[#ffc98c]";
  return <span className={`shrink-0 rounded-[4px] border px-2 py-1 font-mono text-[10px] ${tone}`}>{status}</span>;
}

function Empty({ text }) {
  return <div className="rounded-[4px] border border-[#34404d] bg-[#101820] px-3 py-5 text-center text-[12px] text-friday-muted">{text}</div>;
}

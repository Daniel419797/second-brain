"use client";

import { AlertTriangle, Bell, Check, CheckCheck, Loader2, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "unread", label: "Unread" },
  { id: "high", label: "High Severity" }
];

export function NotificationsView() {
  const { api, data, refresh, interfaceFor } = useDashboard();
  const copy = interfaceFor?.("notifications") || {};
  const [items, setItems] = useState(data.notifications?.items || []);
  const [summary, setSummary] = useState(data.notifications || null);
  const [filter, setFilter] = useState("all");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setBusy("refresh");
    setMessage("");
    try {
      const [rows, nextSummary] = await Promise.all([
        api("/notifications?limit=80"),
        api("/notifications/summary")
      ]);
      setItems(Array.isArray(rows) ? rows : []);
      setSummary(nextSummary || null);
    } catch (err) {
      setMessage(err.message || copy?.empty?.notifications || "Notifications could not be loaded.");
    } finally {
      setBusy("");
    }
  }, [api, copy?.empty?.notifications]);

  useEffect(() => {
    if (data.notifications?.items) setItems(data.notifications.items);
    if (data.notifications) setSummary(data.notifications);
  }, [data.notifications]);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    if (filter === "unread") return items.filter((item) => lower(item.status) !== "read");
    if (filter === "high") return items.filter((item) => Number(item.severity || 0) >= 3);
    return items;
  }, [filter, items]);

  async function markOne(item, status = "read") {
    setBusy(`mark-${item.id}`);
    setMessage("");
    try {
      const updated = await api(`/notifications/${item.id}/mark`, {
        method: "POST",
        body: JSON.stringify({ status })
      });
      setItems((rows) => rows.map((row) => Number(row.id) === Number(item.id) ? updated : row));
      setMessage(status === "read" ? "Friday marked that signal read." : "Friday updated that signal.");
      void refresh();
    } catch (err) {
      setMessage(err.message || "Notification could not be updated.");
    } finally {
      setBusy("");
    }
  }

  async function markAllRead() {
    setBusy("mark-all");
    setMessage("");
    try {
      const result = await api("/notifications/mark-all-read", { method: "POST", body: JSON.stringify({}) });
      setItems((rows) => rows.map((item) => ({ ...item, status: "read" })));
      setSummary((current) => ({ ...(current || {}), unread_count: 0 }));
      setMessage(`${result.updated || 0} notification(s) marked read.`);
      void refresh();
    } catch (err) {
      setMessage(err.message || "Notifications could not be marked read.");
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="grid w-full max-w-[980px] min-w-0 content-start gap-4 text-[#eaf2fb]" aria-label="Notifications">
      <header className="flex min-w-0 flex-wrap items-end gap-3">
        <div className="min-w-0">
          <h1 className="m-0 text-[26px] font-extrabold leading-tight text-white">{copy?.title || "Notifications"}</h1>
          <p className="mt-1 text-[13px] text-friday-muted">{summary?.summary || copy?.subtitle || "System, phone, safety, and workflow notifications."}</p>
        </div>
        <div className="ml-auto flex flex-wrap gap-2">
          <button className="inline-flex min-h-9 items-center gap-2 rounded-[4px] border border-friday-line bg-[#151b22] px-3 text-[12px] font-bold text-white hover:border-friday-accent disabled:opacity-50" type="button" onClick={load} disabled={Boolean(busy)}>
            {busy === "refresh" ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />}
            {copy?.labels?.refresh || "Refresh"}
          </button>
          <button className="inline-flex min-h-9 items-center gap-2 rounded-[4px] border border-friday-blue bg-friday-blue px-3 text-[12px] font-extrabold text-[#061420] disabled:opacity-50" type="button" onClick={markAllRead} disabled={Boolean(busy) || !items.length}>
            {busy === "mark-all" ? <Loader2 className="animate-spin" size={14} /> : <CheckCheck size={14} />}
            {copy?.actions?.find?.((action) => action.id === "mark-all-read")?.label || "Mark All Read"}
          </button>
        </div>
      </header>

      <div className="grid gap-3 md:grid-cols-3">
        <Metric label="Unread" value={summary?.unread_count ?? items.filter((item) => lower(item.status) !== "read").length} />
        <Metric label="Total" value={summary?.total_count ?? items.length} />
        <Metric label="High Severity" value={items.filter((item) => Number(item.severity || 0) >= 3).length} />
      </div>

      <div className="flex flex-wrap gap-2">
        {FILTERS.map((item) => (
          <button className={`min-h-8 rounded-[999px] border px-3 text-[12px] font-bold ${filter === item.id ? "border-friday-accent bg-[#172334] text-friday-accent" : "border-friday-line bg-[#151b22] text-[#dce6f2] hover:border-friday-accent"}`} type="button" onClick={() => setFilter(item.id)} key={item.id}>
            {item.label}
          </button>
        ))}
      </div>

      {message ? <div className="rounded-[4px] border border-[#405063] bg-[#101820] px-4 py-3 text-[13px] text-[#dce9f8]">{message}</div> : null}

      <div className="grid gap-3">
        {filtered.length ? filtered.map((item) => (
          <NotificationCard item={item} busy={busy === `mark-${item.id}`} onRead={() => markOne(item, "read")} key={item.id || `${item.title}-${item.timestamp}`} />
        )) : (
          <div className="grid min-h-[220px] place-items-center rounded-[6px] border border-friday-line bg-[#151b22] px-6 text-center text-[13px] text-friday-muted">
            {copy?.empty?.notifications || "Friday has no signal matching this filter."}
          </div>
        )}
      </div>
    </section>
  );
}

function NotificationCard({ item, busy, onRead }) {
  const high = Number(item.severity || 0) >= 3;
  const unread = lower(item.status) !== "read";
  return (
    <article className={`grid gap-3 rounded-[6px] border bg-[#151b22] p-4 ${high ? "border-[#77424b]" : unread ? "border-[#45678c]" : "border-friday-line"}`}>
      <header className="flex min-w-0 items-start gap-3">
        <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-[4px] border ${high ? "border-[#77424b] bg-[#2a171d] text-[#ffb5b8]" : "border-[#45678c] bg-[#172334] text-friday-accent"}`}>
          {high ? <AlertTriangle size={17} /> : <Bell size={17} />}
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-[15px] font-extrabold text-white">{item.title || item.category || "Notification"}</h2>
          <p className="mt-1 text-[12px] leading-relaxed text-[#dce6f2]">{item.message || item.summary || "No notification body."}</p>
        </div>
        <span className="shrink-0 font-mono text-[11px] text-friday-muted">{timeAgo(item.updated_at || item.timestamp)}</span>
      </header>
      <footer className="flex flex-wrap items-center gap-2 border-t border-friday-line pt-3">
        <span className="rounded-[3px] border border-[#405063] bg-[#101820] px-2 py-1 font-mono text-[10px] uppercase text-[#dce6f2]">{item.source || item.category || "system"}</span>
        <span className="rounded-[3px] border border-[#405063] bg-[#101820] px-2 py-1 font-mono text-[10px] uppercase text-[#dce6f2]">severity {item.severity ?? 0}</span>
        <button className="ml-auto inline-flex min-h-8 items-center gap-2 rounded-[3px] border border-friday-line bg-[#10161d] px-3 text-[12px] text-white hover:border-friday-accent disabled:opacity-50" type="button" onClick={onRead} disabled={!unread || busy}>
          {busy ? <Loader2 className="animate-spin" size={13} /> : <Check size={13} />}
          {unread ? "Mark Read" : "Read"}
        </button>
      </footer>
    </article>
  );
}

function Metric({ label, value }) {
  return (
    <div className="rounded-[5px] border border-friday-line bg-[#151b22] px-4 py-3">
      <span className="block font-mono text-[10px] uppercase tracking-[.08em] text-friday-muted">{label}</span>
      <strong className="mt-1 block text-[24px] leading-none text-white">{value}</strong>
    </div>
  );
}

function lower(value) {
  return String(value || "").toLowerCase();
}

function timeAgo(value) {
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

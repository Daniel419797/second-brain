"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Bot, Cable, CheckCircle2, CircleDollarSign, Database, Loader2, PauseOctagon, RefreshCcw, ShieldCheck, Zap } from "lucide-react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";
import { wsUrl } from "@/services/fridayApi";

export function ControlRoomView() {
  const { api, data, token, refresh, interfaceFor } = useDashboard();
  const copy = interfaceFor?.("control-room") || {};
  const [room, setRoom] = useState(data.controlRoom || null);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const liveRef = useRef(false);

  const loadRoom = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setBusy("refresh");
    setMessage("");
    try {
      const payload = await api("/control-room/status");
      setRoom(payload);
      liveRef.current = true;
    } catch (err) {
      setMessage(err.message || "Control room failed to load.");
    } finally {
      if (!silent) setBusy("");
    }
  }, [api]);

  useEffect(() => {
    if (data.controlRoom) setRoom(data.controlRoom);
  }, [data.controlRoom]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    let socket = null;
    let reconnectTimer = null;
    const connect = () => {
      socket = new WebSocket(wsUrl("/ws/control-room", token));
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          liveRef.current = true;
          setRoom(payload);
        } catch {
          return;
        }
      };
      socket.onclose = () => {
        if (!cancelled) reconnectTimer = window.setTimeout(connect, 2500);
      };
      socket.onerror = () => {
        socket?.close();
      };
    };
    connect();
    return () => {
      cancelled = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [token]);

  useEffect(() => {
    if (!room) void loadRoom({ silent: true });
  }, [loadRoom, room]);

  async function emergencyStop() {
    setBusy("stop");
    setMessage("");
    try {
      const result = await api("/gateway/emergency-stop", { method: "POST", body: JSON.stringify({ reason: "Control room emergency stop" }) });
      setMessage(result.summary || "Emergency stop requested.");
      await loadRoom({ silent: true });
      void refresh();
    } catch (err) {
      setMessage(err.message || "Emergency stop failed.");
    } finally {
      setBusy("");
    }
  }

  const gateway = room?.gateway || data.gateway || {};
  const approvals = room?.approvals || data.approvalSummary || {};
  const tasks = room?.tasks || {};
  const agency = room?.agency || data.agency || {};
  const connectors = gateway.connectors || [];
  const highRisk = useMemo(() => (gateway.recent_events || []).filter((item) => item.risk === "high" || item.status === "pending_approval"), [gateway.recent_events]);

  return (
    <section className="friday-scroll h-full overflow-y-auto overflow-x-hidden bg-friday-bg px-4 py-4 text-[#eef5ff]" aria-label="Friday Control Room">
      <div className="mx-auto grid max-w-[1240px] gap-4">
        <header className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto_auto] lg:items-end">
          <div className="min-w-0">
            <h1 className="text-[26px] font-extrabold leading-tight text-white">{copy?.title || "Control Room"}</h1>
            <p className="mt-2 max-w-[820px] text-[13px] leading-relaxed text-friday-muted">{room?.summary || gateway.summary || copy?.subtitle || "Friday control room is loading."}</p>
          </div>
          <button className="inline-flex min-h-10 items-center justify-center gap-2 rounded-[5px] border border-friday-line bg-[#151b22] px-4 text-[13px] font-bold text-white" type="button" onClick={() => loadRoom()} disabled={Boolean(busy)}>
            {busy === "refresh" ? <Loader2 className="animate-spin" size={15} /> : <RefreshCcw size={15} />}
            {copy?.labels?.refresh || "Refresh"}
          </button>
          <button className="inline-flex min-h-10 items-center justify-center gap-2 rounded-[5px] border border-[#7a3135] bg-[#2a161a] px-4 text-[13px] font-bold text-[#ffb5b8]" type="button" onClick={emergencyStop} disabled={Boolean(busy)}>
            {busy === "stop" ? <Loader2 className="animate-spin" size={15} /> : <PauseOctagon size={15} />}
            {copy?.actions?.find?.((action) => action.id === "emergency-stop")?.label || "Stop"}
          </button>
        </header>

        {message ? <div className="rounded-[5px] border border-[#405063] bg-[#101820] px-4 py-3 text-[13px] text-[#dce9f8]">{message}</div> : null}

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <Metric icon={<Cable size={16} />} label="Connectors" value={gateway.enabled_count || 0} detail={`${gateway.configured_count || 0} configured`} />
          <Metric icon={<Bot size={16} />} label="Tasks" value={tasks.active || 0} detail={`${tasks.total || 0} total`} />
          <Metric icon={<ShieldCheck size={16} />} label="Approvals" value={approvals.count || 0} detail="review gates" />
          <Metric icon={<CircleDollarSign size={16} />} label="Profit" value={Number(agency.finance?.profit || 0).toFixed(0)} detail={agency.finance?.currency || "USD"} />
          <Metric icon={<Zap size={16} />} label="Reliability" value={Math.round(Number(room?.reliability?.latest_score?.overall || room?.reliability?.overall || 0))} detail="score" />
        </div>

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(360px,.8fr)]">
          <Panel title="Connector Matrix" icon={<Cable size={15} />}>
            <div className="grid gap-2 md:grid-cols-2">
              {connectors.slice(0, 12).map((connector) => <ConnectorRow connector={connector} key={connector.key} />)}
            </div>
          </Panel>

          <Panel title="High-Risk Queue" icon={<AlertTriangle size={15} />}>
            <div className="grid gap-2">
              {highRisk.length ? highRisk.slice(0, 6).map((event) => <EventRow event={event} key={event.id} />) : <Empty text={copy?.empty?.highRisk || "Friday has no gated gateway event in this control window."} />}
            </div>
          </Panel>
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          <ListPanel title="Agents" icon={<Bot size={15} />} rows={agentRows(room, copy)} />
          <ListPanel title="Costs And Proof" icon={<Database size={15} />} rows={proofRows(room, copy)} />
          <ListPanel title="Recent Errors" icon={<AlertTriangle size={15} />} rows={(room?.errors || []).map((item) => item.summary || item.action || item.category)} empty={copy?.empty?.errors || "No recent failed audit events."} />
        </div>
      </div>
    </section>
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

function Panel({ title, icon, children }) {
  return (
    <section className="rounded-[5px] border border-friday-line bg-[#151b22] p-4">
      <div className="mb-3 flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-[.08em] text-white">{icon}{title}</div>
      {children}
    </section>
  );
}

function ConnectorRow({ connector }) {
  const ready = Boolean(connector.configured && connector.enabled);
  return (
    <div className="grid min-h-[58px] grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-[4px] border border-[#303b48] bg-[#101820] px-3">
      <div className="min-w-0">
        <strong className="block truncate text-[13px] text-white">{connector.name}</strong>
        <span className="mt-1 block truncate font-mono text-[10px] text-friday-muted">{connector.category} / {connector.trust_level}</span>
      </div>
      <span className={`inline-flex items-center gap-1.5 rounded-[3px] border px-2 py-1 font-mono text-[10px] ${ready ? "border-[#315c48] bg-[#163126] text-[#90efc9]" : "border-[#5c4327] bg-[#261c11] text-[#ffc98c]"}`}>
        {ready ? <CheckCircle2 size={11} /> : <AlertTriangle size={11} />}
        {ready ? "ready" : "setup"}
      </span>
    </div>
  );
}

function EventRow({ event }) {
  return (
    <div className="rounded-[4px] border border-[#59323c] bg-[#20151a] p-3">
      <div className="flex min-w-0 items-center gap-2">
        <strong className="truncate text-[12px] text-white">{event.title}</strong>
        <span className="ml-auto shrink-0 font-mono text-[10px] text-[#ffb5b8]">{event.status}</span>
      </div>
      <p className="m-0 mt-2 line-clamp-2 text-[11px] leading-relaxed text-[#f0c8cc]">{event.connector} / {event.event_type} / {event.content || "No content"}</p>
    </div>
  );
}

function ListPanel({ title, icon, rows, empty }) {
  return (
    <Panel title={title} icon={icon}>
      <div className="grid gap-2">
        {rows.length ? rows.slice(0, 6).map((row, index) => <div className="truncate rounded-[4px] border border-[#303b48] bg-[#101820] px-3 py-2 text-[12px] text-[#dce6f2]" key={`${title}-${index}`}>{row}</div>) : <Empty text={empty || "Friday has no row for this control panel yet."} />}
      </div>
    </Panel>
  );
}

function Empty({ text }) {
  return <div className="grid min-h-[62px] place-items-center rounded-[4px] border border-[#303b48] bg-[#101820] px-3 text-center text-[12px] text-friday-muted">{text}</div>;
}

function agentRows(room, copy) {
  const workers = room?.workers || {};
  const tasks = room?.tasks || {};
  const pending = copy?.empty?.evidence || "Friday has not received this subsystem read yet";
  return [
    `Workers: ${workers.running ? "running" : "stopped"} (${workers.workers || 0})`,
    `Tasks: ${tasks.active || 0} active, ${tasks.pending || 0} pending`,
    `Cloud worker: ${room?.cloud_worker?.summary || pending}`,
    `Model router: ${room?.model_router?.summary || pending}`
  ];
}

function proofRows(room, copy) {
  const pending = copy?.empty?.evidence || "Friday has not received this proof read yet.";
  return [
    room?.proof?.summary || pending,
    room?.agency?.finance?.summary || pending,
    room?.skills?.summary || `${room?.skills?.enabled || 0} skill(s) enabled.`
  ];
}

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BellRing,
  Camera,
  Clipboard,
  Laptop,
  Loader2,
  Monitor,
  Plus,
  RefreshCw,
  Send,
  Smartphone,
  Tablet,
  Upload,
  Watch
} from "lucide-react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";
import { API_URL } from "@/lib/config";

export function AndroidView() {
  const { api, token, data, refresh, interfaceFor } = useDashboard();
  const copy = interfaceFor?.("android") || {};
  const [mesh, setMesh] = useState(data.android || null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [status, setStatus] = useState("");
  const [selectedId, setSelectedId] = useState("");

  const loadAndroid = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    setStatus("");
    try {
      const payload = await api("/android/device-mesh");
      setMesh(payload);
    } catch (err) {
      setStatus(err.message || "Android device mesh could not be loaded.");
    } finally {
      if (!silent) setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    loadAndroid();
    const interval = window.setInterval(() => loadAndroid({ silent: true }), 15000);
    return () => window.clearInterval(interval);
  }, [loadAndroid]);

  const devices = useMemo(() => normalizeDevices(mesh), [mesh]);
  const selectedDevice = devices.find((item) => item.id === selectedId) || devices[0] || null;
  const captures = useMemo(() => normalizeCaptures(mesh), [mesh]);
  const telemetry = useMemo(() => telemetryLines(mesh), [mesh]);
  const nodeCount = Math.max(1, Number(mesh?.active_nodes || 1));

  useEffect(() => {
    if (!selectedId && devices[0]?.id) setSelectedId(devices[0].id);
  }, [devices, selectedId]);

  async function runAction(key, fn, fallback) {
    if (busy) return;
    setBusy(key);
    setStatus("");
    try {
      const result = await fn();
      setStatus(result?.summary || fallback);
      await loadAndroid({ silent: true });
      await refresh();
    } catch (err) {
      setStatus(err.message || `${fallback} failed.`);
    } finally {
      setBusy("");
    }
  }

  function addDevice() {
    const name = window.prompt("Android device name", "Android phone");
    if (!name) return;
    const deviceId = window.prompt("Stable device ID", slugify(name)) || "";
    runAction(
      "add",
      () =>
        api("/android-companion/app/register", {
          method: "POST",
          body: JSON.stringify({
            name,
            device_id: deviceId,
            capabilities: ["notification_sync", "clipboard_sync", "file_transfer_metadata", "camera_frame_metadata"],
            status: { source: "dashboard", online: true }
          })
        }),
      "Android device registered."
    );
  }

  function forceSync() {
    runAction("sync", () => api("/android/device-mesh/sync", { method: "POST", body: JSON.stringify({}) }), "Android mesh synced.");
  }

  function ringDevice() {
    runAction("ring", () => api("/phone/ring", { method: "POST", body: JSON.stringify({ message: "Friday is pinging this Android device." }) }), "Ring request sent.");
  }

  function pushNotification() {
    const message = window.prompt("Notification message", "Friday mission update is ready.");
    if (!message) return;
    runAction(
      "notify",
      () =>
        api("/phone/notify", {
          method: "POST",
          body: JSON.stringify({ title: "Friday", message, priority: "high", tags: "robot,phone" })
        }),
      "Notification pushed to Android."
    );
  }

  function uploadPayload() {
    const localPath = window.prompt("Local file path to send to Android", "");
    if (!localPath) return;
    runAction(
      "upload",
      () =>
        api("/phone/files/push", {
          method: "POST",
          body: JSON.stringify({ local_path: localPath, phone_path: "/sdcard/Download/" })
        }),
      "Payload upload requested."
    );
  }

  function syncClipboard() {
    const text = window.prompt("Clipboard text to sync to Android", "");
    if (!text) return;
    runAction("clipboard", () => api("/phone/clipboard", { method: "POST", body: JSON.stringify({ text }) }), "Clipboard sync requested.");
  }

  function handoffToPc() {
    runAction(
      "handoff",
      () =>
        api("/device-mesh/continue-on-laptop", {
          method: "POST",
          body: JSON.stringify({
            title: "Android dashboard handoff",
            source_device: selectedDevice?.device_id || "android",
            target_device: "laptop",
            payload: { source: "android_dashboard", selected_device: selectedDevice?.name || "" }
          })
        }),
      "Handoff queued for PC."
    );
  }

  return (
    <section className="min-h-full bg-friday-bg text-[#eaf2fb]" aria-label="Android Device Mesh">
      <main className="grid min-w-0 content-start gap-4">
        <header className="flex min-h-[54px] min-w-0 flex-wrap items-start gap-3">
          <div className="min-w-0 max-w-[520px]">
            <h2 className="m-0 text-[25px] font-extrabold tracking-normal text-white">{copy?.title || "Android Device Mesh"}</h2>
            <p className="mt-1 text-[17px] leading-snug text-[#c5d0de]">
              {copy?.subtitle || `Synchronizing high-stakes intelligence across ${nodeCount} active terminal node${nodeCount === 1 ? "" : "s"}.`}
            </p>
          </div>
          <div className="ml-auto flex shrink-0 flex-wrap items-center justify-end gap-2">
            <ToolbarButton icon={busy === "add" ? <Loader2 className="animate-spin" size={14} /> : <Plus size={14} />} label="Add New Device" onClick={addDevice} disabled={Boolean(busy)} />
            <ToolbarButton icon={busy === "sync" ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />} label="Force Global Sync" onClick={forceSync} disabled={Boolean(busy)} primary />
          </div>
        </header>

        <div className="grid min-w-0 gap-4 xl:grid-cols-[340px_minmax(380px,1fr)]">
          <RegisteredNodes devices={devices} selectedId={selectedDevice?.id || ""} loading={loading} onSelect={setSelectedId} />
          <MeshMap selectedDevice={selectedDevice} mesh={mesh} loading={loading} />
        </div>

        <ActionDeck
          busy={busy}
          onRing={ringDevice}
          onNotify={pushNotification}
          onUpload={uploadPayload}
          onClipboard={syncClipboard}
          onHandoff={handoffToPc}
        />

        <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,2fr)_270px]">
          <RecentCaptures captures={captures} copy={copy} token={token} />
          <TelemetryPanel lines={telemetry} copy={copy} loading={loading} />
        </div>

        {status ? (
          <div className="fixed bottom-5 right-5 z-20 max-w-[380px] rounded-[4px] border border-[#45678c] bg-[#9fcaff] px-4 py-3 text-[13px] font-semibold text-[#07111d] shadow-[0_16px_40px_rgba(0,0,0,.32)]">
            {status}
          </div>
        ) : null}
      </main>
    </section>
  );
}

function RegisteredNodes({ devices, selectedId, loading, onSelect }) {
  return (
    <Panel className="min-h-[484px] p-4">
      <PanelTitle icon={<Monitor size={13} />} title="Registered Mesh Nodes" />
      <div className="mt-4 grid gap-3">
        {loading ? (
          <NodeSkeleton />
        ) : devices.length ? (
          devices.slice(0, 5).map((device) => <DeviceCard device={device} selected={device.id === selectedId} onSelect={() => onSelect(device.id)} key={device.id} />)
        ) : (
          <div className="grid min-h-[156px] place-items-center border border-dashed border-[#3d4857] bg-[#10161d] p-4 text-center">
            <div>
              <Smartphone className="mx-auto text-friday-accent" size={26} />
              <strong className="mt-3 block text-[13px] text-white">No registered Android nodes</strong>
              <p className="mt-2 text-[12px] leading-relaxed text-[#c2cedd]">Register the companion app, connect ADB, or add a phone bridge device.</p>
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}

function DeviceCard({ device, selected, onSelect }) {
  const Icon = deviceIcon(device.kind);
  return (
    <button
      className={`grid min-h-[118px] w-full grid-cols-[48px_minmax(0,1fr)_auto] gap-3 rounded-[4px] border p-3 text-left transition-colors ${
        selected ? "border-friday-accent bg-[#2a303a] shadow-[inset_4px_0_0_#9fcaff]" : "border-[#34404d] bg-[#1b2028] opacity-70 hover:border-[#60758d] hover:opacity-100"
      }`}
      type="button"
      onClick={onSelect}
    >
      <span className="grid h-12 w-12 place-items-center border border-[#3d4857] bg-[#111820] text-friday-accent">
        <Icon size={24} />
      </span>
      <span className="min-w-0">
        <strong className="block truncate text-[16px] font-extrabold text-white">{device.name}</strong>
        <span className="mt-1 block truncate text-[13px] font-semibold text-[#d7e1ee]">{device.model}</span>
        <span className="mt-1 block truncate text-[12px] text-[#9aa8ba]">
          <span className={`mr-1.5 inline-block h-2 w-2 rounded-full ${device.connected ? "bg-[#81a5cc]" : "bg-[#606a76]"}`} />
          {device.connected ? "Connected" : "Standby"} - {device.network}
        </span>
      </span>
      <span className="grid justify-items-end gap-1">
        <b className="font-mono text-[16px] text-friday-accent">{device.batteryLabel}</b>
        <span className="font-mono text-[10px] uppercase text-[#9aa8ba]">Battery</span>
      </span>
      <span className="col-span-3 grid grid-cols-2 gap-2 border-t border-[#3d4857] pt-3 font-mono text-[10px] uppercase text-[#dfe8f4]">
        <span className="border border-[#3d4857] bg-[#151b22] px-2 py-2">ID: {device.shortId}</span>
        <span className="border border-[#3d4857] bg-[#151b22] px-2 py-2 text-right">Last Seen: {device.lastSeen}</span>
      </span>
    </button>
  );
}

function MeshMap({ selectedDevice, mesh, loading }) {
  const latency = latencyLabel(mesh);
  const throughput = mesh?.phone?.adb_connected ? "ADB" : mesh?.phone?.ntfy_configured ? "NTFY" : "STANDBY";
  return (
    <Panel className="relative min-h-[484px] overflow-hidden p-0">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(159,202,255,.08),transparent_55%)]" />
      <div className="relative h-full min-h-[484px]">
        <div className="absolute left-[14%] top-[28%] h-[104px] w-[2px] rotate-[15deg] border-l border-dashed border-friday-accent/70" />
        <div className="absolute left-[23%] top-[31%] h-[104px] w-[2px] -rotate-[17deg] border-l border-dashed border-friday-accent/30" />
        <div className="absolute left-1/2 top-[62px] grid h-[118px] w-[160px] -translate-x-1/2 place-items-center rounded-[6px] border-2 border-friday-accent bg-[#2f343d] shadow-[0_0_40px_rgba(159,202,255,.09)]">
          <div className="grid justify-items-center gap-3">
            <Monitor size={42} className="text-friday-accent" />
            <strong className="font-mono text-[12px] uppercase text-white">Friday Command</strong>
          </div>
        </div>
        <div className={`absolute left-[19%] top-[238px] grid h-[142px] w-[86px] rotate-[-11deg] place-items-center rounded-[10px] border-2 ${selectedDevice ? "border-friday-accent bg-[#303640]" : "border-[#3d4857] bg-[#222831]"}`}>
          {selectedDevice ? <Smartphone size={34} className="text-friday-accent" /> : <Smartphone size={34} className="text-[#697687]" />}
        </div>
        <div className="absolute bottom-4 right-4 grid gap-2 font-mono text-[11px] uppercase text-[#dbe8f7]">
          <span className="border border-[#3d4857] bg-[#151b22]/90 px-3 py-2">Latency: <b className="text-friday-accent">{latency}</b></span>
          <span className="border border-[#3d4857] bg-[#151b22]/90 px-3 py-2">Throughput: <b className="text-friday-accent">{throughput}</b></span>
        </div>
        <div className="absolute left-6 top-5 font-mono text-[11px] uppercase tracking-[.16em] text-friday-accent">
          {loading ? "SYNCING_MESH" : selectedDevice ? selectedDevice.name : "NO_ANDROID_NODE"}
        </div>
      </div>
    </Panel>
  );
}

function ActionDeck({ busy, onRing, onNotify, onUpload, onClipboard, onHandoff }) {
  const actions = [
    { key: "ring", label: "Ring Device", icon: BellRing, onClick: onRing },
    { key: "notify", label: "Push Notification", icon: Send, onClick: onNotify },
    { key: "upload", label: "Upload Payload", icon: Upload, onClick: onUpload },
    { key: "clipboard", label: "Sync Clipboard", icon: Clipboard, onClick: onClipboard },
    { key: "handoff", label: "Handoff to PC", icon: Laptop, onClick: onHandoff, primary: true }
  ];
  return (
    <div className="grid min-w-0 grid-cols-2 gap-4 md:grid-cols-5">
      {actions.map((action) => {
        const Icon = action.icon;
        const active = busy === action.key;
        return (
          <button
            className={`grid min-h-[178px] place-items-center border p-4 text-center transition-colors disabled:opacity-60 ${
              action.primary ? "border-friday-blue bg-friday-blue text-[#04111d] hover:bg-[#55b4ff]" : "border-friday-line bg-[#151b22] text-[#eef5ff] hover:border-friday-accent"
            }`}
            type="button"
            onClick={action.onClick}
            disabled={Boolean(busy)}
            key={action.key}
          >
            <span className="grid justify-items-center gap-4">
              {active ? <Loader2 className="animate-spin" size={30} /> : <Icon size={30} />}
              <span className="max-w-[110px] text-[20px] font-medium leading-tight">{action.label}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

function RecentCaptures({ captures, copy, token }) {
  return (
    <Panel className="min-h-[228px] p-4">
      <div className="flex items-center gap-3">
        <PanelTitle title="Recent Device Captures" />
        <a className="ml-auto text-[12px] font-semibold text-friday-accent hover:text-white" href="/vision">View All Intelligence</a>
      </div>
      <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {captures.slice(0, 3).map((item) => <CaptureTile item={item} token={token} key={item.id || item.name} />)}
        <div className="grid min-h-[118px] place-items-center border border-dashed border-[#4b5a6b] bg-[#303640] text-[#9aa8ba]">
          <Plus size={25} />
        </div>
      </div>
      {!captures.length ? <p className="mt-3 text-[12px] text-friday-muted">{copy?.empty?.handoffs || "Friday has no Android capture in this read yet."}</p> : null}
    </Panel>
  );
}

function CaptureTile({ item, token }) {
  const src = assetUrl(item.image_url || item.url, token);
  return (
    <article className="min-w-0 overflow-hidden border border-[#3d4857] bg-[#090d12]">
      <div className="grid h-[118px] place-items-center bg-[#0b1117]">
        {src ? <img className="h-full w-full object-cover grayscale" src={src} alt={item.name || "Android capture"} /> : <Camera size={22} className="text-friday-muted" />}
      </div>
    </article>
  );
}

function TelemetryPanel({ lines, copy, loading }) {
  return (
    <Panel className="min-h-[228px] p-4">
      <PanelTitle title="Real-time Telemetry" />
      <div className="mt-5 grid gap-3 font-mono text-[13px] leading-tight text-[#c5d0de]">
        {loading ? (
          <span className="text-friday-accent">Loading mesh telemetry...</span>
        ) : lines.length ? (
          lines.slice(0, 5).map((line, index) => (
            <div className="grid grid-cols-[68px_minmax(0,1fr)] gap-3" key={`${index}-${line.text}`}>
              <span className="text-[#9aa8ba]">{line.time}</span>
              <b className="text-friday-accent">{line.text}</b>
            </div>
          ))
        ) : (
          <span className="text-[#9aa8ba]">{copy?.empty?.handoffs || "Friday has no Android telemetry event in this read yet."}</span>
        )}
      </div>
    </Panel>
  );
}

function ToolbarButton({ icon, label, primary, disabled, onClick }) {
  return (
    <button
      className={`inline-flex min-h-[64px] min-w-[150px] items-center justify-center gap-2 rounded-[2px] border px-4 text-[13px] font-bold leading-tight transition-colors disabled:opacity-50 ${
        primary ? "border-[#97c8f8] bg-[#97c8f8] text-[#05111d] hover:bg-[#b2d8ff]" : "border-friday-line bg-[#151b22] text-[#eaf2fb] hover:border-friday-accent"
      }`}
      type="button"
      disabled={disabled}
      onClick={onClick}
    >
      {icon}
      <span className="max-w-[88px]">{label}</span>
    </button>
  );
}

function NodeSkeleton() {
  return (
    <div className="grid min-h-[118px] animate-pulse grid-cols-[48px_minmax(0,1fr)] gap-3 rounded-[4px] border border-[#34404d] bg-[#1b2028] p-3">
      <span className="h-12 w-12 bg-[#303743]" />
      <span className="grid content-start gap-2">
        <span className="h-4 w-32 bg-[#303743]" />
        <span className="h-3 w-24 bg-[#303743]" />
        <span className="h-3 w-40 bg-[#303743]" />
      </span>
    </div>
  );
}

function Panel({ className = "", children }) {
  return <section className={`min-w-0 overflow-hidden border border-friday-line bg-[#151b22] ${className}`}>{children}</section>;
}

function PanelTitle({ icon, title }) {
  return (
    <h3 className="m-0 flex items-center gap-2 font-mono text-[12px] font-bold uppercase tracking-[.14em] text-[#aeb8c7]">
      {icon ? <span className="text-[#9aa8ba]">{icon}</span> : null}
      <span>{title}</span>
    </h3>
  );
}

function normalizeDevices(mesh) {
  const appDevices = mesh?.android?.app_devices || [];
  const phoneDevices = mesh?.phone_devices || [];
  const adbDevices = mesh?.phone?.adb_devices || [];
  const battery = mesh?.phone?.battery || {};
  const rows = [];
  for (const device of appDevices) {
    const status = device.status || {};
    rows.push({
      id: `app:${device.device_id}`,
      device_id: device.device_id,
      name: device.name || "Android companion",
      model: status.model || status.device_model || status.platform || "Terminal",
      kind: inferKind(device.name || status.model),
      connected: status.online !== false,
      network: status.network || status.connection || status.transport || "Companion app",
      battery: firstNumber(status.battery_level, status.battery, status.battery_percent),
      updated_at: device.updated_at
    });
  }
  for (const device of phoneDevices) {
    rows.push({
      id: `bridge:${device.id}`,
      device_id: device.adb_serial || `phone-${device.id}`,
      name: device.name || "Android phone",
      model: device.platform || "Terminal",
      kind: "phone",
      connected: Boolean(device.adb_serial || device.ntfy_topic || mesh?.phone?.adb_connected || mesh?.phone?.ntfy_configured),
      network: device.adb_serial ? "ADB" : device.ntfy_topic ? "ntfy" : "Phone bridge",
      battery: device.is_default ? firstNumber(battery.level) : null,
      updated_at: device.updated_at
    });
  }
  for (const device of adbDevices) {
    rows.push({
      id: `adb:${device.serial}`,
      device_id: device.serial,
      name: device.metadata?.model || "ADB Android",
      model: device.state || "Terminal",
      kind: "phone",
      connected: device.state === "device",
      network: device.metadata?.transport_id ? `ADB ${device.metadata.transport_id}` : "ADB",
      battery: firstNumber(battery.level),
      updated_at: mesh?.timestamp
    });
  }
  const seen = new Set();
  return rows
    .filter((item) => {
      const key = item.device_id || item.id;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .map((item) => ({
      ...item,
      batteryLabel: item.battery == null ? "--" : `${Math.round(item.battery)}%`,
      shortId: shortId(item.device_id || item.id),
      lastSeen: item.updated_at ? timeAgo(item.updated_at) : "Now"
    }));
}

function normalizeCaptures(mesh) {
  return (mesh?.captures || mesh?.android?.recent_files || []).filter(Boolean);
}

function telemetryLines(mesh) {
  const rows = [];
  const events = [...(mesh?.phone_events || []), ...(mesh?.android?.recent_events || []), ...(mesh?.commands || [])];
  for (const item of events) {
    rows.push({
      time: formatTime(item.timestamp || item.created_at || item.updated_at),
      text: telemetryText(item)
    });
  }
  if (mesh?.phone?.battery?.available) {
    rows.unshift({ time: formatTime(mesh.timestamp), text: `[BATT] ${mesh.phone.battery.level}% ${mesh.phone.battery.charging ? "charging" : "active"}` });
  }
  if (mesh?.sync?.summary) rows.unshift({ time: formatTime(mesh.timestamp), text: `[SYNC] ${trimText(mesh.sync.summary, 48)}` });
  return rows;
}

function telemetryText(item) {
  const label = String(item.command_type || item.action || item.kind || "mesh").replace(/_/g, " ").toUpperCase();
  return `[${label}] ${trimText(item.summary || item.title || "Android mesh event", 52)}`;
}

function deviceIcon(kind) {
  if (kind === "tablet") return Tablet;
  if (kind === "watch") return Watch;
  return Smartphone;
}

function inferKind(value) {
  const text = String(value || "").toLowerCase();
  if (text.includes("tab") || text.includes("tablet")) return "tablet";
  if (text.includes("watch")) return "watch";
  return "phone";
}

function firstNumber(...values) {
  for (const value of values) {
    const num = Number(value);
    if (Number.isFinite(num)) return num;
  }
  return null;
}

function latencyLabel(mesh) {
  if (mesh?.phone?.adb_connected) return "12ms";
  if (mesh?.phone?.ntfy_configured) return "remote";
  return "idle";
}

function assetUrl(path, token) {
  if (!path || !token) return "";
  if (/^https?:\/\//i.test(path)) return path;
  const separator = path.includes("?") ? "&" : "?";
  return `${API_URL}${path}${separator}token=${encodeURIComponent(token)}`;
}

function shortId(value) {
  const text = String(value || "android").replace(/\s+/g, "");
  if (text.length <= 8) return text.toUpperCase();
  return text.slice(0, 8).toUpperCase();
}

function slugify(value) {
  return String(value || "android-phone").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "android-phone";
}

function timeAgo(value) {
  const then = new Date(value).getTime();
  if (!Number.isFinite(then)) return "Now";
  const seconds = Math.max(1, Math.floor((Date.now() - then) / 1000));
  if (seconds < 60) return "Now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function formatTime(value) {
  const date = value ? new Date(value) : new Date();
  if (!Number.isFinite(date.getTime())) return "--:--";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

function trimText(value, limit) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, Math.max(0, limit - 1)).trim()}...`;
}

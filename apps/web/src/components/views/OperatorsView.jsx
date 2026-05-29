"use client";

import { Activity, Bot, BrainCircuit, Camera, CheckCircle2, Eye, Keyboard, Loader2, Monitor, Pause, Play, RefreshCw, Route, ScanLine, Square, Wand2, Zap } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";

const CONTROL_GROUPS = [
  ["Context", ["active_window", "mouse_position", "screen_size", "pc_awareness_snapshot", "inspect_screen", "inspect_browser", "inspect_accessibility", "screenshot"]],
  ["Pointer", ["click", "double_click", "right_click", "move_mouse", "scroll"]],
  ["Keyboard", ["type_text", "press_key", "hotkey", "wait"]],
  ["Vision", ["screen_step", "open_browser_debug"]]
];
const ACTION_LABELS = {
  active_window: "Window",
  mouse_position: "Mouse",
  screen_size: "Screen",
  pc_awareness_snapshot: "Snapshot",
  inspect_screen: "Inspect",
  inspect_browser: "DOM",
  inspect_accessibility: "UIA",
  screenshot: "Shot",
  click: "Click",
  double_click: "2x Click",
  right_click: "Right",
  move_mouse: "Move",
  scroll: "Scroll",
  type_text: "Type",
  press_key: "Key",
  hotkey: "Hotkey",
  wait: "Wait",
  screen_step: "Step",
  open_browser_debug: "Debug"
};

export function OperatorsView() {
  const { api, refresh, interfaceFor } = useDashboard();
  const copy = interfaceFor?.("operators") || {};
  const [operators, setOperators] = useState([]);
  const [skills, setSkills] = useState([]);
  const [status, setStatus] = useState({});
  const [control, setControl] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [selectedApp, setSelectedApp] = useState("");
  const [selectedSession, setSelectedSession] = useState(0);
  const [instruction, setInstruction] = useState("");
  const [target, setTarget] = useState("");
  const [textValue, setTextValue] = useState("");
  const [keyValue, setKeyValue] = useState("ctrl+l");
  const [url, setUrl] = useState("");
  const [x, setX] = useState("");
  const [y, setY] = useState("");
  const [amount, setAmount] = useState(-5);
  const [seconds, setSeconds] = useState(1);
  const [maxSteps, setMaxSteps] = useState(12);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [lastResult, setLastResult] = useState(null);
  const loadFallback = copy?.empty?.evidence || "Operator data could not be fully loaded.";

  useEffect(() => {
    if (!instruction.trim()) {
      const appLabel = selectedApp ? labelize(selectedApp) : "the active app";
      setInstruction(copy?.labels?.primaryInstruction || `Inspect ${appLabel} and tell me what Friday can safely do next.`);
    }
  }, [copy?.labels?.primaryInstruction, instruction, selectedApp]);

  const load = useCallback(async () => {
    setBusy("refresh");
    setMessage("");
    const results = await Promise.allSettled([
      api("/app-operators"),
      api("/operator-skills"),
      api("/operator-skills/status"),
      api(`/ui-control/status?app=${encodeURIComponent(selectedApp)}&limit=16`),
      api("/desktop/tasks?limit=12")
    ]);
    const [operatorRows, skillRows, skillStatus, controlStatus, taskRows] = results.map((result) => result.status === "fulfilled" ? result.value : null);
    setOperators(Array.isArray(operatorRows) ? operatorRows : []);
    setSkills(Array.isArray(skillRows) ? skillRows : []);
    setStatus(skillStatus || {});
    setControl(controlStatus || null);
    setTasks(Array.isArray(taskRows) ? taskRows : []);
    const active = controlStatus?.active_session || taskRows?.find?.((item) => ["active", "paused", "waiting_confirmation"].includes(String(item.status || "")));
    if (active?.id) setSelectedSession(Number(active.id));
    const failed = results.find((result) => result.status === "rejected");
    if (failed) setMessage(failed.reason?.message || loadFallback);
    setBusy("");
  }, [api, loadFallback, selectedApp]);

  useEffect(() => {
    void load();
  }, [load]);

  const apps = useMemo(() => appChoices(operators, skills, control?.discovered_apps, selectedApp), [operators, skills, control, selectedApp]);
  const selected = operators.find((item) => item.app === selectedApp || item.id === selectedApp || item.name === selectedApp) || skills.find((item) => item.app === selectedApp || item.id === selectedApp) || null;
  const activeTask = tasks.find((item) => Number(item.id) === Number(selectedSession)) || control?.active_session || tasks[0] || null;
  const hasTarget = Boolean(selectedApp);

  async function run(label, action, done) {
    setBusy(label);
    setMessage("");
    try {
      const result = await action();
      setLastResult(result || null);
      setMessage(result?.summary || result?.reply || result?.message || done || `${labelize(label)} complete.`);
      await load();
      void refresh();
    } catch (err) {
      setMessage(err.message || `${labelize(label)} failed.`);
      setBusy("");
    }
  }

  function controlAction(action, extra = {}) {
    const body = {
      action,
      app: selectedApp,
      instruction,
      target: target || selectedApp,
      text: textValue,
      key: keyValue,
      keys: keyValue,
      url,
      x: optionalNumber(x),
      y: optionalNumber(y),
      amount: Number(amount) || -5,
      seconds: Number(seconds) || 1,
      session_id: Number(selectedSession) || 0,
      max_steps: Number(maxSteps) || 12,
      ...extra
    };
    run(action, () => api("/ui-control/action", { method: "POST", body: JSON.stringify(body) }), `${ACTION_LABELS[action] || action} complete.`);
  }

  function startTask() {
    run("guided_task", () => api("/ui-control/task", { method: "POST", body: JSON.stringify({ action: "desktop_task", app: selectedApp, instruction, target, max_steps: Number(maxSteps) || 12 }) }), "Guided UI task started.");
  }

  function loadContext() {
    run("context", () => api("/ui-control/context", { method: "POST", body: JSON.stringify({ app: selectedApp, instruction }) }), "Context loaded.");
  }

  function openApp() {
    controlAction("open_app", { target: selectedApp });
  }

  function focusApp() {
    controlAction("focus_window", { target: target || selectedApp });
  }

  function sessionAction(action) {
    if (!selectedSession) return;
    controlAction(action, { target: String(selectedSession), session_id: Number(selectedSession) });
  }

  return (
    <section className="friday-scroll h-full overflow-y-auto overflow-x-hidden bg-friday-bg px-4 py-4 text-[#eaf2fb]" aria-label="App Operators">
      <div className="mx-auto grid w-full max-w-[1280px] content-start gap-4">
        <header className="flex min-w-0 flex-wrap items-end gap-3">
          <div className="min-w-0">
            <h1 className="m-0 text-[26px] font-extrabold leading-tight text-white">{copy?.title || "UI Control"}</h1>
            <p className="mt-1 text-[13px] text-friday-muted">{control?.summary || copy?.subtitle || "Friday is assembling the live app surface."}</p>
          </div>
          <button className="ml-auto inline-flex min-h-9 items-center gap-2 rounded-[4px] border border-friday-line bg-[#151b22] px-3 text-[12px] font-bold text-white hover:border-friday-accent disabled:opacity-50" type="button" onClick={load} disabled={Boolean(busy)}>
            {busy === "refresh" ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />}
            {copy?.labels?.refresh || "Refresh"}
          </button>
        </header>

        {message ? <div className="rounded-[4px] border border-[#405063] bg-[#101820] px-4 py-3 text-[13px] text-[#dce9f8]">{message}</div> : null}

        <div className="grid gap-3 md:grid-cols-4">
          <Metric icon={<Monitor size={15} />} label="Operators" value={operators.length || apps.length} />
          <Metric icon={<Route size={15} />} label="Skills" value={skills.length || status.operator_count || 0} />
          <Metric icon={<Activity size={15} />} label="Sessions" value={tasks.length || 0} />
          <Metric icon={<Eye size={15} />} label="Active" value={compactWindow(control?.active_window)} />
        </div>

        <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
          <Panel title="Targets" icon={<Monitor size={15} />}>
            <div className="grid gap-2">
              {apps.length ? apps.map((app) => (
                <button className={`grid min-h-[48px] grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-[4px] border px-3 text-left ${selectedApp === app ? "border-friday-accent bg-[#172334] text-friday-accent" : "border-[#303b48] bg-[#101820] text-white hover:border-friday-accent"}`} type="button" onClick={() => setSelectedApp(app)} key={app}>
                  <span className="truncate text-[13px] font-bold">{labelize(app)}</span>
                  <span className="font-mono text-[10px] uppercase text-friday-muted">{operatorKind(app, operators, skills, control?.discovered_apps)}</span>
                </button>
              )) : <div className="rounded-[4px] border border-dashed border-friday-line bg-[#101820] px-3 py-4 text-[12px] leading-relaxed text-friday-muted">{copy?.empty?.sessions || "No UI target came back from the backend yet."}</div>}
            </div>
          </Panel>

          <Panel title="Command Surface" icon={<Wand2 size={15} />}>
            <div className="grid gap-3">
              <div className="grid gap-3 lg:grid-cols-[190px_minmax(0,1fr)_100px]">
                <label className="grid gap-1">
                  <span className="font-mono text-[10px] uppercase text-friday-muted">App</span>
                  <select className="min-h-10 rounded-[4px] border border-[#405063] bg-[#0d141b] px-3 text-[13px] text-white outline-none focus:border-friday-accent" value={selectedApp} onChange={(event) => setSelectedApp(event.target.value)}>
                    {apps.length ? apps.map((app) => <option value={app} key={app}>{labelize(app)}</option>) : <option value="">No backend target</option>}
                  </select>
                </label>
                <label className="grid gap-1">
                  <span className="font-mono text-[10px] uppercase text-friday-muted">Instruction</span>
                  <input className="min-h-10 rounded-[4px] border border-[#405063] bg-[#0d141b] px-3 text-[13px] text-white outline-none focus:border-friday-accent" value={instruction} onChange={(event) => setInstruction(event.target.value)} maxLength={4000} />
                </label>
                <label className="grid gap-1">
                  <span className="font-mono text-[10px] uppercase text-friday-muted">Steps</span>
                  <input className="min-h-10 rounded-[4px] border border-[#405063] bg-[#0d141b] px-3 text-[13px] text-white outline-none focus:border-friday-accent" type="number" min="1" max="50" value={maxSteps} onChange={(event) => setMaxSteps(event.target.value)} />
                </label>
              </div>

              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
                <Action icon={<Monitor size={14} />} label="Open" busy={busy === "open_app"} disabled={Boolean(busy) || !hasTarget} onClick={openApp} />
                <Action icon={<ScanLine size={14} />} label="Focus" busy={busy === "focus_window"} disabled={Boolean(busy) || !hasTarget} onClick={focusApp} />
                <Action icon={<BrainCircuit size={14} />} label="Context" busy={busy === "context"} disabled={Boolean(busy) || !hasTarget} onClick={loadContext} />
                <Action icon={<Route size={14} />} label="Plan" busy={busy === "plan"} disabled={Boolean(busy) || !hasTarget || !instruction.trim()} onClick={() => controlAction("plan")} />
                <Action icon={<Play size={14} />} label="Run" busy={busy === "guided_task"} disabled={Boolean(busy) || !hasTarget || !instruction.trim()} onClick={startTask} primary />
              </div>

              <div className="grid gap-3 lg:grid-cols-4">
                <Input label="Target" value={target} onChange={setTarget} />
                <Input label="X" value={x} onChange={setX} type="number" />
                <Input label="Y" value={y} onChange={setY} type="number" />
                <Input label="Scroll" value={amount} onChange={setAmount} type="number" />
                <Input label="Text" value={textValue} onChange={setTextValue} />
                <Input label="Key/Hotkey" value={keyValue} onChange={setKeyValue} />
                <Input label="URL" value={url} onChange={setUrl} />
                <Input label="Wait" value={seconds} onChange={setSeconds} type="number" />
              </div>

              <div className="grid gap-3">
                {CONTROL_GROUPS.map(([group, actions]) => (
                  <div className="grid gap-2" key={group}>
                    <div className="font-mono text-[10px] font-bold uppercase text-friday-muted">{group}</div>
                    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
                      {actions.map((action) => (
                        <Action key={action} icon={iconFor(action)} label={ACTION_LABELS[action] || labelize(action)} busy={busy === action} disabled={Boolean(busy) || !hasTarget} onClick={() => controlAction(action)} />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </Panel>
        </div>

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
          <Panel title="Sessions" icon={<Activity size={15} />}>
            <div className="grid gap-3">
              <div className="flex flex-wrap gap-2">
                <Action icon={<Pause size={14} />} label="Pause" busy={busy === "desktop_task_pause"} disabled={Boolean(busy) || !selectedSession} onClick={() => sessionAction("desktop_task_pause")} />
                <Action icon={<Play size={14} />} label="Resume" busy={busy === "desktop_task_resume"} disabled={Boolean(busy) || !selectedSession} onClick={() => sessionAction("desktop_task_resume")} />
                <Action icon={<CheckCircle2 size={14} />} label="Confirm" busy={busy === "desktop_task_confirm"} disabled={Boolean(busy) || !selectedSession} onClick={() => sessionAction("desktop_task_confirm")} />
                <Action icon={<Square size={14} />} label="Cancel" busy={busy === "desktop_task_cancel"} disabled={Boolean(busy) || !selectedSession} onClick={() => sessionAction("desktop_task_cancel")} />
              </div>
              <div className="grid gap-2">
                {tasks.slice(0, 8).map((task) => (
                  <button className={`grid min-h-[62px] grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-[4px] border px-3 text-left ${Number(selectedSession) === Number(task.id) ? "border-friday-accent bg-[#172334]" : "border-[#303b48] bg-[#101820] hover:border-friday-accent"}`} type="button" onClick={() => setSelectedSession(Number(task.id))} key={task.id}>
                    <span className="min-w-0">
                  <strong className="block truncate text-[13px] text-white">#{task.id} {task.goal || copy?.empty?.sessions || "UI task"}</strong>
                      <span className="mt-1 block truncate text-[11px] text-friday-muted">{task.last_progress || task.pending_reason || `${task.current_step || 0}/${task.max_steps || 0} steps`}</span>
                    </span>
                    <span className="rounded-[3px] border border-[#405063] bg-[#202936] px-2 py-1 font-mono text-[10px] uppercase text-[#dce8f7]">{task.status || "ready"}</span>
                  </button>
                ))}
              </div>
            </div>
          </Panel>

          <Panel title="Evidence" icon={<Bot size={15} />}>
            <div className="grid gap-3">
              <MiniBlock label="Selected" value={selected || control?.operator || (selectedApp ? { app: selectedApp } : {})} />
              <MiniBlock label="Active Session" value={activeTask || {}} />
              <MiniBlock label="Last Result" value={lastResult || control || {}} />
            </div>
          </Panel>
        </div>

        <Panel title="Learned Operator Skills" icon={<Route size={15} />}>
          <div className="grid gap-2 md:grid-cols-2">
            {(skills.length ? skills : operators).length ? (skills.length ? skills : operators).slice(0, 8).map((item, index) => (
              <div className="grid min-h-[62px] grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-[4px] border border-[#303b48] bg-[#101820] px-3" key={item.id || item.app || index}>
                <div className="min-w-0">
                  <strong className="block truncate text-[13px] text-white">{item.name || item.app || item.id || "Operator skill"}</strong>
                  <span className="mt-1 block truncate text-[11px] text-friday-muted">{item.summary || item.description || item.purpose || copy?.empty?.evidence || "Friday has no operator note for this skill yet."}</span>
                </div>
                <span className="rounded-[3px] border border-[#405063] bg-[#202936] px-2 py-1 font-mono text-[10px] uppercase text-[#dce8f7]">{item.enabled === false ? "off" : item.status || "ready"}</span>
              </div>
            )) : <div className="rounded-[4px] border border-dashed border-friday-line bg-[#101820] px-3 py-4 text-[12px] text-friday-muted">{copy?.empty?.evidence || "No learned operator skill came back from the backend yet."}</div>}
          </div>
        </Panel>
      </div>
    </section>
  );
}

function Metric({ icon, label, value }) {
  return (
    <div className="grid min-h-[78px] grid-cols-[32px_minmax(0,1fr)] items-center gap-3 rounded-[5px] border border-friday-line bg-[#151b22] px-3">
      <span className="grid h-8 w-8 place-items-center rounded-[4px] border border-[#405063] bg-[#202936] text-friday-accent">{icon}</span>
      <div className="min-w-0">
        <span className="block font-mono text-[10px] uppercase text-friday-muted">{label}</span>
        <strong className="mt-1 block truncate text-[18px] text-white">{value}</strong>
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

function Action({ icon, label, busy, disabled, primary, onClick }) {
  return (
    <button className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-[4px] border px-3 text-[12px] font-bold disabled:opacity-50 ${primary ? "border-friday-blue bg-friday-blue text-[#061420]" : "border-friday-line bg-[#101820] text-white hover:border-friday-accent"}`} type="button" onClick={onClick} disabled={disabled}>
      {busy ? <Loader2 className="animate-spin" size={14} /> : icon}
      <span className="truncate">{label}</span>
    </button>
  );
}

function Input({ label, value, onChange, type = "text" }) {
  return (
    <label className="grid gap-1">
      <span className="font-mono text-[10px] uppercase text-friday-muted">{label}</span>
      <input className="min-h-10 min-w-0 rounded-[4px] border border-[#405063] bg-[#0d141b] px-3 text-[13px] text-white outline-none focus:border-friday-accent" type={type} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function MiniBlock({ label, value }) {
  return (
    <div className="min-w-0 rounded-[4px] border border-[#303b48] bg-[#0d141b] p-3">
      <div className="mb-2 font-mono text-[10px] font-bold uppercase text-friday-muted">{label}</div>
      <pre className="max-h-[160px] overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-[#dce6f2]">{stringify(value)}</pre>
    </div>
  );
}

function appChoices(operators, skills, discovered = [], selectedApp = "") {
  const values = new Set();
  if (selectedApp) values.add(selectedApp);
  for (const item of [...operators, ...skills, ...discovered]) {
    if (item.app) values.add(item.app);
    if (item.id && String(item.id).length < 48) values.add(String(item.id));
    if (item.name && String(item.name).length < 48) values.add(String(item.name));
  }
  return [...values].filter(Boolean).slice(0, 24);
}

function operatorKind(app, operators, skills, discovered = []) {
  if (operators.some((item) => item.app === app || item.id === app || item.name === app)) return "operator";
  if (skills.some((item) => item.app === app || item.id === app || item.name === app)) return "skill";
  if (discovered.some((item) => item.name === app)) return "seen";
  return "dynamic";
}

function iconFor(action) {
  if (action.includes("click") || action === "move_mouse" || action === "scroll") return <Zap size={14} />;
  if (action.includes("key") || action === "type_text") return <Keyboard size={14} />;
  if (action.includes("browser")) return <Monitor size={14} />;
  if (action.includes("screen") || action === "screenshot") return <Camera size={14} />;
  return <Eye size={14} />;
}

function labelize(value) {
  return String(value || "").replace(/[-_]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function compactWindow(value) {
  const text = String(value || "none");
  return text.length > 24 ? `${text.slice(0, 22)}...` : text;
}

function optionalNumber(value) {
  const text = String(value ?? "").trim();
  if (!text) return null;
  const number = Number(text);
  return Number.isFinite(number) ? number : null;
}

function stringify(value) {
  try {
    return JSON.stringify(value || {}, null, 2);
  } catch {
    return String(value || "");
  }
}

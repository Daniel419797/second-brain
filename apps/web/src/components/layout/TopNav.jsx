import Link from "next/link";
import { Bell, Brain, Database, Fingerprint, Mic } from "lucide-react";

export function TopNav({ activeView, approvalCount, notificationCount, activeMission, busy, intelligenceOpen, onOpenIntelligence, onStartWorkers, onLogout }) {
  const voiceActive = activeView === "voice-mode";
  const modeLinkClass = (active) =>
    `grid h-full place-items-center border-b-2 px-2 text-[13px] font-semibold transition-colors ${
      active ? "border-friday-accent text-friday-accent" : "border-transparent text-[#d9e2ef] hover:text-friday-accent"
    }`;

  return (
    <header className="flex h-16 min-h-16 w-full items-center gap-5 border-b border-friday-line bg-friday-top px-4">
      <div className="flex min-w-[230px] shrink-0 items-center gap-4">
        <h1 className="m-0 text-[14px] font-black uppercase leading-none tracking-[-.02em] text-white">Friday Command Center</h1>
        <span className="h-5 w-px bg-[#3d4857]" />
      </div>
      <div className="flex h-full items-center gap-5 text-[13px] font-semibold text-[#d9e2ef]" aria-label="Operating mode">
        <Link className={modeLinkClass(voiceActive)} href="/voice-mode">Voice Mode</Link>
        <strong className={modeLinkClass(!voiceActive)}>
          {activeMission ? "Mission Active" : "Observation Mode"}
        </strong>
      </div>
      <div className="ml-auto flex items-center gap-3">
        <Link className={`grid min-h-7 w-7 place-items-center bg-transparent transition-[color,transform] duration-150 hover:-translate-y-px hover:text-friday-accent active:scale-95 motion-reduce:transition-none ${voiceActive ? "text-friday-accent" : "text-[#dbe5f1]"}`} href="/voice-mode" title="Voice Mode">
          <Mic size={17} />
        </Link>
        <button
          className={`inline-flex min-h-8 items-center gap-2 rounded-[3px] px-3 font-mono text-[11px] font-bold uppercase tracking-[.08em] transition-[background-color,border-color,color,transform] duration-150 hover:-translate-y-px hover:border-friday-accent active:scale-[.98] disabled:opacity-50 motion-reduce:transition-none ${
            intelligenceOpen ? "border-[#45678c] bg-[#172334] text-friday-accent" : "border-[#3d4857] bg-[#151b22] text-[#dbe5f1]"
          }`}
          type="button"
          onClick={onOpenIntelligence}
          disabled={busy}
          title="System Intelligence"
          aria-pressed={Boolean(intelligenceOpen)}
        >
          <Brain size={15} />
        </button>
        <button className="grid min-h-7 w-7 place-items-center bg-transparent text-[#dbe5f1] transition-[color,transform] duration-150 hover:-translate-y-px hover:text-friday-accent active:scale-95 disabled:opacity-50 motion-reduce:transition-none" type="button" onClick={onStartWorkers} disabled={busy} title="Agent services">
          <Database size={17} />
        </button>
        <button className={`relative grid min-h-7 w-7 place-items-center bg-transparent transition-[color,transform] duration-150 hover:-translate-y-px hover:text-friday-accent active:scale-95 motion-reduce:transition-none ${notificationCount ? "text-friday-accent after:absolute after:right-px after:top-0 after:h-2 after:w-2 after:animate-friday-pulse after:rounded-full after:bg-friday-accent" : "text-[#dbe5f1]"}`} type="button" title={`${notificationCount || 0} unread notification${notificationCount === 1 ? "" : "s"}`}>
          <Bell size={17} />
        </button>
        <span className="h-[30px] w-px bg-[#3d4857]" />
        <button className={`min-h-[30px] rounded-sm border border-[#4b5868] bg-[#1b222c] px-2.5 py-1 text-[12px] font-semibold transition-[background-color,border-color,transform] duration-150 hover:-translate-y-px hover:border-friday-accent active:scale-[.98] motion-reduce:transition-none ${approvalCount ? "text-friday-accent" : "text-[#dce9f8]"}`} type="button">
          {approvalCount > 9 ? "9+" : approvalCount} Approvals
        </button>
        <button className="grid min-h-9 w-9 place-items-center rounded-full border border-[#8bbcff] bg-[#1a2028] text-[#dbe5f1] transition-[background-color,color,transform] duration-150 hover:scale-105 hover:text-friday-accent active:scale-95 motion-reduce:transition-none" onClick={onLogout} title="Log out">
          <Fingerprint size={17} />
        </button>
      </div>
    </header>
  );
}

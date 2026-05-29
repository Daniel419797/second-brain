import {
  Activity,
  Bell,
  Brain,
  CheckCircle,
  ClipboardList,
  Eye,
  FileText,
  Fingerprint,
  MessageSquare,
  Mic,
  Monitor,
  Phone,
  Play,
  Puzzle,
  ShieldCheck,
  Users
} from "lucide-react";
import Link from "next/link";

const ICONS = {
  Dashboard: Activity,
  Chat: MessageSquare,
  "Voice Mode": Mic,
  "Mission Control": Play,
  Agents: Users,
  Governance: ShieldCheck,
  Tasks: ClipboardList,
  Approvals: CheckCircle,
  Notifications: Bell,
  Projects: FileText,
  Vision: Eye,
  Android: Phone,
  Memory: Brain,
  Safety: ShieldCheck,
  Reliability: ShieldCheck,
  Integrations: Puzzle,
  Operators: Monitor
};

export function Sidebar({ items, activeView, collapsed, online, onToggle }) {
  return (
    <aside className={`flex h-full max-h-full max-w-dvw flex-col overflow-hidden border-r border-friday-line bg-friday-rail transition-[padding] duration-300 ease-out motion-reduce:transition-none ${collapsed ? "px-2 py-4" : "px-4 py-6"}`}>
      <div className={`relative flex items-center transition-[min-height,margin,gap] duration-300 ease-out motion-reduce:transition-none ${collapsed ? "mb-5 min-h-[76px] flex-col justify-start gap-2" : "mb-8 min-h-10 gap-3"}`}>
        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-[2px] border border-[#9fcaff] bg-[#9fcaff] text-[13px] font-bold text-[#061420] transition-[box-shadow,transform] duration-200 ease-out hover:shadow-[0_0_18px_rgba(159,202,255,.18)]">
          F
        </div>
        <div className={`overflow-hidden transition-[opacity,transform,width] duration-200 ease-out motion-reduce:transition-none ${collapsed ? "pointer-events-none w-0 -translate-x-2 opacity-0" : "w-[142px] translate-x-0 opacity-100"}`}>
          <strong className="block text-[22px] font-extrabold leading-none text-friday-accent">Friday</strong>
          <span className="mt-1 block text-[11px] tracking-[.13em] text-white">AI OPERATIONS</span>
        </div>
        <button
          className={`${collapsed ? "static min-h-7 w-7" : "absolute right-0 top-1 min-h-8 w-8"} rounded-full border border-[#405063] bg-[#111820] p-0 font-mono text-xs text-friday-accent transition-[background-color,border-color,transform] duration-200 ease-out hover:scale-105 hover:border-friday-accent hover:bg-[#17202b] active:scale-95 motion-reduce:transition-none`}
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
        >
          <span className={`inline-block transition-transform duration-300 ease-out motion-reduce:transition-none ${collapsed ? "rotate-0" : "rotate-180"}`}>›</span>
        </button>
      </div>

      <nav className="friday-scroll grid min-h-0 content-start gap-1 overflow-y-auto" aria-label="Friday sections">
        {items.map((item) => {
          const Icon = ICONS[item.label] || Activity;
          const active = activeView === item.id;
          return (
            <Link
              aria-label={item.label}
              className={`group flex min-h-10 w-full items-center rounded-none border-0 text-left text-[14px] leading-tight text-[#d9e0ea] transition-[background-color,color,border-color,transform] duration-150 ease-out motion-reduce:transition-none ${
                collapsed ? "justify-center border-l-[2px] px-0 py-2" : "gap-3 border-r-[2px] px-3 py-2"
              } ${active ? "border-friday-accent bg-[#242a33] font-semibold text-friday-accent" : `border-transparent bg-transparent hover:bg-[#242a33] `}`}
              key={item.id}
              href={item.href}
              title={collapsed ? item.label : undefined}
            >
              <Icon className={`h-[17px] w-[17px] shrink-0 transition-colors duration-150 ${active ? "text-friday-accent" : "text-[#d9e6f5] group-hover:text-friday-accent"}`} />
              <span className={collapsed ? "sr-only" : "transition-opacity duration-150"}>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto border-t border-[#3a4552] pt-4">
        <Link
          aria-label="Settings"
          className={`group mb-4 flex min-h-10 w-full items-center rounded-none border-0 text-left text-[14px] leading-tight text-[#d9e0ea] transition-[background-color,color,border-color,transform] duration-150 ease-out motion-reduce:transition-none ${
            collapsed ? "justify-center border-l-[2px] px-0 py-2" : "gap-3 border-r-[2px] px-3 py-2"
          } ${activeView === "settings" ? "border-friday-accent bg-[#242a33] font-semibold text-friday-accent" : `border-transparent bg-transparent hover:bg-[#242a33] ${collapsed ? "hover:scale-[1.04]" : "hover:translate-x-0.5"}`}`}
          href="/settings"
          title={collapsed ? "Settings" : undefined}
        >
          <Fingerprint className={`h-[17px] w-[17px] shrink-0 transition-colors duration-150 ${activeView === "settings" ? "text-friday-accent" : "text-[#d9e6f5] group-hover:text-friday-accent"}`} />
          <span className={collapsed ? "sr-only" : "transition-opacity duration-150"}>Settings</span>
        </Link>
        <div className={`grid min-h-[64px] gap-1 rounded-[6px] border border-[#3d4857] bg-[#20262f] font-mono text-[11px] transition-[padding,border-color,background-color] duration-200 ease-out motion-reduce:transition-none ${collapsed ? "place-items-center px-0" : "px-3 py-3"}`}>
          <div className={`flex items-center gap-2 ${collapsed ? "justify-center" : ""}`}>
            <span className={`h-2 w-2 rounded-full transition-[background-color,box-shadow] duration-300 ${online ? "animate-friday-pulse bg-friday-accent" : "bg-slate-500"}`} />
            <span className={collapsed ? "sr-only" : "font-bold text-[#eaf2fb]"}>{online ? "System Online" : "System Standby"}</span>
          </div>
          <span className={collapsed ? "sr-only" : "text-[10px] text-friday-muted"}>Latency: not measured</span>
        </div>
      </div>
    </aside>
  );
}

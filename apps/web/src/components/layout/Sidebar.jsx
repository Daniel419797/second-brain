import {
  Activity,
  Bell,
  Brain,
  CheckCircle,
  ClipboardList,
  Eye,
  FileText,
  MessageSquare,
  Mic,
  Monitor,
  Phone,
  Play,
  Puzzle,
  Rocket,
  Settings,
  ShieldCheck,
  Terminal,
  Users
} from "lucide-react";
import Link from "next/link";

const ICONS = {
  Dashboard: Activity,
  Chat: MessageSquare,
  "Voice Mode": Mic,
  "Mission Control": Play,
  Agents: Users,
  Agency: Rocket,
  "Control Room": Monitor,
  Governance: ShieldCheck,
  Tasks: ClipboardList,
  Approvals: CheckCircle,
  Notifications: Bell,
  Projects: FileText,
  "Friday Studio": Rocket,
  "Production Studio": Rocket,
  Vision: Eye,
  Android: Phone,
  Memory: Brain,
  Safety: ShieldCheck,
  "Security Lab": Terminal,
  Reliability: ShieldCheck,
  Integrations: Puzzle,
  Operators: Monitor
};

export function Sidebar({ items, activeView, collapsed, onToggle }) {
  return (
    <aside className={`flex h-full max-h-full max-w-dvw flex-col overflow-hidden border-r border-[#2f2f2f] bg-[#171717] transition-[padding] duration-300 ease-out motion-reduce:transition-none ${collapsed ? "px-2 py-4" : "px-3 py-4"}`}>
      <div className={`relative flex items-center transition-[min-height,margin,gap] duration-300 ease-out motion-reduce:transition-none ${collapsed ? "mb-5 min-h-[76px] flex-col justify-start gap-2" : "mb-8 min-h-10 gap-3"}`}>
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-[#3a3a3a] bg-[#242424] text-[13px] font-semibold text-[#f4f4f4] transition-[background-color,transform] duration-200 ease-out hover:bg-[#2f2f2f]">
          F
        </div>
        <div className={`overflow-hidden transition-[opacity,transform,width] duration-200 ease-out motion-reduce:transition-none ${collapsed ? "pointer-events-none w-0 -translate-x-2 opacity-0" : "w-[142px] translate-x-0 opacity-100"}`}>
          <strong className="block text-[20px] font-semibold leading-none text-[#f4f4f4]">Friday</strong>
          <span className="mt-1 block text-[12px] text-[#9c9c9c]">Personal AI</span>
        </div>
        <button
          className={`${collapsed ? "static min-h-8 w-8" : "absolute right-0 top-1 min-h-8 w-8"} rounded-full bg-[#242424] p-0 text-xs text-[#cfcfcf] transition-[background-color,transform] duration-200 ease-out hover:scale-105 hover:bg-[#303030] active:scale-95 motion-reduce:transition-none`}
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
        >
          <span className={`inline-block transition-transform duration-300 ease-out motion-reduce:transition-none ${collapsed ? "rotate-0" : "rotate-180"}`}>{">"}</span>
        </button>
      </div>

      <nav className="friday-scroll grid min-h-0 flex-1 content-start gap-1 overflow-y-auto pb-3" aria-label="Friday sections">
        {items.map((item) => {
          const Icon = ICONS[item.label] || Activity;
          const active = activeView === item.id;
          return (
            <Link
              aria-label={item.label}
              className={`group flex min-h-9 w-full items-center rounded-[10px] text-left text-[14px] leading-tight text-[#d8d8d8] transition-[background-color,color,transform] duration-150 ease-out motion-reduce:transition-none ${
                collapsed ? "justify-center px-0 py-2" : "gap-3 px-3 py-2"
              } ${active ? "bg-[#2f2f2f] font-medium text-[#f5f5f5]" : "bg-transparent hover:bg-[#242424] hover:text-white"}`}
              key={item.id}
              href={item.href}
              title={collapsed ? item.label : undefined}
            >
              <Icon className={`h-[17px] w-[17px] shrink-0 transition-colors duration-150 ${active ? "text-[#f4f4f4]" : "text-[#bdbdbd] group-hover:text-white"}`} />
              <span className={collapsed ? "sr-only" : "transition-opacity duration-150"}>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto shrink-0 border-t border-[#2f2f2f] pt-4">
        <Link
          aria-label="Settings"
          className={`group mb-4 flex min-h-9 w-full items-center rounded-[10px] text-left text-[14px] leading-tight text-[#d8d8d8] transition-[background-color,color,transform] duration-150 ease-out motion-reduce:transition-none ${
            collapsed ? "justify-center px-0 py-2" : "gap-3 px-3 py-2"
          } ${activeView === "settings" ? "bg-[#2f2f2f] font-medium text-[#f5f5f5]" : `bg-transparent hover:bg-[#242424] hover:text-white ${collapsed ? "hover:scale-[1.04]" : ""}`}`}
          href="/settings"
          title={collapsed ? "Settings" : undefined}
        >
          <Settings className={`h-[17px] w-[17px] shrink-0 transition-colors duration-150 ${activeView === "settings" ? "text-[#f4f4f4]" : "text-[#bdbdbd] group-hover:text-white"}`} />
          <span className={collapsed ? "sr-only" : "transition-opacity duration-150"}>Settings</span>
        </Link>
      </div>
    </aside>
  );
}

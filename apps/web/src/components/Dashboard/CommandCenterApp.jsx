"use client";

import { useCallback, useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import { NAV_ITEMS } from "@/lib/config";
import { DashboardProvider } from "@/components/Dashboard/DashboardContext";
import { useFridayData } from "@/hooks/useFridayData";
import { useFridaySession } from "@/hooks/useFridaySession";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopNav } from "@/components/layout/TopNav";
import { LoginView } from "@/components/views/LoginView";

export default function CommandCenterApp({ children }) {
  const session = useFridaySession();
  const pathname = usePathname();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [intelligenceOpen, setIntelligenceOpen] = useState(false);
  const { api, data, busy, liveTimestamp, chatMessages, refresh, chat, voiceChat, clearChat, post } = useFridayData(session.token, session.setError, session.logout);

  const activeMission = useMemo(() => {
    return (data.missions || []).find((mission) => {
      const status = String(mission.status || "").toLowerCase();
      return ["active", "running", "in_progress", "in progress"].includes(status);
    }) || data.missions?.[0] || null;
  }, [data.missions]);

  const approvalCount = data.approvalSummary?.count || data.approvals?.length || 0;
  const notificationCount = data.notifications?.unread_count || data.notifications?.items?.length || 0;
  const activeView = viewFromPath(pathname);
  const toggleSystemIntelligence = useCallback(() => {
    if (!intelligenceOpen) void refresh();
    setIntelligenceOpen((value) => !value);
  }, [intelligenceOpen, refresh]);

  if (!session.token) {
    return (
      <LoginView
        username={session.username}
        setUsername={session.setUsername}
        password={session.password}
        setPassword={session.setPassword}
        error={session.error}
        busy={session.busy}
        onSubmit={session.login}
      />
    );
  }

  return (
    <main
      className={`grid h-dvh w-dvw overflow-hidden bg-friday-bg text-white transition-[grid-template-columns] duration-300 ease-out motion-reduce:transition-none ${sidebarCollapsed ? "grid-cols-[72px_minmax(0,1fr)]" : "grid-cols-[256px_minmax(0,1fr)]"}`}
    >
      <Sidebar
        items={NAV_ITEMS}
        activeView={activeView}
        collapsed={sidebarCollapsed}
        online={data.status?.running}
        onToggle={() => setSidebarCollapsed((value) => !value)}
      />
      <div className="h-full min-w-0 overflow-hidden border-r border-friday-line">
        <TopNav
          activeView={activeView}
          approvalCount={approvalCount}
          notificationCount={notificationCount}
          activeMission={activeMission}
          busy={busy}
          onRefresh={refresh}
          intelligenceOpen={intelligenceOpen}
          onOpenIntelligence={toggleSystemIntelligence}
          onStartWorkers={() => post("/workers/start")}
          onLogout={session.logout}
        />
        <section className="h-[calc(100dvh-64px)] min-w-0 overflow-hidden">
          {session.error ? <p className="text-sm text-friday-danger">{session.error}</p> : null}
          <DashboardProvider
            value={{
              api,
              token: session.token,
              data,
              busy,
              chatMessages,
              activeMission,
              approvalCount,
              chat,
              voiceChat,
              clearChat,
              post,
              refresh,
              activeView,
              liveTimestamp,
              intelligenceOpen,
              closeIntelligence: () => setIntelligenceOpen(false)
            }}
          >
            {children}
          </DashboardProvider>
        </section>
      </div>
    </main>
  );
}

function viewFromPath(pathname) {
  if (!pathname || pathname === "/") return "dashboard";
  return pathname.split("/").filter(Boolean)[0] || "dashboard";
}

"use client";

import { useDashboard } from "@/components/Dashboard/DashboardContext";
import { PageWithIntelligenceRail } from "@/components/Dashboard/PageScaffold";
import { AgentsView } from "@/components/views/AgentsView";
import { AgencyView } from "@/components/views/AgencyView";
import { AndroidView } from "@/components/views/AndroidView";
import { ApprovalsView } from "@/components/views/ApprovalsView";
import { ChatView } from "@/components/views/ChatView";
import { DashboardView } from "@/components/views/DashboardView";
import { GovernanceView } from "@/components/views/GovernanceView";
import { IntegrationsView } from "@/components/views/IntegrationsView";
import { MemoryView } from "@/components/views/MemoryView";
import { MissionControlView } from "@/components/views/MissionControlView";
import { ProjectsView } from "@/components/views/ProjectsView";
import { ReliabilityView } from "@/components/views/ReliabilityView";
import { SafetyView } from "@/components/views/SafetyView";
import { GenericView } from "@/components/views/SimpleListView";
import { TasksView } from "@/components/views/TasksView";
import { VisionView } from "@/components/views/VisionView";
import { VoiceModeView } from "@/components/views/VoiceModeView";

export function DashboardRoute() {
  return <DashboardView />;
}

export function ChatRoute() {
  const { chatMessages, chat, clearChat, busy } = useDashboard();
  return (
    <PageWithIntelligenceRail>
      <ChatView messages={chatMessages} onSend={chat} onClear={clearChat} busy={busy} />
    </PageWithIntelligenceRail>
  );
}

export function MissionControlRoute() {
  return <MissionControlView />;
}

export function VoiceModeRoute() {
  return <VoiceModeView />;
}

export function AgentsRoute() {
  return <AgentsView />;
}

export function AgencyRoute() {
  return <AgencyView />;
}

export function TasksRoute() {
  return <TasksView />;
}

export function ApprovalsRoute() {
  const { data } = useDashboard();
  return <ApprovalsView approvals={data.approvals} summary={data.approvalSummary} />;
}

export function GenericDashboardRoute({ title, rows, empty }) {
  const { data } = useDashboard();
  const resolvedRows = typeof rows === "function" ? rows(data) : rows;
  return (
    <PageWithIntelligenceRail>
      <GenericView title={title} rows={resolvedRows || []} empty={empty} />
    </PageWithIntelligenceRail>
  );
}

export function GovernanceRoute() {
  return (
    <PageWithIntelligenceRail>
      <GovernanceView />
    </PageWithIntelligenceRail>
  );
}

export function ProjectsRoute() {
  return <ProjectsView />;
}

export function VisionRoute() {
  return (
    <PageWithIntelligenceRail>
      <VisionView />
    </PageWithIntelligenceRail>
  );
}

export function AndroidRoute() {
  return (
    <PageWithIntelligenceRail>
      <AndroidView />
    </PageWithIntelligenceRail>
  );
}

export function MemoryRoute() {
  return (
    <PageWithIntelligenceRail>
      <MemoryView />
    </PageWithIntelligenceRail>
  );
}

export function SafetyRoute() {
  return (
    <PageWithIntelligenceRail>
      <SafetyView />
    </PageWithIntelligenceRail>
  );
}

export function ReliabilityRoute() {
  return <ReliabilityView />;
}

export function IntegrationsRoute() {
  return (
    <PageWithIntelligenceRail>
      <IntegrationsView />
    </PageWithIntelligenceRail>
  );
}

export function SettingsRoute() {
  return (
    <GenericDashboardRoute
      title="Settings"
      rows={(data) => data.settings || []}
      empty="Settings are available through the local API and environment configuration."
    />
  );
}

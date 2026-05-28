import { useDashboard } from "@/components/Dashboard/DashboardContext";
import { IntelligenceRail } from "@/components/Dashboard/IntelligenceRail";

export function PageWithIntelligenceRail({ children }) {
  const { activeView, data, activeMission, approvalCount, liveTimestamp, intelligenceOpen, closeIntelligence } = useDashboard();
  const showIntelligence = intelligenceOpen !== false;

  return (
    <div className="relative grid h-full min-w-0 overflow-hidden">
      <div className="friday-scroll min-w-0 animate-friday-fade-in overflow-y-auto px-4 py-4">
        {children}
      </div>
      {showIntelligence ? (
        <div className="absolute inset-y-0 right-0 z-30 w-[min(340px,calc(100vw-88px))] border-l border-friday-line shadow-[-18px_0_36px_rgba(0,0,0,.28)]">
          <IntelligenceRail
            activeView={activeView}
            data={data}
            activeMission={activeMission}
            approvalCount={approvalCount}
            liveTimestamp={liveTimestamp}
            onClose={closeIntelligence}
          />
        </div>
      ) : null}
    </div>
  );
}

import type { ReactNode } from "react";
import CommandCenterApp from "@/components/Dashboard/CommandCenterApp";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return <CommandCenterApp>{children}</CommandCenterApp>;
}

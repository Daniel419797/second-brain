const rawApiUrl = process.env.NEXT_PUBLIC_FRIDAY_API_URL || "http://127.0.0.1:8000";

export const API_URL = rawApiUrl.replace(/\/+$/, "");

export const STATUSES = ["active", "pending", "blocked", "done", "failed", "cancelled"];

export const NAV_ITEMS = [
  ["dashboard", "Dashboard", "/"],
  ["chat", "Chat", "/chat"],
  ["voice-mode", "Voice Mode", "/voice-mode"],
  ["mission-control", "Mission Control", "/mission-control"],
  ["agents", "Agents", "/agents"],
  ["agency", "Agency", "/agency"],
  ["control-room", "Control Room", "/control-room"],
  ["governance", "Governance", "/governance"],
  ["tasks", "Tasks", "/tasks"],
  ["approvals", "Approvals", "/approvals"],
  ["notifications", "Notifications", "/notifications"],
  ["projects", "Projects", "/projects"],
  ["friday-studio", "Friday Studio", "/friday-studio"],
  ["production-studio", "Production Studio", "/production-studio"],
  ["vision", "Vision", "/vision"],
  ["android", "Android", "/android"],
  ["memory", "Memory", "/memory"],
  ["safety", "Safety", "/safety"],
  ["security-lab", "Security Lab", "/security-lab"],
  ["reliability", "Reliability", "/reliability"],
  ["integrations", "Integrations", "/integrations"],
  ["operators", "Operators", "/operators"]
].map(([id, label, href]) => ({ id, label, href }));

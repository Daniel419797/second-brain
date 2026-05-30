import { API_URL } from "@/lib/config";

const SNAPSHOT_ENDPOINTS = {
  status: "/agents/status",
  tasks: "/tasks?limit=80",
  agents: "/agents/roster",
  offices: "/agents/offices",
  missions: "/missions?limit=8",
  missionStatus: "/missions/status",
  agency: "/agency/status",
  gateway: "/gateway/status",
  controlRoom: "/control-room/status",
  projectMemory: "/project-memory/status",
  projectReferences: "/project-memory/reference-images?limit=12",
  productionReadiness: "/coding/production/readiness/status",
  fridayOs: "/friday-os/status",
  judgment: "/judgment/status",
  projectIdeas: "/project-ideas/status",
  approvals: "/approvals/inbox?limit=10",
  approvalSummary: "/approvals/summary",
  thoughts: "/thoughts/summary",
  pcAwareness: "/pc/awareness",
  notifications: "/notifications/summary",
  logs: "/logs/recent?lines=80",
  audit: "/audit/recent?limit=8",
  contextFusion: "/context-fusion/status",
  conversationContinuity: "/conversation-continuity/status",
  agentQuality: "/agent-quality/status",
  evaluation: "/evaluation/summary",
  blackboard: "/blackboard/summary",
  contractsSummary: "/contracts/summary",
  skillsSummary: "/memory/skills/summary",
  interface: "/interface/snapshot"
};

export async function loginToFriday({ username, password }) {
  const response = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
    credentials: "include"
  });
  if (!response.ok) throw new Error("Login failed. Check the API password in .env.");
  return response.json();
}

export function createFridayApi(token) {
  return async function api(path, options = {}) {
    const response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers || {})
      }
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      const error = new Error(detail.detail || `${response.status} ${response.statusText}`);
      error.status = response.status;
      throw error;
    }
    return response.json();
  };
}

export async function loadDashboardSnapshot(api) {
  try {
    return await api("/dashboard/snapshot");
  } catch (err) {
    if (isAuthError(err)) throw err;
    return loadLegacyDashboardSnapshot(api);
  }
}

async function loadLegacyDashboardSnapshot(api) {
  const entries = await Promise.all(
    Object.entries(SNAPSHOT_ENDPOINTS).map(async ([key, path]) => {
      try {
        return [key, await api(path)];
      } catch (err) {
        if (isAuthError(err)) throw err;
        return [key, defaultValueFor(key)];
      }
    })
  );
  return Object.fromEntries(entries);
}

export function isAuthError(err) {
  const status = Number(err?.status || 0);
  return status === 401 || status === 403;
}

export async function sendFridayMessage(api, message) {
  return api("/chat", {
    method: "POST",
    body: JSON.stringify({ message })
  });
}

export async function sendFridayVoiceMessage(api, message) {
  return api("/voice/chat", {
    method: "POST",
    body: JSON.stringify({ message })
  });
}

export function wsUrl(path, token) {
  return `${API_URL.replace(/^http/, "ws")}${path}?token=${encodeURIComponent(token)}`;
}

function defaultValueFor(key) {
  if (["tasks", "agents", "offices", "missions", "approvals", "audit", "projectReferences"].includes(key)) return [];
  if (key === "logs") return { lines: [] };
  return null;
}

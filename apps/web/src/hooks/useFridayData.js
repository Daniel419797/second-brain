"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createFridayApi, isAuthError, loadDashboardSnapshot, sendFridayMessage, sendFridayVoiceMessage, wsUrl } from "@/services/fridayApi";

const INITIAL_DATA = {
  status: null,
  tasks: [],
  agents: [],
  offices: [],
  missions: [],
  agency: null,
  gateway: null,
  controlRoom: null,
  projects: [],
  projectMemory: null,
  projectReferences: [],
  approvals: [],
  approvalSummary: null,
  thoughts: null,
  pcAwareness: null,
  notifications: null,
  logs: { lines: [] },
  audit: [],
  contextFusion: null,
  conversationContinuity: null,
  integrations: null,
  reliability: null,
  agentQuality: null,
  evaluation: null,
  blackboard: null,
  contractsSummary: null,
  skillsSummary: null,
  missionStatus: null,
  interface: null
};

export function useFridayData(token, setGlobalError, onAuthExpired) {
  const api = useMemo(() => createFridayApi(token), [token]);
  const [data, setData] = useState(INITIAL_DATA);
  const [busy, setBusy] = useState(false);
  const [chatBusy, setChatBusy] = useState(false);
  const [liveTimestamp, setLiveTimestamp] = useState("");
  const [chatMessages, setChatMessages] = useState(() => loadChatHistory());
  const chatSocketRef = useRef(null);
  const dashboardLiveRef = useRef(false);

  useEffect(() => {
    try {
      window.localStorage.setItem("friday.chat.history", JSON.stringify(chatMessages.slice(-80)));
    } catch {
      return;
    }
  }, [chatMessages]);

  const refresh = useCallback(async () => {
    if (!token) return;
    setBusy(true);
    try {
      setData({ ...INITIAL_DATA, ...(await loadDashboardSnapshot(api)) });
    } catch (err) {
      if (isAuthError(err)) {
        onAuthExpired?.();
        setGlobalError("Session expired. Please log in again.");
        return;
      }
      setGlobalError(err.message);
    } finally {
      setBusy(false);
    }
  }, [api, onAuthExpired, setGlobalError, token]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    let socket = null;
    let reconnectTimer = null;
    let fallbackTimer = null;

    const connect = () => {
      socket = new WebSocket(wsUrl("/ws/dashboard", token));
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (fallbackTimer) {
            window.clearTimeout(fallbackTimer);
            fallbackTimer = null;
          }
          setLiveTimestamp(payload.timestamp || new Date().toISOString());
          dashboardLiveRef.current = true;
          setData((current) => mergeDashboardPayload(current, payload));
        } catch {
          return;
        }
      };
      socket.onclose = () => {
        dashboardLiveRef.current = false;
        if (!cancelled) {
          reconnectTimer = window.setTimeout(connect, 2000);
        }
      };
      socket.onerror = () => {
        socket?.close();
      };
    };

    connect();
    fallbackTimer = window.setTimeout(() => {
      if (!cancelled) refresh();
    }, 8000);
    return () => {
      cancelled = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      if (fallbackTimer) window.clearTimeout(fallbackTimer);
      socket?.close();
    };
  }, [refresh, token]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    let socket = null;
    let reconnectTimer = null;

    const connect = () => {
      socket = new WebSocket(wsUrl("/ws/notifications", token));
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          setLiveTimestamp(payload.timestamp || new Date().toISOString());
          setData((current) => ({ ...current, notifications: payload }));
        } catch {
          return;
        }
      };
      socket.onclose = () => {
        if (!cancelled) {
          reconnectTimer = window.setTimeout(connect, 2000);
        }
      };
      socket.onerror = () => {
        socket?.close();
      };
    };

    connect();
    return () => {
      cancelled = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [token]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    let socket = null;
    let reconnectTimer = null;

    const connect = () => {
      socket = new WebSocket(wsUrl("/ws/tasks", token));
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          setLiveTimestamp(payload.timestamp || new Date().toISOString());
          setData((current) => mergeTaskPayload(current, payload));
        } catch {
          return;
        }
      };
      socket.onclose = () => {
        if (!cancelled) {
          reconnectTimer = window.setTimeout(connect, 2000);
        }
      };
      socket.onerror = () => {
        socket?.close();
      };
    };

    connect();
    return () => {
      cancelled = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [token]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    let socket = null;
    let reconnectTimer = null;

    const connect = () => {
      socket = new WebSocket(wsUrl("/ws/chat", token));
      chatSocketRef.current = socket;
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === "reply") {
            setChatBusy(false);
            setChatMessages((items) => [
              ...items,
              { id: chatId("friday"), role: "friday", text: payload.reply || "", timestamp: payload.timestamp || new Date().toISOString() }
            ]);
          } else if (payload.type === "error") {
            setChatBusy(false);
            setChatMessages((items) => [
              ...items,
              { id: chatId("system"), role: "system", text: payload.message || "Friday chat failed.", timestamp: payload.timestamp || new Date().toISOString() }
            ]);
            setGlobalError(payload.message || "Friday chat failed.");
          }
        } catch {
          return;
        }
      };
      socket.onclose = () => {
        if (chatSocketRef.current === socket) chatSocketRef.current = null;
        if (!cancelled) setChatBusy(false);
        if (!cancelled) {
          reconnectTimer = window.setTimeout(connect, 2000);
        }
      };
      socket.onerror = () => {
        socket?.close();
      };
    };

    connect();
    return () => {
      cancelled = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      if (chatSocketRef.current === socket) chatSocketRef.current = null;
      socket?.close();
    };
  }, [setGlobalError, token]);

  async function chat(message) {
    const text = message.trim();
    if (!text) return;
    const now = new Date().toISOString();
    setChatMessages((items) => [...items, { id: chatId("user"), role: "user", text, timestamp: now }]);
    const socket = chatSocketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      setChatBusy(true);
      try {
        socket.send(JSON.stringify({ id: chatId("chat"), message: text }));
      } catch (err) {
        setChatBusy(false);
        await sendChatOverHttp(api, text, setChatMessages, setGlobalError);
      }
      return;
    }
    await sendChatOverHttp(api, text, setChatMessages, setGlobalError);
  }

  async function voiceChat(message) {
    const text = message.trim();
    if (!text) return;
    const now = new Date().toISOString();
    setChatMessages((items) => [...items, { id: chatId("user"), role: "user", text, timestamp: now }]);
    setChatBusy(true);
    try {
      const reply = await sendFridayVoiceMessage(api, text);
      setChatMessages((items) => [
        ...items,
        { id: chatId("friday"), role: "friday", text: reply.reply || "", timestamp: reply.timestamp || new Date().toISOString() }
      ]);
    } catch (err) {
      if (isAuthError(err)) {
        onAuthExpired?.();
        setGlobalError("Session expired. Please log in again.");
        return;
      }
      setChatMessages((items) => [
        ...items,
        { id: chatId("system"), role: "system", text: err.message || "Friday voice chat failed.", timestamp: new Date().toISOString() }
      ]);
      setGlobalError(err.message);
    } finally {
      setChatBusy(false);
    }
  }

  async function sendChatOverHttp(apiClient, text, updateMessages, reportError) {
    setChatBusy(true);
    try {
      const reply = await sendFridayMessage(apiClient, text);
      updateMessages((items) => [
        ...items,
        { id: chatId("friday"), role: "friday", text: reply.reply || "", timestamp: reply.timestamp || new Date().toISOString() }
      ]);
    } catch (err) {
      updateMessages((items) => [
        ...items,
        { id: chatId("system"), role: "system", text: err.message || "Friday chat failed.", timestamp: new Date().toISOString() }
      ]);
      reportError(err.message);
    } finally {
      setChatBusy(false);
    }
  }

  function clearChat() {
    setChatMessages([]);
    try {
      window.localStorage.removeItem("friday.chat.history");
    } catch {
      return;
    }
  }

  async function post(path, body = {}) {
    setBusy(true);
    try {
      await api(path, { method: "POST", body: JSON.stringify(body) });
      if (!dashboardLiveRef.current) await refresh();
    } catch (err) {
      if (isAuthError(err)) {
        onAuthExpired?.();
        setGlobalError("Session expired. Please log in again.");
        return;
      }
      setGlobalError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return { api, data, busy: busy || chatBusy, liveTimestamp, chatMessages, refresh, chat, voiceChat, clearChat, post };
}

function mergeDashboardPayload(current, payload) {
  if (!payload || typeof payload !== "object") return current;
  return {
    ...current,
    status: payload.status ?? current.status,
    tasks: payload.tasks ?? current.tasks,
    agents: payload.agents ?? current.agents,
    offices: payload.offices ?? current.offices,
    missions: Array.isArray(payload.missions) ? payload.missions : current.missions,
    agency: payload.agency ?? current.agency,
    gateway: payload.gateway ?? current.gateway,
    controlRoom: payload.controlRoom ?? payload.control_room ?? current.controlRoom,
    missionStatus: payload.missionStatus ?? (!Array.isArray(payload.missions) ? payload.missions : current.missionStatus),
    projects: payload.projects ?? payload.projectMemory?.projects ?? current.projects,
    projectMemory: payload.projectMemory ?? payload.project_memory ?? current.projectMemory,
    projectReferences: payload.projectReferences ?? payload.project_references ?? current.projectReferences,
    approvals: payload.approvals ?? current.approvals,
    approvalSummary: payload.approvalSummary ?? current.approvalSummary,
    thoughts: payload.thoughts ?? current.thoughts,
    pcAwareness: payload.pcAwareness ?? current.pcAwareness,
    notifications: payload.notifications ?? current.notifications,
    logs: payload.logs ?? current.logs,
    audit: payload.audit ?? current.audit,
    contextFusion: payload.contextFusion ?? payload.context_fusion ?? current.contextFusion,
    conversationContinuity: payload.conversationContinuity ?? payload.conversation_continuity ?? current.conversationContinuity,
    integrations: payload.integrations ?? current.integrations,
    reliability: payload.reliability ?? current.reliability,
    agentQuality: payload.agentQuality ?? payload.agent_quality ?? current.agentQuality,
    evaluation: payload.evaluation ?? current.evaluation,
    blackboard: payload.blackboard ?? current.blackboard,
    contractsSummary: payload.contractsSummary ?? current.contractsSummary,
    skillsSummary: payload.skillsSummary ?? current.skillsSummary,
    interface: payload.interface ?? current.interface
  };
}

function mergeTaskPayload(current, payload) {
  if (!payload || typeof payload !== "object") return current;
  const approvalSummary = payload.approvals && !Array.isArray(payload.approvals) ? payload.approvals : current.approvalSummary;
  return {
    ...current,
    status: payload.status ?? current.status,
    tasks: Array.isArray(payload.tasks) ? payload.tasks : current.tasks,
    offices: Array.isArray(payload.offices) ? payload.offices : current.offices,
    agency: payload.agency ?? current.agency,
    gateway: payload.gateway ?? current.gateway,
    controlRoom: payload.controlRoom ?? payload.control_room ?? current.controlRoom,
    approvalSummary,
    thoughts: payload.thoughts ?? current.thoughts,
    notifications: payload.notifications ?? current.notifications,
    evaluation: payload.evaluation ?? current.evaluation,
    blackboard: payload.blackboard ?? current.blackboard
  };
}

function loadChatHistory() {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem("friday.chat.history") || "[]");
    return Array.isArray(parsed) ? parsed.filter((item) => item?.text).slice(-80) : [];
  } catch {
    return [];
  }
}

function chatId(prefix) {
  try {
    return `${prefix}-${crypto.randomUUID()}`;
  } catch {
    return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }
}

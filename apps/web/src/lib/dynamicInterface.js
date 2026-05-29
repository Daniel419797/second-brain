const VIEW_ALIASES = {
  mission: "mission-control",
  missions: "mission-control",
  mission_control: "mission-control",
  control: "control-room",
  control_room: "control-room",
  voice: "voice-mode",
  voice_mode: "voice-mode",
  operator: "operators",
  "ui-control": "operators",
  ui_control: "operators"
};

export function normalizeView(view) {
  const key = String(view || "dashboard").trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^[-_]+|[-_]+$/g, "");
  return VIEW_ALIASES[key] || key || "dashboard";
}

export function interfaceFor(data, view = "dashboard") {
  const key = normalizeView(view);
  return data?.interface?.views?.[key] || data?.interface?.views?.dashboard || {};
}

export function chromeCopy(data) {
  return data?.interface?.chrome || data?.interface?.brand || {};
}

export function interfaceText(data, view, path, fallback = "") {
  const copy = interfaceFor(data, view);
  const value = path.split(".").reduce((current, key) => current?.[key], copy);
  return value == null || value === "" ? fallback : value;
}

export function interfaceActions(data, view) {
  const actions = interfaceFor(data, view)?.actions;
  return Array.isArray(actions) ? actions : [];
}

export function interfaceAction(data, view, id) {
  return interfaceActions(data, view).find((action) => action?.id === id) || null;
}

export function actionLabel(data, view, id, fallback) {
  return interfaceAction(data, view, id)?.label || fallback;
}

const API_BASE = "http://127.0.0.1:8000";

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.source !== "friday-content") return false;
  sendToFriday(message.kind, message.payload)
    .then((result) => sendResponse({ ok: true, result }))
    .catch((error) => sendResponse({ ok: false, error: String(error) }));
  return true;
});

async function settings() {
  return chrome.storage.local.get({ enabled: false, token: "" });
}

async function sendToFriday(kind, payload) {
  const opts = await settings();
  if (!opts.enabled || !opts.token) return { skipped: true, reason: "extension disabled or token missing" };
  let path = "/browser-extension/context";
  let method = "POST";
  let body = JSON.stringify(payload);
  if (kind === "console") path = "/browser-extension/console";
  if (kind === "network") path = "/browser-extension/network";
  if (kind === "page-change") path = "/browser-extension/page-change";
  if (kind === "actions") {
    const url = encodeURIComponent(payload?.url || "");
    path = `/browser-extension/actions?url=${url}`;
    method = "GET";
    body = undefined;
  }
  if (kind === "action-result") {
    path = `/browser-extension/actions/${payload.id}/complete`;
    body = JSON.stringify({ status: payload.status || "done", result: payload.result || "" });
  }
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${opts.token}`
    },
    body
  });
  if (!response.ok) throw new Error(`Friday API ${response.status}`);
  const data = await response.json();
  if (kind === "actions") return { actions: data };
  return data;
}

chrome.webRequest.onErrorOccurred.addListener(
  (details) => {
    sendToFriday("network", {
      browser: "extension",
      url: details.url,
      event_type: "network_error",
      error: details.error,
      method: details.method,
      type: details.type,
      tab_id: details.tabId
    }).catch(() => {});
  },
  { urls: ["<all_urls>"] }
);

async function legacyPost(path, payload, token) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`
    },
    body: JSON.stringify(payload)
  });
  if (!response.ok) throw new Error(`Friday API ${response.status}`);
  return response.json();
}

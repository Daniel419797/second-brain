const SECRET_RE = /(api[_-]?key|token|secret|password|passwd|authorization|bearer|cookie|session|credential)/i;
const TOKEN_VALUE_RE = /\b([a-z0-9_-]{24,}\.[a-z0-9_-]{12,}\.[a-z0-9_-]{12,}|sk-[a-z0-9_-]{16,}|ghp_[a-z0-9_]{20,})\b/gi;

let lastSent = 0;
let lastActionPoll = 0;
let lastPageChange = 0;
let watchObserver = null;

function cleanText(value, max = 240) {
  let text = String(value || "").replace(/\s+/g, " ").trim();
  text = text.replace(TOKEN_VALUE_RE, "[redacted-token]");
  text = text.replace(SECRET_RE, "[redacted-key]");
  return text.slice(0, max);
}

function selectorFor(element) {
  if (!element || !element.tagName) return "";
  if (element.id && !SECRET_RE.test(element.id)) return `#${CSS.escape(element.id)}`;
  const aria = element.getAttribute("aria-label");
  if (aria && !SECRET_RE.test(aria)) return `${element.tagName.toLowerCase()}[aria-label="${cleanText(aria, 80)}"]`;
  const name = element.getAttribute("name");
  if (name && !SECRET_RE.test(name)) return `${element.tagName.toLowerCase()}[name="${cleanText(name, 80)}"]`;
  return element.tagName.toLowerCase();
}

function pageContext() {
  const headings = Array.from(document.querySelectorAll("h1,h2,h3"))
    .slice(0, 60)
    .map((item) => ({ text: cleanText(item.innerText || item.textContent, 180), selector: selectorFor(item) }))
    .filter((item) => item.text);

  const buttons = Array.from(document.querySelectorAll("button,a,[role=button],input[type=submit]"))
    .slice(0, 120)
    .map((item) => ({
      text: cleanText(item.innerText || item.value || item.getAttribute("aria-label") || item.textContent, 160),
      aria: cleanText(item.getAttribute("aria-label"), 160),
      selector: selectorFor(item)
    }))
    .filter((item) => item.text || item.aria);

  const forms = Array.from(document.forms)
    .slice(0, 40)
    .map((form) => ({
      name: cleanText(form.getAttribute("name") || form.id || "form", 120),
      fields: Array.from(form.elements)
        .slice(0, 80)
        .map((field) => {
          const type = String(field.type || "text").toLowerCase();
          const name = String(field.name || field.id || "").trim();
          const sensitive = type === "password" || type === "hidden" || SECRET_RE.test(name);
          return { name: sensitive ? "[redacted]" : cleanText(name, 120), type, sensitive };
        })
    }));

  const links = Array.from(document.querySelectorAll("a[href]"))
    .slice(0, 120)
    .map((item) => ({ text: cleanText(item.innerText || item.textContent, 160), href: cleanText(item.href, 240), selector: selectorFor(item) }))
    .filter((item) => item.text || item.href);

  const inputs = Array.from(document.querySelectorAll("input,textarea,select"))
    .slice(0, 120)
    .map((item) => {
      const type = String(item.type || item.tagName || "text").toLowerCase();
      const name = String(item.name || item.id || "").trim();
      const sensitive = type === "password" || type === "hidden" || SECRET_RE.test(name);
      return {
        name: sensitive ? "[redacted]" : cleanText(name, 120),
        type,
        label: sensitive ? "[redacted]" : cleanText(item.getAttribute("aria-label") || item.placeholder || "", 160),
        selector: sensitive ? "" : selectorFor(item),
        sensitive
      };
    });

  const landmarks = Array.from(document.querySelectorAll("[role],main,nav,aside,header,footer"))
    .slice(0, 80)
    .map((item) => ({
      role: cleanText(item.getAttribute("role") || item.tagName.toLowerCase(), 80),
      label: cleanText(item.getAttribute("aria-label") || item.id || "", 160),
      selector: selectorFor(item)
    }));

  const perf = performance && performance.timing ? {
    domCompleteMs: performance.timing.domComplete - performance.timing.navigationStart,
    loadEventMs: performance.timing.loadEventEnd - performance.timing.navigationStart
  } : {};

  return {
    browser: navigator.userAgent.includes("Edg/") ? "edge" : "chrome",
    url: location.href,
    title: cleanText(document.title, 260),
    selected_text: cleanText(window.getSelection ? window.getSelection().toString() : "", 2000),
    headings,
    buttons,
    links,
    inputs,
    landmarks,
    forms,
    performance: perf,
    metadata: { visibility: document.visibilityState, ready_state: document.readyState }
  };
}

function sendContext(force = false) {
  const now = Date.now();
  if (!force && now - lastSent < 10000) return;
  lastSent = now;
  chrome.runtime.sendMessage({ source: "friday-content", kind: "context", payload: pageContext() });
}

function sendPageChange(summary, metadata = {}) {
  const now = Date.now();
  if (now - lastPageChange < 5000) return;
  lastPageChange = now;
  chrome.runtime.sendMessage({
    source: "friday-content",
    kind: "page-change",
    payload: {
      browser: navigator.userAgent.includes("Edg/") ? "edge" : "chrome",
      url: location.href,
      summary: cleanText(summary || "Page changed", 500),
      metadata
    }
  });
}

const originalError = console.error;
console.error = function patchedFridayConsoleError(...args) {
  try {
    chrome.runtime.sendMessage({
      source: "friday-content",
      kind: "console",
      payload: {
        browser: navigator.userAgent.includes("Edg/") ? "edge" : "chrome",
        url: location.href,
        level: "error",
        message: cleanText(args.map(String).join(" "), 1000),
        source: "console.error"
      }
    });
  } catch (_error) {}
  return originalError.apply(console, args);
};

window.addEventListener("error", (event) => {
  chrome.runtime.sendMessage({
    source: "friday-content",
    kind: "console",
    payload: {
      browser: navigator.userAgent.includes("Edg/") ? "edge" : "chrome",
      url: location.href,
      level: "error",
      message: cleanText(event.message || "window error", 1000),
      source: cleanText(event.filename || "window.error", 200)
    }
  });
}, true);

window.addEventListener("unhandledrejection", (event) => {
  chrome.runtime.sendMessage({
    source: "friday-content",
    kind: "console",
    payload: {
      browser: navigator.userAgent.includes("Edg/") ? "edge" : "chrome",
      url: location.href,
      level: "error",
      message: cleanText(event.reason || "unhandled promise rejection", 1000),
      source: "unhandledrejection"
    }
  });
}, true);

sendContext(true);
document.addEventListener("click", () => sendContext(false), true);
document.addEventListener("click", () => sendPageChange("User clicked page", { event: "click" }), true);
document.addEventListener("input", () => sendContext(false), true);
document.addEventListener("input", () => sendPageChange("User edited a safe page field", { event: "input" }), true);
window.addEventListener("popstate", () => sendPageChange("Browser history/navigation changed", { event: "popstate" }), true);
setInterval(() => sendContext(false), 30000);

async function pollActions(force = false) {
  const now = Date.now();
  if (!force && now - lastActionPoll < 5000) return;
  lastActionPoll = now;
  chrome.runtime.sendMessage({ source: "friday-content", kind: "actions", payload: { url: location.href } }, async (response) => {
    const actions = response?.result?.actions || response?.result || [];
    if (!Array.isArray(actions)) return;
    for (const action of actions) {
      const result = await runAction(action);
      chrome.runtime.sendMessage({ source: "friday-content", kind: "action-result", payload: { id: action.id, ...result } });
    }
  });
}

async function runAction(action) {
  try {
    const selector = String(action.selector || "");
    const element = selector ? document.querySelector(selector) : null;
    if (!element && !["summarize", "scroll", "watch", "explain", "find"].includes(action.action)) {
      return { status: "failed", result: "Selector not found" };
    }
    if (action.action === "click") {
      element.click();
      return { status: "done", result: "Clicked selector" };
    }
    if (action.action === "focus") {
      element.focus();
      return { status: "done", result: "Focused selector" };
    }
    if (action.action === "fill") {
      const type = String(element.type || "").toLowerCase();
      const name = String(element.name || element.id || selector).toLowerCase();
      if (type === "password" || type === "hidden" || SECRET_RE.test(name)) {
        return { status: "blocked", result: "Refused sensitive fill" };
      }
      element.focus();
      element.value = String(action.value || "");
      element.dispatchEvent(new Event("input", { bubbles: true }));
      element.dispatchEvent(new Event("change", { bubbles: true }));
      return { status: "done", result: "Filled selector" };
    }
    if (action.action === "select") {
      element.value = String(action.value || "");
      element.dispatchEvent(new Event("change", { bubbles: true }));
      return { status: "done", result: "Selected value" };
    }
    if (action.action === "scroll") {
      window.scrollBy({ top: Number(action.value || 600), behavior: "smooth" });
      return { status: "done", result: "Scrolled page" };
    }
    if (action.action === "summarize") {
      sendContext(true);
      return { status: "done", result: "Context refresh sent" };
    }
    if (action.action === "watch") {
      if (watchObserver) watchObserver.disconnect();
      watchObserver = new MutationObserver(() => {
        sendContext(true);
        sendPageChange("Watched DOM changed", { event: "mutation" });
      });
      watchObserver.observe(document.documentElement, { subtree: true, childList: true, attributes: true });
      sendContext(true);
      return { status: "done", result: "Watching page changes and sending redacted context" };
    }
    if (action.action === "highlight") {
      element.style.outline = "3px solid #2dd4bf";
      element.scrollIntoView({ behavior: "smooth", block: "center" });
      return { status: "done", result: "Highlighted selector" };
    }
    if (action.action === "explain") {
      sendContext(true);
      const context = pageContext();
      return {
        status: "done",
        result: `${context.title}: ${context.headings.length} headings, ${context.buttons.length} buttons, ${context.forms.length} forms, ${context.inputs.length} inputs`
      };
    }
    if (action.action === "find") {
      const needle = cleanText(action.value || action.reason || "", 120).toLowerCase();
      if (!needle) return { status: "failed", result: "No find text provided" };
      const match = Array.from(document.querySelectorAll("button,a,input,textarea,select,h1,h2,h3,label,[role=button]"))
        .map((item) => ({ item, text: cleanText(item.innerText || item.value || item.placeholder || item.getAttribute("aria-label") || item.textContent, 240) }))
        .find((entry) => entry.text.toLowerCase().includes(needle));
      if (!match) return { status: "failed", result: "No visible element matched" };
      const foundSelector = selectorFor(match.item);
      match.item.style.outline = "3px solid #f59e0b";
      match.item.scrollIntoView({ behavior: "smooth", block: "center" });
      return { status: "done", result: `Found ${match.text} at ${foundSelector}` };
    }
    return { status: "skipped", result: "Unsupported action" };
  } catch (error) {
    return { status: "failed", result: String(error) };
  }
}

setInterval(() => pollActions(false), 5000);
document.addEventListener("visibilitychange", () => pollActions(true));

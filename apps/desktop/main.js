const { app, BrowserWindow, Menu, Tray, nativeImage, shell } = require("electron");
const fs = require("fs");
const path = require("path");

const DASHBOARD_URL = process.env.FRIDAY_DASHBOARD_URL || "http://localhost:3000";
const SETTINGS_FILE = () => path.join(app.getPath("userData"), "desktop-settings.json");

let mainWindow = null;
let tray = null;
let isQuitting = false;

function readSettings() {
  try {
    return JSON.parse(fs.readFileSync(SETTINGS_FILE(), "utf8"));
  } catch {
    return { openAtLogin: false, startHidden: false };
  }
}

function writeSettings(settings) {
  fs.mkdirSync(path.dirname(SETTINGS_FILE()), { recursive: true });
  fs.writeFileSync(SETTINGS_FILE(), JSON.stringify(settings, null, 2));
}

function createWindow() {
  if (mainWindow) {
    mainWindow.show();
    mainWindow.focus();
    return mainWindow;
  }

  const win = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 375,
    minHeight: 640,
    backgroundColor: "#f7f7f4",
    title: "Friday Command Center",
    show: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true
    }
  });

  mainWindow = win;
  win.loadURL(DASHBOARD_URL);

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  win.once("ready-to-show", () => {
    const settings = readSettings();
    const startHidden = settings.startHidden || process.env.FRIDAY_START_HIDDEN === "1" || process.argv.includes("--hidden");
    if (!startHidden) win.show();
  });

  win.on("close", (event) => {
    if (!isQuitting) {
      event.preventDefault();
      win.hide();
    }
  });

  win.on("closed", () => {
    mainWindow = null;
  });

  return win;
}

function createTray() {
  if (tray) return;
  tray = new Tray(trayIcon());
  tray.setToolTip("Friday Command Center");
  tray.on("click", () => {
    createWindow().show();
  });
  rebuildTrayMenu();
}

function rebuildTrayMenu() {
  const settings = readSettings();
  const menu = Menu.buildFromTemplate([
    { label: "Show Friday", click: () => createWindow().show() },
    { label: "Hide Friday", click: () => mainWindow && mainWindow.hide() },
    { type: "separator" },
    {
      label: "Start at login",
      type: "checkbox",
      checked: Boolean(settings.openAtLogin),
      click: (item) => setOpenAtLogin(item.checked)
    },
    { label: "Open dashboard in browser", click: () => shell.openExternal(DASHBOARD_URL) },
    { label: "Reload dashboard", click: () => mainWindow && mainWindow.reload() },
    { type: "separator" },
    { label: "Quit", click: quitApp }
  ]);
  tray.setContextMenu(menu);
}

function setOpenAtLogin(openAtLogin) {
  const settings = { ...readSettings(), openAtLogin: Boolean(openAtLogin) };
  writeSettings(settings);
  app.setLoginItemSettings({
    openAtLogin: settings.openAtLogin,
    path: process.execPath,
    args: ["--hidden"]
  });
  rebuildTrayMenu();
}

function syncLoginSettings() {
  const settings = readSettings();
  if (process.env.FRIDAY_AUTOSTART === "1") {
    settings.openAtLogin = true;
    writeSettings(settings);
  }
  app.setLoginItemSettings({
    openAtLogin: Boolean(settings.openAtLogin),
    path: process.execPath,
    args: ["--hidden"]
  });
}

function trayIcon() {
  const svg = encodeURIComponent(`
    <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">
      <rect width="32" height="32" rx="8" fill="#151914"/>
      <path d="M8 9h17v4H13v4h10v4H13v7H8z" fill="#8CFF9A"/>
    </svg>
  `);
  return nativeImage.createFromDataURL(`data:image/svg+xml;charset=utf-8,${svg}`);
}

function quitApp() {
  isQuitting = true;
  app.quit();
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    const win = createWindow();
    win.show();
    win.focus();
  });

  app.whenReady().then(() => {
    syncLoginSettings();
    createTray();
    createWindow();

    app.on("activate", () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
      else createWindow().show();
    });
  });

  app.on("before-quit", () => {
    isQuitting = true;
  });

  app.on("window-all-closed", () => {
    if (process.platform === "darwin") return;
  });
}

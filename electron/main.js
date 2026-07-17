// main.js — 明管家 v0.3 Electron 主进程
// 职责：拉起后端（uvicorn 子进程 / 打包后用 backend.exe）→ 等待 /health → 窗口 → 托盘 + 单实例 + 关闭到托盘
'use strict';

const { app, BrowserWindow, Tray, Menu, nativeImage, shell, Notification } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

const IS_PACKAGED = app.isPackaged;

// 桌面端安装后：
//   <resourcesPath>/backend/backend.exe              (PyInstaller --onedir 产物，在 extraResources 根下)
//   <resourcesPath>/backend/_internal/backend/frontend/  (前端静态资源，由 spec 把 frontend/ 拷到 _internal/backend/frontend/)
//
// dev 模式：
//   <lifemgr-pwa>/dist-backend/backend/backend.exe   （本地 PyInstaller 产物，方便集成测试）
//   <lifemgr-pwa>/frontend/                         （dev 前端）
const DEV_LIFEMGR_ROOT = path.resolve(__dirname, '..');
const RESOURCES_ROOT = IS_PACKAGED ? process.resourcesPath : DEV_LIFEMGR_ROOT;

function getBackendExePath() {
  if (IS_PACKAGED) {
    return path.join(RESOURCES_ROOT, 'backend', 'backend.exe');
  }
  return path.join(DEV_LIFEMGR_ROOT, 'dist-backend', 'backend', 'backend.exe');
}

function getFrontendDir() {
  if (IS_PACKAGED) {
    return path.join(RESOURCES_ROOT, 'backend', '_internal', 'backend', 'frontend');
  }
  return path.join(DEV_LIFEMGR_ROOT, 'frontend');
}

const PORT = Number(process.env.LIFEMGR_PORT || 8766);
const ICON_PATH = path.join(__dirname, 'icon.png');
const HEALTH_TIMEOUT_MS = 15000;

let backendProc = null;
let mainWindow = null;
let tray = null;
let isQuitting = false;
let backendReady = false;

// ---------- 单实例锁 ----------
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      if (!mainWindow.isVisible()) mainWindow.show();
      mainWindow.focus();
    }
  });
}

// ---------- 后端 spawn ----------
function startBackend() {
  const backendExe = getBackendExePath();
  const env = {
    ...process.env,
    LIFEMGR_PORT: String(PORT),
    LIFEMGR_DATA_DIR: app.getPath('userData'),
    LIFEMGR_FRONTEND_DIR: getFrontendDir(),
    LIFEMGR_LOG_LEVEL: 'warning',
    PYTHONUNBUFFERED: '1',
  };

  console.log('[main] backend:', backendExe);
  console.log('[main] dataDir :', env.LIFEMGR_DATA_DIR);
  console.log('[main] frontend:', env.LIFEMGR_FRONTEND_DIR);

  if (IS_PACKAGED || fs_existsSync(backendExe)) {
    // 桌面端 / dev 模式但已 PyInstaller 打包：直接 spawn exe
    backendProc = spawn(backendExe, [], {
      env,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
  } else {
    // dev 模式（未打包）：调系统 Python
    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
    backendProc = spawn(pythonCmd, [
      '-m', 'uvicorn', 'backend.main:app',
      '--host', '127.0.0.1', '--port', String(PORT),
      '--no-access-log', '--log-level', 'warning',
    ], {
      cwd: DEV_LIFEMGR_ROOT,
      env,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
  }

  backendProc.stdout.on('data', (d) => process.stdout.write(`[backend] ${d}`));
  backendProc.stderr.on('data', (d) => process.stderr.write(`[backend] ${d}`));
  backendProc.on('exit', (code, signal) => {
    backendReady = false;
    console.log(`[backend] exited code=${code} signal=${signal}`);
    backendProc = null;
  });
}

function fs_existsSync(p) {
  try { return require('fs').existsSync(p); } catch (_) { return false; }
}

function waitForHealth(timeoutMs = HEALTH_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const tick = () => {
      const req = http.get({ host: '127.0.0.1', port: PORT, path: '/health', timeout: 800 }, (res) => {
        res.resume();
        if (res.statusCode === 200) return resolve();
        retryOrFail();
      });
      req.on('error', () => { try { req.destroy(); } catch (_) {} retryOrFail(); });
    };
    const retryOrFail = () => {
      if (Date.now() - start >= timeoutMs) return reject(new Error('backend health timeout'));
      setTimeout(tick, 250);
    };
    tick();
  });
}

// ---------- 窗口 ----------
async function createWindow() {
  await waitForHealth();
  backendReady = true;

  mainWindow = new BrowserWindow({
    width: 480,
    height: 900,
    minWidth: 380,
    minHeight: 640,
    backgroundColor: '#0f1115',
    title: 'daydayup',
    icon: ICON_PATH,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.setMenuBarVisibility(false);
  await mainWindow.loadURL(`http://127.0.0.1:${PORT}/`);

  // 关闭按钮 → 最小化到托盘（除非真的退出）
  mainWindow.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault();
      mainWindow.hide();
      if (Notification.isSupported() && process.platform === 'win32') {
        new Notification({
          title: 'daydayup 仍在后台运行',
          body: '点击托盘图标可重新打开。',
          silent: true,
        }).show();
      }
    }
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
}

// ---------- 托盘 ----------
function createTray() {
  const img = nativeImage.createFromPath(ICON_PATH).isEmpty()
    ? nativeImage.createEmpty()
    : nativeImage.createFromPath(ICON_PATH);
  tray = new Tray(img);
  tray.setToolTip(`daydayup v0.2 · 后端 ${backendReady ? '✓' : '…'} :${PORT}`);
  refreshTrayMenu();
  tray.on('click', () => toggleWindow());
  tray.on('double-click', () => toggleWindow());
}

function refreshTrayMenu() {
  if (!tray) return;
  const menu = Menu.buildFromTemplate([
    { label: '打开 daydayup', click: () => showWindow() },
    {
      label: backendReady ? `后端: ✓ :${PORT}` : '后端: 启动中…',
      enabled: false,
    },
    { label: '重新加载', click: () => mainWindow && mainWindow.reload() },
    { type: 'separator' },
    {
      label: '开机自启',
      type: 'checkbox',
      checked: app.getLoginItemSettings().openAtLogin,
      click: (mi) => app.setLoginItemSettings({ openAtLogin: mi.checked, openAsHidden: true }),
    },
    { type: 'separator' },
    { label: '退出 daydayup', click: () => { isQuitting = true; app.quit(); } },
  ]);
  tray.setContextMenu(menu);
}

function showWindow() { if (mainWindow) { mainWindow.show(); mainWindow.focus(); } }
function toggleWindow() {
  if (!mainWindow) return;
  if (mainWindow.isVisible() && !mainWindow.isMinimized()) mainWindow.hide();
  else showWindow();
}

// ---------- 生命周期 ----------
app.whenReady().then(async () => {
  startBackend();
  try {
    await createWindow();
    createTray();
  } catch (err) {
    console.error('[main] startup failed:', err.message);
    new Notification({
      title: 'daydayup 启动失败',
      body: String(err.message).slice(0, 200),
    }).show();
    isQuitting = true;
    app.quit();
  }
});

app.on('window-all-closed', (e) => {
  if (!isQuitting && tray) {
    if (e && typeof e.preventDefault === 'function') e.preventDefault();
  }
});

app.on('before-quit', () => {
  isQuitting = true;
  if (backendProc) {
    try { backendProc.kill(); } catch (_) {}
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow().catch(() => {});
  else showWindow();
});

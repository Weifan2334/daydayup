// main.js — 明管家 v0.3.4 Electron 主进程
// 职责：拉起后端（uvicorn 子进程 / 打包后用 backend.exe）→ 等待 /health → 窗口 → 托盘 + 单实例 + 关闭到托盘
// v0.3.4 改动：① 版本号统一 0.3.4 ② 移除硬编码 API Key，改读 deepseek.key / userData ③ 后端进程树清理 + 崩溃自愈 ④ 全局快捷键 Ctrl+Shift+D
'use strict';

const { app, BrowserWindow, Tray, Menu, nativeImage, shell, Notification, session, globalShortcut } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const http = require('http');

const APP_VERSION = '0.3.4';

// ===================== DeepSeek API Key 注入 =====================
// 安全说明：key 不再以明文落地。
//   - 打包进 ASAR / 开发目录下的 deepseek.key 存储的是 AES-256-GCM 密文（由 encrypt-key.js 生成）。
//   - 主进程启动时用 crypto-key.js 解密，明文仅存在于进程内存，并注入后端环境变量 DEEPSEEK_API_KEY。
//   - 前端（浏览器侧）永远拿不到明文 key，也绕开了直连 DeepSeek 的 CORS 限制。
//   - 没有 AI 设置对话框：key 由内置加密文件统一提供，换 key 须用 encrypt-key.js 重打包。
const { decryptKey, isEncrypted } = require('./crypto-key');

function resolveDeepseekKey() {
  // 打包进 ASAR / 开发目录下的 deepseek.key（密文）
  const candidates = [
    path.join(__dirname, 'deepseek.key'),
    path.join(RESOURCES_ROOT, 'deepseek.key'),
  ];
  for (const p of candidates) {
    try {
      if (fs.existsSync(p)) {
        const raw = fs.readFileSync(p, 'utf8').trim();
        if (!raw) continue;
        // 旧版明文 sk-...（无 ':' 或格式不符）直接当作明文兼容；新密文则解密
        if (isEncrypted(raw)) {
          try {
            const v = decryptKey(raw);
            if (v) return v;
          } catch (e) {
            console.error('[main] 解密 deepseek.key 失败:', e.message);
          }
        } else if (raw) {
          return raw; // 兼容旧明文格式
        }
      }
    } catch (_) { /* ignore */ }
  }
  // 都没有：返回空串，后端 ai.py 会提示未配置（不影响其它功能）
  return '';
}

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

// 后端崩溃自愈参数
const MAX_BACKEND_RESTARTS = 3;
const RESTART_BACKOFF_BASE_MS = 2000;
const RESTART_BACKOFF_CAP_MS = 8000;

let backendProc = null;
let mainWindow = null;
let tray = null;
let isQuitting = false;
let backendReady = false;
let backendRestartCount = 0;
let backendRestartTimer = null;
let backendStarting = false; // 防止 startBackend 重入

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
  if (backendStarting || backendProc) return; // 防重入
  backendStarting = true;

  const backendExe = getBackendExePath();
  const env = {
    ...process.env,
    LIFEMGR_PORT: String(PORT),
    LIFEMGR_DATA_DIR: app.getPath('userData'),
    LIFEMGR_FRONTEND_DIR: getFrontendDir(),
    LIFEMGR_LOG_LEVEL: 'warning',
    DEEPSEEK_API_KEY: resolveDeepseekKey(),
    PYTHONUNBUFFERED: '1',
  };

  console.log('[main] backend:', backendExe);
  console.log('[main] dataDir :', env.LIFEMGR_DATA_DIR);
  console.log('[main] frontend:', env.LIFEMGR_FRONTEND_DIR);
  console.log('[main] deepseek key:', env.DEEPSEEK_API_KEY ? `已注入(${env.DEEPSEEK_API_KEY.length}字符)` : '未配置（AI 功能将禁用）');

  const useExe = IS_PACKAGED || fs.existsSync(backendExe);
  if (useExe) {
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

  backendStarting = false;

  backendProc.stdout.on('data', (d) => process.stdout.write(`[backend] ${d}`));
  backendProc.stderr.on('data', (d) => process.stderr.write(`[backend] ${d}`));
  backendProc.on('exit', (code, signal) => {
    const pid = backendProc ? backendProc.pid : null;
    backendReady = false;
    backendProc = null;
    console.log(`[backend] exited code=${code} signal=${signal} pid=${pid}`);
    refreshTrayMenu();
    // 非主动退出 + 非零退出码 → 崩溃自愈
    if (!isQuitting && code !== 0 && code !== null) {
      scheduleBackendRestart(`后端异常退出(code=${code})`);
    }
  });
  backendProc.on('error', (err) => {
    console.error('[backend] spawn error:', err.message);
    backendReady = false;
    backendProc = null;
    if (!isQuitting) scheduleBackendRestart(`后端启动失败(${err.message})`);
  });
}

// ---------- 后端崩溃自愈 ----------
function scheduleBackendRestart(reason) {
  if (backendRestartTimer) return; // 已在等待重启
  if (backendRestartCount >= MAX_BACKEND_RESTARTS) {
    console.error(`[backend] 已达最大重启次数(${MAX_BACKEND_RESTARTS})，放弃自愈`);
    if (Notification.isSupported()) {
      new Notification({
        title: 'daydayup 后端异常',
        body: `${reason}，已多次重启失败，请手动重启应用。`,
      }).show();
    }
    return;
  }
  backendRestartCount++;
  const delay = Math.min(RESTART_BACKOFF_BASE_MS * backendRestartCount, RESTART_BACKOFF_CAP_MS);
  console.log(`[backend] ${reason}，${delay}ms 后第 ${backendRestartCount}/${MAX_BACKEND_RESTARTS} 次自愈重启...`);
  refreshTrayMenu();
  backendRestartTimer = setTimeout(async () => {
    backendRestartTimer = null;
    startBackend();
    try {
      await waitForHealth();
      backendReady = true;
      backendRestartCount = 0; // 恢复成功，重置计数
      refreshTrayMenu();
      if (mainWindow) {
        mainWindow.reload();
      }
      if (Notification.isSupported()) {
        new Notification({
          title: 'daydayup 后端已恢复',
          body: '后端自动重启成功，已刷新界面。',
          silent: true,
        }).show();
      }
      console.log('[backend] 自愈重启成功');
    } catch (e) {
      backendReady = false;
      refreshTrayMenu();
      console.error('[backend] 自愈重启后健康检查失败:', e.message);
      scheduleBackendRestart('健康检查超时');
    }
  }, delay);
}

// ---------- 后端进程树清理（Windows 下 taskkill /T /F 杀干净子进程）----------
function killBackendTree() {
  if (!backendProc) return;
  const pid = backendProc.pid;
  // 先取消可能 pending 的自愈重启
  if (backendRestartTimer) { clearTimeout(backendRestartTimer); backendRestartTimer = null; }
  try {
    if (process.platform === 'win32' && pid) {
      // /T 连子进程一起杀，/F 强制；避免 PyInstaller --onedir 的残留线程
      spawn('taskkill', ['/PID', String(pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
    } else {
      try { backendProc.kill('SIGTERM'); } catch (_) {}
    }
  } catch (_) {}
  backendProc = null;
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
  refreshTrayMenu();

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 1024,
    minHeight: 680,
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

  // 拦截文件拖放导致的意外导航（file: 协议），把拖放交给渲染进程处理
  mainWindow.webContents.on('will-navigate', (e, url) => {
    if (url.startsWith('file:')) e.preventDefault();
  });

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
  tray.setToolTip(`daydayup v${APP_VERSION} · 后端 ${backendReady ? '✓' : '…'} :${PORT}`);
  refreshTrayMenu();
  tray.on('click', () => toggleWindow());
  tray.on('double-click', () => toggleWindow());
}

function refreshTrayMenu() {
  if (!tray) return;
  let backendLabel;
  if (backendReady) {
    backendLabel = `后端: ✓ :${PORT}`;
  } else if (backendRestartTimer) {
    backendLabel = `后端: 重启中(${backendRestartCount}/${MAX_BACKEND_RESTARTS})…`;
  } else {
    backendLabel = '后端: 启动中…';
  }
  const menu = Menu.buildFromTemplate([
    { label: '打开 daydayup', click: () => showWindow() },
    { label: backendLabel, enabled: false },
    { label: '重新加载', click: () => mainWindow && mainWindow.reload() },
    { label: '重启后端', click: () => { killBackendTree(); scheduleBackendRestart('手动重启后端'); } },
    { type: 'separator' },
    {
      label: '开机自启',
      type: 'checkbox',
      checked: app.getLoginItemSettings().openAtLogin,
      click: (mi) => app.setLoginItemSettings({ openAtLogin: mi.checked, openAsHidden: true }),
    },
    { label: '全局快捷键 Ctrl+Shift+D', enabled: false },
    { type: 'separator' },
    { label: '退出 daydayup', click: () => { isQuitting = true; app.quit(); } },
  ]);
  tray.setContextMenu(menu);
  tray.setToolTip(`daydayup v${APP_VERSION} · 后端 ${backendReady ? '✓' : '…'} :${PORT}`);
}

function showWindow() { if (mainWindow) { mainWindow.show(); mainWindow.focus(); } }
function toggleWindow() {
  if (!mainWindow) return;
  if (mainWindow.isVisible() && !mainWindow.isMinimized()) mainWindow.hide();
  else showWindow();
}

// ---------- 全局快捷键 ----------
function registerGlobalShortcut() {
  // Ctrl+Shift+D 唤起/隐藏主窗口
  const acc = 'Ctrl+Shift+D';
  const ok = globalShortcut.register(acc, () => toggleWindow());
  if (!ok) console.error('[main] 全局快捷键注册失败:', acc);
  else console.log('[main] 全局快捷键已注册:', acc);
}

// ---------- 生命周期 ----------
app.whenReady().then(async () => {
  // 每次启动强制清空前端的 HTTP 缓存、Service Worker 与 CacheStorage，
  // 避免前端更新后仍显示旧界面（Electron 桌面端后端始终本地可用，不需要离线缓存）。
  try {
    await session.defaultSession.clearCache();
    await session.defaultSession.clearStorageData({
      storages: ['serviceworkers', 'cachestorage'],
    });
  } catch (e) {
    console.error('[main] clear cache failed:', e.message);
  }

  registerGlobalShortcut();
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
  killBackendTree();
});

app.on('will-quit', () => {
  // 注销全局快捷键，避免退出后仍占用
  try { globalShortcut.unregisterAll(); } catch (_) {}
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow().catch(() => {});
  else showWindow();
});

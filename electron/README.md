# 明管家 桌面端 v0.3.4

Electron 桌面壳，拉起 FastAPI 后端做子进程（PyInstaller 打包为 `backend.exe`），**复用前端 100%**。

## v0.3.4 变更要点

| 维度 | 改动 |
|---|---|
| 安全 | 移除 `main.js` 中硬编码的 DeepSeek API Key 明文常量；改为优先读 `deepseek.key`（打包进 ASAR）→ 再读 `userData/deepseek.json`（用户应用内设置）→ 都无则 AI 禁用但不崩溃。`deepseek.key` 已加入 `package.json` files。 |
| 版本号 | 统一为 0.3.4（`main.js` 注释 / 托盘 tooltip / `preload.js` / `main.py` FastAPI version / `package.json` description）。 |
| 进程健壮性 | Windows 下后端退出改用 `taskkill /T /F /PID` 杀整个进程树，避免 PyInstaller `--onedir` 子线程残留；后端异常退出时自动重启（最多 3 次、指数退避），成功后刷新界面。 |
| 桌面功能 | 全局快捷键 `Ctrl+Shift+D` 唤起/隐藏窗口；拖拽 `.db` 备份到窗口任意位置即可导入（复用 `/api/data/import`，带确认与覆盖提示）；托盘菜单新增「重启后端」。 |
| 打包瘦身 | `electronLanguages` 仅保留 `zh-CN`/`en-US`（locales 40M→~3M）；PyInstaller spec 额外排除 `unittest`/`pydoc`/`setuptools`/`pip` 等未用标准库。 |

> ⚠️ **API Key 轮换提醒**：旧 key 此前以明文形式存在于 `main.js` 源码中，建议到 DeepSeek 平台轮换一次，再把新 key 写入 `electron/deepseek.key`（开发）或应用内「目标 → 谋士 → AI 设置」（运行时，存于用户数据目录）。

## 设计原则

| 维度 | 选择 | 理由 |
|---|---|---|
| UI | 复用前端 HTML/CSS/JS | 0 改前端，桌面能跑全功能 |
| 后端 | PyInstaller 打包的 `backend.exe` 子进程 | 数据层零重写，开箱即用免装 Python |
| 端口 | 8766（桌面默认） | 不与 v0.1 dev 的 8765 冲突 |
| 平台 | Windows 首发 | 用户主场 |
| 系统集成 | 托盘 + 系统通知 + 单实例 + 开机自启 + 全局快捷键 + 拖拽导入 | 桌面软件的完整集 |

## 目录

```
electron/
├── package.json       # electron-builder 配置（含 electronLanguages 瘦身）
├── main.js            # 主进程：spawn 后端 + 窗口 + 托盘 + 快捷键 + 崩溃自愈
├── preload.js         # 极简 contextBridge
├── deepseek.key       # 本地兜底 API Key（gitignore，打包入 ASAR）
├── icon.png           # 32x32 托盘图标
├── icon-256.png       # 应用图标
└── README.md
```

## 构建

```bash
cd lifemgr-pwa
python scripts/build-backend.py     # 先打后端 → dist-backend/backend/backend.exe

cd electron
npm install
npm run build            # 出 NSIS 安装包：release/daydayup-Setup-0.3.4.exe
# 或仅出免安装目录：
npm run build:dir        # release/win-unpacked/
```

## 桌面能力清单（v0.3.4 已实现）

- [x] 单实例锁 + second-instance → 唤起已有窗口
- [x] 后端子进程 spawn + 健康检查轮询 + 超时兜底
- [x] 后端进程树清理（`taskkill /T /F`）+ 异常崩溃自愈（3 次退避重启）
- [x] 托盘菜单：打开 / 后端状态 / 重新加载 / 重启后端 / 开机自启 / 退出
- [x] 全局快捷键 `Ctrl+Shift+D` 唤起/隐藏
- [x] 拖拽 `.db` 备份导入（带覆盖确认）
- [x] 关闭按钮 → 最小化到托盘（通知一次）
- [x] `setWindowOpenHandler` 拦截 window.open → 外链 `shell.openExternal`
- [x] `will-navigate` 拦截 `file:` 协议，防止拖放意外导航
- [x] preload 沙箱 + contextIsolation + nodeIntegration:false
- [x] before-quit 时杀后端进程树 + 注销全局快捷键

## 桌面能力清单（暂未做）

- [ ] 自动更新（electron-updater）：需发布源 + 代码签名，个人项目暂缓；当前通过重新安装升级
- [ ] 截图拖拽导入（目前仅支持 `.db` 数据库备份）

## 已知约束

- 桌面端启动占用 8766；冲突时用 `LIFEMGR_PORT` 覆盖
- 未配置 DeepSeek Key 时 AI「谋士」功能禁用，其它功能不受影响
- 全局快捷键 `Ctrl+Shift+D` 若被其它软件占用会注册失败（主进程日志可见）

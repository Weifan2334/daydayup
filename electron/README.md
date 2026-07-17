# 明管家 桌面端 v0.2

Electron 桌面壳 v0.2，拉起 FastAPI 后端做子进程，**复用 v0.1 前端 100%**。

## 设计原则

| 维度 | 选择 | 理由 |
|---|---|---|
| UI | 复用 v0.1 HTML/CSS/JS | 0 改前端，2 周桌面能跑全功能 |
| 后端 | 内嵌 uvicorn 子进程 | 数据层零重写，飞书同步代码原样搬 |
| 端口 | 8766（桌面默认） | 不与 v0.1 dev 的 8765 冲突 |
| 平台 | Windows 首发 | 用户主场 |
| 系统集成 | 托盘 + 系统通知 + 单实例 + 开机自启 | 桌面软件的最少集 |
| 启动后端 | `python -m uvicorn` 调系统 Python | v0.2.5 再 PyInstaller 单 exe |

## 目录

```
electron/
├── package.json       # electron devDeps
├── main.js            # 主进程：spawn 后端 + 窗口 + 托盘
├── preload.js         # 极简 contextBridge
├── gen-icon.js        # 0 依赖 PNG 生成器（暖陶土 #d4a373）
├── icon.png           # 32x32 托盘图标
├── icon-256.png       # 应用图标
└── README.md
```

## 启动

```bash
cd lifemgr-pwa/electron
npm install      # 装 electron v32 + 生成图标
npm start        # 起桌面端，自动 spawn uvicorn
```

也可指定端口：
```bash
LIFEMGR_PORT=8788 npm start
```

## 桌面能力清单（v0.2 已实现）

- [x] 单实例锁 + second-instance → 唤起已有窗口
- [x] 后端子进程 spawn + 健康检查轮询 + 超时兜底
- [x] 关闭按钮 → 最小化到托盘（通知一次）
- [x] 托盘菜单：打开 / 重新加载 / 开机自启 / 退出
- [x] 托盘单击 / 双击切换显示
- [x] `setWindowOpenHandler` 拦截 window.open → 外链 `shell.openExternal`
- [x] preload 沙箱 + contextIsolation + nodeIntegration:false
- [x] before-quit 时杀后端进程

## 桌面能力清单（v0.2 暂未做）

- [ ] 全局快捷键（如 Ctrl+Shift+M 唤起）
- [ ] 文件拖拽导入（截图/导出 csv）
- [ ] PyInstaller 单 exe 打包（v0.2.5）
- [ ] 自动更新（v0.3+）

## 已知约束

- 系统 Python 必须有 `uvicorn`（在 lifemgr-pwa 根目录 `pip install -r requirements.txt` 即可）
- 桌面端启动时占用 8766；若有冲突用 `LIFEMGR_PORT` 覆盖
- 主进程 console.log 在 Windows 下不直接可见，看 `npm start` 输出

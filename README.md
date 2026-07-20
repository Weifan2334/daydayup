# 明管家 / daydayup v0.3.4

范先生的个人日常管理 PWA + Electron 桌面应用。

> 设计原则：被动捕获 > 主动录入；看板 > 文档；决策辅助 > 数据陈列。

**完整更新日志 → [CHANGELOG.md](./CHANGELOG.md)**

---

## ✨ v0.3.4 亮点

- **日历回顾** — 过去日期三栏概览（真实记录 / 任务完成 / 金币分布）+ DeepSeek 日报入口
- **AI 定制作息轴** — 输入自身情况，DeepSeek 生成覆盖式推荐作息
- **计划规划** — 模糊计划 → AI 拆解为 4~8 条可执行事件，一键采纳
- **谋士小锦囊** — Q 版谋士形象 + AI 推荐事件时间段
- **24 枚太极金币** — 亮金实体圆币 + 太极浮雕 + 边缘齿纹，随整点暗淡
- **今日双栏视图** — 作息时间轴（推荐）与真实记录网格并排；网格支持拖拽/拉伸/新建
- **桌面端** — 全局快捷键 `Ctrl+Shift+D`、拖拽 `.db` 导入、后端异常自动重启
- **DeepSeek Key 加密** — AES-256-GCM 密文存储，前端/磁盘/asar 无明文

---

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.14 + FastAPI + SQLite (WAL) |
| 前端 | 原生 HTML/CSS/JS PWA（无框架，深色 `#0f1115` + 暖陶土 `#d4a373`） |
| 桌面壳 | Electron 32 + electron-builder |
| AI | DeepSeek 代理（后端 `services/ai.py`，key 不下发前端） |
| 数据 | 本地 SQLite（`data/lifemgr.db`），备份同步至腾讯云 |

---

## 启动

### 开发模式

```bash
# 安装依赖
pip install -r requirements.txt

# 启动后端（带 reload）
cd lifemgr-pwa
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8765
```

浏览器打开 <http://127.0.0.1:8765>。

**PWA 安装**：Chrome/Edge 右上角「安装应用」→ 桌面图标 / 手机主屏。

### 桌面端打包

```bash
# 1. 打包后端（PyInstaller → dist-backend/backend/backend.exe）
python scripts/build-backend.py

# 2. 打包桌面端（electron-builder → win-unpacked/daydayup.exe）
cd electron
./node_modules/.bin/electron-builder --win --dir --x64

# 3. 出 NSIS 安装包
npm run build    # = electron-builder --win nsis
```

> ⚠️ 打包前先杀残留 `daydayup.exe` / `backend.exe` 进程，否则 `EBUSY` 报错。

---

## API 速查

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/api/today?date=YYYY-MM-DD` | 今日聚合视图 |
| GET | `/api/tasks?date=YYYY-MM-DD` | 当日任务列表 |
| POST | `/api/tasks?date=YYYY-MM-DD` | 加任务 `{title, anchor_time?, duration_min?}` |
| POST | `/api/tasks/{id}/toggle` | 切换完成 |
| DELETE | `/api/tasks/{id}` | 删除 |
| GET | `/api/actual_records?date=YYYY-MM-DD` | 当日真实记录 |
| POST | `/api/ai/chat` | DeepSeek 对话 |
| GET | `/api/coins` | 金币查询 |
| GET | `/api/anchors` | 全部作息锚点 |
| GET | `/api/reminders` | 全部提醒 |

---

## 目录结构

```
lifemgr-pwa/
├── backend/
│   ├── main.py               # FastAPI 入口 (v0.3.4)
│   ├── db.py                 # SQLite 封装（per-thread 连接 + busy_timeout）
│   ├── models.py             # Pydantic 模型
│   ├── services/
│   │   ├── ai.py             # DeepSeek 代理（新）
│   │   ├── today.py          # 今日聚合逻辑
│   │   ├── calendar.py       # 日历服务
│   │   ├── crypto.py         # 加解密工具
│   │   └── keygen.py         # 金币系统
│   └── data_sources/         # 外部数据接入
├── frontend/
│   ├── index.html            # 主视图
│   ├── app.js                # 前端逻辑 (IIFE)
│   ├── styles.css            # 深色样式 + 暖陶土
│   ├── audio.js              # 音效
│   ├── manifest.json         # PWA manifest
│   ├── service-worker.js     # 离线缓存
│   └── assets/shaoxia/       # 少侠主题资源
├── electron/
│   ├── main.js               # Electron 主进程（spawn 后端 + 窗口 + 托盘）
│   ├── preload.js            # 安全上下文桥接
│   ├── crypto-key.js         # AES-256-GCM 加解密（新）
│   ├── encrypt-key.js        # Key 轮换脚本（新）
│   └── deepseek.key          # DeepSeek key 密文
├── scripts/
│   ├── build-backend.py      # PyInstaller 打包脚本
│   ├── backend.spec          # PyInstaller spec
│   └ smoke-packaged-backend.py  # 打包后冒烟测试
│   └── test-*.py             # 各模块测试
├── tests/                    # 自动化测试
├── data/lifemgr.db           # SQLite（首次启动创建）
├── CHANGELOG.md              # 更新日志
├── requirements.txt
└── README.md
```

---

## 设计

| 要素 | 值 |
|---|---|
| 主色 | `#d4a373` 暖陶土金 / `#a05a2c` 深陶土 |
| 背景 | `#0f1115` 黑炭 / `#1a1d24` 卡片 / `#20242d` 提升层 |
| 字体 | system-ui + 苹方 / 微软雅黑 |
| 风格 | 武侠三国志主题 · 极简 · 密集信息 · 单手可操作 |
| 桌面图标 | 墨青底 + 居中长剑 + 右上弯月 |

---

## 路线图

| 阶段 | 交付 |
|---|---|
| **v0.3.4** ✅ | 日历回顾 · AI 作息/计划 · 金币系统 · 桌面端强化 · Key 加密 |
| v0.4 | 持仓/备孕/职业 三维决策建议 |
| v0.5 | 日/周/月自动复盘草稿 |
| v0.6 | OKR / 5 年 / 10 年目标树 |

---

## 许可

个人项目，未公开许可。

# 明管家 v0.1

范先生的个人日常管理 PWA。第一阶段交付：**Today 视图**。

> 设计原则：被动捕获 > 主动录入；看板 > 文档；决策辅助 > 数据陈列。

## 技术栈

- 后端：Python 3.14 + FastAPI 0.139 + SQLite (WAL)
- 前端：原生 HTML/CSS/JS PWA（无框架，深色 + 暖陶土强调色）
- 数据：本地 SQLite（`data/lifemgr.db`）
- 部署：单机 `127.0.0.1:8765`（v0.1.1 再上内网穿透）

## 启动

```bash
# 一次性：装依赖
python -m pip install -r requirements.txt

# 启动后端（带 reload）
cd lifemgr-pwa
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8765
```

浏览器打开 <http://127.0.0.1:8765>。

**PWA 安装**：Chrome/Edge 右上角「安装应用」→ 桌面图标 / 手机主屏。

## API 速查

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/api/today?date=YYYY-MM-DD` | 今日聚合视图（前端主入口） |
| GET | `/api/tasks?date=YYYY-MM-DD` | 当日任务列表 |
| POST | `/api/tasks?date=YYYY-MM-DD` | 加任务 `{title, anchor_time?, duration_min?}` |
| POST | `/api/tasks/{id}/toggle` | 切换完成 |
| DELETE | `/api/tasks/{id}` | 删除 |
| GET | `/api/anchors` | 全部作息锚点 |
| GET | `/api/reminders` | 全部提醒 |
| POST | `/api/init/reseed` | 重新种子锚点 + 提醒 |

## 数据源（v0.1）

| 模块 | 数据 | 来源 |
|---|---|---|
| 作息锚点 | 6 个硬锚点 | 飞书文档「范先生作息表 v3」（手工落库；首次启动自动 seed） |
| 提醒 | 9 条 cron 提醒 | MEMORY.md「定时任务」表（首次启动自动 seed） |
| 任务 | 手动添加 / 未来 work-logs 反推 | DB `today_tasks` |

> v0.1 暂无：飞书日历 API（OAuth 已开通，工具未到位）/ cron 历史 / work-logs 自动反推。

## 目录结构

```
lifemgr-pwa/
├── backend/
│   ├── main.py             # FastAPI 入口
│   ├── db.py               # SQLite 封装
│   ├── models.py           # Pydantic 模型
│   ├── services/today.py   # 今日聚合逻辑
│   └── data_sources/       # v0.1.5 接入飞书
├── frontend/
│   ├── index.html          # Today 视图
│   ├── app.js              # 前端逻辑
│   ├── styles.css          # 深色样式
│   ├── manifest.json       # PWA manifest
│   ├── service-worker.js   # 离线缓存
│   └── icons/              # 占位图标（SVG）
├── data/lifemgr.db         # SQLite（首次启动创建）
├── tests/test_today.py     # smoke tests
├── requirements.txt
└── README.md
```

## 路线图

| 阶段 | 时间 | 交付 |
|---|---|---|
| **v0.1** | 2 周 | Today 视图 · 锚点+提醒+任务聚合 |
| v0.1.5 | +3 天 | 飞书日历 API 接入 |
| v0.2 | W3-4 | OKR / 5 年 / 10 年目标树 |
| v0.3 | W5-6 | 日/周/月自动复盘草稿 |
| v0.4 | W7-8 | 持仓/备孕/职业 三维决策建议 |

## 设计参考

- 主色：`#d4a373` 暖陶土（明兰花语） / `#e9c89b` 浅花瓣
- 背景：`#0f1115` 黑炭 / `#1a1d24` 卡片 / `#20242d` 提升层
- 字体：system-ui + 苹方 / 微软雅黑
- 风格：极简、密集信息、单手可操作
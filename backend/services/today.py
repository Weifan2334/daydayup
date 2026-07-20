"""今日聚合服务。

输入一个日期，输出 TodayView（一次性返回客户端需要的全部数据）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .. import db


# ---------- 作息表 v4（范先生 2026-07-14 19:37 提供，15 个时间块） ----------
# 工作日周一~周五（weekdays=1,2,3,4,5）；周末 v4.1 待定。
SCHEDULE_V4_BLOCKS: list[dict[str, Any]] = [
    {"start": "07:30", "end": "08:00", "label": "起床 & 简单早餐",
     "note": "保持规律作息，避免熬夜后早上补觉", "weekdays": "1,2,3,4,5,6,7"},
    {"start": "08:00", "end": "08:30", "label": "运动 / 拉伸",
     "note": "慢跑、瑜伽或力量训练，提升专注力", "weekdays": "1,2,3,4,5,6,7"},
    {"start": "08:30", "end": "09:00", "label": "规划当天任务",
     "note": "列出科研优先级（论文写作、实验、数据分析等）", "weekdays": "1,2,3,4,5,6,7"},
    {"start": "09:00", "end": "11:00", "label": "深度科研时间",
     "note": "适合写论文、做复杂数据分析、设计实验方案", "weekdays": "1,2,3,4,5,6,7"},
    {"start": "11:00", "end": "12:00", "label": "次要科研任务",
     "note": "文献阅读、整理实验数据、写实验记录", "weekdays": "1,2,3,4,5,6,7"},
    {"start": "12:00", "end": "13:00", "label": "午餐 & 短暂休息",
     "note": "放松大脑，避免长时间连续工作", "weekdays": "1,2,3,4,5,6,7"},
    {"start": "13:00", "end": "14:00", "label": "午休",
     "note": "20-30 分钟为宜，过长会影响晚间睡眠", "weekdays": "1,2,3,4,5,6,7"},
    {"start": "14:00", "end": "16:00", "label": "实验或项目推进",
     "note": "实验室工作、编程实现、设备测试等", "weekdays": "1,2,3,4,5,6,7"},
    {"start": "16:00", "end": "16:20", "label": "茶歇 & 走动",
     "note": "放松眼睛、活动身体", "weekdays": "1,2,3,4,5,6,7"},
    {"start": "16:20", "end": "17:30", "label": "学术交流 / 行政事务",
     "note": "课题组会、与学生讨论、填写报表、申请材料", "weekdays": "1,2,3,4,5,6,7"},
    {"start": "17:30", "end": "18:00", "label": "总结与计划",
     "note": "记录成果、整理数据、规划明天任务", "weekdays": "1,2,3,4,5,6,7"},
    {"start": "18:00", "end": "19:00", "label": "晚餐 & 休息",
     "note": "可与同事、朋友交流，转换思维", "weekdays": "1,2,3,4,5,6,7"},
    {"start": "19:00", "end": "21:00", "label": "自由科研时间",
     "note": "补进度、查文献、写论文", "weekdays": "1,2,3,4,5,6,7"},
    {"start": "21:00", "end": "22:00", "label": "放松活动",
     "note": "阅读、音乐、轻运动", "weekdays": "1,2,3,4,5,6,7"},
    {"start": "22:00", "end": "22:30", "label": "睡前准备",
     "note": "避免高强度工作和刷手机", "weekdays": "1,2,3,4,5,6,7"},
]


def _weekday(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return names[dt.weekday()]


def _weekday_num(date_str: str) -> int:
    """1=周一 ... 7=周日"""
    return datetime.strptime(date_str, "%Y-%m-%d").weekday() + 1


def _hm_to_min(hm: str) -> int:
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


def _filter_by_weekday(blocks: list[dict[str, Any]], weekday_num: int) -> list[dict[str, Any]]:
    out = []
    for b in blocks:
        wd = b.get("weekdays", "1,2,3,4,5,6,7")
        if str(weekday_num) in [x.strip() for x in wd.split(",")]:
            out.append(b)
    return out


def _current_block(blocks: list[dict[str, Any]], now_hhmm: str) -> dict[str, Any] | None:
    """现在落在哪个 block（start <= now < end）"""
    now_min = _hm_to_min(now_hhmm)
    for b in blocks:
        if _hm_to_min(b["anchor_time"]) <= now_min < _hm_to_min(b["end_time"]):
            return b
    return None


def _next_block(blocks: list[dict[str, Any]], now_hhmm: str) -> dict[str, Any] | None:
    """下一个还没结束的 block；没有就取明天第一个。"""
    now_min = _hm_to_min(now_hhmm)
    future = [b for b in blocks if _hm_to_min(b["anchor_time"]) > now_min]
    if future:
        return future[0]
    return blocks[0] if blocks else None


def _filter_reminders_for_today(
    reminders: list[dict[str, Any]],
    weekday: int,
    day_of_month: int,
) -> list[dict[str, Any]]:
    out = []
    for r in reminders:
        cadence = r.get("cadence", "daily")
        if cadence == "daily":
            out.append(r)
        elif cadence.startswith("weekly:"):
            n = int(cadence.split(":")[1])
            if weekday == n:
                out.append(r)
        elif cadence.startswith("monthly:"):
            n = int(cadence.split(":")[1])
            if day_of_month == n:
                out.append(r)
    return out


def build_today_view(date_str: str | None = None, user_id: int = 0) -> dict[str, Any]:
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now()
    now_hhmm = now.strftime("%H:%M")
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    weekday_num = _weekday_num(date_str)
    weekday_name = _weekday(date_str)

    # 作息时间块（v4，共享）
    all_blocks = db.list_anchors(enabled_only=True, kind="block")
    today_blocks = _filter_by_weekday(all_blocks, weekday_num)
    current = _current_block(today_blocks, now_hhmm)
    next_b = _next_block(today_blocks, now_hhmm)

    # 兼容旧 anchor（v3 残留 / 用户后续手动加）
    legacy_anchors = db.list_anchors(enabled_only=True, kind="anchor")

    if not user_id:
        user_id = db.current_user_id_or_default()
    tasks = db.list_tasks(user_id, date_str, include_done=True)
    reminders = db.list_reminders(enabled_only=True)
    today_reminders = _filter_reminders_for_today(reminders, weekday_num, dt.day)

    actuals = db.get_actuals_for_date(user_id, date_str)  # {block_id: text}  v2 双栏

    done = sum(1 for t in tasks if t["done"])

    return {
        "today_date": date_str,
        "weekday": weekday_name,
        "weekday_num": weekday_num,
        "current_time": now.strftime("%H:%M:%S"),
        "current_block": current,
        "next_block": next_b,
        "blocks": today_blocks,
        "legacy_anchors": legacy_anchors,
        "tasks": [
            {
                "id": t["id"],
                "task_date": t["task_date"],
                "title": t["title"],
                "source": t["source"],
                "anchor_time": t["anchor_time"],
                "duration_min": t["duration_min"],
                "category": t.get("category", "other"),
                "done": bool(t["done"]),
            }
            for t in tasks
        ],
        "reminders": today_reminders,
        "actuals": {str(k): v for k, v in actuals.items()},
        "summary": {
            "tasks_total": len(tasks),
            "tasks_done": done,
            "tasks_pending": len(tasks) - done,
            "blocks_count": len(today_blocks),
            "reminders_count": len(today_reminders),
        },
    }


# ---------- 种子 ----------

def seed_defaults_if_empty() -> dict[str, str]:
    """首次启动：seed v4 时间块 + 9 条 cron 提醒。

    v4 时间块用 clear_anchors 强制覆盖 v3 6 锚点（v0.1 还没真实用户数据）。
    """
    info = {}

    # v4 强制清空 + 重写
    db.clear_anchors()
    rows = [
        {
            "label": b["label"],
            "anchor_time": b["start"],
            "end_time": b["end"],
            "weekdays": b["weekdays"],
            "note": b["note"],
            "kind": "block",
        }
        for b in SCHEDULE_V4_BLOCKS
    ]
    db.upsert_anchors(rows)
    info["schedule_v4"] = f"seeded {len(rows)} blocks (workdays, from 范先生 2026-07-14 19:37)"

    if not db.list_reminders(enabled_only=False):
        db.upsert_reminders(
            [
                {"label": "晨间锻炼计划发布",      "reminder_time": "20:00", "cadence": "weekly:7",  "source": "cron:d7aecbff"},
                {"label": "晚间锻炼提醒（夫妻）",   "reminder_time": "19:00", "cadence": "daily",      "source": "cron:df0d7a6b"},
                {"label": "工作记录提醒",          "reminder_time": "21:00", "cadence": "daily",      "source": "cron:b022e072"},
                {"label": "基金资讯日报",          "reminder_time": "08:00", "cadence": "daily",      "source": "cron:ffbc24c4"},
                {"label": "投资周报",              "reminder_time": "08:00", "cadence": "weekly:1",   "source": "cron:44b91123"},
                {"label": "基金月度复盘",          "reminder_time": "08:00", "cadence": "monthly:1",  "source": "cron:6a856e7d"},
                {"label": "职业周度复盘",          "reminder_time": "21:00", "cadence": "weekly:7",   "source": "cron:4ce32d61"},
                {"label": "职业月度复盘",          "reminder_time": "21:00", "cadence": "monthly:1",  "source": "cron:5136c1ab"},
                {"label": "周报数据提醒",          "reminder_time": "21:00", "cadence": "weekly:7",   "source": "cron:0c32bebc"},
            ]
        )
        info["reminders"] = "seeded 9 from MEMORY.md cron table"

    return info


def reseed_v4_schedule() -> dict[str, str]:
    """强制 reseed（暴露给 /api/init/reseed）。"""
    info = {}
    db.clear_anchors()
    rows = [
        {
            "label": b["label"],
            "anchor_time": b["start"],
            "end_time": b["end"],
            "weekdays": b["weekdays"],
            "note": b["note"],
            "kind": "block",
        }
        for b in SCHEDULE_V4_BLOCKS
    ]
    db.upsert_anchors(rows)
    info["schedule_v4"] = f"reseeded {len(rows)} blocks"
    return info
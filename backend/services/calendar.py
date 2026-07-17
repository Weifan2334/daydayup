"""日历服务：按月聚合任务统计，生成月历网格。"""
from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from typing import Any

from .. import db


def _ym_to_dt(month_str: str) -> tuple[int, int]:
    dt = datetime.strptime(month_str, "%Y-%m")
    return dt.year, dt.month


def build_calendar_view(month_str: str, today_str: str | None = None, user_id: int = 0) -> dict[str, Any]:
    if today_str is None:
        today_str = datetime.now().strftime("%Y-%m-%d")
    year, month = _ym_to_dt(month_str)
    if not (1 <= month <= 12):
        raise ValueError(f"invalid month: {month_str}")

    cal = calendar.Calendar(firstweekday=0)  # 周一为 0
    weeks = cal.monthdayscalendar(year, month)
    _, days_in_month = calendar.monthrange(year, month)

    stats = db.count_tasks_by_month(user_id or db.current_user_id_or_default(), month_str)

    def make_day(date_str: str, weekday: int) -> dict[str, Any]:
        s = stats.get(date_str, {"total": 0, "done": 0})
        return {
            "date": date_str,
            "weekday": weekday,
            "total": s["total"],
            "done": s["done"],
            "has_tasks": s["total"] > 0,
        }

    days: list[dict[str, Any]] = []
    prev_tail: list[dict[str, Any]] = []
    next_head: list[dict[str, Any]] = []

    for week in weeks:
        for i, d in enumerate(week):
            wd = i + 1  # 周一=1 ... 周日=7
            if d == 0:
                # 属于上月或下月
                if len(days) == 0:
                    # 补上月尾
                    prev = datetime(year, month, 1) - timedelta(days=1)
                    prev_date = (prev.replace(day=prev.day - (6 - i)))  # 周一前的几天
                    # 简化：直接基于当前周序倒推
                    first_of_month = datetime(year, month, 1)
                    days_before_month = (first_of_month.weekday())  # 0=Mon
                    if i < days_before_month:
                        delta = days_before_month - i
                        prev_day_dt = first_of_month - timedelta(days=delta)
                        prev_tail.append(make_day(prev_day_dt.strftime("%Y-%m-%d"), wd))
                else:
                    # 补下月头
                    last_of_month = datetime(year, month, days_in_month)
                    days_after_month = 6 - last_of_month.weekday()
                    if i > days_after_month - 1 or (i >= days_after_month):
                        delta = i - days_after_month + 1
                        next_day_dt = last_of_month + timedelta(days=delta)
                        # 避免越界到下下月
                        if next_day_dt.month == month or len(next_head) == 0 and next_day_dt.month != month:
                            next_head.append(make_day(next_day_dt.strftime("%Y-%m-%d"), wd))
            else:
                date_str = f"{year:04d}-{month:02d}-{d:02d}"
                days.append(make_day(date_str, wd))

    # 用更简洁的方式重新计算 prev_tail / next_head（避免上面边界 bug）
    first_dt = datetime(year, month, 1)
    last_dt = datetime(year, month, days_in_month)
    prev_tail = []
    next_head = []
    # 月历第一行周一的日期：如果不在本月，则属于上月
    first_week_monday = weeks[0][0]  # 0 表示上月
    if first_week_monday == 0:
        # 用 days_before_month 倒推
        wb = first_dt.weekday()  # 0=Mon
        for k in range(wb):
            prev_dt = first_dt - timedelta(days=wb - k)
            prev_tail.append(make_day(prev_dt.strftime("%Y-%m-%d"), k + 1))
    last_weekday = last_dt.weekday()  # 0=Mon
    for k in range(6 - last_weekday):
        nxt_dt = last_dt + timedelta(days=k + 1)
        next_head.append(make_day(nxt_dt.strftime("%Y-%m-%d"), last_weekday + k + 2))

    # 汇总
    days_with_tasks = sum(1 for d in days if d["has_tasks"])
    total_tasks = sum(d["total"] for d in days)
    done_tasks = sum(d["done"] for d in days)
    has_today = any(d["date"] == today_str for d in days)

    return {
        "month": month_str,
        "title": f"{year} 年 {month} 月",
        "first_weekday": 1,  # 周一为第一列
        "days_in_month": days_in_month,
        "prev_month_tail": prev_tail,
        "next_month_head": next_head,
        "days": days,
        "summary": {
            "days_with_tasks": days_with_tasks,
            "total_tasks": total_tasks,
            "done_tasks": done_tasks,
            "has_today": has_today,
        },
    }


def list_tasks_for_date(date_str: str, user_id: int = 0) -> list[dict[str, Any]]:
    return db.list_tasks(user_id or db.current_user_id_or_default(), date_str, include_done=True)
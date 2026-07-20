"""FastAPI 主入口。"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from . import db
from .models import (
    ActualIn, ActualOut, ActualRecordIn, ActualRecordOut, AiAnalyzeIn, AiDailyReportIn, AiPlanIn, AiScheduleIn,
    AuthOut, CalendarView, ChangePasswordIn, CloudBackupIn, CloudBackupOut, CloudConfigIn, CloudConfigOut,
    CloudRestoreCommitIn, CloudRestoreIn, CloudRestorePrepareOut,
    GoalIn, GoalUpdateIn, KeyResultIn, KeyResultUpdateIn,
    LoginIn, RegisterIn, TodayTaskIn, TodayTaskOut, TodayView, UserOut,
)
from .services import auth as auth_service
from .services import calendar as calendar_service
from .services import cloud as cloud_service
from .services import today as today_service
from .services import ai as ai_service

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = Path(os.environ.get("LIFEMGR_FRONTEND_DIR", str(ROOT / "frontend")))

app = FastAPI(title="daydayup v0.3.4", version="0.3.4")

# 金币时间预算：1 天 = 24h = 24 金币；1 金币 = 60 分钟
COIN_BUDGET_DAY = 24
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===================== 鉴权依赖 =====================

def get_current_token(authorization: str | None = Header(default=None)) -> str | None:
    """从 Authorization: Bearer <token> 解析 token。"""
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    if len(parts) == 1:
        return parts[0]
    return None


def require_auth(authorization: str | None = Header(default=None)) -> dict:
    """返回 {'user_id': int, 'username': str, 'token': str}。"""
    token = get_current_token(authorization)
    info = db.lookup_token(token) if token else None
    if not info:
        raise HTTPException(status_code=401, detail="not authenticated")
    return {"user_id": info["user_id"], "username": info["username"], "token": token}


def optional_auth(authorization: str | None = Header(default=None)) -> dict | None:
    token = get_current_token(authorization)
    if not token:
        return None
    info = db.lookup_token(token)
    if not info:
        return None
    return {"user_id": info["user_id"], "username": info["username"], "token": token}


# ===================== 全局异常处理 =====================

@app.exception_handler(ValueError)
def _value_error_handler(request, exc):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(RuntimeError)
def _runtime_error_handler(request, exc):
    logging.exception("runtime error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.exception_handler(auth_service.AuthError)
def _auth_error_handler(request, exc):
    return JSONResponse(status_code=exc.code, content={"detail": str(exc)})


@app.exception_handler(Exception)
def _unhandled_handler(request, exc):
    logging.exception("unhandled: %s", exc)
    return JSONResponse(status_code=500, content={"detail": f"internal error: {type(exc).__name__}"})


# ===================== 生命周期 =====================

@app.on_event("startup")
def _startup() -> None:
    db.get_conn()  # 触发建表
    db.get_or_create_default_user()  # 确保有 default user
    info = today_service.seed_defaults_if_empty()
    if info:
        print(f"[startup] seeded: {info}")


# ===================== Auth API =====================

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": "daydayup v0.3"}


@app.post("/api/auth/register", response_model=AuthOut)
def api_register(payload: RegisterIn) -> dict:
    user = auth_service.register(payload)
    token = db.create_token(user["id"])
    expires_row = db.get_conn().execute(
        "SELECT expires_at FROM auth_tokens WHERE token = ?", (token,)
    ).fetchone()
    return {
        "user": {
            "id": user["id"],
            "username": user["username"],
            "display_name": user.get("display_name"),
            "ssh_registered": bool(user.get("ssh_registered", 0)),
            "created_at": user.get("created_at", ""),
            "last_login_at": user.get("last_login_at"),
        },
        "token": token,
        "expires_at": expires_row["expires_at"] if expires_row else None,
    }


@app.post("/api/auth/login", response_model=AuthOut)
def api_login(payload: LoginIn) -> dict:
    return auth_service.login(payload)


@app.post("/api/auth/logout")
def api_logout(auth: dict = Depends(require_auth)) -> dict[str, str]:
    auth_service.logout(auth["token"])
    return {"status": "logged_out"}


@app.get("/api/auth/me", response_model=UserOut)
def api_me(auth: dict = Depends(require_auth)) -> dict:
    return auth_service.me(auth["token"])


@app.post("/api/auth/change-password")
def api_change_password(payload: ChangePasswordIn, auth: dict = Depends(require_auth)) -> dict[str, str]:
    auth_service.change_password(auth["token"], payload)
    return {"status": "password_changed"}


class SetupSshIn(BaseModel):
    password: str = Field(..., min_length=1)
    poll_timeout: int = Field(90, ge=10, le=180)
    password: str = Field(..., min_length=1)
    poll_timeout: int = Field(90, ge=10, le=180)


@app.post("/api/auth/setup-ssh")
def api_setup_ssh(payload: SetupSshIn, auth: dict = Depends(require_auth)) -> dict:
    """生成 SSH 密钥对 + 上传公钥到 CVM inbox + 轮询注册状态。
    用户登录密码用于加密本地私钥（验证 bcrypt + 派生 AES 密钥）。"""
    from .services import keygen
    user = db.get_user(auth["user_id"])
    if not db.verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="password incorrect")
    return keygen.setup_ssh(auth["user_id"], payload.password, payload.poll_timeout)


# ===================== Today / Tasks / Calendar =====================

@app.get("/api/today", response_model=TodayView)
def api_today(
    date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    auth: dict = Depends(require_auth),
) -> dict:
    return today_service.build_today_view(date, user_id=auth["user_id"])


@app.get("/api/tasks", response_model=list[TodayTaskOut])
def api_list_tasks(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    auth: dict = Depends(require_auth),
) -> list[dict]:
    return db.list_tasks(auth["user_id"], date, include_done=True)


@app.post("/api/tasks", response_model=TodayTaskOut)
def api_add_task(
    date: str = Query(...),
    payload: TodayTaskIn = ...,
    auth: dict = Depends(require_auth),
) -> dict:
    return db.add_task(
        user_id=auth["user_id"],
        task_date=date,
        title=payload.title,
        anchor_time=payload.anchor_time,
        duration_min=payload.duration_min,
        category=payload.category,
    )


@app.post("/api/tasks/{task_id}/toggle", response_model=TodayTaskOut)
def api_toggle_task(task_id: int, auth: dict = Depends(require_auth)) -> dict:
    try:
        return db.toggle_task(auth["user_id"], task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="task not found")


@app.delete("/api/tasks/{task_id}")
def api_delete_task(task_id: int, auth: dict = Depends(require_auth)) -> dict[str, str]:
    db.delete_task(auth["user_id"], task_id)
    return {"status": "deleted"}


@app.get("/api/anchors")
def api_anchors() -> list[dict]:
    # 作息锚点 / 提醒 暂共享
    return db.list_anchors(enabled_only=False)


@app.get("/api/reminders")
def api_reminders() -> list[dict]:
    return db.list_reminders(enabled_only=False)


@app.post("/api/init/reseed")
def api_reseed() -> dict[str, str]:
    return today_service.seed_defaults_if_empty()


@app.post("/api/init/clear_user_data")
def api_clear_user_data(auth: dict = Depends(require_auth)) -> dict[str, int]:
    return db.clear_user_data(auth["user_id"])


# ===================== 时间块实际记录 =====================

@app.post("/api/block_actual", response_model=ActualOut)
def api_upsert_actual(payload: ActualIn, auth: dict = Depends(require_auth)) -> dict:
    db.upsert_actual(auth["user_id"], payload.date, payload.block_id, payload.actual_text)
    return {
        "date": payload.date,
        "block_id": payload.block_id,
        "actual_text": payload.actual_text,
        "updated_at": db.get_actual(auth["user_id"], payload.date, payload.block_id),
    }


@app.get("/api/block_actuals")
def api_get_actuals(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    auth: dict = Depends(require_auth),
) -> dict[str, str]:
    return {str(k): v for k, v in db.get_actuals_for_date(auth["user_id"], date).items()}


# ===================== 自由真实记录（时间轴拖拽） =====================

@app.get("/api/actual_records", response_model=list[ActualRecordOut])
def api_get_actual_records(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    auth: dict = Depends(require_auth),
) -> list[dict]:
    """返回某天用户的自由真实记录列表（按开始时间排序）。"""
    return db.list_actual_records(auth["user_id"], date)


@app.post("/api/actual_records", response_model=ActualRecordOut)
def api_upsert_actual_record(payload: ActualRecordIn, auth: dict = Depends(require_auth)) -> dict:
    """创建或更新一条自由真实记录。id 为空则创建。"""
    return db.upsert_actual_record(
        auth["user_id"], payload.date, payload.start_time, payload.end_time, payload.text, payload.id
    )


@app.delete("/api/actual_records")
def api_delete_actual_record(
    id: int = Query(..., ge=1),
    auth: dict = Depends(require_auth),
) -> dict:
    """删除一条自由真实记录。"""
    deleted = db.delete_actual_record(auth["user_id"], id)
    return {"deleted": deleted}


# ===================== 日历 =====================

@app.get("/api/calendar", response_model=CalendarView)
def api_calendar(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    auth: dict = Depends(require_auth),
) -> dict:
    return calendar_service.build_calendar_view(month, user_id=auth["user_id"])


@app.get("/api/coins")
def api_coins(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    auth: dict = Depends(require_auth),
) -> list[dict]:
    """某单日的金币分布（按类目聚合的时间花费，1 金币 = 1 小时）。"""
    return db.aggregate_coins(auth["user_id"], date, date)


@app.get("/api/tasks_in_range")
def api_tasks_in_range(
    start: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    auth: dict = Depends(require_auth),
) -> list[dict]:
    rows = db.list_tasks_in_range(auth["user_id"], start, end)
    return [
        {
            "id": r["id"],
            "task_date": r["task_date"],
            "title": r["title"],
            "source": r["source"],
            "anchor_time": r["anchor_time"],
            "duration_min": r["duration_min"],
            "category": r.get("category", "other"),
            "done": bool(r["done"]),
        }
        for r in rows
    ]


# ===================== 金币回顾（日 / 周 / 月） =====================

@app.get("/api/review")
def api_review(
    range: str = Query("day", pattern=r"^(day|week|month)$"),
    auth: dict = Depends(require_auth),
) -> dict:
    """日/周/月回顾：按类目聚合金币消耗。1 金币 = 1 小时。

    金币随时间流逝自动扣除（每小时扣 1 金币），未用于事项的时间金币归为「损失」。
    - budget：时间窗金币总量（日=24、周=168、月=24*天数）
    - time_elapsed：已流逝时间对应的金币（按当前时刻算，若范围已结束则等于 budget）
    - used：事件消耗金币（各事项 duration_min 之和 / 60）
    - lost：损失金币 = max(0, time_elapsed - used)
    - remaining：剩余金币 = max(0, budget - time_elapsed)
    """
    from datetime import date as _date, datetime as _dt, timedelta as _td

    now = _dt.now()
    today = now.date()
    if range == "day":
        start = end = today
        budget = COIN_BUDGET_DAY
    elif range == "week":
        monday = today - _td(days=today.weekday())  # weekday(): 周一=0
        start = monday
        end = monday + _td(days=6)
        budget = COIN_BUDGET_DAY * 7
    else:  # month
        start = today.replace(day=1)
        if start.month == 12:
            nxt = start.replace(year=start.year + 1, month=1)
        else:
            nxt = start.replace(month=start.month + 1)
        end = nxt - _td(days=1)
        budget = COIN_BUDGET_DAY * ((end - start).days + 1)

    start_s = start.strftime("%Y-%m-%d")
    end_s = end.strftime("%Y-%m-%d")

    # 时间流逝金币：从范围起点到当前时刻（若范围已完全过去则为 budget）
    if today < start:
        time_elapsed = 0.0
    elif today > end:
        time_elapsed = float(budget)
    else:
        full_days = (today - start).days
        today_hours = now.hour + now.minute / 60.0 + now.second / 3600.0
        time_elapsed = round(full_days * COIN_BUDGET_DAY + today_hours, 4)

    agg = db.aggregate_coins(auth["user_id"], start_s, end_s)
    total_min = sum(r["total_min"] for r in agg)
    used = round(total_min / 60, 2)
    lost = round(max(0.0, time_elapsed - used), 2)
    remaining = round(max(0.0, budget - time_elapsed), 2)
    by_category = [
        {
            "category": (r["category"] or "other"),
            "count": r["count"],
            "minutes": r["total_min"],
            "coins": round(r["total_min"] / 60, 2),
            "done_count": r["done_count"],
        }
        for r in agg
    ]
    tasks = db.list_tasks_in_range(auth["user_id"], start_s, end_s)
    tasks_out = [
        {
            "id": t["id"],
            "task_date": t["task_date"],
            "title": t["title"],
            "category": t.get("category", "other"),
            "anchor_time": t["anchor_time"],
            "duration_min": t["duration_min"],
            "done": bool(t["done"]),
        }
        for t in tasks
    ]
    return {
        "range": range,
        "start": start_s,
        "end": end_s,
        "budget": budget,
        "time_elapsed": time_elapsed,
        "used": used,
        "lost": lost,
        "remaining": remaining,
        "total_minutes": total_min,
        "by_category": by_category,
        "tasks": tasks_out,
    }


# ===================== v0.3 云备份（per-user，内置默认 CVM） =====================
# 内置：所有用户共享同一个 CVM
DEFAULT_CVM = {
    "host": "43.136.130.11",
    "port": 22,
    "username": "daydayup",
    "auth_method": "private_key",
    "remote_path": "/home/daydayup/backups/",
    "os_type": "linux",
}


def _resolve_cvm_config(user_id: int) -> dict:
    """v0.3 C 默认走 daydayup 用户 + 内置的 CVM，user 只需填 private_key 即可。"""
    cfg = db.get_cloud_config(user_id) or {}
    merged = dict(DEFAULT_CVM)
    merged.update({k: v for k, v in cfg.items() if v is not None})
    return merged


@app.get("/api/cloud/config", response_model=CloudConfigOut)
def api_cloud_get_config(auth: dict = Depends(require_auth)) -> dict:
    cfg = db.get_cloud_config(auth["user_id"]) or {}
    base = dict(DEFAULT_CVM)
    base.update({k: v for k, v in cfg.items() if v is not None})
    return {
        "host": base.get("host"),
        "port": int(base.get("port") or 22),
        "username": base.get("username"),
        "auth_method": base.get("auth_method", "private_key"),
        "has_password": bool(base.get("password")),
        "has_private_key": bool(base.get("private_key")),
        "remote_path": base.get("remote_path", "/home/daydayup/backups/"),
        "os_type": base.get("os_type", "linux"),
        "enabled": bool(base.get("enabled", False)),
        "updated_at": cfg.get("updated_at"),
    }


@app.post("/api/cloud/config", response_model=CloudConfigOut)
def api_cloud_save_config(payload: CloudConfigIn, auth: dict = Depends(require_auth)) -> dict:
    merged = dict(DEFAULT_CVM)
    merged.update(payload.model_dump(exclude_unset=True))
    db.upsert_cloud_config(auth["user_id"], merged)
    full = db.get_cloud_config(auth["user_id"]) or {}
    return {
        "host": merged.get("host"),
        "port": int(merged.get("port") or 22),
        "username": merged.get("username"),
        "auth_method": merged.get("auth_method", "private_key"),
        "has_password": bool(merged.get("password")),
        "has_private_key": bool(merged.get("private_key")),
        "remote_path": merged.get("remote_path", "/home/daydayup/backups/"),
        "os_type": merged.get("os_type", "linux"),
        "enabled": True,
        "updated_at": full.get("updated_at"),
    }


@app.post("/api/cloud/test")
def api_cloud_test(auth: dict = Depends(require_auth)) -> dict:
    return cloud_service.test(_resolve_cvm_config(auth["user_id"]))


@app.post("/api/cloud/backup", response_model=CloudBackupOut)
def api_cloud_backup(payload: CloudBackupIn, auth: dict = Depends(require_auth)) -> dict:
    user = db.get_user(auth["user_id"])
    username = user["username"]
    info = cloud_service.make_backup(_resolve_cvm_config(auth["user_id"]), username, payload.passphrase)
    db.add_cloud_backup(auth["user_id"], info)
    return info


@app.get("/api/cloud/backups")
def api_cloud_list_backups(
    prefix: str | None = Query(None),
    auth: dict = Depends(require_auth),
) -> list[dict]:
    user = db.get_user(auth["user_id"])
    return cloud_service.list_backups(_resolve_cvm_config(auth["user_id"]), user["username"], prefix)


@app.delete("/api/cloud/backups/{backup_key:path}")
def api_cloud_delete_backup(backup_key: str, auth: dict = Depends(require_auth)) -> dict:
    cloud_service.delete_backup(_resolve_cvm_config(auth["user_id"]), backup_key)
    db.delete_cloud_backup(auth["user_id"], backup_key)
    return {"status": "deleted"}


@app.post("/api/cloud/restore/prepare", response_model=CloudRestorePrepareOut)
def api_cloud_restore_prepare(payload: CloudRestoreIn, auth: dict = Depends(require_auth)) -> dict:
    info = cloud_service.restore_backup(_resolve_cvm_config(auth["user_id"]), payload.key, payload.passphrase)
    return {
        "temp_path": info["temp_path"],
        "size": info["size"],
        "target_db_path": str(db.DB_PATH),
        "needs_restart": True,
    }


@app.post("/api/cloud/restore/commit")
def api_cloud_restore_commit(payload: CloudRestoreCommitIn, auth: dict = Depends(require_auth)) -> dict:
    cloud_service.commit_restore(payload.temp_path)
    return {"status": "committed", "restart_recommended": True}


# ===================== v0.3 C 年度计划 (OKR) =====================

def _goal_to_out(goal: dict) -> dict:
    out = dict(goal)
    out["progress"] = db.compute_goal_progress(goal)
    return out


@app.get("/api/goals")
def api_list_goals(year: int | None = Query(None), auth: dict = Depends(require_auth)) -> list[dict]:
    goals = db.list_goals(auth["user_id"], year=year)
    return [_goal_to_out(g) for g in goals]


@app.post("/api/goals", status_code=201)
def api_add_goal(payload: GoalIn, auth: dict = Depends(require_auth)) -> dict:
    g = db.add_goal(
        user_id=auth["user_id"], year=payload.year, title=payload.title,
        description=payload.description, category=payload.category,
        target_date=payload.target_date,
    )
    return _goal_to_out(g)


@app.get("/api/goals/{goal_id}")
def api_get_goal(goal_id: int, auth: dict = Depends(require_auth)) -> dict:
    try:
        g = db.get_goal(auth["user_id"], goal_id)
        return _goal_to_out(g)
    except KeyError:
        raise HTTPException(status_code=404, detail="goal not found")


@app.patch("/api/goals/{goal_id}")
def api_update_goal(goal_id: int, payload: GoalUpdateIn, auth: dict = Depends(require_auth)) -> dict:
    fields = payload.model_dump(exclude_unset=True)
    try:
        g = db.update_goal(auth["user_id"], goal_id, **fields)
        return _goal_to_out(g)
    except KeyError:
        raise HTTPException(status_code=404, detail="goal not found")


@app.delete("/api/goals/{goal_id}")
def api_delete_goal(goal_id: int, auth: dict = Depends(require_auth)) -> dict[str, str]:
    try:
        db.delete_goal(auth["user_id"], goal_id)
        return {"status": "deleted"}
    except KeyError:
        raise HTTPException(status_code=404, detail="goal not found")


@app.post("/api/goals/{goal_id}/key-results", status_code=201)
def api_add_kr(goal_id: int, payload: KeyResultIn, auth: dict = Depends(require_auth)) -> dict:
    try:
        return db.add_kr(
            user_id=auth["user_id"], goal_id=goal_id, title=payload.title,
            target_value=payload.target_value, current_value=payload.current_value,
            unit=payload.unit, due_date=payload.due_date,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="goal not found")


@app.patch("/api/key-results/{kr_id}")
def api_update_kr(kr_id: int, payload: KeyResultUpdateIn, auth: dict = Depends(require_auth)) -> dict:
    fields = payload.model_dump(exclude_unset=True)
    try:
        return db.update_kr(auth["user_id"], kr_id, **fields)
    except KeyError:
        raise HTTPException(status_code=404, detail="kr not found")


@app.delete("/api/key-results/{kr_id}")
def api_delete_kr(kr_id: int, auth: dict = Depends(require_auth)) -> dict[str, str]:
    try:
        db.delete_kr(auth["user_id"], kr_id)
        return {"status": "deleted"}
    except KeyError:
        raise HTTPException(status_code=404, detail="kr not found")


# ===================== AI 荐策 (DeepSeek 代理) =====================
# 注：DeepSeek Key 由桌面端主进程从加密文件注入环境变量（DEEPSEEK_API_KEY），
#     不再提供运行时「AI 设置」写入接口，避免任何明文 key 落盘。

@app.post("/api/ai/analyze")
def api_ai_analyze(payload: dict = Body(default_factory=dict), auth: dict = Depends(require_auth)) -> dict:
    """接收前端汇总的用户上下文（目标 / 历史 / 今日排程），代理调用 DeepSeek 返回荐策。"""
    try:
        ctx = AiAnalyzeIn.model_validate(payload).context
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())
    return ai_service.analyze(ctx)


@app.post("/api/ai/plan")
def api_ai_plan(payload: dict = Body(default_factory=dict), auth: dict = Depends(require_auth)) -> dict:
    """接收用户的未来计划描述 + 上下文，代理调用 DeepSeek 将其拆解为事件安排推荐。"""
    try:
        inp = AiPlanIn.model_validate(payload)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())
    ctx = inp.context or {}
    ctx["plan_text"] = inp.plan_text
    return ai_service.plan(ctx)


@app.post("/api/ai/schedule")
def api_ai_schedule(payload: dict = Body(default_factory=dict), auth: dict = Depends(require_auth)) -> dict:
    """接收用户情况描述 + 上下文，代理调用 DeepSeek 生成今日完整作息轴。"""
    try:
        inp = AiScheduleIn.model_validate(payload)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())
    ctx = inp.context or {}
    ctx["user_input"] = inp.user_input
    return ai_service.schedule(ctx)


@app.post("/api/ai/daily_report")
def api_ai_daily_report(payload: dict = Body(default_factory=dict), auth: dict = Depends(require_auth)) -> dict:
    """代理调用 DeepSeek，基于某天的真实记录 / 任务完成 / 金币分布生成当日日报。"""
    from datetime import date as _date

    try:
        inp = AiDailyReportIn.model_validate(payload)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())
    date = inp.date
    # 服务端聚合当日数据，避免前端大包上送
    actuals = db.list_actual_records(auth["user_id"], date)
    tasks = db.list_tasks_in_range(auth["user_id"], date, date)
    agg = db.aggregate_coins(auth["user_id"], date, date)
    weekday = ""
    try:
        d = _date.fromisoformat(date)
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][d.weekday()]
    except Exception:
        pass
    ctx = {
        "date": date,
        "weekday": weekday,
        "actual_records": [
            {"start_time": r["start_time"], "end_time": r["end_time"], "text": r["text"]}
            for r in (actuals or [])
        ],
        "tasks": [
            {
                "title": t["title"],
                "anchor_time": t["anchor_time"],
                "category": t.get("category", "other"),
                "duration_min": t["duration_min"],
                "done": bool(t["done"]),
            }
            for t in (tasks or [])
        ],
        "coin_distribution": [
            {
                "category": (r["category"] or "other"),
                "count": r["count"],
                "coins": round(r["total_min"] / 60, 2),
                "done_count": r["done_count"],
            }
            for r in (agg or [])
        ],
    }
    return ai_service.daily_report(ctx)


# ===================== v0.3 B 数据管理 =====================
# 导出 / 导入 / 重置 / 概览

@app.get("/api/data/stats")
def api_data_stats(auth: dict = Depends(require_auth)) -> dict:
    """数据库概览：大小 / 各表行数 / 上次备份 / SSH 状态。"""
    import os
    size = os.path.getsize(db.DB_PATH) if db.DB_PATH.exists() else 0
    user_id = auth["user_id"]
    conn = db.get_conn()
    user = db.get_user(user_id)
    cloud = db.get_cloud_config(user_id) or {}
    last_backups = db.list_cloud_backups_local(user_id)
    tables = {}
    for t in ("today_tasks", "block_actuals", "settings", "cloud_backups", "goals", "key_results"):
        row = conn.execute(f"SELECT COUNT(*) AS c FROM {t} WHERE user_id = ?", (user_id,)).fetchone() if "user_id" in [c[1] for c in conn.execute(f"PRAGMA table_info({t})").fetchall()] else conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()
        tables[t] = row["c"]
    return {
        "db_path": str(db.DB_PATH),
        "db_size_bytes": size,
        "tables": tables,
        "user": {"id": user_id, "username": user["username"]},
        "cloud_enabled": bool(cloud.get("enabled")),
        "cloud_host": cloud.get("host"),
        "ssh_registered": bool(user.get("ssh_registered", 0)),
        "backup_count_local": len(last_backups),
        "last_backup": last_backups[0] if last_backups else None,
    }


@app.get("/api/data/export")
def api_data_export(auth: dict = Depends(require_auth)) -> FileResponse:
    """下载当前 SQLite DB 为 .db 文件（无加密；要加密请走云备份）。"""
    import shutil
    from datetime import datetime
    if not db.DB_PATH.exists():
        raise HTTPException(status_code=500, detail="db file missing")
    # 复制到临时文件（确保一致性），再发送
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    tmp = db.DB_PATH.parent / f"daydayup-export-{ts}.db"
    shutil.copy2(db.DB_PATH, tmp)
    return FileResponse(
        str(tmp),
        media_type="application/octet-stream",
        filename=f"daydayup-{ts}.db",
        background=None,
    )


@app.post("/api/data/import")
async def api_data_import(file: UploadFile = File(...), auth: dict = Depends(require_auth)) -> dict:
    """上传 .db 文件，覆盖当前 DB（需先关闭连接）。"""
    if not file.filename or not file.filename.endswith(".db"):
        raise HTTPException(status_code=400, detail="file must be .db")
    import shutil
    from pathlib import Path
    # 写到临时文件 → 验证 SQLite 合法性 → 关闭连接 → 替换
    tmp_new = db.DB_PATH.parent / "daydayup-import-tmp.db"
    with open(tmp_new, "wb") as f:
        shutil.copyfileobj(file.file, f)
    # 验证 magic
    with open(tmp_new, "rb") as f:
        magic = f.read(16)
    if not magic.startswith(b"SQLite format 3"):
        tmp_new.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="not a valid SQLite file")
    # 关闭连接，替换
    db.close()
    shutil.move(str(tmp_new), str(db.DB_PATH))
    return {"status": "imported", "restart_required": True}


class ResetIn(BaseModel):
    confirm: bool = False


@app.post("/api/data/reset")
def api_data_reset(payload: ResetIn, auth: dict = Depends(require_auth)) -> dict:
    """重置当前用户的任务 / 实际记录 / 设置 / 本地备份元数据。
    保留：用户账号 / SSH 密钥 / 作息表 / 提醒。"""
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="confirm=true required")
    user_id = auth["user_id"]
    conn = db.get_conn()
    deleted = {}
    # key_results 没有 user_id，要通过 goal_id JOIN
    cur = conn.execute(
        """DELETE FROM key_results
            WHERE goal_id IN (SELECT id FROM goals WHERE user_id = ?)""",
        (user_id,),
    )
    deleted["key_results"] = cur.rowcount
    # 其他表都有 user_id 列
    for t in ("today_tasks", "block_actuals", "settings", "cloud_backups", "goals"):
        cur = conn.execute(f"DELETE FROM {t} WHERE user_id = ?", (user_id,))
        deleted[t] = cur.rowcount
    return {"status": "reset", "deleted": deleted}


# ===================== 前端静态 =====================

if FRONTEND_DIR.exists():
    # v0.3 项目结构：CSS/JS/manifest 都在 frontend/ 根下
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR), check_dir=False), name="static")

    @app.get("/")
    def _index() -> FileResponse:
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/manifest.json")
    def _manifest() -> FileResponse:
        return FileResponse(str(FRONTEND_DIR / "manifest.json"))

    @app.get("/service-worker.js")
    def _sw() -> FileResponse:
        return FileResponse(str(FRONTEND_DIR / "service-worker.js"))

    @app.get("/static/icons/{name:path}")
    def _icon(name: str) -> FileResponse:
        return FileResponse(str(FRONTEND_DIR / "icons" / name))

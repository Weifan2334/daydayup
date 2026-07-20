"""Pydantic models."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TodayTaskIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    anchor_time: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    duration_min: int | None = Field(None, ge=1, le=24 * 60)
    category: str = Field("other", pattern=r"^(work|study|health|life|social|leisure|other)$")


class TodayTaskOut(BaseModel):
    id: int
    task_date: str
    title: str
    source: Literal["manual", "worklog", "schedule", "reminder"]
    anchor_time: str | None = None
    duration_min: int | None = None
    category: str = "other"
    done: bool


class ScheduleBlock(BaseModel):
    """Schedule time block (v4)."""
    id: int
    label: str
    anchor_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end_time: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    weekdays: str = "1,2,3,4,5,6,7"
    enabled: bool = True
    note: str | None = None
    kind: Literal["anchor", "block"] = "block"


class DailyReminder(BaseModel):
    label: str
    reminder_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    cadence: str = "daily"
    enabled: bool = True
    source: str = "manual"


class CalendarDay(BaseModel):
    date: str
    weekday: int
    total: int = 0
    done: int = 0
    has_tasks: bool = False


class CalendarView(BaseModel):
    month: str
    title: str
    first_weekday: int
    days_in_month: int
    prev_month_tail: list[CalendarDay]
    next_month_head: list[CalendarDay]
    days: list[CalendarDay]
    summary: dict[str, int]


class TodayView(BaseModel):
    """Aggregated view: client GET /api/today once is enough."""

    today_date: str
    weekday: str
    weekday_num: int
    current_time: str
    current_block: ScheduleBlock | None
    next_block: ScheduleBlock | None
    blocks: list[ScheduleBlock]
    legacy_anchors: list[ScheduleBlock] = []
    tasks: list[TodayTaskOut]
    reminders: list[DailyReminder]
    actuals: dict[str, str] = {}
    summary: dict[str, int]


class ActualIn(BaseModel):
    block_id: int
    actual_text: str = ""
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")


class ActualOut(BaseModel):
    date: str
    block_id: int
    actual_text: str
    updated_at: str


class ActualRecordIn(BaseModel):
    """自由真实记录（时间轴拖拽）。"""
    id: int | None = None
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    text: str = Field(default="", max_length=2000)


class ActualRecordOut(BaseModel):
    id: int
    start_time: str
    end_time: str
    text: str
    created_at: str
    updated_at: str


class AiScheduleIn(BaseModel):
    """DeepSeek 生成今日作息轴。"""
    user_input: str = Field(default="", max_length=4000)
    context: dict = Field(default_factory=dict)


class AiDailyReportIn(BaseModel):
    """DeepSeek 生成某日日报（真实记录 + 任务完成 + 金币分布）。"""
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    context: dict = Field(default_factory=dict)


# ---- v0.3 云备份（SFTP 到 CVM）----
class CloudConfigIn(BaseModel):
    host: str = Field(..., min_length=1)
    port: int = Field(22, ge=1, le=65535)
    username: str = Field(..., min_length=1)
    auth_method: str = Field("password", pattern=r"^(password|private_key)$")
    password: str | None = None
    private_key: str | None = None
    private_key_passphrase: str | None = None
    remote_path: str = Field("/home/fanwei/backups/", min_length=1)
    os_type: str = Field("linux", pattern=r"^(linux|windows)$")


class CloudConfigOut(BaseModel):
    host: str | None
    port: int
    username: str | None
    auth_method: str
    has_password: bool
    has_private_key: bool
    remote_path: str
    os_type: str
    enabled: bool
    updated_at: str | None = None


class CloudBackupIn(BaseModel):
    passphrase: str = Field(..., min_length=6)
    user_id: str = "default"


class CloudBackupOut(BaseModel):
    key: str
    size: int
    etag: str | None = None
    uploaded_at: str


class CloudRestoreIn(BaseModel):
    key: str
    passphrase: str = Field(..., min_length=6)


class CloudRestorePrepareOut(BaseModel):
    temp_path: str
    size: int
    target_db_path: str
    needs_restart: bool = True


class CloudRestoreCommitIn(BaseModel):
    temp_path: str
    restart_now: bool = False


# ---- v0.3 C 用户系统 ----
class RegisterIn(BaseModel):
    username: str = Field(..., min_length=2, max_length=32, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    password: str = Field(..., min_length=6, max_length=128)
    display_name: str | None = Field(None, max_length=64)


class LoginIn(BaseModel):
    username: str = Field(..., min_length=2, max_length=32)
    password: str = Field(..., min_length=1, max_length=128)


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str | None
    ssh_registered: bool
    created_at: str
    last_login_at: str | None


class AuthOut(BaseModel):
    user: UserOut
    token: str
    expires_at: str | None


class ChangePasswordIn(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=128)


# ---- v0.3 C 年度计划 (OKR) ----
class GoalIn(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=2000)
    category: str = Field("work", pattern=r"^(work|life|health|study|other)$")
    target_date: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class GoalUpdateIn(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    category: str | None = Field(None, pattern=r"^(work|life|health|study|other)$")
    status: str | None = Field(None, pattern=r"^(active|done|paused|dropped)$")
    target_date: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class KeyResultIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    target_value: float | None = None
    current_value: float | None = None
    unit: str = Field("", max_length=20)
    due_date: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class KeyResultUpdateIn(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    done: bool | None = None
    target_value: float | None = None
    current_value: float | None = None
    unit: str | None = Field(None, max_length=20)
    due_date: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")


# ---- AI 荐策 (DeepSeek 代理) ----
class AiAnalyzeIn(BaseModel):
    context: dict = Field(default_factory=dict)


class AiPlanIn(BaseModel):
    plan_text: str = Field(default="", max_length=4000)
    context: dict = Field(default_factory=dict)


# 强制重建所有模型，确保 FastAPI 构建 TypeAdapter 时无未解析 ForwardRef
for _model in (AiAnalyzeIn, AiPlanIn, AiDailyReportIn):
    _model.model_rebuild()
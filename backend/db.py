# -*- coding: utf-8 -*-
"""SQLite 封装。

v0.3 C 表设计（多用户）：
- users：用户账号（id, username, password_hash via bcrypt, ...）
- auth_tokens：登录 token
- today_tasks / block_actuals / settings / cloud_config / cloud_backups：都加 user_id
- schedule_anchors / daily_reminders：v0.3 C 暂不拆分，所有用户共享 system-wide
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

# bcrypt 兼容：直接 import 不行（5.x 改了 API）
import bcrypt as _bcrypt

_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = Path(os.environ.get("LIFEMGR_DATA_DIR", str(_ROOT / "data")))
DB_PATH = DB_DIR / "lifemgr.db"
DB_DIR.mkdir(parents=True, exist_ok=True)


def _connect() -> sqlite3.Connection:
    # 每个线程独立连接：FastAPI 在 threadpool 中并发处理请求，共享单连接会触发
    # "database is locked" / 跨线程 sqlite 错误（间歇性 500）。WAL 模式支持并发读写。
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    # 写锁等待而非立即报错，进一步吸收并发写入的短暂竞争
    conn.execute("PRAGMA busy_timeout = 5000")
    with _CONNS_LOCK:
        _CONNS.append(conn)
    return conn


_LOCAL = threading.local()
_CONNS_LOCK = threading.Lock()
_CONNS: list[sqlite3.Connection] = []


def get_conn() -> sqlite3.Connection:
    conn = getattr(_LOCAL, "conn", None)
    if conn is None:
        _LOCAL.conn = _connect()
    return _LOCAL.conn


# ===================== Schema =====================

def _init_schema() -> None:
    conn = get_conn()
    conn.executescript("""
        -- v0.3 C 迁移：非破坏式建表（保留已有用户数据，重启不再清表）
        CREATE TABLE IF NOT EXISTS schedule_anchors (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            label        TEXT    NOT NULL,
            anchor_time  TEXT    NOT NULL,
            end_time     TEXT,
            weekdays     TEXT    NOT NULL DEFAULT '1,2,3,4,5,6,7',
            enabled      INTEGER NOT NULL DEFAULT 1,
            note         TEXT,
            kind         TEXT    NOT NULL DEFAULT 'anchor'
        );

        CREATE TABLE IF NOT EXISTS daily_reminders (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            label         TEXT    NOT NULL,
            reminder_time TEXT    NOT NULL,
            cadence       TEXT    NOT NULL DEFAULT 'daily',
            enabled       INTEGER NOT NULL DEFAULT 1,
            source        TEXT    NOT NULL DEFAULT 'manual'
        );

        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            username        TEXT    NOT NULL UNIQUE COLLATE NOCASE,
            password_hash   TEXT    NOT NULL,
            display_name    TEXT,
            encrypted_private_key TEXT,
            public_key      TEXT,
            ssh_registered  INTEGER NOT NULL DEFAULT 0,
            cvm_path_prefix TEXT,
            created_at      TEXT    NOT NULL,
            last_login_at   TEXT
        );

        CREATE TABLE IF NOT EXISTS auth_tokens (
            token           TEXT    PRIMARY KEY,
            user_id         INTEGER NOT NULL,
            created_at      TEXT    NOT NULL,
            expires_at      TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS today_tasks (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            task_date     TEXT    NOT NULL,
            title         TEXT    NOT NULL,
            source        TEXT    NOT NULL DEFAULT 'manual',
            anchor_time   TEXT,
            duration_min  INTEGER,
            category      TEXT    NOT NULL DEFAULT 'other',
            done          INTEGER NOT NULL DEFAULT 0,
            created_at    TEXT    NOT NULL,
            updated_at    TEXT    NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_user_date ON today_tasks(user_id, task_date);

        CREATE TABLE IF NOT EXISTS block_actuals (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            actual_date   TEXT    NOT NULL,
            block_id      INTEGER NOT NULL,
            actual_text   TEXT    NOT NULL DEFAULT '',
            updated_at    TEXT    NOT NULL,
            UNIQUE(user_id, actual_date, block_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_actuals_user_date ON block_actuals(user_id, actual_date);

        CREATE TABLE IF NOT EXISTS settings (
            user_id       INTEGER NOT NULL,
            key           TEXT    NOT NULL,
            value         TEXT    NOT NULL,
            updated_at    TEXT    NOT NULL,
            PRIMARY KEY (user_id, key),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS cloud_config (
            id              INTEGER PRIMARY KEY,
            host            TEXT,
            port            INTEGER NOT NULL DEFAULT 22,
            username        TEXT,
            auth_method     TEXT    NOT NULL DEFAULT 'password',
            password        TEXT,
            private_key     TEXT,
            private_key_passphrase TEXT,
            remote_path     TEXT    NOT NULL DEFAULT '/home/daydayup/backups/',
            os_type         TEXT    NOT NULL DEFAULT 'linux',
            enabled         INTEGER NOT NULL DEFAULT 1,
            updated_at      TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cloud_backups (
            user_id       INTEGER NOT NULL,
            key           TEXT    NOT NULL,
            size          INTEGER NOT NULL,
            uploaded_at   TEXT    NOT NULL,
            etag          TEXT,
            PRIMARY KEY (user_id, key),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_cloud_backups_user ON cloud_backups(user_id, uploaded_at DESC);

        -- ============== v0.3 D 自由真实记录（时间轴拖拽） ==============
        CREATE TABLE IF NOT EXISTS actual_records (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            record_date   TEXT    NOT NULL,
            start_time    TEXT    NOT NULL,
            end_time      TEXT    NOT NULL,
            text          TEXT    NOT NULL DEFAULT '',
            created_at    TEXT    NOT NULL,
            updated_at    TEXT    NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_actual_records_user_date ON actual_records(user_id, record_date);

        -- ============== v0.3 C 年度计划 (OKR) ==============
        CREATE TABLE IF NOT EXISTS goals (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            year            INTEGER NOT NULL,
            title           TEXT    NOT NULL,
            description     TEXT,
            category        TEXT    DEFAULT 'work',
            status          TEXT    NOT NULL DEFAULT 'active',
            target_date     TEXT,
            created_at      TEXT    NOT NULL,
            updated_at      TEXT    NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_goals_user_year ON goals(user_id, year);

        CREATE TABLE IF NOT EXISTS key_results (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id         INTEGER NOT NULL,
            title           TEXT    NOT NULL,
            done            INTEGER NOT NULL DEFAULT 0,
            target_value    REAL,
            current_value   REAL,
            unit            TEXT,
            due_date        TEXT,
            sort_order      INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT    NOT NULL,
            updated_at      TEXT    NOT NULL,
            FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_kr_goal ON key_results(goal_id, sort_order);
    """)

    # 迁移：为已存在的 today_tasks 补 category 列（幂等；新库建表时已含该列）
    try:
        _cols = [r[1] for r in conn.execute("PRAGMA table_info(today_tasks)").fetchall()]
        if "category" not in _cols:
            conn.execute("ALTER TABLE today_tasks ADD COLUMN category TEXT NOT NULL DEFAULT 'other'")
    except Exception:
        pass


# ===================== Tasks (per-user) =====================

def add_task(
    user_id: int,
    task_date: str,
    title: str,
    source: str = "manual",
    anchor_time: str | None = None,
    duration_min: int | None = None,
    category: str = "other",
) -> dict[str, Any]:
    if not category:
        category = "other"
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO today_tasks (user_id, task_date, title, source, anchor_time, duration_min, category, done, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
        (user_id, task_date, title, source, anchor_time, duration_min, category, now, now),
    )
    return get_task(user_id, cur.lastrowid)


def list_tasks(user_id: int, task_date: str, include_done: bool = True) -> list[dict[str, Any]]:
    conn = get_conn()
    sql = "SELECT * FROM today_tasks WHERE user_id = ? AND task_date = ?"
    params: tuple[Any, ...] = (user_id, task_date)
    if not include_done:
        sql += " AND done = 0"
    sql += " ORDER BY COALESCE(anchor_time, '99:99'), id"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_task(user_id: int, task_id: int) -> dict[str, Any]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM today_tasks WHERE id = ? AND user_id = ?", (task_id, user_id)).fetchone()
    if row is None:
        raise KeyError(f"task_id={task_id} not found")
    return dict(row)


def toggle_task(user_id: int, task_id: int) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    row = conn.execute("SELECT done FROM today_tasks WHERE id = ? AND user_id = ?", (task_id, user_id)).fetchone()
    if row is None:
        raise KeyError(f"task_id={task_id} not found")
    new_done = 0 if row["done"] else 1
    conn.execute(
        "UPDATE today_tasks SET done = ?, updated_at = ? WHERE id = ?",
        (new_done, now, task_id),
    )
    return get_task(user_id, task_id)


def delete_task(user_id: int, task_id: int) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM today_tasks WHERE id = ? AND user_id = ?", (task_id, user_id))


# ===================== Anchors (shared) =====================

def upsert_anchors(rows: Iterable[dict[str, Any]]) -> None:
    conn = get_conn()
    for r in rows:
        conn.execute(
            """INSERT INTO schedule_anchors (label, anchor_time, end_time, weekdays, enabled, note, kind)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   label=excluded.label,
                   anchor_time=excluded.anchor_time,
                   end_time=excluded.end_time,
                   weekdays=excluded.weekdays,
                   enabled=excluded.enabled,
                   note=excluded.note,
                   kind=excluded.kind""",
            (
                r["label"],
                r["anchor_time"],
                r.get("end_time"),
                r.get("weekdays", "1,2,3,4,5,6,7"),
                r.get("enabled", 1),
                r.get("note"),
                r.get("kind", "anchor"),
            ),
        )


def clear_anchors() -> None:
    """v0.1 升级到 v4 时用：清空旧锚点，重新 seed。"""
    conn = get_conn()
    conn.execute("DELETE FROM schedule_anchors")
    conn.execute("DELETE FROM sqlite_sequence WHERE name='schedule_anchors'")


def clear_user_data(user_id: int) -> dict[str, int]:
    """清空某用户填的数据：today_tasks + block_actuals。保留作息表 + reminders + settings。"""
    conn = get_conn()
    cur1 = conn.execute("DELETE FROM today_tasks WHERE user_id = ?", (user_id,))
    cur2 = conn.execute("DELETE FROM block_actuals WHERE user_id = ?", (user_id,))
    return {"deleted_tasks": cur1.rowcount, "deleted_actuals": cur2.rowcount}


def list_anchors(enabled_only: bool = True, kind: str | None = None) -> list[dict[str, Any]]:
    """kind 过滤：anchor=单点锚点，block=作息时间块。不传则全部。"""
    conn = get_conn()
    sql = "SELECT * FROM schedule_anchors WHERE 1=1"
    params: tuple[Any, ...] = ()
    if enabled_only:
        sql += " AND enabled = 1"
    if kind:
        sql += " AND kind = ?"
        params = (kind,)
    sql += " ORDER BY anchor_time"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ===================== Reminders (shared) =====================

def upsert_reminders(rows: Iterable[dict[str, Any]]) -> None:
    conn = get_conn()
    for r in rows:
        conn.execute(
            """INSERT INTO daily_reminders (label, reminder_time, cadence, enabled, source)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   label=excluded.label,
                   reminder_time=excluded.reminder_time,
                   cadence=excluded.cadence,
                   enabled=excluded.enabled,
                   source=excluded.source""",
            (
                r["label"],
                r["reminder_time"],
                r.get("cadence", "daily"),
                r.get("enabled", 1),
                r.get("source", "manual"),
            ),
        )


def list_reminders(enabled_only: bool = True) -> list[dict[str, Any]]:
    conn = get_conn()
    sql = "SELECT * FROM daily_reminders"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY reminder_time"
    rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


# ===================== Block Actuals (per-user) =====================

def get_actuals_for_date(user_id: int, actual_date: str) -> dict[int, str]:
    """返 {block_id: actual_text}"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT block_id, actual_text FROM block_actuals WHERE user_id = ? AND actual_date = ?",
        (user_id, actual_date),
    ).fetchall()
    return {r["block_id"]: r["actual_text"] for r in rows}


def upsert_actual(user_id: int, actual_date: str, block_id: int, actual_text: str) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    conn.execute(
        """INSERT INTO block_actuals (user_id, actual_date, block_id, actual_text, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(user_id, actual_date, block_id) DO UPDATE SET
               actual_text=excluded.actual_text,
               updated_at=excluded.updated_at""",
        (user_id, actual_date, block_id, actual_text, now),
    )


def get_actual(user_id: int, actual_date: str, block_id: int) -> str:
    conn = get_conn()
    row = conn.execute(
        "SELECT actual_text FROM block_actuals WHERE user_id=? AND actual_date=? AND block_id=?",
        (user_id, actual_date, block_id),
    ).fetchone()
    return row["actual_text"] if row else ""


# ===================== Actual Records (free-form, per-user) =====================

def list_actual_records(user_id: int, record_date: str) -> list[dict[str, Any]]:
    """返回某天用户的自由真实记录列表，按开始时间排序。"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, start_time, end_time, text, created_at, updated_at
             FROM actual_records
            WHERE user_id = ? AND record_date = ?
            ORDER BY start_time""",
        (user_id, record_date),
    ).fetchall()
    return [dict(r) for r in rows]


def upsert_actual_record(
    user_id: int, record_date: str, start_time: str, end_time: str, text: str, record_id: int | None = None
) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    if record_id:
        conn.execute(
            """UPDATE actual_records
                  SET start_time = ?, end_time = ?, text = ?, updated_at = ?
                WHERE id = ? AND user_id = ? AND record_date = ?""",
            (start_time, end_time, text, now, record_id, user_id, record_date),
        )
        cur = conn.execute(
            "SELECT id, start_time, end_time, text, created_at, updated_at FROM actual_records WHERE id = ?",
            (record_id,),
        )
    else:
        cur = conn.execute(
            """INSERT INTO actual_records (user_id, record_date, start_time, end_time, text, created_at, updated_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, record_date, start_time, end_time, text, now, now),
        )
        cur = conn.execute(
            "SELECT id, start_time, end_time, text, created_at, updated_at FROM actual_records WHERE id = ?",
            (cur.lastrowid,),
        )
    return dict(cur.fetchone())


def delete_actual_record(user_id: int, record_id: int) -> bool:
    conn = get_conn()
    cur = conn.execute(
        "DELETE FROM actual_records WHERE id = ? AND user_id = ?",
        (record_id, user_id),
    )
    return cur.rowcount > 0


def count_tasks_by_month(user_id: int, month_str: str) -> dict[str, dict[str, int]]:
    """YYYY-MM → {date: {total, done}}"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT task_date,
                  COUNT(*) AS total,
                  SUM(done) AS done
             FROM today_tasks
            WHERE user_id = ? AND task_date LIKE ?
            GROUP BY task_date""",
        (user_id, month_str + "%"),
    ).fetchall()
    return {r["task_date"]: {"total": r["total"], "done": int(r["done"] or 0)} for r in rows}


def list_tasks_in_range(user_id: int, start_date: str, end_date: str) -> list[dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT * FROM today_tasks
            WHERE user_id = ? AND task_date BETWEEN ? AND ?
            ORDER BY task_date, COALESCE(anchor_time, '99:99'), id""",
        (user_id, start_date, end_date),
    ).fetchall()
    return [dict(r) for r in rows]


def aggregate_coins(user_id: int, start_date: str, end_date: str) -> list[dict[str, Any]]:
    """按类目聚合某日期范围内的金币消耗（1 金币 = 60 分钟）。"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT category,
                  COUNT(*)                           AS count,
                  COALESCE(SUM(duration_min), 0)     AS total_min,
                  SUM(CASE WHEN done = 1 THEN 1 ELSE 0 END) AS done_count
             FROM today_tasks
            WHERE user_id = ? AND task_date BETWEEN ? AND ?
            GROUP BY category
            ORDER BY total_min DESC""",
        (user_id, start_date, end_date),
    ).fetchall()
    return [dict(r) for r in rows]


# ===================== Settings (per-user) =====================

def set_setting(user_id: int, key: str, value: Any) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    payload = json.dumps(value, ensure_ascii=False)
    conn.execute(
        """INSERT INTO settings (user_id, key, value, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
        (user_id, key, payload, now),
    )


def get_setting(user_id: int, key: str, default: Any = None) -> Any:
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE user_id = ? AND key = ?", (user_id, key)).fetchone()
    if row is None:
        return default
    return json.loads(row["value"])


# ===================== Cloud config / backups (per-user) =====================

def get_cloud_config(user_id: int) -> dict[str, Any] | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM cloud_config WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    cfg = dict(row)
    cfg["enabled"] = bool(cfg.get("enabled", 0))
    return cfg


def upsert_cloud_config(user_id: int, cfg: dict[str, Any]) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    conn.execute(
        """INSERT INTO cloud_config
            (id, host, port, username, auth_method, password, private_key, private_key_passphrase,
             remote_path, os_type, enabled, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
               host=excluded.host,
               port=excluded.port,
               username=excluded.username,
               auth_method=excluded.auth_method,
               password=excluded.password,
               private_key=excluded.private_key,
               private_key_passphrase=excluded.private_key_passphrase,
               remote_path=excluded.remote_path,
               os_type=excluded.os_type,
               enabled=excluded.enabled,
               updated_at=excluded.updated_at""",
        (
            user_id,
            cfg.get("host"),
            int(cfg.get("port") or 22),
            cfg.get("username"),
            cfg.get("auth_method", "password"),
            cfg.get("password"),
            cfg.get("private_key"),
            cfg.get("private_key_passphrase"),
            cfg.get("remote_path", "/home/daydayup/backups/"),
            cfg.get("os_type", "linux"),
            1 if cfg.get("enabled", True) else 0,
            now,
        ),
    )


def add_cloud_backup(user_id: int, item: dict[str, Any]) -> None:
    conn = get_conn()
    conn.execute(
        """INSERT INTO cloud_backups (user_id, key, size, uploaded_at, etag)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(user_id, key) DO UPDATE SET
               size=excluded.size,
               uploaded_at=excluded.uploaded_at,
               etag=excluded.etag""",
        (user_id, item["key"], item["size"], item["uploaded_at"], item.get("etag")),
    )


def list_cloud_backups_local(user_id: int) -> list[dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT key, size, uploaded_at, etag FROM cloud_backups WHERE user_id = ? ORDER BY uploaded_at DESC",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_cloud_backup(user_id: int, backup_key: str) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM cloud_backups WHERE user_id = ? AND key = ?", (user_id, backup_key))


def close() -> None:
    """v0.3 云备份：恢复 DB 前必须先关连接。关闭所有线程连接。"""
    with _CONNS_LOCK:
        conns = list(_CONNS)
        _CONNS.clear()
    for conn in conns:
        try:
            conn.close()
        except Exception:
            pass
    _LOCAL.conn = None


# ===================== v0.3 C 用户系统 =====================

def hash_password(password: str) -> str:
    salt = _bcrypt.gensalt(rounds=12)
    return _bcrypt.hashpw(password.encode("utf-8"), salt).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except Exception:
        return False


def get_or_create_default_user() -> int:
    """首次启动时建一个 default 用户用于迁移 + 后备。"""
    conn = get_conn()
    row = conn.execute("SELECT id FROM users WHERE username='default'").fetchone()
    if row:
        return row["id"]
    now = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, display_name, created_at) VALUES (?, ?, ?, ?)",
        ("default", "!locked!", "Default (system)", now),
    )
    return cur.lastrowid


def create_user(username: str, password: str, display_name: str | None = None) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    pw_hash = hash_password(password)
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO users (username, password_hash, display_name, created_at)
           VALUES (?, ?, ?, ?)""",
        (username, pw_hash, display_name or username, now),
    )
    return get_user(cur.lastrowid)


def get_user(user_id: int) -> dict[str, Any]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise KeyError(f"user_id={user_id} not found")
    return dict(row)


def get_user_by_name(username: str) -> dict[str, Any] | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute("SELECT id, username, display_name, ssh_registered, created_at, last_login_at FROM users ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def update_user(user_id: int, **fields: Any) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    conn = get_conn()
    conn.execute(f"UPDATE users SET {cols} WHERE id = ?", (*fields.values(), user_id))


def touch_last_login(user_id: int) -> None:
    update_user(user_id, last_login_at=datetime.now().isoformat(timespec="seconds"))


def create_token(user_id: int, ttl_days: int = 30) -> str:
    import secrets
    token = secrets.token_hex(32)
    now = datetime.now()
    expires = (now + timedelta(days=ttl_days)).isoformat() if ttl_days else None
    conn = get_conn()
    conn.execute(
        "INSERT INTO auth_tokens (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, now.isoformat(timespec="seconds"), expires),
    )
    return token


def lookup_token(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    conn = get_conn()
    row = conn.execute(
        """SELECT t.token, t.user_id, t.expires_at, u.username, u.display_name, u.ssh_registered
             FROM auth_tokens t JOIN users u ON u.id = t.user_id
            WHERE t.token = ?""",
        (token,),
    ).fetchone()
    if row is None:
        return None
    expires = row["expires_at"]
    if expires:
        try:
            if datetime.fromisoformat(expires) < datetime.now():
                return None
        except Exception:
            pass
    return dict(row)


def delete_token(token: str) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))


def current_user_id_or_default() -> int:
    """向后兼容：API 没传 user 时用 default user。"""
    row = get_conn().execute("SELECT id FROM users WHERE username='default'").fetchone()
    if row:
        return row["id"]
    return get_or_create_default_user()


# ===================== Init =====================


# ===================== 年度计划 (OKR) =====================

def list_goals(user_id, year=None):
    conn = get_conn()
    if year is None:
        rows = conn.execute(
            """SELECT g.*,
                      COUNT(k.id) AS kr_total,
                      SUM(CASE WHEN k.done = 1 THEN 1 ELSE 0 END) AS kr_done
                 FROM goals g
            LEFT JOIN key_results k ON k.goal_id = g.id
                WHERE g.user_id = ?
             GROUP BY g.id
             ORDER BY g.status = 'done', g.created_at DESC""",
            (user_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT g.*,
                      COUNT(k.id) AS kr_total,
                      SUM(CASE WHEN k.done = 1 THEN 1 ELSE 0 END) AS kr_done
                 FROM goals g
            LEFT JOIN key_results k ON k.goal_id = g.id
                WHERE g.user_id = ? AND g.year = ?
             GROUP BY g.id
             ORDER BY g.status = 'done', g.created_at DESC""",
            (user_id, year),
        ).fetchall()
    return [dict(r) for r in rows]


def get_goal(user_id, goal_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM goals WHERE id = ? AND user_id = ?", (goal_id, user_id)).fetchone()
    if row is None:
        raise KeyError(f"goal_id={goal_id} not found")
    goal = dict(row)
    krs = conn.execute(
        "SELECT * FROM key_results WHERE goal_id = ? ORDER BY sort_order, id",
        (goal_id,),
    ).fetchall()
    goal['key_results'] = [dict(k) for k in krs]
    return goal


def add_goal(user_id, year, title, description='', category='work', target_date=None):
    now = datetime.now().isoformat(timespec='seconds')
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO goals (user_id, year, title, description, category, target_date, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, year, title, description or None, category, target_date, now, now),
    )
    return get_goal(user_id, cur.lastrowid)


def update_goal(user_id, goal_id, **fields):
    if not fields:
        return get_goal(user_id, goal_id)
    fields['updated_at'] = datetime.now().isoformat(timespec='seconds')
    cols = ', '.join(f'{k}=?' for k in fields)
    conn = get_conn()
    cur = conn.execute(f"UPDATE goals SET {cols} WHERE id = ? AND user_id = ?", (*fields.values(), goal_id, user_id))
    if cur.rowcount == 0:
        raise KeyError(f"goal_id={goal_id} not found")
    return get_goal(user_id, goal_id)


def delete_goal(user_id, goal_id):
    conn = get_conn()
    cur = conn.execute("DELETE FROM goals WHERE id = ? AND user_id = ?", (goal_id, user_id))
    if cur.rowcount == 0:
        raise KeyError(f"goal_id={goal_id} not found")


def add_kr(user_id, goal_id, title, target_value=None, current_value=0, unit='', due_date=None):
    get_goal(user_id, goal_id)
    now = datetime.now().isoformat(timespec='seconds')
    conn = get_conn()
    row = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM key_results WHERE goal_id = ?", (goal_id,)).fetchone()
    cur = conn.execute(
        """INSERT INTO key_results (goal_id, title, target_value, current_value, unit, due_date, sort_order, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (goal_id, title, target_value, current_value or 0, unit or None, due_date, row['n'], now, now),
    )
    conn.execute("UPDATE goals SET updated_at = ? WHERE id = ?", (now, goal_id))
    return dict(conn.execute("SELECT * FROM key_results WHERE id = ?", (cur.lastrowid,)).fetchone())


def update_kr(user_id, kr_id, **fields):
    conn = get_conn()
    row = conn.execute(
        """SELECT g.user_id FROM key_results k JOIN goals g ON g.id = k.goal_id WHERE k.id = ?""",
        (kr_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"kr_id={kr_id} not found")
    if row['user_id'] != user_id:
        raise KeyError(f"kr_id={kr_id} not owned")
    fields['updated_at'] = datetime.now().isoformat(timespec='seconds')
    cols = ', '.join(f'{k}=?' for k in fields)
    conn.execute(f"UPDATE key_results SET {cols} WHERE id = ?", (*fields.values(), kr_id))
    now = datetime.now().isoformat(timespec='seconds')
    conn.execute("UPDATE goals SET updated_at = ? WHERE id = (SELECT goal_id FROM key_results WHERE id = ?)", (now, kr_id))
    return dict(conn.execute("SELECT * FROM key_results WHERE id = ?", (kr_id,)).fetchone())


def delete_kr(user_id, kr_id):
    conn = get_conn()
    row = conn.execute(
        """SELECT g.user_id, k.goal_id FROM key_results k JOIN goals g ON g.id = k.goal_id WHERE k.id = ?""",
        (kr_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"kr_id={kr_id} not found")
    if row['user_id'] != user_id:
        raise KeyError(f"kr_id={kr_id} not owned")
    conn.execute("DELETE FROM key_results WHERE id = ?", (kr_id,))
    now = datetime.now().isoformat(timespec='seconds')
    conn.execute("UPDATE goals SET updated_at = ? WHERE id = ?", (now, row['goal_id']))


def compute_goal_progress(goal):
    # 两种调用：list_goals 返回的 {kr_total, kr_done} 聚合，get_goal 返回的 {key_results: [...]}
    if 'kr_total' in goal:
        total = goal.get('kr_total') or 0
        done = goal.get('kr_done') or 0
    else:
        krs = goal.get('key_results') or []
        total = len(krs)
        done = sum(1 for k in krs if k.get('done'))
    if total == 0:
        return 0
    return int(round(done * 100 / total))

_init_schema()

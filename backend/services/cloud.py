"""云备份业务逻辑（v0.3 阶段 A · SFTP 改造版）。

调用链：
  api -> cloud.{save_config, test, make_backup, list, restore, commit_restore, delete}
       -> sftp_client.*（实际 SSH/SFTP 交互）
       -> crypto.*（加密 / 解密）
       -> db.*（本地元数据 + 状态）
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from typing import Any

from .. import db
from . import sftp_client as remote
from .crypto import encrypt, decrypt


# ---- 配置 ----
def get_config() -> dict[str, Any] | None:
    cfg = db.get_cloud_config()
    return cfg


def save_config(cfg: dict[str, Any]) -> dict[str, Any]:
    required = ("host", "username", "remote_path")
    for k in required:
        if not cfg.get(k):
            raise ValueError(f"missing required field: {k}")
    cfg = dict(cfg)
    cfg.setdefault("port", 22)
    cfg.setdefault("auth_method", "password")
    if not cfg["remote_path"].startswith("/") and not cfg["remote_path"][1:2] == ":":
        # Windows path like C:\ 也允许；其它相对路径补成 /home/...
        cfg["remote_path"] = "/" + cfg["remote_path"]
    if not cfg["remote_path"].endswith("/"):
        cfg["remote_path"] += "/"
    db.upsert_cloud_config(cfg)
    return _mask(cfg)


def _mask(cfg: dict[str, Any]) -> dict[str, Any]:
    out = dict(cfg)
    if out.get("password"):
        out["has_password"] = True
    else:
        out["has_password"] = False
    if out.get("private_key"):
        out["has_private_key"] = True
    else:
        out["has_private_key"] = False
    # 不返回明文
    out.pop("password", None)
    out.pop("private_key", None)
    out.pop("private_key_passphrase", None)
    return out


def _conn_args(cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "host": cfg["host"],
        "port": int(cfg.get("port") or 22),
        "username": cfg["username"],
        "auth_method": cfg.get("auth_method", "password"),
        "password": cfg.get("password") or None,
        "private_key": cfg.get("private_key") or None,
        "private_key_passphrase": cfg.get("private_key_passphrase") or None,
    }


def test() -> dict[str, Any]:
    cfg = get_config()
    if not cfg:
        return {"ok": False, "message": "cloud not configured"}
    try:
        ok, msg = remote.test_connection(
            **_conn_args(cfg),
            remote_path=cfg.get("remote_path", "/home/fanwei/backups/"),
        )
        return {"ok": ok, "message": msg}
    except Exception as e:
        return {"ok": False, "message": f"test failed: {e}"}


# ---- 备份 ----
def make_backup(cfg: dict[str, Any], user_id: str, passphrase: str) -> dict[str, Any]:
    if not user_id or not user_id.strip():
        user_id = user_id or "default"
    cfg_local = cfg
    if not cfg_local:
        raise ValueError("cloud not configured")
    if not passphrase or len(passphrase) < 6:
        raise ValueError("passphrase too short (min 6 chars)")

    # 1. 读 DB
    with open(db.DB_PATH, "rb") as f:
        plain = f.read()
    # 2. 加密
    enc = encrypt(plain, passphrase)
    # 3. 拼远端文件名
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    remote_dir = cfg.get("remote_path", "/home/fanwei/backups/").rstrip("/")
    filename = f"{user_id}_{ts}.db.enc"
    key = f"{remote_dir}/{filename}"
    # 4. 上传
    try:
        info = remote.put_object(**_conn_args(cfg), remote_path=remote_dir, key=key, body=enc)
    except remote.SftpError as e:
        raise RuntimeError(f"sftp upload failed: {e}") from e
    except Exception as e:
        raise RuntimeError(f"upload failed: {e}") from e
    # 不在这里写 DB（v0.3 C：由 main.py 路由层写入 user_id 隔离的元数据）
    return {"key": key, "size": len(enc), "etag": info.get("etag", ""), "uploaded_at": datetime.now(timezone.utc).isoformat()}


# ---- 列表 / 恢复 / 删除 ----
def list_backups(cfg: dict[str, Any], user_id: str = "", prefix_filter: str | None = None) -> list[dict[str, Any]]:
    if not cfg:
        return []
    try:
        items = remote.list_objects(
            **_conn_args(cfg),
            remote_path=cfg.get("remote_path", "/home/fanwei/backups/"),
            prefix=prefix_filter,
        )
    except remote.SftpError as e:
        raise RuntimeError(f"sftp list failed: {e}") from e
    except Exception as e:
        raise RuntimeError(f"list failed: {e}") from e
    return items


def restore_backup(cfg: dict[str, Any], backup_key: str, passphrase: str) -> dict[str, Any]:
    if not cfg:
        raise ValueError("cloud not configured")
    if not passphrase or len(passphrase) < 6:
        raise ValueError("passphrase too short (min 6 chars)")

    try:
        enc = remote.get_object(**_conn_args(cfg), key=backup_key)
    except remote.SftpError as e:
        raise RuntimeError(f"sftp download failed: {e}") from e
    except Exception as e:
        raise RuntimeError(f"download failed: {e}") from e

    try:
        plain = decrypt(enc, passphrase)
    except Exception:
        raise ValueError("decrypt failed (wrong passphrase or corrupted backup)")

    if not plain.startswith(b"SQLite format 3\x00"):
        raise ValueError("decrypted payload is not a SQLite database")

    tmp_path = str(db.DB_PATH) + ".restore.tmp"
    with open(tmp_path, "wb") as f:
        f.write(plain)
    return {"temp_path": tmp_path, "size": len(plain)}


def commit_restore(temp_path: str) -> None:
    if not temp_path or not os.path.exists(temp_path):
        raise FileNotFoundError(temp_path)
    if not temp_path.endswith(".restore.tmp"):
        raise ValueError("refusing to commit non-temp path")
    db.close()
    shutil.move(temp_path, str(db.DB_PATH))


def delete_backup(cfg: dict[str, Any], backup_key: str) -> None:
    if not cfg:
        raise ValueError("cloud not configured")
    if not cfg:
        raise ValueError("cloud not configured")
    try:
        remote.delete_object(**_conn_args(cfg), key=backup_key)
    except remote.SftpError as e:
        raise RuntimeError(f"sftp delete failed: {e}") from e
    except Exception as e:
        raise RuntimeError(f"delete failed: {e}") from e
    db.delete_cloud_backup(backup_key)

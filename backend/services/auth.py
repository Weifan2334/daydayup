"""Auth service (v0.3 C)."""
from __future__ import annotations

import logging
from typing import Any

from .. import db
from ..models import RegisterIn, LoginIn, ChangePasswordIn
from . import keygen

log = logging.getLogger("daydayup.auth")


class AuthError(Exception):
    def __init__(self, message: str, code: int = 400):
        super().__init__(message)
        self.code = code


def register(payload: RegisterIn) -> dict[str, Any]:
    existing = db.get_user_by_name(payload.username)
    if existing is not None:
        raise AuthError("username already exists", code=409)
    user = db.create_user(payload.username, payload.password, payload.display_name)
    # 自动生成 SSH 密钥对（同步、毫秒级） + 后台异步注册到 CVM（≤90s，不阻塞响应）
    try:
        keygen.generate_keypair(user["id"], payload.password)
        keygen.schedule_register_to_cvm(user["id"])
    except Exception as e:
        log.warning("auto keygen failed for new user=%s: %s", user["username"], e)
    return user


def login(payload: LoginIn) -> dict[str, Any]:
    user = db.get_user_by_name(payload.username)
    if user is None:
        raise AuthError("invalid username or password", code=401)
    if user["password_hash"] == "!locked!":
        raise AuthError("account is locked", code=403)
    if not db.verify_password(payload.password, user["password_hash"]):
        raise AuthError("invalid username or password", code=401)
    db.touch_last_login(user["id"])
    token = db.create_token(user["id"])
    expires_row = db.get_conn().execute(
        "SELECT expires_at FROM auth_tokens WHERE token = ?", (token,)
    ).fetchone()
    # 如果登录时发现 ssh_registered=0 但已有密钥对（中途进程被杀、网络抖动等）→ 重启后台注册
    if not user.get("ssh_registered") and user.get("public_key") and user.get("encrypted_private_key"):
        log.info("login resume: re-scheduling CVM register for user=%s", user["username"])
        keygen.schedule_register_to_cvm(user["id"])
    return {
        "user": _to_user_out(user),
        "token": token,
        "expires_at": expires_row["expires_at"] if expires_row else None,
    }


def logout(token: str) -> None:
    if token:
        db.delete_token(token)


def me(token: str) -> dict[str, Any] | None:
    info = db.lookup_token(token)
    if not info:
        return None
    user = db.get_user(info["user_id"])
    return _to_user_out(user)


def change_password(token: str, payload: ChangePasswordIn) -> None:
    info = db.lookup_token(token)
    if not info:
        raise AuthError("not authenticated", code=401)
    user = db.get_user(info["user_id"])
    if not db.verify_password(payload.old_password, user["password_hash"]):
        raise AuthError("old password incorrect", code=400)
    new_hash = db.hash_password(payload.new_password)
    db.update_user(user["id"], password_hash=new_hash)
    # 改密后重新生成密钥对（新密码派生新 AES key 加密新私钥） + 后台异步重新注册到 CVM
    try:
        keygen.generate_keypair(user["id"], payload.new_password)
        keygen.schedule_register_to_cvm(user["id"])
    except Exception as e:
        log.warning("re-keygen on change-password failed for user=%s: %s", user["username"], e)


def _to_user_out(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user.get("display_name"),
        "ssh_registered": bool(user.get("ssh_registered", 0)),
        "created_at": user.get("created_at", ""),
        "last_login_at": user.get("last_login_at"),
    }

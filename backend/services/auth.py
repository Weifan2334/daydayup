"""Auth service (v0.3 C)."""
from __future__ import annotations

from typing import Any

from .. import db
from ..models import RegisterIn, LoginIn, ChangePasswordIn


class AuthError(Exception):
    def __init__(self, message: str, code: int = 400):
        super().__init__(message)
        self.code = code


def register(payload: RegisterIn) -> dict[str, Any]:
    existing = db.get_user_by_name(payload.username)
    if existing is not None:
        raise AuthError("username already exists", code=409)
    user = db.create_user(payload.username, payload.password, payload.display_name)
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


def _to_user_out(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user.get("display_name"),
        "ssh_registered": bool(user.get("ssh_registered", 0)),
        "created_at": user.get("created_at", ""),
        "last_login_at": user.get("last_login_at"),
    }

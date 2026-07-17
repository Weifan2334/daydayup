"""v0.3 C 用户 SSH 密钥对生成 + 自动注册到 CVM。

API 拆分（v0.4 起）：
- generate_keypair(user_id, password) — 同步、毫秒级，只做生成 + 加密 + 存库
- register_to_cvm(user_id, poll_timeout) — 上传公钥 + 轮询注册（慢速、可火忘记）
- schedule_register_to_cvm(user_id) — 后台 daemon thread 调 register_to_cvm
- setup_ssh(user_id, password, poll_timeout) — backward compat / 手动重生成场景
"""
from __future__ import annotations

import io
import logging
import threading
import time
from datetime import datetime
from typing import Any

import paramiko

from .. import db
from .crypto import encrypt, decrypt
from . import sftp_client as remote

log = logging.getLogger("daydayup.keygen")


# CVM 共享配置（和 main.py 的 DEFAULT_CVM 同步）
DEFAULT_CVM = {
    "host": "43.136.130.11",
    "port": 22,
    "username": "daydayup",
    "auth_method": "private_key",
    "remote_path": "/home/daydayup/backups/",
    "os_type": "linux",
}


def _resolve_cvm_config(user_id: int) -> dict[str, Any]:
    cfg = db.get_cloud_config(user_id) or {}
    merged = dict(DEFAULT_CVM)
    merged.update({k: v for k, v in cfg.items() if v is not None})
    return merged


def _encrypt_private_key(pem_str: str, password: str) -> str:
    """用用户密码派生 AES-256-GCM 加密私钥 PEM（hex 输出）。"""
    return encrypt(pem_str.encode("utf-8"), password).hex()


def _decrypt_private_key(hex_blob: str, password: str) -> str:
    return decrypt(bytes.fromhex(hex_blob), password).decode("utf-8")


def _generate_rsa_keypair(bits: int = 2048) -> tuple[str, str]:
    """生成 RSA 密钥对，返回 (private_pem, public_openssh)"""
    key = paramiko.RSAKey.generate(bits)
    priv_buf = io.StringIO()
    key.write_private_key(priv_buf)
    priv_pem = priv_buf.getvalue()
    pub_openssh = f"ssh-rsa {key.get_base64()}"
    return priv_pem, pub_openssh


def generate_keypair(user_id: int, password: str) -> dict[str, Any]:
    """生成 RSA 密钥对 + 用用户密码加密私钥 + 存到 users 表。

    同步、毫秒级，不涉及网络。供 register / change_password 后台调用。
    Returns:
        { status, public_key_fingerprint }
    Raises:
        ValueError: default user 不允许生成密钥
    """
    user = db.get_user(user_id)
    if user["password_hash"] == "!locked!":
        raise ValueError("default user cannot generate keypair")

    priv_pem, pub_openssh = _generate_rsa_keypair(2048)
    encrypted_hex = _encrypt_private_key(priv_pem, password)
    pub_fingerprint = _fingerprint(pub_openssh)

    db.update_user(
        user_id,
        public_key=pub_openssh,
        encrypted_private_key=encrypted_hex,
        cvm_path_prefix=f"/home/daydayup/backups/{user['username']}/",
        ssh_registered=0,  # 重置状态，等待 register_to_cvm 重新注册
    )
    return {"status": "ok", "public_key_fingerprint": pub_fingerprint}


def register_to_cvm(user_id: int, poll_timeout: int = 90, retry_forever: bool = True) -> dict[str, Any]:
    """上传公钥到 CVM inbox/ + 轮询 .ok 注册。慢速（最多 poll_timeout 秒）。

    retry_forever=True：超时后按退避策略无限重试（适合后台 daemon 任务）。
    retry_forever=False：超时返回 pending。

    Returns:
        { status: ok/pending/error, ssh_registered, public_key_fingerprint, message }
    """
    user = db.get_user(user_id)
    cfg = _resolve_cvm_config(user_id)
    inbox_path = "/home/daydayup/inbox"
    pub_filename = f"{user['username']}.pub"
    ok_path = f"{inbox_path}/{user['username']}.ok"
    pub_with_comment = f"{user['public_key']} daydayup-user:{user['username']}\n"
    pub_fingerprint = _fingerprint(user["public_key"])

    backoff = 3
    max_backoff = 30
    elapsed = 0

    while True:
        try:
            # 先检查 .ok 是否已存在
            try:
                _ = remote.get_object(**_cvm_args(cfg), key=ok_path)
                db.update_user(user_id, ssh_registered=1)
                return {
                    "status": "ok",
                    "ssh_registered": True,
                    "public_key_fingerprint": pub_fingerprint,
                    "message": "registered (found .ok)",
                }
            except Exception:
                pass  # .ok not found yet

            # 上传 .pub
            try:
                remote.put_object(
                    **_cvm_args(cfg),
                    remote_path=inbox_path,
                    key=f"{inbox_path}/{pub_filename}",
                    body=pub_with_comment.encode("utf-8"),
                )
                # 上传成功 → 等轮询
                log.info("user=%s pub uploaded, polling for .ok", user["username"])
            except (remote.SftpError, Exception) as e:
                log.warning("user=%s upload failed: %s", user["username"], e)
                if not retry_forever:
                    return {
                        "status": "error",
                        "ssh_registered": False,
                        "public_key_fingerprint": pub_fingerprint,
                        "message": f"upload failed: {e}",
                    }
                time.sleep(backoff)
                elapsed += backoff
                backoff = min(backoff * 2, max_backoff)
                continue

            # 轮询 .ok
            poll_deadline = time.time() + (poll_timeout if elapsed == 0 else min(poll_timeout, max_backoff))
            while time.time() < poll_deadline:
                time.sleep(3)
                try:
                    _ = remote.get_object(**_cvm_args(cfg), key=ok_path)
                    db.update_user(user_id, ssh_registered=1)
                    return {
                        "status": "ok",
                        "ssh_registered": True,
                        "public_key_fingerprint": pub_fingerprint,
                        "message": f"registered after ~{int(time.time() - (poll_deadline - poll_timeout))}s",
                    }
                except Exception:
                    continue

            # 单轮超时
            elapsed += poll_timeout
            if not retry_forever:
                return {
                    "status": "pending",
                    "ssh_registered": False,
                    "public_key_fingerprint": pub_fingerprint,
                    "message": "等待 cron 注册超时",
                }
            log.info("user=%s poll timeout, will retry after %ss", user["username"], backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)

        except Exception as e:
            log.exception("user=%s unexpected error in register loop", user["username"])
            if not retry_forever:
                return {"status": "error", "ssh_registered": False, "message": str(e)}
            time.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)


def schedule_register_to_cvm(user_id: int) -> threading.Thread:
    """后台异步调 register_to_cvm（fire-and-forget）。返回 Thread 对象供调用方选择 join。

    重复调用是幂等的：同一个 user_id 已有线程在跑时直接返回已有 Thread。
    """
    state_key = f"_keygen_register_thread_{user_id}"
    existing = getattr(register_to_cvm, state_key, None)
    if existing is not None and existing.is_alive():
        return existing

    def _runner():
        try:
            log.info("background register started user_id=%s", user_id)
            result = register_to_cvm(user_id, poll_timeout=90, retry_forever=True)
            log.info("background register done user_id=%s result=%s", user_id, result.get("status"))
        except Exception as e:
            log.exception("background register crashed user_id=%s", user_id)
        finally:
            setattr(register_to_cvm, state_key, None)

    t = threading.Thread(target=_runner, name=f"keygen-register-{user_id}", daemon=True)
    setattr(register_to_cvm, state_key, t)
    t.start()
    return t


def setup_ssh(user_id: int, password: str, poll_timeout: int = 90) -> dict[str, Any]:
    """Backward compat / 手动重生成场景。

    等价于 generate_keypair + register_to_cvm(retry_forever=False)。
    """
    user = db.get_user(user_id)
    if user["password_hash"] == "!locked!":
        return {"status": "error", "message": "default user cannot setup ssh"}

    gen = generate_keypair(user_id, password)
    if gen["status"] != "ok":
        return {**gen, "ssh_registered": False}
    return register_to_cvm(user_id, poll_timeout=poll_timeout, retry_forever=False)


def _cvm_args(cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "host": cfg["host"],
        "port": int(cfg.get("port") or 22),
        "username": cfg["username"],
        "auth_method": cfg.get("auth_method", "private_key"),
        "password": cfg.get("password") or None,
        "private_key": cfg.get("private_key") or None,
        "private_key_passphrase": cfg.get("private_key_passphrase") or None,
    }


def _fingerprint(pub_openssh: str) -> str:
    """简单的指纹：SHA256(base64) 前 16 字符。"""
    import hashlib
    parts = pub_openssh.strip().split()
    if len(parts) >= 2:
        b = parts[1].encode("ascii")
    else:
        b = pub_openssh.encode("utf-8")
    return "SHA256:" + hashlib.sha256(b).hexdigest()[:16]

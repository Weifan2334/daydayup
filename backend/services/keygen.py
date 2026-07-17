"""v0.3 C 用户 SSH 密钥对生成 + 自动注册到 CVM。

流程（setup_ssh 是单一端点，blocking 至最多 90s）：
1. 用用户密码派生 AES 密钥
2. paramiko 生成 RSA 2048 密钥对
3. 私钥 PEM 用 AES-256-GCM 加密后存 users.encrypted_private_key
4. 公钥 PEM 存 users.public_key
5. SFTP 上传 {username}.pub 到 CVM /home/daydayup/inbox/
6. 轮询 {username}.ok 出现 → ssh_registered=1，返回成功
7. 失败超时 → 返回错误
"""
from __future__ import annotations

import io
import time
from datetime import datetime
from typing import Any

import paramiko

from .. import db
from .crypto import encrypt, decrypt
from . import sftp_client as remote


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
    """用用户密码派生 AES-256-GCM 加密私钥 PEM（base64 输出）。"""
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


def setup_ssh(user_id: int, password: str, poll_timeout: int = 90) -> dict[str, Any]:
    """一次性完成：生成密钥对 + 加密私钥 + 上传公钥 + 轮询注册。

    Returns:
        { status, ssh_registered, public_key_fingerprint, message }
    """
    user = db.get_user(user_id)
    if user["password_hash"] == "!locked!":
        return {"status": "error", "message": "default user cannot setup ssh"}

    # 1. 生成 RSA 2048 密钥对
    priv_pem, pub_openssh = _generate_rsa_keypair(2048)

    # 2. 私钥用用户密码派生密钥加密
    encrypted_hex = _encrypt_private_key(priv_pem, password)
    pub_fingerprint = _fingerprint(pub_openssh)

    # 3. 存到用户记录（先存，未注册也存了 — 用户重试不丢）
    db.update_user(user_id, public_key=pub_openssh, encrypted_private_key=encrypted_hex,
                   cvm_path_prefix=f"/home/daydayup/backups/{user['username']}/")

    # 4. 上传公钥到 CVM
    cfg = _resolve_cvm_config(user_id)
    inbox_path = f"/home/daydayup/inbox"
    pub_filename = f"{user['username']}.pub"
    ok_path = f"/home/daydayup/inbox/{user['username']}.ok"

    # 重新格式化为 authorized_keys 风格（含 comment）
    pub_with_comment = f"{pub_openssh} daydayup-user:{user['username']}\n"

    try:
        # 先检查 .ok 是否已存在（之前已注册过）
        try:
            _ = remote.get_object(**_cvm_args(cfg), key=ok_path)
            # .ok 已存在 → 视为已注册
            db.update_user(user_id, ssh_registered=1)
            return {
                "status": "ok",
                "ssh_registered": True,
                "public_key_fingerprint": pub_fingerprint,
                "message": "already registered (found .ok)",
            }
        except Exception:
            pass  # .ok not found yet, continue with upload

        # 上传 .pub
        remote.put_object(
            **_cvm_args(cfg),
            remote_path=inbox_path,
            key=f"{inbox_path}/{pub_filename}",
            body=pub_with_comment.encode("utf-8"),
        )
    except remote.SftpError as e:
        return {"status": "error", "message": f"upload failed: {e}"}
    except Exception as e:
        return {"status": "error", "message": f"upload failed: {e}"}

    # 5. 轮询 .ok（cron 每分钟扫一次；最多等 90s）
    deadline = time.time() + poll_timeout
    while time.time() < deadline:
        time.sleep(3)
        try:
            _ = remote.get_object(**_cvm_args(cfg), key=ok_path)
            db.update_user(user_id, ssh_registered=1)
            return {
                "status": "ok",
                "ssh_registered": True,
                "public_key_fingerprint": pub_fingerprint,
                "message": f"registered after ~{int(poll_timeout - (deadline - time.time()))}s",
            }
        except Exception:
            continue

    return {
        "status": "pending",
        "ssh_registered": False,
        "public_key_fingerprint": pub_fingerprint,
        "message": f"公钥已上传到 CVM inbox/，等待 cron 注册（最长 90s）",
    }


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

"""SFTP 客户端封装（v0.3 备份到 CVM 用，替代 cos-python-sdk-v5）。

支持：连接 / 测试 / 列表 / 上传 / 下载 / 删除。
认证：密码 或 私钥（PEM 文本，可选 passphrase）。
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

import paramiko


class SftpError(Exception):
    pass


def _connect(
    host: str,
    port: int,
    username: str,
    auth_method: str,
    password: str | None,
    private_key: str | None,
    private_key_passphrase: str | None,
    timeout: float = 8.0,
) -> paramiko.SSHClient:
    if not host or not username:
        raise SftpError("host/username 不能为空")

    client = paramiko.SSHClient()
    # 第一次连接时跳过 host key 验证（个人 CVM，没有受信任 CA 体系；
    # 生产场景应改成 known_hosts 校验）。
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    pkey = None
    connect_kwargs: dict[str, Any] = {
        "hostname": host,
        "port": int(port) or 22,
        "username": username,
        "timeout": timeout,
        "allow_agent": False,
        "look_for_keys": False,
    }
    if auth_method == "private_key":
        if not private_key:
            raise SftpError("认证方式选了私钥，但未提供私钥内容")
        try:
            pkey = paramiko.RSAKey.from_private_key(
                io.StringIO(private_key),
                password=private_key_passphrase or None,
            )
        except paramiko.ssh_exception.PasswordRequiredException:
            raise SftpError("私钥有 passphrase，请填写或留空重试")
        except paramiko.ssh_exception.SSHException as e:
            raise SftpError(f"私钥格式错误：{e}")
        except Exception as e:
            # 尝试 Ed25519
            try:
                pkey = paramiko.Ed25519Key.from_private_key(
                    io.StringIO(private_key),
                    password=private_key_passphrase or None,
                )
            except Exception:
                raise SftpError(f"私钥解析失败：{e}")
        connect_kwargs["pkey"] = pkey
    else:
        if not password:
            raise SftpError("认证方式选了密码，但未提供密码")
        connect_kwargs["password"] = password

    try:
        client.connect(**connect_kwargs)
    except paramiko.ssh_exception.AuthenticationException:
        raise SftpError("认证失败：用户名/密码/私钥不正确")
    except paramiko.ssh_exception.SSHException as e:
        raise SftpError(f"SSH 错误：{e}")
    except Exception as e:
        raise SftpError(f"连接失败：{e}")
    return client


def _normalize_remote(remote_path: str, filename: str | None = None) -> str:
    """拼路径：保证不出现双 / 。"""
    base = (remote_path or "/home/fanwei/backups/").rstrip("/")
    if filename:
        return f"{base}/{filename.lstrip('/')}"
    return base


def test_connection(
    host: str,
    port: int,
    username: str,
    auth_method: str,
    password: str | None,
    private_key: str | None,
    private_key_passphrase: str | None,
    remote_path: str,
) -> tuple[bool, str]:
    client = _connect(host, port, username, auth_method, password, private_key, private_key_passphrase)
    try:
        sftp = client.open_sftp()
        try:
            # 探测目录可访问 + 可写
            sftp.stat(remote_path)
            # 写测试文件
            test_name = f".daydayup_test_{int(datetime.now().timestamp())}"
            test_path = _normalize_remote(remote_path, test_name)
            try:
                with sftp.open(test_path, "w") as f:
                    f.write("ok")
                sftp.remove(test_path)
            except Exception as e:
                return False, f"目录可访问但写失败：{e}"
        finally:
            sftp.close()
    except Exception as e:
        return False, str(e)
    finally:
        try:
            client.close()
        except Exception:
            pass
    return True, "ok"


def list_objects(
    host: str,
    port: int,
    username: str,
    auth_method: str,
    password: str | None,
    private_key: str | None,
    private_key_passphrase: str | None,
    remote_path: str,
    prefix: str | None = None,
) -> list[dict[str, Any]]:
    client = _connect(host, port, username, auth_method, password, private_key, private_key_passphrase)
    items: list[dict[str, Any]] = []
    try:
        sftp = client.open_sftp()
        try:
            base = remote_path.rstrip("/")
            filter_prefix = (prefix or "").lstrip("/")
            for attr in sftp.listdir_attr(remote_path):
                if attr.filename.startswith("."):
                    continue
                # 仅列文件
                # paramiko 不直接给 file/dir 区分，stat 用 st_mode 判断
                import stat as stat_mod
                if not stat_mod.S_ISREG(attr.st_mode):
                    continue
                key = f"{base}/{attr.filename}"
                if filter_prefix and not key.endswith(".db.enc"):
                    continue
                items.append({
                    "key": key,
                    "size": int(attr.st_size or 0),
                    "last_modified": datetime.fromtimestamp(int(attr.st_mtime), tz=timezone.utc).isoformat() if attr.st_mtime else "",
                    "etag": "",
                })
        finally:
            sftp.close()
    finally:
        try:
            client.close()
        except Exception:
            pass
    items.sort(key=lambda x: x.get("last_modified", ""), reverse=True)
    return items


def put_object(
    host: str,
    port: int,
    username: str,
    auth_method: str,
    password: str | None,
    private_key: str | None,
    private_key_passphrase: str | None,
    remote_path: str,
    key: str,
    body: bytes,
) -> dict[str, Any]:
    client = _connect(host, port, username, auth_method, password, private_key, private_key_passphrase)
    try:
        sftp = client.open_sftp()
        try:
            sftp.putfo(io.BytesIO(body), key)
        finally:
            sftp.close()
    finally:
        try:
            client.close()
        except Exception:
            pass
    return {"etag": "", "request_id": ""}


def get_object(
    host: str,
    port: int,
    username: str,
    auth_method: str,
    password: str | None,
    private_key: str | None,
    private_key_passphrase: str | None,
    key: str,
) -> bytes:
    client = _connect(host, port, username, auth_method, password, private_key, private_key_passphrase)
    try:
        sftp = client.open_sftp()
        try:
            with sftp.open(key, "rb") as f:
                return f.read()
        finally:
            sftp.close()
    finally:
        try:
            client.close()
        except Exception:
            pass


def delete_object(
    host: str,
    port: int,
    username: str,
    auth_method: str,
    password: str | None,
    private_key: str | None,
    private_key_passphrase: str | None,
    key: str,
) -> None:
    client = _connect(host, port, username, auth_method, password, private_key, private_key_passphrase)
    try:
        sftp = client.open_sftp()
        try:
            sftp.remove(key)
        finally:
            sftp.close()
    finally:
        try:
            client.close()
        except Exception:
            pass

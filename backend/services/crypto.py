"""AES-256-GCM 加密 + PBKDF2 密钥派生（v0.3 云备份用）。

文件格式：`[16B salt][12B nonce][ciphertext+16B tag]`
- salt 用于 PBKDF2 派生主密钥
- nonce 用于 AES-GCM
- ciphertext 末尾 16B 是 GCM auth tag（cryptography 库自动追加）
"""
from __future__ import annotations

import os
import base64

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

ITERATIONS = 200_000   # PBKDF2 迭代次数（OWASP 2023 推荐 ≥ 100k）
KEY_LEN = 32           # 256 bit
SALT_LEN = 16
NONCE_LEN = 12


def derive_key(passphrase: str, salt: bytes, iterations: int = ITERATIONS) -> bytes:
    if not passphrase:
        raise ValueError("passphrase is empty")
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=KEY_LEN, salt=salt, iterations=iterations)
    return kdf.derive(passphrase.encode("utf-8"))


def encrypt(plaintext: bytes, passphrase: str) -> bytes:
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = derive_key(passphrase, salt)
    ct = AESGCM(key).encrypt(nonce, plaintext, None)
    return salt + nonce + ct


def decrypt(blob: bytes, passphrase: str) -> bytes:
    if len(blob) < SALT_LEN + NONCE_LEN + 16:
        raise ValueError("blob too short to be a valid encrypted payload")
    salt = blob[:SALT_LEN]
    nonce = blob[SALT_LEN:SALT_LEN + NONCE_LEN]
    ct = blob[SALT_LEN + NONCE_LEN:]
    key = derive_key(passphrase, salt)
    return AESGCM(key).decrypt(nonce, ct, None)


# ---- 便于前端使用的 base64 工具 ----
def encrypt_b64(plaintext: bytes, passphrase: str) -> str:
    return base64.b64encode(encrypt(plaintext, passphrase)).decode("ascii")


def decrypt_b64(b64: str, passphrase: str) -> bytes:
    return decrypt(base64.b64decode(b64), passphrase)

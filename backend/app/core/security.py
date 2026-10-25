"""密码哈希工具。

登录 / 注册 / JWT 已随多用户体系移除；本模块只保留密码哈希函数，
用于本地用户的非空占位字段与历史数据兼容，不参与任何登录校验。

实现：PBKDF2-HMAC-SHA256（标准库 ``hashlib.pbkdf2_hmac``，260,000 轮，
16 字节随机盐），哈希串自描述格式
``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>``。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 260_000
_SALT_BYTES = 16
_HASH_BYTES = 32


def hash_password(plain: str) -> str:
    """对明文做 PBKDF2-HMAC-SHA256 哈希。

    Args:
        plain: 明文密码。

    Returns:
        str: 自描述哈希串 ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>``。
    """
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256", plain.encode("utf-8"), salt, _ITERATIONS, dklen=_HASH_BYTES
    )
    return f"{_ALGORITHM}${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文与存储哈希是否匹配（恒定时间比较）。

    Args:
        plain: 明文密码。
        hashed: 数据库中存储的哈希串。

    Returns:
        bool: 匹配返回 True，否则 False（格式非法同样返回 False）。
    """
    try:
        algorithm, iterations, salt_hex, hash_hex = hashed.split("$")
        if algorithm != _ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            plain.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
            dklen=len(hash_hex) // 2,
        )
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, TypeError):
        return False

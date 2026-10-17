"""密码哈希与校验（PBKDF2-HMAC-SHA256，标准库实现）。

P2 仅提供两个密码函数（种子数据落库使用）；JWT 签发 / 校验
属认证阶段（P3）实现，本文件不预留占位。

实现说明：
- 采用标准库 ``hashlib.pbkdf2_hmac``（260,000 轮 SHA-256，
  FIPS 兼容），避免 passlib 与 bcrypt>=4.1 的兼容性告警，
  且无第三方依赖；
- 哈希串自描述格式 ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>``，
  P3 认证阶段如迁移 bcrypt 可按前缀区分算法，平滑过渡。
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
    """对明文密码做 PBKDF2-HMAC-SHA256 哈希。

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
    """校验明文密码与存储哈希是否匹配（恒定时间比较）。

    Args:
        plain: 用户输入的明文密码。
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
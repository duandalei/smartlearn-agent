"""密码哈希与 JWT 签发 / 校验。

密码部分（P2 实现，P3 直接复用，禁止改用 bcrypt 或重新实现）：
- PBKDF2-HMAC-SHA256（标准库 ``hashlib.pbkdf2_hmac``，260,000 轮，
  16 字节随机盐），哈希串自描述格式
  ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>``。

JWT 部分（P3 实现）：
- 签发与校验统一走本模块 ``create_access_token`` / ``verify_access_token``；
- 使用标准库 ``hmac`` + ``hashlib`` 实现 HS256（HMAC-SHA256），
  不依赖任何第三方 JWT 库；密钥与有效期统一从 ``core/config.py``
  读取，代码内不出现任何硬编码密钥。
- 安全约束：算法锁死 HS256（拒绝其他 alg，防 alg 混淆 / none 攻击）；
  校验时先验签（``hmac.compare_digest`` 恒定时间比较）再解析 payload；
  校验 ``exp`` 过期时间；``sub`` 必须为纯数字字符串。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from app.core.config import get_settings

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

# ---------------------------------------------------------------------------
# JWT 签发与校验（HS256）
# ---------------------------------------------------------------------------
# 算法锁死 HS256：配置中的 JWT_ALGORITHM 非 HS256 时直接拒绝，
# 防止 alg 混淆 / none 算法攻击。
_SUPPORTED_JWT_ALGORITHM: str = "HS256"


class TokenError(ValueError):
    """JWT 校验失败（格式非法 / 签名不符 / 已过期 / 算法不支持）。"""


def _b64url_encode(data: bytes) -> str:
    """字节串编码为 base64url（无 padding）。

    Args:
        data: 原始字节。

    Returns:
        str: base64url 编码字符串（不含 ``=`` 填充）。
    """
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    """解码 base64url 字符串（自动补齐 padding）。

    Args:
        data: base64url 编码字符串。

    Returns:
        bytes: 原始字节。

    Raises:
        ValueError: 字符串含非法字符或长度错误。
    """
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _hmac_sha256_sign(message: str, secret: str) -> str:
    """对消息做 HMAC-SHA256 签名并返回 base64url 串。

    Args:
        message: 待签名字符串（ASCII）。
        secret: 签名密钥。

    Returns:
        str: 签名的 base64url 表示。
    """
    digest = hmac.new(
        secret.encode("utf-8"), message.encode("ascii"), hashlib.sha256
    ).digest()
    return _b64url_encode(digest)


def create_access_token(user_id: int, *, expires_minutes: int | None = None) -> str:
    """为指定用户签发 JWT（HS256）。

    Args:
        user_id: 用户 id，写入 ``sub`` 声明（字符串）。
        expires_minutes: 覆盖有效期（分钟）；None 时使用配置
            ``JWT_EXPIRE_MINUTES``（默认 7 天 = 10080 分钟）。

    Returns:
        str: 签名后的 JWT 字符串。

    Raises:
        ValueError: 配置的算法不是 HS256。
    """
    cfg = get_settings()
    if cfg.JWT_ALGORITHM != _SUPPORTED_JWT_ALGORITHM:
        raise ValueError(f"JWT 仅支持 {_SUPPORTED_JWT_ALGORITHM}，当前配置为 {cfg.JWT_ALGORITHM}")
    minutes = expires_minutes if expires_minutes is not None else cfg.JWT_EXPIRE_MINUTES
    now = int(time.time())
    payload = {"sub": str(user_id), "iat": now, "exp": now + int(minutes) * 60}
    header = {"alg": _SUPPORTED_JWT_ALGORITHM, "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}"
    return f"{signing_input}.{_hmac_sha256_sign(signing_input, cfg.JWT_SECRET)}"


def verify_access_token(token: str) -> int:
    """校验 JWT 并返回其中携带的用户 id。

    校验顺序：先恒定时间验签，再解析 payload（防止对未验签内容的
    任何解析与信任），随后校验 header alg、exp 过期时间与 sub 格式。

    Args:
        token: Bearer Token 去掉 ``Bearer `` 前缀后的字符串。

    Returns:
        int: ``sub`` 声明中的用户 id。

    Raises:
        TokenError: 令牌格式非法、签名不符、算法不支持、已过期
            或 ``sub`` 不是合法数字。
    """
    cfg = get_settings()
    if cfg.JWT_ALGORITHM != _SUPPORTED_JWT_ALGORITHM:
        raise TokenError(f"JWT 仅支持 {_SUPPORTED_JWT_ALGORITHM}，当前配置为 {cfg.JWT_ALGORITHM}")
    parts = token.split(".")
    if len(parts) != 3:
        raise TokenError("令牌格式非法")
    header_b64, payload_b64, signature_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}"
    expected = _hmac_sha256_sign(signing_input, cfg.JWT_SECRET)
    if not hmac.compare_digest(expected, signature_b64):
        raise TokenError("令牌签名不符")
    try:
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
    except ValueError as exc:
        raise TokenError("令牌格式非法") from exc
    if not isinstance(header, dict) or header.get("alg") != _SUPPORTED_JWT_ALGORITHM:
        raise TokenError("令牌算法不支持")
    exp = payload.get("exp") if isinstance(payload, dict) else None
    if not isinstance(exp, (int, float)) or time.time() >= exp:
        raise TokenError("令牌已过期")
    sub = payload.get("sub") if isinstance(payload, dict) else None
    if not isinstance(sub, str) or not sub.isdigit():
        raise TokenError("令牌负载非法")
    return int(sub)
"""应用配置模块。

通过 pydantic-settings 从项目根的 ``.env`` 文件读取配置。
所有密钥、模型名、服务地址一律走配置，**禁止在代码中硬编码**。
切换 LLM / Embedding 只允许修改 ``.env``。

变量清单（与 PROJECT_CONTEXT 第 2 章一致）：
    LLM_BASE_URL / LLM_API_KEY / LLM_MODEL / EMBEDDING_MODEL
    JWT_SECRET / DATABASE_URL / CHROMA_DIR
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# JWT_SECRET 禁止使用的占位值（与 backend/.env.example 保持一致）。
_JWT_SECRET_PLACEHOLDER: str = "change-me-in-env"

# ---------------------------------------------------------------------------
# 路径计算：backend/app/core/config.py -> backend -> 项目根
# ---------------------------------------------------------------------------
# backend/app/core
CORE_DIR: Path = Path(__file__).resolve().parent
# backend/app
APP_DIR: Path = CORE_DIR.parent
# backend
BACKEND_DIR: Path = APP_DIR.parent
# 项目根（smartlearn/）
PROJECT_ROOT: Path = BACKEND_DIR.parent
# 默认运行时数据目录（不进版本库）
DATA_DIR: Path = PROJECT_ROOT / "data"

# .env 文件优先读取项目根，其次读取 backend/ 目录（便于本地调试）
_ENV_FILES: tuple[str, ...] = (
    str(PROJECT_ROOT / ".env"),
    str(BACKEND_DIR / ".env"),
)


class Settings(BaseSettings):
    """全局配置对象。

    所有字段均可通过环境变量或 ``.env`` 覆盖，字段名与环境变量名一致
    （大小写不敏感）。未显式配置时使用下方默认值，保证开箱即可启动。

    Attributes:
        LLM_BASE_URL: OpenAI 兼容服务地址，用于对话与向量化。
        LLM_API_KEY: LLM 服务密钥。
        LLM_MODEL: 对话 / 推理模型名。
        EMBEDDING_MODEL: 向量化模型名。
        JWT_SECRET: JWT 签发与校验密钥。
        JWT_ALGORITHM: JWT 签名算法。
        JWT_EXPIRE_MINUTES: Token 有效期（分钟）。
        DATABASE_URL: SQLAlchemy 连接串，默认 SQLite 文件 data/smartlearn.db。
        CHROMA_DIR: Chroma 本地持久化目录。
        CORS_ORIGINS: 允许跨域的前端地址列表。
        APP_NAME / APP_VERSION / API_V1_PREFIX / DEBUG: 应用元信息与开关。
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- 应用元信息 -------------------------------------------------------
    APP_NAME: str = "SmartLearn Agent"
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True

    # ---- LLM / Embedding --------------------------------------------------
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""
    EMBEDDING_MODEL: str = ""

    # ---- 安全 -------------------------------------------------------------
    JWT_SECRET: str = "change-me-in-env"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7

    # ---- 数据库 -----------------------------------------------------------
    # 默认指向项目根 data/smartlearn.db（SQLite），可在 .env 中覆盖。
    DATABASE_URL: str = f"sqlite:///{(DATA_DIR / 'smartlearn.db').as_posix()}"

    # ---- 向量库 -----------------------------------------------------------
    CHROMA_DIR: str = (DATA_DIR / "chroma").as_posix()

    # ---- 上传目录 ---------------------------------------------------------
    UPLOAD_DIR: str = (DATA_DIR / "uploads").as_posix()
    PUBLIC_KB_DIR: str = (DATA_DIR / "public_kb").as_posix()

    # ---- CORS -------------------------------------------------------------
    # 前端开发服务器默认端口 5173。
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @model_validator(mode="after")
    def _validate_jwt_secret(self) -> "Settings":
        """启动时强制校验 JWT 密钥（安全红线）。

        JWT_SECRET 为空、纯空白或仍等于 .env.example 的占位值时，
        配置加载直接失败 —— 服务必须启动失败退出，禁止使用任何
        内置默认密钥继续运行。

        Raises:
            ValueError: JWT_SECRET 缺失或仍为占位值。
        """
        secret = (self.JWT_SECRET or "").strip()
        if not secret or secret == _JWT_SECRET_PLACEHOLDER:
            raise ValueError(
                "JWT_SECRET 未配置或仍为占位值：请在 .env 中设置为随机强密钥"
                "（可用 python -c \"import secrets; print(secrets.token_hex(32))\" "
                "生成）。禁止使用空值或占位值启动服务。"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """获取全局配置单例。

    使用 ``lru_cache`` 保证进程内只解析一次 ``.env``，避免重复 IO。

    Returns:
        Settings: 全局唯一的配置对象。
    """
    return Settings()


# 模块级快捷引用，便于 `from app.core.config import settings` 直接使用。
settings: Settings = get_settings()
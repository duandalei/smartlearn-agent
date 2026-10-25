"""应用配置模块。

通过 pydantic-settings 从项目根的 ``.env`` 文件读取配置。
所有密钥、模型名、服务地址一律走配置，**禁止在代码中硬编码**。
切换 LLM / Embedding 只允许修改 ``.env``。

变量清单（与 PROJECT_CONTEXT 第 2 章一致）：
    LLM_BASE_URL / LLM_API_KEY / LLM_MODEL（对话配置组）
    EMBEDDING_BASE_URL / EMBEDDING_API_KEY / EMBEDDING_MODEL（向量化配置组，
    任一项为空时逐项回退对应 LLM_* 值）
    DATABASE_URL / CHROMA_DIR / RAG_MIN_SCORE"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
        LLM_BASE_URL: OpenAI 兼容服务地址（对话配置组）。
        LLM_API_KEY: LLM 服务密钥（对话配置组）。
        LLM_MODEL: 对话 / 推理模型名（对话配置组）。
        EMBEDDING_BASE_URL: 向量化服务地址（向量化配置组，空则回退 LLM_BASE_URL）。
        EMBEDDING_API_KEY: 向量化服务密钥（向量化配置组，空则回退 LLM_API_KEY）。
        EMBEDDING_MODEL: 向量化模型名（向量化配置组，空则回退 LLM_MODEL）。
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

    # ---- LLM / Embedding（双配置组：对话走 LLM_*，向量化走 EMBEDDING_*）----
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""
    EMBEDDING_BASE_URL: str = ""
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = ""

    # ---- 数据库 -----------------------------------------------------------
    # 默认指向项目根 data/smartlearn.db（SQLite），可在 .env 中覆盖。
    DATABASE_URL: str = f"sqlite:///{(DATA_DIR / 'smartlearn.db').as_posix()}"

    # ---- 向量库 -----------------------------------------------------------
    CHROMA_DIR: str = (DATA_DIR / "chroma").as_posix()

    # ---- RAG 检索阈值（P9，裁决 #12）-------------------------------------
    # 无据判定阈值：检索命中 score 低于该值视为无据。取值依据（bge-m3
    # 实测分数分布）：领域内 0.572–0.733 / 领域外 0.412–0.533，0.55
    # 恰好挡住领域外最高分 0.533 并保住领域内最低分 0.572（间隔仅
    # 0.04，故另有 Prompt 第二道防线兜底，见 rag/qa.py 模板一规则 3）。
    # 留空回退默认 0.55（契约 §2「留空回退默认」）。
    RAG_MIN_SCORE: float = Field(default=0.55, ge=0.0, le=1.0)

    @field_validator("RAG_MIN_SCORE", mode="before")
    @classmethod
    def _rag_min_score_empty_fallback(cls, value: object) -> object:
        """RAG_MIN_SCORE 留空回退默认 0.55（契约 §2）。

        pydantic-settings 直接映射 float 在环境变量为空字符串或 None
        时会校验失败，必须前置转换（design.md 1.1.2 / tasks.md 1.1）。

        Args:
            value: 环境变量原始值（可能为空串 / None / 数字）。

        Returns:
            object: 空值回退为 0.55，其余原样交给 Field 约束校验。
        """
        if value is None or (isinstance(value, str) and not value.strip()):
            return 0.55
        return value

    # ---- 上传目录 ---------------------------------------------------------
    UPLOAD_DIR: str = (DATA_DIR / "uploads").as_posix()

    # ---- CORS -------------------------------------------------------------
    # 前端开发服务器默认端口 5173。
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # ---- 向量化生效配置（逐项回退，只读派生属性）--------------------------
    # 支持单服务商一键配置：EMBEDDING_* 任一项为空时回退对应 LLM_* 值。
    # 回退 debug 日志由 services/llm.py 在构造向量化客户端时输出，
    # config 层保持纯净、不打印任何日志与密钥明文。

    @property
    def embedding_base_url_effective(self) -> str:
        """向量化服务地址（EMBEDDING_BASE_URL 为空时回退 LLM_BASE_URL）。

        Returns:
            str: 向量化实际使用的服务地址。
        """
        return self.EMBEDDING_BASE_URL.strip() or self.LLM_BASE_URL.strip()

    @property
    def embedding_api_key_effective(self) -> str:
        """向量化服务密钥（EMBEDDING_API_KEY 为空时回退 LLM_API_KEY）。

        Returns:
            str: 向量化实际使用的密钥（不打印、不落日志）。
        """
        return self.EMBEDDING_API_KEY.strip() or self.LLM_API_KEY.strip()

    @property
    def embedding_model_effective(self) -> str:
        """向量化模型名（EMBEDDING_MODEL 为空时回退 LLM_MODEL）。

        Returns:
            str: 向量化实际使用的模型名。
        """
        return self.EMBEDDING_MODEL.strip() or self.LLM_MODEL.strip()


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
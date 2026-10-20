"""FastAPI 应用入口。

职责：
1. 创建 FastAPI 实例（标题 / 版本来自配置）。
2. 注册 CORS 中间件（默认允许前端 http://localhost:5173）。
3. 注册全局异常处理器（统一 ``{code, message, data}`` 响应）。
4. 挂载路由：业务路由前缀 ``/api/v1``，健康检查 ``/health``（无前缀）。

启动方式见项目根 README 或 backend/run.sh。
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router, health_router
from app.core.config import settings
from app.core.response import success
from app.db.migrate import ensure_schema_upgrades
from app.db.session import engine

app: FastAPI = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
)

# ---------------------------------------------------------------------------
# 启动幂等轻量迁移（P8）：import 后、路由挂载前执行——升级代码后重启
# 即完成加列与 file_size 回填，二次启动为空操作（取舍理由见 db/migrate.py）。
# ---------------------------------------------------------------------------
ensure_schema_upgrades(engine)

# ---------------------------------------------------------------------------
# CORS：允许前端开发服务器访问；具体来源由 .env 的 CORS_ORIGINS 控制。
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# 全局异常处理器：保证任何异常都返回统一响应体。
# ---------------------------------------------------------------------------
from app.core.response import register_exception_handlers  # noqa: E402

register_exception_handlers(app)

# ---------------------------------------------------------------------------
# 路由挂载
# ---------------------------------------------------------------------------
# 健康检查：不带版本前缀（PROJECT_CONTEXT 5.1）。
app.include_router(health_router)
# 业务路由：统一 /api/v1 前缀。
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", tags=["root"], summary="服务根路径")
def root() -> dict[str, Any]:
    """返回服务基本信息，便于快速确认服务已启动。

    Returns:
        dict: 统一响应体，``data`` 含服务名与版本。
    """
    return success(
        data={"name": settings.APP_NAME, "version": settings.APP_VERSION},
        message="ok",
    )
"""api 层公共依赖注入。

骨架阶段仅提供已实现的依赖（数据库会话）。``get_current_user`` 等鉴权依赖
将在后续「用户档案 / 认证」阶段实现，本阶段不预留占位函数，避免启动失败。
"""

from __future__ import annotations

from app.db.session import get_db

__all__ = ["get_db"]
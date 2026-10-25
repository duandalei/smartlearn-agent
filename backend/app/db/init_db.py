"""数据库初始化（建表 + 本地用户）。

本地单用户项目，不再写入任何演示业务数据。首次启动：

1. 建齐全部数据表（``Base.metadata.create_all``，幂等）；
2. 确保存在一条本地用户（优先复用库中已有用户，空库创建 ``local``）。

演示数据由用户自己通过界面 / AI 助手生成，不随仓库或种子提供。
"""

from __future__ import annotations

from pathlib import Path

import app.models  # noqa: F401 - 导入以注册全部 ORM 模型到 Base.metadata
from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.models.base import Base
from app.services.local_user import ensure_local_user


def init_db() -> None:
    """建表并确保本地用户存在（幂等）。"""
    db_url = settings.DATABASE_URL
    if db_url.startswith("sqlite:///"):
        Path(db_url.removeprefix("sqlite:///")).parent.mkdir(
            parents=True, exist_ok=True
        )
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        user = ensure_local_user(db)
    print(f"数据库初始化完成：表已就绪，本地用户 id={user.id}")


if __name__ == "__main__":
    init_db()

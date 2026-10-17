"""数据库会话管理。

创建 SQLAlchemy 2.x 的 engine 与 SessionLocal，并提供 FastAPI 依赖
``get_db``。数据库为 SQLite，文件位于项目根 ``data/smartlearn.db``（可通过
``.env`` 的 ``DATABASE_URL`` 覆盖）。

SQLite 默认关闭外键约束，本模块在每条新连接上执行
``PRAGMA foreign_keys=ON``，保证模型层声明的 ``ForeignKey`` 级联
（CASCADE / SET NULL）真实生效。
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# ---------------------------------------------------------------------------
# engine 构造
# ---------------------------------------------------------------------------
# SQLite 在多线程（FastAPI 线程池）下需关闭同线程校验；其它数据库无需该参数。
_connect_args: dict[str, object] = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

# 若为 SQLite 文件库，确保父目录存在，避免首次启动因目录缺失失败。
if settings.DATABASE_URL.startswith("sqlite:///"):
    _db_path_str = settings.DATABASE_URL.replace("sqlite:///", "", 1)
    # 排除内存库（:memory:）
    if _db_path_str and _db_path_str != ":memory:":
        Path(_db_path_str).expanduser().resolve().parent.mkdir(
            parents=True, exist_ok=True
        )

engine: Engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    echo=False,
    future=True,
)

SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


# ---------------------------------------------------------------------------
# SQLite 外键 PRAGMA
# ---------------------------------------------------------------------------
# SQLite 默认关闭外键约束（级联删除形同虚设）。通过 connect 事件监听，
# 在每条新连接（含连接池复用后重连）上开启 PRAGMA foreign_keys=ON。
# 非 SQLite 连接串（.env 覆盖）时跳过注册，模块导入不报错。
if engine.dialect.name == "sqlite":

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(
        dbapi_connection: Any, connection_record: Any
    ) -> None:
        """连接建立时开启 SQLite 外键约束，使 FK 级联真实生效。

        Args:
            dbapi_connection: DBAPI 层连接对象。
            connection_record: SQLAlchemy 连接池的连接记录。
        """
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：提供数据库会话。

    每个请求获取一个 Session，请求结束后自动关闭，保证连接不泄漏。

    Yields:
        Session: SQLAlchemy 会话对象。

    Example:
        >>> @router.get("/demo")
        ... def demo(db: Session = Depends(get_db)) -> dict:
        ...     ...
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
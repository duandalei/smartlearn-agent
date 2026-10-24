"""启动幂等轻量 schema 迁移（全仓首个加列场景）。

职责（design.md 2.3.2-A）：
1. ``knowledge_items`` 补 ``file_size INTEGER NULL`` 列，并对
   ``file_path`` 非空且 ``file_size IS NULL`` 的行按文件系统 stat 回填
   字节数（文件缺失时保持 NULL 并记 warning，不阻断启动）；
2. ``knowledge_chunks`` 补 ``heading_path TEXT NULL`` 列（历史分块
   不回填，由文档重索引写入真实值，见 design.md 2.5）；
3. ``qa_history`` 建表条目（P9，design.md 1.2.4）：main.py 启动时
   不调 create_all，仅把 QAHistory 注册进 ``Base.metadata`` 而不追加
   建表条目的话，**存量库（demo 用户已存在、永不重跑种子）重启后
   qa_history 表不存在，首个 done 落库即 500**——故以
   ``create_all(engine, tables=[QAHistory.__table__])`` 幂等建表
   （已存在跳过，与 P8「重启即升级」惯例一致）。

**为什么放应用启动路径而不放 init_db.py**：种子的幂等开关是
「demo 用户存在即跳过」，存量库永远不会重跑 init_db，迁移挂在
那里等于永不执行；放 ``main.py`` 模块加载路径才能保证「升级代码
后重启即完成迁移」（design.md 2.3.2-A 取舍理由）。

**为什么不用 alembic**：全仓无 alembic 先例，为两个可空列引入
迁移框架违反「禁止引入与需求无关的技术组件」；PRAGMA + ALTER
的十行逻辑足够，后续列变更继续在本模块追加条目即可。

幂等性：PRAGMA 检查列存在性，已存在则跳过 ALTER；回填仅作用于
``file_size IS NULL`` 且原件存在的行，二次启动全部为空操作；
``create_all(tables=[...])`` 对已存在表自动跳过。
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.config import PROJECT_ROOT
from app.models import QAHistory
from app.models.base import Base

logger = logging.getLogger(__name__)


def _table_columns(conn: object, table: str) -> list[str]:
    """读取 SQLite 表的列名清单（PRAGMA table_info）。

    Args:
        conn: 数据库连接（SQLAlchemy Connection）。
        table: 表名。

    Returns:
        list[str]: 列名清单；表不存在时返回空列表（全新库尚未建表，
        建表由 create_all 完成，新表自带全部新列，无需迁移）。
    """
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()  # noqa: S608
    return [str(row[1]) for row in rows]


def _backfill_file_size(conn: object) -> None:
    """回填 ``knowledge_items.file_size``（仅 file_path 非空且 file_size 为 NULL 的行）。

    路径解析口径：``file_path`` 存相对项目根的 POSIX 路径（如
    ``data/uploads/1/1_ml_basics.md``）或绝对路径（测试播种），按
    PROJECT_ROOT 拼接后 stat 取字节数；文件缺失保持 NULL 并记
    warning，不阻断启动（原件被外部移动不应拖垮服务）。

    Args:
        conn: 数据库连接（处于打开事务内）。
    """
    rows = conn.execute(
        text(
            "SELECT id, file_path FROM knowledge_items "
            "WHERE file_path IS NOT NULL AND file_size IS NULL"
        )
    ).fetchall()
    for row_id, file_path in rows:
        p = Path(str(file_path))
        abs_path = p if p.is_absolute() else (PROJECT_ROOT / p)
        try:
            size = abs_path.stat().st_size
        except OSError:
            logger.warning(
                "file_size 回填跳过（原件缺失）: item_id=%s path=%s",
                row_id,
                file_path,
            )
            continue
        conn.execute(
            text("UPDATE knowledge_items SET file_size = :s WHERE id = :i"),
            {"s": size, "i": row_id},
        )
        logger.info("file_size 回填: item_id=%s size=%s", row_id, size)


def ensure_schema_upgrades(engine: Engine) -> None:
    """执行启动期幂等 schema 升级（P8：两个可空列 + file_size 回填；
    P9：qa_history 建表条目）。

    Args:
        engine: 全局 engine（与业务库同库）。

    Raises:
        Exception: 仅当 ALTER/UPDATE 本身失败（数据库损坏级错误）；
            原件缺失等业务性异常不抛出、不阻断启动。
    """
    with engine.begin() as conn:
        item_cols = _table_columns(conn, "knowledge_items")
        if item_cols and "file_size" not in item_cols:
            conn.execute(
                text("ALTER TABLE knowledge_items ADD COLUMN file_size INTEGER NULL")
            )
            logger.info("已为 knowledge_items 添加 file_size 列")
        chunk_cols = _table_columns(conn, "knowledge_chunks")
        if chunk_cols and "heading_path" not in chunk_cols:
            conn.execute(
                text("ALTER TABLE knowledge_chunks ADD COLUMN heading_path TEXT NULL")
            )
            logger.info("已为 knowledge_chunks 添加 heading_path 列")
        # 回填放在 ALTER 之后：存量库首次升级时同事务完成补列与回填；
        # 全新库（表不存在，item_cols 为空）跳过，由 create_all 建全表，
        # 新表行 file_size 由业务写入，无回填需求。
        if item_cols:
            _backfill_file_size(conn)
    # P9：qa_history 建表（幂等：表已存在时 create_all 自动跳过；
    # create_all 自带连接管理，置于显式事务外执行）。
    Base.metadata.create_all(engine, tables=[QAHistory.__table__])
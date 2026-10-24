"""一次性数据迁移：把存量「公共库」文档转入 demo 用户的个人库。

公共库能力移除后，``scope=public`` 的存量文档在新可见性口径下不可见。
本脚本按既定默认处理把它们迁移为 demo 用户个人文档：

1. 备份 SQLite 主文件（含 -wal / -shm）到
   ``data/_reset_backup/public-to-personal-<时间戳>/``；
2. 逐篇将 ``user_id`` 置为 demo 用户 id、``scope`` 置为 personal，
   ``file_path`` 从 ``data/public_kb/<name>`` 改写为
   ``data/uploads/<demo_id>/<id>_<name>``（源文件已作为普通上传
   放入 uploads），同步更新分块的冗余 ``user_id``；
3. 逐篇执行 ``reindex_item`` + ``process_document``，把向量重建到
   demo 个人 collection；
4. 全部成功后删除遗留的 ``kb_public`` / ``kb_public_local``
   collection（失败时保留，便于排查）。

幂等性：库中不存在 ``scope=public`` 文档时直接成功退出（零写操作）。

用法（先停止后端）：

    cd backend
    .venv/Scripts/python scripts/migrate_public_to_personal.py --yes
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select, text  # noqa: E402

from app.core.config import PROJECT_ROOT, settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.enums import KnowledgeItemStatus  # noqa: E402
from app.models.knowledge import KnowledgeItem  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.knowledge import process_document, reindex_item  # noqa: E402

_SQLITE_PREFIX = "sqlite:///"


def _db_path() -> Path:
    """从 ``settings.DATABASE_URL`` 解析 SQLite 文件路径。"""
    url = settings.DATABASE_URL
    if not url.startswith(_SQLITE_PREFIX):
        raise SystemExit(f"仅支持 SQLite 数据库，当前为: {url}")
    raw = url[len(_SQLITE_PREFIX):]
    path = Path(raw)
    if not path.is_absolute():
        path = (BACKEND_DIR / path).resolve()
    return path


def _backup(db_path: Path) -> Path:
    """备份 SQLite 主文件及 -wal / -shm 伴随文件。"""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = (db_path.parent / "_reset_backup" / f"public-to-personal-{stamp}")
    dest.mkdir(parents=True, exist_ok=False)
    for candidate in (
        db_path,
        db_path.with_name(db_path.name + "-wal"),
        db_path.with_name(db_path.name + "-shm"),
    ):
        if candidate.exists():
            shutil.copy2(candidate, dest / candidate.name)
    return dest


def _confirm() -> None:
    if "--yes" in sys.argv:
        return
    print("本脚本会修改存量数据库（建议先停止后端）：")
    print("  1) 备份数据库；2) 公共文档转 demo 个人库并重索引；")
    print("  3) 删除遗留 kb_public* 向量 collection。")
    try:
        answer = input("输入 yes 继续: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n已取消。")
        raise SystemExit(1)
    if answer != "yes":
        print("已取消。")
        raise SystemExit(1)


def main() -> int:
    _confirm()
    db_path = _db_path()
    if not db_path.exists():
        print(f"数据库不存在，无需迁移: {db_path}")
        return 0

    with SessionLocal() as db:
        demo = db.scalar(select(User).where(User.username == "demo"))
        if demo is None:
            print("[FAIL] 未找到 demo 用户，无法确定迁移归属。")
            return 1
        # 历史行 scope='public' 已不在枚举内，必须走原生 SQL 读取，
        # 经 ORM 加载会触发 LookupError。
        items = db.execute(
            text(
                "SELECT id, title, file_path FROM knowledge_items "
                "WHERE scope = 'public' ORDER BY id"
            )
        ).all()
        if not items:
            print("未发现 scope=public 文档，迁移已是目标状态（零写操作）。")
            return 0

        backup_dir = _backup(db_path)
        print(f"数据库备份: {backup_dir}")
        name_map = {
            "ml_basics.md": "1_ml_basics.md",
            "linear_algebra_notes.md": "2_linear_algebra_notes.md",
            "probability_formulas.md": "3_probability_formulas.md",
            "ds_cheatsheet.md": "4_ds_cheatsheet.md",
        }
        plans: list[tuple[int, str, str]] = []
        for item_id, title, old_path in items:
            name = Path(old_path or "").name
            new_name = name_map.get(name, name)
            new_path = f"data/uploads/{demo.id}/{new_name}"
            if not (PROJECT_ROOT / new_path).is_file():
                print(f"[FAIL] 源文件缺失: {new_path}（item_id={item_id}）")
                return 1
            # 状态置 indexed 而非 pending：reindex_item 会拒绝
            # pending/parsing（1007），必须给一个可受理的状态。
            db.execute(
                text(
                    "UPDATE knowledge_items SET user_id = :uid, "
                    "scope = 'personal', file_path = :path, "
                    "status = 'indexed', error_msg = NULL WHERE id = :id"
                ),
                {"uid": demo.id, "path": new_path, "id": item_id},
            )
            db.execute(
                text(
                    "UPDATE knowledge_chunks SET user_id = :uid "
                    "WHERE item_id = :id"
                ),
                {"uid": demo.id, "id": item_id},
            )
            plans.append((item_id, str(title), new_path))
        db.commit()
        demo_id = demo.id

    all_ok = True
    for item_id, title, new_path in plans:
        chunk_count = 0
        try:
            with SessionLocal() as db:
                user = db.get(User, demo_id)
                reindex_item(db, user, item_id)
            asyncio.run(process_document(item_id))
            with SessionLocal() as db:
                fresh = db.get(KnowledgeItem, item_id)
                ok = (
                    fresh is not None
                    and fresh.status == KnowledgeItemStatus.INDEXED
                    and (fresh.chunk_count or 0) > 0
                )
                chunk_count = (fresh.chunk_count or 0) if fresh is not None else 0
                err = None if ok else (fresh.error_msg if fresh else "终态回查失败")
        except Exception as exc:  # noqa: BLE001 - 逐篇隔离，最终汇总
            ok, err = False, f"{type(exc).__name__}: {exc}"
        if ok:
            print(f"[OK] {title} — {chunk_count} chunks ({new_path})")
        else:
            all_ok = False
            print(f"[FAIL] {title} — {err}")

    if not all_ok:
        print(
            "存在失败篇目，保留 kb_public* collection 以便排查；"
            "修复后可重新执行本脚本。"
        )
        return 1

    from app.rag.vectorstore import get_vector_store

    client = get_vector_store()
    existing = set(client.list_collections())
    for name in ("kb_public", "kb_public_local"):
        if name in existing:
            client.delete_collection(name)
            print(f"已删除遗留 collection: {name}")

    print(f"迁移完成：{len(plans)} 篇文档已归入 demo 个人库。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""知识库（P8）pytest 测试基础设施。

设计要点（tasks.md 组 5 写作说明）：
- **测试库隔离**：conftest 顶部（import app 之前）把
  ``DATABASE_URL`` 环境变量指向 ``tempfile.mkdtemp`` 独立 SQLite
  文件——环境变量优先级高于 ``.env``（pydantic-settings 语义），
  engine 在 import 时即绑定临时库，全程不触碰 ``data/smartlearn.db``；
- **Chroma 隔离**：每测试函数独立 ``tmp_path`` Chroma 目录 +
  重置 vectorstore 单例（function 级 autouse）；
- **上传目录隔离**：``UPLOAD_DIR`` 同样 monkeypatch 到 tmp_path，
  原件落盘不污染 ``data/uploads``；
- **数据库清理**：每测试 ``drop_all + create_all``（临时库上
  重建 15 张表，成本毫秒级），双用户 fixture 每测试重新注册；
- **沙箱网络补丁**：顶部按文件路径加载
  ``backend/scripts/_sandbox_patch.py``（IPv6 socketpair 替代 IPv4，
  规避沙箱 WinError 10051；本机非沙箱环境加载亦无害）；
- **Embedding 在线路径**：本机在线 API 实际可达（P8 实测），
  但测试按「沙箱外网禁」口径一律 monkeypatch 为不可用——本地
  兜底才是测试关键路径（真实计算、真实 Chroma 写入）。
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest
from fastapi import Depends, Request
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# 环境隔离（必须在 import app 之前执行）
# ---------------------------------------------------------------------------
_TEST_ROOT = Path(tempfile.mkdtemp(prefix="kb_pytest_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TEST_ROOT / 'test.db').as_posix()}"

# 注（P13）：scripts/test_tools.py 的收集排除由 scripts/conftest.py 的
# collect_ignore 承担——目录级 conftest 的 pytest_ignore_collect 仅对
# 本目录树生效，对本文件的决策须由 scripts/ 自己的 conftest 作出。

# 沙箱 IPv6 socketpair 补丁：按文件路径加载（不依赖包结构）。
_SANDBOX_PATCH = Path(__file__).resolve().parent / "_sandbox_patch.py"
if _SANDBOX_PATCH.is_file():
    _spec = importlib.util.spec_from_file_location("_sandbox_patch", _SANDBOX_PATCH)
    if _spec is not None and _spec.loader is not None:
        _module = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_module)  # noqa: F841 - 补丁在导入时生效

# backend 根入 sys.path（tests 包内的测试模块以 app.* 绝对导入）。
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# app 相关导入必须放在 DATABASE_URL 设置与 sys.path 准备之后。
from app.api.deps import get_current_user, get_db  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.local_user import ensure_local_user  # noqa: E402


def _create_test_user(username: str) -> dict[str, Any]:
    """直接在测试库创建用户并返回测试用身份头。

    生产环境为本地单用户，没有登录/注册；测试通过 ``X-Test-User``
    头选择当前用户，以保留多用户隔离场景的覆盖。应用侧只在该
    fixture 的依赖覆盖里识别这个头，生产代码不包含。

    Args:
        username: 测试用户名（每测试 drop_all 重建后可重复使用同名）。

    Returns:
        dict[str, Any]: ``{"id", "headers", "username"}``。
    """
    from app.db.session import SessionLocal
    from app.models.user import User, UserProfile

    with SessionLocal() as db:
        user = User(
            username=username,
            email=None,
            hashed_password="!",
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(
            UserProfile(
                user_id=user.id,
                name=None,
                school=None,
                major=None,
                grade=None,
                current_goal_type=None,
                interest_directions=[],
                daily_study_minutes=60,
            )
        )
        db.commit()
        db.refresh(user)
        user_id = user.id
    return {
        "id": user_id,
        "headers": {"X-Test-User": str(user_id)},
        "username": username,
    }


@pytest.fixture(scope="session")
def app_client() -> Any:
    """ASGI 直调 TestClient（会话级单例，应用导入一次）。

    生产环境的 ``get_current_user`` 是本地单用户；测试里覆盖为
    ``X-Test-User`` 头选择用户，从而继续验证用户间数据隔离。
    """
    from fastapi.testclient import TestClient

    from app.main import app

    def _test_current_user(
        request: Request, db: Session = Depends(get_db)
    ) -> User:
        raw = request.headers.get("x-test-user", "")
        if raw.isdigit():
            user = db.get(User, int(raw))
            if user is not None:
                return user
        return ensure_local_user(db)

    app.dependency_overrides[get_current_user] = _test_current_user
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(autouse=True)
def _isolated_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """每测试独立 Chroma / 上传目录 + 干净数据库（autouse）。

    Yields:
        None: 仅为隔离副作用；测试体内无须使用本 fixture。
    """
    from app.core.config import settings
    from app.db.session import engine
    from app.models.base import Base
    from app.rag import vectorstore

    monkeypatch.setattr(settings, "CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    vectorstore._reset_vector_store()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    vectorstore._reset_vector_store()


@pytest.fixture
def user_a(app_client: Any) -> dict[str, Any]:
    """用户 A（测试身份头）。"""
    return _create_test_user("student_a")


@pytest.fixture
def user_b(app_client: Any) -> dict[str, Any]:
    """用户 B（测试身份头，用于隔离断言）。"""
    return _create_test_user("student_b")


@pytest.fixture
def offline_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    """把在线向量化 monkeypatch 为不可用（模拟沙箱断网）。

    流水线与检索的降级链路（EmbeddingUnavailableError → 本地兜底）
    全部真实执行；本地哈希向量计算与 Chroma 写入为真实路径。
    """
    from app.core.response import BizException
    import app.rag.embedding as embedding_module

    def _unavailable() -> Any:
        raise BizException(3000, "AI 服务未配置", http_status=502)

    monkeypatch.setattr(embedding_module, "get_embedding_client", _unavailable)


def upload_document(client: Any, user: dict[str, Any], filename: str, content: bytes) -> Any:
    """上传文档辅助（multipart 字段名 file）。

    Args:
        client: TestClient。
        user: 用户 fixture（含鉴权头）。
        filename: 上传文件名。
        content: 文件字节。

    Returns:
        Any: 上传响应（requests.Response）。
    """
    return client.post(
        "/api/v1/knowledge/upload",
        files={"file": (filename, content)},
        headers=user["headers"],
    )


@pytest.fixture
def demo_docs(
    app_client: Any, user_a: dict[str, Any], offline_embedding: None
) -> list[int]:
    """播种 4 篇测试文档到 user_a 个人库并跑真实离线流水线。

    源文件为 ``backend/tests/fixtures/uploads/`` 下的测试素材，随后
    逐篇 ``process_document``（本地兜底向量化真实入库）；返回 item id
    列表（按文件名排序）。
    """
    import asyncio

    from app.core.config import PROJECT_ROOT
    from app.db.session import SessionLocal
    from app.models.enums import (
        KnowledgeItemStatus,
        KnowledgeScope,
        KnowledgeSourceType,
    )
    from app.models.knowledge import KnowledgeItem
    from app.services.knowledge import process_document

    user_id = app_client.get(
        "/api/v1/auth/me", headers=user_a["headers"]
    ).json()["data"]["id"]
    seed_dir = Path(__file__).resolve().parent / "fixtures" / "uploads"
    names = [
        "1_ml_basics.md",
        "2_linear_algebra_notes.md",
        "3_probability_formulas.md",
        "4_ds_cheatsheet.md",
    ]
    files = [seed_dir / name for name in names]
    assert all(p.is_file() for p in files), f"测试上传文件缺失: {seed_dir}"
    item_ids: list[int] = []
    with SessionLocal() as db:
        for md_file in files:
            item = KnowledgeItem(
                user_id=user_id,
                title=md_file.stem.split("_", 1)[-1],
                source_type=KnowledgeSourceType.MD,
                file_path=md_file.resolve().relative_to(PROJECT_ROOT).as_posix(),
                scope=KnowledgeScope.PERSONAL,
                status=KnowledgeItemStatus.PENDING,
                chunk_count=0,
                file_size=md_file.stat().st_size,
            )
            db.add(item)
            db.flush()
            item_ids.append(item.id)
        db.commit()
    for item_id in item_ids:
        asyncio.run(process_document(item_id))
    return item_ids
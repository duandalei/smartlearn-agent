"""模型 API 设置路由（本地单用户）。

- ``GET  /settings/llm``      读取配置状态（Key 仅返回掩码）
- ``PUT  /settings/llm``      保存到 backend/.env 并热加载
- ``POST /settings/llm/test`` 用表单当前值测试对话 / 向量连接（不落盘）
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.core.response import success
from app.schemas.settings import LLMSettingsIn
from app.services import llm_settings

router: APIRouter = APIRouter(prefix="/settings", tags=["设置"])


@router.get("/llm", summary="读取模型 API 配置状态")
def get_llm_settings() -> dict[str, Any]:
    """返回对话 / 向量配置状态与掩码后的 Key。"""
    return success(data=llm_settings.get_settings_status())


@router.put("/llm", summary="保存模型 API 配置")
def update_llm_settings(body: LLMSettingsIn) -> dict[str, Any]:
    """保存配置到 ``.env`` 并热加载（无需重启后端）。"""
    return success(
        data=llm_settings.save_settings(body.model_dump()), message="配置已保存"
    )


@router.post("/llm/test", summary="测试模型连接")
async def test_llm_settings(body: LLMSettingsIn) -> dict[str, Any]:
    """用表单当前值测试对话（含 tools）与向量连接，不保存。"""
    return success(data=await llm_settings.test_connection(body.model_dump()))

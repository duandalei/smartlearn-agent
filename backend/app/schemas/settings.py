"""模型 API 设置出入参。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LLMSettingsIn(BaseModel):
    """设置页表单 / 测试连接入参。

    ``*_api_key`` 留空表示沿用已保存的值；向量三项留空时回退对话配置。
    """

    model_config = ConfigDict(extra="forbid")

    llm_base_url: str = Field(default="", max_length=500, description="对话 Base URL")
    llm_api_key: str = Field(default="", max_length=500, description="对话 API Key")
    llm_model: str = Field(default="", max_length=200, description="对话模型名")

    embedding_base_url: str = Field(default="", max_length=500, description="向量 Base URL")
    embedding_api_key: str = Field(default="", max_length=500, description="向量 API Key")
    embedding_model: str = Field(default="", max_length=200, description="向量模型名")

"""模型 API 设置读写与热加载（本地单用户）。

配置唯一来源是 ``backend/.env``。设置页保存时：

1. 原子写回 ``.env``（保留注释与其他配置）；
2. **原地修改** ``app.core.config.settings``（不替换对象，很多模块直接
   ``from app.core.config import settings`` 引用它）；
3. 清空 ``app.services.llm`` 的客户端单例。

因此保存后无需重启后端即可生效；重启后从 ``.env`` 重新加载。
"""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from app.core.config import BACKEND_DIR, settings
from app.core.response import CODE_PARAM_INVALID, BizException
from app.services import llm

#: ``.env`` 路径（测试可 monkeypatch）。
ENV_PATH: Path = BACKEND_DIR / ".env"

_TEST_TIMEOUT_S: float = 10.0


def mask_key(key: str) -> str:
    """返回 API Key 掩码（不暴露完整值）。"""
    value = (key or "").strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:3]}****{value[-4:]}"


def get_settings_status() -> dict[str, Any]:
    """返回设置页与首次提示所需的配置状态（Key 只给掩码）。"""
    llm_missing = [
        name
        for name, value in (
            ("base_url", settings.LLM_BASE_URL),
            ("api_key", settings.LLM_API_KEY),
            ("model", settings.LLM_MODEL),
        )
        if not value.strip()
    ]
    embedding_missing = [
        name
        for name, value in (
            ("base_url", settings.EMBEDDING_BASE_URL),
            ("api_key", settings.EMBEDDING_API_KEY),
            ("model", settings.EMBEDDING_MODEL),
        )
        if not value.strip()
    ]
    llm_configured = not llm_missing
    embedding_configured = bool(
        settings.embedding_base_url_effective.strip()
        and settings.embedding_api_key_effective.strip()
        and settings.embedding_model_effective.strip()
    )
    return {
        "configured": llm_configured,
        "source": "env" if llm_configured else "none",
        "missing": llm_missing,
        "llm": {
            "base_url": settings.LLM_BASE_URL,
            "model": settings.LLM_MODEL,
            "has_api_key": bool(settings.LLM_API_KEY.strip()),
            "api_key_masked": mask_key(settings.LLM_API_KEY),
            "configured": llm_configured,
        },
        "embedding": {
            "base_url": settings.EMBEDDING_BASE_URL,
            "model": settings.EMBEDDING_MODEL,
            "has_api_key": bool(settings.EMBEDDING_API_KEY.strip()),
            "api_key_masked": mask_key(settings.EMBEDDING_API_KEY),
            "effective_base_url": settings.embedding_base_url_effective,
            "effective_model": settings.embedding_model_effective,
            "configured": embedding_configured,
            "fallback_to_llm": bool(embedding_missing),
            "missing": embedding_missing,
        },
    }


def save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """校验并保存设置到 ``.env``，随后热加载。

    Args:
        payload: ``LLMSettingsIn.model_dump()``，API Key 留空表示沿用旧值。

    Returns:
        dict[str, Any]: 保存后的配置状态。

    Raises:
        BizException: 参数非法（1001 / HTTP 422）。
    """
    base_url = str(payload.get("llm_base_url") or "").strip()
    model = str(payload.get("llm_model") or "").strip()
    api_key = str(payload.get("llm_api_key") or "").strip() or settings.LLM_API_KEY.strip()

    if not base_url or not model:
        raise BizException(
            CODE_PARAM_INVALID, "对话模型的 Base URL 与模型名不能为空", http_status=422
        )
    if not base_url.startswith(("http://", "https://")):
        raise BizException(
            CODE_PARAM_INVALID, "Base URL 必须以 http:// 或 https:// 开头", http_status=422
        )
    if not api_key:
        raise BizException(
            CODE_PARAM_INVALID, "API Key 不能为空", http_status=422
        )

    embedding_base_url = str(payload.get("embedding_base_url") or "").strip()
    embedding_model = str(payload.get("embedding_model") or "").strip()
    embedding_api_key = str(payload.get("embedding_api_key") or "").strip()
    # 向量 Key 留空表示沿用已保存值；但整组向量配置被清空时一并清除，
    # 否则残留的旧 Key 会让运行时无法回退到对话配置。
    if not embedding_api_key and (embedding_base_url or embedding_model):
        embedding_api_key = settings.EMBEDDING_API_KEY.strip()

    updates = {
        "LLM_BASE_URL": base_url,
        "LLM_API_KEY": api_key,
        "LLM_MODEL": model,
        "EMBEDDING_BASE_URL": embedding_base_url,
        "EMBEDDING_API_KEY": embedding_api_key,
        "EMBEDDING_MODEL": embedding_model,
    }
    _write_env(updates)
    for key, value in updates.items():
        setattr(settings, key, value)
    llm.reset_clients()
    return get_settings_status()


async def test_connection(payload: dict[str, Any]) -> dict[str, Any]:
    """用表单当前值测试连接（不落盘）。"""
    llm_base_url = str(payload.get("llm_base_url") or settings.LLM_BASE_URL).strip()
    llm_api_key = (
        str(payload.get("llm_api_key") or "").strip() or settings.LLM_API_KEY.strip()
    )
    llm_model = str(payload.get("llm_model") or settings.LLM_MODEL).strip()

    emb_base_url = str(payload.get("embedding_base_url") or "").strip()
    emb_model = str(payload.get("embedding_model") or "").strip()
    emb_api_key = str(payload.get("embedding_api_key") or "").strip()

    if emb_base_url or emb_model:
        # 表单已填向量配置：空白项依次回退「已保存的向量配置」→「对话配置」。
        # Key 输入框不回显明文，留空必须沿用已保存的向量 Key，否则会拿对话
        # Key 去请求向量服务商（如 DeepSeek Key 请求硅基流动）而误报 401。
        emb_base_url = (
            emb_base_url or settings.EMBEDDING_BASE_URL.strip() or llm_base_url
        )
        emb_model = emb_model or settings.EMBEDDING_MODEL.strip() or llm_model
        emb_api_key = (
            emb_api_key or settings.EMBEDDING_API_KEY.strip() or llm_api_key
        )
    else:
        # 表单未填向量配置：整组回退对话配置。
        emb_base_url, emb_api_key, emb_model = llm_base_url, llm_api_key, llm_model

    return {
        "chat": await _test_chat(llm_base_url, llm_api_key, llm_model),
        "embedding": await _test_embedding(emb_base_url, emb_api_key, emb_model),
    }


async def _test_chat(base_url: str, api_key: str, model: str) -> dict[str, Any]:
    """验证对话配置（同时验证 tools 参数是否被接受）。"""
    if not all((base_url, api_key, model)):
        return {"ok": False, "model": model, "error": "对话配置不完整"}
    client = AsyncOpenAI(
        base_url=base_url, api_key=api_key, timeout=_TEST_TIMEOUT_S, max_retries=0
    )
    try:
        await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "ping",
                            "description": "连接测试",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
            ),
            timeout=_TEST_TIMEOUT_S,
        )
        return {"ok": True, "model": model, "message": "对话连接成功（含 tools 参数）"}
    except Exception as exc:  # noqa: BLE001 - 测试接口需要返回可读错误
        return {
            "ok": False,
            "model": model,
            "error": f"对话连接失败（模型可能不支持 tool calling）：{_short_error(exc)}",
        }


async def _test_embedding(base_url: str, api_key: str, model: str) -> dict[str, Any]:
    """验证向量配置并返回维度。"""
    if not all((base_url, api_key, model)):
        return {"ok": False, "model": model, "error": "向量配置不完整（可留空回退对话配置）"}
    client = AsyncOpenAI(
        base_url=base_url, api_key=api_key, timeout=_TEST_TIMEOUT_S, max_retries=0
    )
    try:
        resp = await asyncio.wait_for(
            client.embeddings.create(model=model, input=["ping"]),
            timeout=_TEST_TIMEOUT_S,
        )
        dimension = len(resp.data[0].embedding) if resp.data else 0
        return {
            "ok": True,
            "model": model,
            "dimension": dimension,
            "message": f"向量连接成功（维度 {dimension}）",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "model": model,
            "error": f"向量连接失败（服务商需支持 /v1/embeddings）：{_short_error(exc)}",
        }


def _short_error(exc: Exception) -> str:
    """截断异常文本，避免把超长响应或密钥写进页面/日志。"""
    text = str(exc).replace("\n", " ").strip()
    return text[:300] or exc.__class__.__name__


def _write_env(updates: dict[str, str]) -> None:
    """原子更新 ``.env``，保留其他行与注释。"""
    text = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
    for key, value in updates.items():
        clean = value.replace("\r", "").replace("\n", "").strip()
        line = f"{key}={clean}"
        pattern = re.compile(rf"(?m)^{re.escape(key)}=.*$")
        if pattern.search(text):
            text = pattern.sub(line, text, count=1)
        else:
            text = text.rstrip("\n") + "\n" + line + "\n"

    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(ENV_PATH.parent), prefix=".env.tmp-", text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp_path, ENV_PATH)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

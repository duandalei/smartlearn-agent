"""模型 API 设置接口测试（不触碰真实 backend/.env）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.core.config import settings
from app.services import llm, llm_settings

_KEYS = (
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_MODEL",
    "EMBEDDING_BASE_URL",
    "EMBEDDING_API_KEY",
    "EMBEDDING_MODEL",
)


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """把 .env 指向临时文件，并清空当前模型配置与客户端缓存。"""
    env_path = tmp_path / ".env"
    monkeypatch.setattr(llm_settings, "ENV_PATH", env_path)
    for key in _KEYS:
        monkeypatch.setattr(settings, key, "")
    monkeypatch.setattr(llm, "_chat_client", object())
    monkeypatch.setattr(llm, "_embedding_client", object())
    return env_path


def test_get_status_missing(app_client: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _isolate(monkeypatch, tmp_path)
    resp = app_client.get("/api/v1/settings/llm")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["configured"] is False
    assert data["source"] == "none"
    assert "base_url" in data["missing"]
    assert data["llm"]["api_key_masked"] == ""


def test_put_saves_env_and_hot_reloads(
    app_client: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_path = _isolate(monkeypatch, tmp_path)
    env_path.write_text(
        "# keep me\nLLM_API_KEY=old-key-1234567890\nOTHER=1\n", encoding="utf-8"
    )
    monkeypatch.setattr(settings, "LLM_API_KEY", "old-key-1234567890")

    resp = app_client.put(
        "/api/v1/settings/llm",
        json={
            "llm_base_url": "https://api.deepseek.com",
            "llm_api_key": "",  # 留空沿用旧 Key
            "llm_model": "deepseek-chat",
            "embedding_base_url": "",
            "embedding_api_key": "",
            "embedding_model": "",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["configured"] is True
    assert data["llm"]["api_key_masked"] == "old****7890"
    assert "old-key-1234567890" not in resp.text

    text = env_path.read_text(encoding="utf-8")
    assert "# keep me" in text and "OTHER=1" in text
    assert "LLM_BASE_URL=https://api.deepseek.com" in text
    assert "LLM_API_KEY=old-key-1234567890" in text
    assert settings.LLM_BASE_URL == "https://api.deepseek.com"
    assert settings.LLM_MODEL == "deepseek-chat"
    assert llm._chat_client is None and llm._embedding_client is None


def test_put_rejects_missing_key(
    app_client: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate(monkeypatch, tmp_path)
    resp = app_client.put(
        "/api/v1/settings/llm",
        json={"llm_base_url": "https://api.deepseek.com", "llm_model": "deepseek-chat"},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == 1001


def test_put_rejects_bad_base_url(
    app_client: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate(monkeypatch, tmp_path)
    resp = app_client.put(
        "/api/v1/settings/llm",
        json={
            "llm_base_url": "api.deepseek.com",
            "llm_api_key": "sk-test-1234567890",
            "llm_model": "deepseek-chat",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == 1001


def test_test_connection_without_config_returns_errors(
    app_client: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate(monkeypatch, tmp_path)
    resp = app_client.post("/api/v1/settings/llm/test", json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["chat"]["ok"] is False
    assert data["embedding"]["ok"] is False

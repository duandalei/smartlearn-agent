"""AI Agent：12 个工具 + 注册表 + 执行器主循环。

- ``app.agent.tools``：12 个工具实现 + 横切校验设施；
- ``app.agent.registry``：TOOLS_SCHEMA（OpenAI function calling 格式）
  与 TOOL_MAP（名称 → 实现映射）；
- ``app.agent.core``：执行器主循环（流式六事件编排）。
"""

from __future__ import annotations

from app.agent.registry import TOOLS_SCHEMA, TOOL_MAP

__all__ = ["TOOLS_SCHEMA", "TOOL_MAP"]
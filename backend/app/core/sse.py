"""SSE 事件流格式化（chat / agent 两个流式端点共用）。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any


async def format_sse(
    event_stream: AsyncIterator[dict[str, Any]],
) -> AsyncIterator[str]:
    """把事件 dict 流格式化为 SSE 文本（``data: {JSON}\\n\\n``）。

    ``json.dumps(..., ensure_ascii=False)`` 保证中文原样传输。

    Args:
        event_stream: 事件字典异步迭代器。

    Yields:
        str: 可直接写入 ``text/event-stream`` 响应的文本帧。
    """
    async for event in event_stream:
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

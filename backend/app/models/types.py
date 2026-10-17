"""JSON 字段类型装饰器（PROJECT_CONTEXT 8.1 契约）。

DB 侧均以 ``TEXT`` 存储 JSON 字符串（写 ``json.dumps`` / 读 ``json.loads``），
Python 侧类型与 ``None`` 处理按字段语义分为两类：

- ``JSONListType``：Python 侧为 ``list[str]``；读到 ``NULL``/``None`` 统一
  返回 ``[]``（空数组是自然默认）。适用字段：``tasks.knowledge_points``、
  ``learning_records.knowledge_points``、``user_profiles.interest_directions``。
- ``JSONType``：Python 侧为 ``Any``；读到 ``NULL``/``None`` 原样返回
  ``None``，禁止强行返回 ``{}``。适用字段：``learning_goals.roadmap``、
  ``learning_reports.content``、``agent_messages.tool_calls``。
  （``roadmap = None`` 表示「从未拆解过」，是有语义的状态。）

层间禁令：services / schemas / api 对上述字段禁止再手动
``json.loads`` / ``json.dumps``。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator


class JSONListType(TypeDecorator[list[str]]):
    """JSON 字符串数组装饰器：Python ``list[str]`` ↔ DB ``TEXT``。

    读到 ``NULL`` / 空串 / 非法 JSON 时统一返回 ``[]``，保证属性值
    永远是可用数组（单条脏数据不致接口 500）。
    """

    impl = Text
    cache_ok = True

    def process_bind_param(
        self, value: list[str] | None, dialect: Any
    ) -> str | None:
        """Python -> DB：序列化为 JSON 字符串。

        Args:
            value: 待写入的字符串列表（None 原样存 NULL）。
            dialect: SQL 方言对象（未使用）。

        Returns:
            str | None: JSON 字符串或 None。
        """
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)

    def process_result_value(
        self, value: str | None, dialect: Any
    ) -> list[str]:
        """DB -> Python：反序列化为字符串列表。

        Args:
            value: 数据库中的 JSON 字符串（可能为 NULL / 脏数据）。
            dialect: SQL 方言对象（未使用）。

        Returns:
            list[str]: 解析结果；NULL / 非法 JSON 一律返回 ``[]``。
        """
        if value is None:
            return []
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        return []


class JSONType(TypeDecorator[Any]):
    """JSON 对象装饰器：Python ``Any``（dict / list[dict]）↔ DB ``TEXT``。

    读到 ``NULL`` 时**原样返回 None**（不返回 ``{}``）——
    ``roadmap=None`` 表示「从未拆解」，须与「拆解结果为空」可区分。
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        """Python -> DB：序列化为 JSON 字符串。

        Args:
            value: 待写入的任意 JSON 可序列化对象（None 存 NULL）。
            dialect: SQL 方言对象（未使用）。

        Returns:
            str | None: JSON 字符串或 None。
        """
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value: str | None, dialect: Any) -> Any:
        """DB -> Python：反序列化为 JSON 对象。

        Args:
            value: 数据库中的 JSON 字符串（可能为 NULL / 脏数据）。
            dialect: SQL 方言对象（未使用）。

        Returns:
            Any: 解析结果；NULL / 非法 JSON 返回 ``None``。
        """
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None
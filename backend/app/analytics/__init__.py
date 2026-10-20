"""学习分析引擎（P7，纯只读，禁止暴露 HTTP，禁止 import services）。

公开函数供 ``api/v1/dashboard.py`` 与 P8 agent 工具调用：
- ``get_overview``：overview 七指标
- ``get_trend``：趋势序列 + 斜率 + 风险预警
- ``get_mastery_list`` / ``get_weakness_top5``：掌握度列表 / 薄弱点 Top5
- ``generate_advice``：三规则今日建议（P8 Agent 接管点）
"""

from __future__ import annotations

from app.analytics.advice import generate_advice
from app.analytics.statistics import get_overview
from app.analytics.trend import get_trend
from app.analytics.weakness import get_mastery_list, get_weakness_top5

__all__ = [
    "get_overview",
    "get_trend",
    "get_mastery_list",
    "get_weakness_top5",
    "generate_advice",
]
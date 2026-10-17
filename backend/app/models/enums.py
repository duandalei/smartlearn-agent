"""枚举常量集中定义。

全部业务枚举统一收敛于此（禁止散落硬编码）。落库策略：
``Enum(native_enum=False, create_constraint=True, values_callable=...)``
生成 ``VARCHAR + CHECK`` 约束 —— SQLite 无原生 ENUM，DB 层仍可拒绝
超界值（如 ``status='not_started'`` 写入被拒绝）。

枚举取值锁定 PROJECT_CONTEXT 第 7 行裁决：
任务状态为 ``todo / in_progress / done / review``（不用
``not_started / reviewing``）。
"""

from __future__ import annotations

import enum


class GoalStatus(str, enum.Enum):
    """学习目标状态。"""

    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class PlanStatus(str, enum.Enum):
    """学习计划版本状态。"""

    ACTIVE = "active"
    ARCHIVED = "archived"


class PlanItemStatus(str, enum.Enum):
    """学习计划条目状态。"""

    PLANNED = "planned"
    DONE = "done"
    SKIPPED = "skipped"


class Priority(str, enum.Enum):
    """优先级（任务与计划条目共用）。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskStatus(str, enum.Enum):
    """学习任务状态（PROJECT_CONTEXT 锁定：todo/in_progress/done/review）。"""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    REVIEW = "review"


class TaskSource(str, enum.Enum):
    """学习任务来源：手工创建 / Agent 生成。"""

    MANUAL = "manual"
    AGENT = "agent"


class PlanSource(str, enum.Enum):
    """学习计划来源：Agent 生成 / 手工创建。"""

    AGENT = "agent"
    MANUAL = "manual"


class KnowledgeScope(str, enum.Enum):
    """知识库可见范围：个人库 / 公共库。"""

    PERSONAL = "personal"
    PUBLIC = "public"


class KnowledgeItemStatus(str, enum.Enum):
    """知识库文档处理状态。"""

    PENDING = "pending"
    PARSING = "parsing"
    INDEXED = "indexed"
    FAILED = "failed"


class KnowledgeSourceType(str, enum.Enum):
    """知识库文档来源类型。"""

    PDF = "pdf"
    MD = "md"
    TXT = "txt"
    DOCX = "docx"
    PPTX = "pptx"
    NOTE = "note"


class MasterySource(str, enum.Enum):
    """掌握度数据来源（quiz 为 V2 预留，P2 不写入）。"""

    SELF_REPORT = "self_report"
    RECORD = "record"
    QUIZ = "quiz"
    GOAL_BREAKDOWN = "goal_breakdown"
    AGENT = "agent"


class MessageRole(str, enum.Enum):
    """Agent 消息角色。"""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    SYSTEM = "system"


class ReportType(str, enum.Enum):
    """学习报告类型。"""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
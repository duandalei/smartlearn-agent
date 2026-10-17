"""ORM 模型聚合导出。

``import app.models`` 即可将全部 15 张表注册到同一 ``Base.metadata``，
``Base.metadata.create_all`` 一次建齐（init_db 依赖此行为）。
"""

from __future__ import annotations

from app.models.base import Base, CreatedAtMixin, TimestampMixin, sa_enum, utc_now
from app.models.enums import (
    GoalStatus,
    KnowledgeItemStatus,
    KnowledgeScope,
    KnowledgeSourceType,
    MasterySource,
    MessageRole,
    PlanItemStatus,
    PlanSource,
    PlanStatus,
    Priority,
    ReportType,
    TaskSource,
    TaskStatus,
)
from app.models.types import JSONListType, JSONType
from app.models.user import User, UserProfile
from app.models.goal import LearningGoal
from app.models.plan import LearningPlan, LearningPlanItem
from app.models.course import Course
from app.models.task import Task
from app.models.record import LearningRecord
from app.models.knowledge import KnowledgeChunk, KnowledgeItem
from app.models.mistake import Mistake
from app.models.mastery import KnowledgeMastery
from app.models.agent import AgentConversation, AgentMessage
from app.models.report import LearningReport

__all__ = [
    # 基础设施
    "Base",
    "CreatedAtMixin",
    "TimestampMixin",
    "sa_enum",
    "utc_now",
    "JSONListType",
    "JSONType",
    # 枚举
    "GoalStatus",
    "PlanStatus",
    "PlanItemStatus",
    "Priority",
    "TaskStatus",
    "TaskSource",
    "PlanSource",
    "KnowledgeScope",
    "KnowledgeItemStatus",
    "KnowledgeSourceType",
    "MasterySource",
    "MessageRole",
    "ReportType",
    # 15 张表模型
    "User",
    "UserProfile",
    "LearningGoal",
    "LearningPlan",
    "LearningPlanItem",
    "Course",
    "Task",
    "LearningRecord",
    "KnowledgeItem",
    "KnowledgeChunk",
    "Mistake",
    "KnowledgeMastery",
    "AgentConversation",
    "AgentMessage",
    "LearningReport",
]
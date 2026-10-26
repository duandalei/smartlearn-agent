"""Pydantic v2 出入参模型聚合导出。

P2 仅有出参（Out）模型；写接口入参（Create / Update）随 P3+ 在
对应领域文件中补充。
"""

from __future__ import annotations

from app.schemas.common import PaginationParams
from app.schemas.user import UserOut, UserProfileOut
from app.schemas.goal import GoalOut
from app.schemas.plan import PlanItemOut, PlanOut
from app.schemas.course import CourseOut
from app.schemas.task import TaskOut
from app.schemas.record import RecordOut
from app.schemas.knowledge import KnowledgeChunkOut, KnowledgeItemOut
from app.schemas.mistake import MistakeOut
from app.schemas.mastery import MasteryOut
from app.schemas.agent import ConversationOut, MessageOut
from app.schemas.report import ReportOut

__all__ = [
    "PaginationParams",
    "UserOut",
    "UserProfileOut",
    "GoalOut",
    "PlanOut",
    "PlanItemOut",
    "CourseOut",
    "TaskOut",
    "RecordOut",
    "KnowledgeItemOut",
    "KnowledgeChunkOut",
    "MistakeOut",
    "MasteryOut",
    "ConversationOut",
    "MessageOut",
    "ReportOut",
]
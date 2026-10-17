"""v1 路由聚合。

本模块统一汇总 v1 版本的路由：
- ``health_router``：健康检查，**不带**版本前缀（PROJECT_CONTEXT 5.1），
  由 main.py 直接挂载到 ``/health``。
- ``api_router``：业务路由，由 main.py 以 ``/api/v1`` 前缀挂载。

P3 起全量端点鉴权（PROJECT_CONTEXT 收编裁决）：除 ``/health``、
``/api/v1/auth/register``、``/api/v1/auth/login`` 三个公开端点外，
所有 ``/api/v1`` 端点均依赖 ``get_current_user`` 并按当前用户隔离数据。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.profile import router as profile_router
from app.api.v1.users import router as users_router
from app.api.v1.user_profiles import router as user_profiles_router
from app.api.v1.goals import router as goals_router
from app.api.v1.plans import router as plans_router
from app.api.v1.learning_plan_items import router as learning_plan_items_router
from app.api.v1.courses import router as courses_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.records import router as records_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.knowledge_chunks import router as knowledge_chunks_router
from app.api.v1.mistakes import router as mistakes_router
from app.api.v1.knowledge_mastery import router as knowledge_mastery_router
from app.api.v1.agent import router as agent_router
from app.api.v1.agent_messages import router as agent_messages_router
from app.api.v1.reports import router as reports_router

# 业务路由（挂载前缀 /api/v1）。
api_router: APIRouter = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(profile_router)
api_router.include_router(users_router)
api_router.include_router(user_profiles_router)
api_router.include_router(goals_router)
api_router.include_router(plans_router)
api_router.include_router(learning_plan_items_router)
api_router.include_router(courses_router)
api_router.include_router(tasks_router)
api_router.include_router(records_router)
api_router.include_router(knowledge_router)
api_router.include_router(knowledge_chunks_router)
api_router.include_router(mistakes_router)
api_router.include_router(knowledge_mastery_router)
api_router.include_router(agent_router)
api_router.include_router(agent_messages_router)
api_router.include_router(reports_router)

# 健康检查路由（不带前缀，直接挂 /health）。
__all__ = ["api_router", "health_router"]
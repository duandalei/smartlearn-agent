"""Dashboard 路由（P7，需登录，按当前用户隔离数据）。

分层契约：本层只做「参数校验 + 鉴权注入 + 调用 analytics + 统一响应
包装」；全部统计逻辑收敛在 ``app/analytics/``（design D1）。overview
请求前一行触发每日衰减检查（``run_daily_decay_check`` 内部自吞异常，
失败不影响 GET 返回）。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.analytics import (
    generate_advice,
    get_mastery_list,
    get_overview,
    get_trend,
    get_weakness_top5,
)
from app.api.deps import get_current_user, get_db
from app.core.response import success
from app.models.user import User
from app.services.mastery import run_daily_decay_check

router: APIRouter = APIRouter(prefix="/dashboard", tags=["学习分析看板"])


@router.get("/overview", summary="指标总览（四指标卡 + 三副文案）")
def dashboard_overview(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Dashboard 顶部指标卡数据（七指标）。

    请求前触发每日掌握度衰减检查（每用户每天最多一次，进程内字典
    判重；失败 try/except 隔离，本接口仍 200 返回未重算旧数据）。
    """
    run_daily_decay_check(db, current_user.id)
    return success(data=get_overview(db, current_user.id))


@router.get("/trend", summary="学习时间趋势（序列 + 斜率 + 风险预警）")
def dashboard_trend(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    days: Annotated[
        int, Query(ge=1, le=365, description="统计天数，1~365")
    ] = 30,
) -> dict[str, Any]:
    """近 N 天按北京自然日聚合补零的学习时长序列（可直接喂 ECharts）。

    同源返回最小二乘斜率 ``slope`` 与风险预警 ``risk_alert``（未触发
    为 null；数据源为最近 5 自然日，与 days 参数解耦）。
    """
    return success(data=get_trend(db, current_user.id, days))


@router.get("/mastery", summary="知识掌握情况（升序列表，排除零分待学点）")
def dashboard_mastery(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """掌握度横向柱状图数据源（按 mastery_score 升序）。"""
    return success(data=get_mastery_list(db, current_user.id))


@router.get("/weakness", summary="薄弱知识点 Top5（含建议文案）")
def dashboard_weakness(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """薄弱知识点 Top5：掌握度升序 + 近 30 天出现频次降序。"""
    return success(data=get_weakness_top5(db, current_user.id))


@router.get("/advice", summary="今日学习建议（基于规则，后续由 Agent 接管）")
def dashboard_advice(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """三规则今日建议（overdue / weakness / streak），命中几条返回几条。"""
    return success(data=generate_advice(db, current_user.id))
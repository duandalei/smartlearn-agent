"""数据库初始化与幂等种子数据。

唯一建表与种子入口（验收 D8：``scripts/init_data.py`` 本阶段不存在，
P13 才实现演示数据重置）。

执行方式::

    cd backend && python -m app.db.init_db

行为：
1. ``Base.metadata.create_all`` 一次建齐 15 张表（幂等：已存在跳过）。
2. 以「demo 用户存在」为唯一幂等开关：存在则跳过全部插入，
   重复执行不报错、不重复插入、退出码恒为 0。
3. 种子全部在单一事务内写入，任一步异常整体回滚（库中无半成品，
   退出码 1）。
4. 全部日期相对执行时刻动态生成（today 基准），任意时间验收均成立；
   所有时间字段统一 UTC。
5. 埋点说明：最近 5 天学习时长严格递减（175→140→105→70→40），
   用于 P7 学习风险预警演示；任务含 3 个已逾期（状态未完成），
   用于 P12 计划调整演示。
6. ``mastery_score`` 为直接给定的演示值，不做聚合计算
   （聚合公式属 P7 analytics 阶段）。
"""

from __future__ import annotations

import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models import (
    AgentConversation,
    AgentMessage,
    Course,
    KnowledgeChunk,
    KnowledgeItem,
    KnowledgeMastery,
    LearningGoal,
    LearningPlan,
    LearningPlanItem,
    LearningRecord,
    LearningReport,
    Mistake,
    Task,
    User,
    UserProfile,
)
from app.models.base import Base, utc_now
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

# ---------------------------------------------------------------------------
# 学习记录种子素材：四大学科 × 8 组真实学习内容（content / achievement /
# problems / knowledge_points / mastery_level），按天轮转取用。
# ---------------------------------------------------------------------------
_ML_DAYS: list[tuple[str, str, str, list[str], int]] = [
    (
        "学习线性回归的最小二乘法推导，并用 NumPy 复现了闭式解",
        "推导了正规方程，验证了与梯度下降结果一致",
        "对多重共线性导致解不稳定的原因还不太清楚",
        ["线性回归", "最小二乘"],
        55,
    ),
    (
        "学习逻辑回归的 sigmoid 函数与决策边界，手推了交叉熵损失对权重的梯度",
        "理清了逻辑回归与线性回归损失函数的区别",
        "对极大似然估计的推导过程还不太理解",
        ["逻辑回归", "交叉熵"],
        60,
    ),
    (
        "精读《机器学习》第 6 章 SVM，整理间隔、对偶与 KKT 条件笔记",
        "画出了软间隔 SVM 的结构示意，对偶问题推导过了一遍",
        "KKT 条件在非线性可分场景下的几何意义还需再消化",
        ["支持向量机", "KKT条件"],
        50,
    ),
    (
        "学习决策树 ID3 与 C4.5 的信息增益准则，用 sklearn 跑了演示数据",
        "理解了信息增益偏向多值属性的原因及增益率修正",
        "预剪枝与后剪枝的取舍标准还比较模糊",
        ["决策树", "信息增益"],
        65,
    ),
    (
        "学习 K-Means 聚类算法，手写了聚类中心迭代过程",
        "掌握了 K 值选择的肘部法则",
        "对初始中心敏感导致局部最优的问题没有完全想清楚",
        ["K-Means", "聚类"],
        60,
    ),
    (
        "学习模型评估指标：查准率、查全率与 F1，整理混淆矩阵笔记",
        "能根据场景选择合适的评价指标",
        "ROC 曲线与 AUC 的关系还要再推导一遍",
        ["模型评估", "混淆矩阵"],
        70,
    ),
    (
        "学习 Transformer 的 Self-Attention 机制，跟着论文推了 QKV 计算流程",
        "理解了注意力权重的物理含义",
        "多头注意力 concat 后的维度变换还有点绕",
        ["Transformer", "Self-Attention"],
        55,
    ),
    (
        "复习朴素贝叶斯与常见概率分布，整理公式卡片",
        "把先验、后验与似然的关系理顺了",
        "连续特征下的高斯朴素贝叶斯推导还不熟练",
        ["朴素贝叶斯", "概率分布"],
        50,
    ),
]

_PY_DAYS: list[tuple[str, str, str, list[str], int]] = [
    (
        "复习 Python 列表推导式与生成器表达式，对比了两者内存占用",
        "理解了惰性求值的适用场景",
        "嵌套推导式的可读性边界还把握不好",
        ["列表推导式", "生成器"],
        85,
    ),
    (
        "学习 Python 装饰器原理，手写了带参数的计时装饰器",
        "弄清了闭包变量捕获的规则",
        "functools.wraps 的作用原理还说不完整",
        ["装饰器", "闭包"],
        75,
    ),
    (
        "学习 NumPy 广播机制与向量化运算，对比了循环实现的性能差异",
        "掌握了 shape 对齐规则",
        "高维数组广播出错时排查还比较慢",
        ["NumPy", "广播机制"],
        80,
    ),
    (
        "学习 Pandas 的 groupby 聚合与缺失值处理",
        "能独立完成小数据集的清洗流程",
        "多级索引的切片语法还得查文档",
        ["Pandas", "数据清洗"],
        70,
    ),
    (
        "学习 Python 异常处理与上下文管理器，重构了成绩统计脚本",
        "掌握了 with 语句的协议原理",
        "自定义异常的继承层次设计还没形成习惯",
        ["异常处理", "上下文管理器"],
        75,
    ),
    (
        "学习 Python 类型注解与 dataclass，给旧脚本补全了类型",
        "理解了 Optional 与 Union 的用法",
        "泛型在函数签名中的写法还不熟",
        ["类型注解", "dataclass"],
        80,
    ),
    (
        "学习正则表达式常用语法，写了日志解析小练习",
        "掌握了分组与贪婪匹配的区别",
        "复杂回溯场景的正则还会写错",
        ["正则表达式"],
        65,
    ),
    (
        "学习文件与目录操作，整理 os.path 与 pathlib 对照表",
        "把旧脚本的路径处理全部改写成了 pathlib",
        "递归遍历时符号链接的处理还不了解",
        ["文件处理", "pathlib"],
        85,
    ),
]

_MATH_DAYS: list[tuple[str, str, str, list[str], int]] = [
    (
        "复习矩阵乘法与转置性质，手算了 3×3 例题",
        "熟练掌握了分块矩阵乘法",
        "分块矩阵求逆的公式记不牢",
        ["线性代数", "矩阵运算"],
        60,
    ),
    (
        "学习特征值与特征向量，推导了 2×2 矩阵的特征多项式",
        "理解了几何重数与代数重数的区别",
        "相似对角化的充要条件还会搞混",
        ["线性代数", "特征值"],
        55,
    ),
    (
        "学习条件概率与全概率公式，做了 10 道练习题",
        "全概率公式的「划分」条件能准确识别",
        "贝叶斯公式的方向性有时还会搞反",
        ["概率论", "全概率公式"],
        45,
    ),
    (
        "学习常见分布：二项、泊松与正态，整理了期望方差速查表",
        "掌握了泊松近似二项的条件",
        "正态分布标准化在积分中的应用还不熟练",
        ["概率论", "常见分布"],
        50,
    ),
    (
        "学习梯度与 Hessian 矩阵，推导了多元函数极值条件",
        "理解了正定 Hessian 与极小值的联系",
        "约束优化的拉格朗日乘子法推导还不熟",
        ["微积分", "梯度"],
        50,
    ),
    (
        "复习行列式性质与克拉默法则，整理了错题",
        "掌握了按行展开的递归计算方法",
        "分块行列式的性质容易与分块矩阵混淆",
        ["线性代数", "行列式"],
        55,
    ),
    (
        "学习期望、方差与协方差的性质，证明了几条常用结论",
        "理解了不相关与独立的区别",
        "协方差矩阵在 PCA 中的作用还没完全串起来",
        ["概率论", "协方差"],
        50,
    ),
    (
        "学习 SVD 分解的几何意义与计算步骤",
        "能手算小矩阵的 SVD",
        "SVD 与特征值分解的联系还需巩固",
        ["线性代数", "SVD"],
        45,
    ),
]

_ALGO_DAYS: list[tuple[str, str, str, list[str], int]] = [
    (
        "复习二叉树的前中后序遍历，迭代版全部手写通过",
        "掌握了栈模拟递归的通用套路",
        "Morris 遍历的线索修改时机还没理解透",
        ["二叉树", "遍历"],
        85,
    ),
    (
        "学习动态规划入门：爬楼梯与打家劫舍，整理了状态转移表",
        "理解了重叠子问题与最优子结构",
        "状态定义的技巧还需要多做题积累",
        ["动态规划"],
        65,
    ),
    (
        "学习哈希表原理与冲突处理，手写了链地址法实现",
        "掌握了负载因子与扩容策略",
        "开放定址法删除时的墓碑问题还没动手实现过",
        ["哈希表"],
        75,
    ),
    (
        "学习图的最短路算法 Dijkstra，用优先队列优化了实现",
        "理解了贪心选择性质的证明思路",
        "负权边场景下算法为什么失效说不清楚",
        ["图算法", "Dijkstra"],
        70,
    ),
    (
        "刷 LeetCode 拓扑排序题目，复习了课程表 I/II",
        "掌握了入度表加队列的标准写法",
        "DFS 判环的染色法还会写错边界",
        ["拓扑排序"],
        70,
    ),
    (
        "学习双向链表实现 LRU 缓存，通过了 LeetCode 146",
        "掌握了哈希加链表的组合套路",
        "虚拟头尾节点简化边界处理的手法还不熟练",
        ["哈希表", "双向链表"],
        75,
    ),
    (
        "学习回溯算法：全排列与子集，画了决策树",
        "理解了剪枝的两种常用思路",
        "去重逻辑的排序前置条件容易漏",
        ["回溯算法"],
        65,
    ),
    (
        "复习排序算法：快排与归并的递归实现，对比了稳定性",
        "掌握了两种算法的时间复杂度推导",
        "快排最坏情况的避免策略只知道随机化",
        ["排序算法"],
        80,
    ),
]

# 学科轮转顺序（与 course 映射）：机器学习 / Python / 数学 / 算法。
_SUBJECT_CYCLE: list[tuple[str, Course | None, list[tuple[str, str, str, list[str], int]]]] = []


# ---------------------------------------------------------------------------
# 前 25 天学习时长（today-29 … today-5）：45~165 分钟预设波动序列；
# 最近 5 天（today-4 … today）固定 175/140/105/70/40 严格递减（风险预警埋点）。
# ---------------------------------------------------------------------------
_PRESET_DURATIONS: list[int] = [
    90, 120, 60, 150, 100, 45, 135, 80, 160, 110,
    70, 125, 95, 140, 55, 105, 165, 85, 130, 75,
    115, 150, 65, 100, 120,
]
_RECENT_DURATIONS: list[int] = [175, 140, 105, 70, 40]


def _seed_users(db: Session, now: datetime) -> User:
    """写入演示用户与学习档案。

    Args:
        db: 数据库会话。
        now: 执行时刻（UTC）。

    Returns:
        User: 已添加的用户对象（未 flush）。
    """
    user = User(
        username="demo",
        email="demo@example.com",
        hashed_password=hash_password("123456"),
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        UserProfile(
            user_id=user.id,
            name="李明轩",
            school="徐州工程学院",
            major="计算机科学与技术",
            grade="大二",
            current_goal_type="考研",
            interest_directions=["机器学习", "深度学习", "大模型应用"],
            daily_study_minutes=120,
        )
    )
    return user


def _seed_courses(db: Session, user: User) -> dict[str, Course]:
    """写入 3 门课程。

    Args:
        db: 数据库会话。
        user: 演示用户。

    Returns:
        dict[str, Course]: 键为 c1/c2/c3 的课程映射。
    """
    courses = {
        "c1": Course(
            user_id=user.id,
            name="机器学习",
            description="覆盖监督学习、无监督学习与神经网络基础，"
            "教材为周志华《机器学习》（西瓜书）",
            teacher="张伟明",
            semester="2025-2026-1",
        ),
        "c2": Course(
            user_id=user.id,
            name="Python 程序设计",
            description="从语法基础到面向对象、常用标准库与数据分析入门",
            teacher="李红梅",
            semester="2025-2026-1",
        ),
        "c3": Course(
            user_id=user.id,
            name="数据结构与算法分析",
            description="线性表、树、图与经典算法，配套在线刷题训练",
            teacher="王建国",
            semester="2025-2026-1",
        ),
    }
    db.add_all(courses.values())
    db.flush()
    return courses


def _build_roadmap() -> dict[str, Any]:
    """构造目标 1 的 4 层知识树（AI 拆解结果）。

    Returns:
        dict[str, Any]: roadmap JSON 结构。
    """
    return {
        "name": "机器学习",
        "children": [
            {
                "name": "数学基础",
                "children": [
                    {
                        "name": "线性代数",
                        "children": [{"name": "矩阵分解"}, {"name": "特征值与特征向量"}],
                    },
                    {
                        "name": "概率论",
                        "children": [{"name": "贝叶斯定理"}, {"name": "常见分布"}],
                    },
                ],
            },
            {
                "name": "监督学习",
                "children": [
                    {"name": "线性回归"},
                    {"name": "逻辑回归"},
                    {"name": "决策树"},
                    {
                        "name": "支持向量机",
                        "children": [{"name": "硬间隔与软间隔"}, {"name": "对偶问题与KKT"}],
                    },
                    {"name": "神经网络基础"},
                ],
            },
            {
                "name": "无监督学习",
                "children": [{"name": "K-Means聚类"}, {"name": "PCA降维"}],
            },
            {
                "name": "模型评估",
                "children": [{"name": "交叉验证"}, {"name": "评价指标"}],
            },
        ],
    }


def _seed_goals(
    db: Session, user: User, today: date, now: datetime
) -> dict[str, LearningGoal]:
    """写入 5 个学习目标（active×3 / completed×1 / archived×1）。

    Args:
        db: 数据库会话。
        user: 演示用户。
        today: 执行日（UTC 日期）。
        now: 执行时刻（UTC）。

    Returns:
        dict[str, LearningGoal]: 键为 g1/g3 的目标映射（供任务引用）。
    """
    goals = [
        LearningGoal(
            user_id=user.id,
            title="6个月掌握机器学习核心算法",
            goal_type="技能提升",
            description="系统学习数学基础、监督学习与无监督学习，"
            "能独立完成经典算法的推导与实现，期末课程目标 90 分",
            start_date=today - timedelta(days=40),
            end_date=today + timedelta(days=140),
            status=GoalStatus.ACTIVE,
            roadmap=_build_roadmap(),
            roadmap_updated_at=now - timedelta(days=40),
        ),
        LearningGoal(
            user_id=user.id,
            title="期末数据结构考到 90 分以上",
            goal_type="期末备考",
            description="重点攻克树、图与动态规划三大板块，刷完课后习题",
            start_date=today - timedelta(days=20),
            end_date=today + timedelta(days=60),
            status=GoalStatus.ACTIVE,
            roadmap=None,
            roadmap_updated_at=None,
        ),
        LearningGoal(
            user_id=user.id,
            title="寒假刷完 LeetCode 热题 200",
            goal_type="刷题训练",
            description="每天 3 题，覆盖数组、链表、树、图与动态规划",
            start_date=today - timedelta(days=10),
            end_date=today + timedelta(days=90),
            status=GoalStatus.ACTIVE,
            roadmap=None,
            roadmap_updated_at=None,
        ),
        LearningGoal(
            user_id=user.id,
            title="通过大学英语四级",
            goal_type="考试",
            description="背完高频词汇，听力与阅读专项训练",
            start_date=today - timedelta(days=200),
            end_date=today - timedelta(days=80),
            status=GoalStatus.COMPLETED,
            roadmap=None,
            roadmap_updated_at=None,
        ),
        LearningGoal(
            user_id=user.id,
            title="备战蓝桥杯省赛",
            goal_type="竞赛",
            description="主攻动态规划与搜索，刷历年真题",
            start_date=today - timedelta(days=150),
            end_date=today - timedelta(days=60),
            status=GoalStatus.ARCHIVED,
            roadmap=None,
            roadmap_updated_at=None,
        ),
    ]
    db.add_all(goals)
    db.flush()
    return {"g1": goals[0], "g3": goals[2]}


def _seed_tasks(
    db: Session,
    user: User,
    goals: dict[str, LearningGoal],
    courses: dict[str, Course],
    today: date,
    now: datetime,
) -> dict[str, Task]:
    """写入 20 个学习任务（todo 7 / in_progress 4 / done 7 / review 2）。

    含 3 个已逾期未完成任务（#2/-1、#18/-3、#20/-5），用于 P12
    计划调整演示。

    Args:
        db: 数据库会话。
        user: 演示用户。
        goals: 目标映射。
        courses: 课程映射。
        today: 执行日（UTC 日期）。
        now: 执行时刻（UTC）。

    Returns:
        dict[str, Task]: 键为 t1/t2/t3/t9/t18 的任务映射（供计划条目与
        学习记录引用）。
    """
    status_map = {
        "todo": TaskStatus.TODO,
        "in_progress": TaskStatus.IN_PROGRESS,
        "done": TaskStatus.DONE,
        "review": TaskStatus.REVIEW,
    }
    priority_map = {
        "low": Priority.LOW,
        "medium": Priority.MEDIUM,
        "high": Priority.HIGH,
    }
    source_map = {"manual": TaskSource.MANUAL, "agent": TaskSource.AGENT}
    # (编号, 标题, 状态, 优先级, 来源, goal, course, 截止偏移天数, 知识点,
    #  预计分钟, 实际分钟, 描述)
    rows: list[tuple[str, str, str, str, str, str | None, str | None,
                     int, list[str], int, int | None, str]] = [
        ("t1", "学习 Transformer 的 Self-Attention 机制", "in_progress", "high",
         "agent", "g1", "c1", 2, ["Transformer", "Self-Attention", "QKV"], 120,
         None, "精读 Attention Is All You Need 第 3 节，手推缩放点积注意力公式"),
        ("t2", "推导 SVM 的对偶问题与 KKT 条件", "in_progress", "medium",
         "manual", "g1", "c1", -1, ["支持向量机", "对偶问题", "KKT条件"], 150,
         None, "对照西瓜书第 6 章完成拉格朗日对偶推导，整理 KKT 条件笔记"),
        ("t3", "实现逻辑回归并用 Iris 数据集验证", "todo", "medium",
         "manual", "g1", "c1", 4, ["逻辑回归", "梯度下降"], 180, None,
         "从零实现 sigmoid 与交叉熵梯度下降，在 Iris 上跑通并画决策边界"),
        ("t4", "精读《机器学习》第 9 章聚类并做笔记", "todo", "low",
         "manual", "g1", "c1", 9, ["K-Means", "无监督学习"], 90, None,
         "整理 K-Means / DBSCAN / AGNES 三类算法的对比笔记"),
        ("t5", "完成机器学习实验二：决策树剪枝", "review", "medium",
         "manual", "g1", "c1", -2, ["决策树", "剪枝"], 120, None,
         "实现预剪枝与后剪枝对比实验，报告待老师批改"),
        ("t6", "整理机器学习错题：混淆矩阵与查准率", "todo", "low",
         "manual", "g1", "c1", 12, ["模型评估", "混淆矩阵"], 60, None,
         "把三次小测里评估指标相关的错题录入错题本并重做"),
        ("t7", "学习 PCA 降维的数学推导", "done", "high",
         "manual", "g1", "c1", -5, ["PCA", "特征值分解"], 150, 130,
         "推导协方差矩阵特征分解形式的 PCA，用 NumPy 验证"),
        ("t8", "LeetCode 198 打家劫舍（动态规划）", "todo", "medium",
         "manual", "g3", "c3", 3, ["动态规划"], 45, None,
         "滚动数组优化空间到 O(1)"),
        ("t9", "LeetCode 146 LRU 缓存机制", "in_progress", "high",
         "agent", "g3", "c3", 0, ["哈希表", "双向链表"], 90, None,
         "哈希表 + 双向链表实现 O(1) 读写，通过全部用例"),
        ("t10", "复习二叉树的四种遍历（递归与迭代）", "done", "low",
         "manual", "g3", "c3", -7, ["二叉树", "遍历"], 60, 50,
         "递归与迭代版全部手写通过，整理了栈模拟模板"),
        ("t11", "完成 Dijkstra 最短路算法手推与代码实现", "done", "medium",
         "manual", "g3", "c3", 6, ["图算法", "Dijkstra"], 120, 160,
         "手推优先队列版流程表，代码通过洛谷模板题"),
        ("t12", "整理图论错题：拓扑排序应用场景", "review", "medium",
         "manual", "g3", "c3", -4, ["拓扑排序"], 60, None,
         "归纳拓扑排序判环与依赖排序两类题型"),
        ("t13", "LeetCode 300 最长递增子序列", "done", "low",
         "manual", "g3", "c3", 10, ["动态规划", "子序列"], 45, 45,
         "掌握 O(n²) 与贪心+二分两种解法"),
        ("t14", "复习 Python 装饰器与闭包原理", "done", "medium",
         "manual", None, "c2", -6, ["装饰器", "闭包"], 60, 55,
         "手写带参数的计时装饰器，理解闭包变量捕获"),
        ("t15", "学习 NumPy 向量化运算并对比循环性能", "done", "medium",
         "agent", None, "c2", -8, ["NumPy", "向量化"], 90, 70,
         "用 %timeit 对比向量化与循环，整理广播规则笔记"),
        ("t16", "编写课程作业：学生成绩统计脚本", "todo", "high",
         "manual", None, "c2", 1, ["文件处理", "字典"], 120, None,
         "读取 CSV 成绩单，输出各科统计与排名，本周五前提交"),
        ("t17", "学习 Pandas 数据清洗常用方法", "in_progress", "low",
         "agent", None, "c2", 14, ["Pandas", "数据清洗"], 90, None,
         "练习 groupby 聚合、缺失值填充与去重"),
        ("t18", "重做概率论错题：全概率公式与贝叶斯", "todo", "high",
         "manual", "g1", None, -3, ["概率论", "贝叶斯定理"], 90, None,
         "重做 10 道全概率与贝叶斯错题，写出每步依据"),
        ("t19", "推导矩阵特征值分解并手算 2×2 例题", "done", "medium",
         "manual", "g1", None, -10, ["线性代数", "特征值分解"], 90, 65,
         "完成特征多项式推导与 3 道手算例题"),
        ("t20", "背诵英语四级高频词汇 List 12", "todo", "low",
         "manual", None, None, -5, ["英语词汇"], 30, None,
         "四级虽已通过，继续保持每日词汇量练习"),
    ]
    tasks: dict[str, Task] = {}
    for key, title, status, priority, source, goal_key, course_key, dl_off, kps, est, actual, desc in rows:
        deadline = now + timedelta(days=dl_off)
        completed_at = None
        if status == "done":
            if dl_off > 0:
                completed_at = now - timedelta(days=1, hours=3)
            else:
                completed_at = deadline - timedelta(hours=2)
        task = Task(
            user_id=user.id,
            goal_id=goals[goal_key].id if goal_key else None,
            course_id=courses[course_key].id if course_key else None,
            title=title,
            description=desc,
            knowledge_points=kps,
            priority=priority_map[priority],
            estimated_minutes=est,
            actual_minutes=actual,
            deadline=deadline,
            scheduled_date=None,
            status=status_map[status],
            source=source_map[source],
            completed_at=completed_at,
        )
        tasks[key] = task
        db.add(task)
    db.flush()
    return tasks


def _seed_plan(
    db: Session,
    user: User,
    goals: dict[str, LearningGoal],
    tasks: dict[str, Task],
    today: date,
) -> None:
    """写入本周学习计划（v1，active，agent 生成）与 8 条计划条目。

    条目状态随执行日自洽：plan_date 早于 today 的置 done，否则 planned。

    Args:
        db: 数据库会话。
        user: 演示用户。
        goals: 目标映射。
        tasks: 任务映射。
        today: 执行日（UTC 日期）。
    """
    monday = today - timedelta(days=today.weekday())
    plan = LearningPlan(
        user_id=user.id,
        goal_id=goals["g1"].id,
        title="机器学习第 7 周学习计划",
        version=1,
        status=PlanStatus.ACTIVE,
        parent_plan_id=None,
        source=PlanSource.AGENT,
        adjust_reason=None,
        start_date=monday,
        end_date=monday + timedelta(days=6),
    )
    db.add(plan)
    db.flush()

    # (相对周一偏移, 开始, 结束, 主题, 任务, 预计分钟, 优先级)
    items: list[tuple[int, time, time, str, str | None, int | None, str]] = [
        (0, time(19, 0), time(20, 30), "线性代数：特征值与特征向量",
         None, 90, "medium"),
        (1, time(19, 0), time(20, 30), "机器学习：SVM 对偶问题与 KKT 推导",
         "t2", 90, "high"),
        (2, time(19, 30), time(21, 0), "Python：迭代器与生成器",
         None, 90, "low"),
        (3, time(19, 0), time(20, 0), "机器学习：Transformer Self-Attention 精读",
         "t1", 60, "high"),
        (4, time(19, 0), time(19, 45), "数据结构：哈希表与 LRU 缓存",
         "t9", 45, "medium"),
        (4, time(20, 0), time(21, 0), "错题复盘：概率论错题重做",
         "t18", 60, "low"),
        (5, time(10, 0), time(12, 0), "机器学习：逻辑回归实验（Iris 数据集）",
         "t3", 120, "medium"),
        (6, time(20, 0), time(20, 30), "休息与本周复盘",
         None, None, "low"),
    ]
    priority_map = {"low": Priority.LOW, "medium": Priority.MEDIUM, "high": Priority.HIGH}
    for day_off, start, end, topic, task_key, minutes, priority in items:
        plan_date = monday + timedelta(days=day_off)
        db.add(
            LearningPlanItem(
                plan_id=plan.id,
                plan_date=plan_date,
                start_time=start,
                end_time=end,
                topic=topic,
                task_id=tasks[task_key].id if task_key else None,
                estimated_minutes=minutes,
                priority=priority_map[priority],
                status=(
                    PlanItemStatus.DONE if plan_date < today else PlanItemStatus.PLANNED
                ),
            )
        )
    # 5 个被计划条目引用的任务补写 scheduled_date（Agent 生成计划时写入）。
    scheduled_map = {"t2": 1, "t1": 3, "t9": 4, "t18": 4, "t3": 5}
    for task_key, day_off in scheduled_map.items():
        tasks[task_key].scheduled_date = monday + timedelta(days=day_off)


def _seed_records(
    db: Session,
    user: User,
    courses: dict[str, Course],
    tasks: dict[str, Task],
    today: date,
) -> None:
    """写入 30 天学习记录（today-29 … today 逐日，学科四轮转）。

    近 10 天与当天学科匹配的 in_progress 任务建立关联。

    Args:
        db: 数据库会话。
        user: 演示用户。
        courses: 课程映射。
        tasks: 任务映射。
        today: 执行日（UTC 日期）。
    """
    subjects: list[tuple[str, Course | None, Any, str | None]] = [
        ("机器学习", courses["c1"], _ML_DAYS, "t1"),
        ("Python", courses["c2"], _PY_DAYS, "t17"),
        ("数学", None, _MATH_DAYS, "t2"),
        ("算法", courses["c3"], _ALGO_DAYS, "t9"),
    ]
    for i in range(30):
        study_date = today - timedelta(days=29 - i)
        _, course, day_pool, task_key = subjects[i % 4]
        content, achievement, problems, kps, mastery = day_pool[i // 4]
        duration = _PRESET_DURATIONS[i] if i < 25 else _RECENT_DURATIONS[i - 25]
        task_id = tasks[task_key].id if i >= 20 else None
        db.add(
            LearningRecord(
                user_id=user.id,
                task_id=task_id,
                course_id=course.id if course else None,
                content=content,
                duration_minutes=duration,
                achievement=achievement,
                problems=problems,
                knowledge_points=kps,
                mastery_level=mastery,
                study_date=study_date,
            )
        )


def _seed_knowledge(db: Session) -> None:
    """写入 4 篇公共知识库文档元数据与 4 个分块。

    P2 只落库元数据与预置分块文本，不调用 Embedding（embedding_id
    恒为 NULL，文件本体由 RAG / P13 阶段放置）。

    Args:
        db: 数据库会话。
    """
    items: list[tuple[str, str, str, int]] = [
        ("机器学习核心概念速览", "md", "data/public_kb/ml_basics.md", 2),
        ("线性代数要点笔记：特征值与矩阵分解", "md",
         "data/public_kb/linear_algebra_notes.md", 1),
        ("概率论与数理统计公式表", "md",
         "data/public_kb/probability_formulas.md", 1),
        ("数据结构常见考点速查", "md", "data/public_kb/ds_cheatsheet.md", 0),
    ]
    type_map = {
        "pdf": KnowledgeSourceType.PDF,
        "md": KnowledgeSourceType.MD,
        "txt": KnowledgeSourceType.TXT,
    }
    created: list[KnowledgeItem] = []
    for title, source_type, file_path, chunk_count in items:
        item = KnowledgeItem(
            user_id=None,
            title=title,
            source_type=type_map[source_type],
            file_path=file_path,
            scope=KnowledgeScope.PUBLIC,
            status=KnowledgeItemStatus.INDEXED,
            error_msg=None,
            chunk_count=chunk_count,
        )
        created.append(item)
        db.add(item)
    db.flush()

    chunks: list[tuple[int, str]] = [
        (0, "监督学习：从带标签数据中学习输入到输出的映射，回归输出连续值、"
            "分类输出离散类别；训练集拟合与测试集泛化的权衡（偏差-方差分解）"
            "是模型选择的核心依据。"),
        (0, "无监督学习：从无标签数据中发现结构，聚类（K-Means、层次聚类）"
            "寻找自然分组，降维（PCA、SVD）保留主要信息压缩维度；模型评估"
            "常用交叉验证与查准率 / 查全率 / F1 等指标。"),
        (1, "特征值与特征向量：Ax = λx 的非零解 x 称为特征向量；2×2 矩阵"
            "特征多项式 λ² − tr(A)λ + det(A) = 0；实对称矩阵必可正交对角化，"
            "SVD 分解 A = UΣVᵀ 将任意矩阵分解为旋转-缩放-旋转三步。"),
        (2, "贝叶斯公式 P(A|B) = P(B|A)P(A)/P(B) 用于「由果溯因」；常见分布"
            "期望方差速记：二项 B(n,p) 期望 np、方差 np(1−p)；泊松 P(λ) 期望"
            "与方差均为 λ；正态 N(μ,σ²) 标准化 Z = (X−μ)/σ。"),
    ]
    for item_idx, content in chunks:
        db.add(
            KnowledgeChunk(
                item_id=created[item_idx].id,
                user_id=None,
                chunk_index=0 if item_idx != 0 else chunks.index(
                    (item_idx, content)
                ) % 2,
                content=content,
                embedding_id=None,
            )
        )


def _seed_mistakes(db: Session, user: User, courses: dict[str, Course]) -> None:
    """写入 8 道错题（分散在概率论 / 线性代数 / 机器学习 / 数据结构）。

    Args:
        db: 数据库会话。
        user: 演示用户。
        courses: 课程映射。
    """
    rows: list[tuple[str | None, str, str, str, str, str]] = [
        (
            None, "概率论·贝叶斯定理",
            "某疾病在人群中的发病率为 0.1%。某检测方法对患者的灵敏度为 99%"
            "（患病者检出阳性概率 0.99），对健康者的误报率为 5%（健康者检出"
            "阳性概率 0.05）。某人检测结果为阳性，求其真正患病的概率。",
            "99%",
            "约 1.96%。P(患病|阳性) = 0.001×0.99 / (0.001×0.99 + 0.999×0.05) ≈ 0.0196",
            "混淆了 P(阳性|患病) 与 P(患病|阳性) 的方向，未使用贝叶斯公式；"
            "忽略了健康人群基数远大于患者，导致误报人数占阳性的大多数。",
        ),
        (
            None, "概率论·全概率公式",
            "袋中有 3 个红球 2 个白球，不放回地取两次，每次取一球。"
            "求第二次取到红球的概率。",
            "1/2",
            "3/5。由全概率公式 P = 3/5×2/4 + 2/5×3/4 = 3/5",
            "分情况计算时条件概率用错；忽略了「第二次取红球」的概率与第一次"
            "结果无关（对称性），可直接得 3/5。",
        ),
        (
            None, "线性代数·特征值",
            "求矩阵 [[2,1],[1,2]] 的特征值与对应的特征向量。",
            "特征值为 1 和 2",
            "特征值为 1 和 3；λ=1 对应特征向量 k(1,−1)ᵀ，λ=3 对应 k(1,1)ᵀ（k≠0）",
            "特征多项式 det(A−λI) = (2−λ)²−1 = (λ−1)(λ−3)，展开时漏掉了 −1 项，"
            "把特征多项式当成了 (2−λ)²。",
        ),
        (
            None, "线性代数·行列式",
            "设 A 为 3 阶方阵且 |A| = 2，求 |2A⁻¹|。",
            "2",
            "4。|2A⁻¹| = 2³·|A|⁻¹ = 8×(1/2) = 4",
            "漏掉了数乘的 n 次幂性质 |kA| = kⁿ|A|（n 为阶数）。",
        ),
        (
            "c1", "机器学习·逻辑回归",
            "逻辑回归模型对某样本输出的预测值为 0.7，能否直接将其理解为"
            "「该样本属于正类的真实概率为 70%」？为什么？",
            "可以，sigmoid 函数输出本来就是概率。",
            "不能。逻辑回归输出是未经校准的置信度，仅在样本均衡、模型指定"
            "正确等条件下才近似概率；需经校准（如 Platt scaling）后才可作为概率使用。",
            "缺少概率校准（calibration）的概念，把模型输出无条件等同于真实后验概率。",
        ),
        (
            "c1", "机器学习·SVM",
            "在软间隔 SVM 中，把惩罚参数 C 减小，模型更倾向于欠拟合还是"
            "过拟合？为什么？",
            "更容易过拟合。",
            "更容易欠拟合。C 越小对间隔违例的惩罚越轻，等价于正则化越强，"
            "决策边界越平滑，容忍更多训练误差。",
            "混淆了 C 与正则化强度的方向；C 小 ⇔ 正则化强 ⇔ 边界更平滑 ⇔ 偏向欠拟合。",
        ),
        (
            "c3", "数据结构·二叉树遍历",
            "已知二叉树的先序遍历序列为 ABDECF，中序遍历序列为 DBEAFC，"
            "求后序遍历序列。",
            "DEBCFA",
            "DEBFCA",
            "由先序确定根 A，中序划分左子树 DBE 与右子树 FC；递归重建时"
            "右子树（F 为根、C 为 F 的孩子）的后序还原顺序出错，C 应在 F 之后输出。",
        ),
        (
            "c3", "数据结构·哈希表",
            "开放定址法（如线性探查）实现的哈希表中，删除元素为什么不能"
            "直接把槽位置空？应如何处理？",
            "直接置空就行，下次查找不到自然返回不存在。",
            "直接置空会截断后续元素的探查链，导致同义词查找失败；应采用墓碑"
            "（DELETED）标记删除，或删除后对后续元素重新散列。",
            "未理解探查链的连续性——槽位置空后探查序列中断，其后因冲突后移的"
            "同义词将永远查不到。",
        ),
    ]
    for course_key, kp, question, user_answer, correct_answer, analysis in rows:
        db.add(
            Mistake(
                user_id=user.id,
                course_id=courses[course_key].id if course_key else None,
                knowledge_point=kp.split("·")[0],
                question=question,
                user_answer=user_answer,
                correct_answer=correct_answer,
                analysis=analysis,
            )
        )


def _seed_mastery(db: Session, user: User, now: datetime) -> None:
    """写入 10 个知识点掌握度（直接给定演示值，不聚合）。

    updated_at 错开，其中「英语阅读」超 30 天未更新，供 P7 时间衰减
    规则演示。

    Args:
        db: 数据库会话。
        user: 演示用户。
        now: 执行时刻（UTC）。
    """
    rows: list[tuple[str, float, str, int]] = [
        ("概率论", 40.0, "record", 5),
        ("线性代数", 50.0, "record", 3),
        ("机器学习", 60.0, "goal_breakdown", 12),
        ("数据结构", 80.0, "record", 8),
        ("Python", 90.0, "self_report", 2),
        ("深度学习", 30.0, "goal_breakdown", 35),
        ("动态规划", 45.0, "record", 6),
        ("SQL", 55.0, "self_report", 20),
        ("计算机网络", 70.0, "self_report", 15),
        ("英语阅读", 50.0, "record", 45),
    ]
    source_map = {
        "record": MasterySource.RECORD,
        "self_report": MasterySource.SELF_REPORT,
        "goal_breakdown": MasterySource.GOAL_BREAKDOWN,
    }
    for kp, score, source, updated_days_ago in rows:
        db.add(
            KnowledgeMastery(
                user_id=user.id,
                knowledge_point=kp,
                mastery_score=score,
                source=source_map[source],
                updated_at=now - timedelta(days=updated_days_ago),
            )
        )


def _seed_agent(db: Session, user: User, now: datetime) -> None:
    """写入 1 个 Agent 会话与 6 条消息（含工具调用链）。

    Args:
        db: 数据库会话。
        user: 演示用户。
        now: 执行时刻（UTC）。
    """
    conversation = AgentConversation(
        user_id=user.id,
        title="最近学习状态分析",
    )
    db.add(conversation)
    db.flush()

    tool_calls_payload: list[dict[str, Any]] = [
        {
            "id": "call_001",
            "type": "function",
            "function": {
                "name": "get_learning_statistics",
                "arguments": "{\"days\": 7}",
            },
        }
    ]
    messages: list[tuple[int, MessageRole, str, str | None,
                         list[dict[str, Any]] | None, str | None]] = [
        (25, MessageRole.USER, "最近学习状态怎么样？帮我分析一下",
         None, None, None),
        (22, MessageRole.ASSISTANT,
         "我先查询一下你最近 7 天的学习统计数据。",
         None, tool_calls_payload, None),
        (21, MessageRole.TOOL,
         "{\"total_learning_minutes\": 530, \"active_days\": 7, "
         "\"tasks_completed\": 4, \"avg_daily_minutes\": 75.7, "
         "\"top_subject\": \"机器学习\"}",
         "get_learning_statistics", None, "call_001"),
        (18, MessageRole.ASSISTANT,
         "根据最近 7 天的数据：你累计学习 530 分钟，保持全周活跃，完成了 4 个"
         "任务，整体状态稳定。不过学习时长从周初的 175 分钟逐步下降到 40 分钟，"
         "连续 5 天递减；同时你有 3 个任务已逾期（SVM 推导、概率论错题、四级"
         "词汇），建议优先补上概率论错题任务，它与你的薄弱知识点（概率论 40 分）"
         "直接相关。",
         None, None, None),
        (13, MessageRole.USER, "好的，那帮我看看哪些知识点比较薄弱？",
         None, None, None),
        (10, MessageRole.ASSISTANT,
         "从掌握度数据看：深度学习（30 分）和概率论（40 分）是最薄弱的两个"
         "知识点，线性代数（50 分）也需要加强。建议：1）本周安排 2 次概率论"
         "错题重练，优先攻克贝叶斯定理与全概率公式；2）线性代数结合特征值分解"
         "的笔记复习，为 PCA 和 SVD 打基础；3）深度学习暂保持基础概念学习，"
         "待机器学习基础（当前 60 分）巩固后再深入。",
         None, None, None),
    ]
    for minutes_ago, role, content, tool_name, tool_calls, tool_call_id in messages:
        db.add(
            AgentMessage(
                conversation_id=conversation.id,
                role=role,
                content=content,
                tool_name=tool_name,
                tool_calls=tool_calls,
                tool_call_id=tool_call_id,
                created_at=now - timedelta(minutes=minutes_ago),
            )
        )


def _seed_report(db: Session, user: User, today: date) -> None:
    """写入上周学习周报。

    Args:
        db: 数据库会话。
        user: 演示用户。
        today: 执行日（UTC 日期）。
    """
    monday = today - timedelta(days=today.weekday())
    db.add(
        LearningReport(
            user_id=user.id,
            report_type=ReportType.WEEKLY,
            period_start=monday - timedelta(days=7),
            period_end=monday - timedelta(days=1),
            summary="上周累计学习 12.6 小时，完成 6 个学习任务；机器学习进度"
            "正常，概率论基础薄弱，建议本周增加 2 次错题重练。",
            content={
                "total_learning_minutes": 756,
                "active_days": 6,
                "tasks_completed": 6,
                "tasks_overdue": 1,
                "avg_daily_minutes": 126,
                "knowledge_points_covered": [
                    "Transformer", "Self-Attention", "逻辑回归",
                    "动态规划", "贝叶斯定理", "线性代数",
                ],
                "weak_points": ["概率论", "深度学习"],
                "suggestions": [
                    "本周增加 2 次概率论错题重练，重点覆盖贝叶斯定理与全概率公式",
                    "保持每日至少 1 小时机器学习学习时长，优先完成已逾期的 SVM 推导任务",
                ],
            },
        )
    )


def _seed_all(db: Session) -> None:
    """在单一事务内写入全部种子数据（按 FK 依赖排序）。

    Args:
        db: 数据库会话（调用方负责 commit / rollback）。
    """
    now = utc_now()
    today = now.date()

    user = _seed_users(db, now)
    courses = _seed_courses(db, user)
    goals = _seed_goals(db, user, today, now)
    tasks = _seed_tasks(db, user, goals, courses, today, now)
    _seed_plan(db, user, goals, tasks, today)
    _seed_records(db, user, courses, tasks, today)
    _seed_knowledge(db)
    _seed_mistakes(db, user, courses)
    _seed_mastery(db, user, now)
    _seed_agent(db, user, now)
    _seed_report(db, user, today)


def _print_summary() -> None:
    """打印 15 张表的记录数摘要，供与验收 B 组核对。"""
    tables: list[tuple[str, type]] = [
        ("users", User),
        ("user_profiles", UserProfile),
        ("learning_goals", LearningGoal),
        ("learning_plans", LearningPlan),
        ("learning_plan_items", LearningPlanItem),
        ("courses", Course),
        ("tasks", Task),
        ("learning_records", LearningRecord),
        ("knowledge_items", KnowledgeItem),
        ("knowledge_chunks", KnowledgeChunk),
        ("mistakes", Mistake),
        ("knowledge_mastery", KnowledgeMastery),
        ("agent_conversations", AgentConversation),
        ("agent_messages", AgentMessage),
        ("learning_reports", LearningReport),
    ]
    with SessionLocal() as db:
        counts = {name: (db.scalar(select(func.count()).select_from(model)) or 0)
                  for name, model in tables}
    print("========== SmartLearn 数据库初始化完成 ==========")
    for name, count in counts.items():
        print(f"{name:<22}{count:>6}")
    print("=================================================")
    print("演示账号: demo / 123456（仅供开发演示，请勿用于生产环境）")


def init_db() -> None:
    """建表并写入幂等种子数据。

    幂等策略：``create_all`` 自身幂等（已存在表跳过）；种子以
    「demo 用户存在」为唯一开关，存在则跳过全部插入。
    """
    db_url = settings.DATABASE_URL
    if db_url.startswith("sqlite:///"):
        Path(db_url.removeprefix("sqlite:///")).parent.mkdir(
            parents=True, exist_ok=True
        )
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.username == "demo"))
        if existing is not None:
            print("种子数据已存在，跳过全部插入。")
        else:
            try:
                _seed_all(db)
                db.commit()
            except Exception as exc:  # noqa: BLE001 整体回滚并退出
                db.rollback()
                print(f"种子数据写入失败，已整体回滚: {exc}", file=sys.stderr)
                raise SystemExit(1) from exc
    _print_summary()


if __name__ == "__main__":
    init_db()
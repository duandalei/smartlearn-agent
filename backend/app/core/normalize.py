"""知识点名称规范化（全项目唯一实现，P6 交付后缺陷修复）。

**双管线语义**（spec 裁定③④，禁止混用）：

- 数组路径（records / tasks 的 ``knowledge_points``）：
  strip → 空白判错（ValueError → 全局处理器转 422/1001「知识点不能
  为空白」）→ 按 strip 后值去重保序 → 长度校验（strip 后 1~100，
  裁定②）。四步顺序为用户裁定，不得调换。
- 树路径（goal.py 拆解产出的 roadmap 叶子名）：仅 strip + strip 后
  判空——纯空白节点名抛 ValueError，由调用方转 ``_ParseFailed`` 走
  「重试一次 → 仍失败转 3000/502」既有兜底；**不去重、不合并同名
  节点**（合并会丢失知识树结构，同名叶子写 knowledge_mastery 时由
  集合天然去重）、不判长度（树深度与规模由 ``_truncate_tree`` 既有
  截断机制约束）。

两条管线共用本模块的 strip/判空核心（``normalize_knowledge_point``）。

**校验落库同源**（本缺陷教训，硬性约束）：规范化函数的返回值是唯一
落库来源——原实现「校验用 ``len(item.strip())``、落库返回原值数组、
按原值判重」导致 ``" Transformer"`` 与 ``"Transformer"`` 分裂为两个
掌握度行；禁止任何「校验用 strip 值、落库用原值」或「按原值判重」
的双口径路径。

**分层定位**（PROJECT_CONTEXT §4）：core 层为全局基础设施，可被任意
层引用；本模块零项目内依赖（仅标准库），schemas 与 services 引用均
属合法方向，不产生分层倒置。

**横切契约**：P8 Agent 创建任务、P7 Dashboard、V2 错题录入等未来
入口写入知识点名称时，必须经由本模块（数组路径）或其同语义约束，
禁止另写第二套清洗实现。
"""

from __future__ import annotations

from typing import Any, Final

#: 知识点名称最大长度（按 strip 后值判，裁定②：校验对象须与落库对象同形态）。
MAX_KNOWLEDGE_POINT_LENGTH: Final[int] = 100

#: 空白知识点（strip 后为空串）的拦截提示文案（数组路径 422/1001）。
EMPTY_KP_MESSAGE: Final[str] = "知识点不能为空白"

#: 超长知识点的拦截提示文案（数组路径 422/1001）。
LENGTH_KP_MESSAGE: Final[str] = "知识点名称长度须为 1~100 字符"


def normalize_knowledge_point(name: str) -> str:
    """单个知识点名称清洗（双管线共用的公共核心）。

    ``strip`` 首尾空白后为空串则抛 ``ValueError``（数组路径经全局
    处理器转 422/1001，树路径由调用方转 ``_ParseFailed`` 重试兜底）；
    **超长不在此函数判**——数组管线在去重后统一判长度（见
    :func:`normalize_knowledge_points` 第 ③ 步），树管线不判长度。

    Args:
        name: 原始知识点名称。

    Returns:
        str: strip 后的名称（调用方的唯一落库来源）。

    Raises:
        ValueError: strip 后为空串（纯空白 / 空字符串）。
    """
    result = name.strip()
    if not result:
        raise ValueError(EMPTY_KP_MESSAGE)
    return result


def normalize_knowledge_points(v: list[str] | None) -> list[str] | None:
    """知识点数组规范化（数组路径，四步固定顺序，用户裁定不得调换）。

    处理顺序：① 逐元素 strip + 空白判错（ValueError）→ ② 按 strip
    后值 ``dict.fromkeys`` 去重保序 → ③ 逐元素长度校验（strip 后值
    1~100，超长抛 ValueError）。**返回值即唯一落库来源**，禁止调用
    方二次取原始数组（校验落库同源，本缺陷根因的硬性禁止项）。

    Args:
        v: 知识点数组。``None`` 表示未提交（部分更新语义，原样透传，
            交由调用方处理）；``[]`` 合法放行（表达「清空 / 不挂知识点」）。

    Returns:
        list[str] | None: 清洗去重后的新数组；``None`` 原样透传。

    Raises:
        ValueError: 任一元素 strip 后为空串，或 strip 后长度超 100。
    """
    if v is None:
        return v
    cleaned = [normalize_knowledge_point(item) for item in v]
    deduped = list(dict.fromkeys(cleaned))
    for item in deduped:
        if len(item) > MAX_KNOWLEDGE_POINT_LENGTH:
            raise ValueError(LENGTH_KP_MESSAGE)
    return deduped


def clean_roadmap_tree(tree: dict) -> dict:
    """知识树节点名清洗（树路径：仅 strip + 判空，保留结构）。

    DFS 递归遍历（含根节点与全部 children 层级），每个节点的
    ``name`` 调 :func:`normalize_knowledge_point`——纯空白节点名抛
    ``ValueError``，由调用方（``services/goal.py`` 的 ``_call_and_parse``）
    转 ``_ParseFailed`` 走既有重试兜底（spec 裁定④ 4b：``RoadmapNode``
    的 ``min_length=1`` 对纯空白 ``" "`` 无效，必须 strip 后显式判空）。

    ``name`` / ``children`` 之外的结构字段原样保留。**不去重、不合并
    同名节点、不判长度**（树管线语义：合并丢知识树结构；同名叶子写
    knowledge_mastery 时由集合天然去重——树保留与掌握度收敛并存）。

    清洗时机（spec 裁定④ 4a）：在 ``_parse_roadmap`` 之后、
    ``_truncate_tree`` 之前调用——roadmap 落库与 ``_collect_leaves``
    取叶子天然共用同一批清洗后的名字，两处同源由构造保证。

    Args:
        tree: 解析成功的知识树节点 dict（``{"name": str, "children":
            list}`` 递归结构）。

    Returns:
        dict: 清洗后的**新**树（不就地修改输入，纯函数语义）。

    Raises:
        ValueError: 任一节点（含根）name strip 后为空串。
    """
    return _clean_node(tree)


def _clean_node(node: Any) -> Any:
    """递归清洗单个节点（``clean_roadmap_tree`` 的实现细节）。

    Args:
        node: 节点 dict；非 dict 值原样返回（结构字段透传）。

    Returns:
        Any: 清洗后的新节点（输入未被修改）。

    Raises:
        ValueError: 节点 name strip 后为空串。
    """
    if not isinstance(node, dict):
        return node
    cleaned: dict = {}
    for key, value in node.items():
        if key == "name":
            cleaned[key] = normalize_knowledge_point(value)
        elif key == "children":
            cleaned[key] = [_clean_node(child) for child in value]
        else:
            cleaned[key] = value
    return cleaned
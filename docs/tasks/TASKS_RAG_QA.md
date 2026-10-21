# RAG AI 学习问答（rag_qa）编码任务规划

> feature: `rag_qa` ｜ 阶段：编码任务规划（spec-task-agent 产出）
> 上游输入：`docs/specs/SPEC_RAG_QA.md`（R3 定稿，14 项裁决 + D1–D9 验收标准）、`docs/designs/DESIGN_RAG_QA.md`（R3 定稿，设计决策 D1–D10 + 三项开放决策点已裁定）、`docs/PROJECT_CONTEXT.md`（§6.16 qa_history 九字段 / §2 RAG_MIN_SCORE / §7.1–7.2 路由与接口均已同步）
> 生成日期：2026-10-21 ｜ 状态：待用户确认
> 落盘路径说明：遵循 R3 裁定②（从本阶段起规格与设计统一放 `docs/specs/` 与 `docs/designs/`）的对偶扩展——`SPEC_` ↔ `DESIGN_` ↔ `TASKS_`、`specs/` ↔ `designs/` ↔ `tasks/`，本文件落 `docs/tasks/TASKS_RAG_QA.md`；历史 8 阶段 tasks 仍在 `.codeartsdoer/specs/<feature>/tasks.md`（被 gitignore），P13 打包时统一复制补齐，本阶段不动历史文档
> 已裁决事项继承（不再重开）：spec 12 项裁决 + R3 三项裁定（① done.data 四字段含 intent / ② 文档路径 / ③ 落库失败 done+null）、design 决策 D1–D10（services 编排+rag 纯函数分层 / SSE 格式化在 api 层 / chat 路径 mode="online" 且 intent 透出 / 落库失败不抛穿 / ChatMessage 重复声明 / 无心跳行 / QA_TOP_K=5 / 前端 401 复用导出 / intent 落库 / chat 独立聊天模板）；`services/llm.py` 的 `chat_stream` **零改动直接复用**（P4 已交付全部流式能力）；本清单不重开任何设计决策
>
> **决策编号读法**：本文「决策 D3」指 design.md 2.8.2 设计决策；「验收 D3」指 spec 8.1 验收标准；「裁定①/③」指 R3 用户裁定。

---

## 0. 任务总览与依赖关系

**分组结构**（10 组，共 30 个子任务）：

```
组1 数据模型与启动迁移 ─┬─→ 组2 rag纯函数 ──→ 组3 services编排 ──→ 组4 API路由 ──┐
                       │                                          ↑(运行依赖)     ├─→ 组9 后端测试 ──→ 组10 构建与验证收尾
                       └─→ 组5 scope扩展兼容 ──────────────────────┘              │
                              （与组2/3/4 文件零交集，可完全并行）                  │
                                             组6 前端类型/API ──→ 组7 AskView组件群 ──→ 组8 路由与菜单 ─┘
                                             （前端仅依赖组4 的接口契约，可与组5/组9 并行）
```

**关键路径**：1.2 → 1.3 → 2.1~2.3 → 3.1 → 3.2 → 4.1/4.2 → 9.3 → 10.2（表就绪 → 纯函数 → 编排 → 端点 → SSE e2e → 全量验证）。

**可并行标注**：
- 组 1 内部：1.1 / 1.2 / 1.4 相互独立可并行（1.3 依赖 1.2 的 ORM 定义）
- 组 2 与组 5 完全并行（`rag/qa.py` 新文件 vs `vectorstore.py`/`knowledge.py` 改动，零交集）
- 组 3 编写仅依赖组 2 与 `search_knowledge` 的**目标签名**（契约已在 design 2.2.2-(3) 定稿）；其运行与测试依赖组 5 落地（scope 参数透传）
- 组 6–8（前端）与组 9（后端测试）可并行：前端仅依赖接口契约（design 2.2.2），不依赖测试通过
- 组 7 内部：7.1 / 7.2 / 7.3 三子组件在类型就绪后可并行，7.4 视图收口

**实现前置约定**（全文适用，各任务不再重复）：
1. pytest 与测试基建 P8 已交付（`backend/tests/conftest.py` 含 `app_client`/`user_a`/`user_b`/`_isolated_runtime` autouse 与 `upload_document` helper、`offline_embedding` fixture），本阶段直接复用，无需新建基础设施
2. 沙箱验证环境网络全禁（外网禁、IPv4 回环拦）：**真实 LLM 调用一律 mock**（`app.services.llm.chat_stream` 注入假流）；检索走真实路径（本地兜底 embedding 真算 + 真 Chroma 写入）；真实流式节奏与浏览器端验收归 10.5 用户本机清单
3. `.env.example` 已有 `RAG_MIN_SCORE=0.55` 模板行（R2 已同步），本阶段不改该文件；`core/config.py` 字段读取属本阶段新增
4. 每个后端模块的 docstring 须回链 design.md 章节号；代码命名英文 snake_case，注释中文（契约 §8.4）
5. 前端组件统一 `<script setup lang="ts">`，类型集中在 `src/types/`，字段保持后端 snake_case（契约 §8.3）

**明确不改动清单（防越界，design 1.1.3-D）**：

| 文件 | 不改动理由 |
|------|-----------|
| `backend/app/services/llm.py` | `chat_stream` 已完整交付本阶段所需全部流式能力（90s 超时、SDK 重试、创建段异常包装、finally 释放连接）；任务书「流式生成需新增能力」经实测不成立，**零改动直接复用** |
| `backend/app/api/v1/knowledge.py` | P7 端点 `POST /knowledge/search` 对外契约不变（不传 scope → 服务层默认 all → 行为与扩展前一致；响应新增可选字段属裁决 #3 允许） |
| `backend/app/rag/embedding.py` / `loader.py` / `splitter.py` | P8 纯能力层，本阶段只消费 `embed_query_with_fallback` |
| `backend/app/main.py` | chat_router 经 `api/v1/__init__.py` 聚合挂载；qa_history 建表经 `ensure_schema_upgrades` 追加条目（调用点已存在于 main.py:35） |
| `backend/.env.example` | RAG_MIN_SCORE 模板行 R2 已写入 |
| `frontend/src/api/knowledge.ts` | P8 前端接口封装不动（`KnowledgeSearchHit` 类型扩展在 `types/index.ts`） |
| `frontend/src/components/knowledge/SearchPanel.vue` | 不消费新字段、不参与跳转定位 |
| `backend/app/agent/`（尚不存在） | Agent 属 P11；兼容性由 scope 默认值静态保证 |

---

## 1. 后端数据模型与启动迁移

**写作说明**：本组为全部后续任务的数据基础（配置阈值 + ORM 九字段 + 建表双路径 + 出入参模型），必须最先完成。字段口径唯一来源：契约 §6.16 与 design 2.3.2。

### 1.1 配置层新增 RAG_MIN_SCORE 阈值字段（默认 0.55，空值回退）

- [ ] **要点**：
  - `Settings` 新增 `RAG_MIN_SCORE: float = Field(default=0.55, ge=0.0, le=1.0)`——合法区间 [0,1]，默认 0.55（裁决 #12 定稿值）
  - 配套 before 模式 `field_validator`：环境变量为空字符串或 None 时回退 0.55（对齐契约 §2「留空回退默认」——pydantic-settings 直接映射 float 会在空串时校验失败，必须前置转换）
  - 模块 docstring 注明取值依据摘要（领域内实测 0.572–0.733 / 领域外 0.412–0.533，0.55 挡住领域外最高分并保住领域内最低分）与回链 design 1.1.2 / 裁决 #12
- **涉及文件**：修改 `backend/app/core/config.py`（不改：`backend/.env.example`)
- **完成判定**：`cd backend && python -m py_compile app/core/config.py` 通过；`python -c "from app.core.config import settings; assert 0.0 <= settings.RAG_MIN_SCORE <= 1.0"` 通过；空串回退与非法值拒绝的断言由 9.1 单测固化
- **依赖**：无
- **决策锚点**：裁决 #12（T=0.55）；契约 §2

### 1.2 新增 EmbedMode 枚举与 QAHistory ORM 模型（九字段）

- [ ] **要点**：
  - `models/enums.py` 新增 `EmbedMode(str, Enum)`：`ONLINE = "online"` / `OFFLINE = "offline"`（ORM 落库列专用；`rag/embedding.py` 的 `Literal` 类型**保持不变**——两套类型各司其职，成员值字符串一致、边界处以字符串值自然衔接，design 2.3.2 双轨说明）
  - 新建 `models/qa.py` 定义 `QAHistory`（`__tablename__ = "qa_history"`），九字段逐字对齐契约 §6.16：`id`（INTEGER 自增主键）、`user_id`（FK `users.id`，`ondelete="CASCADE"`）、`question`（TEXT 非空，长度约束在入参 schema 层把关）、`answer`（TEXT 非空）、`sources`（`JSONType`，非空——无据与 chat 落 `[]` 而非 NULL）、`mode`（`sa_enum(EmbedMode)`，非空，CHECK 约束拒收 online/offline 之外的值）、`is_grounded`（BOOLEAN 非空）、**`intent`（VARCHAR(20) 非空，取值 knowledge|chat，普通 VARCHAR 不设 CHECK——与 `learning_reports.report_type` 等既有轻量枚举列惯例对齐，决策 D9）**、`created_at`（`CreatedAtMixin`，UTC 非空）
  - 复合索引 `(user_id, created_at)`——精确覆盖历史查询「过滤 + 倒序 + 分页」三要素（design 2.3.2 索引论证），不另设单列 user_id 索引
  - 检索档位 scope **不落库**（裁决 #5 字段清单不含）；使用 `Mapped[T] + mapped_column` 声明式风格与全库 16 张表同构
  - docstring 回链 design 2.3.2 与契约 §6.16，并注明「mode 落库是某次问答的检索模式快照，与 P8『文档状态不落 mode』惯例对象不同、不冲突」（design 2.3.1-4）
- **涉及文件**：新增 `backend/app/models/qa.py`；修改 `backend/app/models/enums.py`（不改：`backend/app/rag/embedding.py`)
- **完成判定**：`cd backend && python -m py_compile app/models/qa.py app/models/enums.py` 通过；字段名与 §6.16 表逐字一致（九字段核对）
- **依赖**：无（可与 1.1 / 1.4 并行）
- **决策锚点**：决策 D9（intent 列）；裁决 #5（qa_history 独立表）；裁定①

### 1.3 qa_history 表注册与启动迁移（存量库重启即建）

- [ ] **要点**：
  - `models/__init__.py` 导出 `QAHistory` 并加入 `__all__`（自动注册 `Base.metadata`，表清单 15 → 16）
  - `db/migrate.py` 的 `ensure_schema_upgrades` 追加「建表」条目：`Base.metadata.create_all(engine, tables=[QAHistory.__table__])`（幂等，已存在跳过）——对齐 P8「重启即升级」惯例；**关键缺口**（design 1.2.4）：main.py 不调 create_all、仅注册不追加条目则存量库（demo 用户已存在、永不重跑种子）重启后 qa_history 不存在，首个 done 落库即 500——该理由写入模块 docstring
  - `db/init_db.py` 的 `_print_summary` 摘要表清单与打印说明 15 → 16（建表能力本身由既有 create_all 覆盖）
  - `main.py` 零改动（调用点已存在于 main.py:35）
- **涉及文件**：修改 `backend/app/models/__init__.py`、`backend/app/db/migrate.py`、`backend/app/db/init_db.py`（不改：`backend/app/main.py`)
- **完成判定**：`cd backend && python -m py_compile app/models/__init__.py app/db/migrate.py app/db/init_db.py` 通过；对存量 `data/smartlearn.db` 重启一次后 `python -c "import sqlite3; c=sqlite3.connect('../data/smartlearn.db'); print([r[1] for r in c.execute('PRAGMA table_info(qa_history)')])"` 输出九列名；二次启动幂等（无重复建表报错、启动日志无 ERROR）；全新库经 init_db 建齐 16 张表
- **依赖**：1.2
- **决策锚点**：design 1.2.4（存量库升级路径）

### 1.4 新增 chat 出入参 schema（ChatQAIn / QaSourceItem / ChatHistoryOut）

- [ ] **要点**：
  - `ChatQAIn`：`question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]`（去首尾空白后非空，与检索入参上限一致，spec 6.1）+ `scope: Literal["personal", "public", "all"] = "all"`（小写字面量、大小写敏感）；`model_config = ConfigDict(extra="forbid")` 对齐全仓入参惯例
  - `QaSourceItem`：六字段——`item_id: int | None`、`chunk_index: int | None`（可空为防御性设计：极端脏 metadata 下历史接口不 500，前端跳转判空降级，design 2.3.2）、`content: str`、`source_title: str`、`score: float`、`scope: str`
  - `ChatHistoryOut`：`{id, question, answer, sources: list[QaSourceItem], mode, is_grounded, intent, created_at}`——含 `intent`（历史回放双信号样式判定的前置，裁定①）
  - 越界输入（空 question / 501 字符 / `scope="foo"`）经全局处理器自动 422 + 1001 中文提示（spec 5.1.1 规则 6），schema 层零额外代码
  - docstring 回链 design 2.2.2-(1)(2)
- **涉及文件**：新增 `backend/app/schemas/chat.py`
- **完成判定**：`cd backend && python -m py_compile app/schemas/chat.py` 通过；`python -c "from app.schemas.chat import ChatQAIn; ChatQAIn(question='  ')"` 抛 ValidationError；`ChatQAIn(question='测试')` 的 scope 默认值为 `"all"`
- **依赖**：无（可与 1.1–1.3 并行；字段契约对齐 design 2.2.2）
- **决策锚点**：spec 6.1/6.2/6.3；裁定①（ChatHistoryOut 含 intent）

---

## 2. rag 问答纯函数层（app/rag/qa.py）

**写作说明**：单文件三函数 + 三模板常量，纯函数、无 IO 无事务、不 import services/api（分层铁律：rag 包单向被依赖；`ChatMessage` 在本模块重复声明——决策 D5）。全部签名与模板全文以 design 2.4.1–2.4.3 为准。

### 2.1 classify_intent 意图判断（预编译正则规则集，宁缺毋滥）

- [ ] **要点**：
  - 新建 `app/rag/qa.py`；模块级常量 `_SMALL_TALK_PATTERNS` 四类**预编译**正则（design 2.4.1 表格逐字）：
    - 纯问候：`^(你好|您好|嗨|哈喽|hi|hello|hey|早上好|上午好|中午好|下午好|晚上好|早安|晚安)[!！。.~～呀啊哦哈]*$`
    - 感谢/告别：`^(谢谢|多谢|感谢|辛苦了|thanks|thank you|thx|再见|拜拜|bye|goodbye)[!！。.~～]*$`
    - 助手身份元问题（非锚定 search）：`你是谁|你叫什么|你是什么(模型|AI|机器人|东西)|介绍一下你自己|你能(做|帮)什么`
    - 系统元问题：`(这个|本)?(系统|网站|平台|软件|应用)是(什么|干嘛|做什么)(的)?`
  - `classify_intent(question: str) -> Literal["chat", "knowledge"]`：`text = question.strip().lower()` 归一后任一模式 `search` 命中返回 `"chat"`，否则 `"knowledge"`
  - 返回值三处消费（裁定①）：qa_stream 跳检依据 / done 事件 `data.intent` / qa_history `intent` 落库
  - **可关停设计**（裁决 #9 兜底）：纯字符串操作无外部依赖不抛异常；调用侧 try/except 包裹，任何异常一律返回 `"knowledge"`（退化为始终检索）；清空规则数组即恢复全量检索
  - 宁缺毋滥原则写入 docstring：误判知识型为闲聊的代价是丢失检索（有据变无据），误判闲聊为知识型只是一次多余检索（无害），故只收录高置信模式
- **涉及文件**：新增 `backend/app/rag/qa.py`
- **完成判定**：`cd backend && python -m py_compile app/rag/qa.py` 通过；`python -c "from app.rag.qa import classify_intent; assert classify_intent('你好')=='chat' and classify_intent('什么是 Transformer')=='knowledge'"` 通过；完整样例矩阵由 9.1 固化
- **依赖**：无（可与组 1 并行）
- **决策锚点**：裁决 #9；裁定①

### 2.2 ChatMessage 类型声明与阈值过滤函数

- [ ] **要点**：
  - 本模块**重复声明** `ChatMessage` TypedDict（`role: str` / `content: str` 两字段），不 `from app.services.llm import ChatMessage`——保持 rag 层零 services import 的静态可验证性（决策 D5；`services/chat.py` 消费时二者结构兼容）
  - `filter_sources_by_threshold(results: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]`：`filtered = [r for r in results if r["score"] >= settings.RAG_MIN_SCORE]`，返回 `(filtered, len(filtered) > 0)`
  - 与 spec 5.3.1 规则 1 的等价性（filtered 非空 ⇔ max(score) ≥ T）及逐条过滤的额外收益（有据场景下低分噪声条目也被挡在 sources 之外，使引用编号与有效片段严格一一对应）写入 docstring（design 2.4.2 论证）
  - 阈值读取点**集中**于本函数（`settings.RAG_MIN_SCORE` 单一读取点），qa_stream 不重复读配置——保证 D9 验收「临时调低/复原」只经 `.env` + 重启生效
  - 本函数只在 `intent=knowledge` 路径被调用（chat 路径跳过检索与过滤）；is_grounded 与 intent 的分工说明写入 docstring（裁定①核心）
- **涉及文件**：修改 `backend/app/rag/qa.py`
- **完成判定**：`python -m py_compile app/rag/qa.py` 通过；边界行为由 9.1 固化（0.55 边界 / 空输入 / monkeypatch 0.30）
- **依赖**：2.1（同文件）、1.1（读 RAG_MIN_SCORE）
- **决策锚点**：决策 D5；裁决 #12

### 2.3 Prompt 三模板常量与 build_qa_messages 组装

- [ ] **要点**：
  - 三个模块常量（**全文逐字以 design 2.4.3 为准**，模板集中后端单一位置、禁前端拼 Prompt——spec 4.4 规则 3）：
    - `_GROUNDED_SYSTEM_TEMPLATE`（有据）：含 `[1]`/`[2]` 引用编号与 sources 数组顺序一一对应的指令、禁止编造与禁「根据你的笔记」口吻、**第二道防线逐字指令「如果检索片段与问题无关，直接说明知识库中没有相关内容，不要强行拼接」**（裁决 #12）、简体中文作答要求、`{context_block}` 占位
    - `_UNGROUNDED_SYSTEM_TEMPLATE`（knowledge 无据）：规则 1 逐字锁定固定句式「你的知识库中没有找到相关内容，以下为基于通用知识的回答」为第一句（不得改写、不得省略、不得前置任何内容）；禁止声称内容来自用户知识库/笔记/文档
    - `_CHAT_SYSTEM_TEMPLATE`（chat 轻量聊天，决策 D10）：自然友好回应、**显式禁止使用任何「知识库中没有找到相关内容」类表述**（本次未做知识库检索）、篇幅简短
  - `context_block` 逐条拼接格式（第 i 条）：`[{i}]（来源：{source_title}，相似度 {score}）\n{content}\n\n`——片段正文不截断改写（spec 6.2-3）
  - `build_qa_messages(question: str, sources: list[dict[str, Any]], intent: Literal["chat", "knowledge"] = "knowledge") -> list[ChatMessage]` 分流：`intent="chat"` → 模板三（忽略 sources）；knowledge 且 sources 非空 → 模板一；knowledge 且空 → 模板二；返回 `[{"role": "system", ...}, {"role": "user", "content": question}]` 两元素（单轮无历史上下文，裁决 #6）
  - **无据固定句式仅出现在模板二**（R3 收窄：不出现在模板一与模板三——chat 若沿用将出现「文字宣称无相关内容、样式却正常」的自相矛盾，决策 D10 论证写入 docstring）
- **涉及文件**：修改 `backend/app/rag/qa.py`
- **完成判定**：`python -m py_compile app/rag/qa.py` 通过；三模板组装断言由 9.1 固化（有据含防线指令与 `[1]` 来源块且不含句式 / 无据含句式逐字且不含片段块 / chat 含模板三且不含句式与片段块）
- **依赖**：2.2
- **决策锚点**：决策 D10；裁决 #6/#12；裁定①引申

---

## 3. services 问答编排层（app/services/chat.py）

**写作说明**：业务编排在 services 层（决策 D1：rag/qa.py 若调 search_knowledge 即反向依赖）；产出**事件 dict** 而非 SSE 文本（决策 D2：SSE 格式化属 HTTP 关注点在 api 层）；不 import api、不接收 Request/Response。编排顺序唯一依据：design 2.1.3-A 活动图。

### 3.1 qa_stream SSE 编排生成器（主链路 + 事件构造）

- [ ] **要点**：
  - 新建 `app/services/chat.py`；`async def qa_stream(db: Session, user_id: int, question: str, scope: str) -> AsyncIterator[dict[str, Any]]`
  - 事件构造辅助四函数 `_sources_event(data)` / `_delta_event(text)` / `_done_event(is_grounded, mode, intent, history_id)` / `_error_event(code, message)`——事件结构单一来源，防散落拼 dict；`history_id` 参数类型 `int | None`（落库失败传 None，裁定③）
  - 主链路（design 2.1.3-A 顺序）：① `intent = classify_intent(question)`（try/except 包裹，异常返回 "knowledge"）→ ② chat 路径：`sources=[]`、`is_grounded=False`、`mode="online"`（约定值，决策 D3）直接进 ④；knowledge 路径：**单次**调 `search_knowledge(db, user_id, question, QA_TOP_K, scope)`（scope 原样透传、服务端不重写；检索边界恒为当前认证 user_id，spec 4.3 规则 2）→ BizException 则 yield error 并 return → `filter_sources_by_threshold` → ③ `yield sources 事件`（无据/chat 时 `data=[]`，恰 1 次必推）→ ④ `build_qa_messages` 三模板分流 → ⑤ `async for chunk in llm.chat_stream(messages)`：`answer_parts.append(chunk)` + **立即 `yield delta`（真实流式零缓冲、禁先算后发，spec 4.1 规则 2）**，同时置 `has_delta=True` → ⑥ LLM 流耗尽后、done 之前调 `save_qa_history`（3.2）取 `history_id` → ⑦ `yield done`（**四字段** `{is_grounded, mode, intent, history_id}`，data 必推——裁决 #8 + 裁定①）
  - `QA_TOP_K = 5` 模块常量（决策 D7：不暴露给前端，防参数面膨胀）
  - **LLM 调用注入形态（测试友好）**：`from app.services import llm` 模块引用 + 调用点 `llm.chat_stream(...)` 属性访问——monkeypatch `app.services.llm.chat_stream` 即可注入假流；`search_knowledge` 用 `from app.services.knowledge import search_knowledge` 直接导入绑定（测试以真实检索驱动；chat 跳检用例 patch `app.services.chat.search_knowledge` 计数，design 2.4.4-⑧）
  - db 会话生命周期：生成器持有请求级会话，落库是唯一写事务且发生在流末（FastAPI 依赖 teardown 在响应发送完成后执行，流式期间会话有效——design 1.2.5 ②）
  - `answer = "".join(answer_parts)` 流末一次性拼接，仅用于落库与日志计数，不影响推送节奏
- **涉及文件**：新增 `backend/app/services/chat.py`
- **完成判定**：`cd backend && python -m py_compile app/services/chat.py` 通过；事件序列与四字段断言由 9.3 固化（sources 恰 1 次 → delta 0..n 顺序一致 → done 恰 1 次、`{"is_grounded","mode","intent","history_id"}` 四键齐全）
- **依赖**：组 2（rag/qa.py 三函数）、1.4（无直接依赖，qa_stream 不触 schema）；**运行前置**：组 5（search_knowledge scope 签名——编写可先行，运行与测试需组 5 就绪）
- **决策锚点**：决策 D1/D2/D3/D7；裁定①；裁决 #6

### 3.2 历史落库与分页查询（落库失败不抛穿主链路）

- [ ] **要点**：
  - `save_qa_history(db, user_id, question, answer, sources, mode, is_grounded, intent) -> int | None`：唯一写入口（done 前一步调用）；`db.add + db.commit`；**落库失败不抛穿**——捕获自身异常、`db.rollback()` 释放 SQLite 写锁、`logger.warning`（**含 user_id 与异常类型摘要，禁止记录 question 原文与 answer 全文**——日志泄露用户内容红线，spec 4.3 规则 4）、返回 `None`；调用方以 `history_id=None` 照常构造 done 收尾（裁定③：主链路回答成功，不被辅链路历史保存失败拖垮）
  - `sources` 快照语义：sources 事件 `data` 的 JSON 数组**原样**落库（`JSONType` 写入，无据与 chat 落 `[]`）；快照不随后续库变化更新（spec 5.4.3 场景 2）
  - `intent` 一并落库（决策 D9：chat 与 knowledge 无据两种记录既有字段完全同构 `sources=[] + is_grounded=false`，不落库则历史回放无法区分两种渲染）
  - `list_qa_history(db, user_id, page, page_size) -> dict`：恒带 `QAHistory.user_id == user_id` 过滤（「不可见即不存在」，spec 4.3 规则 3）+ `created_at` 倒序 + 复用 `services/readonly.py` 的 `paginate` 泛型助手 + `ChatHistoryOut` 序列化（禁止裸 ORM 对象出 services 边界）；返回 `{items, total, page, page_size}`
- **涉及文件**：修改 `backend/app/services/chat.py`
- **完成判定**：`python -m py_compile app/services/chat.py` 通过；落库语义由 9.3 固化（成功流后历史新增 1 条且 answer = delta 拼接、intent 落库正确；error 流不新增；**monkeypatch save_qa_history 抛异常 → 事件流仍 done 收尾且 history_id=null、无 error 事件、历史不新增**）
- **依赖**：3.1（同文件）、1.2/1.3（表就绪）
- **决策锚点**：决策 D4/D9；裁定③；裁决 #5/#7

### 3.3 流内异常捕获与 error 事件转换（含日志规范）

- [ ] **要点**：
  - **error 仅两源**（裁定③收窄：落库失败不走 error）：① 检索段 `except BizException as exc: yield _error_event(exc.code, exc.message)`——3000/3001 与中文文案自动继承服务层既有包装（`search_knowledge` 的 message 与 spec 5.1.3 场景 1/2 逐字一致，零二次映射）；② LLM 段：`except BizException`（创建阶段已包装）用其 code/message；`except Exception`（**迭代阶段未包装的原始异常**，`chat_stream` 迭代段不包装——design 1.2.3）转 `_error_event(3000, "回答生成中断，请重试" if has_delta else "AI 服务暂时不可用，请稍后重试")`——按「是否已推送 delta」区分场景 1/3 文案
  - 每个 error 分支 `return`（生成器终止）**保证终结事件恰一个**（裁决 #4：done 与 error 互斥）；原始异常堆栈仅入日志不外透
  - 落库段异常由 `save_qa_history` 内部消化（3.2），不进入本层捕获结构
  - 日志规范：流末 info 一条元数据（`user_id / scope / intent / is_grounded / mode / delta 片数 / 总耗时 / history_id`）；error 分支 warning（user_id/scope/错误码/异常类型）；**全程禁打印问题原文与回答全文**（spec 4.3 规则 4 隐私红线）
- **涉及文件**：修改 `backend/app/services/chat.py`（并入 3.1 的生成器结构，本任务是异常分支与日志的显式核对项）
- **完成判定**：`python -m py_compile app/services/chat.py` 通过；异常路径由 9.3 固化（mock chat_stream 抛 BizException(3000) → sources 后恰一条 error、无 done；迭代中途抛原始异常（首片后）→ 3000「回答生成中断，请重试」；monkeypatch search_knowledge 抛 3001 → error 且**不伪装为无据降级**）
- **依赖**：3.1
- **决策锚点**：裁定③；裁决 #4/#10；spec 5.1.3 三场景文案逐字

---

## 4. api 路由层（SSE 端点 + 历史端点）

**写作说明**：路由只做「鉴权注入 + 请求体解析 + SSE 文本格式化 + StreamingResponse 头部 + success() 包装」（决策 D2）；**受理阶段错误零额外代码**——正常声明 `Depends` 与请求体模型，401/422 由既有全局异常处理器自动产出统一 JSON（`StreamingResponse` 构造发生在受理检查之后，裁决 #10）。

### 4.1 POST /chat/qa SSE 流式问答端点

- [ ] **要点**：
  - 新建 `app/api/v1/chat.py`；路由函数签名（design 2.2.2-(1)）：`async def chat_qa(payload: ChatQAIn, db: Annotated[Session, Depends(get_db)], current_user: Annotated[User, Depends(get_current_user)]) -> StreamingResponse`
  - SSE 文本格式化生成器：内部包一层 `async def _sse_format(events) -> AsyncIterator[str]`，逐条产出 `f"data: {json.dumps(event, ensure_ascii=False)}\n\n"`（中文原样）；**格式化必须在 api 层**（契约 §4：services 禁止拼接 HTTP 响应——决策 D2）
  - `StreamingResponse(media_type="text/event-stream", headers={"Cache-Control": "no-cache"})`（spec 4.3 规则 5 硬性要求）；**不做心跳注释行**（决策 D6：本地 uvicorn 直连无中间层缓冲，YAGNI——备选方案记入 docstring 供后续引入反向代理时再议）
  - 调 `services/chat.qa_stream(db, current_user.id, payload.question, payload.scope)` 驱动事件流；user_id 取认证结果、禁收客户端传入的 user_id/item_id 作为检索边界
  - docstring 回链 design 2.2.1 协调表（受理阶段 JSON / 流内 error 事件的「以流是否开始为分界」）
- **涉及文件**：新增 `backend/app/api/v1/chat.py`
- **完成判定**：`cd backend && python -m py_compile app/api/v1/chat.py` 通过；受理错误与响应头由 9.3 固化（无 token → HTTP 401 + `{code:1003}` JSON 非 SSE；空 question / 501 字符 / `scope="foo"` → 422 + 1001；响应头 `content-type: text/event-stream` + `cache-control: no-cache`）
- **依赖**：3.1、1.4
- **决策锚点**：决策 D2/D6；裁决 #10

### 4.2 GET /chat/history 历史分页端点与路由挂载

- [ ] **要点**：
  - `GET /chat/history`：`page_params: Annotated[PaginationParams, Query()]`（仅分页参数的列表端点，沿用查询参数模型写法——契约 §5.3 既有惯例）+ db + current_user → 薄委托 `services/chat.list_qa_history` + `success()` 包装（路由层零业务逻辑；历史接口**严格走统一响应体**，与 SSE 通道分离）
  - `api/v1/__init__.py` 挂载：`from app.api.v1.chat import router as chat_router` + `api_router.include_router(chat_router)`（一处两行；main.py 零改动）
- **涉及文件**：修改 `backend/app/api/v1/__init__.py`（`api/v1/chat.py` 在 4.1 已建）
- **完成判定**：`python -m py_compile app/api/v1/__init__.py` 通过；pytest 直调 `GET /api/v1/chat/history?page=1&page_size=10` 返回统一响应体 `{code:0, data:{items,total,page,page_size}}`（9.3 固化）；`GET /health` 不受挂载影响
- **依赖**：3.2、4.1（同文件先建）
- **决策锚点**：裁决 #10；契约 §5.2/§5.3

---

## 5. search_knowledge scope 扩展与兼容回归

**写作说明**：本组是 P7 检索底座的**前向兼容扩展**（追加带默认值参数，既有调用方零改动——裁决 #2；新增可选字段不删不改既有字段——裁决 #3）；与组 2/3/4 文件零交集可完全并行，但组 3 的运行与组 9 测试依赖本组落地。**禁止重写检索逻辑**（spec 1.4-1）。

### 5.1 query_visible scope 参数化（collection 选择层过滤）

- [ ] **要点**：
  - `rag/vectorstore.py :: query_visible` 签名追加 `scope: str = "all"`；**循环变量 `scope` 重命名为 `owner_scope`**（原 `for scope, owner_id in (("personal", user_id), ("public", None))` 与新增参数同名冲突，防遮蔽——design 1.2.2 约束①）
  - 目标 collection 清单按 scope 推导（**过滤发生在 collection 选择层**，而非 SQL where 或 Chroma where metadata）：`personal` → 仅 `kb_user_{uid}`（offline 对应仅 `kb_user_{uid}_local`）；`public` → 仅 `kb_public`（offline 对应 `_local`）；`all` → 两路合并（**现状行为原样**，`all` 路径代码与现状逐行一致）
  - 隔离红线天然继承：双层知识库的物理隔离就是 collection 级（`kb_user_{uid}` 分库即权限边界），personal 档在存储结构上不可能命中他用户内容（验收 D4 的结构性保证）；每库 `n_results = min(top_k, count)` + 合并截断的既有口径对三档统一适用（单路时合并退化为恒等）
  - docstring 更新：补 scope 三档语义与「collection 选择层过滤」的取舍理由（design 2.5 实现层面论证）
- **涉及文件**：修改 `backend/app/rag/vectorstore.py`（不改：`backend/app/rag/embedding.py` / `loader.py` / `splitter.py`)
- **完成判定**：`cd backend && python -m py_compile app/rag/vectorstore.py` 通过；三档归属断言由 9.2 固化（personal 仅本人文档 / public 仅公共 / all 混合按 score 降序；用户 B personal 空库 → 空结果）
- **依赖**：无（可与组 1–4 完全并行）
- **决策锚点**：裁决 #2；验收 D4/D5

### 5.2 search_knowledge 签名扩展与来源三字段透出

- [ ] **要点**：
  - `services/knowledge.py :: search_knowledge` 签名追加 `scope: Literal["personal", "public", "all"] = "all"`（**带默认值的位置参数**，任何按位置或关键字传既有四参的调用不受影响——Python 语义保证）；调用 `query_visible` 时透传 scope
  - `KnowledgeSearchHit` 组装时从底层 hit **填充 `item_id / chunk_index / scope` 三字段（不再丢弃**——底层 `query_visible` 命中已含三字段，P7 组装时被丢弃，裁决 #3 实测确认）；既有字段 `content / source_title / score` 不删不改
  - `schemas/knowledge.py :: KnowledgeSearchHit` 追加三个可选字段：`item_id: int | None = None`、`chunk_index: int | None = None`、`scope: str | None = None`（可选语义，实际总有值；Pydantic 序列化下既有消费方按原字段读取不受影响）
  - docstring 更新：「签名保持稳定」声明同步更新为「scope 为前向兼容扩展，既有四参调用行为不变」；回链 design 2.5 兼容性论证四条
- **涉及文件**：修改 `backend/app/services/knowledge.py`、`backend/app/schemas/knowledge.py`（不改：`backend/app/api/v1/knowledge.py`——P7 端点对外契约不变）
- **完成判定**：`python -m py_compile app/services/knowledge.py app/schemas/knowledge.py` 通过；**D8 兼容回归**由 9.2 固化（同一查询下「不传 scope」与「显式传 all」的 mode + results 全字段逐字段相等；`POST /api/v1/knowledge/search` 端点响应含既有三字段且语义不变、新增三字段有值）；既有测试 `pytest tests/test_knowledge_search.py tests/test_knowledge_isolation.py -v` 全绿（扩展零破坏）
- **依赖**：5.1（透传链路）
- **决策锚点**：裁决 #2/#3；验收 D8

---

## 6. 前端类型定义与 SSE 客户端

**写作说明**：仅依赖组 4 的接口契约（design 2.2.2），可与后端测试并行。字段全程 snake_case 对齐后端（契约 §8.3 禁自动大小写转换）；SSE 走 fetch 属 PROJECT_CONTEXT §7.3 认可的流式例外，**禁用 EventSource**（spec 5.6.2 细则 5）。

### 6.1 问答类型组与 KnowledgeSearchHit 扩展

- [ ] **要点**：
  - `types/index.ts` 新增类型组（design 2.6.1 全文，全部 snake_case）：`QaScope = 'personal' | 'public' | 'all'`；`QaIntent = 'knowledge' | 'chat'`（R3 新增）；`QaSourceItem`（`item_id: number | null`、`chunk_index: number | null`、`content`、`source_title`、`score`、`scope: 'personal' | 'public'`）；`QaSseEvent` **可辨识联合**（四事件：sources / delta / done{is_grounded, mode, intent, history_id: number | null} 四字段 / error{code, message}）；`ChatQaPayload`（question + scope?）；`ChatHistoryItem`（id/question/answer/sources/mode/is_grounded/**intent**/created_at）
  - 同步扩展 `KnowledgeSearchHit`：追加 `item_id?: number | null`、`chunk_index?: number | null`、`scope?: 'personal' | 'public' | null`（可选字段，对齐 5.2 后端扩展，不影响既有消费）
  - `AskMessage` 视图内部类型（组件间契约）：`{ role: 'user' | 'assistant', content: string, sources: QaSourceItem[], is_grounded: boolean | null, intent: QaIntent | null, mode: 'online' | 'offline' | null, streaming: boolean, error: string | null }`——流中双信号为 null、done 权威定值
- **涉及文件**：修改 `frontend/src/types/index.ts`（不改：`frontend/src/api/knowledge.ts`)
- **完成判定**：`cd frontend && npm run build`（含 vue-tsc）通过；无 any 扩散；字段名与后端 schema 逐字对齐
- **依赖**：1.4（字段契约对齐）
- **决策锚点**：裁定①（QaIntent 与 done 四字段联合）

### 6.2 request.ts 导出复用与 api/chat.ts SSE 客户端

- [ ] **要点**：
  - `request.ts`：`clearTokenAndRedirect` 仅加 `export`（**行为零变化**——决策 D8：fetch 路径 401 行为必须与 Axios 路径一致，单一实现禁复制两份）
  - 新建 `api/chat.ts`，两函数：
  - `streamChatQa(payload: ChatQaPayload, handlers: { onSources, onDelta, onDone, onError }): Promise<void>`：
    - 请求：`fetch(base + '/chat/qa', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token }, body: JSON.stringify(payload) })`；token 从 `useUserStore().token` 读取；base 取 `import.meta.env.VITE_API_BASE_URL || '/api/v1'`（与 request.ts 同源）
    - **受理阶段错误（HTTP 非 200）**：`await resp.json()` 解析统一响应体 → 401 / `code===1003` 时调导出的 `clearTokenAndRedirect()` + `ElMessage.error(message)`；其他业务码 `ElMessage.error(message)`；随后 reject 终止（流未开始，与裁决 #10「以流是否开始为分界」一致）
    - **流解析（跨 chunk 残包处理核心）**：`resp.body.getReader()` + `TextDecoder('utf-8')`；**行缓冲算法**——`buffer += decoder.decode(value, { stream: true })`，循环 `buffer.indexOf('\n\n')` 切出完整事件块（SSE 事件以空行分隔），剩余半包留在 buffer 等待下一 chunk；对每个完整块取 `data: ` 前缀后的 JSON 行（忽略 `:` 注释行与空行），`JSON.parse` 后按 `type` 判别分发四回调；**残包场景（JSON 被网络分包切断）由「只在 `\n\n` 边界切分」结构性消除**
    - `done`/`error` 到达后 resolve Promise（流终结）；`reader.read()` 抛错（浏览器侧网络中断）→ catch → `onError({ code: 0, message: '网络中断，请重试' })` 本地合成错误——已收到的 delta 保留在消息里（spec 4.2 规则 5 前端半边）
  - `getChatHistory(page, page_size)`：Axios 常规分页（走 request.ts 统一解包，返回 `Promise<{items, total, page, page_size}>`）
  - 模块注释注明「SSE 走 fetch 属 PROJECT_CONTEXT §7.3 流式例外，禁 EventSource」
- **涉及文件**：修改 `frontend/src/api/request.ts`（仅加 export）；新增 `frontend/src/api/chat.ts`
- **完成判定**：`npm run build` 通过；代码走查确认行缓冲算法（`\n\n` 边界切分而非按行切分）与 401 复用（无第二份 clearToken 逻辑）
- **依赖**：6.1
- **决策锚点**：决策 D8；裁决 #10；spec 5.6.2 细则 5

---

## 7. AskView 页面与组件群

**写作说明**：沿用 KnowledgeBaseView 的「视图持有数据 + 子组件 props 进 / emit 出」惯例；Element Plus 组件库；三档控件、来源卡、双信号样式、历史还原四要素对齐 design 2.6.2–2.6.6。

### 7.1 AskComposer.vue 输入区（三档切换 + 提交）

- [ ] **要点**：
  - `el-input`（`maxlength=500`、回车提交、提交前 trim 判空——空问题点击给输入提示不发请求）+ 提交按钮（`streaming` 期间禁用，防并发流串扰——同一时刻至多一个活跃流；不引入 AbortController，YAGNI）
  - 三档 `el-radio-group` + `el-radio-button`（「两者结合 / 仅个人库 / 仅公共库」对应值 `all / personal / public`——button 形态紧凑且不可输入非法值，spec 5.2.3 场景 1 前端先行拦截）
  - `scope` 由 AskView 持有（`ref<QaScope>('all')`）经 `v-model` 双向；**档位即时生效**——随每次提问请求体提交 `{question, scope}`，切换后下一次提问立即按新档检索无需刷新（spec 5.2.1 规则 4）
  - `emit('ask', question)`；props：`modelValue(scope)` / `disabled(streaming)`
- **涉及文件**：新增 `frontend/src/components/ask/AskComposer.vue`
- **完成判定**：`npm run build` 通过；空问题不发请求；三档值与后端字面量一致（spec 4.4 规则 4）
- **依赖**：6.1
- **决策锚点**：spec 5.2.1 规则 2/4

### 7.2 MessageBubble.vue 消息气泡（intent × is_grounded 双信号样式）

- [ ] **要点**：
  - 用户/助手双形态；助手气泡：流式中显示光标 → 完成后按**双信号联合权威驱动**（裁定①两条规则逐字）：`intent === 'knowledge' && is_grounded === false` → **无据警示变体**（灰底 + warning 色边框 + 顶部常驻 `el-alert type="warning"`「未引用知识库 · 基于通用知识回答」不可关闭）；`intent === 'chat'` → **正常回答不显示任何警示**；有据 → 常规白底 + 底部来源卡片组
  - 信号来源：实时流取 `done.data.{intent, is_grounded}`（服务端权威——阈值判定在前端不可见，裁决 #8）；历史还原取 `ChatHistoryItem` 同源字段；**仅 is_grounded 不足以区分「没检索」与「检索无果」两种 false——intent 是必要第二信号**（裁定①核心理由，写入组件注释）
  - 句式仅辅助（LLM 偶发不遵守句式时权威信号兜底，spec 5.3.3 场景 2）；**chat 分支不适用句式判定**（模板三显式禁止该句式）
  - 流中断（无 done，`intent/is_grounded` 均为 null）→ 常规样式 + 错误提示（权威信号缺失宁可不标注）；`history_id === null` → 不显示「已保存」相关状态（裁定③）
  - `mode === 'offline'`（done 或历史记录）→ 气泡内常驻 `el-alert type="warning"`「当前为离线检索模式」（**文案与 SearchPanel 逐字一致**，P8 惯例）；与无据警示并存时先 mode 后 is_grounded 上下排布
  - 无据警示与常规样式差异肉眼可辨（验收 D3 同屏对比）
- **涉及文件**：新增 `frontend/src/components/ask/MessageBubble.vue`
- **完成判定**：`npm run build` 通过；三种变体（警示 / 常规+来源 / 正常聊天）渲染逻辑在代码走查中核对（浏览器端最终核对归 10.5）
- **依赖**：7.3（内嵌 SourceCard）、6.1
- **决策锚点**：裁定①；裁决 #8；验收 D3

### 7.3 SourceCard.vue 来源折叠卡（跳转定位）

- [ ] **要点**：
  - 卡片内容：来源标题（`source_title`，即「文档标题 » 标题路径」）+ 片段摘要（`content` 折叠展示两行、展开全文）+ 相似度徽章（`score` 保留 2 位，沿用 SearchPanel 惯例）+ 归属徽章（`scope==='personal'` → 「个人库」primary 色 / `'public'` → 「公共库」info 色）+ 右上角 `[n]` 序号（与回答中引用编号对应，spec 5.4.1 规则 5）
  - **同文档多片段不去重合并**，逐条独立卡片、编号连续（spec 5.4.1 规则 6）
  - 跳转：点击卡片 → `router.push({ path: '/knowledge-base', query: { item_id: String(source.item_id), chunk_index: String(source.chunk_index) } })`；`item_id` 为空（脏快照防御）→ 按钮禁用降级为纯展示
  - 折叠/展开交互（el-collapse 或自实现均可，Element Plus 风格）
- **涉及文件**：新增 `frontend/src/components/ask/SourceCard.vue`
- **完成判定**：`npm run build` 通过；跳转 query 参数形态与 7.5 承接方逐字对齐（`item_id` / `chunk_index`）
- **依赖**：6.1
- **决策锚点**：spec 5.4.1 规则 1–6；验收 D2

### 7.4 AskView.vue 页面（SSE 消费 + 历史对话流还原）

- [ ] **要点**：
  - 状态：`messages: AskMessage[]`（6.1 内部类型）、`scope = ref<QaScope>('all')`、`streaming = ref(false)`
  - `onAsk(question)`：push 用户消息 + 占位助手消息（streaming=true）→ `streamChatQa({question, scope}, handlers)` 四回调分发响应式更新：`onSources` **即时**写入 sources（卡片先于回答完成出现，spec 5.4.1 规则 1）、`onDelta` 追加 content（逐字渲染）、`onDone` 定值 `is_grounded/intent/mode` + `streaming=false`、`onError` 置 error 提示 + **保留已生成内容不清空**（spec 4.2 规则 5）；流终结（Promise resolve）后恢复提交可用
  - `onMounted` → `getChatHistory(1, 10)` → `items`（created_at 倒序）→ **reverse 后**逐条映射为一对消息（用户气泡 = question；助手气泡 = answer + sources + is_grounded + **intent** + mode，`streaming: false`）——对话流按时间正序还原（第 1 页末尾即最新问答，spec 5.5.1 规则 5）；历史接口失败 → 拦截器弹错 + 保留空对话区可正常提问（spec 5.5.3 场景 2）
  - 「加载更早的问答」按钮（`total > 已加载数` 时显示）→ `page+1` 追加更早条目（保持正序拼接）；空状态 `el-empty`「暂无问答记录，开始提问吧」（spec 5.5.3 场景 1）；无删除/编辑入口（spec 5.5.1 规则 6 只读）
  - 页面布局：对话流滚动区 + 底部固定输入区（AskComposer）；滚动跟随最新消息
- **涉及文件**：新增 `frontend/src/views/AskView.vue`
- **完成判定**：`npm run build` 通过；刷新页面对话流完整还原（含双信号样式还原——**intent 落库是该一致性的前提**，决策 D9）归 10.5 用户核对
- **依赖**：6.2、7.1、7.2
- **决策锚点**：裁定①（回放双信号）；验收 D6

### 7.5 知识库页跳转承接与分块高亮（D2 跳转闭环）

- [ ] **要点**：
  - `KnowledgeBaseView.vue`：挂载时读 `route.query.item_id`（正整数校验）→ 调既有详情端点 `GET /knowledge/items/{id}`（**自带可见性 404 语义**——不可见或已删除，错误提示由拦截器统一弹出「文档不存在」类中文提示，spec 5.4.3 场景 1）→ 命中则置 `activeItem` 并打开 `ChunkDrawer`；**详情调用使定位不受分页影响**（文档可能不在当前页列表中，详情端点直接按 id 取）
  - `ChunkDrawer.vue` 新增可选 prop `highlight_chunk_index: number | null`：对应 `chunk_index` 的分块卡片加高亮样式（条件 class）+ `scrollIntoView` 定位
  - 历史快照过期场景（spec 5.4.3 场景 2）：跳转按 `item_id` 尽力定位、失败时明确中文提示不白屏
- **涉及文件**：修改 `frontend/src/views/KnowledgeBaseView.vue`、`frontend/src/components/knowledge/ChunkDrawer.vue`（不改：`frontend/src/components/knowledge/SearchPanel.vue`、`frontend/src/api/knowledge.ts`)
- **完成判定**：`npm run build` 通过；点击来源卡 → 跳转 `/knowledge-base`、抽屉打开、对应分块高亮、片段原文与卡片一致（验收 D2，归 10.5 用户核对）
- **依赖**：7.3（跳转发起方）、6.1
- **决策锚点**：spec 5.4.1 规则 3；验收 D2

---

## 8. 前端路由与菜单插入

**写作说明**：仅插入条目，既有路由表零改动（裁决 #1 / spec 4.5 规则 4）；`needsAuth: true` 复用既有守卫。

### 8.1 /ask 路由与侧边菜单「AI 问答」插入

- [ ] **要点**：
  - `router/index.ts` 的 `children` 数组在 `knowledge-base` 与 `ai-agent` 条目**之间**插入：`{ path: 'ask', name: 'ask', component: () => import('@/views/AskView.vue'), meta: { title: 'AI 问答', needsAuth: true } }`
  - `MainLayout.vue` 的 `menus` 数组「知识库」**之后**插入：`{ index: '/ask', title: 'AI 问答', icon: 'ChatLineRound' }`（与 AI 助手的 `ChatDotRound` 图标区分；图标可在实现时微调）
- **涉及文件**：修改 `frontend/src/router/index.ts`、`frontend/src/layouts/MainLayout.vue`
- **完成判定**：`cd frontend && npm run build` 通过；登录后侧边菜单出现「AI 问答」且位于「知识库」与「AI 助手」之间；无 token 直接访问 `/ask` 被守卫跳转 `/login`（10.5 用户核对）
- **依赖**：7.4（AskView 组件存在）
- **决策锚点**：裁决 #1

---

## 9. 后端测试（pytest 单测 + ASGI e2e）

**写作说明**：三个测试文件（design 2.7.1 全量用例表）；conftest 全部复用既有 `app_client / user_a / user_b / _isolated_runtime / upload_document / offline_embedding`（沙箱 IPv6 socketpair 补丁已在 conftest 顶部加载，ASGI 直调不经网络）；**真实 LLM 一律 mock**（唯一外部 LLM 调用点），检索走真实路径（本地兜底 embedding 真算 + 真 Chroma）；真实流式节奏归 10.5 本机清单。

### 9.1 test_rag_qa_prompt.py 纯函数单测（无 IO）

- [ ] **覆盖**：
  - **意图判断**：「你好 / 您好 / 谢谢 / 你是谁 / 这个系统是干嘛的 / hello」→ `"chat"`；「什么是 Transformer / Dijkstra 算法是什么 / 你好，请问什么是 SVM（混入知识内容不命中）」→ `"knowledge"`（spec 5.1.1 规则 7 R3 口径）
  - **阈值过滤**：默认 0.55——`[{score:0.572},{score:0.533}]` → 过滤后仅 0.572、is_grounded=True；`[{score:0.484}]` → `([], False)`；空输入 → `([], False)`；monkeypatch `RAG_MIN_SCORE=0.30` 后 0.484 保留（验收 D9 第一段）
  - **RAG_MIN_SCORE 配置**：monkeypatch env 空串后重建 `Settings` 断言回退 0.55；非法值（>1、负数）→ 配置加载失败（spec 4.4 规则 2）
  - **Prompt 有据模板**：组装结果含第二道防线逐字指令「如果检索片段与问题无关，直接说明知识库中没有相关内容，不要强行拼接」、含 `[1]（来源：…，相似度 …）` 块、含片段正文原文、question 位于 user 消息；**不含**无据固定句式
  - **Prompt 无据模板**：`intent="knowledge"` + sources=[] 组装 → 系统提示含固定句式逐字文本「你的知识库中没有找到相关内容，以下为基于通用知识的回答」且要求首句；**不含**知识库片段块（spec 5.3.1 规则 2：句式仅出现在 knowledge 无据）
  - **Prompt 聊天模板（R3）**：`intent="chat"` 组装 → 系统提示含模板三全文；**不含**无据固定句式、不含知识库片段块（决策 D10）
- **涉及文件**：新增 `backend/tests/test_rag_qa_prompt.py`
- **完成判定**：`cd backend && pytest tests/test_rag_qa_prompt.py -v` 全绿；句式与防线指令用精确包含断言（验收锚点）
- **依赖**：组 2、1.1
- **验收锚点**：验收 D9 第一段；spec 5.1.1 规则 7、5.3.1 规则 1/2/7

### 9.2 test_rag_qa_scope.py 三档检索与 D8 兼容回归（真实检索路径）

- [ ] **覆盖**：
  - **三档检索**：用户 A 经 `upload_document` 上传并等待索引后：`scope="personal"` → 命中仅 A 文档；`scope="public"` → 仅公共文档（4 篇种子）；`scope="all"` → 两类混合按 score 降序（验收 D5 / spec 5.2.1 规则 1）
  - **隔离**：用户 B（空个人库）`scope="personal"` 提问 → 空结果；任意档位不含 A 的文档内容与标题（验收 D4）
  - **默认兼容（D8 核心）**：同一查询下「不传 scope」与「显式传 all」的返回（mode + results 全字段）**逐字段相等**；ASGI 直调 `POST /api/v1/knowledge/search`（P7 端点）响应含既有三字段且语义不变、新增 `item_id/chunk_index/scope` 字段有值
  - **字段透出**：命中条目 `item_id` 为正整数、`chunk_index` ≥ 0、`scope ∈ {personal, public}`；`source_title` 为「标题 » 路径」拼接（验收 D2 数据侧）
  - 检索走真实路径：本地兜底 embedding 真算 + 真 Chroma（复用 `_isolated_runtime` 的 tmp_path 隔离与 `upload_document` helper 轮询至 indexed）
- **涉及文件**：新增 `backend/tests/test_rag_qa_scope.py`
- **完成判定**：`pytest tests/test_rag_qa_scope.py -v` 全绿；兼容断言基于逐字段相等（非仅长度/顺序）
- **依赖**：组 5、4.2（端点挂载）；既有 `pytest tests/test_knowledge_search.py tests/test_knowledge_isolation.py -v` 同批回归全绿
- **验收锚点**：验收 D4/D5/D8；spec 4.5 规则 1/2、5.2.1 规则 5

### 9.3 test_rag_qa_stream.py SSE 契约 e2e（ASGI TestClient + mock LLM）

- [ ] **覆盖**：
  - **事件序列（有据）**：注入向量数据 + `monkeypatch.setattr("app.services.llm.chat_stream", fake_stream)`（3 片假流）→ 响应头 `content-type: text/event-stream` + `cache-control: no-cache`；逐行解析 SSE：首条 sources（恰 1 次）、中间全 delta（3 条、顺序与 mock 产出一致）、末条 done；done.data **四字段齐全**且 `is_grounded=true`、`intent="knowledge"`、`history_id` 非空（spec 5.1.1 规则 2/8、裁决 #8、裁定①）
  - **事件序列（无据）**：空库用户（或领域外问题在本地兜底向量下构造低分）→ sources 为 `[]`、done `is_grounded=false` 且 `intent="knowledge"`；落库记录 sources 为 `[]`、intent 为 `"knowledge"`（验收 D3 ②③④⑤ 数据侧）
  - **chat 路径（R3）**：提问「你好」→ sources 空 + done `is_grounded=false`、`intent="chat"`；**patch `app.services.chat.search_knowledge` 断言调用计数为 0**（未发起无意义检索）；落库记录 `intent="chat"`（历史回放区分前置，验收 D3 后半 / 裁定① / 决策 D9）
  - **受理错误走统一响应体**：无 token → HTTP 401 + `{code:1003}` JSON（非 SSE）；空 question / 501 字符 / `scope="foo"` → HTTP 422 + `code=1001`（裁决 #10）
  - **流内异常 → error 事件**：mock `chat_stream` 抛 `BizException(3000, ...)` → sources 后恰一条 error 收尾、无 done、`error.data.{code,message}` 逐字段断言；mock 迭代中途抛原始异常（首片后）→ error 3000「回答生成中断，请重试」（spec 5.1.3 场景 1/3）
  - **检索异常 → error 事件**：monkeypatch `app.services.chat.search_knowledge` 抛 `BizException(3001, "检索失败请稍后重试")` → error 事件且**不伪装为无据降级**（无 sources 空数组 + 无据句式路径，spec 5.1.3 场景 2 / 5.3.1 规则 6）
  - **落库时机与失败处理（R3 裁定③核心）**：成功流后 `GET /chat/history` 新增 1 条且 answer = delta 拼接、sources 与事件一致、intent 落库正确、created_at 倒序；error 流后历史**不新增**；**monkeypatch `save_qa_history` 抛异常 → 事件流仍以 done 收尾且 `history_id=null`（无 error 事件）、历史不新增**（主链路不被辅链路拖垮）
  - **历史隔离与分页**：双账号各问答数条 → 互查不含对方记录（验收 D4 历史维度）；page_size=2 翻页正确、total 正确（验收 D6）
  - **真实流式结构性证明**：mock 为「先 yield 1 片 → `await asyncio.sleep(短暂)` → 再 yield」的异步生成器，断言 TestClient 收到完整流且事件顺序即产出顺序（StreamingResponse 逐段拉取语义；真实逐字节奏最终验证归 10.5——验收 D1 沙箱内结构等价部分）
- **涉及文件**：新增 `backend/tests/test_rag_qa_stream.py`
- **完成判定**：`cd backend && pytest tests/test_rag_qa_stream.py -v` 全绿；全部断言不经网络（LLM mock、检索本地兜底、ASGI 直调）
- **依赖**：组 1–5 全部（表就绪 + 纯函数 + 编排 + 端点 + scope 扩展）
- **验收锚点**：验收 D1（结构等价）/D3/D4/D6/D7；裁定③；裁决 #4/#7/#8/#10

---

## 10. 构建、回归与验证收尾

**写作说明**：本组是全链路收口——后端全量编译与测试、前端类型检查与构建、既有接口回归（D8）、代码走查、用户本机验证清单（真实 LLM 流式与全部浏览器端验收 D1–D9）。

### 10.1 前端类型检查与构建验证节点

- [ ] **要点**：在 `frontend/` 目录内以相对路径执行 `npm run build`（vue-tsc + vite；规避中文用户名 TEMP 路径坑与 esbuild 损坏问题——P8 既有惯例），覆盖组 6–8 全部改动文件
- **涉及文件**：`frontend/`（构建验证，不改源码）
- **完成判定**：`cd frontend && npm run build` 退出码 0，vue-tsc 无类型错误
- **依赖**：组 6、7、8

### 10.2 后端全量编译与测试

- [ ] **要点**：`python -m py_compile` 全部改动与新增文件（config / enums / qa 模型 / migrate / init_db / models__init__ / schemas/chat / rag/qa / services/chat / api/v1/chat / api__init__ / vectorstore / knowledge / schemas/knowledge）；`pytest` **全量**运行（新增 3 个测试文件 + 既有 7 个测试文件）
- **涉及文件**：`backend/`（编译与测试验证）
- **完成判定**：`cd backend && python -m py_compile <全部改动文件>` 零报错；`pytest -v` 全绿（既有用例零失败 = scope 扩展零破坏）
- **依赖**：组 9

### 10.3 既有接口兼容性回归（D8）

- [ ] **要点**：回归确认 P7 契约不回退：`POST /api/v1/knowledge/search` 响应结构与检索结果与扩展前一致（除裁决 #3 允许的三个新增可选字段）；`GET /api/v1/knowledge/items` / `GET /knowledge/items/{id}` / `GET /knowledge-chunks` 零改动；启动迁移不影响其他 15 张表；`GET /health` 正常
- **涉及文件**：无新增（回归验证，操作记录可存 `backend/tmp_verify/` 沿用既有惯例）
- **完成判定**：既有 pytest 用例全绿 + 9.2 兼容断言通过；启动日志无 ERROR
- **依赖**：10.2
- **验收锚点**：验收 D8

### 10.4 代码走查与设计一致性核对

- [ ] **要点**：
  - **分层合规**：api 层两新端点无业务规则、services/chat.py 无 Request/Response 对象、`rag/qa.py` 不 import services/api（决策 D5 的静态可验证性——`grep "from app.services" backend/app/rag/qa.py` 应只命中 ChatMessage 重复声明即零命中）；SSE 文本格式化仅在 api 层（决策 D2）
  - **docstring 回链**：各新模块注明对应 design.md 章节号（2.3.2 模型 / 2.4.1–2.4.3 纯函数 / 2.4.4 编排 / 2.2.2 接口 / 2.5 兼容 / 2.6 前端）
  - **隐私红线**：全链路日志禁打印问题原文与回答全文（spec 4.3 规则 4）；落库失败 warning 含 user_id 不含 question
  - **契约核对**：snake_case 全程、type hints 全覆盖、无硬编码模型名/地址/Key、`QA_TOP_K` 为模块常量非环境配置、错误码沿用既有常量无新码位
  - **前端核对**：双信号样式判定逻辑（`intent=knowledge && is_grounded=false` 才警示、`chat` 恒不警示）与裁定①逐字一致；`\n\n` 边界切分的残包处理；401 复用单一 `clearTokenAndRedirect`
- **涉及文件**：组 1–8 全部新增/改动文件（走查）
- **完成判定**：五项走查全部通过；与 design.md「下游交接说明」无偏差（未覆盖细节按 PROJECT_CONTEXT 总则处理并在提交说明记录）
- **依赖**：10.2、10.1

### 10.5 用户本机验证清单（真实 LLM 流式 + 浏览器端验收 D1–D9）

- [ ] **要点**（沙箱网络全禁，以下留给用户本机执行；前置：`.env` LLM/Embedding 配置有效、4 篇公共文档 33 分块已索引、前后端启动）：
  1. **D1 流式**：登录 → `/ask` → 默认「两者结合」提问「什么是 Transformer」→ 逐字渲染、来源卡片先出现、回答含 `[1]` 编号；另开终端 `curl -N -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"question":"什么是 Transformer"}' http://localhost:8000/api/v1/chat/qa` → 多条 delta 不同时间戳陆续到达、首 delta 时刻明显早于 done（时间戳证明真实流式、禁先算后发）
  2. **D5 三档**：三档分别提问同一问题，网络面板观测**每次仅 1 个 `POST /chat/qa` 请求**；sources 归属集合按档位变化
  3. **D2 来源跳转**：点击来源卡 → 跳 `/knowledge-base`、抽屉打开、对应分块高亮、片段原文与卡片一致
  4. **D3 无据标注（答辩必测）**：新账号（空个人库）切「仅个人库」提问「法国大革命的历史背景」→ 固定句式开头 + 空 sources + 警示样式 + `done.is_grounded=false` + `done.intent="knowledge"` **五要素**；同页提问「你好」→ 正常聊天回答（无固定句式）+ 空 sources + 正常样式无警示 + `done.intent="chat"`；刷新后该条历史仍按正常样式还原（intent 落库生效）
  5. **D4 隔离**：账号 A 上传文档并提问命中；账号 B 同问题提问 + 查历史 → B 无 A 的来源与历史记录
  6. **D6 历史**：完成数条问答后刷新 `/ask` 对话流完整还原（含样式）；`curl` 调 `GET /chat/history?page=1&page_size=10` 核对分页倒序
  7. **D7 异常**：临时改错 `.env` 的 `LLM_BASE_URL` → 重启 → 提问 → 中文错误提示「AI 服务暂时不可用，请稍后重试」、页面可再次提问、历史不新增；还原配置后恢复
  8. **D8 回归**：调用 `POST /api/v1/knowledge/search` 核对响应结构不变（新增三字段除外）
  9. **D9 阈值与第二道防线（两段式）**：默认 0.55 提问「股票K线图怎么看」（≈0.484）→ 空 sources + 无据句式；`.env` 设 `RAG_MIN_SCORE=0.30` 重启 → 同问题（无关片段被召回）→ 回答依 Prompt 第二道防线明确说明知识库无相关内容、不强行拼接；恢复 0.55 行为复原
- **涉及文件**：无新增（操作验证，记录建议存 `backend/tmp_verify/`）
- **完成判定**：D1–D9 逐条核对通过（spec 8.2 验证步骤 9 条全过）
- **依赖**：10.1–10.4

---

## 附：任务 → 需求覆盖对照

| spec 需求条目 | 覆盖任务 |
|---|---|
| 5.1 SSE 流式问答（鉴权/事件顺序/真实流式/引用编号/防编造/入参校验/意图判断/传输格式） | 3.1、3.3、4.1、9.1、9.3、10.5 |
| 5.2 检索范围三档切换（档位定义/单次调用/向后兼容/即时生效/隔离保持） | 5.1、5.2、7.1、9.2、10.5 |
| 5.3 无据降级与防幻觉标注（无据判定/固定句式/sources 空数组/双信号权威/差异化样式/禁伪装/第二道防线） | 1.1、2.2、2.3、7.2、9.1、9.3、10.5 |
| 5.4 参考来源展示与跳转（先渲染/来源内容/跳转/数据完整性/编号对应/同文档多片段/删除与快照过期） | 5.2、7.3、7.5、9.2、10.5 |
| 5.5 历史问答记录（落库/失败不落库与裁定③例外/隔离/分页/回放/只读） | 1.2、1.3、3.2、7.4、9.3、10.5 |
| 5.6 接口清单与 SSE 事件契约（四事件/受理错误分界/fetch 解析/禁 EventSource） | 4.1、4.2、6.2、9.3 |
| 6.1–6.4 数据约束（ChatQAIn/sources 条目/qa_history 九字段/事件载荷） | 1.2、1.4、6.1 |
| 4.1–4.5 DFX（性能/可靠性/安全隐私/可维护性/兼容性） | 3.3、5.2、9.2、9.3、10.3、10.4 |
| 裁决 #1–#14 与 R3 裁定①②③ | 全部任务（组 0 前置约定 + 各任务决策锚点） |
| 验收标准 D1–D9（spec 8.1） | 9.1（D9 第一段）、9.2（D4/D5/D8）、9.3（D1 结构等价/D3/D4/D6/D7）、10.5（D1–D9 全量本机核对） |
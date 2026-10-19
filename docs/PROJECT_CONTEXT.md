# 彭城智学 SmartLearn Agent —— 项目级上下文（PROJECT_CONTEXT）

> 本文件是**全项目开发的唯一技术契约**。所有后续编码（前端、后端、Agent、RAG）都必须遵循本文件约定，**不得擅自更换技术栈、目录结构、分层职责、响应体格式与命名规范**。
> 需求来源：`docs/需求文档.md`（V1.0）。若需求文档与本文件冲突，以本文件 + MVP 7 个核心功能为准。
> **后续开发中，如果开发提示词与本文件冲突，一律以本文件为准；本文件未覆盖的细节，以提示词为准。**
> 状态枚举统一使用本文件的 `todo / in_progress / done / review`（不用 `not_started / reviewing`）。
> 掌握度字段统一命名为 `mastery_score`（不用 `mastery`）；知识点字段在 `tasks / learning_records` 中为复数 `knowledge_points`（JSON 数组），在 `knowledge_mastery` 中为单数 `knowledge_point`。
> 适用范围：MVP 第一版（P0）。V2 功能（错题系统、知识图谱、AI 出题、学习风险预警、GitHub/LeetCode 分析等）暂不实现，仅预留扩展位。

---

## 1. 项目定位与一句话介绍

**一句话介绍**：彭城智学（SmartLearn Agent）是一款面向高校学生的 **AI 学习成长智能体**，通过整合学生的学习目标、任务、学习记录与个人知识库，构建**个人学习画像**，并利用 Agent 主动分析学习状态、制定并**动态调整**学习计划，形成从「记录学习」到「理解学习」再到「持续成长」的 AI 学习闭环。

**核心闭环（贯穿全部功能设计）**：
`记录 → 分析 → 规划 → 执行 → 反馈 → 再规划`

**差异化定位**：
- 不是「AI 问答机器人」，而是「**AI 主动分析 + 动态调整学习计划**」。
- 传统软件解决「记录」问题；本项目解决「**理解**」和「**决策**」问题。
- Agent 不直接访问数据库，而是通过 **Tool 调用**获取数据、产生决策。

**MVP 7 个核心功能（P0，开发优先级顺序）**：
① 用户档案 → ② 学习目标 → ③ 学习任务 → ④ 学习记录 → ⑤ Dashboard → ⑥ RAG 知识库 → ⑦ AI Agent。
其中 AI Agent 在 MVP 必须实现 5 个子能力：**分析学习状态 / 生成学习计划 / 查询个人知识库 / 调整学习任务 / 生成学习报告**。

**目标用户**：高校学生（V1.0 仅「学生用户」单一角色，无管理员后台）。
**目标平台**：Web 应用（前后端分离）。
**非功能红线**：核心操作 ≤ 3 次点击；普通页面响应 ≤ 2 秒；AI 请求必须**流式输出**；必须做身份认证 + 密码加密 + API 鉴权 + 文件访问权限控制。

---

## 2. 技术栈锁定（不得擅自更换）

| 层 | 技术选型 | 说明 |
|---|---|---|
| 前端框架 | **Vue 3**（`<script setup>` 组合式 API） | 统一使用 TS |
| 前端构建 | **Vite** | 开发端口 5173 |
| 前端语言 | **TypeScript** | 严格模式，禁止大面积 `any` |
| 状态管理 | **Pinia** | 配合持久化插件存 token |
| 路由 | **Vue Router 4** | 前端路由守卫鉴权 |
| UI 组件库 | **Element Plus** | 统一组件风格 |
| 图表 | **ECharts** | Dashboard / 报告可视化 |
| HTTP | **Axios** | 统一封装 + 拦截器 |
| 后端语言 | **Python 3.10+** | 必须使用 type hints |
| 后端框架 | **FastAPI** | 统一前缀 `/api/v1` |
| ORM | **SQLAlchemy 2.x** | 使用 2.x 声明式风格（`Mapped` / `mapped_column`） |
| 校验 | **Pydantic v2** | 所有出入参必须校验 |
| 数据库 | **SQLite**（`data/smartlearn.db`） | MVP 用 SQLite；**不使用 MySQL/PostgreSQL** |
| 认证 | **JWT HS256（标准库 `hmac` 实现）** | Bearer Token；算法锁死 HS256，先验签再解析 payload，无第三方 JWT 依赖 |
| 密码 | **PBKDF2-HMAC-SHA256**（标准库 `hashlib`，260k 轮，16 字节随机盐） | 只存哈希，不存明文；哈希串自描述格式 `pbkdf2_sha256$<iter>$<salt>$<hash>`，P3 直接复用 P2 的 `app/core/security.py` |
| 向量库 | **Chroma** | 本地持久化目录 `data/chroma` |
| 文档解析 | **pypdf / python-docx / python-pptx / markdown** | 分别对应 PDF / Word / PPT / Markdown |
| LLM | **OpenAI 兼容接口** | 全部通过 `.env` 配置 |

**LLM / Embedding 环境变量（`.env`，禁止硬编码）**：
```
LLM_BASE_URL=            # 对话配置组：OpenAI 兼容服务地址
LLM_API_KEY=             # 对话配置组：密钥
LLM_MODEL=               # 对话配置组：对话/推理模型名
EMBEDDING_BASE_URL=      # 向量化配置组：服务地址（空则回退 LLM_BASE_URL）
EMBEDDING_API_KEY=       # 向量化配置组：密钥（空则回退 LLM_API_KEY）
EMBEDDING_MODEL=         # 向量化配置组：模型名（空则回退 LLM_MODEL）
```
- 所有 LLM 调用统一走 OpenAI 兼容协议（`/v1/chat/completions` 与 `/v1/embeddings`）。
- 双配置组：对话与推理只走 `LLM_*`；向量化只走 `EMBEDDING_*` 生效配置（`EMBEDDING_BASE_URL / EMBEDDING_API_KEY / EMBEDDING_MODEL` 任一项为空时逐项回退对应 `LLM_*` 值，支持单服务商一键配置）。
- 切换模型只允许改 `.env`，代码内**禁止写死任何模型名、地址、Key**。

**认证与运行环境变量（`.env`，禁止硬编码）**：
```
JWT_SECRET=            # 必填，缺失或仍为占位值时服务必须启动失败
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=10080
DATABASE_URL=          # 可选，默认项目根 data/smartlearn.db
CHROMA_DIR=            # 可选，默认项目根 data/chroma
CORS_ORIGINS=          # 前端允许来源，JSON 数组
```
- `JWT_SECRET` 缺失或仍为占位值（如 `change-me-in-env`）时，应用启动必须直接抛出明确错误并退出，**禁止使用任何内置默认密钥继续运行**。

> ⚠️ 与原需求文档的已知冲突（已按本文件裁决）：需求文档第 23 章建议 MySQL/PostgreSQL，第 21 章列出 Naive UI、第 24 章 Chroma。**本项目统一为 SQLite + Element Plus + Chroma**，不采用 MySQL/Naive UI。

---

## 3. 完整目录结构

```
smartlearn/
├── frontend/                       # Vue 3 前端工程
│   ├── public/
│   ├── src/
│   │   ├── api/                    # 按模块拆分的接口调用（auth/profile/goal/task/...）
│   │   │   ├── request.ts          # Axios 实例 + 拦截器（核心封装）
│   │   │   ├── auth.ts
│   │   │   ├── profile.ts
│   │   │   ├── goal.ts
│   │   │   ├── plan.ts
│   │   │   ├── task.ts
│   │   │   ├── record.ts
│   │   │   ├── dashboard.ts
│   │   │   ├── knowledge.ts
│   │   │   └── agent.ts
│   │   ├── assets/
│   │   ├── components/             # 通用组件（图表、卡片、空状态等）
│   │   ├── layouts/                # 主框架布局（侧边栏 + 顶栏）
│   │   ├── router/
│   │   │   └── index.ts            # 路由表 + 全局前置守卫
│   │   ├── stores/                 # Pinia：user / task / agent 等
│   │   │   └── user.ts             # token 与用户信息
│   │   ├── types/                  # 全局 TS 类型（与后端 schema 对齐）
│   │   ├── utils/                  # 工具函数（日期、格式化、错误提示）
│   │   ├── views/                  # 页面级组件，与路由一一对应
│   │   ├── App.vue
│   │   └── main.ts
│   ├── .env.development            # VITE_API_BASE_URL=http://localhost:8000/api/v1
│   ├── .env.production
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
│
├── backend/                        # FastAPI 后端工程
│   ├── app/
│   │   ├── api/                    # 路由层（只做参数接收、权限校验、调 service）
│   │   │   ├── deps.py             # 依赖注入：get_db / get_current_user
│   │   │   └── v1/
│   │   │       ├── __init__.py     # 汇总 APIRouter，统一挂载 /api/v1
│   │   │       ├── auth.py
│   │   │       ├── profile.py
│   │   │       ├── goals.py
│   │   │       ├── plans.py        # 学习计划版本与条目
│   │   │       ├── courses.py
│   │   │       ├── tasks.py
│   │   │       ├── records.py
│   │   │       ├── dashboard.py
│   │   │       ├── knowledge.py    # RAG 上传 / 检索
│   │   │       ├── agent.py        # Agent 对话（SSE 流式）
│   │   │       └── reports.py
│   │   ├── schemas/                # Pydantic v2 出入参（按领域拆文件）
│   │   ├── models/                 # SQLAlchemy ORM 模型（与数据库表一一对应）
│   │   ├── services/               # 业务逻辑层（事务、业务规则）
│   │   ├── agent/                  # Agent 智能体：工具定义、编排、决策
│   │   │   ├── tools.py            # 12 个 Tool 的实现
│   │   │   ├── executor.py         # LLM 工具调用循环
│   │   │   └── prompts.py          # 系统提示词模板
│   │   ├── rag/                    # RAG：解析 / 切分 / 向量化 / 检索
│   │   │   ├── parser.py           # pypdf/docx/pptx/markdown 解析
│   │   │   ├── splitter.py         # 文本清洗与切分
│   │   │   ├── embedder.py         # Embedding（OpenAI 兼容）
│   │   │   └── store.py            # Chroma 封装
│   │   ├── analytics/              # 学习分析引擎：统计、掌握度、报告
│   │   ├── core/                   # 配置与安全
│   │   │   ├── config.py           # 读取 .env（pydantic-settings）
│   │   │   └── security.py         # JWT 签发/校验（HS256）、PBKDF2 密码哈希
│   │   ├── db/                     # 会话与初始化
│   │   │   ├── session.py          # engine / SessionLocal
│   │   │   └── init_db.py          # 建表 + 种子数据
│   │   └── main.py                 # FastAPI 实例、CORS、异常处理、挂载路由
│   ├── requirements.txt
│   └── .env.example                # 变量模板（不含真实密钥）
│
├── docs/                           # 项目文档
│   ├── 需求文档.md                  # 需求来源
│   └── PROJECT_CONTEXT.md          # 本文件
│
├── data/                           # 运行时数据（不进版本库）
│   ├── smartlearn.db               # SQLite 数据库文件
│   ├── chroma/                     # Chroma 本地持久化目录
│   ├── uploads/                    # 用户上传的学习资料原件
│   └── public_kb/                  # 公共知识库种子资料（预置 3-5 篇真实课程资料，随仓库分发）
│
├── scripts/                        # 辅助脚本
│   ├── init_data.py                # 演示数据重置脚本（P13 实现；建表与种子统一走 app/db/init_db.py）
│   └── seed_demo.py                # 生成比赛 Demo 数据
│
├── .env                            # 真实密钥（不进版本库）
├── .gitignore
└── README.md
```

**约定**：
- `backend/app/api/` 只做「接收 + 鉴权 + 调用 service + 组装响应」，**禁止写业务逻辑**。
- `backend/app/services/` 承载全部业务规则与事务，**禁止直接返回 ORM 对象给路由**（须转 Pydantic）。
- `data/` 目录全部为运行时产物，必须加入 `.gitignore`；`data/chroma` 路径在代码中通过 `core/config.py` 统一读取。

---

## 4. 后端分层约定

**分层调用方向（单向，禁止反向依赖）**：
`api → services → models / rag / analytics / agent`，`core` 与 `db` 为全局基础设施，可被任意层引用。

| 层 | 目录 | 职责 | 禁止事项 |
|---|---|---|---|
| **api（路由）** | `app/api/v1/` | 定义 HTTP 端点、解析路径/查询/请求体、注入 `get_db`/`get_current_user`、调用 service、包装统一响应体 | 禁止写 SQL、禁止写业务规则、禁止直接操作 ORM 之外的逻辑 |
| **schemas（出入参）** | `app/schemas/` | 用 Pydantic v2 定义请求体/响应体/分页模型，做字段校验与序列化 | 禁止含业务逻辑；禁止复用 ORM 模型直接当出入参 |
| **models（ORM）** | `app/models/` | SQLAlchemy 2.x 声明式模型，定义表、字段、关系 | 禁止含业务逻辑；禁止在模型内做外部 IO |
| **services（业务）** | `app/services/` | 业务规则、事务边界、编排多个 model/rag/analytics 调用 | 禁止接收/返回 FastAPI 的 Request/Response 对象；禁止拼接 HTTP 响应 |
| **agent（智能体）** | `app/agent/` | 定义 Agent 工具（Tool）、工具调用循环、系统提示词、决策编排 | 禁止直接写 SQL；**Agent 必须经 services/tools 访问数据** |
| **rag（知识库）** | `app/rag/` | 文档解析→清洗→切分→Embedding→写入 Chroma→相似检索 | 禁止与业务事务耦合；禁止硬编码模型 |
| **analytics（分析）** | `app/analytics/` | 学习时长统计、任务完成率、知识掌握度、报告生成 | 禁止直接对外暴露 HTTP |
| **core（配置与安全）** | `app/core/` | `.env` 配置加载、JWT 签发校验、密码哈希、全局常量 | 禁止依赖上层业务模块 |
| **db** | `app/db/` | engine、SessionLocal、建表初始化 | 禁止在 db 层写业务规则 |

**依赖方向铁律**：`api` 不直接依赖其它 `api`；`services` 之间可互相调用但**禁止循环依赖**；`agent` 通过 `services` 或 `agent/tools.py` 中的封装函数访问数据，**Agent 绝不直接访问数据库或 ORM**（对应需求文档第 19 章）。

**Agent 工具清单（MVP 必须实现，共 12 个）**：
`get_user_profile()`、`get_learning_records()`、`get_tasks()`、`get_knowledge_mastery()`、`get_learning_statistics()`、`search_knowledge_base()`、`create_task()`、`update_task()`、`get_learning_plan()`、`generate_learning_plan()`、`adjust_learning_plan()`、`generate_learning_report()`。
- `get_learning_plan()`：读取当前 `active` 计划及其条目（供周视图课表与对话展示）。
- `generate_learning_plan()`：生成**全新计划版本**（`version` 自增，旧的置 `archived`）。
- `adjust_learning_plan()`：基于现有计划**调整**，新建新版本并将 `parent_plan_id` 指向被调整版本，用于 diff 展示、支持回滚（对应需求文档第 13、14 章）。

---

## 5. API 设计规范

### 5.1 统一前缀
- 所有业务接口统一挂载 **`/api/v1`**，例如 `POST /api/v1/auth/login`。
- 健康检查除外：`GET /health`（不带版本前缀）。

### 5.2 统一响应体
所有接口（含错误）返回统一结构：
```json
{ "code": 0, "message": "success", "data": {} }
```
- `code`：业务状态码，**`0` 表示成功**，非 0 表示失败。
- `message`：人类可读提示，成功固定 `"success"`。
- `data`：业务数据；无数据时为 `null`。

### 5.3 分页规范
分页接口的 `data` 固定为：
```json
{ "items": [], "total": 0, "page": 1, "page_size": 10 }
```
- 请求参数统一为 `page`（从 1 开始，默认 1）、`page_size`（默认 10，上限 100）。
- `total` 为满足条件的总记录数。
- **实现约束（P4 发现，FastAPI 0.143.2）**：`Annotated[PaginationParams, Query()]` 查询参数模型**仅当它是该端点唯一 query 字段时才被展开**（`dependencies/utils.py` 的 `len(fields) == 1` 分支）。列表端点若还需其他标量 Query 参数（如 `status` 筛选），**不得**混用查询参数模型——模型不展开时会被误判为必填的单一 query 参数导致 422；此时分页参数应改为逐个标量声明（参照 `api/v1/goals.py` 的 `list_goals`，校验规则与 `PaginationParams` 完全一致）。仅有分页参数的列表端点继续沿用查询参数模型写法（全仓既有惯例）。

### 5.4 错误码约定

| code | 含义 | HTTP 状态 |
|---|---|---|
| 0 | 成功 | 200 |
| 1001 | 参数校验失败 | 422 |
| 1002 | 用户名或密码错误 | 401 |
| 1003 | Token 无效或已过期 | 401 |
| 1004 | 无权限访问该资源 | 403 |
| 1005 | 资源不存在 | 404 |
| 1006 | 资源已存在（唯一冲突） | 409 |
| 1007 | 业务规则冲突 | 400 |
| 2000 | 文件类型不支持 | 400 |
| 2001 | 文档解析失败 | 500 |
| 3000 | LLM 调用失败 | 502 |
| 3001 | 向量库/检索失败 | 500 |
| 5000 | 服务器内部错误 | 500 |

**实现要求**：通过全局异常处理器（`app/main.py`）把 `HTTPException`、Pydantic 校验错误、自定义 `BizException` 统一转换为上述响应体，**任何接口不得返回裸结构**。

---

## 6. 数据库表清单与字段

> 数据库：SQLite；ORM：SQLAlchemy 2.x；类型列为逻辑类型。
> 通用约定：主键 `id` 统一 `INTEGER` 自增；时间字段统一 `DATETIME`（UTC）；所有时间字段默认非空；外键命名 `<表名单数>_id`；JSON 类字段在 SQLite 中以 `TEXT` 存储 JSON 字符串。
> MVP 表共 **15 张**：`users` `user_profiles` `learning_goals` `learning_plans` `learning_plan_items` `courses` `tasks` `learning_records` `knowledge_items` `knowledge_chunks` `mistakes` `knowledge_mastery` `agent_conversations` `agent_messages` `learning_reports`。
> 时间/日期类字段若允许为空，会在「可空」列显式标注；未标注者默认非空。

### 6.1 users（用户账号）
| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| id | INTEGER | 否 | 主键，自增 |
| username | VARCHAR(50) | 否 | 登录名，全局唯一 |
| email | VARCHAR(120) | 是 | 邮箱，唯一（可空时需业务去重处理） |
| hashed_password | VARCHAR(255) | 否 | bcrypt 哈希，禁止存明文 |
| is_active | BOOLEAN | 否 | 默认 true，禁用后不可登录 |
| created_at | DATETIME | 否 | 创建时间 |
| updated_at | DATETIME | 否 | 更新时间 |

### 6.2 user_profiles（用户学习档案）
| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| id | INTEGER | 否 | 主键 |
| user_id | INTEGER | 否 | 外键 users.id，唯一（一人一档） |
| name | VARCHAR(50) | 是 | 姓名 |
| school | VARCHAR(120) | 是 | 学校 |
| major | VARCHAR(120) | 是 | 专业 |
| grade | VARCHAR(20) | 是 | 年级，如「大二」 |
| current_goal_type | VARCHAR(30) | 是 | 当前目标：考研/保研/就业/比赛 |
| interest_directions | TEXT | 是 | 兴趣方向，JSON 数组字符串 |
| daily_study_minutes | INTEGER | 否 | 每日可学习时长（分钟），范围 15–600，默认 60；供学习计划生成时估算每日可安排容量 |
| created_at | DATETIME | 否 | 创建时间 |
| updated_at | DATETIME | 否 | 更新时间 |

### 6.3 learning_goals（学习目标）
| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| id | INTEGER | 否 | 主键 |
| user_id | INTEGER | 否 | 外键 users.id |
| title | VARCHAR(200) | 否 | 目标名称，如「6个月掌握机器学习」 |
| goal_type | VARCHAR(50) | 是 | 目标类型 |
| description | TEXT | 是 | 目标描述 |
| start_date | DATE | 是 | 开始时间 |
| end_date | DATE | 是 | 截止时间 |
| status | VARCHAR(20) | 否 | active/completed/archived，默认 active |
| roadmap | TEXT | 是 | AI 拆解出的知识树，JSON 字符串，形如 `{"name":"机器学习","children":[...]}`，最多 4 层 |
| roadmap_updated_at | DATETIME | 是 | 最近一次拆解时间 |
| created_at | DATETIME | 否 | 创建时间 |
| updated_at | DATETIME | 否 | 更新时间 |

> **目标拆解约定**：AI 拆解成功后，将知识树写入本表 `roadmap` 并更新 `roadmap_updated_at`；同时把知识树的**叶子节点**写入 `knowledge_mastery`（初始 `mastery_score=0`，`source='goal_breakdown'`），用于后续掌握度聚合与薄弱点分析。

### 6.4 learning_plans（计划版本）
| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| id | INTEGER | 否 | 主键 |
| user_id | INTEGER | 否 | 外键 users.id |
| goal_id | INTEGER | 是 | 外键 learning_goals.id |
| title | VARCHAR(200) | 否 | 计划标题 |
| version | INTEGER | 否 | 版本号，每次重新规划自增 |
| status | VARCHAR(20) | 否 | active/archived，默认 active |
| parent_plan_id | INTEGER | 是 | 外键 learning_plans.id，指向被调整的上一版计划，用于 diff 展示 |
| source | VARCHAR(20) | 否 | agent/manual |
| adjust_reason | TEXT | 是 | Agent 调整计划时写给用户的理由；`parent_plan_id` 非空时必填，`source=manual` 时为空 |
| start_date | DATE | 否 | 计划起始日期（非空；`active` 判定与重叠判定的依据） |
| end_date | DATE | 否 | 计划结束日期（非空；必须 `end_date >= start_date`） |
| created_at | DATETIME | 否 | 创建时间 |
| 约束 | — | — | ① `end_date >= start_date`（数据库层与应用层双重校验）；② 同一 user 下，日期区间与当前 active 计划重叠的计划最多一个；③ 生成/调整一律新建 version，旧版本置 archived，**禁止原地修改** |

> **设计意图**：动态学习计划是本项目最核心的差异化功能（对应需求文档第 13、14 章）。每次生成或调整计划都新建一个 version、旧的置 archived，故**不能**用 `tasks`（原地修改）承载——`tasks` 既画不出周视图的时间网格，也无法保留「原计划 → 新计划」的 diff 与回滚能力。
> **`adjust_reason` 用途**：对应需求文档第 14 章 Agent 必须向用户解释调整原因（如「检测到你本周 Transformer 学习任务未完成，我已经将任务调整到周六下午，并适当减少周六其他低优先级任务。」）。该理由必须落库并在前端 P12 的 diff 视图中与条目改动一并展示，**禁止只存 diff 不存解释**。
> **多周并存约定**：允许本周与下周的计划同时存在（二者日期区间不重叠）。`GET /api/v1/plans/current` 的语义固定为「返回 `start_date <= 今天 <= end_date` 且 `status=active` 的计划」；生成下周计划时**不得**归档本周尚未结束的计划，避免周视图突然只剩一周。
> **`start_date` / `end_date` 非空约定**：这两个字段同时是 `active` 判定（`start_date <= 今天 <= end_date`）与「重叠计划最多一个」约束的共同依据。一个没有起止日期的学习计划本身没有意义；若允许其可空，重叠判定与当前计划查询将只能在特定数据下才暴露问题，故限定为非空并强制 `end_date >= start_date`。**注意与 6.3 `learning_goals` 区分**：目标的 `start_date` / `end_date` **保持可空不变**，以支持「先建目标、后补时间」；仅计划（`learning_plans`）强制非空。

### 6.5 learning_plan_items（计划条目）
| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| id | INTEGER | 否 | 主键 |
| plan_id | INTEGER | 否 | 外键 learning_plans.id |
| plan_date | DATE | 否 | 安排在周几 |
| start_time | TIME | 是 | 开始时间，如 19:00 |
| end_time | TIME | 是 | 结束时间，如 20:30 |
| topic | VARCHAR(200) | 否 | 本次学什么，如「线性代数：特征值」 |
| task_id | INTEGER | 是 | 外键 tasks.id；「休息/复习」类条目可空 |
| estimated_minutes | INTEGER | 是 | 预计时长 |
| priority | VARCHAR(10) | 是 | low/medium/high |
| status | VARCHAR(20) | 否 | planned/done/skipped，默认 planned |
| created_at | DATETIME | 否 | 创建时间 |
| 约束 | — | — | (plan_id, plan_date, start_time) 联合唯一，避免同一时间段冲突 |

> **设计意图**：周视图课表 = 查 `active` plan 的 items 按 `plan_date × 时间段` 排网格；调整 diff = 对比 `parent_plan_id` 与当前 plan 的 items。

### 6.6 courses（课程）
| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| id | INTEGER | 否 | 主键 |
| user_id | INTEGER | 否 | 外键 users.id |
| name | VARCHAR(120) | 否 | 课程名称，如「深度学习」 |
| description | TEXT | 是 | 课程描述 |
| teacher | VARCHAR(50) | 是 | 授课教师 |
| semester | VARCHAR(30) | 是 | 学期 |
| created_at | DATETIME | 否 | 创建时间 |

### 6.7 tasks（学习任务）
| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| id | INTEGER | 否 | 主键 |
| user_id | INTEGER | 否 | 外键 users.id |
| goal_id | INTEGER | 是 | 外键 learning_goals.id，可空 |
| course_id | INTEGER | 是 | 外键 courses.id，可空 |
| title | VARCHAR(200) | 否 | 任务名称，如「学习 Transformer Attention」 |
| description | TEXT | 是 | 任务描述 |
| knowledge_points | TEXT | 是 | 所属知识点，JSON 数组字符串（如 `["Transformer","Attention","QKV","Multi-Head Attention"]`）；一个任务可挂多个知识点 |
| priority | VARCHAR(10) | 否 | low/medium/high，默认 medium |
| estimated_minutes | INTEGER | 是 | 预计耗时（分钟） |
| actual_minutes | INTEGER | 是 | 实际花费分钟数（由关联学习记录回填） |
| deadline | DATETIME | 是 | 截止时间 |
| scheduled_date | DATE | 是 | 计划执行日期（Agent 生成计划时写入） |
| status | VARCHAR(20) | 否 | todo/in_progress/done/review，默认 todo |
| source | VARCHAR(20) | 否 | manual/agent，标识手工创建或 Agent 生成 |
| created_at | DATETIME | 否 | 创建时间 |
| updated_at | DATETIME | 否 | 更新时间 |
| completed_at | DATETIME | 是 | 完成时间，状态置 done 时写入 |

### 6.8 learning_records（学习记录）
| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| id | INTEGER | 否 | 主键 |
| user_id | INTEGER | 否 | 外键 users.id |
| task_id | INTEGER | 是 | 外键 tasks.id，可空 |
| course_id | INTEGER | 是 | 外键 courses.id，可空 |
| content | TEXT | 否 | 学习内容 |
| duration_minutes | INTEGER | 否 | 学习时长（分钟） |
| achievement | TEXT | 是 | 学习成果 |
| problems | TEXT | 是 | 遇到的问题 |
| knowledge_points | TEXT | 是 | 本次学习涉及的知识点，JSON 数组字符串；新增/修改/删除本记录后据此重算 `knowledge_mastery` |
| mastery_level | INTEGER | 是 | 用户自评掌握程度 0–100（掌握度聚合的**输入**，区别于 `knowledge_mastery.mastery_score`） |
| study_date | DATE | 否 | 学习日期（用于按天统计） |
| created_at | DATETIME | 否 | 创建时间 |

### 6.9 knowledge_items（知识库文档）
| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| id | INTEGER | 否 | 主键 |
| user_id | INTEGER | 是 | 外键 users.id；`scope=personal` 必填，`scope=public` 为 NULL |
| title | VARCHAR(200) | 否 | 文档标题 |
| source_type | VARCHAR(20) | 否 | pdf/md/txt/docx/pptx/note |
| file_path | VARCHAR(500) | 是 | 原始文件路径（note 类型可空） |
| scope | VARCHAR(20) | 否 | personal/public，默认 personal（对应需求的双层知识库） |
| status | VARCHAR(20) | 否 | pending/parsing/indexed/failed，默认 pending |
| error_msg | TEXT | 是 | 解析或向量化失败时的错误原因，`status=failed` 时必填 |
| chunk_count | INTEGER | 否 | 切分后的分块数，默认 0 |
| created_at | DATETIME | 否 | 创建时间 |
| updated_at | DATETIME | 否 | 更新时间 |

> **双层知识库可见性与归属（定稿）**：
> - `scope=public`：**系统预置、只读**，学生不可新增/修改/删除；此类记录 `user_id` 为 `NULL`，检索时对所有用户可见。
> - `scope=personal`：**学生上传一律为该值**，仅本人可见；列表、检索、删除均按 `user_id` 过滤。
> - **种子数据要求**：必须在 `data/public_kb/` 预置 **3-5 篇真实课程资料**（如机器学习基础、线性代数要点、概率论公式表、数据结构速查），由 `scripts/init_data.py` 在初始化时导入并向量化；否则演示「个人库 / 公共库 / 两者结合」三档切换时公共库那档为空。

### 6.10 knowledge_chunks（知识分块）
| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| id | INTEGER | 否 | 主键 |
| item_id | INTEGER | 否 | 外键 knowledge_items.id |
| user_id | INTEGER | 是 | 外键 users.id，冗余便于按用户过滤（public 可空） |
| chunk_index | INTEGER | 否 | 分块序号，从 0 开始 |
| content | TEXT | 否 | 分块文本内容 |
| embedding_id | VARCHAR(100) | 是 | Chroma 中的向量记录 id，用于删除/对齐 |
| created_at | DATETIME | 否 | 创建时间 |

### 6.11 mistakes（错题，MVP 无录入界面，V2 提供完整功能）
| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| id | INTEGER | 否 | 主键 |
| user_id | INTEGER | 否 | 外键 users.id |
| course_id | INTEGER | 是 | 外键 courses.id |
| knowledge_point | VARCHAR(200) | 是 | 关联知识点 |
| question | TEXT | 否 | 题目内容 |
| user_answer | TEXT | 是 | 用户作答 |
| correct_answer | TEXT | 是 | 正确答案 |
| analysis | TEXT | 是 | 错因分析 |
| created_at | DATETIME | 否 | 创建时间 |

> **单知识点约定**：一道错题只对应一个 `knowledge_point`（保持单数）；若某题确实跨多个知识点，应拆成多条错题记录，不引入错题-知识点多对多关系。
> **MVP 数据来源说明**：mistakes 表在 MVP **无录入界面**（错题系统属 V2 范围）。MVP 期间的错题数据由 `scripts/init_data.py` 的**种子数据**提供（**8 道**，分散在多个知识点上），用于演示掌握度的**错题扣分效果**；扣分规则本身是**生效的，不是占位逻辑**（见 6.12）。

### 6.12 knowledge_mastery（知识掌握度）
| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| id | INTEGER | 否 | 主键 |
| user_id | INTEGER | 否 | 外键 users.id |
| knowledge_point | VARCHAR(200) | 否 | 知识点名称（**单数**命名，与 tasks/learning_records 的复数 `knowledge_points` 区分） |
| mastery_score | FLOAT | 否 | 掌握度 0–100 |
| source | VARCHAR(20) | 否 | self_report/record/quiz/goal_breakdown/agent，标识来源（`quiz` 为 V2 接入，MVP 不写入） |
| updated_at | DATETIME | 否 | 最近更新时间 |
| 约束 | — | — | (user_id, knowledge_point) 联合唯一 |

> **掌握度计算口径与更新时机（定稿）**：
> - **关系**：`learning_records.mastery_level` 是**输入**（学生本次学习后的自评）；`knowledge_mastery.mastery_score` 是**输出**（系统聚合出的掌握度）。两者不是同一个东西，禁止混用。
> - **聚合公式（必须写入代码注释）**：`mastery_score = clamp(旧 mastery_score × 0.7 + 本次自评 × 0.3, 0, 100)`。知识点首次出现时旧值取 0（例：首次自评 60 → 0×0.7 + 60×0.3 = 18）。
> - **错题扣分**：该知识点下每有一道错题，−3 分，下限 0。
> - **薄弱点过滤（P4 定稿）**：薄弱点分析与 Dashboard 展示中，必须排除「`source='goal_breakdown'` 且 `mastery_score=0`」的知识点。这类点由目标拆解生成、尚未真正学习，不得列为薄弱知识点。一旦该点通过学习记录或自评被更新过，即恢复正常参与排序。
> - **时间衰减**：距最近一次学习记录超过 30 天的知识点，每满 7 天 −2 分，下限 0。衰减基准为该用户该知识点最后一条学习记录的 `study_date`（`max(study_date)`，含未自评记录），**禁止**以 `updated_at` 为基准——掌握度重放本身会刷新 `updated_at`，以其为基准会导致全量重算不幂等；无任何学习记录的知识点（零分待学点）不做衰减。`updated_at` 仅表示最近更新时间。
> - **触发时机**：新增/修改/删除学习记录后立即重算该记录涉及的知识点；每日首次访问 Dashboard 时对当前用户跑一次全量衰减检查。
> - **全量重算**：必须提供 `recalculate_all(user_id)` 函数，供数据修复与答辩演示使用。
> - **MVP 采集源收窄为 3 个**：学习记录自评（主）、错题（扣分）、目标拆解（仅初始化 0 分）。`source` 枚举保留 `quiz` 值但 MVP 不写入，标注「V2 接入」。

### 6.13 agent_conversations（Agent 会话）
| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| id | INTEGER | 否 | 主键 |
| user_id | INTEGER | 否 | 外键 users.id |
| title | VARCHAR(200) | 是 | 会话标题（可由首条消息生成） |
| created_at | DATETIME | 否 | 创建时间 |
| updated_at | DATETIME | 否 | 更新时间 |

### 6.14 agent_messages（Agent 消息）
| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| id | INTEGER | 否 | 主键 |
| conversation_id | INTEGER | 否 | 外键 agent_conversations.id |
| role | VARCHAR(20) | 否 | user/assistant/tool/system |
| content | TEXT | 否 | 消息内容 |
| tool_name | VARCHAR(50) | 是 | 当 role=tool 时记录工具名 |
| tool_calls | TEXT | 是 | role=assistant 且触发工具调用时，存 OpenAI 格式的 tool_calls JSON（含调用参数） |
| tool_call_id | VARCHAR(64) | 是 | role=tool 时对应哪次调用（关联 assistant 消息 tool_calls 中的 id） |
| created_at | DATETIME | 否 | 创建时间 |

> **设计意图**：前端需把工具调用过程可视化展示在对话流里（折叠卡片显示「正在调用 `get_learning_statistics(days=7)`」→ 完成后显示返回摘要）。仅存 `tool_name` 还原不出调用参数与返回内容，故补 `tool_calls` / `tool_call_id`。

### 6.15 learning_reports（学习成长报告）
| 字段 | 类型 | 可空 | 说明 |
|---|---|---|---|
| id | INTEGER | 否 | 主键 |
| user_id | INTEGER | 否 | 外键 users.id |
| report_type | VARCHAR(10) | 否 | daily/weekly/monthly |
| period_start | DATE | 否 | 统计开始日期 |
| period_end | DATE | 否 | 统计结束日期 |
| summary | TEXT | 是 | 报告摘要（面向用户的结论） |
| content | TEXT | 是 | 结构化报告内容，JSON 字符串 |
| created_at | DATETIME | 否 | 创建时间 |

---

## 7. 前端约定

### 7.1 路由表（Vue Router）

| path | 组件（views/） | 是否需要登录 | 说明 |
|---|---|---|---|
| `/login` | `LoginView.vue` | 否 | 登录页 |
| `/` | 重定向到 `/dashboard` | 是 | 默认跳转 |
| `/dashboard` | `DashboardView.vue` | 是 | 学习中心首页（统计卡片 + 趋势 + 掌握度 + AI 建议 + 「本周计划」摘要卡片，点击跳 `/plans`） |
| `/profile` | `ProfileView.vue` | 是 | 用户学习档案 |
| `/goals` | `GoalsView.vue` | 是 | 学习目标管理 |
| `/plans` | `PlanView.vue` | 是 | 学习计划（周视图课表 + 版本调整 diff） |
| `/tasks` | `TasksView.vue` | 是 | 学习任务管理（含任务状态流转） |
| `/learning-records` | `LearningRecordsView.vue` | 是 | 学习记录 |
| `/knowledge-base` | `KnowledgeBaseView.vue` | 是 | RAG 知识库（上传/列表/检索） |
| `/ai-agent` | `AgentView.vue` | 是 | AI Agent 对话（流式输出） |
| `/reports` | `ReportsView.vue` | 是 | 学习成长报告（日报/周报/月报） |
| `/settings` | `SettingsView.vue` | 是 | 设置 |

全局前置守卫：无 token 且目标路由需登录 → 跳 `/login`；已登录访问 `/login` → 跳 `/dashboard`。

### 7.2 页面 ↔ 后端接口对应关系

| 页面 | 主要接口 |
|---|---|
| Login | `POST /api/v1/auth/register`、`POST /api/v1/auth/login`、`GET /api/v1/auth/me` |
| Dashboard | `GET /api/v1/dashboard/overview`、`GET /api/v1/dashboard/trend`、`GET /api/v1/dashboard/mastery`、`GET /api/v1/dashboard/suggestions`、`GET /api/v1/plans/current`（「本周计划」摘要卡片） |
| Profile | `GET/PUT /api/v1/profile` |
| Goals | `GET/POST /api/v1/goals`、`GET/PUT/DELETE /api/v1/goals/{id}`、`POST /api/v1/goals/{id}/breakdown`（AI 拆解） |
| Tasks | `GET/POST /api/v1/tasks`、`GET/PUT/DELETE /api/v1/tasks/{id}`、`PATCH /api/v1/tasks/{id}/status` |
| Learning Records | `GET/POST /api/v1/records`、`GET/PUT/DELETE /api/v1/records/{id}`、`GET /api/v1/records/timeline`（按天聚合时长，无记录日补 0，供图表）、`GET /api/v1/records/stats`（本周学习时长 / 连续学习天数 / 记录条数） |
| Knowledge Base | `POST /api/v1/knowledge/upload`、`GET /api/v1/knowledge/items`、`DELETE /api/v1/knowledge/items/{id}`、`POST /api/v1/knowledge/search` |
| AI Agent | `POST /api/v1/agent/conversations`、`GET /api/v1/agent/conversations`、`PATCH /api/v1/agent/conversations/{id}`（重命名）、`DELETE /api/v1/agent/conversations/{id}`（删除）、`GET /api/v1/agent/conversations/{id}/messages`、`POST /api/v1/agent/chat`（SSE 流式） |
| Plan（`/plans`） | `GET /api/v1/plans`（历史版本列表）、`GET /api/v1/plans/current`（当前 active 计划 + 条目，供周视图课表）、`POST /api/v1/plans/generate`（生成新版本）、`POST /api/v1/plans/{id}/adjust`（调整并生成新版本，`parent_plan_id` 指向原版本，写入 `adjust_reason`）、`GET /api/v1/plans/{id}/diff`（对比 `parent_plan_id`，展示「原计划 → 新计划」+ 调整原因） |
| Reports | `GET /api/v1/reports`、`GET /api/v1/reports/{id}`、`POST /api/v1/reports/generate` |

### 7.3 Axios 封装与拦截器约定（`src/api/request.ts`）
- **实例**：`baseURL = import.meta.env.VITE_API_BASE_URL`（即 `http://localhost:8000/api/v1`），`timeout = 30000`。
- **请求拦截器**：从 Pinia/localStorage 读取 token，若存在则注入 `Authorization: Bearer <token>`。
- **响应拦截器**：
  - 收到 `{code, message, data}` 时，`code === 0` → 直接返回 `data`（业务层无需再解包）；
  - `code !== 0` → `ElMessage.error(message)` 并 `Promise.reject`；
  - HTTP `401` 或 `code` 为 `1002/1003` → 清除 token、跳转 `/login`；
  - 网络错误统一提示「网络异常，请稍后重试」。
- **类型**：所有接口函数返回 `Promise<T>`，`T` 定义在 `src/types/`，与后端 schema 字段名保持一致（后端 snake_case 需在前端类型中保留，避免二次映射错误）。
- **Agent 流式**：`/agent/chat` 使用 `fetch` + `ReadableStream`（引导 SSE），不走 Axios。

### 7.4 Token 存储方式
- 存储介质：`localStorage`，key 固定为 **`smartlearn_token`**。
- 同步维护：Pinia `stores/user.ts` 持有 `token` 与 `userInfo`，登录写入、登出清除，页面刷新时从 localStorage 恢复。
- 禁止把 token 放 URL 参数；禁止在日志中打印 token。

---

## 8. 编码规范

### 8.1 后端（Python）
- **类型注解**：所有函数签名必须写全 type hints（参数与返回值），禁止裸 `def f(x)`。
- **文档字符串**：所有模块、类、公开函数必须有 docstring（说明用途、参数、返回、异常）。
- **命名**：变量/函数 `snake_case`、类 `PascalCase`、常量 `UPPER_SNAKE_CASE`。
- **校验**：**所有接口出入参必须由 Pydantic v2 模型校验**，路由处理函数中不得出现未校验的 `dict` 作为入参。
- **ORM**：SQLAlchemy 2.x 风格（`Mapped[T]` + `mapped_column`），关系用 `relationship`，禁止在路由层直接写 SQL。
- **配置**：所有密钥/地址/模型名从 `core/config.py`（pydantic-settings 读取 `.env`）获取，**禁止硬编码**。
- **异常**：业务错误抛自定义 `BizException(code, message)`，由全局异常处理器统一转换。
- **无裸响应**：路由返回值统一经响应包装，保证 `{code, message, data}`。
- **JSON 字段序列化（`app/models/types.py`）**：定义**两个** `TypeDecorator`，DB 侧均以 `TEXT` 存储 JSON 字符串（写入用 `json.dumps`、读取用 `json.loads`），但 **Python 侧类型与 `None` 处理分离**：
  - **`JSONListType`**：Python 侧为 `list[str]`；读到 `NULL`/`None` 统一返回 `[]`（空数组是自然默认）。适用字段：`tasks.knowledge_points`、`learning_records.knowledge_points`、`user_profiles.interest_directions`。
  - **`JSONType`**：Python 侧为 `Any`（`dict` / `list[dict]`）；读到 `NULL`/`None` **原样返回 `None`**，**不得强行返回 `{}`**。适用字段：`learning_goals.roadmap`、`learning_reports.content`、`agent_messages.tool_calls`。
    - **原因**：`learning_goals.roadmap = None` 表示「**从未拆解过**」，是有语义的状态；若被替换成 `{}`，前端将无法区分「从未拆解」与「拆解结果为空」两种情况。
  - 上述字段统一声明为 `Mapped[...] = mapped_column(JSONListType / JSONType)`。**services / schemas / api 各层禁止再手动 `json.loads`/`json.dumps`**；前端 `src/types/` 中，`JSONListType` 对应字段声明为 `string[]`，`JSONType` 对应字段声明为可选（`... | null`）。

### 8.2 前端（Vue 3 + TS）
- 组件统一使用 **`<script setup lang="ts">`**，禁止 Options API。
- 命名：组件文件 `PascalCase.vue`；变量/函数 `camelCase`；常量 `UPPER_SNAKE_CASE`；Store 用 `useXxxStore`。
- 类型：接口请求/响应类型集中在 `src/types/`，禁止大面积 `any`；与后端字段**保持 snake_case**，仅展示层做 camelCase 转换。
- 状态：跨组件共享状态放 Pinia，禁止滥用全局事件总线。
- 请求：所有网络请求经 `src/api/` 统一封装，禁止在组件内直接 `axios` 调用。
- 样式：优先使用 Element Plus 组件与主题变量，避免散落硬编码色值。

### 8.3 命名对照与数据契约
- **后端内部**：全程 `snake_case`（数据库列名、Pydantic 字段、JSON 传输字段）。
- **前端传输**：与后端对齐使用 `snake_case` 的原始字段名；仅在模板展示需要时局部转 camelCase。
- **统一约定**：JSON 传输字段一律 `snake_case`，前后端**不做自动大小写转换**，以本文件为准，避免隐式映射 bug。

### 8.4 通用
- 提交信息、注释使用中文（与团队惯例一致），代码标识符使用英文。
- 每个功能模块需提供最小可运行路径（Happy Path）后再做异常处理。
- 涉及 LLM / Embedding 的调用点必须做超时与失败兜底（对应错误码 3000/3001）。

---

## 附：MVP 优先级与闭环映射

| MVP 功能 | 对应页面 | 对应后端模块 | 闭环环节 |
|---|---|---|---|
| ① 用户档案 | `/profile` | `api/profile` + `services/profile` | 记录（画像基础） |
| ② 学习目标 | `/goals` | `api/goals` + `services/goal` + agent 拆解 | 规划 |
| ③ 学习任务 | `/tasks` | `api/tasks` + `services/task` | 执行 |
| ④ 学习记录 | `/learning-records` | `api/records` + `services/record` | 记录 |
| ⑤ Dashboard | `/dashboard` | `api/dashboard` + `analytics` | 反馈 |
| ⑥ RAG 知识库 | `/knowledge-base` | `api/knowledge` + `rag` | 知识支撑 |
| ⑦ AI Agent | `/ai-agent` | `api/agent` + `agent` | 分析 / 再规划 |
| 学习计划（⑦ 子能力落地） | `/plans` / `/ai-agent` | `api/plans` + `services/plan` + agent 工具 | 规划 / 再规划 |
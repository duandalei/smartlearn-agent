# 彭城智学 SmartLearn Agent

面向高校学生的 **AI 学习成长智能体**：整合学习目标、任务、学习记录与个人知识库，构建个人学习画像，并利用 Agent 主动分析学习状态、动态调整学习计划，形成 `记录 → 分析 → 规划 → 执行 → 反馈 → 再规划` 的闭环。

> 技术契约以 `docs/PROJECT_CONTEXT.md` 为准。

---

## 一、环境要求

| 依赖 | 版本要求 | 说明 |
|---|---|---|
| Python | 3.10+（推荐 3.11 / 3.12） | 后端 FastAPI |
| Node.js | 18+（推荐 20 / 22） | 前端 Vite |
| npm | 9+ | 随 Node 安装 |
| Git | 任意 | 版本管理 |

> 说明：本项目 **不使用 MySQL / PostgreSQL**，数据库为 SQLite；向量库为本地 Chroma。

**一键安装串链**（首次克隆后）：

```bash
# 1) 后端依赖
cd backend && python -m venv .venv && source .venv/Scripts/activate   # Windows cmd: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # 然后编辑 .env 填入 LLM/Embedding 的 key（见「九、FAQ」）

# 2) 前端依赖
cd ../frontend && npm install

# 3) 一键启动（仓库根目录）
cd .. && start.bat      # macOS / Linux / Git-Bash: bash start.sh
```

> 依赖安装失败时：先核对 Python/Node 是否满足上表最低版本；国内网络可为 pip/npm 配置镜像源（如清华 TUNA 镜像）。

---

## 二、目录结构（骨架）

```
smartlearn/
├── backend/                # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/         # 路由层（health / 后续业务模块）
│   │   ├── core/           # config.py（配置）、response.py（统一响应与异常）
│   │   ├── db/             # session.py（engine / SessionLocal / get_db）
│   │   └── main.py         # 应用入口（CORS、异常处理、路由挂载）
│   ├── requirements.txt
│   ├── .env.example
│   ├── run.sh / run.bat
├── frontend/               # Vue 3 + TS + Vite
│   ├── src/
│   │   ├── api/            # request.ts（Axios 封装）
│   │   ├── layouts/        # MainLayout.vue（侧栏 + 顶栏 + 内容区）
│   │   ├── router/         # 路由表 + 全局守卫
│   │   ├── stores/         # Pinia（user）
│   │   └── views/          # 各页面（骨架占位）
│   ├── .env.development
│   └── vite.config.ts
├── data/                   # 运行时数据（不进版本库；public_kb 除外）
├── docs/                   # 项目文档
├── start.sh / start.bat    # 一键启动（先后端后前端）
└── README.md
```

---

## 三、后端启动

```bash
cd backend

# 1) 创建并激活虚拟环境（推荐）
python -m venv .venv
# Windows (cmd):      .venv\Scripts\activate
# Windows (git-bash):  source .venv/Scripts/activate
# macOS / Linux:       source .venv/bin/activate

# 2) 安装依赖
pip install -r requirements.txt

# 3) 准备环境变量（首次运行可自动从模板生成）
cp .env.example .env      # Windows: copy .env.example .env

# 4) 启动服务
bash run.sh               # Windows: run.bat
# 或
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**一条命令启动后端（Windows）**：`backend\run.bat`

---

## 四、前端启动

```bash
cd frontend

# 1) 安装依赖
npm install

# 2) 启动开发服务器
npm run dev
```

**可选**：前端环境变量见 `frontend/.env.development`（`VITE_API_BASE_URL`）。

---

## 五、一键启动（推荐）

```bash
# Windows
start.bat

# macOS / Linux / Git-Bash
bash start.sh
```

先启动后端（8000），再启动前端（5173）。

---

## 五之二、演示数据一键重置

把运行环境恢复成「可演示的干净状态」（删除并重建 SQLite 库、向量库与上传目录，重建种子数据并对 4 篇公共知识库文档执行真实重新索引）：

```bash
# 先停止后端，再执行：
cd backend
python scripts/reset_demo_data.py --yes
# 脚本会自动使用 backend/.venv 的解释器执行子进程（无需手工激活 venv）；
# 若 .venv 不存在，则回退到当前 Python。
```

**参数语义**：

- `--yes`：跳过交互确认直接执行（不豁免占用检测与配置校验）；
- `--no-backup`：跳过备份步骤（默认会把数据库备份到 `data/_reset_backup/<YYYYmmdd-HHMMSS>/`，摘要会打印该路径）；
- 检测到后端仍在运行/数据库被占用时会直接退出并提示「请先停止后端再重置」，不会杀进程；
- 重复执行幂等，第二次不会报错；`.env` 与 `data/public_kb/` 永不被修改。

**预期摘要样例**（真实输出，分块数以实际切分为准）：

```
========== SmartLearn 演示数据重置完成 ==========
数据库路径: .../data/smartlearn.db（已重建）
演示账号: demo / 123456（仅供开发演示，请勿用于生产环境）
备份目录: .../data/_reset_backup/20261024-182015
公共知识库（4 篇，真实索引）:
  [OK] 机器学习核心概念速览 — 8 chunks
  [OK] 线性代数要点笔记：特征值与矩阵分解 — 8 chunks
  [OK] 概率论与数理统计公式表 — 8 chunks
  [OK] 数据结构常见考点速查 — 9 chunks
下一步: 启动后端与前端（start.bat / bash start.sh），以 demo / 123456 登录
==================================================
退出码: 0
```

**公共知识库索引确认**：启动后登录 `demo / 123456`，左侧菜单「知识库」可见 4 篇公共文档且状态为已索引；或调用 `GET /api/v1/knowledge/items` 按 `scope=public` 过滤核对为 4 条、`chunk_count > 0`。

**常见启动失败处理**：

- 8000 / 5173 端口被占用：重置脚本会提示「请先停止后端再重置」；手工释放可执行 `netstat -ano | findstr :8000` 找到 PID 后在任务管理器结束对应进程（或更换端口）；
- 重置后无法登录：核对摘要中的「数据库路径: …（已重建）」行与 4 篇 `[OK]` 分块行；缺任一项说明重置未成功，停后端后重新执行重置；仍失败按 `docs/DEMO_SCRIPT.md` 附录 A 的回滚指引从 `data/_reset_backup/` 恢复。

> **声明：本项目不提供 Docker 容器化与云部署**，仅支持上述本地运行方式。

---

## 六、访问地址

| 服务 | 地址 |
|---|---|
| 前端首页 | http://localhost:5173 |
| 后端健康检查 | http://localhost:8000/health |
| 后端 API 文档（Swagger） | http://localhost:8000/docs |

---

## 七、验证方式

1. **后端**：浏览器访问 http://localhost:8000/health，应返回
   ```json
   {"code":0,"message":"ok","data":{"status":"healthy"}}
   ```
2. **前端**：访问 http://localhost:5173，自动跳转 `/login`；以演示账号 `demo / 123456` 登录（重置后种子自带）进入主布局，左侧菜单可切换各页面。
3. **统一错误提示**：后端未启动时，前端操作会通过统一拦截器弹出「网络异常，请稍后重试」而非白屏。
4. **后端自动化测试**：`cd backend && pytest -q`（当前基线 206 passed）。
5. **前端构建**：`cd frontend && npm run build`（vue-tsc + vite，应 exit 0）。
6. **演示走查**：按 `docs/DEMO_SCRIPT.md` 的 5 分钟版分镜实际走一遍（前置检查 → 五幕 → 收尾幕）。

---

## 八、约定要点

- 所有业务接口统一前缀 `/api/v1`；健康检查为 `/health`（不带版本前缀）。
- 统一响应体：`{"code":0,"message":"success","data":{}}`，`code=0` 表示成功。
- 所有密钥 / 模型名 / 服务地址一律走 `.env`，**禁止硬编码**。
- JSON 传输字段统一 `snake_case`，前后端不做自动大小写转换。
- `data/` 为运行时产物（`smartlearn.db`、`chroma/`、`uploads/`），已加入 `.gitignore`。
---

## 九、FAQ（常见问题）

1. **端口被占用（8000 / 5173）**：后端占用 8000 时重置脚本会直接退出并提示「请先停止后端再重置」；查找占用进程：`netstat -ano | findstr :8000`（Windows）或 `lsof -i :8000`（macOS/Linux），结束后重试。
2. **LLM / Embedding key 未配置或失效**：`backend/.env` 需配置 `JWT_SECRET`（随机强密钥，可用 `python -c "import secrets; print(secrets.token_hex(32))"` 生成）、对话组 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`（OpenAI 兼容协议，如 DeepSeek）、向量化组 `EMBEDDING_*`（如硅基流动 BAAI/bge-m3，`EMBEDDING_*` 为空时逐项回退 `LLM_*`）。LLM 不可用时计划/报告走规则与模板降级，页面功能不受影响； Embedding 不可用时知识库索引走本地兜底模型。
3. **SQLite 数据库被锁定（database is locked）**：通常是后端仍在运行时执行了重置或手工改库——先停后端再操作；重置脚本内置占用检测，命中会拒绝执行而不是强行写入。
4. **Windows 中文路径 / 终端编码**：项目路径含中文不影响运行（本仓库即在中文用户名目录下开发验证）；若终端打印乱码，将终端代码页切为 UTF-8（`chcp 65001`）或使用 Windows Terminal。

---

## 十、数据集与开源组件说明

**数据集**：本项目**未使用任何外部受限数据集**。`data/public_kb/` 下 4 篇文档为课程笔记型自编材料（Markdown），仅用于知识库检索与 RAG 问答演示：

| 文件 | 标题 | 用途 |
|---|---|---|
| `ml_basics.md` | 机器学习核心概念速览 | 公共知识库种子 / 演示检索语料 |
| `linear_algebra_notes.md` | 线性代数要点笔记：特征值与矩阵分解 | 同上 |
| `probability_formulas.md` | 概率论与数理统计公式表 | 同上 |
| `ds_cheatsheet.md` | 数据结构常见考点速查 | 同上 |

**主要开源组件**（与 `backend/requirements.txt`、`frontend/package.json` 实际依赖一致）：

- 数据库：SQLite（标准库 sqlite3 驱动，零独立服务）；
- 后端：FastAPI + Uvicorn、SQLAlchemy 2.x（ORM）、pydantic / pydantic-settings（配置与校验）；
- 前端：Vue 3 + TypeScript + Vite、Pinia（状态）、Vue Router、Element Plus + @element-plus/icons-vue（UI）、ECharts（图表）、Axios（HTTP）；
- RAG：Chroma（本地向量库）、pypdf / python-docx / python-pptx / markdown（文档解析）；
- LLM：OpenAI 兼容 API（openai SDK，对话与 Embedding 双配置组）；
- 认证与密码：标准库 hmac（HS256 JWT）与 hashlib.pbkdf2_hmac（密码哈希），无第三方加密依赖。

---

## 十一、码道（CodeArts）在本项目中的使用说明

本项目全程使用**华为云码道（CodeArts）代码智能体**辅助开发，覆盖四个环节：

1. **需求环节**：以码道生成各阶段需求规格文档（`docs/specs/`），把口头需求落成可验收的条目（规则 + 验收条件 + 异常场景），例如动态计划调整规则、演示重置流程的边界定义；
2. **设计环节**：由码道产出技术设计文档（`docs/designs/`），包括进程模型裁决（如重置脚本的父子双进程模型）、接口契约与退出码表、风险清单，设计先行的习惯避免了多轮返工；
3. **编码环节**：按任务清单（`docs/tasks/`）分批由码道生成与修订代码，前后端契约（响应体、字段命名、SSE 协议）由文档链保持一致；
4. **测试辅助环节**：码道协助编写与修复后端 pytest 用例（当前 206 passed），并对失败用例做根因定位（如测试库隔离、日期敏感用例）；前端 W1–W12 走查由浏览器自动化完成（本机 Chrome 驱动），码道负责按走查结果修复问题。

相关文档链：`docs/specs/`（规格）→ `docs/designs/`（设计）→ `docs/tasks/`（任务）→ `docs/WALKTHROUGH_PLAN_REPORT_FRONTEND.md`（走查记录），可作为码道协作过程的追溯材料。
# 彭城智学 SmartLearn Agent

面向高校学生的 **AI 学习成长智能体**：整合学习目标、任务、学习记录与个人知识库，构建个人学习画像，并利用 Agent 主动分析学习状态、动态调整学习计划，形成 `记录 → 分析 → 规划 → 执行 → 反馈 → 再规划` 的闭环。知识库问答能力已并入 AI 助手（`/ai-agent`）。

> 本地单用户学习工具：FastAPI + SQLite + Vue 3 + Vite。
>
> **运行平台：仅支持 Windows 10 / 11。**

---

## 零、快速开始（推荐）

```bat
git clone https://github.com/duandalei/smartlearn-agent.git
cd smartlearn-agent
setup.bat
start.bat
```

浏览器打开 http://localhost:5173 ：

- **打开即用**：本地单用户，无需注册 / 登录，直接进入首页记录学习。

---

## 一、环境要求

| 依赖 | 版本要求 | 说明 |
|---|---|---|
| Python | 3.10+（推荐 3.11 / 3.12） | 后端 FastAPI |
| Node.js | 18+（推荐 20 / 22） | 前端 Vite |
| npm | 9+ | 随 Node 安装 |
| Git | 任意 | 版本管理 |

> 说明：本项目 **不使用 MySQL / PostgreSQL**，数据库为 SQLite；向量库为本地 Chroma。

**一键配置（推荐）**：

```bat
setup.bat
```

脚本会自动创建后端虚拟环境、安装前后端依赖、准备 `.env`，并在数据库不存在时初始化数据库（建表 + 本地用户）。之后运行 `start.bat` 即可。

<details>
<summary>手动配置（可选，逐步执行）</summary>

```bat
:: 1) 后端依赖
cd backend
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env

:: 2) 前端依赖
cd ..\frontend
npm install

:: 3) 一键启动（仓库根目录）
cd ..
start.bat
```

</details>

> 依赖安装失败时：先核对 Python/Node 是否满足上表最低版本；国内网络可为 pip/npm 配置镜像源（如清华 TUNA 镜像）。
>
> **首次启动自动化**：`start.bat` / `backend/run.bat` 会自动执行
> `backend/scripts/ensure_dev_env.py`（复制 `.env`）并在数据库不存在时运行
> `python -m app.db.init_db` 初始化数据库（建表 + 本地用户），无需手工建库。也可手动执行：
> `cd backend && python scripts/ensure_dev_env.py && python -m app.db.init_db`。

---

## 二、目录结构（骨架）

```
smartlearn-agent/
├── backend/                # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/         # 路由层（health / 后续业务模块）
│   │   ├── core/           # config.py（配置）、response.py（统一响应与异常）
│   │   ├── db/             # session.py（engine / SessionLocal / get_db）
│   │   └── main.py         # 应用入口（CORS、异常处理、路由挂载）
│   ├── requirements.txt
│   ├── .env.example
│   ├── run.bat
├── frontend/               # Vue 3 + TS + Vite
│   ├── src/
│   │   ├── api/            # request.ts（Axios 封装）
│   │   ├── layouts/        # MainLayout.vue（侧栏 + 顶栏 + 内容区）
│   │   ├── router/         # 路由表
│   │   ├── stores/         # Pinia（user）
│   │   └── views/          # 各页面（骨架占位）
│   ├── .env.development
│   └── vite.config.ts
├── data/                   # 运行时数据（不进版本库）
├── setup.bat               # 一键配置环境
├── scripts/                # setup_env.py（配置脚本）
├── start.bat               # 一键启动（先后端后前端）
└── README.md
```

---

## 三、后端启动

```bash
cd backend

# 1) 创建并激活虚拟环境（推荐）
python -m venv .venv
# Windows:      .venv\Scripts\activate

# 2) 安装依赖
pip install -r requirements.txt

# 3) 准备环境变量（启动脚本会自动处理，也可手动执行）
copy .env.example .env
python scripts\ensure_dev_env.py   # 复制 .env 模板

# 4) 启动服务
run.bat
# 或
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**一条命令启动后端（Windows）**：`backend\run.bat`

### 配置模型 API（可选）

编辑 `backend/.env`，按需填写 OpenAI 兼容接口：

```env
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
# 向量化可独立配置；留空则逐项回退 LLM_*
EMBEDDING_BASE_URL=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=
```

不配置也能正常使用目标、任务、学习记录与计划查看；AI 问答与在线向量化会提示未配置，
知识库索引会走本地兜底向量。

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

```bat
start.bat
```

先启动后端（8000），再启动前端（5173）。

> 已安装 Windows Terminal 时，后端与前端会以两个标签页开在同一个 Windows Terminal 窗口中（窗口名为 SmartLearn）；若在终端内运行 `start.bat`，则直接开在当前窗口。未安装 Windows Terminal 时回退为两个独立 cmd 窗口。

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
2. **前端**：访问 http://localhost:5173，直接进入主布局（本地单用户，无需登录），左侧菜单可切换各页面。
3. **统一错误提示**：后端未启动时，前端操作会通过统一拦截器弹出「网络异常，请稍后重试」而非白屏。
4. **后端自动化测试**：`cd backend && pytest -q`（当前基线 202 passed）。
5. **前端构建**：`cd frontend && npm run build`（vue-tsc + vite，应 exit 0）。

---

## 八、约定要点

- 所有业务接口统一前缀 `/api/v1`；健康检查为 `/health`（不带版本前缀）。
- 统一响应体：`{"code":0,"message":"success","data":{}}`，`code=0` 表示成功。
- 所有密钥 / 模型名 / 服务地址一律走 `.env`，**禁止硬编码**。
- JSON 传输字段统一 `snake_case`，前后端不做自动大小写转换。
- `data/` 为运行时产物（`smartlearn.db`、`chroma/`、`uploads/`），已加入 `.gitignore`。
---

## 九、FAQ（常见问题）

1. **端口被占用（8000 / 5173）**：`netstat -ano | findstr :8000` 找到 PID，结束后端进程后重试。
2. **LLM / Embedding key 未配置或失效**：见 [配置模型 API（可选）](#配置模型-api可选)。对话组 `LLM_*` 为 OpenAI 兼容协议（如 DeepSeek），向量化组 `EMBEDDING_*` 可独立指向其他服务（如硅基流动 BAAI/bge-m3），留空时逐项回退 `LLM_*`。LLM 不可用时计划/报告走规则与模板降级，页面功能不受影响；Embedding 不可用时知识库索引走本地兜底模型。
3. **SQLite 数据库被锁定（database is locked）**：通常是后端仍在运行时手工改库——先停后端再操作。
4. **Windows 中文路径 / 终端编码**：项目路径含中文不影响运行（本仓库即在中文用户名目录下开发验证）；若终端打印乱码，将终端代码页切为 UTF-8（`chcp 65001`）或使用 Windows Terminal。

---

## 十、数据集与开源组件说明

**数据集**：本项目未使用任何外部受限数据集；知识库内容由用户自行上传，仓库不附带演示文档。

**主要开源组件**（与 `backend/requirements.txt`、`frontend/package.json` 实际依赖一致）：

- 数据库：SQLite（标准库 sqlite3 驱动，零独立服务）；
- 后端：FastAPI + Uvicorn、SQLAlchemy 2.x（ORM）、pydantic / pydantic-settings（配置与校验）；
- 前端：Vue 3 + TypeScript + Vite、Pinia（状态）、Vue Router、Element Plus + @element-plus/icons-vue（UI）、ECharts（图表）、Axios（HTTP）；
- RAG：Chroma（本地向量库）、pypdf / python-docx / python-pptx / markdown（文档解析）；
- LLM：OpenAI 兼容 API（openai SDK，对话与 Embedding 双配置组）；

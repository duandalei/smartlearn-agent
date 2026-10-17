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
2. **前端**：访问 http://localhost:5173，自动跳转 `/login`；点击「登录」（骨架阶段占位登录）进入主布局，左侧菜单可点击切换各页面且不报错。
3. **统一错误提示**：在「学习中心」点击「检测后端连通性」按钮，可验证请求链路；若后端未启动，会通过统一拦截器弹出「网络异常，请稍后重试」而非白屏。

---

## 八、约定要点

- 所有业务接口统一前缀 `/api/v1`；健康检查为 `/health`（不带版本前缀）。
- 统一响应体：`{"code":0,"message":"success","data":{}}`，`code=0` 表示成功。
- 所有密钥 / 模型名 / 服务地址一律走 `.env`，**禁止硬编码**。
- JSON 传输字段统一 `snake_case`，前后端不做自动大小写转换。
- `data/` 为运行时产物（`app.db`、`chroma/`、`uploads/`），已加入 `.gitignore`。
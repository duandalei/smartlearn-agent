# AGENTS.md — 给 AI Agent 的项目配置说明

本文件面向被要求「帮我配置 / 运行这个项目」的 AI Agent；项目仅支持 Windows 10 / 11。按顺序执行即可，
无需先阅读其他文档。

项目是 **Python FastAPI + Vue 3** 的单机应用，数据存 SQLite，不需要
MySQL / PostgreSQL / Redis。

## 目标

`git clone` 之后：

1. 一条命令装好前后端依赖与环境变量；
2. 运行一键启动脚本；
3. 浏览器打开 http://localhost:5173 ，直接进入首页（本地单用户，无需登录），即可记录自己的学习。

## 环境要求

| 依赖 | 最低版本 | 检查命令 |
|---|---|---|
| Python | 3.10+（推荐 3.11 / 3.12） | `python --version` |
| Node.js | 18+（推荐 20 / 22） | `node --version` |
| npm | 随 Node.js 安装 | `npm --version` |

## 一条命令配置

Windows（cmd / PowerShell）：

```bat
setup.bat
```


也可以直接调用底层脚本：

```bash
python scripts/setup_env.py
```

脚本会依次完成：

1. 校验 Python / Node 版本；
2. 创建 `backend/.venv`（已存在则复用）；
3. `pip install -r backend/requirements.txt`；
4. 准备 `backend/.env`；
5. 数据库不存在时执行 `python -m app.db.init_db` 初始化数据库（建表 + 本地用户）；
6. `npm ci`（无 lock 时 `npm install`）安装前端依赖。

**成功标志**：最后输出「环境配置完成」且退出码为 0。
失败时按脚本提示处理（版本过低 / 网络失败 / 端口占用等）。

## 启动

Windows：

```bat
start.bat
```


启动后：

- 后端 http://localhost:8000 ，健康检查 `GET /health` 返回 `{"code":0,...}`；
  接口文档 http://localhost:8000/docs
- 前端 http://localhost:5173
- 本地单用户，打开前端即进入首页，没有登录 / 注册页。

启动脚本会自动补齐：`.env` 缺失时复制模板、
数据库不存在时执行 `init_db`。

## 配置 LLM / Embedding（可选）

在 `backend/.env` 中填写 OpenAI 兼容接口：

```env
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
# 向量化可独立配置；留空则逐项回退 LLM_*
EMBEDDING_BASE_URL=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=
```

不配置也能启动和使用任务、学习记录、计划查看；AI 问答与在线向量化会提示
未配置，知识库索引会走本地兜底向量。

## 验证清单

1. `GET http://localhost:8000/health` 返回 `code=0`；
2. 前端 5173 能打开首页（没有登录页）；
3. 直接进入主布局，能创建目标 / 任务并记录学习；
4. 「学习记录」→「记录学习」能保存一条记录；
5. 刷新页面后记录仍在（SQLite 已落库）。

## 常见问题

- **Python / Node 版本过低**：按上表升级后重跑配置脚本；
- **pip / npm 网络失败**：配置国内镜像源后重试；
- **端口被占用**：`netstat -ano | findstr :8000`，结束后端进程后重启；
- **想清空本地数据**：先停后端，删除 `data/smartlearn.db` 与 `data/chroma/` 后重启（会清空记录）；
- **不要提交**：`backend/.env`、`data/*.db`、`.venv/`、`node_modules/`。

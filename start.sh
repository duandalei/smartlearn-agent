#!/usr/bin/env bash
# ===========================================================================
# 一键启动脚本（Linux / macOS / Git-Bash）
# 先启动后端，再启动前端；Ctrl+C 结束时会一并关闭后端。
# ===========================================================================
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ---- 启动后端（后台运行）--------------------------------------------------
echo "[1/2] 启动后端 ..."
(
  cd "${ROOT_DIR}/backend"
  if [ -d ".venv" ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate 2>/dev/null || true
  fi
  # 环境自检：缺 .env 时复制模板；JWT_SECRET 仍为占位值时自动生成随机值
  python scripts/ensure_dev_env.py
  # 首次启动：数据库不存在时自动写入演示种子数据
  if [ ! -f "${ROOT_DIR}/data/smartlearn.db" ]; then
    echo "[初始化] 未检测到数据库，正在写入演示种子数据 ..."
    python -m app.db.init_db
  fi
  exec python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
) &
BACKEND_PID=$!

# 退出时关闭后端
trap 'echo "[停止] 关闭后端 (pid=${BACKEND_PID})"; kill "${BACKEND_PID}" 2>/dev/null || true' EXIT

# ---- 启动前端（前台）------------------------------------------------------
echo "[2/2] 启动前端 ..."
cd "${ROOT_DIR}/frontend"
if [ ! -d "node_modules" ]; then
  echo "[提示] 未检测到 node_modules，正在安装前端依赖 ..."
  npm install
fi
npm run dev
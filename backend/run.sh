#!/usr/bin/env bash
# ===========================================================================
# 后端启动脚本（Linux / macOS / Git-Bash）
# 用法：bash run.sh  或  ./run.sh
# ===========================================================================
set -e

# 切换到脚本所在目录（backend/）
cd "$(dirname "$0")"

# 若存在虚拟环境则自动激活
if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate 2>/dev/null || true
fi

# 环境自检：缺 .env 时复制模板；JWT_SECRET 仍为占位值时自动生成随机值
python scripts/ensure_dev_env.py

# 首次启动：数据库不存在时写入演示种子数据
if [ ! -f "../data/smartlearn.db" ]; then
  echo "[初始化] 未检测到数据库，正在写入演示种子数据 ..."
  python -m app.db.init_db
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

echo "[启动] 后端服务 http://localhost:${PORT}  (文档 /docs)"
exec python -m uvicorn app.main:app --reload --host "${HOST}" --port "${PORT}"
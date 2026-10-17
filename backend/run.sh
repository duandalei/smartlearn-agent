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

# 首次运行可用 .env.example 生成 .env（不覆盖已有 .env）
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  echo "[提示] 未检测到 .env，已由 .env.example 生成，请按需填写真实密钥。"
  cp .env.example .env
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

echo "[启动] 后端服务 http://localhost:${PORT}  (文档 /docs)"
exec python -m uvicorn app.main:app --reload --host "${HOST}" --port "${PORT}"
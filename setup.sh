#!/usr/bin/env bash
# ===========================================================================
# SmartLearn 一键环境配置（Linux / macOS / Git-Bash）
# 用法：bash setup.sh
# 完成后执行 bash start.sh 启动项目
# ===========================================================================
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "[错误] 未检测到 Python，请安装 Python 3.10+ 后重试。" >&2
  exit 1
fi

exec "$PY" "${ROOT_DIR}/scripts/setup_env.py" "$@"

"""开发环境自检：确保 backend/.env 存在。

一键启动脚本（start.bat / run.bat）在拉起后端前调用；本地单用户模式
不使用 JWT；这里只做一件事：``.env`` 不存在时从 ``.env.example`` 复制。
仅使用标准库，未安装项目依赖时也能执行。
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

BACKEND_DIR: Path = Path(__file__).resolve().parent.parent
ENV_PATH: Path = BACKEND_DIR / ".env"
EXAMPLE_PATH: Path = BACKEND_DIR / ".env.example"


def main() -> int:
    """确保 ``.env`` 存在；成功返回 0，模板缺失返回 1。"""
    if ENV_PATH.exists():
        return 0
    if not EXAMPLE_PATH.exists():
        print("缺少 .env 与 .env.example，无法初始化开发环境", file=sys.stderr)
        return 1
    shutil.copyfile(EXAMPLE_PATH, ENV_PATH)
    print(f"已从模板创建 {ENV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

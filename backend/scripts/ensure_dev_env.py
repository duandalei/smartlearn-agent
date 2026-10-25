"""开发环境自检：确保 backend/.env 存在且 JWT_SECRET 可用。

一键启动脚本（start.bat / start.sh）在拉起后端前调用，只做两件事：

1. ``.env`` 不存在时从 ``.env.example`` 复制；
2. ``JWT_SECRET`` 缺失、为空或仍是占位值时，生成随机强密钥并就地写入。

只改 JWT_SECRET 一行，不覆盖用户已经配置的 LLM / Embedding / 数据库
等变量；仅使用标准库，未安装项目依赖时也能执行。
"""

from __future__ import annotations

import re
import secrets
import shutil
import sys
from pathlib import Path

BACKEND_DIR: Path = Path(__file__).resolve().parent.parent
ENV_PATH: Path = BACKEND_DIR / ".env"
EXAMPLE_PATH: Path = BACKEND_DIR / ".env.example"

#: 与 app/core/config.py 的占位值校验保持一致。
PLACEHOLDER: str = "change-me-in-env"


def main() -> int:
    """执行自检；成功返回 0，模板缺失返回 1。"""
    if not ENV_PATH.exists():
        if not EXAMPLE_PATH.exists():
            print("缺少 .env 与 .env.example，无法初始化开发环境", file=sys.stderr)
            return 1
        shutil.copyfile(EXAMPLE_PATH, ENV_PATH)
        print(f"已从模板创建 {ENV_PATH}")

    text = ENV_PATH.read_text(encoding="utf-8")
    match = re.search(r"(?m)^JWT_SECRET=(.*)$", text)
    current = match.group(1).strip() if match else ""
    if current and current != PLACEHOLDER:
        return 0

    secret = secrets.token_hex(32)
    if match:
        text = re.sub(r"(?m)^JWT_SECRET=.*$", f"JWT_SECRET={secret}", text)
    else:
        text = text.rstrip() + f"\nJWT_SECRET={secret}\n"
    ENV_PATH.write_text(text, encoding="utf-8")
    print("已生成随机 JWT_SECRET 并写入 backend/.env（仅本机开发使用）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

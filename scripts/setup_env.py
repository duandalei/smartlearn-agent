"""一键配置开发环境（Windows / macOS / Linux 通用）。

用法::

    python scripts/setup_env.py          # 完整配置
    python scripts/setup_env.py --skip-db  # 只装依赖，不初始化数据库

流程：校验 Python / Node → 创建 backend/.venv → 安装后端依赖 →
生成 backend/.env 与随机 JWT_SECRET → 数据库不存在时写入演示种子 →
安装前端依赖。成功后运行 start.bat（Windows）或 bash start.sh 启动。

脚本只依赖标准库；每一步失败都会打印可执行的修复提示并返回非零，
方便用户或 AI Agent 直接按提示处理。
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT: Path = Path(__file__).resolve().parent.parent
BACKEND: Path = ROOT / "backend"
FRONTEND: Path = ROOT / "frontend"
VENV: Path = BACKEND / ".venv"
DB_PATH: Path = ROOT / "data" / "smartlearn.db"
REQUIREMENTS: Path = BACKEND / "requirements.txt"
PACKAGE_LOCK: Path = FRONTEND / "package-lock.json"

MIN_PYTHON: tuple[int, int] = (3, 10)
MIN_NODE_MAJOR: int = 18


def _venv_python() -> Path:
    """当前平台下 venv 解释器路径。"""
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    """执行命令；失败时抛出 CalledProcessError（由 main 统一收口）。"""
    printable = " ".join(str(part) for part in cmd)
    print(f"\n$ {printable}" + (f"    (cwd={cwd})" if cwd else ""))
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def _check_python() -> bool:
    if sys.version_info < MIN_PYTHON:
        print(
            f"[错误] 需要 Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+，"
            f"当前为 {sys.version.split()[0]}。请升级后重试。",
            file=sys.stderr,
        )
        return False
    print(f"[检查] Python {sys.version.split()[0]} OK")
    return True


def _node_binary() -> str | None:
    return shutil.which("node")


def _check_node() -> bool:
    node = _node_binary()
    if node is None:
        print(
            "[错误] 未检测到 Node.js。请安装 Node.js 18+（推荐 20/22）并加入 PATH："
            "https://nodejs.org/",
            file=sys.stderr,
        )
        return False
    try:
        raw = subprocess.run(
            [node, "--version"], check=True, capture_output=True, text=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"[错误] 无法执行 node：{exc}", file=sys.stderr)
        return False
    match = re.match(r"v(\d+)", raw)
    major = int(match.group(1)) if match else 0
    if major < MIN_NODE_MAJOR:
        print(
            f"[错误] 需要 Node.js {MIN_NODE_MAJOR}+，当前为 {raw}。请升级后重试。",
            file=sys.stderr,
        )
        return False
    print(f"[检查] Node.js {raw} OK")
    return True


def _npm_binary() -> str | None:
    if os.name == "nt":
        return shutil.which("npm.cmd") or shutil.which("npm")
    return shutil.which("npm")


def _ensure_venv() -> Path:
    python = _venv_python()
    if python.exists():
        print(f"[检查] 复用虚拟环境 {VENV}")
        return python
    print(f"[安装] 创建虚拟环境 {VENV}")
    _run([sys.executable, "-m", "venv", str(VENV)])
    if not python.exists():
        raise RuntimeError(f"虚拟环境创建后未找到解释器：{python}")
    return python


def _install_backend(python: Path) -> None:
    print("[安装] 安装后端依赖（首次可能需要几分钟）")
    _run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-r",
            str(REQUIREMENTS),
        ]
    )


def _prepare_env(python: Path) -> None:
    print("[配置] 生成 backend/.env 与随机 JWT_SECRET")
    _run([str(python), str(BACKEND / "scripts" / "ensure_dev_env.py")], cwd=BACKEND)


def _init_db(python: Path) -> None:
    if DB_PATH.exists():
        print(f"[检查] 数据库已存在，跳过初始化：{DB_PATH}")
        return
    print("[初始化] 未检测到数据库，写入演示种子数据")
    _run([str(python), "-m", "app.db.init_db"], cwd=BACKEND)


def _install_frontend() -> None:
    npm = _npm_binary()
    if npm is None:
        raise RuntimeError("未检测到 npm（通常随 Node.js 一起安装）")
    print("[安装] 安装前端依赖（首次可能需要几分钟）")
    if PACKAGE_LOCK.exists():
        try:
            _run([npm, "ci", "--no-audit", "--no-fund"], cwd=FRONTEND)
            return
        except subprocess.CalledProcessError:
            print("[提示] npm ci 失败，改用 npm install 重试")
    _run([npm, "install", "--no-audit", "--no-fund"], cwd=FRONTEND)


def _print_summary() -> None:
    start_cmd = "start.bat" if os.name == "nt" else "bash start.sh"
    print(
        "\n"
        "==============================================\n"
        " 环境配置完成\n"
        "==============================================\n"
        f" 启动项目: {start_cmd}\n"
        " 前端地址: http://localhost:5173\n"
        " 后端地址: http://localhost:8000（接口文档 /docs）\n"
        " 演示账号: demo / 123456（可直接注册新账号）\n"
        "\n"
        " 说明: LLM / Embedding 未配置时，核心功能（任务、记录、计划查看）\n"
        "       仍可正常使用；AI 问答与在线向量化需要填写 backend/.env。\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="配置 SmartLearn 开发环境")
    parser.add_argument(
        "--skip-db", action="store_true", help="跳过演示数据库初始化（启动时会自动补）"
    )
    args = parser.parse_args()

    print("========== SmartLearn 环境配置 ==========")
    if not _check_python() or not _check_node():
        return 1

    try:
        python = _ensure_venv()
        _install_backend(python)
        _prepare_env(python)
        if not args.skip_db:
            _init_db(python)
        _install_frontend()
    except subprocess.CalledProcessError as exc:
        print(
            f"\n[失败] 命令执行失败（退出码 {exc.returncode}）。"
            "请检查网络与上方报错；pip/npm 可配置国内镜像后重试。",
            file=sys.stderr,
        )
        return 1
    except (OSError, RuntimeError) as exc:
        print(f"\n[失败] {exc}", file=sys.stderr)
        return 1

    _print_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

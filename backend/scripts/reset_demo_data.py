"""SmartLearn 演示数据一键重置脚本（父进程编排层）。

用法（在 backend/ 目录下执行）：
    python scripts/reset_demo_data.py [--yes] [--no-backup]

行为概览（design §2.1.3-C 主链）：
    参数解析 → 配置探测（子进程，与后端同源） → 三道防线占用检测
    → 交互确认 → 备份（可 --no-backup 跳过） → 删除 → 初始化子进程
    → 重索引子进程 → 只读验证 → 摘要。

铁律（design §1.2.4）：
    本模块顶层零 ``import app.*``；app 相关 import 只允许出现在 worker
    函数体内（组 2 实现）。配置获取一律经由子进程探测，父进程不解析
    .env 文本，保证口径与后端 100% 同源。

退出码（design §2.2.2-E）：
    0  成功（含验证通过）
    1  参数错误 / 用户取消确认 / 非 TTY 未 --yes / 未分类错误
    2  数据库被占用或后端在运行
    3  备份失败
    4  删除失败
    5  初始化子进程失败
    6  重索引失败（任一篇）或最终验证不通过
    7  配置加载失败 / 非 SQLite 形态
"""

from __future__ import annotations

import os
import shutil
import socket
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPTS_DIR.parent
BACKEND_PORT = 8000


def _child_python() -> str:
    """子进程解释器：优先 backend/.venv，避免用系统 Python 缺依赖。"""
    candidates = [
        BACKEND_DIR / ".venv" / "Scripts" / "python.exe",
        BACKEND_DIR / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return sys.executable


CHILD_PYTHON = _child_python()

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_OCCUPIED = 2
EXIT_BACKUP_FAILED = 3
EXIT_DELETE_FAILED = 4
EXIT_INIT_FAILED = 5
EXIT_REINDEX_FAILED = 6
EXIT_CONFIG_FAILED = 7

SQLITE_PREFIX = "sqlite:///"

PROBE_SNIPPET = (
    "from app.core.config import settings;"
    "print('@@CFG@@');"
    "print(settings.DATABASE_URL);"
    "print(settings.CHROMA_DIR);"
    "print(settings.UPLOAD_DIR)"
)

USAGE = """\
用法: python scripts/reset_demo_data.py [--yes] [--no-backup]

选项:
  --yes        跳过交互确认直接执行（不豁免占用检测与配置校验）
  --no-backup  跳过备份步骤
  -h, --help   显示本帮助并退出

说明: 演示数据一键重置——备份并重建数据库、向量库与上传目录，
      恢复为可演示的干净状态。绝不修改 .env 与 data/public_kb/。
"""


class Config:
    def __init__(self, database_url: str, db_path: Path, chroma_dir: Path, upload_dir: Path) -> None:
        self.database_url = database_url
        self.db_path = db_path
        self.chroma_dir = chroma_dir
        self.upload_dir = upload_dir
        self.backup_root = db_path.parent / "_reset_backup"


def parse_args(argv: list[str]) -> dict:
    args = {"yes": False, "no_backup": False, "worker_reindex": False, "verify_only": False}
    known = {
        "--yes": "yes",
        "--no-backup": "no_backup",
        "--worker-reindex": "worker_reindex",
        "--verify-only": "verify_only",
    }
    for token in argv:
        if token in ("-h", "--help"):
            print(USAGE)
            raise SystemExit(EXIT_OK)
        if token in known:
            args[known[token]] = True
            continue
        print(f"参数错误: 无法识别的参数 {token!r}\n", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    if args["worker_reindex"] and (args["yes"] or args["no_backup"]):
        print("参数错误: --worker-reindex 不能与 --yes/--no-backup 同现", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    if args["verify_only"] and (args["yes"] or args["no_backup"] or args["worker_reindex"]):
        print("参数错误: --verify-only 不能与 --yes/--no-backup/--worker-reindex 同现", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    return args


def _resolve_path(raw: str) -> Path:
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = BACKEND_DIR / p
    return p.resolve()


def probe_config() -> Config:
    """配置探测子进程：父进程零 import app，三路径与后端同源解析。"""
    try:
        proc = subprocess.run(
            [CHILD_PYTHON, "-c", PROBE_SNIPPET],
            cwd=str(BACKEND_DIR),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"配置加载失败，请检查 .env（探测子进程无法执行: {exc}）", file=sys.stderr)
        raise SystemExit(EXIT_CONFIG_FAILED)
    if proc.returncode != 0:
        print("配置加载失败，请检查 .env（探测子进程报错）:", file=sys.stderr)
        tail = (proc.stderr or "").strip().splitlines()
        for line in tail[-5:]:
            print(f"  {line}", file=sys.stderr)
        raise SystemExit(EXIT_CONFIG_FAILED)
    lines = proc.stdout.splitlines()
    try:
        marker = lines.index("@@CFG@@")
        database_url, chroma_raw, upload_raw = lines[marker + 1 : marker + 4]
    except (ValueError, IndexError):
        print("配置加载失败，请检查 .env（探测输出格式异常）", file=sys.stderr)
        raise SystemExit(EXIT_CONFIG_FAILED)
    database_url = database_url.strip()
    if not database_url.startswith(SQLITE_PREFIX) or ":memory:" in database_url:
        scheme = database_url.split(":", 1)[0] if ":" in database_url else "unknown"
        print(
            f"配置加载失败: 仅支持 SQLite 文件库形态（当前 scheme={scheme}，URL 已隐藏）",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_CONFIG_FAILED)
    db_path = _resolve_path(database_url[len(SQLITE_PREFIX):])
    cfg = Config(
        database_url=database_url,
        db_path=db_path,
        chroma_dir=_resolve_path(chroma_raw.strip()),
        upload_dir=_resolve_path(upload_raw.strip()),
    )
    print(f"数据库路径: {cfg.db_path}")
    print(f"向量库目录: {cfg.chroma_dir}")
    print(f"上传目录:   {cfg.upload_dir}")
    return cfg


def guard_occupancy(db_path: Path, port: int = BACKEND_PORT, skip_port: bool = False) -> None:
    """三道防线占用检测；命中即以 exit 2 终止，绝不杀进程。"""
    if not skip_port:
        try:
            conn = socket.create_connection(("127.0.0.1", port), timeout=1)
        except OSError:
            conn = None
        if conn is not None:
            conn.close()
            print(
                f"{port} 端口被占用（可能是后端仍在运行），请先停止后端再重置。",
                file=sys.stderr,
            )
            raise SystemExit(EXIT_OCCUPIED)
    if not db_path.exists():
        return
    probe: sqlite3.Connection | None = None
    try:
        probe = sqlite3.connect(str(db_path), timeout=0)
        probe.execute("BEGIN IMMEDIATE")
        probe.rollback()
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower():
            print(
                f"数据库文件被占用（{db_path}），请先停止后端再重置。",
                file=sys.stderr,
            )
            raise SystemExit(EXIT_OCCUPIED)
    finally:
        if probe is not None:
            probe.close()
    if os.name == "nt":
        try:
            os.rename(db_path, db_path)
        except OSError:
            print(
                f"数据库文件被系统占用（{db_path}），请先停止后端再重置。",
                file=sys.stderr,
            )
            raise SystemExit(EXIT_OCCUPIED)


def confirm(cfg: Config, assume_yes: bool) -> None:
    if assume_yes:
        return
    print("即将删除以下运行期数据（不影响 .env 与 data/public_kb/）:")
    print(f"  数据库文件: {cfg.db_path}（含 -wal/-shm 伴随文件）")
    print(f"  向量库目录: {cfg.chroma_dir}")
    print(f"  上传目录:   {cfg.upload_dir}（目录内容清空，目录本身保留）")
    if not sys.stdin.isatty():
        print("非交互环境且未提供 --yes，拒绝执行。", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    try:
        answer = input("请输入完整 yes 确认执行: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n已取消，未做任何修改。")
        raise SystemExit(EXIT_USAGE)
    if answer != "yes":
        print("已取消，未做任何修改。")
        raise SystemExit(EXIT_USAGE)


def backup_database(cfg: Config, no_backup: bool) -> tuple[Path | None, str]:
    """备份 SQLite 主文件及 -wal/-shm 到 _reset_backup/<时间戳>/；撞名追加序号。

    返回 (备份目录或 None, 摘要备份行文本)——三态：实际路径 /
    「未备份（--no-backup）」/「未备份（数据库不存在）」。
    """
    if no_backup:
        print("备份: 未备份（--no-backup）")
        return None, "未备份（--no-backup）"
    if not cfg.db_path.exists():
        print(f"备份: 数据库文件不存在（{cfg.db_path}），跳过备份（视为首次运行）")
        return None, "未备份（数据库不存在）"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = cfg.backup_root / stamp
    suffix = 2
    while dest.exists():
        dest = cfg.backup_root / f"{stamp}-{suffix}"
        suffix += 1
    try:
        dest.mkdir(parents=True, exist_ok=False)
        for candidate in (
            cfg.db_path,
            cfg.db_path.with_name(cfg.db_path.name + "-wal"),
            cfg.db_path.with_name(cfg.db_path.name + "-shm"),
        ):
            if candidate.exists():
                shutil.copy2(candidate, dest / candidate.name)
    except OSError as exc:
        print(
            f"备份失败: {exc}。已中止后续步骤，未删除任何数据。",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_BACKUP_FAILED)
    print(f"备份目录: {dest}")
    return dest, str(dest)


def validate_protected_paths(cfg: Config) -> None:
    """路径安全守卫：运行期路径与受保护路径重叠即 exit 7（零写操作）。

    在 probe_config 之后、占用检测/确认/备份/删除之前执行；主链与
    --verify-only 共用。防 .env 误配把 UPLOAD_DIR 指到 data/、项目根
    或 data/public_kb 时 rmtree/遍历删除受保护内容（spec §4.3-1）。
    """
    project_root = BACKEND_DIR.parent
    data_root = (project_root / "data").resolve()
    public_kb = (data_root / "public_kb").resolve()
    env_files = {(project_root / ".env").resolve(), (BACKEND_DIR / ".env").resolve()}
    protected_dirs = {project_root.resolve(), BACKEND_DIR.resolve(), data_root}
    for label, p in (("数据库", cfg.db_path), ("向量库", cfg.chroma_dir), ("上传目录", cfg.upload_dir)):
        rp = p.resolve()
        if rp in env_files or rp == public_kb or rp.is_relative_to(public_kb) or public_kb.is_relative_to(rp):
            print(
                f"配置安全校验失败: {label}路径 {rp} 与受保护路径（.env / data/public_kb）重叠，已拒绝执行，未做任何修改。",
                file=sys.stderr,
            )
            raise SystemExit(EXIT_CONFIG_FAILED)
        if rp in protected_dirs:
            print(
                f"配置安全校验失败: {label}路径 {rp} 指向项目根 / backend / data 目录本身，已拒绝执行，未做任何修改。",
                file=sys.stderr,
            )
            raise SystemExit(EXIT_CONFIG_FAILED)


def _rollback_hint(backup_dir: Path | None) -> str:
    if backup_dir is None:
        return "无备份可回滚，可再次执行本脚本重建。"
    return (
        f"先停止后端，将 {backup_dir} 下的数据库主文件及 -wal、-shm "
        f"伴随文件复制回原数据库路径覆盖，然后重启后端。"
    )


def clean_runtime_data(cfg: Config, backup_dir: Path | None) -> None:
    """删除运行期数据：db 三文件 → chroma 整体 → uploads 内容（保留目录）。

    删除前二次执行防线 2+3（跳过端口探测，收口 TOCTOU）；任一删除失败
    即中止剩余删除，exit 4 并输出失败路径与回滚指引。删除集合仅由
    validate_protected_paths 校验通过的 db/-wal/-shm、CHROMA_DIR、
    UPLOAD_DIR 内容构成；受保护路径（.env / data/public_kb）由守卫
    在删除前拦截，本函数不再重复校验。
    """
    guard_occupancy(cfg.db_path, skip_port=True)
    targets: list[tuple[str, Path]] = [
        ("数据库主文件", cfg.db_path),
        ("WAL 伴随文件", cfg.db_path.with_name(cfg.db_path.name + "-wal")),
        ("SHM 伴随文件", cfg.db_path.with_name(cfg.db_path.name + "-shm")),
    ]
    try:
        for label, path in targets:
            if path.exists():
                path.unlink()
                print(f"已删除{label}: {path}")
        if cfg.chroma_dir.exists():
            shutil.rmtree(cfg.chroma_dir)
            print(f"已删除向量库目录: {cfg.chroma_dir}")
        if cfg.upload_dir.exists():
            for child in cfg.upload_dir.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            print(f"已清空上传目录内容: {cfg.upload_dir}")
    except OSError as exc:
        print(
            f"删除失败: {exc.filename or ''} {exc}。已中止剩余删除步骤。",
            file=sys.stderr,
        )
        print(f"数据库回滚指引: {_rollback_hint(backup_dir)}", file=sys.stderr)
        print("向量库与上传目录不备份、不回滚，由重新执行重置/重索引再生成。", file=sys.stderr)
        raise SystemExit(EXIT_DELETE_FAILED)


def run_init_child() -> None:
    """初始化子进程：python -m app.db.init_db（建表 + 种子，输出原样透传）。"""
    try:
        proc = subprocess.run(
            [CHILD_PYTHON, "-m", "app.db.init_db"],
            cwd=str(BACKEND_DIR),
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"初始化子进程无法执行: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_INIT_FAILED)
    if proc.returncode != 0:
        print(
            f"初始化子进程失败（exit {proc.returncode}），原始报错见上方输出。",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_INIT_FAILED)
    print("初始化子进程: 建表与种子数据完成")


def run_reindex_worker(cfg: Config) -> tuple[int, str]:
    """重索引子进程编排：worker 输出原样透传，退出码 0/1 映射为父进程 0/6。

    返回 (退出码, worker stdout 原文)——stdout 供摘要块逐篇行取用
    （父进程不重新格式化 worker 的事实数据，design §2.2.2-D）。
    子进程以脚本文件方式启动时 ``sys.path[0]`` 是 scripts/ 目录而非
    backend/，须显式注入 PYTHONPATH 才能 import app.*（init 子进程用
    ``-m`` 形态以 cwd 入 sys.path，无此问题）。
    """
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        proc = subprocess.run(
            [CHILD_PYTHON, str(SCRIPTS_DIR / "reset_demo_data.py"), "--worker-reindex"],
            cwd=str(BACKEND_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"重索引子进程无法执行: {exc}", file=sys.stderr)
        return EXIT_REINDEX_FAILED, ""
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    if proc.returncode != 0:
        print(
            "重索引失败：存在失败篇目或公共文档数量异常（见上方 [FAIL] 行与数量提示）。",
            file=sys.stderr,
        )
        return EXIT_REINDEX_FAILED, proc.stdout or ""
    return EXIT_OK, proc.stdout or ""


def _verify_rows(cfg: Config) -> tuple[int, list[str]]:
    """sqlite3 只读交叉验证（mode=ro URI，零写操作）。

    返回 (退出码, 逐篇结果行)：数量恰为 4、每篇 status=indexed、
    chunk_count>0 且等于 knowledge_chunks 实际行数；任一不满足返回 6。
    """
    if not cfg.db_path.exists():
        return EXIT_REINDEX_FAILED, [f"[FAIL] 数据库文件不存在: {cfg.db_path}"]
    try:
        conn = sqlite3.connect(f"file:{cfg.db_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return EXIT_REINDEX_FAILED, [f"[FAIL] 数据库只读打开失败: {exc}"]
    try:
        rows = conn.execute(
            "SELECT id, title, status, chunk_count FROM knowledge_items "
            "WHERE scope='public' ORDER BY id"
        ).fetchall()
    except sqlite3.Error as exc:
        conn.close()
        return EXIT_REINDEX_FAILED, [f"[FAIL] 验证查询失败（库未初始化？）: {exc}"]
    if len(rows) != 4:
        lines = [f"[FAIL] 公共文档数量恰为 4 的硬门禁不满足：实际 {len(rows)} 篇"]
        lines += [f"  - {title}" for _, title, _, _ in rows]
        conn.close()
        return EXIT_REINDEX_FAILED, lines
    lines: list[str] = []
    all_ok = True
    for item_id, title, status, chunk_count in rows:
        real = conn.execute(
            "SELECT COUNT(*) FROM knowledge_chunks WHERE item_id=?", (item_id,)
        ).fetchone()[0]
        if status == "indexed" and chunk_count and chunk_count > 0 and chunk_count == real:
            lines.append(f"[OK] {title} — {chunk_count} chunks")
        else:
            all_ok = False
            lines.append(
                f"[FAIL] {title} — status={status} chunk_count={chunk_count} 实际行数={real}"
            )
    conn.close()
    return (EXIT_OK if all_ok else EXIT_REINDEX_FAILED), lines


def verify_reset(cfg: Config) -> int:
    """只读验证入口：主链末段与 --verify-only 共用；逐篇打印结果行。"""
    code, lines = _verify_rows(cfg)
    for line in lines:
        print(line)
    return code


def print_summary(cfg: Config, backup_line: str, item_lines: list[str]) -> None:
    """结构化摘要块（全文中文，不含任何密钥）；仅在验证通过后调用。"""
    print("========== SmartLearn 演示数据重置完成 ==========")
    print(f"数据库路径: {cfg.db_path}（已重建）")
    print("演示账号: demo / 123456（仅供开发演示，请勿用于生产环境）")
    print(f"备份目录: {backup_line}")
    print("公共知识库（4 篇，真实索引）:")
    for line in item_lines:
        print(f"  {line}")
    print(
        "验证查询（可选）: cd backend && python -c \"import sqlite3;"
        "c=sqlite3.connect('../data/smartlearn.db');"
        "print(c.execute(\\\"select title,status,chunk_count from knowledge_items "
        "where scope='public'\\\").fetchall())\""
    )
    print("下一步: 启动后端与前端（start.bat / bash start.sh），以 demo / 123456 登录")
    print("==================================================")


async def _worker_reindex() -> int:
    """worker 子命令：4 篇公共文档真实重索引（函数体内才 import app.*）。"""
    from sqlalchemy import func, select

    from app.core.response import BizException
    from app.db.session import SessionLocal
    from app.models.enums import KnowledgeItemStatus, KnowledgeScope
    from app.models.knowledge import KnowledgeChunk, KnowledgeItem
    from app.models.user import User
    from app.rag.embedding import embed_query_with_fallback
    from app.services.knowledge import process_document, reindex_item

    with SessionLocal() as db0:
        demo_id = db0.scalar(select(User.id).where(User.username == "demo"))
        if demo_id is None:
            print("[FAIL] 未找到 demo 用户（初始化子进程未成功执行？）", file=sys.stderr)
            return 1
        rows = db0.execute(
            select(KnowledgeItem.id, KnowledgeItem.title)
            .where(KnowledgeItem.scope == KnowledgeScope.PUBLIC)
            .order_by(KnowledgeItem.id)
        ).all()
    items = [(row[0], row[1]) for row in rows]
    if len(items) != 4:
        print(
            f"[FAIL] 公共文档数量恰为 4 的硬门禁不满足：实际 {len(items)} 篇",
            file=sys.stderr,
        )
        for _, title in items:
            print(f"  - {title}", file=sys.stderr)
        return 1

    try:
        _, probe_mode = await embed_query_with_fallback("reset-probe")
    except Exception:
        probe_mode = "online"

    all_ok = True
    for item_id, title in items:
        try:
            with SessionLocal() as db1:
                user = db1.get(User, demo_id)
                reindex_item(db1, user, item_id)
            await process_document(item_id)
            with SessionLocal() as db2:
                fresh = db2.get(KnowledgeItem, item_id)
                real = db2.scalar(
                    select(func.count())
                    .select_from(KnowledgeChunk)
                    .where(KnowledgeChunk.item_id == item_id)
                )
                ok = (
                    fresh is not None
                    and fresh.status == KnowledgeItemStatus.INDEXED
                    and fresh.chunk_count is not None
                    and fresh.chunk_count > 0
                    and fresh.chunk_count == real
                )
                if ok:
                    err = None
                else:
                    err = (fresh.error_msg if fresh else None) or "终态回查不满足三条件"
        except BizException as exc:
            ok, err, fresh = False, f"BizException {exc.code}: {exc.message}", None
        except Exception as exc:
            ok, err, fresh = False, f"{type(exc).__name__}: {exc}", None
        if ok:
            mode_note = " (offline 兜底)" if probe_mode == "offline" else ""
            print(f"[OK] {title} — {fresh.chunk_count} chunks{mode_note}")
        else:
            all_ok = False
            print(f"[FAIL] {title} — {err}")
    return 0 if all_ok else 1


def _worker_entry() -> int:
    import asyncio

    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    cfg = probe_config()
    validate_protected_paths(cfg)
    return asyncio.run(_worker_reindex())


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args["worker_reindex"]:
        return _worker_entry()
    cfg = probe_config()
    validate_protected_paths(cfg)
    if args["verify_only"]:
        code = verify_reset(cfg)
        if code == EXIT_OK:
            print("只读验证通过（--verify-only，全程零写操作）。")
        else:
            print("只读验证不通过（--verify-only，全程零写操作）。", file=sys.stderr)
        return code
    guard_occupancy(cfg.db_path)
    confirm(cfg, assume_yes=args["yes"])
    backup_dir, backup_line = backup_database(cfg, no_backup=args["no_backup"])
    clean_runtime_data(cfg, backup_dir)
    run_init_child()
    reindex_code, worker_stdout = run_reindex_worker(cfg)
    if reindex_code != EXIT_OK:
        return reindex_code
    verify_code, verify_lines = _verify_rows(cfg)
    if verify_code != EXIT_OK:
        for line in verify_lines:
            print(line)
        print("最终验证不通过，不输出「重置完成」摘要。", file=sys.stderr)
        return verify_code
    worker_item_lines = [
        line.strip()
        for line in worker_stdout.splitlines()
        if line.strip().startswith(("[OK] ", "[FAIL] "))
    ]
    print_summary(cfg, backup_line, worker_item_lines or verify_lines)
    print("退出码: 0")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
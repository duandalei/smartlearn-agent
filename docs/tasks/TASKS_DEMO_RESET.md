# TASKS_DEMO_RESET —— 演示数据重置 + 演示脚本 + README 补齐 编码任务清单

> **变更说明（2026-10-25，公共库能力已移除）**：4 篇演示文档作为 demo 用户的普通上传文件放在 `data/uploads/1/`；重置 worker 按 4 个确切 `file_path` 查询并重索引，清理环节显式保留这 4 个文件。下文涉及 `data/public_kb/`、`scope=PUBLIC` 的历史条目仅作演进记录，以现行代码与 README/DEMO_SCRIPT 为准。

> feature：`demo_reset`（P13 收尾批次）
> 上游输入：`.codeartsdoer/specs/demo_reset/spec.md`（339 行，5 处定点修订后定稿）；`docs/designs/DESIGN_DEMO_RESET.md`（648 行，4 处定点修订后定稿）
> UI 依据：`docs/WALKTHROUGH_PLAN_REPORT_FRONTEND.md`（W1–W12 已通过）；`docs/需求文档.md` 第 32 节（五步演示剧本）
> 产物落点：本文档落在 `docs/tasks/TASKS_DEMO_RESET.md`（用户指定，对齐 `TASKS_PLAN_REPORT_FRONTEND.md` 等既有惯例），**不**写 `.codeartsdoer/specs/demo_reset/tasks.md`
> 基线事实：后端测试 206 passed；`git status --short -uall` 开工基线含 P13 未提交文件（见任务 1.1）

---

## 非目标（写死，任何任务不得越界）

1. **不改产品代码**：`backend/app/**` 零改动；发现必须修改产品代码才能完成重置时，停止并汇报，不得擅自修改（spec §1.4-2）。
2. **不改前端业务代码**：`frontend/src/**` 零改动。
3. **不改测试**：`backend/tests/**` 零改动；不新增 `backend/scripts/test_*.py`（pytest 收集红线，spec §1.4-6）。
4. **不做 Docker / 云部署**：不创建 `Dockerfile`、`docker-compose.yml`、`docs/DEPLOY_HUAWEI.md`；README 与 DEMO_SCRIPT 中禁止出现 Docker / 云部署章节（spec §1.4-1）。
5. **不 commit**：本轮产出物不执行任何 git commit（spec §1.4-5）。
6. **不杀进程**：占用检测只提示退出，禁止 `kill` / `taskkill`（spec §1.4-4）。
7. **不动受保护路径**：`.env` 任何执行路径下（含异常、中断）不删不改；`data/uploads/1/` 下 4 篇演示上传文件由清理环节显式保留（spec §4.3-1 的沿用口径）。
8. **不进入下游阶段**：不打包提交包、不生成 P14 报告；本清单完成后停止，编码由实现阶段执行。

## 最终门禁（写死，组 6 逐条验收）

| # | 门禁 | 判据 |
|---|---|---|
| G1 | 幂等两跑 | `reset_demo_data.py --yes` 连跑两次，退出码均 0，第二次不报错 |
| G2 | 索引终态 | 4 篇演示文档 `status=indexed` 且每篇 `chunk_count > 0` 且 `chunk_count == knowledge_chunks 实际行数` |
| G3 | 后端测试 | `cd backend && pytest -q` → 206 passed（若有变化必须说明原因） |
| G4 | 前端构建 | `cd frontend && npm run build` → exit 0 |
| G5 | 改动范围 | `git status --short -uall` 与开工基线对比：只多出 `backend/scripts/reset_demo_data.py`、`docs/DEMO_SCRIPT.md`、`docs/designs/DESIGN_DEMO_RESET.md`（基线中已有则不算新增）、`docs/tasks/TASKS_DEMO_RESET.md`、`README.md` 改动条目；`backend/app/`、`frontend/src/` 无任何改动条目 |
| G6 | 脚本走查 | `docs/DEMO_SCRIPT.md` 5 分钟版实际走查一遍，结果记录进汇报 |

---

## 1. 实现重置脚本父进程：CLI + 配置探测 + 三道占用检测 + 确认 + 备份

> 目标：交付 `backend/scripts/reset_demo_data.py` 的父进程前半链（参数 → 探测 → 占用检测 → 确认 → 备份），任一环节失败按退出码表收口，不删任何数据。
> 依据：design §2.1.3-A（父子双进程模型）、§2.1.3-B（三道防线）、§2.2.2-A（CLI 契约）；spec §5.1.1 规则 1/2/3/4、§4.3。

### 1.1 记录开工 git 基线并搭建脚本骨架

- [x] 执行 `git status --short -uall` 记录开工基线，输出原文保存（供组 6 对比贴入汇报）；随后新建 `backend/scripts/reset_demo_data.py`，只搭骨架：模块 docstring、`main(argv)` 入口、`if __name__ == "__main__"` 分发，**模块顶层零 `import app.*`**（app 相关 import 只允许出现在后续 worker 函数体内）。
- 涉及文件：`backend/scripts/reset_demo_data.py`（新增）
- 实现要点：文件名 `reset_demo_data.py` 不匹配 pytest 收集模式 `test_*.py` / `*_test.py`，结构性规避误收集（design §1.2.5）；不修改 `backend/scripts/conftest.py`。
- 对应章节：spec §5.4.1-4（基线对比）、§1.4-6；design §1.2.5、§2.1.3-A 落地要点。
- 完成判据：`cd backend && python scripts/reset_demo_data.py --help` 可运行（或打印用法）且退出码为 0/1；`cd backend && pytest -q --collect-only scripts/` 不收集该文件（收集数与基线一致）。

### 1.2 实现 CLI 参数解析与角色分发

- [x] 在 `reset_demo_data.py` 中实现四个参数的解析与互斥校验：`--yes`（跳过交互确认）、`--no-backup`（跳过备份）、`--worker-reindex`（隐藏子命令，worker 角色入口）、`--verify-only`（隐藏子命令，只读验证入口：仅执行「配置探测 + sqlite3 只读验证 + 验证摘要」，不执行占用检测、确认、备份、删除、初始化、重索引，全程零写操作；退出码：验证通过 0 / 验证不一致 6 / 配置失败 7）；`--worker-reindex` 与 `--yes`/`--no-backup` 同现时报参数错误，`--verify-only` 与 `--yes`/`--no-backup`/`--worker-reindex` 同现时报参数错误；参数非法打印 usage 并 exit 1。
- 涉及文件：`backend/scripts/reset_demo_data.py`
- 实现要点：`--worker-reindex` 与 `--verify-only` 在 README / DEMO_SCRIPT 中均不暴露、不出现在普通 `--help` 主用法中（design §2.2.1 接口表、§2.2.2-A 参数表）；`--yes` 不豁免占用检测（spec §4.3-2）。
- 对应章节：spec §6.1-1/2；design §2.2.2-A、裁决速查表 #8。
- 完成判据：`python scripts/reset_demo_data.py --worker-reindex --yes` → 非零退出且输出参数错误提示；`python scripts/reset_demo_data.py --verify-only --yes` → 非零退出且输出参数错误提示；`python scripts/reset_demo_data.py --bad-flag` → exit 1 + usage。

### 1.3 实现配置探测子进程（三路径同源解析）

- [x] 在 `reset_demo_data.py` 中实现配置探测：父进程以 `subprocess.run([sys.executable, "-c", "<探测片段>"], cwd=backend目录)` 起子进程 import `app.core.config`，以固定分隔行回传 `DATABASE_URL` / `CHROMA_DIR` / `UPLOAD_DIR`；父进程校验 `DATABASE_URL` 为 `sqlite:///` 前缀且非 `:memory:`，三路径统一 `Path(...).expanduser().resolve()` 归一化；备份根目录由「库文件父目录 + `/_reset_backup`」推导；探测失败或非 SQLite 形态 exit 7 并提示检查 `.env`。
- 涉及文件：`backend/scripts/reset_demo_data.py`
- 实现要点：父进程**不** import `app.core.config`（零 app import 铁律，design §1.2.4）；不解析 `.env` 文本（口径与后端 100% 同源）；探测片段**不打印任何密钥字段**（spec §4.3-3）。
- 对应章节：spec §5.1.1 规则 1、§4.3-3；design §2.2.2-A 配置探测子进程契约、§1.2.4。
- 完成判据：配置覆盖用**进程环境变量**实现、全程不碰 `.env`——执行 `CHROMA_DIR=<临时目录> DATABASE_URL=sqlite:///<临时库> python scripts/reset_demo_data.py --yes --no-backup`（或等价形态单独触发探测环节），脚本识别的 chroma 路径为临时值而非默认值；JWT 失败测试用进程环境变量将 `JWT_SECRET=` 置空或置为 config.py 占位值 `change-me-in-env` 触发 → exit 7 且提示含「配置加载失败，请检查 .env」；因从未修改 `.env`，测试结束无需还原。

### 1.4 实现三道防线占用检测

- [x] 在 `reset_demo_data.py` 中实现 `guard_occupancy` 模块内函数：防线 1 `socket.create_connection((127.0.0.1, 8000), timeout=1)` 连通即拒（提示「8000 端口被占用（可能是后端仍在运行），请先停止后端再重置」）；防线 2 标准库 `sqlite3` 以 `timeout=0` 连接后 `BEGIN IMMEDIATE` 立即 `ROLLBACK`，`database is locked` 即拒（探测连接显式 `close()`）；防线 3 仅 `os.name == "nt"` 时 `os.rename(db, db)` 自改名，`PermissionError` 即拒；任一命中 exit 2，未命中静默返回；库文件不存在时防线 2/3 自动跳过、防线 1 仍执行。
- 涉及文件：`backend/scripts/reset_demo_data.py`
- 实现要点：执行时机为「参数解析 + 配置探测之后、交互确认之前」；**绝不杀进程**（无任何 kill 调用）；`--yes` 不豁免。
- 对应章节：spec §5.1.1 规则 2、§4.3-2、§5.1.3 场景 1；design §2.1.3-B、§2.2.2-C。
- 完成判据：后端运行中执行 `python scripts/reset_demo_data.py --yes` → exit 2，输出「请先停止后端再重置」类提示，且 `data/smartlearn.db` 未变动、无进程被杀；后端停止后同命令可越过本环节。

### 1.5 实现交互确认（完整 yes / 非 TTY 拒绝）

- [x] 在 `reset_demo_data.py` 中实现确认环节：未 `--yes` 时打印将删除的路径清单（库文件含 `-wal`/`-shm`、chroma 目录、uploads 目录内容），要求输入完整 `yes`；输入不符或用户取消 → 输出「已取消，未做任何修改」并 exit 1；stdin 非 TTY 且未 `--yes` → 直接拒绝 exit 1；`--yes` 时跳过本环节。
- 涉及文件：`backend/scripts/reset_demo_data.py`
- 实现要点：确认清单中的路径逐字来自任务 1.3 的归一化结果，不硬编码默认路径。
- 对应章节：spec §5.1.1 规则 4、§6.1-1；design §2.2.2-A 参数边界、§2.1.3-C Confirm 节点。
- 完成判据：`echo "" | python scripts/reset_demo_data.py`（非 TTY 无 `--yes`）→ exit 1；交互执行输入 `no` → exit 1 且输出「已取消，未做任何修改」，文件系统零变动。

### 1.6 实现数据库备份（时间戳目录 + 撞名序号）

- [x] 在 `reset_demo_data.py` 中实现备份：默认将数据库主文件及存在时的 `-wal`、`-shm` 以 `shutil.copy2` 复制到 `<库父目录>/_reset_backup/<YYYYmmdd-HHMMSS>/`；目标目录已存在时追加 `-2`、`-3` 序号后缀；`--no-backup` 时整体跳过本环节；备份失败（目录不可写/磁盘不足）→ 中止后续删除、保留原数据、exit 3 并输出失败原因；任何失败路径下已完成的备份不得删除。
- 涉及文件：`backend/scripts/reset_demo_data.py`
- 实现要点：备份只覆盖 SQLite 三文件，向量库与上传目录不备份（spec §4.2-3）；文件操作只用标准库（spec §5.1.1 规则 8）。
- 对应章节：spec §5.1.1 规则 3、§4.2-2/3、§6.2、§5.1.3 场景 4；design §2.1.3-C Backup 步与撞名处理。
- 完成判据：默认执行一次重置（或单独触发备份环节）→ 输出含备份目录路径，该目录下可找到完整数据库副本（主文件 + 存在时的伴随文件）；同一秒内连跑两次备份 → 生成两个不同名目录互不覆盖。

## 2. 实现删除 + 初始化子进程 + worker 重索引（逐篇隔离 / 全新 session 回查 / 数量=4 硬门禁）

> 目标：完成主链后半——删除运行期数据、`python -m app.db.init_db` 子进程重建、`--worker-reindex` 子进程真实重索引 4 篇演示文档。
> 依据：design §2.1.3-A、§2.1.3-C、§2.2.2-B；spec §5.1.1 规则 5/6、§4.2-4。本组依赖组 1 全部完成（CLI/探测/占用检测/确认/备份就绪后才可串接）。

### 2.1 实现运行期数据删除（含删除前二次占用探测）

- [x] 在 `reset_demo_data.py` 中实现删除环节：删除动作前再执行一次防线 2+3 二次探测（跳过防线 1），命中仍 exit 2；随后按序删除——数据库主文件及 `-wal`/`-shm` → chroma 目录整体 → uploads 目录内容（保留 uploads 目录本身与 4 篇演示上传文件）；任一文件删除失败即中止（剩余不删），exit 4，输出失败文件与「按备份回滚数据库」指引；`.env` 不出现在删除集合的任何代码路径中。
- 涉及文件：`backend/scripts/reset_demo_data.py`
- 实现要点：二次探测收口 TOCTOU 窗口（design §2.1.3-B）；chroma/uploads 无回滚义务（spec §4.2-3），删除失败提示中如实说明。
- 对应章节：spec §5.1.1 规则 1、§4.2-3、§4.3-1；design §2.1.3-C Clean 步、风险 R1/R5。
- 完成判据：构造 uploads 内某文件被占用（如编辑器打开）后执行 → exit 4，提示含失败文件路径与回滚指引，且备份目录仍完整存在；正常路径下删除后 `data/smartlearn.db`、`data/chroma/` 不存在、`data/uploads/` 仅保留 4 篇演示文件，而 `data/uploads/1/` 4 篇与 `.env` 原样未动（前后 `dir` / `ls` 与哈希比对）。

### 2.2 串接初始化子进程（python -m app.db.init_db）

- [x] 在 `reset_demo_data.py` 中实现初始化子进程编排：删除完成后以 `subprocess.run([sys.executable, "-m", "app.db.init_db"], cwd=backend目录)` 执行建表 + 种子；子进程 stdout/stderr 原样透传；退出码非 0 → 父进程 exit 5，透传 init_db 原始报错并提示「先按备份回滚数据库再排查」。
- 涉及文件：`backend/scripts/reset_demo_data.py`（编排侧唯一触点；`backend/app/db/init_db.py` 零改动只读复用）
- 实现要点：必须先删库再初始化——`init_db` 幂等开关只有「demo 用户存在则跳过全部插入」（design §1.2.1）；`init_db` 自带库父目录 mkdir 逻辑，编排层不代建。
- 对应章节：spec §5.1.1 规则 5、§4.2-4；design §2.1.3-A 子进程 2、§1.2.1。
- 完成判据：删除后单独触发本环节 → 子进程 exit 0，新库文件出现；用标准库 `sqlite3` 查询新库 `SELECT username FROM users` 含 `demo`，`SELECT COUNT(*) FROM knowledge_items WHERE scope='public'` 返回 4。

### 2.3 实现 worker 重索引子命令（--worker-reindex）

- [x] 在 `reset_demo_data.py` 同一文件内实现 `_worker_reindex()`（async，由 `asyncio.run` 驱动）：函数体内才 import app 服务层；短 session 查 demo 用户与 4 个演示上传文件的 `file_path` 精确匹配清单（按 id 排序）；**数量硬门禁——恰为 4 篇**，≠4 时打印实际数量与标题清单立即 exit 1；随后 4 篇**串行**，每篇三步：① 短生命周期 `SessionLocal` 内 `reindex_item(db1, demo, item.id)` 并随 with 关闭；② `await process_document(item.id)`；③ **全新** `SessionLocal` 回查终态，三条件缺一不可——`status == indexed` 且 `chunk_count > 0` 且 `chunk_count == SELECT COUNT(*) FROM knowledge_chunks WHERE item_id=?`；每篇独立 try/except（`BizException` 与未预期异常分别捕获），打印 `[OK] <标题> — N chunks` 或 `[FAIL] <标题> — <原因>` 后继续下一篇；跨循环只携带 id/title 标量，不持 ORM 对象跨 await；全部完成后任一篇失败则 exit 1。
- 涉及文件：`backend/scripts/reset_demo_data.py`（worker 分支）；只读复用 `backend/app/services/knowledge.py`（`reindex_item` 507 行 / `process_document` 267 行）、`backend/app/db/session.py`、`backend/app/models`
- 实现要点：禁止绕过 `reindex_item` 直接调 `process_document`（种子态 indexed 会被入口状态机拒）；禁止 `asyncio.gather` 并行（SQLite 写锁竞争）；回查必须全新 session（旧 session 读快照可能看不到新提交）；worker 在调用前探测一次在线 embedding 可用性，仅离线兜底篇目的结果行附 `(offline 兜底)` 标注，在线篇目省略 mode（design §2.2.2-B mode 透传条款）。
- 对应章节：spec §5.1.1 规则 6/8、§5.1.3 场景 2/3、§4.1-1；design §2.2.2-B 全文（逐篇隔离 / session 三禁区 / 数量硬门禁）、裁决速查表 #2。
- 完成判据：完整执行重置后 worker 输出 4 行 `[OK]` 且数字为真实切分结果；人为制造单篇失败——先完成一次正常重置，将 `data/smartlearn.db` 复制为 `backend/tmp_verify/reindex_fail.db` 临时库副本，用标准库 `sqlite3` 把该副本中某篇 public 文档的 `file_path` 改为一个不存在的绝对临时路径，再以 `DATABASE_URL=sqlite:///<临时库>` 进程环境变量执行 `--worker-reindex` → 该篇 `[FAIL]` + 原因，其余篇目继续，worker exit 1；**全程禁止改名/删除 `data/uploads/1/` 源文档**。

### 2.4 串接重索引子进程并映射退出码

- [x] 在 `reset_demo_data.py` 父进程主链中实现 `ReindexRunner`：初始化子进程成功后以 `subprocess.run([sys.executable, "scripts/reset_demo_data.py", "--worker-reindex"], cwd=backend目录)` 执行；worker 结果行原样透传（父进程不重新格式化 worker 的事实数据）；worker exit 非 0 或演示文档数量 ≠4 → 父进程 exit 6，逐篇标示成功/失败及 `error_msg`，**不输出「重置完成」摘要**。
- 涉及文件：`backend/scripts/reset_demo_data.py`
- 实现要点：worker 自身退出码收敛 0/1，父进程映射为 6（design §2.2.2-E）；失败篇目禁止显示虚假分块数（spec §5.1.1 规则 6）。
- 对应章节：spec §5.1.1 规则 6、§6.1-3；design §2.1.3-C ReindexChild 节点、§2.2.2-D 透传条款。
- 完成判据：接 2.3 的人为失败场景 → 父进程 exit 6，输出含失败篇目与原因、不含「重置完成」标题行；**本组不要求产出 exit 0**（最终 exit 0 依赖组 3 只读验证与摘要，成功路径止于「组 3 尚未实现」exit 1）；父进程「worker 调用 + 退出码映射」抽成可直调函数（`run_reindex_worker(cfg) -> int`），便于以 monkeypatch/subprocess fake 直测映射，`main` 只负责编排与打印占位。

## 3. 实现只读验证 + 结构化摘要 + 退出码收口

> 目标：重置末段的父进程只读交叉验证与摘要打印，八档退出码全部落位。
> 依据：design §2.2.2-D/E；spec §6.1-3、§6.3。本组依赖组 2 完成（worker 结果行与新库终态就绪）。

### 3.1 实现 sqlite3 只读交叉验证

- [x] 在 `reset_demo_data.py` 中实现验证环节：父进程以标准库 `sqlite3` 只读连接（`mode=ro` URI）直查新库——`knowledge_items WHERE scope='public'` 取 `title/status/chunk_count` 作为摘要主数据源；`knowledge_chunks GROUP BY item_id` 行数与 `chunk_count` 交叉一致；验证不通过（任一篇 `status != indexed`、`chunk_count <= 0` 或行数不一致、数量 ≠4）→ exit 6；该验证函数同时被主链末段与 `--verify-only` 隐藏入口复用（后者仅执行「配置探测 + 本验证 + 验证摘要」，不执行占用检测、确认、备份、删除、初始化、重索引，不产生任何写操作）。
- 涉及文件：`backend/scripts/reset_demo_data.py`
- 实现要点：父进程不用 ORM（零 app import 铁律）；只读模式防误写；与 worker 侧三条件回查同一口径（双源互证）。
- 对应章节：spec §5.1.1 规则 6a、§4.2-4a；design §2.2.2-D 验证查询方式裁决、§2.2.2-B 第三条件、§2.2.2-A `--verify-only` 参数行。
- 完成判据：① 正常重置后执行 `python scripts/reset_demo_data.py --verify-only` → exit 0；② 复制 `data/smartlearn.db` 为临时库副本（如 `backend/tmp_verify/verify_fail.db`），用标准库 `sqlite3` 把该副本中某篇 `chunk_count` 改成与 `knowledge_chunks` 行数不符的值，以 `DATABASE_URL=sqlite:///<临时库>` 进程环境变量执行 `--verify-only` → exit 6；③ 两次执行前后确认没有新增备份目录、没有删除/重建任何文件（`--verify-only` 全程零写操作）；真实库与 `.env` 均未被修改。

### 3.2 实现结构化摘要打印

- [x] 在 `reset_demo_data.py` 中实现摘要块，版式对齐 design §2.2.2-D：标题行「SmartLearn 演示数据重置完成」、数据库路径（标注「已重建」）、演示账号 `demo / 123456`（附「仅供开发演示，请勿用于生产环境」）、备份目录路径（`--no-backup` 时显式打印「未备份（--no-backup）」）、演示知识库 4 篇逐行 `[OK] 标题 — N chunks`（仅离线兜底篇目附 `(offline 兜底)`；失败篇目 `[FAIL] 标题 — 原因`，禁止虚假数字）、可选验证查询命令、下一步提示；全文中文、不打印任何密钥。
- 涉及文件：`backend/scripts/reset_demo_data.py`
- 实现要点：worker 的逐篇结果行原样透传进摘要块；分块数一律来自任务 3.1 的真实查询，禁止硬编码（spec §5.1.1 规则 6）。
- 对应章节：spec §6.3 全部四项、§4.4-1、§4.3-3；design §2.2.2-D 摘要块版式。
- 完成判据：重置成功后 stdout 含上述全部要素；`python scripts/reset_demo_data.py --yes --no-backup` 的摘要备份行逐字为「未备份（--no-backup）」；摘要中检索不到 `.env` 内任何密钥明文。

### 3.3 核对八档退出码全路径

- [x] 对照退出码表逐档触发核对：0（成功）/ 1（参数错误、用户取消、非 TTY 无 `--yes`）/ 2（三道防线占用）/ 3（备份失败）/ 4（删除失败）/ 5（初始化子进程失败）/ 6（重索引失败或验证不通过）/ 7（配置加载失败、非 SQLite 形态）；每档的触发路径、提示文案、备份保留行为与 design §2.1.3-C 失败行为表一致。
- 涉及文件：`backend/scripts/reset_demo_data.py`
- 实现要点：3/4/5 档可用临时构造（如备份根目录设为只读、占用 uploads 文件）触发；exit 7 档用进程环境变量 `JWT_SECRET=` 置空触发（**不修改 `.env`**）；每档触发后环境必须恢复原状。
- 对应章节：spec §6.1-3、§5.1.3 各场景；design §2.2.2-E、§2.1.3-C 失败行为表。
- 完成判据：逐档实跑记录「命令 → 退出码 → 首行提示」，八档全部与表一致；所有构造的故障均已清除。另含路径安全守卫档（组 3 增补）：`UPLOAD_DIR`/`CHROMA_DIR`/`DATABASE_URL` 指向 `data/`、项目根或 `.env` 文件本身时，`validate_protected_paths` 在占用检测/确认/备份/删除之前拦截 → exit 7 且零写操作；主链与 `--verify-only` 均复用该守卫。

## 4. 编写 docs/DEMO_SCRIPT.md（默认 5 分钟版 + 可选加长版，PlanView 主路径）

> 目标：交付演示者可照做照读的分镜脚本。
> 依据：design §2.4.1 结构骨架与写作约束；spec §5.2；`docs/需求文档.md` 第 32 节；`docs/WALKTHROUGH_PLAN_REPORT_FRONTEND.md` W1–W12 事实。本组依赖组 3 完成（摘要口径与验证命令定稿后方可引用，spec §5.3.1-3 一致性规则的同源要求）；写作时允许与组 5 并行。

### 4.1 编写前置检查清单（6 项）

- [x] 在 `docs/DEMO_SCRIPT.md` 中编写前置检查章节，6 项逐项给出命令与「通过标志」：① 执行重置 `cd backend && python scripts/reset_demo_data.py --yes`（通过：摘要含备份路径 + 4 篇 `[OK]` + 退出码 0）；② 启动前后端（通过：`/health` 返回 code=0）；③ 登录 demo / 123456（通过：Dashboard 各卡片有数据）；④ 演示知识库 4 篇均 indexed 且分块数 > 0（通过：知识库页可见 4 篇；或 `GET /api/v1/knowledge/items` 按 file_path 前缀 data/uploads/1/ 核对为 4 篇——真实端点口径）；⑤ 周报有数据（通过：报告页可见上周周报）；⑥ 自备上传文件：复制 `data/uploads/1/2_linear_algebra_notes.md` 副本到桌面（4 篇演示文件重置后保留，第二幕上传副本作为新文档）。
- 涉及文件：`docs/DEMO_SCRIPT.md`（新增）
- 实现要点：命令与摘要素材逐字对齐组 3 实际输出；端点写 `GET /api/v1/knowledge/items`（`/knowledge/public` 不存在，spec §5.4.1-2.c 勘误口径）。
- 对应章节：spec §5.2.1 规则 1；design §2.4.1 骨架第①段、§1.2.6。
- 完成判据：按清单逐项实走，每项都能观察到文档所写的通过标志；清单中每条命令在当前仓库可直接执行。

### 4.2 编写五步分镜 + Dashboard 收尾幕（每幕三小节，默认 5 分钟版）

- [x] 在 `docs/DEMO_SCRIPT.md` 中编写五幕 + 收尾幕，每幕固定三小节「操作路径 / 预期界面 / 口播词（30–45 秒中文成稿可直接照读）」：第 1 幕创建目标 AI 拆解（目标页 →「创建学习目标」→ 输入「6个月掌握机器学习」）；第 2 幕上传资料进知识库（上传桌面备用 md → 轮询状态到 indexed，状态 pending→parsing→indexed 流转可见）；第 3 幕 Agent 分析学习状态（Agent 对话页输入「我最近感觉机器学习学得很乱，帮我分析一下」，预期流式输出 + 工具调用痕迹）；第 4 幕生成下周计划——固定走 `/plans` 工具栏「生成下一周学习计划」（W2 已验证路径，全程停留 /plans，信息头出现「下周计划」标注且按钮结束 loading 后再继续）；第 5 幕任务未完成动态调整——固定走 `/plans` 周视图「重新调整计划」→ diff 双栏预览 →「查看调整后的计划」/「关闭对比」/ ESC（W4/W5 已验证路径）；收尾幕 Dashboard 学习画像（趋势图近 5 天递减、掌握度雷达/薄弱点、风险预警）。
- 涉及文件：`docs/DEMO_SCRIPT.md`
- 实现要点：编写前逐条对照 WALKTHROUGH 文档 W1–W12 的实际操作路径与预期核对，**不凭想象写界面**；第 4/5 幕只写 PlanView 主路径（Agent 触发计划/调整如要提及，必须标注「需先走查确认，不作为主路径」）；预期界面只写既有元素——不出现「v2 徽章」等不存在元素；diff 预览描述对齐 W4 事实（adjust_reason 全文显著、移出/新增标记）；关闭对比/ESC 路径出现「新计划已生效」轻提示；口播词逐句成稿，总时长五幕 + 收尾约 5 分钟。
- 对应章节：spec §5.2.1 规则 2、§2 五步演示剧本术语；design §2.4.1 骨架第②段与写作约束；需求文档第 32 节。
- 完成判据：逐幕对照前端实况走读，操作路径上的每个页面/按钮在当前前端代码中真实存在（可 grep `frontend/src/views/PlanView.vue` 中「生成下一周学习计划」「重新调整计划」等文案佐证）；五幕口播词朗读计时合计在 5 分钟 ±30 秒内。

### 4.3 编写常见问题四类 + 回滚指引附录

- [x] 在 `docs/DEMO_SCRIPT.md` 中编写常见问题章节：① 登录失败（排查顺序：后端是否启动 → 是否已执行重置 → 数据库路径；附备用话术与现场重跑重置指引）；② 知识库检索无结果（先确认 4 篇演示文档 indexed；换用随文档给出的预置问题清单，问题与 4 篇文档内容强相关）；③ LLM 不可用（降级话术「现场网络波动，系统已切换到本地检索结果」；指明周报/计划等不依赖实时 LLM 的环节可继续）；④ 目标拆解失败（改用种子目标「6个月掌握机器学习核心算法」继续演示，不阻塞后续计划生成与报告演示）；附录回滚指引逐字对齐 spec §4.2-3：停后端 → `data/_reset_backup/<YYYYmmdd-HHMMSS>/` 下主文件及 `-wal`/`-shm` 复制回原库路径覆盖 → 重启后端；向量库与上传目录不备份不回滚，由重新执行重置再生成。
- 涉及文件：`docs/DEMO_SCRIPT.md`
- 实现要点：预置问题清单至少 3 条，逐条能在 4 篇演示文档（ml_basics / linear_algebra_notes / probability_formulas / ds_cheatsheet）中找到答案依据。
- 对应章节：spec §5.2.1 规则 3、§5.2.3 场景 1/2/3、§4.2-3；design §2.4.1 骨架第③④段。
- 完成判据：模拟 LLM 不可用走查第 3 幕——用启动后端时的进程环境变量（如临时错误的 `LLM_BASE_URL`）或浏览器 DevTools 断网模拟，**不修改 `.env`** → 演示者可按脚本给出不暴露技术故障的降级话术并继续演示；回滚指引与 spec §4.2-3 逐字一致。

### 4.4 追加可选「8–10 分钟加长版」章节 + 全篇禁止项自查

- [x] 在 `docs/DEMO_SCRIPT.md` 末尾追加加长版附加章节：明确标注「可选，非默认」，逐幕标注哪些幕可展开（如第 3 幕追加追问、第 5 幕走 W12「查看调整记录」回看路径、收尾幕展开报告导出 W10）；随后全篇自查：不出现 Docker / 云部署步骤，不要求修改产品代码或真实密钥。
- 涉及文件：`docs/DEMO_SCRIPT.md`
- 实现要点：加长版引用的 W10/W12 路径同样以 WALKTHROUGH 已验证事实为准。
- 对应章节：spec §5.2.1 规则 4；design 裁决速查表 #6、§2.4.1 写作约束。
- 完成判据：`grep -in "docker\|云部署" docs/DEMO_SCRIPT.md` 无命中；加长版章节首行含「可选」标注，默认路径仍是 5 分钟版。

## 5. 修订 README.md 四项内容补齐

> 目标：在现有八章基础上只补不推翻，补齐比赛四项要求。
> 依据：design §2.4.2；spec §5.3。本组依赖组 3 完成（重置命令、摘要样式、账号、地址逐字对齐脚本实际行为）；允许与组 4 并行。

### 5.1 修订「环境要求」+ 新增「演示数据一键重置」节

- [x] 修订 `README.md`「一、环境要求」：保留现有版本表，补「后端 `pip install -r requirements.txt`、前端 `npm install`、一键 `start.bat` / `start.sh`」的串链说明；在「五、一键启动」之后新增「演示数据一键重置」节：`cd backend && python scripts/reset_demo_data.py --yes` 命令、`--yes` / `--no-backup` 语义、预期摘要样例（以组 3 真实跑出的摘要为准贴样例，分块数为真实数字）、演示知识库索引确认方式（知识库页 + 可选验证查询命令）、demo / 123456 账号、常见启动失败处理（8000/5173 端口占用识别与释放、重置后无法登录的排查：核对重置摘要是否完整出现初始化完成 + 4 篇分块验证行，必要时重新执行重置）；节内**明确声明本项目不提供 Docker 容器化与云部署**；同步修订「七、验证方式」中骨架期占位描述为真实登录验证口径。
- 涉及文件：`README.md`（修改）
- 实现要点：摘要样例必须来自真实执行输出（design 未决点 1：真实分块数实跑才知）；依赖安装失败处理给出最低版本核对与镜像源建议（spec §5.3.3 场景 1）。
- 对应章节：spec §5.3.1 规则 1a/1b、§5.3.3 场景 1/2/3；design §2.4.2 表第 1/2 行。
- 完成判据：按新增节逐步操作可在干净环境完成重置并登录；`grep -n "演示数据一键重置" README.md` 命中且节内含「不提供 Docker 容器化与云部署」声明。

### 5.2 新增「数据集与开源组件说明」章

- [x] 在 `README.md` 新增独立章：`data/uploads/1/` 4 篇演示上传文件（1_ml_basics / 2_linear_algebra_notes / 3_probability_formulas / 4_ds_cheatsheet）的来源与用途（课程笔记型自编材料，供知识库检索演示）；主要开源组件清单（SQLite、FastAPI、Vue 3、Element Plus、Chroma、pypdf、OpenAI 兼容 API 等）；声明未使用外部受限数据集。
- 涉及文件：`README.md`
- 实现要点：组件清单与 `backend/requirements.txt`、`frontend/package.json` 实际依赖一致，不列未使用的组件。
- 对应章节：spec §5.3.1 规则 1c；design §2.4.2 表第 3 行。
- 完成判据：章节中 4 篇文档名与 `data/uploads/1/` 实际文件逐一对应（`ls data/uploads/1/` 比对）；组件清单抽查 3 项均能在依赖文件中找到。

### 5.3 新增「码道（CodeArts）使用说明」章

- [x] 在 `README.md` 新增独立章：写明码道（CodeArts）参与的开发环节（需求、设计、编码、测试辅助）与各自作用描述。
- 涉及文件：`README.md`
- 实现要点：表述与项目实际使用过程一致，不夸大不虚构。
- 对应章节：spec §5.3.1 规则 1d；design §2.4.2 表第 4 行。
- 完成判据：`grep -n "码道" README.md` 命中独立章节，内容覆盖需求/设计/编码/测试四类环节。

### 5.4 README 一致性核对与禁止项自查

- [x] 全文核对：README 中重置命令、摘要样式、账号、访问地址与脚本实际行为逐字一致；保留现有仍然有效的八章内容未被推翻重写；全文检索禁止项。
- 涉及文件：`README.md`
- 实现要点：一致性以组 3 真实输出为唯一基准（spec §5.3.1-3）；保留性对照 git diff 确认既有章节仅有增补与占位修正。
- 对应章节：spec §5.3.1 规则 2/3、§4.5-1；design §2.4.2 禁止项落地。
- 完成判据：除「本项目不提供 Docker 容器化与云部署」这一行声明句外，README 不得出现 Docker / docker-compose / 云部署的操作指引或章节；`grep -in "docker\|docker-compose\|云部署" README.md` 命中仅允许该声明行；`git diff README.md` 显示既有章节保留、新增为两章一节加两处修订；README 每条命令实跑输出与文档描述相符。

## 6. 收尾验收（最终门禁 G1–G6）

> 目标：全部产物就绪后按最终门禁逐条实跑验收，贴真实输出。
> 依据：spec §5.4.1；design 第三章验收映射。本组依赖组 1–5 全部完成。

### 6.1 门禁 G1：重置连跑两次（幂等验证）

- [x] 停后端后连续执行两次 `cd backend && python scripts/reset_demo_data.py --yes`，记录两次完整输出与退出码。
- 涉及文件：`backend/scripts/reset_demo_data.py`（验证对象）
- 实现要点：两次均默认备份（不带 `--no-backup`），第二次输出同样含备份路径（撞名序号后缀生效）、demo 账号提示与 4 篇分块验证行。
- 对应章节：spec §5.4.1-1、§5.1.1 规则 7、§4.2-1；design 第三章映射表第 1 行。
- 完成判据：两次退出码均 0；第二次无报错；两份摘要均含备份目录路径、demo / 123456 提示、4 篇 `[OK]` 分块行；两个备份目录并存互不覆盖。

### 6.2 门禁 G2：索引终态三条件验证

- [x] 重置完成后用标准库 `sqlite3` 查询新库：4 篇演示文档 `status='indexed'`、每篇 `chunk_count > 0`、每篇 `chunk_count == (SELECT COUNT(*) FROM knowledge_chunks WHERE item_id=?)`；并确认 `data/uploads/1/` 4 篇源文档与 `.env` 内容未变（与开工前哈希比对）。
- 涉及文件：验证对象 `data/smartlearn.db`、`data/uploads/1/`、`.env`
- 实现要点：查询命令即摘要中「验证查询（可选）」行所附命令，可照抄执行。
- 对应章节：spec §5.1.1 规则 1a/6a、§4.2-4a、§4.3-1；design §2.2.2-B/D。
- 完成判据：查询返回 4 行且三条件逐篇成立；`data/uploads/1/` 与 `.env` 哈希与开工前一致。

### 6.3 门禁 G3：后端 pytest 全绿

- [x] 执行 `cd backend && pytest -q`，记录尾部统计行。
- 涉及文件：验证对象 `backend/tests/`（零改动）
- 实现要点：若结果非 206 passed，必须在汇报中逐条说明差异原因；确认 `scripts/reset_demo_data.py` 未被收集（收集总数与基线一致）。
- 对应章节：spec §5.4.1-2.a、§1.4-6；design §1.2.5、风险 R6。
- 完成判据：尾部输出 `206 passed`（或附原因说明的差异结果）；收集数不含 `reset_demo_data.py`。

### 6.4 门禁 G4：前端构建通过

- [x] 执行 `cd frontend && npm run build`，记录退出码与构建结果。
- 涉及文件：验证对象 `frontend/`（`src/**` 零改动）
- 实现要点：失败贴原文输出，禁止虚报。
- 对应章节：spec §5.4.1-2.b、§5.4.1-5。
- 完成判据：exit 0，构建产物正常生成。

### 6.5 门禁 G5：git 基线对比 + 受保护路径复核

- [x] 收工时执行 `git status --short -uall` 与任务 1.1 记录的开工基线逐条对比；并复核未创建 Docker / 云部署文件、未执行任何 commit。
- 涉及文件：仓库根（验证对象）
- 实现要点：允许新增集 = `backend/scripts/reset_demo_data.py`、`docs/DEMO_SCRIPT.md`、`docs/designs/DESIGN_DEMO_RESET.md`、`docs/tasks/TASKS_DEMO_RESET.md` 及 `README.md` 改动；**G6 发现并修复的 P4 bug 例外**：`frontend/src/utils/goal.ts`（`toEChartsTree` 的 `children` 判空，一行）已获用户授权；除此之外 `backend/app/`、`frontend/src/`、`backend/tests/` 不得新增任何改动条目（基线中 P13 已存在的条目保持原样不算新增）。
- 对应章节：spec §5.4.1-4、§5.1.1 规则 9a、§1.4-1/5；design 第五章文件清单。
- 完成判据：对比结果只多出允许新增集；`git status --short backend/app/ frontend/src/` 相对基线零新增；`git log` 无本轮新 commit；仓库内无 `Dockerfile` / `docker-compose.yml` / `docs/DEPLOY_HUAWEI.md`。

### 6.6 门禁 G6：DEMO_SCRIPT 5 分钟版实际走查

- [x] 按 `docs/DEMO_SCRIPT.md` 前置检查清单 → 五幕 → 收尾幕实际走查一遍（重置后启动前后端、demo 登录、逐幕操作），记录每幕结果与口播计时。

> **G6 实施记录（2026-10-24，浏览器自动化）**：操作走查完成。第 1 幕首次暴露 `toEChartsTree()` 未判空导致 `Cannot read properties of undefined (reading 'map')`，已修复 `frontend/src/utils/goal.ts` 一行并复测通过（知识树 35 个知识点正常渲染）；第 2 幕上传 `linear_algebra_notes.md`，轮询至 indexed（8 chunks）；第 3 幕 Agent 约 28s；第 4 幕生成下周约 14s；第 5 幕 diff + 确认通过；Dashboard 通过。**口播计时未实际朗读，建议现场复核**。截图见仓库外 `.tools/g6-shots/`。
>
> 另：G6 复跑时发现未激活 venv 时 README 的 `python scripts/...` 会让子进程缺依赖；脚本已改为自动使用 `backend/.venv` 解释器，系统 Python 复跑 exit 0，4 篇演示文档重新 indexed（8/8/8/9）。
- 涉及文件：`docs/DEMO_SCRIPT.md`（验证对象）
- 实现要点：第 4/5 幕严格走 `/plans` 工具栏主路径（W2/W4/W5）；任一环节与脚本描述不符即记录差异并修订文档后重走该幕；走查结果（含每幕通过/差异、总时长）写入本轮汇报。
- 对应章节：spec §5.2.1 规则 1a/2a、§5.4.1-3；design §2.4.1、风险 R9。
- 完成判据：五幕 + 收尾幕全部按脚本完成，演示者无需即兴发挥；总时长约 5 分钟；走查记录（每幕结果 + 计时）形成文字留档。

---

## 附 A：spec 验收条件 → 任务 映射表（覆盖率自检）

| spec 验收条件 | 覆盖任务 |
|---|---|
| §5.4.1-1 重置验证（连跑两次、摘要三要素） | 3.2、6.1 |
| §5.4.1-2.a 后端测试 206 passed | 1.1（防收集）、6.3 |
| §5.4.1-2.b 前端构建通过 | 6.4 |
| §5.4.1-2.c 演示文档 4 条（真实端点核对） | 2.2（种子 4 篇）、4.1（清单第 ④ 项）、6.2 |
| §5.4.1-2.d demo/123456 登录返回 token | 2.2（种子含 demo）、4.1（清单第 ③ 项）、6.6（实登走查） |
| §5.4.1-3 文档交付（DEMO_SCRIPT / README） | 4.1–4.4、5.1–5.4 |
| §5.4.1-4 git 基线对比 | 1.1（开工基线）、6.5（收工对比） |
| §5.4.1-5 汇报纪律（真实输出） | 6.1–6.6 全部判据（贴原文） |
| §5.1.1-1a 路径解析（uploads 4 篇/.env 原样） | 1.3、2.1、6.2 |
| §5.1.1-2a 占用拒绝（非零退出 + 提示 + 不删不杀） | 1.4、6.1（前置停后端） |
| §5.1.1-3a 备份目录含完整副本 | 1.6、6.1 |
| §5.1.1-4a `--yes` 无阻塞一次完成 | 1.2、1.5、6.1 |
| §5.1.1-5a 重建后 demo 登录且数据齐全 | 2.2、6.6 |
| §5.1.1-6a 4 篇 indexed 且 chunk>0；失败如实标示 | 2.3、2.4、3.1、3.2、6.2 |
| §5.1.1-7a 幂等第二次不报错 | 1.6（撞名后缀）、6.1 |
| §5.1.1-8 实现约束（标准库 + 复用存量 + 直调服务层） | 1.6、2.2、2.3 |
| §5.1.1-9a git status 无 app/前端改动 | 6.5 |
| §4.2-2/3 备份可回滚 + 回滚指引 + 失败不半成品 | 1.6、2.1、2.2（exit 5 提示）、3.3、4.3（附录） |
| §4.2-4/a 重建必须真正生效（全新后端视角验证） | 1.3（探测子进程）、2.2/2.3（子进程链）、3.1、6.2 |
| §4.3-1 受保护路径红线 | 2.1、6.2 |
| §4.3-2 不杀进程 | 1.4、3.3（exit 2 档核对） |
| §4.3-3 不打印密钥 | 1.3、3.2 |
| §5.2.1-1a 前置检查可观察通过标志 | 4.1、6.6 |
| §5.2.1-2a 五步分镜可照做照读 | 4.2、6.6 |
| §5.2.1-3a LLM 不可用降级话术 | 4.3、6.6（模拟断网走查） |
| §5.2.1-4 脚本禁止容器化/云部署 | 4.4（自查） |
| §5.3.1-1a 环境依赖与一键安装 | 5.1 |
| §5.3.1-1b 本地运行与复现步骤（评审可按 README 复现） | 5.1、5.4 |
| §5.3.1-1c 数据集与开源组件说明 | 5.2 |
| §5.3.1-1d 码道（CodeArts）使用说明 | 5.3 |
| §5.3.1-2a README 无 Docker/云部署 | 5.1（声明）、5.4（检索） |
| §5.3.1-3a README 与实际行为一致 | 5.1（真实摘要样例）、5.4 |
| §4.1 性能（10 分钟红线 / 不新增依赖） | 2.3（串行 4 篇次分钟级）、1.6（仅标准库）、6.1（两跑实计） |
| §4.4 可维护性（摘要可核对 / 文档可照做） | 3.2、4.2、6.6 |
| §4.5 兼容性（README 保留既有内容 / Windows 与 macOS/Linux 兼容） | 5.4、1.4（防线 3 按 os.name 门控） |
| §6.1-3 退出码（0 成功 / 异常非 0） | 1.2–3.3（各档落位）、3.3（全档核对） |
| §6.2 备份目录（位置/命名/内容） | 1.6、6.1 |
| §6.3 摘要四要素 | 3.2 |
| §6.4 DEMO_SCRIPT 结构（前置/分镜/常见问题） | 4.1、4.2、4.3 |

自检结论：spec §5.4.1 五条验收口径、§5.1.1 九条规则（含子条款 a）、§4.1–4.5 DFX 条款、§5.2/§5.3 规则与 §6.1–6.4 数据约束全部有任务落点；本文档 6 组 27 个子任务均服务于上述条款，无孤儿任务。

## 附 B：任务依赖图

```
组 1（父进程：1.1 基线骨架 → 1.2 CLI → 1.3 配置探测 → 1.4 占用检测 → 1.5 确认 → 1.6 备份）
        │（1.3/1.4/1.5/1.6 是 2.1 的前置；同组内按序执行）
        ▼
组 2（2.1 删除[依赖 1.4/1.6] → 2.2 init 子进程 → 2.3 worker 实现 ∥ 2.4 父进程串接[2.4 依赖 2.3 契约定稿]）
        │
        ▼
组 3（3.1 只读验证 → 3.2 摘要 → 3.3 八档退出码核对）
        │（摘要口径与 CLI 定稿）
        ├──────────────► 组 4（4.1 → 4.2 → 4.3 → 4.4，另依赖 W1–W12 既有事实）
        └──────────────► 组 5（5.1 → 5.2 → 5.3 → 5.4）   ※ 组 4 与组 5 可并行
        ▼
组 6（6.1 → 6.2 → 6.3 ∥ 6.4 → 6.5 → 6.6；全部依赖组 1–5 完成）
```

---

> 纪律声明：本任务清单仅描述「做什么 + 做到什么程度」，不含具体代码实现；编码由实现阶段执行。所有验证任务必须贴真实输出，无法验证的写「未验证」，禁止虚报。
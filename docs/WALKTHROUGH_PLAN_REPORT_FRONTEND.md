# P13 计划/报告前端 · 本机走查交接（W1–W13）

> **状态：已完成自动化验证（2026-10-24，Claude Code + puppeteer-core 驱动本机 Chrome；W1–W12 通过，W13 可选未执行）。** 证据见文末「自动化验证记录」。建议人工复验至少复核 W4 双栏视觉、W5 三条路径与 W6 错误卡。
>
> 上游依据：`docs/specs/SPEC_PLAN_REPORT_FRONTEND.md`（633 行定稿）、`docs/designs/DESIGN_PLAN_REPORT_FRONTEND.md`（959 行定稿）、`docs/tasks/TASKS_PLAN_REPORT_FRONTEND.md`（8.3 节 W1–W13 原始表述）。
>
> 沙箱侧已完成：`npm run build` 通过（vue-tsc 零报错）+ 全部静态 grep 检查通过（见 tasks 8.1）。**最终判据写死：「`npm run build` 通过 + 本机走查 W1–W13 全部通过」，两者缺一不可交付。**

## 前置条件

1. 后端已启动（`cd backend && uvicorn app.main:app --reload`，或既有启动方式），演示数据已重置；
2. `cd frontend && npm run dev` 前端已启动；
3. 可登录测试账号（一个**有当前计划**的账号用于 W1/W4–W6/W12；一个**空态账号**或先归档现有计划用于 W2 空态路径）；
4. 浏览器打开 DevTools「网络」面板全程观察请求序列；
5. W6 需要 DevTools「离线」开关（或请求拦截工具）；W13 需要修改后端 `.env` 的 `LLM_BASE_URL` 并重启后端（可选环境）。

## 走查表（W1–W13）

| 编号 | 操作 | 预期（请求序列 + 界面） | 结果（待填） | 证据（截图/文字） |
|---|---|---|---|---|
| W1 | 有当前计划的账号打开 `/plans` | **仅 1 次** `GET /plans/current` 完成首屏；7 列（周一~周日）× 3 行（上午/下午/晚上）网格，列头日期与计划周期一致；抽查 19:00 条目在「晚上」行、14:00 条目在「下午」行；周五休息条目（若有）在独立休息区块、不占三时段行；planned 条目左侧醒目色条、done 条目灰显对勾；条目卡片四类信息齐全 | | |
| W2 | 空态账号（或工具栏入口）点「生成下一周学习计划」 | 按钮 loading 且仅 1 次 `POST /plans/generate`；周视图立即渲染下周完整网格（不显示空态）、信息头含「下周计划」标注；unplaced_tasks 非空时下方提示卡含标题与原因、空数组时无卡片占位；全程停留 /plans 无跳转 | | |
| W3 | W2 之后刷新页面 | 重新出现且仅 1 次 `GET /plans/current`；若本周另有 active 计划则显示本周计划，否则显示空态（会话态不持久，预期行为） | | |
| W4 | 周视图点「重新调整计划」 | 按钮全程锁定；网络面板依序出现 `POST /plans/{id}/adjust` →（可选）`GET /plans/current` →（必要时）1..N 次 `GET /learning-plan-items?page=N&page_size=100`；**全程无** `GET /plans/{id}/diff`、无任何确认/提交类请求；diff 预览顶部 adjust_reason 全文显著可见；双栏中被移动条目两栏均有醒目标记、removed 左栏标「移出」、added 右栏标「新增」；底部清单含挪动描述（涉及休息条目时显示「休息时段」）；**右栏与后续周视图为新版本条目，不出现本周计划内容** | | |
| W5 | 在 diff 预览分别走两条路径：① 点「查看调整后的计划」② 再次调整后点「关闭对比」③ 再次调整后按 ESC | 三条路径均**零新请求**切为新版本周视图；路径①无提示；路径②③出现「新计划已生效」轻提示；预览与切换后网格内容一致（同一份条目） | | |
| W6 | 调整成功后、learning-plan-items 阶段用 DevTools 设 offline（或拦截该请求置失败） | 页面出现**独立错误卡**，文案含「**计划调整已生效，但新版本条目暂时加载失败**」（不得只写「加载失败」）；不出现旧网格冒充新版本；点「重新加载」→ 发出 1 次 `GET /plans/current`，页面恢复到当前生效计划或空态 | | |
| W7 | 三个按钮分别在请求飞行期间重复点击（可用 DevTools 降速模拟）：「生成下一周学习计划」「重新调整计划」「生成报告」 | 均不发起第二次请求（按钮 loading/禁用态生效） | | |
| W8 | 打开 `/reports`；依次切 日报 → 周报 → 月报 → 周报；点分页器第 2 页 | 首屏仅 1 次 `GET /reports?report_type=weekly&page=1`；每类型至多首次各 1 次请求，回到周报**零请求**渲染缓存；点第 2 页 → 1 次 `page=2` 请求并渲染该页；任意卡片头部肉眼即见「{period_start} 至 {period_end}」区间（无需展开正文）；空 tab 显示空态 + 生成引导、无分页器 | | |
| W9 | 周报 tab 点「生成报告」 | 请求体仅 `{"report_type":"weekly"}`（无 period_end）；成功后列表自动重载 page=1，第一张卡片为刚生成的报告（无需手动刷新） | | |
| W10 | 点某卡片「导出 Markdown」，用文本编辑器打开下载文件 | 网络面板**零新请求**；文件名形如「学习周报_2026-10-12_2026-10-18.md」；首行为含区间的一级标题；引言含区间重申与生成时间；七个分区（有数据时）齐全；weak_points 为空的报告该节显示「本期无明显薄弱知识点」且文件完整；结尾「生成方式」标注；**全文无「undefined/null」字样** | | |
| W11 | 断网点「生成下一周学习计划」；恢复网络重试；token 过期后访问 /plans | 断网弹「网络异常，请稍后重试」，页面不白屏、保持可用的空态/原视图；恢复网络重试成功；token 过期自动跳 /login（既有行为不回退） | | |
| W12 | 对 parent_plan_id 非空的计划，信息头点「查看调整记录」 | 发出 1 次 `GET /plans/{id}/diff`；回看视图可见 adjust_reason 与三类改动清单、**无双栏网格、无任何应用/确认按钮**；点「返回周视图」→ 零请求回到原周视图且数据不变；首版计划（parent_plan_id=null）无该入口；diff 空结构时显示「该版本无调整记录」 | | |
| W13 | （可选环境）改错后端 `.env` 的 `LLM_BASE_URL` 重启后端 → 生成计划 / 生成报告；之后恢复正常配置 | 生成计划成功但信息头显示「规则降级」徽章 + 页面出现降级提示；生成报告成功但卡片显示「规则模板」徽章（数字仍为真实统计）；恢复后徽章回到「LLM 规划 / LLM 总结」且无降级提示 | | |

## 四条关键请求序列（验收基准）

1. **W1 首屏**：仅 1 次 `GET /plans/current`（data=null 时空态，不追加任何请求）。
2. **W4 调整**：`POST /plans/{id}/adjust` →（可选）`GET /plans/current` →（必要时）1..N 次 `GET /learning-plan-items`（page_size=100，MAX_PAGES=50 硬上限）；**全程不出现** `GET /plans/{id}/diff`（该端点仅供 W12 回看路径）。
3. **W5 切换**：「查看调整后的计划」/「关闭对比」/ ESC → **零请求**；仅关闭/ESC 路径出现「新计划已生效」。
4. **W8 报告 tab**：首屏仅 weekly 1 次请求；切 tab 已加载**零请求**；分页真实请求（page_size=10）。

## 自动化验证记录（2026-10-24）

**环境**：本机 Chrome（headless）+ puppeteer-core 23.11.1；后端 `127.0.0.1:8000`，前端 `127.0.0.1:5173`；账号 `demo / 123456`。
**方法**：真实登录 → 真实点击 → 记录 Network 请求序列与页面文本；不是 mock。

| 编号 | 结果 | 关键证据 |
|---|---|---|
| W1 | 通过 | 打开 /plans 后仅 1 次 `GET /plans/current`；标题「机器学习第 7 周学习计划」；7 列网格；14:00 条目在下午行、19:00 条目在晚上行 |
| W2 | 通过 | 仅 1 次 `POST /plans/generate`；标题变为「学习计划（2026-10-26 ~ 2026-11-01）」；「下周计划」tag 出现 |
| W3 | 通过 | 刷新后仅 1 次 `GET /plans/current`；回到本周 plan 5（会话态不持久） |
| W4 | 通过 | 请求序列：`POST /plans/{id}/adjust` → `GET /plans/current`（返回本周 plan，id 不匹配）→ `GET /learning-plan-items?page=1&page_size=100` → `page=2`；**无** `GET /plans/{id}/diff`；diff 预览出现，右栏为新版本条目 |
| W5 | 通过 | 主按钮 / 关闭对比 / ESC 三条路径均 **零请求**；关闭与 ESC 均出现「新计划已生效」，主按钮不出现 |
| W6 | 通过 | 请求拦截 `*learning-plan-items*` 后：adjust 成功、取数失败，出现错误卡，文案逐字为「计划调整已生效，但新版本条目暂时加载失败」；点「重新加载」仅发 1 次 `GET /plans/current` |
| W7 | 通过 | 生成按钮双击仅 1 次 `POST /plans/generate`；调整按钮双击仅 1 次 `POST /plans/{id}/adjust` |
| W8 | 通过 | 首屏仅 1 次 weekly 请求；切到日报发 1 次 daily 请求；切回周报 **零请求**；周报 3 张卡片 |
| W9 | 通过 | `POST /reports/generate` 返回 200；列表重载 `GET /reports?...page=1`；卡片数 3 → 4，新报告置顶 |
| W10 | 通过 | 导出 **零 API 请求**；下载文件名 `学习周报_2026-10-12_2026-10-18.md`；首行为含区间标题；正文无 `undefined/null`；含「生成方式：」 |
| W11 | 通过 | 拦截 `POST /plans/generate` 后点生成：出现「网络异常，请稍后重试」，页面仍显示周视图，未白屏 |
| W12 | 通过 | 发出 1 次 `GET /plans/{id}/diff`；回看视图可见理由与清单、**无双栏网格**；「返回周视图」零请求 |
| W13 | 未执行 | 需要改后端 `.env` 的 `LLM_BASE_URL` 并重启，属可选环境；未验证 |

**W4 初次“不能调整”的定位**：第一次自动化点击「重新调整计划」时，`POST /plans/generate` 仍在飞行中，调整按钮处于 `disabled`（`:disabled="generating"`），点击不会发请求，看起来像“不能调整”。等到信息头出现「下周计划」、生成按钮结束 loading 后再点，adjust 正常。**这是预期防重行为，不是 bug。**

**自动化发现并已修复的视觉 bug**：W4 diff 双栏在 1440px 下右栏被挤出视口（`.pane` 作为 grid item 的 `min-width:auto` 被 WeekGrid 的 912px 最小宽度撑开）。修复：
- `PlanDiffPreview.vue`：`.dual-pane` 改为 `minmax(0,1fr) minmax(0,1fr)`，`.pane { min-width: 0 }`；
- `WeekGrid.vue`：compact 模式列宽改为 `56px repeat(7, minmax(0,1fr))` + `min-width:560px`。
修复后复测：`documentElement.scrollWidth = clientWidth = 1440`，两个 pane 各 588px，双栏 7 天完整并排；`npm run build` 通过（7.00s）。

**截图证据**：`C:\Users\段大磊\Desktop\项目提示词\.tools\walkthrough-shots\`（W1/W2/W4/W5a/W5b/W5c/W6/W12/W3/W8/W9/W10/W11 及修复后的 `W4-diff-fixed.png`）。该目录在仓库外，仅作本机证据，不随提交包分发。

**数据库变更**：自动化验证过程会真实创建计划/报告（每轮 generate/adjust 都落库）。验证前已备份：`data/_bak-walkthrough-20261024-133737.db`。若需恢复原始演示数据，停后端后用它覆盖 `data/smartlearn.db`。

## 发现问题的记录方式

- 每条不通过的 W 项：在「结果」列写「不通过」并在「证据」列贴请求序列截图与控制台报错；
- 与本批无关的既有问题（其他页面旧 bug）：另列清单记录，不在本文件判定；
- 全部通过后：在「结果」列逐条写「通过」并注明执行日期与执行人。
# Agent 前端对话页（agent_frontend）编码任务规划

> feature: `agent_frontend` ｜ 阶段：编码任务规划（spec-task-agent 产出）
> 上游输入：`docs/specs/SPEC_AGENT_FRONTEND.md`（R2 裁定定稿，606 行：8 项裁定 O1–O8 / F1–F13 验收标准 / §5.3 SSE 六事件消费状态机 / §5.4 工具卡片 / §5.6 历史回放 / §6 七文件拆分）、`docs/designs/DESIGN_AGENT_FRONTEND.md`（1071 行定稿：七文件架构 / agent.ts 与 chat.ts 十六项同构对照表 2.4.2 / ToolCallCard 四态视觉规格与 36px 高度锁定 2.4.1 / ViewMessage segments 建模 2.3.2 / buildViewMessages 两阶段配对算法 2.4.3 / 决策 A1–A12 / 实施顺序 2.7）、`docs/PROJECT_CONTEXT.md`（§7 前端约定：Vue3 script setup + TS 严格 / Element Plus / fetch+ReadableStream / token key=`smartlearn_token` / §7.3 request.ts 拦截器口径 / §8.2 前端编码规范）、P9 前端交付实测核对（行号见 §0 前置约定 5）
> 生成日期：2026-10-22 ｜ 状态：待用户确认
> 落盘路径说明：沿用对偶惯例——`SPEC_` ↔ `DESIGN_` ↔ `TASKS_`、`specs/` ↔ `designs/` ↔ `tasks/`（同 `docs/tasks/TASKS_AGENT_CHAT.md`），本文件落 `docs/tasks/TASKS_AGENT_FRONTEND.md`
> 已裁决事项继承（不再重开）：spec 8 项裁定 O1–O8（O1 四子组件独立文件 / O2 el-empty 空态 / O3 用户指定 4 快捷问题 / O4 首屏 50 条 / O5 禁切换+轻提示+停止常驻 / O6 文字行+行内 spinner / O7 维持「AI 助手」 / O8 弱化小字统计）+ 4 项冲突裁决（#1 停止为本阶段新增能力 / #2 types/agent.ts 独立文件 / #3 首屏单页 page_size=50 / #4 显式新建与空态直发两路径并存）；design 决策 A1–A12（摘要同行截断 / segments 保序 / 统一 ToolCallView 形态 / **A4 停止链路顺序锁死** / autoFollow 滞回 / 竞态双防护 / 调用中同 36px / delta 合并尾段 / 自绘折叠卡 / 局部 v-loading / thinking 弱化保留 / 历史 ok 判定含 error 键）；**R3 用户硬约束（aborted 判定必须为 catch 首句，先于任何错误分类逻辑，不得重排）**——本清单将其列为独立任务项（2.4 / 6.3）与三重验证锚点（§0 前置约定 7 / 7.3 / 8）
>
> **编号读法**：本文「决策 A4」指 design 2.8.1 设计决策；「验收 F7」指 spec §8.1 验收标准；「V1–V10」指 design 2.5.2 本机走查项（对 spec §8.3 V1–V7 的扩展）；「R1–R8」指 design 2.6 兼容性回归清单（勿与 spec 修订记录 R1–R3 混淆）。

---

## 0. 任务总览与依赖关系

**分组结构**（9 组，共 28 个子任务，实施顺序按 design 2.7 定稿：types → api → ToolCallCard → MessageItem+AgentComposer → ConversationList → AgentView 替换骨架 → build → 走查交接）：

```
组1 types/agent.ts ──→ 组2 api/agent.ts ─┬─→ 组6 AgentView.vue（替换骨架）──→ 组7 构建与回归 ──→ 组8 本机走查交接 ──→ 组9 文档同步收尾
组3 ToolCallCard.vue ────────────────────┤        ↑
组4 MessageItem+AgentComposer ───────────┤        │
组5 ConversationList.vue ────────────────┘        │
        （组3/4/5 依赖组1 类型，可与组2 并行；组6 汇合全部）─→ 组7 → 组8 → 组9
```

**关键路径**：1.2 → 2.3 → 2.4（R3）→ 6.2 → 6.3（R3）→ 6.5 → 7.1 → 7.3 → 8.1 → 9.2。

**可并行标注**：
- 组 1 是全部后续文件的编译依赖（类型先行，design 2.7 步骤 1）
- 组 2 / 组 3 相互零文件交集，可并行（组 4 依赖组 3 的 ToolCallCard）
- 组 4 / 组 5 零文件交集，可并行（均只依赖组 1）
- 组 6 依赖组 1–5 全部落地（状态编排汇合点）
- 组 9.1（文档裁定）无代码依赖，可任意时机执行；组 9.2 依赖组 7

**实施前置约定**（全文适用，各任务不再重复）：

1. **运行环境**：前端一律在 `frontend/` 目录下使用 npm（沙箱 `npm run build` 可用）；本机走查需后端 `uvicorn` 启动 + `.env` LLM 配置有效（组 8 前置）。
2. **构建链路**：`npm run build` = `vue-tsc --noEmit && vite build`（`frontend/package.json:8` 实测）——TS 严格模式零错误是硬门槛（F12）；**禁大面积 `any`**（spec §4.4 规则 1）。
3. **esbuild 间歇崩溃预案**（既有经验，design 2.9 风险 1）：build 偶发 esbuild 二进制损坏报错（服务进程级报错，与 TS 类型错误可明确区分）——先按既有路径恢复（`npm pack` 下载 esbuild 包 + 系统 bsdtar 解压重下覆盖 node_modules 内对应二进制）再重试；**判定纪律：崩溃特征非代码错误，避免误判为类型错误返工**。
4. **P9 文件零改动冻结清单**（F12 硬标准，git diff 必须为空）：
   | 冻结文件 | 实测锚点（任务完成判定引用） |
   |---|---|
   | `frontend/src/api/chat.ts`（168 行） | `streamChatQa` :49-152（解析循环内联 :119-152，**不可 import**——agent.ts 逐行同构复刻）；受理段 :66-90；dispatch :102-117；catch :146-148 |
   | `frontend/src/api/request.ts`（132 行） | `clearTokenAndRedirect` :55-61（401 单一实现，agent.ts 仅新增 import）；`TOKEN_KEY` :24；拦截器 :66-130 |
   | `frontend/src/views/AskView.vue`（300 行） | `scrollToBottom` :43-48；`reactive(placeholderAssistant())` :81（流式响应式关键）；finally 复位 :112-116；布局 CSS :235-299 |
   | `frontend/src/components/ask/*`（3 文件） | AskComposer / MessageBubble / SourceCard——agent 四子组件全部新建于 `components/agent/`，不向 ask 组件注入扩展 |
   | `frontend/src/types/index.ts` | `QaSseEvent` :508-520 既有类型零改动；agent 类型独立 `types/agent.ts` 并存（裁决 #2） |
   | `frontend/src/router/index.ts`（119 行） | `/ai-agent` 路由 :73-78（meta `AI 助手` / `needsAuth: true`）零改动（O7） |
   | `frontend/src/layouts/MainLayout.vue` | 菜单项 :36「AI 助手」+ `default-active` :69 零改动 |
   | `backend/` 全部 | 后端零改动（六端点 P11 已验收，前端只消费） |
   验证命令：`git diff --stat -- frontend/src/api/chat.ts frontend/src/api/request.ts frontend/src/views/AskView.vue frontend/src/components/ask/ frontend/src/types/index.ts frontend/src/router/index.ts frontend/src/layouts/MainLayout.vue backend/`（输出为空）。
5. **P9 现状实测锚点**（本清单完成判定的行号基准，全部经实际读取核实）：`AgentView.vue` 现为 14 行骨架占位（`PagePlaceholder` :6-13，本阶段整体替换）；`components/` 现有子目录 ask/dashboard/goal/knowledge/record/task——**无 agent 子目录（需新建）**；`api/` 无 agent.ts、`types/` 仅 index.ts（均需新建）；`stores/user.ts` token :29（`useUserStore().token` 供给）。
6. **Element Plus 组件选型**：遵循 design 视觉规格表（2.4.1-A）——图标 `Loading/CircleCheck/CircleClose/ArrowRight/ArrowDown/InfoFilled/VideoPause/Promotion`；**折叠卡自绘 div+CSS 而非 el-collapse**（决策 A9：36px 锁定在 el-collapse 结构内不可达）；`el-input type="textarea"` + `show-word-limit`；`el-empty` 空态（O2）；`el-dialog` 重命名 + `ElMessageBox.confirm` 删除确认；`el-alert type="error"` 错误行；切换加载用消息区容器**局部** `v-loading`（决策 A10，禁全屏指令）。中文文案全部走 ElMessage/ElMessageBox。
7. **R3 硬约束（本清单最高优先级约束，独立任务项 2.4 + 6.3 落实）**：「停止生成」的 **aborted 判定必须放在 catch 块的最前面（第一条语句），先于任何错误分类逻辑，不得被后续 catch 逻辑重排**。用户主动停止不是错误——若落到「网络中断，请重试」分支，用户点了停止却看到一条红色错误，体验直接崩掉。锁死顺序（design 决策 A4）：**视图层先置位 `stopped` → `abort()` → agent.ts catch 首语句 `signal?.aborted === true` 判定 → 静默 return（不合成网络中断、不触发 onError）**。三重验证锚点：① 代码审查 catch 首语句（2.4 完成判定）；② 静态 grep 走查（7.3）；③ 本机走查 V2「点停止后无红色错误行」（组 8）。

**常量表核对表**（AgentView.vue 模块级，全部锁定值 + 注释来源，design 2.1.2-B；组 6.1 逐字落地，组 9.2 走查复核；字面量联合类型在 types/agent.ts 定义）：

| 常量 | 值 | 依据（注释必写） |
|------|-----|------|
| `MESSAGE_MAX_LEN` | `2000` | spec §7.1 规则 1（与后端 O6 同值同义，前端独立常量做发送前拦截） |
| `CONVERSATION_PAGE_SIZE` | `50` | spec 冲突裁决 #3（首屏单页固定值，后端上限 100 内取 50） |
| `QUICK_QUESTIONS` | 4 项数组（「我最近学习怎么样」「我哪些知识点最薄弱」「我还有哪些任务没做完」「帮我制定下周学习计划」） | O3 用户指定清单 |
| `FINISH_HINTS` | `{ normal: '', max_rounds: '信息较多，已为你总结', timeout: '处理时间较长，以下是已获取的部分' }` | spec §7.4 规则 3（F4「映射齐全」审查项） |
| `THINKING_TEXT` | `'思考中'` | spec §7.4 规则 4（固定常量 + 「（第 N 轮）」后缀拼接） |
| `STOPPED_TEXT` | `'已停止生成'` | spec §5.3.1 规则 11（轻量标记非错误样式） |
| `GENERATING_BLOCK_HINT` | `'请先停止当前生成'` | O5 裁定（禁静默；AgentView 统一弹出，单一来源） |
| `ARG_VALUE_MAX_LEN` | `20` | spec §5.4.1 规则 1（参数值超 20 字符截断加省略号） |
| `LIST_TOTAL_HINT` | `` `仅显示最近 ${CONVERSATION_PAGE_SIZE} 条会话` `` | O4（total 超出首屏时底部提示，不做加载更多） |

ToolCallCard 组件级常量：`--toolcard-row-height: 36px`（CSS 变量）、耗时格式化阈值 `1000ms`（<1000 → `8ms`；≥1000 → `1.2s` 秒保留一位小数）。

**交付范围铁律**：仅 7 个文件（1 改 6 新增）——`views/AgentView.vue`（替换 14 行骨架）+ `components/agent/` 四子组件（ToolCallCard / MessageItem / ConversationList / AgentComposer）+ `api/agent.ts` + `types/agent.ts`；`PagePlaceholder.vue` 组件本身保留（其他页仍用，仅本页不再引用）。

---

## 1. types/agent.ts 类型单一来源

**写作说明**：新增 `frontend/src/types/agent.ts`（~170 行，design 2.3.2 全量）。纯类型文件（零运行时代码）；与 `types/index.ts` 并存零耦合（裁决 #2——agent 类型不被其他模块反向依赖，只有 agent 域 import）；字面量与后端共用同一套（snake_case 原样，禁二次映射）。是全部后续文件的编译依赖（design 2.7 步骤 1）。

### 1.1 传输层类型定义（六事件联合 + 会话/消息/分页）

- [ ] **要点**：
  - `AgentFinishReason = 'normal' | 'max_rounds' | 'timeout'`；`AgentSseEvent` 六事件可辨识联合——`thinking{round: number; content?: string}` / `tool_call{call_id, name, arguments: Record<string, unknown>}` / `tool_result{call_id, name, ok, elapsed_ms, summary, truncated}` / `delta(data: string)` / `done{conversation_id, message_id: number|null, rounds, tool_call_count, finish_reason}` / `error{code, message}`——逐字对齐 design 2.3.2-(A) 与 spec §7.2 七条载荷约束
  - `AgentConversation{id, title: string|null, created_at, updated_at}`、`ConversationPage{items, total, page, page_size}`、`AgentToolCall{id, type, function: {name, arguments: string}}`（OpenAI 原始格式，arguments 为 JSON 字符串）、`AgentMessageRole = 'user'|'assistant'|'tool'`、`AgentMessage{id, conversation_id, role, content, tool_name: string|null, tool_calls: AgentToolCall[]|null, tool_call_id: string|null, created_at}`、`AgentChatPayload{message, conversation_id?}`
  - 写法模板对齐 `types/index.ts:508-520` 的 `QaSseEvent`（字面量 `type` 判别 + data 载荷逐字段 snake_case）
- **涉及文件**：新增 `frontend/src/types/agent.ts`
- **完成判定**：`cd frontend && npx vue-tsc --noEmit src/types/agent.ts 2>&1 || npm run build`（组 1 里程碑统一跑 build）；字段与 spec §7.2/§7.3 逐项人工对照一致（§4.4 规则 1 验收）
- **依赖**：无
- **决策锚点**：裁决 #2（独立文件并存）；**验收锚点**：F12（类型集中）

### 1.2 视图层类型定义（ViewMessage + segments + ToolCallView 统一形态）

- [ ] **要点**：
  - `ViewMessage = UserViewMessage | AssistantViewMessage`——user 分支 `{kind: 'user', content}`；assistant 分支 `{kind: 'assistant', segments: AssistantSegment[], streaming: boolean, finish: FinishInfo|null, error: string|null, stopped: boolean}`（块级字段：流式光标 / done 定值 / 错误行 / 已停止标记——决策 A2「收尾是块级终结信息不属流内段」）
  - `AssistantSegment` 三种段联合：`{kind:'thinking', round: number|null, content, done}`（done=该轮弱化）/ `{kind:'tool', call: ToolCallView}` / `{kind:'text', content}`——**保序是「工作轨迹」语义的结构保证**（design 2.3.2-B 注释原文要点写入类型注释）
  - `FinishInfo{finish_reason, rounds, tool_call_count, conversation_id}`；`ToolCallView{call_id, name, arguments: Record<string, unknown>|string, result: ToolResultView|null}`（**result===null 即调用中态；arguments 联合类型第二分支 = 历史容错降级**）；`ToolResultView{ok, elapsed_ms: number|null, summary, truncated, raw_content: string|null}`——实时/历史差异全部收敛为两个可空字段（`elapsed_ms: null` → 历史省略耗时；`raw_content: null` → 实时展开显示 summary 全文），组件无模式分支（决策 A3）
- **涉及文件**：修改 `frontend/src/types/agent.ts`
- **完成判定**：`npm run build` 类型层通过；`grep -n "kind:" frontend/src/types/agent.ts` 命中 'user'/'assistant'/'thinking'/'tool'/'text' 五判别值
- **依赖**：1.1
- **决策锚点**：A2 / A3 / A8；**验收锚点**：F8（统一形态的结构前提）

### 1.3 类型契约核对与编译门

- [ ] **要点**：
  - 全文件零 `any`（禁大面积 any，spec §4.4 规则 1）；类型注释回链 design 章节号（2.3.2）；snake_case 全程保留（PROJECT_CONTEXT §8.3——JSON 传输字段不做自动大小写转换）
  - 确认 `types/index.ts` 零改动（grep 确认 agent.ts 不 import index.ts 也无反向依赖）
- **涉及文件**：核对（无代码改动）
- **完成判定**：`grep -c "any" frontend/src/types/agent.ts` 无裸 `any` 使用；`git diff --stat -- frontend/src/types/index.ts` 输出为空
- **依赖**：1.2
- **验收锚点**：F12

**里程碑验证（组 1 结束）**：
```bash
cd frontend && npm run build        # 退出码 0（此时新类型未被引用，验证类型层自身合法性）
git diff --stat -- frontend/src/types/index.ts   # 输出为空
```

---

## 2. api/agent.ts SSE 流客户端与会话管理五函数

**写作说明**：新增 `frontend/src/api/agent.ts`（~240 行，design 2.2.2 / 2.4.2）。模块 docstring 注明「解析骨架与 P9 chat.ts 逐行同构（差异仅端点/事件数/signal，见 DESIGN 2.4.2 对照表）」。**chat.ts 解析循环内联于 `streamChatQa` 函数体（chat.ts:119-152），模块仅导出三个名字，无可 import 的独立解析函数——同构复刻是唯一合规路径**（design 实测发现 ①，十六项对照表为 F7 证据）。

### 2.1 模块骨架 + 会话管理五函数（request.ts 通道）

- [ ] **要点**：
  - 导入形态对齐 chat.ts:15-20（`ElMessage` / `request` default + `clearTokenAndRedirect` / `useUserStore` / `types/agent` 类型）；模块级常量 `CODE_TOKEN_INVALID = 1003`（与 request.ts:31 同口径，chat.ts:31 同款）
  - 五函数全部 `request.get/post/patch/delete` + `as Promise<T>` 断言形态（P9 chat.ts:161-168 同款）：`getAgentConversations(page, pageSize) → Promise<ConversationPage>`、`createAgentConversation(title?) → Promise<AgentConversation>`、`renameAgentConversation(conversationId, title) → Promise<AgentConversation>`、`deleteAgentConversation(conversationId) → Promise<null>`、`getAgentConversationMessages(conversationId) → Promise<AgentMessage[]>`（签名逐字对齐 design 2.2.2-(2) 表格）
  - **禁止复制第二份 401 跳转逻辑**——错误提示/401 处理/`code===0` 解包全部由 request.ts 拦截器（:66-130）统一完成，本文件对 422/1001、404/1005 零手写错误分支
- **涉及文件**：新增 `frontend/src/api/agent.ts`
- **完成判定**：`cd frontend && npm run build` 通过；`grep -n "clearTokenAndRedirect\|window.location" frontend/src/api/agent.ts` —— `window.location` 零命中（401 跳转仅经 clearTokenAndRedirect 单一实现，spec §4.3 规则 2）
- **依赖**：组 1
- **决策锚点**：design 1.2.3（双通道同源）；**验收锚点**：F9（非流式通道走拦截器）

### 2.2 streamAgentChat 受理段（fetch + signal 透传 + 受理错误三态）

- [ ] **要点**：
  - 签名逐字对齐 design 2.2.2-(1)：`streamAgentChat(payload: AgentChatPayload, handlers: AgentStreamHandlers, signal?: AbortSignal): Promise<void>`；`AgentStreamHandlers` 六回调接口（onThinking 入参 `{round?: number; content?: string}` 放宽——design 2.9 风险 3 前向兼容）
  - token 读取 `useUserStore().token` + `base = import.meta.env.VITE_API_BASE_URL || '/api/v1'`（chat.ts:53-54 同款）；fetch `POST ${base}/agent/chat` + `Content-Type: application/json` + 条件注入 `Authorization: Bearer`（token 空串不注入，chat.ts:56-65 同款）+ **`signal` 透传 fetch init**（裁决 #1 新增能力，十六项对照表 #3 差异键）
  - 受理三态逐行复刻 chat.ts:66-90：建连 catch → `ElMessage.error('网络异常，请稍后重试')` + onError return；`!resp.ok` → try 解析 `{code, message}`（非 JSON 保留默认文案）→ `resp.status === 401 || code === 1003` → `clearTokenAndRedirect()` → `ElMessage.error(message)` → onError 终止（422/1001、404/1005 由通用 ElMessage(message) 分支覆盖——后端中文文案直出）
  - reader 空兜底 `onError「当前浏览器不支持流式响应」` return（chat.ts:92-96 同款，spec §5.1.3 场景 1）
  - **token 红线**：拼头不拼 URL、禁 console 打印（spec §4.3 规则 1）
- **涉及文件**：修改 `frontend/src/api/agent.ts`
- **完成判定**：`npm run build` 通过；`grep -n "agent/chat\|signal" frontend/src/api/agent.ts` 命中端点与 signal 透传；`grep -cn "console.log" frontend/src/api/agent.ts` 输出 0
- **依赖**：2.1
- **决策锚点**：裁决 #1；**验收锚点**：F9 / F10（受理层）

### 2.3 行缓冲解析主循环 + dispatch 六事件分发（十六项同构复刻）

- [ ] **要点**：
  - 对照表左列基准逐项复刻（design 2.4.2-A #7-#13，chat.ts 实测行号）：`new TextDecoder('utf-8')` + `buffer = ''`（#7，chat.ts:98-100）→ dispatch switch **六事件**、done/error 返回 `'end'`、**新增 default → 静默 `'continue'`**（#8——未知 type 前向兼容，spec §5.3.1 规则 4；chat.ts:102-117 为四事件无 default）→ 读取主循环 `for(;;){ read → done break → buffer += decoder.decode(value, {stream: true}) }`（#9，:120-123）→ 内层 `indexOf('\n\n')` 边界切块（#10，:125-130）→ 行过滤 `block.trim()` / 空行 / `':'` 注释行 / 非 `'data: '` 前缀 continue（#11，:130-133）→ 脏块 `JSON.parse(line.slice(6))` try-catch continue（#12，:134-140）→ `dispatch(event) === 'end'` return 终结短路（#13，:141）
  - 流耗尽合成错误 `onError「网络中断，请重试」`（#14 差异：**前置 aborted 判定**，aborted → return 不合成——归 2.4 核验）→ finally `reader.releaseLock()`（#16，:149-151）
  - `JSON.parse` 后的 event 需经类型收窄安全分发（脏 `type` 运行时落入 default——TS 层 dispatch 穷尽性由可辨识联合结构性保证）
- **涉及文件**：修改 `frontend/src/api/agent.ts`
- **完成判定**：`npm run build` 通过；**代码审查**——十六项对照表逐项人工比对（12 项逐行相同 + 4 项契约性差异：端点/事件数/signal/aborted 判定），hunk 级记录比对结果（F7 交付证据）
- **依赖**：2.2
- **决策锚点**：design 2.4.2-A（F7 证据表）；**验收锚点**：**F7（SSE 解析复用——本任务即其代码审查主体）** / F10

### 2.4 【R3 硬约束·独立任务项】catch 首语句 aborted 判定（停止静默链路）

- [ ] **要点**：
  - **catch 块的第一条语句必须是 `if (signal?.aborted === true) return`（或等价的 aborted 判定短路），先于任何错误分类逻辑**——用户主动停止不是错误：abort 触发 pending `reader.read()` reject（AbortError）进入 catch，此处静默 return，**不合成「网络中断，请重试」、不触发 onError、不渲染红色错误行**（R3 硬约束原文要义 + 决策 A4）
  - 锁死顺序不得被后续 catch 逻辑重排：aborted 判定 → 静默 return；非 aborted → `handlers.onError({code: 0, message: '网络中断，请重试'})`（chat.ts:146-148 复刻）——**两个分支的先后顺序为实现后不得调整项**
  - 建连 catch（chat.ts:66-71 同构位）：abort 恰在建连窗口触发且 `signal?.aborted === true` → 静默 return（对照表 #4 差异注释）
  - 流耗尽路径（read done 且无终结事件）前置同款 aborted 判定（对照表 #14 差异——停止后流以 done 收尾时避免误报网络中断）
  - 防御性预案注释位（design 2.4.4-B / 2.9 风险 4）：个别浏览器 read 未 reject 的行为差异时，catch 分支内 `reader.cancel().catch(() => {})`（幂等，主流 Chrome/Edge 按 fetch 规范 reject——预案为兜底非主路径）
- **涉及文件**：修改 `frontend/src/api/agent.ts`（streamAgentChat catch 区）
- **完成判定**（三重验证锚点之一——代码审查项）：
  - **人工代码审查：catch 块首语句即 `signal?.aborted` 判定**（对照 agent.ts 实际实现的 catch 块逐行核验，记录审查结论）
  - `grep -n -A 2 "} catch" frontend/src/api/agent.ts` —— 输出中每个 catch 后第一行均为 aborted 判定或建连 catch 的 ElMessage 位（人工核对）
  - `grep -c "signal?.aborted" frontend/src/api/agent.ts` ≥ 2（read 抛错 catch + 流耗尽路径）
- **依赖**：2.3
- **决策锚点**：**A4（R3 锁死顺序：先置位 stopped → abort() → catch 前置 aborted 判定 → 静默 return）**；**验收锚点**：F6（停止生成）/ F10（网络中断与停止分流——spec §5.3.1 规则 11 vs 13 差异化实现）
- **本机走查对应**：V2「点停止后无红色错误行」（组 8）

**里程碑验证（组 2 结束）**：
```bash
cd frontend && npm run build                                    # 退出码 0
grep -n "signal?.aborted" frontend/src/api/agent.ts             # ≥2 命中（catch 首句 + 流耗尽前置）
grep -n "网络中断" frontend/src/api/agent.ts                    # 命中处均位于 aborted 判定之后（人工核验顺序）
git diff --stat -- frontend/src/api/chat.ts                     # 输出为空（P9 冻结）
```

---

## 3. components/agent/ToolCallCard.vue 四态卡片

**写作说明**：新增 `frontend/src/components/agent/ToolCallCard.vue`（~300 行，design 2.4.1）。**实时流与历史回放共用同一组件**（O1 结构性理由——F8 样式一致性的编译期保证）；**用户设计重点 ①（工具卡片高度控制）的核心载体**。props-emits 惯例对齐 ask 组件（类型化 defineProps/defineEmits，零 api 调用）。

### 3.1 四态渲染骨架（纯数据驱动，无模式 prop）

- [ ] **要点**：
  - props `{ call: ToolCallView }`；emits `{(e: 'toggle', callId: string, expanded: boolean): void}`（design 2.2.2-(3) 契约逐字）
  - 态判定纯数据驱动（design 2.4.1-C）：`call.result === null` → 调用中（`Loading` 图标 is-loading 旋转 16px + 「正在调用 `name(args)` …」文案）；`call.result.ok === false` → 失败（`CircleClose` 16px error 色 + 警示边框 `--el-color-error-light-5` + 极浅警示底 `--el-color-error-light-9` + 摘要位显示错误说明 error 色）；`expanded === true`（内部 `ref(false)` 初始折叠）→ 展开态外壳（头部行同折叠 + 详情区）；否则完成折叠（`CircleCheck` 16px success 色）——**失败态是完成态的警示变体，同样可展开**
  - 折叠行各列：图标区 22px / 工具名等宽 12px font-weight 600（`'JetBrains Mono', Consolas, monospace` 回退）max-width 40% ellipsis / 紧凑参数 12px secondary 色 max-width 30% ellipsis / 耗时 flex-shrink:0 / 摘要弹性区 / 箭头 `ArrowRight`↔`ArrowDown` 14px
  - 调用中态整卡不可点、无 hover；完成/失败/展开头部行 click 切换、hover 边框 `--el-color-primary-light-7` + `cursor: pointer`
- **涉及文件**：新增 `frontend/src/components/agent/ToolCallCard.vue`
- **完成判定**：`npm run build` 通过；`grep -n "el-collapse" frontend/src/components/agent/ToolCallCard.vue` 零命中（决策 A9 自绘）；`grep -cn "import request\|@/api" frontend/src/components/agent/ToolCallCard.vue` 输出 0（子组件零 api 调用，spec §4.4 规则 4）
- **依赖**：组 1（ToolCallView 类型）
- **决策锚点**：A3 / A7 / A9；**验收锚点**：F1（卡片可见）/ F2（折叠交互）

### 3.2 36px 单行高度锁定 CSS（用户设计重点 ①）

- [ ] **要点**：
  - `.tool-card` CSS 变量 `--toolcard-row-height: 36px` + `border-radius: 6px` + `overflow: hidden`（展开动画防溢出）；`.tool-row` 折叠行骨架（调用中/完成/失败共用）：`display: flex; align-items: center; gap: 4px; height: var(--toolcard-row-height); padding: 0 12px 0 8px; box-sizing: border-box`（design 2.4.1-B 逐字落地）
  - **高度恒定的结构保证**：所有列 `white-space: nowrap` + 各自 ellipsis/max-width——无论参数多少键、摘要多长，折叠行**永不换行**（调用中与完成同 36px 单行，状态迁移零高度跳变——决策 A7）
  - **4 连卡片总高验证写入注释**：卡片堆叠 gap = 6px（MessageItem segments 容器）；4 张折叠卡 = `4×36 + 3×6 = 162px` ≤ 对话区 1/3（500px 保守估算 1/3 ≈ 167px ✓）——注释含此计算（design 2.4.1-B 验证段）
  - 展开态：头部行 36px + 详情区 auto（border-top 分隔 + padding 10px 12px + gap 8px + 背景 `--el-fill-color-light`）；`max-height` 过渡动画 `.2s ease`（或 `<Transition>`，轻量自绘）；**详情区 `v-if="expanded"` 惰性渲染**（design 2.9 风险 2——回放性能）
- **涉及文件**：修改 `frontend/src/components/agent/ToolCallCard.vue`（scoped CSS）
- **完成判定**：**CSS 审查**（用户重点 ① 核对项）：`grep -n "toolcard-row-height\|white-space: nowrap\|text-overflow: ellipsis" frontend/src/components/agent/ToolCallCard.vue` —— 36px 锁定值 + nowrap/ellipsis 体系命中；人工核验 `.tool-row` height 为 `var(--toolcard-row-height)` 且无其他 height 声明覆盖
- **依赖**：3.1
- **决策锚点**：**A1（摘要同行 ellipsis 截断）/ A7（调用中同高）/ A9（自绘）**；**验收锚点**：F1 + 用户重点 ①（4 连卡片不淹没对话——走查观测点归 V1）

### 3.3 三个格式化纯函数 + toggle 上报 + 历史容错渲染

- [ ] **要点**：
  - `formatArgsCompact(arguments)`：对象 → `key=value` 逗号连接、值超 20 字符截断加 `…`（常量 `ARG_VALUE_MAX_LEN` 由 props 外部约定 20——组件内定义同值常量并注释）；**字符串形态（历史容错降级）→ 原文截断 20 字符**；空对象 → 空串（渲染 `name()` 括号留空，spec §5.4.1 规则 8——**arguments 渲染不得抛错**）
  - `formatElapsed(elapsed_ms)`：`<1000 → '{n}ms'`；`≥1000 → '{s 一位小数}s'`（如 `1.2s`）；null → 不渲染该 span（历史卡折叠行省略耗时项，`v-if="call.result?.elapsed_ms != null"`——F8「无耗时项但样式一致」）；失败调用 elapsed_ms 照显
  - `formatDetailJson(raw_content)`：try `JSON.parse` → `JSON.stringify(obj, null, 2)` 缩进美化（`<pre>` 等宽 12px max-height 240px overflow-y:auto）；catch → 原文返回降级（spec §5.6 规则 4）
  - 展开态内容切换：实时卡显示 summary 全文（pre-wrap 不截断；`truncated=true` 尾部「…（已截断）」标记 12px placeholder 色）；历史卡显示格式化 JSON——**数据驱动切换（raw_content 是否 null），无模式分支**（决策 A3）
  - emits `toggle` 上报展开/收起（视图层滚动高度补偿观测点，F2 走查点）
- **涉及文件**：修改 `frontend/src/components/agent/ToolCallCard.vue`
- **完成判定**：`npm run build` 通过；`grep -n "formatArgsCompact\|formatElapsed\|formatDetailJson" frontend/src/components/agent/ToolCallCard.vue` 三函数齐备；人工核验：`name()` 空参形态 / 字符串 arguments 降级 / 历史无耗时三项容错路径在模板中均有对应分支
- **依赖**：3.2
- **决策锚点**：A3；**验收锚点**：F1 / F2 / F8（容错与统一渲染）

**里程碑验证（组 3 结束）**：
```bash
cd frontend && npm run build
grep -n "toolcard-row-height: 36px" frontend/src/components/agent/ToolCallCard.vue   # 锁定值命中
grep -c "el-collapse" frontend/src/components/agent/ToolCallCard.vue                  # 0
```

---

## 4. MessageItem.vue 消息渲染单元 + AgentComposer.vue 输入区

**写作说明**：新增两个组件（~220 + ~150 行，design 2.2.2-(4)/(6)）。MessageItem 是 segments 保序渲染的宿主（决策 A2 的渲染面）；AgentComposer 对齐 P9 AskComposer 校验链惯例（trim 判空 → ElMessage.warning 不发请求；maxlength 输入层硬限）。

### 4.1 MessageItem：user 气泡 / assistant 块 segments 保序渲染

- [ ] **要点**：
  - props `{ message: ViewMessage }`；emits `{(e: 'card-toggle', callId: string, expanded: boolean): void}`（ToolCallCard toggle 原样透传——design 2.2.2-(4) 契约补记）
  - user 分支：主色右对齐气泡（视觉规格复刻 MessageBubble.vue:54-60/113-175 的 bubbleClass 模式——**视觉复刻到新文件，旧文件不动**）；assistant 分支：`v-for segment in message.segments` 按 kind 三分支渲染——thinking 行（`THINKING_TEXT` + 「（第 N 轮）」后缀 + 行内小 spinner（O6）；`done: true` 弱化样式；`content` 浅色小字附加）/ tool 段（`<ToolCallCard :call="segment.call" @toggle="..." />`）/ text 段（`white-space: pre-wrap`；`message.streaming && 为最后一个 text 段` 时尾部闪烁光标）
  - **块末固定区（非 segment，design 2.4.4-E 渲染顺序：segments → 收尾提示 → 统计 → 错误行/已停止）**：① `finish && finish_reason !== 'normal'` → 轻量信息条（自绘 div：`InfoFilled` 14px + 文案 12px secondary + 无底色块）；② 统计小字**恒显**（normal 也显示）：`{rounds} 轮 · {tool_call_count} 次工具调用`（12px `--el-color-text-placeholder` 灰阶、**无 badge 无底色**——O8「统计恒显、提示分态」）；③ `error` → `el-alert type="error" closable=false` 内联错误行；④ `stopped` → `STOPPED_TEXT` 12px secondary + `VideoPause` 12px（轻量非错误样式）
  - **禁 overlay**：生成期间无任何遮罩（spec §5.5.1 规则 3）——组件内零 `v-loading` 全屏指令
- **涉及文件**：新增 `frontend/src/components/agent/MessageItem.vue`
- **完成判定**：`npm run build` 通过；`grep -n "轮 ·\|次工具调用" frontend/src/components/agent/MessageItem.vue` 统计小字模板命中（O8）；`grep -c "v-loading" frontend/src/components/agent/MessageItem.vue` 输出 0（F3 代码审查项「无 overlay」）
- **依赖**：组 1 + 组 3（ToolCallCard）
- **决策锚点**：A2 / A11；**验收锚点**：F3（thinking 轻量）/ F4（三态+弱化统计渲染面）

### 4.2 MessageItem：thinking 弱化态与 segments 时序保证

- [ ] **要点**：
  - thinking 段 `done: true` → 弱化样式（小字号浅灰已完成态，**不删除**——保留轨迹可读性，决策 A11）；round 为 null 的防御段（`round: null` 显示无轮次后缀形态）
  - segments 保序渲染是「工作轨迹」语义的渲染保证（模板 v-for 天然保序——组件不排序、不重排、不合并段）
  - card-toggle 透传契约：`@toggle="(id, ex) => emit('card-toggle', id, ex)"`
- **涉及文件**：修改 `frontend/src/components/agent/MessageItem.vue`
- **完成判定**：`npm run build` 通过；人工核验：thinking 弱化仅 class 切换（无 v-if 删除已过轮提示行）
- **依赖**：4.1
- **决策锚点**：A11；**验收锚点**：F3（已出现内容不被遮挡、清空或位移）

### 4.3 AgentComposer：输入校验 + 发送⇄停止原位切换（O5）

- [ ] **要点**：
  - props `{ streaming: boolean }`；emits `{(e: 'send', message: string): void; (e: 'stop'): void}`（design 2.2.2-(6) 契约逐字）
  - `el-input type="textarea"` + `:maxlength="2000"`（MESSAGE_MAX_LEN 常量注入或组件内同值常量+注释）+ `show-word-limit`（计数「N / 2000」内建）+ `:autosize="{ minRows: 2, maxRows: 5 }"`；Enter 发送 / Shift+Enter 换行（`@keydown.enter.exact.prevent="submit"`——prevent 阻止默认换行，shift 组合自然换行）
  - 校验链（AskComposer.vue:36-45 惯例对齐）：trim 判空 → `ElMessage.warning('请输入消息')` 不发请求；达上限 maxlength 硬限结构性消除 + 发送禁用
  - **按钮原位切换（O5 常驻）**：空闲 = `type="primary"` icon `Promotion`「发送」；生成中 = `type="danger"` icon `VideoPause`「停止生成」——**同一按钮原位切换，位置固定于 composer 区不随内容滚动移动**；生成中 textarea **保持可输入**（预输入下一问，spec §5.3.1 规则 12），仅发送动作被停止替代；发送后清空输入框
- **涉及文件**：新增 `frontend/src/components/agent/AgentComposer.vue`
- **完成判定**：`npm run build` 通过；`grep -n "stop\|停止生成" frontend/src/components/agent/AgentComposer.vue` 停止 emit 与按钮文案命中；`grep -cn "import request\|@/api" frontend/src/components/agent/AgentComposer.vue` 输出 0
- **依赖**：组 1
- **决策锚点**：O5（停止常驻结构性满足）；**验收锚点**：F6（停止按钮）/ F11（输入约束）

**里程碑验证（组 4 结束）**：
```bash
cd frontend && npm run build
grep -c "v-loading" frontend/src/components/agent/MessageItem.vue    # 0（禁 overlay）
```

---

## 5. ConversationList.vue 会话列表（左栏交互域）

**写作说明**：新增 `frontend/src/components/agent/ConversationList.vue`（~240 行，design 2.2.2-(5)）。全新交互域（P9 无会话概念）；**不含 api 调用**（重命名/删除仅 emit 参数，由 AgentView 落请求——spec §4.4 规则 4）。

### 5.1 列表渲染 + 当前高亮 + 空标题占位 + total 提示

- [ ] **要点**：
  - props `{ conversations: AgentConversation[]; currentId: number | null; loading: boolean; generating: boolean }`；emits `{create / select(conversationId) / rename(conversationId, title) / remove(conversationId)}`（design 2.2.2-(5) 契约逐字）
  - 服务端 updated_at 倒序原样渲染（前端不排序）；当前会话行高亮样式（选中态背景/边框）；`title` 空或 null → 行显示「新会话」占位；loading 骨架/spinner 态（spec §4.1 规则 4——不白屏）
  - `generating: true` 时列表项与新建入口视觉置灰（**轻提示由 AgentView 统一弹出——文案常量单一来源 `GENERATING_BLOCK_HINT`，避免双提示**，design 2.2.2-(5) 归属裁定）
  - total 超出 `CONVERSATION_PAGE_SIZE` 时底部「仅显示最近 50 条会话」12px 灰字（O4——不做加载更多）
- **涉及文件**：新增 `frontend/src/components/agent/ConversationList.vue`
- **完成判定**：`npm run build` 通过；`grep -n "新会话\|仅显示最近" frontend/src/components/agent/ConversationList.vue` 两文案命中；`grep -cn "import request\|@/api" frontend/src/components/agent/ConversationList.vue` 输出 0
- **依赖**：组 1
- **决策锚点**：O4 / O5（视觉禁用归属）；**验收锚点**：F5

### 5.2 重命名弹窗（1..200 校验）+ 删除确认（交互内聚）

- [ ] **要点**：
  - 重命名：`el-dialog` + `el-input` maxlength 200 + show-word-limit + 预填当前标题；**空标题或超 200 字提交按钮禁用**（前端提交前拦截——spec §5.2.3 场景 2；后端 422 由拦截器兜底）；确认后 `emit('rename', id, title)`
  - 删除：`ElMessageBox.confirm` 确认框，文案含「删除后不可恢复，将同时删除会话内全部消息」（spec §5.2.1 规则 6 原文）；确认后 `emit('remove', id)`；取消 → 无请求无变更
  - 点击行 → `emit('select', id)`（切换加载由 AgentView 处理）
- **涉及文件**：修改 `frontend/src/components/agent/ConversationList.vue`
- **完成判定**：`npm run build` 通过；人工核验：弹窗/确认内置于组件（操作结果以事件上报，API 调用在 AgentView——职责单一验收）
- **依赖**：5.1
- **决策锚点**：design 2.2.2-(5) 交互内聚；**验收锚点**：F5（全操作矩阵）

**里程碑验证（组 5 结束）**：
```bash
cd frontend && npm run build
grep -cn "import request\|@/api" frontend/src/components/agent/ConversationList.vue   # 0（零 api 调用）
```

---

## 6. AgentView.vue 页面编排（替换骨架）

**写作说明**：`frontend/src/views/AgentView.vue` 14 行骨架（`PagePlaceholder` :6-13）整体替换为完整实现（~430 行，design 2.1.3 / 2.4.3 / 2.4.4）。视图状态编排唯一宿主：常量表（§0 已列）+ 双栏布局 + SSE 回调分发到响应式树 + 停止链路 + 竞态防护 + 历史还原调度 + 快捷问题。**路由与 MainLayout 零改动**（O7——`router/index.ts:73-78` 已注册）。

### 6.1 常量表 + 响应式状态域 + 双栏页面骨架

- [ ] **要点**：
  - 模块级常量九项逐字落地（§0 常量表：MESSAGE_MAX_LEN / CONVERSATION_PAGE_SIZE / QUICK_QUESTIONS / FINISH_HINTS / THINKING_TEXT / STOPPED_TEXT / GENERATING_BLOCK_HINT / ARG_VALUE_MAX_LEN / LIST_TOTAL_HINT——全部注释来源「spec 章节号/O 裁定」）
  - 状态域（design 2.4.4-A）：`messages = ref<ViewMessage[]>([])`、`streaming = ref(false)`、`abortController: AbortController | null`（非 ref——无需模板响应）、`conversations = ref<AgentConversation[]>([])`、`currentConversation = ref<AgentConversation | null>`、`loadSeq = 0`、`messagesLoading = ref(false)`、`autoFollow = ref(true)`、`scroller = ref<HTMLElement | null>`
  - 页面骨架（design 2.4.4-D）：`agent-page`（flex row · height:100% · overflow:hidden——复刻 P9「页面不滚动」约束，AskView.vue:235-299 三件套模式）→ 左栏 `conversation-panel`（flex 0 0 264px · 内部滚动：panel-head「AI 助手」+ 新建按钮（Plus 图标）/ ConversationList / panel-foot total 提示）→ 右栏 `chat-panel`（flex 1 · min-width 0）：chat-head（当前会话标题，空显示「新会话」）/ `chat-scroll`（flex 1 · overflow-y auto · ref=scroller，**唯一滚动容器**）/ composer-area（AgentComposer，停止按钮位置固定）
  - onMounted：`refreshConversations()` → 拉列表 → 自动选中第一项回放（spec §5.6.1 规则 8——刷新恢复最近活跃会话；无会话时空态）
- **涉及文件**：替换 `frontend/src/views/AgentView.vue` 全部内容
- **完成判定**：`npm run build` 通过；`grep -n "QUICK_QUESTIONS\|FINISH_HINTS\|CONVERSATION_PAGE_SIZE" frontend/src/views/AgentView.vue` 常量命中；`grep -n "PagePlaceholder" frontend/src/views/AgentView.vue` 零命中（骨架引用移除）
- **依赖**：组 1–5 全部
- **决策锚点**：design 2.1.2-B 常量表；**验收锚点**：F4（文案常量集中）/ F12（路由零改动——本文件是唯一改动的既有文件）

### 6.2 发送链路与六事件回调分发（reactive 占位 + segments 写入规则）

- [ ] **要点**：
  - `onSend(message)`：去首尾空白非空 + ≤2000 校验（禁发口径，agent.ts 不重复校验——视图层是唯一校验点）；push user 气泡（普通对象）+ **`reactive(placeholderAssistant())` 占位块**（P9 AskView.vue:78-82 模式实测确认——回调闭包改局部变量需响应式代理才能逐片触发重渲染，**必须 reactive 包裹**）；`new AbortController()` 持句柄；`streaming.value = true`
  - 请求体 `{message, ...(currentConversation.value ? {conversation_id: currentConversation.value.id} : {})}`（空态直发不带 id，裁决 #4 两路径并存）
  - 六回调写入规则（design 2.4.4-A 表逐行）：`onThinking` → `d.round != null` push 新段 `{kind:'thinking', round, content: d.content ?? '', done: false}` + **之前最后一个 thinking 段置 done: true**（弱化，A11）；仅 content → 追加到最后 thinking 段（防御路径）；`onToolCall` → push `{kind:'tool', call: {call_id, name, arguments, result: null}}`（segments 保序即堆叠序——**事件偏序为分组式（每轮 thinking → delta* → tool_call×N → tool_result×N），保序 append 天然成立**，决策 A2）；`onToolResult` → segments 内按 call_id 查找 tool 段写入 `call.result = {ok, elapsed_ms, summary, truncated, raw_content: null}`，**未命中 → push 独立完成态卡片段**（降级路径，spec §5.3.1 规则 8）；`onDelta` → 最后一个段为 text → `content += t`，否则 push 新 text 段（**中间轮解释与最终回答分属不同 text 段**——A8 合并策略）；`onDone` → `assistant.finish = {...}` + 空态直发时用 `d.conversation_id` 触发列表刷新后绑定（刷新回调内取 items 首个 id 匹配）；`onError` → `assistant.error = d.message`（内容保留红线——只增错误行 segments 不动）
  - 每个内容更新回调内 `if (autoFollow.value) void scrollToBottom()`
- **涉及文件**：修改 `frontend/src/views/AgentView.vue`
- **完成判定**：`npm run build` 通过；`grep -n "reactive(" frontend/src/views/AgentView.vue` 占位块 reactive 包裹命中；人工核验：六回调齐备且 call_id 配对写入路径正确
- **依赖**：6.1 + 组 2（streamAgentChat）
- **决策锚点**：A2 / A8 / A11；**验收锚点**：F1（卡片按序堆叠）/ F3 / F6（流式渲染）

### 6.3 【R3 硬约束·独立任务项】停止链路顺序锁死 + 单一 finally 复位块

- [ ] **要点**：
  - `onStop()` 顺序**锁死不得重排**（决策 A4）：① **先置位** `assistant.stopped = true`（保留内容红线——置位先行保证标记与内容落定，即使 abort 触发的 reject 竞先也只走静默分支）→ ② `abortController?.abort()` → ③ agent.ts catch 首语句 aborted 判定（2.4 已落实）→ ④ 静默 resolve → finally 复位
  - **单一 finally 复位块**（P9 AskView.vue:112-116 模式）：`assistant.streaming = false; streaming.value = false; abortController = null; void refreshConversations()`——**五条终结路径（done / error / 停止 / 网络中断 / 受理失败）全部经 Promise 终结触发，结构性消灭「永久转圈」**（spec §4.2 规则 1 终态必达）
  - 列表刷新时机：一次对话请求终结后刷新（spec §5.2.1 规则 10——新会话首次对话 done 后列表出现该会话且排序正确，无需手动刷新）
  - 停止后立即再发：finally 先复位 streaming 再允许新发送（Promise 时序保证）；前次已停止块保持不动，新请求携带同一会话 id 续聊（spec §5.3.3 场景 3）
- **涉及文件**：修改 `frontend/src/views/AgentView.vue`
- **完成判定**：`npm run build` 通过；**代码审查**：`grep -n -B 2 -A 2 "abort()" frontend/src/views/AgentView.vue` —— abort() 调用前置行即 `assistant.stopped = true` 置位（顺序锁死核验）；`grep -n "finally" frontend/src/views/AgentView.vue` 单一复位块命中
- **依赖**：6.2 + 2.4（agent.ts 静默分支）
- **决策锚点**：**A4（R3 锁死顺序——本任务与 2.4 构成停止链路两端）**；**验收锚点**：F6 / F10（五路径复位）；**本机走查**：V2（点停止 → 无红色错误行 + 内容保留 + 按钮复位）
- **三重验证锚点归集**：① 代码审查 catch 首语句（2.4）＋置位先于 abort（本任务）；② 静态 grep（7.3）；③ 本机 V2（组 8）

### 6.4 竞态防护（O5 短路 + loadSeq）+ 滚动跟随（autoFollow 滞回）

- [ ] **要点**：
  - **O5 结构性禁止**：`streaming === true` 时 `selectConversation()` / `onCreate()` 入口短路 → `ElMessage.info(GENERATING_BLOCK_HINT)`（「请先停止当前生成」，**禁止静默无响应**）→ return 不发生切换——竞态源头消除
  - **loadSeq 序号守卫**（决策 A6）：`selectConversation()` 内 `const seq = ++loadSeq`；`getAgentConversationMessages` 回调渲染前校验 `seq === loadSeq` 不等则丢弃——空闲时快速连点两会话的旧响应晚到不污染当前视图；列表刷新无守卫（全局数据后到即最新）
  - `scrollToBottom()` 复刻 P9（AskView.vue:43-48：`await nextTick()` → `scroller.scrollTop = scroller.scrollHeight`）；**autoFollow 滞回守卫**（决策 A5）：scroll 监听 `scrollHeight - scrollTop - clientHeight > 80` → `autoFollow = false`（用户上滚查看历史——F3）；回底 `< 40` → 恢复 true（滞回带防抖动）
  - 切换加载：`messagesLoading = true` → 拉取 → buildViewMessages → 一次性替换 `messages.value`（全量重建非增量）→ false；消息区容器**局部** `v-loading`（决策 A10——生成期间禁任何 overlay，切换加载是合规交集）；404/1005（并发删除）由拦截器弹错 + 从列表移除该行
- **涉及文件**：修改 `frontend/src/views/AgentView.vue`
- **完成判定**：`npm run build` 通过；`grep -n "loadSeq" frontend/src/views/AgentView.vue` 守卫命中；`grep -n "autoFollow\|scrollTop" frontend/src/views/AgentView.vue` 滚动跟随命中；人工核验：v-loading 仅挂消息区容器（非全屏指令）
- **依赖**：6.2
- **决策锚点**：A5 / A6 / A10 / O5；**验收锚点**：F3（可上滚）/ F5（生成中轻提示）/ F10

### 6.5 buildViewMessages 历史回放算法（用户设计重点 ②）

- [ ] **要点**：
  - 纯函数置于 AgentView.vue 内（视图域私有算法不进 api 层）：`buildViewMessages(msgs: AgentMessage[]) → ViewMessage[]`——design 2.4.3-A 伪代码逐行落地：
    - `cardIndex: Map<string, ToolCallView>`（call_id → 卡片引用）；id 升序逐条映射：`user` → 气泡；`assistant 且 tool_calls 非空` → 新块（content 非空先 push text 段）→ 逐 tool_call 容错解析 arguments → 建卡 `result: null` → `cardIndex.set(tc.id, card)`（**两阶段配对骨架：注册→回填单次遍历时序天然成立**）；`assistant 纯文本` → 单 text 段完成块；`tool` → `cardIndex.get(tool_call_id)` **未命中 continue（孤儿跳过不渲染不崩溃）** → 命中则 `JSON.parse(content)` 容错 → ok 判定 `!(parsed 为非空对象且 'error' in parsed)`（**决策 A12：对齐后端 `"error" not in result` 语义**）→ `card.result = {ok, elapsed_ms: null, summary: errorText, truncated: false, raw_content: msg.content}`（**历史无耗时 → null；raw_content → 展开态格式化 JSON**）
  - **arguments 容错解析三分支**（design 2.4.3-B）：`JSON.parse` 成功且对象 → 标准形态；成功但数组/标量 → 原样返回（渲染层字符串分支兜底）；失败 → **原始字符串降级（整条历史不崩）**；空串 → `{}`（`name()` 括号留空）
  - 回放块一律完成态：`streaming: false / finish: null / error: null / stopped: false`（spec §5.6.1 规则 7——无光标无思考行；**停止后回放差异：`stopped` 标记仅存于实时流内存视图，回放不补「已停止」标记**——design 2.4.3-D 对齐后端半截不落库语义）
- **涉及文件**：修改 `frontend/src/views/AgentView.vue`
- **完成判定**：`npm run build` 通过；`grep -n "buildViewMessages\|cardIndex" frontend/src/views/AgentView.vue` 算法与索引命中；人工核验：孤儿 continue / arguments 降级 / ok 含 error 键判定三路径齐备
- **依赖**：6.1
- **决策锚点**：**A3 / A12 + 用户重点 ②（保真度四项：call_id 精确配对 / arguments 容错 / 历史卡与实时卡同组件 / 孤儿跳过）**；**验收锚点**：**F8（历史回放——本任务即其算法主体）**；**本机走查**：V4
- **配套 CSS 审查**（用户重点 ② 核对项）：历史卡与实时卡同组件渲染的结构保证在组 3（ToolCallCard 无模式分支）——本任务完成判定含「历史卡与实时卡同组件」核对（grep ToolCallCard 仅在 MessageItem 中被引用一次，无第二实现）

### 6.6 空态与快捷问题（O2/O3）+ 会话管理编排

- [ ] **要点**：
  - 空态（`messages.length === 0`）：`el-empty` description「向 AI 助手提问，它会自动调用工具分析你的学习数据」+ 快捷问题区 4 个 `el-button plain` 纵排（`QUICK_QUESTIONS` 常量）；**点击即等价 onSend(question) 直接发送**（填入并发送——一步动作）；**非空会话不显示**（v-if 按消息数判定）
  - 会话编排：新建 → `createAgentConversation()` → 插入列表顶部并置当前 + 右侧空态；切换 → `selectConversation`（loadSeq 守卫 + 消息回放）；重命名 → `renameAgentConversation()` 成功后更新列表行与 chat-head 标题；删除 → 确认后 `deleteAgentConversation()` → 列表移除，**删除当前会话 → 切到剩余首个（无会话时空态）**；`refreshConversations()` → `getAgentConversations(1, 50)` 按服务端顺序覆盖
  - 生成中列表操作被 6.4 的 O5 短路拦截（轻提示）
- **涉及文件**：修改 `frontend/src/views/AgentView.vue`
- **完成判定**：`npm run build` 通过；`grep -n "我最近学习怎么样\|我哪些知识点最薄弱\|我还有哪些任务没做完\|帮我制定下周学习计划" frontend/src/views/AgentView.vue` 四快捷问题**仅出现于 QUICK_QUESTIONS 常量定义处**（O3 清单一处定义）；`grep -n "el-empty" frontend/src/views/AgentView.vue` 空态命中
- **依赖**：6.4 / 6.5
- **决策锚点**：O2 / O3 / O4；**验收锚点**：F5（全操作矩阵）/ **F13（快捷问题）**

**里程碑验证（组 6 结束）**：
```bash
cd frontend && npm run build                                              # 退出码 0（全文件集成编译）
grep -n -B 2 "abort()" frontend/src/views/AgentView.vue                  # 前置行 = assistant.stopped = true（R3 顺序）
grep -c "PagePlaceholder" frontend/src/views/AgentView.vue               # 0（骨架替换完成）
```

---

## 7. 构建与回归（F12 硬门槛）

**写作说明**：本组是 F12 验收的落地。前端无 pytest——验证方式三轨：**vue-tsc 编译（npm run build）+ 代码审查（git diff / grep / 对照表）+ 本机走查（组 8）**。esbuild 间歇崩溃按 §0 前置约定 3 的预案处理（先恢复再重试，勿误判为类型错误）。

### 7.1 npm run build 零错误（硬门槛）

- [ ] **要点**：
  - `cd frontend && npm run build`（`vue-tsc --noEmit && vite build`，package.json:8）——退出码 0、无 TS 报错、vite 产物生成；TS 严格模式 + 禁大面积 any（spec §4.4 规则 1）
  - 类型契约静态审查：build 通过即证明六事件联合穷尽（dispatch switch 穷尽性由 TS 判别联合结构性保证）
  - esbuild 崩溃判定纪律：报错为 esbuild 服务进程级（非 TS 类型错误）→ 按预案恢复重试
- **涉及文件**：无代码改动（构建验证）
- **完成判定**：`cd frontend && npm run build; echo EXIT=$?` 输出 `EXIT=0` 且 vue-tsc 无报错输出
- **依赖**：组 1–6 全部
- **验收锚点**：F12（构建链路）/ F4（类型穷尽性间接验证）

### 7.2 P9 冻结文件 git diff 零改动（R1–R5 / R7 / R8）

- [ ] **要点**：
  - 七类冻结文件逐一 diff 审查（design 2.6 R1–R8 前端部分）：chat.ts（R1）/ AskView.vue + ask 组件（R2）/ request.ts（R3）/ types/index.ts（R4）/ router/index.ts + MainLayout.vue（R5）/ backend/ 全部（R7）
  - AgentView.vue 骨架替换为**唯一许可的既有文件改动**（R8：14 行骨架 → 完整实现；PagePlaceholder 不再被本页引用但组件保留）
- **涉及文件**：审查冻结清单（无代码改动）
- **完成判定**：`git diff --stat -- frontend/src/api/chat.ts frontend/src/api/request.ts frontend/src/views/AskView.vue frontend/src/components/ask/ frontend/src/types/index.ts frontend/src/router/index.ts frontend/src/layouts/MainLayout.vue backend/` 输出为空；`git status --short backend/ | wc -l` 输出 0
- **依赖**：组 1–6
- **验收锚点**：F12 / R1–R5 / R7 / R8

### 7.3 变更范围核对 + R3 静态 grep 收口（三重验证锚点之二）

- [ ] **要点**：
  - **变更范围核对**：`git status --short frontend/` 仅 7 个文件（1 改 6 新增：AgentView.vue + components/agent/ 四文件 + api/agent.ts + types/agent.ts）+ 本 tasks.md；无其他任何文件
  - **R3 静态 grep 走查**：`grep -n -A 2 "} catch" frontend/src/api/agent.ts` —— 逐 catch 人工核对：read 抛错 catch 的**首语句为 `signal?.aborted` 判定**、其后才是「网络中断」合成；建连 catch 的 aborted 窗口分支在错误提示之前
  - **R3 顺序核对**：`grep -n -B 2 "abort()" frontend/src/views/AgentView.vue` —— abort() 前置行即 `stopped = true` 置位
  - **F7 同构收口**：十六项对照表（design 2.4.2-A）与 agent.ts 实际实现逐项比对记录（12 项逐行相同 + 4 项契约性差异——代码审查交付证据）
- **涉及文件**：审查（无代码改动）
- **完成判定**：`git status --short frontend/ | wc -l` 输出 ≤ 7（新增 6 + 修改 1）；上述三条 grep 输出经人工核对通过并记录
- **依赖**：7.1 / 7.2
- **验收锚点**：**F7 / F12 + R3 静态验证锚点（三重验证之二）**

**里程碑验证（组 7 结束——沙箱可自动化验证全量收口）**：
```bash
cd frontend && npm run build; echo EXIT=$?                                                   # EXIT=0
git diff --stat -- frontend/src/api/chat.ts frontend/src/api/request.ts frontend/src/views/AskView.vue frontend/src/components/ask/ frontend/src/types/index.ts frontend/src/router/index.ts frontend/src/layouts/MainLayout.vue backend/   # 输出为空
git status --short frontend/                                                                  # 仅 7 个交付文件
grep -n -A 2 "} catch" frontend/src/api/agent.ts                                              # catch 首句 aborted 判定（人工核对）
```

---

## 8. 本机走查清单交接（V1–V10 → F1–F13 不可自动化项）

**写作说明**：沙箱无浏览器与后端服务——全部行为验收走用户本机走查（design 2.5.2 V1–V10，承接并扩展 spec §8.3 V1–V7）。**前置条件：后端 `uvicorn` 启动 + `.env` LLM 配置有效 + 前端 `npm run dev`（或 build 产物预览）+ 登录态**。走查顺序按 V1→V2 组织（V1 生成中途停止可同时覆盖停止链路）。

### 8.1 走查清单逐项执行（含 R3 走查锚点 V2）

- [ ] **要点**（逐项核对并记录，映射 F 项）：
  | # | 场景 | 步骤要点 | 预期（含验收锚点） |
  |---|------|---------|---------|
  | V1 | 真实多工具分析 | 登录 → /ai-agent → 空态点快捷问题「我最近学习怎么样」 | ≥3 张卡片按序堆叠（调用中 loading 单行 → 完成 36px 折叠行 → 工作轨迹）；逐字回答含真实数字；thinking 行每轮一次且递增；done 后小字统计「N 轮 · M 次工具调用」；**4 连卡片总高观测 ≤ 对话区 1/3**（用户重点 ① 走查锚点）；F1/F3/F6/F13 |
  | **V2** | **停止生成（R3 走查锚点）** | V1 生成中途点「停止生成」 | DevTools 网络面板请求 **canceled**；已出现文本/卡片全保留；「已停止生成」轻量标记；**无红色错误行（R3 硬约束——点停止不得出现「网络中断，请重试」红色提示）**；按钮复位「发送」；列表操作恢复；F6 |
  | V3 | 流内错误 | 改错后端 `.env` LLM_BASE_URL 重启 → 发送 | 中文错误提示行（块内 el-alert）；已生成内容保留；按钮复位 → 还原配置恢复；F10 |
  | V4 | 历史回放 | V1 完成后刷新页面 | 最近会话自动选中回放；卡片折叠态完整重现（**与实时卡同样式**、无耗时项、无思考行）；参数与摘要可见；展开显示格式化 JSON；**孤儿防御不崩溃**；F8 + 用户重点 ② |
  | V5 | 会话管理矩阵 | 新建 → 空态直发消息 → 重命名（含超 200 禁提交）→ 删除非当前 → 删除当前（确认框）；生成中点其他会话/新建 | 各操作结果正确；列表 updated_at 倒序 + 续聊升至首位；空标题「新会话」；首条消息后刷新显示截断标题；生成中点击 → 「请先停止当前生成」轻提示且**无切换发生**；F5 |
  | V6 | 三态收尾（尽力） | 连续复杂追问或后端 mock max_rounds/timeout | max_rounds → 「信息较多，已为你总结」；timeout → 「处理时间较长，以下是已获取的部分」；normal 无提示行但统计小字仍显示；F4 |
  | V7 | 鉴权 | 清 token 访问 /ai-agent；过期 token 发送（会话管理与 SSE 双通道） | 路由守卫跳 /login 带 redirect；SSE 受理 401 → 清 token 跳登录；非流式端点走拦截器同款；F9 |
  | V8 | 输入约束 | 空白消息点发送；粘贴 2001 字 | 空白 → 「请输入消息」警告不发；2001 → maxlength 硬限 + 计数「2000 / 2000」+ 发送禁用；F11 |
  | V9 | 卡片交互与容错 | V1 后逐张卡片点击展开/收起；展开历史卡对比实时卡；后端 mock 非法参数看失败卡 | 展开 = 参数完整键值 + 摘要全文（实时）/ 格式化 JSON（历史）+ 截断标记；再点收起；失败卡警示样式 + 中文错误说明；F2 |
  | V10 | 弱网 loading | DevTools 节流后进页面/切换会话 | 列表与消息加载均有 loading 态不白屏（spec §4.1 规则 4） |
- **涉及文件**：无新增（操作验证，记录建议存 `frontend/tmp_verify/` 或走查记录文档）
- **完成判定**：V1–V10 逐条核对通过（spec §8.3 全量承接 + design 2.5.2 扩展）；**V2 含 R3 第三重验证锚点「点停止后无红色错误行」——必须显式记录结论**
- **依赖**：组 7
- **验收锚点**：F1–F11 / F13 中全部不可自动化项 + R3 走查锚点

**里程碑验证（组 8 结束）**：
```bash
# 无沙箱命令——用户本机执行 V1–V10 并逐项记录（V2 为 R3 硬约束走查锚点，必录）
```

---

## 9. 文档同步与收尾

### 9.1 PROJECT_CONTEXT §3 目录树裁定（实测裁定：无需更新）

- [ ] **要点**：
  - **实测裁定**：`docs/PROJECT_CONTEXT.md` §3 目录树 `components/` 行仅写注释「通用组件（图表、卡片、空状态等）」，**未列出任何子目录**（components/ask/、components/dashboard/ 等既有子目录同样未列出）——新增 `components/agent/` 与该惯例对称，**无需更新目录树**；且 §3 `api/` 小节已列 `agent.ts`（PROJECT_CONTEXT.md:104）、§7.2 页面↔接口表已有 AI Agent 六端点行——文档已先行覆盖本阶段交付
  - 在交付说明中记录本裁定与理由（「§3 components/ 不列子目录惯例 + api/agent.ts 与 §7.2 已列」），避免后续阶段误判为遗漏
- **涉及文件**：无代码改动（裁定记录，随交付说明输出）
- **完成判定**：交付说明含裁定段；`grep -n "components/" docs/PROJECT_CONTEXT.md` 确认该行无子目录列举（与裁定一致）
- **依赖**：无代码依赖（可任意时机执行）
- **决策锚点**：用户任务书第 8 项「实际读取后裁定」要求

### 9.2 代码走查与设计一致性核对

- [ ] **要点**：
  - **R3 三重验证收口归档**：① 2.4 代码审查（catch 首语句 aborted 判定）＋ 6.3（置位先于 abort）→ ② 7.3 静态 grep → ③ 8.1 V2 走查（无红色错误行）——三重结论归档
  - **决策 A1–A12 锚点逐条走查**：A1 摘要同行截断（3.2）/ A2 segments 保序（6.2）/ A3 统一 ToolCallView（1.2 + 3.1）/ **A4 停止链路锁死顺序（2.4 + 6.3）**/ A5 autoFollow 滞回（6.4）/ A6 竞态双防护（6.4）/ A7 调用中同 36px（3.2）/ A8 delta 合并尾段（6.2）/ A9 自绘折叠卡（3.1）/ A10 局部 v-loading（6.4）/ A11 thinking 弱化保留（4.2）/ A12 历史 ok 判定（6.5）
  - **用户两点设计重点核对项归档**：① 36px 折叠行锁定 + 4 连卡片 ≤ 对话区 1/3（3.2 CSS 审查 + V1 走查观测）；② buildViewMessages 两阶段配对 + arguments 容错降级 + 历史卡与实时卡同组件（6.5 算法审查 + V4 走查）
  - **契约核对**：snake_case 全程 / token 红线（拼头不拼 URL、禁 console 打印——`grep -rn "console.log" frontend/src/api/agent.ts frontend/src/views/AgentView.vue` 零命中）/ 子组件零 api 调用（`grep -rln "import request\|@/api" frontend/src/components/agent/` 零命中）/ 常量集中无散落硬编码文案（grep 快捷问题四文案/三态文案仅出现于常量定义处）
  - **docstring 回链**：各新文件注明对应 design 章节号（2.2.2 / 2.3.2 / 2.4.1 / 2.4.2 / 2.4.3 / 2.4.4）
  - 交付时输出（对齐 spec §8.2 用户偏好）：文件清单（每文件职责一句话）+ npm run build 结果原样粘贴 + 需本机走查项清单（映射 F1–F11/F13）
- **涉及文件**：组 1–6 全部新增/改动文件（走查，无代码改动）
- **完成判定**：上述走查项全部通过并记录；与 design.md「下游交接说明」无偏差（未覆盖细节按 PROJECT_CONTEXT 总则处理并在提交说明记录）
- **依赖**：组 7、组 8
- **验收锚点**：design 2.8.1/2.8.2 对照表逐条遵循 + R3 三重锚点归档

**里程碑验证（组 9 结束——全阶段收口）**：
```bash
grep -rln "import request\|@/api" frontend/src/components/agent/        # 输出为空（子组件零 api 调用）
grep -rn "console.log" frontend/src/api/agent.ts frontend/src/views/AgentView.vue   # 输出为空（token/隐私红线）
git diff --stat | tail -5                                               # 变更范围核对：仅设计许可的 7 文件 + 本 tasks.md（+ 如有走查记录）
```

---

## 附一：任务 → 验收覆盖对照（F1–F13，验证方式三轨）

> 验证方式图例：**[B]** = build（vue-tsc 编译）/ **[C]** = 代码审查（diff / grep / 对照表）/ **[W]** = 本机走查（V1–V10）。

| 验收项 | 判定标准摘要（spec §8.1） | 覆盖任务 | 验证轨道 |
|---|---|---|---|
| F1 工具调用卡片可见 | 「正在调用 name(args)…」调用中文案；完成折叠显示名/参/耗时/摘要；≥3 卡按序堆叠 | 3.1（四态）、3.2（36px 锁定）、3.3（格式化）、6.2（onToolCall/onToolResult） | [B][C] + **[W] V1** |
| F2 卡片折叠交互 | 默认折叠；点击展开（实时=摘要全文，历史=格式化 JSON）；再点折叠 | 3.3（toggle + 惰性展开 + 内容切换） | [B] + **[W] V9** |
| F3 thinking 轻量信号 | 每轮一行且递增；无遮罩；已出现内容不被遮挡/清空/位移 | 6.2（onThinking 写入）、4.1/4.2（弱化态渲染）、6.4（autoFollow 可上滚） | [C]（无 overlay grep）+ **[W] V1** |
| F4 finish_reason 三态 + 弱化统计 | 三分支文案齐全常量集中；normal 无提示但统计恒显；小号灰字无 badge | 6.1（FINISH_HINTS 常量）、4.1（块末固定区渲染） | [C]（三分支映射）+ **[W] V6** |
| F5 会话列表 | 倒序/新建/重命名/删除/高亮/「新会话」/续聊居首/生成中轻提示不切换 | 5.1、5.2、6.6、6.4（O5 短路） | [B] + **[W] V5** |
| F6 流式渲染 + 停止 | 逐字出现；按钮原位切换常驻；停止 canceled + 内容保留 + 「已停止」+ 复位可再发 | 6.2（流式）、6.3（停止链路+finally）、4.3（按钮切换）、2.4（aborted 静默） | [C] + **[W] V1/V2** |
| **F7 SSE 解析复用** | agent.ts 与 chat.ts 解析骨架一致（\n\n 切块/残包 buffer/decoder stream:true/脏块跳过），仅事件扩为六种 | **2.3（十六项对照表同构复刻——主体）**、7.3（比对收口） | **[C]（对照表逐项审查——本项纯代码审查验收）** |
| **F8 历史回放** | 刷新/切换 → 同样式折叠卡片；arguments 容错；孤儿不崩溃；无耗时但样式一致 | **6.5（buildViewMessages 算法——主体）**、1.2/3.1（统一 ToolCallView 无模式分支） | [B][C] + **[W] V4** |
| F9 鉴权 | 未登录跳 /login 带 redirect；SSE 401 清 token 跳登录；非流式走拦截器 | 2.2（受理 401/1003）、2.1（request 通道） | [C]（clearTokenAndRedirect 单一实现 grep）+ **[W] V7** |
| F10 异常处理 | 流内错误中文提示+内容保留；断网「网络中断」+保留；五路径全复位 | 2.2/2.3/2.4（受理+流耗尽+catch 分流）、6.3（单一 finally） | [C] + **[W] V3** |
| F11 输入约束 | 空白禁发；2000 上限计数提示+禁发；422 中文提示 | 4.3（校验链 + maxlength） | [B] + **[W] V8** |
| F12 构建与兼容 | npm run build 零错误；P9 文件 git diff 为空；router/MainLayout 零改动 | **7.1（build 硬门槛）、7.2（冻结 diff）、7.3（范围核对）**、1.3 | **[B][C]（本项纯命令验收）** |
| F13 快捷问题按钮 | 空会话 4 按钮可点即发送；非空不显示 | 6.6（O2/O3 空态） | [C]（常量单处定义）+ **[W] V1** |

## 附二：R3 硬约束验证锚点汇总（三重验证）

| # | 验证方式 | 锚点位置 | 判定内容 |
|---|---------|---------|---------|
| ① | **代码审查** | 任务 2.4 完成判定 + 任务 6.3 完成判定 | **catch 块首语句即 `signal?.aborted` 判定**（先于任何错误分类逻辑）；onStop 中 `assistant.stopped = true` 置位先于 `abort()` 调用——锁死顺序未被重排 |
| ② | **静态 grep** | 任务 7.3 | `grep -n -A 2 "} catch" frontend/src/api/agent.ts`（catch 后第一行为 aborted 判定）+ `grep -n -B 2 "abort()" frontend/src/views/AgentView.vue`（前置行为置位） |
| ③ | **本机走查 V2** | 任务 8.1 | V1 生成中途点停止 → **无红色错误行**（不落入「网络中断，请重试」分支）+ 请求 canceled + 内容保留 + 「已停止生成」标记 + 按钮复位 |

## 附三：spec 需求条目 → 任务覆盖

| spec 需求条目 | 覆盖任务 |
|---|---|
| §5.1 布局与路由激活（双栏/零改动路由/O3 快捷问题） | 6.1（骨架）、6.6（空态）、7.2（R5 零改动 diff） |
| §5.2 会话列表管理（规则 1–10 含 O5 约束） | 5.1、5.2、6.4（O5 短路）、6.6（编排与刷新时机） |
| §5.3 SSE 六事件消费状态机（规则 1–14） | 2.2（受理）、2.3（分发）、6.2（六回调写入）、6.3（终态复位）、4.3（按钮状态） |
| §5.4 工具调用卡片可视化（规则 1–8） | 3.1（四态）、3.2（高度）、3.3（格式化与容错） |
| §5.5 thinking 信号与 finish_reason 三态（含 O8） | 4.1（渲染）、4.2（弱化）、6.1（常量） |
| §5.6 历史回放还原算法（规则 1–8） | 6.5（buildViewMessages 全量）、6.4（切换调度与 loading） |
| §5.7 鉴权与异常分层（规则 1–4） | 2.1（拦截器通道）、2.2（SSE 鉴权）、6.3（错误分层终态） |
| §4.1–4.5 DFX（流式/滚动/终态必达/红线/零改动） | 6.2（流式）、6.4（autoFollow）、6.3（终态）、9.2（token 红线 grep）、7.2（零改动） |
| §6 七文件拆分 + §7 数据约束 | 组 1–6 文件结构 + 常量表（§0）+ 1.1（字段对齐） |
| §8 F1–F13 验收 | 附一全量映射 |
| 裁决 #1–#4 + O1–O8 + R3 硬约束 | §0 前置约定 + 各任务决策锚点 + **2.4/6.3（R3 独立任务项）+ 附二（三重验证）** |
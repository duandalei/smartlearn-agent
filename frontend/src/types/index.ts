/**
 * 全局 TypeScript 类型定义（与后端 Pydantic schema 对齐）。
 *
 * 约定：字段名与后端保持 snake_case（PROJECT_CONTEXT 8.3），
 * 仅展示层按需转 camelCase。本文件随业务阶段逐步扩展。
 */

/** 统一响应体：{code, message, data}（PROJECT_CONTEXT 5.2）。 */
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

/** 分页数据结构（PROJECT_CONTEXT 5.3）。 */
export interface PageResult<T = unknown> {
  items: T[]
  total: number
  page: number
  page_size: number
}

/** 当前本地用户信息（对齐后端 UserOut，不含密码相关字段）。 */
export interface UserInfo {
  id: number
  username: string
  email: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

/** 用户学习档案（对齐后端 UserProfileOut）。 */
export interface UserProfile {
  id: number
  user_id: number
  name: string | null
  school: string | null
  major: string | null
  grade: string | null
  current_goal_type: string | null
  interest_directions: string[]
  daily_study_minutes: number
  created_at: string
  updated_at: string
}

/**
 * 档案更新入参（PUT /profile，字段级部分更新）。
 *
 * 后端语义：仅「已提交且非 null」的字段生效，未提交字段保持原值；
 * 前端只需把要修改的字段放进对象即可。
 */
export interface UserProfileUpdatePayload {
  name?: string
  school?: string
  major?: string
  grade?: string
  current_goal_type?: string
  interest_directions?: string[]
  daily_study_minutes?: number
}
// ---------------------------------------------------------------------------
// 学习目标（P4）
// ---------------------------------------------------------------------------

/** 目标状态（对齐后端 GoalStatus 枚举）。 */
export type GoalStatus = 'active' | 'completed' | 'archived'

/** 表单可选的目标类型（5 枚举；历史数据可能为其他字符串）。 */
export type GoalTypeOption = '考研' | '保研' | '就业' | '比赛' | '技能提升'

/** 知识树节点（对齐后端 RoadmapNode；children 空数组 = 叶子）。 */
export interface RoadmapNode {
  name: string
  children: RoadmapNode[]
}

/** 学习目标（对齐后端 GoalOut；roadmap 可空 = 从未拆解）。 */
export interface Goal {
  id: number
  user_id: number
  title: string
  goal_type: string | null // 读侧宽松：兼容历史值；写侧由表单限制 5 枚举
  description: string | null
  start_date: string | null // 'YYYY-MM-DD'
  end_date: string | null
  status: GoalStatus
  roadmap: RoadmapNode | null
  roadmap_updated_at: string | null
  created_at: string
  updated_at: string
}

/** 知识树查询 / 拆解出参（对齐后端 RoadmapOut）。 */
export interface GoalRoadmap {
  goal_id: number
  roadmap: RoadmapNode | null
  roadmap_updated_at: string | null
}

/** 目标列表查询参数。 */
export interface GoalListQuery {
  page?: number
  page_size?: number
  status?: GoalStatus
}

/** 新建目标入参。 */
export interface GoalCreatePayload {
  title: string
  goal_type?: GoalTypeOption
  description?: string
  start_date?: string
  end_date?: string
}

/** 编辑目标入参（部分更新：仅提交要修改的字段）。 */
export interface GoalUpdatePayload {
  title?: string
  goal_type?: GoalTypeOption
  description?: string
  start_date?: string
  end_date?: string
  status?: GoalStatus
}
// ---------------------------------------------------------------------------
// 学习任务（P5）
// ---------------------------------------------------------------------------

/** 任务状态（对齐后端 TaskStatus 枚举，spec 锁定四值）。 */
export type TaskStatus = 'todo' | 'in_progress' | 'done' | 'review'

/** 优先级（对齐后端 Priority 枚举）。 */
export type TaskPriority = 'low' | 'medium' | 'high'

/** 学习任务（对齐后端 TaskOut；knowledge_points 永为数组，spec 4.5.3）。 */
export interface Task {
  id: number
  user_id: number
  goal_id: number | null
  course_id: number | null
  title: string
  description: string | null
  knowledge_points: string[]
  priority: TaskPriority
  estimated_minutes: number | null
  actual_minutes: number | null
  deadline: string | null // ISO 时间戳
  scheduled_date: string | null // 'YYYY-MM-DD'
  status: TaskStatus
  source: 'manual' | 'agent'
  created_at: string
  updated_at: string
  completed_at: string | null
}

/** 任务列表查询参数（与后端 8 个标量 query 一一对应）。 */
export interface TaskListQuery {
  page?: number
  page_size?: number
  status?: TaskStatus
  priority?: TaskPriority
  course_id?: number
  knowledge_point?: string
  overdue?: boolean
  keyword?: string
}

/** 新建任务入参（无 status / scheduled_date，对齐 TaskCreate）。 */
export interface TaskCreatePayload {
  title: string
  description?: string
  goal_id?: number
  course_id?: number
  knowledge_points?: string[]
  priority?: TaskPriority
  estimated_minutes?: number
  deadline?: string
}

/** 编辑任务入参（部分更新；额外含 actual_minutes / scheduled_date）。 */
export interface TaskUpdatePayload extends Partial<TaskCreatePayload> {
  actual_minutes?: number
  scheduled_date?: string
}

/** 状态流入参（PATCH /tasks/{id}/status）。 */
export interface TaskStatusPayload {
  status: TaskStatus
}

/** 看板数据（固定四键，列序 = 状态机流转序）。 */
export type TaskBoardData = Record<TaskStatus, Task[]>

/** 任务统计（对齐后端 TaskStatsOut，字段全 snake_case 直传）。 */
export interface TaskStats {
  total: number
  status_counts: Record<TaskStatus, number>
  overdue_count: number
  weekly_completion_rate: number
  today_todo_count: number
}

// ---------------------------------------------------------------------------
// 课程（P2 只读接口消费，P5 课程下拉数据源）
// ---------------------------------------------------------------------------

/** 课程（对齐后端 CourseOut）。 */
export interface Course {
  id: number
  user_id: number
  name: string
  description: string | null
  teacher: string | null
  semester: string | null
  created_at: string
}
// ---------------------------------------------------------------------------
// 学习记录（P6）
// ---------------------------------------------------------------------------

/**
 * 学习记录（对齐后端 RecordOut）。
 *
 * mastery_level 是学生本次学习的自评（聚合输入，null = 本次不参与
 * 掌握度聚合），与 knowledge_mastery.mastery_score（聚合输出）语义不同。
 */
export interface LearningRecord {
  id: number
  user_id: number
  task_id: number | null
  course_id: number | null
  content: string
  duration_minutes: number
  achievement: string | null
  problems: string | null
  knowledge_points: string[] // JSONListType 读出语义：永为数组
  mastery_level: number | null
  study_date: string // 'YYYY-MM-DD'（可补记历史日期）
  created_at: string
}

/** 记录列表查询参数（与后端 6 个标量 query 一一对应）。 */
export interface RecordListQuery {
  page?: number
  page_size?: number
  start_date?: string
  end_date?: string
  course_id?: number
  knowledge_point?: string
}

/** 新建记录入参（对齐后端 RecordCreate；study_date 不得晚于北京今天）。 */
export interface RecordCreatePayload {
  content: string
  duration_minutes: number
  study_date: string
  mastery_level?: number | null
  knowledge_points?: string[]
  task_id?: number | null
  course_id?: number | null
  achievement?: string | null
  problems?: string | null
}

/**
 * 编辑记录入参（对齐后端 RecordUpdate，提交即生效含显式 null）。
 *
 * 与 TaskUpdate 的「传 null 不清空」不同：mastery_level 置 null =
 * 退出掌握度聚合、task_id / course_id 置 null = 解除关联。
 */
export interface RecordUpdatePayload {
  content?: string
  duration_minutes?: number
  study_date?: string
  mastery_level?: number | null
  knowledge_points?: string[] | null
  task_id?: number | null
  course_id?: number | null
  achievement?: string | null
  problems?: string | null
}

/** 时间线单日（对齐后端 TimelineItemOut，无记录的天补 0）。 */
export interface TimelineItem {
  date: string
  minutes: number
}

/** 时间线出参（对齐后端 TimelineOut，恰 days 条、date 升序）。 */
export interface TimelineData {
  days: number
  start_date: string
  end_date: string
  items: TimelineItem[]
}

/** 学习统计（对齐后端 RecordStatsOut，三值全部后端计算）。 */
export interface RecordStats {
  weekly_minutes: number
  streak_days: number
  total_count: number
}

/** 记录按日期分组的渲染结构（utils/record.ts groupRecordsByDate 产物）。 */
export interface RecordDateGroup {
  date: string
  title: string // 今天 / 昨天 / YYYY-MM-DD
  records: LearningRecord[]
}// ---------------------------------------------------------------------------
// 学习分析看板（P7）
// ---------------------------------------------------------------------------

/** 指标总览（对齐后端 OverviewOut 七指标，全部后端计算直传）。 */
export interface OverviewData {
  total_minutes: number
  task_completion_rate: number
  avg_mastery: number
  streak_days: number
  total_record_count: number
  avg_session_minutes: number
  overdue_task_count: number
}

/** 趋势序列单日（date 为 'YYYY-MM-DD'，后端补零直传，前端零解析）。 */
export interface TrendItem {
  date: string
  minutes: number
}

/** 学习风险预警（未触发时整体为 null）。 */
export interface RiskAlert {
  level: string
  title: string
  message: string
  suggestion: string
}

/** 学习时间趋势出参（对齐后端 TrendOut；risk_alert 与 days 参数解耦）。 */
export interface TrendData {
  days: number
  start_date: string
  end_date: string
  items: TrendItem[]
  slope: number
  risk_alert: RiskAlert | null
}

/** 掌握度单项（对齐后端 MasteryItemOut）。 */
export interface MasteryItem {
  knowledge_point: string
  mastery_score: number
}

/** 掌握度出参（对齐后端 MasteryOut，按 mastery_score 升序）。 */
export interface MasteryData {
  items: MasteryItem[]
}

/** 薄弱点单项（对齐后端 WeaknessItemOut，recent_count 为近 30 天出现频次）。 */
export interface WeaknessItem {
  knowledge_point: string
  mastery_score: number
  recent_count: number
  advice: string
}

/** 薄弱点出参（对齐后端 WeaknessOut，Top5 已由后端排定）。 */
export interface WeaknessData {
  items: WeaknessItem[]
}

/** 建议类型（对齐后端三规则顺序：overdue / weakness / streak）。 */
export type AdviceType = 'overdue' | 'weakness' | 'streak'

/** 建议单项（对齐后端 AdviceItemOut）。 */
export interface AdviceItem {
  type: AdviceType
  title: string
  content: string
}

/** 建议出参（对齐后端 AdviceOut，命中几条返回几条）。 */
export interface AdviceData {
  items: AdviceItem[]
}// ---------------------------------------------------------------------------
// 知识库（P8，RAG 检索）
// ---------------------------------------------------------------------------

/** 文档处理状态（对齐后端 KnowledgeItemStatus 枚举：D1 裁决四态）。 */
export type KnowledgeItemStatus = 'pending' | 'parsing' | 'indexed' | 'failed'

/** 文档归属（公共库能力已移除，仅个人库）。 */
export type KnowledgeScope = 'personal'

/** 知识库文档（对齐后端 KnowledgeItemOut，列表与详情共用）。 */
export interface KnowledgeItem {
  id: number
  user_id: number | null
  title: string
  source_type: string
  file_path: string | null
  scope: KnowledgeScope
  status: KnowledgeItemStatus
  error_msg: string | null
  chunk_count: number
  file_size: number | null
  created_at: string
  updated_at: string
}

/** 上传受理响应（对齐后端 KnowledgeUploadOut：status 恒为 pending）。 */
export interface KnowledgeUploadResult {
  item_id: number
  status: string
}

/** 知识分块（对齐后端 KnowledgeChunkOut，chunk_index 升序全量返回）。 */
export interface KnowledgeChunk {
  id: number
  item_id: number
  user_id: number | null
  chunk_index: number
  content: string
  heading_path: string | null
  embedding_id: string | null
  created_at: string
}

/** 检索入参（POST /knowledge/search，query 非空 ≤500 字符、top_k 1~20）。 */
export interface KnowledgeSearchPayload {
  query: string
  top_k?: number
}

/** 单条检索命中（对齐后端 KnowledgeSearchHit，按 score 降序）。
 *
 * item_id / chunk_index / scope 为 P9 裁决 #3 新增可选字段（后端
 * 组装时透出，供问答来源卡跳转定位与归属徽章使用）；可选语义对齐
 * 后端 schema（默认 null，实际总有值），不影响既有消费方。
 */
export interface KnowledgeSearchHit {
  content: string
  source_title: string
  score: number
  item_id?: number | null
  chunk_index?: number | null
  scope?: KnowledgeScope | null
}

/** 检索响应（对齐后端 KnowledgeSearchOut；mode 为可用性瞬时判定，不落库）。 */
export interface KnowledgeSearchResult {
  mode: 'online' | 'offline'
  results: KnowledgeSearchHit[]
}

// ---------------------------------------------------------------------------
// AI 学习问答（P9，RAG QA）
// ---------------------------------------------------------------------------

/** 问题意图（对齐后端 done.data.intent / qa_history.intent，R3 新增）。 */
export type QaIntent = 'knowledge' | 'chat'

/** SSE 来源条目（对齐后端 sources 事件 data 元素 / QaSourceItem）。
 *
 * item_id / chunk_index 可空为防御性设计：极端脏快照下历史接口不
 * 500，前端跳转判空降级为纯展示。
 */
export interface QaSourceItem {
  item_id: number | null
  chunk_index: number | null
  content: string
  source_title: string
  score: number
  scope: KnowledgeScope
}

/** SSE 事件可辨识联合（对齐后端四事件契约；done 为 R3 四字段）。 */
export type QaSseEvent =
  | { type: 'sources'; data: QaSourceItem[] }
  | { type: 'delta'; data: string }
  | {
      type: 'done'
      data: {
        is_grounded: boolean
        mode: 'online' | 'offline'
        intent: QaIntent
        history_id: number | null
      }
    }
  | { type: 'error'; data: { code: number; message: string } }

/** 问答请求体（POST /chat/qa；公共库已移除，无 scope）。 */
export interface ChatQaPayload {
  question: string
}

/** 历史问答条目（对齐后端 ChatHistoryOut，含 intent——回放双信号
 * 样式判定的前置信号：intent=knowledge 且 is_grounded=false 才渲染
 * 无据警示，intent=chat 恒正常样式）。 */
export interface ChatHistoryItem {
  id: number
  question: string
  answer: string
  sources: QaSourceItem[]
  mode: 'online' | 'offline'
  is_grounded: boolean
  intent: QaIntent
  created_at: string
}

/** 历史分页响应（对齐后端 paginate 结构）。 */
export interface ChatHistoryResult {
  items: ChatHistoryItem[]
  total: number
  page: number
  page_size: number
}

/** 问答视图内部消息类型（AskView ↔ MessageBubble 组件间契约）。
 *
 * 双信号 is_grounded / intent 在流中为 null（权威值由 done 事件
 * 服务端下发），done 后定值；历史还原直接携带定值。
 */
export interface AskMessage {
  role: 'user' | 'assistant'
  content: string
  sources: QaSourceItem[]
  is_grounded: boolean | null
  intent: QaIntent | null
  mode: 'online' | 'offline' | null
  streaming: boolean
  error: string | null
}
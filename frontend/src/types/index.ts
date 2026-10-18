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

/** 健康检查返回的 data。 */
export interface HealthData {
  status: string
}

/** 登录用户信息（对齐后端 UserOut，不含密码相关字段）。 */
export interface UserInfo {
  id: number
  username: string
  email: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

/** 登录 / 注册入参（POST /auth/login、POST /auth/register）。 */
export interface LoginPayload {
  username: string
  password: string
}

/** 注册入参（须与后端 RegisterIn 一致：用户名 ≥2 位，密码 ≥6 位）。 */
export interface RegisterPayload {
  username: string
  password: string
  confirm_password: string
}

/** 登录 / 注册成功响应的 data（对齐后端 AuthResult）。 */
export interface AuthResult {
  access_token: string
  token_type: string
  user: UserInfo
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
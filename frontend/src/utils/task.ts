/**
 * 学习任务纯函数与常量（P5，design 2.5.7）。
 *
 * 本文件是后端 `backend/app/services/task.py` 中 TRANSITIONS / STATUS_LABELS
 * 常量的前端镜像，仅用于渲染可选项与文案；状态合法性判定的唯一来源是
 * 后端状态机（非法流转返回 1007/400），即使前端镜像被绕过也有后端兜底。
 * 修改状态机时须同步维护两处（互为注释指向）。
 */
import type { Task, TaskPriority, TaskStatus } from '@/types'

/** 状态中文（镜像后端 STATUS_LABELS，spec 6.2.4）。 */
export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  todo: '待办',
  in_progress: '进行中',
  done: '已完成',
  review: '待复盘',
}

/**
 * 合法流转表（镜像后端 TRANSITIONS，有且仅有 5 条边）：
 * todo→in_progress / in_progress→done / in_progress→todo（搁置回退，裁定㉑）/
 * done→review / review→done。
 */
export const TASK_TRANSITIONS: Record<TaskStatus, TaskStatus[]> = {
  todo: ['in_progress'],
  in_progress: ['done', 'todo'],
  done: ['review'],
  review: ['done'],
}

/**
 * 行内切换可选项：仅列出当前状态的合法目标。
 *
 * 搁置边（in_progress→todo）label 显示「待办（搁置）」以区分正向流转。
 */
export function nextStatusOptions(s: TaskStatus): { value: TaskStatus; label: string }[] {
  return TASK_TRANSITIONS[s].map((target) => ({
    value: target,
    label:
      s === 'in_progress' && target === 'todo'
        ? '待办（搁置）'
        : TASK_STATUS_LABELS[target],
  }))
}

/**
 * 逾期判断（口径同后端 spec 6.3.1）：deadline 已过且 status ∈ {todo, in_progress}。
 * 无 deadline 或已 done/review 一律返回 false。
 */
export function isTaskOverdue(task: Task, now: Date = new Date()): boolean {
  if (task.deadline == null) return false
  if (task.status !== 'todo' && task.status !== 'in_progress') return false
  return new Date(task.deadline).getTime() < now.getTime()
}

/** 优先级 tag 类型（high=danger / medium=warning / low=info）。 */
export function priorityTagType(p: TaskPriority): 'danger' | 'warning' | 'info' {
  if (p === 'high') return 'danger'
  if (p === 'medium') return 'warning'
  return 'info'
}

/** 看板列固定顺序（裁定⑫：todo / in_progress / done / review）。 */
export const BOARD_COLUMNS: TaskStatus[] = ['todo', 'in_progress', 'done', 'review']

/** 个位数补零。 */
function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

/**
 * 截止时间格式化为 'YYYY-MM-DD HH:mm'；空值返回 '—'。
 * 纯原生 Date 实现，不引入日期库（用户约定）。
 */
export function formatDeadline(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}
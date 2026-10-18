<script setup lang="ts">
/**
 * 新建 / 编辑任务弹窗（P5，design 2.5.4）。
 *
 * - props.task 为 null 时是新建模式；弹窗不出现任何状态控件
 *   （spec 5.6.1 规则 4 硬性约束——状态变更入口仅列表行内切换与看板拖拽）。
 * - knowledge_points：el-select multiple + allow-create，输入新标签回车即创建
 *   选中（spec 5.6.1 规则 4a）；≤20 项，前端过滤空串（spec 5.6.3 场景 2）。
 * - deadline 不加 disabledDate，允许选过去时间（补录，决策⑳）。
 * - 提交语义：新建走 createTask；编辑仅提交实际变更字段（对比原值构造 payload）。
 * - 失败弹窗保持打开、表单数据不丢失（spec 5.6.3 场景 3）。
 */
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { createTask, updateTask } from '@/api/task'
import type {
  Course,
  Task,
  TaskCreatePayload,
  TaskPriority,
  TaskUpdatePayload,
} from '@/types'

const props = defineProps<{
  visible: boolean
  /** null = 新建。 */
  task: Task | null
  courses: Course[]
  /** 已加载任务的知识点聚合（供下拉候选）。 */
  knowledgeOptions: string[]
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'saved', task: Task): void
}>()

const formRef = ref<FormInstance>()
const saving = ref(false)

/** 表单模型（可空字段统一 null 占位，提交时过滤）。 */
const form = reactive({
  title: '',
  description: '',
  course_id: null as number | null,
  knowledge_points: [] as string[],
  priority: 'medium' as TaskPriority,
  estimated_minutes: null as number | null,
  deadline: null as Date | null,
  actual_minutes: null as number | null,
  scheduled_date: null as string | null,
})

/** 弹窗标题。 */
const dialogTitle = computed(() => (props.task ? '编辑任务' : '新建任务'))

/** 校验规则（与后端 schema 双保险）。 */
const rules: FormRules = {
  title: [
    { required: true, message: '请输入任务名称', trigger: 'blur' },
    { min: 1, max: 200, message: '任务名称长度为 1~200 个字符', trigger: 'blur' },
  ],
  knowledge_points: [
    {
      trigger: 'change',
      validator: (_rule, value: string[], callback) => {
        if (value.length > 20) {
          callback(new Error('知识点最多 20 个'))
        } else {
          callback()
        }
      },
    },
  ],
  estimated_minutes: [
    {
      trigger: 'change',
      validator: (_rule, value: number | null, callback) => {
        if (value != null && value < 1) {
          callback(new Error('预计耗时至少 1 分钟'))
        } else {
          callback()
        }
      },
    },
  ],
  actual_minutes: [
    {
      trigger: 'change',
      validator: (_rule, value: number | null, callback) => {
        if (value != null && value < 0) {
          callback(new Error('实际耗时不能为负数'))
        } else {
          callback()
        }
      },
    },
  ],
}

/** 打开弹窗时回填表单（新建模式全部置空）。 */
function fillForm(): void {
  const t = props.task
  form.title = t?.title ?? ''
  form.description = t?.description ?? ''
  form.course_id = t?.course_id ?? null
  form.knowledge_points = t ? [...t.knowledge_points] : []
  form.priority = t?.priority ?? 'medium'
  form.estimated_minutes = t?.estimated_minutes ?? null
  form.deadline = t?.deadline ? new Date(t.deadline) : null
  form.actual_minutes = t?.actual_minutes ?? null
  form.scheduled_date = t?.scheduled_date ?? null
  formRef.value?.clearValidate()
}

watch(
  () => props.visible,
  (v) => {
    if (v) {
      fillForm()
    }
  },
)

/** 知识点候选：props 聚合选项 + 当前已选但不在候选中的标签。 */
const kpOptions = computed<string[]>(() => {
  const extra = form.knowledge_points.filter((k) => !props.knowledgeOptions.includes(k))
  return [...props.knowledgeOptions, ...extra]
})

/** Date → ISO 字符串（本地时区，提交给后端解析）。 */
function dateToIso(d: Date | null): string | undefined {
  if (!d) return undefined
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString()
}

/** 构造新建入参（空字段不提交键）。 */
function buildCreatePayload(): TaskCreatePayload {
  const payload: TaskCreatePayload = { title: form.title.trim() }
  if (form.description.trim()) payload.description = form.description.trim()
  if (typeof form.course_id === 'number') payload.course_id = form.course_id
  if (form.knowledge_points.length > 0) payload.knowledge_points = [...form.knowledge_points]
  if (form.priority !== 'medium') payload.priority = form.priority
  if (typeof form.estimated_minutes === 'number') payload.estimated_minutes = form.estimated_minutes
  const deadlineIso = dateToIso(form.deadline)
  if (deadlineIso) payload.deadline = deadlineIso
  return payload
}

/**
 * 构造编辑入参：仅提交实际变更字段。
 *
 * 后端 TaskUpdate 不支持 null 清空（未提交 = 保持原值），与 P4 目标编辑同语义。
 */
function buildUpdatePayload(): TaskUpdatePayload {
  const t = props.task
  if (!t) return {}
  const payload: TaskUpdatePayload = {}
  if (form.title.trim() !== t.title) payload.title = form.title.trim()

  const desc = form.description.trim() || null
  if (desc !== t.description && desc != null) payload.description = desc

  if (form.course_id !== t.course_id && typeof form.course_id === 'number') {
    payload.course_id = form.course_id
  }

  const kps = form.knowledge_points.filter((k) => k.trim() !== '')
  if (kps.length !== t.knowledge_points.length || kps.some((k, i) => k !== t.knowledge_points[i])) {
    payload.knowledge_points = kps
  }

  if (form.priority !== t.priority) payload.priority = form.priority
  if (form.estimated_minutes !== t.estimated_minutes && typeof form.estimated_minutes === 'number') {
    payload.estimated_minutes = form.estimated_minutes
  }
  if (form.deadline != null) {
    const iso = dateToIso(form.deadline)
    if (iso && iso !== t.deadline) payload.deadline = iso
  }
  if (form.actual_minutes !== t.actual_minutes && typeof form.actual_minutes === 'number') {
    payload.actual_minutes = form.actual_minutes
  }
  if (form.scheduled_date != null && form.scheduled_date !== t.scheduled_date) {
    payload.scheduled_date = form.scheduled_date
  }
  return payload
}

/** 提交表单（校验通过后按模式调对应接口；失败保持弹窗打开）。 */
async function handleSubmit(): Promise<void> {
  const valid = await formRef.value?.validate().then(
    () => true,
    () => false,
  )
  if (!valid) return

  saving.value = true
  try {
    let saved: Task
    if (props.task) {
      const payload = buildUpdatePayload()
      if (Object.keys(payload).length === 0) {
        ElMessage.info('没有修改的内容')
        return
      }
      saved = await updateTask(props.task.id, payload)
    } else {
      saved = await createTask(buildCreatePayload())
    }
    ElMessage.success(props.task ? '任务已更新' : '任务已创建')
    emit('saved', saved)
    emit('update:visible', false)
  } catch {
    // 错误提示已由 request.ts 拦截器统一展示；弹窗保持打开、数据不丢
  } finally {
    saving.value = false
  }
}

/** 取消并关闭弹窗。 */
function handleCancel(): void {
  emit('update:visible', false)
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    :title="dialogTitle"
    width="560px"
    :close-on-click-modal="false"
    @update:model-value="(v: boolean) => emit('update:visible', v)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
      <el-form-item label="任务名称" prop="title">
        <el-input
          v-model="form.title"
          placeholder="如：完成 Transformers 精读第三章"
          maxlength="200"
          show-word-limit
          clearable
        />
      </el-form-item>
      <el-form-item label="所属课程" prop="course_id">
        <el-select
          v-model="form.course_id"
          placeholder="选择课程（可空）"
          clearable

        >
          <el-option v-for="c in courses" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="知识点" prop="knowledge_points">
        <el-select
          v-model="form.knowledge_points"
          multiple
          filterable
          allow-create
          default-first-option
          placeholder="输入知识点回车创建（最多 20 个，可空）"
        >
          <el-option v-for="k in kpOptions" :key="k" :label="k" :value="k" />
        </el-select>
      </el-form-item>
      <el-form-item label="优先级" prop="priority">
        <el-radio-group v-model="form.priority">
          <el-radio value="low">低</el-radio>
          <el-radio value="medium">中</el-radio>
          <el-radio value="high">高</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="预计耗时" prop="estimated_minutes">
        <el-input-number
          v-model="form.estimated_minutes"
          :min="1"
          :step="10"
          placeholder="分钟（可空）"
          controls-position="right"
        />
      </el-form-item>
      <el-form-item label="截止时间" prop="deadline">
        <el-date-picker
          v-model="form.deadline"
          type="datetime"
          placeholder="选择截止时间（可空，可选过去时间补录）"
          clearable
        />
      </el-form-item>
      <template v-if="task">
        <el-form-item label="实际耗时" prop="actual_minutes">
          <el-input-number
            v-model="form.actual_minutes"
            :min="0"
            :step="10"
            placeholder="分钟（可空）"
            controls-position="right"
          />
        </el-form-item>
        <el-form-item label="计划日期" prop="scheduled_date">
          <el-date-picker
            v-model="form.scheduled_date"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择计划执行日期（可空）"
            clearable
          />
        </el-form-item>
      </template>
      <el-form-item label="任务描述" prop="description">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="3"
          maxlength="1000"
          placeholder="补充任务细节、验收标准等（可空）"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="handleCancel">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleSubmit">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.el-select,
.el-date-editor,
.el-input-number {
  width: 100%;
}
</style>
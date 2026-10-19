<script setup lang="ts">
/**
 * 新建 / 编辑学习记录弹窗（P6）。
 *
 * - props.editing 为 null 时是新建模式；props.preset 携带 P5 跳转 /
 *   空态引导的预填值（content / knowledge_points / course_id /
 *   task_id / task_title），仅打开弹窗瞬间生效。
 * - study_date 禁选未来日期（后端同口径校验「不得晚于今天」）。
 * - mastery_level 三段刻度（0-40 薄弱 / 40-70 一般 / 70-100 熟练），
 *   「跳过自评」勾选后滑块禁用、提交 null（本次不参与掌握度聚合）；
 *   编辑回填原值为 null 时自动勾选。
 * - 提交语义：新建走 createRecord；编辑仅提交实际变更字段——与 Task
 *   不同，RecordUpdate 显式 null 生效（mastery_level 置空退出聚合、
 *   task_id / course_id 置空解除关联）。
 * - 失败弹窗保持打开、表单数据不丢失（拦截器已统一弹错）。
 */
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { createRecord, updateRecord } from '@/api/record'
import { normalizeKnowledgePoints } from '@/utils/knowledge'
import { MASTERY_SEGMENTS, masterySegment, todayLocalStr } from '@/utils/record'
import type {
  Course,
  LearningRecord,
  RecordCreatePayload,
  RecordUpdatePayload,
} from '@/types'

/** 新建弹窗预填值（P5 跳转 / 空态引导传入；纯前端结构，不提交）。 */
export interface RecordPreset {
  content?: string
  knowledge_points?: string[]
  course_id?: number | null
  task_id?: number | null
  task_title?: string
}

const props = defineProps<{
  visible: boolean
  /** null = 新建。 */
  editing: LearningRecord | null
  courses: Course[]
  /** 新建模式预填值（编辑模式忽略）。 */
  preset: RecordPreset | null
  /** 已加载记录的知识点聚合（供下拉候选）。 */
  knowledgeOptions?: string[]
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'saved', record: LearningRecord): void
}>()

const formRef = ref<FormInstance>()
const saving = ref(false)

/** 表单模型（可空字段统一 null 占位）。 */
const form = reactive({
  content: '',
  duration_minutes: 30,
  study_date: '',
  knowledge_points: [] as string[],
  course_id: null as number | null,
  task_id: null as number | null,
  task_title: '',
  mastery_level: 60,
  achievement: '',
  problems: '',
})

/** 跳过自评：勾选后滑块禁用、提交 mastery_level=null。 */
const skipSelf = ref(false)

/** 弹窗标题。 */
const dialogTitle = computed(() => (props.editing ? '编辑学习记录' : '记录学习'))

/** 滑块三段刻度点位。 */
const sliderMarks: Record<number, string> = { 0: '0', 40: '40', 70: '70', 100: '100' }

/** 当前自评所属分段（跳过自评时无高亮）。 */
const currentSegment = computed<string | null>(() => {
  if (skipSelf.value) return null
  return masterySegment(form.mastery_level)?.label ?? null
})

/** 任务关联回显文案（编辑模式无标题来源时回退显示编号）。 */
const taskDisplay = computed(() => {
  if (form.task_id == null) return ''
  return form.task_title || `已关联任务 #${form.task_id}`
})

/** 知识点候选：props 聚合选项 + 当前已选但不在候选中的标签。 */
const kpOptions = computed<string[]>(() => {
  const options = props.knowledgeOptions ?? []
  const extra = form.knowledge_points.filter((k) => !options.includes(k))
  return [...options, ...extra]
})

/** 校验规则（与后端 schema 双保险）。 */
const rules: FormRules = {
  content: [
    { required: true, message: '请输入学习内容', trigger: 'blur' },
    { min: 1, max: 500, message: '学习内容长度为 1~500 个字符', trigger: 'blur' },
  ],
  duration_minutes: [
    {
      trigger: 'change',
      validator: (_rule, value: number | null, callback) => {
        if (value == null || value < 1 || value > 1440) {
          callback(new Error('学习时长须为 1~1440 分钟'))
        } else {
          callback()
        }
      },
    },
  ],
  study_date: [{ required: true, message: '请选择学习日期', trigger: 'change' }],
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
}

/** study_date 禁选未来日期（补记历史允许，spec 同后端校验口径）。 */
function disableFutureDate(d: Date): boolean {
  return todayLocalStr(d) > todayLocalStr()
}

/** 打开弹窗时回填表单（编辑回填原值 / 新建应用 preset + 默认值）。 */
function fillForm(): void {
  const r = props.editing
  if (r) {
    form.content = r.content
    form.duration_minutes = r.duration_minutes
    form.study_date = r.study_date
    form.knowledge_points = [...r.knowledge_points]
    form.course_id = r.course_id
    form.task_id = r.task_id
    form.task_title = ''
    form.mastery_level = r.mastery_level ?? 60
    skipSelf.value = r.mastery_level == null
    form.achievement = r.achievement ?? ''
    form.problems = r.problems ?? ''
  } else {
    const p = props.preset
    form.content = p?.content ?? ''
    form.duration_minutes = 30
    form.study_date = todayLocalStr()
    form.knowledge_points = p?.knowledge_points ? [...p.knowledge_points] : []
    form.course_id = p?.course_id ?? null
    form.task_id = p?.task_id ?? null
    form.task_title = p?.task_title ?? ''
    form.mastery_level = 60
    skipSelf.value = false
    form.achievement = ''
    form.problems = ''
  }
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

/** 构造新建入参（可空字段仅在非空时提交键）。 */
function buildCreatePayload(): RecordCreatePayload {
  const payload: RecordCreatePayload = {
    content: form.content.trim(),
    duration_minutes: form.duration_minutes,
    study_date: form.study_date,
  }
  payload.mastery_level = skipSelf.value ? null : form.mastery_level
  const kps = normalizeKnowledgePoints(form.knowledge_points)
  if (kps.length > 0) {
    payload.knowledge_points = kps
  }
  if (typeof form.course_id === 'number') payload.course_id = form.course_id
  if (typeof form.task_id === 'number') payload.task_id = form.task_id
  if (form.achievement.trim()) payload.achievement = form.achievement.trim()
  if (form.problems.trim()) payload.problems = form.problems.trim()
  return payload
}

/**
 * 构造编辑入参：仅提交实际变更字段（显式 null 生效——自评从有值改
 * 勾选跳过、任务/课程解除关联、成果/问题清空均提交 null）。
 */
function buildUpdatePayload(): RecordUpdatePayload {
  const r = props.editing
  if (!r) return {}
  const payload: RecordUpdatePayload = {}
  if (form.content.trim() !== r.content) payload.content = form.content.trim()
  if (form.duration_minutes !== r.duration_minutes) {
    payload.duration_minutes = form.duration_minutes
  }
  if (form.study_date !== r.study_date) payload.study_date = form.study_date

  const newMastery = skipSelf.value ? null : form.mastery_level
  if (newMastery !== r.mastery_level) payload.mastery_level = newMastery

  const kps = normalizeKnowledgePoints(form.knowledge_points)
  if (
    kps.length !== r.knowledge_points.length ||
    kps.some((k, i) => k !== r.knowledge_points[i])
  ) {
    payload.knowledge_points = kps
  }
  if (form.task_id !== r.task_id) payload.task_id = form.task_id
  if (form.course_id !== r.course_id) payload.course_id = form.course_id

  const achievement = form.achievement.trim() || null
  if (achievement !== r.achievement) payload.achievement = achievement
  const problems = form.problems.trim() || null
  if (problems !== r.problems) payload.problems = problems
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
    let saved: LearningRecord
    if (props.editing) {
      const payload = buildUpdatePayload()
      if (Object.keys(payload).length === 0) {
        ElMessage.info('没有修改的内容')
        return
      }
      saved = await updateRecord(props.editing.id, payload)
    } else {
      saved = await createRecord(buildCreatePayload())
    }
    ElMessage.success(props.editing ? '学习记录已更新' : '学习记录已保存')
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
      <el-form-item label="学习内容" prop="content">
        <el-input
          v-model="form.content"
          placeholder="如：精读 Transformer 论文第三章并整理笔记"
          maxlength="500"
          show-word-limit
          clearable
        />
      </el-form-item>
      <el-form-item label="学习日期" prop="study_date">
        <el-date-picker
          v-model="form.study_date"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择学习日期（可补记历史日期）"
          :disabled-date="disableFutureDate"
          clearable
        />
      </el-form-item>
      <el-form-item label="学习时长" prop="duration_minutes">
        <el-input-number
          v-model="form.duration_minutes"
          :min="1"
          :max="1440"
          :step="15"
          controls-position="right"
        />
        <span class="field-hint">分钟</span>
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
      <el-form-item label="所属课程" prop="course_id">
        <el-select v-model="form.course_id" placeholder="选择课程（可空）" clearable>
          <el-option v-for="c in courses" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="关联任务" prop="task_id">
        <el-input
          v-if="form.task_id != null"
          :model-value="taskDisplay"
          readonly
          clearable
          @clear="form.task_id = null"
        />
        <span v-else class="field-hint">未关联（可从任务页完成后跳转带入）</span>
      </el-form-item>
      <el-form-item label="自评掌握" prop="mastery_level">
        <div class="mastery-block">
          <el-slider
            v-model="form.mastery_level"
            :min="0"
            :max="100"
            :step="1"
            :marks="sliderMarks"
            :disabled="skipSelf"
          />
          <div class="mastery-segments">
            <span
              v-for="seg in MASTERY_SEGMENTS"
              :key="seg.label"
              class="seg"
              :class="{ active: currentSegment === seg.label }"
            >{{ seg.label }}</span>
          </div>
          <el-checkbox v-model="skipSelf">跳过自评（本次不参与掌握度计算）</el-checkbox>
        </div>
      </el-form-item>
      <el-form-item label="学习成果" prop="achievement">
        <el-input
          v-model="form.achievement"
          type="textarea"
          :rows="2"
          maxlength="2000"
          placeholder="本次学会了什么（可空）"
        />
      </el-form-item>
      <el-form-item label="遇到的问题" prop="problems">
        <el-input
          v-model="form.problems"
          type="textarea"
          :rows="2"
          maxlength="2000"
          placeholder="卡在哪里、待解决疑问（可空）"
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
  width: 180px;
}
.el-select {
  width: 100%;
}
.field-hint {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.mastery-block {
  width: 100%;
}
.mastery-segments {
  display: flex;
  gap: 24px;
  margin: 18px 8px 4px;
}
.mastery-segments .seg {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.mastery-segments .seg.active {
  font-weight: 600;
  color: var(--el-color-primary);
}
</style>
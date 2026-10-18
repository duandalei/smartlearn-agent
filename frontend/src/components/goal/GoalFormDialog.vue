<script setup lang="ts">
/**
 * 新建 / 编辑目标弹窗（P4，design 2.5.3）。
 *
 * - props.goal 为 null 时是新建模式（status 固定 active，不显示状态下拉）。
 * - goal_type 下拉选项为 5 枚举；编辑回显历史值（非枚举）时动态插入当前值。
 * - 日期校验：两者齐且 end < start 报「截止时间不能早于开始时间」
 *   （对应后端 1007 文案，前端先拦后端兜底）。
 * - 提交语义：编辑仅提交实际变更字段（空值不提交键，与后端「不支持
 *   null 清空」一致）；新建提交 GoalCreatePayload。
 */
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { createGoal, updateGoal } from '@/api/goal'
import type { Goal, GoalCreatePayload, GoalStatus, GoalTypeOption, GoalUpdatePayload } from '@/types'

const props = defineProps<{
  visible: boolean
  goal: Goal | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'saved', goal: Goal): void
}>()

/** 目标类型 5 枚举（对齐后端 GoalTypeStr）。 */
const BASE_GOAL_TYPES: GoalTypeOption[] = ['考研', '保研', '就业', '比赛', '技能提升']

/** 目标状态下拉选项（仅编辑模式显示）。 */
const STATUS_OPTIONS: { value: GoalStatus; label: string }[] = [
  { value: 'active', label: '进行中' },
  { value: 'completed', label: '已完成' },
  { value: 'archived', label: '已归档' },
]

const formRef = ref<FormInstance>()
const saving = ref(false)

/** 表单模型（可空字段统一用 '' / null 占位，提交时过滤）。 */
const form = reactive({
  title: '',
  goal_type: '',
  description: '',
  start_date: null as string | null,
  end_date: null as string | null,
  status: 'active' as GoalStatus,
})

/** 下拉选项：5 枚举 +（编辑且当前值为历史值时）动态插入当前值保证回显。 */
const goalTypeOptions = computed<(string | GoalTypeOption)[]>(() => {
  const current = props.goal?.goal_type
  if (current && !BASE_GOAL_TYPES.includes(current as GoalTypeOption)) {
    return [...BASE_GOAL_TYPES, current]
  }
  return [...BASE_GOAL_TYPES]
})

/** 弹窗标题。 */
const dialogTitle = computed(() => (props.goal ? '编辑目标' : '新建目标'))

/** 校验规则（与后端 schema 双保险）。 */
const rules: FormRules = {
  title: [
    { required: true, message: '请输入目标名称', trigger: 'blur' },
    { min: 1, max: 200, message: '目标名称长度为 1~200 个字符', trigger: 'blur' },
  ],
  end_date: [
    {
      trigger: 'change',
      validator: (_rule, _value, callback) => {
        if (form.end_date && form.start_date && form.end_date < form.start_date) {
          callback(new Error('截止时间不能早于开始时间'))
        } else {
          callback()
        }
      },
    },
  ],
}

/** 打开弹窗时回填表单（新建模式全部置空）。 */
function fillForm(): void {
  const g = props.goal
  form.title = g?.title ?? ''
  form.goal_type = g?.goal_type ?? ''
  form.description = g?.description ?? ''
  form.start_date = g?.start_date ?? null
  form.end_date = g?.end_date ?? null
  form.status = g?.status ?? 'active'
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

// 开始日期变化后对截止日期做联动重校（倒置提示即时消失 / 出现）。
watch(
  () => form.start_date,
  () => {
    if (form.end_date) {
      formRef.value?.validateField('end_date').catch(() => {})
    }
  },
)

/** 构造新建入参（空字段不提交键）。 */
function buildCreatePayload(): GoalCreatePayload {
  const payload: GoalCreatePayload = { title: form.title.trim() }
  if (form.goal_type) payload.goal_type = form.goal_type as GoalTypeOption
  if (form.description.trim()) payload.description = form.description.trim()
  if (form.start_date) payload.start_date = form.start_date
  if (form.end_date) payload.end_date = form.end_date
  return payload
}

/**
 * 构造编辑入参：仅提交实际变更字段。
 *
 * 清空类字段不提交键（后端不支持 null 清空，语义为「保持原值」）。
 */
function buildUpdatePayload(): GoalUpdatePayload {
  const g = props.goal
  if (!g) return {}
  const payload: GoalUpdatePayload = {}
  if (form.title.trim() !== g.title) payload.title = form.title.trim()
  if ((form.goal_type || null) !== g.goal_type && form.goal_type) {
    payload.goal_type = form.goal_type as GoalTypeOption
  }
  if ((form.description.trim() || null) !== g.description && form.description.trim()) {
    payload.description = form.description.trim()
  }
  if (form.start_date && form.start_date !== g.start_date) payload.start_date = form.start_date
  if (form.end_date && form.end_date !== g.end_date) payload.end_date = form.end_date
  if (form.status !== g.status) payload.status = form.status
  return payload
}

/** 提交表单（校验通过后按模式调对应接口）。 */
async function handleSubmit(): Promise<void> {
  const valid = await formRef.value?.validate().then(
    () => true,
    () => false,
  )
  if (!valid) return

  saving.value = true
  try {
    let saved: Goal
    if (props.goal) {
      const payload = buildUpdatePayload()
      if (Object.keys(payload).length === 0) {
        ElMessage.info('没有修改的内容')
        return
      }
      saved = await updateGoal(props.goal.id, payload)
    } else {
      saved = await createGoal(buildCreatePayload())
    }
    ElMessage.success(props.goal ? '目标已更新' : '目标已创建')
    emit('saved', saved)
    emit('update:visible', false)
  } catch {
    // 错误提示已由 request.ts 拦截器统一展示
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
    width="520px"
    :close-on-click-modal="false"
    @update:model-value="(v: boolean) => emit('update:visible', v)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
      <el-form-item label="目标名称" prop="title">
        <el-input
          v-model="form.title"
          placeholder="如：6个月掌握机器学习"
          maxlength="200"
          show-word-limit
          clearable
        />
      </el-form-item>
      <el-form-item label="目标类型" prop="goal_type">
        <el-select v-model="form.goal_type" placeholder="选择目标类型（可空）" clearable>
          <el-option v-for="o in goalTypeOptions" :key="o" :label="o" :value="o" />
        </el-select>
      </el-form-item>
      <el-form-item label="开始日期" prop="start_date">
        <el-date-picker
          v-model="form.start_date"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择开始日期（可空）"
          clearable
        />
      </el-form-item>
      <el-form-item label="截止日期" prop="end_date">
        <el-date-picker
          v-model="form.end_date"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择截止日期（可空）"
          clearable
        />
      </el-form-item>
      <el-form-item v-if="goal" label="状态" prop="status">
        <el-select v-model="form.status">
          <el-option v-for="o in STATUS_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="目标描述" prop="description">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="3"
          maxlength="1000"
          placeholder="补充目标的背景、预期成果等（可空）"
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
.el-date-editor {
  width: 100%;
}
</style>
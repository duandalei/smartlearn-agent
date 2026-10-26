<script setup lang="ts">
/**
 * 学习档案页面（P3 接入 GET/PUT /api/v1/profile）。
 *
 * - 进入页面拉取当前用户档案（后端对无档案用户惰性补建默认档案）。
 * - 保存采用「字段级部分更新」：仅提交发生变化的字段，未改动字段
 *   不出现在 PUT 请求体中（与后端 UserProfileUpdate 语义一致）。
 * - 学校 / 专业 / 年级 / 目标类型为可输入下拉（allow-create），
 *   兴趣方向为多选标签（可自定义），每日学习时长为 15-600 分钟滑块。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import PageHeader from '@/components/common/PageHeader.vue'
import { fetchProfile, updateProfile } from '@/api/profile'
import type { UserProfile, UserProfileUpdatePayload } from '@/types'

/** 页面加载中（首次拉取档案）。 */
const pageLoading = ref(false)
/** 保存中。 */
const saving = ref(false)
/** 后端返回的原始档案（用于差异比较）。 */
const profile = ref<UserProfile | null>(null)

/** 表单模型（null 统一归一为空字符串，便于输入组件绑定）。 */
const form = reactive({
  name: '',
  school: '',
  major: '',
  grade: '',
  current_goal_type: '',
  interest_directions: [] as string[],
  daily_study_minutes: 60,
})

/** 学校候选（可输入自定义值）。 */
const schoolOptions = ['中国矿业大学', '江苏师范大学', '徐州医科大学', '徐州工程学院']
/** 专业候选（可输入自定义值）。 */
const majorOptions = [
  '计算机科学与技术',
  '软件工程',
  '人工智能',
  '数据科学与大数据技术',
  '电子信息工程',
  '机械工程',
]
/** 年级候选（可输入自定义值）。 */
const gradeOptions = ['大一', '大二', '大三', '大四', '研一', '研二', '研三']
/** 目标类型候选（PROJECT_CONTEXT 6.2：考研/保研/就业/比赛，可自定义）。 */
const goalTypeOptions = ['考研', '保研', '就业', '比赛']
/** 兴趣方向候选（可输入自定义标签）。 */
const interestOptions = [
  '前端开发',
  '后端开发',
  '人工智能',
  '算法',
  '考研数学',
  '英语四六级',
]

/** 每日学习时长的友好展示（如「1 小时 30 分钟」）。 */
const dailyMinutesLabel = computed(() => {
  const m = form.daily_study_minutes
  const h = Math.floor(m / 60)
  const rest = m % 60
  if (h === 0) return `${rest} 分钟`
  if (rest === 0) return `${h} 小时`
  return `${h} 小时 ${rest} 分钟`
})

/**
 * 拉取当前用户档案并回填表单。
 */
async function loadProfile(): Promise<void> {
  pageLoading.value = true
  try {
    const p = await fetchProfile()
    profile.value = p
    form.name = p.name ?? ''
    form.school = p.school ?? ''
    form.major = p.major ?? ''
    form.grade = p.grade ?? ''
    form.current_goal_type = p.current_goal_type ?? ''
    form.interest_directions = [...p.interest_directions]
    form.daily_study_minutes = p.daily_study_minutes
  } catch {
    // 错误提示已由 request.ts 拦截器统一展示
  } finally {
    pageLoading.value = false
  }
}

/**
 * 构造部分更新请求体：仅包含与后端当前值不同的字段。
 *
 * null 与空字符串视为「未填写」，两者互不视为变更。
 */
function buildPayload(): UserProfileUpdatePayload {
  const payload: UserProfileUpdatePayload = {}
  const orig = profile.value
  if (!orig) return payload

  if (form.name !== (orig.name ?? '')) payload.name = form.name
  if (form.school !== (orig.school ?? '')) payload.school = form.school
  if (form.major !== (orig.major ?? '')) payload.major = form.major
  if (form.grade !== (orig.grade ?? '')) payload.grade = form.grade
  if (form.current_goal_type !== (orig.current_goal_type ?? '')) {
    payload.current_goal_type = form.current_goal_type
  }
  const origInterests = orig.interest_directions
  const interestsChanged =
    form.interest_directions.length !== origInterests.length ||
    form.interest_directions.some((x) => !origInterests.includes(x))
  if (interestsChanged) payload.interest_directions = [...form.interest_directions]
  if (form.daily_study_minutes !== orig.daily_study_minutes) {
    payload.daily_study_minutes = form.daily_study_minutes
  }
  return payload
}

/** 保存档案（无变更时提示并跳过请求）。 */
async function handleSave(): Promise<void> {
  const payload = buildPayload()
  if (Object.keys(payload).length === 0) {
    ElMessage.info('没有修改的内容')
    return
  }
  saving.value = true
  try {
    const p = await updateProfile(payload)
    profile.value = p
    form.name = p.name ?? ''
    form.school = p.school ?? ''
    form.major = p.major ?? ''
    form.grade = p.grade ?? ''
    form.current_goal_type = p.current_goal_type ?? ''
    form.interest_directions = [...p.interest_directions]
    form.daily_study_minutes = p.daily_study_minutes
    ElMessage.success('档案已保存')
  } catch {
    // 错误提示已由 request.ts 拦截器统一展示
  } finally {
    saving.value = false
  }
}

onMounted(loadProfile)
</script>

<template>
  <div class="page profile-view">
    <PageHeader
      folio="卷八 · 本人"
      title="学习档案"
      lead="这些信息用于个性化推荐和 AI 助手上下文；随时可以修改。"
    />

    <section v-loading="pageLoading" class="panel">
      <div class="panel__head">
        <div>
          <div class="panel__title">基本信息</div>
          <div class="panel__sub">只保存在本机，不会上传</div>
        </div>
        <span class="seal seal--sm seal--ghost" aria-hidden="true">人</span>
      </div>

      <div class="panel__body">
        <el-form :model="form" label-position="top" class="profile-form">
          <div class="form-section">
            <div class="form-section__title">身份</div>
            <el-row :gutter="24">
              <el-col :xs="24" :sm="12">
                <el-form-item label="姓名">
                  <el-input v-model="form.name" placeholder="请输入姓名" maxlength="50" clearable />
                </el-form-item>
              </el-col>
              <el-col :xs="24" :sm="12">
                <el-form-item label="学校">
                  <el-select
                    v-model="form.school"
                    placeholder="选择或输入学校"
                    filterable
                    allow-create
                    default-first-option
                    clearable
                  >
                    <el-option v-for="o in schoolOptions" :key="o" :label="o" :value="o" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="24">
              <el-col :xs="24" :sm="12">
                <el-form-item label="专业">
                  <el-select
                    v-model="form.major"
                    placeholder="选择或输入专业"
                    filterable
                    allow-create
                    default-first-option
                    clearable
                  >
                    <el-option v-for="o in majorOptions" :key="o" :label="o" :value="o" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :xs="24" :sm="12">
                <el-form-item label="年级">
                  <el-select
                    v-model="form.grade"
                    placeholder="选择或输入年级"
                    filterable
                    allow-create
                    default-first-option
                    clearable
                  >
                    <el-option v-for="o in gradeOptions" :key="o" :label="o" :value="o" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
          </div>

          <div class="form-section">
            <div class="form-section__title">学习方向</div>
            <el-row :gutter="24">
              <el-col :xs="24" :sm="12">
                <el-form-item label="当前目标类型">
                  <el-select
                    v-model="form.current_goal_type"
                    placeholder="选择或输入目标类型"
                    filterable
                    allow-create
                    default-first-option
                    clearable
                  >
                    <el-option v-for="o in goalTypeOptions" :key="o" :label="o" :value="o" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :xs="24" :sm="12">
                <el-form-item label="兴趣方向">
                  <el-select
                    v-model="form.interest_directions"
                    placeholder="选择或输入兴趣标签（可多选）"
                    multiple
                    filterable
                    allow-create
                    default-first-option
                    class="interest-select"
                  >
                    <el-option v-for="o in interestOptions" :key="o" :label="o" :value="o" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
          </div>

          <div class="form-section">
            <div class="form-section__title">每日节奏</div>
            <el-form-item label="每日学习时长">
              <div class="slider-row">
                <el-slider
                  v-model="form.daily_study_minutes"
                  :min="15"
                  :max="600"
                  :step="15"
                  show-input
                  :show-input-controls="false"
                />
              </div>
              <div class="slider-hint">
                当前：{{ dailyMinutesLabel }}（范围 15 - 600 分钟）
              </div>
            </el-form-item>
          </div>

          <div class="form-actions">
            <el-button type="primary" :loading="saving" @click="handleSave">保存档案</el-button>
            <span class="form-actions__hint">只提交发生变化的字段</span>
          </div>
        </el-form>
      </div>
    </section>
  </div>
</template>

<style scoped>
.profile-form {
  max-width: 820px;
}

.profile-form :deep(.el-select) {
  width: 100%;
}

.interest-select :deep(.el-select__wrapper) {
  flex-wrap: wrap;
}

.slider-row {
  width: 100%;
  padding: 0 8px;
}

.slider-hint {
  width: 100%;
  margin-top: 6px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-4);
}
</style>
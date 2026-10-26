<script setup lang="ts">
/**
 * 成长报告三 tab 编排（P13 批次 3；design 2.1.3-D / 2.4.5；spec §5.5 / §5.6）。
 *
 * 按需加载 + 会话内缓存（不复用 useDashboardBlock——reload 语义与「未加载
 * 才请求」缓存语义冲突，design 1.2.2）：
 * - 默认激活周报 tab，onMounted 仅加载 weekly（首屏仅 1 次请求，spec §4.1-2）；
 * - 切换 tab：loaded === false 才请求；已加载直接渲染缓存，零请求（规则 1b）；
 * - 翻页始终真实请求并覆盖当前页缓存（page_size 固定 10）；
 * - 列表失败 → 该 tab 空态（含生成入口），拦截器已弹错（spec §5.5.3-1）；
 * - 生成成功 → 该 tab 重置 page=1 重载列表（决策 D9：重载优于头部插入，
 *   新报告置顶由后端倒序保证）。
 *
 * 列表按后端 created_at 倒序直传渲染，前端不重排。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { fetchReports, generateReport } from '@/api/report'
import type { Report, ReportType } from '@/types/report'
import PageHeader from '@/components/common/PageHeader.vue'
import ReportCard from '@/components/report/ReportCard.vue'
import { REPORT_TYPE_LABELS } from '@/utils/report'

/** 单 tab 状态（design 2.1.3-D：items/total/page/pageSize/loaded/loading）。 */
interface TabState {
  items: Report[]
  total: number
  page: number
  pageSize: number
  loaded: boolean
  loading: boolean
}

const REPORT_TYPES: readonly ReportType[] = ['daily', 'weekly', 'monthly']

function emptyTabState(): TabState {
  return { items: [], total: 0, page: 1, pageSize: 10, loaded: false, loading: false }
}

/** 当前激活 tab（受控模式：:model-value + @tab-change，对齐 P5 惯例）。 */
const activeType = ref<ReportType>('weekly')

const tabState = reactive<Record<ReportType, TabState>>({
  daily: emptyTabState(),
  weekly: emptyTabState(),
  monthly: emptyTabState(),
})

const generatingReport = ref(false)

/**
 * 加载指定 tab 的列表页（spec §5.5.1 规则 1/2）。
 *
 * 失败时 items 清空、total=0、page=1、loaded=true——该 tab 显示空态（含生成
 * 入口），不永久骨架（spec §5.5.3-1）。
 */
async function loadTabList(type: ReportType, page: number): Promise<void> {
  const state = tabState[type]
  if (state.loading) return
  state.loading = true
  try {
    const res = await fetchReports({ report_type: type, page, page_size: state.pageSize })
    state.items = res.items
    state.total = res.total
    state.page = page
    state.loaded = true
  } catch {
    // 拦截器已弹错；该 tab 显示空态（含生成入口）
    state.items = []
    state.total = 0
    state.page = 1
    state.loaded = true
  } finally {
    state.loading = false
  }
}

/** 切换 tab：未加载才请求；已加载零请求渲染缓存（spec §5.5.1 规则 1b）。 */
function handleTabChange(name: string | number): void {
  const type = name as ReportType
  activeType.value = type
  if (!tabState[type].loaded) {
    void loadTabList(type, 1)
  }
}

/** 翻页：始终真实请求并覆盖当前页缓存（会话缓存只管「切回页 1」语义）。 */
function handlePageChange(page: number): void {
  void loadTabList(activeType.value, page)
}

/**
 * 生成报告（spec §5.6.1 规则 1）：请求体仅 {report_type}，不传统计区间参数，
 * 恒用后端缺省最近完整周期。成功后重载该 tab 第 1 页（新报告置顶）。
 */
async function handleGenerateReport(): Promise<void> {
  if (generatingReport.value) return
  generatingReport.value = true
  try {
    await generateReport({ report_type: activeType.value })
    ElMessage.success('报告生成成功')
    await loadTabList(activeType.value, 1)
  } catch {
    // 拦截器已弹错；列表维持原状（spec §5.6.3-1）
  } finally {
    generatingReport.value = false
  }
}

onMounted(() => {
  void loadTabList('weekly', 1)
})
</script>

<template>
  <div class="page reports-view">
    <PageHeader
      folio="卷七 · 回望"
      title="成长报告"
      lead="按天、周、月回看学习轨迹；报告会指出变化，而不只是罗列数字。"
    >
      <template #actions>
        <el-tooltip content="同一周期重复生成会追加新报告行" placement="bottom">
          <el-button
            type="primary"
            :loading="generatingReport"
            :disabled="tabState[activeType].loading"
            @click="handleGenerateReport"
          >
            生成当前周期报告
          </el-button>
        </el-tooltip>
      </template>
    </PageHeader>

    <el-tabs :model-value="activeType" @tab-change="handleTabChange">
      <el-tab-pane
        v-for="type in REPORT_TYPES"
        :key="type"
        :label="REPORT_TYPE_LABELS[type]"
        :name="type"
      >
        <!-- 首次加载骨架（loaded=false 且飞行中） -->
        <el-skeleton v-if="tabState[type].loading && !tabState[type].loaded" :rows="8" animated />

        <template v-else-if="tabState[type].loaded">
          <!-- 空态：无分页器，含生成入口（spec §5.5.1 规则 8） -->
          <div v-if="tabState[type].total === 0" class="empty-note report-empty">
            <span class="seal seal--ghost" aria-hidden="true">报</span>
            <div class="empty-note__title">还没有{{ REPORT_TYPE_LABELS[type] }}报告</div>
            <div>生成第一份，回看这一段时间的学习轨迹。</div>
            <div class="empty-note__actions">
              <el-button type="primary" :loading="generatingReport" @click="handleGenerateReport">
                生成报告
              </el-button>
            </div>
          </div>

          <template v-else>
            <div class="report-list">
              <ReportCard
                v-for="report in tabState[type].items"
                :key="report.id"
                :report="report"
              />
            </div>
            <el-pagination
              class="pager"
              :total="tabState[type].total"
              :current-page="tabState[type].page"
              :page-size="tabState[type].pageSize"
              layout="prev, pager, next, total"
              @current-change="handlePageChange"
            />
          </template>
        </template>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.report-list {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.report-empty {
  padding: 56px 24px;
}

.pager {
  display: flex;
  justify-content: flex-end;
  padding-top: 18px;
}
</style>
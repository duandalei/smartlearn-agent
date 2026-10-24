<script setup lang="ts">
/**
 * 报告卡片（P13；design 2.4.5 / D11；spec §5.5.1 规则 3/4/5/6/7、§5.6.1 规则 3、
 * §5.6.3-2/3）。
 *
 * 纯展示 + 内联纯前端导出（零请求，design 2.1.2 铁律 2 的明确豁免）：
 * ① 头部显著区间（类型 tag + 「period_start 至 period_end」大字 + 生成时间 +
 * 生成方式徽章）② 摘要引用块 ③ 七要素分区（有则显示、无则隐藏）④ 导出按钮。
 *
 * 零数据容错：content=null 仅渲染 ①（+② 若有），页面不报错、不渲染
 * 「undefined/null」字样（spec §5.5.1 规则 6）。
 */
import { ElMessage } from 'element-plus'

import type { Report } from '@/types/report'
import MarkdownText from '@/components/common/MarkdownText.vue'
import { formatMinutes } from '@/utils/record'
import {
  downloadReportMarkdown,
  formatCreatedAtLocal,
  generatedByLabel,
  REPORT_TYPE_LABELS,
} from '@/utils/report'

const props = defineProps<{
  report: Report
}>()

/** 生成方式徽章文案（null = 不渲染徽章，决策 D11）。 */
function badgeText(): string | null {
  return generatedByLabel(props.report.content?.generated_by)
}

/** 差值带符号显示（正负号语义保留，spec §6.7-6；0 显示 '0'）。 */
function signed(n: number): string {
  return n > 0 ? `+${n}` : `${n}`
}

/** 导出（纯前端 Blob 下载；浏览器拦截时兜底提示，spec §5.6.3-3）。 */
function handleExport(): void {
  try {
    downloadReportMarkdown(props.report)
  } catch {
    ElMessage.error('浏览器已拦截下载，请允许下载后重试')
  }
}
</script>

<template>
  <el-card class="report-card" shadow="never">
    <!-- ① 头部：区间必须在头部肉眼即见，禁止只在正文埋（spec §5.5.1 规则 3） -->
    <div class="card-head">
      <el-tag size="small" effect="plain">{{ REPORT_TYPE_LABELS[report.report_type] }}</el-tag>
      <span class="period">{{ report.period_start }} 至 {{ report.period_end }}</span>
      <el-tag v-if="badgeText()" size="small" type="warning">{{ badgeText() }}</el-tag>
      <span class="created-at">生成于 {{ formatCreatedAtLocal(report.created_at) }}</span>
    </div>

    <!-- ② 摘要引用块（空则省略） -->
    <blockquote v-if="report.summary" class="summary">
      <MarkdownText :content="report.summary" />
    </blockquote>

    <!-- ③ 七要素分区（有则显示、无则隐藏该分区；content=null 整块不渲染） -->
    <template v-if="report.content">
      <div v-if="typeof report.content.total_minutes === 'number'" class="section">
        <div class="section-title">学习时长</div>
        <div class="section-body">{{ formatMinutes(report.content.total_minutes) }}</div>
      </div>

      <div
        v-if="typeof report.content.task_completed === 'number'"
        class="section"
      >
        <div class="section-title">任务完成</div>
        <div class="section-body">
          完成 {{ report.content.task_completed }} 个任务<template v-if="typeof report.content.completion_rate === 'number'">，完成率 {{ report.content.completion_rate }}%</template>
        </div>
      </div>

      <div class="section">
        <div class="section-title">学习最多的方向</div>
        <div class="section-body">{{ report.content.top_direction ?? '本期暂无' }}</div>
      </div>

      <div class="section">
        <div class="section-title">薄弱知识点</div>
        <div class="section-body">
          <template v-if="report.content.weak_points && report.content.weak_points.length > 0">
            <el-tag
              v-for="wp in report.content.weak_points"
              :key="wp.knowledge_point"
              :type="wp.mastery_score < 40 ? 'danger' : 'warning'"
              class="wp-tag"
            >
              {{ wp.knowledge_point }} {{ wp.mastery_score }} 分
            </el-tag>
          </template>
          <span v-else class="empty-text">本期无明显薄弱知识点</span>
        </div>
      </div>

      <div v-if="report.content.progress" class="section">
        <div class="section-title">阶段进步（对比上一周期）</div>
        <div class="section-body progress-lines">
          <div>学习时长：{{ signed(report.content.progress.minutes_diff) }} 分钟</div>
          <div>完成任务：{{ signed(report.content.progress.task_completed_diff) }} 个</div>
          <div v-if="report.content.progress.avg_mastery_diff != null">
            平均掌握度：{{ signed(report.content.progress.avg_mastery_diff) }} 分
          </div>
        </div>
      </div>

      <div v-if="report.content.advice && report.content.advice.length > 0" class="section">
        <div class="section-title">建议</div>
        <ol class="advice-list">
          <li v-for="(text, i) in report.content.advice" :key="i">{{ text }}</li>
        </ol>
      </div>
    </template>

    <!-- ④ 操作区 -->
    <div class="actions">
      <el-button plain size="small" @click="handleExport">导出 Markdown</el-button>
    </div>
  </el-card>
</template>

<style scoped>
.report-card {
  margin-bottom: 12px;
}
.card-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.period {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.created-at {
  margin-left: auto;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.summary {
  margin: 12px 0 0;
  padding: 8px 12px;
  border-left: 3px solid var(--el-color-info);
  background: var(--el-fill-color-light);
  border-radius: 0 4px 4px 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}
.section {
  margin-top: 14px;
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.section-body {
  font-size: 14px;
  color: var(--el-text-color-primary);
  line-height: 1.7;
}
.wp-tag {
  margin-right: 8px;
}
.empty-text {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.progress-lines div {
  line-height: 1.8;
}
.advice-list {
  margin: 0;
  padding-left: 20px;
  font-size: 14px;
  line-height: 1.9;
  color: var(--el-text-color-primary);
}
.actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
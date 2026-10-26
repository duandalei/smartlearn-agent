<script setup lang="ts">
/**
 * 成长报告卡片：像一页装订好的报告纸，而不是通用数据卡。
 * 头部区间显著，正文分栏排布，导出保持纯前端。
 */
import { computed } from 'vue'
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

const TYPE_CHAR: Record<Report['report_type'], string> = {
  daily: '日',
  weekly: '周',
  monthly: '月',
}

const typeChar = computed(() => TYPE_CHAR[props.report.report_type])

/** 过滤掉没有名称的薄弱点，避免渲染出空标签。 */
const weakPoints = computed(() =>
  (props.report.content?.weak_points ?? []).filter(
    (wp) => (wp.knowledge_point ?? '').trim().length > 0,
  ),
)

function scoreText(score: unknown): string {
  return typeof score === 'number' ? `${score} 分` : '未评分'
}

function badgeText(): string | null {
  return generatedByLabel(props.report.content?.generated_by)
}

function signed(n: number): string {
  return n > 0 ? `+${n}` : `${n}`
}

function deltaClass(n: number): string {
  if (n > 0) return 'is-up'
  if (n < 0) return 'is-down'
  return ''
}

function handleExport(): void {
  try {
    downloadReportMarkdown(props.report)
  } catch {
    ElMessage.error('浏览器已拦截下载，请允许下载后重试')
  }
}
</script>

<template>
  <article class="report-paper">
    <header class="report-head">
      <div class="report-head__main">
        <div class="report-kicker">
          <span class="report-type">{{ REPORT_TYPE_LABELS[report.report_type] }}</span>
          <span class="report-period">
            {{ report.period_start }} — {{ report.period_end }}
          </span>
        </div>
        <div class="report-sub">
          <span class="report-created">生成于 {{ formatCreatedAtLocal(report.created_at) }}</span>
          <el-tag v-if="badgeText()" size="small" type="warning" effect="plain">
            {{ badgeText() }}
          </el-tag>
        </div>
      </div>
      <span class="seal seal--ghost report-seal" aria-hidden="true">{{ typeChar }}</span>
    </header>

    <blockquote v-if="report.summary" class="report-summary">
      <span class="report-summary__label">摘要</span>
      <div class="report-summary__body">
        <MarkdownText :content="report.summary" />
      </div>
    </blockquote>

    <template v-if="report.content">
      <div class="report-grid">
        <section v-if="typeof report.content.total_minutes === 'number'" class="report-section">
          <div class="report-label">学习时长</div>
          <div class="report-value report-value--number">
            {{ formatMinutes(report.content.total_minutes) }}
          </div>
        </section>

        <section v-if="typeof report.content.task_completed === 'number'" class="report-section">
          <div class="report-label">任务完成</div>
          <div class="report-value">
            完成 {{ report.content.task_completed }} 个任务<template
              v-if="typeof report.content.completion_rate === 'number'"
            >，完成率 {{ report.content.completion_rate }}%</template>
          </div>
        </section>

        <section class="report-section">
          <div class="report-label">学习最多的方向</div>
          <div class="report-value">{{ report.content.top_direction ?? '本期暂无' }}</div>
        </section>

        <section class="report-section">
          <div class="report-label">薄弱知识点</div>
          <div class="report-value">
            <template v-if="weakPoints.length > 0">
              <el-tag
                v-for="wp in weakPoints"
                :key="wp.knowledge_point"
                :type="typeof wp.mastery_score === 'number' && wp.mastery_score < 40 ? 'danger' : 'warning'"
                effect="plain"
                class="wp-tag"
              >
                {{ wp.knowledge_point }} {{ scoreText(wp.mastery_score) }}
              </el-tag>
            </template>
            <span v-else class="muted">本期无明显薄弱知识点</span>
          </div>
        </section>

        <section v-if="report.content.progress" class="report-section report-section--wide">
          <div class="report-label">阶段进步（对比上一周期）</div>
          <div class="progress-grid">
            <div class="progress-row">
              <span class="progress-name">学习时长</span>
              <span class="progress-delta" :class="deltaClass(report.content.progress.minutes_diff)">
                {{ signed(report.content.progress.minutes_diff) }} 分钟
              </span>
            </div>
            <div class="progress-row">
              <span class="progress-name">完成任务</span>
              <span
                class="progress-delta"
                :class="deltaClass(report.content.progress.task_completed_diff)"
              >
                {{ signed(report.content.progress.task_completed_diff) }} 个
              </span>
            </div>
            <div v-if="report.content.progress.avg_mastery_diff != null" class="progress-row">
              <span class="progress-name">平均掌握度</span>
              <span
                class="progress-delta"
                :class="deltaClass(report.content.progress.avg_mastery_diff)"
              >
                {{ signed(report.content.progress.avg_mastery_diff) }} 分
              </span>
            </div>
          </div>
        </section>

        <section
          v-if="report.content.advice && report.content.advice.length > 0"
          class="report-section report-section--wide"
        >
          <div class="report-label">建议</div>
          <ol class="advice-list">
            <li v-for="(text, i) in report.content.advice" :key="i">{{ text }}</li>
          </ol>
        </section>
      </div>
    </template>

    <footer class="report-foot">
      <span class="report-foot__note">报告由学习记录与掌握度汇总生成</span>
      <el-button plain size="small" @click="handleExport">导出 Markdown</el-button>
    </footer>
  </article>
</template>

<style scoped>
.report-paper {
  padding: 22px 24px 14px;
  background: var(--paper-2);
  border: 1px solid var(--line);
  border-radius: var(--radius);
}

/* Head ------------------------------------------------------------------- */
.report-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--line);
}

.report-head__main {
  min-width: 0;
}

.report-kicker {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}

.report-type {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.12em;
  color: var(--vermilion);
}

.report-period {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--ink);
}

.report-sub {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 6px;
}

.report-created {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-4);
}

.report-seal {
  width: 30px;
  height: 30px;
  font-size: 15px;
}

/* Summary ---------------------------------------------------------------- */
.report-summary {
  display: flex;
  gap: 14px;
  margin: 16px 0 0;
  padding: 14px 16px;
  background: var(--paper-3);
  border: 1px solid var(--line);
  border-radius: var(--radius);
}

.report-summary__label {
  flex: 0 0 auto;
  padding-top: 2px;
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.1em;
  color: var(--vermilion);
}

.report-summary__body {
  min-width: 0;
  font-family: var(--font-display);
  font-size: 14px;
  line-height: 1.8;
  color: var(--ink-2);
}

/* Sections --------------------------------------------------------------- */
.report-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px 28px;
  padding-top: 18px;
}

.report-section {
  min-width: 0;
}

.report-section--wide {
  grid-column: 1 / -1;
}

.report-label {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.12em;
  color: var(--ink-4);
}

.report-value {
  margin-top: 5px;
  font-size: 14px;
  line-height: 1.7;
  color: var(--ink-2);
}

.report-value--number {
  font-family: var(--font-display);
  font-variant-numeric: lining-nums tabular-nums;
  font-size: 20px;
  font-weight: 600;
  color: var(--ink);
}

.wp-tag {
  margin: 0 6px 4px 0;
}

.progress-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 8px;
}

.progress-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  background: var(--paper-3);
  border: 1px solid var(--line-soft);
  border-radius: var(--radius);
}

.progress-name {
  font-size: 11px;
  color: var(--ink-3);
}

.progress-delta {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-2);
  white-space: nowrap;
}

.progress-delta.is-up {
  color: var(--jade);
}

.progress-delta.is-down {
  color: var(--vermilion);
}

.advice-list {
  margin: 8px 0 0;
  padding: 0;
  list-style: none;
  counter-reset: advice;
}

.advice-list li {
  counter-increment: advice;
  position: relative;
  padding: 7px 0 7px 28px;
  border-bottom: 1px solid var(--line-soft);
  font-size: 13px;
  line-height: 1.75;
  color: var(--ink-2);
}

.advice-list li:last-child {
  border-bottom: none;
}

.advice-list li::before {
  content: counter(advice, decimal-leading-zero);
  position: absolute;
  left: 0;
  top: 7px;
  font-family: var(--font-display);
  font-size: 12px;
  font-weight: 600;
  color: var(--vermilion);
}

/* Foot ------------------------------------------------------------------- */
.report-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}

.report-foot__note {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--ink-4);
}

@media (max-width: 720px) {
  .report-paper {
    padding: 18px 16px 12px;
  }

  .report-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 16px;
  }

  .progress-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .report-period {
    font-size: 18px;
  }
}
</style>

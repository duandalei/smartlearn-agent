<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import PageHeader from '@/components/common/PageHeader.vue'
import AdviceCard from '@/components/dashboard/AdviceCard.vue'
import MasteryChart from '@/components/dashboard/MasteryChart.vue'
import MetricCards from '@/components/dashboard/MetricCards.vue'
import RiskAlertCard from '@/components/dashboard/RiskAlertCard.vue'
import TrendChart from '@/components/dashboard/TrendChart.vue'
import WeaknessList from '@/components/dashboard/WeaknessList.vue'
import {
  fetchDashboardAdvice,
  fetchDashboardMastery,
  fetchDashboardOverview,
  fetchDashboardTrend,
  fetchDashboardWeakness,
} from '@/api/dashboard'
import { useDashboardBlock } from '@/composables/useDashboardBlock'

const router = useRouter()
const trendDays = ref(30)

const {
  data: overviewData,
  loading: overviewLoading,
  error: overviewError,
  reload: reloadOverview,
} = useDashboardBlock(fetchDashboardOverview)

const {
  data: trendData,
  loading: trendLoading,
  error: trendError,
  reload: reloadTrend,
} = useDashboardBlock(() => fetchDashboardTrend(trendDays.value))

const {
  data: masteryData,
  loading: masteryLoading,
  error: masteryError,
  reload: reloadMastery,
} = useDashboardBlock(fetchDashboardMastery)

const {
  data: weaknessData,
  loading: weaknessLoading,
  error: weaknessError,
  reload: reloadWeakness,
} = useDashboardBlock(fetchDashboardWeakness)

const {
  data: adviceData,
  loading: adviceLoading,
  error: adviceError,
  reload: reloadAdvice,
} = useDashboardBlock(fetchDashboardAdvice)

function handleTrendDaysChange(days: number): void {
  trendDays.value = days
  void reloadTrend()
}
</script>

<template>
  <div class="page dashboard-view">
    <PageHeader
      folio="卷一 · 今日"
      title="学习中心"
      lead="今天的学习状态、近期趋势，以及最值得先做的一件事。"
    >
      <template #actions>
        <el-button @click="router.push('/learning-records')">记录学习</el-button>
        <el-button type="primary" @click="router.push('/ai-agent')">问 AI 助手</el-button>
      </template>
    </PageHeader>

    <MetricCards
      :data="overviewData"
      :loading="overviewLoading"
      :error="overviewError"
      :reload="reloadOverview"
    />

    <div class="dash-grid">
      <TrendChart
        :data="trendData"
        :loading="trendLoading"
        :error="trendError"
        :reload="reloadTrend"
        :days="trendDays"
        :on-days-change="handleTrendDaysChange"
      />
      <AdviceCard
        :data="adviceData"
        :loading="adviceLoading"
        :error="adviceError"
        :reload="reloadAdvice"
      />
    </div>

    <div class="dash-grid">
      <section class="panel mastery-panel">
        <div class="panel__head">
          <div>
            <div class="panel__title">知识掌握</div>
            <div class="panel__sub">按知识点平均掌握度，虚线为 60 分参照</div>
          </div>
          <span class="seal seal--sm seal--ghost" aria-hidden="true">学</span>
        </div>
        <div class="panel__body">
          <MasteryChart
            :data="masteryData"
            :loading="masteryLoading"
            :error="masteryError"
            :reload="reloadMastery"
          />

          <div class="mastery-rule" aria-hidden="true" />

          <div class="section-head">
            <div class="section-title">薄弱知识点</div>
            <span class="section-note">近 30 天 · Top 5</span>
          </div>

          <WeaknessList
            :data="weaknessData"
            :loading="weaknessLoading"
            :error="weaknessError"
            :reload="reloadWeakness"
          />
        </div>
      </section>

      <RiskAlertCard
        :alert="trendData?.risk_alert ?? null"
        :loading="trendLoading"
        :error="trendError"
        :reload="reloadTrend"
      />
    </div>
  </div>
</template>

<style scoped>
.dash-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.85fr) minmax(300px, 1fr);
  gap: 20px;
  align-items: stretch;
}

.mastery-panel {
  min-width: 0;
}

.mastery-rule {
  height: 1px;
  margin: 22px 0 18px;
  background: var(--line);
}

@media (max-width: 1100px) {
  .dash-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>

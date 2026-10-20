<script setup lang="ts">
import { ref } from 'vue'

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
  <div class="dashboard-view">
    <MetricCards
      :data="overviewData"
      :loading="overviewLoading"
      :error="overviewError"
      :reload="reloadOverview"
    />

    <el-row :gutter="16" class="dashboard-row">
      <el-col :xs="24" :lg="16">
        <TrendChart
          :data="trendData"
          :loading="trendLoading"
          :error="trendError"
          :reload="reloadTrend"
          :days="trendDays"
          :on-days-change="handleTrendDaysChange"
        />
      </el-col>
      <el-col :xs="24" :lg="8">
        <AdviceCard
          :data="adviceData"
          :loading="adviceLoading"
          :error="adviceError"
          :reload="reloadAdvice"
        />
      </el-col>
    </el-row>

    <el-row :gutter="16" class="dashboard-row">
      <el-col :xs="24" :lg="16">
        <el-card shadow="never">
          <template #header>
            <span class="card-title">知识掌握情况</span>
          </template>
          <MasteryChart
            :data="masteryData"
            :loading="masteryLoading"
            :error="masteryError"
            :reload="reloadMastery"
          />
          <el-divider class="mastery-divider" />
          <div class="weakness-title">薄弱知识点 Top5</div>
          <WeaknessList
            :data="weaknessData"
            :loading="weaknessLoading"
            :error="weaknessError"
            :reload="reloadWeakness"
          />
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="8">
        <RiskAlertCard
          :alert="trendData?.risk_alert ?? null"
          :loading="trendLoading"
          :error="trendError"
          :reload="reloadTrend"
        />
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.dashboard-row {
  margin-top: 16px;
}
.card-title {
  font-size: 15px;
  font-weight: 600;
}
.mastery-divider {
  margin: 16px 0 8px;
}
.weakness-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  margin-bottom: 4px;
}
</style>
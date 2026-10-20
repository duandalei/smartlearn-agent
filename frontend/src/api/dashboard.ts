import request from '@/api/request'
import type {
  AdviceData,
  MasteryData,
  OverviewData,
  TrendData,
  WeaknessData,
} from '@/types'

export function fetchDashboardOverview(): Promise<OverviewData> {
  return request.get('/dashboard/overview') as unknown as Promise<OverviewData>
}

export function fetchDashboardTrend(days = 30): Promise<TrendData> {
  return request.get('/dashboard/trend', {
    params: { days },
  }) as unknown as Promise<TrendData>
}

export function fetchDashboardMastery(): Promise<MasteryData> {
  return request.get('/dashboard/mastery') as unknown as Promise<MasteryData>
}

export function fetchDashboardWeakness(): Promise<WeaknessData> {
  return request.get('/dashboard/weakness') as unknown as Promise<WeaknessData>
}

export function fetchDashboardAdvice(): Promise<AdviceData> {
  return request.get('/dashboard/advice') as unknown as Promise<AdviceData>
}
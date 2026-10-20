import { onMounted, ref, type Ref } from 'vue'

export interface DashboardBlock<T> {
  data: Ref<T | null>
  loading: Ref<boolean>
  error: Ref<boolean>
  reload: () => Promise<void>
}

export function useDashboardBlock<T>(fetcher: () => Promise<T>): DashboardBlock<T> {
  const data = ref<T | null>(null) as Ref<T | null>
  const loading = ref(false)
  const error = ref(false)

  async function reload(): Promise<void> {
    loading.value = true
    error.value = false
    try {
      data.value = await fetcher()
    } catch {
      error.value = true
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    void reload()
  })

  return { data, loading, error, reload }
}
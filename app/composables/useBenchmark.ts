import { computed, ref } from 'vue'
import type { BenchmarkCase, BenchmarkCaseDetail } from '@/api/contracts'
import type { SimfeaClient } from '@/api/simfeaClient'

export type SortKey = 'method' | 'u_L_mm' | 'sigma' | 'error' | 'notes'

export const METHOD_CATEGORIES: Record<string, { label: string; color: string }> = {
  analytic: { label: '解析解', color: '#2ecc71' },
  calculix: { label: 'CalculiX', color: '#f5a623' },
  ansys: { label: 'ANSYS', color: '#f04449' },
  abaqus: { label: 'Abaqus', color: '#48c8fa' },
  pinn: { label: 'PINN', color: '#9575f6' },
}

export function methodCategory(method: string) {
  const key = method.toLowerCase()
  if (key === 'analytic') return METHOD_CATEGORIES.analytic
  if (key === 'pinn' || key.includes('neural')) return METHOD_CATEGORIES.pinn
  if (key === 'ansys' || key === 'abaqus' || key === 'calculix')
    return METHOD_CATEGORIES[key] ?? { label: '传统 FEM', color: '#48c8fa' }
  return { label: method, color: '#8f99ab' }
}

export function parseError(value: string): number {
  const n = Number(value)
  return Number.isNaN(n) ? Infinity : Math.abs(n)
}

export function errorClass(value: string): string {
  const e = parseError(value)
  if (e === 0) return 'exact'
  if (e < 1e-4) return 'tiny'
  if (e < 0.01) return 'good'
  if (e < 1.0) return 'mid'
  return 'large'
}

export function errorLabel(value: string): string {
  const e = parseError(value)
  if (e === 0) return '精确'
  if (e < 1e-8) return '≈0'
  if (e < 1e-4) return e.toExponential(1)
  if (e < 0.01) return `${(e * 100).toFixed(2)}%`
  if (e < 1.0) return `${(e * 100).toFixed(1)}%`
  return `${e.toFixed(1)}×`
}

export function errorBarWidth(value: string): string {
  const e = parseError(value)
  if (e === 0) return '0%'
  if (e >= 100) return '100%'
  return `${Math.min(100, Math.max(2, 15 + Math.log10(e) * 12))}%`
}

export function formatNum(value: string, precision = 6): string {
  const n = Number(value)
  if (Number.isNaN(n)) return '—'
  return n.toPrecision(precision)
}

export function useBenchmark(api: SimfeaClient) {
  const cases = ref<BenchmarkCase[]>([])
  const selectedName = ref<string | null>(null)
  const detail = ref<BenchmarkCaseDetail | null>(null)
  const loading = ref(false)
  const sortKey = ref<SortKey>('error')
  const sortDir = ref<'asc' | 'desc'>('asc')

  const caseGroups = computed(() => {
    const order = ['基础案例', '扩展案例']
    const groups: Record<string, BenchmarkCase[]> = {}
    for (const c of cases.value) {
      const g = c.group || '基础案例'
      if (!groups[g]) groups[g] = []
      groups[g].push(c)
    }
    return order.filter((g) => groups[g]?.length).map((label) => ({ label, cases: groups[label] }))
  })

  const sortedResults = computed(() => {
    if (!detail.value) return []
    const arr = [...detail.value.results]
    arr.sort((a, b) => {
      const aVal =
        sortKey.value === 'method'
          ? a.method
          : sortKey.value === 'u_L_mm'
            ? Number(a.u_L_mm) || 0
            : sortKey.value === 'sigma'
              ? Number(a.sigma_MPa || a.sigma_max_MPa) || 0
              : sortKey.value === 'error'
                ? parseError(a.error_u_L_mm)
                : a.notes || ''
      const bVal =
        sortKey.value === 'method'
          ? b.method
          : sortKey.value === 'u_L_mm'
            ? Number(b.u_L_mm) || 0
            : sortKey.value === 'sigma'
              ? Number(b.sigma_MPa || b.sigma_max_MPa) || 0
              : sortKey.value === 'error'
                ? parseError(b.error_u_L_mm)
                : b.notes || ''
      if (typeof aVal === 'number' && typeof bVal === 'number')
        return sortDir.value === 'asc' ? aVal - bVal : bVal - aVal
      const cmp = String(aVal).localeCompare(String(bVal))
      return sortDir.value === 'asc' ? cmp : -cmp
    })
    return arr
  })

  const stats = computed(() => {
    if (!detail.value) return null
    const results = detail.value.results
    const analytic = results.find((r) => r.method.toLowerCase() === 'analytic')
    const errors = results
      .filter((r) => r.method.toLowerCase() !== 'analytic')
      .map((r) => parseError(r.error_u_L_mm))
    return {
      total: results.length,
      hasAnalytic: !!analytic,
      analyticDisplacement: analytic?.u_L_mm || null,
      analyticStress: analytic?.sigma_MPa || analytic?.sigma_max_MPa || null,
      bestError: errors.length ? Math.min(...errors) : null,
      bestMethod: errors.length
        ? results
            .filter((r) => r.method.toLowerCase() !== 'analytic')
            .sort((a, b) => parseError(a.error_u_L_mm) - parseError(b.error_u_L_mm))[0]?.method
        : null,
    }
  })

  async function fetchCases() {
    try {
      const res = await api.listBenchmarks()
      cases.value = res.data.cases
    } catch {
      /* handled by API client */
    }
  }

  async function selectCase(name: string) {
    selectedName.value = name
    loading.value = true
    try {
      const res = await api.getBenchmarkCase(name)
      detail.value = res.data
    } catch {
      /* */
    }
    loading.value = false
  }

  return {
    cases,
    selectedName,
    detail,
    loading,
    sortKey,
    sortDir,
    caseGroups,
    sortedResults,
    stats,
    fetchCases,
    selectCase,
  }
}

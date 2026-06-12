import { computed } from 'vue'
import type { BenchmarkCase } from '@/api/contracts'
import type { SimfeaClient } from '@/api/simfeaClient'
import { useBenchmark } from './useBenchmark'

export interface LadderLevelCase {
  name: string
  title: string
  subtitle: string
  group: string
  complete: boolean
  hasProblem: boolean
  hasResults: boolean
}

export interface LadderLevel {
  level: number
  label: string
  body: string
  cases: LadderLevelCase[]
  totalCases: number
  completeCases: number
}

export interface EvidenceFlags {
  runProof: boolean
  failureRecord: boolean
  systemDiagram: boolean | null
  singlePathCall: boolean | null
  minClosedLoop: boolean
  diffComparison: boolean | null
}

export interface CaseEvidence {
  caseName: string
  title: string
  group: string
  evidence: EvidenceFlags
  loaded: boolean
}

export interface MethodLabStats {
  totalCases: number
  casesWithResults: number
  casesWithProblems: number
  completionPercent: number
  casesByGroup: { label: string; count: number }[]
}

export interface RoadmapCase {
  name: string
  title: string
  group: string
  complete: boolean
  hasProblem: boolean
  hasResults: boolean
  methodCount: number | null
  nextStep: string
}

const CAE_LADDER_DEFS = [
  {
    level: 1,
    label: '结果可观察型',
    body: '运行一个最小真实算例，观察输入、日志、结果文件和可视化。适合从 CalculiX 杆单元、悬臂梁、平面桁架这类小算例开始。',
  },
  {
    level: 2,
    label: '机制重建型',
    body: '用 Python / NumPy 重建一个最小 FEM 机制，例如节点、单元、材料、组装 K、施加边界条件并求解 Ku=f。',
  },
  {
    level: 3,
    label: '真实工具链型',
    body: '追踪 FreeCAD FEM、CalculiX、VTK / ParaView 等真实工具链中的一条路径，而不是一次性阅读全系统。',
  },
] as const

function classifyCase(c: BenchmarkCase): { l1: boolean; l2: boolean; l3: boolean } {
  const name = c.name.toLowerCase()
  const title = (c.title || '').toLowerCase()
  const searchText = `${name} ${title}`

  const l1 = c.has_results
  const l2 =
    c.group === '扩展案例' ||
    searchText.includes('python') ||
    searchText.includes('py') ||
    searchText.includes('重建')
  const l3 =
    searchText.includes('freecad') ||
    searchText.includes('calculix') ||
    searchText.includes('vtk') ||
    searchText.includes('paraview') ||
    searchText.includes('工具链') ||
    searchText.includes('workflow') ||
    searchText.includes('full')

  return { l1, l2, l3 }
}

function toLadderCase(c: BenchmarkCase): LadderLevelCase {
  return {
    name: c.name,
    title: c.title || c.name,
    subtitle: c.subtitle || '',
    group: c.group || '基础案例',
    complete: c.has_problem && c.has_results,
    hasProblem: c.has_problem,
    hasResults: c.has_results,
  }
}

export function useMethodLab(api: SimfeaClient) {
  const bench = useBenchmark(api)

  const ladderLevels = computed<LadderLevel[]>(() => {
    return CAE_LADDER_DEFS.map((def) => {
      const cases = bench.cases.value
        .filter((c) => {
          const cls = classifyCase(c)
          if (def.level === 1) return cls.l1
          if (def.level === 2) return cls.l2
          return cls.l3
        })
        .map(toLadderCase)

      return {
        ...def,
        cases,
        totalCases: cases.length,
        completeCases: cases.filter((c) => c.complete).length,
      }
    })
  })

  const caseEvidence = computed<CaseEvidence[]>(() => {
    return bench.cases.value.map((c) => ({
      caseName: c.name,
      title: c.title || c.name,
      group: c.group || '基础案例',
      evidence: {
        runProof: c.has_results,
        failureRecord: c.has_problem,
        systemDiagram: null,
        singlePathCall: null,
        minClosedLoop: c.has_problem && c.has_results,
        diffComparison: null,
      },
      loaded: false,
    }))
  })

  const methodLabStats = computed<MethodLabStats>(() => {
    const cases = bench.cases.value
    const total = cases.length
    const withResults = cases.filter((c) => c.has_results).length
    const withProblems = cases.filter((c) => c.has_problem).length
    const complete = cases.filter((c) => c.has_problem && c.has_results).length

    const groupMap: Record<string, number> = {}
    for (const c of cases) {
      const g = c.group || '基础案例'
      groupMap[g] = (groupMap[g] || 0) + 1
    }
    const order = ['基础案例', '扩展案例']
    const casesByGroup = order.filter((g) => groupMap[g]).map((label) => ({ label, count: groupMap[label] }))

    return {
      totalCases: total,
      casesWithResults: withResults,
      casesWithProblems: withProblems,
      completionPercent: total > 0 ? Math.round((complete / total) * 100) : 0,
      casesByGroup,
    }
  })

  const roadmapCases = computed<RoadmapCase[]>(() => {
    const order = ['基础案例', '扩展案例']
    const sorted = [...bench.cases.value].sort((a, b) => {
      const ga = order.indexOf(a.group || '基础案例')
      const gb = order.indexOf(b.group || '基础案例')
      if (ga !== gb) return ga - gb
      return a.name.localeCompare(b.name)
    })

    return sorted.map((c) => {
      const hasProblem = c.has_problem
      const hasResults = c.has_results
      let nextStep: string
      if (!hasProblem && !hasResults) nextStep = '需要问题描述和求解结果'
      else if (!hasProblem) nextStep = '需要问题描述'
      else if (!hasResults) nextStep = '需要求解验证'
      else nextStep = '已完备，可对比分析'

      return {
        name: c.name,
        title: c.title || c.name,
        group: c.group || '基础案例',
        complete: hasProblem && hasResults,
        hasProblem,
        hasResults,
        methodCount: null,
        nextStep,
      }
    })
  })

  return {
    // from useBenchmark
    cases: bench.cases,
    caseGroups: bench.caseGroups,
    loading: bench.loading,
    detail: bench.detail,
    fetchCases: bench.fetchCases,
    selectCase: bench.selectCase,
    // method-lab specific
    ladderLevels,
    caseEvidence,
    methodLabStats,
    roadmapCases,
  }
}

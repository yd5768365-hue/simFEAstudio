<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { BenchmarkCase, BenchmarkCaseDetail } from '@/api/contracts'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps<{
  apiBaseUrl: string
}>()

const emit = defineEmits<{
  back: []
}>()

const cases = ref<BenchmarkCase[]>([])
const selectedName = ref<string | null>(null)
const detail = ref<BenchmarkCaseDetail | null>(null)
const loading = ref(false)

function formatError(value: string): string {
  if (!value || value === '0' || value === '0.0') return '0'
  const n = Number(value)
  if (Number.isNaN(n)) return value
  if (n === 0) return '0'
  if (n < 1e-4 && n > -1e-4) return n.toExponential(2)
  return n.toPrecision(3)
}

async function fetchCases() {
  const res = await fetch(`${props.apiBaseUrl}/v1/benchmarks`)
  const json = await res.json()
  cases.value = json.data.cases
}

async function selectCase(name: string) {
  selectedName.value = name
  loading.value = true
  try {
    const res = await fetch(`${props.apiBaseUrl}/v1/benchmarks/${encodeURIComponent(name)}`)
    const json = await res.json()
    detail.value = json.data
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchCases()
})
</script>

<template>
  <div class="view-container workbench-view">
    <header class="workbench-topbar">
      <div class="workbench-titlebar">
        <div class="app-mark" aria-hidden="true">BL</div>
        <span>Benchmark Lab</span>
        <span class="topbar-status online">{{ cases.length }} 个案例</span>
      </div>
      <div class="workbench-commandbar" aria-label="工具栏">
        <button type="button" @click="emit('back')">← 返回作业区</button>
      </div>
    </header>

    <section class="workbench-layout" aria-label="Benchmark 布局">
      <section class="schematic-pane" aria-label="案例列表">
        <div class="pane-title">验证案例</div>
        <div class="schematic-canvas">
          <div v-if="cases.length === 0" class="empty-state">
            暂无 benchmark 案例。<br />在 <code>learning/benchmarks/</code> 目录中添加案例后刷新。
          </div>
          <div v-else class="model-tree">
            <button
              v-for="c in cases"
              :key="c.name"
              type="button"
              class="tree-node neutral"
              :class="{ selected: selectedName === c.name }"
              @click="selectCase(c.name)"
            >
              <span class="tree-icon" :class="{ ready: c.has_results, neutral: !c.has_results }"></span>
              <div class="tree-body">
                <div class="tree-head">
                  <strong>{{ c.name }}</strong>
                  <span v-if="c.has_problem" class="tree-badge">md</span>
                  <span v-if="c.has_results" class="tree-badge" style="background: rgba(38,162,105,0.15); color: #26a269">csv</span>
                </div>
                <small>{{ c.has_problem ? '问题描述 + ' : '' }}{{ c.has_results ? '对比结果' : '无结果数据' }}</small>
              </div>
              <span class="tree-arrow">›</span>
            </button>
          </div>
        </div>
      </section>

      <aside class="properties-pane" aria-label="案例详情">
        <div class="pane-title">案例详情</div>
        <div v-if="!detail && !loading" class="empty-state" style="padding: 48px 16px; text-align: center">
          ← 从左侧选择一个案例
        </div>
        <div v-else-if="loading" class="empty-state" style="padding: 48px 16px; text-align: center">加载中…</div>
        <div v-else-if="detail" style="padding: 16px; overflow-y: auto; flex: 1">
          <div
            v-if="detail.problem_md"
            class="problem-content"
            v-html="renderMarkdown(detail.problem_md)"
          />
          <div v-if="detail.results.length > 0" class="results-section">
            <h3>求解结果对比</h3>
            <table class="comparison-table">
              <thead>
                <tr>
                  <th>方法</th>
                  <th>u(L) mm</th>
                  <th>σ MPa</th>
                  <th>误差</th>
                  <th>备注</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in detail.results"
                  :key="row.method"
                  :class="{ 'row-analytic': row.method === 'analytic' }"
                >
                  <td><strong>{{ row.method }}</strong></td>
                  <td class="col-numeric">{{ row.u_L_mm || '—' }}</td>
                  <td class="col-numeric">{{ row.sigma_MPa || row.sigma_max_MPa || '—' }}</td>
                  <td class="col-numeric">{{ formatError(row.error_u_L_mm) }}</td>
                  <td class="col-notes">{{ row.notes || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </aside>
    </section>
  </div>
</template>

<style scoped>
.empty-state { color: #9ca6b8; font-size: 0.78rem; }
.empty-state code { background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 3px; font-size: 0.72rem; }

.results-section { margin-top: 24px; }
.results-section h3 { color: #edf2fb; font-size: 0.9rem; margin: 0 0 10px; padding-bottom: 6px; border-bottom: 1px solid #2d3442; }

.comparison-table { width: 100%; border-collapse: collapse; font-size: 0.72rem; }
.comparison-table th { background: #171b24; color: #9ca6b8; text-align: left; padding: 8px 10px; border-bottom: 2px solid #2d3442; font-weight: 600; }
.comparison-table td { padding: 6px 10px; border-bottom: 1px solid #1e2330; color: #c4cad6; }
.row-analytic td { color: #26a269; }
.col-numeric { font-family: 'Cascadia Code', Consolas, monospace; text-align: right; }
.col-notes { color: #6b7280; max-width: 240px; font-size: 0.66rem; }

.problem-content :deep(h1) { font-size: 1.1rem; color: #edf2fb; margin: 0 0 12px; padding-bottom: 6px; border-bottom: 1px solid #2d3442; }
.problem-content :deep(h2) { font-size: 0.9rem; color: #edf2fb; margin: 20px 0 8px; }
.problem-content :deep(h3) { font-size: 0.82rem; color: #edf2fb; margin: 16px 0 6px; }
.problem-content :deep(p) { color: #c4cad6; line-height: 1.65; margin: 6px 0; font-size: 0.76rem; }
.problem-content :deep(strong) { color: #edf2fb; }
.problem-content :deep(code) { background: #171b24; padding: 2px 5px; border-radius: 3px; font-size: 0.72rem; color: #7dd3fc; }
.problem-content :deep(pre) { background: #11141a; border: 1px solid #2d3442; border-radius: 6px; padding: 12px; overflow-x: auto; }
.problem-content :deep(pre code) { background: none; padding: 0; color: #c4cad6; }
.problem-content :deep(table) { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 0.72rem; }
.problem-content :deep(th) { background: #171b24; color: #9ca6b8; text-align: left; padding: 6px 10px; border-bottom: 2px solid #2d3442; }
.problem-content :deep(td) { padding: 4px 10px; border-bottom: 1px solid #1e2330; color: #c4cad6; }
.problem-content :deep(li) { color: #c4cad6; line-height: 1.65; font-size: 0.76rem; }
</style>

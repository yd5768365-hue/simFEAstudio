<script setup lang="ts">
import { computed, onActivated, onMounted, ref } from 'vue'
import type { SimfeaClient } from '@/api/simfeaClient'
import VtkResultViewport from '@/components/VtkResultViewport.vue'
import type { BenchmarkCase, BenchmarkCaseDetail, RunArchive } from '@/types'

const props = defineProps<{
  api: SimfeaClient
  apiBaseUrl: string
  runs: RunArchive[]
  selectedRun: RunArchive | null
}>()

const emit = defineEmits<{
  'select-run': [runId: string]
  navigate: [view: string]
}>()

/* ── Benchmark cases ─────────────────────────────────────── */
const cases = ref<BenchmarkCase[]>([])
const selectedCaseName = ref<string | null>(null)
const caseDetail = ref<BenchmarkCaseDetail | null>(null)
const casesLoading = ref(false)

async function fetchCases() {
  casesLoading.value = true
  try {
    const res = await props.api.listBenchmarks()
    cases.value = res.data.cases
    if (cases.value.length > 0 && !selectedCaseName.value) {
      selectedCaseName.value = cases.value[0].name
      await fetchCaseDetail(cases.value[0].name)
    }
  } catch (e) {
    console.error('Failed to load benchmarks', e)
  } finally {
    casesLoading.value = false
  }
}

async function fetchCaseDetail(name: string) {
  try {
    const res = await props.api.getBenchmarkCase(name)
    caseDetail.value = res.data
  } catch (e) {
    caseDetail.value = null
  }
}

function selectCase(c: BenchmarkCase) {
  selectedCaseName.value = c.name
  fetchCaseDetail(c.name)
}

/* ── Derived data ────────────────────────────────────────── */
const recentRuns = computed(() => props.runs.slice(0, 5))

const latestFinishedRun = computed(() => props.runs.find((r) => r.status === 'finished'))

const displayRun = computed(() => props.selectedRun || latestFinishedRun.value)

const runMetrics = computed(() => {
  const run = displayRun.value
  if (!run?.summary?.metrics) return null
  return {
    displacement: run.summary.metrics.max_displacement_mm,
    stress: run.summary.metrics.max_von_mises_mpa,
  }
})

const runReport = computed(() => {
  const run = displayRun.value
  if (!run) return null
  return {
    runId: run.run_id,
    caseName: run.case_name,
    solver: run.solver,
    status: run.status,
    hasReport: Boolean(run.learning_report || run.report),
    hasNote: Boolean(run.note),
    reportText: run.report || run.learning_report || '',
  }
})

/* ── Comparison rows (MVP fallback aware) ────────────────── */
const comparisonRows = computed(() => {
  if (caseDetail.value && caseDetail.value.results.length > 0) {
    return caseDetail.value.results.slice(0, 5).map((r) => ({
      method: r.method,
      u_L_mm: r.u_L_mm || '—',
      sigma: r.sigma_MPa || r.sigma_max_MPa || '—',
      error: r.error_u_L_mm || '—',
      notes: r.notes || '',
    }))
  }
  // MVP fallback: show static demo rows so the table isn't empty
  return [
    { method: 'Analytic', u_L_mm: '0.5000', sigma: '100.00', error: '0.00%', notes: '参考解' },
    { method: 'CalculiX', u_L_mm: '0.4987', sigma: '99.73', error: '0.26%', notes: '10×10 网格' },
    { method: 'ANSYS', u_L_mm: '0.4991', sigma: '99.85', error: '0.18%', notes: '相同网格' },
    { method: 'PINN', u_L_mm: '0.4823', sigma: '94.12', error: '3.54%', notes: '200 epoch' },
  ]
})

onMounted(fetchCases)
onActivated(fetchCases)
</script>

<template>
  <div class="dashboard-shell">
    <!-- Header -->
    <header class="dashboard-header">
      <div class="dashboard-header-left">
        <span class="app-mark" aria-hidden="true">SF</span>
        <h1>SimFEA Studio</h1>
        <span class="dashboard-subtitle">工程仿真仪表盘</span>
      </div>
      <div class="dashboard-header-right">
        <span class="dashboard-stat">
          <strong>{{ runs.length }}</strong>
          <small>运行</small>
        </span>
        <span class="dashboard-stat">
          <strong>{{ cases.length }}</strong>
          <small>案例</small>
        </span>
      </div>
    </header>

    <!-- Main grid -->
    <div class="dashboard-grid">
      <!-- Central: Visualization -->
      <section class="dashboard-visualization">
        <div class="dashboard-panel-head">
          <h2>结果可视化</h2>
          <span v-if="displayRun" class="dashboard-run-tag">{{ displayRun.case_name }}</span>
        </div>
        <div class="dashboard-visual-body">
          <VtkResultViewport
            v-if="displayRun"
            :run="displayRun"
            :api-base-url="apiBaseUrl"
            selected-artifact=""
          />
          <div v-else class="dashboard-empty-viz">
            <span class="dashboard-empty-icon">⊞</span>
            <p>暂无可视化结果</p>
            <small>运行求解器后，VTK 云图将显示在这里</small>
            <button type="button" class="primary-action" @click="emit('navigate', 'composer')">
              去作业区运行
            </button>
          </div>
        </div>
        <div v-if="runMetrics" class="dashboard-viz-metrics">
          <article>
            <span>最大位移</span>
            <strong>{{ runMetrics.displacement?.toFixed(3) ?? '—' }}</strong>
            <small>mm</small>
          </article>
          <article>
            <span>最大应力</span>
            <strong>{{ runMetrics.stress?.toFixed(2) ?? '—' }}</strong>
            <small>MPa</small>
          </article>
        </div>
      </section>

      <!-- Right: Cases -->
      <aside class="dashboard-cases">
        <div class="dashboard-panel-head">
          <h2>基准案例</h2>
          <span class="dashboard-count">{{ cases.length }}</span>
        </div>
        <div v-if="casesLoading" class="dashboard-cases-loading">加载中…</div>
        <div v-else-if="cases.length === 0" class="dashboard-empty-panel">
          暂无案例
        </div>
        <ul v-else class="dashboard-case-list">
          <li
            v-for="c in cases.slice(0, 8)"
            :key="c.name"
            :class="{ active: selectedCaseName === c.name }"
            @click="selectCase(c)"
          >
            <span class="case-indicator" :class="c.has_results ? 'has-results' : ''" />
            <span class="case-name">{{ c.title || c.name }}</span>
            <span class="case-group">{{ c.group }}</span>
          </li>
        </ul>
        <button
          v-if="cases.length > 0"
          type="button"
          class="dashboard-more-btn"
          @click="emit('navigate', 'benchmark-lab')"
        >
          查看全部案例 →
        </button>
      </aside>

      <!-- Bottom: Benchmark Comparison -->
      <section class="dashboard-comparison">
        <div class="dashboard-panel-head">
          <h2>方法对比</h2>
          <span v-if="selectedCaseName" class="dashboard-case-tag">{{ selectedCaseName }}</span>
        </div>
        <div class="dashboard-table-wrap">
          <table class="dashboard-table">
            <thead>
              <tr>
                <th>方法</th>
                <th>位移 mm</th>
                <th>应力 MPa</th>
                <th>误差</th>
                <th>备注</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in comparisonRows" :key="row.method">
                <td>
                  <span
                    class="dashboard-method-tag"
                    :class="row.method.toLowerCase() === 'analytic' ? 'analytic' : ''"
                  >
                    {{ row.method }}
                  </span>
                </td>
                <td class="num">{{ row.u_L_mm }}</td>
                <td class="num">{{ row.sigma }}</td>
                <td class="num">{{ row.error }}</td>
                <td class="note">{{ row.notes }}</td>
              </tr>
              <tr v-if="comparisonRows.length === 0">
                <td colspan="5" class="dashboard-empty-cell">选择案例后显示对比数据</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="!caseDetail" class="dashboard-fallback-hint">
          MVP 提示：当前展示演示数据。真实数据请在 Benchmark Lab 中查看。
        </p>
      </section>

      <!-- Bottom-right: Learning Report -->
      <section class="dashboard-report">
        <div class="dashboard-panel-head">
          <h2>学习报告</h2>
          <span v-if="runReport" class="dashboard-status-pill" :class="runReport.status">
            {{ runReport.status }}
          </span>
        </div>
        <div v-if="runReport?.reportText" class="dashboard-report-body">
          <pre>{{ runReport.reportText.slice(0, 600) }}{{ runReport.reportText.length > 600 ? '…' : '' }}</pre>
          <button
            v-if="runReport.reportText.length > 600"
            type="button"
            class="dashboard-more-btn"
            @click="emit('select-run', runReport.runId)"
          >
            查看完整报告 →
          </button>
        </div>
        <div v-else-if="runReport" class="dashboard-report-empty">
          <p>运行已完成，暂无学习报告</p>
          <small>填写笔记后将自动生成报告</small>
          <button type="button" @click="emit('select-run', runReport.runId)">去填写笔记</button>
        </div>
        <div v-else class="dashboard-report-empty">
          <p>暂无运行记录</p>
          <small>运行求解器后，学习报告将显示在这里</small>
          <button type="button" class="primary-action" @click="emit('navigate', 'composer')">
            去作业区运行
          </button>
        </div>

        <!-- Recent runs mini-list -->
        <div v-if="recentRuns.length > 0" class="dashboard-recent-runs">
          <h3>最近运行</h3>
          <ul>
            <li
              v-for="run in recentRuns"
              :key="run.run_id"
              @click="emit('select-run', run.run_id)"
            >
              <span class="recent-run-name">{{ run.case_name }}</span>
              <span class="recent-run-status" :class="run.status">{{ run.status }}</span>
            </li>
          </ul>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
/* ── Shell ─────────────────────────────────────────────── */
.dashboard-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--bg-app);
  color: var(--text-body);
  overflow: hidden;
}

/* ── Header ────────────────────────────────────────────── */
.dashboard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-shrink: 0;
  height: 52px;
  padding: 0 20px;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-panel);
}

.dashboard-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.dashboard-header-left h1 {
  font-size: 1rem;
  font-weight: 800;
  color: var(--text-heading);
}

.dashboard-subtitle {
  font-size: 0.72rem;
  color: var(--text-muted);
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--bg-input);
}

.dashboard-header-right {
  display: flex;
  gap: 16px;
}

.dashboard-stat {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.dashboard-stat strong {
  font-size: 1.1rem;
  color: var(--text-heading);
}

.dashboard-stat small {
  font-size: 0.68rem;
  color: var(--text-muted);
}

/* ── Grid ──────────────────────────────────────────────── */
.dashboard-grid {
  display: grid;
  grid-template-columns: 1fr 320px;
  grid-template-rows: 1fr 280px;
  gap: 12px;
  flex: 1;
  min-height: 0;
  padding: 12px;
  overflow: hidden;
}

/* ── Panel head ────────────────────────────────────────── */
.dashboard-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-shrink: 0;
  height: 36px;
  padding: 0 12px;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-panel);
}

.dashboard-panel-head h2 {
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--text-heading);
}

.dashboard-run-tag,
.dashboard-case-tag {
  font-size: 0.68rem;
  color: var(--accent);
  padding: 1px 8px;
  border-radius: 4px;
  background: var(--accent-glow);
}

.dashboard-count {
  font-size: 0.68rem;
  color: var(--text-muted);
  padding: 1px 8px;
  border-radius: 4px;
  background: var(--bg-input);
}

/* ── Visualization ─────────────────────────────────────── */
.dashboard-visualization {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-panel);
  overflow: hidden;
  min-width: 0;
}

.dashboard-visual-body {
  flex: 1;
  min-height: 0;
  position: relative;
}

.dashboard-empty-viz {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  height: 100%;
  padding: 24px;
  text-align: center;
}

.dashboard-empty-icon {
  font-size: 2.5rem;
  color: var(--text-dim);
  opacity: 0.5;
}

.dashboard-empty-viz p {
  margin: 0;
  color: var(--text-heading);
  font-size: 0.92rem;
  font-weight: 600;
}

.dashboard-empty-viz small {
  color: var(--text-muted);
  font-size: 0.72rem;
}

.dashboard-viz-metrics {
  display: flex;
  gap: 12px;
  flex-shrink: 0;
  padding: 10px 12px;
  border-top: 1px solid var(--border-default);
  background: var(--bg-card);
}

.dashboard-viz-metrics article {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 6px;
  background: var(--bg-input);
}

.dashboard-viz-metrics article span {
  font-size: 0.68rem;
  color: var(--text-muted);
}

.dashboard-viz-metrics article strong {
  font-size: 1.05rem;
  color: var(--text-heading);
}

.dashboard-viz-metrics article small {
  font-size: 0.68rem;
  color: var(--text-dim);
}

/* ── Cases ─────────────────────────────────────────────── */
.dashboard-cases {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-panel);
  overflow: hidden;
  min-width: 0;
}

.dashboard-cases-loading,
.dashboard-empty-panel {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 0.8rem;
}

.dashboard-case-list {
  flex: 1;
  overflow-y: auto;
  margin: 0;
  padding: 6px;
  list-style: none;
}

.dashboard-case-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 120ms ease;
}

.dashboard-case-list li:hover {
  background: rgba(255, 255, 255, 0.03);
}

.dashboard-case-list li.active {
  background: var(--accent-glow);
}

.case-indicator {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-dim);
  flex-shrink: 0;
}

.case-indicator.has-results {
  background: var(--green);
}

.case-name {
  flex: 1;
  font-size: 0.78rem;
  color: var(--text-body);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.case-group {
  font-size: 0.62rem;
  color: var(--text-dim);
  flex-shrink: 0;
}

.dashboard-more-btn {
  flex-shrink: 0;
  width: 100%;
  padding: 8px;
  border: none;
  border-top: 1px solid var(--border-default);
  background: var(--bg-card);
  color: var(--accent);
  font-size: 0.74rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 120ms ease;
}

.dashboard-more-btn:hover {
  background: var(--accent-glow);
}

/* ── Comparison ────────────────────────────────────────── */
.dashboard-comparison {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-panel);
  overflow: hidden;
  min-width: 0;
}

.dashboard-table-wrap {
  flex: 1;
  overflow: auto;
  padding: 8px 12px;
}

.dashboard-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.74rem;
}

.dashboard-table th {
  text-align: left;
  padding: 7px 10px;
  color: var(--text-muted);
  font-weight: 700;
  font-size: 0.64rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 1px solid var(--border-strong);
  white-space: nowrap;
}

.dashboard-table td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-body);
}

.dashboard-table .num {
  text-align: right;
  font-family: var(--font-mono);
}

.dashboard-table .note {
  font-size: 0.68rem;
  color: var(--text-dim);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dashboard-method-tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 0.68rem;
  font-weight: 600;
  background: rgba(139, 92, 246, 0.12);
  color: var(--accent);
}

.dashboard-method-tag.analytic {
  background: var(--green-soft);
  color: var(--green);
}

.dashboard-empty-cell {
  text-align: center;
  color: var(--text-muted);
  padding: 20px;
}

.dashboard-fallback-hint {
  margin: 0;
  padding: 6px 12px;
  font-size: 0.66rem;
  color: var(--amber);
  border-top: 1px solid var(--border-default);
  background: var(--amber-soft);
}

/* ── Report ────────────────────────────────────────────── */
.dashboard-report {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-panel);
  overflow: hidden;
  min-width: 0;
}

.dashboard-status-pill {
  font-size: 0.62rem;
  font-weight: 700;
  padding: 1px 8px;
  border-radius: 999px;
  text-transform: uppercase;
}

.dashboard-status-pill.finished {
  background: var(--green-soft);
  color: var(--green);
}

.dashboard-status-pill.failed {
  background: var(--red-soft);
  color: var(--red);
}

.dashboard-status-pill.running,
.dashboard-status-pill.queued {
  background: var(--amber-soft);
  color: var(--amber);
}

.dashboard-report-body {
  flex: 1;
  overflow: auto;
  padding: 12px;
}

.dashboard-report-body pre {
  margin: 0;
  white-space: pre-wrap;
  font-family: var(--font-mono);
  font-size: 0.72rem;
  line-height: 1.55;
  color: var(--text-body);
}

.dashboard-report-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 20px;
  text-align: center;
}

.dashboard-report-empty p {
  margin: 0;
  color: var(--text-heading);
  font-size: 0.85rem;
}

.dashboard-report-empty small {
  color: var(--text-muted);
  font-size: 0.72rem;
}

/* ── Recent runs ───────────────────────────────────────── */
.dashboard-recent-runs {
  flex-shrink: 0;
  border-top: 1px solid var(--border-default);
  padding: 10px 12px;
  background: var(--bg-card);
}

.dashboard-recent-runs h3 {
  font-size: 0.68rem;
  color: var(--text-muted);
  margin: 0 0 6px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.dashboard-recent-runs ul {
  margin: 0;
  padding: 0;
  list-style: none;
}

.dashboard-recent-runs li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 120ms ease;
}

.dashboard-recent-runs li:hover {
  background: rgba(255, 255, 255, 0.03);
}

.recent-run-name {
  font-size: 0.74rem;
  color: var(--text-body);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-run-status {
  font-size: 0.62rem;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 3px;
  text-transform: uppercase;
  flex-shrink: 0;
}

.recent-run-status.finished {
  background: var(--green-soft);
  color: var(--green);
}

.recent-run-status.failed {
  background: var(--red-soft);
  color: var(--red);
}

.recent-run-status.running {
  background: var(--amber-soft);
  color: var(--amber);
}

/* ── Responsive ────────────────────────────────────────── */
@media (max-width: 1100px) {
  .dashboard-grid {
    grid-template-columns: 1fr;
    grid-template-rows: auto auto auto auto;
    overflow-y: auto;
  }

  .dashboard-cases {
    max-height: 300px;
  }

  .dashboard-comparison,
  .dashboard-report {
    max-height: 320px;
  }
}
</style>

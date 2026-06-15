<script setup lang="ts">
import { onActivated, onMounted } from 'vue'
import { createSimfeaClient } from '@/api/simfeaClient'
import {
  errorBarWidth,
  errorClass,
  errorLabel,
  formatNum,
  methodCategory,
  useBenchmark,
} from '@/composables/useBenchmark'
import { renderMarkdown, sanitizeHtml } from '@/utils/markdown'

const props = defineProps<{ apiBaseUrl: string }>()
const emit = defineEmits<{ back: [] }>()

const api = createSimfeaClient(props.apiBaseUrl, () => {})
const {
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
} = useBenchmark(api)

function toggleSort(key: typeof sortKey.value) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'asc'
  }
}
function sortIcon(key: typeof sortKey.value): string {
  if (sortKey.value !== key) return ''
  return sortDir.value === 'asc' ? ' ▴' : ' ▾'
}

onMounted(fetchCases)
onActivated(fetchCases)
</script>

<template>
  <div class="lab">
    <!-- Top bar -->
    <div class="lab-top">
      <button type="button" class="lab-back" @click="emit('back')">
        <svg width="14" height="14" viewBox="0 0 16 16"><path d="M10 3L5 8l5 5" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>
      </button>
      <span class="lab-title">基准</span>
      <span class="lab-spacer"></span>
      <span class="lab-file" v-if="selectedName">{{ selectedName }}</span>
    </div>

    <div class="lab-body">
      <!-- Case list sidebar -->
      <nav class="lab-sidebar">
        <div class="lab-sidebar-head">案例</div>
        <div v-for="group in caseGroups" :key="group.label" class="lab-group">
          <div class="lab-group-label">{{ group.label }}</div>
          <button
            v-for="c in group.cases" :key="c.name"
            type="button"
            class="lab-file-btn"
            :class="{ active: selectedName === c.name }"
            @click="selectCase(c.name)"
          >
            <span class="lab-file-icon">{{ c.has_results ? '●' : '○' }}</span>
            <span class="lab-file-name">{{ c.title || c.name }}</span>
          </button>
        </div>
        <div v-if="cases.length === 0" class="lab-sidebar-empty">
          暂无案例
        </div>
      </nav>

      <!-- Detail area -->
      <div class="lab-main">
        <div v-if="loading" class="lab-loading"><span class="lab-spinner"></span> 加载中…</div>
        <div v-else-if="!detail" class="lab-welcome">
          <p>从左侧选择一个案例</p>
          <small>每个案例包含问题描述和多种求解方法的对比结果</small>
        </div>
        <template v-else>
          <div class="lab-preview">
            <div v-if="detail.problem_html" v-html="sanitizeHtml(detail.problem_html)" />
            <div v-else-if="detail.problem_md" v-html="renderMarkdown(detail.problem_md)" />

            <div v-if="stats" class="bm-stats">
              <div class="bm-stat"><span class="bm-stat-val">{{ stats.total }}</span><span class="bm-stat-lbl">求解方法</span></div>
              <div class="bm-stat" v-if="stats.hasAnalytic"><span class="bm-stat-val accent">{{ formatNum(stats.analyticDisplacement || '', 4) }}</span><span class="bm-stat-lbl">解析解位移 mm</span></div>
              <div class="bm-stat" v-if="stats.analyticStress"><span class="bm-stat-val accent">{{ formatNum(stats.analyticStress, 4) }}</span><span class="bm-stat-lbl">解析解应力 MPa</span></div>
              <div class="bm-stat" v-if="stats.bestError !== null"><span class="bm-stat-val green">{{ errorLabel(String(stats.bestError)) }}</span><span class="bm-stat-lbl">最小误差</span></div>
            </div>

            <div v-if="detail.results.length > 0" class="bm-table-section">
              <div class="bm-table-head"><span>结果对比</span><span class="bm-table-hint">点击表头排序</span></div>
              <div class="bm-table-wrap">
                <table class="bm-table">
                  <thead><tr>
                    <th class="bm-th-method" @click="toggleSort('method')">方法{{ sortIcon('method') }}</th>
                    <th class="bm-th-num" @click="toggleSort('u_L_mm')">u(L) mm{{ sortIcon('u_L_mm') }}</th>
                    <th class="bm-th-num" @click="toggleSort('sigma')">σ MPa{{ sortIcon('sigma') }}</th>
                    <th class="bm-th-error" @click="toggleSort('error')">误差{{ sortIcon('error') }}</th>
                    <th class="bm-th-notes" @click="toggleSort('notes')">备注{{ sortIcon('notes') }}</th>
                  </tr></thead>
                  <tbody>
                    <tr v-for="row in sortedResults" :key="row.method" :class="{ 'bm-row-analytic': row.method.toLowerCase() === 'analytic' }">
                      <td><span class="bm-tag" :style="{background:methodCategory(row.method).color+'18',color:methodCategory(row.method).color,border:'1px solid '+methodCategory(row.method).color+'40'}">{{ methodCategory(row.method).label }}</span></td>
                      <td class="bm-num">{{ row.u_L_mm || '—' }}</td>
                      <td class="bm-num">{{ row.sigma_MPa || row.sigma_max_MPa || '—' }}</td>
                      <td class="bm-err"><span class="bm-err-bar" :class="'e-'+errorClass(row.error_u_L_mm)" :style="{width:errorBarWidth(row.error_u_L_mm)}"></span><span class="bm-err-txt" :class="'e-'+errorClass(row.error_u_L_mm)">{{ errorLabel(row.error_u_L_mm) }}</span></td>
                      <td class="bm-notes">{{ row.notes || '—' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── Same layout as ExperimentLab ──────────────── */
.lab { display: flex; flex-direction: column; height: 100%; padding: 0 20px; }
.lab-top { display: flex; align-items: center; gap: 10px; flex-shrink: 0; padding: 12px 0; border-bottom: 1px solid var(--border-subtle); }
.lab-back { background: none; border: none; color: var(--text-muted); cursor: pointer; padding: 2px; }
.lab-back:hover { color: var(--text-body); }
.lab-title { font-size: 0.85rem; font-weight: 600; color: var(--text-heading); }
.lab-file { font-size: 0.8rem; color: var(--text-muted); padding: 2px 8px; background: var(--bg-input); border-radius: 4px; }
.lab-spacer { flex: 1; }

.lab-body { display: flex; flex: 1; min-height: 0; gap: 0; }

.lab-sidebar { width: 200px; flex-shrink: 0; overflow-y: auto; border-right: 1px solid var(--border-subtle); padding: 10px 8px; }
.lab-sidebar-head { font-size: 0.62rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-dim); padding: 0 6px 8px; }
.lab-group { margin-bottom: 10px; }
.lab-group-label { font-size: 0.62rem; color: var(--text-dim); padding: 2px 6px 4px; text-transform: uppercase; letter-spacing: 0.04em; }
.lab-file-btn { display: flex; align-items: center; gap: 6px; width: 100%; padding: 5px 6px; background: none; border: none; border-radius: 4px; color: var(--text-body); font-size: 0.76rem; cursor: pointer; text-align: left; }
.lab-file-btn:hover { background: rgba(255,255,255,0.03); }
.lab-file-btn.active { background: var(--accent-glow); color: var(--accent); }
.lab-file-icon { font-size: 0.7rem; flex-shrink: 0; }
.lab-file-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lab-sidebar-empty { padding: 16px 6px; font-size: 0.72rem; color: var(--text-dim); }

.lab-main { flex: 1; display: flex; flex-direction: column; min-width: 0; min-height: 0; }

.lab-loading { display: flex; align-items: center; justify-content: center; gap: 8px; height: 100%; color: var(--text-muted); font-size: 0.85rem; }
.lab-spinner { width: 18px; height: 18px; border: 2px solid var(--border-subtle); border-top-color: var(--accent-hover); border-radius: 50%; animation: spin 0.6s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.lab-welcome { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; color: var(--text-muted); font-size: 0.85rem; gap: 6px; }
.lab-welcome small { font-size: 0.7rem; color: var(--text-dim); }

/* ── Preview: same as ExperimentLab exactly ───── */
.lab-preview { flex: 1; overflow-y: auto; padding: 20px 24px; background: var(--bg-app); border-left: 1px solid var(--border-subtle); font-size: 0.85rem; line-height: 1.85; color: var(--text-body); }
.lab-preview :deep(h1) { font-size: 1.4rem; font-weight: 800; color: var(--text-heading); margin: 0 0 16px; padding-bottom: 10px; border-bottom: 1px solid var(--border-default); }
.lab-preview :deep(h2) { font-size: 1.12rem; font-weight: 700; color: var(--text-heading); margin: 24px 0 10px; padding-left: 12px; border-left: 3px solid var(--accent); }
.lab-preview :deep(h3) { font-size: 0.95rem; font-weight: 600; color: var(--text-heading); margin: 18px 0 8px; }
.lab-preview :deep(p) { margin: 10px 0; }
.lab-preview :deep(strong) { color: var(--text-heading); font-weight: 700; }
.lab-preview :deep(code) { background: var(--bg-input); padding: 2px 7px; border-radius: 4px; font-size: 0.88em; color: var(--accent-blue); font-family: var(--font-mono); }
.lab-preview :deep(pre) { background: var(--bg-input); border: 1px solid var(--border-default); border-radius: 8px; padding: 16px 20px; overflow-x: auto; font-size: 0.78rem; line-height: 1.65; margin: 16px 0; }
.lab-preview :deep(pre code) { background: none; padding: 0; font-size: inherit; color: var(--text-body); }
.lab-preview :deep(table) { width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 0.8rem; border: 1px solid var(--border-default); border-radius: 8px; overflow: hidden; }
.lab-preview :deep(thead) { border-bottom: 2px solid var(--border-strong); }
.lab-preview :deep(th) { background: var(--bg-panel); color: var(--text-muted); font-weight: 700; padding: 10px 14px; text-align: left; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; }
.lab-preview :deep(td) { padding: 8px 14px; border-bottom: 1px solid var(--border-subtle); color: var(--text-body); }
.lab-preview :deep(tr:nth-child(even) td) { background: rgba(255,255,255,0.015); }
.lab-preview :deep(blockquote) { border-left: 3px solid var(--accent); margin: 16px 0; padding: 12px 18px; color: var(--text-muted); background: var(--accent-glow); border-radius: 0 8px 8px 0; }
.lab-preview :deep(ul), .lab-preview :deep(ol) { margin: 10px 0; padding-left: 24px; }
.lab-preview :deep(li) { margin: 5px 0; line-height: 1.75; }
.lab-preview :deep(hr) { border: none; border-top: 1px solid var(--border-subtle); margin: 28px 0; }

/* ── Stats bar ────────────────────────────────── */
.bm-stats { display: flex; gap: 28px; padding: 14px 20px; margin: 16px 0; background: var(--bg-card); border: 1px solid var(--border-default); border-radius: 6px; flex-wrap: wrap; }
.bm-stat { display: flex; flex-direction: column; gap: 2px; }
.bm-stat-val { font-family: var(--font-mono); font-size: 1.1rem; font-weight: 700; color: var(--text-heading); }
.bm-stat-val.accent { color: var(--accent-hover); }
.bm-stat-val.green { color: var(--green); }
.bm-stat-lbl { font-size: 0.64rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.03em; }

/* ── Comparison table ─────────────────────────── */
.bm-table-section { margin-top: 20px; }
.bm-table-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; font-size: 0.78rem; font-weight: 600; color: var(--text-heading); }
.bm-table-hint { font-size: 0.64rem; color: var(--text-dim); font-weight: 400; }
.bm-table-wrap { overflow-x: auto; border: 1px solid var(--border-default); border-radius: 6px; }
.bm-table { width: 100%; border-collapse: collapse; font-size: 0.76rem; font-variant-numeric: tabular-nums; }
.bm-table th { background: var(--bg-input); color: var(--text-muted); text-align: left; padding: 8px 12px; font-weight: 700; font-size: 0.66rem; text-transform: uppercase; letter-spacing: 0.04em; cursor: pointer; user-select: none; white-space: nowrap; border-bottom: 2px solid var(--border-strong); }
.bm-table th:hover { color: var(--text-heading); }
.bm-table td { padding: 8px 12px; border-bottom: 1px solid var(--border-subtle); color: var(--text-body); }
.bm-th-num { text-align: right; }
.bm-num { text-align: right; font-family: var(--font-mono); font-size: 0.78rem; }
.bm-th-error { width: 160px; }
.bm-th-notes { min-width: 100px; }
.bm-err { display: flex; align-items: center; gap: 6px; }
.bm-err-bar { height: 4px; border-radius: 2px; min-width: 2px; max-width: 60px; opacity: 0.8; }
.bm-err-bar.e-exact { background: var(--green); width: 2px !important; }
.bm-err-bar.e-tiny { background: var(--green); opacity: 0.5; }
.bm-err-bar.e-good { background: var(--green); }
.bm-err-bar.e-mid { background: var(--amber); }
.bm-err-bar.e-large { background: var(--red); }
.bm-err-txt { font-family: var(--font-mono); font-size: 0.7rem; font-weight: 600; white-space: nowrap; }
.bm-err-txt.e-exact, .bm-err-txt.e-tiny, .bm-err-txt.e-good { color: var(--green); }
.bm-err-txt.e-mid { color: var(--amber); }
.bm-err-txt.e-large { color: var(--red); }
.bm-notes { font-size: 0.68rem; color: var(--text-dim); max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bm-tag { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 0.7rem; font-weight: 600; }
.bm-row-analytic td { background: rgba(46,204,113,0.05); font-weight: 600; color: var(--text-heading); }
</style>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { createSimfeaClient } from '@/api/simfeaClient'
import type { RunArchive } from '@/types'

const props = defineProps<{
  runs: RunArchive[]
  apiBaseUrl: string
}>()

const emit = defineEmits<{
  back: []
  'select-run': [runId: string]
}>()

const localLog: string[] = []
const api = createSimfeaClient(props.apiBaseUrl, (line) => localLog.push(line))

const searchText = ref('')
const statusFilter = ref('')
const exportingId = ref<string | null>(null)
const exportMessage = ref('')

const runsWithLearning = computed(() =>
  props.runs.filter((run) => {
    const hasLearning = run.learning_report || run.note || run.summary
    if (!hasLearning) return false
    if (statusFilter.value && run.status !== statusFilter.value) return false
    if (searchText.value) {
      const text = searchText.value.toLowerCase()
      if (
        !run.case_name.toLowerCase().includes(text) &&
        !run.solver.toLowerCase().includes(text) &&
        !run.run_id.toLowerCase().includes(text)
      )
        return false
    }
    return true
  })
)

const statuses = computed(() => {
  const unique = new Set(props.runs.map((r) => r.status))
  return [...unique].sort()
})

function hasNotes(run: RunArchive) {
  return Boolean(run.note)
}

function hasReport(run: RunArchive) {
  return Boolean(run.learning_report)
}

function hasMetrics(run: RunArchive) {
  return Boolean(run.summary?.metrics)
}

async function handleExport(run: RunArchive, format: string) {
  exportingId.value = run.run_id
  exportMessage.value = ''
  try {
    const result = await api.exportLearningRecord(run.run_id, format)
    exportMessage.value = `已导出：${result.data.path || result.message}`
  } catch (err) {
    exportMessage.value = `导出失败：${err}`
  } finally {
    exportingId.value = null
  }
}

function formatDate(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
</script>

<template>
  <div class="library-view">
    <header class="library-header">
      <div class="library-header-left">
        <button type="button" @click="emit('back')">← 返回作业区</button>
        <h2>学习库</h2>
        <span class="library-count">{{ runsWithLearning.length }} 条记录</span>
      </div>
      <div class="library-controls">
        <input
          v-model="searchText"
          type="text"
          class="library-search"
          placeholder="搜索案例名称、求解器…"
        />
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
        <span v-if="exportMessage" class="export-message">{{ exportMessage }}</span>
      </div>
    </header>

    <div v-if="runsWithLearning.length === 0" class="empty-state library-empty">
      暂无学习记录。运行求解器并填写引导问题后，这里会汇总所有历史算例的学习记录。
    </div>

    <div class="library-grid">
      <article
        v-for="run in runsWithLearning"
        :key="run.run_id"
        class="library-card"
        @click="emit('select-run', run.run_id)"
      >
        <div class="library-card-head">
          <strong>{{ run.case_name }}</strong>
          <span class="status-pill" :class="run.status === 'finished' ? 'online' : run.status === 'failed' ? 'offline' : 'pending'">
            {{ run.status }}
          </span>
        </div>
        <div class="library-card-meta">
          <span>{{ run.solver }} / {{ run.runner }}</span>
          <small>{{ formatDate(run.created_at) }}</small>
        </div>
        <div class="library-card-tags">
          <span v-if="hasNotes(run)" class="tag tag-online">笔记</span>
          <span v-else class="tag tag-neutral">无笔记</span>
          <span v-if="hasReport(run)" class="tag tag-online">报告</span>
          <span v-else class="tag tag-neutral">无报告</span>
          <span v-if="hasMetrics(run)" class="tag tag-purple">有结果</span>
        </div>
        <div class="library-card-metrics" v-if="run.summary?.metrics">
          <small v-if="run.summary.metrics.max_displacement_mm != null">
            位移 {{ Number(run.summary.metrics.max_displacement_mm).toFixed(3) }} mm
          </small>
          <small v-if="run.summary.metrics.max_von_mises_mpa != null">
            应力 {{ Number(run.summary.metrics.max_von_mises_mpa).toFixed(2) }} MPa
          </small>
        </div>
        <div class="library-card-actions" @click.stop>
          <button type="button" @click="emit('select-run', run.run_id)">查看详情</button>
          <button
            type="button"
            :disabled="exportingId === run.run_id"
            @click="handleExport(run, 'md')"
          >
            {{ exportingId === run.run_id ? '导出中…' : '导出 MD' }}
          </button>
          <button
            type="button"
            :disabled="exportingId === run.run_id"
            @click="handleExport(run, 'json')"
          >
            导出 JSON
          </button>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { createSimfeaClient } from '@/api/simfeaClient'
import ResultEvidenceView from '@/components/ResultEvidenceView.vue'
import type { GuidedQuestion, RunArchive } from '@/types'

const props = defineProps<{
  run: RunArchive | null
  apiBaseUrl: string
  remoteOutput: string
}>()

const emit = defineEmits<{
  back: []
  refresh: []
}>()

const api = createSimfeaClient(props.apiBaseUrl, () => {})

const questions = ref<GuidedQuestion[]>([])
const answers = ref<Record<string, string>>({})
const reportText = ref<string | null>(null)
const saving = ref(false)
const generating = ref(false)
const savedMessage = ref('')
const reportLoading = ref(false)

const inputFiles = computed(() => props.run?.input_files ?? [])
const metrics = computed(() => props.run?.summary?.metrics ?? null)
const hasReport = computed(() => Boolean(props.run?.report || reportText.value))
const displayReport = computed(() => reportText.value || props.run?.report || '')

function metricRow(label: string, key: string, unit: string) {
  const value = metrics.value?.[key]
  return typeof value === 'number' ? `${value.toFixed(4)} ${unit}` : '暂无'
}

async function loadQuestions() {
  if (!props.run?.run_id) return
  try {
    const result = await api.getGuidedQuestions(props.run.run_id)
    if (result.data?.questions) {
      questions.value = result.data.questions
      const initial: Record<string, string> = {}
      for (const q of result.data.questions) {
        initial[q.id] = q.answer || ''
      }
      answers.value = initial
    }
  } catch {
    questions.value = []
  }
}

async function saveNotes() {
  if (!props.run?.run_id) return
  saving.value = true
  savedMessage.value = ''
  try {
    await api.saveRunNote(props.run.run_id, '', { ...answers.value })
    savedMessage.value = '笔记已保存，报告已自动生成。'
    await loadReport()
    emit('refresh')
  } catch (err) {
    savedMessage.value = `保存失败：${err}`
  } finally {
    saving.value = false
  }
}

async function generateReport() {
  if (!props.run?.run_id) return
  generating.value = true
  try {
    const result = await api.generateRunReport(props.run.run_id)
    reportText.value = result.data.report
  } catch (err) {
    reportText.value = `生成报告失败：${err}`
  } finally {
    generating.value = false
  }
}

async function loadReport() {
  if (!props.run?.run_id) return
  reportLoading.value = true
  try {
    const result = await api.generateRunReport(props.run.run_id)
    reportText.value = result.data.report
  } catch {
    // report may not exist yet
  } finally {
    reportLoading.value = false
  }
}

watch(
  () => props.run?.run_id,
  () => {
    questions.value = []
    answers.value = {}
    reportText.value = null
    savedMessage.value = ''
    if (props.run?.run_id) {
      loadQuestions()
    }
  },
  { immediate: true }
)
</script>

<template>
  <div class="detail-view">
    <header class="detail-header">
      <div class="detail-header-left">
        <button type="button" @click="emit('back')">← 返回作业区</button>
        <h2>{{ run?.case_name || '运行详情' }}</h2>
        <span v-if="run" class="status-pill" :class="run.status === 'finished' ? 'online' : run.status === 'failed' ? 'offline' : 'pending'">
          {{ run.status }}
        </span>
      </div>
      <div class="detail-header-meta">
        <span>{{ run?.solver }} / {{ run?.runner }} / {{ run?.compute_node }}</span>
      </div>
    </header>

    <div class="detail-grid-2col">
      <section class="detail-section">
        <h3>输入文件</h3>
        <ul v-if="inputFiles.length" class="detail-file-list">
          <li v-for="f in inputFiles" :key="f">{{ f }}</li>
        </ul>
        <p v-else class="empty-state">暂无输入文件记录</p>

        <h3>结果数值</h3>
        <dl v-if="metrics" class="detail-metrics">
          <div>
            <dt>最大位移</dt>
            <dd>{{ metricRow('max_displacement_mm', 'max_displacement_mm', 'mm') }}</dd>
          </div>
          <div>
            <dt>等效应力</dt>
            <dd>{{ metricRow('max_von_mises_mpa', 'max_von_mises_mpa', 'MPa') }}</dd>
          </div>
          <div v-if="run?.exit_code != null">
            <dt>退出码</dt>
            <dd>{{ run.exit_code }}</dd>
          </div>
          <div v-if="run?.job_id">
            <dt>作业 ID</dt>
            <dd>{{ run.job_id }}</dd>
          </div>
        </dl>
        <p v-else class="empty-state">暂无结果数值</p>

        <h3>运行日志</h3>
        <pre v-if="remoteOutput" class="detail-log"><code>{{ remoteOutput }}</code></pre>
        <p v-else class="empty-state">暂无运行日志</p>
      </section>

      <section class="detail-section">
        <ResultEvidenceView
          :run="run"
          :api-base-url="apiBaseUrl"
          :report-preview="displayReport"
          :remote-output="remoteOutput"
        />
      </section>
    </div>

    <section class="detail-section learning-section">
      <h3>学习记录</h3>

      <div v-if="questions.length" class="guided-questions">
        <div v-for="q in questions" :key="q.id" class="question-field">
          <label :for="`q-${q.id}`">{{ q.question }}</label>
          <textarea
            :id="`q-${q.id}`"
            v-model="answers[q.id]"
            rows="3"
            placeholder="在此输入你的思考和回答…"
          />
        </div>
        <div class="question-actions">
          <button type="button" class="primary-action" :disabled="saving" @click="saveNotes">
            {{ saving ? '正在保存…' : '保存笔记' }}
          </button>
          <span v-if="savedMessage" class="saved-message">{{ savedMessage }}</span>
        </div>
      </div>
      <p v-else class="empty-state">暂无引导问题。笔记功能需要运行完成后才能使用。</p>

      <div class="report-block">
        <div class="report-head">
          <h3>AI 学习报告</h3>
          <button
            v-if="!hasReport"
            type="button"
            class="primary-action"
            :disabled="generating"
            @click="generateReport"
          >
            {{ generating ? '正在生成…' : '生成报告' }}
          </button>
        </div>
        <pre v-if="hasReport" class="detail-report"><code>{{ displayReport }}</code></pre>
        <p v-else class="empty-state">先保存引导问题笔记，系统会自动生成报告，也可以手动点击"生成报告"。</p>
      </div>

    </section>
  </div>
</template>

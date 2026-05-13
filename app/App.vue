<script setup lang="ts">
import { invoke } from '@tauri-apps/api/core'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { createSimfeaClient } from '@/api/simfeaClient'
import RemotePanel from '@/components/RemotePanel.vue'
import ResultEvidenceView from '@/components/ResultEvidenceView.vue'
import { useRemoteRuns } from '@/composables/useRemoteRuns'
import { useRunEvents } from '@/composables/useRunEvents'
import { useSidecarListeners } from '@/composables/useSidecarListeners'
import type { GuidedQuestion, RunArchive, ToolchainItem } from '@/types'
import { renderMarkdown } from '@/utils/markdown'

const configuredApiBaseUrl = import.meta.env.VITE_SIMFEA_API_BASE_URL as string | undefined
const apiBaseUrl =
  configuredApiBaseUrl?.replace(/\/$/, '') || `http://${window.location.hostname || 'localhost'}:8008`

interface ConnectionStatus {
  connected: boolean
  host: string
  pid: string
  runsRoot: string
  configPath: string
  learningExportRoot: string
  learningFormats: string[]
  learningDefaultFormat: string
  message: string
}

const status = ref<ConnectionStatus>({
  connected: false,
  host: '',
  pid: '',
  runsRoot: '',
  configPath: '',
  learningExportRoot: '',
  learningFormats: ['md', 'json', 'txt'],
  learningDefaultFormat: 'md',
  message: '尚未验证侧车服务连接。',
})

const archivedRuns = ref<RunArchive[]>([])
const selectedRun = ref<RunArchive | null>(null)
const toolchainItems = ref<ToolchainItem[]>([])
const guidedQuestions = ref<GuidedQuestion[]>([])
const reportPreview = ref('')
const learningExportTarget = ref('')
const selectedLearningFormat = ref('md')
const noteMessage = ref('选择一次运行后，回答引导问题，保存后生成学习报告。')
const reportMessage = ref('运行完成后，这里会显示自动生成的学习沉淀报告。')
const exportMessage = ref('学习记录可以导出到配置目录，也可以临时指定一个目录。')
const logs = ref('[界面] 正在监听侧车服务和网络日志...')

const evidenceArtifacts = computed(
  () => selectedRun.value?.artifacts?.filter((artifact) => artifact !== 'artifacts/result_summary.json') ?? []
)
const renderedReport = computed(() => (reportPreview.value ? renderMarkdown(reportPreview.value) : ''))

const selectedArtifacts = computed(() =>
  evidenceArtifacts.value.length ? evidenceArtifacts.value.join('、') : '暂无结果文件'
)

const selectedToolchain = computed<ToolchainItem[]>(
  () => selectedRun.value?.toolchain ?? toolchainItems.value
)

const availableLearningFormats = computed(() =>
  status.value.learningFormats.length > 0 ? status.value.learningFormats : ['md', 'json', 'txt']
)

const solverFilter = ref('')
const statusFilter = ref('')
const availableSolvers = computed(() => {
  const solvers = new Set(archivedRuns.value.map((r) => r.solver).filter(Boolean))
  return [...solvers].sort()
})
const filteredRuns = computed(() => {
  let runs = archivedRuns.value
  if (solverFilter.value) runs = runs.filter((r) => r.solver === solverFilter.value)
  if (statusFilter.value) runs = runs.filter((r) => r.status === statusFilter.value)
  return runs
})

const appendLog = (line: string) => {
  logs.value += `\n${line}`
}

const api = createSimfeaClient(apiBaseUrl, appendLog)
const { initSidecarListeners, disposeSidecarListeners } = useSidecarListeners({ appendLog })
const { openRunEventStream, closeRunEventStream } = useRunEvents({ baseUrl: apiBaseUrl })

const remoteRuns = useRemoteRuns({
  api,
  openRunEventStream,
  closeRunEventStream,
  onRunFinished: async (runId: string) => {
    await loadRunsAction()
    await selectRunAction(runId)
  },
  appendLog,
})

const { remoteStatus, computeNodes, solvers, selectedComputeNode, activeComputeNodeLabel, remoteLabel } =
  remoteRuns

const connectionLabel = computed(() => (status.value.connected ? '侧车服务在线' : '侧车服务待连接'))

const loadRunsAction = async () => {
  const result = await api.listRuns()
  archivedRuns.value = result.data.runs ?? []
  if (!selectedRun.value && archivedRuns.value.length > 0) {
    await selectRunAction(archivedRuns.value[0].run_id)
  }
}

const selectRunAction = async (runId: string) => {
  const result = await api.getRun(runId)
  if (!result.data) {
    noteMessage.value = '没有找到这次运行的归档。'
    return
  }

  selectedRun.value = result.data
  reportPreview.value = result.data.report ?? ''
  reportMessage.value = result.data.learning_report
    ? `学习报告：${result.data.local_archive}\\${result.data.learning_report}`
    : '运行完成，等待填写笔记后生成学习报告。'
  exportMessage.value = result.data.learning_export
    ? `最近导出：${result.data.learning_export.path}`
    : '这次运行还没有导出到学习库。'

  // Fetch guided questions (backend fills in existing answers from note.md)
  try {
    const qResult = await api.getGuidedQuestions(runId)
    if (qResult.data?.questions) {
      guidedQuestions.value = qResult.data.questions
      noteMessage.value = `引导问题已加载（${guidedQuestions.value.length} 题）`
    }
  } catch {
    noteMessage.value = '打不开引导问题。'
  }
}

const saveNoteAction = async () => {
  if (!selectedRun.value) {
    noteMessage.value = '请先选择一次运行记录。'
    return
  }

  const answers: Record<string, string> = {}
  let hasContent = false
  for (const q of guidedQuestions.value) {
    const answer = q.answer.trim()
    answers[q.id] = answer
    if (answer) hasContent = true
  }
  if (!hasContent) {
    noteMessage.value = '请至少填写一个问题的答案。'
    return
  }

  const result = await api.saveRunNote(selectedRun.value.run_id, '', answers)
  noteMessage.value = result.data.saved ? `学习笔记已保存：${result.data.note_path}` : '学习笔记保存失败。'
  if (result.data.report_path) {
    reportMessage.value = `学习报告已刷新：${result.data.report_path}`
  }
  await selectRunAction(selectedRun.value.run_id)
}

const refreshReportAction = async () => {
  if (!selectedRun.value) {
    reportMessage.value = '请先选择一次运行记录。'
    return
  }

  const result = await api.generateRunReport(selectedRun.value.run_id)
  if (!result.data) {
    reportMessage.value = '学习报告生成失败。'
    return
  }

  reportPreview.value = result.data.report
  if (selectedRun.value && result.data.summary) {
    selectedRun.value = {
      ...selectedRun.value,
      summary: result.data.summary,
    }
  }
  reportMessage.value = `学习报告已生成：${result.data.report_path}`
  await loadRunsAction()
}

const exportLearningRecordAction = async () => {
  if (!selectedRun.value) {
    exportMessage.value = '请先选择一次运行记录。'
    return
  }

  const result = await api.exportLearningRecord(
    selectedRun.value.run_id,
    selectedLearningFormat.value,
    learningExportTarget.value.trim() || undefined
  )
  if (!result.data?.exported) {
    exportMessage.value = '学习记录导出失败。'
    return
  }

  exportMessage.value = `学习记录已导出：${result.data.export_path}`
  if (result.data.summary) {
    selectedRun.value = {
      ...selectedRun.value,
      summary: result.data.summary,
      learning_export: result.data.record,
    }
  }
  await loadRunsAction()
}

const connectServerAction = async () => {
  try {
    const result = await api.connect()
    status.value = {
      connected: true,
      host: result.data.host,
      pid: String(result.data.pid),
      runsRoot: result.data.runs_root,
      configPath: result.data.config_path,
      learningExportRoot: result.data.learning_export_root,
      learningFormats: result.data.learning_formats ?? ['md', 'json', 'txt'],
      learningDefaultFormat: result.data.learning_default_format ?? 'md',
      message: '侧车服务连接成功。',
    }
    learningExportTarget.value = result.data.learning_export_root ?? ''
    selectedLearningFormat.value = result.data.learning_default_format ?? 'md'
    remoteRuns.setComputeNodes(result.data.compute_nodes ?? [], result.data.default_compute_node ?? '')
    remoteRuns.setSolvers(result.data.solvers ?? [])
    toolchainItems.value = result.data.toolchain ?? []
    await loadRunsAction()
  } catch (err) {
    status.value = {
      connected: false,
      host: '',
      pid: '',
      runsRoot: '',
      configPath: '',
      learningExportRoot: '',
      learningFormats: ['md', 'json', 'txt'],
      learningDefaultFormat: 'md',
      message: '连接失败，请确认 FastAPI sidecar 已启动。',
    }
    appendLog(`[界面] 连接 API 服务失败：${err}`)
  }
}

const shutdownSidecarAction = async () => {
  try {
    await invoke('shutdown_sidecar')
    status.value = {
      connected: false,
      host: '',
      pid: '',
      runsRoot: '',
      configPath: '',
      learningExportRoot: '',
      learningFormats: ['md', 'json', 'txt'],
      learningDefaultFormat: 'md',
      message: '已请求关闭侧车服务。',
    }
    appendLog('[界面] 已请求关闭侧车服务。')
  } catch (err) {
    appendLog(`[界面] 关闭侧车服务失败：${err}`)
  }
}

const startSidecarAction = async () => {
  try {
    await invoke('start_sidecar')
    appendLog('[界面] 已请求启动侧车服务，稍后自动验证连接。')
    window.setTimeout(connectServerAction, 1000)
  } catch (err) {
    appendLog(`[界面] 启动侧车服务失败：${err}`)
  }
}

const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'F11') {
    event.preventDefault()
    invoke('toggle_fullscreen')
  }
}

onMounted(() => {
  initSidecarListeners()
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  disposeSidecarListeners()
  closeRunEventStream()
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <main class="studio-shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">SimFEA Studio 物证工作台</p>
        <h1>远程运行、实时日志、结果归档、学习笔记</h1>
        <p class="mission">
          这个闭环先不追求完整求解器，而是把一次远程计算变成可回放的学习证据：
          命令、日志、结果文件、远程目录和个人复盘会被收进同一个运行档案。
        </p>
      </div>
      <div class="connection-stack">
        <div class="connection-pill" :class="{ online: status.connected }">
          <span class="status-dot" />
          <span>{{ connectionLabel }}</span>
        </div>
        <div class="connection-pill" :class="{ online: remoteStatus.connected }">
          <span class="status-dot" />
          <span>{{ remoteLabel }}</span>
        </div>
      </div>
    </header>

    <section class="workspace-grid" aria-label="SimFEA Studio 工作区">
      <section class="panel project-panel" aria-labelledby="project-title">
        <div class="section-heading">
          <p class="eyebrow">当前闭环</p>
          <h2 id="project-title">远程闭环样例</h2>
        </div>
        <p class="body-copy">
          任务会通过配置文件中的计算节点执行，在远程目录创建输入文件和结果文件，同时把 stdout/stderr 实时传回前端。
          结束后，侧车服务会把 result.txt 拉回本地 `.simfea/runs/` 归档目录。
        </p>
        <dl class="facts">
          <div>
            <dt>前端</dt>
            <dd>Vue / Vite</dd>
          </div>
          <div>
            <dt>侧车</dt>
            <dd>FastAPI / Python</dd>
          </div>
          <div>
            <dt>执行器</dt>
            <dd>SSHRunner / 配置节点</dd>
          </div>
        </dl>
      </section>

      <section class="panel control-panel" aria-labelledby="control-title">
        <div class="section-heading">
          <p class="eyebrow">侧车服务</p>
          <h2 id="control-title">本地控制面板</h2>
        </div>
        <div class="button-row">
          <button class="primary-action" type="button" @click="connectServerAction">
            验证连接
          </button>
          <button type="button" @click="startSidecarAction" :disabled="status.connected">
            启动侧车
          </button>
          <button type="button" @click="shutdownSidecarAction" :disabled="!status.connected">
            关闭侧车
          </button>
        </div>
        <div class="connection-detail">
          <span>{{ status.message }}</span>
          <span v-if="status.connected">API：{{ status.host }}</span>
          <span v-if="status.connected">进程：{{ status.pid }}</span>
          <span v-if="status.runsRoot">物证仓库：{{ status.runsRoot }}</span>
          <span v-if="status.learningExportRoot">学习库：{{ status.learningExportRoot }}</span>
          <span v-if="status.configPath">配置文件：{{ status.configPath }}</span>
        </div>
      </section>

      <RemotePanel
        :compute-nodes="computeNodes"
        :solvers="solvers"
        :selected-compute-node="selectedComputeNode"
        :active-compute-node-label="activeComputeNodeLabel"
        :remote-status="remoteStatus"
        :connected="status.connected"
        :actions="{
          probeRemoteNodeAction: () => remoteRuns.probeRemoteNodeAction(),
          probeSchedulerAction: () => remoteRuns.probeSchedulerAction(),
          probeSolversAction: () => remoteRuns.probeSolversAction(),
          startRemoteDemoRunAction: () => remoteRuns.startRemoteDemoRunAction(),
          startSlurmDemoRunAction: () => remoteRuns.startSlurmDemoRunAction(),
          startSolverRunAction: (solverAlias: string) => remoteRuns.startSolverRunAction(solverAlias),
          cancelRemoteRunAction: () => remoteRuns.cancelRemoteRunAction(),
        }"
        @update:selected-compute-node="selectedComputeNode = $event"
      />

      <section class="panel toolchain-panel" aria-labelledby="toolchain-title">
        <div class="section-heading">
          <p class="eyebrow">工具链地图</p>
          <h2 id="toolchain-title">把竞品变成证据来源</h2>
        </div>
        <div class="toolchain-list">
          <article v-for="item in selectedToolchain" :key="item.name" class="toolchain-item">
            <div>
              <h3>{{ item.name }}</h3>
              <p>{{ item.role }}</p>
            </div>
            <span>{{ item.status }}</span>
          </article>
          <p v-if="selectedToolchain.length === 0" class="empty-state">
            工具链地图会从后端配置加载。
          </p>
        </div>
      </section>

      <section class="panel runs-panel" aria-labelledby="runs-title">
        <div class="section-heading">
          <p class="eyebrow">物证仓库</p>
          <h2 id="runs-title">运行记录</h2>
        </div>
        <div class="filter-row">
          <select v-model="solverFilter" class="filter-select">
            <option value="">全部求解器</option>
            <option v-for="s in availableSolvers" :key="s" :value="s">{{ s }}</option>
          </select>
          <select v-model="statusFilter" class="filter-select">
            <option value="">全部状态</option>
            <option value="finished">finished</option>
            <option value="failed">failed</option>
            <option value="running">running</option>
            <option value="canceled">canceled</option>
          </select>
          <span class="filter-count">{{ filteredRuns.length }} / {{ archivedRuns.length }} 条</span>
        </div>
        <div class="run-table" role="table" aria-label="运行记录">
          <div class="run-row run-head" role="row">
            <span role="columnheader">算例</span>
            <span role="columnheader">求解器</span>
            <span role="columnheader">状态</span>
            <span role="columnheader">位移(mm)</span>
            <span role="columnheader">应力(MPa)</span>
          </div>
          <button
            v-for="run in filteredRuns"
            :key="run.run_id"
            type="button"
            class="run-row run-button"
            :class="{ selected: selectedRun?.run_id === run.run_id }"
            @click="selectRunAction(run.run_id)"
          >
            <span>{{ run.case_name }}</span>
            <span>{{ run.solver }}</span>
            <span>{{ run.status }}</span>
            <span>{{ run.summary?.metrics?.max_displacement_mm?.toFixed(2) ?? '—' }}</span>
            <span>{{ run.summary?.metrics?.max_von_mises_mpa?.toFixed(2) ?? '—' }}</span>
          </button>
          <p v-if="filteredRuns.length === 0" class="empty-state">
            暂无匹配的运行记录。
          </p>
        </div>
      </section>

      <ResultEvidenceView
        :run="selectedRun"
        :api-base-url="apiBaseUrl"
        :report-preview="reportPreview"
        :remote-output="remoteStatus.output"
      />

      <section class="panel note-panel" aria-labelledby="note-title">
        <div class="section-heading">
          <p class="eyebrow">学习笔记</p>
          <h2 id="note-title">本次复盘</h2>
        </div>
        <div v-if="selectedRun" class="run-summary">
          <span>运行：{{ selectedRun.run_id }}</span>
          <span>退出码：{{ selectedRun.exit_code ?? '未结束' }}</span>
          <span>结果：{{ selectedArtifacts }}</span>
        </div>
        <div v-if="!selectedRun" class="note-placeholder">
          选择一次运行记录后，这里会显示引导问题。
        </div>
        <div v-for="q in guidedQuestions" :key="q.id" class="guided-question">
          <label :for="`q-${q.id}`">{{ q.question }}</label>
          <textarea
            :id="`q-${q.id}`"
            v-model="q.answer"
            :disabled="!selectedRun"
            :placeholder="`回答：${q.question.slice(0, 20)}...`"
            rows="2"
          />
        </div>
        <div class="button-row">
          <button type="button" class="primary-action" @click="saveNoteAction" :disabled="!selectedRun">
            保存学习笔记
          </button>
        </div>
        <p class="note-message">{{ noteMessage }}</p>
      </section>

      <section class="panel export-panel" aria-labelledby="export-title">
        <div class="section-heading">
          <p class="eyebrow">长期沉淀</p>
          <h2 id="export-title">学习记录导出</h2>
        </div>
        <label class="field-label">
          <span>导出目录</span>
          <input
            v-model="learningExportTarget"
            :placeholder="status.learningExportRoot || '.simfea/learning'"
            :disabled="!selectedRun"
          />
        </label>
        <label class="field-label">
          <span>记录格式</span>
          <select v-model="selectedLearningFormat" :disabled="!selectedRun">
            <option v-for="format in availableLearningFormats" :key="format" :value="format">
              {{ format }}
            </option>
          </select>
        </label>
        <div class="button-row">
          <button type="button" class="primary-action" @click="exportLearningRecordAction" :disabled="!selectedRun">
            导出学习记录
          </button>
        </div>
        <p class="note-message">
          默认目录来自 .simfea/config.json；md 适合阅读，json 适合后续 AI agent 读取，txt 适合快速检索。
        </p>
        <p class="note-message">{{ exportMessage }}</p>
      </section>

      <section class="panel report-panel" aria-labelledby="report-title">
        <div class="section-heading">
          <p class="eyebrow">沉淀报告</p>
          <h2 id="report-title">learning_report.md</h2>
        </div>
        <div class="button-row">
          <button type="button" class="primary-action" @click="refreshReportAction" :disabled="!selectedRun">
            刷新学习报告
          </button>
        </div>
        <p class="note-message">{{ reportMessage }}</p>
        <div v-if="renderedReport" class="report-preview" v-html="renderedReport" />
        <p v-else class="empty-state">
          选择一次运行记录后，这里会显示自动生成的学习沉淀报告。
        </p>
      </section>

      <section class="panel log-panel" aria-labelledby="log-title">
        <div class="section-heading compact-heading">
          <p class="eyebrow">实时日志</p>
          <h2 id="log-title">侧车与远程输出</h2>
        </div>
        <pre class="logs-display"><code>{{ logs }}</code></pre>
      </section>
    </section>
  </main>
</template>

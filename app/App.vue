<script setup lang="ts">
import { invoke } from '@tauri-apps/api/core'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { createSimfeaClient } from '@/api/simfeaClient'
import LearningLibrary from '@/components/LearningLibrary.vue'
import RunDetailView from '@/components/RunDetailView.vue'
import ToolchainManager from '@/components/ToolchainManager.vue'
import { useRemoteRuns } from '@/composables/useRemoteRuns'
import { useRunEvents } from '@/composables/useRunEvents'
import { useSidecarListeners } from '@/composables/useSidecarListeners'
import type { RunArchive, ToolchainItem } from '@/types'

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

interface UploadedInputFile {
  name: string
  size: number
}

interface JobTemplate {
  id: string
  name: string
  worker: string
  computeNode: string
  nodeMode: string
  files: UploadedInputFile[]
  savedAt: string
}

type JobMode = 'single' | 'pipeline'
type UploadMode = 'single-file' | 'folder'

interface PipelineStep {
  id: string
  launcher: string
  inputName: string
}

interface QueueItem {
  id: string
  title: string
  mode: JobMode
  progress: number
  status: 'queued' | 'running' | 'finished' | 'failed'
  stage: string
  logOpen: boolean
  logs: string[]
  createdAt: string
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
  message: '等待连接本地侧车服务。',
})

const archivedRuns = ref<RunArchive[]>([])
const selectedRun = ref<RunArchive | null>(null)
const toolchainItems = ref<ToolchainItem[]>([])
const logs = ref('[system] SimFEA Studio 桌面工作台已加载。')

const appendLog = (line: string) => {
  logs.value = `${logs.value}\n${line}`
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

const workerOptions = [
  { alias: 'calculix', label: 'CalculiX', kind: '结构求解器' },
  { alias: 'abaqus', label: 'Abaqus', kind: '商业求解器' },
  { alias: 'elmer', label: 'Elmer', kind: '多物理场' },
]

const nodeModeOptions = [
  { value: 'local', label: '本地工作站' },
  { value: 'ssh', label: 'SSH 远程' },
  { value: 'hpc', label: 'HPC 队列' },
]

const filteredComputeNodes = computed(() =>
  nodeMode.value === 'local'
    ? computeNodes.value.filter((n) => n.alias === 'local')
    : computeNodes.value.filter((n) => n.alias !== 'local')
)

const solverInputHint = computed(() => {
  const hints: Record<string, string> = {
    calculix: '.inp (CalculiX 输入文件)',
    freecad: '.FCStd 或 .step (FreeCAD 几何文件)',
    prepomax: '.pmx (PrePoMax 项目文件)',
    'prepomax-regenerate': '.pmx + .STEP (PrePoMax 再生文件对)',
    openfoam: 'OpenFOAM case 目录',
    elmer: '.sif (Elmer 求解器输入文件)',
  }
  return hints[selectedWorker.value] || '查看求解器文档确认输入格式'
})

const fileCheckHint = computed(() => {
  if (uploadedInputFiles.value.length === 0) return null
  const fileNames = uploadedInputFiles.value.map((f) => f.name.toLowerCase())
  const checks: Record<string, { ext: string[]; label: string }> = {
    calculix: { ext: ['.inp'], label: 'CalculiX' },
    freecad: { ext: ['.fcstd', '.step', '.stp'], label: 'FreeCAD' },
    prepomax: { ext: ['.pmx'], label: 'PrePoMax' },
    'prepomax-regenerate': { ext: ['.pmx', '.step', '.stp'], label: 'PrePoMax Regenerate' },
    openfoam: { ext: [], label: 'OpenFOAM' },
    elmer: { ext: ['.sif'], label: 'Elmer' },
  }
  const check = checks[selectedWorker.value]
  if (!check) return null
  if (check.ext.length === 0)
    return `已检测到 ${uploadedInputFiles.value.length} 个文件，请确认 ${check.label} case 目录完整`
  const matched = uploadedInputFiles.value.find((f) =>
    check.ext.some((ext) => f.name.toLowerCase().endsWith(ext))
  )
  if (matched) return `已检测到 ${matched.name}，${check.label} 可直接提交`
  return `缺少 ${check.ext.join(' 或 ')} 文件，请检查`
})

const selectedWorker = ref('calculix')
const nodeMode = ref('local')

watch(nodeMode, (mode) => {
  if (mode === 'local') {
    selectedComputeNode.value = 'local'
  }
})
const jobName = ref(`结构验证_${new Date().toISOString().slice(0, 10)}`)
const customArgs = ref('')
const timeoutMinutes = ref('')
const jobMode = ref<JobMode>('single')
const uploadMode = ref<UploadMode>('single-file')
const singleInputFormat = ref('.inp')
const instanceFolderName = ref('')
const uploadedInputFiles = ref<UploadedInputFile[]>([])
const savedJobTemplates = ref<JobTemplate[]>([])
const pipelineSteps = ref<PipelineStep[]>([
  { id: 'step-freecad', launcher: 'FreeCAD', inputName: 'model.FCStd' },
  { id: 'step-prepomax', launcher: 'PrePoMax', inputName: 'mesh_definition.pm' },
  { id: 'step-calculix', launcher: 'CalculiX', inputName: 'job.inp' },
  { id: 'step-archive', launcher: '归档', inputName: 'result bundle' },
])
const queueItems = ref<QueueItem[]>([])
const isFileDragActive = ref(false)
const showSolverConfig = ref(false)

const finishedRunCount = computed(() => archivedRuns.value.filter((run) => run.status === 'finished').length)
const failedRunCount = computed(() => archivedRuns.value.filter((run) => run.status === 'failed').length)
const activeRunCount = computed(
  () =>
    archivedRuns.value.filter((run) =>
      ['created', 'running', 'queued', 'submitting', 'canceling'].includes(run.status)
    ).length
)
const latestRun = computed(() => archivedRuns.value[0] ?? null)

const remoteOutputLines = computed(() =>
  remoteStatus.value.output
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
)

const remoteOutputLastLine = computed(() => {
  const lines = remoteOutputLines.value
  return lines.length > 0 ? lines[lines.length - 1] : ''
})

const nodeHealth = computed(() => ({
  label: remoteStatus.value.running ? '节点运行中' : remoteStatus.value.connected ? '节点在线' : '节点待测试',
  detail: remoteStatus.value.message || remoteLabel.value,
  tone: remoteStatus.value.running ? 'pending' : remoteStatus.value.connected ? 'online' : 'offline',
}))

const selectedSolverDefinition = computed(() =>
  solvers.value.find((solver) => solver.alias === selectedWorker.value)
)

const selectedWorkerReady = computed(() => Boolean(selectedSolverDefinition.value))

const selectedWorkerLabel = computed(() => {
  const configured = selectedSolverDefinition.value
  const fallback = workerOptions.find((worker) => worker.alias === selectedWorker.value)
  return configured?.label || fallback?.label || selectedWorker.value
})

const workstationReady = computed(() => status.value.connected && selectedWorkerReady.value)

const selectedInputs = computed(() => selectedRun.value?.input_files ?? [])

const recentRuns = computed(() => archivedRuns.value.slice(0, 6))

const mainInputFile = computed(() => uploadedInputFiles.value[0]?.name || '尚未选择输入文件')

const pipelineSummary = computed(() => pipelineSteps.value.map((step) => step.launcher).join(' -> '))

const latestRunStatus = computed(() => {
  if (!latestRun.value) return '暂无运行记录'
  return `${latestRun.value.status} / ${latestRun.value.solver}`
})

const taskProgressCard = computed(() => {
  const active = queueItems.value.find((item) => item.status === 'running' || item.status === 'queued')
  if (active) {
    return {
      label: active.stage,
      progress: active.progress,
      detail: active.title,
      tone: active.status === 'running' ? 'tone-amber' : 'tone-purple',
    }
  }
  if (remoteStatus.value.running) {
    return {
      label: '求解器运行中',
      progress: 50,
      detail: remoteStatus.value.message || '等待输出…',
      tone: 'tone-amber',
    }
  }
  return {
    label: '空闲',
    progress: 0,
    detail: '无活跃任务',
    tone: 'tone-blue',
  }
})

const canSubmitConfiguredJob = computed(
  () => status.value.connected && selectedWorkerReady.value && !remoteStatus.value.running
)

const dashboardMetrics = computed(() => [
  {
    label: '运行档案',
    value: archivedRuns.value.length,
    detail: `${finishedRunCount.value} 个完成，${failedRunCount.value} 个失败`,
    tone: 'cyan',
  },
  {
    label: '工作器入口',
    value: solvers.value.length || toolchainItems.value.length,
    detail: selectedWorkerReady.value ? `${selectedWorkerLabel.value} 已配置` : '等待侧车配置',
    tone: 'purple',
  },
  {
    label: '当前活动',
    value: activeRunCount.value,
    detail: latestRun.value ? `最近：${latestRun.value.solver}` : '暂无运行记录',
    tone: remoteStatus.value.running ? 'amber' : status.value.connected ? 'green' : 'red',
  },
])

function statusTone(statusText: string) {
  if (statusText === 'finished') return 'online'
  if (statusText === 'running' || statusText === 'queued' || statusText === 'submitting') return 'pending'
  if (statusText === 'failed' || statusText === 'canceled') return 'offline'
  return 'neutral'
}

function formatDate(value?: string | null) {
  if (!value) return '暂无'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function metricValue(run: RunArchive | null, key: 'max_displacement_mm' | 'max_von_mises_mpa') {
  const value = run?.summary?.metrics?.[key]
  return typeof value === 'number' ? value.toFixed(3) : '暂无'
}

function artifactSummary(run: RunArchive | null) {
  const artifacts = run?.artifacts?.filter((artifact) => artifact !== 'artifacts/result_summary.json') ?? []
  if (artifacts.length === 0) return '暂无产物'
  return artifacts.slice(0, 3).join(' / ')
}

function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function mapQueueTone(statusText: QueueItem['status']) {
  if (statusText === 'finished') return 'online'
  if (statusText === 'running' || statusText === 'queued') return 'pending'
  if (statusText === 'failed') return 'offline'
  return 'neutral'
}

function queueStageByMode(mode: JobMode, message: string) {
  if (message.includes('归档')) return '正在归档'
  if (message.includes('后处理')) return '正在后处理'
  if (mode === 'pipeline') return '正在工作流执行'
  return '正在工作器运行'
}

function createQueueItem(mode: JobMode) {
  const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
  const title =
    mode === 'single'
      ? `${jobName.value || '未命名作业'} / ${selectedWorkerLabel.value}`
      : `${jobName.value || '未命名作业'} / ${pipelineSummary.value}`
  const inputMode =
    uploadMode.value === 'single-file' ? '单文件' : `文件夹 ${instanceFolderName.value || '未选择'}`
  const item: QueueItem = {
    id,
    title,
    mode,
    progress: 8,
    status: 'queued',
    stage: '排队中',
    logOpen: false,
    logs: [`[queue] 已提交任务，输入模式：${inputMode}`],
    createdAt: new Date().toISOString(),
  }
  queueItems.value = [item, ...queueItems.value].slice(0, 8)
  return item.id
}

function updateQueueItem(id: string, patch: Partial<QueueItem>, logLine?: string) {
  const index = queueItems.value.findIndex((item) => item.id === id)
  if (index < 0) return
  const current = queueItems.value[index]
  queueItems.value[index] = {
    ...current,
    ...patch,
    logs: logLine ? [...current.logs, logLine] : current.logs,
  }
}

function toggleQueueLog(id: string) {
  const index = queueItems.value.findIndex((item) => item.id === id)
  if (index < 0) return
  queueItems.value[index] = { ...queueItems.value[index], logOpen: !queueItems.value[index].logOpen }
}

function acceptInputFiles(files: FileList | null) {
  if (!files || files.length === 0) return
  uploadedInputFiles.value = Array.from(files).map((file) => ({
    name: file.name,
    size: file.size,
  }))
  appendLog(`[upload] 已选择 ${uploadedInputFiles.value.length} 个输入文件。`)
}

function handleFileDrop(event: DragEvent) {
  isFileDragActive.value = false
  acceptInputFiles(event.dataTransfer?.files ?? null)
}

function handleFileInputChange(event: Event) {
  const input = event.target as HTMLInputElement
  if (uploadMode.value === 'folder') {
    const firstPath = (input.files?.[0] as File & { webkitRelativePath?: string })?.webkitRelativePath || ''
    instanceFolderName.value = firstPath.split('/')[0] || ''
  }
  acceptInputFiles(input.files)
}

function saveCurrentTemplate() {
  const template: JobTemplate = {
    id: `${Date.now()}`,
    name: jobName.value || `${selectedWorkerLabel.value} 模板`,
    worker: selectedWorker.value,
    computeNode: selectedComputeNode.value,
    nodeMode: nodeMode.value,
    files: [...uploadedInputFiles.value],
    savedAt: new Date().toISOString(),
  }
  savedJobTemplates.value = [template, ...savedJobTemplates.value].slice(0, 6)
  appendLog(`[template] 已保存模板：${template.name}`)
}

function applyTemplate(template: JobTemplate) {
  jobName.value = template.name
  selectedWorker.value = template.worker
  selectedComputeNode.value = template.computeNode
  nodeMode.value = template.nodeMode
  uploadedInputFiles.value = [...template.files]
  appendLog(`[template] 已载入模板：${template.name}`)
}

function submitConfiguredJob() {
  if (!selectedWorkerReady.value) {
    appendLog(`[solver] ${selectedWorkerLabel.value} 尚未在配置中可用。`)
    return
  }
  if (!status.value.connected || remoteStatus.value.running) {
    appendLog('[queue] 当前无法提交，请先确认侧车连通且没有正在运行的任务。')
    return
  }

  const queueId = createQueueItem(jobMode.value)
  updateQueueItem(
    queueId,
    { status: 'running', progress: 30, stage: '正在启动' },
    '[queue] 正在初始化运行环境'
  )
  if (jobMode.value === 'single') {
    remoteRuns.startSolverRunAction(selectedWorker.value)
  } else {
    remoteRuns.startFreecadPrepomaxWorkflowAction()
  }
}

watch(solvers, (list) => {
  if (list.length > 0 && !list.find((s) => s.alias === selectedWorker.value)) {
    selectedWorker.value = list[0].alias
  }
})

watch(
  () => remoteStatus.value.message,
  (message) => {
    const active = queueItems.value.find((item) => item.status === 'running')
    if (!active || !message) return
    const progress = Math.min(88, active.progress + 6)
    updateQueueItem(
      active.id,
      { progress, stage: queueStageByMode(active.mode, message) },
      `[runtime] ${message}`
    )
  }
)

watch(
  () => remoteStatus.value.running,
  (running) => {
    const active = queueItems.value.find((item) => item.status === 'running')
    if (!active || running) return
    const failed = remoteStatus.value.message.includes('失败')
    updateQueueItem(
      active.id,
      {
        status: failed ? 'failed' : 'finished',
        progress: 100,
        stage: failed ? '已失败' : '已完成',
      },
      failed ? '[queue] 任务结束：失败' : '[queue] 任务结束：完成'
    )
  }
)

const loadRunsAction = async () => {
  const result = await api.listRuns()
  archivedRuns.value = result.data.runs ?? []
  if (!selectedRun.value && archivedRuns.value.length > 0) {
    await selectRunAction(archivedRuns.value[0].run_id)
  }
}

const selectRunAction = async (runId: string) => {
  const result = await api.getRun(runId)
  selectedRun.value = result.data
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
      message: '本地侧车服务连接成功。',
    }
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
    appendLog(`[connect] ${err}`)
  }
}

const startSidecarAction = async () => {
  try {
    await invoke('start_sidecar')
    appendLog('[sidecar] 已请求启动侧车服务。')
    window.setTimeout(connectServerAction, 1000)
  } catch (err) {
    appendLog(`[sidecar] 启动失败：${err}`)
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
      message: '侧车服务已关闭。',
    }
    appendLog('[sidecar] 已请求关闭侧车服务。')
  } catch (err) {
    appendLog(`[sidecar] 关闭失败：${err}`)
  }
}

const refreshAllAction = async () => {
  await connectServerAction()
  await loadRunsAction()
}

const isTauriRuntime = () => {
  const internals = (
    window as unknown as {
      __TAURI_INTERNALS__?: { transformCallback?: unknown }
    }
  ).__TAURI_INTERNALS__
  return typeof internals?.transformCallback === 'function'
}

const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'F11') {
    event.preventDefault()
    if (isTauriRuntime()) {
      invoke('toggle_fullscreen')
    }
  }
}

onMounted(() => {
  if (isTauriRuntime()) {
    initSidecarListeners()
  }
  window.addEventListener('keydown', handleKeydown)
  connectServerAction()
})

onUnmounted(() => {
  if (isTauriRuntime()) {
    disposeSidecarListeners()
  }
  closeRunEventStream()
  window.removeEventListener('keydown', handleKeydown)
})

type AppView = 'composer' | 'run-detail' | 'learning-library' | 'toolchain-manager'
const currentView = ref<AppView>('composer')
const detailRunId = ref<string | null>(null)

function navigateTo(view: AppView) {
  currentView.value = view
}

function openRunDetail(runId: string) {
  detailRunId.value = runId
  currentView.value = 'run-detail'
  selectRunAction(runId)
}

function backToComposer() {
  currentView.value = 'composer'
}
</script>

<template>
  <main class="studio-shell">
    <nav class="side-nav" aria-label="主导航">
      <button
        type="button"
        class="nav-item"
        :class="{ active: currentView === 'composer' }"
        @click="navigateTo('composer')"
      >
        <span class="nav-icon" aria-hidden="true">▦</span>
        <span class="nav-label">作业区</span>
      </button>
      <button
        type="button"
        class="nav-item"
        :class="{ active: currentView === 'learning-library' }"
        @click="navigateTo('learning-library')"
      >
        <span class="nav-icon" aria-hidden="true">▤</span>
        <span class="nav-label">学习库</span>
      </button>
      <button
        type="button"
        class="nav-item"
        :class="{ active: currentView === 'toolchain-manager' }"
        @click="navigateTo('toolchain-manager')"
      >
        <span class="nav-icon" aria-hidden="true">TC</span>
        <span class="nav-label">工具链</span>
      </button>
    </nav>

    <div v-if="currentView === 'composer'" class="view-container">
      <header class="hero-panel">
      <div class="hero-copy">
        <svg class="hero-logo" width="100%" viewBox="0 0 680 200" role="img" aria-label="SimFEA Studio">
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M2 1L8 5L2 9" fill="none" stroke="#3a4252" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </marker>
          </defs>
          <rect x="40" y="20" width="600" height="160" rx="4" fill="none" stroke="#3a4252" stroke-width="0.5"/>
          <line x1="40" y1="60" x2="640" y2="60" stroke="#3a4252" stroke-width="0.5" stroke-dasharray="4,6"/>
          <line x1="40" y1="100" x2="640" y2="100" stroke="#3a4252" stroke-width="0.5" stroke-dasharray="4,6"/>
          <line x1="40" y1="140" x2="640" y2="140" stroke="#3a4252" stroke-width="0.5" stroke-dasharray="4,6"/>
          <line x1="180" y1="20" x2="180" y2="180" stroke="#3a4252" stroke-width="0.5" stroke-dasharray="4,6"/>
          <line x1="340" y1="20" x2="340" y2="180" stroke="#3a4252" stroke-width="0.5" stroke-dasharray="4,6"/>
          <line x1="500" y1="20" x2="500" y2="180" stroke="#3a4252" stroke-width="0.5" stroke-dasharray="4,6"/>
          <circle cx="40" cy="20" r="2.5" fill="#38a3ff"/>
          <circle cx="640" cy="20" r="2.5" fill="#38a3ff"/>
          <circle cx="40" cy="180" r="2.5" fill="#38a3ff"/>
          <circle cx="640" cy="180" r="2.5" fill="#38a3ff"/>
          <text x="60" y="36" font-family="Cascadia Code, Consolas, monospace" font-size="10" fill="#748295" font-weight="400">v2.0 · 2026</text>
          <text x="620" y="36" font-family="Cascadia Code, Consolas, monospace" font-size="10" fill="#748295" font-weight="400" text-anchor="end">FEA · AI · SIM</text>
          <text x="340" y="118" font-family="Microsoft YaHei, Segoe UI, Arial, sans-serif" font-size="72" font-weight="500" fill="#edf3fb" text-anchor="middle" letter-spacing="2">SimFEA</text>
          <rect x="200" y="130" width="280" height="2" rx="1" fill="#38a3ff" opacity="0.6"/>
          <text x="340" y="162" font-family="Cascadia Code, Consolas, monospace" font-size="16" font-weight="400" fill="#38a3ff" text-anchor="middle" letter-spacing="8">STUDIO</text>
          <text x="60" y="170" font-family="Cascadia Code, Consolas, monospace" font-size="9" fill="#748295" font-weight="400">SIM · FEA · ARCHIVE</text>
          <text x="620" y="170" font-family="Microsoft YaHei, Segoe UI, Arial, sans-serif" font-size="9" fill="#748295" font-weight="400" text-anchor="end">可沉淀的仿真工作台</text>
        </svg>
        <h1>仿真运行 · 证据归档 · 学习沉淀</h1>
        <p class="hero-text">
          不造求解器，只管理求解器——把每一次仿真从"跑就散"变成可回放的工程证据。
        </p>
        <div class="hero-actions">
          <button type="button" class="primary-action" @click="refreshAllAction">刷新工作台</button>
          <button type="button" @click="startSidecarAction" :disabled="status.connected">启动侧车</button>
          <button type="button" @click="shutdownSidecarAction" :disabled="!status.connected">关闭侧车</button>
        </div>
      </div>
    </header>

    <section class="status-section" aria-label="系统状态与指标">
      <div class="status-left">
        <section class="panel status-panel status-panel-compact" aria-labelledby="status-title">
        <div class="section-heading">
          <p class="eyebrow">Status</p>
          <h2 id="status-title">状态区</h2>
        </div>

        <div class="status-stack">
          <article class="status-tile" :class="status.connected ? 'online' : 'offline'">
            <span>系统状态</span>
            <strong>{{ status.connected ? '侧车已连接' : '侧车离线' }}</strong>
            <p>{{ status.connected ? `${status.host} / pid ${status.pid}` : status.message }}</p>
          </article>
          <article class="status-tile" :class="workstationReady ? 'online' : 'offline'">
            <span>工作器状态</span>
            <strong>{{ workstationReady ? '已就绪' : '待配置' }}</strong>
            <p>{{ selectedWorkerLabel }} / {{ selectedWorkerReady ? '已在侧车配置中' : '未发现可用配置' }}</p>
          </article>
        </div>
      </section>

        <article v-if="latestRun" class="latest-run-card">
          <button type="button" class="primary-action latest-run-action" @click="openRunDetail(latestRun.run_id)">
            查看证据
          </button>
          <div class="latest-run-info">
            <span>最近运行</span>
            <strong>{{ latestRun.case_name }}</strong>
            <p>{{ latestRun.solver }} / {{ formatDate(latestRun.created_at) }}</p>
          </div>
        </article>
      </div>

      <section class="health-board" aria-label="系统健康状态">
        <article
          v-for="metric in dashboardMetrics"
          :key="metric.label"
          class="metric-card"
          :class="[`tone-${metric.tone}`, metric.label === '工作器入口' ? 'metric-card-clickable' : '']"
          @click="metric.label === '工作器入口' ? navigateTo('toolchain-manager') : undefined"
        >
          <span>{{ metric.label }}</span>
          <strong>{{ metric.value }}</strong>
          <p>{{ metric.detail }}</p>
        </article>

        <article class="metric-card task-progress-card" :class="taskProgressCard.tone">
          <span>实时任务</span>
          <strong>{{ taskProgressCard.label }}</strong>
          <div class="task-mini-progress">
            <div class="task-mini-progress-fill" :style="{ width: `${taskProgressCard.progress}%` }" />
          </div>
          <p>{{ taskProgressCard.detail }}</p>
        </article>
      </section>
    </section>

    <div v-if="remoteStatus.running" class="run-progress-bar" aria-label="求解器运行进度">
      <div class="progress-bar-strip" />
      <div class="progress-bar-info">
        <span class="progress-bar-label">{{ remoteStatus.message }}</span>
        <span v-if="remoteOutputLastLine" class="progress-bar-detail">{{ remoteOutputLastLine }}</span>
      </div>
    </div>

    <section class="job-shell-grid" aria-label="作业配置工作台">
      <section class="panel job-config-panel" aria-labelledby="job-config-title">
        <div class="section-heading">
          <p class="eyebrow">Job Setup</p>
          <h2 id="job-config-title">作业配置区</h2>
          <p>选择工作器、计算节点和输入文件，形成一次可以保存、复用、提交的仿真作业。</p>
        </div>

        <div class="config-card">
          <div class="toggle-stack">
            <div class="mode-toggle" role="tablist" aria-label="作业模式">
              <button type="button" :class="{ active: jobMode === 'single' }" @click="jobMode = 'single'">单求解器模式</button>
              <button type="button" :class="{ active: jobMode === 'pipeline' }" @click="jobMode = 'pipeline'">启动链模式</button>
            </div>

            <div class="mode-toggle" role="tablist" aria-label="上传模式">
              <button type="button" :class="{ active: uploadMode === 'single-file' }" @click="uploadMode = 'single-file'">单个文件</button>
              <button type="button" :class="{ active: uploadMode === 'folder' }" @click="uploadMode = 'folder'">实例文件夹</button>
            </div>
          </div>

          <div v-if="jobMode === 'pipeline'" class="pipeline-steps-card">
            <span class="pipeline-label">启动链步骤</span>
            <div class="pipeline-chain">
              <div v-for="(step, idx) in pipelineSteps" :key="step.id" class="pipeline-node">
                <span class="pipeline-node-icon">{{ idx + 1 }}</span>
                <strong>{{ step.launcher }}</strong>
                <small>{{ step.inputName }}</small>
              </div>
            </div>
          </div>

          <div class="form-grid">
            <label class="field">
              <span>
                作业名称
                <button type="button" class="save-template-inline" @click="saveCurrentTemplate">存为模板</button>
              </span>
              <input v-model="jobName" type="text" placeholder="例如：cantilever_modal_001" />
            </label>

            <label v-if="jobMode === 'single'" class="field">
              <span>工作器</span>
              <select v-model="selectedWorker">
                <option v-if="solvers.length === 0" v-for="worker in workerOptions" :key="worker.alias" :value="worker.alias">
                  {{ worker.label }} / {{ worker.kind }}
                </option>
                <option v-for="solver in solvers" :key="solver.alias" :value="solver.alias">
                  {{ solver.label }} / {{ solver.kind }}
                </option>
              </select>
              <small v-if="solvers.length === 0" class="field-hint">尚未探测 — 显示预设列表</small>
            </label>

            <label class="field">
              <span>节点类型</span>
              <select v-model="nodeMode">
                <option v-for="mode in nodeModeOptions" :key="mode.value" :value="mode.value">
                  {{ mode.label }}
                </option>
              </select>
            </label>

            <label v-if="nodeMode !== 'local'" class="field">
              <span>计算节点</span>
              <select
                v-model="selectedComputeNode"
                :disabled="computeNodes.length === 0 || remoteStatus.running"
              >
                <option v-for="node in filteredComputeNodes" :key="node.alias" :value="node.alias">
                  {{ node.label }} / {{ node.alias }}
                </option>
              </select>
            </label>
          </div>

          <label
            class="drop-zone"
            :class="{ active: isFileDragActive }"
            @dragenter.prevent="isFileDragActive = true"
            @dragover.prevent="isFileDragActive = true"
            @dragleave.prevent="isFileDragActive = false"
            @drop.prevent="handleFileDrop"
          >
            <input type="file" multiple :webkitdirectory="uploadMode === 'folder' ? 'true' : undefined" @change="handleFileInputChange" />
            <span class="drop-icon">INP</span>
            <strong>拖拽输入文件到这里</strong>
            <p>支持主文件和子文件一起放入；当前选择：{{ mainInputFile }}</p>
          </label>

          <div v-if="uploadedInputFiles.length" class="uploaded-list" aria-label="已选择输入文件">
            <div v-for="file in uploadedInputFiles" :key="`${file.name}-${file.size}`">
              <span>{{ file.name }}</span>
              <small>{{ formatFileSize(file.size) }}</small>
            </div>
          </div>

          <p v-if="fileCheckHint" class="input-format-hint" :class="{ 'check-ok': fileCheckHint.includes('可直接提交') }">{{ fileCheckHint }}</p>
          <p v-else class="input-format-hint">当前 {{ selectedWorkerLabel }} 需要：{{ solverInputHint }}</p>

          <div class="form-grid compact">
            <label class="field">
              <span>自定义参数</span>
              <input v-model="customArgs" type="text" placeholder="例如：--cpus 8 --memory 16G" />
            </label>
            <label class="field">
              <span>超时时间</span>
              <input v-model="timeoutMinutes" type="text" placeholder="分钟" />
            </label>
          </div>

          <div class="job-actions">
            <button type="button" @click="remoteRuns.probeRemoteNodeAction()" :disabled="!status.connected">
              测试节点
            </button>
            <button type="button" @click="remoteRuns.probeSolversAction()" :disabled="!status.connected">
              探测工作器
            </button>
            <button type="button" @click="saveCurrentTemplate">存为模板</button>
            <button
              type="button"
              class="primary-action"
              :disabled="!canSubmitConfiguredJob"
              @click="submitConfiguredJob"
            >
              提交作业
            </button>
          </div>
        </div>
      </section>

      <aside class="right-rail" aria-label="状态与模板">

        <section class="panel log-panel" aria-labelledby="log-title">
          <div class="section-heading">
            <p class="eyebrow">Live Log</p>
            <h2 id="log-title">实时日志</h2>
          </div>
          <pre class="logs-display logs-display--compact"><code>{{ logs }}</code></pre>
        </section>

        <section class="panel template-panel" aria-labelledby="template-title">
          <div class="section-heading split-heading">
            <div>
              <p class="eyebrow">Templates</p>
              <h2 id="template-title">模板列表</h2>
            </div>
            <span>{{ savedJobTemplates.length }} 个模板</span>
          </div>

          <div class="template-list">
            <button
              v-for="template in savedJobTemplates"
              :key="template.id"
              type="button"
              class="template-card"
              @click="applyTemplate(template)"
            >
              <strong>{{ template.name }}</strong>
              <span>{{ template.worker }} / {{ template.nodeMode }} / {{ template.files.length }} 个文件</span>
            </button>
            <p v-if="savedJobTemplates.length === 0" class="empty-state">
              点击“存为模板”保存当前参数配置，后续同类算例可以直接调用。
            </p>
          </div>
        </section>
      </aside>

      <section v-if="queueItems.length" class="panel queue-panel" aria-labelledby="queue-title">
        <div class="section-heading">
          <p class="eyebrow">Task Queue</p>
          <h2 id="queue-title">任务队列</h2>
        </div>
        <div class="queue-grid">
          <article
            v-for="item in queueItems"
            :key="item.id"
            class="queue-card"
            :class="`tone-${mapQueueTone(item.status)}`"
          >
            <div class="queue-head">
              <strong>{{ item.title }}</strong>
              <span class="status-pill" :class="mapQueueTone(item.status)">{{ item.status }}</span>
            </div>
            <div class="queue-progress">
              <div class="queue-progress-fill" :style="{ width: `${item.progress}%` }" />
            </div>
            <div class="queue-meta">
              <span>{{ item.stage }}</span>
              <small>{{ formatDate(item.createdAt) }}</small>
            </div>
            <button type="button" class="queue-log-toggle" @click="toggleQueueLog(item.id)">
              {{ item.logOpen ? '收起日志' : '展开日志' }}
            </button>
            <pre v-if="item.logOpen" class="queue-log"><code>{{ item.logs.join('\n') }}</code></pre>
          </article>
        </div>
      </section>

      <section class="panel evidence-section" aria-labelledby="evidence-title">
        <div class="section-heading">
          <p class="eyebrow">Run Evidence</p>
          <h2 id="evidence-title">最近运行证据区</h2>
          <p>命令、输入、日志、结果产物和本地归档集中展示，方便确认闭环是否真正跑通。</p>
        </div>

        <div class="evidence-layout">
          <div class="run-list">
            <button
              v-for="run in recentRuns"
              :key="run.run_id"
              type="button"
              class="run-card"
              :class="{ selected: selectedRun?.run_id === run.run_id }"
              @click="selectRunAction(run.run_id)"
            >
              <span class="run-title">{{ run.case_name }}</span>
              <span class="run-meta">{{ run.solver }} / {{ formatDate(run.created_at) }}</span>
              <span class="status-pill" :class="statusTone(run.status)">{{ run.status }}</span>
            </button>
            <p v-if="recentRuns.length === 0" class="empty-state">暂无运行档案。</p>
          </div>

          <article class="evidence-detail">
            <template v-if="selectedRun">
              <div class="detail-head">
                <div>
                  <span class="eyebrow">Selected Run</span>
                  <h3>{{ selectedRun.case_name }}</h3>
                </div>
                <span class="status-pill" :class="statusTone(selectedRun.status)">{{ selectedRun.status }}</span>
              </div>
              <dl class="detail-grid">
                <div>
                  <dt>Run ID</dt>
                  <dd>{{ selectedRun.run_id }}</dd>
                </div>
                <div>
                  <dt>Runner</dt>
                  <dd>{{ selectedRun.runner }}</dd>
                </div>
                <div>
                  <dt>节点</dt>
                  <dd>{{ selectedRun.compute_node }}</dd>
                </div>
                <div>
                  <dt>退出码</dt>
                  <dd>{{ selectedRun.exit_code ?? '暂无' }}</dd>
                </div>
                <div>
                  <dt>最大位移</dt>
                  <dd>{{ metricValue(selectedRun, 'max_displacement_mm') }} mm</dd>
                </div>
                <div>
                  <dt>等效应力</dt>
                  <dd>{{ metricValue(selectedRun, 'max_von_mises_mpa') }} MPa</dd>
                </div>
              </dl>
              <div class="evidence-files">
                <div>
                  <span>输入文件</span>
                  <p>{{ selectedInputs.length ? selectedInputs.join(' / ') : '暂无输入文件' }}</p>
                </div>
                <div>
                  <span>结果产物</span>
                  <p>{{ artifactSummary(selectedRun) }}</p>
                </div>
                <div>
                  <span>本地档案</span>
                  <p>{{ selectedRun.local_archive }}</p>
                </div>
              </div>
            </template>
            <p v-else class="empty-state">选择一条运行记录后，这里会显示可复盘证据。</p>
          </article>
        </div>
      </section>

      <ResultEvidenceView
        :run="selectedRun"
        :api-base-url="apiBaseUrl"
        :report-preview="selectedRun?.learning_report ?? ''"
        :remote-output="remoteStatus.output"
      />

    </section>

      <div v-if="showSolverConfig" class="dialog-backdrop" @click.self="showSolverConfig = false">
        <div class="dialog-card solver-config-dialog">
          <div class="dialog-header">
            <strong>求解器配置详情</strong>
            <p>配置文件：{{ status.configPath || '未获取' }}</p>
          </div>
          <div class="dialog-body solver-list">
            <div v-if="solvers.length === 0 && toolchainItems.length === 0" class="empty-state">
              暂无求解器配置。请先探测工作器或检查侧车配置。
            </div>
            <article v-for="solver in solvers" :key="solver.alias" class="solver-entry">
              <div class="solver-entry-head">
                <strong>{{ solver.label }}</strong>
                <span class="tag tag-purple">{{ solver.kind }}</span>
              </div>
              <dl class="solver-entry-detail">
                <div>
                  <dt>别名</dt>
                  <dd>{{ solver.alias }}</dd>
                </div>
                <div>
                  <dt>可执行文件</dt>
                  <dd>{{ solver.executable }}</dd>
                </div>
                <div v-if="solver.description">
                  <dt>描述</dt>
                  <dd>{{ solver.description }}</dd>
                </div>
                <div>
                  <dt>产物匹配</dt>
                  <dd>{{ solver.artifact_patterns.join(', ') || '无' }}</dd>
                </div>
              </dl>
            </article>
            <article v-for="item in toolchainItems" :key="item.name" class="solver-entry">
              <div class="solver-entry-head">
                <strong>{{ item.name }}</strong>
                <span class="tag tag-neutral">{{ item.role }}</span>
              </div>
              <p class="solver-entry-status">状态：{{ item.status }}</p>
            </article>
          </div>
          <div class="dialog-actions">
            <button type="button" class="primary-action" @click="showSolverConfig = false">关闭</button>
          </div>
        </div>
      </div>
    </div>

    <RunDetailView
      v-else-if="currentView === 'run-detail'"
      :run="selectedRun"
      :api-base-url="apiBaseUrl"
      :remote-output="remoteStatus.output"
      @back="backToComposer"
      @refresh="detailRunId ? selectRunAction(detailRunId) : undefined"
    />

    <LearningLibrary
      v-else-if="currentView === 'learning-library'"
      :runs="archivedRuns"
      :api-base-url="apiBaseUrl"
      @back="backToComposer"
      @select-run="openRunDetail"
    />

    <ToolchainManager
      v-else-if="currentView === 'toolchain-manager'"
      :api="api"
      :config-path="status.configPath"
      @back="backToComposer"
    />
  </main>
</template>


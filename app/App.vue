<script setup lang="ts">
import { invoke } from '@tauri-apps/api/core'
import { computed, KeepAlive, onMounted, onUnmounted, ref, watch } from 'vue'
import { createSimfeaClient } from '@/api/simfeaClient'
import AiChatView from '@/components/AiChatView.vue'
import BenchmarkLab from '@/components/BenchmarkLab.vue'
import ChatTaskInput from '@/components/ChatTaskInput.vue'
import ConnectionStatus from '@/components/ConnectionStatus.vue'
import ExperimentLab from '@/components/ExperimentLab.vue'
import LearningLibrary from '@/components/LearningLibrary.vue'
import MethodLabView from '@/components/MethodLabView.vue'
import PropertyPanel from '@/components/PropertyPanel.vue'
import ResearchView from '@/components/ResearchView.vue'
import RunDetailView from '@/components/RunDetailView.vue'
import SolverDevView from '@/components/SolverDevView.vue'
import SystemStatus from '@/components/SystemStatus.vue'
import ToolchainManager from '@/components/ToolchainManager.vue'
import WorkflowTree from '@/components/WorkflowTree.vue'
import { useAppSettings } from '@/composables/useAppSettings'
import { useRemoteRuns } from '@/composables/useRemoteRuns'
import { useRunEvents } from '@/composables/useRunEvents'
import { useSidecarListeners } from '@/composables/useSidecarListeners'
import { useWorkflowState } from '@/composables/useWorkflowState'
import type { WorkflowSlotId, WorkflowStatus, WorkflowToolOption } from '@/composables/workflowConfig'
import {
  allTools,
  defaultToolSelections,
  downstreamOrder,
  solverToolCompat,
  toolToSolverAlias,
} from '@/composables/workflowConfig'
import type { RunArchive, ToolchainItem } from '@/types'
import { resolveApiBaseUrl } from '@/utils/apiBaseUrl'
import { formatDate } from '@/utils/date'

const configuredApiBaseUrl = import.meta.env.VITE_SIMFEA_API_BASE_URL as string | undefined
const apiBaseUrl = resolveApiBaseUrl(configuredApiBaseUrl, window.location.hostname)

interface ApiConnectionStatus {
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

const status = ref<ApiConnectionStatus>({
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

const settings = useAppSettings()
const selectedWorker = settings.selectedWorker
const nodeMode = ref('local')

watch(nodeMode, (mode) => {
  if (mode === 'local') {
    selectedComputeNode.value = 'local'
  }
})

watch(selectedComputeNode, (v) => {
  settings.selectedComputeNode.value = v
})
const jobName = ref(settings.jobName.value || `结构验证_${new Date().toISOString().slice(0, 10)}`)
watch(jobName, (v) => {
  settings.jobName.value = v
})
const customArgs = settings.customArgs
const timeoutMinutes = settings.timeoutMinutes
const jobMode = ref<JobMode>('single')
const uploadMode = ref<UploadMode>('single-file')
const {
  selectedWorkflowSlotId,
  dirtyNodes,
  enabledNodes,
  workflowToolSelection,
  toggleNodeEnabled,
  applyPreset,
  markDirty,
  clearDirtyNodes,
  buildWorkflowSolverSteps,
  buildStepsFromNode,
} = useWorkflowState()

// Init workflow tool selections from persisted settings
if (Object.keys(settings.workflowToolSelections.value).length > 0) {
  workflowToolSelection.value = { ...workflowToolSelection.value, ...settings.workflowToolSelections.value }
}
watch(
  workflowToolSelection,
  (v) => {
    settings.workflowToolSelections.value = { ...v }
  },
  { deep: true }
)

const contextMenu = ref<{ show: boolean; x: number; y: number; slotId: WorkflowSlotId | null }>({
  show: false,
  x: 0,
  y: 0,
  slotId: null,
})
const statusIcon: Record<WorkflowStatus, string> = {
  ready: '✓',
  neutral: '—',
  running: '⚡',
  blocked: '✕',
}

const instanceFolderName = ref('')
const uploadedInputFiles = ref<UploadedInputFile[]>([])
const uploadedRawFiles = ref<File[]>([])
const savedJobTemplates = ref<JobTemplate[]>([])
const pipelineSteps = ref<PipelineStep[]>([
  { id: 'step-freecad', launcher: 'FreeCAD', inputName: 'model.FCStd' },
  { id: 'step-prepomax', launcher: 'PrePoMax', inputName: 'mesh_definition.pm' },
  { id: 'step-calculix', launcher: 'CalculiX', inputName: 'job.inp' },
  { id: 'step-archive', launcher: '归档', inputName: 'result bundle' },
])
const queueItems = ref<QueueItem[]>([])

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

const MAX_RECENT_RUNS = 6
const MAX_QUEUE_ITEMS = 8
const MAX_SAVED_TEMPLATES = 6

const recentRuns = computed(() => archivedRuns.value.slice(0, MAX_RECENT_RUNS))

const mainInputFile = computed(() => uploadedInputFiles.value[0]?.name || '尚未选择输入文件')

const pipelineSummary = computed(() => pipelineSteps.value.map((step) => step.launcher).join(' -> '))

const latestRunStatus = computed(() => {
  if (!latestRun.value) return '暂无运行记录'
  return `${latestRun.value.status} / ${latestRun.value.solver}`
})

// Base tool definitions — each tool must appear here exactly once
// Solver → compatible tool ids per slot (only declare slots that DIFFER from allTools)
function buildToolsForSolver(slotId: WorkflowSlotId): WorkflowToolOption[] {
  const compatIds = solverToolCompat[selectedWorker.value]?.[slotId]
  const allSlotTools = allTools[slotId]
  if (!compatIds || compatIds.length === 0) return allSlotTools
  const idSet = new Set(compatIds)
  // Compatible tools first (in declared order), then remaining tools from allTools
  const compatTools = compatIds
    .map((id) => allSlotTools.find((t) => t.id === id))
    .filter(Boolean) as WorkflowToolOption[]
  const extras = allSlotTools.filter((t) => !idSet.has(t.id))
  return [...compatTools, ...extras]
}

// Dynamic tools — changes when solver or workerOptions change
const workflowTools = computed<Record<WorkflowSlotId, WorkflowToolOption[]>>(() => ({
  geometry: buildToolsForSolver('geometry'),
  mesh: buildToolsForSolver('mesh'),
  material: buildToolsForSolver('material'),
  boundary: buildToolsForSolver('boundary'),
  solver: buildToolsForSolver('solver'),
  post: buildToolsForSolver('post'),
  validation: buildToolsForSolver('validation'),
}))

const toolLabelMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const slotId of Object.keys(workflowTools.value) as WorkflowSlotId[]) {
    for (const tool of workflowTools.value[slotId]) {
      map[tool.id] = tool.label
    }
  }
  return map
})

// Auto-reset incompatible tool selections when solver changes
watch(selectedWorker, () => {
  const compat = solverToolCompat[selectedWorker.value]
  if (!compat) return
  const selection = { ...workflowToolSelection.value }
  let changed = false
  for (const slotId of Object.keys(compat) as WorkflowSlotId[]) {
    const compatIds = compat[slotId]
    if (!compatIds || compatIds.length === 0) continue
    const current = selection[slotId]
    if (!compatIds.includes(current)) {
      selection[slotId] = compatIds[0]
      changed = true
    }
  }
  if (changed) workflowToolSelection.value = selection
})

function selectedWorkflowTool(slotId: WorkflowSlotId) {
  const tools = workflowTools.value[slotId]
  return tools.find((tool) => tool.id === workflowToolSelection.value[slotId]) ?? tools[0]
}

function workflowStatus(slotId: WorkflowSlotId): WorkflowStatus {
  const hasFiles = uploadedInputFiles.value.length > 0

  // Solver states
  if (slotId === 'solver' && remoteStatus.value.running) return 'running'
  if (slotId === 'solver' && !selectedWorkerReady.value) return 'blocked'

  // Dependent slots: only ready when upstream is satisfied
  if (slotId === 'geometry') return hasFiles ? 'ready' : 'neutral'
  if (slotId === 'mesh') return hasFiles ? 'ready' : 'neutral'
  if (slotId === 'material') return hasFiles ? 'ready' : 'neutral'
  if (slotId === 'boundary') return hasFiles ? 'ready' : 'neutral'
  if (slotId === 'solver') return 'ready'
  if (slotId === 'post') return latestRun.value ? 'ready' : 'neutral'
  if (slotId === 'validation') return latestRun.value ? 'ready' : 'neutral'

  return 'neutral'
}

function workflowStatusLabel(slotId: WorkflowSlotId) {
  if (dirtyNodes.value.has(slotId)) return '需更新'
  return statusLabelMap[workflowStatus(slotId)] ?? '待输入'
}

const statusLabelMap: Record<WorkflowStatus, string> = {
  ready: '已就绪',
  neutral: '待输入',
  running: '运行中',
  blocked: '待配置',
}

const workflowSlots = computed<WorkflowSlotView[]>(() => [
  {
    id: 'geometry',
    order: 1,
    title: '模型/几何',
    subtitle: '输入工程模型',
    detail: uploadedInputFiles.value.length
      ? `${uploadedInputFiles.value.length} 个输入文件`
      : mainInputFile.value,
    status: workflowStatus('geometry'),
    statusLabel: workflowStatusLabel('geometry'),
    tools: workflowTools.value.geometry,
    selectedTool: selectedWorkflowTool('geometry'),
  },
  {
    id: 'mesh',
    order: 2,
    title: '网格',
    subtitle: '生成或沿用网格',
    detail: '固定槽位，工具可替换',
    status: workflowStatus('mesh'),
    statusLabel: workflowStatusLabel('mesh'),
    tools: workflowTools.value.mesh,
    selectedTool: selectedWorkflowTool('mesh'),
  },
  {
    id: 'material',
    order: 3,
    title: '材料',
    subtitle: '定义材料参数',
    detail: '材料块进入求解输入',
    status: workflowStatus('material'),
    statusLabel: workflowStatusLabel('material'),
    tools: workflowTools.value.material,
    selectedTool: selectedWorkflowTool('material'),
  },
  {
    id: 'boundary',
    order: 4,
    title: '边界条件',
    subtitle: '约束与载荷',
    detail: '约束、载荷、工况',
    status: workflowStatus('boundary'),
    statusLabel: workflowStatusLabel('boundary'),
    tools: workflowTools.value.boundary,
    selectedTool: selectedWorkflowTool('boundary'),
  },
  {
    id: 'solver',
    order: 5,
    title: '求解',
    subtitle: '运行外部求解器',
    detail: remoteStatus.value.running ? remoteStatus.value.message : latestRunStatus.value,
    status: workflowStatus('solver'),
    statusLabel: workflowStatusLabel('solver'),
    tools: workflowTools.value.solver,
    selectedTool: selectedWorkflowTool('solver'),
  },
  {
    id: 'post',
    order: 6,
    title: '后处理',
    subtitle: '转换与查看结果',
    detail: latestRun.value ? formatDate(latestRun.value.created_at) : '暂无结果',
    status: workflowStatus('post'),
    statusLabel: workflowStatusLabel('post'),
    tools: workflowTools.value.post,
    selectedTool: selectedWorkflowTool('post'),
  },
  {
    id: 'validation',
    order: 7,
    title: '验证/报告',
    subtitle: '形成可复盘证据',
    detail: latestRun.value ? '可进入 Benchmark Lab' : '等待结果',
    status: workflowStatus('validation'),
    statusLabel: workflowStatusLabel('validation'),
    tools: workflowTools.value.validation,
    selectedTool: selectedWorkflowTool('validation'),
  },
])

const selectedWorkflowSlot = computed(
  () => workflowSlots.value.find((slot) => slot.id === selectedWorkflowSlotId.value) ?? workflowSlots.value[0]
)

function updateWorkflowTool(slotId: WorkflowSlotId, event: Event) {
  const value = (event.target as HTMLSelectElement).value
  workflowToolSelection.value = { ...workflowToolSelection.value, [slotId]: value }
  if (slotId === 'solver') selectedWorker.value = value
  markDirty(slotId)
}

watch(selectedWorker, (worker) => {
  if (workflowToolSelection.value.solver !== worker) {
    workflowToolSelection.value = { ...workflowToolSelection.value, solver: worker }
  }
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

const canSubmitConfiguredJob = computed(() => {
  if (!status.value.connected || remoteStatus.value.running) return false
  if (jobMode.value === 'single') return selectedWorkerReady.value
  return true
})

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

function metricValue(run: RunArchive | null, key: 'max_displacement_mm' | 'max_von_mises_mpa') {
  const value = run?.summary?.metrics?.[key]
  return typeof value === 'number' ? value.toFixed(3) : '暂无'
}

function artifactSummary(run: RunArchive | null) {
  const artifacts = run?.artifacts?.filter((artifact) => artifact !== 'artifacts/result_summary.json') ?? []
  if (artifacts.length === 0) return '暂无产物'
  return artifacts.slice(0, 3).join(' / ')
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
  queueItems.value = [item, ...queueItems.value].slice(0, MAX_QUEUE_ITEMS)
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
  const arr = Array.from(files)
  uploadedRawFiles.value = arr
  uploadedInputFiles.value = arr.map((file) => ({
    name: file.name,
    size: file.size,
  }))
  markDirty('geometry')
  appendLog(`[upload] 已选择 ${uploadedInputFiles.value.length} 个输入文件。`)
}

function handleFileDrop(event: DragEvent) {
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
  savedJobTemplates.value = [template, ...savedJobTemplates.value].slice(0, MAX_SAVED_TEMPLATES)
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

function handleNodeContextMenu(slotId: WorkflowSlotId, event: MouseEvent) {
  event.preventDefault()
  contextMenu.value = { show: true, x: event.clientX, y: event.clientY, slotId }
}

function closeContextMenu() {
  contextMenu.value = { show: false, x: 0, y: 0, slotId: null }
}

function switchNodeTool(slotId: WorkflowSlotId, toolId: string) {
  workflowToolSelection.value = { ...workflowToolSelection.value, [slotId]: toolId }
  markDirty(slotId)
  closeContextMenu()
}

function updateNode(slotId: WorkflowSlotId) {
  closeContextMenu()
  if (!status.value.connected || remoteStatus.value.running) {
    appendLog('[update] 当前无法执行，请确认侧车连通且没有正在运行的任务。')
    return
  }
  const steps = buildStepsFromNode(slotId)
  if (steps.length === 0) {
    appendLog('[update] 选中的节点及其下游没有可执行步骤。')
    return
  }
  appendLog(`[update] 增量更新: ${steps.join(' -> ')}`)
  clearDirtyNodes()
  remoteRuns.startCustomWorkflowAction(steps)
}

function resetNodeTool(slotId: WorkflowSlotId) {
  switchNodeTool(slotId, defaultToolSelections[slotId])
}

function removeInputFile(name: string) {
  uploadedInputFiles.value = uploadedInputFiles.value.filter((f) => f.name !== name)
  uploadedRawFiles.value = uploadedRawFiles.value.filter((f) => f.name !== name)
  appendLog(`[upload] 已移除文件：${name}`)
}

function handleTreeKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    const slotOrder: WorkflowSlotId[] = [
      'geometry',
      'mesh',
      'material',
      'boundary',
      'solver',
      'post',
      'validation',
    ]
    const currentIdx = slotOrder.indexOf(selectedWorkflowSlotId.value)
    let nextIdx: number
    if (event.key === 'ArrowDown') {
      nextIdx = currentIdx < slotOrder.length - 1 ? currentIdx + 1 : 0
    } else {
      nextIdx = currentIdx > 0 ? currentIdx - 1 : slotOrder.length - 1
    }
    selectedWorkflowSlotId.value = slotOrder[nextIdx]
  }
}

function handleTaskTranslated(config: {
  solver: string
  caseName: string
  explanation: string
  suggestedParams: Record<string, string>
}) {
  if (solvers.value.find((s) => s.alias === config.solver)) {
    selectedWorker.value = config.solver
  }
  if (config.caseName) {
    jobName.value = config.caseName
  }
  appendLog(`[ai] ${config.explanation}`)
}

// Preflight check
const preflightRunning = ref(false)
const preflightResult = ref<Record<string, unknown> | null>(null)
const preflightError = ref('')

async function runPreflightCheck() {
  preflightRunning.value = true
  preflightResult.value = null
  preflightError.value = ''
  try {
    // Read file content from uploaded file, or use solver default
    let content = ''
    if (uploadedRawFiles.value.length > 0) {
      content = await uploadedRawFiles.value[0].text()
    } else {
      content = getDefaultInpContent()
    }
    const resp = await fetch(`${apiBaseUrl}/v1/preflight`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    })
    const j = await resp.json()
    if (resp.ok) {
      preflightResult.value = j.data as Record<string, unknown>
    } else {
      preflightError.value = (j.detail as string) || '检查失败'
    }
  } catch (err) {
    preflightError.value = String(err)
  } finally {
    preflightRunning.value = false
  }
}

function getDefaultInpContent(): string {
  // Return the default cantilever template from the selected solver
  const solver = solvers.value.find((s) => s.alias === selectedWorker.value)
  // The solver's input_files template is not exposed through the public API
  // Use a basic CalculiX template
  return `*HEADING
Preflight Check
*NODE, NSET=Nall
1, 0., 0., 0.
2, 100., 0., 0.
*ELEMENT, TYPE=B31, ELSET=beam
1, 1, 2
*MATERIAL, NAME=steel
*ELASTIC
210000., 0.3
*BEAM SECTION, ELSET=beam, MATERIAL=steel, SECTION=RECT
20., 20.
0., 0., 1.
*BOUNDARY
1, 1, 6
*STEP
*STATIC
*CLOAD
2, 2, -100.
*NODE FILE
U
*EL FILE, ELSET=beam
S
*END STEP
`
}

function submitConfiguredJob() {
  if (!status.value.connected || remoteStatus.value.running) {
    appendLog('[queue] 当前无法提交，请先确认侧车连通且没有正在运行的任务。')
    return
  }
  if (jobMode.value === 'single' && !selectedWorkerReady.value) {
    appendLog(`[solver] ${selectedWorkerLabel.value} 尚未在配置中可用。`)
    return
  }

  const queueId = createQueueItem(jobMode.value)
  updateQueueItem(
    queueId,
    { status: 'running', progress: 30, stage: '正在启动' },
    '[queue] 正在初始化运行环境'
  )
  if (jobMode.value === 'single') {
    clearDirtyNodes()
    remoteRuns.startSolverRunAction(selectedWorker.value)
  } else {
    const steps = buildWorkflowSolverSteps()
    appendLog(`[workflow] 自定义工作流 ${steps.length} 步: ${steps.join(' -> ')}`)
    clearDirtyNodes()
    remoteRuns.startCustomWorkflowAction(steps)
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

const connectServerAction = async (retries = 5, delayMs = 1000) => {
  for (let attempt = 1; attempt <= retries; attempt++) {
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
      // Restore persisted compute node if available
      const savedNode = settings.selectedComputeNode.value
      if (savedNode && computeNodes.value.find((n) => n.alias === savedNode)) {
        selectedComputeNode.value = savedNode
      }
      remoteRuns.setSolvers(result.data.solvers ?? [])
      toolchainItems.value = result.data.toolchain ?? []
      await loadRunsAction()
      return
    } catch (err) {
      if (attempt < retries) {
        appendLog(`[connect] 尝试 ${attempt}/${retries} 失败，${delayMs / 1000}s 后重试…`)
        await new Promise((r) => setTimeout(r, delayMs))
      } else {
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

type AppView =
  | 'composer'
  | 'run-detail'
  | 'learning-library'
  | 'method-lab'
  | 'ai-chat'
  | 'experiment'
  | 'research'
  | 'toolchain-manager'
  | 'benchmark-lab'
  | 'solver-dev'
const currentView = ref<AppView>((settings.lastView.value as AppView) || 'composer')
watch(currentView, (v) => {
  settings.lastView.value = v
})
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
        <span class="nav-icon" aria-hidden="true">⚙</span>
        <span class="nav-label">作业</span>
      </button>
      <button
        type="button"
        class="nav-item"
        :class="{ active: currentView === 'learning-library' }"
        @click="navigateTo('learning-library')"
      >
        <span class="nav-icon" aria-hidden="true">📚</span>
        <span class="nav-label">学习</span>
      </button>
      <button
        type="button"
        class="nav-item"
        :class="{ active: currentView === 'method-lab' }"
        @click="navigateTo('method-lab')"
      >
        <span class="nav-icon" aria-hidden="true">M</span>
        <span class="nav-label">方法</span>
      </button>
      <button
        type="button"
        class="nav-item"
        :class="{ active: currentView === 'ai-chat' }"
        @click="navigateTo('ai-chat')"
      >
        <span class="nav-icon" aria-hidden="true">AI</span>
        <span class="nav-label">问答</span>
      </button>
      <button
        type="button"
        class="nav-item"
        :class="{ active: currentView === 'experiment' }"
        @click="navigateTo('experiment')"
      >
        <span class="nav-icon" aria-hidden="true">⟨⟩</span>
        <span class="nav-label">实验</span>
      </button>
      <button
        type="button"
        class="nav-item"
        :class="{ active: currentView === 'research' }"
        @click="navigateTo('research')"
      >
        <span class="nav-icon" aria-hidden="true">R</span>
        <span class="nav-label">研究</span>
      </button>
      <button
        type="button"
        class="nav-item"
        :class="{ active: currentView === 'benchmark-lab' }"
        @click="navigateTo('benchmark-lab')"
      >
        <span class="nav-icon" aria-hidden="true">⊞</span>
        <span class="nav-label">基准</span>
      </button>
      <button
        type="button"
        class="nav-item"
        :class="{ active: currentView === 'solver-dev' }"
        @click="navigateTo('solver-dev')"
      >
        <span class="nav-icon" aria-hidden="true">∫</span>
        <span class="nav-label">求解器</span>
      </button>
      <button
        type="button"
        class="nav-item"
        :class="{ active: currentView === 'toolchain-manager' }"
        @click="navigateTo('toolchain-manager')"
      >
        <span class="nav-icon" aria-hidden="true">⚡</span>
        <span class="nav-label">工具</span>
      </button>
    </nav>

    <KeepAlive>
      <div v-if="currentView === 'composer'" class="view-container workbench-view">
      <header class="workbench-topbar">
        <div class="workbench-titlebar">
          <div class="app-mark" aria-hidden="true">SF</div>
          <span>SimFEA Studio</span>
          <span class="topbar-status" :class="status.connected ? 'online' : 'offline'">{{ status.connected ? '已连接' : '离线' }}</span>
        </div>
        <div class="workbench-commandbar" aria-label="工作台工具栏">
          <span class="topbar-status" :class="status.connected ? 'online' : 'offline'">{{ status.connected ? '● 已连接' : '○ 离线' }}</span>
        </div>
      </header>

      <ChatTaskInput
        :api-base-url="apiBaseUrl"
        :disabled="remoteStatus.running"
        @task-translated="handleTaskTranslated"
      />

      <div v-if="remoteStatus.running" class="run-progress-bar" aria-label="求解器运行进度">
        <div class="progress-bar-strip" />
        <div class="progress-bar-info">
          <span class="progress-bar-label">{{ remoteStatus.message }}</span>
          <span v-if="remoteOutputLastLine" class="progress-bar-detail">{{ remoteOutputLastLine }}</span>
        </div>
      </div>

      <section class="workbench-layout" aria-label="SimFEA 项目原理图工作台">
        <WorkflowTree
          :workflow-slots="workflowSlots"
          :selected-workflow-slot-id="selectedWorkflowSlotId"
          :enabled-nodes="enabledNodes"
          :dirty-nodes="dirtyNodes"
          :uploaded-input-files="uploadedInputFiles"
          :main-input-file="mainInputFile"
          :file-check-hint="fileCheckHint"
          :active-compute-node-label="activeComputeNodeLabel"
          :workflow-tools="workflowTools"
          :workflow-tool-selection="workflowToolSelection"
          :context-menu="contextMenu"
          @select-slot="selectedWorkflowSlotId = $event"
          @toggle-node="toggleNodeEnabled"
          @apply-preset="applyPreset"
          @tree-keydown="handleTreeKeydown"
          @context-menu="handleNodeContextMenu"
          @files-dropped="handleFileDrop"
          @files-selected="handleFileInputChange"
          @remove-file="removeInputFile"
          @close-context-menu="closeContextMenu"
          @switch-tool="switchNodeTool"
          @update-node="updateNode"
          @reset-tool="resetNodeTool"
        />

        <PropertyPanel
          :job-name="jobName"
          :selected-workflow-slot="selectedWorkflowSlot"
          :workflow-tool-selection="workflowToolSelection"
          :selected-worker="selectedWorker"
          :solvers="solvers"
          :worker-options="workerOptions"
          :compute-nodes="computeNodes"
          :selected-compute-node="selectedComputeNode"
          :remote-running="remoteStatus.running"
          :status-connected="status.connected"
          :custom-args="customArgs"
          :timeout-minutes="timeoutMinutes"
          :uploaded-input-files="uploadedInputFiles"
          :file-check-hint="fileCheckHint"
          @update:job-name="jobName = $event"
          @update-tool="updateWorkflowTool"
          @update:selected-worker="selectedWorker = $event"
          @update:selected-compute-node="selectedComputeNode = $event"
          @update:custom-args="customArgs = $event"
          @update:timeout-minutes="timeoutMinutes = $event"
          @click="closeContextMenu"
        />
      </section>

      <!-- Action bar: preflight + submit -->
      <div class="action-bar">
        <ConnectionStatus :connected="status.connected" :label="status.connected ? '侧车已连接' : '侧车离线'" @reconnect="connectServerAction()" />
        <span class="action-worker">{{ selectedWorkerLabel }} · {{ activeComputeNodeLabel }}</span>
        <button
          type="button"
          class="action-preflight"
          :disabled="!status.connected || preflightRunning"
          @click="runPreflightCheck"
        >
          {{ preflightRunning ? '检查中…' : '预检查' }}
        </button>
        <button
          type="button"
          class="action-submit"
          :disabled="!canSubmitConfiguredJob"
          @click="submitConfiguredJob"
        >
          提交作业
        </button>
      </div>

      <!-- Preflight result -->
      <div v-if="preflightResult || preflightError" class="preflight-result" :class="preflightResult ? (preflightResult.status as string) : 'error'">
        <div class="pf-head">
          <span v-if="preflightResult" class="pf-status" :class="preflightResult.status as string">
            {{ preflightResult.status === 'PASS' ? '✓ 通过' : preflightResult.status === 'BLOCKED' ? '✕ 阻塞' : '⚠ 警告' }}
          </span>
          <span v-if="preflightError" class="pf-status error">✕ 错误</span>
          <button type="button" class="pf-close" @click="preflightResult = null; preflightError = ''">×</button>
        </div>
        <p v-if="preflightError" class="pf-err-msg">{{ preflightError }}</p>
        <div v-if="preflightResult" class="pf-summary">
          <span v-if="(preflightResult.summary as Record<string,number>)?.total === 0" class="pf-clean">未发现任何问题，可以提交求解。</span>
          <span v-else>
            共 {{ (preflightResult.summary as Record<string,number>)?.total }} 个问题：
            <em class="pf-sev-error" v-if="(preflightResult.summary as Record<string,number>)?.error">错误 {{ (preflightResult.summary as Record<string,number>)?.error }}</em>
            <em class="pf-sev-warn" v-if="(preflightResult.summary as Record<string,number>)?.warning">警告 {{ (preflightResult.summary as Record<string,number>)?.warning }}</em>
          </span>
        </div>
        <div v-if="preflightResult && (preflightResult.issues as unknown[]).length" class="pf-issues">
          <div v-for="(issue, i) in (preflightResult.issues as Record<string,unknown>[])" :key="i" class="pf-issue" :class="'sev-' + (issue.severity as string).toLowerCase()">
            <span class="pf-issue-sev">{{ issue.severity }}</span>
            <span class="pf-issue-rule">{{ issue.rule_id }}</span>
            <span class="pf-issue-msg">{{ issue.message }}</span>
            <span v-if="issue.location?.line" class="pf-issue-line">行 {{ issue.location.line }}</span>
          </div>
        </div>
      </div>

      <footer class="workbench-statusbar" aria-label="工作台状态">
        <SystemStatus
          :sidecar-connected="status.connected"
          :solvers-available="solvers.length"
          :runs-archived="archivedRuns.length"
        />
      </footer>
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

    <MethodLabView
      v-else-if="currentView === 'method-lab'"
      :api-base-url="apiBaseUrl"
      @back="backToComposer"
    />

    <AiChatView
      v-else-if="currentView === 'ai-chat'"
      :runs="archivedRuns"
      :api-base-url="apiBaseUrl"
      @back="backToComposer"
    />

    <ExperimentLab
      v-else-if="currentView === 'experiment'"
      :api="api"
      @back="backToComposer"
    />

    <ResearchView
      v-else-if="currentView === 'research'"
      :api="api"
      @back="backToComposer"
    />

    <BenchmarkLab
      v-else-if="currentView === 'benchmark-lab'"
      :api-base-url="apiBaseUrl"
      @back="backToComposer"
    />

    <SolverDevView
      v-else-if="currentView === 'solver-dev'"
      :api="api"
      @back="backToComposer"
    />

    <ToolchainManager
      v-else-if="currentView === 'toolchain-manager'"
      :api="api"
      :config-path="status.configPath"
      @back="backToComposer"
    />
    </KeepAlive>
  </main>
</template>

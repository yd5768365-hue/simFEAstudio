<script setup lang="ts">
import { invoke } from '@tauri-apps/api/core'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { createSimfeaClient } from '@/api/simfeaClient'
import ResultEvidenceView from '@/components/ResultEvidenceView.vue'
import RunConfigDialog from '@/components/RunConfigDialog.vue'
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
  remoteStatus.output
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
)

const remoteOutputLastLine = computed(() => {
  const lines = remoteOutputLines.value
  return lines.length > 0 ? lines[lines.length - 1] : ''
})

const sidecarHealth = computed(() => ({
  label: status.value.connected ? '侧车在线' : '侧车离线',
  detail: status.value.connected ? `${status.value.host} / PID ${status.value.pid}` : status.value.message,
  tone: status.value.connected ? 'online' : 'offline',
}))

const nodeHealth = computed(() => ({
  label: remoteStatus.value.running ? '节点运行中' : remoteStatus.value.connected ? '节点在线' : '节点待测试',
  detail: remoteStatus.value.message || remoteLabel.value,
  tone: remoteStatus.value.running ? 'pending' : remoteStatus.value.connected ? 'online' : 'offline',
}))

const evidenceArtifacts = computed(
  () => selectedRun.value?.artifacts?.filter((artifact) => artifact !== 'artifacts/result_summary.json') ?? []
)

const selectedInputs = computed(() => selectedRun.value?.input_files ?? [])

const workflowReady = computed(
  () => hasSolver('freecad') && (hasSolver('prepomax-regenerate') || hasSolver('prepomax'))
)

const toolchainStatusCards = computed(() => {
  const solverCards = solvers.value.map((solver) => ({
    name: solver.label || solver.alias,
    role: solver.description || solver.kind || '从配置文件加载的工具链入口',
    status: solver.executable ? '已配置' : '未配置',
    tone: solverTone(solver.alias),
    meta: solver.alias,
  }))

  if (solverCards.length > 0) {
    return solverCards
  }

  return toolchainItems.value.map((item) => ({
    name: item.name,
    role: item.role,
    status: item.status,
    tone: toolchainTone(item.name),
    meta: item.name,
  }))
})

const recentRuns = computed(() => archivedRuns.value.slice(0, 6))

const dashboardMetrics = computed(() => [
  {
    label: '运行档案',
    value: archivedRuns.value.length,
    detail: `${finishedRunCount.value} 个完成，${failedRunCount.value} 个失败`,
    tone: 'blue',
  },
  {
    label: '工具链入口',
    value: solvers.value.length || toolchainItems.value.length,
    detail: workflowReady.value ? 'FreeCAD / PrePoMax 链路已配置' : '等待工具链检测',
    tone: 'purple',
  },
  {
    label: '当前活动',
    value: activeRunCount.value,
    detail: latestRun.value ? `最近：${latestRun.value.solver}` : '暂无运行记录',
    tone: remoteStatus.value.running ? 'amber' : status.value.connected ? 'green' : 'red',
  },
])

const recipes = computed(() => [
  {
    title: '几何到前处理证据链',
    subtitle: 'FreeCAD -> PrePoMax -> 归档',
    detail: '验证本地 CAD 与前处理入口，保存脚本、命令、stdout/stderr 和生成文件。',
    steps: ['FreeCAD', 'PrePoMax', 'Archive'],
    ready: status.value.connected && workflowReady.value && !remoteStatus.value.running,
    tone: 'blue',
    actionLabel: '运行链路配方',
    run: () => remoteRuns.startFreecadPrepomaxWorkflowAction(),
  },
  {
    title: '结构求解器验证',
    subtitle: 'CalculiX -> 结果摘要',
    detail: '运行结构求解器适配器，把输入文件、日志、结果和摘要写入同一个档案。',
    steps: ['INP', 'CalculiX', 'Result'],
    ready: status.value.connected && hasSolver('calculix') && !remoteStatus.value.running,
    tone: 'green',
    actionLabel: '运行 CalculiX',
    run: () => remoteRuns.startSolverRunAction('calculix'),
  },
  {
    title: '远程运行闭环',
    subtitle: '节点探测 -> 运行 -> 复盘',
    detail: '用于验证远程目录、实时事件流和本地归档，不先追求完整求解器。',
    steps: ['Probe', 'Run', 'Evidence'],
    ready: status.value.connected && Boolean(selectedComputeNode.value) && !remoteStatus.value.running,
    tone: 'amber',
    actionLabel: '运行闭环样例',
    run: () => remoteRuns.startRemoteDemoRunAction(),
  },
])

const selectedRecipeIndex = ref(0)
const selectedRecipe = computed(() => recipes.value[selectedRecipeIndex.value] ?? recipes.value[0])
const solverMode = ref<'single' | 'workflow'>('single')

const configDialog = ref({
  open: false,
  title: '',
  subtitle: '',
  inputFiles: [] as string[],
  workdir: '.simfea/runs',
  onConfirm: null as (() => void) | null,
})

const openConfigDialog = (title: string, subtitle: string, inputFiles: string[], run: () => void) => {
  configDialog.value = {
    open: true,
    title,
    subtitle,
    inputFiles,
    workdir: '.simfea/runs',
    onConfirm: run,
  }
}

const closeConfigDialog = () => {
  configDialog.value.open = false
}

const confirmConfigDialog = () => {
  configDialog.value.onConfirm?.()
  configDialog.value.open = false
}

const availableSingleSolvers = computed(() =>
  solvers.value.filter((s) => !['prepomax', 'prepomax-regenerate'].includes(s.alias))
)

const singleSolverCards = computed(() =>
  availableSingleSolvers.value.map((solver) => {
    const alias = solver.alias.toLowerCase()
    if (alias === 'freecad') {
      return {
        ...solver,
        badge: 'CAD',
        summary: '通过 FreeCAD Python API 生成几何模型，输出 FCStd 与 STEP。',
        actionLabel: '生成几何',
      }
    }
    if (alias === 'calculix') {
      return {
        ...solver,
        badge: 'Solver',
        summary: '运行 CalculiX 结构算例，归档求解日志和结果文件。',
        actionLabel: '运行求解',
      }
    }
    if (alias === 'elmer') {
      return {
        ...solver,
        badge: 'Solver',
        summary: solver.description || 'Elmer 多物理场求解器适配器。',
        actionLabel: '运行 Elmer',
      }
    }
    if (alias === 'openfoam') {
      return {
        ...solver,
        badge: 'Solver',
        summary: solver.description || 'OpenFOAM CFD 求解器适配器。',
        actionLabel: '运行 OpenFOAM',
      }
    }
    return {
      ...solver,
      badge: solver.kind || 'Solver',
      summary: solver.description || '',
      actionLabel: `运行 ${solver.label}`,
    }
  })
)

function hasSolver(alias: string) {
  return solvers.value.some((solver) => solver.alias === alias)
}

function solverTone(alias: string) {
  if (alias.includes('freecad')) return 'blue'
  if (alias.includes('prepomax')) return 'purple'
  if (alias.includes('calculix')) return 'green'
  if (alias.includes('openfoam')) return 'cyan'
  if (alias.includes('elmer')) return 'amber'
  return 'neutral'
}

function toolchainTone(name: string) {
  const normalized = name.toLowerCase()
  if (normalized.includes('freecad')) return 'blue'
  if (normalized.includes('prepomax') || normalized.includes('calculix')) return 'purple'
  if (normalized.includes('ssh') || normalized.includes('docker')) return 'green'
  return 'neutral'
}

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
</script>

<template>
  <main class="studio-shell">
    <header class="hero-panel">
      <div class="hero-copy">
        <p class="eyebrow">SimFEA Studio / OpenHPC-style Evidence Workbench</p>
        <h1>把工具链状态、工作流配方和运行证据放进一个桌面流程里</h1>
        <p class="hero-text">
          首页不再只是按钮集合，而是像工程软件栈一样显示每个组件是否可用、下一条配方能否执行、最近一次运行留下了哪些可复盘证据。
        </p>
        <div class="hero-actions">
          <button type="button" class="primary-action" @click="refreshAllAction">刷新工作台</button>
          <button type="button" @click="startSidecarAction" :disabled="status.connected">启动侧车</button>
          <button type="button" @click="shutdownSidecarAction" :disabled="!status.connected">关闭侧车</button>
        </div>
      </div>

      <section class="health-board" aria-label="系统健康状态">
        <article class="health-card" :class="sidecarHealth.tone">
          <span class="health-dot" />
          <div>
            <strong>{{ sidecarHealth.label }}</strong>
            <p>{{ sidecarHealth.detail }}</p>
          </div>
        </article>
        <article class="health-card" :class="nodeHealth.tone">
          <span class="health-dot" />
          <div>
            <strong>{{ nodeHealth.label }}</strong>
            <p>{{ nodeHealth.detail }}</p>
          </div>
        </article>
        <article
          v-for="metric in dashboardMetrics"
          :key="metric.label"
          class="metric-card"
          :class="`tone-${metric.tone}`"
        >
          <span>{{ metric.label }}</span>
          <strong>{{ metric.value }}</strong>
          <p>{{ metric.detail }}</p>
        </article>
      </section>
    </header>

    <div v-if="remoteStatus.running" class="run-progress-bar" aria-label="求解器运行进度">
      <div class="progress-bar-strip" />
      <div class="progress-bar-info">
        <span class="progress-bar-label">{{ remoteStatus.message }}</span>
        <span v-if="remoteOutputLastLine" class="progress-bar-detail">{{ remoteOutputLastLine }}</span>
      </div>
    </div>

    <section class="workspace-grid" aria-label="首页工作台">
      <section class="panel toolchain-section" aria-labelledby="toolchain-title">
        <div class="section-heading">
          <p class="eyebrow">Toolchain Status</p>
          <h2 id="toolchain-title">工具链状态区</h2>
          <p>把 FreeCAD、PrePoMax、CalculiX 和远程节点当成可检测组件，而不是散落按钮。</p>
        </div>

        <div class="node-selector-card">
          <label>
            <span>当前计算节点</span>
            <select
              v-model="selectedComputeNode"
              :disabled="computeNodes.length === 0 || remoteStatus.running"
            >
              <option v-for="node in computeNodes" :key="node.alias" :value="node.alias">
                {{ node.label }} / {{ node.alias }}
              </option>
            </select>
          </label>
          <div class="node-actions">
            <button type="button" :disabled="!status.connected" @click="remoteRuns.probeRemoteNodeAction()">
              测试节点
            </button>
            <button type="button" :disabled="!status.connected" @click="remoteRuns.probeSolversAction()">
              探测求解器
            </button>
          </div>
        </div>

        <div class="toolchain-grid">
          <article
            v-for="item in toolchainStatusCards"
            :key="item.meta"
            class="tool-card"
            :class="`tone-${item.tone}`"
          >
            <span class="tool-icon" aria-hidden="true" />
            <div>
              <strong>{{ item.name }}</strong>
              <p>{{ item.role }}</p>
              <small>{{ item.status }}</small>
            </div>
          </article>
          <p v-if="toolchainStatusCards.length === 0" class="empty-state">
            尚未读取工具链配置，点击“刷新工作台”连接侧车服务。
          </p>
        </div>
      </section>

      <section class="panel recipe-section" aria-labelledby="recipe-title">
        <div class="section-heading">
          <p class="eyebrow">Solver Control</p>
          <h2 id="recipe-title">仿真器选择入口</h2>
          <p>选择单个求解器或活动链，配置后运行。</p>
        </div>

        <div class="mode-toggle">
          <button
            type="button"
            :class="{ active: solverMode === 'single' }"
            @click="solverMode = 'single'"
          >
            单个活动器
          </button>
          <button
            type="button"
            :class="{ active: solverMode === 'workflow' }"
            @click="solverMode = 'workflow'"
          >
            活动链
          </button>
        </div>

        <div v-if="solverMode === 'single'" class="solver-card-grid">
          <article
            v-for="solver in singleSolverCards"
            :key="solver.alias"
            class="solver-card"
            :class="{ featured: ['freecad', 'calculix'].includes(solver.alias) }"
          >
            <div class="solver-card-head">
              <span class="solver-badge">{{ solver.badge }}</span>
              <strong>{{ solver.label }}</strong>
            </div>
            <p>{{ solver.summary }}</p>
            <button
              type="button"
              class="primary-action"
              :disabled="!status.connected || remoteStatus.running"
              @click="openConfigDialog(
                solver.label,
                solver.description || solver.kind || '',
                Object.keys(solver.input_files ?? {}),
                () => remoteRuns.startSolverRunAction(solver.alias)
              )"
            >
              {{ solver.actionLabel }}
            </button>
          </article>
        </div>

        <article
          v-if="solverMode === 'workflow'"
          class="recipe-card"
          :class="`tone-blue`"
        >
          <div class="recipe-head">
            <div>
              <strong>几何到前处理证据链</strong>
              <p>FreeCAD -> PrePoMax -> 归档</p>
            </div>
            <span :class="workflowReady && status.connected && !remoteStatus.running ? 'ready' : 'blocked'">
              {{ workflowReady && status.connected && !remoteStatus.running ? '可运行' : '待配置' }}
            </span>
          </div>
          <ol class="recipe-steps">
            <li>FreeCAD</li>
            <li>PrePoMax</li>
            <li>Archive</li>
          </ol>
          <p class="recipe-detail">验证本地 CAD 与前处理入口，保存脚本、命令、stdout/stderr 和生成文件。</p>
          <button
            type="button"
            class="primary-action"
            :disabled="!status.connected || !workflowReady || remoteStatus.running"
            @click="openConfigDialog(
              'FreeCAD -> PrePoMax 活动链',
              '多步求解器工作流',
              [],
              () => remoteRuns.startFreecadPrepomaxWorkflowAction()
            )"
          >
            运行链路配方
          </button>
        </article>
      </section>

      <section class="panel evidence-section" aria-labelledby="evidence-title">
        <div class="section-heading">
          <p class="eyebrow">Run Evidence</p>
          <h2 id="evidence-title">最近运行证据区</h2>
          <p>最近的命令、输入、日志和结果产物会集中显示，方便判断闭环是否真的跑起来。</p>
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

      <section class="panel log-section" aria-labelledby="log-title">
        <div class="section-heading">
          <p class="eyebrow">Live Log</p>
          <h2 id="log-title">实时日志</h2>
        </div>
        <pre class="logs-display"><code>{{ logs }}</code></pre>
      </section>
    </section>

    <RunConfigDialog
      :open="configDialog.open"
      :title="configDialog.title"
      :subtitle="configDialog.subtitle"
      :input-files="configDialog.inputFiles"
      :workdir="configDialog.workdir"
      @confirm="confirmConfigDialog()"
      @cancel="closeConfigDialog()"
    />
  </main>
</template>

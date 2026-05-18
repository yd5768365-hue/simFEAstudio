<script setup lang="ts">
import { computed } from 'vue'
import type { ComputeNodeConfig, RemoteStatus } from '@/composables/useRemoteRuns'
import type { SolverDefinition } from '@/types'

interface RemotePanelActions {
  probeRemoteNodeAction: () => void
  probeSchedulerAction: () => void
  probeSolversAction: () => void
  startRemoteDemoRunAction: () => void
  startSlurmDemoRunAction: () => void
  startSolverRunAction: (solverAlias: string) => void
  startFreecadPrepomaxWorkflowAction: () => void
  cancelRemoteRunAction: () => void
}

const props = defineProps<{
  computeNodes: ComputeNodeConfig[]
  solvers: SolverDefinition[]
  selectedComputeNode: string
  activeComputeNodeLabel: string
  remoteStatus: RemoteStatus
  connected: boolean
  actions: RemotePanelActions
}>()

const emit = defineEmits<{
  'update:selectedComputeNode': [value: string]
}>()

const solverPriority: Record<string, number> = {
  freecad: 0,
  prepomax: 1,
  'prepomax-regenerate': 2,
  calculix: 3,
  openfoam: 4,
  elmer: 5,
}

const solverCards = computed(() =>
  props.solvers
    .map((solver) => {
      const alias = solver.alias.toLowerCase()
      if (alias === 'freecad') {
        return {
          ...solver,
          badge: 'CAD',
          summary: '通过 FreeCAD Python API 生成几何模型，输出 FCStd 与 STEP。',
          artifactText: 'FCStd / STEP',
          actionText: '生成几何',
          featured: true,
        }
      }
      if (alias === 'prepomax-regenerate') {
        return {
          ...solver,
          badge: 'PrePoMax',
          summary: '使用 PrePoMax CLI 重新生成网格、输入文件与结果物证。',
          artifactText: 'PMX / INP / FRD',
          actionText: '运行再生',
          featured: true,
        }
      }
      if (alias === 'prepomax') {
        return {
          ...solver,
          badge: 'PrePoMax',
          summary: '检查 PrePoMax 命令行入口，作为后续前处理流程的占位。',
          artifactText: 'CLI 检查',
          actionText: '检查入口',
          featured: true,
        }
      }
      if (alias === 'calculix') {
        return {
          ...solver,
          badge: 'Solver',
          summary: '运行 CalculiX 结构算例，归档求解日志和结果文件。',
          artifactText: 'INP / FRD / VTK',
          actionText: '运行求解',
          featured: false,
        }
      }
      return {
        ...solver,
        badge: solver.kind || 'Solver',
        summary: solver.description || '从配置文件加载的求解器适配器。',
        artifactText: solver.artifact_patterns.slice(0, 3).join(' / ') || '结果文件',
        actionText: `运行 ${solver.label}`,
        featured: false,
      }
    })
    .sort((a, b) => (solverPriority[a.alias] ?? 50) - (solverPriority[b.alias] ?? 50))
)

const workflowSteps = computed(() => [
  {
    label: 'FreeCAD',
    text: '几何建模',
    ready: props.solvers.some((solver) => solver.alias === 'freecad'),
  },
  {
    label: 'PrePoMax',
    text: '前处理与网格',
    ready: props.solvers.some((solver) => solver.alias === 'prepomax-regenerate'),
  },
  {
    label: 'CalculiX',
    text: '结构求解',
    ready: props.solvers.some((solver) => solver.alias === 'calculix'),
  },
])

const workflowReady = computed(
  () =>
    props.solvers.some((solver) => solver.alias === 'freecad') &&
    props.solvers.some((solver) => solver.alias === 'prepomax-regenerate')
)
</script>

<template>
  <section class="panel remote-panel" aria-labelledby="remote-title">
    <div class="remote-panel-header">
      <div class="section-heading">
        <p class="eyebrow">计算工作台</p>
        <h2 id="remote-title">{{ activeComputeNodeLabel }}</h2>
      </div>
      <span class="remote-state" :class="{ running: remoteStatus.running, connected }">
        {{ remoteStatus.running ? '运行中' : connected ? '就绪' : '未连接' }}
      </span>
    </div>

    <div class="workflow-strip" aria-label="FreeCAD 到求解器流程">
      <div
        v-for="(step, index) in workflowSteps"
        :key="step.label"
        class="workflow-step"
        :class="{ ready: step.ready }"
      >
        <span class="workflow-index">{{ index + 1 }}</span>
        <strong>{{ step.label }}</strong>
        <small>{{ step.text }}</small>
      </div>
    </div>

    <div class="remote-node-card">
      <label class="node-selector">
        <span>当前节点</span>
        <select
          :value="selectedComputeNode"
          :disabled="computeNodes.length === 0 || remoteStatus.running"
          @change="emit('update:selectedComputeNode', ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="node in computeNodes" :key="node.alias" :value="node.alias">
            {{ node.label }} / {{ node.alias }}
          </option>
        </select>
      </label>
      <button
        type="button" class="primary-action"
        :disabled="!connected || !selectedComputeNode"
        @click="actions.probeRemoteNodeAction()"
      >
        测试连接
      </button>
    </div>

    <p v-if="computeNodes.length === 0" class="empty-state">
      尚未配置计算节点。请根据 simfea.config.example.json 创建 .simfea/config.json。
    </p>

    <div class="remote-action-grid">
      <div class="remote-action-group">
        <span class="action-group-title">环境检查</span>
        <div class="button-row">
          <button
            type="button"
            :disabled="!connected || !selectedComputeNode || remoteStatus.running"
            @click="actions.probeSchedulerAction()"
          >
            探测调度器
          </button>
          <button
            type="button"
            :disabled="!connected || !selectedComputeNode || remoteStatus.running"
            @click="actions.probeSolversAction()"
          >
            探测求解器
          </button>
        </div>
      </div>

      <div class="remote-action-group">
        <span class="action-group-title">样例任务</span>
        <div class="button-row">
          <button
            type="button"
            :disabled="!connected || !selectedComputeNode || remoteStatus.running"
            @click="actions.startRemoteDemoRunAction()"
          >
            运行闭环样例
          </button>
          <button
            type="button"
            :disabled="!connected || !selectedComputeNode || remoteStatus.running"
            @click="actions.startSlurmDemoRunAction()"
          >
            运行 Slurm 样例
          </button>
          <button
            type="button" class="danger-action"
            :disabled="!remoteStatus.running || !remoteStatus.runId"
            @click="actions.cancelRemoteRunAction()"
          >
            取消任务
          </button>
        </div>
      </div>
    </div>

    <div v-if="solverCards.length > 0" class="solver-board">
      <div class="solver-board-header">
        <div>
          <span class="action-group-title">工具链入口</span>
          <p>先证明几何和前处理链路，再接真实算例。</p>
        </div>
        <button
          type="button"
          class="primary-action workflow-run-button"
          :disabled="!connected || !selectedComputeNode || remoteStatus.running || !workflowReady"
          @click="actions.startFreecadPrepomaxWorkflowAction()"
        >
          一键运行 FreeCAD -> PrePoMax
        </button>
      </div>
      <div class="solver-card-grid">
        <article
          v-for="solver in solverCards"
          :key="solver.alias"
          class="solver-card"
          :class="{ featured: solver.featured }"
        >
          <div class="solver-card-head">
            <span class="solver-badge">{{ solver.badge }}</span>
            <strong>{{ solver.label }}</strong>
          </div>
          <p>{{ solver.summary }}</p>
          <div class="solver-meta-line">
            <span>{{ solver.kind }}</span>
            <span>{{ solver.artifactText }}</span>
          </div>
          <button
            type="button"
            :class="{ 'primary-action': solver.featured }"
            :disabled="!connected || !selectedComputeNode || remoteStatus.running"
            @click="actions.startSolverRunAction(solver.alias)"
          >
            {{ solver.actionText }}
          </button>
        </article>
      </div>
    </div>

    <div class="connection-detail">
      <span>{{ remoteStatus.message }}</span>
      <span v-if="remoteStatus.remoteWorkdir">工作目录：{{ remoteStatus.remoteWorkdir }}</span>
      <span v-if="remoteStatus.archivePath">本地归档：{{ remoteStatus.archivePath }}</span>
    </div>

    <div v-if="remoteStatus.output" class="remote-output-card">
      <div class="remote-output-title">
        <span>探测结果</span>
      </div>
      <pre class="remote-output"><code>{{ remoteStatus.output }}</code></pre>
    </div>
  </section>
</template>

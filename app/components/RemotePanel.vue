<script setup lang="ts">
import type { ComputeNodeConfig, RemoteStatus } from '@/composables/useRemoteRuns'
import type { SolverDefinition } from '@/types'

interface RemotePanelActions {
  probeRemoteNodeAction: () => void
  probeSchedulerAction: () => void
  probeSolversAction: () => void
  startRemoteDemoRunAction: () => void
  startSlurmDemoRunAction: () => void
  startSolverRunAction: (solverAlias: string) => void
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
</script>

<template>
  <section class="panel remote-panel" aria-labelledby="remote-title">
    <div class="section-heading">
      <p class="eyebrow">远程计算</p>
      <h2 id="remote-title">计算节点：{{ activeComputeNodeLabel }}</h2>
    </div>
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
    <p v-if="computeNodes.length === 0" class="empty-state">
      尚未配置计算节点。请根据 simfea.config.example.json 创建 .simfea/config.json。
    </p>
    <div class="button-row">
      <button
        type="button" class="primary-action"
        :disabled="!connected || !selectedComputeNode"
        @click="actions.probeRemoteNodeAction()"
      >
        测试远程节点
      </button>
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
        取消当前任务
      </button>
    </div>
    <div v-if="solvers.length > 0" class="button-row solver-actions">
      <button
        v-for="solver in solvers"
        :key="solver.alias"
        type="button"
        :disabled="!connected || !selectedComputeNode || remoteStatus.running"
        @click="actions.startSolverRunAction(solver.alias)"
      >
        运行 {{ solver.label }}
      </button>
    </div>
    <div class="connection-detail">
      <span>{{ remoteStatus.message }}</span>
      <span v-if="remoteStatus.remoteWorkdir">远程目录：{{ remoteStatus.remoteWorkdir }}</span>
      <span v-if="remoteStatus.archivePath">本地归档：{{ remoteStatus.archivePath }}</span>
    </div>
    <pre v-if="remoteStatus.output" class="remote-output"><code>{{ remoteStatus.output }}</code></pre>
  </section>
</template>

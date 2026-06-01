<script setup lang="ts">
import { open } from '@tauri-apps/plugin-dialog'
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import type { SimfeaClient } from '@/api/simfeaClient'
import type { SolverInstallation } from '@/types'

const props = defineProps<{
  api: SimfeaClient
  configPath: string
}>()

const emit = defineEmits<{
  back: []
}>()

const installations = ref<SolverInstallation[]>([])
const pathInputs = reactive<Record<string, string>>({})
const busy = ref<Record<string, string>>({})
const isTauriRuntime = () => {
  const internals = (
    window as unknown as {
      __TAURI_INTERNALS__?: { transformCallback?: unknown }
    }
  ).__TAURI_INTERNALS__
  return typeof internals?.transformCallback === 'function'
}
const message = ref('')
const selectedAlias = ref<string>('')

const installProgress = reactive<Record<string, { pct: number; message: string; step: string }>>({})
const installError = reactive<Record<string, string>>({})
const activeEventSources = new Map<string, EventSource>()

onUnmounted(() => {
  for (const es of activeEventSources.values()) {
    es.close()
  }
  activeEventSources.clear()
})

function setInstallation(next: SolverInstallation) {
  const index = installations.value.findIndex((item) => item.alias === next.alias)
  if (index >= 0) {
    installations.value[index] = next
  } else {
    installations.value.push(next)
  }
  pathInputs[next.alias] = next.discovered_path || next.configured_executable || pathInputs[next.alias] || ''
}

function statusLabel(status: SolverInstallation['status']) {
  if (status === 'verified') return '已验证'
  if (status === 'found') return '已发现'
  return '未发现'
}

function statusTone(status: SolverInstallation['status']) {
  if (status === 'verified') return 'ready'
  if (status === 'found') return 'neutral'
  return 'blocked'
}

const selectedSolver = () => installations.value.find((s) => s.alias === selectedAlias.value)

async function loadInstallations() {
  message.value = ''
  const result = await props.api.listSolverInstallations()
  installations.value = result.data.solvers
  for (const item of installations.value) {
    pathInputs[item.alias] = item.discovered_path || item.configured_executable || ''
  }
  if (!selectedAlias.value && installations.value.length > 0) {
    selectedAlias.value = installations.value[0].alias
  }
}

async function scan(alias: string) {
  busy.value = { ...busy.value, [alias]: 'scan' }
  try {
    const result = await props.api.scanSolverInstallation(alias)
    setInstallation(result.data)
    message.value = `${result.data.label} 自动搜索完成。`
  } finally {
    busy.value = { ...busy.value, [alias]: '' }
  }
}

async function savePath(alias: string) {
  const executable = pathInputs[alias]?.trim()
  if (!executable) {
    message.value = '请先填写可执行文件路径。'
    return
  }
  busy.value = { ...busy.value, [alias]: 'save' }
  try {
    const result = await props.api.configureSolverExecutable(alias, executable)
    setInstallation(result.data)
    message.value = `${result.data.label} 路径已写入配置。`
  } finally {
    busy.value = { ...busy.value, [alias]: '' }
  }
}

async function verify(alias: string) {
  busy.value = { ...busy.value, [alias]: 'verify' }
  try {
    const result = await props.api.verifySolverInstallation(alias, pathInputs[alias])
    setInstallation(result.data)
    message.value = result.data.verified
      ? `${result.data.label} 已通过测试运行。`
      : `${result.data.label} 测试未通过，请检查路径或安装。`
  } finally {
    busy.value = { ...busy.value, [alias]: '' }
  }
}

async function pickFile(alias: string) {
  if (!isTauriRuntime()) {
    message.value = '文件选择器仅在桌面应用中可用。'
    return
  }
  busy.value = { ...busy.value, [alias]: 'pick' }
  let selected: string | null = null
  try {
    const result = await open({
      multiple: false,
      directory: false,
      filters: [{ name: '可执行文件', extensions: ['exe', 'bat', 'com', 'cmd'] }],
    })
    if (result && typeof result === 'string') selected = result
  } catch {
    message.value = '无法打开文件选择器。'
    return
  } finally {
    busy.value = { ...busy.value, [alias]: '' }
  }
  if (selected) {
    pathInputs[alias] = selected
    await savePath(alias)
  }
}

async function installSolver(alias: string) {
  installError[alias] = ''
  installProgress[alias] = { pct: 0, message: '正在启动安装...', step: 'download' }
  try {
    const result = await props.api.installSolver(alias)
    const url = `${props.api.baseUrl}/v1/toolchain/solvers/${alias}/install/${result.install_id}/events`
    const es = new EventSource(url)
    activeEventSources.set(alias, es)
    es.onmessage = (event) => {
      let data: any
      try {
        data = JSON.parse(event.data)
      } catch {
        return
      }
      if (data.type === 'install_progress') {
        installProgress[alias] = { pct: data.progress_pct, message: data.message, step: data.step }
      } else if (data.type === 'install_complete') {
        es.close()
        activeEventSources.delete(alias)
        delete installProgress[alias]
        setInstallation(data.data)
        message.value = `${data.data.label} 安装完成。`
      } else if (data.type === 'install_error') {
        es.close()
        activeEventSources.delete(alias)
        delete installProgress[alias]
        installError[alias] = data.message
      }
    }
    es.onerror = () => {
      es.close()
      activeEventSources.delete(alias)
      delete installProgress[alias]
      installError[alias] = 'SSE 连接中断。'
    }
  } catch {
    delete installProgress[alias]
    installError[alias] = '无法启动安装。'
  }
}

onMounted(loadInstallations)
</script>

<template>
  <div class="view-container workbench-view">
    <header class="workbench-topbar">
      <div class="workbench-titlebar">
        <div class="app-mark" aria-hidden="true">TC</div>
        <span>工具链管理</span>
        <span class="topbar-status online">{{ installations.length }} 个求解器</span>
      </div>
      <div class="workbench-commandbar">
        <button type="button" @click="loadInstallations">刷新状态</button>
        <button type="button" @click="emit('back')">← 返回作业区</button>
      </div>
    </header>

    <section class="workbench-layout">
      <!-- Left: solver list -->
      <section class="schematic-pane">
        <div class="pane-title">求解器</div>
        <div class="schematic-canvas">
          <div class="model-tree">
            <button
              v-for="item in installations"
              :key="item.alias"
              type="button"
              class="tree-node"
              :class="[statusTone(item.status), { selected: selectedAlias === item.alias }]"
              @click="selectedAlias = item.alias"
            >
              <span class="tree-icon" :class="statusTone(item.status)"></span>
              <div class="tree-body">
                <div class="tree-head">
                  <strong>{{ item.label }}</strong>
                  <span class="tree-state" :class="statusTone(item.status)">{{ statusLabel(item.status) }}</span>
                </div>
                <small>{{ item.configured_executable || item.discovered_path || '未配置路径' }}</small>
              </div>
              <span class="tree-arrow">›</span>
            </button>
          </div>
        </div>
      </section>

      <!-- Right: solver detail -->
      <aside class="properties-pane">
        <div class="pane-title">求解器配置</div>
        <template v-if="selectedSolver()">
          <div style="padding: 9px; overflow-y: auto; flex: 1">
            <div class="property-block">
              <span>安装模式</span>
              <strong>{{ selectedSolver()!.label }}</strong>
              <p>{{ selectedSolver()!.install_hint }}</p>
            </div>

            <div class="property-block">
              <span>可执行文件路径</span>
              <input
                v-model="pathInputs[selectedSolver()!.alias]"
                type="text"
                class="prop-input"
                placeholder="粘贴或输入 exe / bat / com 路径"
              />
            </div>

            <div class="property-block">
              <span>当前配置</span>
              <p>{{ selectedSolver()!.configured_executable || '未配置' }}</p>
            </div>
            <div class="property-block">
              <span>自动发现</span>
              <p>{{ selectedSolver()!.discovered_path || '未发现' }}</p>
            </div>
            <div class="property-block">
              <span>输入类型</span>
              <p>{{ selectedSolver()!.input_extensions.join(' / ') || '无' }}</p>
            </div>

            <!-- Install progress -->
            <div v-if="installProgress[selectedSolver()!.alias]" class="property-block">
              <span>安装进度</span>
              <div class="install-bar">
                <div class="install-bar-fill" :style="{ width: installProgress[selectedSolver()!.alias].pct + '%' }"></div>
              </div>
              <p>{{ installProgress[selectedSolver()!.alias].message }}</p>
            </div>

            <!-- Install error -->
            <div v-if="installError[selectedSolver()!.alias]" class="property-block">
              <p style="color: #ef4444">{{ installError[selectedSolver()!.alias] }}</p>
            </div>

            <!-- Verify output -->
            <pre v-if="selectedSolver()!.stdout || selectedSolver()!.stderr" class="tool-output"><code>{{ selectedSolver()!.stdout || selectedSolver()!.stderr }}</code></pre>

            <!-- Actions -->
            <div class="property-block" style="display: flex; flex-wrap: wrap; gap: 6px">
              <button
                v-if="selectedSolver()!.install_mode === 'managed_or_external' && selectedSolver()!.status === 'missing' && !installProgress[selectedSolver()!.alias]"
                type="button" class="primary-action" @click="installSolver(selectedSolver()!.alias)" :disabled="Boolean(busy[selectedSolver()!.alias])"
              >
                安装 Solver Pack
              </button>
              <button type="button" @click="scan(selectedSolver()!.alias)" :disabled="Boolean(busy[selectedSolver()!.alias])">自动搜索</button>
              <button type="button" @click="pickFile(selectedSolver()!.alias)" :disabled="Boolean(busy[selectedSolver()!.alias])">选择路径</button>
              <button type="button" class="primary-action" @click="verify(selectedSolver()!.alias)" :disabled="Boolean(busy[selectedSolver()!.alias])">测试运行</button>
              <button type="button" @click="savePath(selectedSolver()!.alias)" :disabled="Boolean(busy[selectedSolver()!.alias])">保存路径</button>
            </div>
          </div>
        </template>
        <div v-else style="padding: 48px 16px; text-align: center; color: #9ca6b8; font-size: 0.78rem">
          ← 从左侧选择一个求解器
        </div>
      </aside>
    </section>

    <div class="action-bar">
      <span class="action-status">{{ message || '准备就绪' }}</span>
      <span class="action-worker">配置：{{ configPath || '未连接' }}</span>
    </div>
  </div>
</template>

<style scoped>
.install-bar { height: 8px; background: #1e2330; border-radius: 4px; overflow: hidden; margin: 6px 0; }
.install-bar-fill { height: 100%; background: #8b5cf6; border-radius: 4px; transition: width 0.3s ease; }
.tool-output { max-height: 160px; overflow-y: auto; padding: 8px; background: #0f1116; border-radius: 4px; font-size: 0.62rem; color: #9ca6b8; margin-top: 6px; white-space: pre-wrap; }
</style>

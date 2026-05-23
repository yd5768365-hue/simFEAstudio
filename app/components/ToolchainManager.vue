<script setup lang="ts">
import { open } from '@tauri-apps/plugin-dialog'
import { onMounted, reactive, ref } from 'vue'
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
  if (status === 'verified') return 'online'
  if (status === 'found') return 'pending'
  return 'offline'
}

function installModeLabel(mode: string) {
  if (mode === 'managed_or_external') return '可外接 / 可安装包'
  return '外部安装'
}

function openInstallGuide(url: string) {
  window.open(url, '_blank', 'noopener,noreferrer')
}

async function loadInstallations() {
  message.value = ''
  const result = await props.api.listSolverInstallations()
  installations.value = result.data.solvers
  for (const item of installations.value) {
    pathInputs[item.alias] = item.discovered_path || item.configured_executable || ''
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
    message.value = '文件选择器仅在桌面应用中可用，请手动粘贴路径。'
    return
  }
  busy.value = { ...busy.value, [alias]: 'pick' }
  let selected: string | null = null
  try {
    const result = await open({
      multiple: false,
      directory: false,
      filters: [
        {
          name: '可执行文件',
          extensions: ['exe', 'bat', 'com', 'cmd'],
        },
      ],
    })
    if (result && typeof result === 'string') {
      selected = result
    }
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

onMounted(loadInstallations)
</script>

<template>
  <section class="toolchain-view">
    <header class="toolchain-header">
      <div class="toolchain-header-left">
        <button type="button" @click="emit('back')">返回</button>
        <div>
          <p class="eyebrow">Toolchain Manager</p>
          <h2>工具链管理</h2>
          <p class="toolchain-subtitle">
            把求解器从“有没有装”变成“已发现、已验证、可复用”的明确状态。
          </p>
        </div>
      </div>
      <button type="button" class="primary-action" @click="loadInstallations">刷新状态</button>
    </header>

    <section class="panel toolchain-guide-panel">
      <div class="section-heading">
        <p class="eyebrow">Install Policy</p>
        <h2>安装策略</h2>
      </div>
      <div class="install-policy-grid">
        <article>
          <strong>商业软件</strong>
          <p>Abaqus、ANSYS 只做本机接入和许可证环境验证，不进入安装包。</p>
        </article>
        <article>
          <strong>外部工具</strong>
          <p>FreeCAD、PrePoMax 提供安装指引、路径选择和测试运行。</p>
        </article>
        <article>
          <strong>开源求解器</strong>
          <p>CalculiX 可使用已有安装，后续也可以接独立 Solver Pack。</p>
        </article>
      </div>
    </section>

    <section class="toolchain-manager-grid" aria-label="求解器安装状态">
      <article v-for="item in installations" :key="item.alias" class="panel tool-install-card">
        <div class="tool-install-head">
          <div>
            <span class="eyebrow">{{ installModeLabel(item.install_mode) }}</span>
            <h2>{{ item.label }}</h2>
          </div>
          <span class="status-pill" :class="statusTone(item.status)">{{ statusLabel(item.status) }}</span>
        </div>

        <p class="tool-install-hint">{{ item.install_hint }}</p>

        <div class="tool-path-field">
          <label :for="`tool-path-${item.alias}`">可执行文件路径</label>
          <input
            :id="`tool-path-${item.alias}`"
            v-model="pathInputs[item.alias]"
            type="text"
            placeholder="粘贴或输入 exe / bat / com 路径"
          />
        </div>

        <dl class="tool-install-meta">
          <div>
            <dt>当前配置</dt>
            <dd>{{ item.configured_executable || '未配置' }}</dd>
          </div>
          <div>
            <dt>自动发现</dt>
            <dd>{{ item.discovered_path || '未发现' }}</dd>
          </div>
          <div>
            <dt>输入类型</dt>
            <dd>{{ item.input_extensions.join(' / ') }}</dd>
          </div>
        </dl>

        <div v-if="item.status === 'missing'" class="install-empty-state">
          <strong>还没有发现这个工具</strong>
          <p>先按安装向导完成安装，再回来自动搜索或粘贴路径。</p>
        </div>

        <pre v-if="item.stdout || item.stderr" class="tool-verify-output"><code>{{ item.stdout || item.stderr }}</code></pre>

        <div class="tool-install-actions">
          <button type="button" @click="scan(item.alias)" :disabled="Boolean(busy[item.alias])">
            自动搜索
          </button>
          <button type="button" @click="pickFile(item.alias)" :disabled="Boolean(busy[item.alias])">
            选择路径
          </button>
          <button type="button" class="primary-action" @click="verify(item.alias)" :disabled="Boolean(busy[item.alias])">
            测试运行
          </button>
          <button
            v-if="item.install_guide_url"
            type="button"
            @click="openInstallGuide(item.install_guide_url)"
          >
            安装向导
          </button>
        </div>
      </article>
    </section>

    <p v-if="message" class="toolchain-message">{{ message }}</p>
    <p class="toolchain-config-path">配置文件：{{ configPath || '尚未连接侧车' }}</p>
  </section>
</template>

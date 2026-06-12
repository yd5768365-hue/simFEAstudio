<script setup lang="ts">
import { onMounted, ref } from 'vue'

defineProps<{
  sidecarConnected: boolean
  solversAvailable: number
  runsArchived: number
}>()

const ollamaStatus = ref<'checking' | 'online' | 'offline'>('checking')
const lastCheck = ref('')

async function checkOllama() {
  ollamaStatus.value = 'checking'
  try {
    const resp = await fetch('http://localhost:11434/api/tags', { signal: AbortSignal.timeout(3000) })
    if (resp.ok) {
      ollamaStatus.value = 'online'
    } else {
      ollamaStatus.value = 'offline'
    }
  } catch {
    ollamaStatus.value = 'offline'
  }
  lastCheck.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function statusDot(s: string) {
  if (s === 'online' || s === true) return 'dot-green'
  if (s === 'checking') return 'dot-amber'
  return 'dot-red'
}

onMounted(checkOllama)
</script>

<template>
  <div class="ss">
    <span class="ss-item" :class="sidecarConnected ? 'ok' : 'err'" :title="sidecarConnected ? '侧车已连接' : '侧车离线'">
      <span class="ss-dot" :class="sidecarConnected ? 'dot-green' : 'dot-red'"></span>
      侧车
    </span>
    <span class="ss-item" :class="ollamaStatus === 'online' ? 'ok' : ollamaStatus === 'checking' ? '' : 'err'" :title="ollamaStatus === 'online' ? 'Ollama 可用' : ollamaStatus === 'checking' ? '检测中…' : 'Ollama 不可用'">
      <span class="ss-dot" :class="statusDot(ollamaStatus)"></span>
      AI{{ ollamaStatus === 'checking' ? '?' : ollamaStatus === 'online' ? '' : '✕' }}
    </span>
    <span v-if="solversAvailable > 0" class="ss-item neutral">
      <span class="ss-dot dot-green"></span>
      {{ solversAvailable }} 求解器
    </span>
    <span v-if="runsArchived > 0" class="ss-item neutral">
      {{ runsArchived }} 运行
    </span>
    <span class="ss-item dim" :title="`上次检测 ${lastCheck}`" @click="checkOllama" style="cursor: pointer">
      {{ lastCheck || '—' }}
    </span>
  </div>
</template>

<style scoped>
.ss {
  display: flex;
  align-items: center;
  gap: 14px;
}

.ss-item {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.68rem;
  color: var(--text-dim);
  transition: color var(--transition-fast);
}

.ss-item.ok    { color: var(--green); }
.ss-item.err   { color: var(--red); }
.ss-item.neutral { color: var(--text-muted); }
.ss-item.dim   { color: var(--text-dim); }

.ss-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot-green { background: var(--green); }
.dot-amber { background: var(--amber); animation: ss-pulse 1.5s infinite; }
.dot-red   { background: var(--red); }

@keyframes ss-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>

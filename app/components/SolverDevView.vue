<script setup lang="ts">
import { onActivated, onMounted, ref } from 'vue'
import type { SimfeaClient } from '@/api/simfeaClient'
import { renderMarkdown } from '@/utils/markdown'

interface DevFile {
  path: string
  name: string
  size: number
}

const props = defineProps<{ api: SimfeaClient }>()
const emit = defineEmits<{ back: [] }>()

const files = ref<DevFile[]>([])
const selected = ref<DevFile | null>(null)
const content = ref('')
const loading = ref(false)

async function loadFiles() {
  try {
    const r = await props.api.listExperimentFiles()
    files.value = (r.data.files as DevFile[]).filter((f) => f.path.startsWith('learning/solver-dev/'))
    if (files.value.length && !selected.value) {
      openFile(files.value[0])
    }
  } catch {
    files.value = []
  }
}

async function openFile(f: DevFile) {
  loading.value = true
  try {
    const r = await props.api.readExperimentFile(f.path)
    content.value = r.data.content
    selected.value = f
  } catch {
    content.value = '*加载失败*'
  }
  loading.value = false
}

onMounted(loadFiles)
onActivated(loadFiles)
</script>

<template>
  <div class="lab">
    <div class="lab-top">
      <button type="button" class="lab-back" @click="emit('back')">
        <svg width="14" height="14" viewBox="0 0 16 16"><path d="M10 3L5 8l5 5" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>
      </button>
      <span class="lab-title">求解器开发</span>
      <span v-if="selected" class="lab-file">{{ selected.name }}</span>
    </div>

    <div class="lab-body">
      <nav class="lab-sidebar">
        <div class="lab-sidebar-head">开发日志</div>
        <button
          v-for="f in files" :key="f.path"
          type="button"
          class="lab-file-btn"
          :class="{ active: selected?.path === f.path }"
          @click="openFile(f)"
        >
          <span class="lab-file-icon">📄</span>
          <span class="lab-file-name">{{ f.name }}</span>
        </button>
        <div v-if="files.length === 0" class="lab-sidebar-empty">
          暂无开发日志<br><small>在 learning/solver-dev/ 下创建 .md 文件</small>
        </div>
      </nav>

      <div class="lab-main">
        <div v-if="loading" class="lab-loading"><span class="lab-spinner"></span> 加载中…</div>
        <div v-else-if="!selected" class="lab-welcome">
          <p>SimFEA-Lab Core</p>
          <small>从零手写 FEM 求解器，触碰底层逻辑</small>
        </div>
        <div v-else class="lab-preview" v-html="renderMarkdown(content)" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.lab { display: flex; flex-direction: column; height: 100%; padding: 0 20px; }
.lab-top { display: flex; align-items: center; gap: 10px; flex-shrink: 0; padding: 12px 0; border-bottom: 1px solid var(--border-subtle); }
.lab-back { background: none; border: none; color: var(--text-muted); cursor: pointer; padding: 2px; }
.lab-back:hover { color: var(--text-body); }
.lab-title { font-size: 0.85rem; font-weight: 600; color: var(--text-heading); }
.lab-file { font-size: 0.8rem; color: var(--text-muted); padding: 2px 8px; background: var(--bg-input); border-radius: 4px; }

.lab-body { display: flex; flex: 1; min-height: 0; }
.lab-sidebar { width: 200px; flex-shrink: 0; overflow-y: auto; border-right: 1px solid var(--border-subtle); padding: 10px 8px; }
.lab-sidebar-head { font-size: 0.62rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-dim); padding: 0 6px 8px; }
.lab-file-btn { display: flex; align-items: center; gap: 6px; width: 100%; padding: 5px 6px; background: none; border: none; border-radius: 4px; color: var(--text-body); font-size: 0.76rem; cursor: pointer; text-align: left; }
.lab-file-btn:hover { background: rgba(255,255,255,0.03); }
.lab-file-btn.active { background: var(--accent-glow); color: var(--accent); }
.lab-file-icon { font-size: 0.7rem; flex-shrink: 0; }
.lab-file-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lab-sidebar-empty { padding: 16px 6px; font-size: 0.72rem; color: var(--text-dim); }

.lab-main { flex: 1; display: flex; flex-direction: column; min-width: 0; min-height: 0; }
.lab-loading { display: flex; align-items: center; justify-content: center; gap: 8px; height: 100%; color: var(--text-muted); font-size: 0.85rem; }
.lab-spinner { width: 18px; height: 18px; border: 2px solid var(--border-subtle); border-top-color: var(--accent-hover); border-radius: 50%; animation: spin 0.6s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.lab-welcome { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; color: var(--text-muted); font-size: 0.85rem; gap: 6px; }
.lab-welcome small { font-size: 0.7rem; color: var(--text-dim); }

.lab-preview { flex: 1; overflow-y: auto; padding: 20px 24px; background: var(--bg-app); border-left: 1px solid var(--border-subtle); font-size: 0.85rem; line-height: 1.85; color: var(--text-body); }
.lab-preview :deep(h1) { font-size: 1.4rem; font-weight: 800; color: var(--text-heading); margin: 0 0 16px; padding-bottom: 10px; border-bottom: 1px solid var(--border-default); }
.lab-preview :deep(h2) { font-size: 1.12rem; font-weight: 700; color: var(--text-heading); margin: 24px 0 10px; padding-left: 12px; border-left: 3px solid var(--accent); }
.lab-preview :deep(h3) { font-size: 0.95rem; font-weight: 600; color: var(--text-heading); margin: 18px 0 8px; }
.lab-preview :deep(p) { margin: 10px 0; }
.lab-preview :deep(strong) { color: var(--text-heading); font-weight: 700; }
.lab-preview :deep(code) { background: var(--bg-input); padding: 2px 7px; border-radius: 4px; font-size: 0.88em; color: var(--accent-blue); }
.lab-preview :deep(pre) { background: var(--bg-input); border: 1px solid var(--border-default); border-radius: 8px; padding: 16px 20px; overflow-x: auto; font-size: 0.78rem; line-height: 1.65; margin: 16px 0; }
.lab-preview :deep(pre code) { background: none; padding: 0; font-size: inherit; color: var(--text-body); }
.lab-preview :deep(table) { width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 0.8rem; border: 1px solid var(--border-default); border-radius: 8px; overflow: hidden; }
.lab-preview :deep(th) { background: var(--bg-panel); color: var(--text-muted); font-weight: 700; padding: 10px 14px; text-align: left; font-size: 0.72rem; text-transform: uppercase; }
.lab-preview :deep(td) { padding: 8px 14px; border-bottom: 1px solid var(--border-subtle); }
.lab-preview :deep(ul), .lab-preview :deep(ol) { margin: 10px 0; padding-left: 24px; }
.lab-preview :deep(li) { margin: 5px 0; line-height: 1.75; }
.lab-preview :deep(blockquote) { border-left: 3px solid var(--accent); margin: 16px 0; padding: 12px 18px; color: var(--text-muted); background: var(--accent-glow); border-radius: 0 8px 8px 0; }
.lab-preview :deep(hr) { border: none; border-top: 1px solid var(--border-subtle); margin: 28px 0; }
</style>

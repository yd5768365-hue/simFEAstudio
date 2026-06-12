<script setup lang="ts">
import { onActivated, onMounted } from 'vue'
import { fileIcon, useExperimentFiles } from '@/composables/useExperimentFiles'
import { renderMarkdown } from '@/utils/markdown'
import { highlightCode } from '@/utils/syntaxHighlight'

const props = defineProps<{ apiBaseUrl: string }>()
const emit = defineEmits<{ back: [] }>()

const {
  files,
  selectedFile,
  editorContent,
  consoleOutput,
  running,
  modified,
  savedPath,
  preview,
  loading,
  isMarkdown,
  isCodeFile,
  fileGroups,
  fetchFiles,
  openFile,
  saveFile,
  newFile,
  runFile,
  onEditorKeydown,
} = useExperimentFiles(props.apiBaseUrl)

onMounted(fetchFiles)
onActivated(fetchFiles)
</script>

<template>
  <div class="lab">
    <!-- Top bar -->
    <div class="lab-top">
      <button type="button" class="lab-back" @click="emit('back')">
        <svg width="14" height="14" viewBox="0 0 16 16"><path d="M10 3L5 8l5 5" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>
      </button>
      <span class="lab-title">实验</span>
      <span v-if="selectedFile" class="lab-file">
        {{ selectedFile.name }}
        <span v-if="modified" class="lab-dirty">●</span>
      </span>
      <span class="lab-spacer"></span>
      <button type="button" class="lab-btn" @click="newFile">新建</button>
      <button type="button" class="lab-btn" :disabled="!modified" @click="saveFile">保存</button>
      <button type="button" class="lab-btn" :disabled="!selectedFile || running" @click="runFile">
        {{ running ? '运行中…' : '▶ 运行' }}
      </button>
      <button
        v-if="isMarkdown || isCodeFile"
        type="button"
        class="lab-btn"
        :class="{ active: preview }"
        @click="preview = !preview"
      >
        {{ preview ? '编辑' : '预览' }}
      </button>
    </div>

    <div class="lab-body">
      <!-- File sidebar -->
      <nav class="lab-sidebar">
        <div class="lab-sidebar-head">文件</div>
        <div v-for="group in fileGroups" :key="group.dir" class="lab-group">
          <div class="lab-group-label">{{ group.dir }}</div>
          <template v-if="group.docs.length">
            <div class="lab-section-label">问题描述</div>
            <button
              v-for="f in group.docs" :key="f.path"
              type="button"
              class="lab-file-btn"
              :class="{ active: selectedFile?.path === f.path }"
              @click="openFile(f)"
            >
              <span class="lab-file-icon">📄</span>
              <span class="lab-file-name">{{ f.name }}</span>
            </button>
          </template>
          <template v-if="group.code.length">
            <div class="lab-section-label">代码</div>
            <button
              v-for="f in group.code" :key="f.path"
              type="button"
              class="lab-file-btn"
              :class="{ active: selectedFile?.path === f.path }"
              @click="openFile(f)"
            >
              <span class="lab-file-icon">{{ fileIcon(f.name) }}</span>
              <span class="lab-file-name">{{ f.name }}</span>
            </button>
          </template>
        </div>
        <div v-if="files.length === 0" class="lab-sidebar-empty">
          暂无实验文件<br><small>在 learning/experiments/ 下创建</small>
        </div>
      </nav>

      <!-- Editor + console -->
      <div class="lab-main">
        <div v-if="loading" class="lab-loading"><span class="lab-spinner"></span> 加载中…</div>
        <div v-else-if="!selectedFile" class="lab-welcome">
          <p>从左侧选择一个文件开始编辑</p>
          <small>Ctrl+S 保存 · F5 运行</small>
        </div>
        <template v-else>
          <div class="lab-editor-wrap">
            <div v-if="isMarkdown && preview" class="lab-preview" v-html="renderMarkdown(editorContent || '*空文件*')" />
            <div
              v-else-if="isCodeFile && preview"
              class="lab-preview lab-code-preview"
              v-html="highlightCode(editorContent || '', selectedFile?.name ?? '.txt')"
            />
            <textarea
              v-else
              v-model="editorContent"
              class="lab-editor"
              spellcheck="false"
              @keydown="onEditorKeydown"
              @input="modified = true"
            />
          </div>
          <div class="lab-console-wrap">
            <div class="lab-console-head">
              <span>终端</span>
              <button type="button" class="lab-console-clear" @click="consoleOutput = ''">清空</button>
            </div>
            <pre class="lab-console"><code>{{ consoleOutput || '— 按 F5 或点击「运行」执行文件 —' }}</code></pre>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lab { display: flex; flex-direction: column; height: 100%; padding: 0 20px; }

/* ── Top bar ─────────────────────────────────── */
.lab-top {
  display: flex; align-items: center; gap: 10px;
  flex-shrink: 0; padding: 12px 0; border-bottom: 1px solid var(--border-subtle);
}

.lab-back { background: none; border: none; color: var(--text-muted); cursor: pointer; padding: 2px; }
.lab-back:hover { color: var(--text-body); }

.lab-title { font-size: 0.85rem; font-weight: 600; color: var(--text-heading); }

.lab-file {
  font-size: 0.8rem; color: var(--text-muted);
  padding: 2px 8px; background: var(--bg-input); border-radius: 4px;
}

.lab-dirty { color: var(--amber); margin-left: 4px; font-size: 0.6rem; }

.lab-spacer { flex: 1; }

.lab-btn {
  padding: 5px 12px; background: var(--bg-card); border: 1px solid var(--border-default);
  border-radius: 5px; color: var(--text-muted); font-size: 0.72rem; cursor: pointer;
  transition: all var(--transition-fast);
}

.lab-btn:hover:not(:disabled) { border-color: var(--border-strong); color: var(--text-body); }
.lab-btn:disabled { opacity: 0.3; cursor: default; }
.lab-btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.lab-btn.primary:hover:not(:disabled) { background: var(--accent-hover); }
.lab-btn.primary:disabled { opacity: 0.3; }
.lab-btn.active { border-color: var(--accent); color: var(--accent); }

/* ── Body: sidebar + main ────────────────────── */
.lab-body { display: flex; flex: 1; min-height: 0; gap: 0; }

/* ── Sidebar ─────────────────────────────────── */
.lab-sidebar {
  width: 200px; flex-shrink: 0; overflow-y: auto;
  border-right: 1px solid var(--border-subtle); padding: 10px 8px;
}

.lab-sidebar-head {
  font-size: 0.62rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--text-dim); padding: 0 6px 8px;
}

.lab-group { margin-bottom: 10px; }

.lab-group-label {
  font-size: 0.62rem; color: var(--text-dim); padding: 2px 6px 4px;
  text-transform: uppercase; letter-spacing: 0.04em;
}

.lab-section-label {
  font-size: 0.6rem; color: var(--text-dim); padding: 6px 6px 2px;
  border-top: 1px dashed var(--border-subtle); margin-top: 2px;
}

.lab-file-btn {
  display: flex; align-items: center; gap: 6px;
  width: 100%; padding: 5px 6px; background: none; border: none; border-radius: 4px;
  color: var(--text-body); font-size: 0.76rem; cursor: pointer; text-align: left;
}

.lab-file-btn:hover { background: rgba(255,255,255,0.03); }
.lab-file-btn.active { background: var(--accent-glow); color: var(--accent); }

.lab-file-icon { font-size: 0.7rem; flex-shrink: 0; }
.lab-file-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.lab-sidebar-empty { padding: 16px 6px; font-size: 0.72rem; color: var(--text-dim); }
.lab-sidebar-empty small { font-size: 0.64rem; }

/* ── Main area ───────────────────────────────── */
.lab-main { flex: 1; display: flex; flex-direction: column; min-width: 0; min-height: 0; }

.lab-loading {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  height: 100%; color: var(--text-muted); font-size: 0.85rem;
}
.lab-spinner {
  width: 18px; height: 18px;
  border: 2px solid var(--border-subtle);
  border-top-color: var(--accent-hover);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.lab-welcome {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  flex: 1; color: var(--text-muted); font-size: 0.85rem; gap: 6px;
}

.lab-welcome small { font-size: 0.7rem; color: var(--text-dim); }

/* ── Editor ──────────────────────────────────── */
.lab-editor-wrap { flex: 1; min-height: 0; padding: 0 0 0 12px; }

.lab-editor {
  width: 100%; height: 100%; padding: 14px; background: var(--bg-input);
  border: 1px solid var(--border-default); border-radius: 6px;
  color: var(--text-body); font-family: 'Cascadia Code', 'JetBrains Mono', Consolas, monospace;
  font-size: 0.8rem; line-height: 1.65; resize: none; outline: none; box-sizing: border-box;
  tab-size: 4; white-space: pre; overflow-wrap: normal; overflow-x: auto;
}

.lab-editor:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-glow); }

/* ── Console ─────────────────────────────────── */
.lab-console-wrap { flex-shrink: 0; height: 200px; padding: 0 0 0 12px; margin-top: 8px; }

.lab-console-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 4px 10px; background: var(--bg-panel); border: 1px solid var(--border-default);
  border-bottom: none; border-radius: 6px 6px 0 0; font-size: 0.68rem; color: var(--text-dim);
}

.lab-console-clear {
  background: none; border: none; color: var(--text-dim); font-size: 0.66rem; cursor: pointer;
}

.lab-console-clear:hover { color: var(--text-body); }

.lab-console {
  margin: 0; padding: 10px 14px; height: calc(100% - 28px);
  background: var(--bg-input); border: 1px solid var(--border-default); border-radius: 0 0 6px 6px;
  font-family: 'Cascadia Code', 'JetBrains Mono', Consolas, monospace;
  font-size: 0.74rem; line-height: 1.55; color: var(--text-body);
  overflow-y: auto; white-space: pre-wrap; word-break: break-word;
  box-sizing: border-box;
}

/* ── Markdown preview ─────────────────────────── */
.lab-preview {
  height: 100%; overflow-y: auto; padding: 20px 24px;
  background: var(--bg-app); border: 1px solid var(--border-default);
  border-radius: 6px; font-size: 0.85rem; line-height: 1.85; color: var(--text-body);
}

.lab-preview :deep(h1) {
  font-size: 1.4rem; font-weight: 800; color: var(--text-heading);
  margin: 36px 0 16px; padding-bottom: 10px;
  border-bottom: 1px solid var(--border-default);
}
.lab-preview :deep(h1:first-child) { margin-top: 0; }

.lab-preview :deep(h2) {
  font-size: 1.12rem; font-weight: 700; color: var(--text-heading);
  margin: 32px 0 12px; padding-left: 12px;
  border-left: 3px solid var(--accent);
}
.lab-preview :deep(h2:first-child) { margin-top: 0; }

.lab-preview :deep(h3) {
  font-size: 0.95rem; font-weight: 600; color: var(--text-heading);
  margin: 22px 0 10px;
}
.lab-preview :deep(h3:first-child) { margin-top: 0; }

.lab-preview :deep(h4) {
  font-size: 0.85rem; font-weight: 600; color: var(--text-heading);
  margin: 16px 0 8px;
}

.lab-preview :deep(p) { margin: 10px 0; }

.lab-preview :deep(strong) { color: var(--text-heading); font-weight: 700; }

.lab-preview :deep(a) {
  color: var(--accent-hover); text-decoration: none;
  border-bottom: 1px solid var(--accent-border);
}
.lab-preview :deep(a:hover) { color: var(--accent); border-bottom-color: var(--accent); }

.lab-preview :deep(code) {
  background: var(--bg-input); padding: 2px 7px; border-radius: 4px;
  font-size: 0.88em; color: var(--accent-blue); font-family: var(--font-mono);
}

.lab-preview :deep(pre) {
  background: var(--bg-input); border: 1px solid var(--border-default);
  border-radius: 8px; padding: 16px 20px; overflow-x: auto;
  font-size: 0.78rem; line-height: 1.65; margin: 16px 0; tab-size: 4;
}
.lab-preview :deep(pre code) {
  background: none; padding: 0; border-radius: 0; font-size: inherit;
  color: var(--text-body);
}

.lab-preview :deep(table) {
  width: 100%; border-collapse: collapse; margin: 16px 0 20px;
  font-size: 0.8rem; font-variant-numeric: tabular-nums;
  border: 1px solid var(--border-default); border-radius: 8px;
  overflow: hidden;
}
.lab-preview :deep(thead) { border-bottom: 2px solid var(--border-strong); }
.lab-preview :deep(th) {
  background: var(--bg-panel); color: var(--text-muted); font-weight: 700;
  padding: 10px 14px; text-align: left;
  font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em;
  white-space: nowrap;
}
.lab-preview :deep(td) {
  padding: 8px 14px; border-bottom: 1px solid var(--border-subtle);
  color: var(--text-body); vertical-align: top;
}
.lab-preview :deep(tr:nth-child(even) td) { background: rgba(255,255,255,0.015); }
.lab-preview :deep(tr:hover td) { background: rgba(139,92,246,0.05); }

.lab-preview :deep(blockquote) {
  border-left: 3px solid var(--accent); margin: 16px 0; padding: 12px 18px;
  color: var(--text-muted); background: var(--accent-glow);
  border-radius: 0 8px 8px 0;
}
.lab-preview :deep(blockquote strong) { color: var(--accent-hover); }
.lab-preview :deep(blockquote p) { margin: 4px 0; color: var(--text-muted); }

.lab-preview :deep(ul), .lab-preview :deep(ol) { margin: 10px 0; padding-left: 24px; }
.lab-preview :deep(li) { margin: 5px 0; line-height: 1.75; }
.lab-preview :deep(li > ul), .lab-preview :deep(li > ol) { margin: 4px 0; }
.lab-preview :deep(ul ul) { list-style-type: circle; }
.lab-preview :deep(ul ul ul) { list-style-type: square; }

.lab-preview :deep(hr) { border: none; border-top: 1px solid var(--border-subtle); margin: 28px 0; }

.lab-preview :deep(img) { max-width: 100%; border-radius: 8px; border: 1px solid var(--border-default); }

.lab-preview :deep(em) { font-style: italic; color: var(--text-muted); }

/* ── Code preview / syntax highlighting ───────── */
.lab-code-preview {
  font-family: 'Cascadia Code', 'JetBrains Mono', Consolas, monospace;
  font-size: 0.8rem; line-height: 1.65; tab-size: 4;
}

.lab-code-preview :deep(.syn-block) {
  margin: 0; padding: 0; background: none; border: none; border-radius: 0;
}

.lab-code-preview :deep(.syn-keyword)   { color: #c084fc; font-weight: 600; }
.lab-code-preview :deep(.syn-builtin)   { color: #60a5fa; }
.lab-code-preview :deep(.syn-funcall)   { color: #fbbf24; }
.lab-code-preview :deep(.syn-decorator) { color: #facc15; }
.lab-code-preview :deep(.syn-string)    { color: #34d399; }
.lab-code-preview :deep(.syn-fstring)   { color: #34d399; font-weight: 600; }
.lab-code-preview :deep(.syn-comment)   { color: #6b7280; font-style: italic; }
.lab-code-preview :deep(.syn-number)    { color: #fb923c; }
.lab-code-preview :deep(.syn-json-key)  { color: #a78bfa; }
.lab-code-preview :deep(.syn-inp-keyword) { color: #f87171; font-weight: 700; }
</style>

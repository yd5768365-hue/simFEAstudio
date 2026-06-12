<script setup lang="ts">
import { computed, onActivated, onMounted, ref } from 'vue'
import { renderMarkdown } from '@/utils/markdown'

interface ResearchNote {
  path: string
  name: string
  size: number
}

const props = defineProps<{ apiBaseUrl: string }>()
const emit = defineEmits<{ back: [] }>()

const baseUrl = props.apiBaseUrl.replace(/\/+$/, '')

const notes = ref<ResearchNote[]>([])
const selectedPath = ref('')
const content = ref('')
const editing = ref(false)
const editContent = ref('')
const savedMsg = ref('')
const showNewDialog = ref(false)
const newNoteName = ref('')
const creatingNote = ref(false)

function openNewDialog() {
  newNoteName.value = `research-${new Date().toISOString().slice(0, 10)}.md`
  showNewDialog.value = true
}

async function confirmNewNote() {
  const raw = newNoteName.value.trim()
  if (!raw) return
  const name = raw.endsWith('.md') ? raw : `${raw}.md`
  const path = `learning/research/${name}`
  creatingNote.value = true
  try {
    await fetch(`${baseUrl}/v1/experiment/files/${encodeURI(path)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: '# 新研究笔记\n\n' }),
    })
    showNewDialog.value = false
    await loadNotes()
    selectedPath.value = path
    content.value = '# 新研究笔记\n\n'
    editing.value = true
    editContent.value = '# 新研究笔记\n\n'
  } catch {
    /* */
  }
  creatingNote.value = false
}

function cancelNewDialog() {
  showNewDialog.value = false
  newNoteName.value = ''
}

async function loadNotes() {
  try {
    const r = await fetch(`${baseUrl}/v1/experiment/files`)
    const j = await r.json()
    notes.value = ((j.data?.files || []) as ResearchNote[]).filter((f) =>
      f.path.startsWith('learning/research/')
    )
  } catch {
    notes.value = []
  }
}

async function openNote(f: ResearchNote) {
  if (editing.value && !confirm('放弃未保存的更改？')) return
  try {
    const r = await fetch(`${baseUrl}/v1/experiment/files/${encodeURI(f.path)}`)
    const j = await r.json()
    content.value = j.data.content as string
    selectedPath.value = f.path
    editing.value = false
  } catch {
    /* */
  }
}

function startEdit() {
  editContent.value = content.value
  editing.value = true
}

async function saveEdit() {
  try {
    await fetch(`${baseUrl}/v1/experiment/files/${encodeURI(selectedPath.value)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: editContent.value }),
    })
    content.value = editContent.value
    editing.value = false
    savedMsg.value = `已保存 — ${new Date().toLocaleTimeString()}`
    setTimeout(() => (savedMsg.value = ''), 2000)
  } catch {
    /* */
  }
}

function cancelEdit() {
  editing.value = false
}

const sortedNotes = computed(() => [...notes.value].sort((a, b) => b.name.localeCompare(a.name)))

onMounted(loadNotes)
onActivated(loadNotes)
</script>

<template>
  <div class="rv">
    <div class="rv-top">
      <button type="button" class="rv-back" @click="emit('back')">
        <svg width="14" height="14" viewBox="0 0 16 16"><path d="M10 3L5 8l5 5" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>
      </button>
      <span class="rv-title">研究</span>
      <span v-if="savedMsg" class="rv-saved">{{ savedMsg }}</span>
      <span class="rv-spacer"></span>
      <button type="button" class="rv-btn" @click="openNewDialog">新建</button>
      <button v-if="editing" type="button" class="rv-btn primary" @click="saveEdit">保存</button>
      <button v-if="editing" type="button" class="rv-btn" @click="cancelEdit">取消</button>
      <button v-if="!editing && content" type="button" class="rv-btn" @click="startEdit">编辑</button>
    </div>

    <div class="rv-body">
      <nav class="rv-sidebar">
        <div class="rv-sidebar-head">研究笔记</div>
        <div v-if="sortedNotes.length === 0" class="rv-sidebar-empty">
          暂无研究笔记
        </div>
        <button
          v-for="f in sortedNotes" :key="f.path"
          type="button" class="rv-file-btn"
          :class="{ active: selectedPath === f.path }"
          @click="openNote(f)"
        >
          <span>{{ f.name }}</span>
        </button>
      </nav>

      <div class="rv-main">
        <div v-if="!selectedPath" class="rv-welcome">
          <h3>AI + 工业落地研究</h3>
          <p>记录 AI 在工业仿真中的应用研究、技术调研和落地分析。</p>
          <div class="rv-topics">
            <div class="rv-topic">
              <strong>AI 辅助建模</strong>
              <span>自然语言 → 仿真参数、自动前处理</span>
            </div>
            <div class="rv-topic">
              <strong>AI 替代求解器</strong>
              <span>PINN、Neural Operator、Physics Foundation Models</span>
            </div>
            <div class="rv-topic">
              <strong>AI 结果分析</strong>
              <span>自动后处理、异常检测、报告生成</span>
            </div>
            <div class="rv-topic">
              <strong>AI + 传统 CAE</strong>
              <span>混合求解策略、自适应网格、优化设计</span>
            </div>
          </div>
        </div>

        <div v-else-if="editing" class="rv-editor-wrap">
          <textarea
            v-model="editContent"
            class="rv-editor"
            spellcheck="false"
          />
        </div>

        <div v-else class="rv-content" v-html="renderMarkdown(content || '*空文件*')" />
      </div>
    </div>

    <!-- New Note Dialog -->
    <div v-if="showNewDialog" class="rv-overlay" @click.self="cancelNewDialog">
      <div class="rv-dialog">
        <h4>新建研究笔记</h4>
        <input
          v-model="newNoteName"
          class="rv-dialog-input"
          placeholder="文件名"
          @keyup.enter="confirmNewNote"
          @keyup.escape="cancelNewDialog"
          autofocus
        />
        <div class="rv-dialog-path">learning/research/</div>
        <div class="rv-dialog-actions">
          <button type="button" class="rv-btn" @click="cancelNewDialog" :disabled="creatingNote">取消</button>
          <button type="button" class="rv-btn primary" @click="confirmNewNote" :disabled="creatingNote">
            {{ creatingNote ? '创建中…' : '创建' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rv { display: flex; flex-direction: column; height: 100%; padding: 0 20px; }

.rv-top {
  display: flex; align-items: center; gap: 10px;
  flex-shrink: 0; padding: 12px 0; border-bottom: 1px solid var(--border-subtle);
}

.rv-back { background: none; border: none; color: var(--text-muted); cursor: pointer; padding: 2px; }
.rv-back:hover { color: var(--text-body); }

.rv-title { font-size: 0.85rem; font-weight: 600; color: var(--text-heading); }
.rv-saved { font-size: 0.7rem; color: var(--green); }

.rv-spacer { flex: 1; }

.rv-btn {
  padding: 5px 12px; background: var(--bg-card); border: 1px solid var(--border-default);
  border-radius: 5px; color: var(--text-muted); font-size: 0.72rem; cursor: pointer;
}
.rv-btn:hover { border-color: var(--border-strong); color: var(--text-body); }
.rv-btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }

.rv-body { display: flex; flex: 1; min-height: 0; }

.rv-sidebar {
  width: 190px; flex-shrink: 0; overflow-y: auto;
  border-right: 1px solid var(--border-subtle); padding: 10px 8px;
}

.rv-sidebar-head {
  font-size: 0.62rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--text-dim); padding: 0 6px 8px;
}

.rv-sidebar-empty {
  font-size: 0.72rem; color: var(--text-dim); padding: 8px 6px;
}

.rv-file-btn {
  display: block; width: 100%; padding: 5px 6px; background: none; border: none;
  border-radius: 4px; color: var(--text-body); font-size: 0.74rem;
  cursor: pointer; text-align: left; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.rv-file-btn:hover { background: rgba(255,255,255,0.03); }
.rv-file-btn.active { background: var(--accent-glow); color: var(--accent); }

.rv-main { flex: 1; min-width: 0; overflow-y: auto; padding: 20px 24px; }

.rv-welcome {
  max-width: 600px; margin: 0 auto;
}

.rv-welcome h3 { font-size: 1.1rem; color: var(--text-heading); margin: 0 0 6px; }
.rv-welcome p { font-size: 0.82rem; color: var(--text-muted); margin: 0 0 20px; }

.rv-topics { display: flex; flex-direction: column; gap: 10px; }

.rv-topic {
  padding: 12px 14px; background: var(--bg-card); border: 1px solid var(--border-default);
  border-radius: 8px;
}

.rv-topic strong { display: block; font-size: 0.82rem; color: var(--text-heading); margin-bottom: 2px; }
.rv-topic span { font-size: 0.72rem; color: var(--text-dim); }

.rv-editor-wrap { height: 100%; padding: 0; }

.rv-editor {
  width: 100%; height: 100%; padding: 14px; background: var(--bg-input);
  border: 1px solid var(--border-default); border-radius: 6px;
  color: var(--text-body); font-family: 'Cascadia Code', 'JetBrains Mono', Consolas, monospace;
  font-size: 0.8rem; line-height: 1.65; resize: none; outline: none; box-sizing: border-box;
  tab-size: 4;
}

.rv-editor:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-glow); }

/* ── Content container ── */

.rv-content {
  max-width: 960px; margin: 0 auto;
  font-size: 0.85rem; line-height: 1.85; color: var(--text-body);
  padding-bottom: 60px;
}

/* ── Headings ── */

.rv-content :deep(h1) {
  font-size: 1.4rem; font-weight: 800; color: var(--text-heading);
  margin: 36px 0 16px; padding-bottom: 10px;
  border-bottom: 1px solid var(--border-default);
  letter-spacing: -0.01em;
}

.rv-content :deep(h2) {
  font-size: 1.12rem; font-weight: 700; color: var(--text-heading);
  margin: 32px 0 12px; padding-left: 12px;
  border-left: 3px solid var(--accent);
}

.rv-content :deep(h3) {
  font-size: 0.95rem; font-weight: 600; color: var(--text-heading);
  margin: 22px 0 10px;
}

.rv-content :deep(h4) {
  font-size: 0.85rem; font-weight: 600; color: var(--text-heading);
  margin: 16px 0 8px;
}

/* ── Paragraph ── */

.rv-content :deep(p) {
  margin: 10px 0; color: var(--text-body);
}

.rv-content :deep(strong) {
  color: var(--text-heading); font-weight: 700;
}

/* ── Links ── */

.rv-content :deep(a) {
  color: var(--accent-hover); text-decoration: none;
  border-bottom: 1px solid var(--accent-border);
  transition: border-color var(--transition-fast);
}
.rv-content :deep(a:hover) {
  color: var(--accent); border-bottom-color: var(--accent);
}

/* ── Inline code ── */

.rv-content :deep(code) {
  background: var(--bg-input); padding: 2px 7px; border-radius: 4px;
  font-size: 0.88em; color: var(--accent-blue); font-family: var(--font-mono);
  white-space: nowrap;
}

/* ── Fenced code block ── */

.rv-content :deep(pre) {
  background: var(--bg-input); border: 1px solid var(--border-default);
  border-radius: 8px; padding: 16px 20px; overflow-x: auto;
  font-size: 0.78rem; line-height: 1.65; margin: 16px 0;
  tab-size: 4;
}
.rv-content :deep(pre code) {
  background: none; padding: 0; border-radius: 0; font-size: inherit;
  white-space: pre; color: var(--text-body);
}

/* ── Table ── */

.rv-content :deep(table) {
  width: 100%; border-collapse: collapse; margin: 16px 0 20px;
  font-size: 0.8rem; font-variant-numeric: tabular-nums;
  border: 1px solid var(--border-default); border-radius: 8px;
  overflow: hidden;
}

.rv-content :deep(thead) {
  border-bottom: 2px solid var(--border-strong);
}

.rv-content :deep(th) {
  background: var(--bg-panel); color: var(--text-muted); font-weight: 700;
  padding: 10px 14px; text-align: left;
  font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em;
  white-space: nowrap;
}

.rv-content :deep(td) {
  padding: 8px 14px; border-bottom: 1px solid var(--border-subtle);
  color: var(--text-body); vertical-align: top;
}

.rv-content :deep(tr:nth-child(even) td) {
  background: rgba(255,255,255,0.015);
}

.rv-content :deep(tr:hover td) {
  background: rgba(139,92,246,0.05);
}

/* ── Blockquote ── */

.rv-content :deep(blockquote) {
  border-left: 3px solid var(--accent); margin: 16px 0; padding: 12px 18px;
  color: var(--text-muted); background: var(--accent-glow);
  border-radius: 0 8px 8px 0;
}

.rv-content :deep(blockquote strong) {
  color: var(--accent-hover);
}

.rv-content :deep(blockquote p) {
  margin: 4px 0; color: var(--text-muted);
}

/* ── Lists ── */

.rv-content :deep(ul), .rv-content :deep(ol) {
  margin: 10px 0; padding-left: 24px;
}

.rv-content :deep(li) {
  margin: 5px 0; color: var(--text-body); line-height: 1.75;
}

.rv-content :deep(li > ul), .rv-content :deep(li > ol) {
  margin: 4px 0;
}

.rv-content :deep(ul ul) { list-style-type: circle; }
.rv-content :deep(ul ul ul) { list-style-type: square; }

/* ── Horizontal rule ── */

.rv-content :deep(hr) {
  border: none; border-top: 1px solid var(--border-subtle);
  margin: 28px 0;
}

/* ── Images ── */

.rv-content :deep(img) {
  max-width: 100%; border-radius: 8px;
  border: 1px solid var(--border-default);
}

/* ── Inline emphasis ── */

.rv-content :deep(em) {
  font-style: italic; color: var(--text-muted);
}

/* ── Keyboard ── */

.rv-content :deep(kbd) {
  display: inline-block;
  padding: 2px 7px; font-size: 0.78em; font-family: var(--font-mono);
  background: var(--bg-input); border: 1px solid var(--border-default);
  border-radius: 4px; color: var(--text-muted);
  box-shadow: 0 1px 0 var(--border-default);
}

/* ── Vertical rhythm helpers ── */

.rv-content :deep(h1:first-child),
.rv-content :deep(h2:first-child),
.rv-content :deep(h3:first-child) { margin-top: 0; }

/* ── New Note Dialog ── */

.rv-overlay {
  position: fixed; inset: 0; z-index: 100;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,0.55);
}

.rv-dialog {
  width: 380px; max-width: 90vw;
  background: var(--bg-panel); border: 1px solid var(--border-strong);
  border-radius: 10px; padding: 20px 22px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
}

.rv-dialog h4 {
  margin: 0 0 14px; font-size: 0.9rem; font-weight: 700; color: var(--text-heading);
}

.rv-dialog-input {
  width: 100%; padding: 8px 10px;
  background: var(--bg-input); border: 1px solid var(--border-default);
  border-radius: 6px; color: var(--text-body); font-size: 0.82rem;
  outline: none; box-sizing: border-box;
}

.rv-dialog-input:focus {
  border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-glow);
}

.rv-dialog-path {
  margin-top: 6px; font-size: 0.68rem; color: var(--text-dim);
  font-family: var(--font-mono);
}

.rv-dialog-actions {
  display: flex; justify-content: flex-end; gap: 8px;
  margin-top: 16px;
}
</style>

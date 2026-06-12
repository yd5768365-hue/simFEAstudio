<script setup lang="ts">
import { computed, nextTick, onActivated, onMounted, ref, watch } from 'vue'
import { createSimfeaClient } from '@/api/simfeaClient'
import type { KnowledgeDocument, RunArchive } from '@/types'
import { formatDate } from '@/utils/date'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources: { text: string; source: string; score: number }[]
}

interface ChatSession {
  id: string
  title: string
  date: string
  messages: ChatMessage[]
}

const CHAT_HISTORY_KEY = 'simfea-chat-history'

const props = defineProps<{
  runs: RunArchive[]
  apiBaseUrl: string
}>()

const emit = defineEmits<{ back: [] }>()

const api = createSimfeaClient(props.apiBaseUrl, () => {})
const baseUrl = props.apiBaseUrl.replace(/\/+$/, '')

const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const loading = ref(false)
const error = ref('')
const showRunPanel = ref(false)
const showKbPanel = ref(false)
const selectedRunId = ref('')
const chatBody = ref<HTMLElement | null>(null)

// Knowledge
const knowledgeDocs = ref<KnowledgeDocument[]>([])
const selectedDocIds = ref<Set<string>>(new Set())
const filePathInput = ref('')
const filePathMsg = ref('')

// History
const sessions = ref<ChatSession[]>([])
const currentSessionId = ref('')
const showHistory = ref(false)

// ── Knowledge ──────────────────────────────────
async function loadDocs() {
  try {
    const r = await api.listKnowledgeDocuments()
    knowledgeDocs.value = r.data.documents
  } catch {
    knowledgeDocs.value = []
  }
}

function toggleDoc(docId: string) {
  const next = new Set(selectedDocIds.value)
  if (next.has(docId)) {
    next.delete(docId)
  } else {
    next.add(docId)
  }
  selectedDocIds.value = next
}

async function ingestByPath() {
  const path = filePathInput.value.trim()
  if (!path) return
  filePathMsg.value = '索引中…'
  try {
    const r = await fetch(`${baseUrl}/v1/knowledge/documents/by-path`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    })
    const j = await r.json()
    if (r.ok) {
      filePathMsg.value = `已索引: ${j.data.name} (${j.data.chunk_count} 块)`
      filePathInput.value = ''
      await loadDocs()
    } else {
      filePathMsg.value = `失败: ${j.detail || r.status}`
    }
  } catch {
    filePathMsg.value = '请求失败'
  }
}

// ── History ────────────────────────────────────
function loadHistory() {
  try {
    const raw = localStorage.getItem(CHAT_HISTORY_KEY)
    sessions.value = raw ? (JSON.parse(raw) as ChatSession[]) : []
  } catch {
    sessions.value = []
  }
}

function saveHistory() {
  try {
    localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(sessions.value.slice(0, 20)))
  } catch {
    /* */
  }
}

function newSession() {
  const s: ChatSession = {
    id: Date.now().toString(36),
    title: `对话 ${sessions.value.length + 1}`,
    date: new Date().toISOString(),
    messages: [],
  }
  sessions.value.unshift(s)
  currentSessionId.value = s.id
  messages.value = []
  saveHistory()
}

function saveCurrentSession() {
  if (!currentSessionId.value || messages.value.length === 0) return
  const s = sessions.value.find((s) => s.id === currentSessionId.value)
  if (!s) return
  s.messages = [...messages.value]
  s.date = new Date().toISOString()
  if (s.messages.length > 0) {
    const first = s.messages[0].content
    s.title = first.slice(0, 30) + (first.length > 30 ? '…' : '')
  }
  saveHistory()
}

function openSession(id: string) {
  const s = sessions.value.find((s) => s.id === id)
  if (!s) return
  currentSessionId.value = s.id
  messages.value = [...s.messages]
  showHistory.value = false
}

function deleteSession(id: string) {
  sessions.value = sessions.value.filter((s) => s.id !== id)
  if (currentSessionId.value === id) {
    currentSessionId.value = ''
    messages.value = []
  }
  saveHistory()
}

// Auto-save on message change
watch(
  messages,
  () => {
    if (currentSessionId.value) saveCurrentSession()
  },
  { deep: true }
)

// ── Chat ──────────────────────────────────────
const runsWithLearning = computed(() => props.runs.filter((run) => run.note || run.learning_report))

const selectedRun = computed(() => props.runs.find((r) => r.run_id === selectedRunId.value) ?? null)

const selectedMetrics = computed(() => selectedRun.value?.summary?.metrics ?? null)

onMounted(() => {
  loadDocs()
  loadHistory()
})
onActivated(() => {
  loadDocs()
  loadHistory()
})

function metricText(key: string, unit: string): string {
  const m = selectedMetrics.value as Record<string, unknown> | null
  const value = m?.[key]
  return typeof value === 'number' ? `${(value as number).toFixed(3)} ${unit}` : '—'
}

function msgId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

async function scrollToBottom() {
  await nextTick()
  if (chatBody.value) {
    chatBody.value.scrollTop = chatBody.value.scrollHeight
  }
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || loading.value) return

  if (!currentSessionId.value) newSession()

  messages.value.push({ id: msgId(), role: 'user', content: text, sources: [] })
  inputText.value = ''
  loading.value = true
  error.value = ''
  await scrollToBottom()

  const docIds = selectedDocIds.value.size > 0 ? [...selectedDocIds.value] : undefined
  try {
    const result = await api.askKnowledge(text, selectedRunId.value || undefined, docIds)
    messages.value.push({
      id: msgId(),
      role: 'assistant',
      content: result.data.answer,
      sources: result.data.sources.filter((s) => s.score > 0),
    })
  } catch (err) {
    messages.value.push({ id: msgId(), role: 'assistant', content: `请求失败：${err}`, sources: [] })
    error.value = String(err)
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}

function clearChat() {
  messages.value = []
  error.value = ''
}
</script>

<template>
  <div class="chat">
    <!-- Top bar -->
    <div class="chat-top">
      <button type="button" class="chat-top-back" @click="emit('back')">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M10 3L5 8l5 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <span>返回</span>
      </button>
      <div class="chat-top-right">
        <button type="button" class="chat-top-btn" :class="{ active: showHistory }" @click="showHistory = !showHistory; showRunPanel = false; showKbPanel = false">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="2" y="2" width="12" height="12" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M5 5h6M5 8h6M5 11h4" stroke="currentColor" stroke-width="1" stroke-linecap="round"/></svg>
          <span>历史</span>
        </button>
        <button type="button" class="chat-top-btn" :class="{ active: selectedRunId }" @click="showRunPanel = !showRunPanel; showKbPanel = false; showHistory = false">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="6" cy="6" r="4.5" stroke="currentColor" stroke-width="1.3"/><path d="M9.5 9.5L14 14" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>
          <span>{{ selectedRunId ? selectedRun?.case_name?.slice(0, 12) || '已关联' : '关联运行' }}</span>
        </button>
        <button type="button" class="chat-top-btn" :class="{ active: selectedDocIds.size > 0 }" @click="showKbPanel = !showKbPanel; showRunPanel = false; showHistory = false">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="2" y="2" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.2"/><rect x="9" y="2" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.2"/><rect x="2" y="9" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.2"/><rect x="9" y="9" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.2"/></svg>
          <span>知识库{{ selectedDocIds.size ? ` (${selectedDocIds.size})` : '' }}</span>
        </button>
        <button v-if="messages.length" type="button" class="chat-top-btn" @click="clearChat">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M2 4h12l-1 10H3L2 4z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M5 4V2h6v2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>
        </button>
      </div>
    </div>

    <!-- History panel -->
    <div v-if="showHistory" class="chat-panel">
      <button type="button" class="chat-panel-action" @click="newSession()">+ 新对话</button>
      <div v-if="sessions.length === 0" class="chat-panel-empty">暂无历史记录</div>
      <div v-for="s in sessions" :key="s.id" class="chat-hist-item" :class="{ active: s.id === currentSessionId }" @click="openSession(s.id)">
        <div class="chat-hist-body">
          <span class="chat-hist-title">{{ s.title }}</span>
          <span class="chat-hist-date">{{ s.date.slice(0, 10) }}</span>
        </div>
        <button type="button" class="chat-hist-del" @click.stop="deleteSession(s.id)">×</button>
      </div>
    </div>

    <!-- Run panel -->
    <div v-if="showRunPanel" class="chat-panel">
      <select v-model="selectedRunId" class="chat-ctx-select">
        <option value="">不关联运行记录</option>
        <option v-for="run in runsWithLearning" :key="run.run_id" :value="run.run_id">
          {{ run.case_name }} &nbsp;·&nbsp; {{ run.solver }} &nbsp;·&nbsp; {{ formatDate(run.created_at) }}
        </option>
      </select>
      <div v-if="selectedRun" class="chat-ctx-info">
        <span class="status-pill" :class="selectedRun.status === 'finished' ? 'online' : selectedRun.status === 'failed' ? 'offline' : 'pending'">{{ selectedRun.status }}</span>
        <span>{{ selectedRun.solver }}</span>
        <span v-if="selectedMetrics">位移 {{ metricText('max_displacement_mm', 'mm') }} &nbsp;·&nbsp; 应力 {{ metricText('max_von_mises_mpa', 'MPa') }}</span>
      </div>
    </div>

    <!-- Knowledge panel -->
    <div v-if="showKbPanel" class="chat-panel">
      <div class="chat-kb-section">
        <div class="chat-kb-label">已索引文档</div>
        <p v-if="knowledgeDocs.length === 0" class="chat-panel-empty">暂无文档</p>
        <label v-for="doc in knowledgeDocs" :key="doc.id" class="chat-doc">
          <input type="checkbox" :checked="selectedDocIds.has(doc.id)" @change="toggleDoc(doc.id)" />
          <span>{{ doc.name }}</span>
          <small>{{ doc.chunk_count }} 块</small>
        </label>
      </div>
      <div class="chat-kb-section">
        <div class="chat-kb-label">输入文件路径</div>
        <div class="chat-kb-path-row">
          <input v-model="filePathInput" type="text" class="chat-kb-path-input" placeholder="C:\Users\...\讲义.pdf" @keydown.enter="ingestByPath" />
          <button type="button" class="chat-kb-path-btn" @click="ingestByPath">索引</button>
        </div>
        <p v-if="filePathMsg" class="chat-kb-path-msg" :class="{ ok: filePathMsg.startsWith('已索引') }">{{ filePathMsg }}</p>
      </div>
    </div>

    <!-- Messages -->
    <div ref="chatBody" class="chat-body">
      <div v-if="messages.length === 0 && !loading" class="chat-empty">
        <div class="chat-empty-icon">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none"><rect x="2" y="2" width="20" height="20" rx="4" stroke="currentColor" stroke-width="1.2"/><path d="M7 8h10M7 12h7M7 16h4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
        </div>
        <p class="chat-empty-title">SimFEA AI 助手</p>
        <p class="chat-empty-desc">基于知识库文档和运行数据回答你的问题。</p>
        <div class="chat-empty-hints">
          <button v-for="hint in ['为什么最大应力出现在固定端？', '如何验证仿真结果的准确性？', '有限元方法的基本原理是什么？']" :key="hint" type="button" class="chat-empty-hint" @click="inputText = hint; sendMessage()">{{ hint }}</button>
        </div>
      </div>

      <template v-for="msg in messages" :key="msg.id">
        <div class="chat-msg" :class="msg.role">
          <div class="chat-msg-inner">
            <div class="chat-msg-role">{{ msg.role === 'user' ? 'You' : 'AI' }}</div>
            <div class="chat-msg-text">{{ msg.content }}</div>
            <div v-if="msg.sources.length" class="chat-msg-refs">
              <span class="chat-msg-refs-label">参考</span>
              <span v-for="(s, i) in msg.sources.slice(0, 3)" :key="i" class="chat-msg-ref">{{ s.source }} <em>{{ (s.score * 100).toFixed(0) }}%</em></span>
            </div>
          </div>
        </div>
      </template>

      <div v-if="loading" class="chat-msg assistant">
        <div class="chat-msg-inner">
          <div class="chat-msg-role">AI</div>
          <div class="chat-msg-loading"><span></span><span></span><span></span></div>
        </div>
      </div>
    </div>

    <!-- Input -->
    <div class="chat-foot">
      <div class="chat-foot-inner">
        <input v-model="inputText" type="text" class="chat-foot-input" placeholder="输入你的问题…" :disabled="loading" @keydown.enter="sendMessage" />
        <button type="button" class="chat-foot-send" :disabled="loading || !inputText.trim()" @click="sendMessage">
          <svg v-if="!loading" width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" class="spin"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" stroke-dasharray="32" stroke-dashoffset="8" stroke-linecap="round"/></svg>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── Root ────────────────────────────────────── */
.chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-width: 700px;
  margin: 0 auto;
  padding: 0 16px;
}

/* ── Top bar ─────────────────────────────────── */
.chat-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  padding: 10px 0 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.chat-top-back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 0.82rem;
  cursor: pointer;
  padding: 4px 0;
  transition: color var(--transition-fast);
}

.chat-top-back:hover { color: var(--text-body); }

.chat-top-right {
  display: flex;
  gap: 6px;
}

.chat-top-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  background: none;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-muted);
  font-size: 0.72rem;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.chat-top-btn:hover { border-color: var(--border-strong); color: var(--text-body); }
.chat-top-btn.active { background: var(--accent-glow); border-color: var(--accent-border); color: var(--accent); }

/* ── Panels (shared) ─────────────────────────── */
.chat-panel {
  flex-shrink: 0;
  padding: 8px 0;
  border-bottom: 1px solid var(--border-subtle);
  display: flex; flex-direction: column; gap: 4px;
  max-height: 200px; overflow-y: auto;
}

.chat-panel-empty { font-size: 0.7rem; color: var(--text-dim); padding: 4px 0; }

.chat-panel-action {
  align-self: flex-start;
  padding: 4px 10px; background: var(--accent); color: #fff;
  border: none; border-radius: 4px; font-size: 0.7rem; cursor: pointer;
}

.chat-panel-action:hover { background: var(--accent-hover); }

/* ── History ─────────────────────────────────── */
.chat-hist-item {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 8px; border-radius: 4px; cursor: pointer;
  transition: background var(--transition-fast);
}

.chat-hist-item:hover { background: rgba(255,255,255,0.03); }
.chat-hist-item.active { background: var(--accent-glow); }

.chat-hist-body { flex: 1; min-width: 0; }

.chat-hist-title {
  display: block; font-size: 0.76rem; color: var(--text-body);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

.chat-hist-date { font-size: 0.64rem; color: var(--text-dim); }

.chat-hist-del {
  background: none; border: none; color: var(--text-dim);
  font-size: 0.9rem; cursor: pointer; padding: 0 4px;
  opacity: 0; transition: opacity var(--transition-fast);
}

.chat-hist-item:hover .chat-hist-del { opacity: 1; }
.chat-hist-del:hover { color: var(--red); }

/* ── Run selector ────────────────────────────── */
.chat-ctx-select {
  width: 100%;
  padding: 7px 10px;
  background: var(--bg-input); color: var(--text-body);
  border: 1px solid var(--border-default); border-radius: 6px;
  font-family: var(--font-ui); font-size: 0.78rem; cursor: pointer;
}

.chat-ctx-select:focus { outline: none; border-color: var(--accent); }

.chat-ctx-info {
  display: flex; align-items: center; gap: 10px;
  font-size: 0.76rem; color: var(--text-muted);
}

/* ── Knowledge panel ─────────────────────────── */
.chat-kb-section {
  display: flex; flex-direction: column; gap: 4px;
}

.chat-kb-label {
  font-size: 0.65rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.05em; color: var(--text-dim); padding: 2px 0;
}

.chat-doc {
  display: flex; align-items: center; gap: 6px;
  padding: 3px 4px; border-radius: 3px; cursor: pointer;
  font-size: 0.72rem; color: var(--text-muted);
}

.chat-doc:hover { background: rgba(255,255,255,0.03); }
.chat-doc input[type="checkbox"] { accent-color: var(--accent); cursor: pointer; }
.chat-doc small { margin-left: auto; color: var(--text-dim); font-size: 0.62rem; }

.chat-kb-path-row {
  display: flex; gap: 6px;
}

.chat-kb-path-input {
  flex: 1; padding: 6px 10px;
  background: var(--bg-input); color: var(--text-body);
  border: 1px solid var(--border-default); border-radius: 4px;
  font-family: 'Cascadia Code', 'JetBrains Mono', Consolas, monospace;
  font-size: 0.72rem; outline: none;
}

.chat-kb-path-input:focus { border-color: var(--accent); }

.chat-kb-path-btn {
  padding: 6px 14px; background: var(--accent); color: #fff;
  border: none; border-radius: 4px; font-size: 0.72rem; cursor: pointer;
}

.chat-kb-path-btn:hover { background: var(--accent-hover); }

.chat-kb-path-msg {
  margin: 0; font-size: 0.66rem; color: var(--text-dim);
}

.chat-kb-path-msg.ok { color: var(--green); }

/* ── Message body ────────────────────────────── */
.chat-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 0;
}

/* ── Empty state ─────────────────────────────── */
.chat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 32px 16px 16px;
}

.chat-empty-icon {
  color: var(--text-dim);
  margin-bottom: 10px;
  opacity: 0.5;
}

.chat-empty-title {
  margin: 0 0 4px;
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-heading);
}

.chat-empty-desc {
  margin: 0 0 14px;
  font-size: 0.78rem;
  color: var(--text-muted);
  max-width: 360px;
}

.chat-empty-hints {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}

.chat-empty-hint {
  padding: 8px 14px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-muted);
  font-size: 0.78rem;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.chat-empty-hint:hover {
  border-color: var(--border-strong);
  color: var(--text-body);
}

/* ── Message ─────────────────────────────────── */
.chat-msg + .chat-msg {
  margin-top: 16px;
}

.chat-msg-inner {
  max-width: 88%;
}

.chat-msg.user .chat-msg-inner {
  margin-left: auto;
}

.chat-msg-role {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-dim);
  margin-bottom: 4px;
  padding: 0 2px;
}

.chat-msg-text {
  font-size: 0.86rem;
  line-height: 1.7;
  color: var(--text-body);
  white-space: pre-wrap;
  word-break: break-word;
}

/* ── References ──────────────────────────────── */
.chat-msg-refs {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.chat-msg-refs-label {
  font-size: 0.65rem;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.chat-msg-ref {
  font-size: 0.7rem;
  padding: 2px 8px;
  background: var(--bg-input);
  border-radius: 4px;
  color: var(--text-muted);
}

.chat-msg-ref em {
  font-style: normal;
  color: var(--accent-blue);
  font-family: var(--font-mono);
  margin-left: 2px;
}

/* ── Loading ─────────────────────────────────── */
.chat-msg-loading {
  display: flex;
  gap: 5px;
  padding: 8px 0;
}

.chat-msg-loading span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-dim);
  animation: chat-pulse 1.2s infinite;
}

.chat-msg-loading span:nth-child(2) { animation-delay: 0.2s; }
.chat-msg-loading span:nth-child(3) { animation-delay: 0.4s; }

@keyframes chat-pulse {
  0%, 80%, 100% { opacity: 0.2; }
  40% { opacity: 0.8; }
}

/* ── Input ───────────────────────────────────── */
.chat-foot {
  flex-shrink: 0;
  padding: 10px 0 14px;
}

.chat-foot-inner {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 6px 6px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.chat-foot-inner:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow);
}

.chat-foot-input {
  flex: 1;
  background: none;
  border: none;
  color: var(--text-body);
  font-family: var(--font-ui);
  font-size: 0.86rem;
  outline: none;
  padding: 4px 0;
}

.chat-foot-input::placeholder { color: var(--text-dim); }
.chat-foot-input:disabled { opacity: 0.4; }

.chat-foot-send {
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--text-body);
  border: none;
  border-radius: 8px;
  color: var(--bg-app);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.chat-foot-send:hover:not(:disabled) { background: var(--text-heading); }
.chat-foot-send:disabled { opacity: 0.2; cursor: not-allowed; }

.spin {
  animation: chat-spin 1s linear infinite;
}

@keyframes chat-spin {
  to { transform: rotate(360deg); }
}
</style>

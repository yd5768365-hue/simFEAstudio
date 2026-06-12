<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  apiBaseUrl: string
  disabled: boolean
}>()

const emit = defineEmits<{
  'task-translated': [
    config: {
      solver: string
      caseName: string
      explanation: string
      suggestedParams: Record<string, string>
    },
  ]
}>()

const description = ref('')
const loading = ref(false)
const error = ref('')
const result = ref<{
  solver: string
  caseName: string
  explanation: string
  suggestedParams: Record<string, string>
} | null>(null)

async function submitTask() {
  const text = description.value.trim()
  if (!text || loading.value) return

  loading.value = true
  error.value = ''
  result.value = null

  try {
    const resp = await fetch(`${props.apiBaseUrl}/v1/completions/translate-task`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description: text }),
    })
    if (!resp.ok) {
      const detail = await resp.text().catch(() => '')
      throw new Error(`请求失败 (${resp.status}): ${detail}`)
    }
    const json = await resp.json()
    const data = json.data as Record<string, unknown>
    result.value = {
      solver: String(data.solver || ''),
      caseName: String(data.case_name || ''),
      explanation: String(data.explanation || ''),
      suggestedParams: (data.suggested_params as Record<string, string>) || {},
    }
  } catch (err) {
    error.value = `分析失败：${err}`
  } finally {
    loading.value = false
  }
}

function applyConfig() {
  if (!result.value) return
  emit('task-translated', {
    solver: result.value.solver,
    caseName: result.value.caseName,
    explanation: result.value.explanation,
    suggestedParams: result.value.suggestedParams,
  })
  // Reset after applying
  description.value = ''
  result.value = null
}

function dismissResult() {
  result.value = null
}
</script>

<template>
  <div class="chat-task-input">
    <div class="chat-input-row">
      <input
        v-model="description"
        type="text"
        class="chat-text-input"
        placeholder="描述你的仿真任务，例如：一根长 1m 的钢杆受 1000N 拉力，计算位移和应力"
        :disabled="loading || props.disabled"
        @keydown.enter="submitTask"
      />
      <button
        type="button"
        class="chat-submit-btn"
        :disabled="loading || !description.trim() || props.disabled"
        @click="submitTask"
      >
        {{ loading ? '分析中…' : '分析' }}
      </button>
    </div>

    <p v-if="error" class="chat-error">{{ error }}</p>

    <div v-if="result" class="chat-result-card">
      <div class="chat-result-head">
        <span class="chat-result-solver">求解器：{{ result.solver }}</span>
        <span class="chat-result-case">算例：{{ result.caseName }}</span>
        <button type="button" class="chat-result-dismiss" @click="dismissResult">✕</button>
      </div>
      <p class="chat-result-explanation">{{ result.explanation }}</p>
      <dl v-if="Object.keys(result.suggestedParams).length" class="chat-result-params">
        <div v-for="(value, key) in result.suggestedParams" :key="key">
          <dt>{{ key }}</dt>
          <dd>{{ value }}</dd>
        </div>
      </dl>
      <div class="chat-result-actions">
        <button type="button" class="chat-apply-btn" @click="applyConfig">
          应用此配置
        </button>
      </div>
    </div>
  </div>
</template>

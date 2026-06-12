<script setup lang="ts">
import { computed, onActivated, onMounted, ref } from 'vue'
import { createSimfeaClient } from '@/api/simfeaClient'
import type { KnowledgeDocument } from '@/types'

const props = defineProps<{
  apiBaseUrl: string
}>()

const emit = defineEmits<{
  back: []
}>()

const api = createSimfeaClient(props.apiBaseUrl, () => {})

const documents = ref<KnowledgeDocument[]>([])
const uploading = ref(false)
const uploadMessage = ref('')
const uploadError = ref('')
const loading = ref(true)

const hasDocuments = computed(() => documents.value.length > 0)

async function loadDocuments() {
  loading.value = true
  try {
    const result = await api.listKnowledgeDocuments()
    documents.value = result.data.documents
  } catch {
    documents.value = []
  } finally {
    loading.value = false
  }
}

async function handleFileUpload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  const suffix = file.name.split('.').pop()?.toLowerCase()
  if (!suffix || !['pdf', 'md', 'txt', 'markdown'].includes(suffix)) {
    uploadError.value = `不支持的文件格式: .${suffix || '未知'}。支持 .pdf, .md, .txt`
    return
  }

  uploading.value = true
  uploadMessage.value = ''
  uploadError.value = ''
  try {
    const result = await api.uploadKnowledgeDocument(file)
    uploadMessage.value = `"${result.data.name}" 已上传（${result.data.chunk_count} 个文本块）`
    await loadDocuments()
  } catch (err) {
    uploadError.value = `上传失败：${err}`
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function deleteDocument(docId: string) {
  try {
    await api.deleteKnowledgeDocument(docId)
    documents.value = documents.value.filter((d) => d.id !== docId)
  } catch {
    // silently ignore
  }
}

function handleDragOver(event: DragEvent) {
  event.preventDefault()
}

function handleDrop(event: DragEvent) {
  event.preventDefault()
  const file = event.dataTransfer?.files?.[0]
  if (!file) return
  const dataTransfer = new DataTransfer()
  dataTransfer.items.add(file)
  const syntheticEvent = { target: { files: dataTransfer.files, value: '' } } as unknown as Event
  handleFileUpload(syntheticEvent)
}

onMounted(loadDocuments)
onActivated(loadDocuments)
</script>

<template>
  <div class="knowledge-panel">
    <header class="kp-header">
      <button type="button" @click="emit('back')">← 返回</button>
      <h2>知识库</h2>
      <span class="kp-count">{{ documents.length }} 份文档</span>
    </header>

    <section class="kp-upload">
      <div
        class="kp-dropzone"
        :class="{ uploading }"
        @dragover="handleDragOver"
        @drop="handleDrop"
      >
        <p>拖拽文档到此处，或点击选择文件</p>
        <p class="kp-dropzone-hint">支持 PDF、Markdown、纯文本</p>
        <input
          type="file"
          accept=".pdf,.md,.txt,.markdown"
          :disabled="uploading"
          @change="handleFileUpload"
        />
        <span v-if="uploading" class="kp-upload-status">正在处理和嵌入…</span>
      </div>
      <p v-if="uploadMessage" class="kp-message ok">{{ uploadMessage }}</p>
      <p v-if="uploadError" class="kp-message error">{{ uploadError }}</p>
    </section>

    <section class="kp-documents">
      <p v-if="loading">加载中…</p>
      <p v-else-if="!hasDocuments" class="empty-state">
        知识库为空。上传教材或讲义 PDF 后即可使用 AI 问答功能。
      </p>
      <ul v-else class="kp-doc-list">
        <li v-for="doc in documents" :key="doc.id" class="kp-doc-item">
          <div class="kp-doc-info">
            <span class="kp-doc-name">{{ doc.name }}</span>
            <span class="kp-doc-meta">{{ doc.chunk_count }} 个文本块 · {{ doc.created_at.slice(0, 10) }}</span>
          </div>
          <button type="button" class="kp-doc-delete" @click="deleteDocument(doc.id)">删除</button>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{
  open: boolean
  title: string
  subtitle: string
  inputFiles: string[]
  workdir: string
}>()

const emit = defineEmits<{
  confirm: []
  cancel: []
  'update:workdir': [value: string]
}>()

const localWorkdir = ref(props.workdir)

const hasInputFiles = computed(() => props.inputFiles.length > 0)
</script>

<template>
  <div v-if="open" class="dialog-backdrop" @click.self="emit('cancel')">
    <div class="dialog-card" role="dialog" aria-label="运行配置">
      <div class="dialog-header">
        <strong>{{ title }}</strong>
        <p>{{ subtitle }}</p>
      </div>

      <div class="dialog-body">
        <label v-if="hasInputFiles">
          <span>输入文件</span>
          <p class="input-file-list">{{ inputFiles.join(' / ') }}</p>
        </label>

        <label>
          <span>工作目录</span>
          <input
            type="text"
            v-model="localWorkdir"
            class="dialog-input"
            placeholder=".simfea/runs"
          />
        </label>
      </div>

      <div class="dialog-actions">
        <button type="button" class="secondary-action" @click="emit('cancel')">取消</button>
        <button type="button" class="primary-action" @click="emit('confirm')">确认运行</button>
      </div>
    </div>
  </div>
</template>

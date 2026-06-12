<script setup lang="ts">
defineProps<{
  connected: boolean
  label: string
}>()

const emit = defineEmits<{
  reconnect: []
}>()
</script>

<template>
  <div class="cs-root" :class="{ offline: !connected }">
    <span class="cs-dot" :class="connected ? 'on' : 'off'"></span>
    <span class="cs-label">{{ label }}</span>
    <button v-if="!connected" class="cs-retry" @click="emit('reconnect')">重试</button>
  </div>
</template>

<style scoped>
.cs-root {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.72rem;
  color: var(--text-muted);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  transition: color var(--transition-fast);
}
.cs-root.offline { color: var(--danger, #ef4444); }

.cs-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.cs-dot.on  { background: #22c55e; box-shadow: 0 0 4px #22c55e88; }
.cs-dot.off { background: #ef4444; }

.cs-retry {
  margin-left: 4px;
  padding: 1px 8px;
  font-size: 0.65rem;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-body);
  cursor: pointer;
}
.cs-retry:hover { background: rgba(255,255,255,0.05); }
</style>

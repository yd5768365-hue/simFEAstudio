<script setup lang="ts">
import { ref } from 'vue'
import type { WorkflowSlotId, WorkflowSlotView, WorkflowToolOption } from '@/composables/workflowConfig'

defineProps<{
  workflowSlots: WorkflowSlotView[]
  selectedWorkflowSlotId: WorkflowSlotId
  enabledNodes: Set<WorkflowSlotId>
  dirtyNodes: Set<WorkflowSlotId>
  uploadedInputFiles: { name: string; size: number }[]
  mainInputFile: string
  fileCheckHint: string | null
  activeComputeNodeLabel: string
  workflowTools: Record<WorkflowSlotId, WorkflowToolOption[]>
  workflowToolSelection: Record<WorkflowSlotId, string>
  contextMenu: { show: boolean; x: number; y: number; slotId: WorkflowSlotId | null }
}>()

const emit = defineEmits<{
  'select-slot': [slotId: WorkflowSlotId]
  'toggle-node': [slotId: WorkflowSlotId]
  'apply-preset': [name: string]
  'tree-keydown': [event: KeyboardEvent]
  'context-menu': [slotId: WorkflowSlotId, event: MouseEvent]
  'files-dropped': [event: DragEvent]
  'files-selected': [event: Event]
  'remove-file': [name: string]
  'close-context-menu': []
  'switch-tool': [slotId: WorkflowSlotId, toolId: string]
  'update-node': [slotId: WorkflowSlotId]
  'reset-tool': [slotId: WorkflowSlotId]
}>()

const isDragOver = ref(false)
function onDragEnter(e: DragEvent) {
  e.preventDefault()
  isDragOver.value = true
}
function onDragOver(e: DragEvent) {
  e.preventDefault()
}
function onDragLeave() {
  isDragOver.value = false
}
function onDrop(e: DragEvent) {
  isDragOver.value = false
  emit('files-dropped', e)
}

const groups = [
  {
    key: 'pre',
    label: '前处理',
    color: '#38bdf8',
    slots: ['geometry', 'mesh', 'material', 'boundary'] as WorkflowSlotId[],
  },
  {
    key: 'solve',
    label: '求解',
    color: '#f59e0b',
    slots: ['solver'] as WorkflowSlotId[],
  },
  {
    key: 'post',
    label: '后处理',
    color: '#26a269',
    slots: ['post', 'validation'] as WorkflowSlotId[],
  },
]

function groupForSlot(slotId: WorkflowSlotId) {
  return groups.find((g) => g.slots.includes(slotId))!
}
</script>

<template>
  <div class="flow">
    <div class="flow-top">
      <div class="flow-top-left">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <rect x="3" y="3" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.3"/>
          <rect x="14" y="3" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.3"/>
          <rect x="3" y="14" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.3"/>
          <rect x="14" y="14" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.3"/>
          <path d="M10 6.5h4M10 17.5h4M6.5 10v4M17.5 10v4" stroke="currentColor" stroke-width="1" stroke-linecap="round"/>
        </svg>
        <span>仿真流程</span>
        <span class="flow-count">{{ workflowSlots.filter(s => enabledNodes.has(s.id)).length }}/{{ workflowSlots.length }}</span>
      </div>
      <div class="flow-presets">
        <button @click="emit('apply-preset', 'full')">完整</button>
        <button @click="emit('apply-preset', 'solver-only')">仅求解</button>
        <button @click="emit('apply-preset', 'geom-solver')">几何+求解</button>
      </div>
    </div>

    <div class="flow-canvas" @keydown="emit('tree-keydown', $event)">
      <template v-for="(group, gi) in groups" :key="group.key">
        <div class="flow-group">
          <div class="flow-group-head" :style="{ '--gc': group.color }">
            <span class="flow-group-dot"></span>
            <span>{{ group.label }}</span>
          </div>
          <div class="flow-group-body">
            <template v-for="(slotId, si) in group.slots" :key="slotId">
              <template v-if="workflowSlots.find(s => s.id === slotId)">
                <div
                  class="flow-node"
                  :class="{
                    selected: selectedWorkflowSlotId === slotId,
                    disabled: !enabledNodes.has(slotId),
                    dirty: dirtyNodes.has(slotId),
                  }"
                  tabindex="0"
                  @click="emit('select-slot', slotId)"
                  @contextmenu.prevent="emit('context-menu', slotId, $event)"
                >
                  <span class="flow-node-num">{{ workflowSlots.find(s => s.id === slotId)!.order }}</span>
                  <div class="flow-node-body">
                    <span class="flow-node-title">{{ workflowSlots.find(s => s.id === slotId)!.title }}</span>
                    <span class="flow-node-tool">{{ workflowToolSelection[slotId] ? workflowSlots.find(s => s.id === slotId)!.selectedTool.label : '' }}</span>
                  </div>
                  <span class="flow-node-badge" :class="dirtyNodes.has(slotId) ? 'dirty' : workflowSlots.find(s => s.id === slotId)!.status">
                    {{ dirtyNodes.has(slotId) ? '需更新' : workflowSlots.find(s => s.id === slotId)!.statusLabel }}
                  </span>
                </div>
                <!-- Arrow between nodes -->
                <div v-if="si < group.slots.length - 1" class="flow-arrow">
                  <svg width="12" height="16" viewBox="0 0 12 16"><path d="M6 0v12M2 9l4 4 4-4" stroke="currentColor" stroke-width="1.2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
                </div>
              </template>
            </template>
          </div>
        </div>
        <!-- Arrow between groups -->
        <div v-if="gi < groups.length - 1" class="flow-group-arrow">
          <svg width="16" height="24" viewBox="0 0 16 24"><path d="M8 0v20M3 17l5 5 5-5" stroke="currentColor" stroke-width="1.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>
      </template>
    </div>

    <!-- File drop (geometry) -->
    <div
      v-if="selectedWorkflowSlotId === 'geometry'"
      class="flow-drop"
      :class="{ active: isDragOver }"
      @dragenter="onDragEnter"
      @dragover.prevent="onDragOver"
      @dragleave="onDragLeave"
      @drop.prevent="onDrop"
    >
      <input type="file" multiple @change="emit('files-selected', $event)" />
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M12 6v12M6 12h12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
      <div>
        <span>{{ uploadedInputFiles.length ? mainInputFile : '拖拽或点击选择输入文件' }}</span>
        <small v-if="uploadedInputFiles.length">{{ uploadedInputFiles.length }} 个文件</small>
        <small v-else>.inp / .FCStd / .step / .geo</small>
      </div>
    </div>
    <div v-if="selectedWorkflowSlotId === 'geometry' && uploadedInputFiles.length" class="flow-files">
      <div v-for="f in uploadedInputFiles" :key="f.name" class="flow-file">
        <span>{{ f.name }}</span>
        <small>{{ f.size < 1024 ? `${f.size} B` : f.size < 1024 * 1024 ? `${(f.size / 1024).toFixed(1)} KB` : `${(f.size / 1024 / 1024).toFixed(1)} MB` }}</small>
        <button type="button" @click.stop="emit('remove-file', f.name)">&times;</button>
      </div>
    </div>
    <p v-if="selectedWorkflowSlotId === 'geometry' && fileCheckHint" class="flow-hint" :class="{ ok: fileCheckHint.includes('可直接提交') }">{{ fileCheckHint }}</p>

    <!-- Context menu -->
    <div
      v-if="contextMenu.show"
      class="flow-ctx"
      :style="{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }"
      @click.stop
    >
      <template v-if="contextMenu.slotId && workflowTools[contextMenu.slotId]">
        <div class="flow-ctx-label">切换工具</div>
        <button
          v-for="tool in workflowTools[contextMenu.slotId]"
          :key="tool.id"
          type="button"
          class="flow-ctx-item"
          :class="{ active: workflowToolSelection[contextMenu.slotId] === tool.id }"
          @click="emit('switch-tool', contextMenu.slotId!, tool.id)"
        >{{ tool.label }}</button>
        <div class="flow-ctx-sep"></div>
      </template>
      <button type="button" class="flow-ctx-item primary" @click="contextMenu.slotId ? emit('update-node', contextMenu.slotId) : null">从此节点开始执行</button>
      <div class="flow-ctx-sep"></div>
      <button type="button" class="flow-ctx-item" @click="contextMenu.slotId ? emit('reset-tool', contextMenu.slotId) : null">重置为默认</button>
      <button type="button" class="flow-ctx-item dim" @click="emit('close-context-menu')">取消</button>
    </div>
  </div>
</template>

<style scoped>
.flow {
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: 14px;
  overflow-y: auto;
  user-select: none;
}

/* ── Top bar ─────────────────────────────────── */
.flow-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.flow-top-left {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-heading);
  font-size: 0.82rem;
  font-weight: 600;
}

.flow-top-left svg { color: var(--accent); flex-shrink: 0; }

.flow-count {
  font-size: 0.62rem;
  font-weight: 400;
  color: var(--text-dim);
  padding: 1px 7px;
  background: var(--bg-input);
  border-radius: 8px;
}

.flow-presets {
  display: flex;
  gap: 4px;
}

.flow-presets button {
  padding: 3px 8px;
  background: none;
  border: 1px solid var(--border-default);
  border-radius: 4px;
  color: var(--text-dim);
  font-size: 0.66rem;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.flow-presets button:hover {
  border-color: var(--accent-border);
  color: var(--accent);
}

/* ── Canvas ──────────────────────────────────── */
.flow-canvas {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 0 12px;
}

/* ── Group ───────────────────────────────────── */
.flow-group {
  width: 100%;
}

.flow-group-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  font-size: 0.64rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--gc, var(--text-dim));
}

.flow-group-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--gc, var(--text-dim));
}

.flow-group-body {
  padding: 0 4px;
}

/* ── Arrow between nodes ─────────────────────── */
.flow-arrow {
  display: flex;
  justify-content: center;
  height: 18px;
  color: var(--border-default);
}

/* ── Arrow between groups ────────────────────── */
.flow-group-arrow {
  display: flex;
  justify-content: center;
  height: 26px;
  color: var(--border-strong);
}

/* ── Node ────────────────────────────────────── */
.flow-node {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border-radius: 8px;
  border: 1px solid var(--border-subtle);
  background: var(--bg-input);
  cursor: pointer;
  transition: all var(--transition-fast);
  position: relative;
}

.flow-node:hover {
  border-color: var(--border-strong);
}

.flow-node.selected {
  background: var(--accent-glow);
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent-border);
}

.flow-node.disabled {
  opacity: 0.3;
  pointer-events: none;
}

.flow-node.dirty {
  border-color: rgba(245, 158, 11, 0.4);
}

.flow-node-num {
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 7px;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  font-size: 0.7rem;
  font-weight: 700;
  color: var(--text-dim);
  flex-shrink: 0;
  font-family: var(--font-mono);
}

.flow-node.selected .flow-node-num {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}

.flow-node.dirty .flow-node-num {
  border-color: var(--amber);
  color: var(--amber);
}

.flow-node-body {
  flex: 1;
  min-width: 0;
}

.flow-node-title {
  display: block;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-heading);
  margin-bottom: 1px;
}

.flow-node-tool {
  display: block;
  font-size: 0.66rem;
  color: var(--text-dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.flow-node-badge {
  font-size: 0.62rem;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 6px;
  flex-shrink: 0;
  color: var(--text-dim);
  background: rgba(107, 114, 128, 0.1);
}

.flow-node-badge.ready   { color: var(--green);   background: var(--green-soft); }
.flow-node-badge.running { color: var(--accent);  background: var(--accent-glow); animation: flow-pulse 2s infinite; }
.flow-node-badge.blocked { color: var(--red);     background: var(--red-soft); }
.flow-node-badge.neutral { color: var(--text-dim); background: rgba(107, 114, 128, 0.1); }
.flow-node-badge.dirty   { color: var(--amber);   background: var(--amber-soft); }

@keyframes flow-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

/* ── Drop zone ───────────────────────────────── */
.flow-drop {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  padding: 12px 14px;
  border: 1px dashed var(--border-default);
  border-radius: 8px;
  cursor: pointer;
  position: relative;
  transition: all var(--transition-fast);
}

.flow-drop.active {
  border-color: var(--accent);
  background: var(--accent-glow);
}

.flow-drop input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.flow-drop svg {
  color: var(--text-dim);
  flex-shrink: 0;
}

.flow-drop span {
  display: block;
  font-size: 0.76rem;
  color: var(--text-muted);
}

.flow-drop small {
  font-size: 0.66rem;
  color: var(--text-dim);
}

/* ── File list ───────────────────────────────── */
.flow-files {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-top: 8px;
}

.flow-file {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  background: var(--bg-input);
  border-radius: 4px;
  font-size: 0.7rem;
}

.flow-file span {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-body);
}

.flow-file small {
  color: var(--text-dim);
  flex-shrink: 0;
  font-size: 0.64rem;
}

.flow-file button {
  background: none;
  border: none;
  color: var(--text-dim);
  cursor: pointer;
  font-size: 0.9rem;
  padding: 0 2px;
}

.flow-file button:hover { color: var(--red); }

.flow-hint {
  margin: 6px 0 0;
  font-size: 0.66rem;
  color: var(--text-dim);
}

.flow-hint.ok { color: var(--green); }

/* ── Context menu ────────────────────────────── */
.flow-ctx {
  position: fixed;
  z-index: 100;
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  padding: 4px;
  min-width: 180px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
}

.flow-ctx-label {
  padding: 5px 10px 2px;
  font-size: 0.6rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-dim);
}

.flow-ctx-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 5px 10px;
  background: none;
  border: none;
  border-radius: 4px;
  color: var(--text-body);
  font-size: 0.74rem;
  cursor: pointer;
}

.flow-ctx-item:hover { background: rgba(255,255,255,0.04); }
.flow-ctx-item.active { color: var(--accent); }
.flow-ctx-item.primary { color: var(--accent-blue); font-weight: 600; }
.flow-ctx-item.dim { color: var(--text-dim); }

.flow-ctx-sep {
  height: 1px;
  background: var(--border-subtle);
  margin: 3px 6px;
}
</style>

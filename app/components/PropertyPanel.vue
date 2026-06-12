<script setup lang="ts">
import { computed } from 'vue'
import type { WorkflowSlotId, WorkflowSlotView, WorkflowToolOption } from '@/composables/workflowConfig'

const props = defineProps<{
  jobName: string
  selectedWorkflowSlot: WorkflowSlotView
  workflowToolSelection: Record<WorkflowSlotId, string>
  selectedWorker: string
  solvers: { alias: string; label: string }[]
  workerOptions: { alias: string; label: string; kind: string }[]
  computeNodes: { alias: string; label: string }[]
  selectedComputeNode: string
  remoteRunning: boolean
  statusConnected: boolean
  customArgs: string
  timeoutMinutes: string
  uploadedInputFiles: { name: string; size: number }[]
  fileCheckHint: string | null
}>()

const emit = defineEmits<{
  'update:jobName': [value: string]
  'update-tool': [slotId: WorkflowSlotId, event: Event]
  'update:selectedWorker': [alias: string]
  'update:selectedComputeNode': [alias: string]
  'update:customArgs': [value: string]
  'update:timeoutMinutes': [value: string]
}>()

const slotMeta = computed(() => {
  const s = props.selectedWorkflowSlot
  return {
    icon: slotIcons[s.id] || '',
    desc: slotDescriptions[s.id] || '',
  }
})

const slotIcons: Record<string, string> = {
  geometry: 'M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5z',
  mesh: 'M3 3h7v7H3V3zm11 0h7v7h-7V3zM3 14h7v7H3v-7zm11 0h7v7h-7v-7z',
  material: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5',
  boundary: 'M8 2v4l4 2-4 2v4l10-6L8 2z',
  solver: 'M13 2L3 14h9l-1 8 10-12h-9l1-8z',
  post: 'M4 4h16v2H4V4zm0 6h16v2H4v-2zm0 6h10v2H4v-2z',
  validation: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
}

const slotDescriptions: Record<string, string> = {
  geometry: '选择几何模型来源。支持导入 .inp、FreeCAD .FCStd、STEP 文件，或手动编写算例文件夹。',
  mesh: '选择网格生成工具。如果 .inp 已包含网格定义，可沿用；否则通过 Gmsh、PrePoMax 等工具生成。',
  material: '定义材料属性。可以从 .inp 沿用材料块、通过表单编辑常用参数、或引用 YAML 材料库。',
  boundary: '定义约束与载荷。包括位移约束（*BOUNDARY）和集中力/压力载荷（*CLOAD/*DLOAD）。',
  solver: '选择求解器并配置计算资源。支持 CalculiX、ANSYS MAPDL、Elmer、OpenFOAM。',
  post: '选择后处理工具，将求解器输出转换为可视化格式（VTK）或提取数值摘要。',
  validation: '验证仿真结果。与 Benchmark Lab 中的解析解对比，或与 ANSYS MAPDL 交叉验证。',
}
</script>

<template>
  <aside class="pp">
    <div class="pp-header">作业配置</div>

    <!-- Job name -->
    <div class="pp-section">
      <label class="pp-field">
        <span class="pp-label">作业名称</span>
        <input
          :value="jobName"
          type="text"
          placeholder="结构验证_2026"
          class="pp-input"
          @input="emit('update:jobName', ($event.target as HTMLInputElement).value)"
        />
      </label>
    </div>

    <!-- Selected slot -->
    <div class="pp-section">
      <div class="pp-slot-head">
        <span class="pp-slot-num">{{ selectedWorkflowSlot.order }}</span>
        <div>
          <strong>{{ selectedWorkflowSlot.title }}</strong>
          <span class="pp-slot-status" :class="selectedWorkflowSlot.status">{{ selectedWorkflowSlot.statusLabel }}</span>
        </div>
      </div>
      <p class="pp-slot-desc">{{ slotMeta.desc }}</p>
    </div>

    <!-- Tool selector (all slots) -->
    <div class="pp-section">
      <label class="pp-field">
        <span class="pp-label">工具</span>
        <select
          class="pp-input"
          :value="workflowToolSelection[selectedWorkflowSlot.id]"
          @change="emit('update-tool', selectedWorkflowSlot.id, $event)"
        >
          <option v-for="tool in selectedWorkflowSlot.tools" :key="tool.id" :value="tool.id">
            {{ tool.label }}
          </option>
        </select>
      </label>
      <p class="pp-hint">{{ selectedWorkflowSlot.selectedTool.output }}</p>
    </div>

    <!-- Slot-specific config -->
    <div class="pp-section">

      <!-- Geometry -->
      <template v-if="selectedWorkflowSlot.id === 'geometry'">
        <div class="pp-block">
          <span class="pp-label">输入文件</span>
          <div v-if="uploadedInputFiles.length" class="pp-files">
            <div v-for="f in uploadedInputFiles" :key="`${f.name}-${f.size}`" class="pp-file">
              <span>{{ f.name }}</span>
              <small>{{ f.size < 1024 ? `${f.size} B` : f.size < 1024 * 1024 ? `${(f.size / 1024).toFixed(1)} KB` : `${(f.size / 1024 / 1024).toFixed(1)} MB` }}</small>
            </div>
          </div>
          <p v-else class="pp-empty">尚未选择输入文件。在左侧流程图中拖拽或点击上传。</p>
          <p v-if="fileCheckHint" class="pp-hint" :class="{ ok: fileCheckHint.includes('可直接提交') }">{{ fileCheckHint }}</p>
        </div>
      </template>

      <!-- Mesh -->
      <template v-else-if="selectedWorkflowSlot.id === 'mesh'">
        <label class="pp-field">
          <span class="pp-label">单元类型</span>
          <select class="pp-input">
            <option>T3D2 — 2 节点杆单元</option>
            <option>B31 — 2 节点梁单元</option>
            <option>C3D8 — 8 节点六面体</option>
            <option>C3D4 — 4 节点四面体</option>
          </select>
        </label>
        <label class="pp-field">
          <span class="pp-label">单元大小 (mm)</span>
          <input type="text" class="pp-input" placeholder="自动" />
        </label>
      </template>

      <!-- Material -->
      <template v-else-if="selectedWorkflowSlot.id === 'material'">
        <label class="pp-field">
          <span class="pp-label">弹性模量 E (MPa)</span>
          <input type="text" class="pp-input" placeholder="210000" />
        </label>
        <label class="pp-field">
          <span class="pp-label">泊松比 &nu;</span>
          <input type="text" class="pp-input" placeholder="0.3" />
        </label>
        <label class="pp-field">
          <span class="pp-label">密度 (kg/mm³)</span>
          <input type="text" class="pp-input" placeholder="7.85e-6" />
        </label>
      </template>

      <!-- Boundary -->
      <template v-else-if="selectedWorkflowSlot.id === 'boundary'">
        <label class="pp-field">
          <span class="pp-label">约束类型</span>
          <select class="pp-input">
            <option>固定端 — 1,1,6</option>
            <option>简支 — 约束位移，释放转动</option>
            <option>对称 — 法向约束</option>
          </select>
        </label>
        <label class="pp-field">
          <span class="pp-label">载荷类型</span>
          <select class="pp-input">
            <option>集中力 — *CLOAD</option>
            <option>分布载荷 — *DLOAD</option>
            <option>强制位移 — *BOUNDARY</option>
          </select>
        </label>
        <label class="pp-field">
          <span class="pp-label">载荷值</span>
          <input type="text" class="pp-input" placeholder="例如: 2, 2, -100" />
        </label>
      </template>

      <!-- Solver -->
      <template v-else-if="selectedWorkflowSlot.id === 'solver'">
        <label class="pp-field">
          <span class="pp-label">求解器</span>
          <select :value="selectedWorker" class="pp-input" @change="emit('update:selectedWorker', ($event.target as HTMLSelectElement).value)">
            <option v-if="solvers.length === 0" v-for="w in workerOptions" :key="w.alias" :value="w.alias">{{ w.label }}</option>
            <option v-for="s in solvers" :key="s.alias" :value="s.alias">{{ s.label }}</option>
          </select>
        </label>
        <label class="pp-field">
          <span class="pp-label">计算节点</span>
          <select :value="selectedComputeNode" :disabled="computeNodes.length === 0 || remoteRunning" class="pp-input" @change="emit('update:selectedComputeNode', ($event.target as HTMLSelectElement).value)">
            <option v-for="n in computeNodes" :key="n.alias" :value="n.alias">{{ n.label }}</option>
          </select>
        </label>
        <label class="pp-field">
          <span class="pp-label">命令行参数</span>
          <input :value="customArgs" type="text" placeholder="--cpus 8 --memory 16G" class="pp-input" @input="emit('update:customArgs', ($event.target as HTMLInputElement).value)" />
        </label>
        <label class="pp-field">
          <span class="pp-label">超时 (分钟)</span>
          <input :value="timeoutMinutes" type="text" placeholder="默认" class="pp-input" @input="emit('update:timeoutMinutes', ($event.target as HTMLInputElement).value)" />
        </label>
      </template>

      <!-- Post -->
      <template v-else-if="selectedWorkflowSlot.id === 'post'">
        <label class="pp-field">
          <span class="pp-label">输出格式</span>
          <select class="pp-input">
            <option>VTK — ParaView / VTK.js 可视化</option>
            <option>JSON — 数值摘要</option>
            <option>CSV — 表格导出</option>
          </select>
        </label>
      </template>

      <!-- Validation -->
      <template v-else-if="selectedWorkflowSlot.id === 'validation'">
        <label class="pp-field">
          <span class="pp-label">对比目标</span>
          <select class="pp-input">
            <option>解析解 — 理论公式</option>
            <option>Benchmark Lab — 多方法对比</option>
            <option>ANSYS MAPDL — 商业求解器对照</option>
          </select>
        </label>
        <label class="pp-field">
          <span class="pp-label">误差容忍度 (%)</span>
          <input type="text" class="pp-input" placeholder="1.0" />
        </label>
      </template>
    </div>
  </aside>
</template>

<style scoped>
.pp {
  display: flex;
  flex-direction: column;
  gap: 0;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: 16px;
  overflow-y: auto;
  min-width: 260px;
}

.pp-header {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-dim);
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-subtle);
  margin-bottom: 12px;
}

/* ── Section ─────────────────────────────────── */
.pp-section {
  padding: 12px 0;
  border-bottom: 1px solid var(--border-subtle);
}

.pp-section:last-child {
  border-bottom: none;
  flex: 1;
}

/* ── Slot head ───────────────────────────────── */
.pp-slot-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.pp-slot-num {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  font-size: 0.7rem;
  font-weight: 700;
  flex-shrink: 0;
  font-family: var(--font-mono);
}

.pp-slot-head strong {
  font-size: 0.88rem;
  color: var(--text-heading);
  display: block;
}

.pp-slot-status {
  font-size: 0.66rem;
  color: var(--text-dim);
}

.pp-slot-status.ready { color: var(--green); }
.pp-slot-status.running { color: var(--accent); }
.pp-slot-status.blocked { color: var(--red); }

.pp-slot-desc {
  margin: 8px 0 0;
  font-size: 0.74rem;
  color: var(--text-muted);
  line-height: 1.5;
}

/* ── Fields ──────────────────────────────────── */
.pp-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
}

.pp-field:last-child { margin-bottom: 0; }

.pp-label {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.pp-input {
  width: 100%;
  padding: 7px 10px;
  background: var(--bg-input);
  border: 1px solid var(--border-default);
  border-radius: 5px;
  color: var(--text-body);
  font-family: var(--font-ui);
  font-size: 0.8rem;
  box-sizing: border-box;
}

.pp-input:focus {
  outline: none;
  border-color: var(--accent);
}

select.pp-input {
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' fill='%239ca6b8' viewBox='0 0 16 16'%3E%3Cpath d='M8 11L3 6h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  padding-right: 28px;
}

.pp-input:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── Hint / empty ────────────────────────────── */
.pp-hint {
  margin: 6px 0 0;
  font-size: 0.66rem;
  color: var(--text-dim);
}

.pp-hint.ok { color: var(--green); }

.pp-empty {
  margin: 0;
  font-size: 0.72rem;
  color: var(--text-dim);
}

/* ── Files ───────────────────────────────────── */
.pp-files {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.pp-file {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  background: var(--bg-input);
  border-radius: 4px;
  font-size: 0.72rem;
}

.pp-file span { color: var(--text-body); }
.pp-file small { color: var(--text-dim); }

/* ── Block ───────────────────────────────────── */
.pp-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>

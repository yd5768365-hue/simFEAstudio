import { ref } from 'vue'
import type { WorkflowSlotId } from '@/composables/workflowConfig'
import { downstreamOrder, toolToSolverAlias } from '@/composables/workflowConfig'

export function useWorkflowState() {
  const selectedWorkflowSlotId = ref<WorkflowSlotId>('solver')
  const dirtyNodes = ref<Set<WorkflowSlotId>>(new Set())
  const enabledNodes = ref<Set<WorkflowSlotId>>(new Set(downstreamOrder))
  const workflowToolSelection = ref<Record<WorkflowSlotId, string>>({
    geometry: 'import-inp',
    mesh: 'inp-mesh',
    material: 'inp-material',
    boundary: 'inp-boundary',
    solver: 'calculix',
    post: 'frd-vtk',
    validation: 'benchmark-lab',
  })

  function toggleNodeEnabled(slotId: WorkflowSlotId) {
    const next = new Set(enabledNodes.value)
    if (next.has(slotId)) {
      next.delete(slotId)
    } else {
      next.add(slotId)
    }
    enabledNodes.value = next
  }

  function applyPreset(name: string) {
    if (name === 'full') {
      enabledNodes.value = new Set(downstreamOrder)
    } else if (name === 'solver-only') {
      enabledNodes.value = new Set(['solver'])
    } else if (name === 'geom-solver') {
      enabledNodes.value = new Set(['geometry', 'solver'])
    }
  }

  function markDirty(slotId: WorkflowSlotId) {
    const idx = downstreamOrder.indexOf(slotId)
    for (let i = idx; i < downstreamOrder.length; i++) {
      dirtyNodes.value.add(downstreamOrder[i])
    }
  }

  function clearDirtyNodes() {
    dirtyNodes.value = new Set()
  }

  function buildWorkflowSolverSteps(): (string | { solver: string; params?: Record<string, string> })[] {
    const result: (string | { solver: string; params?: Record<string, string> })[] = []
    for (const slotId of downstreamOrder) {
      if (!enabledNodes.value.has(slotId)) continue
      const toolId = workflowToolSelection.value[slotId]
      const solverAlias = toolToSolverAlias[toolId]
      if (solverAlias) {
        result.push({ solver: solverAlias, params: { tool_id: toolId, slot: slotId } })
      }
    }
    return result
  }

  function buildStepsFromNode(
    slotId: WorkflowSlotId
  ): (string | { solver: string; params?: Record<string, string> })[] {
    const idx = downstreamOrder.indexOf(slotId)
    const result: (string | { solver: string; params?: Record<string, string> })[] = []
    for (let i = idx; i < downstreamOrder.length; i++) {
      const sid = downstreamOrder[i]
      if (!enabledNodes.value.has(sid)) continue
      const toolId = workflowToolSelection.value[sid]
      const solverAlias = toolToSolverAlias[toolId]
      if (solverAlias) result.push({ solver: solverAlias, params: { tool_id: toolId, slot: sid } })
    }
    return result
  }

  return {
    selectedWorkflowSlotId,
    dirtyNodes,
    enabledNodes,
    workflowToolSelection,
    toggleNodeEnabled,
    applyPreset,
    markDirty,
    clearDirtyNodes,
    buildWorkflowSolverSteps,
    buildStepsFromNode,
  }
}

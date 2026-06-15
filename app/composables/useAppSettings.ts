import { ref, watch } from 'vue'

const STORAGE_KEY = 'simfea-settings'

interface AppSettings {
  selectedWorker: string
  selectedComputeNode: string
  jobName: string
  customArgs: string
  timeoutMinutes: string
  workflowToolSelections: Record<string, string>
  lastView: string
}

function load(): Partial<AppSettings> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    return JSON.parse(raw) as Partial<AppSettings>
  } catch {
    return {}
  }
}

function save(settings: Partial<AppSettings>) {
  const current = load()
  const merged = { ...current, ...settings }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(merged))
  } catch {
    // localStorage full or unavailable — silently ignore
  }
}

export function useAppSettings() {
  const saved = load()

  const selectedWorker = ref<string>(saved.selectedWorker || 'calculix')
  const selectedComputeNode = ref<string>(saved.selectedComputeNode || 'local')
  const jobName = ref<string>(saved.jobName || '')
  const customArgs = ref<string>(saved.customArgs || '')
  const timeoutMinutes = ref<string>(saved.timeoutMinutes || '')
  const workflowToolSelections = ref<Record<string, string>>(saved.workflowToolSelections || {})
  const lastView = ref<string>(saved.lastView || 'composer')

  // Persist on change
  watch(selectedWorker, (v) => save({ selectedWorker: v }))
  watch(selectedComputeNode, (v) => save({ selectedComputeNode: v }))
  watch(jobName, (v) => save({ jobName: v }))
  watch(customArgs, (v) => save({ customArgs: v }))
  watch(timeoutMinutes, (v) => save({ timeoutMinutes: v }))
  watch(workflowToolSelections, (v) => save({ workflowToolSelections: { ...v } }), { deep: true })
  watch(lastView, (v) => save({ lastView: v }))

  return {
    selectedWorker,
    selectedComputeNode,
    jobName,
    customArgs,
    timeoutMinutes,
    workflowToolSelections,
    lastView,
  }
}

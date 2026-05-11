<script setup lang="ts">
import { computed, ref } from 'vue'
import VtkResultViewport from '@/components/VtkResultViewport.vue'
import type { RunArchive } from '@/types'

interface VisualizationMetrics {
  runId: string
  runner: string
  jobId: string
  partition: string
  runNode: string
  displacementMm: number | null
  stressMpa: number | null
  displacementRatio: number
  stressRatio: number
  status: string
  evidenceReady: boolean
}

const props = defineProps<{
  run: RunArchive | null
  apiBaseUrl: string
  reportPreview: string
  remoteOutput: string
}>()

const viewMode = ref<'evidence' | 'vtk'>('evidence')

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max)

const extractValue = (source: string, key: string) => {
  const match = new RegExp(`${key}=([^\\n\\r]+)`).exec(source)
  return match?.[1]?.trim() ?? ''
}

const extractNumber = (source: string, key: string) => {
  const value = Number.parseFloat(extractValue(source, key))
  return Number.isFinite(value) ? value : null
}

const evidenceArtifacts = computed(
  () => props.run?.artifacts?.filter((artifact) => artifact !== 'artifacts/result_summary.json') ?? []
)

const selectedArtifacts = computed(() =>
  evidenceArtifacts.value.length ? evidenceArtifacts.value.join('、') : '暂无结果文件'
)

const visualizationDataSource = computed(() =>
  props.run?.summary ? '结构化摘要：result_summary.json' : '兼容解析：日志与报告'
)

const visualizationSource = computed(() => `${props.reportPreview}\n${props.remoteOutput}`)

const hasVtkArtifact = computed(() =>
  Boolean(
    props.run?.summary?.visualization?.vtk_artifact ||
      props.run?.artifacts?.some((artifact) => artifact.endsWith('.vtk') || artifact.endsWith('.vtu'))
  )
)

const visualizationMetrics = computed<VisualizationMetrics>(() => {
  const source = visualizationSource.value
  const summary = props.run?.summary
  const displacementMm = summary?.metrics?.max_displacement_mm ?? extractNumber(source, 'max_displacement_mm')
  const stressMpa = summary?.metrics?.max_von_mises_mpa ?? extractNumber(source, 'max_von_mises_mpa')
  const jobId = props.run?.job_id || summary?.scheduler?.job_id || extractValue(source, 'job_id') || '暂无'
  const partition =
    props.run?.partition || summary?.scheduler?.partition || extractValue(source, 'partition') || '暂无'
  const runNode =
    props.run?.allocated_node ||
    summary?.scheduler?.allocated_node ||
    extractValue(source, 'run_node') ||
    extractValue(source, 'hostname') ||
    '暂无'
  const runner =
    props.run?.runner || summary?.runner || (source.includes('Slurm') ? 'SlurmRunner' : 'SSHRunner')

  return {
    runId: props.run?.run_id ?? '暂无',
    runner,
    jobId,
    partition,
    runNode,
    displacementMm,
    stressMpa,
    displacementRatio: clamp((displacementMm ?? 0.08) / 1.2, 0.06, 1),
    stressRatio: clamp((stressMpa ?? 18) / 220, 0.08, 1),
    status: props.run?.status ?? summary?.status ?? '未选择',
    evidenceReady: Boolean(
      props.run &&
        (summary?.visualization?.ready ||
          displacementMm !== null ||
          stressMpa !== null ||
          source.trim() ||
          evidenceArtifacts.value.length)
    ),
  }
})

const beamDeformationPath = computed(() => {
  const d = visualizationMetrics.value.displacementRatio
  return `M 150 150 C 260 ${150 + d * 10} 410 ${150 + d * 34} 600 ${150 + d * 72}`
})

const loadArrowY = computed(() => 150 + visualizationMetrics.value.displacementRatio * 72)

const stressSegments = computed(() =>
  Array.from({ length: 8 }, (_, index) => {
    const position = (index + 1) / 8
    const intensity = clamp(visualizationMetrics.value.stressRatio * (0.45 + position * 0.85), 0.1, 1)
    return {
      id: `stress-${index}`,
      x: 150 + index * 54,
      width: 50,
      fill: `rgb(${Math.round(70 + intensity * 170)}, ${Math.round(150 - intensity * 72)}, ${Math.round(88 - intensity * 42)})`,
      opacity: 0.76 + intensity * 0.18,
    }
  })
)
</script>

<template>
  <section class="panel visualization-panel" aria-labelledby="visualization-title">
    <div class="section-heading">
      <p class="eyebrow">结果可视化</p>
      <h2 id="visualization-title">悬臂梁证据视图</h2>
    </div>
    <div v-if="visualizationMetrics.evidenceReady" class="visualization-body">
      <div class="view-toggle" aria-label="结果视图切换">
        <button type="button" :class="{ active: viewMode === 'evidence' }" @click="viewMode = 'evidence'">
          证据图
        </button>
        <button type="button" :class="{ active: viewMode === 'vtk' }" :disabled="!hasVtkArtifact" @click="viewMode = 'vtk'">
          VTK 视图
        </button>
      </div>
      <div class="visualization-summary">
        <span>{{ visualizationMetrics.runner }}</span>
        <span>{{ visualizationDataSource }}</span>
        <span>状态：{{ visualizationMetrics.status }}</span>
        <span>节点：{{ visualizationMetrics.runNode }}</span>
        <span>JobID：{{ visualizationMetrics.jobId }}</span>
      </div>
      <VtkResultViewport
        v-if="viewMode === 'vtk'"
        :run="run"
        :api-base-url="apiBaseUrl"
      />
      <div v-else class="beam-viewport" role="img" aria-label="悬臂梁变形和应力云图示意">
        <svg viewBox="0 0 720 300" class="beam-svg" aria-hidden="true">
          <defs>
            <linearGradient id="beamAxis" x1="0" x2="1" y1="0" y2="0">
              <stop offset="0%" stop-color="#4f6f8f" />
              <stop offset="100%" stop-color="#d65f4f" />
            </linearGradient>
            <marker id="loadArrow" markerWidth="10" markerHeight="10" refX="5" refY="5" orient="auto">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#b8463c" />
            </marker>
          </defs>
          <rect x="96" y="86" width="24" height="128" rx="2" fill="#263645" />
          <g stroke="#6c7885" stroke-width="2">
            <path
              v-for="mark in 6"
              :key="mark"
              :d="`M ${76 + mark * 4} ${88 + mark * 19} L ${120 + mark * 4} ${62 + mark * 19}`"
            />
          </g>
          <line x1="150" y1="150" x2="600" y2="150" stroke="#9aa7b5" stroke-width="4" stroke-dasharray="10 10" />
          <g>
            <rect
              v-for="segment in stressSegments"
              :key="segment.id"
              :x="segment.x"
              y="126"
              :width="segment.width"
              height="48"
              rx="4"
              :fill="segment.fill"
              :opacity="segment.opacity"
            />
          </g>
          <path :d="beamDeformationPath" fill="none" stroke="url(#beamAxis)" stroke-width="12" stroke-linecap="round" />
          <circle cx="600" :cy="loadArrowY" r="9" fill="#ffffff" stroke="#b8463c" stroke-width="3" />
          <line x1="640" y1="72" x2="606" :y2="loadArrowY" stroke="#b8463c" stroke-width="4" marker-end="url(#loadArrow)" />
          <text x="150" y="112" class="beam-label">固定端</text>
          <text x="536" y="104" class="beam-label">自由端载荷</text>
        </svg>
      </div>
      <div class="visualization-metrics">
        <article>
          <span>最大位移</span>
          <strong>{{ visualizationMetrics.displacementMm ?? '暂无' }}</strong>
          <small>mm</small>
        </article>
        <article>
          <span>等效应力</span>
          <strong>{{ visualizationMetrics.stressMpa ?? '暂无' }}</strong>
          <small>MPa</small>
        </article>
        <article>
          <span>分区</span>
          <strong>{{ visualizationMetrics.partition }}</strong>
          <small>Slurm</small>
        </article>
        <article>
          <span>归档</span>
          <strong>{{ selectedArtifacts }}</strong>
          <small>artifacts</small>
        </article>
      </div>
    </div>
    <p v-else class="empty-state">
      选择一次已完成运行后，这里会显示结果证据图。
    </p>
  </section>
</template>

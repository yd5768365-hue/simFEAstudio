<script setup lang="ts">
import '@kitware/vtk.js/Rendering/Profiles/Geometry'

import vtkPolyDataReader from '@kitware/vtk.js/IO/Legacy/PolyDataReader'
import vtkActor from '@kitware/vtk.js/Rendering/Core/Actor'
import vtkMapper from '@kitware/vtk.js/Rendering/Core/Mapper'
import vtkFullScreenRenderWindow from '@kitware/vtk.js/Rendering/Misc/FullScreenRenderWindow'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { RunArchive } from '@/types'

const props = defineProps<{
  run: RunArchive | null
  apiBaseUrl: string
}>()

const container = ref<HTMLDivElement | null>(null)
const message = ref('选择带有 VTK 物证的运行后，这里会显示三维结果。')
const loading = ref(false)

let fullScreenRenderer: any = null
let actor: any = null
let mapper: any = null
let reader: any = null

const vtkArtifact = computed(() => {
  const fromSummary = props.run?.summary?.visualization?.vtk_artifact
  if (fromSummary) {
    return fromSummary
  }
  return (
    props.run?.artifacts?.find((artifact) => artifact.endsWith('.vtk') || artifact.endsWith('.vtu')) ?? ''
  )
})

const artifactUrl = computed(() => {
  if (!props.run || !vtkArtifact.value) {
    return ''
  }
  const safePath = vtkArtifact.value.split('/').map(encodeURIComponent).join('/')
  return `${props.apiBaseUrl}/v1/runs/${props.run.run_id}/artifacts/${safePath}`
})

const disposeScene = () => {
  actor?.delete?.()
  mapper?.delete?.()
  reader?.delete?.()
  fullScreenRenderer?.delete?.()
  actor = null
  mapper = null
  reader = null
  fullScreenRenderer = null
}

const renderVtk = async () => {
  disposeScene()

  if (!container.value) {
    return
  }

  if (!artifactUrl.value) {
    message.value = '这次运行还没有 VTK 结果文件。'
    return
  }

  loading.value = true
  message.value = '正在加载 VTK 结果...'
  await nextTick()

  try {
    const response = await fetch(artifactUrl.value)
    if (!response.ok) {
      throw new Error(`VTK 文件读取失败：${response.status}`)
    }

    const vtkText = await response.text()
    reader = vtkPolyDataReader.newInstance()
    reader.parseAsText(vtkText)
    const polyData = reader.getOutputData(0)
    const scalars = polyData.getPointData().getScalars()

    mapper = vtkMapper.newInstance()
    mapper.setInputData(polyData)
    if (scalars) {
      mapper.setScalarVisibility(true)
      mapper.setScalarRange(scalars.getRange())
    }

    actor = vtkActor.newInstance()
    actor.setMapper(mapper)

    fullScreenRenderer = vtkFullScreenRenderWindow.newInstance({
      rootContainer: container.value,
      background: [0.97, 0.98, 0.99],
      containerStyle: {
        width: '100%',
        height: '100%',
        position: 'relative',
      },
    })

    const renderer = fullScreenRenderer.getRenderer()
    const renderWindow = fullScreenRenderer.getRenderWindow()
    renderer.addActor(actor)
    renderer.resetCamera()
    renderWindow.render()
    message.value = `VTK 视图：${vtkArtifact.value}`
  } catch (err) {
    message.value = String(err)
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.run?.run_id, vtkArtifact.value, props.apiBaseUrl],
  () => {
    renderVtk()
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  disposeScene()
})
</script>

<template>
  <div class="vtk-viewport-shell">
    <div ref="container" class="vtk-viewport" :class="{ loading }" />
    <p class="vtk-status">{{ message }}</p>
  </div>
</template>

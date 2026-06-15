<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { RunArchive } from '@/types'

const props = defineProps<{
  run: RunArchive | null
  apiBaseUrl: string
  selectedArtifact: string
}>()

const container = ref<HTMLDivElement | null>(null)
const message = ref('选择带有 VTK 物证的运行后，这里会显示三维结果。')
const loading = ref(false)

type VtkDisposable = {
  delete?: () => void
}

type VtkScalars = {
  getRange: () => number[]
}

type VtkPolyData = {
  getPointData: () => {
    getScalars: () => VtkScalars | null
  }
}

type VtkReader = VtkDisposable & {
  parseAsArrayBuffer?: (data: ArrayBuffer) => void
  parseAsText?: (text: string) => void
  getOutputData: (index: number) => VtkPolyData
}

type VtkMapper = VtkDisposable & {
  setInputData: (data: VtkPolyData) => void
  setScalarVisibility: (visible: boolean) => void
  setScalarRange: (range: number[]) => void
}

type VtkActor = VtkDisposable & {
  setMapper: (mapper: VtkMapper) => void
}

type VtkRenderer = {
  addActor: (actor: VtkActor) => void
  resetCamera: () => void
}

type VtkRenderWindow = {
  render: () => void
}

type VtkFullScreenRenderer = VtkDisposable & {
  getRenderer: () => VtkRenderer
  getRenderWindow: () => VtkRenderWindow
}

type VtkFactory<T> = {
  newInstance: (options?: unknown) => T
}

let fullScreenRenderer: VtkFullScreenRenderer | null = null
let actor: VtkActor | null = null
let mapper: VtkMapper | null = null
let reader: VtkReader | null = null
let vtkModulesPromise: Promise<{
  vtkActor: VtkFactory<VtkActor>
  vtkMapper: VtkFactory<VtkMapper>
  vtkFullScreenRenderWindow: VtkFactory<VtkFullScreenRenderer>
  vtkPolyDataReader: VtkFactory<VtkReader>
  vtkXMLPolyDataReader: VtkFactory<VtkReader>
}> | null = null

const loadVtkModules = () => {
  vtkModulesPromise ??= Promise.all([
    import('@kitware/vtk.js/Rendering/Profiles/Geometry'),
    import('@kitware/vtk.js/IO/Legacy/PolyDataReader'),
    import('@kitware/vtk.js/IO/XML/XMLPolyDataReader'),
    import('@kitware/vtk.js/Rendering/Core/Actor'),
    import('@kitware/vtk.js/Rendering/Core/Mapper'),
    import('@kitware/vtk.js/Rendering/Misc/FullScreenRenderWindow'),
  ]).then(([, polyDataReader, xmlPolyDataReader, actorModule, mapperModule, renderWindowModule]) => ({
    vtkActor: actorModule.default,
    vtkMapper: mapperModule.default,
    vtkFullScreenRenderWindow: renderWindowModule.default,
    vtkPolyDataReader: polyDataReader.default,
    vtkXMLPolyDataReader: xmlPolyDataReader.default,
  }))
  return vtkModulesPromise
}

const vtkArtifact = computed(() => {
  if (props.selectedArtifact) {
    return props.selectedArtifact
  }
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

    const { vtkActor, vtkMapper, vtkFullScreenRenderWindow, vtkPolyDataReader, vtkXMLPolyDataReader } =
      await loadVtkModules()
    const isVtu = vtkArtifact.value.toLowerCase().endsWith('.vtu')
    reader = isVtu ? vtkXMLPolyDataReader.newInstance() : vtkPolyDataReader.newInstance()
    if (isVtu) {
      reader.parseAsArrayBuffer(await response.arrayBuffer())
    } else {
      reader.parseAsText(await response.text())
    }
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

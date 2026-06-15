export type WorkflowSlotId = 'geometry' | 'mesh' | 'material' | 'boundary' | 'solver' | 'post' | 'validation'

export type WorkflowStatus = 'ready' | 'neutral' | 'blocked' | 'running'

export interface WorkflowToolOption {
  id: string
  label: string
  output: string
}

export interface WorkflowSlotView {
  id: WorkflowSlotId
  order: number
  title: string
  subtitle: string
  detail: string
  status: WorkflowStatus
  statusLabel: string
  tools: WorkflowToolOption[]
  selectedTool: WorkflowToolOption
}

export const downstreamOrder: WorkflowSlotId[] = [
  'geometry',
  'mesh',
  'material',
  'boundary',
  'solver',
  'post',
  'validation',
]

export const defaultToolSelections: Record<WorkflowSlotId, string> = {
  geometry: 'import-inp',
  mesh: 'inp-mesh',
  material: 'inp-material',
  boundary: 'inp-boundary',
  solver: 'calculix',
  post: 'frd-vtk',
  validation: 'benchmark-lab',
}

export const toolToSolverAlias: Record<string, string | null> = {
  'freecad-step': 'freecad',
  gmsh: 'gmsh',
  prepomax: 'prepomax',
  calculix: 'calculix',
  'ansys-mapdl': 'ansys-mapdl',
  elmer: 'elmer',
  'frd-vtk': 'frd_to_vtk',
  'summary-json': 'summary-json',
  'import-inp': null,
  'manual-case': null,
  'inp-mesh': null,
  'inp-material': null,
  'material-form': null,
  'yaml-material': null,
  'inp-boundary': null,
  'bc-form': null,
  'benchmark-load': null,
  'vtk-viewer': null,
  'benchmark-lab': null,
  'analytic-check': null,
  'mapdl-compare': null,
  blockmesh: null,
  snappyhexmesh: null,
  elmergrid: null,
  openfoam: 'openfoam',
  paraview: null,
  foamtovtk: null,
  elmervtk: null,
}

export const allTools: Record<WorkflowSlotId, WorkflowToolOption[]> = {
  geometry: [
    { id: 'import-inp', label: '导入 .inp', output: 'mesh-ready inp' },
    { id: 'freecad-step', label: 'FreeCAD / STEP', output: '.step / .FCStd' },
    { id: 'manual-case', label: '手写算例', output: 'case folder' },
  ],
  mesh: [
    { id: 'inp-mesh', label: '沿用 .inp 网格', output: '*.inp' },
    { id: 'gmsh', label: 'Gmsh', output: '*.msh / *.inp' },
    { id: 'prepomax', label: 'PrePoMax', output: '*.inp' },
    { id: 'blockmesh', label: 'blockMesh', output: 'polyMesh' },
    { id: 'snappyhexmesh', label: 'snappyHexMesh', output: 'polyMesh' },
    { id: 'elmergrid', label: 'ElmerGrid', output: 'mesh.*' },
  ],
  material: [
    { id: 'inp-material', label: '沿用 .inp 材料', output: '*MATERIAL' },
    { id: 'material-form', label: '表单编辑', output: 'material block' },
    { id: 'yaml-material', label: 'YAML 材料库', output: 'materials.yaml' },
  ],
  boundary: [
    { id: 'inp-boundary', label: '沿用 .inp 边界', output: '*BOUNDARY / *CLOAD' },
    { id: 'bc-form', label: '边界条件表单', output: 'bc block' },
    { id: 'benchmark-load', label: 'Benchmark 载荷', output: 'reference load' },
  ],
  solver: [
    { id: 'calculix', label: 'CalculiX', output: '.frd / .dat' },
    { id: 'ansys-mapdl', label: 'ANSYS MAPDL', output: '.rst / text result' },
    { id: 'elmer', label: 'Elmer', output: 'Elmer results' },
    { id: 'openfoam', label: 'OpenFOAM', output: 'foam case' },
  ],
  post: [
    { id: 'frd-vtk', label: 'FRD -> VTK', output: '.vtk' },
    { id: 'summary-json', label: '结果摘要提取', output: 'result_summary.json' },
    { id: 'vtk-viewer', label: 'VTK Viewer', output: 'viewport' },
    { id: 'paraview', label: 'ParaView', output: 'screenshot / data' },
    { id: 'foamtovtk', label: 'foamToVTK', output: '.vtk' },
    { id: 'elmervtk', label: 'ElmerVTK', output: '.vtk' },
  ],
  validation: [
    { id: 'benchmark-lab', label: 'Benchmark Lab', output: 'comparison.csv' },
    { id: 'analytic-check', label: '解析解对比', output: 'error table' },
    { id: 'mapdl-compare', label: 'MAPDL 对照', output: 'solver comparison' },
  ],
}

export const solverToolCompat: Record<string, Partial<Record<WorkflowSlotId, string[]>>> = {
  calculix: {
    mesh: ['inp-mesh', 'gmsh', 'prepomax'],
    post: ['frd-vtk', 'summary-json', 'vtk-viewer'],
  },
  'ansys-mapdl': {
    mesh: ['inp-mesh', 'gmsh'],
    post: ['frd-vtk', 'summary-json', 'vtk-viewer'],
    validation: ['benchmark-lab', 'analytic-check', 'mapdl-compare'],
  },
  elmer: {
    mesh: ['gmsh', 'elmergrid'],
    post: ['elmervtk', 'summary-json', 'vtk-viewer'],
    validation: ['benchmark-lab', 'analytic-check'],
  },
  openfoam: {
    geometry: ['manual-case'],
    mesh: ['blockmesh', 'snappyhexmesh', 'gmsh'],
    post: ['paraview', 'foamtovtk', 'summary-json'],
    validation: ['benchmark-lab'],
  },
}

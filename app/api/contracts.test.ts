import { describe, expect, it } from 'vitest'
import { ApiClientError, extractValidationIssues } from './client'
import {
  connectResponseSchema,
  listSolverInstallationsResponseSchema,
  probeNodeResponseSchema,
  probeSolversResponseSchema,
  runArchiveSchema,
  sseEventSchema,
  startSolverRunResponseSchema,
  startWorkflowRunResponseSchema,
} from './contracts'

describe('connectResponseSchema', () => {
  it('parses a full connect response', () => {
    const result = connectResponseSchema.parse({
      message: 'Connected to SimFEA Studio API server on port 8008.',
      data: {
        port: 8008,
        pid: 12345,
        host: 'http://localhost:8008',
        runs_root: '/tmp/runs',
        config_path: '/tmp/config.json',
        learning_export_root: '/tmp/learning',
        learning_formats: ['md', 'json'],
        learning_default_format: 'md',
        default_compute_node: 'node1',
        compute_nodes: [
          {
            alias: 'node1',
            label: 'Node 1',
            host: '192.168.1.1',
            user: 'test',
            remote_runs_root: '/home/test/runs',
            configured: true,
          },
        ],
        solvers: [
          {
            alias: 'calculix',
            label: 'CalculiX',
            kind: 'structural',
            executable: 'ccx',
            artifact_patterns: ['*.frd', 'result.txt'],
          },
        ],
        toolchain: [{ name: 'test', role: 'solver', status: 'ready' }],
      },
    })
    expect(result.data.port).toBe(8008)
    expect(result.data.compute_nodes).toHaveLength(1)
    expect(result.data.compute_nodes[0].alias).toBe('node1')
    expect(result.data.solvers?.[0].alias).toBe('calculix')
    expect(result.message).toContain('Connected')
  })

  it('parses a minimal connect response', () => {
    const result = connectResponseSchema.parse({
      message: 'Connected.',
      data: {
        port: 8008,
        pid: 0,
        host: '',
        runs_root: '',
        config_path: '',
        learning_export_root: '',
        learning_formats: ['md'],
        learning_default_format: 'md',
        compute_nodes: [],
      },
    })
    expect(result.data.port).toBe(8008)
    expect(result.data.compute_nodes).toHaveLength(0)
  })
})

describe('runArchiveSchema', () => {
  it('parses a minimal run archive', () => {
    const result = runArchiveSchema.parse({
      run_id: 'run-001',
      case_name: 'test-case',
      solver: 'custom',
      runner: 'SSHRunner',
      compute_node: 'node1',
      status: 'finished',
      created_at: '2024-01-01T00:00:00Z',
      remote_workdir: '/home/test/runs/run-001',
      local_archive: '/tmp/runs/run-001',
      artifacts: ['result.txt'],
    })
    expect(result.run_id).toBe('run-001')
    expect(result.artifacts).toHaveLength(1)
  })

  it('parses a full run archive', () => {
    const result = runArchiveSchema.parse({
      run_id: 'run-002',
      case_name: 'beam',
      solver: 'custom',
      runner: 'SlurmRunner',
      compute_node: 'hpc1',
      status: 'finished',
      created_at: '2024-01-01T00:00:00Z',
      started_at: '2024-01-01T00:01:00Z',
      finished_at: '2024-01-01T00:05:00Z',
      exit_code: 0,
      remote_workdir: '/home/test/runs/run-002',
      local_archive: '/tmp/runs/run-002',
      artifacts: ['result.txt', 'result.vtk', 'logs.out'],
      input_files: ['inputs/case.inp'],
      learning_report: '/tmp/runs/run-002/report.md',
      note: 'test note',
      report: '# Report',
      scheduler: 'slurm',
      job_id: '12345',
      partition: 'compute',
      allocated_node: 'node42',
      requested_cpus: 4,
      requested_memory: '8G',
      summary: {
        solver: 'custom',
        metrics: {
          max_displacement_mm: 1.5,
          max_von_mises_mpa: 120.0,
        },
        visualization: {
          kind: 'vtk',
          vtk_artifact: 'result.vtk',
          ready: true,
        },
        scheduler: {
          job_id: '12345',
          partition: 'compute',
          allocated_node: 'node42',
          requested_cpus: 4,
          requested_memory: '8G',
        },
      },
    })
    expect(result.exit_code).toBe(0)
    expect(result.summary?.metrics?.max_displacement_mm).toBe(1.5)
    expect(result.scheduler).toBe('slurm')
    expect(result.requested_cpus).toBe(4)
    expect(result.input_files).toEqual(['inputs/case.inp'])
  })
})

describe('sseEventSchema', () => {
  it('discriminates stdout events', () => {
    const result = sseEventSchema.parse({
      run_id: 'run-001',
      type: 'stdout',
      seq: 1,
      archive_path: '/tmp/run-001',
      line: 'computation step 1 done',
    })
    expect(result.type).toBe('stdout')
  })

  it('discriminates stderr events', () => {
    const result = sseEventSchema.parse({
      run_id: 'run-001',
      type: 'stderr',
      seq: 2,
      archive_path: '/tmp/run-001',
      line: 'warning: deprecated flag',
    })
    expect(result.type).toBe('stderr')
  })

  it('discriminates status events', () => {
    const result = sseEventSchema.parse({
      run_id: 'run-001',
      type: 'status',
      seq: 3,
      archive_path: '/tmp/run-001',
      status: 'running',
      line: 'Task started.',
      remote_workdir: '/tmp/remote/run-001',
    })
    expect(result.type).toBe('status')
    expect(result.status).toBe('running')
  })

  it('discriminates finished events', () => {
    const result = sseEventSchema.parse({
      run_id: 'run-001',
      type: 'finished',
      seq: 4,
      archive_path: '/tmp/run-001',
      status: 'ok',
      exit_code: 0,
      line: 'Completed.',
      job_id: '225383',
      allocated_node: 'node42',
    })
    expect(result.type).toBe('finished')
    expect(result.exit_code).toBe(0)
    expect(result.job_id).toBe('225383')
  })

  it('discriminates artifact events', () => {
    const result = sseEventSchema.parse({
      run_id: 'run-001',
      type: 'artifact',
      seq: 5,
      archive_path: '/tmp/run-001',
      line: 'artifact archived',
      artifact: 'artifacts/result.txt',
    })
    expect(result.type).toBe('artifact')
    expect(result.artifact).toBe('artifacts/result.txt')
  })

  it('rejects unknown event types', () => {
    expect(() =>
      sseEventSchema.parse({
        run_id: 'run-001',
        type: 'unknown_event',
        seq: 0,
        archive_path: '/tmp/run-001',
      })
    ).toThrow()
  })
})

describe('solver contracts', () => {
  it('parses a solver installation list response', () => {
    const result = listSolverInstallationsResponseSchema.parse({
      message: 'toolchain loaded',
      data: {
        solvers: [
          {
            alias: 'freecad',
            label: 'FreeCAD',
            install_mode: 'external',
            status: 'found',
            configured_executable: 'C:/FreeCAD/bin/FreeCADCmd.exe',
            discovered_path: 'C:/FreeCAD/bin/FreeCADCmd.exe',
            executable_candidates: ['FreeCADCmd.exe'],
            common_paths: ['C:/FreeCAD/bin/FreeCADCmd.exe'],
            searched_paths: ['C:/FreeCAD/bin/FreeCADCmd.exe'],
            verify_command: '"${executable}" --version',
            install_hint: 'Install FreeCAD first.',
            install_guide_url: 'https://www.freecad.org/downloads.php',
            input_extensions: ['.FCStd', '.step'],
          },
        ],
      },
    })
    expect(result.data.solvers[0].status).toBe('found')
  })

  it('parses a solver probe response', () => {
    const result = probeSolversResponseSchema.parse({
      message: 'node1 solver probe completed.',
      data: {
        alias: 'node1',
        label: 'Node 1',
        connected: true,
        duration_seconds: 0.5,
        exit_code: 0,
        stdout: 'calculix=/usr/bin/ccx\n',
        stderr: '',
        solvers: [
          {
            alias: 'calculix',
            label: 'CalculiX',
            kind: 'structural',
            executable: 'ccx',
            artifact_patterns: ['*.frd', 'result.txt'],
            available: true,
            path: '/usr/bin/ccx',
          },
        ],
      },
    })
    expect(result.data.solvers[0].available).toBe(true)
  })

  it('parses a start solver run response', () => {
    const result = startSolverRunResponseSchema.parse({
      message: 'node1 calculix solver run started.',
      data: {
        run_id: 'run-001',
        status: 'created',
        archive_path: '/tmp/run-001',
        remote_workdir: '/home/test/run-001',
        compute_node: 'node1',
        solver: {
          alias: 'calculix',
          label: 'CalculiX',
          kind: 'structural',
          executable: 'ccx',
          artifact_patterns: ['*.frd', 'result.txt'],
        },
      },
    })
    expect(result.data.solver.alias).toBe('calculix')
  })

  it('parses a start workflow run response', () => {
    const result = startWorkflowRunResponseSchema.parse({
      message: 'local FreeCAD -> PrePoMax workflow started.',
      data: {
        run_id: 'run-freecad-prepomax-001',
        status: 'created',
        archive_path: '/tmp/run-freecad-prepomax-001',
        remote_workdir: '/tmp/run-freecad-prepomax-001',
        compute_node: 'local',
        workflow: {
          alias: 'freecad-prepomax',
          label: 'FreeCAD -> PrePoMax',
          kind: 'workflow',
          executable: 'WorkflowRunner',
          artifact_patterns: ['*.FCStd', '*.step', '*.frd', 'result.txt'],
          steps: [
            {
              alias: 'freecad',
              label: 'FreeCAD',
              kind: 'preprocessor',
              executable: 'python',
              artifact_patterns: ['*.FCStd', '*.step', 'result.txt'],
            },
            {
              alias: 'prepomax-regenerate',
              label: 'PrePoMax Regenerate',
              kind: 'structural-prepost',
              executable: 'PrePoMax',
              artifact_patterns: ['*.pmx', '*.frd', 'result.txt'],
            },
          ],
        },
      },
    })
    expect(result.data.workflow.steps).toHaveLength(2)
  })
})

describe('probeNodeResponseSchema', () => {
  it('parses a probe response', () => {
    const result = probeNodeResponseSchema.parse({
      message: 'node1 remote compute node probe completed.',
      data: {
        alias: 'node1',
        label: 'Node 1',
        connected: true,
        duration_seconds: 1.23,
        exit_code: 0,
        stdout: 'hostname=node1\nuser=test\ncpu_cores=8\nworkdir=/home/test\n',
        stderr: '',
        details: {
          hostname: 'node1',
          user: 'test',
          cpu_cores: '8',
          workdir: '/home/test',
        },
      },
    })
    expect(result.data.connected).toBe(true)
    expect(result.data.details.hostname).toBe('node1')
    expect(result.data.duration_seconds).toBe(1.23)
    expect(result.data.exit_code).toBe(0)
    expect(result.message).toContain('completed')
  })
})

describe('ApiClientError', () => {
  it('stores status and message', () => {
    const err = new ApiClientError(404, 'Not found', { detail: 'missing' })
    expect(err.name).toBe('ApiClientError')
    expect(err.status).toBe(404)
    expect(err.message).toBe('Not found')
    expect(err.body).toEqual({ detail: 'missing' })
  })

  it('extractValidationIssues extracts details array', () => {
    const err = new ApiClientError(422, 'Validation failed', {
      message: 'Validation failed',
      details: [{ msg: 'field required' }, { msg: 'invalid type' }],
    })
    const issues = extractValidationIssues(err)
    expect(issues).toEqual(['field required', 'invalid type'])
  })

  it('extractValidationIssues falls back to message', () => {
    const err = new ApiClientError(500, 'Server error', null)
    const issues = extractValidationIssues(err)
    expect(issues).toEqual(['Server error'])
  })

  it('extractValidationIssues handles non-ApiClientError', () => {
    const issues = extractValidationIssues(new Error('boom'))
    expect(issues).toEqual(['boom'])
  })
})

import { describe, expect, it } from 'vitest'
import { connectResponseSchema, probeNodeResponseSchema, runArchiveSchema } from './contracts'

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
        toolchain: [{ name: 'test', role: 'solver', status: 'ready' }],
      },
    })
    expect(result.data.port).toBe(8008)
    expect(result.data.compute_nodes).toHaveLength(1)
    expect(result.data.compute_nodes[0].alias).toBe('node1')
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

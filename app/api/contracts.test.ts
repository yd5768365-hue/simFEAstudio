import { describe, expect, it } from 'vitest';
import {
  runArchiveSchema,
  connectResponseSchema,
  probeNodeResponseSchema,
} from './contracts';

describe('connectResponseSchema', () => {
  it('parses a full connect response', () => {
    const result = connectResponseSchema.parse({
      data: {
        connected: true,
        host: 'localhost',
        pid: 12345,
        runs_root: '/tmp/runs',
        config_path: '/tmp/config.json',
        learning_export_root: '/tmp/learning',
        learning_formats: ['md', 'json'],
        learning_default_format: 'md',
        message: 'connected',
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
        default_compute_node: 'node1',
        toolchain: [{ name: 'test', role: 'solver', status: 'ready' }],
      },
    });
    expect(result.data.connected).toBe(true);
    expect(result.data.compute_nodes).toHaveLength(1);
    expect(result.data.compute_nodes[0].alias).toBe('node1');
  });

  it('parses a minimal connect response', () => {
    const result = connectResponseSchema.parse({
      data: {
        connected: false,
        host: '',
        pid: 0,
        runs_root: '',
        config_path: '',
        learning_export_root: '',
        learning_formats: ['md'],
        learning_default_format: 'md',
        message: 'failed',
        compute_nodes: [],
      },
    });
    expect(result.data.connected).toBe(false);
    expect(result.data.compute_nodes).toHaveLength(0);
  });
});

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
    });
    expect(result.run_id).toBe('run-001');
    expect(result.artifacts).toHaveLength(1);
  });

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
    });
    expect(result.exit_code).toBe(0);
    expect(result.summary?.metrics?.max_displacement_mm).toBe(1.5);
    expect(result.scheduler).toBe('slurm');
    expect(result.requested_cpus).toBe(4);
  });
});

describe('probeNodeResponseSchema', () => {
  it('parses a probe response', () => {
    const result = probeNodeResponseSchema.parse({
      data: {
        connected: true,
        duration_seconds: 1.23,
        details: {
          hostname: 'node1',
          user: 'test',
          cpu_cores: '8',
          workdir: '/home/test',
        },
      },
    });
    expect(result.data.connected).toBe(true);
    expect(result.data.details.hostname).toBe('node1');
  });
});

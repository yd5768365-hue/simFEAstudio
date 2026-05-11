import { z } from 'zod'

// ── Shared schemas ──────────────────────────────────────────

export const toolchainItemSchema = z.object({
  name: z.string(),
  role: z.string(),
  status: z.string(),
})

export type ToolchainItem = z.output<typeof toolchainItemSchema>

export const computeNodeSchema = z.object({
  alias: z.string(),
  label: z.string(),
  host: z.string(),
  user: z.string(),
  port: z.number().optional(),
  remote_runs_root: z.string(),
  configured: z.boolean(),
})

export type ComputeNodeConfig = z.output<typeof computeNodeSchema>

export const learningExportRecordSchema = z.object({
  path: z.string(),
  format: z.string(),
  exported_at: z.string(),
})

export type LearningExportRecord = z.output<typeof learningExportRecordSchema>

export const resultSummarySchema = z.object({
  schema_version: z.string().optional(),
  run_id: z.string().optional(),
  case_name: z.string().optional(),
  case_type: z.string().optional(),
  solver: z.string().optional(),
  runner: z.string().optional(),
  status: z.string().optional(),
  scheduler: z
    .object({
      name: z.string().optional(),
      job_id: z.string().optional(),
      partition: z.string().optional(),
      allocated_node: z.string().optional(),
      requested_cpus: z.number().nullable().optional(),
      requested_memory: z.string().optional(),
      last_state: z.string().optional(),
    })
    .optional(),
  metrics: z
    .object({
      max_displacement_mm: z.number().nullable().optional(),
      max_von_mises_mpa: z.number().nullable().optional(),
    })
    .optional(),
  artifacts: z.array(z.string()).optional(),
  visualization: z
    .object({
      kind: z.string().optional(),
      vtk_artifact: z.string().optional(),
      ready: z.boolean().optional(),
    })
    .optional(),
})

export type ResultSummary = z.output<typeof resultSummarySchema>

export const runArchiveSchema = z.object({
  run_id: z.string(),
  case_name: z.string(),
  solver: z.string(),
  runner: z.string(),
  compute_node: z.string(),
  status: z.string(),
  created_at: z.string(),
  started_at: z.string().optional(),
  finished_at: z.string().optional(),
  exit_code: z.number().optional(),
  remote_workdir: z.string(),
  local_archive: z.string(),
  artifacts: z.array(z.string()),
  learning_report: z.string().optional(),
  result_summary: z.string().optional(),
  note: z.string().optional(),
  report: z.string().optional(),
  learning_export: learningExportRecordSchema.optional(),
  learning_exports: z.array(learningExportRecordSchema).optional(),
  summary: resultSummarySchema.nullable().optional(),
  toolchain: z.array(toolchainItemSchema).optional(),
  scheduler: z.string().optional(),
  job_id: z.string().optional(),
  partition: z.string().optional(),
  allocated_node: z.string().optional(),
  requested_cpus: z.number().optional(),
  requested_memory: z.string().optional(),
})

export type RunArchive = z.output<typeof runArchiveSchema>

// ── Connection ──────────────────────────────────────────────

export const connectResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    port: z.number(),
    pid: z.number(),
    host: z.string(),
    runs_root: z.string(),
    config_path: z.string(),
    learning_export_root: z.string(),
    learning_formats: z.array(z.string()),
    learning_default_format: z.string(),
    default_compute_node: z.string().optional(),
    compute_nodes: z.array(computeNodeSchema),
    toolchain: z.array(toolchainItemSchema).optional(),
  }),
})

export type ConnectResponse = z.output<typeof connectResponseSchema>

// ── Runs ────────────────────────────────────────────────────

export const listRunsResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    runs_root: z.string().optional(),
    learning_export_root: z.string().optional(),
    learning_formats: z.array(z.string()).optional(),
    learning_default_format: z.string().optional(),
    runs: z.array(runArchiveSchema),
  }),
})

export type ListRunsResponse = z.output<typeof listRunsResponseSchema>

export const getRunResponseSchema = z.object({
  message: z.string(),
  data: runArchiveSchema.nullable(),
})

export type GetRunResponse = z.output<typeof getRunResponseSchema>

export const saveNoteBodySchema = z.object({
  note: z.string(),
})

export const saveNoteResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    saved: z.boolean(),
    note_path: z.string().optional(),
    report_path: z.string().optional(),
  }),
})

export type SaveNoteResponse = z.output<typeof saveNoteResponseSchema>

export const generateReportResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    run_id: z.string().optional(),
    report: z.string(),
    report_path: z.string(),
    summary: z.unknown().optional(),
  }),
})

export type GenerateReportResponse = z.output<typeof generateReportResponseSchema>

export const exportLearningBodySchema = z.object({
  format: z.string(),
  target_dir: z.string().optional(),
})

export const exportLearningResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    exported: z.boolean(),
    export_path: z.string().optional(),
    summary: z.unknown().optional(),
    record: z.unknown().optional(),
  }),
})

export type ExportLearningResponse = z.output<typeof exportLearningResponseSchema>

export const startDemoRunResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    run_id: z.string(),
    status: z.string(),
    archive_path: z.string(),
    remote_workdir: z.string(),
    compute_node: z.string(),
  }),
})

export type StartDemoRunResponse = z.output<typeof startDemoRunResponseSchema>

export const startSlurmDemoRunResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    run_id: z.string(),
    status: z.string(),
    archive_path: z.string(),
    remote_workdir: z.string(),
    compute_node: z.string(),
    scheduler: z.string().optional(),
    partition: z.string().optional(),
    requested_cpus: z.number().optional(),
    requested_memory: z.string().optional(),
  }),
})

export type StartSlurmDemoRunResponse = z.output<typeof startSlurmDemoRunResponseSchema>

export const cancelRunResponseSchema = z.object({
  message: z.string(),
  data: z.unknown(),
})

// ── Compute Nodes ───────────────────────────────────────────

const runCommandResultSchema = z.object({
  exit_code: z.number(),
  stdout: z.string(),
  stderr: z.string(),
  duration_seconds: z.number(),
})

export const probeNodeResponseSchema = z.object({
  message: z.string(),
  data: runCommandResultSchema.extend({
    alias: z.string(),
    label: z.string(),
    connected: z.boolean(),
    details: z.object({
      hostname: z.string().optional(),
      user: z.string().optional(),
      cpu_cores: z.string().optional(),
      workdir: z.string().optional(),
    }),
  }),
})

export type ProbeNodeResponse = z.output<typeof probeNodeResponseSchema>

export const probeSchedulerResponseSchema = z.object({
  message: z.string(),
  data: runCommandResultSchema.extend({
    alias: z.string(),
    label: z.string(),
    connected: z.boolean(),
    details: z.object({
      hostname: z.string().optional(),
      user: z.string().optional(),
      scheduler: z.string().optional(),
      sbatch: z.boolean().optional(),
      srun: z.boolean().optional(),
      squeue: z.boolean().optional(),
      qsub: z.boolean().optional(),
      bsub: z.boolean().optional(),
      cpu_cores: z.string().optional(),
      memory: z.string().optional(),
      workdir: z.string().optional(),
    }),
  }),
})

export type ProbeSchedulerResponse = z.output<typeof probeSchedulerResponseSchema>

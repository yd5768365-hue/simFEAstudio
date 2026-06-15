import { z } from 'zod'

// ── Shared schemas ──────────────────────────────────────────

export const toolchainItemSchema = z.object({
  name: z.string(),
  role: z.string(),
  status: z.string(),
})

export type ToolchainItem = z.output<typeof toolchainItemSchema>

export const solverDefinitionSchema = z.object({
  alias: z.string(),
  label: z.string(),
  kind: z.string(),
  executable: z.string(),
  description: z.string().optional(),
  artifact_patterns: z.array(z.string()),
})

export type SolverDefinition = z.output<typeof solverDefinitionSchema>

export const solverInstallationSchema = z.object({
  alias: z.string(),
  label: z.string(),
  install_mode: z.string(),
  status: z.enum(['missing', 'found', 'verified']),
  configured_executable: z.string(),
  discovered_path: z.string(),
  executable_candidates: z.array(z.string()),
  common_paths: z.array(z.string()),
  searched_paths: z.array(z.string()).optional(),
  verify_command: z.string(),
  install_hint: z.string(),
  install_guide_url: z.string(),
  input_extensions: z.array(z.string()),
  verified: z.boolean().optional(),
  exit_code: z.number().optional(),
  stdout: z.string().optional(),
  stderr: z.string().optional(),
  duration_seconds: z.number().optional(),
})

export type SolverInstallation = z.output<typeof solverInstallationSchema>

export const solverExecutableBodySchema = z.object({
  executable: z.string().optional(),
})

export const computeNodeSchema = z.object({
  alias: z.string(),
  label: z.string(),
  host: z.string(),
  user: z.string(),
  port: z.number().nullable().optional(),
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
  started_at: z.string().nullable().optional(),
  finished_at: z.string().nullable().optional(),
  exit_code: z.number().nullable().optional(),
  remote_workdir: z.string(),
  local_archive: z.string(),
  input_files: z.array(z.string()).nullable().optional(),
  artifacts: z.array(z.string()),
  learning_report: z.string().nullable().optional(),
  result_summary: z.string().nullable().optional(),
  note: z.string().nullable().optional(),
  report: z.string().nullable().optional(),
  learning_export: learningExportRecordSchema.nullable().optional(),
  learning_exports: z.array(learningExportRecordSchema).nullable().optional(),
  summary: resultSummarySchema.nullable().optional(),
  toolchain: z.array(toolchainItemSchema).nullable().optional(),
  scheduler: z.string().nullable().optional(),
  job_id: z.string().nullable().optional(),
  partition: z.string().nullable().optional(),
  allocated_node: z.string().nullable().optional(),
  requested_cpus: z.number().nullable().optional(),
  requested_memory: z.string().nullable().optional(),
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
    solvers: z.array(solverDefinitionSchema).optional(),
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
  note: z.string().optional(),
  answers: z.record(z.string()).optional(),
  export: z.boolean().optional(),
  format: z.string().optional(),
  target_dir: z.string().optional(),
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

export const guidedQuestionSchema = z.object({
  id: z.string(),
  question: z.string(),
  answer: z.string(),
})

export type GuidedQuestion = z.output<typeof guidedQuestionSchema>

export const guidedQuestionsResponseSchema = z.object({
  message: z.string(),
  data: z
    .object({
      run_id: z.string(),
      questions: z.array(guidedQuestionSchema),
    })
    .nullable(),
})

export type GuidedQuestionsResponse = z.output<typeof guidedQuestionsResponseSchema>

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

export const preflightIssueSchema = z.object({
  severity: z.string(),
  category: z.string(),
  message: z.string(),
})

export type PreflightIssue = z.output<typeof preflightIssueSchema>

export const startSolverRunResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    run_id: z.string(),
    status: z.string(),
    archive_path: z.string(),
    remote_workdir: z.string(),
    compute_node: z.string(),
    solver: solverDefinitionSchema,
    preflight_issues: z.array(preflightIssueSchema).optional().default([]),
  }),
})

export type StartSolverRunResponse = z.output<typeof startSolverRunResponseSchema>

export const startWorkflowRunResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    run_id: z.string(),
    status: z.string(),
    archive_path: z.string(),
    remote_workdir: z.string(),
    compute_node: z.string(),
    workflow: solverDefinitionSchema.extend({
      steps: z.array(solverDefinitionSchema),
    }),
  }),
})

export type StartWorkflowRunResponse = z.output<typeof startWorkflowRunResponseSchema>

export const workflowStepSchema = z.union([
  z.string(),
  z.object({
    solver: z.string(),
    params: z.record(z.string()).optional(),
  }),
])

export type WorkflowStep = z.output<typeof workflowStepSchema>

export const customWorkflowBodySchema = z.object({
  steps: z.array(workflowStepSchema),
})

export type CustomWorkflowBody = z.output<typeof customWorkflowBodySchema>

export const startCustomWorkflowRunResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    run_id: z.string(),
    status: z.string(),
    archive_path: z.string(),
    remote_workdir: z.string(),
    compute_node: z.string(),
    workflow: solverDefinitionSchema.extend({
      steps: z.array(solverDefinitionSchema),
    }),
    skipped_steps: z.array(z.string()).optional(),
  }),
})

export type StartCustomWorkflowRunResponse = z.output<typeof startCustomWorkflowRunResponseSchema>

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

// ── SSE Events ──────────────────────────────────────────────
// Mirrors src/backends/simfea_api/schemas.py

export const sseEventBaseSchema = z.object({
  run_id: z.string(),
  type: z.string(),
  seq: z.number(),
  archive_path: z.string(),
})

export const stdoutEventSchema = sseEventBaseSchema.extend({
  type: z.literal('stdout'),
  line: z.string(),
})

export const stderrEventSchema = sseEventBaseSchema.extend({
  type: z.literal('stderr'),
  line: z.string(),
})

export const statusEventSchema = sseEventBaseSchema.extend({
  type: z.literal('status'),
  status: z.enum(['running', 'submitting', 'queued', 'canceling']),
  line: z.string(),
  remote_workdir: z.string().nullable().optional(),
  job_id: z.string().nullable().optional(),
})

export const artifactEventSchema = sseEventBaseSchema.extend({
  type: z.literal('artifact'),
  line: z.string(),
  artifact: z.string().optional(),
})

export const finishedEventSchema = sseEventBaseSchema.extend({
  type: z.literal('finished'),
  status: z.string(),
  exit_code: z.number(),
  line: z.string(),
  job_id: z.string().nullable().optional(),
  allocated_node: z.string().nullable().optional(),
})

export const staProgressEventSchema = sseEventBaseSchema.extend({
  type: z.literal('sta_progress'),
  line: z.string(),
  step: z.number(),
  increment: z.number(),
  iteration: z.number(),
  progress_pct: z.number().nullable().optional(),
})

export const sseEventSchema = z.discriminatedUnion('type', [
  stdoutEventSchema,
  stderrEventSchema,
  statusEventSchema,
  artifactEventSchema,
  finishedEventSchema,
  staProgressEventSchema,
])

export type SseEvent = z.output<typeof sseEventSchema>
export type StdoutEvent = z.output<typeof stdoutEventSchema>
export type StderrEvent = z.output<typeof stderrEventSchema>
export type StatusEvent = z.output<typeof statusEventSchema>
export type ArtifactEvent = z.output<typeof artifactEventSchema>
export type FinishedEvent = z.output<typeof finishedEventSchema>
export type StaProgressEvent = z.output<typeof staProgressEventSchema>

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

export const probeSolversResponseSchema = z.object({
  message: z.string(),
  data: runCommandResultSchema.extend({
    alias: z.string(),
    label: z.string(),
    connected: z.boolean(),
    solvers: z.array(
      solverDefinitionSchema.extend({
        available: z.boolean(),
        path: z.string(),
      })
    ),
  }),
})

export type ProbeSolversResponse = z.output<typeof probeSolversResponseSchema>

export const listSolversResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    solvers: z.array(solverDefinitionSchema),
  }),
})

export type ListSolversResponse = z.output<typeof listSolversResponseSchema>

export const listSolverInstallationsResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    solvers: z.array(solverInstallationSchema),
  }),
})

export type ListSolverInstallationsResponse = z.output<typeof listSolverInstallationsResponseSchema>

export const solverInstallationResponseSchema = z.object({
  message: z.string(),
  data: solverInstallationSchema,
})

export type SolverInstallationResponse = z.output<typeof solverInstallationResponseSchema>

// ── Solver Pack Install ───────────────────────────────────────

export const installSolverResponseSchema = z.object({
  install_id: z.string(),
  message: z.string(),
})

export type InstallSolverResponse = z.output<typeof installSolverResponseSchema>

export const installProgressEventSchema = z.object({
  type: z.literal('install_progress'),
  step: z.enum(['download', 'extract', 'scan', 'verify']),
  progress_pct: z.number(),
  message: z.string(),
})

export const installCompleteEventSchema = z.object({
  type: z.literal('install_complete'),
  data: solverInstallationSchema,
})

export const installErrorEventSchema = z.object({
  type: z.literal('install_error'),
  message: z.string(),
})

export const installEventSchema = z.discriminatedUnion('type', [
  installProgressEventSchema,
  installCompleteEventSchema,
  installErrorEventSchema,
])

export type InstallProgressEvent = z.output<typeof installProgressEventSchema>
export type InstallCompleteEvent = z.output<typeof installCompleteEventSchema>
export type InstallErrorEvent = z.output<typeof installErrorEventSchema>
export type InstallEvent = z.output<typeof installEventSchema>

// ── Benchmark Lab ───────────────────────────────────────────

export const learningTierSchema = z.object({
  id: z.string(),
  label: z.string(),
  focus: z.string(),
})

export type LearningTier = z.output<typeof learningTierSchema>

export const benchmarkCaseSchema = z.object({
  name: z.string(),
  has_problem: z.boolean(),
  has_results: z.boolean(),
  group: z.string().optional().default('基础案例'),
  title: z.string().optional().default(''),
  subtitle: z.string().optional().default(''),
  level: z.string().optional().default(''),
  physics: z.string().optional().default(''),
  dimension: z.string().optional().default(''),
  methods: z.array(z.string()).optional().default([]),
  status: z.string().optional().default(''),
  learning_tier: learningTierSchema.nullable().optional(),
})

export type BenchmarkCase = z.output<typeof benchmarkCaseSchema>

export const listBenchmarksResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    cases: z.array(benchmarkCaseSchema),
  }),
})

export type ListBenchmarksResponse = z.output<typeof listBenchmarksResponseSchema>

export const benchmarkResultSchema = z.object({
  method: z.string(),
  u_L_mm: z.string(),
  sigma_MPa: z.string().optional(),
  sigma_max_MPa: z.string().optional(),
  error_u_L_mm: z.string(),
  notes: z.string(),
})

export type BenchmarkResult = z.output<typeof benchmarkResultSchema>

export const benchmarkCaseDetailSchema = z.object({
  name: z.string(),
  group: z.string().optional().default('基础案例'),
  title: z.string().optional().default(''),
  level: z.string().optional().default(''),
  physics: z.string().optional().default(''),
  dimension: z.string().optional().default(''),
  methods: z.array(z.string()).optional().default([]),
  status: z.string().optional().default(''),
  learning_tier: learningTierSchema.nullable().optional(),
  problem_html: z.string().optional().default(''),
  problem_md: z.string().optional().default(''),
  results: z.array(benchmarkResultSchema),
})

export type BenchmarkCaseDetail = z.output<typeof benchmarkCaseDetailSchema>

export const getBenchmarkCaseResponseSchema = z.object({
  message: z.string(),
  data: benchmarkCaseDetailSchema,
})

export type GetBenchmarkCaseResponse = z.output<typeof getBenchmarkCaseResponseSchema>

// ── Knowledge Base ─────────────────────────────────────────

export const knowledgeDocumentSchema = z.object({
  id: z.string(),
  name: z.string(),
  original_path: z.string().optional(),
  created_at: z.string(),
  chunk_count: z.number(),
})

export type KnowledgeDocument = z.output<typeof knowledgeDocumentSchema>

export const uploadKnowledgeResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    doc_id: z.string(),
    name: z.string(),
    chunk_count: z.number(),
  }),
})

export type UploadKnowledgeResponse = z.output<typeof uploadKnowledgeResponseSchema>

export const listKnowledgeResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    documents: z.array(knowledgeDocumentSchema),
  }),
})

export type ListKnowledgeResponse = z.output<typeof listKnowledgeResponseSchema>

export const deleteKnowledgeResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    deleted: z.boolean(),
  }),
})

export type DeleteKnowledgeResponse = z.output<typeof deleteKnowledgeResponseSchema>

export const askKnowledgeBodySchema = z.object({
  run_id: z.string().optional(),
  question: z.string(),
  doc_ids: z.array(z.string()).optional(),
})

export const knowledgeSourceSchema = z.object({
  text: z.string(),
  source: z.string(),
  score: z.number(),
})

export const askKnowledgeResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    answer: z.string(),
    sources: z.array(knowledgeSourceSchema),
  }),
})

export type AskKnowledgeResponse = z.output<typeof askKnowledgeResponseSchema>

// ── Experiment Lab ────────────────────────────────────────────

export const expFileSchema = z.object({
  path: z.string(),
  name: z.string(),
  dir: z.string(),
  size: z.number(),
})

export type ExpFile = z.output<typeof expFileSchema>

export const listExperimentFilesResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    files: z.array(expFileSchema),
  }),
})

export type ListExperimentFilesResponse = z.output<typeof listExperimentFilesResponseSchema>

export const readExperimentFileResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    content: z.string(),
    path: z.string(),
  }),
})

export type ReadExperimentFileResponse = z.output<typeof readExperimentFileResponseSchema>

export const saveExperimentFileBodySchema = z.object({
  content: z.string(),
})

export const saveExperimentFileResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    path: z.string(),
  }),
})

export const runExperimentCodeBodySchema = z.object({
  code: z.string().optional(),
  file_path: z.string().optional(),
})

export const runExperimentCodeResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    exit_code: z.number(),
    stdout: z.string(),
    stderr: z.string(),
  }),
})

export type RunExperimentCodeResponse = z.output<typeof runExperimentCodeResponseSchema>

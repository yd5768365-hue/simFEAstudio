export interface ToolchainItem {
  name: string;
  role: string;
  status: string;
}

export interface ResultSummary {
  schema_version?: string;
  run_id?: string;
  case_name?: string;
  case_type?: string;
  solver?: string;
  runner?: string;
  status?: string;
  scheduler?: {
    name?: string;
    job_id?: string;
    partition?: string;
    allocated_node?: string;
    requested_cpus?: number | null;
    requested_memory?: string;
    last_state?: string;
  };
  metrics?: {
    max_displacement_mm?: number | null;
    max_von_mises_mpa?: number | null;
  };
  artifacts?: string[];
  visualization?: {
    kind?: string;
    vtk_artifact?: string;
    ready?: boolean;
  };
}

export interface RunArchive {
  run_id: string;
  case_name: string;
  solver: string;
  runner: string;
  compute_node: string;
  status: string;
  created_at: string;
  started_at?: string;
  finished_at?: string;
  exit_code?: number;
  remote_workdir: string;
  local_archive: string;
  artifacts: string[];
  learning_report?: string;
  result_summary?: string;
  note?: string;
  report?: string;
  summary?: ResultSummary | null;
  toolchain?: ToolchainItem[];
  scheduler?: string;
  job_id?: string;
  partition?: string;
  allocated_node?: string;
  requested_cpus?: number;
  requested_memory?: string;
}

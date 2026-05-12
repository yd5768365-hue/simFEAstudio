# SimFEA Studio

SimFEA Studio is a desktop-oriented CAE workflow studio built with Vue 3, Tauri, and a FastAPI sidecar. It turns local, SSH, Slurm, and solver executions into reproducible engineering evidence: command logs, archived inputs, solver artifacts, result summaries, VTK visualization data, and learning notes.

The current milestone is no longer just a UI proof of concept. The project can run a real local CalculiX cantilever case, collect FRD/DAT/STA artifacts, convert FRD output to VTK, summarize displacement and stress metrics, and stream run events back to the frontend.

## Highlights

- Vue 3 + Vite frontend inside a Tauri desktop shell.
- FastAPI Python sidecar for run orchestration and evidence APIs.
- Local, SSH, Slurm, and declarative solver runner paths.
- OpenCAEHub-inspired solver configuration with `pre_commands`, `command_template`, `post_commands`, `artifact_patterns`, and `input_files`.
- CalculiX local end-to-end path with FRD to VTK conversion.
- VTK.js result viewport with lazy-loaded visualization modules.
- SSE run event stream with reconnect replay via `from_seq`.
- Archived run directory containing metadata, command scripts, stdout/stderr, events, inputs, artifacts, reports, and notes.
- Backend and frontend contract tests covering the current workflow.

## Architecture

```text
Vue 3 / Vite / Tauri
  -> HTTP + SSE
FastAPI sidecar
  -> LocalRunner / SSHRunner / SlurmRunner / SolverRunner
  -> CalculiX / OpenFOAM / Elmer adapters
  -> run archive + result summary + learning report
  -> VTK.js visualization in the frontend
```

The repository keeps the runner boundary explicit:

- `LocalRunner`: runs commands on the local machine.
- `SSHRunner`: runs commands on a configured remote node.
- `SlurmRunner`: submits and polls batch jobs.
- `SolverRunner`: writes solver input files, runs solver commands, collects artifacts, and triggers post-processing.

## Current Solver Status

| Solver | Status | Notes |
| --- | --- | --- |
| CalculiX | Working local end-to-end path | Runs a real cantilever case, archives `.frd/.dat/.sta`, converts FRD to VTK, and extracts summary metrics. |
| OpenFOAM | Adapter placeholder | Configuration shape is present; a real case bundle still needs to be added. |
| Elmer | Adapter placeholder | Configuration shape is present; a real case bundle still needs to be added. |

Example verified CalculiX output:

```text
status=finished
exit_code=0
solver=calculix
max_displacement_mm=8.933
max_von_mises_mpa=37.502
artifacts=cantilever.frd, cantilever.dat, cantilever.sta, result.txt, result_summary.json, solver_result.vtk
```

## Quick Start

### 1. Install dependencies

```powershell
corepack pnpm install
python -m pip install -e .
```

For the known Windows development environment, the `simfea` conda environment has been used for Python verification.

### 2. Create local configuration

```powershell
New-Item -ItemType Directory -Force .simfea
Copy-Item simfea.config.example.json .simfea\config.json
```

For a local Windows CalculiX run, configure a local node and point the solver executable to your CalculiX wrapper or binary:

```json
{
  "compute": {
    "default_node": "local",
    "nodes": [
      { "alias": "local", "label": "Local workstation", "host": "localhost" }
    ]
  },
  "solvers": [
    {
      "alias": "calculix",
      "executable": "C:\\path\\to\\CalculiX\\bin\\ccx.bat",
      "command_template": "C:\\path\\to\\CalculiX\\bin\\ccx.bat cantilever"
    }
  ]
}
```

`.simfea/` is intentionally ignored by Git because it contains local machine paths and run archives.

### 3. Start the sidecar

```powershell
python src/backends/main.py
```

### 4. Start the frontend

```powershell
corepack pnpm dev:frontend
```

### 5. Trigger a local solver run

```powershell
curl -X POST http://localhost:8008/v1/runs/local/solvers/calculix
curl http://localhost:8008/v1/runs
```

## API Surface

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/v1/connect` | GET | Sidecar connection and configuration summary. |
| `/v1/config` | GET | Current API, compute node, solver, and learning settings. |
| `/v1/compute-nodes` | GET | List configured compute nodes. |
| `/v1/compute-nodes/{alias}/probe` | GET | Probe node reachability and basic environment details. |
| `/v1/compute-nodes/{alias}/scheduler-probe` | GET | Probe Slurm/PBS/LSF-style scheduler tools. |
| `/v1/compute-nodes/{alias}/solvers/probe` | GET | Probe configured solver executables. |
| `/v1/solvers` | GET | List public solver definitions. |
| `/v1/runs` | GET | List archived runs. |
| `/v1/runs/{run_id}` | GET | Load one run archive. |
| `/v1/runs/{alias}/demo` | POST | Start an SSH demo run. |
| `/v1/runs/{alias}/slurm-demo` | POST | Start a Slurm demo run. |
| `/v1/runs/{alias}/solvers/{solver_alias}` | POST | Start a configured solver run. |
| `/v1/runs/{run_id}/events` | GET | SSE run events; supports `?from_seq=N` replay. |
| `/v1/runs/{run_id}/artifacts/{artifact_path}` | GET | Download archived artifacts. |
| `/v1/runs/{run_id}/result-summary` | GET | Load generated result summary. |
| `/v1/runs/{run_id}/report` | GET | Generate or load a learning report. |
| `/v1/runs/{run_id}/learning-export` | POST | Export a learning record as md/json/txt. |
| `/v1/runs/{run_id}/note` | POST | Save a run note. |
| `/v1/runs/{run_id}/cancel` | POST | Request run cancellation. |

## Run Archive Layout

```text
.simfea/runs/<run_id>/
  meta.json
  command.sh
  stdout.log
  stderr.log
  events.jsonl
  note.md
  learning_report.md
  inputs/
  artifacts/
    cantilever.frd
    cantilever.dat
    cantilever.sta
    result.txt
    result_summary.json
    solver_result.vtk
```

## Verification

Current verification recorded in the development log:

```powershell
python -m unittest discover -s src/backends/tests -v
corepack pnpm test
corepack pnpm build
python -m py_compile src/backends/main.py src/backends/simfea_api/*.py src/backends/simfea_api/runners/*.py src/backends/inference/*.py
git diff --check
```

Latest known coverage:

- Backend: 75 unit tests passing.
- Frontend: 20 Vitest tests passing.
- Production frontend build passes with only the known lazy-loaded VTK XML reader chunk warning.

## Documentation

- `docs/DEV_LOG_2026-05-12.md`: detailed development log and verification notes.
- `docs/ARCHITECTURE_ROADMAP.md`: architecture direction and borrowed patterns from sim-main and OpenCAEHub.
- `docs/RUNNER_DESIGN.md`: runner boundaries and execution model.
- `docs/API_CONTRACTS.md`: API contract examples.
- `docs/AI_FEA_EXPLORATION_NOTE_2030.md`: project introduction and AI + FEA exploration note.

## Roadmap

- Add real OpenFOAM case integration.
- Add real Elmer case integration.
- Add FreeCAD or Salome preprocessing hooks.
- Improve frontend result inspection around generated VTK and solver artifacts.
- Continue evolving AI-assisted learning reports and engineering evidence review.

## License

Apache-2.0

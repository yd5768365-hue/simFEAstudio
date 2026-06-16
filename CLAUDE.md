# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project identity

SimFEA Studio is a desktop simulation learning workbench. It does **not** solve physics equations — it manages solvers, compute nodes, run archives, and learning records. Think "lab notebook for FEA," not another CAE tool.

The project is evolving toward a **Benchmark Lab** — a solver-agnostic comparison platform that validates standard mechanics problems (analytic / FEM / AI solvers) side by side. See `docs/DIRECTION_2026.md` for the full vision.

## Tech stack

| Layer | Technology |
|-------|-----------|
| Desktop shell | Tauri 2 (Rust) |
| Frontend | Vue 3 + TypeScript + Vite + VTK.js |
| Backend | FastAPI Python sidecar (spawned by Tauri) |
| Solvers | CalculiX (verified), OpenFOAM/Elmer (skeleton) |
| Package manager | pnpm (frontend), pip (Python) |

## Common commands

```powershell
# Development
pnpm install                      # Install frontend deps
python -m pip install -e .        # Install Python package
python src/backends/main.py       # Start sidecar (port 8008)
pnpm dev:frontend                 # Vite dev server (port 3000)
pnpm dev:all                      # Sidecar + frontend concurrently
pnpm dev:tauri                    # Full Tauri desktop app (auto-starts Vite)

# Testing
python -m unittest discover -s src/backends/tests -v    # Python unit tests
python -m unittest src/backends/tests/test_learning.py -v  # Single Python test file
pnpm test                        # Vitest unit tests
pnpm test:watch                  # Vitest in watch mode
pnpm vitest run app/api/contracts.test.ts  # Single Vitest file

# Linting & formatting
pnpm lint                        # Biome check (app/ only)
pnpm format                      # Biome check --write (app/ only)
python scripts/check_backend_boundaries.py   # Python module boundary audit

# Build
pnpm build                       # Vite production build
pnpm build:sidecar-winos         # PyInstaller sidecar binary (Windows)
git diff --check                 # Whitespace validation
```

Note: `pnpm dev:tauri` automatically starts the Vite dev server via `beforeDevCommand` — you do not need to run `pnpm dev:frontend` separately.

Line endings are enforced to LF via `.gitattributes` (`* text=auto eol=lf`).

## Architecture

```
Tauri desktop shell
  └─ spawns Python sidecar (src/backends/main.py)
       └─ FastAPI on port 8008
            ├─ /v1/runs/* — run lifecycle (solver runs + workflow runs)
            ├─ /v1/runs/{alias}/workflows/* — multi-step solver workflows
            ├─ /v1/compute-nodes/* — SSH/scheduler probes
            ├─ /v1/solvers — solver definitions
            ├─ /v1/toolchain/* — solver discovery, path config, verification, install
            ├─ /v1/benchmarks — list benchmark cases (learning/benchmarks/)
            ├─ /v1/benchmarks/{case_name} — problem.md + comparison.csv
            └─ SSE /v1/runs/{id}/events — real-time log streaming

Vue frontend (app/)
  └─ Vite dev server on port 3000
       ├─ App.vue — top-level layout with side-navigation (4 views)
       │    ├─ Composer (作业区) — job config, run evidence, live logs
       │    ├─ Benchmark Lab (基准) — benchmark case browser
       │    ├─ Learning Library (学习库) — run archive browser
       │    └─ Toolchain Manager (工具链) — solver discovery & config
       ├─ components/BenchmarkLab.vue — benchmark case list + comparison tables
       ├─ components/RemotePanel.vue — remote run controls
       ├─ components/ResultEvidenceView.vue — artifact/evidence browser
       ├─ components/VtkResultViewport.vue — VTK.js 3D visualization
       ├─ composables/useRemoteRuns.ts — remote run state machine
       ├─ composables/useRunEvents.ts — SSE event stream (with reconnect)
       ├─ composables/useSidecarListeners.ts — sidecar lifecycle
       ├─ types.ts — re-exports all type-only exports from contracts.ts
       ├─ utils/markdown.ts — minimal markdown→HTML renderer (headings, code, tables, lists)
       └─ api/simfeaClient.ts — typed API client (Zod contracts)
```

### Backend module layout

```
src/backends/
├── main.py                      # FastAPI app + all route handlers
├── simfea_api/
│   ├── config.py                # Settings, solver/node data models, path resolution
│   ├── run_archive.py           # RemoteRun dataclass, event buffer, I/O helpers
│   ├── learning.py              # Structured guided notes + learning report generator
│   ├── results.py               # Result summary + FRD→VTK post-processing trigger
│   ├── frd_to_vtk.py            # CalculiX FRD parser + ASCII VTK writer
│   ├── logger.py                # Structured logging (ANSI dev / JSON prod)
│   ├── schemas.py               # Pydantic SSE event models (discriminated union)
│   ├── cleanup.py               # Background run directory pruning
│   └── runners/
│       ├── ssh.py               # SSH command execution + SCP file transfer
│       ├── slurm.py             # sbatch submission
│       ├── slurm_polling.py     # squeue/sacct polling + state machine
│       ├── solver.py            # SolverRunner: input files → pre → solver → post → artifacts
│       ├── remote_files.py      # Remote file glob helpers
│       └── workflow.py          # WorkflowRunner: chain solver steps into one run
├── inference/
│   └── infer_text_api.py        # AI text inference (report generation)
└── tests/                       # Python unit tests (unittest)
```

### Python module boundary rules

Enforced by `scripts/check_backend_boundaries.py`:
1. `simfea_api/` modules must not import `main` (no circular imports)
2. `runners/` must not import `fastapi` or `sse_starlette` (runners are pure execution)

## Key design decisions

### Three-layer learning architecture (order matters)

```
1. Log streaming (SSE, real-time) → stdout/stderr recorded
2. Guided user notes → structured Q&A saved to note.md
3. AI learning report → generated only after note.md is saved
```

The original order (logs → report → notes) was wrong — users need to reflect before AI summarizes. The `POST /v1/runs/:id/note` endpoint triggers `learning_report.md` regeneration.

### Typed API contracts

Frontend uses a contract-based typed API client with three layers:

1. **`app/api/contracts.ts`** — Zod schemas that mirror FastAPI response shapes (SSE events use `z.discriminatedUnion` on `type`)
2. **`app/api/client.ts`** — Generic `contract()` + `createClient()` wrapper around `fetch`. URL params are type-checked via the contract's `params` tuple. Every response is validated through `c.response.parse(json)` before the caller sees it. Validation failures or HTTP errors throw `ApiClientError`.
3. **`app/api/simfeaClient.ts`** — Instantiates the generic client with all endpoint contracts. Returns a typed `SimfeaClient` object.

When adding or changing an endpoint, update the Zod schema, the contract definition, and the Python route together.

### Frontend import conventions

- `@/` absolute imports (maps to `app/` via `tsconfig.json` paths + `config/vite.config.js` alias)
- Barrel exports at `app/api/index.ts` and `app/composables/index.ts`
- Type-only imports use `import type { X }` from `@/types` — `app/types.ts` re-exports all public types from `api/contracts.ts` so components don't need to know the source module

### Biome formatting

- 2-space indent, single quotes, as-needed semicolons, ES5 trailing commas
- Line width: 110 characters
- Pre-commit hook runs `lint-staged` → Biome on staged files
- Style: no comments in code unless explaining a non-obvious why. Delete dead code, don't comment it out.

### Python logging

Use `create_logger(name)` from `simfea_api/logger.py` instead of `print()`. In dev mode it outputs ANSI-colored human-readable lines; in production (`SIMFEA_ENV=production`) it emits JSON lines.

### Evidence warehouse (.simfea/)

```
.simfea/runs/<run_id>/
├── meta.json              # Run metadata (status, solver, node, timestamps)
├── run.command            # The actual command executed
├── stdout.log / stderr.log
├── events.jsonl           # SSE event replay buffer
├── note.md                # Structured guided notes (Q&A format)
├── learning_report.md     # Auto-generated after note saved
├── inputs/                # Solver input files
└── artifacts/             # Solver outputs (.frd, .dat, .sta, result.txt, solver_result.vtk)
```

`.simfea/` is git-ignored. Never commit solver paths or SSH credentials.

### Solvers are declarative (JSON config)

User `.simfea/config.json` overrides specific fields for a named solver (e.g., `calculix`) while preserving defaults for others. Merging is by `alias` — user config does not wipe the default solver list.

Each solver definition: `executable`, `command_template`, `pre_commands`, `post_commands`, `artifact_patterns`, `input_files`.

### WorkflowRunner (multi-step solver chains)

`runners/workflow.py` defines workflows that chain multiple solver steps into a single run archive. The first built-in workflow is `freecad-prepomax`: FreeCAD generates a `.step` geometry → PrePoMax regeneration processes it for meshing/solving. Each step is a regular `SolverDefinition`; the workflow collects artifact patterns from all steps and runs sequentially in the same workdir.  Workflows are exposed at `POST /v1/runs/{alias}/workflows/freecad-prepomax`.

### Benchmark Lab (case comparison platform)

`learning/benchmarks/` contains structured benchmark cases, each with a `problem.md` (physics description + analytic solution) and a `results/comparison.csv` (unified comparison table across methods — analytic, CalculiX, PINN, ANSYS, etc.).

Backend endpoints (`GET /v1/benchmarks`, `GET /v1/benchmarks/{case_name}`) scan the directory and serve problem descriptions + CSV results. The frontend `BenchmarkLab.vue` renders problem.md via the custom `app/utils/markdown.ts` renderer and displays comparison tables.

The `comparison.csv` format: `method, u_L_mm, sigma_MPa, error_u_L_mm, notes`. This is solver-agnostic — the UI doesn't need to understand each solver's internals.

Current cases: `rod_tension`, `rod_distributed_load` (1D rod problems). See `docs/DIRECTION_2026.md` for the long-term vision.

### Tauri sidecar lifecycle

Tauri (`src-tauri/src/main.rs`) spawns a PyInstaller-built sidecar binary at startup via `shell().sidecar("main")`. The sidecar is a `CommandChild` stored in `Arc<Mutex<Option<CommandChild>>>` app state. Stdout/stderr lines from the sidecar are emitted to the frontend as `sidecar-stdout` / `sidecar-stderr` events. Shutdown works by writing `"sidecar shutdown\n"` to the sidecar's stdin, then killing the process.

The `useSidecarListeners.ts` composable listens for these Tauri events on the frontend side.

Tauri plugins in use: `tauri-plugin-shell`, `tauri-plugin-http`, `tauri-plugin-dialog` (native file picker for solver executable selection in ToolchainManager).

### Frontend state management

There is no Pinia or Vuex store. All reactive state lives in composables:
- `useRemoteRuns.ts` — remote run state machine (runs list, start/cancel, polling)
- `useRunEvents.ts` — SSE event stream with exponential-backoff reconnect (max 5 retries, 1s–30s), `lastSeq` tracking for `?from_seq=` replay
- `useSidecarListeners.ts` — sidecar lifecycle events from Tauri

### Windows-specific gotchas

- `asyncio.create_subprocess_shell` can hang on Windows when child processes spawn grandchildren that inherit pipe handles. The fix is `subprocess.run` in `loop.run_in_executor` (see `_run_local_command` in `main.py`).
- CalculiX on Windows requires `ccx.bat`, not `ccx.exe` — the `.bat` sets `OMP_NUM_THREADS` and DLL path.
- FRD parser in `frd_to_vtk.py` handles CalculiX v2.10 `1PSTEP` format, not the `2D`/`2S` sections described in older documentation.

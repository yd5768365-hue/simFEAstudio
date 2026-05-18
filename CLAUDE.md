# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project identity

SimFEA Studio is a desktop simulation learning workbench. It does **not** solve physics equations — it manages solvers, compute nodes, run archives, and learning records. Think "lab notebook for FEA," not another CAE tool.

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
python -m unittest discover -s src/backends/tests -v    # Python unit tests (75)
python -m unittest src/backends/tests/test_learning.py -v  # Single Python test file
pnpm test                        # Vitest unit tests (20)
pnpm test:watch                  # Vitest in watch mode

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
            └─ SSE /v1/runs/{id}/events — real-time log streaming

Vue frontend (app/)
  └─ Vite dev server on port 3000
       ├─ App.vue — top-level layout
       ├─ components/RemotePanel.vue — remote run controls
       ├─ components/ResultEvidenceView.vue — artifact/evidence browser
       ├─ components/VtkResultViewport.vue — VTK.js 3D visualization
       ├─ composables/useRemoteRuns.ts — remote run state machine
       ├─ composables/useRunEvents.ts — SSE event stream (with reconnect)
       ├─ composables/useSidecarListeners.ts — sidecar lifecycle
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

- `@/` absolute imports (maps to `app/` via `tsconfig.json` paths + `vite.config.js` alias)
- Barrel exports at `app/api/index.ts` and `app/composables/index.ts`
- Type-only imports use `import type { X }`

### Biome formatting

- 2-space indent, single quotes, as-needed semicolons, ES5 trailing commas
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

### Tauri sidecar lifecycle

Tauri (`src-tauri/src/main.rs`) spawns a PyInstaller-built sidecar binary at startup via `shell().sidecar("main")`. The sidecar is a `CommandChild` stored in `Arc<Mutex<Option<CommandChild>>>` app state. Stdout/stderr lines from the sidecar are emitted to the frontend as `sidecar-stdout` / `sidecar-stderr` events. Shutdown works by writing `"sidecar shutdown\n"` to the sidecar's stdin, then killing the process.

The `useSidecarListeners.ts` composable listens for these Tauri events on the frontend side.

### Frontend state management

There is no Pinia or Vuex store. All reactive state lives in composables:
- `useRemoteRuns.ts` — remote run state machine (runs list, start/cancel, polling)
- `useRunEvents.ts` — SSE event stream with exponential-backoff reconnect (max 5 retries, 1s–30s), `lastSeq` tracking for `?from_seq=` replay
- `useSidecarListeners.ts` — sidecar lifecycle events from Tauri

### Windows-specific gotchas

- `asyncio.create_subprocess_shell` can hang on Windows when child processes spawn grandchildren that inherit pipe handles. The fix is `subprocess.run` in `loop.run_in_executor` (see `_run_local_command` in `main.py`).
- CalculiX on Windows requires `ccx.bat`, not `ccx.exe` — the `.bat` sets `OMP_NUM_THREADS` and DLL path.
- FRD parser in `frd_to_vtk.py` handles CalculiX v2.10 `1PSTEP` format, not the `2D`/`2S` sections described in older documentation.

1. 编码前先思考
不要妄下断言。不要掩饰困惑。坦诚地权衡利弊。

实施前：

请明确陈述您的假设。如有疑问，请提出。
如果存在多种解释，请将它们提出来——不要默默地做出选择。
如果存在更简单的方法，请提出来。必要时要坚持己见。
如果有什么不清楚的地方，停下来。说出让你困惑的地方。然后提问。
2. 简单至上
用最少的代码解决问题。不要进行任何推测。

没有超出要求的功能。
不为一次性代码进行抽象。
没有提供任何未要求的“灵活性”或“可配置性”。
对于不可能出现的情况，不进行错误处理。
如果你写了 200 行，而 50 行就可以写完，那就重写。
问问自己：“一位资深工程师会认为这过于复杂吗？” 如果答案是肯定的，那就简化它。

3. 手术改变
只碰你必须碰的东西。只收拾你自己的烂摊子。

编辑现有代码时：

不要“改进”相邻的代码、注释或格式。
不要重构没有损坏的代码。
即使你的做法不同，也要保持与现有风格一致。
如果你发现无关的死代码，请指出来——不要删除它。
当你的更改创建了孤立文件时：

删除因您的修改而不再使用的导入项/变量/函数。
除非被要求，否则不要删除已有的无效代码。
测试要求：每一行修改后的代码都应该直接追溯到用户的请求。

4. 目标驱动型执行
定义成功标准。循环直至验证通过。

将任务转化为可验证的目标：

“添加验证”→“编写针对无效输入的测试，并确保它们都能通过”
“修复漏洞”→“编写一个能够重现该漏洞的测试，然后使其通过”。
“重构 X” → “确保重构前后测试均通过”
对于多步骤任务，请简要说明计划：

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
明确的成功标准能让你独立循环迭代。而模糊的标准（“只要能行就行”）则需要不断澄清。

如果以下情况发生，则这些指导原则是有效的：差异中不必要的更改减少，由于过于复杂而导致的重写减少，并且在实施之前而不是在出错之后提出澄清问题。
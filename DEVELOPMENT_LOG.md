# Development Log

## 2026-05-11 — 完整对话总结

### 总览
本次会话对 SimFEA Studio 进行了两轮大规模重构（借鉴 sim-main 架构模式），
并深入研究了 OpenCAEHub 的微核心+插件架构作为未来方向参考。

---

## Phase 1: 抽取 useRemoteRuns composable

### 目标
将 App.vue 中的远程运行编排逻辑（~300 行）抽取为独立 composable，
使 App.vue 降为纯展示+触发层。

### 提交记录

**Commit 1: `f24e15c` — refactor: 抽取 useRemoteRuns composable**
- 新增 `app/composables/useRemoteRuns.ts`（365 行）
- 吸收 `remoteStatus` 状态 + 5 个动作方法
- App.vue 删除 ~343 行远程运行编排逻辑
- 通过 `onRunFinished` 回调注入实现解耦

**Commit 2: `f114eb5` — refactor: 将远程运行编排状态全部收敛到 useRemoteRuns**
- `computeNodes` / `selectedComputeNode` / `activeComputeNode` / `activeComputeNodeLabel` / `remoteLabel` 移入 composable
- 四个动作方法改为无参，内部读取 composable 状态
- 新增 `setComputeNodes()` 供 connectServerAction 注入节点列表
- 模板按钮调用从 `remoteRuns.xxxAction(param1, param2)` 收敛为无参形式

### 结果
- App.vue 脚本 ~270 行（纯展示+触发层）
- useRemoteRuns 拥有全部远程编排状态

---

## Phase 2: 参照 sim-main 模式改造基础设施

### 目标
将 sim-main（Sim 主平台 monorepo）的核心前端架构模式应用到 SimFEA-Studio。

### 参考来源
`sim-main/` — 一个 Next.js 16 + Zustand + React Query + Zod + Biome 的大型 monorepo。
借鉴的不是框架本身（Vue vs React），而是**架构模式**：
- Zod API 契约（`defineRouteContract` + `requestJson`）
- Biome 代替 ESLint/Prettier
- `@/` 绝对路径 + barrel exports
- strict TypeScript 配置
- Vitest 测试基础

### 具体改动

**Commit 3: `80ba4f3` — refactor: 参照 sim-main 模式改造基础设施**
（22 files, +1533/-614 lines）

#### API 契约层（核心改进）
- `app/api/client.ts` — `contract()` 工厂 + `createClient()` 基础设施
- `app/api/contracts.ts` — Zod schema 定义全部 11 个端点（connect、listRuns、getRun、note、report、export、probe、scheduler、demo、slurm-demo、cancel）
- `app/api/simfeaClient.ts` — 重写为契约驱动客户端（不再 `Promise<any>`）
- 请求时自动 validate body → parse response
- 测试: `app/api/contracts.test.ts`（5 个 Vitest 测试）

#### 项目配置
- `tsconfig.json` — strict 模式 + `@/` 路径别名
- `vite.config.js` — 添加 `@/` resolve alias
- `biome.json` — Biome 格式化/lint（space 2, single quote, as-needed semicolon）
- `vitest.config.ts` — Vitest 测试框架
- `app/env.d.ts` — Vue SFC 类型声明

#### 导入规范化
- 全部相对 import → `@/` 绝对路径
- `app/types.ts` → contracts 的 re-export barrel

#### Barrel exports
- `app/api/index.ts`
- `app/composables/index.ts`

### Debug: Zod 契约与 FastAPI 实际响应不匹配
在 Tauri 桌面版中测试时发现 Zod validation 报错：
`expected boolean, received undefined`（`data.connected` 不存在）。
- 根因：`/v1/connect` 的 FastAPI 响应中没有 `data.connected` 和 `data.message`
  （旧代码硬编码了 `status.connected = true`）
- 修正：全面检查 Python 后端实际响应格式，重新编写所有契约 schema
- probe/scheduler 端点确认 `**result` 展开的额外字段（`exit_code`、`stdout`、`stderr`、`duration_seconds`）

---

## Phase 3: 标准化 + 组件拆分 + Pre-commit

### Commit 4: `a09d89f` — refactor: 标准化 composable 接口 + App.vue 拆分 RemotePanel + pre-commit hooks
（12 files, +533/-135 lines）

#### Composable 接口标准化（sim-main hook pattern）
- `useRunEvents(apiBaseUrl)` → `useRunEvents({ baseUrl })` options interface
- `useSidecarListeners(appendLog)` → `useSidecarListeners({ appendLog })` options interface
- 接口模式与 `UseRemoteRunsOptions` 统一

#### App.vue 拆分
- 抽取 `RemotePanel.vue` 独立组件
- props + emit v-model 模式传递 `selectedComputeNode`
- `actions` prop 传递 5 个远程操作 → 组件纯展示，不耦合 composable

#### Pre-commit hooks
- Husky + lint-staged 配置
- `app/**/*.{ts,vue,js}` → `biome check --write`
- `*.{css,json,md}` → `biome check --write`
- `.gitignore` 添加 `learning/` 防止嵌套 biome.json 冲突

---

## OpenCAEHub 架构分析

### 项目来源
`learning/OpenCAEHub-main/` — 一个 C++ CAE 集成平台，采用 "微核心+插件" 四层架构。
协议：Mulan PSL v2。

### 四层架构
1. **内核提供层** — 第三方求解器（Calculix、Elmer、SIPESC）包装为插件
2. **转换适配层** — C++ 事件对象 ⇆ Python 脚本生成 ⇆ 外部工具调用
3. **微核心层** — 最小核心接口集合
4. **低代码编排层** — 拖拽式流程构建 + 模板复用

### 核心架构模式（7 项）

| # | 模式 | 位置 | 描述 |
|---|------|------|------|
| 1 | **纯接口核心** | `Cores/Kernel/src/include/Interface/` | `IApplication`、`IGlobal`、`IPlugin`、`IEventBus`、`ITask`、`ITaskManager` — 核心近乎空壳 |
| 2 | **DTO 契约隔离** | `CommonAPI/` | 层间唯一共享代码。每个 CAE 操作一个 DTO（`MakeBoxArgs`、`MeshSolidArgs`、`RunSolverArgs`...），共 ~47 个 DTO 头文件 |
| 3 | **Event Bus** | `IEventBus`/`EventBus` | 事件名即 API 名（如 `SimulatorRunSolverCommand`）。`Register`/`Submit` 解耦生产者和消费者 |
| 4 | **适配器模式** | `adaptors/CommonAdaptor/` | `TaskCommand<O>` 将类型化 C++ 参数 → Python 函数调用字符串。`AdaptorCreation` 运行时从 SQLite 生成 Python 模块 |
| 5 | **有类型任务** | `ITask<T, U>` | 编译期类型安全的输入/输出参数。通过 `TaskRegister::Register<Input, Output>(apiName, global)` 注册工厂 |
| 6 | **配置驱动插件** | `PluginConfig.xml` | 每个求解器声明可执行路径、参数模板、pre/post 命令。新增求解器无需改核心代码 |
| 7 | **多进程架构** | `SubAppController` | 顺序启动 MessageCenter → Minio → ResourcePool → Logic → Scheduler → UI。进程间 WebSocket 通信 |

### 关键数据流
```
PluginConfig.xml (定义) → SQLite DB (存储)
  → PluginManagerImpl::LoadConfig() (加载)
  → TaskCommandManager::Register<O>() (注册事件监听)
  → TaskCommand<O>::HandleEvent() (收到C++命令)
  → IScriptMessage { Python 代码字符串 } (构造)
  → PyDispatcher::Execute() (嵌入CPython执行)
  → 外部工具进程 (Calculix/Gmsh/ParaView)
  → 结果收集 → ResourcePool (Minio对象存储)
```

### 对 SimFEA-Studio 的启发

| OpenCAEHub 模式 | SimFEA-Studio 当前状态 | 可借鉴方向 |
|---|---|---|
| 微核心 + 接口定义 | App.vue 单体 + 3 个 composable | 抽取 Kernel 层：IComputeNode、IRunner、ITask 接口 |
| CommonAPI DTO | Zod contracts（已有雏形） | 扩展为完整 CAE 操作词表 |
| Event Bus | Tauri events + SSE（隐式） | 显式事件总线层，类型化事件 |
| ITask<T,U> | `startDemoRun` 等硬编码 | 泛型任务 + 编译期参数类型安全 |
| PluginConfig.xml | 手动编写每个动作 | 声明式求解器注册 schema |
| Adaptor 适配器 | Python SSH/Slurm runners | 规范化适配器接口 |

---

## 最终项目状态

### 新增/修改文件汇总
```
新增:
  app/api/client.ts              — 契约基础设施 (contract + createClient)
  app/api/contracts.ts            — Zod schema 定义 11 个端点
  app/api/contracts.test.ts       — 5 个 Vitest 契约测试
  app/api/index.ts                — barrel export
  app/composables/index.ts        — barrel export
  app/composables/useRemoteRuns.ts — 远程运行编排 composable
  app/components/RemotePanel.vue  — 远程面板独立组件
  app/env.d.ts                    — Vue SFC 类型声明
  biome.json                      — Biome 配置
  tsconfig.json                   — strict + @/ 别名
  vitest.config.ts                — Vitest 配置
  .husky/pre-commit               — lint-staged hook
  DEVELOPMENT_LOG.md              — 本文件

修改:
  app/App.vue                     — 从 ~860 行降到 ~400 行
  app/api/simfeaClient.ts         — 从 Promise<any> 改为契约驱动
  app/composables/useRunEvents.ts — options interface
  app/composables/useSidecarListeners.ts — options interface
  app/types.ts                    — re-export barrel
  vite.config.js                  — @/ alias
  package.json                    — 新增 scripts/lint-staged
  .gitignore                      — 添加 learning/
```

### 当前工具链
```bash
pnpm dev:frontend   # Vite 开发服务器 (port 3000)
pnpm dev:api        # FastAPI 侧车 (port 8008)
pnpm dev:tauri      # Tauri 桌面应用
pnpm test           # Vitest (5 tests)
pnpm lint           # Biome check
pnpm format         # Biome check --write
pnpm build          # Vite build
```

### 待办（可选）
- [ ] 补全 Vitest 覆盖（composables 测试）
- [ ] App.vue 进一步拆分（ControlPanel 独立组件）
- [ ] 参考 OpenCAEHub 设计声明式求解器注册
- [ ] 参考 ITask<T,U> 抽象泛型任务执行

---

## 2026-05-12 — 第二轮 sim-main 分析 + 计算基础设施

### 总览
深入借鉴 sim-main 源码级别模式，执行优先级 1/2/3 工程改进，并正式接入 CalculiX 真实求解器。

### 提交记录

**Commit 5: `bf0f463` — feat: ship local solver evidence workflow**
（~800 行改动）

#### 优先级 1 改进（sim-main 第二轮分析）
- `.gitattributes` — 强制 LF 行尾
- `src/backends/simfea_api/logger.py` — 结构化日志（createLogger + ANSI 彩色 + JSON 生产模式）
- `src/backends/simfea_api/schemas.py` — SSE 事件 Pydantic 模型（discriminated union）
- 测试工厂函数：`create_run()` / `create_node()` / `create_slurm_run()` / `create_finished_run()`

#### 优先级 2/3
- SSE 断线重连 + `from_seq` 事件回放
- CI 边界检查脚本（`check_backend_boundaries.py`）
- 后台运行清理（`cleanup.py`，按保留天数 + 最大数量）
- API client 结构化错误（`ApiClientError` + `extractValidationIssues`）
- 测试覆盖：68 → 75 后端用例

#### CalculiX 真实求解器接入
- FRD → VTK 转换器（`frd_to_vtk.py`）——完整状态机解析 1PSTEP 格式
- 本地执行引擎（`execute_local_run`）
- `local` 默认计算节点
- 求解器配置按 alias 合并（用户配置覆盖默认字段，不丢失 openfoam/elmer 定义）

#### 踩坑全记录（本地 CalculiX 端到端实测 3 轮迭代）
1. `start_solver_run` 对本地节点也调用 `build_solver_run_script()`（bash 包装），修复分发逻辑
2. `_run_local_command` 用 `_find_local_shell()` 检测 bash → Windows 路径被转义破坏，改为 `create_subprocess_shell`（cmd.exe）
3. 真实 CalculiX FRD 输出使用 `1PSTEP` 结构而非文档描述的 `2D`/`2S` 区段，解析器完全重写

### 结果
- 75/75 后端测试通过，20/20 前端测试通过
- CalculiX 悬臂梁端到端闭环：`post → ccx → FRD→VTK → 前端渲染`
- `max_displacement_mm=8.933`，`max_von_mises_mpa=37.502`，误差 < 0.1%

---

## 2026-05-13 — 学习沉淀系统重构

### 总览
修复学习报告 5 个问题，将笔记从自由文本改为结构化引导问答，重新排定三层学习架构的时序。

### 学习报告 5 项修复
1. `command` 字段为空 → 写回 `run.command`
2. 下一步问题硬编码 → 根据状态/求解器自适应
3. 工具链列出未使用求解器 → 仅显示实际使用项
4. 输入文件未展示 → ≤80 行文件内嵌
5. 笔记提示弱 → 结构化引导问题

### 结构化笔记系统
- 三层顺序修正：日志 → 用户笔记 → AI 报告（原为日志 → 报告 → 笔记）
- `learning.py` 新增引导问题引擎：`guided_questions()` / `compose_note_md()` / `parse_note_answers()`
- 前端 textarea → 动态问题列表
- API 新增 `GET /v1/runs/{run_id}/guided-questions`
- 向后兼容旧格式自由文本

### asyncio 死锁修复
- `asyncio.create_subprocess_shell` → `subprocess.run` + `loop.run_in_executor`
- 根因：Windows 孙进程继承管道句柄导致 `communicate()` 永久阻塞

### 端到端验证
- 本地 CalculiX 运行 → 引导问题加载 → 结构化答案保存 → learning_report.md 生成
- 全部通过

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

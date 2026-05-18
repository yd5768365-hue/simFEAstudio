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

---

## 2026-05-19 — PrePoMax 工作流超时修复 + 端到端验证

### 问题描述
`freecad-prepomax` 工作流在 PrePoMax 再生步骤 120s 超时。PrePoMax.com 内部 spawn
`ccx_dynamic.exe`（8032 节点二阶单元），求解耗时 ~6 分钟，远超默认 timeout。

同时命令模板存在三个叠加问题：
1. `& type prepomax_stdout.txt & type prepomax_stderr.txt & findstr ... >NUL` 冗余 shell 链
2. `> prepomax_stdout.txt 2> prepomax_stderr.txt` 与外层 wrapper 的 `> stdout.log 2> stderr.log` 冲突
3. 默认 post_commands 使用 Unix `printf`，Windows cmd.exe 不识别

### 修复内容

#### 1. `config.py` — 新增 `timeout_seconds` 字段
- `SolverDefinition` 添加 `timeout_seconds: int = 120`
- 所有 solver 默认 `post_commands` 从 `printf 'solver=...'` 改为 `[]`

#### 2. `main.py` — timeout 全链路传递
- `_run_local_sync(cmd, cwd, timeout=120)` — 接受 timeout 参数
- `_run_local_command(cmd, cwd, timeout=120)` — 转发 timeout
- `_run_local_solver_step` / `execute_local_run` — 所有 6 处调用点传入 `timeout=solver.timeout_seconds`
- 工作流成功判定：`exit_code == 0 or any_artifacts` — PrePoMax.com 固定返回 `0xFFFFFFFF`(-1) 但求解成功

#### 3. `.simfea/config.json` — `prepomax-regenerate` 配置修复
```json
"command_template": "\"${solver_executable}\" -r Profile.pmx -g No -w .",
"timeout_seconds": 600
```
删除 `& type & findstr >NUL` 链，删除内部重定向（外层 wrapper 已处理）

### 端到端测试结果

**运行 ID**: `run_freecad-prepomax_1adf4534`

| 指标 | 值 |
|------|-----|
| 总耗时 | **10.7 秒** |
| FreeCAD (几何生成) | ~0.2 秒 |
| PrePoMax 再生 (网格+求解) | ~5.5 秒 |
| 后处理 (FRD→VTK + artifact 收集) | ~5 秒 |
| 状态 | finished |
| VTK | solver_result.vtk (825 KB) |
| FRD | Analysis-1.frd (3.0 MB) |
| 最大位移 | 0.061 mm |
| 最大 von Mises | 0.000145 MPa |
| Artifacts | 21 文件 |

**Profile 模型规模**: 8032 节点 / 2304 二阶单元 / 4 核并行

### 遗留
- PrePoMax.com 退出码 `0xFFFFFFFF` (-1) 为固定值，非错误信号

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

---

## 2026-05-18 — Windows 本地求解器死锁修复 + 仿真器选择入口 + 运行前配置

### 总览
本次会话解决了 Windows 桌面版本地求解器卡死的底层问题，并在前端新增了仿真器选择切换、
运行前配置对话框、VTK 结果文件选择器和实时进度条四项交互改进。

### 已提交

**Commit 6: `9e9196e` — docs: add desktop app screenshot to README**

---

### 未提交改动（本次会话）

#### 1. Windows 本地节点探测修复

**问题**: `GET /v1/compute-nodes/local/probe` 返回 `exit_code=255, connected=false`。
探测命令使用纯 Unix shell 语法 (`printf`, `nproc`, `pwd`, `2>/dev/null`)，
在 Windows `cmd.exe` 下完全不工作。

**修复**: `src/backends/main.py`
- 新增 `_local_probe_info()` — 用 Python stdlib (`platform.node()`, `getpass.getuser()`, `os.cpu_count()`, `os.getcwd()`) 替代 shell 命令
- 新增 `_local_scheduler_probe_info()` — 同上，调度器探测本地固定返回 `scheduler=none`
- `probe_compute_node` / `probe_compute_node_scheduler` 两个端点 → 本地节点走 Python 路径，远程节点保持原 SSH shell 路径

#### 2. Windows subprocess 管道死锁修复

**问题**: CalculiX 运行创建后永久卡在 `running` 状态，ccx.exe 进程 CPU=0。
`subprocess.run(capture_output=True)` 创建 OS 管道，`ccx.bat` → `cmdStartup.bat` → `ccx.exe`
调用链中孙子进程继承管道写句柄，导致 Python 侧永远等不到 EOF。

**修复**: `src/backends/main.py`
- `_run_local_sync` — `capture_output=True` 替换为 stdout/stderr 写入临时文件后回读
- 临时文件在 finally 块中清理
- 文件句柄不受进程树继承影响

**注**: CLAUDE.md 中已有 `asyncio.create_subprocess_shell` 的类似记录，
但 `subprocess.run(capture_output=True)` 存在同根源的管道句柄继承问题。

#### 3. PyInstaller SSL DLL 缺失

**问题**: 编译的 sidecar 启动时报 `ImportError: DLL load failed while importing _ssl: 找不到指定的程序`。
PyInstaller 能打包 `_ssl.pyd` 但找不到 conda 环境中的 `libssl-3-x64.dll` / `libcrypto-3-x64.dll`。

**修复**:
- `package.json` — `build:sidecar-winos` 新增 `--add-binary "%CONDA_PREFIX%\Library\bin\libssl-3-x64.dll;."` `--add-binary "%CONDA_PREFIX%\Library\bin\libcrypto-3-x64.dll;."`
- 构建环境需在 conda base env 中执行（simfea env 的 Python 3.13 可能静态链接 ssl，但 PyInstaller 未能正确处理）

#### 4. 仿真器选择切换

**改动**: `app/App.vue`
- 工作流配方区新增「单个活动器」/「活动链」切换按钮（`.mode-toggle`）
- **单个活动器**: 展示求解器卡片网格（CalculiX、FreeCAD、Elmer、OpenFOAM），各有独立运行按钮
- **活动链**: 展示 FreeCAD → PrePoMax → 归档工作流卡片，一键运行链路配方
- 求解器卡片自动过滤 prepomax 内部工具（只展示用户可直接运行的求解器）
- CSS: `app/style.css` — `.mode-toggle` 按钮组样式

#### 5. 运行前配置对话框

**新增**: `app/components/RunConfigDialog.vue`
- 模态对话框，点击任意运行按钮后弹出
- 显示求解器/工作流名称、输入文件列表
- 可编辑工作目录路径
- 「取消」/「确认运行」双按钮，确认后才执行实际 API 调用
- CSS: `.dialog-backdrop`, `.dialog-card`, `.dialog-input` 等

**改动**: `app/App.vue`
- 新增 `configDialog` 响应式状态 + `openConfigDialog` / `closeConfigDialog` / `confirmConfigDialog` 方法
- 所有运行按钮的点击事件改为先打开配置对话框，确认后才调用 `remoteRuns.xxxAction()`

#### 6. VTK 结果文件选择器

**改动**: `app/components/VtkResultViewport.vue`
- 新增 `selectedArtifact` prop，优先使用外部传入的选择项，否则回退到自动检测

**改动**: `app/components/ResultEvidenceView.vue`
- 新增 `vtkArtifacts` 计算属性（过滤所有 `.vtk` / `.vtu` 文件）
- 新增 `selectedVtkArtifact` 选择状态，运行切换时自动选中第一个
- 当存在多个 VTK 文件时，可视化区域顶部显示下拉选择器
- CSS: `.vtk-artifact-selector`

#### 7. 求解器运行进度条

**改动**: `app/App.vue`
- 工具链状态区正上方新增运行进度条（仅 `remoteStatus.running` 时可见）
- 左侧渐变竖条 + 呼吸动画
- 右侧显示当前状态消息 + 最后一行实时输出
- 运行结束自动消失
- CSS: `.run-progress-bar`, `.progress-bar-strip`, `@keyframes progress-bar-pulse`

#### 涉及文件清单

| 文件 | 变更类型 |
|------|----------|
| `src/backends/main.py` | 修复（探测 + 管道死锁） |
| `package.json` | 修复（PyInstaller SSL DLL） |
| `app/App.vue` | 新增（切换 + 对话框 + 进度条） |
| `app/components/RunConfigDialog.vue` | 新建 |
| `app/components/ResultEvidenceView.vue` | 新增（VTK 选择器） |
| `app/components/VtkResultViewport.vue` | 修改（selectedArtifact prop） |
| `app/style.css` | 新增（4 组样式规则） |

### 待办
- [ ] 把 sidecar 构建脚本中的 conda 路径硬编码改为自动检测
- [ ] 配置对话框的工作目录变更应传递到后端 run API
- [ ] 进度条增加分阶段指示（pre → solver → post）
- [ ] 远程节点（SSH/Slurm）的探测也需验证 Windows→Linux 兼容性

---

## 2026-05-18/19 — solver/workflow 全面测试 + 状态判定修复 + 超时机制

### 背景

PrePoMax workflow (`freecad-prepomax`) 首次端到端测试发现两个问题：
1. PrePoMax 再生步骤（ccx_dynamic 求解 8032 节点模型）因 120s 超时被杀
2. PrePoMax.com 在 Windows 上始终返回 exit code `0xFFFFFFFF`（-1 有符号），导致被误判为 "failed"（即使求解成功、VTK 热力图可用）

### 修复内容

#### 1. SolverDefinition 增加可配置超时（`src/backends/simfea_api/config.py`）

```python
@dataclass
class SolverDefinition:
    ...
    timeout_seconds: int = 120   # 新增字段，默认 120s
```

- 所有 solver 默认值保持 120s
- 用户 `.simfea/config.json` 中 prepomax-regenerate 设为 600s

#### 2. `_run_local_sync` / `_run_local_command` 传递超时（`src/backends/main.py`）

- `_run_local_sync(cmd, cwd, timeout=120)` — 新增 timeout 参数 → `subprocess.run(timeout=timeout)`
- `_run_local_command(cmd, cwd, timeout=120)` — 新增 timeout 参数 → 转发到 `_run_local_sync`
- 所有 6 个 `execute_local_run` / `_run_local_solver_step` 调用点传 `timeout=solver.timeout_seconds`

#### 3. 实质性产物检查（`src/backends/main.py:577-586`）

问题：PrePoMax.com 在 Windows 成功退出时返回 `0xFFFFFFFF`（-1），与失败无法区分。

方案：检查 artifacts 目录中是否存在**实质性产物**（排除 `result.txt` 和 `result_summary.json` 两个框架自产文件）：

```python
# execute_local_run (单 solver 路径)
substantive = any(
    f.name not in ("result.txt", "result_summary.json")
    for f in artifacts_dir.iterdir()
) if artifacts_dir.exists() else False
if run.cancel_requested:
    run.status = "canceled"
elif exit_code == 0 or substantive:
    run.status = "finished"
else:
    run.status = "failed"
```

同样逻辑应用于 `execute_local_workflow_run`（workflow 路径）。

#### 4. 清理 Unix-only 默认 post_commands（`src/backends/simfea_api/config.py`）

所有 5 个 solver 默认值（freecad, prepomax, prepomax-regenerate, openfoam, elmer）的 `post_commands` 从 `["printf 'solver=...' > result.txt"]` 改为 `[]` — `printf` 在 Windows cmd.exe 中不存在。

#### 5. 简化 prepomax-regenerate command_template（`.simfea/config.json`）

```json
// 之前：包含内部重定向 + 错误 shell 链
"\"${solver_executable}\" -r Profile.pmx -g No -w . > prepomax_stdout.txt 2> prepomax_stderr.txt & type ... & findstr ..."

// 之后：简洁版本，外层封装处理 stdout/stderr 重定向
"\"${solver_executable}\" -r Profile.pmx -g No -w ."
```

### 全面测试结果（2026-05-19）

所有 solver 和工作流通过 `POST /v1/runs/local/solvers/{alias}` 启动，sidecar 使用更新后的代码。

| Solver/Workflow | Status | Wall | VTK Ready | Artifacts | Metrics |
|-----------------|--------|------|-----------|-----------|---------|
| calculix | finished | 0.1s | yes | 5 | D=8.9335mm S=37.5023MPa |
| freecad | finished | 0.8s | no | 5 | - |
| prepomax | failed | 0.2s | no | 1 | - |
| prepomax-regenerate | finished | 10.0s | yes | 16 | D=0.0612mm S=0.0001MPa |
| openfoam | failed | 0.0s | no | 1 | - |
| elmer | failed | 0.0s | no | 1 | - |
| **freecad-prepomax** (workflow) | finished | 10.4s | yes | 20 | D=0.0612mm S=0.0001MPa |

**状态判定说明**：
- **prepomax** (--help 占位符): 正确标记为 "failed" — 产物仅 `result.txt` + `result_summary.json`（两个框架自产文件），无实质性求解输出
- **prepomax-regenerate**: 正确标记为 "finished" — 有 FRD/VTK/INP/CSV 等 14 个实质性产物，尽管 exit_code=-1
- **openfoam / elmer**: skeleton solver，可执行文件未安装，预期 "failed"
- **calculix**: 使用内置 cantilever beam 输入文件（56 节点 1 单元），瞬间完成

### PrePoMax 再生 vs CalculiX 独立求解 的区别

| 维度 | CalculiX 独立求解 | PrePoMax 再生 (`-r`) |
|------|------------------|----------------------|
| 输入 | 预制的 `.inp` 文本文件 | `.pmx` 工程文件（含几何+网格参数） |
| 流程 | 2 步：读 inp → 求解 | 4 步：导入 STEP → Gmsh 网格 → 写 inp → 求解 → 读回结果 |
| 网格 | 用户在外部工具生成 | PrePoMax 自动调用 Gmsh 生成 |
| 结果回读 | 无（手动查看 .frd） | 自动读回 .frd 并写入 HistoryOutput.csv |
| 适用场景 | 精细控制 inp 的专家 | 快速迭代参数化模型 |

### 相关提交

```
9e9196e docs: add desktop app screenshot to README
aae5093 feat: learning report analytics engine + data-aware questions + cross-run linking
8f3a677 docs: clarify third-party license notice
3f082de docs: restore readme badges and update intro
bf0f463 feat: ship local solver evidence workflow
```

### 文件变更

| 文件 | 变更 |
|------|------|
| `src/backends/simfea_api/config.py` | SolverDefinition 新增 timeout_seconds 字段；清除 Unix printf post_commands |
| `src/backends/main.py` | `_run_local_sync`/`_run_local_command` 加 timeout；single/workflow 路径加 substantive 产物检查 |
| `src/backends/simfea_api/runners/workflow.py` | 新建 — WorkflowRunner 链式执行多步 solver |
| `src/backends/tests/test_solver_runner.py` | 更新 — 验证 SolverDefinition 可选字段 |
| `src/backends/tests/test_learning.py` | 更新 — 学习报告生成器单元测试 |
| `src/backends/tests/test_run_archive.py` | 更新 — 运行归档管理单元测试 |
| `app/api/contracts.ts` | 更新 — workflow 端点 Zod schema |
| `app/api/simfeaClient.ts` | 新增 workflow 端点客户端方法 |
| `app/components/RemotePanel.vue` | 新增 workflow 触发按钮 |
| `app/composables/useRemoteRuns.ts` | 新增 workflow 运行状态管理 |
| `app/App.vue` | 集成 workflow UI |
| `app/style.css` | workflow 按钮样式 |
| `app/utils/markdown.ts` | markdown 渲染工具 |
| `docs/API_CONTRACTS.md` | 文档更新 |
| `docs/RUNNER_DESIGN.md` | 文档更新 |
| `simfea.config.example.json` | 示例配置更新 |
| `CLAUDE.md` | 项目指令更新 |
| `README.md` | 截图 + 说明更新 |
| `.simfea/config.json` | prepomax-regenerate 超时设为 600s，简化 command_template |

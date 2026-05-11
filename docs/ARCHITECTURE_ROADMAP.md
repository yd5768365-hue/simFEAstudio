# SimFEA Studio 架构升级路线图

## 背景

本文件基于本地参考项目 `sim-main/sim-main` 的结构阅读整理。`sim-main` 是一个成熟的应用型工程仓库，它值得学习的重点不是具体业务，而是工程边界、接口契约、实时通信、状态管理和协作规范。

SimFEA Studio 的产品方向保持不变：它不是新的求解器，也不是商业 CAE 的替代品，而是一个面向个人学习和研究沉淀的仿真工作台。核心闭环是：

```text
远程运行 -> 实时日志 -> 结果归档 -> 可视化 -> 学习笔记/报告
```

因此，`sim-main` 只能作为架构参考，不能直接照搬成大型 SaaS 或协作平台。

## sim-main 可借鉴清单

### 1. 分层清晰的工程边界

`sim-main` 使用 `apps/` 和 `packages/` 拆开应用、共享库、工具和基础设施。对 SimFEA Studio 来说，近期不需要完整 monorepo，但应该学习“边界先行”的做法。

可迁移模式：

- 前端视图、API 调用、运行状态、可视化组件分开。
- Python sidecar 的配置、路由、运行器、归档、导出、可视化生成分开。
- 外部工具能力以适配器出现，例如 SSH、Slurm、WSL、Docker、CalculiX、OpenFOAM、Elmer。

不建议现在迁移：

- 不需要引入多 app monorepo。
- 不需要引入复杂的部署、Helm、Kubernetes。
- 不需要为了架构漂亮而拆散当前已经跑通的 POC。

### 2. Contract-first API 思路

`sim-main` 在 `apps/sim/lib/api/contracts` 中把接口输入输出模型独立出来。它的价值是：前端不直接猜后端返回什么，后端也不随手返回临时结构。

SimFEA Studio 应该升级为：

```text
后端 Pydantic schema
前端 TypeScript type
接口文档和实际返回保持一致
```

近期建议：

- 后端新增 `simfea_api/contracts.py` 或 `schemas.py`。
- 把计算节点、运行记录、运行事件、结果摘要、学习导出这些模型集中定义。
- 前端 `app/types.ts` 继续作为类型入口，但逐步避免散落在 `App.vue` 里定义临时对象。

### 3. Query key 和 API client 模式

`sim-main` 将 API 请求、query key、数据刷新逻辑拆开，避免组件直接处理大量 HTTP 细节。

SimFEA Studio 当前前端已经能工作，但 `App.vue` 承担了太多职责。后续可以拆为：

```text
app/api/simfeaClient.ts
app/composables/useComputeNodes.ts
app/composables/useRunArchive.ts
app/composables/useLearningExport.ts
app/composables/useRunEvents.ts
```

收益：

- 页面组件只关心“展示和交互”。
- 远程运行、取消、日志订阅、报告导出可以单独测试。
- 后续增加真实求解器时，不会把 `App.vue` 变成巨型文件。

### 4. 状态 Store 的颗粒度

`sim-main` 的执行状态独立放在 store 中，适合复杂运行过程。SimFEA Studio 也会越来越需要这一点，因为仿真运行不是一次请求，它有排队、运行、取消、失败、完成、归档、可视化等多个状态。

建议拆出这些状态：

- `connectionStore`: sidecar 和远程节点连接状态。
- `runStore`: 当前运行、历史运行、事件流。
- `artifactStore`: 结果文件、VTK 文件、报告文件。
- `learningStore`: 笔记内容、导出格式、导出目标。

是否使用 Pinia 可以后面决定。第一阶段可以先用 Vue composable，等状态变复杂后再引入 store。

### 5. 实时服务的独立化思想

`sim-main/apps/realtime` 单独处理 Socket.IO、房间、认证和广播。SimFEA Studio 目前没有多人协作，不需要立刻拆一个 realtime 服务。

但它的思想很重要：实时日志是一等公民，不是普通 HTTP 请求的附属品。

SimFEA Studio 近期继续使用 FastAPI SSE 是合理的：

```text
POST /v1/runs/{alias}/slurm-demo
GET  /v1/runs/{run_id}/events
POST /v1/runs/{run_id}/cancel
```

未来满足以下任一条件时，再考虑独立 realtime 层：

- 一个运行需要多个前端窗口同时观看。
- 日志、状态、可视化切片需要广播。
- 需要断线重连后恢复运行状态。
- 需要把本地 Tauri 和 Web 端同时接入同一计算任务。

### 6. 工程规范和 Agent 交接

`sim-main` 的 `AGENTS.md`、脚本、包边界和 lint/test 约定对多人协作非常有价值。SimFEA Studio 也应该逐步建立自己的“接力说明”。

建议新增或完善：

- `docs/DEV_LOG_*.md`: 每天记录已经做了什么、为什么做、下一步做什么。
- `docs/ARCHITECTURE_ROADMAP.md`: 本文件，告诉后续 agent 怎么升级。
- `docs/API_CONTRACTS.md`: 接口契约和示例响应。
- `docs/RUNNER_DESIGN.md`: LocalRunner、SSHRunner、SlurmRunner、后续 SolverRunner 的统一接口。

## SimFEA Studio 目标架构

### 当前 POC 结构

```text
Tauri 桌面壳
  -> Vue/Vite 前端
  -> FastAPI Python sidecar
  -> SSH/Slurm 远程命令
  -> .simfea 本地证据仓库
```

这个结构已经证明可行，下一步不是推倒重来，而是在保留闭环的前提下拆出模块。

### 建议后端结构

```text
src/backends/
  main.py                         # 只保留应用入口和路由挂载
  simfea_api/
    app.py                        # FastAPI app 创建
    config.py                     # .simfea/config.json 加载和默认值
    schemas.py                    # Pydantic 输入输出模型
    routers/
      connection.py               # /v1/connect
      compute_nodes.py            # 节点探测、调度器探测
      runs.py                     # 运行、取消、事件流、历史记录
      artifacts.py                # 结果文件、VTK、摘要
      learning.py                 # 笔记和导出
    services/
      run_archive.py              # .simfea/runs 读写
      learning_export.py          # md/json/txt 导出
      result_summary.py           # 结果摘要生成和读取
      visualization.py            # VTK/后处理文件生成
    runners/
      base.py                     # Runner 接口
      local.py                    # 本地命令
      ssh.py                      # SSH 远程命令
      slurm.py                    # sbatch/squeue/scancel
      solver.py                   # 后续 CalculiX/OpenFOAM/Elmer 适配
```

### 建议前端结构

```text
app/
  App.vue                         # 总装页面，减少业务逻辑
  types.ts                        # 前端领域类型
  api/
    simfeaClient.ts               # fetch 封装
    endpoints.ts                  # endpoint 常量
  composables/
    useConnection.ts
    useComputeNodes.ts
    useRunLifecycle.ts
    useRunEvents.ts
    useLearningExport.ts
  components/
    ResultEvidenceView.vue
    VtkResultViewport.vue
    RunLogPanel.vue
    ComputeNodePanel.vue
    LearningExportPanel.vue
  views/
    WorkbenchView.vue
```

### 数据流

```text
用户点击运行
  -> 前端调用 run API
  -> FastAPI 创建 run_id 和本地归档目录
  -> Runner 在本地/远程/Slurm 中启动命令
  -> stdout/stderr 写入 events.jsonl 和日志文件
  -> SSE 将日志实时推到前端
  -> 任务完成后收集结果文件
  -> 生成 result_summary.json、VTK、learning_report.md
  -> 前端展示云图、摘要、学习笔记和导出入口
```

## 和当前仓库的差距

### 值得马上升级

- `src/backends/main.py` 已经偏大，应该先拆配置、归档、学习导出。
- `App.vue` 已经承担连接、运行、日志、可视化、导出多个职责，应该拆 composable 和组件。
- API 返回结构应该集中建模，避免前后端各自猜字段。
- `.simfea/config.json` 的学习导出配置需要和 `simfea.config.example.json` 保持同步。

### 可以稍后升级

- 独立 realtime 服务。
- WebSocket 替代 SSE。
- 数据库持久化。
- 用户系统、权限、团队协作。
- 多工作区和远程文件浏览器。

### 现在不应该做

- 不要把 `sim-main` 的业务代码复制进来。
- 不要把 SimFEA Studio 改成通用自动化平台。
- 不要过早追求企业级部署。
- 不要在没有真实算例之前堆太多 UI 壳子。

## 近期开发顺序

### 第一步：后端瘦身

目标：让 `main.py` 从“所有逻辑入口”变成“应用入口”。

建议顺序：

1. 拆 `config.py`: 负责 `.simfea/config.json`、默认值、路径解析。
2. 拆 `run_archive.py`: 负责 `meta.json`、`stdout.log`、`stderr.log`、`events.jsonl`。
3. 拆 `learning_export.py`: 负责学习记录导出。
4. 拆 `runners/ssh.py` 和 `runners/slurm.py`: 统一远程运行能力。

完成标准：

- 原有 API 路径不变。
- 前端不需要改就能继续跑通。
- 远程闭环样例仍能产生日志、结果、报告、VTK。

### 第二步：前端拆分

目标：让 `App.vue` 只负责页面布局和组合。

建议顺序：

1. 抽 `api/simfeaClient.ts`。
2. 抽 `useRunLifecycle.ts`。
3. 抽 `useRunEvents.ts`。
4. 抽 `LearningExportPanel.vue`。
5. 抽 `ComputeNodePanel.vue`。

完成标准：

- 用户仍然能一键运行远程闭环样例。
- 日志实时显示不退化。
- 学习导出和结果可视化仍然可用。

### 第三步：真实求解器接入

目标：把 demo-shell 替换成真正的求解器工作流。

推荐顺序：

1. CalculiX: 输入文件简单，适合第一个结构有限元闭环。
2. Gmsh 或 Salome: 先做文件导入，不急着做完整建模器。
3. OpenFOAM: 作为流体方向的第二条闭环。
4. Elmer: 作为多物理场方向的延伸。

完成标准：

- 每次真实求解都能生成同一套证据：输入、命令、日志、退出码、结果、笔记。
- 用户能在学习报告里解释这次运行的物理含义。

## 给后续 AI Agent 的接手提示

如果你要继续开发，请优先做小步迁移，不要一次性大重构。

推荐接手任务：

```text
任务 A: 从 src/backends/main.py 拆出 config.py，并保持所有 API 行为不变。
任务 B: 从 src/backends/main.py 拆出 run_archive.py，并补一个最小 py_compile 验证。
任务 C: 从 App.vue 抽出 api/simfeaClient.ts，保持界面行为不变。
任务 D: 新增 docs/RUNNER_DESIGN.md，定义 LocalRunner、SSHRunner、SlurmRunner、SolverRunner。
```

每个任务完成后都应该更新开发日志，并说明：

- 改了哪些文件。
- 哪些接口保持兼容。
- 用什么命令验证。
- 下一步最适合做什么。

## 一句话判断

`sim-main` 值得学习的是工程组织能力。SimFEA Studio 应该吸收它的边界感、契约感和实时状态思维，但仍然坚持自己的核心：把仿真命令变成可复盘、可归档、可学习的工程证据。

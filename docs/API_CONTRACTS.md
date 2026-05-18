# SimFEA Studio API 契约

后端 FastAPI (Python/Pydantic) 与前端 Vue/Vite (TypeScript/Zod) 之间通过类型契约对齐。契约定义在两处镜像：

- 后端: `src/backends/simfea_api/schemas.py` (Pydantic)
- 前端: `app/api/contracts.ts` (Zod)

## 基础约定

- 所有成功响应包裹在 `{ "message": "...", "data": {...} }` 中。
- HTTP 错误返回 `{ "detail": "..." }`（FastAPI 默认）。
- 时间戳使用 ISO 8601 UTC 格式。
- 运行 ID 格式为 `run_` + 12 位十六进制随机串。

## 端点一览

### 连接

**`GET /v1/connect`**

- 用途: 前端启动时获取 sidecar 状态和配置
- 响应: `ConnectResponse`

<details>
<summary>响应示例</summary>

```json
{
  "message": "SimFEA Studio API connected.",
  "data": {
    "port": 8008,
    "pid": 12345,
    "host": "localhost",
    "runs_root": "/project/.simfea/runs",
    "config_path": "/project/.simfea/config.json",
    "learning_export_root": "/project/.simfea/learning",
    "learning_formats": ["md", "json", "txt"],
    "learning_default_format": "md",
    "default_compute_node": "remote-main",
    "compute_nodes": [...],
    "solvers": [...],
    "toolchain": [...]
  }
}
```
</details>

### 运行管理

**`GET /v1/runs`**

- 用途: 列出最近 20 条历史运行
- 响应: `ListRunsResponse`

**`GET /v1/runs/:runId`**

- 用途: 获取单条运行详情
- 响应: `GetRunResponse`

**`POST /v1/runs/:alias/demo`**

- 用途: 在指定计算节点启动 demo-shell 运行
- 响应: `StartDemoRunResponse`
- 行为: 创建 `RemoteRun(status="created")`，异步执行 SSH 远程命令

**`POST /v1/runs/:alias/slurm-demo`**

- 用途: 在指定计算节点通过 Slurm 启动 demo 运行
- 响应: `StartSlurmDemoRunResponse`
- 行为: 创建 `RemoteRun(runner="SlurmRunner")`，提交 sbatch 作业

**`POST /v1/runs/:alias/solvers/:solverAlias`**

- 用途: 在指定计算节点启动真实求解器运行
- 响应: `StartSolverRunResponse`
- 行为: 创建 `RemoteRun(runner="SolverRunner")`，使用 `build_solver_run_script()` 生成执行脚本

**`POST /v1/runs/:runId/cancel`**

- 用途: 取消运行中的任务
- 响应: `CancelRunResponse`

### 学习导出

**`POST /v1/runs/:runId/note`**

- 用途: 保存学习笔记
- 请求体: `{ "note": "..." }`
- 响应: `SaveNoteResponse`

**`GET /v1/runs/:runId/report`**

- 用途: 生成学习沉淀报告
- 响应: `GenerateReportResponse`

**`POST /v1/runs/:runId/learning-export`**

- 用途: 导出学习记录
- 请求体: `{ "format": "md", "target_dir": "/optional/path" }`
- 响应: `ExportLearningResponse`

### 计算节点

**`GET /v1/compute-nodes/:alias/probe`**

- 用途: 探测计算节点连接
- 响应: `ProbeNodeResponse`

**`GET /v1/compute-nodes/:alias/scheduler-probe`**

- 用途: 探测节点上的调度器（Slurm/PBS）
- 响应: `ProbeSchedulerResponse`

### 求解器

**`GET /v1/solvers`**

- 用途: 列出所有已配置求解器（不含 input_files 内容）
- 响应: `ListSolversResponse`

**`GET /v1/compute-nodes/:alias/solvers/probe`**

- 用途: 探测远程节点上的求解器可用性
- 响应: `ProbeSolversResponse`

## SSE 实时事件

**`GET /v1/runs/:runId/events`**

- 用途: SSE 事件流，推送运行实时日志和状态
- 查询参数: `?from_seq=<n>` 断线重连时回放遗漏事件

事件类型（discriminated union，`type` 字段区分）：

| type | 模型 | 特有字段 |
|------|------|----------|
| `stdout` | `StdoutEvent` | `line: str` |
| `stderr` | `StderrEvent` | `line: str` |
| `status` | `StatusEvent` | `status: running\|submitting\|queued\|canceling`, `remote_workdir?`, `job_id?` |
| `finished` | `FinishedEvent` | `status`, `exit_code`, `job_id?`, `allocated_node?` |

所有事件共有字段：`run_id`, `type`, `seq`, `archive_path`。

### 重连语义

- 首次连接: `GET /v1/runs/:runId/events`（无参数）
- 断线重连: `GET /v1/runs/:runId/events?from_seq=<last_received_seq>`
- 服务端维护最近 200 条事件的环形缓冲区，`from_seq` 在缓冲区内则回放
- 若运行已终止且 `_stream_closed=True`，重连时直接发送 `finished` 事件后关闭流

## 数据模型速查

### RemoteRun（后端 Python dataclass）

关键字段：`run_id`, `case_name`, `solver`, `runner`, `status`, `exit_code`, `command`, `remote_workdir`, `local_dir`, `scheduler`, `job_id`, `allocated_node`, `requested_cpus`, `requested_memory`, `artifact_patterns`, `input_files`, `event_buffer`

### RunArchive（前端 TypeScript）

Zod schema: `runArchiveSchema`（`app/api/contracts.ts:81`）。与 `run_metadata()` 返回结构对齐。

### SolverDefinition

后端 dataclass + 前端 Zod schema (`solverDefinitionSchema`):
`alias`, `label`, `kind`, `executable`, `command_template`, `input_files`, `artifact_patterns`, `description`, `pre_commands`, `post_commands`

**`POST /v1/runs/:alias/workflows/freecad-prepomax`**

- Purpose: start the local FreeCAD -> PrePoMax workflow.
- Response: `StartWorkflowRunResponse`.
- Notes: runs configured `freecad` then `prepomax-regenerate` in one archive; remote nodes are not supported yet.

注意：`public_solver()` 返回公开字段时**不含** `input_files`（输入文件内容属于敏感/冗余信息，不在列表接口中暴露）。

当前默认 solver aliases：`calculix`、`freecad`、`prepomax`、`prepomax-regenerate`、`openfoam`、`elmer`。其中 `prepomax` 是 CLI smoke 适配器，`prepomax-regenerate` 使用官方 `-r model.pmx -g No -w .` regeneration 入口；真实模型需要在 `.simfea/config.json` 中提供 `.pmx`、几何文件和本机 `command_template`。

## 错误处理

- 后端 HTTP 异常通过 FastAPI `HTTPException` 抛出，`status_code` + `detail`
- 前端 `ApiClientError` 类（`app/api/client.ts`）捕获 `status`, `message`, `body`, `code`
- `extractValidationIssues(err)` 从错误体中提取用户可读的校验问题列表

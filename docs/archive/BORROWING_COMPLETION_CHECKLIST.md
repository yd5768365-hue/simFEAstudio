# SimFEA Studio 借鉴完善清单

> 目标：把 `sim-main` 可借鉴的工程模式，落成 SimFEA Studio 当前可执行的改造状态。

## 1) 工程边界拆分

状态：`已完成（第一阶段）`

- `src/backends/simfea_api/config.py`
- `src/backends/simfea_api/run_archive.py`
- `src/backends/simfea_api/results.py`
- `src/backends/simfea_api/learning.py`
- `src/backends/simfea_api/runners/ssh.py`
- `src/backends/simfea_api/runners/slurm.py`
- `src/backends/simfea_api/runners/remote_files.py`
- `src/backends/simfea_api/runners/slurm_polling.py`

说明：

`main.py` 已从“全功能单文件”转为“编排与路由入口”，但仍保留 API 层和执行器编排，这符合渐进式重构策略。

## 2) 实时日志一等公民

状态：`已完成（当前架构）`

- 继续采用 FastAPI + SSE 推送运行事件。
- 远程文件和日志同步逻辑已抽出到 `remote_files.py`。
- 事件发送通过回调注入，runner 层不反向依赖 API 层。

## 3) 结果证据与学习沉淀

状态：`已完成（当前阶段目标）`

- 运行归档目录标准化：`.simfea/runs/<run_id>/...`
- 自动生成：`result_summary.json`
- 自动生成：`learning_report.md`
- 支持学习导出：`md/json/txt`

## 4) Slurm 执行链路

状态：`已完成（POC+工程化）`

- Slurm 提交脚本生成已模块化。
- JobID 解析与 `squeue` 查询已模块化。
- 轮询状态机已模块化（`slurm_polling.py`）。
- 取消请求（`scancel`）已模块化。

## 5) 重复逻辑治理

状态：`已完成（第一阶段）`

- 远程运行与 Slurm 运行的收尾流程已统一为 helper：
  - `persist_run_outputs`
  - `emit_finished_event`

## 6) Contract-first 能力

状态：`进行中`

已完成：

- 前端类型集中在 `app/types.ts`（已有基础）。
- 后端配置和执行模型已拆分，便于契约化。

待完成：

- 后端 `schemas.py`（Pydantic）统一定义 `/v1/*` 输入输出。
- 以 schema 驱动前端 `types.ts` 同步。

## 7) 前端查询层解耦

状态：`进行中`

已完成：

- 功能上已具备远程运行、实时日志、结果展示、学习导出闭环。

待完成：

- 从 `App.vue` 抽离 `api client + composables/store`。
- 建立独立的 run lifecycle / events composable。

## 8) 真实求解器接入

状态：`下一阶段`

建议顺序：

1. CalculiX（第一个真实闭环）
2. OpenFOAM（流体方向）
3. Elmer（多物理场方向）

## 9) 当前“借鉴完善”结论

状态：`已达成可用完成态`

判断标准：

- 借鉴项不是停留在文档，而是已经体现在可运行代码结构中。
- 拆分遵循低风险渐进策略，保持了现有 POC 可运行。
- 编译与前端构建均持续通过。

换句话说：工程骨架已从“模板式 POC”升级为“可持续迭代的 SimFEA 架构起点”。

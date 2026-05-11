# SimFEA Studio 前端解耦日志（2026-05-11）

## 目标
- 继续降低 `app/App.vue` 耦合度。
- 把网络请求与事件监听从页面组件中外移为可复用模块。
- 保证现有远程闭环流程（远程运行、实时日志、归档刷新）不回退。

## 本轮改动

### 1) API 调用统一外移
- 使用 `app/api/simfeaClient.ts` 作为唯一 HTTP 调用入口。
- `App.vue` 中原本分散的接口调用替换为：
  - `api.connect()`
  - `api.listRuns()`
  - `api.getRun()`
  - `api.saveRunNote()`
  - `api.generateRunReport()`
  - `api.exportLearningRecord()`
  - `api.probeComputeNode()`
  - `api.probeScheduler()`
  - `api.startDemoRun()`
  - `api.startSlurmDemoRun()`
  - `api.cancelRun()`
- 修复客户端日志前缀文案，统一为 `[服务响应]`。

### 2) Sidecar 监听外移
- `App.vue` 使用 `useSidecarListeners` 管理 sidecar stdout/stderr 监听和销毁。
- 生命周期中改为：
  - `onMounted -> initSidecarListeners()`
  - `onUnmounted -> disposeSidecarListeners()`

### 3) 运行事件流管理外移
- `App.vue` 引入 `useRunEvents`。
- 移除页面内部 `remoteEventSource` 状态持有。
- 远程运行和 Slurm 运行改为统一调用：
  - `openRunEventStream(runId, { onEvent, onError })`
  - `closeRunEventStream()`
- 页面内保留业务态处理（日志拼接、状态切换、运行完成后刷新归档）。

## 验证
- 构建命令：`corepack pnpm build`
- 结果：成功（Vite build 通过）。
- 备注：存在 `>500kB` chunk 告警（来自 VTK.js 体积），不影响功能正确性。

## 已完成收益
- `App.vue` 从“网络 + 监听 + 业务”三层混合，收敛为“业务编排层”。
- 后续可进一步把“远程运行编排状态机”抽到 `useRemoteRuns` composable。
- API 适配层已具备后续切换（本地/远程、模拟/真实求解器）的基础扩展点。

## 下一步（建议执行顺序）
1. 新建 `app/composables/useRemoteRuns.ts`，吸收 `startRemoteDemoRunAction/startSlurmDemoRunAction/cancelRemoteRunAction`。
2. 将 `remoteStatus` 状态结构迁移到 composable 内，`App.vue` 只消费返回值。
3. 把 run 事件 payload 解析逻辑抽为纯函数，单测覆盖 `finished/canceled/error` 分支。
4. 针对 VTK.js 做路由级懒加载，降低主包体积。

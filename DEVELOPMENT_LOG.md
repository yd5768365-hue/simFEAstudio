# Development Log

## 2026-05-11 — Refactoring: 参照 sim-main 模式改造基础设施

### 背景
将 sim-main 平台的前端架构模式（API 契约、严格 TypeScript、Biome、测试基础）
应用到 SimFEA Studio 的后端无关部分。

### 已完成

#### 0. Composable 抽取（第1轮）
- `useRemoteRuns` 从 App.vue 抽取（remoteStatus + 5 个动作 + setComputeNodes）
- App.vue 降为纯展示+触发层

#### 1. API 契约层（源自 sim-main `defineRouteContract` 模式）
- `app/api/client.ts` — `contract()` + `createClient()` 基础设施
- `app/api/contracts.ts` — Zod schema 定义全部 11 个端点的请求/响应
- `app/api/simfeaClient.ts` — 重写为基于契约的类型安全客户端（不再 `Promise<any>`）
- `app/api/contracts.test.ts` — 5 个契约单元测试（Vitest）

#### 2. 项目配置
- `tsconfig.json` — strict 模式 + `@/` 路径别名
- `vite.config.js` — 添加 `@/` resolve alias
- `biome.json` — Biome 格式化/lint（space 2, single quote, as-needed semicolon）
- `vitest.config.ts` — Vitest 测试框架
- `app/env.d.ts` — Vue SFC 类型声明

#### 3. 导入规范化
- 全部相对 import → `@/` 绝对路径
- `app/types.ts` → contracts 的 re-export barrel

#### 4. Barrel exports
- `app/api/index.ts`
- `app/composables/index.ts`

#### 5. Composable 抽取（前两个 session）
- `useRemoteRuns` 从 App.vue 抽取（remoteStatus + 5 个动作 + setComputeNodes）
- App.vue 降为纯展示+触发层

### 关键决策
- ✅ **Zod 驱动类型**：类型从 Zod schema 推导（`z.output<typeof schema>`），不写手动 interface
- ✅ **单文件 contracts.ts**：12 个端点，不拆分多文件（sim-main 拆分是因为 ~100 端点）
- ✅ **message 在顶层**：FastAPI 响应 `{ message, data }`，契约精确匹配
- ❌ **Pass-through + strip**：发现契约不匹配时修正 schema，不靠 `.passthrough()` 绕过

#### 6. Composable 接口标准化
- `useRunEvents` → `UseRunEventsOptions { baseUrl }` options interface
- `useSidecarListeners` → `UseSidecarListenersOptions { appendLog }` options interface
- 接口模式与 `UseRemoteRunsOptions` 统一

#### 7. Pre-commit hooks
- Husky + lint-staged 配置
- pre-commit 自动运行 `biome check --write`
- 覆盖 `.ts`、`.vue`、`.js`、`.css`、`.json`、`.md`

#### 8. App.vue 拆分
- 抽取 `RemotePanel.vue` 独立组件（props + emit v-model 模式）
- App.vue 模板从 11 个 panel 降到 10 个，脚本逻辑更聚焦

### 待办
- [ ] 补全 Vitest 覆盖（composables 测试）
- [ ] App.vue 进一步拆分（控制面板面板独立组件？）
- [ ] CI：pnpm test + pnpm lint 列入 pre-commit

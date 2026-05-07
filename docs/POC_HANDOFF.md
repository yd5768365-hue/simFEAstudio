# SimFEA Studio — 项目状态与开发基线

## 项目定位

SimFEA Studio 是一个面向机械/仿真领域的桌面工作台，基于 Vue 3 + Tauri v2 + FastAPI 技术栈构建。

核心理念：**不造求解器，只管理求解器、算力、运行环境和学习记录。**

## 已验证能力

- Vue/Vite 前端可在 `http://localhost:3000` 正常启动
- FastAPI 侧车服务可在 `http://localhost:8008` 正常响应
- `GET /v1/connect` 返回侧车连接信息
- `GET /v1/compute-nodes/shh1/probe` 探测远程 SSH 节点
- `POST /v1/runs/shh1/demo` + SSE 事件流远程实时任务
- Tauri 桌面壳可正常加载前端并管理侧车生命周期
- Windows 侧车可执行文件打包（PyInstaller）

## 开发命令基线

| 操作 | 命令 |
|---|---|
| 完整启动 | `npm run dev:tauri` |
| 前端开发 | `npm run dev:frontend` |
| 后端测试 | `conda run -n simfea uvicorn src.backends.main:app --host 127.0.0.1 --port 8012` |
| 打包侧车 | `conda run -n simfea pyinstaller -c -F --clean --name main-x86_64-pc-windows-msvc --distpath src-tauri/bin/api src/backends/main.py` |
| 前端构建 | `npm run build` |

## 环境约定

- Python 环境：conda `simfea`（Python 3.11.15）
- WSL 专用发行版：`simFEA`
- 远程 SSH 节点：`shh1`（`cloud.dghpc.com:1014`）
- 前端包管理器：`npm`（当前环境可用）

> 注：`pnpm` 声明在 `package.json` 中但当前 shell 不可直接调用。Tauri 配置已改用 `npm run ...`。如需使用 `pnpm`，需在 Windows 侧配置 Corepack。

## 待推进方向

详见 `DEV_LOG_2026-05-07.md`，当前优先级：

1. **Runner 抽象** — 将 SSH 逻辑从 `main.py` 拆到 `src/backends/runners/`
2. **运行记录落盘** — stdout/stderr/meta.json 写入 `.simfea/runs/`
3. **远程工作目录 + 上传/下载** — 结果归巢最小闭环
4. **任务取消接口** — `POST /v1/runs/{run_id}/cancel`
5. **调度器探测** — 确认 shh1 背后 HPC 平台作业调度方式
6. **第一个真实求解器算例** — CalculiX 悬臂梁

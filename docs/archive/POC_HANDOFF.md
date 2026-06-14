# SimFEA Studio — 项目状态与开发基线

## 项目定位

SimFEA Studio 是一个面向机械/仿真领域的桌面工作台，基于 Vue 3 + Tauri v2 + FastAPI 技术栈构建。

核心理念：**不造求解器，只管理求解器、算力、运行环境和学习记录。**

## 已验证能力

- Vue/Vite 前端可在 `http://localhost:3000` 正常启动
- FastAPI 侧车服务可在 `http://localhost:8008` 正常响应
- `GET /v1/connect` 返回侧车连接信息
- `GET /v1/compute-nodes/remote-main/probe` 探测远程 SSH 节点
- `GET /v1/compute-nodes/remote-main/scheduler-probe` 探测远程调度器入口
- `POST /v1/runs/remote-main/demo` + SSE 事件流远程实时任务
- `POST /v1/runs/remote-main/slurm-demo` 生成 Slurm 脚本、提交 sbatch、轮询 squeue、归档 Slurm 输出
- `POST /v1/runs/{run_id}/cancel` 可请求取消正在运行的远程任务
- 每次运行都会生成本地物证归档和 `learning_report.md`
- Tauri 桌面壳可正常加载前端并管理侧车生命周期
- Windows 侧车可执行文件打包（PyInstaller）

## 开发命令基线

| 操作 | 命令 |
|---|---|
| 完整启动 | `npm run dev:tauri` |
| 前端开发 | `npm run dev:frontend` |
| 后端测试 | `conda run -n simfea python src/backends/main.py` |
| 打包侧车 | `conda run -n simfea pyinstaller -c -F --clean --name main-x86_64-pc-windows-msvc --distpath src-tauri/bin/api src/backends/main.py` |
| 前端构建 | `npm run build` |

## 环境约定

- Python 环境：conda `simfea`（Python 3.11.15）
- WSL 专用发行版：`simFEA`
- 远程 SSH 节点：`remote-main`（`example.hpc.edu:22`）
- 前端包管理器：`pnpm`（通过 Corepack 使用）

> 注：如当前 shell 不可直接调用 `pnpm`，可先启用 Node.js 自带的 Corepack。

## 待推进方向

详见 `DEV_LOG_2026-05-07.md`，当前优先级：

1. **Runner 抽象** — 将 SSH 逻辑从 `main.py` 拆到 `src/backends/runners/`
2. **SlurmRunner 配置化** — 将分区、CPU、内存、节点数从硬编码迁移到 `.simfea/config.json`
3. **第一个真实求解器算例** — CalculiX 悬臂梁
4. **输入文件归档** — 把几何、网格、边界条件、求解参数纳入 `.simfea/runs/`
5. **结果可视化入口** — 接入 VTK.js 读取归档结果文件

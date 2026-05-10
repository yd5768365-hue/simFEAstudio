<div align="center">
  <h1>SimFEA Studio</h1>
  <p><strong>仿真学习桌面工作台</strong></p>
  <p>为开源求解器、远程算力和学习记录提供统一的图形化执行环境。</p>

  ![Vue.js](https://img.shields.io/badge/Frontend-Vue_3-4FC08D?logo=vuedotjs)
  ![Tauri](https://img.shields.io/badge/Desktop-Tauri_v2-FFC131?logo=tauri)
  ![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi)
  ![Python](https://img.shields.io/badge/Language-Python_3.11-3776AB?logo=python)
  ![Rust](https://img.shields.io/badge/Desktop-Rust-CE422B?logo=rust)
  ![License](https://img.shields.io/badge/License-Apache_2.0-8162C3)
</div>

---

## 项目定位

SimFEA Studio 不是新的仿真引擎，不是商业 CAE 的竞品，也不是 AI 自动化工具。

它是一个面向机械仿真学习的个人工作台：把已有命令行求解器、远程算力、运行日志、结果文件和学习笔记收进同一个可回放的物证仓库。

> 不造求解器，只管理求解器、算力、运行环境和学习记录。

## 模板来源

本项目最初基于 [AlanSynn/vue-tauri-fastapi-sidecar-template](https://github.com/AlanSynn/vue-tauri-fastapi-sidecar-template) 搭建 `Tauri + Vue + FastAPI sidecar` 技术骨架。

当前仓库已经改造为 SimFEA Studio 的独立项目：原模板主要提供桌面壳、前端和 Python sidecar 的启动链路；远程计算、Slurm 闭环、物证归档、VTK 可视化和学习记录沉淀是本项目后续围绕机械仿真学习目标扩展出来的功能。

## 当前架构

```text
Tauri 桌面壳
→ Vue / Vite 前端
→ FastAPI Python sidecar
→ SSH / Slurm / 本地归档
```

SimFEA Studio 的目标不是“一键自动仿真”，而是把每一次亲手拆解过的物理概念留下证据：

- 输入：算例脚本、求解参数、远程工作目录。
- 过程：stdout/stderr 实时日志、调度器状态、JobID。
- 结果：`result.txt`、`result_summary.json`、`cantilever_result.vtk`。
- 复盘：`note.md`、`learning_report.md`。

## 核心特性

### 桌面外壳，而非求解器

SimFEA Studio 本身不求解任何物理方程。它的职责是在图形界面中管理那些真正会求解的工具。

| 繁琐的事 | SimFEA Studio 替你管理 |
|---|---|
| SSH 连接参数、密钥、主机别名 | 统一节点配置，一键连接 |
| 命令在本地还是远程执行 | Runner 抽象，前端无感切换 |
| 手动复制粘贴运行日志 | 自动 SSE 流式回传，界面实时显示 |
| 运行记录散落在各处终端 | 每一次运行都归档为学习物证 |

### 统一命令执行通道

```text
Vue 3 + Tauri
    ↓ HTTP / SSE
FastAPI sidecar
    ↓
SSH / Slurm / WSL / Docker / Local
    ↓
真实求解器
```

你可以在本地 WSL 里调 CalculiX 小算例，也可以在远程 HPC 节点上跑大作业，所有输出都通过统一事件流回到同一个界面。

## 已实现能力

- Tauri v2 桌面壳启动 Python sidecar，并在退出时清理 sidecar 进程。
- FastAPI 提供连接、运行记录、学习报告、artifact 文件读取接口。
- Vue 工作台展示侧车状态、计算节点、实时日志、运行记录、学习笔记和结果视图。
- 计算节点配置从 `.simfea/config.json` 读取，避免硬编码真实服务器信息。
- SSHRunner 最小闭环：远程执行命令、实时回传日志、下载结果、生成学习报告。
- SlurmRunner 最小闭环：写入 `.slurm`、`sbatch` 提交、解析 JobID、轮询 `squeue`、同步 `slurm-*.out/.err`。
- 结构化结果摘要：每次运行生成 `artifacts/result_summary.json`。
- 结果可视化：
  - 轻量 SVG 悬臂梁证据图。
  - VTK.js 视图入口，读取 `artifacts/cantilever_result.vtk`。
- 物证仓库自动归档在 `.simfea/runs/<run_id>/`。

## 物证仓库

```text
.simfea/runs/<run_id>/
├── meta.json
├── command.sh
├── stdout.log
├── stderr.log
├── events.jsonl
├── note.md
├── learning_report.md
└── artifacts/
    ├── result.txt
    ├── result_summary.json
    └── cantilever_result.vtk
```

`.simfea/` 是本地私有目录，已经被 `.gitignore` 忽略。不要把真实服务器账号、密钥、运行归档提交到仓库。

## 界面组件

| 组件 | 功能 |
|---|---|
| 顶部状态徽章 | 侧车服务与远程节点状态 |
| 侧车控制台 | 验证连接、启动/关闭侧车 |
| 远程计算面板 | 探测 SSH 节点、探测调度器、提交 demo / Slurm 运行 |
| 工具链地图 | FreeCAD、Salome、CalculiX、OpenFOAM、Elmer 的后续入口 |
| 物证仓库 | 运行记录选择与归档查看 |
| 结果可视化 | SVG 证据图和 VTK 视图 |
| 学习笔记 | 保存运行复盘 |
| 沉淀报告 | 自动生成 `learning_report.md` |
| 实时日志 | 侧车、远程命令、Slurm 输出 |

## 快速开始

### 1. 准备环境

推荐使用 miniconda 环境：

```powershell
conda activate simfea
```

需要安装：

- Node.js / pnpm
- Python 3.11
- Rust stable
- Windows OpenSSH
- Tauri 构建依赖

### 2. 安装依赖

```powershell
pnpm install
python -m pip install -e .
```

如果当前 PowerShell 找不到 `pnpm`，可以使用本机 Node.js 自带的 Corepack：

```powershell
corepack pnpm install
```

### 3. 配置计算节点

复制示例配置：

```powershell
New-Item -ItemType Directory -Force .simfea
Copy-Item simfea.config.example.json .simfea\config.json
```

然后编辑 `.simfea/config.json`：

```json
{
  "compute": {
    "default_node": "remote-main",
    "nodes": [
      {
        "alias": "remote-main",
        "label": "Remote SSH compute node",
        "host": "example.hpc.edu",
        "user": "your_username",
        "port": 22,
        "identity_file": "~/.ssh/id_ed25519",
        "remote_runs_root": "$HOME/simfea-runs"
      }
    ]
  }
}
```

学习记录可以额外导出到长期笔记库，目录和默认格式也放在同一个配置文件里：

```json
{
  "learning": {
    "export_root": ".simfea/learning",
    "default_format": "md",
    "formats": ["md", "json", "txt"]
  }
}
```

### 4. 打包 sidecar

Tauri dev 使用 PyInstaller 打包后的 sidecar：

```powershell
pnpm build:sidecar-winos
```

### 5. 启动桌面应用

```powershell
pnpm tauri dev
```

如果只想分离启动前后端：

```powershell
pnpm dev:all
```

前端默认地址：`http://localhost:3000`
API 默认地址：`http://localhost:8008`

## 使用流程

1. 点击“验证连接”，确认 FastAPI sidecar 在线。
2. 选择计算节点。
3. 点击“测试远程节点”，验证 SSH 通道。
4. 点击“探测调度器”，识别 Slurm/PBS/LSF 命令。
5. 点击“运行闭环样例”或“运行 Slurm 样例”。
6. 在实时日志中观察远程输出。
7. 在物证仓库选择运行记录。
8. 查看证据图或 VTK 视图。
9. 写入学习笔记并刷新 `learning_report.md`。
10. 在“学习记录导出”里选择 `md/json/txt`，把本次记录同步到指定学习库目录。

## API 端点

| Endpoint | 用途 |
|---|---|
| `GET /v1/connect` | 验证 sidecar 和配置 |
| `GET /v1/compute-nodes/{alias}/probe` | SSH 节点探测 |
| `GET /v1/compute-nodes/{alias}/scheduler-probe` | 调度器探测 |
| `POST /v1/runs/{alias}/demo` | SSHRunner 闭环样例 |
| `POST /v1/runs/{alias}/slurm-demo` | SlurmRunner 闭环样例 |
| `GET /v1/runs/{run_id}/events` | SSE 实时事件流 |
| `POST /v1/runs/{run_id}/cancel` | 取消运行 |
| `GET /v1/runs` | 运行记录列表 |
| `GET /v1/runs/{run_id}` | 单次运行详情 |
| `GET /v1/runs/{run_id}/result-summary` | 生成/读取结构化摘要 |
| `GET /v1/runs/{run_id}/artifacts/{path}` | 读取归档文件 |
| `POST /v1/runs/{run_id}/note` | 保存学习笔记 |
| `GET /v1/runs/{run_id}/report` | 刷新学习报告 |
| `POST /v1/runs/{run_id}/learning-export` | 导出学习记录到指定目录 |

## 项目结构

```text
SimFEA-Studio/
├── app/
│   ├── App.vue
│   ├── style.css
│   ├── types.ts
│   └── components/
│       ├── ResultEvidenceView.vue
│       └── VtkResultViewport.vue
├── src/backends/
│   └── main.py
├── src-tauri/
│   ├── src/main.rs
│   └── tauri.conf.json
├── docs/
└── simfea.config.example.json
```

## 后续路线图

- [x] Vue / Tauri / FastAPI 基础链路
- [x] SSH 远程执行和实时日志
- [x] 本地物证仓库
- [x] 学习笔记和学习报告
- [x] Slurm 最小闭环
- [x] 结构化结果摘要
- [x] VTK.js 最小视图入口
- [ ] 抽象 Runner 接口
- [ ] CalculiX 悬臂梁真实算例
- [ ] CalculiX 结果转换为 `.vtk/.vtu`
- [ ] FreeCAD / Salome 输入文件接入
- [ ] OpenFOAM / Elmer 运行模板

## 安全提醒

- `.simfea/config.json` 不提交。
- SSH 私钥不提交。
- `.simfea/runs/` 不提交。
- 公开文档中不要写真实服务器地址、端口、用户名、私钥路径。

## License

Apache-2.0

<div align="center">
  <h1>SimFEA Studio</h1>
  <p><strong>面向开源FEA学习者的仿真工作台</strong></p>
  <p>把每一次亲手跑通的仿真，变成可回放、可对比、可积累的学习证据。</p>

  ![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi)
  ![Vue.js](https://img.shields.io/badge/Frontend-Vue_3-4FC08D?logo=vuedotjs)
  ![Python](https://img.shields.io/badge/Language-Python_3.11-3776AB?logo=python)
  ![Tauri](https://img.shields.io/badge/Desktop-Tauri_v2_(optional)-FFC131?logo=tauri)
  ![VTK.js](https://img.shields.io/badge/Visualization-VTK.js-5C6BC0)
  ![CalculiX](https://img.shields.io/badge/Solver-CalculiX-2F6DB3)
  ![License](https://img.shields.io/badge/License-Apache_2.0-8162C3)
</div>

## 这是什么

SimFEA Studio 是一个运行在本地的仿真学习工作台。

它不造求解器，而是把 CalculiX、FreeCAD、PrePoMax、OpenFOAM 等开源求解器串联起来，统一管理执行环境、运行日志、结果文件和学习笔记——让每一次仿真都产生可追溯的学习物证，而不是跑完就忘的终端输出。

```
pip install -e . && simfea-studio
```

启动后浏览器自动打开，内置悬臂梁 demo 数据，无需配置求解器即可看到完整界面。

---

## 适合谁用

- **正在学有限元的学生**：想用开源工具（CalculiX）做真实仿真，但环境配置、日志管理、结果归档全靠手动
- **做 AI+FEA 研究的开发者**：需要批量跑仿真、积累对比数据、记录实验过程，不想每次都重新整理文件
- **想系统记录 FEA 学习过程的人**：不只是跑通算例，而是能回答"当时为什么这么设置、结果和解析解差了多少、下次该怎么改"

---

## 三个核心功能

### 1. 物证归档：每次仿真都留下完整记录

每次运行自动归档到 `.simfea/runs/<run_id>/`：

```
.simfea/runs/<run_id>/
├── meta.json              # 求解器、节点、状态、时间
├── run.command            # 实际执行的命令
├── stdout.log             # 完整求解日志
├── stderr.log             # 标准错误日志
├── events.jsonl           # SSE 事件流回放
├── note.md                # 结构化引导笔记
├── learning_report.md     # AI 合成学习报告
└── artifacts/
    ├── cantilever.frd
    ├── result_summary.json    # max_displacement_mm / max_von_mises_mpa
    └── solver_result.vtk
```

不再有"跑完不知道结果放哪了"的问题。

### 2. 三层学习沉淀：从日志到报告

运行结束后不是直接归档了事，而是引导你把这次仿真变成可复用的知识：

1. **实时日志**：stdout/stderr 逐行 SSE 推送，求解过程全程可见
2. **结构化笔记**：自动生成引导问题（目的是什么、预期结果、实际差异、下次改进），按问题填写而不是面对空白文本框
3. **学习报告**：笔记保存后自动合成 `learning_report.md`，日志摘要 + 结果指标 + 你的回答整合在一起

**研究笔记**：独立的 Markdown 编辑视图，支持新建、编辑和实时预览，用于记录与单次运行无关的长期学习笔记。

### 3. Benchmark Lab：13 个基准案例，含解析解对比

覆盖杆/梁/板/壳/桁架/扭转/热应力/压力容器，每个案例提供 CalculiX、ANSYS、PINN 的对比数据和解析解。不是玩具算例，是可以用来验证求解器配置和学习进度的参照系。

---

## 快速开始

### 路径一：pip 安装（推荐 — 仅需 Python 3.11+）

```powershell
git clone https://github.com/yd5768365-hue/simFEA-studio.git
cd simFEA-studio
pip install -e .
simfea-studio
```

浏览器打开 `http://localhost:8008`，内置 demo 数据开箱可见。

### 路径二：前端开发模式

```powershell
# 终端 1
python src/backends/main.py

# 终端 2
pnpm install
pnpm dev:frontend
```

### 路径三：桌面版（Tauri 原生窗口）

```powershell
pnpm install
pnpm dev:tauri
```

首次编译需 5–15 分钟，需要 Rust + VS Build Tools。

### 配置真实求解器（可选）

安装 [CalculiX](http://www.calculix.de/) 后在 `.simfea/config.json` 中填写路径：

```json
{
  "compute": {
    "default_node": "local",
    "nodes": [
      { "alias": "local", "label": "本机", "host": "localhost" }
    ]
  },
  "solvers": [
    {
      "alias": "calculix",
      "executable": "C:\\CalculiX\\bin\\ccx.bat",
      "command_template": "C:\\CalculiX\\bin\\ccx.bat cantilever"
    }
  ]
}
```

---

## 求解器支持

| 求解器 | 状态 | 说明 |
| --- | --- | --- |
| **CalculiX** | ✅ 已端到端验证 | FRD → VTK，指标摘要，物证归档，Solver Pack 安装 |
| FreeCAD | 骨架就绪 | 无头 Python 宏执行 |
| PrePoMax | ✅ regeneration 已验证 | STEP → Gmsh → CalculiX → VTK 热力图 |
| **freecad-prepomax** | ✅ 已端到端验证 | 两步链式工作流，统一归档 20 个产物 |
| OpenFOAM | 骨架就绪 | 待接入真实 case |
| Elmer | 骨架就绪 | 待接入真实 case |

**实测数据（2026-05-19）**

| Workflow | 耗时 | VTK | 关键指标 |
| --- | --- | --- | --- |
| calculix | 0.1s | ✅ | D=8.93mm S=37.50MPa |
| prepomax-regenerate | 10.0s | ✅ | D=0.061mm S=0.0001MPa |
| freecad-prepomax | 10.4s | ✅ | D=0.061mm S=0.0001MPa |

---

## 当前架构

```text
浏览器 / Tauri 桌面壳
        │
FastAPI (独立 uvicorn 或 sidecar)
        │
   Vue SPA · REST API · SSE 事件流
        │
LocalRunner · SSHRunner · SlurmRunner
SolverRunner · WorkflowRunner
        │
CalculiX / FreeCAD / PrePoMax / OpenFOAM / Elmer
        │
.simfea/runs/<run_id>  物证仓库
```

---

## 验证

```powershell
python -m unittest discover -s src/backends/tests -v
python scripts/check_backend_boundaries.py
pnpm test
pnpm build
```

- 后端：125 个单元测试通过
- 前端：35 个 Vitest 测试通过（6 个测试文件）
- 模块边界：24 个模块，0 违规

---

## 路线图

- [x] CalculiX 本地端到端链路 + FRD → VTK
- [x] SSH 远程运行 + Slurm HPC 提交
- [x] 物证归档 + 三层学习沉淀
- [x] Benchmark Lab — 13 个基准案例，含解析解对比
- [x] Method Lab — From 1 to 0 教学框架
- [x] pip 安装模式 + demo 数据降级
- [x] 工具链管理页面（FreeCAD / PrePoMax / CalculiX）
- [x] 研究笔记 — Markdown 编辑/预览/管理
- [ ] GP/神经网络 surrogate 接入真实 CalculiX 数据
- [ ] OpenFOAM / Elmer 真实 case 接入
- [ ] AI 辅助证据评分和复盘建议
- [ ] 桌面安装包（Windows .msi / macOS .dmg）

---

## 模板来源

本项目最初基于 [AlanSynn/vue-tauri-fastapi-sidecar-template](https://github.com/AlanSynn/vue-tauri-fastapi-sidecar-template) 搭建骨架。本地/远程执行、Slurm 闭环、求解器声明式配置、FRD → VTK、物证归档和学习记录沉淀是围绕机械仿真学习目标扩展出来的功能。

---

## License

Apache-2.0。本项目代码以仓库根目录的 `LICENSE` 为准。Vue、Tauri、FastAPI、VTK.js、CalculiX 等第三方依赖分别遵循其各自许可证。

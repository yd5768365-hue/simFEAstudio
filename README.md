<div align="center">
  <h1>SimFEA Studio</h1>
  <p><strong>仿真学习桌面工作台</strong></p>
  <p>为开源求解器提供统一的图形化执行环境，记录每一次亲手拆解过的物理概念</p>

  <!-- Tech badges -->
  ![Vue.js](https://img.shields.io/badge/Frontend-Vue_3-4FC08D?logo=vuedotjs)
  ![Tauri](https://img.shields.io/badge/Desktop-Tauri_v2-FFC131?logo=tauri)
  ![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi)
  ![Python](https://img.shields.io/badge/Language-Python_3.11-3776AB?logo=python)
  ![Rust](https://img.shields.io/badge/Desktop-Rust-CE422B?logo=rust)
  ![License](https://img.shields.io/badge/License-Apache_2.0-8162C3)
  <br/><br/>

  **[文档](#快速开始) • [特性](#核心特性) • [路线图](#开发路线图) • [贡献](#参与贡献)**
</div>

---

## 项目定位

**SimFEA Studio** 不是新的仿真引擎，不是商业 CAE 的竞品，也不是 AI 自动化工具。

它是一个**面向机械/仿真工程师的个人工作台** —— 为现有开源命令行求解器（CalculiX、OpenFOAM、Elmer 等）提供：
- 📱 统一的图形化执行环境
- 🌍 跨越本地/WSL/Docker/远程 HPC 的命令管理
- 📊 每一次求解运行的学习记录与复盘体系

> **核心理念**：不造求解器，只管理求解器、算力、运行环境和学习记录。

---

## 核心特性

### 🖥️ 桌面外壳，而非求解器

SimFEA Studio 本身不求解任何物理方程。它的职责是**在图形界面中管理那些真正会求解的工具**：

| 繁琐的事 | SimFEA Studio 替你管理 |
|---|---|
| SSH 连接参数、密钥、主机别名 | 统一节点配置，一键连接 |
| 命令在本地还是远程执行 | Runner 抽象，前端无感切换 |
| 手动复制粘贴运行日志 | 自动 SSE 流式回传，界面实时显示 |
| 运行记录散落在各处终端 | 每一次运行都归档为学习物证 |

### 🌉 统一命令执行通道

支持多种执行环境，对前端透明：

```
┌─────────────────────┐
│  Vue 3 + Tauri      │  桌面界面
└──────────┬──────────┘
           │ HTTP / SSE
┌──────────▼──────────┐
│  FastAPI 侧车服务   │  后端 API
└──────────┬──────────┘
           │
    ┌──────┴────────────────┬──────────┐
    │                       │          │
 ┌──▼──┐  ┌──────┐  ┌───────▼──┐  ┌──▼───┐
 │ SSH │  │ WSL  │  │ Docker   │  │Local │
 └─────┘  └──────┘  └──────────┘  └──────┘
    │         │           │          │
    └─────────┴───────────┴──────────┘
           你的求解器
```

**实际应用场景**：
- 在本地 WSL 里调 CalculiX 调试小算例
- 在远程 HPC 节点上跑 OpenFOAM 大作业
- 全部通过统一的事件流回传到同一个界面

### 📋 每一次运行都是物证

不仅仅是日志，而是你学习过程的完整证据链：

```
.simfea/runs/<run_id>/
├── meta.json       # 运行元数据：求解器、节点、时间戳
├── stdout.log      # 标准输出完整记录
├── stderr.log      # 错误输出
├── command.sh      # 执行的命令原文
└── artifacts/      # 结果文件（.vtk / .foam / 等）
```

---

## 产品功能

### 当前已实现

✅ FastAPI 侧车服务完整生命周期管理（启动、停止、状态监测）
✅ 远程 SSH 节点探测（主机名、CPU 核心数、用户、工作目录）
✅ 远程命令实时执行，SSE 事件流逐行回传至界面
✅ 侧车服务日志实时显示
✅ 求解器接入框架（CalculiX / OpenFOAM / Elmer 占位）

### 界面组件

启动项目后，Tauri 窗口包括：

| 组件 | 功能 |
|---|---|
| **顶部状态徽章** | 侧车服务在线状态、远程节点连通状态一目了然 |
| **侧车控制台** | 验证连接、启动/停止侧车服务、实时日志 |
| **远程算力面板** | 探测 SSH 节点、运行远程任务、实时回传日志 |
| **求解器入口** | CalculiX / OpenFOAM / Elmer 执行环境 |
| **物证仓库** | 所有运行记录的检索与复盘 |

---

## 技术栈

| 层级 | 技术 | 说明 |
|---|---|---|
| **桌面壳** | Tauri v2 | 轻量级跨平台桌面框架（相比 Electron 更轻） |
| **前端框架** | Vue 3 + Vite | 响应式 UI 与快速开发体验 |
| **后端 API** | Python 3.11 + FastAPI | 高性能异步 API，支持 SSE 流式响应 |
| **实时通信** | SSE (Server-Sent Events) | 服务器推送，避免轮询，减低延迟 |
| **侧车打包** | PyInstaller | 将 FastAPI 服务打包为单文件分发 |
| **远程通道** | OpenSSH（系统自带） | 标准 SSH 连接管理 |
| **编程语言占比** | Vue (34.9%) / Python (25.4%) / Rust (16%) / CSS (14.7%) | — |

### 为什么这样选型？

- **Tauri vs Electron**：Tauri 使用系统 WebView，包体积更小（~2MB vs ~150MB）
- **FastAPI vs Flask**：原生异步支持，SSE 流式传输性能更好
- **SSE vs WebSocket**：单向推送场景足够，实现更简洁，无需心跳保活

---

## 快速开始

### 系统要求

| 依赖 | 版本 | 用途 |
|---|---|---|
| **Node.js** | ≥ 18 | 前端构建（Vite） |
| **Python** | ≥ 3.9 | FastAPI 后端 |
| **Rust 工具链** | stable | Tauri 构建 |
| **OpenSSH** | 系统自带 | 远程连接 |
| **conda** | 最新 | Python 环境管理 |

**系统支持**：Windows 10+ / macOS 10.13+ / Linux (Ubuntu 18.04+)

### 安装步骤

#### 1️⃣ 克隆仓库并初始化环境

```bash
git clone https://github.com/yd5768365-hue/simFEAstudio.git
cd simFEAstudio

# 创建 Python 虚拟环境
conda create -n simfea python=3.11
conda activate simfea
```

#### 2️⃣ 安装前端依赖

```bash
npm install
# 或使用 yarn / pnpm
```

#### 3️⃣ 安装 Python 依赖

```bash
pip install -e .  # 以开发模式安装
pip install -r requirements-dev.txt  # 开发工具
```

#### 4️⃣ 打包 Python 侧车（可选，开发时无需）

```bash
# 仅在修改后端代码后需要执行
pyinstaller -c -F --clean \
  --name main-x86_64-pc-windows-msvc \
  --distpath src-tauri/bin/api \
  src/backends/main.py
```

#### 5️⃣ 启动开发模式

```bash
# 方式一：直接启动 Tauri 开发模式（推荐）
npm run dev:tauri

# 方式二：分离启动（调试时有用）
# 终端 1
npm run dev

# 终端 2
npm run dev:backend  # 启动 FastAPI 侧车
```

### 验证安装

启动后在 Tauri 窗口中依次验证：

1. **验证侧车连接**
   - 点击「验证连接」按钮
   - 应该看到绿色状态徽章：`Sidecar Online`

2. **探测远程节点**
   - 点击「测试远程节��」
   - 系统将尝试连接 SSH 节点 `shh1`（cloud.dghpc.com:1014）
   - 日志窗口应显示节点信息（CPU、用户、工作目录）

3. **执行远程任务**
   - 点击「运行远程测试任务」
   - 观察日志窗口逐行输出命令执行过程

若所有步骤均成功，说明开发环境搭建完毕！

### 常见问题排查

<details>
<summary><b>问：Tauri 启动失败，提示找不到 Rust 工具链</b></summary>

**解决**：
```bash
rustup install stable
rustup default stable
```

</details>

<details>
<summary><b>问：Python 侧车启动失败，提示 `ModuleNotFoundError`</b></summary>

**解决**：
```bash
# 确认虚拟环境已激活
conda activate simfea

# 重新安装依赖
pip install -e .
```

</details>

<details>
<summary><b>问：无法连接远程 SSH 节点</b></summary>

**排查步骤**：
1. 验证网络连通性：`ping cloud.dghpc.com`
2. 测试 SSH 连接：`ssh -p 1014 user@cloud.dghpc.com`
3. 检查 `~/.ssh/config` 中的节点配置
4. 查看后端日志（侧车控制台）获取详细错误信息

</details>

---

## 项目结构

```
SimFEA-Studio/
├── app/                           # 前端代码
│   ├── components/                # Vue 组件
│   │   ├── SidecarConsole.vue     # 侧车控制台
│   │   ├── RemotePanel.vue        # 远程算力面板
│   │   └── LogViewer.vue          # 实时日志窗口
│   ├── App.vue                    # 主界面
│   └── main.ts                    # 前端入口
│
├── src/                           # 后端代码
│   └── backends/
│       ├── main.py                # FastAPI 主程序 & 路由
│       ├── api/                   # API 端点
│       │   ├── sidecar.py         # 侧车生命周期管理
│       │   ├── runners.py         # 多种 Runner 实现
│       │   └── remote.py          # SSH 远程执行
│       ├── models/                # 数据模型
│       ├── utils/                 # 工具函数
│       └── config.py              # 配置管理
│
├── src-tauri/                     # Tauri 桌面框架
│   ├── src/
│   │   └── main.rs                # Tauri 主进程
│   ├── tauri.conf.json            # Tauri 配置（窗口、权限等）
│   └── bin/api/                   # 打包后的侧车可执行文件
│
├── docs/                          # 项目文档
│   ├── architecture.md            # 架构设计文档
│   ├── api-reference.md           # API 参考
│   └── contributing.md            # 贡献指南
│
├── pyproject.toml                 # Python 项目配置
├── package.json                   # Node.js 配置
├── Cargo.toml                     # Rust 配置
└── README.md                      # 本文件
```

---

## 开发指南

### 本地开发工作流

```bash
# 激活环境
conda activate simfea

# 开发前端
npm run dev

# 另一个终端：开发后端（自动重载）
npm run dev:backend

# 调试 Tauri（可视化调试前端）
npm run dev:tauri

# 构建生产版本
npm run build

# 运行测试
npm run test
npm run test:backend
```

### 添加新的求解器支持

在 `src/backends/solvers/` 中添加新的求解器类：

```python
# src/backends/solvers/mynewsolver.py
from .base import BaseSolver

class MyNewSolverRunner(BaseSolver):
    name = "MyNewSolver"
    input_ext = ".mns"  # 输入文件扩展名
    output_ext = ".out"
    
    async def run(self, input_file: str, runner) -> str:
        """执行求解器"""
        cmd = f"mynewsolver {input_file}"
        return await runner.execute(cmd)
    
    def parse_output(self, output_file: str) -> dict:
        """解析输出结果"""
        # 自定义解析逻辑
        pass
```

### 代码风格

- **Python**：遵循 PEP 8，使用 `black` 格式化
  ```bash
  pip install black
  black src/
  ```

- **Vue/JavaScript**：遵循 ESLint 配置
  ```bash
  npm run lint
  npm run lint:fix
  ```

- **Rust**：使用 `rustfmt`
  ```bash
  cargo fmt
  ```

---

## 架构设计

### 数据流

```
用户交互 (前端)
    ↓
Vue 事件 → HTTP 请求 (JSON)
    ↓
FastAPI 路由处理
    ↓
Runner 抽象层
    ├─ LocalRunner   (本地 shell)
    ├─ WslRunner     (WSL 环境)
    ├─ DockerRunner  (Docker 容器)
    └─ SshRunner     (远程 SSH)
    ↓
命令执行 & SSE 推送
    ↓
前端 EventSource 监听
    ↓
日志窗口实时显示 + 结果保存
```

### 运行记录存储

每次求解运行产生的物证存储在 `.simfea/runs/` 下：

```
.simfea/runs/20260507_143522_calcul1x/
├── meta.json         # {"solver": "CalculiX", "node": "local", "status": "success", ...}
├── command.sh        # 实际执行的命令
├── stdout.log        # 标准输出
├── stderr.log        # 标准错误
├── timing.json       # {"start": "...", "end": "...", "elapsed_sec": 12.5}
└── artifacts/
    ├── result.vtk    # 仿真结果（VTK 格式）
    └── output.dat    # 其他输出文件
```

---

## 开发路线图

### Phase 1: 核心链路 ✅
- [x] 桌面 → 侧车 → SSH → 实时事件流完整打通
- [x] 远程节点探测与状态监测
- [x] SSE 日志流式传输

### Phase 2: 执行引擎 🔄 进行中
- [ ] Runner 抽象完善 (LocalRunner / SshRunner / WslRunner / DockerRunner)
- [ ] 运行记录落盘与物证仓库的元数据管理
- [ ] 后台任务队列 (支持并行执行)

### Phase 3: 求解器集成 📋 计划中
- [ ] CalculiX 结构有限元（悬臂梁算例）
- [ ] OpenFOAM 流体动力学（层流算例）
- [ ] Elmer 多物理场耦合
- [ ] 求解器参数化脚本生成

### Phase 4: 用户体验 🎯 计划中
- [ ] 运行记录检索、排序、对比
- [ ] 结果可视化（ParaView 集成）
- [ ] 案例库与模板
- [ ] 团队协作（运行记录分享、注释）

### Phase 5: 高级功能 💡 未来
- [ ] 任务调度器探测 (sbatch / srun / qsub)
- [ ] 工作流编排（DAG 任务依赖）
- [ ] 参数扫描与优化（并行蒙特卡洛）
- [ ] 云存储集成（结果自动备份）

---

## 参与贡献

我们欢迎任何形式的贡献！

### 贡献流程

1. **Fork** 本仓库
2. **创建特性分支**：`git checkout -b feature/your-feature`
3. **提交更改**：`git commit -am 'Add new feature'`
4. **推送到分支**：`git push origin feature/your-feature`
5. **提交 Pull Request**

### 贡献指南

详见 [CONTRIBUTING.md](./docs/contributing.md)

### 报告问题

发现 Bug？[在此提交 Issue](../../issues)，请包含：
- 系统信息（OS、Python 版本、Node 版本）
- 复现步骤
- 实际行为 vs 预期行为
- 相关日志或截图

---

## 许可证

本项目采用 [Apache License 2.0](./LICENSE) 开源。

简而言之，你可以自由使用、修改和分发，但必须：
- 保留原始许可证声明
- 说明对源代码的修改
- 在 `NOTICE` 文件中保留版权声明

---

## 常见问题 (FAQ)

<details>
<summary><b>Q: SimFEA Studio 能否替代 ANSYS / Abaqus？</b></summary>

**A**: 不能。SimFEA Studio 不是求解器，而是求解器的**管理工具**。它帮助你更方便地使用开源求解器（如 CalculiX、OpenFOAM），但不能独立求解问题。

</details>

<details>
<summary><b>Q: 可以用来做什么？</b></summary>

**A**: 
- 在本地或远程 HPC 上运行开源求解器，获得统一的图形界面
- 管理多个求解任务的参数和记录
- 学习仿真的基本流程（前处理 → 求解 → 后处理）
- 自动化重复性的求解任务

</details>

<details>
<summary><b>Q: 如何添加自己的求解器？</b></summary>

**A**: 参见开发指南的「添加新的求解器支持」部分。或在 [Discussions](../../discussions) 中提问。

</details>

<details>
<summary><b>Q: 是否支持离线使用？</b></summary>

**A**: 可以。只要 Tauri 应用启动，不一定需要网络。但远程 SSH 节点执行显然需要网络连接。

</details>

---

## 相关资源

- 📖 [完整文档](./docs/)
- 🔗 [API 参考](./docs/api-reference.md)
- 🏗️ [架构设计](./docs/architecture.md)
- 🤝 [贡献指南](./docs/contributing.md)

## 致谢

感谢以下开源项目的支持：
- [Tauri](https://tauri.app/) - 轻量级桌面框架
- [Vue 3](https://vuejs.org/) - 渐进式 JavaScript 框架
- [FastAPI](https://fastapi.tiangolo.com/) - 现代 Python Web 框架
- [CalculiX](http://www.calculix.de/) / [OpenFOAM](https://www.openfoam.com/) / [Elmer](https://www.csc.fi/web/elmer) - 开源求解器

---

<div align="center">
  <sub>
    SimFEA Studio • 为学习仿真的每一步留下痕迹 ✨
  </sub>
  <br/>
  <sub>
    📧 问题反馈：<a href="../../issues">提交 Issue</a> | 💬 讨论建议：<a href="../../discussions">开启 Discussion</a>
  </sub>
</div>

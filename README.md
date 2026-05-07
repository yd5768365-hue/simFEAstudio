<div align="center">
  <h1>SimFEA Studio</h1>
  <p><strong>仿真学习桌面外壳</strong></p>
  <p>包装开源命令行求解器，记录每一次亲手拆解过的物理概念。</p>

  <!-- Tech badges -->
  ![Vue.js](https://img.shields.io/badge/Frontend-Vue_3-4FC08D?logo=vuedotjs)
  ![Tauri](https://img.shields.io/badge/Desktop-Tauri_v2-FFC131?logo=tauri)
  ![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi)
  ![Python](https://img.shields.io/badge/Language-Python_3.11-3776AB?logo=python)
  ![License](https://img.shields.io/badge/License-Apache_2.0-8162C3)
  <br/>
</div>

---

**SimFEA Studio** 不是新的仿真引擎，不是商业 CAE 的竞品，也不是 AI 自动化工具。

它是一个面向机械/仿真工程师的个人工作台——为现有开源命令行求解器（CalculiX、OpenFOAM、Elmer 等）提供图形化的远程执行环境与学习管理体系。

> 不造求解器，只管理求解器、算力、运行环境和学习记录。

---

## 界面预览

<!-- 在此处放入产品截图 -->

如果你已经在本地启动项目，打开 Tauri 窗口可以看到：
- **顶部状态徽章** — 侧车服务在线状态、远程节点连通状态一目了然
- **侧车控制台** — 验证连接、启动/停止侧车服务
- **远程算力面板** — 探测 SSH 节点、运行远程任务、实时回传日志
- **求解器入口** — CalculiX / OpenFOAM / Elmer 执行环境占位
- **物证仓库** — 每一次运行的记录与复盘
- **实时日志窗口** — 侧车服务与远程任务的全部输出

---

## 核心特性

### 桌面外壳，而非求解器

SimFEA Studio 本身不求解任何物理方程。它做的事情是：**帮你在图形界面中管理那些真正会求解的工具**。

| 你不需要关心 | SimFEA Studio 替你管理 |
|---|---|
| SSH 连接参数、密钥、主机别名 | 统一节点配置，一键连接 |
| 命令在本地还是远程执行 | Runner 抽象，前端无感切换 |
| 手动复制粘贴运行日志 | 自动 SSE 流式回传，界面实时显示 |
| 运行记录散落在各处终端 | 每一次运行都归档为学习物证 |

### 统一命令执行通道

SSH、WSL、Docker、本地 shell——在 SimFEA Studio 眼里是同一件事：

```
桌面界面 (Vue + Tauri)
    ↓ HTTP / SSE
FastAPI 侧车服务
    ↓ SSH / WSL / Docker / Local
你的求解器
```

区别只在于命令被送到了哪里执行。这意味着未来你可以：
- 在本地 WSL 里调 CalculiX 调试小算例
- 在远程 HPC 节点上跑 OpenFOAM 大作业
- 全部通过统一的事件流回传到同一个界面

### 每一次运行都是物证

```
.simfea/runs/<run_id>/
├── meta.json       # 运行元数据：求解器、节点、时间
├── stdout.log      # 标准输出完整记录
├── stderr.log      # 错误输出
├── command.sh      # 执行的命令原文
└── artifacts/      # 结果文件归档
```

这不是日志——这是你学习过程的证据链。

---

## 当前能力

- FastAPI 侧车服务完整生命周期管理（启动、停止、状态监测）
- 远程 SSH 节点探测（主机名、CPU 核心数、用户、工作目录）
- 远程命令实时执行，SSE 事件流逐行回传至界面
- 侧车服务日志实时显示
- 求解器接入框架占位（CalculiX 结构有限元 / OpenFOAM 流体 / Elmer 多物理场）

---

## 快速开始

### 环境要求

| 依赖 | 版本要求 | 用途 |
|---|---|---|
| Node.js | ≥ 18 | 前端构建 |
| Python | ≥ 3.9 | FastAPI 后端 |
| Rust 工具链 | stable | Tauri 构建 |
| OpenSSH | 系统自带 | 远程通道 |
| conda 环境 | `simfea` | Python 依赖管理 |

### 启动

```bash
# 1. 安装前端依赖
npm install

# 2. 安装 Python 依赖
conda run -n simfea python -m pip install .

# 3. 打包 Python 侧车
conda run -n simfea pyinstaller -c -F --clean \
  --name main-x86_64-pc-windows-msvc \
  --distpath src-tauri/bin/api \
  src/backends/main.py

# 4. 启动 Tauri 开发模式
npm run dev:tauri
```

### 验证

在 Tauri 窗口中：

1. 点击「验证连接」— 确认侧车服务在线
2. 点击「测试远程节点」— 探测 SSH 节点 `shh1` 状态
3. 点击「运行远程测试任务」— 远程执行命令，在日志窗口观察逐行输出

---

## 技术栈

| 层 | 选型 |
|---|---|
| 桌面壳 | Tauri v2 |
| 前端框架 | Vue 3 + Vite |
| 后端 API | Python 3.11 + FastAPI |
| 实时通信 | SSE (Server-Sent Events) |
| 侧车打包 | PyInstaller (单文件分发) |
| 远程通道 | 系统 OpenSSH |
| WSL 发行版 | `simFEA`（项目专用） |
| 远程节点 | `shh1`（cloud.dghpc.com:1014） |

---

## 项目结构

```
SimFEA-Studio/
├── app/                    # 前端代码 (Vue 3)
│   └── App.vue             # 主界面
├── src/
│   └── backends/
│       └── main.py         # FastAPI API 路由与侧车入口
├── src-tauri/              # Tauri 桌面壳
│   ├── src/main.rs         # Tauri 主进程
│   ├── tauri.conf.json     # Tauri 配置
│   └── bin/api/            # 打包后的侧车可执行文件
├── docs/                   # 项目文档与开发日志
└── README.md
```

---

## 开发路线图

```text
✓ 完成  核心链路：桌面 → 侧车 → SSH → 实时事件流
  进行  Runner 抽象 (LocalRunner / SshRunner / WslRunner / DockerRunner)
  进行  运行记录落盘与物证仓库
  计划  远程工作目录 + 上传/下载（结果归巢）
  计划  任务取消接口
  计划  调度器探测（sbatch / srun / qsub）
  计划  第一个真实求解器算例（CalculiX 悬臂梁）
```

---

## 许可证

[Apache-2.0](./LICENSE)

---

<div align="center">
  <sub>SimFEA Studio 基于开源项目构建，不是商业 CAE 替代品，而是你学习仿真的个人实验台。</sub>
</div>

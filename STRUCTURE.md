# 📁 simFEAstudio 仓库结构

## 项目概览

SimFEA Studio 是一个开源有限元分析（FEA）学习平台，采用 **Tauri 桌面应用 + FastAPI 后端 + Vue 3 前端** 的现代全栈架构。

---

## 文件夹层级

```
simFEAstudio/
│
├── 🎨 前端 (Vue 3)
│   └── app/
│       ├── api/              → 类型化 API 客户端 (Zod 合约)
│       ├── components/       → Vue 组件库
│       ├── composables/      → 组合 API 逻辑复用
│       ├── utils/            → 工具函数
│       ├── App.vue           → 主应用组件
│       ├── main.js           → Vue 入口
│       ├── style.css         → 全局样式
│       └── types.ts          → 类型重导出
│
├── 💻 后端 (Python FastAPI)
│   └── src/backends/
│       ├── simfea_api/       → 核心业务逻辑
│       │   ├── config.py           → 配置、求解器定义
│       │   ├── run_archive.py      → 运行档案管理
│       │   ├── learning.py         → 学习报告生成
│       │   ├── results.py          → 结果处理、VTK 转换
│       │   ├── frd_to_vtk.py       → CalculiX FRD 解析
│       │   ├── logger.py           → 结构化日志
│       │   ├── schemas.py          → SSE 事件模型
│       │   ├── cleanup.py          → 清理过期运行
│       │   ├── install.py          → 求解器安装
│       │   ├── toolchain.py        → 工具链管理
│       │   ├── security.py         → 安全验证
│       │   └── infer_text_api.py   → AI 推理接口
│       ├── runners/          → 执行引擎 (纯函数，无 FastAPI)
│       │   ├── ssh.py              → SSH 命令构建
│       │   ├── slurm.py            → SLURM 脚本生成
│       │   ├── slurm_polling.py    → SLURM 作业轮询
│       │   ├── remote_files.py     → 远程文件下载
│       │   ├── solver.py           → 求解器探测、验证
│       │   └── workflow.py         → 多步工作流定义
│       ├── routers/          → FastAPI 路由处理器
│       ├── execution/        → 执行状态机协调
│       ├── cae_preflight_lib/ → CAE 预检库 (监控等)
│       ├── inference/        → AI 推理服务
│       ├── demo_runs/        → 演示数据集
│       ├── tests/            → Python 单元测试
│       ├── main.py           → FastAPI 应用入口 (8008 端口)
│       ├── cli.py            → 命令行接口
│       └── state.py          → 全局应用状态
│
├── 🖥️ Tauri 桌面壳 (Rust)
│   └── src-tauri/
│       └── src/main.rs       → 管理应用窗口、启动 Python sidecar
│
├── 🔧 构建与配置
│   ├── config/               → 构建配置文件
│   │   ├── vite.config.js    → Vite 构建配置
│   │   └── tsconfig.json     → TypeScript 配置
│   ├── scripts/              → 构建脚本
│   │   └── build_pip.py      → 前端编译 + pip 打包
│   ├── pyproject.toml        → Python 项目配置
│   ├── package.json          → pnpm 依赖声明
│   └── pnpm-lock.yaml        → 依赖锁定
│
├── 📦 部署与文档
│   ├── docker/               → Docker 部署配置
│   ├── docs/                 → 项目文档
│   ├── learning/             → 学习基准案例库
│   ├── public/               → 静态资源 (favicon 等)
│   └── MANIFEST.in           → pip 包文件清单
│
├── ⚙️ 工程配置
│   ├── .github/              → GitHub Actions 工作流
│   ├── .husky/               → Git hooks (pre-commit 等)
│   ├── .claude/              → Claude AI 配置
│   ├── .gitignore            → Git 忽略规则
│   └── .gitattributes        → Git 属性
│
└── 📄 项目文件
    ├── README.md             → 项目说明、快速开始
    ├── CLAUDE.md             → 开发指南、架构设计
    ├── AGENTS.md             → AI 代理说明
    ├── LICENSE               → Apache 2.0 许可证
    └── STRUCTURE.md          → 本文档（仓库结构说明）
```

---

## 核心模块职责

### 前端 (app/)
- **api/** → 类型安全的 API 客户端（基于 Zod 合约验证）
- **components/** → 可复用 Vue 组件（表格、卡片、模态框等）
- **composables/** → 逻辑提取（SSE 流、文件上传、状态管理）
- **utils/** → Markdown 渲染、时间格式化、数值处理

### 后端 (src/backends/)
- **simfea_api/** → 业务逻辑核心（求解器管理、学习报告生成）
- **runners/** → 纯函数执行引擎（支持本地、SSH、SLURM 执行）
- **routers/** → HTTP 路由定义（调用 simfea_api 和 runners）
- **execution/** → 状态机（协调异步运行、事件发送）

### 数据流
```
Tauri 桌面 → FastAPI (8008) ← Vue 前端 (1420/3000)
    ↓
Python Backend
    ├─ routers/     (HTTP 层)
    ├─ simfea_api/  (业务逻辑)
    └─ runners/     (执行引擎)
    ↓
.simfea/runs/<run_id>/
    ├─ meta.json
    ├─ stdout.log
    ├─ events.jsonl
    ├─ note.md
    ├─ learning_report.md
    └─ artifacts/ (求解器产物)
```

---

## 快速导航

| 需求 | 文件位置 |
|------|---------|
| 修改 UI 组件 | `app/components/` |
| 添加新 API 端点 | `src/backends/routers/` + `src/backends/simfea_api/` |
| 支持新求解器 | `src/backends/simfea_api/config.py` |
| 配置 SSH/SLURM | `src/backends/runners/` |
| 修改学习报告逻辑 | `src/backends/simfea_api/learning.py` |
| 查看演示数据 | `src/backends/demo_runs/` |
| 构建 pip 包 | 运行 `scripts/build_pip.py` |

---

## 设计原则

1. **三层架构** → routers (HTTP) → simfea_api (逻辑) → runners (执行)
2. **类型安全** → 前端 Zod + TypeScript，后端 Pydantic
3. **模块独立** → runners 不导入 FastAPI，易于单元测试
4. **证据留存** → `.simfea/` 本地私有档案，git 忽略
5. **可观测性** → 结构化日志、SSE 实时流、事件回放


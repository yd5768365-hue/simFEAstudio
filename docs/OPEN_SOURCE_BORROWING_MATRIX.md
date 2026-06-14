# Open Source Borrowing Matrix

## 借鉴原则

- 只借工作台能力，不借大平台体量。
- 优先借案例结构、求解器适配、证据归档、教程分层和工作流表达。
- 不把 SimFEA Studio 变成求解器、CAD 内核或工业级协同平台。
- 每一轮借鉴都必须落到一个可验证的小改动：文档、检查脚本、测试、界面入口或运行证据。

## 项目矩阵

| 项目 | 值得借鉴 | 不借什么 | 第一轮落地 |
| --- | --- | --- | --- |
| FreeCAD | Workbench / Addon 的功能入口分层；Python 脚本可复现操作；问题报告要求版本、步骤和样例文件。 | 不借 CAD 内核、完整参数化建模系统、庞大的桌面插件生态。 | 把 SimFEA Studio 的“作业、学习、方法、基准、工具链”视为工作台入口，后续每个入口都要有清晰输入、输出和证据。 |
| SALOME | Study / Object Browser / Notebook / Viewer 的研究对象组织方式；从建模、网格、求解到后处理的 study 管理。 | 不借工业级模块系统、多人协作、完整前后处理平台。 | 强化“案例就是 study”的概念：每个 benchmark case 至少有问题描述、输入、结果和学习证据。 |
| Gmsh | Geometry / Mesh / Solver / Post-processing 四段式；脚本、CLI、GUI、API 并行入口；教程由浅入深。 | 不借网格算法和 CAD kernel 细节。 | 用五段式检查 Benchmark Lab：`geometry / mesh / solver / post / evidence`。轻量 1D 案例中，`mesh` 可由 `dimension` 表示的离散化阶段推断。 |
| OpenFOAM | Case 目录即契约：输入树、运行命令、日志和结果共同定义一次计算；教程案例可直接作为学习样例。 | 不借 CFD 求解器实现和复杂字典修复系统。 | 为 `learning/benchmarks` 建立只读 case contract，显式 `workflow_stages` 优先；没有显式字段时，从问题描述、方法、维度和结果文件推断。 |
| FEniCSx / DOLFINx | Demo 同时讲方程、离散、边界条件、求解器设置和派生量；提供脚本 / notebook 入口。 | 不借弱形式求解框架，也不把 Studio 改成 PDE 编程环境。 | 生成 `learning/benchmarks/LEARNING_PATH.md`，用“物理问题 -> 离散化 -> 求解方法 -> 派生量 -> 复盘问题”组织案例。 |
| MFEM | Examples / miniapps 分层；简单例子、并行例子和复杂应用分开，便于学习路径递进。 | 不借 C++ 高性能 FEM 架构和并行求解器能力。 | 生成 L1 Example / L2 Benchmark / L3 Miniapp 三层学习路径。 |

## 当前第一轮优化边界

第一轮已经落地两件事：

1. 把开源项目的借鉴边界写清楚，防止后续优化漂移成大平台重构。
2. 增加一个只读 Benchmark case contract 检查，确认 13 个案例是否具备最小的学习和对比结构。

第二轮已经把 Gmsh / OpenFOAM 的 case-flow 思路推进到检查脚本中：

- `geometry`: 由问题描述文件表示。
- `mesh`: 由 `dimension` 或真实 `.inp` 输入表示；在基础案例里等价于离散化阶段。
- `solver`: 由 `methods` 或真实 `.inp` 输入表示。
- `post`: 由 `results/*.csv` 表示。
- `evidence`: 由问题描述和结果文件共同支撑。

第三轮已经把 MFEM / FEniCSx 的教学组织方式推进到生成脚本中：

- `scripts/build_benchmark_learning_path.py` 读取 13 个 `case.json`。
- `learning/benchmarks/LEARNING_PATH.md` 按 L1 Example / L2 Benchmark / L3 Miniapp 分层。
- 每层保留物理类型、维度、方法和状态，方便 Method Lab 后续消费。

暂不处理：

- `App.vue` 大拆分。
- `src/backends/main.py` 大拆分。
- OpenFOAM / Elmer 真实求解器接入。
- 清理当前工作区已有未提交文件。

第四轮已经把 SALOME / FreeCAD 的 Study / Workbench 思路推进到 API 契约中：

- `/v1/benchmarks` 继续保留原来的 `name`、`title`、`group`、`has_problem`、`has_results` 字段。
- 同时透出 `case.json` 中的 `level`、`physics`、`dimension`、`methods`、`status`，让 Benchmark Lab 和 Method Lab 可以把案例当成可浏览的 study object。
- 新增 `learning_tier`，把 L1 / L2 / L3 映射为稳定前端契约，前端优先使用显式层级，缺失时才回退旧启发式分类。

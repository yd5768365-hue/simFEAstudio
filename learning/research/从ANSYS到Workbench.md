# 从"开源 ANSYS"到"学习工作台"——一个项目的方向修正

> 2026-06-10 反思笔记

## 最初的野心

2026 年 5 月，我启动了 SimFEA Studio。当时的想法很大：做一个**开源替代 ANSYS 的桌面应用**。

具体设想：
- Tauri 桌面壳 + Vue 前端 + Python 后端
- 集成 CalculiX、OpenFOAM、Elmer 等开源求解器
- SSH/Slurm/Docker 多种运行通道
- Docker 容器一键部署——任何机器都能跑
- 对标 ANSYS Workbench 的前处理→求解→后处理流程

于是有了 6 月 1 日的 Docker 全栈容器化：ubuntu + CalculiX + Gmsh + nginx + FastAPI + supervisor，`docker compose up` 一键启动。

## 碰到的现实

做了几周之后，逐渐认识到几个事实：

1. **CalculiX 已经很成熟**——v2.22，200+ C 源文件，接触/材料非线性/动力学/热力耦合全部覆盖。它不是"缺一个 GUI"，它是**缺一个愿意花时间学的人**。

2. **前处理是更大的坑**——CAE 前处理（Cubit、Salome、Gmsh、FreeCAD）每个都是独立的大型项目。做一个能用的 GUI 前处理器，工作量不亚于再写一个求解器。

3. **`F:\手搓一个求解器\work\` 里有 9 个开源项目**——别人已经做了 CAE 关键词编辑器、Cubit-CalculiX 插件、FRD→VTK 转换器。我做的任何东西，都有更成熟的替代品。

4. **我是大一学生**——资源（一台 RTX 3060 12GB 的笔记本）和时间都有限。和商业软件竞争是不现实的。

## 转向的触发点

6 月 9 日，调研了 CalculiX 生态的 9 个开源项目后，写了 `calculix-ecosystem-exploration.md`。结论很清楚：

> SimFEA 不做前处理、不做求解器、不替代任何商业软件。
> 它做"学习记录"——管理求解器、归档运行、对比方法、沉淀笔记。
> 定位是"FEA 的 lab notebook"，不是"另一个 CAE 工具"。

同一天，《SimFEA 项目群状态总结》明确了三个项目的边界：

| 项目 | 定位 | 我学到了什么 |
|------|------|------------|
| SimFEA Studio | 对比工作台 | 全栈开发、架构设计 |
| SimFEA-Lab Core | 手写 FEM 求解器 | 刚度矩阵、边界条件、组装求解 |
| cae-preflight | INP 预检查 | 输入验证、关键词解析 |

## 转向的价值

回头看，这个方向修正是项目中最关键的决策：

**放弃了**：
- 做一个商业软件的免费替代品（没意义，CalculiX 已经够好）
- 做一个通用前处理 GUI（工作量太大，非我擅长的）
- Docker 全栈容器化作为核心卖点（变成了可选通道）

**得到了**：
- 一个 13 案例的 Benchmark Lab，每个案例有 6 种方法对比
- 一个手写 FEM 求解器，从单杆开始逐步扩展
- 一个求解器开发视图，跟踪 Core 的进度
- 一个 Bridge 脚本，让 Core 自动对接 Studio

**最重要的是得到了清晰的自我定位**：

```
我不是在做产品，我是在学习 FEM。
Studio 是我的笔记本，Core 是我的草稿纸，
Benchmark Lab 是我的验证台。
AI 是加速器，不是替代品。
```

## 那个 Docker 容器现在在哪里

6 月 1 日写的 `docker/Dockerfile`、`docker/nginx.conf`、`docker/supervisord.conf`、`docker-compose.yml` 仍然在仓库里。它的角色变了：

- 从"核心部署方式"变成了"ComputeNode 的一种——docker 类型节点"
- 和 local / SSH / Slurm 并列，作为 Runner 的一个选项
- 没有浪费，只是定位变了

## 经验教训

1. **从具体问题出发，不要从宏大愿景出发**——"我想做一个开源 ANSYS"是愿景，"我想对比杆拉伸的 6 种解法"是可执行的任务
2. **认清边界比扩张功能更需要勇气**——停止做 Docker 全栈容器化的主力推进，承认它只是可选的 Runner 通道
3. **大一学生的优势不是资源，是时间**——我有 4 年时间去理解 FEM 底层，不需要现在就做一个产品
4. **手写求解器比集成求解器更有学习价值**——用 CalculiX 跑 100 个案例，不如自己写 1 个杆单元

## 当前路线（2026-06-10）

```
Core v0.1: 1D 杆单元 ✓
    ↓
Core v0.2: 多杆系统 → 解锁 Studio Case 10
    ↓
Core v0.3: 2D 桁架 → 解锁 Studio Case 13
    ↓
Core v0.4: Euler-Bernoulli 梁 → 解锁 Case 03, 07, 12
    ↓
...
```

每实现一种新单元 → 草稿纸推导 → 代码验证 → AI 上传到 Studio → 对比表中多一行 `simfea-core`。

所有 AI 的使用都服务于一个目标：**加速我理解 FEM 底层的速度**，而不是代替我理解。

# Benchmark Learning Path

这个索引借鉴 MFEM 的 examples / miniapps 分层，以及 FEniCSx demo 的教学表达：

物理问题 -> 离散化 -> 求解方法 -> 派生量 -> 复盘问题

## 分层原则

- L1 Example：结果可观察，优先建立量纲、边界条件和结果指标感。
- L2 Benchmark：机制重建，重点比较解析解、传统 FEM 和误差来源。
- L3 Miniapp：真实工具链，强调输入质量、运行日志、结果归档和证据链。

## L1 Example

结果观察：先看输入、边界条件、量纲、结果指标和误差方向。

| 目录 | 案例 | 物理 | 维度 | 方法 | 状态 |
| --- | --- | --- | --- | --- | --- |
| `01_一维杆拉伸` | 一维杆拉伸 | 结构力学 | 1D 杆 | analytic, simfea-core, calculix, ansys, pinn | completed |
| `02_一维杆分布载荷` | 一维杆分布载荷 | 结构力学 | 1D 杆 | analytic, calculix, ansys, pinn | completed |
| `08_弹簧串并联` | 弹簧串并联 | 结构力学 | 离散弹簧系统 | analytic, calculix | completed |

## L2 Benchmark

机制重建：对照解析解和数值结果解释误差、刚度、载荷与边界。

| 目录 | 案例 | 物理 | 维度 | 方法 | 状态 |
| --- | --- | --- | --- | --- | --- |
| `03_悬臂梁弯曲` | 悬臂梁弯曲 | 结构力学 | 1D 梁 | analytic, calculix | completed |
| `04_圆孔板应力集中` | 圆孔板应力集中 | 结构力学 | 2D 平面应力 | analytic-kirsch, analytic-heywood, calculix | completed |
| `06_圆轴扭转` | 圆轴扭转 | 结构力学 | 1D 轴 | analytic, calculix | completed |
| `07_简支梁中央集中力` | 简支梁中央集中力 | 结构力学 | 1D 梁 | analytic, calculix | completed |
| `09_热膨胀约束杆` | 热膨胀约束杆 | 热应力 | 1D 杆 | analytic, calculix | completed |
| `10_阶梯杆拉伸` | 阶梯杆拉伸 | 结构力学 | 1D 杆 | analytic, calculix | completed |
| `11_薄壁圆筒压力容器` | 薄壁圆筒压力容器 | 压力容器 | 壳体 | analytic, calculix | completed |
| `12_简支梁均布载荷` | 简支梁均布载荷 | 结构力学 | 1D 梁 | analytic, calculix | completed |
| `13_平面二杆桁架` | 平面二杆桁架 | 结构力学 | 2D 桁架 | analytic, calculix | completed |

## L3 Miniapp

真实工具链：关注输入预检查、求解流程、日志、归档和可复盘证据。

| 目录 | 案例 | 物理 | 维度 | 方法 | 状态 |
| --- | --- | --- | --- | --- | --- |
| `05_预检查演示` | 预检查演示 | 求解器输入质量 | 工具链演示 | 错误示例, 修正示例 | demo |

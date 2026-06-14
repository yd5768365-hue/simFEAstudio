# 基准案例库

仿真方法对比验证案例。每个案例包含：

- `问题描述.md` — 物理问题、控制方程、边界条件、解析解推导
- `解析解.py` — 解析解 Python 实现（可独立运行）
- `calculix/` — CalculiX 输入文件与运行结果
- `pinn/` — PINN 实现（如有）
- `results/对比结果.csv` — 多方法对比结果表
- `case.json` — 案例分组、层级、物理类型、维度、方法列表和状态

## 案例列表

| # | 目录 | 分组 | 层级 | 维度 | 方法 | 状态 |
|---|------|------|------|------|------|------|
| 1 | `01_一维杆拉伸` | 基础案例 | L1 | 1D 杆 | analytic, simfea-core, calculix, ansys, pinn | completed |
| 2 | `02_一维杆分布载荷` | 基础案例 | L1 | 1D 杆 | analytic, calculix, ansys, pinn | completed |
| 3 | `03_悬臂梁弯曲` | 基础案例 | L2 | 1D 梁 | analytic, calculix | completed |
| 4 | `04_圆孔板应力集中` | 基础案例 | L2 | 2D 平面应力 | analytic-kirsch, analytic-heywood, calculix | completed |
| 5 | `05_预检查演示` | 基础案例 | L3 | 工具链演示 | 错误示例, 修正示例 | demo |
| 6 | `06_圆轴扭转` | 扩展案例 | L2 | 1D 轴 | analytic, calculix | completed |
| 7 | `07_简支梁中央集中力` | 扩展案例 | L2 | 1D 梁 | analytic, calculix | completed |
| 8 | `08_弹簧串并联` | 扩展案例 | L1 | 离散弹簧系统 | analytic, calculix | completed |
| 9 | `09_热膨胀约束杆` | 扩展案例 | L2 | 1D 杆 | analytic, calculix | completed |
| 10 | `10_阶梯杆拉伸` | 扩展案例 | L2 | 1D 杆 | analytic, calculix | completed |
| 11 | `11_薄壁圆筒压力容器` | 扩展案例 | L2 | 壳体 | analytic, calculix | completed |
| 12 | `12_简支梁均布载荷` | 扩展案例 | L2 | 1D 梁 | analytic, calculix | completed |
| 13 | `13_平面二杆桁架` | 扩展案例 | L2 | 2D 桁架 | analytic, calculix | completed |

## 案例元数据约定

`case.json` 保持轻量，不做复杂 schema。当前只要求这些字段：

```json
{
  "group": "基础案例",
  "title": "一维杆拉伸",
  "level": "L1",
  "physics": "结构力学",
  "dimension": "1D 杆",
  "methods": ["analytic", "calculix"],
  "status": "completed"
}
```

`level` 用于 Method Lab 的 CAE 入口阶梯：

- `L1`：结果观察，先建立边界条件、量纲和指标感。
- `L2`：机制重建，对照解析解解释误差和力学机制。
- `L3`：真实工具链，强调输入预检查、求解流程和证据归档。

# CalculiX 生态项目调研报告

> 调研日期：2026-06-10
> 源码路径：`F:\手搓一个求解器\work\`

对 CalculiX 开源生态的 9 个相关项目进行了系统性调研，按功能分为三类。

---

## 一、核心求解器 & 算例

### 1. CalculiX-master（求解器源码）

| 属性 | 内容 |
|------|------|
| 版本 | v2.22 |
| 语言 | C |
| 作者 | Guido Dhondt (CCX) / Klaus Wittig (CGX) |
| 官网 | http://www.calculix.de |
| 规模 | 200+ 个 `.c` 源文件 |

完整的三维结构有限元求解器：

- **静力学**：线弹性、非线性（几何/材料/接触）
- **动力学**：模态分析、谐响应、瞬态动力学、稳态动力学
- **热分析**：稳态/瞬态热传导、热力耦合
- **材料**：弹性、塑性、超弹性、蠕变、形状记忆合金
- **接触**：Node-to-Surface、Surface-to-Surface、Mortar
- **特殊功能**：裂纹分析、循环对称、子结构

这是整个 CalculiX 生态的核心，所有其他项目围绕它构建。

### 2. CalculiX-Examples-master（参数化算例集）

| 属性 | 内容 |
|------|------|
| 作者 | Martin Kraska（勃兰登堡应用科技大学） |
| 规模 | 50+ 个算例 |
| 前处理 | CGX 或 GMSH |
| 语言 | CGX 脚本 + Python |

覆盖的物理场景：

| 类别 | 案例 |
|------|------|
| 接触 | Hertz 接触、过盈配合、阀门密封、板簧、CNC 装配 |
| 非线性 | 螺栓预紧、屈曲、塑性弯曲、拉伸试验、蠕变 |
| 热分析 | 焊接变形、热冲击、热成像检测 |
| 动力学 | 离散系统频响、模态分析 |
| 断裂 | CT 试样能量释放率 |
| 优化 | 参数优化（CAD/Opt）、截面比较 |
| RVE | 周期边界条件、平面滑动、正交各向异性 |
| 测试 | 节点力验证、耦合约束、梁单元测试 |

附带 Python 工具脚本：

- `param.py` — FBD 参数化几何生成
- `dat2txt.py` — DAT 结果提取
- `monitor.py` — 求解监控
- `periodic.py` — 周期边界条件
- `separate.py` — 避免节点平均的后处理

---

## 二、前处理 & GUI 工具

### 3. cae-master — CalculiX Advanced Environment

| 属性 | 内容 |
|------|------|
| 作者 | Ihor Mirzov |
| 语言 | Python 3 + PyQt5 |
| 许可 | GPL v3 |
| 特点 | 开箱即用（自带 CCX/CGX 二进制 + Python 运行时） |

**目前最完整的 CalculiX 开源 GUI 前处理器**：

- **关键词编辑器**：基于 `kw_list.xml` 维护所有 CalculiX 关键词，每个关键词有专属编辑对话框
- **INP 解析器**：测试超过 20,000 个 INP 文件（包括 Abaqus 模型）
- **CGX 集成**：CGX 窗口连接到编辑器，接受命令
- **作业管理**：从 GUI 编译 Fortran 子程序、提交求解、打开结果
- **结果查看**：可导出为 VTU 在 Paraview 中查看
- **集成转换器**：`ccx2paraview` (FRD→VTK)+ `unv2ccx` (UNV→INP)

工作流程：FreeCAD/Salome 建模 → CAE 导入网格 → 编辑关键词 → 求解 → 查看结果

### 4. Cubit-CalculiX-main — Coreform Cubit 组件

| 属性 | 内容 |
|------|------|
| 版本 | 2025.9 |
| 语言 | C++ |
| 依赖 | Coreform Cubit 2025.8 |
| 平台 | Windows 11 / Ubuntu 24.04 |

在 Cubit 中完整定义 CalculiX 模型，功能极其全面：

**材料库**（可通过库管理）：
- 弹性（各向同性/正交各向异性/各向异性/工程常数）
- 塑性（各向同性/随动/混合/Johnson Cook）
- 超弹性（Arruda-Boyce/Mooney-Rivlin/Neo Hooke/Ogden/Polynomial/Yeoh）
- Hyperfoam、Mohr Coulomb、蠕变、阻尼、热膨胀

**完整的求解步骤支持**：
- Static、Frequency、Buckle、Heat Transfer
- Coupled/Uncoupled Temperature-Displacement
- Dynamic、Modal Dynamic、Steady State Dynamics、Complex Frequency

**结果转换**（自动计算 von Mises / 主应力）：
- FRD 节点结果 → Paraview
- DAT 节点/单元/积分点结果 → Paraview
- 多块检查器可视化单部件
- 积分点结果可视化

**Python API**：可查询结果文件，用于收敛性研究和基于结果的网格细化。

### 5. beso-master — 双向渐进结构优化

| 属性 | 内容 |
|------|------|
| 作者 | @fandaL |
| 语言 | Python |
| 许可 | LGPL v3 |
| 依赖 | CalculiX ≥ v2.17 + NumPy + FreeCAD ≥ v0.18 |

**BESO**（Bi-directional Evolutionary Structural Optimization）：

- 从设计域中迭代删除低应力单元、恢复高应力单元
- 收敛到最优材料分布（类骨骼结构）
- 提供 FreeCAD GUI 界面

示例：
1. 简支 2D 梁
2. 发动机支架
3. 航空轴承支架
4. FreeCAD GUI 操作

---

## 三、数据转换 & 后处理

### 6. ccx2paraview-master — FRD → Paraview 转换器

| 属性 | 内容 |
|------|------|
| 作者 | Ihor Mirzov |
| 语言 | Python |
| 版本 | v3.2.0 |
| 安装 | `pip install ccx2paraview` |

**核心功能**：
- CalculiX ASCII `.frd` → VTK 传统格式 / VTU XML 压缩格式
- 自动生成 von Mises 应力和主应力/主应变分量
- 每个时间步生成单独文件 + 汇总 PVD 文件（支持 Paraview 动画）
- 支持 FRD 中任意数量的输出间隔

**命令行**：
```bash
ccx2paraview job.frd vtk    # 转 VTK
ccx2paraview job.frd vtu    # 转 VTU
ccx2paraview job.frd vtk vtu # 同时转两种格式
```

**Python API**：
```python
from ccx2paraview import Converter
c = Converter('job.frd', ['vtu'])
c.run()
```

附带 Paraview Programmable Filter 代码片段（应力张量重构、特征值/特征向量计算）。

### 7. CCXStressReader-main — DAT 应力读取器

| 属性 | 内容 |
|------|------|
| 作者 | Mote3D |
| 语言 | Python |
| 许可 | LGPL |

读取 CalculiX `.dat` 文件中的积分点输出（应力/应变/等效塑性应变），计算最小值、最大值和算术平均值，输出 `.txt`。

**关键价值**：积分点结果比插值到节点的结果更准确，尤其在非线性材料行为的应力分析中。

激活方式（INP 文件）：
```
*EL PRINT, ELSET=Eall, FREQUENCY=n
S, E, PEEQ
```

### 8. gmsh2ccx-master — Gmsh → CalculiX 转换器

| 属性 | 内容 |
|------|------|
| 作者 | Ihor Mirzov |
| 语言 | Python |
| 许可 | GPL v3 |

**解决的问题**：Gmsh 导出 2D INP 时不生成 `*SURFACE` 关键字，也不列出属于 Physical Curve 的单元边 → 无法在 CalculiX 中对 2D 单元边施加边界条件。

**功能**：
- 从 Gmsh 的 Physical Curve 生成 `*SURFACE` 和 `*NSET`
- 正确计算单元边号
- 支持一阶三角形 (S3) 和四边形 (S4)
- 附带 `INPParser.py`：通用 INP 解析库（读取节点/单元/集合/表面、计算形心、场插值）

用法：
```bash
python3 gmsh2ccx.py -g gmsh3.inp -c ccx3.inp -e S3 -ns 1
```

### 9. konvertor-master — GMSH/ABAQUS → CGX 转换器

| 属性 | 内容 |
|------|------|
| 语言 | C++ |
| 功能 | GMSH/ABAQUS INP → CGX INP |

单文件 C++ 程序（`konvertor.cpp`），功能类似 gmsh2ccx，但针对 CGX 特定格式。说明文档极简，可能为早期原型。

---

## 对 SimFEA Studio 的启发

### 可直接复用的资源

1. **CalculiX-Examples（50+ 算例）** → Benchmark Lab 的标准测试案例
   - 每个案例已有理论解或参考结果，可直接纳入 `comparison.csv`
   - 参数化脚本 (`param.py`) 可改造为 SimFEA 的作业模板

2. **ccx2paraview** → 对比 SimFEA 现有的 `frd_to_vtk.py`
   - ccx2paraview 更成熟（支持时间序列、主应力自动计算、PVD 汇总）
   - 可作为后端转换的可选引擎

3. **CCXStressReader** → 补充 `.dat` 解析能力
   - SimFEA 目前只处理 FRD，增加 DAT 可提供积分点级精度

### 可借鉴的设计模式

4. **CAE 的 XML 驱动关键词编辑器** — 可借鉴到 Toolchain Manager
   - 所有关键词定义在 `kw_list.xml`，GUI 自动生成编辑对话框
   - 模式：声明式定义 → 自动生成 UI

5. **Cubit-CalculiX 的 Python API** — 收敛性研究 + 网格细化的好设计
   - `ccx.help()` 查询 API
   - 结果可查询、绘图、导出 CSV

6. **BESO 的优化循环** — 未来 Benchmark Lab 可加入优化基准
   - `求解 → 读取结果 → 更新设计 → 再求解` 的自动化循环

### 技术栈对比

| 功能 | SimFEA 现有 | 社区方案 | 建议 |
|------|------------|---------|------|
| FRD→VTK | `frd_to_vtk.py` | ccx2paraview v3.2 | 可替换或并存 |
| DAT 解析 | 无 | CCXStressReader | 可集成 |
| 前处理 GUI | 无 | CAE / Cubit-CalculiX | 非 SimFEA 定位（Benchmark Lab 不代替前处理） |
| 拓扑优化 | 无 | BESO | 未来 Benchmark 类型 |
| INP 解析 | 无 | INPParser.py | 可用于输入文件校验 |
| 网格转换 | 无 | gmsh2ccx / konvertor | 可用于多源网格导入 |

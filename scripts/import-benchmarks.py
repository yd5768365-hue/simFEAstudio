r"""Import entry-level benchmark cases for SimFEA Benchmark Lab.

Target: first-year Mechanics of Materials (材料力学) curriculum.
All cases have simple analytic solutions suitable for learning FEA basics.

Usage:
    python scripts/import-benchmarks.py
    python scripts/import-benchmarks.py --write
    python scripts/import-benchmarks.py --write --replace
"""

import argparse
import shutil
import sys
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent.parent / "learning" / "benchmarks"

# ── Case definitions (entry-level 材料力学) ────────────────────


def _case_torsion():
    """Simple torsion of a circular shaft."""
    name = "06_圆轴扭转"
    md = r"""# Case 6: 圆轴扭转 (Circular Shaft Torsion)

## 物理问题描述

一根等截面实心圆轴，左端固定，右端受扭矩 $T$ 作用。轴截面为圆形，材料均匀各向同性，属于线弹性静力学扭转问题。

```
  固定端                                    T →
  ┌──────┬──────────────────────────────┬──────→
  │  //  │     G, J (均匀圆截面)         │  T   │
  └──────┴──────────────────────────────┴──────→
  x = 0                                x = L
```

**几何与材料参数：**

| 参数 | 符号 | 值 | 单位 |
|------|------|-----|------|
| 轴长 | L | 200 | mm |
| 轴径 | d | 20 | mm |
| 剪切模量 | G | 80 000 | MPa |
| 扭矩 | T | 10 000 | N·mm |

## 解析解

### 截面极惯性矩

$$
J = \frac{\pi d^4}{32} = \frac{\pi \times 20^4}{32} = 15\,708\ \text{mm}^4
$$

### 最大剪应力（发生在表面）

$$
\tau_{\max} = \frac{T \cdot (d/2)}{J}
$$

### 自由端扭转角

$$
\phi = \frac{T \cdot L}{G \cdot J}
$$

## 参考值

| 物理量 | 表达式 | 数值 | 单位 |
|--------|--------|------|------|
| $J$ | $\pi d^4 / 32$ | 15 708 | mm⁴ |
| $\tau_{\max}$ | $T \cdot r / J$ | 6.37 | MPa |
| $\phi$ | $T L / (G J)$ | 1.59×10⁻³ | rad |

## 参考文献

- 刘鸿文. (2011). *材料力学* (第5版). 高等教育出版社. 第三章 扭转.
"""
    csv = """method,tau_max_MPa,phi_rad,error_pct,notes
analytic,6.37,0.00159,,材料力学圆轴扭转公式
calculix,,,,C3D8 三维实体 (to verify)
"""
    return name, md, csv


def _case_simply_supported_beam():
    """Simply supported beam with center point load."""
    name = "07_简支梁中央集中力"
    md = r"""# Case 7: 简支梁中央集中力 (Simply Supported Beam, Center Load)

## 物理问题描述

一根等截面矩形梁，两端简支，跨中受集中力 $P$。材料均匀各向同性，小变形假设。

```
        P
        ▼
  ══════╤══════
  ▲      |      ▲
  └── L/2 ──┴── L/2 ──┘
```

**几何与材料参数：**

| 参数 | 符号 | 值 | 单位 |
|------|------|-----|------|
| 跨度 | L | 500 | mm |
| 截面宽 | b | 20 | mm |
| 截面高 | h | 30 | mm |
| 弹性模量 | E | 210 000 | MPa |
| 集中力 | P | 1 000 | N |

## 解析解

### 截面惯性矩

$$
I = \frac{b h^3}{12} = \frac{20 \times 30^3}{12} = 45\,000\ \text{mm}^4
$$

### 跨中最大挠度

$$
\delta_{\max} = \frac{P L^3}{48 E I}
$$

### 跨中最大弯曲正应力

$$
\sigma_{\max} = \frac{M_{\max} \cdot (h/2)}{I} = \frac{(PL/4) \cdot (h/2)}{I}
$$

## 参考值

| 物理量 | 数值 | 单位 |
|--------|------|------|
| $I$ | 45 000 | mm⁴ |
| $\delta_{\max}$ | 约 0.275 | mm |
| $\sigma_{\max}$ | 约 41.7 | MPa |

## 与 Case 3（悬臂梁）对比

| | 简支梁 | 悬臂梁 |
|--|--------|--------|
| 最大挠度 | $PL^3/(48EI)$ | $PL^3/(3EI)$ |
| 最大弯矩 | $PL/4$ | $PL$ |

同样载荷下，简支梁挠度仅为悬臂梁的 1/16。

## 参考文献

- 刘鸿文. (2011). *材料力学* (第5版). 第五章 弯曲变形.
"""
    csv = """method,delta_max_mm,sigma_max_MPa,error_pct,notes
analytic,0.275,41.7,,简支梁中央集中力公式
calculix,,,,B31 梁单元 (to verify)
"""
    return name, md, csv


def _case_springs():
    """Series and parallel springs."""
    name = "08_弹簧串并联"
    md = r"""# Case 8: 弹簧串并联 (Springs in Series and Parallel)

## 物理问题描述

两根弹簧分别以串联和并联方式连接，下端施加拉力 $P$。计算两种连接方式的等效刚度和位移。

```
  串联:                    并联:
  ═══════                   ═══════
  ┌─///─┐                   ┌─///─┐
  │ k1  │                   │ k1  │
  ├─///─┤                   ├─///─┤
  │ k2  │                   │ k2  │
  └──┬──┘                   └──┬──┘
     ▼ P                       ▼ P
```

**参数：**

| 参数 | 符号 | 值 | 单位 |
|------|------|-----|------|
| 弹簧 1 刚度 | k1 | 100 | N/mm |
| 弹簧 2 刚度 | k2 | 200 | N/mm |
| 拉力 | P | 500 | N |

## 解析解

### 串联

等效刚度：

$$
\frac{1}{k_{\text{ser}}} = \frac{1}{k_1} + \frac{1}{k_2}
$$

位移：

$$
\delta_{\text{ser}} = \frac{P}{k_{\text{ser}}} = P \cdot \left(\frac{1}{k_1} + \frac{1}{k_2}\right)
$$

### 并联

等效刚度：

$$
k_{\text{par}} = k_1 + k_2
$$

位移：

$$
\delta_{\text{par}} = \frac{P}{k_{\text{par}}}
$$

## 参考值

| 物理量 | 串联 | 并联 | 单位 |
|--------|------|------|------|
| 等效刚度 | 66.7 | 300 | N/mm |
| 位移 | 7.5 | 1.67 | mm |

## 参考文献

- 刘鸿文. (2011). *材料力学* (第5版). 第二章 拉伸与压缩.
"""
    csv = """method,delta_series_mm,delta_parallel_mm,error_pct,notes
analytic,7.5,1.67,,弹簧串并联公式
calculix,,,,SPRING1 单元 (to verify)
"""
    return name, md, csv


def _case_thermal_stress():
    """Thermal stress in a constrained bar."""
    name = "09_热膨胀约束杆"
    md = r"""# Case 9: 热膨胀约束杆 (Thermal Stress in Constrained Bar)

## 物理问题描述

一根两端完全固定的均匀杆，温度升高 $\Delta T$。由于热膨胀被约束，杆内产生压缩热应力。材料为线弹性。

```
  ╔════════════════════════╗
  ║   E, A, α              ║  ΔT = +50°C
  ╚════════════════════════╝
  x=0                    x=L
  完全固定                 完全固定
```

**参数：**

| 参数 | 符号 | 值 | 单位 |
|------|------|-----|------|
| 杆长 | L | 500 | mm |
| 截面积 | A | 100 | mm² |
| 弹性模量 | E | 210 000 | MPa |
| 热膨胀系数 | α | 1.2×10⁻⁵ | /°C |
| 温升 | ΔT | 50 | °C |

## 解析解

### 完全约束情况

热应变被完全约束：$\varepsilon_{\text{mech}} + \varepsilon_{\text{therm}} = 0$

$$
\varepsilon_{\text{mech}} = -\alpha \Delta T
$$

热应力：

$$
\sigma = E \cdot \varepsilon_{\text{mech}} = -E \alpha \Delta T
$$

注意：正值为拉应力，负值为压应力。此处为压缩。

### 一端自由情况（对比）

若一端自由，则 $\sigma = 0$，伸长量：

$$
\Delta L = \alpha L \Delta T
$$

## 参考值

| 物理量 | 数值 | 单位 |
|--------|------|------|
| 热应变 | −6×10⁻⁴ | — |
| 热应力（约束） | −126 | MPa |
| 自由伸长量 | 0.3 | mm |

## 参考文献

- 刘鸿文. (2011). *材料力学* (第5版). 第二章 温度应力.
"""
    csv = """method,sigma_thermal_MPa,free_elongation_mm,error_pct,notes
analytic,-126.0,0.3,,热应力公式
calculix,,,,C3D8 热力耦合 (to verify)
"""
    return name, md, csv


def _case_stepped_bar():
    """Stepped bar under axial load."""
    name = "10_阶梯杆拉伸"
    md = r"""# Case 10: 阶梯杆拉伸 (Stepped Bar Under Axial Load)

## 物理问题描述

一根两段式阶梯圆杆，左端固定，右端受拉力 $P$。两段截面不同，但材料相同。需要分段计算变形后叠加。

```
  固定端                                             P →
  ┌──────┬──────────────────┬──────────────────────┬──────→
  │  //  │  A1, L1          │  A2, L2              │  P   │
  └──────┴──────────────────┴──────────────────────┴──────→
```

**参数：**

| 参数 | 符号 | 值 | 单位 |
|------|------|-----|------|
| 段 1 长度 | L1 | 100 | mm |
| 段 2 长度 | L2 | 200 | mm |
| 段 1 直径 | d1 | 10 | mm |
| 段 2 直径 | d2 | 20 | mm |
| 弹性模量 | E | 210 000 | MPa |
| 拉力 | P | 5 000 | N |

## 解析解

### 各段截面积

$$
A_1 = \pi d_1^2 / 4 = 78.54\ \text{mm}^2
$$

$$
A_2 = \pi d_2^2 / 4 = 314.16\ \text{mm}^2
$$

### 各段应力

$$
\sigma_1 = \frac{P}{A_1},\quad \sigma_2 = \frac{P}{A_2}
$$

### 总伸长量

$$
\Delta L_{\text{total}} = \Delta L_1 + \Delta L_2 = \frac{P L_1}{E A_1} + \frac{P L_2}{E A_2}
$$

## 参考值

| 物理量 | 数值 | 单位 |
|--------|------|------|
| $\sigma_1$ | 63.66 | MPa |
| $\sigma_2$ | 15.92 | MPa |
| $\Delta L_{\text{total}}$ | 0.0454 | mm |

## 参考文献

- 刘鸿文. (2011). *材料力学* (第5版). 第二章 拉伸与压缩.
"""
    csv = """method,sigma1_MPa,sigma2_MPa,delta_total_mm,error_pct,notes
analytic,63.66,15.92,0.0454,,分段叠加法
calculix,,,,,C3D8 三维实体 (to verify)
"""
    return name, md, csv


def _case_pressure_vessel():
    """Thin-walled cylindrical pressure vessel."""
    name = "11_薄壁圆筒压力容器"
    md = r"""# Case 11: 薄壁圆筒压力容器 (Thin-Walled Pressure Vessel)

## 物理问题描述

一个薄壁圆柱形容器，承受内部均匀气压 $p$。两端封头为半球形。计算筒身段的环向应力和轴向应力。

```
          ┌──────────────────────┐
    ══════╡   p (内部气压)       ╞══════
          └──────────────────────┘
          ←───── L ──────→
    r ──→╎               ╎←── t (壁厚)
```

**参数：**

| 参数 | 符号 | 值 | 单位 |
|------|------|-----|------|
| 筒体内径 | r | 200 | mm |
| 壁厚 | t | 4 | mm |
| 筒体长度 | L | 800 | mm |
| 内压 | p | 2.0 | MPa |
| 弹性模量 | E | 210 000 | MPa |
| 泊松比 | ν | 0.3 | — |

## 解析解（薄壁假设，r/t = 50 > 10）

### 环向应力（周向应力）

取半筒截面，力平衡：

$$
\sigma_h = \frac{p \cdot r}{t}
$$

### 轴向应力

取封头截面，力平衡：

$$
\sigma_a = \frac{p \cdot r}{2t}
$$

注意：$\sigma_h = 2\sigma_a$，这是薄壁圆筒的重要特征。

### 径向膨胀（环向应变）

$$
\varepsilon_h = \frac{\sigma_h - \nu \sigma_a}{E},\quad \Delta r = \varepsilon_h \cdot r
$$

## 参考值

| 物理量 | 数值 | 单位 |
|--------|------|------|
| $\sigma_h$（环向） | 100 | MPa |
| $\sigma_a$（轴向） | 50 | MPa |
| $\Delta r$（半径膨胀） | 0.081 | mm |

## 参考文献

- 刘鸿文. (2011). *材料力学* (第5版). 第七章 应力状态与强度理论.
"""
    csv = """method,sigma_hoop_MPa,sigma_axial_MPa,delta_r_mm,error_pct,notes
analytic,100.0,50.0,0.081,,薄壁圆筒公式
calculix,,,,,S4 壳单元 (to verify)
"""
    return name, md, csv


def _case_udl_beam():
    """Simply supported beam with uniform distributed load."""
    name = "12_简支梁均布载荷"
    md = r"""# Case 12: 简支梁均布载荷 (Simply Supported Beam, Uniform Load)

## 物理问题描述

一根等截面矩形梁，两端简支，全跨受均布线载荷 $q$。与 Case 7（集中力）对比，理解不同载荷形式下的内力分布。

```
  q = 2 N/mm (均布)
  ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
  ══════════════════════
  ▲                     ▲
  └──────── L ──────────┘
```

**参数：**

| 参数 | 符号 | 值 | 单位 |
|------|------|-----|------|
| 跨度 | L | 500 | mm |
| 截面宽 | b | 20 | mm |
| 截面高 | h | 30 | mm |
| 弹性模量 | E | 210 000 | MPa |
| 均布线载荷 | q | 2 | N/mm |

## 解析解

### 截面惯性矩

$$
I = \frac{b h^3}{12} = 45\,000\ \text{mm}^4
$$

### 最大弯矩（跨中）

$$
M_{\max} = \frac{q L^2}{8}
$$

### 跨中最大挠度

$$
\delta_{\max} = \frac{5 q L^4}{384 E I}
$$

### 最大正应力（跨中上下表面）

$$
\sigma_{\max} = \frac{M_{\max} \cdot (h/2)}{I}
$$

## 参考值

| 物理量 | 数值 | 单位 |
|--------|------|------|
| $M_{\max}$ | 62 500 | N·mm |
| $\delta_{\max}$ | 约 0.43 | mm |
| $\sigma_{\max}$ | 约 20.8 | MPa |

### 与 Case 7 对比（相同总载荷 P = qL = 1000 N）

| | 均布 qL | 集中力 P |
|--|---------|---------|
| $M_{\max}$ | $qL^2/8$ | $PL/4 = qL^2/4$ |
| $\delta_{\max}$ | $5qL^4/(384EI)$ | $PL^3/(48EI) = qL^4/(48EI)$ |

均布载荷的弯矩和挠度均小于同等总载荷的集中力情况。

## 参考文献

- 刘鸿文. (2011). *材料力学* (第5版). 第四章 弯曲内力.
"""
    csv = """method,delta_max_mm,sigma_max_MPa,error_pct,notes
analytic,0.43,20.8,,简支梁均布载荷公式
calculix,,,,B31 梁单元 (to verify)
"""
    return name, md, csv


def _case_truss():
    """Two-bar truss — statically determinate."""
    name = "13_平面二杆桁架"
    md = r"""# Case 13: 平面二杆桁架 (Two-Bar Plane Truss)

## 物理问题描述

两根等截面杆铰接于一点，上端分别铰支于两侧。铰接点受竖向力 $P$。两杆仅受轴向力（二力杆），是静定桁架的最简模型。

```
      ▲           ▲
       \         /
        \  θ  θ /
         \     /
          \   /
           \ /
            ▼
            P
```

**参数：**

| 参数 | 符号 | 值 | 单位 |
|------|------|-----|------|
| 杆长 | L | 500 | mm |
| 截面积 | A | 100 | mm² |
| 夹角 | θ | 30 | ° |
| 弹性模量 | E | 210 000 | MPa |
| 竖向力 | P | 10 000 | N |

## 解析解

### 节点力平衡（对称结构）

竖向平衡：$2N \sin\theta = P$

$$
N = \frac{P}{2\sin\theta} = \frac{10\,000}{2 \times 0.5} = 10\,000\ \text{N}
$$

### 杆内应力

$$
\sigma = \frac{N}{A}
$$

### 铰点竖向位移

每根杆伸长量：$\Delta L = \frac{N L}{E A}$

由几何关系，铰点竖向位移：

$$
\delta_v = \frac{\Delta L}{\sin\theta}
$$

## 参考值

| 物理量 | 数值 | 单位 |
|--------|------|------|
| 杆内力 $N$ | 10 000 | N |
| 杆应力 $\sigma$ | 100 | MPa |
| 铰点竖向位移 $\delta_v$ | 0.476 | mm |

## 参考文献

- 刘鸿文. (2011). *材料力学* (第5版). 第二章 轴向拉伸.
- 哈尔滨工业大学. (2016). *结构力学*. 高等教育出版社.
"""
    csv = """method,sigma_MPa,delta_v_mm,error_pct,notes
analytic,100.0,0.476,,节点力平衡法
calculix,,,,T3D2 杆单元 (to verify)
"""
    return name, md, csv


# ── Master list ──────────────────────────────────────────────

CASES = [
    _case_torsion,
    _case_simply_supported_beam,
    _case_springs,
    _case_thermal_stress,
    _case_stepped_bar,
    _case_pressure_vessel,
    _case_udl_beam,
    _case_truss,
]


def write_case(case_dir: Path, problem_md: str, comparison_csv: str) -> None:
    """Write a benchmark case with standard directory structure."""
    results_dir = case_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    (case_dir / "问题描述.md").write_text(problem_md, encoding="utf-8")
    (results_dir / "对比结果.csv").write_text(comparison_csv, encoding="utf-8")

    print(f"  OK {case_dir.name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import entry-level benchmark case source files.")
    parser.add_argument("--output-dir", default=str(BENCH_DIR), help="Benchmark output directory.")
    parser.add_argument("--write", action="store_true", help="Write files. Without this flag, only preview.")
    parser.add_argument("--replace", action="store_true", help="Remove existing cases 06-13 before writing.")
    args = parser.parse_args(argv)

    bench_dir = Path(args.output_dir)
    cases = [case_fn() for case_fn in CASES]

    print(f"Benchmark directory: {bench_dir}")
    print(f"Prepared {len(cases)} cases.\n")

    if not args.write:
        for name, _, _ in cases:
            print(f"  DRY {name}")
        print("\nDry run only. Re-run with --write to create files.")
        return 0

    bench_dir.mkdir(parents=True, exist_ok=True)

    if args.replace:
        for num in range(6, 14):
            for entry in bench_dir.iterdir():
                if entry.is_dir() and entry.name.startswith(f"{num:02d}_"):
                    shutil.rmtree(entry)
                    print(f"  RM {entry.name}")

    for name, md, csv in cases:
        case_dir = bench_dir / name
        write_case(case_dir, md, csv)

    print(f"\nDone — {len(cases)} cases processed.")
    print("\nNext: node scripts/build-benchmark-html.js")
    return 0


if __name__ == "__main__":
    sys.exit(main())

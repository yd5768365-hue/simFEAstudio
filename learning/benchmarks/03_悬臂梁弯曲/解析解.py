"""
=============================================================================
  Analytic Solution: Cantilever Beam Bending (Euler-Bernoulli Theory)
  Benchmark Case: cantilever_beam
=============================================================================

  悬臂梁端部受集中力 P, 固支端在 x=0, 自由端在 x=L.

  几何:  L=1000mm, 矩形截面 b×h=20×20mm
  材料:  E=210000MPa, nu=0.3
  载荷:  P=100N (向下, y方向)

  Euler-Bernoulli 梁弯曲方程:
    EI * w''''(x) = 0
    w(0)=0,  w'(0)=0           (固支端)
    M(L)=0,  V(L)=-P            (自由端)

  挠度曲线:
    w(x) = P*x^2/(6*E*I) * (3L - x)

  端部最大位移:
    w(L) = P*L^3 / (3*E*I)     (= 11.9048 mm)

  最大弯曲应力 (固支端顶面):
    sigma_max = M*y/I = P*L*(h/2)/I  (= 75.00 MPa)

  参考:
    Timoshenko & Goodier, Theory of Elasticity, 3rd ed., McGraw-Hill, 1970.
    刘鸿文, 材料力学, 第5版, 高等教育出版社, 2011.
=============================================================================
"""

# ── 几何参数 ─────────────────────────────────────
L = 1000.0       # 梁长 (mm)
b = 20.0          # 截面宽度 (mm)
h = 20.0          # 截面高度 (mm)

# ── 材料参数 ─────────────────────────────────────
E = 210000.0      # 弹性模量 (MPa)
nu = 0.3          # 泊松比 (仅用于 CalculiX 对照)

# ── 载荷 ────────────────────────────────────────
P = 100.0         # 端部集中力 (N, 向下)

# ── 截面属性 ─────────────────────────────────────
# 矩形截面惯性矩: I = b*h^3/12
I = b * h**3 / 12  # = 13333.33 mm^4

# ── 端部位移: w(L) = P*L^3/(3*E*I) ─────────────
w_tip = P * L**3 / (3 * E * I)

# ── 最大应力: sigma_max = M*y/I = P*L*(h/2)/I ──
sigma_max = P * L * (h / 2) / I

# ═════════════════════════════════════════════════════════════════════
print("Cantilever Beam — Analytic Solution (Euler-Bernoulli)")
print("=" * 55)
print(f"  Moment of inertia  I  = {I:10.2f} mm^4")
print(f"  Tip displacement  w(L) = {w_tip:10.4f} mm")
print(f"  Max stress     sigma   = {sigma_max:10.2f} MPa")
print("=" * 55)
print()
print("# Copy this line to results/comparison.csv:")
print(f"analytic,{w_tip:.4f},{sigma_max:.2f},0.0,Euler-Bernoulli beam theory")

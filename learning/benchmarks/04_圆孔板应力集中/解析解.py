"""
=============================================================================
  Analytic Solution: Plate with Circular Hole (Kirsch Solution)
  Benchmark Case: hole_plate
=============================================================================

  矩形平板中心有圆孔, 上下两端受均匀拉伸应力 sigma_0.
  属于 2D 平面应力问题. 孔边产生应力集中.

  几何:  W=100mm, H=200mm, 孔径 d=20mm (d/W=0.2)
  材料:  E=210000MPa, nu=0.3
  载荷:  sigma_0=100MPa (远端均匀拉伸)

  Kirsch 解 (无限大板):
    sigma_thetatheta(r,theta) = sigma_0/2 * (1 + a^2/r^2)
                              - sigma_0/2 * (1 + 3*a^4/r^4) * cos(2*theta)

    孔边 (r=a, theta=90°):
      sigma_max = 3 * sigma_0
      K_t = 3.0

  Heywood 有限宽度修正 (d/W=0.2):
    K_t = 2 + (1 - d/W)^3 = 2.512
    sigma_max = K_t * sigma_0 = 251.2 MPa

  参考:
    Kirsch, G. (1898). VDI-Z, 42, 797-807.
    Peterson, R. E. (1974). Stress Concentration Factors, Wiley.
=============================================================================
"""

# ── 几何参数 ─────────────────────────────────────
W = 100.0        # 板宽 (mm)
H = 200.0        # 板高 (mm)
d = 20.0         # 孔径 (mm)
a = d / 2        # 孔半径 (mm)
t = 1.0          # 板厚 (mm, 平面应力假设下厚度不影响应力)

# ── 材料参数 ─────────────────────────────────────
E = 210000.0     # 弹性模量 (MPa)
nu = 0.3         # 泊松比

# ── 载荷 ────────────────────────────────────────
sigma_0 = 100.0  # 远端均匀拉伸应力 (MPa)

# ═════════════════════════════════════════════════════════════════════
# Kirsch 无限大板解
# ═════════════════════════════════════════════════════════════════════

K_t_inf = 3.0
sigma_max_inf = K_t_inf * sigma_0  # = 300 MPa

# ═════════════════════════════════════════════════════════════════════
# Heywood 有限宽度修正
# ═════════════════════════════════════════════════════════════════════

d_W = d / W  # = 0.2

# Heywood 公式: K_t = 2 + (1 - d/W)^3
K_t_finite = 2.0 + (1.0 - d_W)**3  # ≈ 2.512
sigma_max_finite = K_t_finite * sigma_0  # ≈ 251.2 MPa

# 净截面名义应力
sigma_net = sigma_0 * W / (W - d)  # = 125 MPa

# ═════════════════════════════════════════════════════════════════════
print("Hole-in-Plate — Analytic Solution")
print("=" * 55)
print(f"  d/W ratio          = {d_W:.2f}")
print(f"  K_t (infinite)     = {K_t_inf:.1f}")
print(f"  sigma_max (inf)    = {sigma_max_inf:.0f} MPa")
print(f"  K_t (finite, Heywood) = {K_t_finite:.3f}")
print(f"  sigma_max (finite) = {sigma_max_finite:.1f} MPa")
print(f"  sigma_net          = {sigma_net:.0f} MPa")
print("=" * 55)
print()
print("# Copy these lines to results/comparison.csv:")
print(f"analytic-kirsch,{sigma_max_inf:.1f},{K_t_inf:.1f},,Kirsch infinite-plate")
print(f"analytic-heywood,{sigma_max_finite:.1f},{K_t_finite:.3f},,Heywood d/W={d_W}")

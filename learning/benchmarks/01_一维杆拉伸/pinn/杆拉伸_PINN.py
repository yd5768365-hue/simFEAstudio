"""
=============================================================================
  PINN Solver: 1D Rod Tension (一维杆端部拉伸)
  Benchmark Case: rod_tension
=============================================================================

  物理问题:
    等截面直杆，左端固定 (u=0)，右端受轴向拉力 P。
    L=100mm, A=10mm^2, E=210000MPa, P=1000N.
    控制方程: u''(x)=0,  x in [0, L]
    边界条件: u(0)=0, EA*u'(L)=P
    解析解:  u(L)=PL/EA=0.0476190476mm, sigma=P/A=100MPa

  PINN 方法:
    将物理约束 (PDE + 边界条件) 编码进损失函数，
    用神经网络逼近位移场 u(x)。

  无因次化:
    x_bar = x/L,  u_bar = u/u_ref (u_ref = PL/EA)
    无因次控制方程仍为 u_bar''=0，边界条件变为 u_bar(0)=0, u_bar'(1)=1.

  网络结构: 1→32→32→32→1 (tanh激活)
  训练: 5000 epochs, Adam + ReduceLROnPlateau

  运行:
    python rod_tension_pinn.py
    (需要 PyTorch: conda activate deepxde)

  输出:
    - 位移场对比图: rod_tension_pinn_result.png
    - comparison.csv 行: pinn,<u_L>,<sigma>,<error>,...

  Author: SimFEA Studio Benchmark Lab
  Date: 2026-06-09
=============================================================================
"""

import torch
import torch.nn as nn
import numpy as np
import matplotlib
matplotlib.use('Agg')  # 非交互式后端，保存图片无需 GUI
import matplotlib.pyplot as plt

# ── 全局设置 ─────────────────────────────────────
torch.manual_seed(42)
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f'[PINN] Device: {device}')

# ═══════════════════════════════════════════════════════════════════════════
# 1. 物理参数
# ═══════════════════════════════════════════════════════════════════════════

L   = 100.0       # 杆长 (mm)
A   = 10.0        # 截面积 (mm^2)
E   = 210000.0    # 弹性模量 (MPa)
P   = 1000.0      # 端部拉力 (N)

# 参考位移 — 解析解在自由端 (x=L) 的值
u_ref = P * L / (E * A)         # = 0.0476190476 mm
sigma_analytic = P / A           # = 100 MPa

print(f'[PINN] u_ref = {u_ref:.10f} mm')
print(f'[PINN] sigma_analytic = {sigma_analytic} MPa')

# ═══════════════════════════════════════════════════════════════════════════
# 2. 神经网络定义
# ═══════════════════════════════════════════════════════════════════════════
#
#  输入:   x_bar ∈ [0, 1]  (无因次坐标, 单个标量)
#  输出:   u_bar            (无因次位移, 单个标量)
#  结构:   1 → 32 → 32 → 32 → 1, 激活函数使用 tanh
#          (tanh 是光滑函数, 适合 PINN 的高阶自动微分)
#  参数量: 2209
#

class PINN(nn.Module):
    """Physics-Informed Neural Network for 1D bar displacement field."""

    def __init__(self, hidden: int = 32, layers: int = 3):
        super().__init__()
        # 构建全连接层序列
        seq = [nn.Linear(1, hidden), nn.Tanh()]
        for _ in range(layers - 1):
            seq.extend([nn.Linear(hidden, hidden), nn.Tanh()])
        seq.append(nn.Linear(hidden, 1))
        self.net = nn.Sequential(*seq)

        # Xavier 初始化 — 让每层输出的方差保持一致
        for m in self.net:
            if isinstance(m, nn.Linear):
                nn.init.xavier_normal_(m.weight)
                nn.init.zeros_(m.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


model = PINN(hidden=32, layers=3).to(device)
n_params = sum(p.numel() for p in model.parameters())
print(f'[PINN] Model parameters: {n_params}')

# ═══════════════════════════════════════════════════════════════════════════
# 3. 损失函数 (核心 — PINN 的物理约束)
# ═══════════════════════════════════════════════════════════════════════════
#
#  总损失 = L_pde + λ_bc * L_bc + λ_force * L_force
#
#  L_pde:   PDE 残差 |u_bar''|^2 在内部配点上的均值
#           方程 u_bar''=0 说明位移是线性函数
#
#  L_bc:    Dirichlet 边界条件 u_bar(0)=0
#           左端固定 — 位移为零
#
#  L_force: Neumann 边界条件 u_bar'(1)=1
#           右端受力 — 应变等于 P/EA (无因次化后变为 1)
#
#  lambda 权重用于平衡不同损失项的量级
#

def compute_loss(model, x_interior, x_bc):
    """计算 PDE 残差和边界条件损失。"""

    # ── PDE 残差: u''(x) = 0 ──
    # 需要二阶导数，所以 requires_grad_ 后做两次 backward
    x = x_interior.clone().requires_grad_(True)
    u = model(x)

    # 一阶导: du/dx
    u_x = torch.autograd.grad(
        u, x, torch.ones_like(u),
        create_graph=True  # 保留计算图以计算二阶导
    )[0]

    # 二阶导: d^2u/dx^2
    u_xx = torch.autograd.grad(
        u_x, x, torch.ones_like(u_x),
        create_graph=True
    )[0]

    loss_pde = (u_xx ** 2).mean()  # PDE 残差的均方值

    # ── Dirichlet BC: u(0) = 0 ──
    u_at_0 = model(x_bc[0:1])       # x=0 处
    loss_bc = u_at_0.pow(2).mean()  # u(0) 应该为 0

    # ── Neumann BC: u'(1) = 1 ──
    x_end = x_bc[1:2].clone().requires_grad_(True)
    u_end = model(x_end)
    u_x_end = torch.autograd.grad(
        u_end, x_end, torch.ones_like(u_end),
        create_graph=True
    )[0]
    loss_force = ((u_x_end - 1.0) ** 2).mean()  # u'(1) 应该为 1

    return loss_pde, loss_bc, loss_force

# ═══════════════════════════════════════════════════════════════════════════
# 4. 训练
# ═══════════════════════════════════════════════════════════════════════════
#
#  配点策略:
#    - 内部配点: 100 个均匀分布在 [0, 1]
#    - 边界配点: x=0 (Dirichlet) 和 x=1 (Neumann)
#
#  优化器: Adam (lr=1e-3) + ReduceLROnPlateau
#    - patience=500: 500 个 epoch 无改善则降低学习率
#    - factor=0.5:   学习率减半
#    - min_lr=1e-6:  学习率下限
#
#  损失权重:
#    - lambda_bc = 10:   Dirichlet 条件权重较高
#    - lambda_force = 10: Neumann 条件权重较高
#

# 配点
N_interior = 100
x_interior = torch.linspace(0, 1, N_interior).view(-1, 1).to(device)
x_bc = torch.tensor([[0.0], [1.0]], device=device)

# 优化器与调度器
optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
    optimizer, patience=500, factor=0.5, min_lr=1e-6
)

# 损失权重
lambda_bc    = 10.0   # Dirichlet BC 权重
lambda_force = 10.0   # Neumann BC 权重

# 训练历史记录
history = {'epoch': [], 'loss': [], 'pde': [], 'bc': [], 'force': []}

EPOCHS = 5000
print(f'[PINN] Training {EPOCHS} epochs...')

for epoch in range(EPOCHS):
    optimizer.zero_grad()

    # 前向 + 损失计算
    loss_pde, loss_bc, loss_force = compute_loss(model, x_interior, x_bc)
    loss_total = loss_pde + lambda_bc * loss_bc + lambda_force * loss_force

    # 反向传播
    loss_total.backward()
    optimizer.step()
    scheduler.step(loss_total)

    # 每 500 步记录
    if epoch % 500 == 0:
        history['epoch'].append(epoch)
        history['loss'].append(loss_total.item())
        history['pde'].append(loss_pde.item())
        history['bc'].append(loss_bc.item())
        history['force'].append(loss_force.item())
        print(f'  {epoch:5d} | Loss {loss_total.item():.2e}'
              f' | PDE {loss_pde.item():.2e}'
              f' | BC {loss_bc.item():.2e}'
              f' | Force {loss_force.item():.2e}')

print(f'[PINN] Final loss: {loss_total.item():.2e}')

# ═══════════════════════════════════════════════════════════════════════════
# 5. 结果验证
# ═══════════════════════════════════════════════════════════════════════════
#
#  用训练好的模型在 [0,1] 上密集采样 (1001 个点)，
#  将无因次结果还原为物理量，与解析解对比。
#

model.eval()
with torch.no_grad():
    x_test = torch.linspace(0, 1, 1001).view(-1, 1).to(device)
    u_pred_nd = model(x_test).cpu().numpy().flatten()

# 还原为物理单位
x_phys  = x_test.cpu().numpy().flatten() * L        # mm
u_pred  = u_pred_nd * u_ref                          # mm
u_exact = (P / (E * A)) * x_phys                     # mm, 线性分布

# 自由端结果
u_L_pinn    = float(u_pred[-1])
u_L_exact   = u_ref
abs_error   = abs(u_L_pinn - u_L_exact)
rel_error   = abs_error / u_L_exact

print('=' * 55)
print('  PINN Results — 1D Rod Tension')
print('=' * 55)
print(f'  u(L) PINN          = {u_L_pinn:.10f} mm')
print(f'  u(L) Exact         = {u_L_exact:.10f} mm')
print(f'  Absolute error     = {abs_error:.2e} mm')
print(f'  Relative error     = {rel_error:.2e} ({rel_error*100:.4f}%)')
print(f'  sigma (uniform)    = {sigma_analytic} MPa')
print('=' * 55)

# ── comparison.csv 输出 ──
print()
print('# Copy this line to results/comparison.csv:')
print(f'pinn,{u_L_pinn:.10f},,{rel_error:.2e},PyTorch PINN {EPOCHS} epochs')

# ═══════════════════════════════════════════════════════════════════════════
# 6. 可视化
# ═══════════════════════════════════════════════════════════════════════════

fig, axes = plt.subplots(1, 2, figsize=(12, 4))

# 左图: 位移场对比
ax1 = axes[0]
ax1.plot(x_phys, u_exact, 'k-',  linewidth=2.0, label='Exact (linear)')
ax1.plot(x_phys, u_pred,  'r--', linewidth=1.5, label=f'PINN (err={rel_error:.2e})')
ax1.set_xlabel('x (mm)')
ax1.set_ylabel('u (mm)')
ax1.set_title('Displacement Field: u(x)')
ax1.legend()
ax1.grid(True, alpha=0.3)

# 右图: 逐点误差 (对数坐标)
ax2 = axes[1]
ax2.semilogy(x_phys, np.abs(u_pred - u_exact), 'r-', linewidth=1.0)
ax2.set_xlabel('x (mm)')
ax2.set_ylabel('|u_pred - u_exact| (mm)')
ax2.set_title('Pointwise Absolute Error (log scale)')
ax2.grid(True, alpha=0.3)

plt.tight_layout()

import os
out_dir = os.path.dirname(os.path.abspath(__file__))
out_path = os.path.join(out_dir, 'rod_tension_pinn_result.png')
plt.savefig(out_path, dpi=120, bbox_inches='tight')
print(f'[PINN] Plot saved: {out_path}')

"""
Coupling 耦合模块

提供运动耦合、分布耦合和 MPC（多点约束）功能。

类层次：
  Coupling     # 耦合（运动/分布）
  Mpc          # 多点约束

参考 pygccx model_keywords/coupling.py, mpc.py 设计
"""
from __future__ import annotations

from cae_preflight_lib.coupling.coupling import Coupling
from cae_preflight_lib.coupling.mpc import Mpc

__all__ = [
    "Coupling",
    "Mpc",
]

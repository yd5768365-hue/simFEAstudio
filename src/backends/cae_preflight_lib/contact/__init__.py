"""
Contact 接触模块

提供接触对、绑定、摩擦、间隙等接触相关类的实现。

类层次：
  SurfaceInteraction     # 表面相互作用
    ├── SurfaceBehavior  # 表面行为（压力-间隙）
    └── Friction         # 摩擦

  ContactPair           # 接触对
  Tie                   # 绑定接触
  Gap                   # 间隙单元（节点对）
  GapUnit               # 间隙单元（单元方式）

参考 pygccx model_keywords/contact_*.py 设计
"""
from __future__ import annotations

from cae_preflight_lib.contact.surface_interaction import SurfaceInteraction
from cae_preflight_lib.contact.surface_behavior import SurfaceBehavior
from cae_preflight_lib.contact.friction import Friction
from cae_preflight_lib.contact.contact_pair import ContactPair
from cae_preflight_lib.contact.tie import Tie
from cae_preflight_lib.contact.gap import Gap, GapUnit

__all__ = [
    "SurfaceInteraction",
    "SurfaceBehavior",
    "Friction",
    "ContactPair",
    "Tie",
    "Gap",
    "GapUnit",
]

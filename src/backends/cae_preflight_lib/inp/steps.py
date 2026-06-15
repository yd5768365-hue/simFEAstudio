"""
INP 载荷步 Python 类封装

提供类型安全的载荷步类层次结构，替代简单的 create_step() 函数。

类层次：
  StepBase (基类)
    ├── StaticStep      # 静力学
    ├── DynamicStep     # 动力学
    ├── FrequencyStep   # 模态分析
    ├── BuckleStep      # 屈曲分析
    ├── ThermalStep     # 热分析
    └── ViscoStep       # 粘塑性

参考 pygccx step_keywords/ 设计
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any

from cae_preflight_lib._utils import f2s


# =============================================================================
# Step 基类
# =============================================================================

@dataclass
class StepBase(ABC):
    """
    载荷步基类。

    提供通用的 step 属性和抽象方法。

    Attributes:
        nlgeom: 是否启用几何非线性（True/False/None）
        inc: 最大增量步数
        amplitude: 载荷幅值类型（RAMP/STEP）
        perturbation: 是否使用上一个非扰动步作为预加载
        desc: 描述文本
        step_keywords: 内嵌的 step keywords（如 BOUNDARY, CLOAD 等）
    """

    nlgeom: Optional[bool] = None
    """是否启用几何非线性"""
    inc: int = 100
    """最大增量步数"""
    amplitude: str = "RAMP"
    """载荷幅值类型：RAMP（逐步加载）或 STEP（瞬时加载）"""
    perturbation: bool = False
    """是否使用上一个非扰动步作为预加载"""
    desc: str = ""
    """描述文本"""
    step_keywords: list[Any] = field(default_factory=list, init=False)
    """内嵌的 step keywords"""

    def __post_init__(self):
        if self.inc < 1:
            raise ValueError(f"inc must be >= 1, got {self.inc}")

    def add_keyword(self, kw: Any) -> None:
        """添加 step keyword（如 Boundary, Load 等）。"""
        self.step_keywords.append(kw)

    @property
    @abstractmethod
    def step_type(self) -> str:
        """返回 step 类型标识（*STATIC, *DYNAMIC 等）。"""
        pass

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = []

        # STEP 行
        line = self.step_type
        if self.perturbation:
            line += ",PERTURBATION"
        if self.nlgeom is not None:
            line += ",NLGEOM" if self.nlgeom else ",NLGEOM=NO"
        if self.inc != 100:
            line += f",INC={self.inc}"
        if self.amplitude != "RAMP":
            line += f",AMPLITUDE={self.amplitude}"
        lines.append(line)

        # 内嵌 keywords
        for kw in self.step_keywords:
            if hasattr(kw, "to_inp_lines"):
                lines.extend(kw.to_inp_lines())
            elif isinstance(kw, str):
                lines.append(kw)

        lines.append("")
        return lines

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())


# =============================================================================
# Static Step
# =============================================================================

@dataclass
class StaticStep(StepBase):
    """
    静力学分析步。

    *STATIC

    Attributes:
        direct: 是否使用直接时间步进（关闭自动时间步）
        time_period: 步时间周期
        init_time_inc: 初始时间增量
        min_time_inc: 最小时间增量
        max_time_inc: 最大时间增量
        time_reset: 是否重置总时间
        total_time_at_start: 步开始时的总时间
    """

    direct: bool = False
    """是否使用直接时间步进"""
    time_period: float = 1.0
    """步时间周期"""
    init_time_inc: float = 1.0
    """初始时间增量"""
    min_time_inc: Optional[float] = None
    """最小时间增量"""
    max_time_inc: Optional[float] = None
    """最大时间增量"""
    time_reset: bool = False
    """是否重置总时间"""
    total_time_at_start: Optional[float] = None
    """步开始时的总时间"""

    @property
    def step_type(self) -> str:
        return "*STATIC"

    def to_inp_lines(self) -> list[str]:
        lines = []

        # STEP 行
        line = self.step_type
        if self.perturbation:
            line += ",PERTURBATION"
        if self.nlgeom is not None:
            line += ",NLGEOM" if self.nlgeom else ",NLGEOM=NO"
        if self.inc != 100:
            line += f",INC={self.inc}"
        if self.time_reset:
            line += ",TIME RESET"
        if self.total_time_at_start is not None:
            line += f",TOTAL TIME AT START={f2s(self.total_time_at_start)}"
        lines.append(line)

        # 数据行
        data_parts = [f2s(self.init_time_inc), f2s(self.time_period)]
        if self.min_time_inc is not None:
            data_parts.append(f2s(self.min_time_inc))
        if self.max_time_inc is not None:
            data_parts.append(f2s(self.max_time_inc))
        lines.append(",".join(data_parts))

        # 内嵌 keywords
        for kw in self.step_keywords:
            if hasattr(kw, "to_inp_lines"):
                lines.extend(kw.to_inp_lines())
            elif isinstance(kw, str):
                lines.append(kw)

        lines.append("")
        return lines


# =============================================================================
# Dynamic Step
# =============================================================================

@dataclass
class DynamicStep(StepBase):
    """
    动力学分析步。

    *DYNAMIC

    Attributes:
        direct: 是否使用直接时间步进
        time_period: 步时间周期
        init_time_inc: 初始时间增量
        min_time_inc: 最小时间增量
        max_time_inc: 最大时间增量
    """

    direct: bool = False
    """是否使用直接时间步进"""
    time_period: float = 1.0
    """步时间周期"""
    init_time_inc: float = 1.0
    """初始时间增量"""
    min_time_inc: Optional[float] = None
    """最小时间增量"""
    max_time_inc: Optional[float] = None
    """最大时间增量"""

    @property
    def step_type(self) -> str:
        return "*DYNAMIC"

    def to_inp_lines(self) -> list[str]:
        lines = []

        # STEP 行
        line = self.step_type
        if self.perturbation:
            line += ",PERTURBATION"
        if self.nlgeom is not None:
            line += ",NLGEOM" if self.nlgeom else ",NLGEOM=NO"
        if self.inc != 100:
            line += f",INC={self.inc}"
        if self.direct:
            line += ",DIRECT"
        lines.append(line)

        # 数据行
        data_parts = [f2s(self.init_time_inc), f2s(self.time_period)]
        if self.min_time_inc is not None:
            data_parts.append(f2s(self.min_time_inc))
        if self.max_time_inc is not None:
            data_parts.append(f2s(self.max_time_inc))
        lines.append(",".join(data_parts))

        # 内嵌 keywords
        for kw in self.step_keywords:
            if hasattr(kw, "to_inp_lines"):
                lines.extend(kw.to_inp_lines())
            elif isinstance(kw, str):
                lines.append(kw)

        lines.append("")
        return lines


# =============================================================================
# Frequency Step
# =============================================================================

@dataclass
class FrequencyStep(StepBase):
    """
    模态分析步。

    *FREQUENCY

    Attributes:
        solver: 求解器类型
        storage: 是否存储特征值和模态
        global_coords: 是否使用全局坐标系
        cycmpc: 循环多点约束是否激活
        alpha: 数值阻尼参数（-1/3 到 0）
        no_frequencies: 请求的特征值数量
        lower_frequency: 频率范围下限
        upper_frequency: 频率范围上限
    """

    solver: str = "DEFAULT"
    """求解器"""
    storage: bool = False
    """是否存储特征值和模态"""
    global_coords: bool = True
    """是否使用全局坐标系"""
    cycmpc: bool = True
    """循环多点约束是否激活"""
    alpha: Optional[float] = None
    """数值阻尼参数（-1/3 到 0）"""
    no_frequencies: int = 1
    """请求的特征值数量"""
    lower_frequency: Optional[float] = None
    """频率范围下限"""
    upper_frequency: Optional[float] = None
    """频率范围上限"""

    def __post_init__(self):
        super().__post_init__()
        if self.alpha is not None:
            if self.alpha < -1/3 or self.alpha > 0:
                raise ValueError(f"alpha must be between -1/3 and 0, got {self.alpha}")

    @property
    def step_type(self) -> str:
        return "*FREQUENCY"

    def to_inp_lines(self) -> list[str]:
        lines = []

        # STEP 行
        line = self.step_type
        if self.solver != "DEFAULT":
            line += f",SOLVER={self.solver}"
        if self.storage:
            line += ",STORAGE=YES"
        if not self.global_coords:
            line += ",GLOBAL=NO"
        if not self.cycmpc:
            line += ",CYCMPC=INACTIVE"
        if self.alpha is not None:
            line += f",ALPHA={f2s(self.alpha)}"
        lines.append(line)

        # 数据行
        data_parts = [str(self.no_frequencies)]
        if self.lower_frequency is not None:
            data_parts.append(f2s(self.lower_frequency))
        if self.upper_frequency is not None:
            data_parts.append(f2s(self.upper_frequency))
        lines.append(",".join(data_parts))

        # 内嵌 keywords
        for kw in self.step_keywords:
            if hasattr(kw, "to_inp_lines"):
                lines.extend(kw.to_inp_lines())
            elif isinstance(kw, str):
                lines.append(kw)

        lines.append("")
        return lines


# =============================================================================
# Buckle Step
# =============================================================================

@dataclass
class BuckleStep(StepBase):
    """
    屈曲分析步。

    *BUCKLE

    Attributes:
        solver: 求解器类型
        no_buckling_factors: 请求的屈曲因子数量
        accuracy: 精度
        no_lanczos_vectors: Lanczos 向量数量
        max_iterations: 最大迭代次数
    """

    solver: str = "DEFAULT"
    """求解器"""
    no_buckling_factors: int = 1
    """请求的屈曲因子数量"""
    accuracy: Optional[float] = None
    """精度"""
    no_lanczos_vectors: Optional[int] = None
    """Lanczos 向量数量"""
    max_iterations: Optional[int] = None
    """最大迭代次数"""

    @property
    def step_type(self) -> str:
        return "*BUCKLE"

    def to_inp_lines(self) -> list[str]:
        lines = []

        # STEP 行
        line = self.step_type
        if self.solver != "DEFAULT":
            line += f",SOLVER={self.solver}"
        lines.append(line)

        # 数据行
        data_parts = [str(self.no_buckling_factors)]
        if self.accuracy is not None:
            data_parts.append(f2s(self.accuracy))
        if self.no_lanczos_vectors is not None:
            data_parts.append(str(self.no_lanczos_vectors))
        if self.max_iterations is not None:
            data_parts.append(str(self.max_iterations))
        lines.append(",".join(data_parts))

        # 内嵌 keywords
        for kw in self.step_keywords:
            if hasattr(kw, "to_inp_lines"):
                lines.extend(kw.to_inp_lines())
            elif isinstance(kw, str):
                lines.append(kw)

        lines.append("")
        return lines


# =============================================================================
# Thermal Step
# =============================================================================

@dataclass
class ThermalStep(StepBase):
    """
    热分析步。

    *HEAT TRANSFER（稳态或瞬态）

    Attributes:
        time_period: 步时间周期（瞬态热分析）
        init_time_inc: 初始时间增量
        min_time_inc: 最小时间增量
        max_time_inc: 最大时间增量
    """

    time_period: float = 1.0
    """步时间周期"""
    init_time_inc: float = 1.0
    """初始时间增量"""
    min_time_inc: Optional[float] = None
    """最小时间增量"""
    max_time_inc: Optional[float] = None
    """最大时间增量"""

    @property
    def step_type(self) -> str:
        return "*HEAT TRANSFER"

    def to_inp_lines(self) -> list[str]:
        lines = []

        # STEP 行
        line = self.step_type
        if self.perturbation:
            line += ",PERTURBATION"
        if self.nlgeom is not None:
            line += ",NLGEOM" if self.nlgeom else ",NLGEOM=NO"
        if self.inc != 100:
            line += f",INC={self.inc}"
        lines.append(line)

        # 数据行
        data_parts = [f2s(self.init_time_inc), f2s(self.time_period)]
        if self.min_time_inc is not None:
            data_parts.append(f2s(self.min_time_inc))
        if self.max_time_inc is not None:
            data_parts.append(f2s(self.max_time_inc))
        lines.append(",".join(data_parts))

        # 内嵌 keywords
        for kw in self.step_keywords:
            if hasattr(kw, "to_inp_lines"):
                lines.extend(kw.to_inp_lines())
            elif isinstance(kw, str):
                lines.append(kw)

        lines.append("")
        return lines


# =============================================================================
# 便捷函数（兼容旧 API）
# =============================================================================

def create_static_step(
    nlgeom: bool = False,
    inc: int = 100,
    time_period: float = 1.0,
    init_time_inc: float = 1.0,
) -> StaticStep:
    """
    创建静力学分析步。

    兼容旧 API。
    """
    return StaticStep(nlgeom=nlgeom, inc=inc, time_period=time_period, init_time_inc=init_time_inc)


def create_dynamic_step(
    nlgeom: bool = False,
    inc: int = 100,
    time_period: float = 1.0,
    init_time_inc: float = 1.0,
) -> DynamicStep:
    """
    创建动力学分析步。
    """
    return DynamicStep(nlgeom=nlgeom, inc=inc, time_period=time_period, init_time_inc=init_time_inc)


def create_frequency_step(
    nlgeom: bool = False,
    inc: int = 100,
    no_frequencies: int = 1,
) -> FrequencyStep:
    """
    创建模态分析步。
    """
    return FrequencyStep(nlgeom=nlgeom, inc=inc, no_frequencies=no_frequencies)


def create_buckle_step(
    nlgeom: bool = False,
    inc: int = 100,
    no_buckling_factors: int = 1,
) -> BuckleStep:
    """
    创建屈曲分析步。
    """
    return BuckleStep(nlgeom=nlgeom, inc=inc, no_buckling_factors=no_buckling_factors)

# BaseSolver 抽象类
"""
BaseSolver 抽象基类
新增求解器只需继承此类并在 registry.py 注册一行。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SolveResult:
    """求解器返回结果的统一数据结构。"""

    success: bool
    output_dir: Path
    output_files: list[Path]
    stdout: str
    stderr: str
    returncode: int
    duration_seconds: float
    error_message: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # 便利属性
    # ------------------------------------------------------------------ #

    @property
    def frd_file(self) -> Optional[Path]:
        """CalculiX 结果文件 (.frd)"""
        for f in self.output_files:
            if f.suffix == ".frd":
                return f
        return None

    @property
    def dat_file(self) -> Optional[Path]:
        """CalculiX 数据文件 (.dat)"""
        for f in self.output_files:
            if f.suffix == ".dat":
                return f
        return None

    @property
    def duration_str(self) -> str:
        s = self.duration_seconds
        if s < 60:
            return f"{s:.1f}s"
        m, sec = divmod(int(s), 60)
        return f"{m}m {sec}s"


class BaseSolver(ABC):
    """
    所有求解器的抽象基类。

    子类必须实现：
        - check_installation() → bool
        - get_version()        → Optional[str]
        - solve()              → SolveResult
        - supported_formats()  → list[str]
    """

    #: 在 registry 中注册时使用的名称，子类必须覆盖
    name: str = ""
    #: 人类可读的描述
    description: str = ""

    # ------------------------------------------------------------------ #
    # 抽象接口
    # ------------------------------------------------------------------ #

    @abstractmethod
    def check_installation(self) -> bool:
        """检查求解器二进制文件是否可用。"""
        ...

    @abstractmethod
    def get_version(self) -> Optional[str]:
        """返回求解器版本字符串，无法获取时返回 None。"""
        ...

    @abstractmethod
    def solve(
        self,
        inp_file: Path,
        output_dir: Path,
        *,
        timeout: int = 3600,
        **kwargs,
    ) -> SolveResult:
        """
        执行仿真求解。

        Args:
            inp_file:   输入文件路径（.inp 或其他格式）
            output_dir: 结果输出目录，不存在时自动创建
            timeout:    超时秒数，默认 1 小时
            **kwargs:   求解器特定参数

        Returns:
            SolveResult 数据类
        """
        ...

    @abstractmethod
    def supported_formats(self) -> list[str]:
        """返回支持的输入文件扩展名列表，如 ['.inp']。"""
        ...

    # ------------------------------------------------------------------ #
    # 公共工具方法
    # ------------------------------------------------------------------ #

    def validate_input(self, inp_file: Path) -> tuple[bool, str]:
        """
        前置校验输入文件。
        返回 (ok, error_message)。
        """
        if not inp_file.exists():
            return False, f"文件不存在: {inp_file}"
        if not inp_file.is_file():
            return False, f"路径不是文件: {inp_file}"
        if inp_file.suffix not in self.supported_formats():
            fmts = ", ".join(self.supported_formats())
            return False, f"不支持的格式 '{inp_file.suffix}'，{self.name} 支持: {fmts}"
        return True, ""

    def __repr__(self) -> str:  # pragma: no cover
        installed = "Y" if self.check_installation() else "N"
        return f"<Solver name={self.name!r} installed={installed}>"

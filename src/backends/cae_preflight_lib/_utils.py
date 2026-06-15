"""
通用工具函数

提供项目范围内使用的辅助函数。
"""
from __future__ import annotations

from typing import Union


Number = Union[int, float]


def f2s(x: Number) -> str:
    """
    将数字格式化为字符串（7位指数格式）。

    用于生成精确格式化的数字输出，适合写入 INP 文件。

    Args:
        x: 数值（int 或 float）

    Returns:
        格式化字符串，如 "1.2345678e+00"

    Example:
        >>> f2s(1.5)
        '1.5000000e+00'
        >>> f2s(0.001234567)
        '1.2345670e-03'
    """
    return f"{x:.7e}"

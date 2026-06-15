# _utils.py
"""
Viewer 模块共享工具函数
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import numpy as np


# 预编译正则表达式（避免循环中重复编译）
_NUMBER_PATTERN = re.compile(r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?")


def von_mises(stress: np.ndarray) -> np.ndarray:
    """
    从 6 分量 Cauchy/Voigt 应力张量计算 Von Mises 等效应力。

    应力顺序：S11, S22, S33, S12, S13, S23

    Args:
        stress: (N, 6) 的应力数组

    Returns:
        (N,) 的 Von Mises 应力数组
    """
    s11, s22, s33 = stress[:, 0], stress[:, 1], stress[:, 2]
    s12, s13, s23 = stress[:, 3], stress[:, 4], stress[:, 5]
    return np.sqrt(0.5 * (
        (s11 - s22) ** 2 +
        (s22 - s33) ** 2 +
        (s33 - s11) ** 2 +
        6.0 * (s12 ** 2 + s13 ** 2 + s23 ** 2)
    ))


# ------------------------------------------------------------------ #
# 应力计算工具（借鉴 pygccx stress_tools）
# 应力顺序：S11, S22, S33, S12, S13, S23 (Voigt notation)
# ------------------------------------------------------------------ #

def _voigt_to_tensor(stress: np.ndarray) -> np.ndarray:
    """
    将 Voigt 应力数组转换为 3x3 对称张量。

    Args:
        stress: (N, 6) 的应力数组

    Returns:
        (N, 3, 3) 的对称张量数组
    """
    tensor = np.zeros((*stress.shape[:-1], 3, 3), dtype=stress.dtype)
    tensor[..., 0, 0] = stress[..., 0]  # S11
    tensor[..., 1, 1] = stress[..., 1]  # S22
    tensor[..., 2, 2] = stress[..., 2]  # S33
    tensor[..., 0, 1] = stress[..., 3]  # S12
    tensor[..., 1, 0] = stress[..., 3]
    tensor[..., 0, 2] = stress[..., 4]  # S13
    tensor[..., 2, 0] = stress[..., 4]
    tensor[..., 1, 2] = stress[..., 5]  # S23
    tensor[..., 2, 1] = stress[..., 5]
    return tensor


def get_principal_stresses(stress: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    计算主应力和主方向。

    使用特征值分解计算主应力，结果按降序排列。

    Args:
        stress: (N, 6) 的应力数组，顺序 S11, S22, S33, S12, S13, S23

    Returns:
        (N, 3) 主应力数组（σ1 ≥ σ2 ≥ σ3，降序排列）
        (N, 3, 3) 主方向数组（列向量是对应特征方向）
    """
    tensors = _voigt_to_tensor(stress)  # (N, 3, 3)

    n = stress.shape[0]
    eigenvalues = np.zeros((n, 3))
    eigenvectors = np.zeros((n, 3, 3))

    for i in range(n):
        eigvals, eigvecs = np.linalg.eigh(tensors[i])
        # eigh 返回升序，需要反转
        eigenvalues[i] = eigvals[::-1]
        eigenvectors[i] = eigvecs[:, ::-1]

    return eigenvalues, eigenvectors


def get_principal_shear_stresses(stress: np.ndarray) -> np.ndarray:
    """
    计算三个主剪切应力。

    主剪切应力公式：
        τ12 = |σ1 - σ2| / 2
        τ13 = |σ1 - σ3| / 2
        τ23 = |σ2 - σ3| / 2

    Args:
        stress: (N, 6) 的应力数组

    Returns:
        (N, 3) 的主剪切应力数组 [τ12, τ13, τ23]
    """
    principal, _ = get_principal_stresses(stress)
    sigma1, sigma2, sigma3 = principal[:, 0], principal[:, 1], principal[:, 2]

    tau12 = np.abs(sigma1 - sigma2) / 2.0
    tau13 = np.abs(sigma1 - sigma3) / 2.0
    tau23 = np.abs(sigma2 - sigma3) / 2.0

    return np.stack([tau12, tau13, tau23], axis=1)


def get_max_shear_stress(stress: np.ndarray) -> np.ndarray:
    """
    计算最大剪切应力。

    Args:
        stress: (N, 6) 的应力数组

    Returns:
        (N,) 的最大剪切应力数组
    """
    shear = get_principal_shear_stresses(stress)
    return np.max(shear, axis=1)


def get_worst_principal_stress(stress: np.ndarray) -> np.ndarray:
    """
    计算最不利主应力（绝对值最大者）。

    用于最大主应力失效理论判断。

    Args:
        stress: (N, 6) 的应力数组

    Returns:
        (N,) 的最不利主应力数组
    """
    principal, _ = get_principal_stresses(stress)
    sigma1, sigma3 = principal[:, 0], principal[:, 2]

    # 最不利 = max(|σ1|, |σ3|)，因为 σ1 ≥ σ2 ≥ σ3
    worst = np.copy(sigma1)
    mask = np.abs(sigma3) > np.abs(sigma1)
    worst[mask] = sigma3[mask]
    return worst


def get_stress_invariants(stress: np.ndarray) -> dict[str, np.ndarray]:
    """
    计算应力不变量 I1, I2, I3。

    用于应力分析的后处理。

    Args:
        stress: (N, 6) 的应力数组

    Returns:
        包含 I1, I2, I3 的字典
    """
    s11, s22, s33 = stress[:, 0], stress[:, 1], stress[:, 2]
    s12, s13, s23 = stress[:, 3], stress[:, 4], stress[:, 5]

    # 第一不变量：I1 = σ11 + σ22 + σ33
    I1 = s11 + s22 + s33

    # 第二不变量：I2 = σ11*σ22 + σ22*σ33 + σ33*σ11 - σ12² - σ13² - σ23²
    I2 = s11 * s22 + s22 * s33 + s33 * s11 - s12 ** 2 - s13 ** 2 - s23 ** 2

    # 第三不变量：I3 = det(σ)
    # = σ11*σ22*σ33 + 2*σ12*σ13*σ23 - σ11*σ23² - σ22*σ13² - σ33*σ12²
    I3 = (
        s11 * s22 * s33
        + 2.0 * s12 * s13 * s23
        - s11 * s23 ** 2
        - s22 * s13 ** 2
        - s33 * s12 ** 2
    )

    return {"I1": I1, "I2": I2, "I3": I3}


def parse_numbers(line: str) -> list[float]:
    """
    从文本行中解析所有数字（处理科学计数法和连在一起的情况）。

    Args:
        line: 文本行

    Returns:
        解析出的数字列表
    """
    matches = _NUMBER_PATTERN.findall(line)
    numbers = []
    for m in matches:
        try:
            numbers.append(float(m))
        except ValueError:
            pass
    return numbers


def find_frd(results_dir: Path) -> Optional[Path]:
    """
    在目录中查找第一个 .frd 文件。

    Args:
        results_dir: 结果目录

    Returns:
        .frd 文件路径，或 None
    """
    frd_files = sorted(results_dir.glob("*.frd"))
    return frd_files[0] if frd_files else None

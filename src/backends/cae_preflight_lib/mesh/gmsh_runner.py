# gmsh 网格生成
"""
Gmsh 网格划分封装
将 STEP / BREP / IGES 几何文件划分为有限元网格，输出 .inp 或 .msh 文件。

精度预设（characteristic length factor）：
  coarse  → lc_factor = 1.0（最粗）
  medium  → lc_factor = 0.5
  fine    → lc_factor = 0.25（最细）
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# 公共数据结构
# ------------------------------------------------------------------ #

class MeshQuality(str, Enum):
    COARSE = "coarse"
    MEDIUM = "medium"
    FINE   = "fine"

    @property
    def lc_factor(self) -> float:
        return {"coarse": 1.0, "medium": 0.5, "fine": 0.25}[self.value]

    @property
    def label_cn(self) -> str:
        return {"coarse": "粗糙", "medium": "中等", "fine": "精细"}[self.value]


@dataclass
class MeshResult:
    success: bool
    mesh_file: Optional[Path] = None
    inp_file: Optional[Path] = None     # CalculiX .inp 格式（经 converter 转换）
    error: Optional[str] = None
    duration_seconds: float = 0.0
    node_count: int = 0
    element_count: int = 0
    quality: Optional[MeshQuality] = None
    warnings: list[str] = field(default_factory=list)

    @property
    def duration_str(self) -> str:
        s = self.duration_seconds
        return f"{s:.1f}s" if s < 60 else f"{int(s)//60}m {int(s)%60}s"


# ------------------------------------------------------------------ #
# 支持的几何格式
# ------------------------------------------------------------------ #

SUPPORTED_GEO_FORMATS = {
    ".step": "STEP",
    ".stp":  "STEP",
    ".brep": "BREP/OCC",
    ".iges": "IGES",
    ".igs":  "IGES",
    ".geo":  "Gmsh geometry script",
    ".stl":  "STL surface",
}

SUPPORTED_MESH_FORMATS = {
    ".msh":  "Gmsh native format",
    ".inp":  "Abaqus / CalculiX",
    ".vtk":  "Legacy VTK",
    ".vtu":  "VTK XML Unstructured Grid",
}


def check_gmsh() -> bool:
    """检查 gmsh Python 包是否可用。"""
    try:
        import gmsh  # noqa: F401
        return True
    except ImportError:
        return False


def get_gmsh_version() -> Optional[str]:
    try:
        import gmsh
        return gmsh.__version__
    except (ImportError, AttributeError):
        return None


# ------------------------------------------------------------------ #
# 核心网格划分
# ------------------------------------------------------------------ #

def mesh_geometry(
    geo_file: Path,
    output_dir: Path,
    quality: MeshQuality = MeshQuality.MEDIUM,
    output_format: str = ".msh",
    element_order: int = 1,
    optimize: bool = True,
    timeout: int = 600,
) -> MeshResult:
    """
    用 Gmsh 将几何文件划分网格。

    Args:
        geo_file:      输入几何文件（.step / .brep / .iges / .geo）
        output_dir:    网格文件输出目录
        quality:       网格精度预设
        output_format: 输出格式（".msh" 或 ".inp"）
        element_order: 单元阶次（1=线性, 2=二次）
        optimize:      是否对网格质量做后处理优化
        timeout:       超时秒数（网格划分可能较慢）

    Returns:
        MeshResult
    """
    try:
        import gmsh
    except ImportError:
        return MeshResult(
            success=False,
            error="gmsh 未安装。请运行: pip install gmsh",
        )

    # ---- 校验输入 ----
    geo_file = geo_file.resolve()
    if not geo_file.exists():
        return MeshResult(success=False, error=f"几何文件不存在: {geo_file}")

    ext = geo_file.suffix.lower()
    if ext not in SUPPORTED_GEO_FORMATS:
        fmts = ", ".join(SUPPORTED_GEO_FORMATS)
        return MeshResult(success=False, error=f"不支持的格式 '{ext}'，支持: {fmts}")

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    out_ext = output_format if output_format.startswith(".") else f".{output_format}"
    mesh_path = output_dir / f"{geo_file.stem}{out_ext}"

    start = time.monotonic()
    warnings: list[str] = []

    try:
        gmsh.initialize()
        gmsh.option.setNumber("General.Terminal", 0)       # 静默模式
        gmsh.option.setNumber("General.Verbosity", 2)

        # ---- 载入几何 ----
        if ext == ".geo":
            gmsh.merge(str(geo_file))
        else:
            gmsh.model.occ.importShapes(str(geo_file))
            gmsh.model.occ.synchronize()

        # ---- 网格精度设置 ----
        _set_mesh_size(gmsh, quality.lc_factor)

        # ---- 网格划分 ----
        gmsh.model.mesh.generate(3)          # 3D 网格

        if element_order == 2:
            gmsh.model.mesh.setOrder(2)

        if optimize:
            gmsh.model.mesh.optimize("Netgen")

        # ---- 统计节点 / 单元数 ----
        node_tags, _, _ = gmsh.model.mesh.getNodes()
        node_count = len(node_tags)

        element_count = 0
        for dim, tag in gmsh.model.getEntities():
            types, tags, _ = gmsh.model.mesh.getElements(dim, tag)
            for t in tags:
                element_count += len(t)

        # ---- 写出 ----
        if out_ext == ".inp":
            gmsh.option.setNumber("Mesh.SaveGroupsOfNodes", 1)
            gmsh.option.setNumber("Mesh.SaveAll", 0)
        gmsh.write(str(mesh_path))

    except Exception as exc:
        try:
            gmsh.finalize()
        except Exception:
            pass
        return MeshResult(
            success=False,
            error=f"网格划分失败: {exc}",
            duration_seconds=time.monotonic() - start,
        )
    finally:
        try:
            gmsh.finalize()
        except Exception:
            pass

    duration = time.monotonic() - start

    return MeshResult(
        success=True,
        mesh_file=mesh_path,
        inp_file=mesh_path if out_ext == ".inp" else None,
        duration_seconds=duration,
        node_count=node_count,
        element_count=element_count,
        quality=quality,
        warnings=warnings,
    )


def mesh_interactive(
    geo_file: Path,
    output_dir: Path,
) -> MeshResult:
    """
    交互式网格划分：逐步提示用户选择精度等选项。
    实际提问由 CLI 层（main.py）完成，此处只执行划分。
    """
    return mesh_geometry(geo_file, output_dir)


# ------------------------------------------------------------------ #
# 内部工具
# ------------------------------------------------------------------ #

def _set_mesh_size(gmsh, lc_factor: float) -> None:
    """
    根据几何包围盒自动推算特征尺寸，再乘以 lc_factor 缩放。
    """
    try:
        bb = gmsh.model.getBoundingBox(-1, -1)  # 全局包围盒
        # bb = (xmin, ymin, zmin, xmax, ymax, zmax)
        diag = (
            (bb[3] - bb[0]) ** 2 +
            (bb[4] - bb[1]) ** 2 +
            (bb[5] - bb[2]) ** 2
        ) ** 0.5
        if diag > 0:
            lc = diag * 0.1 * lc_factor   # 默认以对角线 10% 为基准
            gmsh.option.setNumber("Mesh.CharacteristicLengthMax", lc)
            gmsh.option.setNumber("Mesh.CharacteristicLengthMin", lc * 0.1)
    except Exception as exc:
        log.warning("无法设置特征尺寸，使用 Gmsh 默认值: %s", exc)

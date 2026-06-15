# cad_generator.py
"""
CadQuery 几何生成

参数化 CAD 几何创建，支持：
  - 梁（Beam）：指定长度、宽度、高度、圆角半径
  - 圆柱（Cylinder）：指定半径、高度、角度
  - 板（Plate）：指定长度、宽度、厚度

懒加载 cadquery 依赖。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# 懒加载 CadQuery
_cadquery = None


def _get_cadquery():
    """懒加载并返回 CadQuery 模块。"""
    global _cadquery
    if _cadquery is None:
        import cadquery
        _cadquery = cadquery
    return _cadquery


# ------------------------------------------------------------------ #
# 参数数据类
# ------------------------------------------------------------------ #

@dataclass
class BeamParams:
    """梁参数。"""
    length: float
    width: float
    height: float
    fillet_radius: float = 0.0


@dataclass
class CylinderParams:
    """圆柱参数。"""
    radius: float
    height: float
    angle: float = 360.0  # degrees, partial cylinder


@dataclass
class PlateParams:
    """板参数。"""
    length: float
    width: float
    thickness: float


@dataclass
class CadResult:
    """CAD 操作结果。"""
    success: bool
    workplane: Optional[object] = None  # CadQuery Workplane
    step_file: Optional[Path] = None
    inp_file: Optional[Path] = None
    error: Optional[str] = None
    generated_code: Optional[str] = None  # AI 生成的代码


@dataclass
class NlGenerateResult:
    """自然语言生成结果。"""
    success: bool
    workplane: Optional[object] = None
    step_file: Optional[Path] = None
    error: Optional[str] = None
    generated_code: Optional[str] = None
    description: str = ""


# ------------------------------------------------------------------ #
# CadGenerator
# ------------------------------------------------------------------ #

class CadGenerator:
    """
    CadQuery 几何生成器。

    提供参数化几何创建和导出功能。
    """

    def create_beam(self, params: BeamParams) -> CadResult:
        """
        创建梁几何。

        Args:
            params: BeamParams 参数

        Returns:
            CadResult
        """
        try:
            cq = _get_cadquery()

            # 创建基础长方体
            wp = (
                cq.Workplane("XY")
                .box(params.length, params.width, params.height, centered=(True, True, False))
            )

            # 可选圆角
            if params.fillet_radius > 0:
                # 圆角仅对边生效，需要分别处理
                try:
                    wp = wp.edges("|Z").fillet(params.fillet_radius)
                except Exception:
                    pass  # 圆角失败不影响基础几何

            return CadResult(success=True, workplane=wp)

        except ImportError:
            return CadResult(success=False, error="CadQuery 未安装，请运行: pip install cadquery")
        except Exception as exc:
            return CadResult(success=False, error=f"创建梁失败: {exc}")

    def create_cylinder(self, params: CylinderParams) -> CadResult:
        """
        创建圆柱几何。

        Args:
            params: CylinderParams 参数

        Returns:
            CadResult
        """
        try:
            cq = _get_cadquery()

            if params.angle >= 360:
                # 完整圆柱
                wp = (
                    cq.Workplane("XY")
                    .circle(params.radius)
                    .extrude(params.height)
                )
            else:
                # 部分圆柱（扇形）
                import math
                wp = (
                    cq.Workplane("XY")
                    .lineTo(params.radius, 0)
                    .lineTo(
                        params.radius * math.cos(math.radians(params.angle)),
                        params.radius * math.sin(math.radians(params.angle)),
                    )
                    .lineTo(params.radius, 0)
                    .close()
                    .extrude(params.height)
                )

            return CadResult(success=True, workplane=wp)

        except ImportError:
            return CadResult(success=False, error="CadQuery 未安装，请运行: pip install cadquery")
        except Exception as exc:
            return CadResult(success=False, error=f"创建圆柱失败: {exc}")

    def create_plate(self, params: PlateParams) -> CadResult:
        """
        创建板几何。

        Args:
            params: PlateParams 参数

        Returns:
            CadResult
        """
        try:
            cq = _get_cadquery()

            wp = (
                cq.Workplane("XY")
                .box(params.length, params.width, params.thickness, centered=(True, True, False))
            )

            return CadResult(success=True, workplane=wp)

        except ImportError:
            return CadResult(success=False, error="CadQuery 未安装，请运行: pip install cadquery")
        except Exception as exc:
            return CadResult(success=False, error=f"创建板失败: {exc}")

    def export_step(self, workplane: object, filename: str, output_dir: Path = Path(".")) -> Path:
        """
        导出为 STEP 文件。

        Args:
            workplane: CadQuery Workplane 对象
            filename: 输出文件名（不含扩展名）
            output_dir: 输出目录

        Returns:
            导出的文件路径
        """
        output_path = (output_dir / filename).with_suffix(".step")
        cq = _get_cadquery()
        cq.exporters.export(workplane, str(output_path))
        return output_path

    def export_inp(self, workplane: object, filename: str, mesh_size: float = 1.0, output_dir: Path = Path(".")) -> Path:
        """
        导出为 .inp 文件（通过 gmsh 网格划分）。

        Note: 需要 gmsh 和 meshio 依赖。

        Args:
            workplane: CadQuery Workplane 对象
            filename: 输出文件名（不含扩展名）
            mesh_size: 网格尺寸
            output_dir: 输出目录

        Returns:
            导出的文件路径
        """
        try:
            import gmsh
            import meshio  # noqa: F401 - imported to validate optional dependency availability
        except ImportError:
            raise RuntimeError("导出 .inp 需要 gmsh 和 meshio，请运行: pip install gmsh meshio")

        output_path = (output_dir / filename).with_suffix(".inp")

        # 临时 STEP 文件
        tmp_step = output_dir / f"{filename}_tmp.step"
        cq = _get_cadquery()
        cq.exporters.export(workplane, str(tmp_step))

        # 使用 gmsh 网格划分
        gmsh.initialize()
        try:
            gmsh.model.occ.importShapes(str(tmp_step))
            gmsh.model.occ.synchronize()
            gmsh.model.mesh.setSize(gmsh.model.occ.getEntities(), mesh_size)
            gmsh.model.mesh.generate(3)
            gmsh.write(str(output_path))
        finally:
            gmsh.finalize()

        # 清理临时文件
        if tmp_step.exists():
            tmp_step.unlink()

        return output_path

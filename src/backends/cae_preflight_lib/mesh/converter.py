# meshio 格式转换
"""
网格格式转换模块（基于 meshio）
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

try:
    import meshio as _meshio
    _HAS_MESHIO = True
except ImportError:
    _meshio = None  # type: ignore
    _HAS_MESHIO = False

_EXT_TO_FORMAT: dict[str, str] = {
    ".msh":   "gmsh",
    ".inp":   "abaqus",
    ".vtu":   "vtu",
    ".vtk":   "vtk",
    ".xdmf":  "xdmf",
    ".med":   "med",
    ".stl":   "stl",
    ".obj":   "obj",
    ".off":   "off",
    ".medit": "medit",
    ".cgns":  "cgns",
}

READABLE_FORMATS = set(_EXT_TO_FORMAT.keys())
WRITABLE_FORMATS = {".inp", ".vtu", ".vtk", ".msh", ".xdmf", ".stl"}


@dataclass
class ConvertResult:
    success: bool
    output_file: Optional[Path] = None
    error: Optional[str] = None
    duration_seconds: float = 0.0
    node_count: int = 0
    element_count: int = 0
    source_format: str = ""
    target_format: str = ""

    @property
    def duration_str(self) -> str:
        s = self.duration_seconds
        return f"{s:.1f}s" if s < 60 else f"{int(s)//60}m {int(s)%60}s"


def convert_mesh(
    src: Path,
    dst: Path,
    *,
    prune_z_0: bool = False,
    remove_orphaned_nodes: bool = True,
) -> ConvertResult:
    """将网格文件从一种格式转换为另一种格式。"""
    if not _HAS_MESHIO:
        return ConvertResult(success=False, error="meshio 未安装，请运行: pip install meshio")

    src = src.resolve()
    if not src.exists():
        return ConvertResult(success=False, error=f"源文件不存在: {src}")

    src_ext = src.suffix.lower()
    dst_ext = dst.suffix.lower()

    if src_ext not in READABLE_FORMATS:
        return ConvertResult(
            success=False,
            error=f"不支持读取格式 '{src_ext}'，支持: {', '.join(sorted(READABLE_FORMATS))}",
        )
    if dst_ext not in WRITABLE_FORMATS:
        return ConvertResult(
            success=False,
            error=f"不支持写出格式 '{dst_ext}'，支持: {', '.join(sorted(WRITABLE_FORMATS))}",
        )

    dst.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()

    try:
        mesh = _meshio.read(str(src))
        if remove_orphaned_nodes:
            mesh = _remove_orphaned_nodes(mesh)
        if prune_z_0 and mesh.points.shape[1] == 3 and (mesh.points[:, 2] == 0).all():
            mesh.points = mesh.points[:, :2]
        _meshio.write(str(dst), mesh, file_format=_EXT_TO_FORMAT.get(dst_ext))
    except Exception as exc:  # noqa: BLE001
        return ConvertResult(
            success=False, error=str(exc),
            duration_seconds=time.monotonic() - start,
            source_format=src_ext, target_format=dst_ext,
        )

    return ConvertResult(
        success=True,
        output_file=dst,
        duration_seconds=time.monotonic() - start,
        node_count=len(mesh.points),
        element_count=sum(len(cb.data) for cb in mesh.cells),
        source_format=src_ext,
        target_format=dst_ext,
    )


def msh_to_inp(msh_file: Path, output_dir: Optional[Path] = None) -> ConvertResult:
    """Gmsh .msh → CalculiX .inp"""
    out_dir = output_dir or msh_file.parent
    return convert_mesh(msh_file, out_dir / f"{msh_file.stem}.inp")


def inp_to_vtu(inp_file: Path, output_dir: Optional[Path] = None) -> ConvertResult:
    """CalculiX .inp → VTK .vtu"""
    out_dir = output_dir or inp_file.parent
    return convert_mesh(inp_file, out_dir / f"{inp_file.stem}.vtu")


def detect_format(path: Path) -> Optional[str]:
    """返回文件格式的 meshio 名称，未知时返回 None。"""
    return _EXT_TO_FORMAT.get(path.suffix.lower())


def _remove_orphaned_nodes(mesh):
    """删除未被任何单元引用的孤立节点，重新映射索引。"""
    try:
        import numpy as np
        used: set[int] = set()
        for cb in mesh.cells:
            used.update(cb.data.flatten().tolist())
        if len(used) == len(mesh.points):
            return mesh
        used_arr = sorted(used)
        old_to_new = {old: new for new, old in enumerate(used_arr)}
        new_points = mesh.points[used_arr]
        new_cells = [
            _meshio.CellBlock(cb.type, np.vectorize(old_to_new.get)(cb.data))
            for cb in mesh.cells
        ]
        new_point_data = {k: v[used_arr] for k, v in mesh.point_data.items()}
        return _meshio.Mesh(
            points=new_points, cells=new_cells,
            point_data=new_point_data, cell_data=mesh.cell_data,
            field_data=mesh.field_data,
        )
    except Exception as exc:
        log.warning("删除孤立节点失败，跳过: %s", exc)
        return mesh
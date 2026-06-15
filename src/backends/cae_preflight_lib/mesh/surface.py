"""
网格 Surface 类

用于定义接触对、载荷施加面等。

CalculiX 中 Surface 是节点集或单元面的集合，用于：
- 接触对定义（*CONTACT PAIR）
- 分布载荷（*DLOAD）
- 分布边界条件（*DSLOAD）
- 表面效应（*SFILM, *SFLUX）

类层次：
  SurfaceBase (ABC)
    ├── NodeSurface     # 节点基表面
    └── ElementSurface  # 单元面基表面

参考 pygccx mesh/surface.py 设计
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterable

from cae_preflight_lib.enums import SurfaceType


# =============================================================================
# Surface 基类
# =============================================================================

@dataclass
class SurfaceBase(ABC):
    """
    Surface 基类。

    Attributes:
        name: Surface 名称
    """

    name: str
    """Surface 名称"""

    @abstractmethod
    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        pass

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())


# =============================================================================
# Node Surface
# =============================================================================

@dataclass
class NodeSurface(SurfaceBase):
    """
    基于节点的 Surface。

    适用于分布载荷、边界条件等。

    Attributes:
        name: Surface 名称
        node_ids: 节点 ID 集合
        node_set_names: 节点集名称集合
    """

    node_ids: set[int] = field(default_factory=set)
    """节点 ID 集合"""
    node_set_names: set[str] = field(default_factory=set)
    """节点集名称集合"""

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = [f"*SURFACE,NAME={self.name.upper()},TYPE={SurfaceType.NODE}"]

        # 先添加节点集名称
        for nset in self.node_set_names:
            lines.append(f"{nset},")

        # 再添加单独的节点 ID
        for nid in self.node_ids:
            lines.append(f"{nid},")

        # 删除最后一个逗号
        if lines[-1].endswith(","):
            lines[-1] = lines[-1][:-1]

        return lines

    def add_node_id(self, node_id: int) -> None:
        """添加节点 ID。"""
        self.node_ids.add(node_id)

    def add_node_set(self, nset_name: str) -> None:
        """添加节点集名称。"""
        self.node_set_names.add(nset_name)


# =============================================================================
# Element Surface
# =============================================================================

@dataclass
class ElementSurface(SurfaceBase):
    """
    基于单元面的 Surface。

    适用于接触对、表面载荷等。

    每个单元面由 (elem_id, face_id) 元组标识。
    face_id 是 CalculiX 手册中定义的面编号（从 1 开始）。

    Attributes:
        name: Surface 名称
        element_faces: 单元面集合 {(elem_id, face_id), ...}
    """

    element_faces: set[tuple[int, int]] = field(default_factory=set)
    """单元面集合 {(elem_id, face_id), ...}"""

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = [f"*SURFACE,NAME={self.name.upper()},TYPE={SurfaceType.ELEMENT}"]

        for elem_id, face_id in sorted(self.element_faces):
            lines.append(f"{elem_id},S{face_id}")

        return lines

    def add_element_face(self, elem_id: int, face_id: int) -> None:
        """添加单元面。"""
        self.element_faces.add((elem_id, face_id))


# =============================================================================
# Surface 工厂函数
# =============================================================================

def create_surface_from_node_set(
    name: str,
    elements: Iterable[ElementSurface],
    node_set_ids: set[int],
) -> ElementSurface:
    """
    从节点集创建单元面 Surface。

    查找所有包含给定节点集的单元及其面，构建 ElementSurface。

    Args:
        name: Surface 名称
        elements: 单元可迭代对象
        node_set_ids: 节点 ID 集合

    Returns:
        ElementSurface

    Note:
        需要 Element 类支持 get_faces() 方法。
        可以使用 cae.mesh.element 中的 Element 和 MeshElements。
    """
    from cae_preflight_lib.mesh.element import get_element_faces

    surface: set[tuple[int, int]] = set()

    for elem in elements:
        elem_node_ids = set(elem.node_ids)

        # 检查节点集是否与单元有交集
        if node_set_ids.isdisjoint(elem_node_ids):
            continue

        # 检查每个面
        faces = get_element_faces(elem.type)
        if not faces:
            continue

        for face_idx, face_nodes in enumerate(faces):
            # face_idx 是 0-based，CalculiX face_id 是 1-based
            face_node_set = set(elem.node_ids[i] for i in face_nodes)
            if node_set_ids.issuperset(face_node_set):
                surface.add((elem.id, face_idx + 1))  # 转换为 1-based

    return ElementSurface(name=name.upper(), element_faces=surface)


def create_node_surface(
    name: str,
    node_ids: Iterable[int] = (),
    node_set_names: Iterable[str] = (),
) -> NodeSurface:
    """
    创建节点 Surface。

    Args:
        name: Surface 名称
        node_ids: 节点 ID 集合
        node_set_names: 节点集名称集合

    Returns:
        NodeSurface
    """
    return NodeSurface(
        name=name.upper(),
        node_ids=set(node_ids),
        node_set_names=set(node_set_names),
    )


def create_element_surface(
    name: str,
    element_faces: Iterable[tuple[int, int]] = (),
) -> ElementSurface:
    """
    创建单元面 Surface。

    Args:
        name: Surface 名称
        element_faces: 单元面集合 {(elem_id, face_id), ...}

    Returns:
        ElementSurface
    """
    return ElementSurface(
        name=name.upper(),
        element_faces=set(element_faces),
    )

"""
网格单元模块

提供单元数据结构、验证和面索引映射。
借鉴 pygccx mesh/element.py 设计。

面索引表（FACE_INDEX_TABLE）：
  每个单元类型有一组面，每面由节点索引元组定义。
  索引对应 node_ids 中的位置（0-based）。

例如 C3D8 (8节点六面体) 的 FACE_INDEX_TABLE:
  ((0,1,2,3),   # 面0: 节点0,1,2,3 (底面)
   (4,7,6,5),   # 面1: 节点4,7,6,5 (顶面)
   (0,4,5,1),   # 面2: 节点0,4,5,1 (前面)
   (1,5,6,2),   # 面3: 节点1,5,6,2 (右面)
   (2,6,7,3),   # 面4: 节点2,6,7,3 (后面)
   (3,7,4,0))   # 面5: 节点3,7,4,0 (左面)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from cae_preflight_lib.enums import ElementType


# =============================================================================
# 面索引表：ElementType -> tuple of faces -> tuple of node indices
# =============================================================================

FACE_INDEX_TABLE: dict[ElementType, tuple[tuple[int, ...], ...]] = {
    # --- 3D 连续体单元 ---
    ElementType.C3D4: (  # 4节点四面体（4个三角面）
        (0, 1, 2),   # 面0: 三角面0-1-2
        (0, 3, 1),   # 面1: 三角面0-3-1
        (1, 3, 2),   # 面2: 三角面1-3-2
        (2, 3, 0),   # 面3: 三角面2-3-0
    ),
    ElementType.C3D6: (  # 6节点五面体（2三角面 + 3四边面）
        (0, 1, 2),            # 面0: 三角面0-1-2
        (3, 5, 4),            # 面1: 三角面3-4-5
        (0, 1, 4, 3),         # 面2: 四边面0-1-4-3
        (1, 2, 5, 4),         # 面3: 四边面1-2-5-4
        (2, 0, 3, 5),         # 面4: 四边面2-0-3-5
    ),
    ElementType.C3D8: (  # 8节点六面体（6个四边面）
        (0, 1, 2, 3),  # 面0: 底面 0-1-2-3
        (4, 7, 6, 5),  # 面1: 顶面 4-7-6-5
        (0, 4, 5, 1),  # 面2: 前面 0-4-5-1
        (1, 5, 6, 2),  # 面3: 右面 1-5-6-2
        (2, 6, 7, 3),  # 面4: 后面 2-6-7-3
        (3, 7, 4, 0),  # 面5: 左面 3-7-4-0
    ),
    ElementType.C3D8I: (  # 8节点六面体（非协调模式），同 C3D8
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ),
    ElementType.C3D10: (  # 10节点四面体（4个三角面）
        # 节点0-3: 角节点, 4-9: 边中点
        # 面由角节点确定（忽略边中点）
        (0, 1, 2),   # 面0: 角节点0-1-2
        (0, 3, 1),   # 面1: 角节点0-3-1
        (1, 3, 2),   # 面2: 角节点1-3-2
        (2, 3, 0),   # 面3: 角节点2-3-0
    ),
    ElementType.C3D15: (  # 15节点五面体
        # 节点0-2: 底面角节点, 3-5: 顶面角节点
        # 6-14: 边中点
        (0, 1, 2),          # 面0: 三角面0-1-2
        (3, 5, 4),          # 面1: 三角面3-4-5
        (0, 1, 4, 3),       # 面2: 四边面0-1-4-3
        (1, 2, 5, 4),       # 面3: 四边面1-2-5-4
        (2, 0, 3, 5),       # 面4: 四边面2-0-3-5
    ),
    ElementType.C3D20: (  # 20节点六面体
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ),
    ElementType.C3D20R: (  # 20节点六面体（减缩）
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ),
    # --- Shell 单元 ---
    ElementType.S3: (  # 3节点三角形壳
        (0, 1, 2),
    ),
    ElementType.S4: (  # 4节点四边形壳
        (0, 1, 2, 3),
    ),
    ElementType.S4R: (  # 4节点四边形壳（减缩）
        (0, 1, 2, 3),
    ),
    ElementType.S6: (  # 6节点三角形壳
        (0, 1, 2),
    ),
    ElementType.S8: (  # 8节点四边形壳
        (0, 1, 2, 3),
    ),
    ElementType.S8R: (  # 8节点四边形壳（减缩）
        (0, 1, 2, 3),
    ),
    # --- 2D 平面应力/应变单元 ---
    ElementType.CPS3: ((0, 1, 2),),
    ElementType.CPS4: ((0, 1, 2, 3),),
    ElementType.CPS4R: ((0, 1, 2, 3),),
    ElementType.CPS6: ((0, 1, 2),),
    ElementType.CPS8: ((0, 1, 2, 3),),
    ElementType.CPS8R: ((0, 1, 2, 3),),
    ElementType.CPE3: ((0, 1, 2),),
    ElementType.CPE4: ((0, 1, 2, 3),),
    ElementType.CPE4R: ((0, 1, 2, 3),),
    ElementType.CPE6: ((0, 1, 2),),
    ElementType.CPE8: ((0, 1, 2, 3),),
    ElementType.CPE8R: ((0, 1, 2, 3),),
    ElementType.CAX3: ((0, 1, 2),),
    ElementType.CAX4: ((0, 1, 2, 3),),
    ElementType.CAX4R: ((0, 1, 2, 3),),
    ElementType.CAX6: ((0, 1, 2),),
    ElementType.CAX8: ((0, 1, 2, 3),),
    ElementType.CAX8R: ((0, 1, 2, 3),),
}


# =============================================================================
# 角节点数表（用于高阶单元）
# =============================================================================

CORNER_NODE_COUNT_TABLE: dict[ElementType, int] = {
    # 点单元
    ElementType.SPRING1: 1,
    ElementType.DCOUP3D: 1,
    ElementType.MASS: 1,
    # 2节点单元
    ElementType.GAPUNI: 2,
    ElementType.DASHPOTA: 2,
    ElementType.SPRING2: 2,
    ElementType.SPRINGA: 2,
    ElementType.T2D2: 2,
    ElementType.T3D2: 2,
    ElementType.B21: 2,
    # 3节点单元
    ElementType.T3D3: 3,
    ElementType.B31: 3,
    ElementType.B31R: 3,
    ElementType.B32: 3,
    ElementType.B32R: 3,
    # 4节点单元（低阶实体/壳）
    ElementType.C3D4: 4,
    ElementType.C3D8: 8,  # C3D8 有8个节点，但角节点是前4个？不，C3D8全部是角节点
    ElementType.C3D8R: 8,
    ElementType.C3D8I: 8,
    ElementType.S3: 3,
    ElementType.S4: 4,
    ElementType.S4R: 4,
    ElementType.CPS4: 4,
    ElementType.CPE4: 4,
    ElementType.CAX4: 4,
    # 6节点单元
    ElementType.C3D6: 6,
    ElementType.S6: 3,
    ElementType.CPS6: 3,
    ElementType.CPE6: 3,
    ElementType.CAX6: 3,
    # 8节点单元（高阶壳）
    ElementType.S8: 4,
    ElementType.S8R: 4,
    ElementType.CPS8: 4,
    ElementType.CPE8: 4,
    ElementType.CAX8: 4,
    # 10节点四面体
    ElementType.C3D10: 4,
    # 15节点五面体
    ElementType.C3D15: 6,
    # 20节点六面体
    ElementType.C3D20: 8,
    ElementType.C3D20R: 8,
}


# =============================================================================
# 辅助函数
# =============================================================================


def get_element_faces(element_type: ElementType) -> tuple[tuple[int, ...], ...]:
    """
    获取单元的面节点索引。

    Args:
        element_type: 单元类型

    Returns:
        面列表，每个面是节点索引元组
    """
    return FACE_INDEX_TABLE.get(element_type, ())


def get_face_count(element_type: ElementType) -> int:
    """获取单元的面数量。"""
    faces = FACE_INDEX_TABLE.get(element_type, ())
    return len(faces)


def get_corner_node_count(element_type: ElementType) -> int:
    """
    获取单元的角节点数量。

    对于线性单元，等于总节点数。
    对于二次单元，角节点数 < 总节点数。
    """
    return CORNER_NODE_COUNT_TABLE.get(element_type, element_type.node_count)


# =============================================================================
# Element 数据类
# =============================================================================


@dataclass
class Element:
    """
    网格单元。

    提供单元验证和面查询功能。

    Attributes:
        id: 单元编号
        type: 单元类型
        node_ids: 节点编号元组（顺序对应 CalculiX 连接定义）
    """

    id: int
    type: ElementType
    node_ids: tuple[int, ...]

    def __post_init__(self):
        """验证单元数据。"""
        self._validate()

    def _validate(self) -> None:
        """验证节点数是否与单元类型匹配。"""
        expected = self.type.node_count
        actual = len(self.node_ids)
        if actual != expected:
            raise ValueError(
                f"单元 {self.type.value} 需要 {expected} 个节点，"
                f"但得到 {actual} 个"
            )

    def get_faces(self) -> list[tuple[int, ...]]:
        """
        获取所有面的节点编号列表。

        Returns:
            面列表，每面是节点编号元组
        """
        face_indices = get_element_faces(self.type)
        return [tuple(self.node_ids[i] for i in face) for face in face_indices]

    def get_face_nodes(self, face_index: int) -> tuple[int, ...]:
        """
        获取指定面的节点编号。

        Args:
            face_index: 面索引（0-based）

        Returns:
            该面的节点编号元组
        """
        faces = get_element_faces(self.type)
        if face_index < 0 or face_index >= len(faces):
            raise IndexError(f"面索引 {face_index} 超出范围 (0-{len(faces)-1})")
        face = faces[face_index]
        return tuple(self.node_ids[i] for i in face)

    def get_corner_node_ids(self) -> tuple[int, ...]:
        """获取角节点编号。"""
        n_corners = get_corner_node_count(self.type)
        return self.node_ids[:n_corners]

    @property
    def dimension(self) -> int:
        """获取单元空间维度（0/1/2/3）。"""
        if self.type in (ElementType.SPRING1, ElementType.DCOUP3D, ElementType.MASS):
            return 0
        if self.type in (
            ElementType.GAPUNI, ElementType.DASHPOTA,
            ElementType.SPRING2, ElementType.SPRINGA,
            ElementType.T2D2, ElementType.T3D2,
            ElementType.T3D3,
            ElementType.B21, ElementType.B31, ElementType.B31R,
            ElementType.B32, ElementType.B32R,
        ):
            return 1
        if self.type.is_shell or self.type.is_2d:
            return 2
        return 3


@dataclass
class MeshElements:
    """
    网格单元集合。

    提供批量单元查询功能。
    """

    elements: list[Element] = field(default_factory=list)

    def get_by_id(self, elem_id: int) -> Optional[Element]:
        """按 ID 查找单元。"""
        for elem in self.elements:
            if elem.id == elem_id:
                return elem
        return None

    def get_by_type(self, elem_type: ElementType) -> list[Element]:
        """按类型查找单元。"""
        return [e for e in self.elements if e.type == elem_type]

    def get_solid_elements(self) -> list[Element]:
        """获取所有3D实体单元。"""
        return [e for e in self.elements if e.type.is_solid]

    def get_shell_elements(self) -> list[Element]:
        """获取所有壳单元。"""
        return [e for e in self.elements if e.type.is_shell]

    def get_beam_elements(self) -> list[Element]:
        """获取所有梁单元。"""
        return [e for e in self.elements if e.type.is_beam]

    def get_face_neighbor_elements(
        self, element: Element, face_index: int
    ) -> list[Element]:
        """
        查找与给定单元指定面相邻的单元。

        用于边界条件应用等场景。

        Args:
            element: 参考单元
            face_index: 面索引

        Returns:
            共享该面的相邻单元列表
        """
        face_nodes = element.get_face_nodes(face_index)
        neighbors = []

        for other in self.elements:
            if other.id == element.id:
                continue
            # 检查 other 的所有面是否与 face_nodes 匹配
            for other_face in other.get_faces():
                if set(other_face) == set(face_nodes):
                    neighbors.append(other)
                    break

        return neighbors

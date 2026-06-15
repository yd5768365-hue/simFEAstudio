"""
CalculiX .frd 文件解析器
.frd 是 CalculiX 输出的二进制/ASCII 混合格式结果文件。
本模块将其解析为 Python 数据结构，供 vtk_export.py 使用。

.frd 结构速查：
  1C  — 节点坐标块
  2C  — 单元拓扑块
  100C — 结果块（位移 U、应力 S、应变 E、反力 RF 等）
  9999 — 文件结束标记
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import numpy.typing as npt

from cae_preflight_lib.enums import ResultLocation, FrdResultEntity


@dataclass
class FrdNodes:
    ids: list[int]                        # 节点编号（1-based）
    coords: list[tuple[float, float, float]]  # (x, y, z)


@dataclass
class FrdElement:
    eid: int
    etype: int           # CalculiX 单元类型编号
    connectivity: list[int]   # 节点编号列表


@dataclass
class FrdResultStep:
    """
    单个载荷步 / 时间步的结果。

    Attributes:
        entity: 结果实体类型（DISP, STRESS, STRAIN 等）
        step: 载荷步号
        step_inc_no: 步内增量号（STATIC 为增量号，FREQUENCY 为模态号）
        total_inc_no: 总增量号
        time: 时间值
        name: 字段名（与 entity 对应）
        components: 分量名称列表
        values: 字典，key=节点ID, value=分量值数组
        node_ids: 节点 ID 列表
        analysis_type: 分析类型：STATIC, FREQUENCY, BUCKLE 等
        entity_location: 结果位置：NODAL, ELEMENT, INT_PNT
    """

    step: int
    time: float
    name: str  # 字段名，如 "DISP", "STRESS"
    components: list[str]  # 分量名称列表
    values: dict[int, Sequence[float]]  # {节点ID: 分量值序列}
    node_ids: list[int]  # 与 values 对应的节点编号
    entity: FrdResultEntity  # 结果实体类型
    step_inc_no: int = 0  # 步内增量号
    total_inc_no: int = 0  # 总增量号
    analysis_type: str = "STATIC"  # 分析类型
    entity_location: ResultLocation = ResultLocation.NODAL  # 结果位置

    def get_values_by_ids(self, ids: list[int]) -> npt.NDArray[np.float64]:
        """
        返回指定节点 ID 的结果值。

        Args:
            ids: 节点 ID 列表

        Returns:
            2D numpy 数组，shape=(len(ids), no_components)
            如果节点不存在，对应行填充为零
        """
        no_comp = len(self.components) if self.components else 1
        return np.array([
            self.values.get(nid, np.zeros(no_comp)) for nid in ids
        ])


@dataclass
class FrdData:
    """
    .frd 文件解析结果容器。

    包含节点、单元和所有结果集。
    """

    nodes: Optional[FrdNodes] = None
    elements: list[FrdElement] = field(default_factory=list)
    results: list[FrdResultStep] = field(default_factory=list)

    @property
    def has_geometry(self) -> bool:
        return self.nodes is not None and len(self.elements) > 0

    @property
    def node_count(self) -> int:
        return len(self.nodes.ids) if self.nodes else 0

    @property
    def element_count(self) -> int:
        return len(self.elements)

    def get_result(self, name: str, step: int = -1) -> Optional[FrdResultStep]:
        """按名称和步骤号查找结果，step=-1 取最后一步。"""
        matches = [r for r in self.results if name.upper() in r.name.upper()]
        if not matches:
            return None
        return matches[step]

    def get_results_by(
        self,
        *,
        entity: Optional[FrdResultEntity] = None,
        name: Optional[str] = None,
        step: Optional[int] = None,
        step_inc_no: Optional[int] = None,
        total_inc_no: Optional[int] = None,
        time: Optional[float] = None,
        analysis_type: Optional[str] = None,
        entity_location: Optional[ResultLocation] = None,
    ) -> list[FrdResultStep]:
        """
        按条件过滤结果集。

        所有参数都是可选的，不指定的参数不参与过滤。
        当 time 有值时，返回时间最接近的结果集。

        Args:
            entity: 结果实体类型（FrdResultEntity），如 DISP, STRESS
            name: 字段名（不区分大小写，包含匹配），与 entity 二选一
            step: 载荷步号
            step_inc_no: 步内增量号
            total_inc_no: 总增量号
            time: 目标时间（返回时间最接近的结果集）
            analysis_type: 分析类型（不区分大小写），如 "STATIC", "FREQUENCY"
            entity_location: 结果位置（NODAL, ELEMENT, INT_PNT）

        Returns:
            符合条件的 FrdResultStep 列表
        """
        results = self.results

        if entity is not None:
            results = [r for r in results if r.entity == entity]

        if name is not None:
            results = [r for r in results if name.upper() in r.name.upper()]

        if step is not None:
            results = [r for r in results if r.step == step]

        if step_inc_no is not None:
            results = [r for r in results if r.step_inc_no == step_inc_no]

        if total_inc_no is not None:
            results = [r for r in results if r.total_inc_no == total_inc_no]

        if analysis_type is not None:
            results = [
                r for r in results
                if r.analysis_type.upper() == analysis_type.upper()
            ]

        if entity_location is not None:
            results = [r for r in results if r.entity_location == entity_location]

        if time is not None and results:
            closest = min(results, key=lambda r: abs(r.time - time))
            results = [closest]

        return results

    def get_available_times(self) -> list[float]:
        """返回所有结果的时间列表（去重、排序）。"""
        times = sorted({r.time for r in self.results})
        return times

    def get_result_names(self) -> list[str]:
        """返回所有结果字段名称（去重）。"""
        names = list({r.name for r in self.results})
        return sorted(names)

    def get_steps(self) -> list[int]:
        """返回所有载荷步号（去重、排序）。"""
        steps = sorted({r.step for r in self.results})
        return steps

    def get_entities(self) -> list[FrdResultEntity]:
        """返回所有结果实体类型（去重）。"""
        entities = list({r.entity for r in self.results})
        return sorted(entities, key=lambda e: e.value)


# ------------------------------------------------------------------ #
# 单元类型映射：CalculiX 编号 → 节点数
# ------------------------------------------------------------------ #
_ETYPE_NODES: dict[int, int] = {
    1:  8,   # C3D8    8节点六面体
    2:  6,   # C3D6    6节点五面体
    3:  4,   # C3D4    4节点四面体
    4:  20,  # C3D20   20节点六面体（二阶）
    5:  15,  # C3D15   15节点五面体（二阶）
    6:  10,  # C3D10   10节点四面体（二阶）
    7:  3,   # S3      3节点壳
    8:  6,   # S6      6节点壳
    9:  4,   # S4      4节点壳
    10: 8,   # S8      8节点壳
    11: 2,   # B21     2节点梁
    12: 3,   # B22     3节点梁
}


# 例如 "0.00000E+00-5.00000E-01" 需要被拆分成两个数字。
_NUMBER_RE = re.compile(r"[+-]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?")
_FRD_PREFIX_WIDTH = 13
_FRD_VALUE_WIDTH = 12


def parse_frd(
    frd_file: Path,
    *,
    result_names: Optional[set[str]] = None,
    include_element_connectivity: bool = True,
) -> FrdData:
    """
    解析 CalculiX ASCII .frd 文件。

    Returns:
        FrdData 数据类，包含节点、单元和结果字段。

    Raises:
        ValueError: 文件格式无法识别时。
        FileNotFoundError: 文件不存在时。
    """
    if not frd_file.exists():
        raise FileNotFoundError(f"找不到 .frd 文件: {frd_file}")

    text = frd_file.read_text(encoding="latin-1", errors="replace")
    lines = text.splitlines()

    wanted_result_names = (
        {name.upper() for name in result_names}
        if result_names
        else None
    )

    data = FrdData()
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # ---- 节点坐标块 ----
        if line.startswith("    1C") or line.startswith("    1PSET"):
            i, data.nodes = _parse_nodes(lines, i)
            continue

        # ---- 单元拓扑块 ----
        if line.startswith("    2C") or line.startswith("    2PSET") or line.startswith("    3C") or line.startswith("    3PSET"):
            i, elems = _parse_elements(
                lines,
                i,
                include_connectivity=include_element_connectivity,
            )
            data.elements.extend(elems)
            continue

        # ---- 结果块 ----
        if line.startswith("  100C"):
            i, result = _parse_result(lines, i, wanted_result_names)
            if result:
                data.results.append(result)
            continue

        # ---- 文件结束 ----
        if line.strip() == "9999":
            break

        i += 1

    # 填充 step_inc_no
    _fill_step_inc_no(data.results)

    return data


# ------------------------------------------------------------------ #
# 内部解析函数
# ------------------------------------------------------------------ #

def _fill_step_inc_no(results: list[FrdResultStep]) -> None:
    """
    填充 step_inc_no（步内增量号）。

    根据 pygccx 的逻辑：
    - 当 step 变化时，重置增量计数
    - step_inc_no = total_inc_no - last_inc_no_of_previous_step
    """
    last_step_no = 0
    last_total_inc_no = 0

    for rs in results:
        if rs.step != last_step_no:
            # 新步开始，重置
            last_total_inc_no = rs.total_inc_no - 1
            last_step_no = rs.step
        rs.step_inc_no = rs.total_inc_no - last_total_inc_no


def _parse_fixed_width_row(
    line: str,
    value_count: int,
) -> Optional[tuple[int, tuple[float, ...]]]:
    """Fast path for standard FRD rows with fixed-width numeric columns."""
    if value_count <= 0:
        return None

    expected_len = _FRD_PREFIX_WIDTH + value_count * _FRD_VALUE_WIDTH
    if len(line) != expected_len:
        return None

    try:
        row_id = int(line[3:_FRD_PREFIX_WIDTH])
        if value_count == 3:
            values = (
                float(line[13:25]),
                float(line[25:37]),
                float(line[37:49]),
            )
        elif value_count == 6:
            values = (
                float(line[13:25]),
                float(line[25:37]),
                float(line[37:49]),
                float(line[49:61]),
                float(line[61:73]),
                float(line[73:85]),
            )
        else:
            values = tuple(
                float(line[offset: offset + _FRD_VALUE_WIDTH])
                for offset in range(_FRD_PREFIX_WIDTH, expected_len, _FRD_VALUE_WIDTH)
            )
    except ValueError:
        return None

    return row_id, values

def _parse_nodes(lines: list[str], start: int) -> tuple[int, FrdNodes]:
    """解析节点坐标块，返回 (下一行索引, FrdNodes)。"""
    ids: list[int] = []
    coords: list[tuple[float, float, float]] = []
    i = start + 1

    while i < len(lines):
        line = lines[i]
        if line.startswith(" -1"):
            parsed = _parse_fixed_width_row(line, 3)
            if parsed is not None:
                nid, (x, y, z) = parsed
            else:
                matches = _NUMBER_RE.findall(line)
                # 格式: [-1, node_id, x, y, z] 或 [node_id, x, y, z]
                # 需要至少4个数值
                if len(matches) >= 5:
                    # 第一个是行标记-1，跳过
                    nid = int(matches[1])
                    x = float(matches[2])
                    y = float(matches[3])
                    z = float(matches[4])
                elif len(matches) >= 4:
                    nid = int(matches[0])
                    x = float(matches[1])
                    y = float(matches[2])
                    z = float(matches[3])
                else:
                    i += 1
                    continue

            # 验证节点ID是合理的（通常是正整数）
            if nid > 0:
                ids.append(nid)
                coords.append((x, y, z))

        elif line.startswith(" -3"):
            i += 1
            break
        i += 1

    return i, FrdNodes(ids=ids, coords=coords)


def _parse_elements(
    lines: list[str],
    start: int,
    *,
    include_connectivity: bool = True,
) -> tuple[int, list[FrdElement]]:
    """解析单元拓扑块。

    注意：C3D20R 等高阶单元的连接数据可能跨越多行（每行10个节点）。
    需要累积所有连续的 ' -2' 行来构建完整的连接列表。
    """
    elements: list[FrdElement] = []
    i = start + 1

    while i < len(lines):
        line = lines[i]
        if line.startswith(" -1"):
            # 单元头行：" -1  <eid>  <etype>  <group>  <mat>"
            parts = line.split()
            if len(parts) >= 3:
                try:
                    eid = int(parts[1])
                    etype = int(parts[2])
                except ValueError:
                    i += 1
                    continue

                # 读取所有连续的 ' -2' 行（高阶单元连接数据可能跨多行）
                connectivity: list[int] = []
                i += 1
                while i < len(lines) and lines[i].startswith(" -2"):
                    if include_connectivity:
                        connectivity.extend(map(int, lines[i].split()[1:]))
                    i += 1
                if include_connectivity:
                    if connectivity:
                        elements.append(FrdElement(eid=eid, etype=etype, connectivity=connectivity))
                else:
                    elements.append(FrdElement(eid=eid, etype=etype, connectivity=connectivity))
        elif line.startswith(" -3"):
            i += 1
            break
        else:
            i += 1

    return i, elements


def _parse_result(
    lines: list[str],
    start: int,
    wanted_result_names: Optional[set[str]] = None,
) -> tuple[int, Optional[FrdResultStep]]:
    """解析单个结果块（位移、应力等）。"""
    header = lines[start]
    # 格式示例："  100C                             DISP        1  0.00000E+00"
    parts = header.split()
    field_name = "UNKNOWN"
    step = 1
    time = 0.0
    analysis_type = "STATIC"
    total_inc_no = 0

    if len(parts) >= 2:
        field_name = parts[1] if len(parts) > 1 else "UNKNOWN"

    capture_block = (
        wanted_result_names is None
        or field_name.upper() in wanted_result_names
    )

    # 找 step, time, total_inc_no
    for j, p in enumerate(parts):
        try:
            v = int(p)
            if 1 <= v <= 9999:
                step = v
                if j + 1 < len(parts):
                    time = float(parts[j + 1])
                break
        except ValueError:
            continue

    # 尝试从固定宽度格式提取 total_inc_no（位置 58-63）
    if len(header) >= 63:
        try:
            total_inc_no = int(header[58:63].strip())
        except ValueError:
            pass

    # 尝试从固定宽度格式提取 analysis_type（位置 63-73）
    if len(header) >= 74:
        analysis_str = header[63:73].strip()
        if analysis_str:
            analysis_type = analysis_str

    # 映射字段名到 FrdResultEntity
    try:
        entity = FrdResultEntity(field_name)
    except ValueError:
        entity = FrdResultEntity.DISP  # 默认值

    i = start + 1
    components: list[str] = []
    node_ids: list[int] = []
    values: dict[int, Sequence[float]] = {}

    while i < len(lines):
        line = lines[i]

        # -4 行可能包含实际字段名（如 DISP、STRESS）
        # 格式：" -4  DISP        4    1"
        if line.startswith(" -4"):
            parts4 = line.split()
            if len(parts4) >= 2:
                candidate = parts4[1]
                # 如果 parts[1] 不是数字，说明是字段名
                if not candidate.isdigit():
                    field_name = candidate
                    capture_block = (
                        wanted_result_names is None
                        or field_name.upper() in wanted_result_names
                    )
                    # 更新 entity
                    try:
                        entity = FrdResultEntity(field_name)
                    except ValueError:
                        entity = FrdResultEntity.DISP
            i += 1
            continue

        # 分量定义行
        if line.startswith(" -5"):
            if not capture_block:
                i += 1
                continue
            # 分量名行：" -5  D1  1  2  1  0"
            parts5 = line.split()
            if len(parts5) >= 2:
                components.append(parts5[1])

        elif line.startswith(" -1"):
            if not capture_block:
                i += 1
                continue
            # 结果数值行
            parsed = _parse_fixed_width_row(line, len(components))
            if parsed is not None:
                try:
                    nid, vals = parsed
                    node_ids.append(nid)
                    values[nid] = vals
                except ValueError:
                    pass
            else:
                matches = _NUMBER_RE.findall(line)
                if len(matches) >= 3:
                    try:
                        nid = int(matches[1])
                        vals = tuple(map(float, matches[2:]))
                        node_ids.append(nid)
                        values[nid] = vals
                    except (ValueError, IndexError):
                        pass

        elif line.startswith(" -3"):
            i += 1
            break

        i += 1

    if not capture_block or not node_ids:
        return i, None

    # 根据 entity 类型推断 entity_location
    # 节点结果：位移、力、反力
    # 单元结果：应力、应变等（大多数在 ELEMENT 或 INT_PNT）
    entity_location = ResultLocation.NODAL
    if entity in (
        FrdResultEntity.STRESS,
        FrdResultEntity.STRAIN,
        FrdResultEntity.MSTRESS,
        FrdResultEntity.PEEQ,
    ):
        entity_location = ResultLocation.ELEMENT

    return i, FrdResultStep(
        step=step,
        time=time,
        name=field_name,
        components=components,
        values=values,
        node_ids=node_ids,
        entity=entity,
        step_inc_no=0,  # 后续填充
        total_inc_no=total_inc_no,
        analysis_type=analysis_type,
        entity_location=entity_location,
    )

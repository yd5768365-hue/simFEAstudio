"""
CalculiX .dat 文件解析器

.dat 文件是 CalculiX 输出的文本格式结果文件，包含 NODE PRINT 和 EL PRINT 的结果。
本模块将其解析为 Python 数据结构。

.dat 文件结构速查：
  STEP X              — 载荷步开始
  INCREMENT X         — 增量步号
  displacements (...)  — 节点位移结果
  forces (...)        — 节点力/反力结果
  stresses (...)       — 单元应力结果
  strains (...)        — 单元应变结果
  contact ...         — 接触结果

参考 pygccx result_reader/dat_result.py 设计
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from cae_preflight_lib.enums import DatResultEntity


# 结果位置枚举
class ResultLocation(str):
    NODAL = "NODAL"      # 节点结果
    ELEMENT = "ELEMENT"  # 单元结果
    INT_PNT = "INT_PNT"  # 积分点结果


# 实体类型到结果位置的映射
ENTITY_2_LOCATION_MAP: dict[DatResultEntity, str] = {
    # 节点打印实体
    DatResultEntity.U: ResultLocation.NODAL,
    DatResultEntity.RF: ResultLocation.NODAL,
    # 单元打印实体
    DatResultEntity.S: ResultLocation.INT_PNT,
    DatResultEntity.E: ResultLocation.INT_PNT,
    DatResultEntity.ME: ResultLocation.INT_PNT,
    DatResultEntity.PEEQ: ResultLocation.INT_PNT,
    DatResultEntity.EVOL: ResultLocation.ELEMENT,
    DatResultEntity.COORD: ResultLocation.INT_PNT,
    DatResultEntity.ENER: ResultLocation.INT_PNT,
    DatResultEntity.ELKE: ResultLocation.ELEMENT,
    DatResultEntity.ELSE: ResultLocation.ELEMENT,
    DatResultEntity.EMAS: ResultLocation.ELEMENT,
    # 接触打印实体
    DatResultEntity.CELS: ResultLocation.NODAL,
    DatResultEntity.CSTR: ResultLocation.NODAL,
    DatResultEntity.CDIS: ResultLocation.NODAL,
}


# 分析类型
class DatAnalysisType:
    STATIC = "STATIC"
    FREQUENCY = "FREQUENCY"
    BUCKLE = "BUCKLE"


@dataclass(frozen=True)
class DatResultSet:
    """
    单个结果集。

    Attributes:
        entity: 结果实体类型（U, RF, S, E 等）
        no_components: 每个值的分量数
        step_time: 时间值
        step_no: 载荷步号
        step_inc_no: 增量步号（静态为增量号，模态为模态号，屈曲为屈曲因子号）
        analysis_type: 分析类型
        set_name: 节点集或单元集名称
        component_names: 分量名称元组
        values: 字典，key=节点ID/单元ID，value=分量值数组
        entity_location: 结果位置（NODAL/ELEMENT/INT_PNT）
    """
    entity: DatResultEntity
    no_components: int
    step_time: float
    step_no: int
    step_inc_no: int
    analysis_type: str
    set_name: str
    component_names: tuple[str, ...]
    values: dict[int, np.ndarray] = field(repr=False)
    entity_location: str = ResultLocation.NODAL

    def get_values_by_ids(self, ids: list[int]) -> np.ndarray:
        """
        按节点/单元 ID 列表获取结果值。

        Args:
            ids: 节点或单元 ID 列表

        Returns:
            如果 entity_location 是 NODAL 或 ELEMENT，返回 (N, M) 数组，N=ID数量，M=分量数
            如果 entity_location 是 INT_PNT，返回 (N, P, M) 数组，N=ID数量，P=积分点数量，M=分量数
        """
        return np.array([self.values[id] for id in ids])


@dataclass
class DatResult:
    """
    .dat 文件解析结果容器。

    提供 `get_result_sets_by()` 方法按条件过滤结果集。

    Usage:
        result = parse_dat("output.dat")
        # 获取所有位移结果
        u_sets = result.get_result_sets_by(entity=DatResultEntity.U)
        # 获取 step=1 的位移结果
        u_step1 = result.get_result_sets_by(entity=DatResultEntity.U, step_no=1)
        # 获取时间最接近 0.5 的结果
        u_near05 = result.get_result_sets_by(entity=DatResultEntity.U, step_time=0.5)
    """
    result_sets: list[DatResultSet] = field(default_factory=list)

    def get_result_sets_by(
        self,
        *,
        entity: Optional[DatResultEntity] = None,
        step_no: Optional[int] = None,
        step_inc_no: Optional[int] = None,
        step_time: Optional[float] = None,
        analysis_type: Optional[str] = None,
        set_name: Optional[str] = None,
    ) -> list[DatResultSet]:
        """
        按条件过滤结果集。

        所有参数都是可选的。step_time 会在最后应用，返回时间最接近的结果集。

        Args:
            entity: 结果实体类型（如 DatResultEntity.U, DatResultEntity.S）
            step_no: 载荷步号
            step_inc_no: 增量步号
            step_time: 目标时间（返回时间最接近的结果）
            analysis_type: 分析类型（STATIC, FREQUENCY, BUCKLE）
            set_name: 节点集或单元集名称

        Returns:
            符合条件的 DatResultSet 列表
        """
        rs = self.result_sets

        if entity is not None:
            rs = [r for r in rs if r.entity == entity]

        if step_no is not None:
            rs = [r for r in rs if r.step_no == step_no]

        if step_inc_no is not None:
            rs = [r for r in rs if r.step_inc_no == step_inc_no]

        if analysis_type is not None:
            rs = [r for r in rs if r.analysis_type.upper() == analysis_type.upper()]

        if set_name is not None:
            rs = [r for r in rs if r.set_name == set_name]

        if step_time is not None:
            available_times = {r.step_time for r in self.result_sets}
            nearest_time = min(available_times, key=lambda x: abs(x - step_time))
            rs = [r for r in rs if r.step_time == nearest_time]

        return rs

    def get_available_times(self) -> list[float]:
        """返回所有去重排序后的时间列表。"""
        return sorted({r.step_time for r in self.result_sets})

    def get_result_entities(self) -> list[DatResultEntity]:
        """返回所有结果实体类型的去重列表。"""
        return list({r.entity for r in self.result_sets})

    def get_set_names(self) -> list[str]:
        """返回所有节点集/单元集名称的去重列表。"""
        return list({r.set_name for r in self.result_sets if r.set_name})


def _is_numeric(s: str) -> bool:
    """检查字符串是否为数值。"""
    try:
        float(s)
        return True
    except ValueError:
        return False


def _parse_data_line(line: list[str], entity_loc: str) -> tuple[int, np.ndarray]:
    """
    解析数据行。

    Args:
        line: 分割后的行数据
        entity_loc: 结果位置

    Returns:
        (id, values_array)
    """
    id_ = int(line[0])  # 如果不是整数会抛出异常

    # 过滤掉非数值元素（如行尾的 'L'）
    numeric_values = [s for s in line[1:] if _is_numeric(s)]

    if entity_loc == ResultLocation.INT_PNT:
        # 积分点结果：id, int_pnt_id, value1, value2, ...
        # 实际格式可能是: elem_id int_pnt_id values...
        return id_, np.array([float(s) for s in numeric_values[1:]], dtype=float)

    return id_, np.array([float(s) for s in numeric_values], dtype=float)


def _parse_header_line(line: list[str]) -> tuple[str, str, float, tuple[str, ...]]:
    """
    解析结果头行。

    格式示例：
        displacements (vx,vy,vz) for set SET1 and time  0.1000000E+01
        stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz) for set SET2 and time  0.1000000E+01

    Returns:
        (entity_name, set_name, step_time, component_names)
    """
    line_text = ' '.join(line)

    # 跳过 total 行
    if line[0].lower() == 'total':
        raise ValueError("Skipping total line")

    # 解析时间值（最后一个数值）
    step_time = float(line[-1])

    # 解析 set_name
    set_name = ''
    try:
        idx_and = line.index('and')
        try:
            idx_set = line.index('set')
            set_name = ' '.join(line[idx_set + 1:idx_and])
        except ValueError:
            pass
    except ValueError:
        pass

    # 解析实体名称和分量
    # 实体名在 '(' 之前或 'for' 之前
    entity_name = ''
    component_names: tuple[str, ...] = ()

    # 提取分量名
    comp_match = re.findall(r'\((.*?)\)', line_text)
    if comp_match:
        # 处理分量名中的逗号分隔
        all_components = []
        for c in comp_match:
            # 有些格式是 "elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz"
            parts = c.replace(',', ' ').split()
            all_components.extend([p.strip() for p in parts if p.strip()])

        component_names = tuple(all_components)

    # 提取实体名
    for i, col in enumerate(line):
        if col.startswith('(') or col == 'for':
            entity_name = ' '.join(line[:i])
            break

    # 标准化实体名
    entity_name_lower = entity_name.lower()
    if 'displacement' in entity_name_lower:
        entity_name = 'U'
    elif 'force' in entity_name_lower or 'reaction' in entity_name_lower:
        entity_name = 'RF'
    elif 'stress' in entity_name_lower:
        entity_name = 'S'
    elif 'strain' in entity_name_lower and 'mechanical' not in entity_name_lower:
        entity_name = 'E'
    elif 'mechanical strain' in entity_name_lower:
        entity_name = 'ME'
    elif 'equivalent plastic' in entity_name_lower or 'peeq' in entity_name_lower:
        entity_name = 'PEEQ'
    elif 'volume' in entity_name_lower:
        entity_name = 'EVOL'
    elif 'coordinate' in entity_name_lower:
        entity_name = 'COORD'
    elif 'internal energy density' in entity_name_lower:
        entity_name = 'ENER'
    elif 'kinetic energy' in entity_name_lower:
        entity_name = 'ELKE'
    elif 'internal energy' in entity_name_lower:
        entity_name = 'ELSE'
    elif 'mass' in entity_name_lower:
        entity_name = 'EMAS'
    elif 'contact energy' in entity_name_lower:
        entity_name = 'CELS'
    elif 'contact stress' in entity_name_lower:
        entity_name = 'CSTR'
    elif 'contact displacement' in entity_name_lower or 'relative contact' in entity_name_lower:
        entity_name = 'CDIS'

    return entity_name, set_name, step_time, component_names


def _value_dict_to_array(
    value_dict: dict[int, list[np.ndarray]], entity_loc: str
) -> dict[int, np.ndarray]:
    """将值字典转换为 numpy 数组。"""
    if entity_loc == ResultLocation.INT_PNT:
        # 积分点：每个 ID 对应多个积分点
        return {id_: np.array(lst) for id_, lst in value_dict.items()}
    # 节点/单元：每个 ID 对应一个值数组
    return {id_: lst[0] for id_, lst in value_dict.items()}


def _get_no_components(value_dict: dict[int, np.ndarray]) -> int:
    """获取分量数。"""
    arr = next(iter(value_dict.values()))
    if len(arr.shape) == 1:
        return arr.shape[0]
    # 积分点情况：返回每行分量数
    return arr.shape[1] if arr.ndim > 1 else 1


def _detect_entity_type(entity_name: str) -> DatResultEntity:
    """从实体名称检测实体类型枚举。"""
    name_map = {
        'U': DatResultEntity.U,
        'RF': DatResultEntity.RF,
        'S': DatResultEntity.S,
        'E': DatResultEntity.E,
        'ME': DatResultEntity.ME,
        'PEEQ': DatResultEntity.PEEQ,
        'EVOL': DatResultEntity.EVOL,
        'COORD': DatResultEntity.COORD,
        'ENER': DatResultEntity.ENER,
        'ELKE': DatResultEntity.ELKE,
        'ELSE': DatResultEntity.ELSE,
        'EMAS': DatResultEntity.EMAS,
        'CELS': DatResultEntity.CELS,
        'CSTR': DatResultEntity.CSTR,
        'CDIS': DatResultEntity.CDIS,
    }
    return name_map.get(entity_name.upper(), DatResultEntity.U)


class DatReader:
    """
    .dat 文件状态机解析器。

    使用方法：
        reader = DatReader()
        result = reader.parse_file("output.dat")
    """

    class State:
        NONE = "NONE"
        RESULT_SET_OPEN = "RESULT_SET_OPEN"

    def __init__(self):
        self.state = self.State.NONE
        self.result_sets: list[DatResultSet] = []

        # 当前结果集的状态
        self.entity_name = ''
        self.set_name = ''
        self.step_time = 0.0
        self.step_no = 0
        self.step_inc = 0
        self.analysis_type = DatAnalysisType.STATIC
        self.component_names: tuple[str, ...] = ()
        self.value_dict: dict[int, list[np.ndarray]] = defaultdict(list)

    def parse_file(self, filepath: str | Path) -> DatResult:
        """
        解析 .dat 文件。

        Args:
            filepath: .dat 文件路径

        Returns:
            DatResult 对象

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件格式不支持（ccx < 2.22）
        """
        with open(filepath, encoding='utf-8', errors='replace') as f:
            lines = [line.strip() for line in f if line.strip()]

        return self._parse_lines(lines)

    def _parse_lines(self, lines: list[str]) -> DatResult:
        """解析行列表。"""
        self.result_sets = []
        self.step_no = 0
        self.step_inc = 0
        self.analysis_type = DatAnalysisType.STATIC

        has_step_word = False  # ccx >= 2.22 的标志

        i = 0
        while i < len(lines):
            line = lines[i]
            parts = line.split()

            if not parts:
                i += 1
                continue

            # 状态机
            if self.state == self.State.NONE:
                first_char = parts[0][0].upper() if parts[0] else ''

                # 检测 STEP 开始（可能有空格，如 "S T E P"）
                line_upper = line.upper().replace(' ', '')
                if first_char == 'S' and line_upper.startswith('STEP'):
                    has_step_word = True
                    self.step_no = int(parts[-1])
                    self.step_inc = 0
                    self.analysis_type = DatAnalysisType.STATIC

                # 检测 EIGENVALUENUMBER（模态/屈曲步）
                elif first_char == 'E' and line_upper.startswith('EIGENVALUENUMBER'):
                    self.step_inc = int(parts[-1])

                # 检测 INCREMENT（静态增量步）
                elif first_char == 'I' and line_upper.startswith('INCREMENT'):
                    self.step_inc = int(parts[-1])

                # 检测频率信息
                elif first_char == 'E' and line_upper.startswith('EIGENVALUEOUTPUT'):
                    self.analysis_type = DatAnalysisType.FREQUENCY

                # 检测屈曲信息
                elif first_char == 'B' and line_upper.startswith('BUCKLINGFACTOROUTPUT'):
                    self.analysis_type = DatAnalysisType.BUCKLE

                # 检测结果集开始
                elif self._is_result_header(line):
                    if not has_step_word:
                        raise ValueError(
                            "此 .dat 文件由 ccx < 2.22 生成，不支持解析。"
                            "请使用 ccx >= 2.22。"
                        )
                    try:
                        self._start_result_set(parts)
                        self.state = self.State.RESULT_SET_OPEN
                    except Exception:
                        pass

            elif self.state == self.State.RESULT_SET_OPEN:
                # 尝试解析数据行
                try:
                    entity_loc = ENTITY_2_LOCATION_MAP.get(
                        _detect_entity_type(self.entity_name),
                        ResultLocation.NODAL
                    )
                    id_, values = _parse_data_line(parts, entity_loc)
                    self.value_dict[id_].append(values)
                except (ValueError, IndexError):
                    # 不是数据行，结束当前结果集
                    self._finish_result_set()
                    self.state = self.State.NONE
                    continue

            i += 1

        # 处理最后的结果集
        if self.state == self.State.RESULT_SET_OPEN:
            self._finish_result_set()

        return DatResult(result_sets=self.result_sets)

    def _is_result_header(self, line: str) -> bool:
        """检查行是否为结果头行。"""
        # 常见结果类型关键词
        keywords = [
            'displacement', 'force', 'stress', 'strain', 'coordinate',
            'volume', 'energy', 'mass', 'contact', 'plastic'
        ]
        # 移除空格后转小写
        line_normalized = line.lower().replace(' ', '')
        return any(kw in line_normalized for kw in keywords)

    def _start_result_set(self, line: list[str]) -> None:
        """开始新的结果集。"""
        self.entity_name, self.set_name, self.step_time, self.component_names = \
            _parse_header_line(line)

        self.value_dict = defaultdict(list)

    def _finish_result_set(self) -> None:
        """完成结果集，添加到列表。"""
        if not self.value_dict:
            return

        entity_type = _detect_entity_type(self.entity_name)
        entity_loc = ENTITY_2_LOCATION_MAP.get(entity_type, ResultLocation.NODAL)

        values_arr = _value_dict_to_array(self.value_dict, entity_loc)
        no_comp = _get_no_components(values_arr)

        result_set = DatResultSet(
            entity=entity_type,
            no_components=no_comp,
            step_time=self.step_time,
            step_no=self.step_no,
            step_inc_no=self.step_inc,
            analysis_type=self.analysis_type,
            set_name=self.set_name,
            component_names=self.component_names[-no_comp:] if self.component_names else (),
            values=values_arr,
            entity_location=entity_loc,
        )
        self.result_sets.append(result_set)


def parse_dat(filepath: str | Path) -> DatResult:
    """
    解析 .dat 文件。

    Args:
        filepath: .dat 文件路径

    Returns:
        DatResult 对象

    Usage:
        result = parse_dat("output.dat")

        # 获取所有位移
        u_sets = result.get_result_sets_by(entity=DatResultEntity.U)

        # 获取 step=1 的应力
        s_sets = result.get_result_sets_by(entity=DatResultEntity.S, step_no=1)

        # 获取时间最接近 0.5 的结果
        sets_near_05 = result.get_result_sets_by(step_time=0.5)
    """
    reader = DatReader()
    return reader.parse_file(filepath)

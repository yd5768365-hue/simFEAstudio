# reference_cases.py
"""
参考案例库 — CalculiX 官方测试集

两阶段检索：
1. 分类树硬过滤（精确匹配，排除不相关案例）
2. 加权匹配排序（返回 Top-N 最近邻）
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

# ------------------------------------------------------------------ #
# 元数据结构
# ------------------------------------------------------------------ #


@dataclass
class CaseMetadata:
    """案例元数据。"""
    name: str
    element_type: str           # C3D8, S4, B31, etc.
    problem_type: str           # solid, shell, beam, 2D, acoustic, thermal
    analysis_type: str         # static, dynamic, modal, buckling, thermal
    boundary_type: str         # encastre, symmetry, displacement, equation, periodic
    load_type: str             # cload, dload, pressure, temperature, gravity
    load_magnitude: float     # 总载荷大小（归一化参考值）

    # 材料
    material_E: Optional[float] = None   # 弹性模量
    material_nu: Optional[float] = None  # 泊松比
    material_rho: Optional[float] = None # 密度

    # 几何
    node_count: int = 0
    element_count: int = 0
    model_size: Optional[float] = None   # 模型特征尺寸

    # 预期结果范围（从 .dat.ref 提取的真实值）
    expected_disp_max: Optional[float] = None
    expected_disp_min: Optional[float] = None
    expected_stress_max: Optional[float] = None
    expected_stress_min: Optional[float] = None

    # 文件路径
    inp_path: Optional[str] = None
    ref_path: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------ #
# 分类树 — Stage 1 硬过滤
# ------------------------------------------------------------------ #


class ClassificationTree:
    """
    分类树用于硬过滤。

    分类维度（按优先级）：
    1. problem_type — 几何类型（solid / shell / beam / 2D / acoustic / thermal）
    2. analysis_type — 分析类型（static / dynamic / modal / buckling / thermal）
    3. element_family — 单元族（C3D / S / B / CPS / CPE / ACPD）

    过滤时按维度逐层筛选，不匹配则直接排除。
    """

    DIMENSIONS = ["problem_type", "analysis_type", "element_family"]

    @classmethod
    def get_element_family(cls, element_type: str) -> str:
        """从单元类型提取单元族。"""
        et = element_type.upper()
        if et.startswith("C3D"):
            return "C3D"
        if et.startswith("S") and not et.startswith("SU"):
            return "S"  # 壳单元
        if et.startswith("B"):
            return "B"  # 梁单元
        if et.startswith("CPS") or et.startswith("CPE"):
            return "CPS_CPE"  # 平面应力/应变
        if et.startswith("ACPD"):
            return "ACPD"  # 声学
        if et.startswith("F"):
            return "F"  # 流体
        if et.startswith("SPRING"):
            return "SPRING"
        if et.startswith("MASS"):
            return "MASS"
        if et.startswith("UN"):
            return "UN"  # 用户单元
        return "OTHER"

    @classmethod
    def classify_problem_type(cls, element_type: str, inp_text: str) -> str:
        """从单元类型和 INP 内容推断问题类型。"""
        et = element_type.upper()
        inp_upper = inp_text.upper()

        # 声学
        if "ACOUSTIC" in inp_upper or et.startswith("ACPD"):
            return "acoustic"
        # 热分析
        if "*HEAT" in inp_upper or "*THERMAL" in inp_upper:
            return "thermal"
        # 梁
        if et.startswith("B"):
            return "beam"
        # 壳
        if et.startswith("S") and not et.startswith("SU"):
            return "shell"
        # 平面应力/应变
        if et.startswith("CPS") or et.startswith("CPE"):
            return "2D"
        # 实体
        if et.startswith("C3D"):
            return "solid"
        # 弹簧/质量
        if et.startswith("SPRING") or et.startswith("MASS"):
            return "discrete"
        return "other"

    @classmethod
    def classify_analysis_type(cls, inp_text: str) -> str:
        """从 INP 内容推断分析类型。"""
        inp_upper = inp_text.upper()
        if "*MODAL" in inp_upper or "*FREQUENCY" in inp_upper:
            return "modal"
        if "*BUCKLE" in inp_upper:
            return "buckle"
        if "*DYNAMIC" in inp_upper:
            return "dynamic"
        if "*HEAT" in inp_upper or "*THERMAL" in inp_upper:
            return "thermal"
        if "*COUPLED" in inp_upper or "*TEMPERATURE" in inp_upper:
            return "coupled"
        return "static"

    @classmethod
    def classify_boundary_type(cls, inp_text: str) -> str:
        """从 INP 内容推断边界条件类型。"""
        inp_upper = inp_text.upper()
        if "*ENCASTRE" in inp_upper:
            return "encastre"
        if "*SYMMETRY" in inp_upper:
            return "symmetry"
        if "*EQUATION" in inp_upper:
            return "equation"
        if "*PERIODIC" in inp_upper:
            return "periodic"
        if "*BOUNDARY" in inp_upper:
            # 进一步区分
            if inp_upper.count("*BOUNDARY") > 2:
                return "multi_displacement"
            return "displacement"
        if "*MPC" in inp_upper or "*COUP" in inp_upper:
            return "mpc"
        return "other"

    @classmethod
    def classify_load_type(cls, inp_text: str) -> str:
        """从 INP 内容推断载荷类型。"""
        inp_upper = inp_text.upper()
        if "*CLOAD" in inp_upper:
            return "cload"
        if "*DLOAD" in inp_upper:
            return "dload"
        if "*DSLOAD" in inp_upper or "*BOUNDARY" in inp_upper:
            return "pressure"
        if "*CFLUX" in inp_upper or "*DFLUX" in inp_upper:
            return "thermal_flux"
        if "*TEMPERATURE" in inp_upper:
            return "temperature"
        if "*GRAVITY" in inp_upper or "*DENSITY" in inp_upper:
            return "body_force"
        return "other"

    @classmethod
    def get_bucket_key(cls, metadata: CaseMetadata) -> str:
        """获取分类桶的 key。"""
        return f"{metadata.problem_type}|{metadata.analysis_type}|{cls.get_element_family(metadata.element_type)}"


# ------------------------------------------------------------------ #
# 加权匹配器 — Stage 2 排序
# ------------------------------------------------------------------ #


class WeightedMatcher:
    """
    加权匹配器用于在桶内排序。

    权重设计原则：
    - 高权重：直接决定物理行为（element_type, boundary_type）
    - 中权重：影响结果量级（material_E, load_type, load_magnitude）
    - 低权重：细节参数（nu）
    """

    WEIGHTS = {
        "element_type": 3.0,
        "boundary_type": 2.5,
        "problem_type": 2.0,
        "material_E": 1.5,
        "load_type": 1.5,
        "load_magnitude": 1.0,
        "analysis_type": 0.8,
        "material_nu": 0.5,
    }

    @classmethod
    def compute_similarity(
        cls,
        user_meta: CaseMetadata,
        ref_meta: CaseMetadata,
    ) -> float:
        """计算两个案例的相似度得分（0-1）。"""
        score = 0.0
        total_weight = sum(cls.WEIGHTS.values())

        # element_type（完全匹配才给分）
        if user_meta.element_type == ref_meta.element_type:
            score += cls.WEIGHTS["element_type"]
        else:
            # 同族单元给部分分
            user_family = ClassificationTree.get_element_family(user_meta.element_type)
            ref_family = ClassificationTree.get_element_family(ref_meta.element_type)
            if user_family == ref_family:
                score += cls.WEIGHTS["element_type"] * 0.5

        # boundary_type
        if user_meta.boundary_type == ref_meta.boundary_type:
            score += cls.WEIGHTS["boundary_type"]

        # problem_type
        if user_meta.problem_type == ref_meta.problem_type:
            score += cls.WEIGHTS["problem_type"]

        # material_E（对数尺度比较）
        if user_meta.material_E and ref_meta.material_E:
            ratio = max(user_meta.material_E, ref_meta.material_E) / min(user_meta.material_E, ref_meta.material_E)
            if ratio < 1.5:
                score += cls.WEIGHTS["material_E"]
            elif ratio < 3.0:
                score += cls.WEIGHTS["material_E"] * 0.5

        # load_type
        if user_meta.load_type == ref_meta.load_type:
            score += cls.WEIGHTS["load_type"]

        # load_magnitude（对数尺度比较）
        if user_meta.load_magnitude and ref_meta.load_magnitude:
            mag_ratio = max(user_meta.load_magnitude, ref_meta.load_magnitude) / min(user_meta.load_magnitude, ref_meta.load_magnitude)
            if mag_ratio < 2.0:
                score += cls.WEIGHTS["load_magnitude"]
            elif mag_ratio < 10.0:
                score += cls.WEIGHTS["load_magnitude"] * 0.3

        # analysis_type
        if user_meta.analysis_type == ref_meta.analysis_type:
            score += cls.WEIGHTS["analysis_type"]

        # material_nu
        if user_meta.material_nu and ref_meta.material_nu:
            nu_diff = abs(user_meta.material_nu - ref_meta.material_nu)
            if nu_diff < 0.05:
                score += cls.WEIGHTS["material_nu"]
            elif nu_diff < 0.1:
                score += cls.WEIGHTS["material_nu"] * 0.3

        return score / total_weight


# ------------------------------------------------------------------ #
# 案例数据库
# ------------------------------------------------------------------ #


class CaseDatabase:
    """
    参考案例数据库。

    支持：
    - 从 JSON 加载
    - 两阶段检索（分类树 + 加权匹配）
    """

    def __init__(self, cases: list[CaseMetadata]):
        self.cases = cases
        self._buckets: dict[str, list[CaseMetadata]] = {}

        # 构建分类桶
        for case in cases:
            key = ClassificationTree.get_bucket_key(case)
            self._buckets.setdefault(key, []).append(case)

    @classmethod
    def from_json(cls, json_path: Path) -> "CaseDatabase":
        """从 JSON 文件加载。"""
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        cases = []
        for name, meta_dict in data.items():
            meta_dict.pop("name", None)  # 避免重复 name 参数
            cases.append(CaseMetadata(name=name, **meta_dict))

        return cls(cases)

    def find_similar(
        self,
        user_meta: CaseMetadata,
        top_n: int = 5,
    ) -> list[tuple[CaseMetadata, float]]:
        """
        查找最相似的案例。

        Args:
            user_meta: 用户案例的元数据
            top_n: 返回前 N 个最相似案例

        Returns:
            [(案例, 相似度得分), ...]，按得分降序排列
        """
        # Stage 1: 分类树硬过滤
        bucket_key = ClassificationTree.get_bucket_key(user_meta)
        bucket = self._buckets.get(bucket_key, [])

        # 如果精确桶为空，尝试放宽条件
        if not bucket:
            # 尝试：同 problem_type + 同 analysis_type
            bucket = [
                c for c in self.cases
                if c.problem_type == user_meta.problem_type
                and c.analysis_type == user_meta.analysis_type
            ]

        if not bucket:
            # 最后手段：同 problem_type
            bucket = [
                c for c in self.cases
                if c.problem_type == user_meta.problem_type
            ]

        # Stage 2: 加权匹配排序
        scored = [
            (case, WeightedMatcher.compute_similarity(user_meta, case))
            for case in bucket
        ]
        scored.sort(key=lambda x: x[1], reverse=True)

        return scored[:top_n]


# ------------------------------------------------------------------ #
# 工具函数
# ------------------------------------------------------------------ #


def parse_inp_metadata(inp_path: Path) -> CaseMetadata:
    """
    从 INP 文件解析元数据。

    提取：单元类型、材料参数、边界条件类型、载荷类型、节点/单元数
    """
    text = inp_path.read_text(encoding="utf-8", errors="replace")

    # 提取名称
    name = inp_path.stem

    # 提取单元类型
    element_type = "UNKNOWN"
    for line in text.splitlines():
        if line.upper().startswith("*ELEMENT"):
            parts = line.split(",")
            for p in parts:
                p = p.strip().upper()
                if p.startswith("TYPE="):
                    element_type = p.split("=")[1].strip()
                    break

    # 提取材料参数
    material_E = None
    material_nu = None
    for i, line in enumerate(text.splitlines()):
        if line.upper().startswith("*ELASTIC"):
            # 读取下一行
            if i + 1 < len(text.splitlines()):
                next_line = text.splitlines()[i + 1]
                parts = re.findall(r'[+-]?\d+\.?\d*(?:[eE][-+]?\d+)?', next_line)
                if len(parts) >= 1:
                    material_E = float(parts[0])
                if len(parts) >= 2:
                    material_nu = float(parts[1])

    # 节点数和单元数
    node_count = 0
    element_count = 0
    in_node_section = False
    in_element_section = False

    for line in text.splitlines():
        ul = line.upper().strip()
        if ul.startswith("*NODE"):
            in_node_section = True
            in_element_section = False
        elif ul.startswith("*ELEMENT"):
            in_node_section = False
            in_element_section = True
        elif ul.startswith("*") and not ul.startswith("*NODE") and not ul.startswith("*ELEMENT"):
            in_node_section = False
            in_element_section = False
        elif in_node_section and line.strip() and not line.strip().startswith("*"):
            node_count += 1
        elif in_element_section and line.strip() and not line.strip().startswith("*"):
            element_count += 1

    # 分类
    problem_type = ClassificationTree.classify_problem_type(element_type, text)
    analysis_type = ClassificationTree.classify_analysis_type(text)
    boundary_type = ClassificationTree.classify_boundary_type(text)
    load_type = ClassificationTree.classify_load_type(text)

    # 计算载荷大小（归一化）
    load_magnitude = _extract_load_magnitude(text)

    # 模型尺寸
    model_size = _extract_model_size(text)

    return CaseMetadata(
        name=name,
        element_type=element_type,
        problem_type=problem_type,
        analysis_type=analysis_type,
        boundary_type=boundary_type,
        load_type=load_type,
        load_magnitude=load_magnitude,
        material_E=material_E,
        material_nu=material_nu,
        node_count=node_count,
        element_count=element_count,
        model_size=model_size,
        inp_path=str(inp_path),
    )


def _extract_load_magnitude(text: str) -> float:
    """提取总载荷大小。"""
    total = 0.0
    for line in text.splitlines():
        ul = line.upper().strip()
        if ul.startswith("*CLOAD"):
            parts = re.findall(r'[+-]?\d+\.?\d*(?:[eE][-+]?\d+)?', line)
            for p in parts:
                try:
                    val = float(p)
                    if val > 0 and val < 1e15:
                        total += abs(val)
                except ValueError:
                    pass
        elif ul.startswith("*DLOAD"):
            parts = re.findall(r'[+-]?\d+\.?\d*(?:[eE][-+]?\d+)?', line)
            for p in parts:
                try:
                    val = float(p)
                    if val > 0 and val < 1e15:
                        total += abs(val)
                except ValueError:
                    pass
    return total if total > 0 else 1.0  # 默认 1.0


def _extract_model_size(text: str) -> Optional[float]:
    """估算模型特征尺寸（从节点坐标范围）。"""
    coords = []
    in_node = False
    for line in text.splitlines():
        if line.upper().strip().startswith("*NODE"):
            in_node = True
            continue
        if line.upper().strip().startswith("*") and in_node:
            in_node = False
        if in_node:
            parts = re.findall(r'[+-]?\d+\.?\d*(?:[eE][-+]?\d+)?', line)
            if len(parts) >= 3:
                try:
                    coords.append((float(parts[1]), float(parts[2]), float(parts[3])))
                except (ValueError, IndexError):
                    pass

    if not coords:
        return None

    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    zs = [c[2] for c in coords]

    return max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))

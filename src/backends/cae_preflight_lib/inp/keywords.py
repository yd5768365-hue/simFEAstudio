"""
INP 关键词 Python 类封装

将 kw_list.json 中的关键词定义转换为类型安全的 Python dataclass。
支持从 Block 自动构建关键词对象，便于操作和验证。

Usage:
    from cae_preflight_lib.inp.keywords import KeywordRegistry

    # 获取关键词类
    Elastic = KeywordRegistry.get("ELASTIC")
    mat = Elastic(params={"TYPE": "ISO"}, data=[[210000, 0.3]])

    # 从 Block 构建
    block = Block(keyword_name="*ELASTIC", lead_line="*ELASTIC,TYPE=ISO", data_lines=["210000, 0.3"])
    kw = KeywordRegistry.from_block(block)
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, TypeVar

if TYPE_CHECKING:
    from cae_preflight_lib.inp import Block

__all__ = [
    "KeywordRegistry",
    "KeywordBase",
    "ParamDef",
    "KeywordDef",
]

# =============================================================================
# 懒加载关键词定义
# =============================================================================

_kw_definitions: Optional[dict[str, KeywordDef]] = None


def _load_kw_definitions() -> dict[str, KeywordDef]:
    """懒加载关键词定义（kw_list.json → KeywordDef）。"""
    global _kw_definitions
    if _kw_definitions is None:
        kw_path = Path(__file__).parent / "kw_list.json"
        with open(kw_path, encoding="utf-8") as f:
            raw = json.load(f)

        _kw_definitions = {}
        for kw_name, kw_info in raw.items():
            args = []
            for arg in kw_info.get("arguments", []):
                param = ParamDef(
                    name=arg.get("name", ""),
                    form=arg.get("form", "Line"),
                    required=arg.get("required", False),
                    options=arg.get("options", ""),
                    default=arg.get("default"),
                    comment=arg.get("comment", ""),
                    newline=arg.get("newline", False),
                    use=arg.get("use", ""),
                    group_form=arg.get("group_form", ""),
                )
                args.append(param)

            _kw_definitions[kw_name.upper().lstrip("*")] = KeywordDef(
                name=kw_name,
                arguments=args,
            )

    return _kw_definitions


# =============================================================================
# 关键词元数据
# =============================================================================


class ParamForm(str, Enum):
    """参数形式。"""
    LINE = "Line"         # 行内参数
    INT = "Int"          # 整数
    FLOAT = "Float"      # 浮点数
    BOOL = "Bool"        # 布尔
    COMBO = "Combo"      # 下拉选择
    TEXT = "Text"         # 文本


@dataclass(frozen=True)
class ParamDef:
    """关键词参数定义。"""
    name: str
    form: str = "Line"
    required: bool = False
    options: str = ""       # COMBO 类型的选项，用 | 分隔
    default: Optional[str] = None
    comment: str = ""
    newline: bool = False   # 是否需要换行
    use: str = ""           # 引用其他关键词（如 "*MATERIAL"）
    group_form: str = ""    # 分组形式（如 "Table", "HBox"）


@dataclass(frozen=True)
class KeywordDef:
    """关键词定义元数据。"""
    name: str                    # 关键词全名，如 "*ELASTIC"
    arguments: list[ParamDef] = field(default_factory=list)

    def get_param(self, name: str) -> Optional[ParamDef]:
        """按名称查找参数定义（不区分大小写）。"""
        name_upper = name.upper()
        for arg in self.arguments:
            if arg.name.upper() == name_upper:
                return arg
        return None

    @property
    def required_params(self) -> list[ParamDef]:
        """返回所有必填参数。"""
        return [a for a in self.arguments if a.required]

    @property
    def optional_params(self) -> list[ParamDef]:
        """返回所有可选参数。"""
        return [a for a in self.arguments if not a.required]


# =============================================================================
# 关键词基类
# =============================================================================

K = TypeVar("K", bound="KeywordBase")


class KeywordBase(ABC):
    """
    关键词基类。

    所有关键词类都继承此类，提供统一的接口。
    子类需要定义：
      - keyword_name: 关键词名称（不含 *）
      - params: 参数字典
      - data: 数据行列表
    """

    keyword_name: str = ""

    def __init__(
        self,
        params: Optional[dict[str, Any]] = None,
        data: Optional[list[list[float]]] = None,
    ):
        self.params: dict[str, Any] = params or {}
        self.data: list[list[float]] = data or []

    @abstractmethod
    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        ...

    def to_block_data(self) -> tuple[list[str], list[str]]:
        """转换为 Block 的 lead_line 和 data_lines。"""
        lines = self.to_inp_lines()
        lead_line = lines[0] if lines else ""
        data_lines = lines[1:] if len(lines) > 1 else []
        return lead_line, data_lines

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())


# =============================================================================
# 常用关键词类
# =============================================================================


class KeywordRegistry:
    """
    关键词注册表。

    提供从 kw_list.json 动态创建的关键词类，
    以及从 Block 构建关键词对象的功能。

    Usage:
        # 获取关键词定义
        def_ = KeywordRegistry.get_def("ELASTIC")

        # 从 Block 构建关键词对象
        block = Block(keyword_name="*ELASTIC", lead_line="*ELASTIC,TYPE=ISO", data_lines=["210000, 0.3"])
        kw = KeywordRegistry.from_block(block)
    """

    _cache: dict[str, type[KeywordBase]] = {}

    @classmethod
    def get_def(cls, keyword: str) -> Optional[KeywordDef]:
        """
        获取关键词定义元数据。

        Args:
            keyword: 关键词名（如 "ELASTIC", "*ELASTIC", "elastic"）

        Returns:
            KeywordDef 或 None
        """
        kw_clean = keyword.upper().lstrip("*")
        defs = _load_kw_definitions()
        return defs.get(kw_clean)

    @classmethod
    def get(cls, keyword: str) -> type[KeywordBase]:
        """
        获取关键词类（动态创建）。

        Args:
            keyword: 关键词名

        Returns:
            动态创建的关键词类
        """
        kw_clean = keyword.upper().lstrip("*")

        if kw_clean in cls._cache:
            return cls._cache[kw_clean]

        # 动态创建类
        def_ = cls.get_def(keyword)
        if def_ is None:
            raise ValueError(f"未知关键词: {keyword}")

        cls._cache[kw_clean] = cls._create_class(def_)
        return cls._cache[kw_clean]

    @classmethod
    def _create_class(cls, def_: KeywordDef) -> type[KeywordBase]:
        """根据 KeywordDef 动态创建关键词类。"""
        kw_name = def_.name.lstrip("*")

        class DynamicKeyword(KeywordBase):
            keyword_name: str = def_.name

            def __init__(
                self,
                params: Optional[dict[str, Any]] = None,
                data: Optional[list[list[float]]] = None,
            ):
                super().__init__(params=params, data=data)

            def to_inp_lines(self) -> list[str]:
                lines = [self.keyword_name]
                # 添加参数（所有传入的 params，不只看 def_.arguments）
                param_parts = []
                for key, val in self.params.items():
                    if val is None:
                        continue
                    # 查找参数定义
                    param_def = None
                    for p in def_.arguments:
                        if p.name.upper() == key.upper():
                            param_def = p
                            break
                    # 根据参数类型决定格式
                    if param_def and param_def.form == "Bool":
                        param_parts.append(param_def.name)
                    else:
                        param_parts.append(f"{key}={val}")

                if param_parts:
                    lines[0] = f"{self.keyword_name},{','.join(param_parts)}"

                # 添加数据行
                for row in self.data:
                    lines.append(", ".join(str(v) for v in row))
                return lines

        DynamicKeyword.__name__ = f"Kw_{kw_name}"
        DynamicKeyword.__qualname__ = f"Kw_{kw_name}"
        return DynamicKeyword

    @classmethod
    def from_block(cls, block: "Block") -> Optional[KeywordBase]:
        """
        从 Block 构建关键词对象。

        Args:
            block: Block 实例

        Returns:
            KeywordBase 子类实例，或 None（如果未找到定义）
        """

        def_ = cls.get_def(block.keyword_name)
        if def_ is None:
            return None

        # 解析参数
        params: dict[str, Any] = {}
        for arg in def_.arguments:
            val = block.get_param(arg.name)
            if val is not None:
                # 类型转换
                if arg.form == "Int":
                    val = int(val)
                elif arg.form == "Float":
                    val = float(val)
                params[arg.name.upper()] = val

        # 解析数据行
        data: list[list[float]] = []
        number_pattern = r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?"
        for line in block.data_lines:
            nums = re.findall(number_pattern, line)
            row = [float(n) for n in nums]
            if row:
                data.append(row)

        # 创建对象
        kw_cls = cls.get(block.keyword_name)
        return kw_cls(params=params, data=data)


# =============================================================================
# 常用关键词便捷函数
# =============================================================================


def create_elastic(
    elastic_type: str = "ISO",
    E: Optional[float] = None,
    nu: Optional[float] = None,
    **kwargs: Any,
) -> KeywordBase:
    """
    创建 *ELASTIC 关键词。

    Args:
        elastic_type: 弹性类型 ISO/ORTHO/ENGINEERING CONSTANTS/ANISO
        E: 弹性模量（ISO 类型）
        nu: 泊松比（ISO 类型）
        **kwargs: 其他参数

    Returns:
        ELASTIC 关键词对象
    """
    cls = KeywordRegistry.get("ELASTIC")
    params: dict[str, Any] = {"TYPE": elastic_type}
    data: list[list[float]] = []

    if elastic_type == "ISO" and E is not None and nu is not None:
        data.append([E, nu])
    elif kwargs:
        data.append([kwargs.get(k, 0) for k in ["E", "nu", "G12", "G13", "G23"]])

    return cls(params=params, data=data)


def create_material(name: str) -> KeywordBase:
    """
    创建 *MATERIAL 关键词。

    Args:
        name: 材料名称

    Returns:
        MATERIAL 关键词对象
    """
    cls = KeywordRegistry.get("MATERIAL")
    return cls(params={"NAME": name})


def create_solid_section(
    elset: str,
    material: str,
    orientation: Optional[str] = None,
) -> KeywordBase:
    """
    创建 *SOLID SECTION 关键词。

    Args:
        elset: 单元集名称
        material: 材料名称
        orientation: 方向名称（可选）

    Returns:
        SOLID SECTION 关键词对象
    """
    cls = KeywordRegistry.get("SOLID SECTION")
    params: dict[str, Any] = {"ELSET": elset, "MATERIAL": material}
    if orientation:
        params["ORIENTATION"] = orientation
    return cls(params=params)


def create_step(
    nlgeom: bool = False,
    inc: Optional[int] = None,
) -> KeywordBase:
    """
    创建 *STEP 关键词。

    Args:
        nlgeom: 是否启用几何非线性
        inc: 最大增量步数

    Returns:
        STEP 关键词对象
    """
    cls = KeywordRegistry.get("STEP")
    params: dict[str, Any] = {}
    if nlgeom:
        params["NLGEOM"] = "YES"
    if inc is not None:
        params["INC"] = str(inc)
    return cls(params=params)


def create_static() -> KeywordBase:
    """创建 *STATIC 关键词（静力学分析步）。"""
    cls = KeywordRegistry.get("STATIC")
    return cls(params={})


def create_boundary(
    nset: str,
    dof_start: int = 1,
    dof_end: int = 3,
    value: float = 0.0,
) -> KeywordBase:
    """
    创建 *BOUNDARY 关键词。

    Args:
        nset: 节点集名称
        dof_start: 起始自由度
        dof_end: 终止自由度
        value: 约束值（默认为0）

    Returns:
        BOUNDARY 关键词对象
    """
    cls = KeywordRegistry.get("BOUNDARY")
    params: dict[str, Any] = {"NSET": nset}
    data = [[nset, dof_start, dof_end, value]]
    return cls(params=params, data=data)


def create_cload(
    node: int,
    dof: int,
    value: float,
) -> KeywordBase:
    """
    创建 *CLOAD 关键词。

    Args:
        node: 节点编号或节点集名称
        dof: 自由度编号
        value: 载荷值

    Returns:
        CLOAD 关键词对象
    """
    cls = KeywordRegistry.get("CLOAD")
    params: dict[str, Any] = {}
    data = [[node, dof, value]]
    return cls(params=params, data=data)


def create_node_set(
    name: str,
    nset: str,
    generate: bool = False,
) -> KeywordBase:
    """
    创建 *NSET 关键词（节点集）。

    Args:
        name: 节点集名称
        nset: 同 name
        generate: 是否使用 GENERATE 范围生成

    Returns:
        NSET 关键词对象
    """
    cls = KeywordRegistry.get("NSET")
    params: dict[str, Any] = {"NSET": name}
    if generate:
        params["GENERATE"] = ""
    return cls(params=params)


def create_element(
    element_type: str,
    elset: Optional[str] = None,
) -> KeywordBase:
    """
    创建 *ELEMENT 关键词。

    Args:
        element_type: 单元类型（如 C3D8, C3D4, S4）
        elset: 单元集名称（可选）

    Returns:
        ELEMENT 关键词对象
    """
    cls = KeywordRegistry.get("ELEMENT")
    params: dict[str, Any] = {"TYPE": element_type}
    if elset:
        params["ELSET"] = elset
    return cls(params=params)

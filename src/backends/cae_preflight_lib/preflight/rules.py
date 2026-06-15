"""求解前验证规则元数据。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleInfo:
    rule_id: str
    category: str
    title: str
    explanation: str
    suggestions: list[str]
    possible_solver_errors: list[str]


RULES: dict[str, RuleInfo] = {
    "CAE-STRUCT-001": RuleInfo(
        "CAE-STRUCT-001",
        "structure",
        "缺少节点定义",
        "输入文件缺少 *NODE，求解器无法获得模型节点坐标。",
        ["添加有效的 *NODE 节点定义。", "确认节点定义没有被注释或放在未包含的文件中。"],
        ["输入文件解析失败", "模型拓扑不完整"],
    ),
    "CAE-STRUCT-002": RuleInfo(
        "CAE-STRUCT-002",
        "structure",
        "缺少单元定义",
        "输入文件缺少 *ELEMENT，求解器无法建立单元拓扑。",
        ["添加有效的 *ELEMENT 单元定义。", "确认网格导出过程包含单元数据。"],
        ["输入文件解析失败", "模型拓扑不完整"],
    ),
    "CAE-MAT-001": RuleInfo(
        "CAE-MAT-001",
        "material",
        "缺少材料定义",
        "输入文件缺少 *MATERIAL，截面或材料属性无法绑定到材料定义。",
        ["添加 *MATERIAL, NAME=<材料名>。", "补充弹性、密度等必要材料属性。"],
        ["材料分配错误", "刚度矩阵构建失败"],
    ),
    "CAE-MAT-002": RuleInfo(
        "CAE-MAT-002",
        "material",
        "材料引用未定义",
        "某个关键字引用了不存在的材料名。",
        ["定义被引用的材料。", "或修正引用处的材料名称。"],
        ["材料分配错误", "输入文件解析失败"],
    ),
    "CAE-MAT-003": RuleInfo(
        "CAE-MAT-003",
        "material",
        "材料定义未被任何截面使用",
        "输入文件定义了材料但没有任何截面引用它，可能是名称不匹配或多余定义。",
        ["检查截面中的 MATERIAL 参数是否与材料名称一致。", "删除未使用的材料定义。"],
        ["材料分配错误"],
    ),
    "CAE-SEC-001": RuleInfo(
        "CAE-SEC-001",
        "section",
        "缺少截面定义",
        "输入文件缺少实体、壳或梁截面定义，单元可能没有材料或截面属性。",
        ["添加 *SOLID SECTION、*SHELL SECTION 或 *BEAM SECTION。"],
        ["单元属性缺失", "材料分配错误"],
    ),
    "CAE-SEC-002": RuleInfo(
        "CAE-SEC-002",
        "section",
        "截面引用了未定义材料",
        "截面引用了未定义的材料，通常会导致求解器报错。",
        ["定义该材料。", "或修正截面中的 MATERIAL 参数。"],
        ["材料分配错误", "输入文件解析失败"],
    ),
    "CAE-SEC-003": RuleInfo(
        "CAE-SEC-003",
        "section",
        "截面引用了未定义单元集",
        "截面定义中的 ELSET 参数引用了不存在的单元集。",
        ["使用 *ELSET, ELSET=<名称> 定义该单元集。", "或修正截面定义中的 ELSET 参数。"],
        ["单元属性缺失", "集合引用错误"],
    ),
    "CAE-SET-001": RuleInfo(
        "CAE-SET-001",
        "set",
        "节点集引用未找到",
        "某处引用了不存在的节点集。",
        ["定义对应的 *NSET。", "或修正引用名称。"],
        ["集合引用错误", "边界或载荷无法施加"],
    ),
    "CAE-SET-002": RuleInfo(
        "CAE-SET-002",
        "set",
        "单元集引用未找到",
        "某处引用了不存在的单元集。",
        ["定义对应的 *ELSET。", "或修正引用名称。"],
        ["集合引用错误", "载荷或截面无法施加"],
    ),
    "CAE-BC-001": RuleInfo(
        "CAE-BC-001",
        "boundary",
        "缺少边界条件",
        "输入文件缺少 *BOUNDARY，静力结构分析中模型可能存在刚体运动。",
        ["添加足够的 *BOUNDARY 约束。", "检查是否需要固定刚体自由度。"],
        ["奇异矩阵", "零主元", "刚体运动"],
    ),
    "CAE-BC-002": RuleInfo(
        "CAE-BC-002",
        "boundary",
        "边界条件引用了未定义节点集",
        "边界条件引用了不存在的节点集。",
        ["定义该 *NSET。", "或修正边界条件中的集合名称。"],
        ["集合引用错误", "边界条件无法施加"],
    ),
    "CAE-LOAD-001": RuleInfo(
        "CAE-LOAD-001",
        "load",
        "集中载荷引用了未定义节点集",
        "集中载荷引用了不存在的节点集。",
        ["定义该 *NSET。", "或改用有效节点或节点集名称。"],
        ["集合引用错误", "载荷无法施加"],
    ),
    "CAE-LOAD-002": RuleInfo(
        "CAE-LOAD-002",
        "load",
        "分布载荷引用了未定义单元集",
        "分布载荷引用了不存在的单元集。",
        ["定义该 *ELSET。", "或修正 *DLOAD 引用名称。"],
        ["集合引用错误", "载荷无法施加"],
    ),
    "CAE-STEP-001": RuleInfo(
        "CAE-STEP-001",
        "step",
        "缺少分析步",
        "输入文件缺少 *STEP，求解器没有可执行的分析过程。",
        ["添加 *STEP、分析过程关键字和 *END STEP。"],
        ["没有分析步", "求解无法启动"],
    ),
    "CAE-STEP-002": RuleInfo(
        "CAE-STEP-002",
        "step",
        "分析步未闭合",
        "分析步开始和结束数量不匹配。",
        ["为每个 *STEP 添加匹配的 *END STEP。"],
        ["输入文件解析失败", "分析步定义错误"],
    ),
}

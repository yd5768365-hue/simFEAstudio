"""面向 Abaqus/CalculiX 输入文件的确定性求解前检查。"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from cae_preflight_lib.inp import Block, InpParser
from cae_preflight_lib.preflight.config import PipelineConfig
from cae_preflight_lib.preflight.models import IssueLocation, PreflightIssue, PreflightResult, Severity
from cae_preflight_lib.preflight.rules import RULES

SECTION_KEYWORDS = {"*SOLID SECTION", "*SHELL SECTION", "*BEAM SECTION"}
SUPPORTED_SOLVERS = {"calculix", "abaqus"}


def run_preflight(
    inp_file: Path,
    *,
    solver: str = "calculix",
    category: Optional[str] = None,
    strict_static: bool = False,
    pipeline: Optional[PipelineConfig] = None,
) -> PreflightResult:
    solver_name = solver.lower().strip()
    if solver_name not in SUPPORTED_SOLVERS:
        raise ValueError(f"不支持的求解器: {solver}")

    parser = InpParser()
    blocks = parser.parse(inp_file)
    context = _InpContext(inp_file=inp_file, blocks=blocks)

    issues: list[PreflightIssue] = []
    issues.extend(_check_structure(context))
    issues.extend(_check_materials(context))
    issues.extend(_check_sections(context))
    issues.extend(_check_boundaries(context, strict_static=strict_static))
    issues.extend(_check_loads(context))
    issues.extend(_check_steps(context))

    if category:
        category_name = category.lower().strip()
        issues = [issue for issue in issues if issue.category == category_name]

    pipeline_config = pipeline or PipelineConfig.default()
    return PreflightResult(
        input_file=inp_file,
        solver=solver_name,
        issues=issues,
        pipeline=pipeline_config.to_dict(),
    )


def explain_rule(rule_id: str, *, lang: str = "zh") -> Optional[str]:
    rule = RULES.get(rule_id.upper().strip())
    if rule is None:
        return None

    suggestions = "\n".join(f"- {item}" for item in rule.suggestions)
    solver_errors = "\n".join(f"- {item}" for item in rule.possible_solver_errors)
    return (
        f"{rule.rule_id}: {rule.title}\n\n"
        f"类别: {rule.category}\n"
        f"解释: {rule.explanation}\n"
        f"建议:\n{suggestions}\n"
        f"可能关联的求解器错误:\n{solver_errors}"
    )


class _InpContext:
    def __init__(self, *, inp_file: Path, blocks: list[Block]) -> None:
        self.inp_file = inp_file
        self.blocks = blocks
        self.by_keyword: dict[str, list[Block]] = {}
        for block in blocks:
            self.by_keyword.setdefault(block.keyword_name.upper(), []).append(block)

        self.materials = {
            name.upper()
            for name in _defined_names(self.blocks_for("*MATERIAL"), "NAME")
            if name
        }
        self.nsets = {
            name.upper()
            for name in _defined_names(self.blocks_for("*NSET"), "NSET")
            if name
        }
        self.elsets = {
            name.upper()
            for name in _defined_names(self.blocks_for("*ELSET"), "ELSET")
            if name
        }

    def blocks_for(self, keyword: str) -> list[Block]:
        return self.by_keyword.get(keyword.upper(), [])

    def has_keyword(self, keyword: str) -> bool:
        return bool(self.blocks_for(keyword))


def _defined_names(blocks: Iterable[Block], param: str) -> list[str]:
    names: list[str] = []
    for block in blocks:
        value = block.get_param(param)
        if value:
            names.append(value.strip())
    return names


_SAFE_FIX_RULES = {"CAE-STEP-001", "CAE-STEP-002"}


def _issue(
    ctx: _InpContext,
    rule_id: str,
    severity: Severity,
    message: str,
    *,
    block: Optional[Block] = None,
    evidence: Optional[list[str]] = None,
    suggestions: Optional[list[str]] = None,
) -> PreflightIssue:
    rule = RULES[rule_id]
    return PreflightIssue(
        rule_id=rule_id,
        severity=severity,
        category=rule.category,
        title=rule.title,
        message=message,
        location=IssueLocation(
            file=ctx.inp_file.name,
            line=block.line_range[0] + 1 if block is not None else None,
        ),
        evidence=evidence or ([block.lead_line] if block is not None else []),
        suggestions=suggestions or list(rule.suggestions),
        possible_solver_errors=list(rule.possible_solver_errors),
        confidence=1.0,
        safe_fix_available=rule_id in _SAFE_FIX_RULES,
    )


def _check_structure(ctx: _InpContext) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    if not ctx.has_keyword("*NODE"):
        issues.append(_issue(ctx, "CAE-STRUCT-001", Severity.ERROR, "缺少 *NODE 节点定义。"))
    if not ctx.has_keyword("*ELEMENT"):
        issues.append(_issue(ctx, "CAE-STRUCT-002", Severity.ERROR, "缺少 *ELEMENT 单元定义。"))
    return issues


def _check_materials(ctx: _InpContext) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    if not ctx.has_keyword("*MATERIAL"):
        issues.append(_issue(ctx, "CAE-MAT-001", Severity.ERROR, "缺少 *MATERIAL 材料定义。"))
        return issues
    # 收集所有截面实际引用的材料名
    referenced: set[str] = set()
    for kw in SECTION_KEYWORDS:
        for block in ctx.blocks_for(kw):
            m = block.get_param("MATERIAL")
            if m:
                referenced.add(m.upper())
    for block in ctx.blocks_for("*MATERIAL"):
        name = block.get_param("NAME")
        if name and name.upper() not in referenced:
            issues.append(
                _issue(
                    ctx,
                    "CAE-MAT-003",
                    Severity.WARNING,
                    f"材料 {name} 定义了但未被任何截面引用。",
                    block=block,
                )
            )
    return issues


def _check_sections(ctx: _InpContext) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    section_blocks = [block for keyword in SECTION_KEYWORDS for block in ctx.blocks_for(keyword)]
    if not section_blocks:
        issues.append(_issue(ctx, "CAE-SEC-001", Severity.ERROR, "缺少截面定义。"))
        return issues

    for block in section_blocks:
        material = block.get_param("MATERIAL")
        if material and material.upper() not in ctx.materials:
            issues.append(
                _issue(
                    ctx,
                    "CAE-SEC-002",
                    Severity.ERROR,
                    f"截面引用了未定义材料: {material}",
                    block=block,
                    suggestions=[
                        f"使用 *MATERIAL, NAME={material} 定义材料 {material}。",
                        "或修正截面定义中的 MATERIAL 参数。",
                    ],
                )
            )
        elset = block.get_param("ELSET")
        if elset and elset.upper() not in ctx.elsets:
            issues.append(
                _issue(
                    ctx,
                    "CAE-SEC-003",
                    Severity.ERROR,
                    f"截面引用了未定义单元集: {elset}",
                    block=block,
                    suggestions=[
                        f"使用 *ELSET, ELSET={elset} 定义单元集 {elset}。",
                        "或修正截面定义中的 ELSET 参数。",
                    ],
                )
            )
    return issues


def _check_boundaries(ctx: _InpContext, *, strict_static: bool) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    boundary_blocks = ctx.blocks_for("*BOUNDARY")
    if not boundary_blocks:
        return [
            _issue(
                ctx,
                "CAE-BC-001",
                Severity.ERROR if strict_static else Severity.WARNING,
                "缺少 *BOUNDARY 边界条件。",
            )
        ]

    for block in boundary_blocks:
        references = _node_set_references(block)
        for ref in references:
            if ref.upper() not in ctx.nsets:
                issues.append(
                    _issue(
                        ctx,
                        "CAE-BC-002",
                        Severity.ERROR,
                        f"边界条件引用了未定义节点集: {ref}",
                        block=block,
                        evidence=[block.lead_line, *_matching_data_lines(block, ref)],
                        suggestions=[
                            f"使用 *NSET, NSET={ref} 定义节点集 {ref}。",
                            "或修正边界条件中的节点集名称。",
                        ],
                    )
                )
    return issues


def _check_loads(ctx: _InpContext) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    for block in ctx.blocks_for("*CLOAD"):
        for ref in _node_set_references(block):
            if ref.upper() not in ctx.nsets:
                issues.append(
                    _issue(
                        ctx,
                        "CAE-LOAD-001",
                        Severity.ERROR,
                        f"*CLOAD 引用了未定义节点集: {ref}",
                        block=block,
                        evidence=[block.lead_line, *_matching_data_lines(block, ref)],
                        suggestions=[
                            f"使用 *NSET, NSET={ref} 定义节点集 {ref}。",
                            "或修正 *CLOAD 的施加载荷对象。",
                        ],
                    )
                )

    for block in ctx.blocks_for("*DLOAD"):
        for ref in _element_set_references(block):
            if ref.upper() not in ctx.elsets:
                issues.append(
                    _issue(
                        ctx,
                        "CAE-LOAD-002",
                        Severity.ERROR,
                        f"*DLOAD 引用了未定义单元集: {ref}",
                        block=block,
                        evidence=[block.lead_line, *_matching_data_lines(block, ref)],
                        suggestions=[
                            f"使用 *ELSET, ELSET={ref} 定义单元集 {ref}。",
                            "或修正 *DLOAD 的施加载荷对象。",
                        ],
                    )
                )
    return issues


def _check_steps(ctx: _InpContext) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    step_count = len(ctx.blocks_for("*STEP"))
    end_step_count = len(ctx.blocks_for("*END STEP"))
    if step_count == 0:
        issues.append(_issue(ctx, "CAE-STEP-001", Severity.ERROR, "缺少 *STEP 分析步。"))
    if step_count != end_step_count:
        step_block = ctx.blocks_for("*STEP")[0] if ctx.blocks_for("*STEP") else None
        issues.append(
            _issue(
                ctx,
                "CAE-STEP-002",
                Severity.ERROR,
                f"*STEP / *END STEP 不平衡: {step_count} 个 *STEP，{end_step_count} 个 *END STEP。",
                block=step_block,
            )
        )
    return issues


def _node_set_references(block: Block) -> list[str]:
    refs: list[str] = []
    param_ref = block.get_param("NSET")
    if param_ref:
        refs.append(param_ref.strip())
    for line in block.data_lines:
        token = _first_data_token(line)
        if token and not _looks_numeric(token):
            refs.append(token)
    return _dedupe(refs)


def _element_set_references(block: Block) -> list[str]:
    refs: list[str] = []
    param_ref = block.get_param("ELSET")
    if param_ref:
        refs.append(param_ref.strip())
    for line in block.data_lines:
        token = _first_data_token(line)
        if token and not _looks_numeric(token):
            refs.append(token)
    return _dedupe(refs)


def _first_data_token(line: str) -> str:
    return line.split(",", 1)[0].strip()


def _looks_numeric(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def _matching_data_lines(block: Block, ref: str) -> list[str]:
    needle = ref.lower()
    return [line for line in block.data_lines if needle in line.lower()]


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.upper()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result

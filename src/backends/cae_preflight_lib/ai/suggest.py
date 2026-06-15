# suggest.py
"""
优化建议生成

基于诊断结果生成优化建议。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .llm_client import LLMClient
from .prompts import make_suggest_prompt
from .stream_handler import StreamHandler
from .diagnose import DiagnoseResult, DiagnosticIssue
from .explain import _find_frd, _extract_stats
from cae_preflight_lib.viewer.frd_parser import parse_frd


@dataclass
class Suggestion:
    """优化建议条目。"""
    category: str  # "material" | "mesh" | "boundary" | "geometry"
    priority: int  # 1-5, 1 最高
    title: str
    description: str
    expected_improvement: str
    implementation_difficulty: str  # "easy" | "medium" | "hard"


@dataclass
class SuggestResult:
    """优化建议结果。"""
    success: bool
    suggestions: list[Suggestion] = field(default_factory=list)
    summary: str = ""
    error: Optional[str] = None


def suggest_results(
    results_dir: Path,
    diagnose_result: DiagnoseResult,
    client: Optional[LLMClient],
    *,
    stream: bool = True,
) -> SuggestResult:
    """
    基于诊断结果生成优化建议。

    Args:
        results_dir: 包含 .frd 文件的目录
        diagnose_result: 来自 diagnose_results() 的诊断结果
        client: LLM 客户端（可选）
        stream: 是否流式输出

    Returns:
        SuggestResult
    """
    try:
        # 提取关键指标
        frd_file = _find_frd(results_dir)
        max_stress = 0.0
        max_displacement = 0.0
        material_yield = 250e6

        if frd_file:
            try:
                frd_data = parse_frd(frd_file)
                stats = _extract_stats(frd_data)
                max_stress = stats["max_stress"]
                max_displacement = stats["max_displacement"]
            except Exception:
                pass

        # 规则建议（不依赖 AI）
        suggestions: list[Suggestion] = []
        suggestions.extend(_rule_based_suggestions(diagnose_result.issues))

        # AI 建议（如果可用）
        ai_summary = ""
        if client:
            issue_dicts = [
                {
                    "severity": i.severity,
                    "category": i.category,
                    "message": i.message,
                }
                for i in diagnose_result.issues
            ]
            prompt_text = make_suggest_prompt(
                issue_dicts,
                diagnose_result.ai_diagnosis or "",
                max_stress,
                max_displacement,
                material_yield,
            )

            if stream:
                handler = StreamHandler()
                tokens = client.complete_streaming(prompt_text)
                ai_text = handler.stream_tokens(tokens)
            else:
                ai_text = client.complete(prompt_text)

            ai_suggestions = _parse_ai_suggestions(ai_text)
            suggestions.extend(ai_suggestions)
            ai_summary = ai_text

        # 按优先级排序
        suggestions.sort(key=lambda s: s.priority)

        # 限制数量
        suggestions = suggestions[:10]

        return SuggestResult(
            success=True,
            suggestions=suggestions,
            summary=ai_summary,
        )

    except Exception as exc:
        return SuggestResult(success=False, error=f"建议生成失败: {exc}")


def _rule_based_suggestions(issues: list[DiagnosticIssue]) -> list[Suggestion]:
    """基于规则检测结果生成基础建议。"""
    suggestions: list[Suggestion] = []

    for issue in issues:
        if issue.category == "convergence":
            suggestions.append(Suggestion(
                category="boundary",
                priority=1,
                title="检查边界条件和载荷设置",
                description=f"求解收敛失败：{issue.message}",
                expected_improvement="消除收敛问题，获得有效解",
                implementation_difficulty="medium",
            ))
        elif issue.category == "mesh_quality":
            suggestions.append(Suggestion(
                category="mesh",
                priority=2,
                title="优化网格划分",
                description=f"网格质量警告：{issue.message}",
                expected_improvement="提高计算精度，避免虚假应力集中",
                implementation_difficulty="medium",
            ))
        elif issue.category == "stress_concentration":
            suggestions.append(Suggestion(
                category="geometry",
                priority=2,
                title="缓解应力集中",
                description=f"应力集中：{issue.message}",
                expected_improvement="降低峰值应力，提高疲劳寿命",
                implementation_difficulty="hard",
            ))
        elif issue.category == "displacement":
            suggestions.append(Suggestion(
                category="geometry",
                priority=2,
                title="增强结构刚度",
                description=f"位移过大：{issue.message}",
                expected_improvement="减小变形，满足刚度要求",
                implementation_difficulty="medium",
            ))

    return suggestions


def _parse_ai_suggestions(text: str) -> list[Suggestion]:
    """解析 AI 返回的 JSON 建议列表。"""
    suggestions: list[Suggestion] = []

    # 尝试提取 JSON 数组
    json_match = re.search(r"\[[\s\S]*\]", text)
    if json_match:
        try:
            data = json.loads(json_match.group())
            for item in data:
                suggestions.append(Suggestion(
                    category=item.get("category", "geometry"),
                    priority=int(item.get("priority", 3)),
                    title=item.get("title", "优化建议"),
                    description=item.get("description", ""),
                    expected_improvement=item.get("expected_improvement", ""),
                    implementation_difficulty=item.get("implementation_difficulty", "medium"),
                ))
            return suggestions
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

    # 回退：简单文本解析
    lines = text.strip().splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if len(line) > 20:
            suggestions.append(Suggestion(
                category="geometry",
                priority=3,
                title=line[:50],
                description=line,
                expected_improvement="待评估",
                implementation_difficulty="medium",
            ))

    return suggestions

# ai 模块
"""
CAE-CLI AI 模式模块

提供：
  - LLMClient: llama-server 进程管理
  - StreamHandler: 流式输出处理
  - explain: AI 结果解读
  - diagnose: 规则检测 + AI 诊断
  - suggest: 优化建议生成
  - CadGenerator: CadQuery 几何生成

懒加载 heavy dependencies（llama-cpp-python, cadquery）。
"""
from __future__ import annotations

from cae_preflight_lib.ai.cad_generator import BeamParams, CadGenerator, CylinderParams, PlateParams
from cae_preflight_lib.ai.diagnose import diagnose_results
from cae_preflight_lib.ai.explain import explain_results
from cae_preflight_lib.ai.llm_client import LLMClient, LLMConfig
from cae_preflight_lib.ai.stream_handler import StreamHandler
from cae_preflight_lib.ai.suggest import suggest_results

__all__ = [
    # LLM 客户端
    "LLMClient",
    "LLMConfig",
    # 流式处理
    "StreamHandler",
    # 结果类型（懒加载）
    "ExplainResult",
    "DiagnosticIssue",
    "DiagnoseResult",
    "Suggestion",
    "SuggestResult",
    "CadResult",
    "BeamParams",
    "CylinderParams",
    "PlateParams",
    "ChainReasoningResult",
    # 函数
    "explain_results",
    "diagnose_results",
    "suggest_results",
    "CadGenerator",
    "ChainReasoner",
]


def __getattr__(name: str):
    """懒加载重类型，避免导入 heavy dependencies。"""
    if name in ("ExplainResult",):
        from cae_preflight_lib.ai.explain import ExplainResult
        return ExplainResult
    if name in ("DiagnosticIssue", "DiagnoseResult"):
        from cae_preflight_lib.ai.diagnose import DiagnosticIssue, DiagnoseResult
        if name == "DiagnosticIssue":
            return DiagnosticIssue
        return DiagnoseResult
    if name in ("Suggestion", "SuggestResult"):
        from cae_preflight_lib.ai.suggest import Suggestion, SuggestResult
        if name == "Suggestion":
            return Suggestion
        return SuggestResult
    if name in ("CadResult",):
        from cae_preflight_lib.ai.cad_generator import CadResult
        return CadResult
    if name in ("ChainReasoningResult",):
        from cae_preflight_lib.ai.chain_reasoning import ChainReasoningResult
        return ChainReasoningResult
    if name in ("ChainReasoner",):
        from cae_preflight_lib.ai.chain_reasoning import ChainReasoner
        return ChainReasoner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

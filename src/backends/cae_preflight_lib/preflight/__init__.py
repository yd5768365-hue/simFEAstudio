"""CAE 求解前验证包。"""

from cae_preflight_lib.preflight.config import PipelineConfig, PreflightConfig, StageConfig, load_config
from cae_preflight_lib.preflight.models import (
    CheckSummary,
    IssueLocation,
    PreflightIssue,
    PreflightResult,
    RiskLevel,
    Severity,
)
from cae_preflight_lib.preflight.runner import explain_rule, run_preflight

__all__ = [
    "CheckSummary",
    "IssueLocation",
    "PreflightConfig",
    "PreflightIssue",
    "PreflightResult",
    "PipelineConfig",
    "RiskLevel",
    "Severity",
    "StageConfig",
    "explain_rule",
    "load_config",
    "run_preflight",
]

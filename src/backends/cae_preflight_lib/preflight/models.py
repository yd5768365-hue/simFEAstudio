"""求解前验证的结构化数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class Severity(str, Enum):
    FATAL = "FATAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class RiskLevel(str, Enum):
    PASS = "PASS"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class IssueLocation:
    file: str
    line: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "line": self.line}


@dataclass(frozen=True)
class PreflightIssue:
    rule_id: str
    severity: Severity
    category: str
    title: str
    message: str
    location: IssueLocation
    evidence: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    possible_solver_errors: list[str] = field(default_factory=list)
    confidence: float = 1.0
    safe_fix_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "category": self.category,
            "title": self.title,
            "message": self.message,
            "location": self.location.to_dict(),
            "evidence": list(self.evidence),
            "suggestions": list(self.suggestions),
            "possible_solver_errors": list(self.possible_solver_errors),
            "confidence": self.confidence,
            "safe_fix_available": self.safe_fix_available,
        }


@dataclass(frozen=True)
class CheckSummary:
    category: str
    passed: bool
    issue_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "passed": self.passed,
            "issue_count": self.issue_count,
        }


@dataclass
class PreflightResult:
    input_file: Path
    solver: str
    issues: list[PreflightIssue] = field(default_factory=list)
    pipeline: dict[str, Any] = field(default_factory=dict)
    version: str = "0.1.0"

    @property
    def success(self) -> bool:
        return not any(issue.severity in {Severity.FATAL, Severity.ERROR} for issue in self.issues)

    @property
    def status(self) -> str:
        if not self.success:
            return "BLOCKED"
        if any(i.severity == Severity.WARNING for i in self.issues):
            return "PASS_WITH_WARNINGS"
        if any(i.severity == Severity.INFO for i in self.issues):
            return "PASS_WITH_INFO"
        return "PASS"

    @property
    def risk_level(self) -> RiskLevel:
        severities = {issue.severity for issue in self.issues}
        if not severities:
            return RiskLevel.PASS
        if Severity.FATAL in severities or Severity.ERROR in severities:
            return RiskLevel.HIGH
        if Severity.WARNING in severities:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    @property
    def summary(self) -> dict[str, int]:
        return {
            "total": len(self.issues),
            "fatal": sum(1 for issue in self.issues if issue.severity == Severity.FATAL),
            "error": sum(1 for issue in self.issues if issue.severity == Severity.ERROR),
            "warning": sum(1 for issue in self.issues if issue.severity == Severity.WARNING),
            "info": sum(1 for issue in self.issues if issue.severity == Severity.INFO),
        }

    @property
    def checks(self) -> list[CheckSummary]:
        categories = [
            "structure",
            "material",
            "section",
            "set",
            "boundary",
            "load",
            "step",
        ]
        return [
            CheckSummary(
                category=category,
                passed=not any(issue.category == category for issue in self.issues),
                issue_count=sum(1 for issue in self.issues if issue.category == category),
            )
            for category in categories
        ]

    def _build_action_plan(self) -> dict[str, Any]:
        if self.status == "BLOCKED":
            return {
                "recommended_action": "fix_before_run",
                "next_steps": [
                    "修复所有 ERROR / FATAL 级别问题。",
                    "重新运行 cae preflight 验证。",
                    "通过后再运行求解器。",
                ],
            }
        if self.status == "PASS_WITH_WARNINGS":
            return {
                "recommended_action": "review_warnings",
                "next_steps": [
                    "检查 WARNING 问题是否影响当前工况。",
                    "可继续运行求解器。",
                ],
            }
        return {
            "recommended_action": "ready_to_run",
            "next_steps": ["未发现问题，可直接运行求解器。"],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status,
            "risk_level": self.risk_level.value,
            "summary": self.summary,
            "issues": [issue.to_dict() for issue in self.issues],
            "action_plan": self._build_action_plan(),
            "pipeline": self.pipeline,
            "checks": [check.to_dict() for check in self.checks],
            "meta": {
                "solver": self.solver,
                "input_file": str(self.input_file),
                "version": self.version,
            },
        }

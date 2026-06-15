"""cae.toml 配置文件加载器。"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]


IMPLEMENTED_STAGES = {"syntax", "rules"}
KNOWN_STAGES = {
    "syntax",
    "rules",
    "safe_fix",
    "solver_run",
    "read_result",
    "mesh_advice",
    "ai_explain",
    "report",
}
DEFAULT_STAGE_ENABLED = {
    "syntax": True,
    "rules": True,
    "safe_fix": False,
    "solver_run": False,
    "read_result": False,
    "mesh_advice": False,
    "ai_explain": False,
    "report": False,
}


@dataclass(frozen=True)
class StageConfig:
    name: str
    enabled: bool
    implemented: bool

    @property
    def status(self) -> str:
        if not self.enabled:
            return "disabled"
        if not self.implemented:
            return "skipped"
        return "completed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "implemented": self.implemented,
            "status": self.status,
        }


@dataclass(frozen=True)
class PipelineConfig:
    stages: list[StageConfig] = field(default_factory=list)
    unknown_stages: list[str] = field(default_factory=list)

    @classmethod
    def default(cls) -> "PipelineConfig":
        return cls(
            stages=[
                StageConfig(
                    name=name,
                    enabled=enabled,
                    implemented=name in IMPLEMENTED_STAGES,
                )
                for name, enabled in DEFAULT_STAGE_ENABLED.items()
            ]
        )

    def enabled_unimplemented_stages(self) -> list[str]:
        return [
            stage.name
            for stage in self.stages
            if stage.enabled and not stage.implemented
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "stages": [stage.to_dict() for stage in self.stages],
        }


@dataclass
class PreflightConfig:
    solver: str = "calculix"
    strict: bool = False
    strict_static: bool = False
    output_format: str = "rich"
    pipeline: PipelineConfig = field(default_factory=PipelineConfig.default)
    config_path: Optional[Path] = None
    parse_error: Optional[str] = None


def load_config(config_file: Optional[Path] = None) -> PreflightConfig:
    """从 cae.toml 加载配置，找不到时返回默认值。"""
    if tomllib is None:
        return PreflightConfig(parse_error="当前 Python 环境缺少 TOML 解析支持。")

    path = config_file or Path("cae.toml")
    if not path.exists():
        return PreflightConfig()

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return PreflightConfig(config_path=path, parse_error=str(exc))

    pf = data.get("preflight", {})
    stages_data = data.get("stages", {})
    pipeline = _load_pipeline_config(stages_data if isinstance(stages_data, dict) else {})
    return PreflightConfig(
        solver=str(pf.get("solver", "calculix")),
        strict=bool(pf.get("strict", False)),
        strict_static=bool(pf.get("strict_static", False)),
        output_format=str(pf.get("output_format", "rich")),
        pipeline=pipeline,
        config_path=path,
    )


def _load_pipeline_config(stages_data: dict[str, Any]) -> PipelineConfig:
    unknown = sorted(key for key in stages_data if key not in KNOWN_STAGES)
    stages = [
        StageConfig(
            name=name,
            enabled=bool(stages_data.get(name, DEFAULT_STAGE_ENABLED[name])),
            implemented=name in IMPLEMENTED_STAGES,
        )
        for name in DEFAULT_STAGE_ENABLED
    ]
    return PipelineConfig(stages=stages, unknown_stages=unknown)

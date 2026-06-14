from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import NamedTuple


TIER_DEFS = {
    "L1": ("L1 Example", "结果观察：先看输入、边界条件、量纲、结果指标和误差方向。"),
    "L2": ("L2 Benchmark", "机制重建：对照解析解和数值结果解释误差、刚度、载荷与边界。"),
    "L3": ("L3 Miniapp", "真实工具链：关注输入预检查、求解流程、日志、归档和可复盘证据。"),
}


class BenchmarkCase(NamedTuple):
    name: str
    title: str
    level: str
    physics: str
    dimension: str
    methods: tuple[str, ...]
    status: str


def load_cases(root: Path) -> list[BenchmarkCase]:
    cases: list[BenchmarkCase] = []
    if not root.exists():
        return cases
    for case_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        meta_path = case_dir / "case.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        methods = meta.get("methods", [])
        cases.append(
            BenchmarkCase(
                name=case_dir.name,
                title=str(meta.get("title", case_dir.name)),
                level=str(meta.get("level", "L1")),
                physics=str(meta.get("physics", "")),
                dimension=str(meta.get("dimension", "")),
                methods=tuple(str(method) for method in methods if method),
                status=str(meta.get("status", "")),
            )
        )
    return cases


def build_learning_path(root: Path) -> str:
    cases = load_cases(root)
    lines = [
        "# Benchmark Learning Path",
        "",
        "这个索引借鉴 MFEM 的 examples / miniapps 分层，以及 FEniCSx demo 的教学表达：",
        "",
        "物理问题 -> 离散化 -> 求解方法 -> 派生量 -> 复盘问题",
        "",
        "## 分层原则",
        "",
        "- L1 Example：结果可观察，优先建立量纲、边界条件和结果指标感。",
        "- L2 Benchmark：机制重建，重点比较解析解、传统 FEM 和误差来源。",
        "- L3 Miniapp：真实工具链，强调输入质量、运行日志、结果归档和证据链。",
        "",
    ]

    for level in ("L1", "L2", "L3"):
        title, body = TIER_DEFS[level]
        tier_cases = [case for case in cases if case.level == level]
        lines.extend([
            f"## {title}",
            "",
            body,
            "",
            "| 目录 | 案例 | 物理 | 维度 | 方法 | 状态 |",
            "| --- | --- | --- | --- | --- | --- |",
        ])
        if tier_cases:
            for case in tier_cases:
                methods = ", ".join(case.methods)
                lines.append(
                    f"| `{case.name}` | {case.title} | {case.physics} | {case.dimension} | {methods} | {case.status} |"
                )
        else:
            lines.append("| - | 暂无 | - | - | - | - |")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    root = Path(args[0]) if args else Path("learning") / "benchmarks"
    output = Path(args[1]) if len(args) > 1 else root / "LEARNING_PATH.md"
    output.write_text(build_learning_path(root), encoding="utf-8")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

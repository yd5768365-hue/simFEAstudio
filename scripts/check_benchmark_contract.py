from __future__ import annotations

import json
import sys
from pathlib import Path


REQUIRED_CASE_KEYS = ("title", "methods", "level")
REQUIRED_WORKFLOW_STAGES = ("geometry", "mesh", "solver", "post", "evidence")


def load_case_data(case_dir: Path) -> tuple[dict, list[str]]:
    case_json = case_dir / "case.json"
    if not case_json.exists():
        return {}, ["missing case.json"]

    try:
        return json.loads(case_json.read_text(encoding="utf-8")), []
    except json.JSONDecodeError as exc:
        return {}, [f"invalid case.json: {exc.msg}"]


def workflow_stage_coverage(case_dir: Path, data: dict | None = None) -> set[str]:
    case_data = data if data is not None else load_case_data(case_dir)[0]
    declared = case_data.get("workflow_stages")
    if isinstance(declared, list):
        return {str(stage) for stage in declared}

    stages: set[str] = set()
    if any(case_dir.glob("*问题描述.md")) or (case_dir / "problem.md").exists():
        stages.add("geometry")
        stages.add("evidence")
    if case_data.get("dimension") or any(case_dir.rglob("*.inp")):
        stages.add("mesh")
    if case_data.get("methods") or any(case_dir.rglob("*.inp")):
        stages.add("solver")
    results_dir = case_dir / "results"
    if results_dir.exists() and any(results_dir.glob("*.csv")):
        stages.add("post")
        stages.add("evidence")
    return stages


def check_case(case_dir: Path) -> list[str]:
    issues: list[str] = []
    data, data_issues = load_case_data(case_dir)
    if data_issues:
        return data_issues

    for key in REQUIRED_CASE_KEYS:
        if key not in data:
            issues.append(f"missing case.json key: {key}")

    if not any(case_dir.glob("*问题描述.md")) and not (case_dir / "problem.md").exists():
        issues.append("missing problem markdown")

    results_dir = case_dir / "results"
    if not results_dir.exists():
        issues.append("missing results directory")
    elif not any(results_dir.glob("*.csv")):
        issues.append("missing results csv")

    stages = workflow_stage_coverage(case_dir, data)
    for stage in REQUIRED_WORKFLOW_STAGES:
        if stage not in stages:
            issues.append(f"missing workflow stage: {stage}")

    return issues


def benchmark_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir() and not path.name.startswith("."))


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    root = Path(args[0]) if args else Path("learning") / "benchmarks"
    failures: dict[str, list[str]] = {}

    for case_dir in benchmark_dirs(root):
        issues = check_case(case_dir)
        if issues:
            failures[case_dir.name] = issues

    if failures:
        print("Benchmark contract issues:")
        for case_name, issues in failures.items():
            print(f"- {case_name}")
            for issue in issues:
                print(f"  - {issue}")
        return 1

    print(f"Benchmark contract OK: {len(benchmark_dirs(root))} cases checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

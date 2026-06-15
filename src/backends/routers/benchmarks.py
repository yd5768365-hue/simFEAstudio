"""Benchmark Lab endpoints."""

import csv
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

try:
    from ..simfea_api.config import PROJECT_ROOT
except ImportError:
    from simfea_api.config import PROJECT_ROOT

benchmarks_router = APIRouter(prefix="/v1")
BENCHMARKS_DIR = PROJECT_ROOT / "learning" / "benchmarks"
DEFAULT_GROUP = "基础案例"
LEARNING_TIER_DEFS = {
    "L1": {"id": "L1", "label": "L1 Example", "focus": "result observation"},
    "L2": {"id": "L2", "label": "L2 Benchmark", "focus": "mechanism reconstruction"},
    "L3": {"id": "L3", "label": "L3 Miniapp", "focus": "tool-chain workflow"},
}


def _read_case_meta(case_dir: Path) -> dict:
    """Read optional case.json metadata."""
    meta_file = case_dir / "case.json"
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if isinstance(meta, dict):
                return meta
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _learning_tier(level: str) -> dict | None:
    return LEARNING_TIER_DEFS.get(level.upper())


def _extract_title_subtitle(md_path: Path) -> tuple[str, str]:
    """Extract the first H1 heading as title and the next meaningful line as subtitle."""
    import re

    title = ""
    subtitle = ""
    if not md_path.exists():
        return title, subtitle
    try:
        text = md_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        past_h1 = False
        for line in lines:
            stripped = line.strip()
            if not past_h1:
                if stripped.startswith("# ") and not stripped.startswith("## "):
                    title = stripped[2:].strip()
                    past_h1 = True
            else:
                if not stripped or stripped.startswith("#") or stripped.startswith("```") or stripped.startswith("|"):
                    continue
                subtitle = re.sub(r'\*\*|__|\$', '', stripped)[:80]
                break
    except OSError:
        pass
    return title, subtitle


@benchmarks_router.get("/benchmarks")
def list_benchmarks():
    if not BENCHMARKS_DIR.exists():
        return {"message": "No benchmarks found.", "data": {"cases": []}}
    cases = []
    for case_dir in sorted(BENCHMARKS_DIR.iterdir()):
        if not case_dir.is_dir():
            continue
        problem_file = case_dir / "问题描述.md"
        if not problem_file.exists():
            problem_file = case_dir / "problem.md"
        results_file = case_dir / "results" / "对比结果.csv"
        if not results_file.exists():
            results_file = case_dir / "results" / "comparison.csv"
        title, subtitle = _extract_title_subtitle(problem_file)
        meta = _read_case_meta(case_dir)
        level = str(meta.get("level", ""))
        cases.append({
            "name": case_dir.name,
            "has_problem": problem_file.exists(),
            "has_results": results_file.exists(),
            "group": meta.get("group", DEFAULT_GROUP),
            "title": title or meta.get("title", ""),
            "subtitle": subtitle,
            "level": level,
            "physics": meta.get("physics", ""),
            "dimension": meta.get("dimension", ""),
            "methods": meta.get("methods", []),
            "status": meta.get("status", ""),
            "learning_tier": _learning_tier(level),
        })
    return {
        "message": f"Found {len(cases)} benchmark case(s).",
        "data": {"cases": cases},
    }


@benchmarks_router.get("/benchmarks/{case_name}")
def get_benchmark_case(case_name: str):
    case_dir = BENCHMARKS_DIR / case_name
    if not case_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Benchmark case '{case_name}' not found")
    meta = _read_case_meta(case_dir)
    level = str(meta.get("level", ""))
    problem_html = ""
    html_file = case_dir / "问题描述.html"
    if not html_file.exists():
        html_file = case_dir / "problem.html"
    if html_file.exists():
        problem_html = html_file.read_text(encoding="utf-8")
    problem_md = ""
    if not problem_html:
        md_file = case_dir / "问题描述.md"
        if not md_file.exists():
            md_file = case_dir / "problem.md"
        if md_file.exists():
            problem_md = md_file.read_text(encoding="utf-8")
    results = []
    results_file = case_dir / "results" / "对比结果.csv"
    if not results_file.exists():
        results_file = case_dir / "results" / "comparison.csv"
    if results_file.exists():
        with results_file.open(encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                results.append(dict(row))
    return {
        "message": f"Benchmark case '{case_name}'",
        "data": {
            "name": case_name,
            "group": meta.get("group", DEFAULT_GROUP),
            "title": meta.get("title", ""),
            "level": level,
            "physics": meta.get("physics", ""),
            "dimension": meta.get("dimension", ""),
            "methods": meta.get("methods", []),
            "status": meta.get("status", ""),
            "learning_tier": _learning_tier(level),
            "problem_html": problem_html,
            "problem_md": problem_md,
            "results": results,
        },
    }

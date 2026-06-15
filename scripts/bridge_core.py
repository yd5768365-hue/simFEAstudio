r"""Bridge SimFEA Studio benchmark cases → SimFEA-Lab Core solver.

Reads case parameters from Studio's benchmark directories, runs
SimFEA-Lab Core's bridge_runner, and updates the comparison CSV
with the simfea-core results row.

Usage:
    python scripts/bridge_core.py --core-build F:/path/to/core/build 01_一维杆拉伸
    python scripts/bridge_core.py --core-build F:/path/to/core/build --all

Requirements:
    - SimFEA-Lab Core build path passed with --core-build or SIMFEA_CORE_BUILD
    - bridge_runner.exe available
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from io import StringIO
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parent.parent
BENCH_DIR = STUDIO_ROOT / "learning" / "benchmarks"
CORE_BUILD_ENV = "SIMFEA_CORE_BUILD"

# ── Unit conversion ──────────────────────────────────────────
# Studio uses mm units; Core uses SI (m).
# Convert: mm → m (÷1000), MPa → Pa (×1e6), mm² → m² (÷1e6)

def _mm_to_m(v: float) -> float: return v / 1000.0
def _mpa_to_pa(v: float) -> float: return v * 1e6
def _mm2_to_m2(v: float) -> float: return v / 1e6

def _m_to_mm(v: float) -> float: return v * 1000.0
def _pa_to_mpa(v: float) -> float: return v / 1e6


# ── Parameter extractors per case type ───────────────────────

def _extract_bar_tension(case_dir: Path) -> dict | None:
    """Extract L, E, A, P from a 1D bar tension case."""
    md = case_dir / "问题描述.md"
    if not md.exists():
        return None
    text = md.read_text(encoding="utf-8")

    params = {}
    # Match markdown table rows: | 参数 | 符号 | 值 | 单位 |
    # Pattern: | 杆长 | L | 100 | mm |
    patterns = {
        "L": r"\|\s*(?:杆长|长度|轴长|跨[度距]|筒体长度)\s*\|\s*\w+\s*\|\s*([\d.\s]+?)\s*\|",
        "E": r"\|\s*(?:弹性模量|剪切模量)\s*\|\s*[EG]\s*\|\s*([\d.\s]+?)\s*\|",
        "P": r"\|\s*(?:拉力|端部拉力|集中力|竖向力|内压|扭矩|温升|法向力|线载荷)\s*\|\s*[TPFpq]\s*\|\s*([\d.\s]+?)\s*\|",
    }

    def _parse_num(s: str) -> float:
        return float(s.replace(" ", ""))

    for key, pat in patterns.items():
        m = re.search(pat, text)
        if m:
            params[key] = _parse_num(m.group(1))

    # Special handling for area: direct A / b×h / πd²/4
    a_m = re.search(r"\|\s*截面积\s*\|\s*A\s*\|\s*([\d.\s]+?)\s*\|", text)
    b_m = re.search(r"\|\s*截面宽\s*\|\s*b\s*\|\s*([\d.\s]+?)\s*\|", text)
    h_m = re.search(r"\|\s*截面高\s*\|\s*h\s*\|\s*([\d.\s]+?)\s*\|", text)
    d_m = re.search(r"\|\s*轴径\s*\|\s*d\s*\|\s*([\d.\s]+?)\s*\|", text)
    if "A" not in params:
        if a_m:
            params["A"] = _parse_num(a_m.group(1))
        elif b_m and h_m:
            params["A"] = _parse_num(b_m.group(1)) * _parse_num(h_m.group(1))
        elif d_m:
            import math
            params["A"] = math.pi * _parse_num(d_m.group(1))**2 / 4

    required = {"L", "E", "A", "P"}
    if not required.issubset(params.keys()):
        missing = required - params.keys()
        print(f"  !! Missing params: {missing}")
        return None

    # Convert to SI
    return {
        "length": _mm_to_m(params["L"]),
        "elastic_modulus": _mpa_to_pa(params["E"]),
        "area": _mm2_to_m2(params["A"]),
        "force": params["P"],
    }


# ── Case type → extractor mapping ────────────────────────────

CASE_EXTRACTORS = {
    "01_一维杆拉伸": ("bar_tension", _extract_bar_tension),
    "02_一维杆分布载荷": ("bar_tension", _extract_bar_tension),
    "10_阶梯杆拉伸": ("bar_tension", _extract_bar_tension),
}


def resolve_core_build(core_build_arg: str | None, env: dict[str, str] = os.environ) -> Path | None:
    """Resolve the SimFEA-Lab Core build directory from CLI or environment."""
    core_build = core_build_arg or env.get(CORE_BUILD_ENV)
    return Path(core_build) if core_build else None


def run_core(case_dir: Path, core_build: Path, bridge_exe: Path) -> dict | None:
    """Run Core solver for a benchmark case, return results dict."""
    case_name = case_dir.name
    if case_name not in CASE_EXTRACTORS:
        print(f"  skip: {case_name} (not yet supported)")
        return None

    _, extractor = CASE_EXTRACTORS[case_name]
    params = extractor(case_dir)
    if params is None:
        return None

    if not bridge_exe.exists():
        print(f"  !! bridge_runner.exe not found at {bridge_exe}")
        print(f"     Build Core first: cd {core_build.parent} && cmake --build . --target bridge_runner")
        return None

    args = [
        str(bridge_exe),
        str(params["length"]),
        str(params["elastic_modulus"]),
        str(params["area"]),
        str(params["force"]),
    ]

    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=10, cwd=str(core_build))
        if proc.returncode > 1:
            print(f"  !! Core error: {proc.stderr.strip()}")
            return None
        result = json.loads(proc.stdout.strip())
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        print(f"  !! Core run failed: {e}")
        return None

    # Convert SI → Studio units (mm, MPa)
    return {
        "u_L_mm": f"{_m_to_mm(result['tip_displacement_m']):.6f}",
        "sigma_MPa": f"{_pa_to_mpa(result['stress_pa']):.6f}",
        "error_u_L_mm": f"{abs(_m_to_mm(result['error'])):.6e}",
        "notes": f"SimFEA-Lab Core C++ 1D bar (verification: {result['verification']})",
    }


def update_csv(case_dir: Path, core_result: dict) -> bool:
    """Update 对比结果.csv — add or replace simfea-core row."""
    csv_path = case_dir / "results" / "对比结果.csv"
    if not csv_path.exists():
        csv_path = case_dir / "results" / "comparison.csv"
    if not csv_path.exists():
        print(f"  !! CSV not found for {case_dir.name}")
        return False

    # Read existing rows
    text = csv_path.read_text(encoding="utf-8").strip()
    reader = csv.DictReader(StringIO(text))
    fieldnames = reader.fieldnames or []
    rows = [dict(row) for row in reader]

    # Build simfea-core row matching CSV columns
    core_row = {"method": "simfea-core"}
    for col in fieldnames:
        if col == "method":
            continue
        core_row[col] = core_result.get(col, "")

    # Replace existing or append
    replaced = False
    for i, row in enumerate(rows):
        if row.get("method", "").lower() == "simfea-core":
            rows[i] = core_row
            replaced = True
            break
    if not replaced:
        rows.append(core_row)

    # Write back
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

    csv_path.write_text(output.getvalue(), encoding="utf-8")
    print(f"  OK: {csv_path.name} updated ({len(rows)} rows)")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Bridge SimFEA Studio benchmark cases to SimFEA-Lab Core.")
    parser.add_argument("cases", nargs="*", help="Benchmark case directory names.")
    parser.add_argument("--all", action="store_true", help="Run every supported benchmark case.")
    parser.add_argument("--core-build", help=f"SimFEA-Lab Core build directory. Overrides {CORE_BUILD_ENV}.")
    args = parser.parse_args()

    core_build = resolve_core_build(args.core_build)
    if core_build is None:
        print(f"Core build directory is not configured. Use --core-build or set {CORE_BUILD_ENV}.")
        return 1

    bridge_exe = core_build / "bridge_runner.exe"
    if not bridge_exe.exists():
        print(f"bridge_runner.exe not found at {bridge_exe}")
        print(f"Build Core first: cd {core_build.parent} && cmake --build . --target bridge_runner")
        return 1

    targets = args.cases
    if args.all or not targets:
        targets = sorted(d.name for d in BENCH_DIR.iterdir() if d.is_dir())

    ok = 0
    for name in targets:
        case_dir = BENCH_DIR / name
        if not case_dir.is_dir():
            print(f"  !! not found: {name}")
            continue
        print(f"\n{name}")
        result = run_core(case_dir, core_build, bridge_exe)
        if result is None:
            continue
        if update_csv(case_dir, result):
            ok += 1

    print(f"\nDone — {ok}/{len(targets)} cases updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

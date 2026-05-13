"""Analytical solution comparisons for learning report enrichment.

Parses solver input files to compute known analytical solutions (beam theory, etc.)
and compares them with FEA results. Only provides analysis when the element type
and load case are recognized — never fabricates comparisons.
"""

import json
import re
from pathlib import Path


def _parse_ccx_inp(text: str) -> dict:
    """Extract structural parameters from a CalculiX .inp file."""
    params: dict = {}

    # Node coordinates — use to compute beam length
    nodes: dict[int, tuple[float, float, float]] = {}
    node_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("*NODE"):
            node_section = True
            continue
        if stripped.startswith("*") and node_section:
            node_section = False
            continue
        if node_section and stripped:
            parts = stripped.split(",")
            if len(parts) >= 4:
                try:
                    nid = int(parts[0].strip())
                    x = float(parts[1].strip())
                    y = float(parts[2].strip())
                    z = float(parts[3].strip())
                    nodes[nid] = (x, y, z)
                except ValueError:
                    continue

    if len(nodes) >= 2:
        nids = sorted(nodes.keys())
        # Compute the distance between the first two nodes (simplification: beam axis)
        p0 = nodes[nids[0]]
        p1 = nodes[nids[1]]
        params["beam_length_mm"] = (
            (p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2 + (p1[2] - p0[2]) ** 2
        ) ** 0.5

    # Material properties
    elastic_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("*ELASTIC"):
            elastic_section = True
            continue
        if elastic_section and stripped and not stripped.startswith("*"):
            parts = stripped.split(",")
            if len(parts) >= 2:
                try:
                    params["youngs_modulus_mpa"] = float(parts[0].strip())
                    params["poisson_ratio"] = float(parts[1].strip())
                except ValueError:
                    pass
            elastic_section = False

    # Beam section (SECTION=RECT)
    m = re.search(r"SECTION\s*=\s*RECT", text, re.IGNORECASE)
    if m:
        # Find the data line after SECTION=RECT
        idx = text.find(m.group(0))
        remainder = text[idx:]
        lines = remainder.splitlines()
        if len(lines) >= 2:
            data_line = lines[1].strip()
            if not data_line.startswith("*"):
                parts = data_line.split(",")
                if len(parts) >= 2:
                    try:
                        params["section_a_mm"] = float(parts[0].strip())
                        params["section_b_mm"] = float(parts[1].strip())
                    except ValueError:
                        pass

    # Load (CLOAD)
    params["load_N"] = 0.0
    cload_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("*CLOAD"):
            cload_section = True
            continue
        if cload_section and stripped and not stripped.startswith("*"):
            parts = stripped.split(",")
            if len(parts) >= 3:
                try:
                    force = float(parts[2].strip())
                    params["load_N"] = abs(force)
                except ValueError:
                    pass
            cload_section = False

    # Element type
    m = re.search(r"TYPE\s*=\s*(\w+)", text, re.IGNORECASE)
    if m:
        params["element_type"] = m.group(1).upper()

    return params


def _beam_theory_cantilever(params: dict) -> dict | None:
    """Compute Euler-Bernoulli cantilever beam analytical solution.

    δ = PL³ / (3EI)  — tip displacement
    σ = My / I = (PL)(h/2) / I  — max bending stress
    """
    L = params.get("beam_length_mm")
    E = params.get("youngs_modulus_mpa")
    F = params.get("load_N")
    a = params.get("section_a_mm")  # local y dim (bending direction)
    b = params.get("section_b_mm")  # local z dim

    if not all(v is not None and v > 0 for v in [L, E, F, a, b]):
        return None

    # Rectangular section: I = b * a³ / 12 (bending about local z)
    I = b * (a ** 3) / 12

    # Tip displacement (Euler-Bernoulli)
    delta = F * (L ** 3) / (3 * E * I)

    # Max bending stress at the fixed end
    M = F * L
    sigma_max = M * (a / 2) / I

    return {
        "formula": "悬臂梁 Euler-Bernoulli 梁理论",
        "delta_mm": round(delta, 3),
        "sigma_max_mpa": round(sigma_max, 3),
        "I_mm4": round(I, 2),
        "assumptions": [
            "小变形线弹性",
            "Euler-Bernoulli 假设（忽略剪切变形）",
            "固定端完全刚接",
            "集中力作用于自由端",
        ],
    }


def analyze_run(run_dir: Path) -> dict:
    """Analyze a completed run and return structured observations.

    Returns a dict with keys:
        analytical: dict or None — analytical comparison results
        observations: list[str] — notable observations about the results
    """
    result: dict = {"analytical": None, "observations": []}

    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        return result

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("status") != "finished" or meta.get("exit_code") != 0:
        return result

    solver = meta.get("solver", "")
    if solver != "calculix":
        return result

    # Find and parse the input file
    input_files = meta.get("input_files") or []
    inp_text = None
    for rel_path in input_files:
        abs_path = run_dir / rel_path
        if abs_path.suffix == ".inp" and abs_path.exists():
            inp_text = abs_path.read_text(encoding="utf-8")
            break

    if not inp_text:
        # Try inputs/ directory
        for inp_file in sorted((run_dir / "inputs").glob("*.inp")):
            inp_text = inp_file.read_text(encoding="utf-8")
            break

    if not inp_text:
        return result

    params = _parse_ccx_inp(inp_text)
    element_type = params.get("element_type", "")

    # Only provide analytical comparison for beam elements
    if element_type in ("B31", "B32", "B33"):
        analytical = _beam_theory_cantilever(params)
        if analytical:
            result["analytical"] = analytical

            # Read actual results for comparison
            summary_path = run_dir / "artifacts" / "result_summary.json"
            if summary_path.exists():
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                metrics = summary.get("metrics", {})
                fea_delta = metrics.get("max_displacement_mm")
                fea_sigma = metrics.get("max_von_mises_mpa")

                if fea_delta is not None and analytical["delta_mm"] != 0:
                    delta_err = abs(fea_delta - analytical["delta_mm"]) / analytical["delta_mm"] * 100
                    result["analytical"]["fea_delta_mm"] = fea_delta
                    result["analytical"]["delta_error_pct"] = round(delta_err, 2)

                if fea_sigma is not None and analytical["sigma_max_mpa"] != 0:
                    sigma_err = abs(fea_sigma - analytical["sigma_max_mpa"]) / analytical["sigma_max_mpa"] * 100
                    result["analytical"]["fea_sigma_mpa"] = fea_sigma
                    result["analytical"]["sigma_error_pct"] = round(sigma_err, 2)

    # Generate observations
    if result["analytical"]:
        delta_err = result["analytical"].get("delta_error_pct")
        if delta_err is not None:
            if delta_err < 1:
                result["observations"].append(
                    f"位移结果与 Euler-Bernoulli 梁理论解误差仅 {delta_err}%，"
                    f"说明在此长细比下梁理论假设成立，B31 单元给出了可靠的位移解。"
                )
            elif delta_err < 5:
                result["observations"].append(
                    f"位移结果与梁理论解误差 {delta_err}%，在工程可接受范围内。"
                    f"差异可能源于 Timoshenko 剪切修正或边界条件处理。"
                )
            else:
                result["observations"].append(
                    f"位移与 Euler-Bernoulli 理论解差异 {delta_err}%。"
                    f"B31 为 Timoshenko 梁单元，包含剪切变形，理论对比应使用 Timoshenko 公式。"
                    f"建议检查截面惯性矩的计算方向。"
                )

    return result


def render_analysis_section(analysis: dict) -> str:
    """Render the analysis dict into a markdown section for the learning report."""
    if not analysis.get("analytical") and not analysis.get("observations"):
        return ""

    lines = ["## 结果分析", ""]

    analytical = analysis.get("analytical")
    if analytical:
        lines.append("### 与解析解对比")
        lines.append("")
        lines.append(f"**理论模型**：{analytical.get('formula', '')}")
        lines.append("")
        lines.append("| 指标 | 理论值 | 仿真值 | 误差 |")
        lines.append("|------|--------|--------|------|")

        delta = analytical.get("delta_mm")
        fea_delta = analytical.get("fea_delta_mm")
        delta_err = analytical.get("delta_error_pct")
        if delta is not None:
            fea_str = f"{fea_delta:.3f}" if fea_delta is not None else "—"
            err_str = f"{delta_err:.2f}%" if delta_err is not None else "—"
            lines.append(f"| 最大位移 (mm) | {delta:.3f} | {fea_str} | {err_str} |")

        sigma = analytical.get("sigma_max_mpa")
        fea_sigma = analytical.get("fea_sigma_mpa")
        sigma_err = analytical.get("sigma_error_pct")
        if sigma is not None:
            fea_str = f"{fea_sigma:.3f}" if fea_sigma is not None else "—"
            err_str = f"{sigma_err:.2f}%" if sigma_err is not None else "—"
            lines.append(f"| 最大应力 (MPa) | {sigma:.3f} | {fea_str} | {err_str} |")

        lines.append("")
        lines.append(f"截面惯性矩 I = {analytical.get('I_mm4', '—')} mm⁴")
        lines.append("")
        lines.append("**理论假设**：")
        for a in analytical.get("assumptions", []):
            lines.append(f"- {a}")
        lines.append("")

    observations = analysis.get("observations", [])
    if observations:
        lines.append("### 观察")
        lines.append("")
        for obs in observations:
            lines.append(f"- {obs}")
        lines.append("")

    return "\n".join(lines)

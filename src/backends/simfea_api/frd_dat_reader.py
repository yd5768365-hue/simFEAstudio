"""CalculiX .dat file parser — integration-point results.

Reads element variable output (*EL PRINT) from CalculiX .dat files.
Computes min, max, and arithmetic mean for Mises equivalent stress,
total effective strain, and equivalent plastic strain at integration points.

Integration-point data is generally more accurate than nodal-extrapolated
data, particularly in non-linear stress analyses.

Based on CCXStressReader (Henning Richter, LGPL v2.1).
"""

from __future__ import annotations

from pathlib import Path

# Header signatures in .dat EL PRINT output
_STRESS_HEADER = "stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz)"
_STRAIN_HEADER = "strains (elem, integ.pnt.,exx,eyy,ezz,exy,exz,eyz)"
_PEEQ_HEADER = "equivalent plastic strain"


def parse_dat(dat_path: Path) -> dict:
    """Parse EL PRINT output from a CalculiX .dat file.

    Returns:
        dict with keys:
          - "stresses": list of [elem_id, ip, sxx, syy, szz, sxy, sxz, syz]
          - "strains":  list of [elem_id, ip, exx, eyy, ezz, exy, exz, eyz]
          - "peeq":     list of [elem_id, ip, peeq]
        Missing data types are empty lists.
    """
    text = dat_path.read_text(encoding="utf-8", errors="replace")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # Locate section boundaries
    stress_idx = _find_header(lines, _STRESS_HEADER)
    strain_idx = _find_header(lines, _STRAIN_HEADER)
    peeq_idx = _find_header(lines, _PEEQ_HEADER)

    # Markers for where each section ends (position of next header or EOF)
    markers = sorted(
        i for i in (stress_idx, strain_idx, peeq_idx) if i >= 0
    )

    result: dict = {"stresses": [], "strains": [], "peeq": []}

    if stress_idx >= 0:
        end = _next_marker(stress_idx, markers) if markers else len(lines)
        result["stresses"] = _read_el_print_block(lines, stress_idx + 1, end, 8)

    if strain_idx >= 0:
        end = _next_marker(strain_idx, markers) if markers else len(lines)
        result["strains"] = _read_el_print_block(lines, strain_idx + 1, end, 8)

    if peeq_idx >= 0:
        end = _next_marker(peeq_idx, markers) if markers else len(lines)
        result["peeq"] = _read_el_print_block(lines, peeq_idx + 1, end, 3)

    return result


def _find_header(lines: list[str], header: str) -> int:
    """Return index of header line, or -1 if not found."""
    for i, line in enumerate(lines):
        if header in line:
            return i
    return -1


def _next_marker(current: int, markers: list[int]) -> int:
    """Return the next marker greater than current, or None sentinel."""
    for m in markers:
        if m > current:
            return m
    return 10**9  # sentinel for "end of file"


def _read_el_print_block(
    lines: list[str], start: int, end: int, expected_cols: int,
) -> list[list[float]]:
    """Read numeric rows from EL PRINT block.

    Each row: elem_id, ip, val1, val2, ...
    Only rows whose first token is numeric are kept.
    """
    rows: list[list[float]] = []
    for i in range(start, min(end, len(lines))):
        line = lines[i]
        # Skip sub-headers and non-data lines
        if not line or not line[0].isdigit():
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            row = [float(v) for v in parts]
            if len(row) >= expected_cols:
                rows.append(row[:expected_cols])
            else:
                rows.append(row)
        except ValueError:
            continue
    return rows


def dat_summary(dat_path: Path) -> dict:
    """Compute min / max / arithmetic-mean for integration-point quantities.

    Returns dict with keys like:
      "mises_stress_min", "mises_stress_max", "mises_stress_mean",
      "equiv_strain_min", "equiv_strain_max", "equiv_strain_mean",
      "peeq_min", "peeq_max", "peeq_mean"
    Only present when the corresponding data exists in the .dat file.
    """
    import math

    data = parse_dat(dat_path)
    summary: dict = {}

    if data["stresses"]:
        mises_vals = [_mises_from_row(r) for r in data["stresses"]]
        summary["mises_stress_min"] = min(mises_vals)
        summary["mises_stress_max"] = max(mises_vals)
        summary["mises_stress_mean"] = sum(mises_vals) / len(mises_vals)

    if data["strains"]:
        eeq_vals = [_eeq_from_row(r) for r in data["strains"]]
        summary["equiv_strain_min"] = min(eeq_vals)
        summary["equiv_strain_max"] = max(eeq_vals)
        summary["equiv_strain_mean"] = sum(eeq_vals) / len(eeq_vals)

    if data["peeq"]:
        peeq_vals = [r[2] for r in data["peeq"] if len(r) >= 3]
        if peeq_vals:
            summary["peeq_min"] = min(peeq_vals)
            summary["peeq_max"] = max(peeq_vals)
            summary["peeq_mean"] = sum(peeq_vals) / len(peeq_vals)

    return summary


def _mises_from_row(row: list[float]) -> float:
    """Von Mises stress from [elem, ip, sxx, syy, szz, sxy, sxz, syz]."""
    import math
    _, _, sxx, syy, szz, sxy, sxz, syz = row
    return math.sqrt(
        0.5 * (
            (sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2
            + 6 * (sxy ** 2 + syz ** 2 + sxz ** 2)
        )
    )


def _eeq_from_row(row: list[float]) -> float:
    """Equivalent total strain from [elem, ip, exx, eyy, ezz, exy, exz, eyz]."""
    import math
    _, _, exx, eyy, ezz, exy, exz, eyz = row
    return (2.0 / 3.0) * math.sqrt(
        0.5 * (
            (exx - eyy) ** 2 + (eyy - ezz) ** 2 + (ezz - exx) ** 2
            + 6 * (exy ** 2 + eyz ** 2 + exz ** 2)
        )
    )


def write_dat_summary(dat_path: Path, output_path: Path) -> dict:
    """Parse a .dat file and write min/max/mean summary to output_path.

    Returns the summary dict from dat_summary().
    """
    summary = dat_summary(dat_path)
    lines: list[str] = [
        f"Integration-point results from: {dat_path.name}",
        "-" * 60,
    ]
    for key in sorted(summary.keys()):
        lines.append(f"  {key} = {summary[key]:.6e}")
    lines.append("")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return summary

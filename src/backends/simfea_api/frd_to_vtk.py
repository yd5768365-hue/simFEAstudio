"""Minimal CalculiX .frd to VTK ASCII converter.

Parses FRD sections for nodes (2C), elements (3C), displacements (2D),
and stresses (2S). Outputs an unstructured grid VTK file with displacement
vectors and von Mises stress scalars.

Reference: OpenCAEHub artifact pipeline pattern — structured output
collection from solver-native formats into visualization-ready files.
"""

import math
import re
from pathlib import Path

# FRD uses E12.5 fixed-width real fields that can run together when negative.
# This regex matches each number token including concatenated ones.
_FRD_TOKEN = re.compile(r"[+-]?\d+\.?\d*(?:[EeDd][+-]?\d+)?")


def _parse_frd_line(line: str) -> list[float]:
    """Parse an FRD data line, handling concatenated fixed-width fields."""
    values = []
    for token in _FRD_TOKEN.findall(line):
        token = token.replace("D", "E").replace("d", "E")
        try:
            values.append(float(token))
        except ValueError:
            pass
    return values


def _parse_frd_sections(text: str) -> dict[str, list[list[float]]]:
    """Parse FRD text into sections. Returns {section_key: [rows of float values]}.

    Real CalculiX FRD structure (observed from v2.10 output):

      - 2C / 3C sections for geometry (coordinates, elements), terminated by -3.
      - 1PSTEP sections for result data: each step contains:
          * 100CL class header (skip)
          * -4 DISP / -4 STRESS data descriptor
          * -5 component descriptor lines (skip)
          * -1 data rows  → extracted as "2D" (displacements) or "2S" (stresses)
          * -3 terminates the step
    """
    sections: dict[str, list[list[float]]] = {}
    current_key: str | None = None
    data_section_codes = {"2C", "3C"}

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == "-3":
            current_key = None
            continue
        if stripped == "9999":
            continue
        code = stripped[:2]
        if code in data_section_codes:
            current_key = code
            if current_key not in sections:
                sections[current_key] = []
            continue
        # 1PSTEP: step result section — reset state, data type set by -4 descriptor
        if code == "1P":
            current_key = None
            continue
        # 100CL: class header inside a 1PSTEP, no data to extract
        if code == "10":
            continue
        # -4: data descriptor — "DISP" → displacements, "STRESS" → stresses
        if code == "-4":
            upper = stripped.upper()
            if "DISP" in upper:
                current_key = "2D"
                if current_key not in sections:
                    sections[current_key] = []
            elif "STR" in upper:
                current_key = "2S"
                if current_key not in sections:
                    sections[current_key] = []
            continue
        # -5: component descriptor (D1/D2/D3 or SXX/SYY/...), skip
        if code == "-5":
            continue
        # Metadata headers: 1C (file header), 1U (user/date/program info)
        if code in ("1C", "1U"):
            current_key = None
            continue
        if not current_key:
            continue
        values = _parse_frd_line(line)
        if values:
            sections[current_key].append(values)

    return sections


def _parse_nodes(coord_rows: list[list[float]]) -> dict[int, tuple[float, float, float]]:
    """Parse 2C section: each row is [format, node_id, x, y, z]."""
    nodes: dict[int, tuple[float, float, float]] = {}
    for row in coord_rows:
        if len(row) >= 5:
            nid = int(row[1])
            nodes[nid] = (row[2], row[3], row[4])
    return nodes


def _parse_elements(elem_rows: list[list[float]]) -> list[list[int]]:
    """Parse 3C section from real CalculiX FRD.

    Format -1 (1D/2D elements): [format, elem_id, n1, n2, ...]
    Format -2 (3D elements):    [format, n1, n2, ..., n8]  (no elem_id, 8 hex nodes)

    We skip -1 rows (1D beam expansion info) and use -2 rows for 3D hex elements.
    """
    elements: list[list[int]] = []
    for row in elem_rows:
        if len(row) < 3:
            continue
        fmt = int(row[0])
        if fmt == -1:
            continue  # 1D/2D beam expansion — not useful for 3D visualization
        if fmt == -2:
            # Format: [-2, n1, n2, ..., n8]
            elements.append([int(n) for n in row[1:]])
    return elements


def _parse_nodal_data(
    rows: list[list[float]], components: int
) -> dict[int, list[float]]:
    """Parse 2D or 2S section: each row is [format, node_id, v1, v2, ...]."""
    data: dict[int, list[float]] = {}
    for row in rows:
        if len(row) >= 2 + components:
            nid = int(row[1])
            data[nid] = row[2 : 2 + components]
    return data


def _von_mises(sx: float, sy: float, sz: float,
              sxy: float = 0, syz: float = 0, szx: float = 0) -> float:
    """Compute von Mises stress from stress components."""
    return math.sqrt(
        0.5 * (
            (sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2
            + 6 * (sxy ** 2 + syz ** 2 + szx ** 2)
        )
    )


def frd_to_vtk(frd_path: Path, vtk_path: Path) -> dict:
    """Convert CalculiX .frd file to ASCII VTK unstructured grid.

    Returns metrics dict: {max_displacement_mm, max_von_mises_mpa}.
    """
    text = frd_path.read_text(encoding="utf-8", errors="replace")
    sections = _parse_frd_sections(text)

    nodes = _parse_nodes(sections.get("2C", []))
    if not nodes:
        raise ValueError(f"No nodes found in FRD: {frd_path}")

    elements = _parse_elements(sections.get("3C", []))
    displacements = _parse_nodal_data(sections.get("2D", []), 3)
    stresses = _parse_nodal_data(sections.get("2S", []), 6)

    node_ids = sorted(nodes.keys())
    id_to_index = {nid: idx for idx, nid in enumerate(node_ids)}

    # Compute per-node displacement magnitude and von Mises stress
    max_disp = 0.0
    max_vm = 0.0
    disp_mags: list[float] = []
    vm_stresses: list[float] = []

    for nid in node_ids:
        disp = displacements.get(nid, [0.0, 0.0, 0.0])
        mag = math.sqrt(disp[0] ** 2 + disp[1] ** 2 + disp[2] ** 2)
        disp_mags.append(mag)
        if mag > max_disp:
            max_disp = mag

        stress = stresses.get(nid, [0.0] * 6)
        vm = _von_mises(*stress[:6]) if len(stress) >= 6 else 0.0
        vm_stresses.append(vm)
        if vm > max_vm:
            max_vm = vm

    # Map elements to 0-indexed node indices
    cell_connectivity: list[list[int]] = []
    cell_types: list[int] = []
    for elem in elements:
        indices = [id_to_index[n] for n in elem if n in id_to_index]
        if len(indices) == 2:
            cell_connectivity.append(indices)
            cell_types.append(3)  # VTK_LINE
        elif len(indices) == 3:
            cell_connectivity.append(indices)
            cell_types.append(5)  # VTK_TRIANGLE
        elif len(indices) == 4:
            cell_connectivity.append(indices)
            cell_types.append(9)  # VTK_QUAD
        elif len(indices) == 8:
            cell_connectivity.append(indices)
            cell_types.append(12)  # VTK_HEXAHEDRON
        elif len(indices) >= 4:
            cell_connectivity.append(indices)
            cell_types.append(7)  # VTK_POLYGON

    if not cell_connectivity:
        raise ValueError(f"No valid elements found in FRD: {frd_path}")

    # Write ASCII VTK
    lines = [
        "# vtk DataFile Version 3.0",
        f"SimFEA Studio CalculiX result: {frd_path.name}",
        "ASCII",
        "DATASET UNSTRUCTURED_GRID",
        f"POINTS {len(node_ids)} float",
    ]
    for nid in node_ids:
        x, y, z = nodes[nid]
        lines.append(f"  {x:.6f} {y:.6f} {z:.6f}")

    total_cell_size = sum(len(c) + 1 for c in cell_connectivity)
    lines.append(f"CELLS {len(cell_connectivity)} {total_cell_size}")
    for conn in cell_connectivity:
        lines.append(f"  {len(conn)} " + " ".join(str(i) for i in conn))

    lines.append(f"CELL_TYPES {len(cell_connectivity)}")
    for ct in cell_types:
        lines.append(f"  {ct}")

    lines.append(f"POINT_DATA {len(node_ids)}")
    lines.append("SCALARS von_mises_mpa float 1")
    lines.append("LOOKUP_TABLE default")
    for vm in vm_stresses:
        lines.append(f"  {vm:.6f}")

    lines.append("VECTORS displacement_mm float")
    for nid in node_ids:
        d = displacements.get(nid, [0.0, 0.0, 0.0])
        lines.append(f"  {d[0]:.6f} {d[1]:.6f} {d[2]:.6f}")

    vtk_path.parent.mkdir(parents=True, exist_ok=True)
    vtk_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"max_displacement_mm": max_disp, "max_von_mises_mpa": max_vm}

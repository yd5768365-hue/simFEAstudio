"""CalculiX .frd to VTK/VTU converter with multi-step support.

Parses FRD sections for nodes (2C), elements (3C), and result steps (1PSTEP).
Outputs legacy VTK ASCII, modern VTU XML, and PVD collection files with
von Mises stress/strain, principal stress/strain, and displacement vectors.

Inspired by ccx2paraview (Ihor Mirzov, GPL v3).
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# FRD uses E12.5 fixed-width real fields that can run together when negative.
_FRD_TOKEN = re.compile(r"[+-]?\d+\.?\d*(?:[EeDd][+-]?\d+)?")

# ── FRD element type → VTK cell type ──────────────────────────
# Based on ccx2paraview convert_elem_type and CGX manual §10.
_FRD_TO_VTK_ELEM: dict[int, int] = {
    1: 12,   # C3D8/F3D8/C3D8R/C3D8I  → VTK_HEXAHEDRON
    2: 13,   # C3D6/F3D6                → VTK_WEDGE
    3: 10,   # C3D4/F3D4                → VTK_TETRA
    4: 25,   # C3D20/C3D20R             → VTK_QUADRATIC_HEXAHEDRON
    5: 13,   # C3D15                    → VTK_WEDGE (mid-nodes dropped)
    6: 24,   # C3D10/C3D10T             → VTK_QUADRATIC_TETRA
    7: 5,    # S3/M3D3/CPS3/CPE3/CAX3   → VTK_TRIANGLE
    8: 22,   # S6/M3D6/CPS6/CPE6/CAX6   → VTK_QUADRATIC_TRIANGLE
    9: 9,    # S4/S4R/M3D4/CPS4/CPE4...  → VTK_QUAD
    10: 23,  # S8/S8R/M3D8/CPS8/CPE8...  → VTK_QUADRATIC_QUAD
    11: 3,   # B21/B31/T2D2/T3D2/...     → VTK_LINE
    12: 21,  # B32/B32R/T3D3             → VTK_QUADRATIC_EDGE
}


def _guess_vtk_type(node_count: int) -> int:
    """Fallback: guess VTK cell type from node count."""
    return {2: 3, 3: 5, 4: 9, 6: 13, 8: 12, 10: 24, 15: 13, 20: 25}.get(node_count, 7)


# ── FRD line parsing ──────────────────────────────────────────


def _parse_frd_line(line: str) -> list[float]:
    """Parse an FRD data line, handling concatenated fixed-width fields."""
    values: list[float] = []
    for token in _FRD_TOKEN.findall(line):
        token = token.replace("D", "E").replace("d", "E")
        try:
            values.append(float(token))
        except ValueError:
            pass
    return values


# ── Math ──────────────────────────────────────────────────────


def _von_mises(sx: float, sy: float, sz: float,
              sxy: float = 0, syz: float = 0, szx: float = 0) -> float:
    """Compute von Mises equivalent value from 6 tensor components."""
    return math.sqrt(
        0.5 * (
            (sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2
            + 6 * (sxy ** 2 + syz ** 2 + szx ** 2)
        )
    )


def _principal(sxx: float, syy: float, szz: float,
               sxy: float = 0, syz: float = 0, sxz: float = 0
               ) -> tuple[float, float, float, float]:
    """Compute principal values (eigenvalues) of a symmetric 3×3 tensor.

    Returns (min, mid, max, worst) where 'worst' has the largest |value|.
    Uses the trigonometric method for 3×3 symmetric matrices.
    """
    if sxx == syy == szz == sxy == syz == sxz == 0:
        return (0.0, 0.0, 0.0, 0.0)

    # Invariants from the characteristic polynomial det(σ - λI) = 0
    # → λ³ + p1·λ² + p2·λ + p3 = 0
    p1 = -(sxx + syy + szz)
    p2 = (sxx * syy + syy * szz + szz * sxx
          - sxy * sxy - syz * syz - sxz * sxz)
    p3 = -(sxx * syy * szz + 2 * sxy * syz * sxz
           - sxx * syz * syz - syy * sxz * sxz - szz * sxy * sxy)

    q = max((p1 * p1 - 3 * p2) / 9, 0.0)
    r = (2 * p1 * p1 * p1 - 9 * p1 * p2 + 27 * p3) / 54

    if q < 1e-15:
        # Degenerate case: all eigenvalues equal
        lam = -p1 / 3
        return (lam, lam, lam, lam)

    r_over_q3 = max(-1.0, min(1.0, r / math.sqrt(q * q * q)))
    theta = math.acos(r_over_q3)
    sqrt_q = math.sqrt(q)

    e1 = -2 * sqrt_q * math.cos(theta / 3) - p1 / 3
    e2 = -2 * sqrt_q * math.cos((theta + 2 * math.pi) / 3) - p1 / 3
    e3 = -2 * sqrt_q * math.cos((theta + 4 * math.pi) / 3) - p1 / 3

    eigenvalues = sorted([e1, e2, e3])
    worst = eigenvalues[0] if abs(eigenvalues[0]) > abs(eigenvalues[2]) else eigenvalues[2]
    return (eigenvalues[0], eigenvalues[1], eigenvalues[2], worst)


# ── Data structures ───────────────────────────────────────────


@dataclass
class FrdMesh:
    """Parsed mesh geometry from 2C and 3C sections."""
    nodes: dict[int, tuple[float, float, float]] = field(default_factory=dict)
    elements: list[tuple[int, list[int]]] = field(default_factory=list)
    # elements: [(frd_elem_type, [node_ids])]


@dataclass
class FrdStep:
    """Result data for one step/increment."""
    step: int = 0
    inc: float = 0.0
    displacements: dict[int, list[float]] = field(default_factory=dict)
    stresses: dict[int, list[float]] = field(default_factory=dict)
    strains: dict[int, list[float]] = field(default_factory=dict)

    def has_data(self) -> bool:
        return bool(self.displacements or self.stresses or self.strains)


# ── FRD file parser ───────────────────────────────────────────


def _parse_line_range(lines: list[str], start: int, end: int) -> list[str]:
    """Slice lines safely."""
    return [l.strip() for l in lines[start:end] if l.strip()]


def _parse_frd_file(frd_path: Path) -> tuple[FrdMesh, list[FrdStep]]:
    """Parse a CalculiX .frd file into mesh geometry and result steps.

    Key sections:
      2C — nodal coordinates (terminated by -3)
      3C — element definitions (terminated by -3)
      1PSTEP — step results container
        100CL — class/step header (step number, time/frequency)
        -4 DISP  / -4 STRESS  / -4 TOSTRAIN  — data descriptors
        -5 D1..  / -5 SXX..   / -5 EXX..      — component descriptors (skipped)
        -1 ...   — actual data values
        -3       — ends the current -4 block
      Next 1PSTEP or 9999
    """
    text = frd_path.read_text(encoding="utf-8", errors="replace")
    lines = [l.strip() for l in text.splitlines()]
    n = len(lines)

    mesh = FrdMesh()
    steps: list[FrdStep] = []

    # ── Pass 1: extract 2C (nodes) and 3C (elements) ──
    i = 0
    while i < n:
        line = lines[i]
        if not line:
            i += 1
            continue

        # Nodes
        if line.startswith("2C"):
            _parse_node_section(lines, i + 1, mesh)
            i = _skip_to(lines, i + 1, "-3") + 1
            continue

        # Elements
        if line.startswith("3C"):
            _parse_element_section(lines, i + 1, mesh)
            i = _skip_to(lines, i + 1, "-3") + 1
            continue

        # Steps start here — switch to pass 2
        if line.startswith("1PSTEP"):
            break

        i += 1

    # ── Pass 2: extract result steps ──
    # Find all 1PSTEP boundaries
    step_starts: list[int] = []
    for idx in range(i, n):
        if lines[idx].startswith("1PSTEP"):
            step_starts.append(idx)

    for si, start in enumerate(step_starts):
        end = step_starts[si + 1] if si + 1 < len(step_starts) else n
        step = _parse_one_step(lines, start, end)
        if step and step.has_data():
            steps.append(step)

    return mesh, steps


def _skip_to(lines: list[str], start: int, target: str) -> int:
    """Return index of first line at or after `start` that exactly equals `target`."""
    for i in range(start, len(lines)):
        if lines[i] == target:
            return i
    return len(lines) - 1


def _parse_node_section(lines: list[str], start: int, mesh: FrdMesh) -> None:
    """Parse 2C nodal coordinate section."""
    i = start
    while i < len(lines):
        line = lines[i]
        if line == "-3":
            break
        if line.startswith("-1"):
            vals = _parse_frd_line(line)
            if len(vals) >= 5:
                mesh.nodes[int(vals[1])] = (vals[2], vals[3], vals[4])
        i += 1


def _parse_element_section(lines: list[str], start: int, mesh: FrdMesh) -> None:
    """Parse 3C element definition section.

    Element definition format (two lines per element):
      -1  <elem_id>  <type>  0  <set_id>
      -2  <n1>  <n2>  <n3>  <n4>  ...
    The -1 line carries the element type; the -2 line carries node ids.
    """
    i = start
    current_type = 0
    while i < len(lines):
        line = lines[i]
        if line == "-3":
            break
        if line.startswith("-1"):
            vals = _parse_frd_line(line)
            if len(vals) >= 3:
                current_type = int(vals[2])
        elif line.startswith("-2"):
            vals = _parse_frd_line(line)
            if len(vals) >= 2 and current_type:
                node_ids = [int(v) for v in vals[1:]]
                mesh.elements.append((current_type, node_ids))
        i += 1


def _parse_one_step(lines: list[str], start: int, end: int) -> FrdStep | None:
    """Parse one 1PSTEP section into a FrdStep."""
    step = FrdStep()
    i = start + 1  # skip "1PSTEP" line itself

    while i < end:
        line = lines[i]
        if not line:
            i += 1
            continue

        # Step header — extract step number and time/frequency.
        # Format: "100CL  101 <12-char-inc> <int> <int> <step> ..."
        # Per ccx2paraview: skip 12 chars (class + id), then inc(12), two ints, step.
        if line.startswith("100CL") or line.startswith(" 100"):
            if len(line) > 12:
                tail = line[12:]
                match = re.match(r"^(.{12})\s+\d+\s+\d+\s+(\d+)", tail)
                if match:
                    try:
                        step.inc = float(match.group(1))
                    except ValueError:
                        pass
                    try:
                        step.step = int(match.group(2))
                    except ValueError:
                        pass
            i += 1
            continue

        # Data block descriptor
        if line.startswith("-4"):
            upper = line.upper()
            if "DISP" in upper:
                _parse_data_block(lines, i, step.displacements, 3)
            elif "STR" in upper:
                _parse_data_block(lines, i, step.stresses, 6)
            elif "TOSTRAIN" in upper or "STRAIN" in upper:
                _parse_data_block(lines, i, step.strains, 6)
            # Skip to end of this data block
            i = _skip_to(lines, i + 1, "-3") + 1
            continue

        # Component descriptors — consumed inside _parse_data_block
        # Metadata lines to skip
        if line.startswith("-5") or line.startswith("1C") or line.startswith("1U"):
            i += 1
            continue

        i += 1

    return step


def _parse_data_block(
    lines: list[str], desc_line_idx: int,
    target: dict[int, list[float]], ncomps: int,
) -> None:
    """Parse a -4 data block: skip -5 descriptors, then read -1 data rows.

    Lines are read starting from desc_line_idx + 1 (after the -4 line)
    until -3 is encountered.
    """
    i = desc_line_idx + 1
    while i < len(lines):
        line = lines[i]
        if line == "-3" or line == "":
            break
        # Skip -5 component descriptor lines
        if line.startswith("-5"):
            i += 1
            continue
        # Data row
        if line.startswith("-1"):
            vals = _parse_frd_line(line)
            if len(vals) >= 2:
                nid = int(vals[1])
                data = list(vals[2:2 + ncomps])
                # Pad with zeros if short
                while len(data) < ncomps:
                    data.append(0.0)
                target[nid] = data
            i += 1
            continue
        # Multi-line continuation (-2 prefix for >6 components)
        if line.startswith("-2"):
            # Continuation lines add to the previous node's data
            vals = _parse_frd_line(line)
            if vals:
                # Find the last node we added data for
                last_nid = max(target.keys()) if target else None
                if last_nid is not None:
                    target[last_nid].extend(vals[:ncomps - len(target[last_nid])])
            i += 1
            continue
        i += 1


# ── VTK legacy ASCII writer ───────────────────────────────────


def _write_vtk_ascii(
    frd_path: Path, vtk_path: Path,
    mesh: FrdMesh, step: FrdStep,
    node_ids: list[int], id_to_index: dict[int, int],
) -> dict:
    """Write a single-step legacy VTK ASCII file. Returns metrics dict."""
    max_disp = 0.0
    max_vm = 0.0
    disp_mags: list[float] = []
    vm_stresses: list[float] = []
    principal_stress: list[tuple[float, float, float, float]] = []
    principal_strain: list[tuple[float, float, float, float]] = []
    vm_strains: list[float] = []

    for nid in node_ids:
        # Displacement
        d = step.displacements.get(nid, [0.0, 0.0, 0.0])
        mag = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
        disp_mags.append(mag)
        if mag > max_disp:
            max_disp = mag

        # von Mises stress
        s = step.stresses.get(nid, [0.0] * 6)
        vm = _von_mises(*s[:6]) if len(s) >= 6 else 0.0
        vm_stresses.append(vm)
        if vm > max_vm:
            max_vm = vm

        # Principal stress
        principal_stress.append(_principal(*s[:6]) if len(s) >= 6 else (0.0, 0.0, 0.0, 0.0))

        # von Mises strain
        e = step.strains.get(nid, [0.0] * 6)
        vme = _von_mises(*e[:6]) if len(e) >= 6 else 0.0
        vm_strains.append(vme)

        # Principal strain
        principal_strain.append(_principal(*e[:6]) if len(e) >= 6 else (0.0, 0.0, 0.0, 0.0))

    # Build cell connectivity
    cell_conn: list[list[int]] = []
    cell_types: list[int] = []
    for elem_type, elem_nodes in mesh.elements:
        indices = [id_to_index[n] for n in elem_nodes if n in id_to_index]
        if not indices:
            continue
        vtk_type = _FRD_TO_VTK_ELEM.get(elem_type)
        if vtk_type is None:
            vtk_type = _guess_vtk_type(len(indices))
        cell_conn.append(indices)
        cell_types.append(vtk_type)

    if not cell_conn:
        raise ValueError(f"No valid elements found in FRD: {frd_path}")

    # Write lines
    lines: list[str] = [
        "# vtk DataFile Version 3.0",
        f"SimFEA Studio CalculiX result: {frd_path.name}",
        "ASCII",
        "DATASET UNSTRUCTURED_GRID",
        f"POINTS {len(node_ids)} float",
    ]
    for nid in node_ids:
        x, y, z = mesh.nodes[nid]
        lines.append(f"  {x:.6f} {y:.6f} {z:.6f}")

    total_cell_size = sum(len(c) + 1 for c in cell_conn)
    lines.append(f"CELLS {len(cell_conn)} {total_cell_size}")
    for conn in cell_conn:
        lines.append(f"  {len(conn)} " + " ".join(str(idx) for idx in conn))

    lines.append(f"CELL_TYPES {len(cell_conn)}")
    for ct in cell_types:
        lines.append(f"  {ct}")

    lines.append(f"POINT_DATA {len(node_ids)}")

    has_stress = any(v != 0.0 for v in vm_stresses)
    has_disp = any(m > 0.0 for m in disp_mags)
    has_strain = any(v != 0.0 for v in vm_strains)

    if has_stress:
        lines.append("SCALARS von_mises_mpa float 1")
        lines.append("LOOKUP_TABLE default")
        for vm in vm_stresses:
            lines.append(f"  {vm:.6f}")

        lines.append("SCALARS principal_stress float 4")
        lines.append("LOOKUP_TABLE default")
        for p in principal_stress:
            lines.append(f"  {p[0]:.6f} {p[1]:.6f} {p[2]:.6f} {p[3]:.6f}")

    if has_strain:
        lines.append("SCALARS von_mises_strain float 1")
        lines.append("LOOKUP_TABLE default")
        for vme in vm_strains:
            lines.append(f"  {vme:.6e}")

        lines.append("SCALARS principal_strain float 4")
        lines.append("LOOKUP_TABLE default")
        for p in principal_strain:
            lines.append(f"  {p[0]:.6e} {p[1]:.6e} {p[2]:.6e} {p[3]:.6e}")

    if has_disp:
        lines.append("VECTORS displacement_mm float")
        for nid in node_ids:
            d = step.displacements.get(nid, [0.0, 0.0, 0.0])
            lines.append(f"  {d[0]:.6f} {d[1]:.6f} {d[2]:.6f}")

    vtk_path.parent.mkdir(parents=True, exist_ok=True)
    vtk_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"max_displacement_mm": max_disp, "max_von_mises_mpa": max_vm}


# ── VTU XML writer ────────────────────────────────────────────


def _write_vtu_xml(
    file_path: Path, mesh: FrdMesh, step: FrdStep,
    node_ids: list[int], id_to_index: dict[int, int],
) -> None:
    """Write a single-step VTU XML (inline ASCII) file."""
    n_points = len(node_ids)
    n_cells = len(mesh.elements)

    vtkfile = ET.Element("VTKFile", {
        "type": "UnstructuredGrid",
        "version": "0.1",
        "byte_order": "LittleEndian",
    })
    ugrid = ET.SubElement(vtkfile, "UnstructuredGrid")
    piece = ET.SubElement(ugrid, "Piece", {
        "NumberOfPoints": str(n_points),
        "NumberOfCells": str(n_cells),
    })

    # ── Points ──
    points_elem = ET.SubElement(piece, "Points")
    pdata = ET.SubElement(points_elem, "DataArray", {
        "type": "Float32", "NumberOfComponents": "3", "format": "ascii",
    })
    pdata.text = "\n".join(
        f"{mesh.nodes[nid][0]:.6f} {mesh.nodes[nid][1]:.6f} {mesh.nodes[nid][2]:.6f}"
        for nid in node_ids
    )

    # ── Cells ──
    cells_elem = ET.SubElement(piece, "Cells")

    conn_text: list[str] = []
    offsets: list[str] = []
    types: list[str] = []
    offset = 0

    for elem_type, elem_nodes in mesh.elements:
        indices = [str(id_to_index[n]) for n in elem_nodes if n in id_to_index]
        if not indices:
            continue
        conn_text.append(" ".join(indices))
        offset += len(indices)
        offsets.append(str(offset))
        vtk_type = _FRD_TO_VTK_ELEM.get(elem_type)
        if vtk_type is None:
            vtk_type = _guess_vtk_type(len(indices))
        types.append(str(vtk_type))

    ET.SubElement(cells_elem, "DataArray", {
        "type": "Int32", "Name": "connectivity", "format": "ascii",
    }).text = "\n".join(conn_text)

    ET.SubElement(cells_elem, "DataArray", {
        "type": "Int32", "Name": "offsets", "format": "ascii",
    }).text = "\n".join(offsets)

    ET.SubElement(cells_elem, "DataArray", {
        "type": "UInt8", "Name": "types", "format": "ascii",
    }).text = "\n".join(types)

    # ── PointData ──
    pd_elem = ET.SubElement(piece, "PointData")

    # von Mises stress
    if step.stresses:
        ET.SubElement(pd_elem, "DataArray", {
            "type": "Float32", "Name": "von_mises_mpa",
            "NumberOfComponents": "1", "format": "ascii",
        }).text = "\n".join(
            f"{_von_mises(*step.stresses.get(nid, [0.0]*6)[:6]):.6f}"
            if len(step.stresses.get(nid, [0.0]*6)) >= 6 else "0.000000"
            for nid in node_ids
        )

        # Principal stresses
        ET.SubElement(pd_elem, "DataArray", {
            "type": "Float32", "Name": "principal_stress",
            "NumberOfComponents": "4", "format": "ascii",
        }).text = "\n".join(
            " ".join(f"{v:.6f}" for v in _principal(*step.stresses.get(nid, [0.0]*6)[:6]))
            if len(step.stresses.get(nid, [0.0]*6)) >= 6 else "0.000000 0.000000 0.000000 0.000000"
            for nid in node_ids
        )

    # von Mises strain
    if step.strains:
        ET.SubElement(pd_elem, "DataArray", {
            "type": "Float32", "Name": "von_mises_strain",
            "NumberOfComponents": "1", "format": "ascii",
        }).text = "\n".join(
            f"{_von_mises(*step.strains.get(nid, [0.0]*6)[:6]):.6e}"
            if len(step.strains.get(nid, [0.0]*6)) >= 6 else "0.000000e+00"
            for nid in node_ids
        )

        ET.SubElement(pd_elem, "DataArray", {
            "type": "Float32", "Name": "principal_strain",
            "NumberOfComponents": "4", "format": "ascii",
        }).text = "\n".join(
            " ".join(f"{v:.6e}" for v in _principal(*step.strains.get(nid, [0.0]*6)[:6]))
            if len(step.strains.get(nid, [0.0]*6)) >= 6 else "0.000000e+00 0.000000e+00 0.000000e+00 0.000000e+00"
            for nid in node_ids
        )

    # Displacement vectors
    if step.displacements:
        ET.SubElement(pd_elem, "DataArray", {
            "type": "Float32", "Name": "displacement_mm",
            "NumberOfComponents": "3", "format": "ascii",
        }).text = "\n".join(
            f"{d[0]:.6f} {d[1]:.6f} {d[2]:.6f}"
            for d in (step.displacements.get(nid, [0.0, 0.0, 0.0]) for nid in node_ids)
        )

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        '<?xml version="1.0"?>\n' + ET.tostring(vtkfile, encoding="unicode"),
        encoding="utf-8",
    )


# ── PVD collection writer ─────────────────────────────────────


def _write_pvd_xml(pvd_path: Path, base_name: str, steps: list[FrdStep]) -> None:
    """Write ParaView Data (PVD) collection for time-series animation."""
    n = len(steps)
    padding = len(str(n)) if n > 1 else 1

    lines = [
        '<?xml version="1.0"?>',
        '<VTKFile type="Collection" version="0.1" byte_order="LittleEndian">',
        '  <Collection>',
    ]
    for i, step in enumerate(steps):
        num = f".{i + 1:0{padding}}" if n > 1 else ""
        lines.append(
            f'    <DataSet part="{i}" file="{base_name}{num}.vtu"'
            f' timestep="{step.inc}"/>'
        )
    lines.append('  </Collection>')
    lines.append('</VTKFile>')
    pvd_path.parent.mkdir(parents=True, exist_ok=True)
    pvd_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Public API ─────────────────────────────────────────────────


def _merge_steps(steps: list[FrdStep]) -> FrdStep:
    """Merge all steps into one for backward-compatible single-file output.

    Each step may carry a different result type (e.g. step 1 = DISP,
    step 2 = STRESS).  Merge collects all data into a flat step so the
    legacy VTK contains displacements AND stresses in one file.
    """
    merged = FrdStep()
    for s in steps:
        merged.displacements.update(s.displacements)
        merged.stresses.update(s.stresses)
        merged.strains.update(s.strains)
    return merged


def frd_to_vtk(frd_path: Path, vtk_path: Path) -> dict:
    """Convert CalculiX .frd file to legacy ASCII VTK.

    Backward-compatible signature. All result steps are merged into one
    VTK file so displacement and stress data appear together — matching
    the original behaviour of the single-step parser.

    Returns {max_displacement_mm, max_von_mises_mpa}.
    """
    mesh, steps = _parse_frd_file(frd_path)

    if not mesh.nodes:
        raise ValueError(f"No nodes found in FRD: {frd_path}")

    step = _merge_steps(steps) if steps else FrdStep()
    node_ids = sorted(mesh.nodes.keys())
    id_to_index = {nid: idx for idx, nid in enumerate(node_ids)}

    return _write_vtk_ascii(frd_path, vtk_path, mesh, step, node_ids, id_to_index)


def frd_convert(
    frd_path: Path,
    output_dir: Path,
    base_name: str = "solver_result",
) -> dict:
    """Convert CalculiX .frd to VTU (+PVD if multi-step) and legacy VTK.

    Args:
        frd_path: Path to the .frd file.
        output_dir: Directory to write output files.
        base_name: Base filename stem (default: "solver_result").

    Returns:
        dict with max_displacement_mm, max_von_mises_mpa from the last step.
    """
    mesh, steps = _parse_frd_file(frd_path)

    if not mesh.nodes:
        raise ValueError(f"No nodes found in FRD: {frd_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    node_ids = sorted(mesh.nodes.keys())
    id_to_index = {nid: idx for idx, nid in enumerate(node_ids)}

    if not steps:
        empty = FrdStep()
        _write_vtu_xml(output_dir / f"{base_name}.vtu", mesh, empty, node_ids, id_to_index)
        return _write_vtk_ascii(frd_path, output_dir / f"{base_name}.vtk", mesh, empty, node_ids, id_to_index)

    n = len(steps)
    padding = len(str(n)) if n > 1 else 1

    # Write per-step VTU
    for i, step in enumerate(steps):
        num = f".{i + 1:0{padding}}" if n > 1 else ""
        _write_vtu_xml(
            output_dir / f"{base_name}{num}.vtu",
            mesh, step, node_ids, id_to_index,
        )

    # PVD for multi-step
    if n > 1:
        _write_pvd_xml(output_dir / f"{base_name}.pvd", base_name, steps)

    # Legacy VTK from last step
    last_step = steps[-1]
    return _write_vtk_ascii(
        frd_path, output_dir / f"{base_name}.vtk",
        mesh, last_step, node_ids, id_to_index,
    )

"""Tests for frd_to_vtk — FRD parsing, VTK/VTU generation, backward compat."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simfea_api.frd_to_vtk import (
    _parse_frd_file,
    _von_mises,
    _principal,
    frd_to_vtk,
    frd_convert,
    FrdMesh,
    FrdStep,
)

# Sample FRD with two steps: DISP (step 1) + STRESS (step 2)
# Format matches real CalculiX v2.10 output.
SAMPLE_FRD = """    1C
    1USimFEA Studio Test Case
    1UUSER
    1UPGM               CalculiX
    1UVERSION           Version 2.10
    2C                             8                                     1
 -1         1 0.000000E+00 0.000000E+00 0.000000E+00
 -1         2 1.000000E+00 0.000000E+00 0.000000E+00
 -1         3 1.000000E+00 1.000000E+00 0.000000E+00
 -1         4 0.000000E+00 1.000000E+00 0.000000E+00
 -1         5 0.000000E+00 0.000000E+00 1.000000E+00
 -1         6 1.000000E+00 0.000000E+00 1.000000E+00
 -1         7 1.000000E+00 1.000000E+00 1.000000E+00
 -1         8 0.000000E+00 1.000000E+00 1.000000E+00
 -3
    3C                             1                                     1
 -1         1    1    0    1
 -2         1         2         3         4         5         6         7         8
 -3
    1PSTEP                         1           1           1
  100CL  101 1.000000000           8                     0    1           1
 -4  DISP        3    1
 -5  D1          1    2    1    0
 -5  D2          1    2    2    0
 -5  D3          1    2    3    0
 -5  ALL         1    2    0    0    1ALL
 -1         1 0.000000E+00 0.000000E+00 0.000000E+00
 -1         2 0.000000E+00-1.200000E-01 0.000000E+00
 -1         3 0.000000E+00 0.000000E+00 0.000000E+00
 -1         4 0.000000E+00 0.000000E+00 0.000000E+00
 -1         5 0.000000E+00 0.000000E+00 0.000000E+00
 -1         6 0.000000E+00 0.000000E+00 0.000000E+00
 -1         7 0.000000E+00 0.000000E+00 0.000000E+00
 -1         8 0.000000E+00 0.000000E+00 0.000000E+00
 -3
    1PSTEP                         2           1           1
  100CL  101 1.000000000           8                     0    1           1
 -4  STRESS      6    1
 -5  SXX         1    4    1    1
 -5  SYY         1    4    2    2
 -5  SZZ         1    4    3    3
 -5  SXY         1    4    1    2
 -5  SYZ         1    4    2    3
 -5  SZX         1    4    3    1
 -1         1 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00
 -1         2 0.000000E+00 2.500000E+01 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00
 -1         3 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00
 -1         4 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00
 -1         5 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00
 -1         6 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00
 -1         7 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00
 -1         8 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00 0.000000E+00
 -3
  9999
"""

# Single-step FRD (only DISP, no STRESS)
SINGLE_STEP_FRD = """    1C
    1UPGM               CalculiX
    2C                             8                                     1
 -1         1 0.000000E+00 0.000000E+00 0.000000E+00
 -1         2 1.000000E+00 0.000000E+00 0.000000E+00
 -1         3 1.000000E+00 1.000000E+00 0.000000E+00
 -1         4 0.000000E+00 1.000000E+00 0.000000E+00
 -1         5 0.000000E+00 0.000000E+00 1.000000E+00
 -1         6 1.000000E+00 0.000000E+00 1.000000E+00
 -1         7 1.000000E+00 1.000000E+00 1.000000E+00
 -1         8 0.000000E+00 1.000000E+00 1.000000E+00
 -3
    3C                             1                                     1
 -1         1    1    0    1
 -2         1         2         3         4         5         6         7         8
 -3
    1PSTEP                         1           1           1
  100CL  101 1.000000000           8                     0    1           1
 -4  DISP        3    1
 -5  D1          1    2    1    0
 -5  D2          1    2    2    0
 -5  D3          1    2    3    0
 -5  ALL         1    2    0    0    1ALL
 -1         1 0.000000E+00 0.000000E+00 0.000000E+00
 -1         2 0.000000E+00-1.200000E-01 0.000000E+00
 -1         3 0.000000E+00 0.000000E+00 0.000000E+00
 -1         4 0.000000E+00 0.000000E+00 0.000000E+00
 -1         5 0.000000E+00 0.000000E+00 0.000000E+00
 -1         6 0.000000E+00 0.000000E+00 0.000000E+00
 -1         7 0.000000E+00 0.000000E+00 0.000000E+00
 -1         8 0.000000E+00 0.000000E+00 0.000000E+00
 -3
  9999
"""


class ParseFrdFileTest(unittest.TestCase):
    """Tests for the stream-based _parse_frd_file."""

    def test_extracts_nodes_and_elements(self):
        mesh, steps = _parse_frd_file(
            _temp_frd(SAMPLE_FRD)
        )
        self.assertEqual(len(mesh.nodes), 8)
        self.assertEqual(len(mesh.elements), 1)
        self.assertEqual(mesh.elements[0][0], 1)  # C3D8 type
        self.assertEqual(mesh.elements[0][1], [1, 2, 3, 4, 5, 6, 7, 8])

    def test_parses_two_steps(self):
        mesh, steps = _parse_frd_file(
            _temp_frd(SAMPLE_FRD)
        )
        self.assertEqual(len(steps), 2)
        # Step 1: displacements only
        self.assertEqual(steps[0].step, 1)
        self.assertIn(2, steps[0].displacements)
        self.assertAlmostEqual(steps[0].displacements[2][1], -0.12, places=3)
        # Step 2: stresses only
        self.assertEqual(steps[1].step, 1)  # same step number, different data type
        self.assertIn(2, steps[1].stresses)
        self.assertAlmostEqual(steps[1].stresses[2][1], 25.0, places=1)

    def test_single_step_frd(self):
        mesh, steps = _parse_frd_file(
            _temp_frd(SINGLE_STEP_FRD)
        )
        self.assertEqual(len(steps), 1)
        self.assertTrue(steps[0].displacements)
        self.assertFalse(steps[0].stresses)

    def test_node_coordinates(self):
        mesh, _ = _parse_frd_file(_temp_frd(SAMPLE_FRD))
        self.assertAlmostEqual(mesh.nodes[1][0], 0.0)
        self.assertAlmostEqual(mesh.nodes[2][0], 1.0)


class MathTest(unittest.TestCase):
    """Tests for von Mises and principal value calculations."""

    def test_von_mises_zero(self):
        self.assertEqual(_von_mises(0, 0, 0, 0, 0, 0), 0.0)

    def test_von_mises_uniaxial(self):
        # Pure uniaxial stress σxx = 100, von Mises = 100
        vm = _von_mises(100, 0, 0, 0, 0, 0)
        self.assertAlmostEqual(vm, 100.0, places=1)

    def test_von_mises_shear(self):
        # Pure shear τ = 50, von Mises = √3 * |τ| ≈ 86.6
        vm = _von_mises(0, 0, 0, 50, 0, 0)
        self.assertAlmostEqual(vm, 86.6025, places=3)

    def test_principal_uniaxial(self):
        p = _principal(100, 0, 0, 0, 0, 0)
        self.assertAlmostEqual(p[0], 0.0, places=6)   # min
        self.assertAlmostEqual(p[2], 100.0, places=6)  # max
        self.assertEqual(p[3], 100.0)                   # worst = max

    def test_principal_hydrostatic(self):
        p = _principal(50, 50, 50, 0, 0, 0)
        self.assertAlmostEqual(p[0], 50.0, places=6)
        self.assertAlmostEqual(p[2], 50.0, places=6)

    def test_principal_zero(self):
        p = _principal(0, 0, 0, 0, 0, 0)
        self.assertEqual(p, (0.0, 0.0, 0.0, 0.0))


class FrdToVtkBackCompatTest(unittest.TestCase):
    """Verify frd_to_vtk() back-compat: same signature, same results."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_converts_beam_frd_to_vtk(self):
        frd_path = self.tmp / "beam.frd"
        vtk_path = self.tmp / "beam.vtk"
        frd_path.write_text(SAMPLE_FRD, encoding="utf-8")

        metrics = frd_to_vtk(frd_path, vtk_path)

        self.assertTrue(vtk_path.exists())
        self.assertGreater(metrics["max_displacement_mm"], 0.0)
        self.assertGreater(metrics["max_von_mises_mpa"], 0.0)

    def test_vtk_output_has_expected_sections(self):
        frd_path = self.tmp / "beam.frd"
        vtk_path = self.tmp / "beam.vtk"
        frd_path.write_text(SAMPLE_FRD, encoding="utf-8")

        frd_to_vtk(frd_path, vtk_path)
        content = vtk_path.read_text(encoding="utf-8")

        self.assertIn("DATASET UNSTRUCTURED_GRID", content)
        self.assertIn("POINTS 8 float", content)
        self.assertIn("CELLS 1", content)
        self.assertIn("von_mises_mpa", content)
        self.assertIn("displacement_mm", content)
        # New: principal stresses included
        self.assertIn("principal_stress", content)

    def test_extracts_metrics_from_beam(self):
        frd_path = self.tmp / "beam.frd"
        vtk_path = self.tmp / "beam.vtk"
        frd_path.write_text(SAMPLE_FRD, encoding="utf-8")

        metrics = frd_to_vtk(frd_path, vtk_path)

        # Merged steps: DISP from step 1, STRESS from step 2
        self.assertAlmostEqual(metrics["max_displacement_mm"], 0.12, places=2)
        self.assertAlmostEqual(metrics["max_von_mises_mpa"], 25.0, places=3)

    def test_rejects_empty_frd(self):
        frd_path = self.tmp / "empty.frd"
        vtk_path = self.tmp / "empty.vtk"
        frd_path.write_text("  9999\n", encoding="utf-8")

        with self.assertRaises(ValueError):
            frd_to_vtk(frd_path, vtk_path)


class FrdConvertTest(unittest.TestCase):
    """Tests for the new frd_convert() multi-step API."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_multi_step_produces_per_step_vtu(self):
        frd_path = self.tmp / "beam.frd"
        frd_path.write_text(SAMPLE_FRD, encoding="utf-8")
        out_dir = self.tmp / "out"

        metrics = frd_convert(frd_path, out_dir, "solver_result")

        self.assertIn("max_von_mises_mpa", metrics)
        self.assertTrue((out_dir / "solver_result.vtk").exists())
        self.assertTrue((out_dir / "solver_result.1.vtu").exists())
        self.assertTrue((out_dir / "solver_result.2.vtu").exists())
        self.assertTrue((out_dir / "solver_result.pvd").exists())

    def test_vtu_output_has_correct_structure(self):
        frd_path = self.tmp / "beam.frd"
        frd_path.write_text(SAMPLE_FRD, encoding="utf-8")
        out_dir = self.tmp / "out"

        frd_convert(frd_path, out_dir, "solver_result")

        vtu_content = (out_dir / "solver_result.2.vtu").read_text(encoding="utf-8")
        self.assertIn("UnstructuredGrid", vtu_content)
        self.assertIn("von_mises_mpa", vtu_content)
        self.assertIn("principal_stress", vtu_content)
        self.assertIn('format="ascii"', vtu_content)

    def test_pvd_collection_structure(self):
        frd_path = self.tmp / "beam.frd"
        frd_path.write_text(SAMPLE_FRD, encoding="utf-8")
        out_dir = self.tmp / "out"

        frd_convert(frd_path, out_dir, "solver_result")

        pvd = (out_dir / "solver_result.pvd").read_text(encoding="utf-8")
        self.assertIn('<VTKFile type="Collection"', pvd)
        self.assertIn('solver_result.1.vtu', pvd)
        self.assertIn('solver_result.2.vtu', pvd)

    def test_single_step_no_pvd(self):
        frd_path = self.tmp / "single.frd"
        frd_path.write_text(SINGLE_STEP_FRD, encoding="utf-8")
        out_dir = self.tmp / "out"

        frd_convert(frd_path, out_dir, "solver_result")

        self.assertTrue((out_dir / "solver_result.vtk").exists())
        self.assertTrue((out_dir / "solver_result.vtu").exists())
        # Single step → no PVD needed
        self.assertFalse((out_dir / "solver_result.pvd").exists())

    def test_element_type_frd_1_is_hex(self):
        """FRD element type 1 (C3D8) → VTK type 12 (HEXAHEDRON)."""
        frd_path = self.tmp / "beam.frd"
        frd_path.write_text(SAMPLE_FRD, encoding="utf-8")
        out_dir = self.tmp / "out"

        frd_convert(frd_path, out_dir, "solver_result")

        vtk_content = (out_dir / "solver_result.vtk").read_text(encoding="utf-8")
        # CELL_TYPES section should have 12 (hex)
        self.assertIn("CELL_TYPES 1", vtk_content)
        self.assertIn("  12", vtk_content)


def _temp_frd(content: str) -> Path:
    """Write FRD content to a temp file, return path."""
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".frd", mode="w", encoding="utf-8", delete=False)
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


if __name__ == "__main__":
    unittest.main()

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simfea_api.frd_to_vtk import _parse_frd_sections, _parse_nodes, _parse_elements, frd_to_vtk

# Real CalculiX v2.10 FRD format: 2C/3C for geometry, 1PSTEP for results.
# Result data uses -4 DISP / -4 STRESS descriptors and -5 component descriptors,
# NOT legacy 2D/2S section headers.
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


class ParseFrdSectionsTest(unittest.TestCase):
    def test_extracts_all_sections(self):
        sections = _parse_frd_sections(SAMPLE_FRD)
        self.assertIn("2C", sections)
        self.assertIn("3C", sections)
        self.assertIn("2D", sections)
        self.assertIn("2S", sections)

    def test_coordinates_section(self):
        sections = _parse_frd_sections(SAMPLE_FRD)
        nodes = _parse_nodes(sections["2C"])
        self.assertEqual(len(nodes), 8)
        self.assertAlmostEqual(nodes[1][0], 0.0)
        self.assertAlmostEqual(nodes[2][0], 1.0)

    def test_elements_section(self):
        sections = _parse_frd_sections(SAMPLE_FRD)
        elements = _parse_elements(sections["3C"])
        self.assertEqual(len(elements), 1)
        # format -2: [n1..n8] — 8 hex nodes
        self.assertEqual(elements[0], [1, 2, 3, 4, 5, 6, 7, 8])


class FrdToVtkTest(unittest.TestCase):
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

    def test_extracts_metrics_from_beam(self):
        frd_path = self.tmp / "beam.frd"
        vtk_path = self.tmp / "beam.vtk"
        frd_path.write_text(SAMPLE_FRD, encoding="utf-8")

        metrics = frd_to_vtk(frd_path, vtk_path)

        self.assertAlmostEqual(metrics["max_displacement_mm"], 0.12, places=3)
        self.assertAlmostEqual(metrics["max_von_mises_mpa"], 25.0, places=3)

    def test_rejects_empty_frd(self):
        frd_path = self.tmp / "empty.frd"
        vtk_path = self.tmp / "empty.vtk"
        frd_path.write_text("  9999\n", encoding="utf-8")

        with self.assertRaises(ValueError):
            frd_to_vtk(frd_path, vtk_path)


if __name__ == "__main__":
    unittest.main()

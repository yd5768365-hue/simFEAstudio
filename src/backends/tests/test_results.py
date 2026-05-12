import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simfea_api.results import (
    generate_cantilever_vtk_artifact,
    generate_result_summary,
    parse_key_value_text,
    parse_optional_float,
    parse_optional_int,
    primary_vtk_artifact,
    run_artifacts,
)


class ParseKeyValueTextTest(unittest.TestCase):
    def test_parses_simple_pairs(self):
        result = parse_key_value_text("a=1\nb=2")
        self.assertEqual(result, {"a": "1", "b": "2"})

    def test_skips_lines_without_equals(self):
        result = parse_key_value_text("header\nkey=value\nfooter")
        self.assertEqual(result, {"key": "value"})

    def test_strips_whitespace_around_key_value(self):
        result = parse_key_value_text("  key  =  value  ")
        self.assertEqual(result, {"key": "value"})

    def test_handles_equals_in_value(self):
        result = parse_key_value_text("cmd=echo hello=world")
        self.assertEqual(result, {"cmd": "echo hello=world"})

    def test_handles_empty_string(self):
        result = parse_key_value_text("")
        self.assertEqual(result, {})


class ParseOptionalFloatTest(unittest.TestCase):
    def test_parses_float_string(self):
        self.assertEqual(parse_optional_float("3.14"), 3.14)

    def test_parses_int_string(self):
        self.assertEqual(parse_optional_float("42"), 42.0)

    def test_returns_none_for_none(self):
        self.assertIsNone(parse_optional_float(None))

    def test_returns_none_for_empty_string(self):
        self.assertIsNone(parse_optional_float(""))

    def test_returns_none_for_non_numeric(self):
        self.assertIsNone(parse_optional_float("abc"))

    def test_parses_int_value(self):
        self.assertEqual(parse_optional_float(42), 42.0)


class ParseOptionalIntTest(unittest.TestCase):
    def test_parses_int_string(self):
        self.assertEqual(parse_optional_int("42"), 42)

    def test_truncates_float_to_int(self):
        self.assertEqual(parse_optional_int("3.14"), 3)

    def test_returns_none_for_none(self):
        self.assertIsNone(parse_optional_int(None))

    def test_returns_none_for_non_numeric(self):
        self.assertIsNone(parse_optional_int("abc"))


class PrimaryVtkArtifactTest(unittest.TestCase):
    def test_finds_vtk(self):
        self.assertEqual(primary_vtk_artifact(["dir/a.vtk", "dir/b.txt"]), "dir/a.vtk")

    def test_finds_vtu(self):
        self.assertEqual(primary_vtk_artifact(["dir/a.vtu", "dir/b.txt"]), "dir/a.vtu")

    def test_prefers_vtk_over_vtu(self):
        self.assertEqual(
            primary_vtk_artifact(["artifacts/result.vtu", "artifacts/result.vtk"]),
            "artifacts/result.vtk",
        )

    def test_returns_empty_for_no_match(self):
        self.assertEqual(primary_vtk_artifact(["dir/a.txt"]), "")

    def test_returns_empty_for_empty_list(self):
        self.assertEqual(primary_vtk_artifact([]), "")


class RunArtifactsTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_empty_for_missing_artifacts_dir(self):
        self.assertEqual(run_artifacts(self.run_dir), [])

    def test_lists_artifact_files(self):
        adir = self.run_dir / "artifacts"
        adir.mkdir()
        (adir / "result.txt").touch()
        (adir / "mesh.vtk").touch()
        artifacts = run_artifacts(self.run_dir)
        self.assertIn("artifacts/mesh.vtk", artifacts)
        self.assertIn("artifacts/result.txt", artifacts)

    def test_excludes_summary_when_asked(self):
        adir = self.run_dir / "artifacts"
        adir.mkdir()
        (adir / "result_summary.json").touch()
        (adir / "result.txt").touch()
        artifacts = run_artifacts(self.run_dir, include_summary=False)
        self.assertEqual(artifacts, ["artifacts/result.txt"])

    def test_includes_summary_by_default(self):
        adir = self.run_dir / "artifacts"
        adir.mkdir()
        (adir / "result_summary.json").touch()
        (adir / "result.txt").touch()
        artifacts = run_artifacts(self.run_dir)
        self.assertIn("artifacts/result_summary.json", artifacts)
        self.assertIn("artifacts/result.txt", artifacts)


class GenerateCantileverVtkTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_creates_vtk_file_and_returns_path(self):
        path = generate_cantilever_vtk_artifact(self.run_dir, displacement_mm=0.5, stress_mpa=30.0)
        self.assertEqual(path, "artifacts/cantilever_result.vtk")
        vtk_file = self.run_dir / path
        self.assertTrue(vtk_file.exists())
        content = vtk_file.read_text(encoding="utf-8")
        self.assertIn("POINTS", content)
        self.assertIn("POLYGONS", content)

    def test_uses_default_values_when_none(self):
        path = generate_cantilever_vtk_artifact(self.run_dir, displacement_mm=None, stress_mpa=None)
        self.assertTrue((self.run_dir / path).exists())


class GenerateResultSummaryTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_returns_none_for_missing_meta(self):
        self.assertIsNone(generate_result_summary(self.run_dir))

    def test_generates_summary_from_meta(self):
        meta = {
            "run_id": "test-run",
            "case_name": "cantilever",
            "solver": "demo-shell",
            "runner": "SSHRunner",
            "status": "finished",
            "exit_code": 0,
            "created_at": "2026-01-01T00:00:00Z",
            "started_at": "2026-01-01T00:01:00Z",
            "finished_at": "2026-01-01T00:02:00Z",
            "compute_node": "test-node",
            "compute_node_label": "Test Node",
            "remote_workdir": "/tmp/remote",
            "local_archive": str(self.run_dir),
            "command": "echo test",
            "solver_kind": "cantilever_beam",
        }
        (self.run_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        (self.run_dir / "stdout.log").touch()
        summary = generate_result_summary(self.run_dir)
        self.assertIsNotNone(summary)
        self.assertEqual(summary["run_id"], "test-run")
        self.assertEqual(summary["case_name"], "cantilever")
        self.assertEqual(summary["status"], "finished")

    def test_parses_stdout_and_result_text(self):
        meta = {
            "run_id": "test-run",
            "case_name": "static",
            "solver": "calculix",
            "solver_kind": "static",
            "runner": "SSHRunner",
            "status": "finished",
            "exit_code": 0,
            "created_at": "2026-01-01T00:00:00Z",
            "compute_node": "test-node",
            "compute_node_label": "Test",
            "remote_workdir": "/tmp/remote",
            "local_archive": str(self.run_dir),
            "command": "echo test",
        }
        (self.run_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        (self.run_dir / "stdout.log").write_text(
            "max_displacement_mm=2.5\nmax_von_mises_mpa=180.0\n", encoding="utf-8"
        )
        adir = self.run_dir / "artifacts"
        adir.mkdir()
        (adir / "result.txt").write_text("solver=calculix\n", encoding="utf-8")
        summary = generate_result_summary(self.run_dir)
        self.assertEqual(summary["metrics"]["max_displacement_mm"], 2.5)
        self.assertEqual(summary["metrics"]["max_von_mises_mpa"], 180.0)
        self.assertEqual(summary["solver"], "calculix")

    def test_solver_summary_uses_archived_vtu(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run_solver"
            artifacts_dir = run_dir / "artifacts"
            artifacts_dir.mkdir(parents=True)
            (artifacts_dir / "mesh.vtu").write_text("<VTKFile></VTKFile>\n", encoding="utf-8")
            (artifacts_dir / "result.txt").write_text(
                "solver=elmer\nstatus=success\nexit_code=0\n",
                encoding="utf-8",
            )
            (run_dir / "stdout.log").write_text("hostname=node01\n", encoding="utf-8")
            (run_dir / "meta.json").write_text(
                json.dumps(
                    {
                        "run_id": "run_solver",
                        "case_name": "Elmer adapter run",
                        "solver": "elmer",
                        "solver_kind": "multiphysics",
                        "runner": "SolverRunner",
                        "status": "finished",
                        "exit_code": 0,
                    }
                ),
                encoding="utf-8",
            )

            summary = generate_result_summary(run_dir)

        self.assertIsNotNone(summary)
        self.assertEqual(summary["case_type"], "multiphysics")
        self.assertEqual(summary["visualization"]["vtk_artifact"], "artifacts/mesh.vtu")
        self.assertTrue(summary["visualization"]["ready"])


if __name__ == "__main__":
    unittest.main()

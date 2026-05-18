import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simfea_api.learning import (
    build_plain_learning_record,
    compose_note_md,
    generate_learning_report,
    sanitize_filename_part,
)


class SanitizeFilenamePartTest(unittest.TestCase):
    def test_preserves_clean_string(self):
        result = sanitize_filename_part("hello_world")
        self.assertEqual(result, "hello_world")

    def test_replaces_special_chars(self):
        result = sanitize_filename_part('foo:bar<baz>')
        self.assertEqual(result, "foo_bar_baz")

    def test_replaces_spaces(self):
        result = sanitize_filename_part("hello world")
        self.assertEqual(result, "hello_world")

    def test_returns_fallback_for_none(self):
        result = sanitize_filename_part(None, fallback="fallback")
        self.assertEqual(result, "fallback")

    def test_returns_fallback_for_empty(self):
        result = sanitize_filename_part("", fallback="default")
        self.assertEqual(result, "default")

    def test_trims_to_80_chars(self):
        long_name = "a" * 100
        result = sanitize_filename_part(long_name)
        self.assertEqual(len(result), 80)

    def test_strips_leading_trailing_dots_and_underscores(self):
        result = sanitize_filename_part("__test__.txt", fallback="x")
        self.assertEqual(result, "test__.txt")


class BuildPlainLearningRecordTest(unittest.TestCase):
    def setUp(self):
        self.meta = {
            "run_id": "run-001",
            "case_name": "cantilever",
            "solver": "calculix",
            "runner": "SSHRunner",
            "compute_node": "node1",
            "compute_node_label": "Node 1",
            "status": "finished",
            "exit_code": 0,
            "local_archive": "/tmp/run-001",
            "remote_workdir": "/remote/run-001",
        }

    def test_builds_record_with_all_fields(self):
        summary = {
            "metrics": {
                "max_displacement_mm": 2.5,
                "max_von_mises_mpa": 180.0,
            }
        }
        record = build_plain_learning_record(self.meta, "report content", "my note", summary)
        self.assertIn("run-001", record)
        self.assertIn("calculix", record)
        self.assertIn("最大位移 mm：2.5", record)
        self.assertIn("最大 Von Mises MPa：180.0", record)
        self.assertIn("my note", record)
        self.assertIn("report content", record)

    def test_handles_none_summary(self):
        record = build_plain_learning_record(self.meta, "report", "note", None)
        self.assertIn("最大位移 mm：无", record)

    def test_handles_empty_note(self):
        record = build_plain_learning_record(self.meta, "report", "", {})
        self.assertIn("尚未填写。", record)


class GenerateLearningReportTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_raises_for_missing_meta_json(self):
        with self.assertRaises(FileNotFoundError):
            generate_learning_report(self.run_dir)

    def test_generates_report_and_returns_path(self):
        meta = {
            "run_id": "r1",
            "case_name": "beam",
            "solver": "demo-shell",
            "runner": "SSHRunner",
            "status": "finished",
            "exit_code": 0,
            "created_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:01:00Z",
            "compute_node": "test",
            "compute_node_label": "Test",
            "local_archive": str(self.run_dir),
            "remote_workdir": "/tmp/remote",
            "command": "echo test",
            "scheduler": None,
        }
        (self.run_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        (self.run_dir / "note.md").write_text("my note", encoding="utf-8")
        (self.run_dir / "stdout.log").write_text("line1\nline2", encoding="utf-8")
        (self.run_dir / "stderr.log").write_text("", encoding="utf-8")
        (self.run_dir / "artifacts").mkdir(parents=True)
        (self.run_dir / "artifacts" / "result.txt").write_text("result data", encoding="utf-8")

        report_path = generate_learning_report(self.run_dir)
        self.assertTrue(report_path.exists())
        content = report_path.read_text(encoding="utf-8")
        self.assertIn("SimFEA Studio 学习沉淀报告", content)
        self.assertIn("beam", content)
        self.assertIn("my note", content)
        self.assertIn("result data", content)

    def test_includes_scheduler_info_for_slurm_run(self):
        meta = {
            "run_id": "r2",
            "case_name": "slurm-beam",
            "solver": "demo-shell",
            "runner": "SlurmRunner",
            "status": "finished",
            "exit_code": 0,
            "created_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:01:00Z",
            "compute_node": "hpc",
            "compute_node_label": "HPC",
            "local_archive": str(self.run_dir),
            "remote_workdir": "/tmp/remote",
            "command": "sbatch job.slurm",
            "scheduler": "slurm",
            "job_id": "12345",
            "partition": "compute",
            "allocated_node": "node01",
            "requested_cpus": 8,
            "requested_memory": "16G",
            "last_scheduler_state": "COMPLETED",
        }
        (self.run_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        (self.run_dir / "note.md").touch()
        (self.run_dir / "stdout.log").touch()
        (self.run_dir / "stderr.log").touch()
        (self.run_dir / "artifacts").mkdir(parents=True)
        (self.run_dir / "artifacts" / "result.txt").touch()

        report_path = generate_learning_report(self.run_dir)
        content = report_path.read_text(encoding="utf-8")
        self.assertIn("12345", content)
        self.assertIn("node01", content)
        self.assertIn("COMPLETED", content)

    def test_next_steps_reuse_structured_next_answer(self):
        meta = {
            "run_id": "r3",
            "case_name": "beam",
            "solver": "calculix",
            "runner": "SolverRunner",
            "status": "finished",
            "exit_code": 0,
            "created_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:01:00Z",
            "compute_node": "local",
            "compute_node_label": "Local",
            "local_archive": str(self.run_dir),
            "remote_workdir": "",
            "command": "ccx cantilever",
        }
        (self.run_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        (self.run_dir / "note.md").write_text(
            compose_note_md({"next": "mesh=2mm, load=-120N"}, meta),
            encoding="utf-8",
        )
        (self.run_dir / "stdout.log").touch()
        (self.run_dir / "stderr.log").touch()
        (self.run_dir / "artifacts").mkdir(parents=True)
        (self.run_dir / "artifacts" / "result.txt").touch()

        report_path = generate_learning_report(self.run_dir)
        content = report_path.read_text(encoding="utf-8")

        self.assertIn("已记录的下次调整：mesh=2mm, load=-120N", content)


if __name__ == "__main__":
    unittest.main()

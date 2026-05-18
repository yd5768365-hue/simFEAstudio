import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simfea_api.run_archive import (
    RemoteRun,
    append_text,
    ensure_run_files,
    load_archived_runs,
    remember_run_event,
    read_optional_text,
    read_tail,
    replay_run_events,
    run_metadata,
)

from tests.factories import create_finished_run, create_run, create_slurm_run


class RunMetadataTest(unittest.TestCase):
    def test_returns_expected_keys(self):
        run = create_run()
        meta = run_metadata(run)

        self.assertEqual(meta["run_id"], run.run_id)
        self.assertEqual(meta["case_name"], "test-cantilever")
        self.assertEqual(meta["solver"], "demo-shell")
        self.assertEqual(meta["runner"], "SSHRunner")
        self.assertEqual(meta["status"], "created")

    def test_finished_run_reflects_status(self):
        run = create_finished_run()
        meta = run_metadata(run)

        self.assertEqual(meta["status"], "finished")
        self.assertEqual(meta["exit_code"], 0)
        self.assertIsNotNone(meta["started_at"])
        self.assertIsNotNone(meta["finished_at"])

    def test_slurm_run_includes_scheduler_fields(self):
        run = create_slurm_run()
        meta = run_metadata(run)

        self.assertEqual(meta["scheduler"], "slurm")
        self.assertEqual(meta["partition"], "compute")
        self.assertEqual(meta["requested_cpus"], 4)
        self.assertEqual(meta["requested_memory"], "8G")

    def test_solver_run_includes_archived_input_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = create_run(
                local_dir=Path(tmp) / "run_solver",
                artifacts_dir=Path(tmp) / "run_solver" / "artifacts",
                runner="SolverRunner",
                solver="calculix",
                input_files={"cantilever.inp": "*HEADING\n", "nested/case.txt": "hello\n"},
            )
            ensure_run_files(run)

            meta = run_metadata(run)

        self.assertEqual(meta["input_files"], ["inputs/cantilever.inp", "inputs/nested/case.txt"])


class LoadArchivedRunsTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tmpdir.name) / "config.json"
        self.previous_runs_root = os.environ.get("SIMFEA_RUNS_ROOT")
        self.previous_config_path = os.environ.get("SIMFEA_CONFIG_PATH")
        self.config_path.write_text("{}", encoding="utf-8")
        os.environ["SIMFEA_RUNS_ROOT"] = self.tmpdir.name
        os.environ["SIMFEA_CONFIG_PATH"] = str(self.config_path)

    def tearDown(self):
        if self.previous_runs_root is None:
            os.environ.pop("SIMFEA_RUNS_ROOT", None)
        else:
            os.environ["SIMFEA_RUNS_ROOT"] = self.previous_runs_root
        if self.previous_config_path is None:
            os.environ.pop("SIMFEA_CONFIG_PATH", None)
        else:
            os.environ["SIMFEA_CONFIG_PATH"] = self.previous_config_path
        self.tmpdir.cleanup()

    def test_includes_result_summary_payload(self):
        run_dir = Path(self.tmpdir.name) / "run-001"
        artifacts_dir = run_dir / "artifacts"
        artifacts_dir.mkdir(parents=True)
        (run_dir / "meta.json").write_text(
            json.dumps(
                {
                    "run_id": "run-001",
                    "case_name": "beam",
                    "solver": "calculix",
                    "runner": "SolverRunner",
                    "compute_node": "local",
                    "status": "finished",
                    "created_at": "2026-05-13T00:00:00Z",
                    "remote_workdir": "",
                    "local_archive": str(run_dir),
                    "artifacts": ["artifacts/result_summary.json"],
                }
            ),
            encoding="utf-8",
        )
        (artifacts_dir / "result_summary.json").write_text(
            json.dumps(
                {
                    "run_id": "run-001",
                    "metrics": {
                        "max_displacement_mm": 8.933,
                        "max_von_mises_mpa": 37.502,
                    },
                }
            ),
            encoding="utf-8",
        )

        runs = load_archived_runs()

        self.assertEqual(runs[0]["result_summary"], "artifacts/result_summary.json")
        self.assertEqual(runs[0]["summary"]["metrics"]["max_displacement_mm"], 8.933)

    def test_keeps_run_when_result_summary_is_invalid(self):
        run_dir = Path(self.tmpdir.name) / "run-002"
        artifacts_dir = run_dir / "artifacts"
        artifacts_dir.mkdir(parents=True)
        (run_dir / "meta.json").write_text(
            json.dumps(
                {
                    "run_id": "run-002",
                    "case_name": "beam",
                    "solver": "calculix",
                    "runner": "SolverRunner",
                    "compute_node": "local",
                    "status": "finished",
                    "created_at": "2026-05-13T00:00:00Z",
                    "remote_workdir": "",
                    "local_archive": str(run_dir),
                    "artifacts": ["artifacts/result_summary.json"],
                }
            ),
            encoding="utf-8",
        )
        (artifacts_dir / "result_summary.json").write_text("{", encoding="utf-8")

        runs = load_archived_runs()

        self.assertEqual(runs[0]["run_id"], "run-002")
        self.assertEqual(runs[0]["result_summary"], "artifacts/result_summary.json")
        self.assertNotIn("summary", runs[0])


class AppendReadRoundtripTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tmpdir.name) / "test.log"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_write_and_read(self):
        append_text(self.path, "line one")
        append_text(self.path, "line two")

        content = read_optional_text(self.path)
        self.assertEqual(content, "line one\nline two\n")

    def test_read_missing_returns_default(self):
        missing = Path(self.tmpdir.name) / "nope.log"
        result = read_optional_text(missing, default="n/a")
        self.assertEqual(result, "n/a")


class RunEventBufferTest(unittest.TestCase):
    def test_replay_returns_events_after_sequence(self):
        run = create_run()
        remember_run_event(run, {"seq": 1, "type": "stdout", "line": "one"})
        remember_run_event(run, {"seq": 2, "type": "stdout", "line": "two"})
        remember_run_event(run, {"seq": 3, "type": "finished", "line": "done"})

        replayed = replay_run_events(run, from_seq=1)

        self.assertEqual([event["seq"] for event in replayed], [2, 3])

    def test_replay_without_sequence_is_empty_for_legacy_clients(self):
        run = create_run()
        remember_run_event(run, {"seq": 1, "type": "stdout", "line": "one"})

        replayed = replay_run_events(run, from_seq=None)

        self.assertEqual(replayed, [])

    def test_event_buffer_keeps_recent_events(self):
        run = create_run()
        for seq in range(5):
            remember_run_event(run, {"seq": seq, "type": "stdout"}, limit=3)

        self.assertEqual([event["seq"] for event in run.event_buffer], [2, 3, 4])


class ReadTailTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tmpdir.name) / "tail.log"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_limits_to_max_lines(self):
        for i in range(10):
            append_text(self.path, f"line {i:02d}")
        tail = read_tail(self.path, max_lines=3)
        expected = "line 07\nline 08\nline 09"
        self.assertEqual(tail, expected)

    def test_empty_file_returns_placeholder(self):
        self.path.touch()
        tail = read_tail(self.path)
        self.assertEqual(tail, "暂无")

    def test_fewer_lines_than_max(self):
        append_text(self.path, "only")
        append_text(self.path, "two")
        tail = read_tail(self.path, max_lines=10)
        self.assertEqual(tail, "only\ntwo")


if __name__ == "__main__":
    unittest.main()

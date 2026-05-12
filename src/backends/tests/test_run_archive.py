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

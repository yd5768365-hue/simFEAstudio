import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simfea_api.cleanup import cleanup_old_runs
from simfea_api.config import AppSettings


def _make_settings(runs_root: Path, retention_days: int = 90, max_runs: int = 100) -> AppSettings:
    return AppSettings(
        api_port=8008,
        api_public_host="localhost",
        runs_root=runs_root,
        learning_export_root=Path("/tmp/learning"),
        learning_formats=["md"],
        learning_default_format="md",
        config_path=Path("/tmp/config.json"),
        ssh_exe="ssh",
        scp_exe="scp",
        compute_nodes={},
        default_compute_node="",
        solvers={},
        toolchain=[],
        run_retention_days=retention_days,
        max_runs=max_runs,
    )


def _create_run(run_dir: Path, run_id: str, created_at: str):
    run_dir.mkdir(parents=True)
    (run_dir / "meta.json").write_text(
        json.dumps({"run_id": run_id, "created_at": created_at}), encoding="utf-8"
    )


class CleanupOldRunsTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.runs_root = Path(self.tmpdir.name)
        self.now = datetime(2026, 5, 12, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_no_runs_root(self):
        settings = _make_settings(self.runs_root / "missing")
        result = cleanup_old_runs(settings, now=self.now)
        self.assertEqual(result["removed"], 0)
        self.assertEqual(result["kept"], 0)
        self.assertIn("no runs root", result["reason"])

    def test_no_runs_found(self):
        settings = _make_settings(self.runs_root)
        result = cleanup_old_runs(settings, now=self.now)
        self.assertEqual(result["removed"], 0)
        self.assertEqual(result["kept"], 0)

    def test_removes_runs_older_than_retention(self):
        _create_run(self.runs_root / "old-run", "r1", "2026-01-01T00:00:00Z")
        _create_run(self.runs_root / "new-run", "r2", "2026-05-10T00:00:00Z")

        settings = _make_settings(self.runs_root, retention_days=30, max_runs=100)
        result = cleanup_old_runs(settings, now=self.now)

        self.assertEqual(result["removed"], 1)
        self.assertEqual(result["kept"], 1)
        self.assertFalse((self.runs_root / "old-run").exists())
        self.assertTrue((self.runs_root / "new-run").exists())

    def test_removes_excess_runs_over_max_count(self):
        for i in range(5):
            _create_run(
                self.runs_root / f"run-{i}",
                f"r{i}",
                f"2026-05-{(i+1):02d}T00:00:00Z",
            )

        settings = _make_settings(self.runs_root, retention_days=90, max_runs=2)
        result = cleanup_old_runs(settings, now=self.now)

        self.assertEqual(result["removed"], 3)
        self.assertEqual(result["kept"], 2)
        self.assertFalse((self.runs_root / "run-0").exists())
        self.assertFalse((self.runs_root / "run-1").exists())
        self.assertFalse((self.runs_root / "run-2").exists())
        self.assertTrue((self.runs_root / "run-3").exists())
        self.assertTrue((self.runs_root / "run-4").exists())

    def test_both_retention_and_max_runs_applied(self):
        # Old runs removed by retention
        _create_run(self.runs_root / "old-1", "r-old", "2025-01-01T00:00:00Z")
        _create_run(self.runs_root / "old-2", "r-old2", "2025-06-01T00:00:00Z")
        # New runs, but too many
        _create_run(self.runs_root / "new-1", "r1", "2026-05-01T00:00:00Z")
        _create_run(self.runs_root / "new-2", "r2", "2026-05-03T00:00:00Z")
        _create_run(self.runs_root / "new-3", "r3", "2026-05-05T00:00:00Z")

        settings = _make_settings(self.runs_root, retention_days=30, max_runs=1)
        result = cleanup_old_runs(settings, now=self.now)

        self.assertEqual(result["removed"], 4)
        self.assertEqual(result["kept"], 1)
        self.assertTrue((self.runs_root / "new-3").exists())

    def test_handles_missing_created_at_in_meta(self):
        run_dir = self.runs_root / "no-date"
        run_dir.mkdir(parents=True)
        (run_dir / "meta.json").write_text(
            json.dumps({"run_id": "r1"}), encoding="utf-8"
        )
        old_time = (self.now - timedelta(days=200)).timestamp()
        os.utime(str(run_dir), (old_time, old_time))

        settings = _make_settings(self.runs_root, retention_days=30, max_runs=100)
        result = cleanup_old_runs(settings, now=self.now)

        self.assertEqual(result["removed"], 1)
        self.assertFalse(run_dir.exists())


if __name__ == "__main__":
    unittest.main()

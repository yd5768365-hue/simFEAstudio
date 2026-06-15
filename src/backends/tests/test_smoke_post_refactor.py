"""Runtime smoke test after execution refactor."""
import sys
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

BACKENDS = Path(__file__).resolve().parent.parent
if str(BACKENDS) not in sys.path:
    sys.path.insert(0, str(BACKENDS))

from main import app


class PostRefactorSmokeTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_get_config(self):
        r = self.client.get("/v1/config")
        self.assertEqual(r.status_code, 200)
        self.assertIn("data", r.json())

    def test_get_solvers(self):
        r = self.client.get("/v1/solvers")
        self.assertEqual(r.status_code, 200)
        self.assertIn("data", r.json())

    def test_get_runs(self):
        r = self.client.get("/v1/runs")
        self.assertEqual(r.status_code, 200)
        self.assertIn("data", r.json())

    def test_get_experiment_files(self):
        r = self.client.get("/v1/experiment/files")
        self.assertEqual(r.status_code, 200)
        self.assertIn("data", r.json())

    def test_read_experiment_file_path_style(self):
        # Read a known benchmark file using path-style parameter
        # Note: actual benchmark directories use Chinese names
        r = self.client.get("/v1/experiment/files/learning/benchmarks/01_一维杆拉伸/问题描述.md")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("data", body)
        self.assertIn("content", body["data"])
        self.assertIn("杆", body["data"]["content"])


if __name__ == "__main__":
    unittest.main()

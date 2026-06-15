import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

fastapi_stub = types.ModuleType("fastapi")


class _RouterStub:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda fn: fn


class _HTTPExceptionStub(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


fastapi_stub.APIRouter = _RouterStub
fastapi_stub.HTTPException = _HTTPExceptionStub

try:
    import fastapi  # noqa: F401
except ImportError:
    sys.modules["fastapi"] = fastapi_stub

from src.backends.routers import benchmarks


class BenchmarkRouterTests(unittest.TestCase):
    def test_list_benchmarks_includes_case_metadata_and_learning_tier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case_dir = root / "01_rod"
            case_dir.mkdir()
            (case_dir / "case.json").write_text(
                json.dumps(
                    {
                        "group": "basic",
                        "title": "Rod Tension",
                        "level": "L1",
                        "physics": "structural",
                        "dimension": "1D rod",
                        "methods": ["analytic", "calculix"],
                        "status": "completed",
                    }
                ),
                encoding="utf-8",
            )
            (case_dir / "problem.md").write_text("# Rod Tension\n\nMinimal benchmark.", encoding="utf-8")
            (case_dir / "results").mkdir()
            (case_dir / "results" / "comparison.csv").write_text("method,value\nanalytic,1\n", encoding="utf-8")

            original_root = benchmarks.BENCHMARKS_DIR
            benchmarks.BENCHMARKS_DIR = root
            try:
                response = benchmarks.list_benchmarks()
            finally:
                benchmarks.BENCHMARKS_DIR = original_root

        case = response["data"]["cases"][0]
        self.assertEqual(case["group"], "basic")
        self.assertEqual(case["title"], "Rod Tension")
        self.assertEqual(case["level"], "L1")
        self.assertEqual(case["physics"], "structural")
        self.assertEqual(case["dimension"], "1D rod")
        self.assertEqual(case["methods"], ["analytic", "calculix"])
        self.assertEqual(case["status"], "completed")
        self.assertEqual(
            case["learning_tier"],
            {"id": "L1", "label": "L1 Example", "focus": "result observation"},
        )

    def test_get_benchmark_case_includes_case_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case_dir = root / "02_beam"
            case_dir.mkdir()
            (case_dir / "case.json").write_text(
                json.dumps(
                    {
                        "group": "extended",
                        "title": "Beam Bending",
                        "level": "L2",
                        "physics": "structural",
                        "dimension": "1D beam",
                        "methods": ["analytic"],
                        "status": "draft",
                    }
                ),
                encoding="utf-8",
            )
            (case_dir / "problem.md").write_text("# Beam Bending\n", encoding="utf-8")
            (case_dir / "results").mkdir()
            (case_dir / "results" / "comparison.csv").write_text(
                "method,u_L_mm,error_u_L_mm,notes\nanalytic,1,0,baseline\n",
                encoding="utf-8",
            )

            original_root = benchmarks.BENCHMARKS_DIR
            benchmarks.BENCHMARKS_DIR = root
            try:
                response = benchmarks.get_benchmark_case("02_beam")
            finally:
                benchmarks.BENCHMARKS_DIR = original_root

        detail = response["data"]
        self.assertEqual(detail["group"], "extended")
        self.assertEqual(detail["title"], "Beam Bending")
        self.assertEqual(detail["level"], "L2")
        self.assertEqual(detail["learning_tier"]["label"], "L2 Benchmark")
        self.assertEqual(detail["results"][0]["method"], "analytic")


if __name__ == "__main__":
    unittest.main()

import importlib.util
import tempfile
import unittest
from pathlib import Path


def load_import_benchmarks_module():
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "import-benchmarks.py"
    spec = importlib.util.spec_from_file_location("import_benchmarks", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ImportBenchmarksScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.import_benchmarks = load_import_benchmarks_module()

    def test_default_run_does_not_write_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "benchmarks"

            exit_code = self.import_benchmarks.main(["--output-dir", str(output_dir)])

            self.assertEqual(0, exit_code)
            self.assertFalse(output_dir.exists())

    def test_write_flag_creates_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "benchmarks"

            exit_code = self.import_benchmarks.main(["--write", "--output-dir", str(output_dir)])

            self.assertEqual(0, exit_code)
            self.assertTrue((output_dir / "06_圆轴扭转" / "问题描述.md").is_file())
            self.assertTrue((output_dir / "13_平面二杆桁架" / "results" / "对比结果.csv").is_file())


if __name__ == "__main__":
    unittest.main()

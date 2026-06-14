import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "build_benchmark_learning_path.py"
spec = importlib.util.spec_from_file_location("build_benchmark_learning_path", SCRIPT_PATH)
build_benchmark_learning_path = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_benchmark_learning_path)
build_learning_path = build_benchmark_learning_path.build_learning_path


class BenchmarkLearningPathTests(unittest.TestCase):
    def test_learning_path_groups_cases_by_mfem_style_tiers(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for dirname, title, level in [
                ("01_rod", "一维杆拉伸", "L1"),
                ("03_beam", "悬臂梁弯曲", "L2"),
                ("05_preflight", "预检查演示", "L3"),
            ]:
                case_dir = root / dirname
                case_dir.mkdir()
                (case_dir / "case.json").write_text(
                    '{"title":"%s","level":"%s","physics":"结构力学",'
                    '"dimension":"1D","methods":["analytic","calculix"],"status":"completed"}'
                    % (title, level),
                    encoding="utf-8",
                )

            markdown = build_learning_path(root)

            self.assertIn("## L1 Example", markdown)
            self.assertIn("| `01_rod` | 一维杆拉伸 |", markdown)
            self.assertIn("## L2 Benchmark", markdown)
            self.assertIn("| `03_beam` | 悬臂梁弯曲 |", markdown)
            self.assertIn("## L3 Miniapp", markdown)
            self.assertIn("| `05_preflight` | 预检查演示 |", markdown)

    def test_learning_path_includes_fenicsx_style_learning_flow(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case_dir = root / "01_rod"
            case_dir.mkdir()
            (case_dir / "case.json").write_text(
                '{"title":"一维杆拉伸","level":"L1","physics":"结构力学",'
                '"dimension":"1D 杆","methods":["analytic"],"status":"completed"}',
                encoding="utf-8",
            )

            markdown = build_learning_path(root)

            self.assertIn("物理问题 -> 离散化 -> 求解方法 -> 派生量 -> 复盘问题", markdown)
            self.assertIn("结构力学", markdown)
            self.assertIn("1D 杆", markdown)


if __name__ == "__main__":
    unittest.main()

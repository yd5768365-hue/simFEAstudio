import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "check_benchmark_contract.py"
spec = importlib.util.spec_from_file_location("check_benchmark_contract", SCRIPT_PATH)
check_benchmark_contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_benchmark_contract)
check_case = check_benchmark_contract.check_case
workflow_stage_coverage = check_benchmark_contract.workflow_stage_coverage


class BenchmarkContractTests(unittest.TestCase):
    def test_valid_case_passes(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp) / "case"
            case_dir.mkdir()
            (case_dir / "case.json").write_text(
                '{"title":"Rod","methods":["analytic"],"level":"L1"}',
                encoding="utf-8",
            )
            (case_dir / "问题描述.md").write_text("# Rod\n", encoding="utf-8")
            (case_dir / "calculix").mkdir()
            (case_dir / "calculix" / "rod.inp").write_text("*HEADING\n", encoding="utf-8")
            (case_dir / "results").mkdir()
            (case_dir / "results" / "对比结果.csv").write_text(
                "method,value\nanalytic,1\n",
                encoding="utf-8",
            )

            self.assertEqual(check_case(case_dir), [])

    def test_missing_problem_description_is_reported(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp) / "case"
            case_dir.mkdir()
            (case_dir / "case.json").write_text(
                '{"title":"Rod","methods":["analytic"],"level":"L1"}',
                encoding="utf-8",
            )

            self.assertIn("missing problem markdown", check_case(case_dir))

    def test_declared_workflow_stages_must_cover_openfoam_style_case_flow(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp) / "case"
            case_dir.mkdir()
            (case_dir / "case.json").write_text(
                '{"title":"Rod","methods":["analytic"],"level":"L1",'
                '"workflow_stages":["geometry","solver","evidence"]}',
                encoding="utf-8",
            )
            (case_dir / "问题描述.md").write_text("# Rod\n", encoding="utf-8")
            (case_dir / "results").mkdir()
            (case_dir / "results" / "对比结果.csv").write_text(
                "method,value\nanalytic,1\n",
                encoding="utf-8",
            )

            self.assertIn("missing workflow stage: mesh", check_case(case_dir))
            self.assertIn("missing workflow stage: post", check_case(case_dir))

    def test_existing_case_files_can_imply_workflow_stage_coverage(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp) / "case"
            case_dir.mkdir()
            (case_dir / "case.json").write_text(
                '{"title":"Rod","methods":["analytic"],"level":"L1"}',
                encoding="utf-8",
            )
            (case_dir / "问题描述.md").write_text("# Rod\n", encoding="utf-8")
            (case_dir / "calculix").mkdir()
            (case_dir / "calculix" / "rod.inp").write_text("*HEADING\n", encoding="utf-8")
            (case_dir / "results").mkdir()
            (case_dir / "results" / "对比结果.csv").write_text(
                "method,value\nanalytic,1\n",
                encoding="utf-8",
            )

            self.assertEqual(workflow_stage_coverage(case_dir), {"geometry", "mesh", "solver", "post", "evidence"})
            self.assertEqual(check_case(case_dir), [])

    def test_case_metadata_can_imply_discretization_and_solver_stages(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp) / "case"
            case_dir.mkdir()
            (case_dir / "case.json").write_text(
                '{"title":"Rod","methods":["analytic","calculix"],"level":"L1","dimension":"1D 杆"}',
                encoding="utf-8",
            )
            (case_dir / "问题描述.md").write_text("# Rod\n", encoding="utf-8")
            (case_dir / "results").mkdir()
            (case_dir / "results" / "对比结果.csv").write_text(
                "method,value\nanalytic,1\n",
                encoding="utf-8",
            )

            self.assertEqual(workflow_stage_coverage(case_dir), {"geometry", "mesh", "solver", "post", "evidence"})
            self.assertEqual(check_case(case_dir), [])


if __name__ == "__main__":
    unittest.main()

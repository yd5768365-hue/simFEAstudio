import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simfea_api.config import SolverDefinition, settings
from simfea_api.runners.solver import (
    build_solver_probe_command,
    build_solver_run_script,
    public_solver,
    render_command_template,
)
from simfea_api.runners.remote_files import build_remote_artifact_list_script
from simfea_api.runners.workflow import (
    FREECAD_PREPOMAX_WORKFLOW_ALIAS,
    public_freecad_prepomax_workflow,
    workflow_artifact_patterns,
)
from tests.factories import create_run


class SolverConfigTest(unittest.TestCase):
    def test_default_solvers_are_loaded(self):
        solvers = settings().solvers

        self.assertIn("calculix", solvers)
        self.assertIn("freecad", solvers)
        self.assertIn("prepomax", solvers)
        self.assertIn("prepomax-regenerate", solvers)
        self.assertIn("openfoam", solvers)
        self.assertIn("elmer", solvers)

    def test_default_solver_install_specs_are_loaded(self):
        install_specs = settings().solver_install_specs

        self.assertIn("calculix", install_specs)
        self.assertIn("freecad", install_specs)
        self.assertIn("prepomax", install_specs)
        self.assertIn("FreeCADCmd.exe", install_specs["freecad"].executable_candidates)
        self.assertEqual(install_specs["calculix"].install_mode, "managed_or_external")


class SolverRunnerTest(unittest.TestCase):
    def test_public_solver_omits_input_templates(self):
        solver = SolverDefinition(
            alias="calculix",
            label="CalculiX",
            kind="structural",
            executable="ccx",
            command_template="ccx cantilever",
            input_files={"cantilever.inp": "content"},
            artifact_patterns=["*.frd", "result.txt"],
            pre_commands=["module load calculix"],
            post_commands=["grep 'U' cantilever.dat"],
        )

        data = public_solver(solver)

        self.assertEqual(data["alias"], "calculix")
        self.assertEqual(data["pre_commands"], ["module load calculix"])
        self.assertEqual(data["post_commands"], ["grep 'U' cantilever.dat"])
        self.assertNotIn("input_files", data)

    def test_probe_command_contains_each_solver_alias(self):
        command = build_solver_probe_command(list(settings().solvers.values()))

        self.assertIn("calculix=", command)
        self.assertIn("freecad=", command)
        self.assertIn("prepomax=", command)
        self.assertIn("prepomax-regenerate=", command)
        self.assertIn("openfoam=", command)
        self.assertIn("elmer=", command)

    def test_freecad_adapter_writes_macro(self):
        run = create_run(run_id="run_freecad")
        solver = settings().solvers["freecad"]

        script = build_solver_run_script(run, solver)

        self.assertIn("freecad_smoke.py", script)
        self.assertIn("freecad_smoke.step", script)
        self.assertIn("import FreeCAD as App", script)
        self.assertIn(solver.executable, script)

    def test_prepomax_adapter_is_explicit_placeholder(self):
        solver = settings().solvers["prepomax"]

        self.assertIn("placeholder", solver.description.lower())
        self.assertIn("-r", solver.description)
        self.assertIn("--help", solver.command_template)
        self.assertIn("README.prepomax.txt", solver.input_files)

    def test_prepomax_regenerate_uses_official_cli(self):
        solver = settings().solvers["prepomax-regenerate"]

        self.assertIn("-r", solver.command_template)
        self.assertIn("-g No", solver.command_template)
        self.assertIn("-w .", solver.command_template)
        self.assertIn("README.prepomax-regenerate.txt", solver.input_files)

    def test_render_command_template_supports_placeholders(self):
        run = create_run(run_id="run_abc")
        solver = settings().solvers["calculix"]

        command = render_command_template("echo {run_id} ${solver_alias}", run, solver)

        self.assertEqual(command, "echo run_abc calculix")

    def test_run_script_writes_inputs_and_result(self):
        run = create_run(run_id="run_abc")
        solver = settings().solvers["calculix"]

        script = build_solver_run_script(run, solver)

        self.assertIn("cantilever.inp", script)
        self.assertIn("result.txt", script)
        self.assertIn("command=", script)

    def test_pre_post_commands_appear_in_run_script(self):
        run = create_run(run_id="run_pre_post")
        solver = SolverDefinition(
            alias="test-solver",
            label="Test",
            kind="structural",
            executable="test_exe",
            command_template="test_exe input.dat",
            input_files={},
            artifact_patterns=["result.txt"],
            pre_commands=["echo 'setup'", "mkdir -p /tmp/scratch"],
            post_commands=["echo 'teardown'", "cp *.out results/"],
        )

        script = build_solver_run_script(run, solver)

        self.assertIn("pre_command=", script)
        self.assertIn("echo 'setup'", script)
        self.assertIn("mkdir -p /tmp/scratch", script)
        self.assertIn("post_command=", script)
        self.assertIn("echo 'teardown'", script)
        self.assertIn("cp *.out results/", script)
        # Pre commands appear before the solver command, post commands after
        pre_pos = script.index("pre_command=")
        cmd_pos = script.index("command=")
        post_pos = script.index("post_command=")
        self.assertLess(pre_pos, cmd_pos)
        self.assertLess(cmd_pos, post_pos)

    def test_artifact_list_script_expands_configured_globs(self):
        script = build_remote_artifact_list_script(["*.frd", "postProcessing/**", "result.txt"])

        self.assertIn("shopt -s nullglob globstar", script)
        self.assertIn("for f in '*.frd'; do", script)
        self.assertIn("for match in $f; do", script)
        self.assertIn("for f in 'postProcessing/**'; do", script)

    def test_freecad_prepomax_workflow_merges_artifacts(self):
        solvers = [settings().solvers["freecad"], settings().solvers["prepomax-regenerate"]]

        workflow = public_freecad_prepomax_workflow(solvers)

        self.assertEqual(workflow["alias"], FREECAD_PREPOMAX_WORKFLOW_ALIAS)
        self.assertEqual([step["alias"] for step in workflow["steps"]], ["freecad", "prepomax-regenerate"])
        self.assertIn("*.FCStd", workflow_artifact_patterns(solvers))
        self.assertIn("*.frd", workflow_artifact_patterns(solvers))
        self.assertIn("result.txt", workflow_artifact_patterns(solvers))


if __name__ == "__main__":
    unittest.main()

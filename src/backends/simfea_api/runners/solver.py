from string import Template

from ..config import SolverDefinition
from ..run_archive import RemoteRun
from .ssh import sh_quote


def public_solver(solver: SolverDefinition) -> dict:
    return {
        "alias": solver.alias,
        "label": solver.label,
        "kind": solver.kind,
        "executable": solver.executable,
        "description": solver.description,
        "artifact_patterns": solver.artifact_patterns,
        "pre_commands": solver.pre_commands,
        "post_commands": solver.post_commands,
    }


def render_command_template(template: str, run: RemoteRun, solver: SolverDefinition) -> str:
    values = {
        "run_id": run.run_id,
        "remote_workdir": run.remote_workdir,
        "solver_alias": solver.alias,
        "solver_executable": solver.executable,
    }
    rendered = Template(template).safe_substitute(values)
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


def build_solver_probe_command(solvers: list[SolverDefinition]) -> str:
    lines = ["set +e"]
    for solver in solvers:
        lines.append(f"printf '{solver.alias}='")
        lines.append(f"command -v {sh_quote(solver.executable)} 2>/dev/null || true")
    return "\n".join(lines)


def build_solver_run_script(run: RemoteRun, solver: SolverDefinition) -> str:
    input_blocks = []
    for name, content in solver.input_files.items():
        input_blocks.append(
            "\n".join(
                [
                    f"mkdir -p {sh_quote('/'.join(name.split('/')[:-1]))}" if "/" in name else "",
                    f"cat > {sh_quote(name)} <<'SIMFEA_INPUT_EOF'",
                    content.rstrip(),
                    "SIMFEA_INPUT_EOF",
                ]
            ).strip()
        )

    pre_blocks = "\n".join(
        f'echo "pre_command={sh_quote(cmd)}"\n{cmd}' for cmd in solver.pre_commands
    )
    post_blocks = "\n".join(
        f'echo "post_command={sh_quote(cmd)}"\n{cmd}' for cmd in solver.post_commands
    )

    artifact_patterns = " ".join(sh_quote(pattern) for pattern in solver.artifact_patterns)
    command = render_command_template(solver.command_template, run, solver)

    return f"""
set -e
RUN_ID={sh_quote(run.run_id)}
REMOTE_WORKDIR={sh_quote(run.remote_workdir)}
SOLVER_ALIAS={sh_quote(solver.alias)}
SOLVER_EXECUTABLE={sh_quote(solver.executable)}
mkdir -p "$REMOTE_WORKDIR"
cd "$REMOTE_WORKDIR"
echo "SimFEA Studio solver run started"
echo "run_id=$RUN_ID"
echo "solver=$SOLVER_ALIAS"
echo "hostname=$(hostname)"
echo "user=$(whoami)"
echo "workdir=$(pwd)"
if ! command -v "$SOLVER_EXECUTABLE" >/dev/null 2>&1; then
  echo "Solver executable not found: $SOLVER_EXECUTABLE" >&2
  exit 127
fi
{chr(10).join(input_blocks)}
{pre_blocks}
echo "command={command}"
set +e
{command}
exit_code=$?
set -e
{post_blocks}
cat > result.txt <<EOF
SimFEA Studio solver result
run_id=$RUN_ID
solver=$SOLVER_ALIAS
solver_executable=$SOLVER_EXECUTABLE
hostname=$(hostname)
status=$([ "$exit_code" -eq 0 ] && echo success || echo failed)
exit_code=$exit_code
artifact_patterns={artifact_patterns}
EOF
echo "artifact=result.txt"
echo "SimFEA Studio solver run finished with exit_code=$exit_code"
exit "$exit_code"
"""
